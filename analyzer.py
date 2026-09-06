"""Combine signals into a scored ranking; Claude judges which candidates are truly actionable."""
import json
import re
import anthropic

SYSTEM = (
    "You are a skeptical stock analyst. You "
    "receive JSON for tickers that passed technical screens (volume, breakout, RSI), "
    "each with a facts pack (analyst target upside %, position in 52-week range, "
    "trailing P/E, beta, 30d volatility), Yahoo sentiment, and upcoming earnings. "
    "For EACH candidate, first build the strongest bear case from the actual "
    "numbers: overextension near 52-week highs, rich valuation, earnings gap risk "
    "vs its historical move, volatility that dwarfs the upside, sentiment froth "
    "chasing a move already made. Upcoming earnings are event risk to weigh "
    "against the setup, not a bonus — compare the historical post-earnings move "
    "to the claimed upside. Then rank the candidates and pass ONLY the single "
    "best one whose concrete upside clearly outweighs its own bear case. Pass "
    "two only if a second is just as clearly worth it. You are choosing the best "
    "available setup, not certifying a sure thing — some doubt is normal and is "
    "not by itself a reason to reject. Return an empty picks list only when every "
    "candidate's bear case actually wins on its numbers. Respond with ONLY this "
    "JSON, no other text: "
    '{"picks": [{"ticker": "XYZ", "line": "XYZ $price — setup and upside\\n'
    'Risks: the 1-2 strongest reasons NOT to buy\\nVerdict: why it is worth it '
    'anyway\\nInvalid below: $<level>"}]}. Each line value is 3-4 short '
    "plain-text lines joined by \\n, under 480 chars, citing the actual numbers, "
    "strongest pick first, no financial-advice disclaimers. The final line must "
    "always be the invalidation level — the candidate's stop_ref, or a tighter "
    "level if its own numbers justify one — so every alert states what would "
    "prove the setup wrong. Output the JSON object and nothing else: no prose, no code fences, no keys beyond \"ticker\" and \"line\", no ticker that was not in the candidates I sent. Use {\"picks\": []} when nothing qualifies."
)


def signal_types(s):
    """How many independent signal families fired (volume, breakout, RSI, earnings)."""
    return (bool(s.get("unusual_volume")) + bool(s.get("breakout_20d"))
            + bool(s.get("rsi_oversold") or s.get("rsi_overbought"))
            + ("earnings" in s))


def rank(signals, sentiment, earnings):
    """Attach a composite score to each signal dict and return sorted descending."""
    for s in signals:
        t = s["ticker"]
        score = 2.0 * s.get("unusual_volume", False)
        score += 2.0 * s.get("breakout_20d", False)
        # RSI is directional, the alert is not: overbought on a fresh breakout is a
        # caution, so it subtracts. signal_types() still counts it as the RSI family
        # firing — confluence measures independent evidence, not direction.
        score += 1.0 * s.get("rsi_oversold", False)
        score -= 1.0 * s.get("rsi_overbought", False)
        sent = sentiment.get(t)
        if sent:
            # Headline tone only, capped at +/-1.5. There used to be a mention-count
            # bonus too, but Yahoo's comments endpoint has 403'd since Jul 2026, so
            # the count was always 0 and the term was dead weight.
            score += max(-3, min(3, sent["sentiment"])) * 0.5
            s["yahoo_sentiment"] = sent
        if t in earnings:
            # No score bonus: the judge prompt treats an upcoming report as event
            # risk, so paying +2.0 for it here had the scorer and the judge
            # disagreeing. Still attached, and still a signal family.
            s["earnings"] = earnings[t]
        s["score"] = round(score, 1)
    return sorted(signals, key=lambda s: s["score"], reverse=True)


def _close_open_brackets(s):
    """Append the brackets Claude left open, or return s unchanged if a string is open.

    Observed 2026-07-24: a reply ended `..."}]` — valid JSON one `}` short, with
    stop_reason end_turn, so not a truncation that more max_tokens would fix. The
    greedy regex below then compounds it by matching to the LAST `}`, eating the
    closing `]` too, and a correctly-judged pick was silently dropped.

    An unterminated string means the reply died mid-sentence; those are left to fail
    so a half-written alert never goes out. Quote-aware, so a brace inside a line
    value is not counted.
    """
    stack, in_str, esc = [], False, False
    for ch in s:
        if esc:
            esc = False
        elif in_str and ch == "\\":
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif stack and ch == stack[-1]:
                stack.pop()
    return s if in_str else s + "".join(reversed(stack))


MAX_PICKS = 3
MAX_LINE_CHARS = 480
PICK_KEYS = {"ticker", "line"}

# The judge's output contract. Documented here, demanded by SYSTEM, and enforced by
# validate_picks(); all three must be changed together.
#
#   {"picks": [ {"ticker": "<one of the candidate tickers>",
#                "line":   "<3-4 plain-text lines joined by \\n, <=480 chars,
#                            last line 'Invalid below: $<level>'>"} ]}
#
# picks is required and may be empty (a legitimate "nothing qualifies"), at most
# MAX_PICKS entries, no duplicate tickers, no keys beyond PICK_KEYS. Anything else
# is a JudgeFormatError, never a silent zero-pick run.
SCHEMA_REMINDER = (
    'Your previous reply did not match the required schema: {reason}\n'
    'Reply again with ONLY this JSON and nothing else — no prose, no code fences:\n'
    '{{"picks": [{{"ticker": "XYZ", "line": "XYZ $price — setup and upside\\n'
    'Risks: ...\\nVerdict: ...\\nInvalid below: $<level>"}}]}}\n'
    'Use "picks": [] if no candidate qualifies. Only tickers from the candidates '
    'I sent. Each line must be under 480 characters and must end with the '
    '"Invalid below: $<level>" line.'
)


class JudgeFormatError(ValueError):
    """Claude's reply did not match the pick schema. Never swallow this quietly."""


def _extract_json(text):
    """Best-effort recovery of the JSON object from a reply. Returns a dict or None.

    Extraction is allowed to be forgiving — prose, code fences and a missing
    closing brace are model quirks, not schema violations. Two attempts: the
    greedy `{...}` match, then the same text with unclosed brackets repaired.
    What the object *contains* is judged strictly, by validate_picks().
    """
    start = text.find("{")
    if start < 0:
        return None
    blob = re.search(r"\{.*\}", text, re.S)
    attempts = ([blob.group()] if blob else []) + [_close_open_brackets(text[start:])]
    for attempt in attempts:
        try:
            obj = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def validate_picks(obj, valid):
    """Return the picks list, or raise JudgeFormatError naming exactly what is wrong.

    Strict on purpose. The old filter dropped bad picks silently, so an alert could
    go out with no invalidation level and a run with a mangled reply was
    indistinguishable in the logs from a genuine "nothing qualifies".
    """
    if not isinstance(obj, dict):
        raise JudgeFormatError(f"top level is {type(obj).__name__}, expected an object")
    if "picks" not in obj:
        raise JudgeFormatError(f"no 'picks' key; got keys {sorted(obj)}")
    picks = obj["picks"]
    if not isinstance(picks, list):
        raise JudgeFormatError(f"'picks' is {type(picks).__name__}, expected a list")
    if len(picks) > MAX_PICKS:
        raise JudgeFormatError(f"{len(picks)} picks, at most {MAX_PICKS} allowed")
    seen = set()
    for i, p in enumerate(picks):
        where = f"picks[{i}]"
        if not isinstance(p, dict):
            raise JudgeFormatError(f"{where} is {type(p).__name__}, expected an object")
        extra = set(p) - PICK_KEYS
        if extra:
            raise JudgeFormatError(f"{where} has unexpected key(s) {sorted(extra)}")
        missing = PICK_KEYS - set(p)
        if missing:
            raise JudgeFormatError(f"{where} is missing key(s) {sorted(missing)}")
        t, line = p["ticker"], p["line"]
        if not isinstance(t, str):
            raise JudgeFormatError(f"{where}.ticker is {type(t).__name__}, expected a string")
        if t not in valid:
            raise JudgeFormatError(
                f"{where}.ticker {t!r} was not one of the candidates {sorted(valid)}")
        if t in seen:
            raise JudgeFormatError(f"{where}.ticker {t!r} appears twice")
        seen.add(t)
        if not isinstance(line, str):
            raise JudgeFormatError(f"{where}.line is {type(line).__name__}, expected a string")
        if not line.strip():
            raise JudgeFormatError(f"{where}.line is empty")
        if len(line) > MAX_LINE_CHARS:
            raise JudgeFormatError(
                f"{where}.line is {len(line)} chars, over the {MAX_LINE_CHARS} budget")
        if "Invalid below" not in line:
            raise JudgeFormatError(
                f"{where}.line has no 'Invalid below: $<level>' line — every alert "
                "must state what would prove it wrong")
    return picks


def parse_picks(text, valid):
    """Parse and validate a judge reply. Raises JudgeFormatError on anything off-schema."""
    obj = _extract_json(text)
    if obj is None:
        raise JudgeFormatError(
            "no JSON object found in the reply: " + repr(text[:300]))
    return validate_picks(obj, valid)


# Set by judge() on every call. parse_picks is silent when the reply has no braces,
# so a genuine rejection, a prose-only reply and a truncated one all look like 0 picks
# in the logs. judge_smoke.py prints these to tell them apart. ponytail: globals, not a
# return-tuple, so no caller has to change.
LAST_REPLY = ""
LAST_STOP_REASON = ""


def judge(candidates, client=None):
    """Ask Claude which candidates merit an alert.

    Returns a validated picks list (possibly empty — that is a real rejection).
    Raises JudgeFormatError if the reply is off-schema twice in a row. One bounded
    retry, quoting the exact validation error back to the model; then it fails
    loudly rather than pretending the day had no picks.
    """
    global LAST_REPLY, LAST_STOP_REASON
    client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    valid = {c["ticker"] for c in candidates}
    messages = [{"role": "user", "content": json.dumps(candidates)}]
    last_error = None
    for attempt in (1, 2):
        resp = client.messages.create(
            model="claude-sonnet-5",
            # Sonnet 5 runs adaptive thinking when `thinking` is omitted (4.6 did not),
            # so max_tokens now covers thinking + the JSON. 1500 risked a truncated
            # reply — which used to read as "no picks" and silently stop alerts, and
            # now raises JudgeFormatError instead.
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},  # low made the judge lazily reject everything
            system=SYSTEM,
            messages=messages,
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        LAST_REPLY, LAST_STOP_REASON = text, resp.stop_reason
        try:
            return parse_picks(text, valid)
        except JudgeFormatError as e:
            last_error = e
            if attempt == 2:
                break
            print(f"judge: reply {attempt} off-schema ({e}) — retrying once")
            messages = messages + [
                {"role": "assistant", "content": text or "(empty reply)"},
                {"role": "user", "content": SCHEMA_REMINDER.format(reason=e)},
            ]
    raise JudgeFormatError(
        f"judge returned an off-schema reply twice; last error: {last_error}. "
        f"stop_reason={LAST_STOP_REASON!r} raw={LAST_REPLY[:300]!r}")


if __name__ == "__main__":
    # self-check: multi-signal ticker with sentiment + earnings outranks a lone RSI hit
    sigs = [{"ticker": "AAA", "rsi_oversold": True},
            {"ticker": "BBB", "unusual_volume": True, "breakout_20d": True}]
    ranked = rank(sigs, {"BBB": {"sentiment": 2}},
                  {"BBB": {"earnings_date": "2026-07-14", "avg_post_earnings_move_pct": 5.0}})
    # 2.0 volume + 2.0 breakout + 1.0 tone; earnings is a risk flag worth 0
    assert ranked[0]["ticker"] == "BBB" and ranked[0]["score"] == 5.0, ranked[0]
    assert ranked[1]["score"] == 1.0
    # confluence: BBB fired volume+breakout+earnings = 3 families, AAA only RSI = 1
    assert signal_types(ranked[0]) == 3 and signal_types(ranked[1]) == 1
    # direction: a breakout that is already overbought is worth less than the
    # breakout alone (2.0 - 1.0), not more (it used to score 3.0)
    ob = rank([{"ticker": "CCC", "breakout_20d": True, "rsi_overbought": True}], {}, {})
    assert ob[0]["score"] == 1.0, ob
    # but it still counts as two families firing, so confluence is unaffected
    assert signal_types(ob[0]) == 2
    print("rank self-check ok")

    # self-check: the schema contract. The exhaustive cases live in test_analyzer.py
    # (.venv/bin/python -m pytest test_analyzer.py -q); these are the two that must
    # never regress — recover a recoverable reply, reject everything else out loud.
    def _parse(text):
        return parse_picks(text, {"BBB"})

    good = ('{"picks": [{"ticker": "BBB", "line": "BBB $10 \u2014 up\\nRisks: x\\n'
            'Verdict: y\\nInvalid below: $9.10"}]}')
    assert len(_parse(good)) == 1
    assert len(_parse("Here are my picks:\n```json\n" + good + "\n```")) == 1  # prose + fences
    # brackets left open but every string closed: content is complete, so recover it.
    # This is the real 2026-07-24 reply shape — valid JSON one `}` short — which
    # silently cost a correctly-judged pick before _close_open_brackets existed.
    assert len(_parse(good[:-2])) == 1
    assert _parse('{"picks": []}') == []   # a real "nothing qualifies" is not an error
    for bad in ["None of these candidates are actionable today.",   # prose only
                '{"verdict": "no"}',                                 # wrong schema
                '{"picks": 5}',                                      # picks not a list
                '{"picks": [{"ticker": "ZZZ", "line": "x\\nInvalid below: $1"}]}',
                '{"picks": [{"ticker": "BBB"}]}',                    # missing line
                '{"picks": [{"ticker": "BBB", "line": "BBB $10 up"}]}',  # no invalidation
                good[:-20]]:                                         # died mid-sentence
        try:
            _parse(bad)
        except JudgeFormatError:
            pass
        else:
            raise AssertionError("should have raised JudgeFormatError: " + bad)
    print("judge-parse self-check ok")
