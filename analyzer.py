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
    "prove the setup wrong."
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


def parse_picks(text, valid):
    """Pull the picks out of Claude's reply. Never raises — bad reply means no picks.

    Claude sometimes wraps the JSON in prose or code fences, drops a closing brace,
    or just says in plain English that nothing qualifies; a quiet run beats a crashed
    one either way. Two attempts: the greedy `{...}` match, then the same text with
    unclosed brackets repaired.
    """
    start = text.find("{")
    if start < 0:
        return []
    blob = re.search(r"\{.*\}", text, re.S)
    attempts = ([blob.group()] if blob else []) + [_close_open_brackets(text[start:])]
    for attempt in attempts:
        try:
            picks = json.loads(attempt)["picks"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if not isinstance(picks, list):
            continue
        return [p for p in picks if isinstance(p, dict)
                and p.get("ticker") in valid and p.get("line")]
    print("judge: unparseable response, treating as no picks:", repr(text[:500]))
    return []


# Set by judge() on every call. parse_picks is silent when the reply has no braces,
# so a genuine rejection, a prose-only reply and a truncated one all look like 0 picks
# in the logs. judge_smoke.py prints these to tell them apart. ponytail: globals, not a
# return-tuple, so no caller has to change.
LAST_REPLY = ""
LAST_STOP_REASON = ""


def judge(candidates):
    """Ask Claude which candidates merit an alert. Returns picks (possibly empty)."""
    global LAST_REPLY, LAST_STOP_REASON
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    resp = client.messages.create(
        model="claude-sonnet-5",
        # Sonnet 5 runs adaptive thinking when `thinking` is omitted (4.6 did not),
        # so max_tokens now covers thinking + the JSON. 1500 risked a truncated
        # reply, which parse_picks reads as "no picks" — alerts would just stop.
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},  # low made the judge lazily reject everything
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(candidates)}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    LAST_REPLY, LAST_STOP_REASON = text, resp.stop_reason
    return parse_picks(text, {c["ticker"] for c in candidates})


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

    # self-check: the response shapes that crashed live runs must all parse or degrade to []
    def _parse(text):
        return parse_picks(text, {"BBB"})

    good = '{"picks": [{"ticker": "BBB", "line": "BBB $10 — up"}]}'
    assert len(_parse(good)) == 1
    assert len(_parse("Here are my picks:\n```json\n" + good + "\n```")) == 1  # prose + fences
    assert len(_parse('{"picks": [{"ticker": "BBB", "line": "BBB $10 — up\\nRisks: x\\n'
                      'Verdict: y\\nInvalid below: $9.10"}]}')) == 1          # 4-line shape
    assert _parse("None of these candidates are actionable today.") == []     # plain English
    assert _parse('{"picks": [{"ticker": "ZZZ", "line": "x"}]}') == []        # hallucinated ticker
    assert _parse('{"picks": [{"ticker": "BBB"}]}') == []                     # missing line
    assert _parse('{"verdict": "no"}') == []                                  # wrong schema
    assert _parse('{"picks": 5}') == []                                       # picks not a list
    # brackets left open but every string closed: content is complete, so recover it.
    # This is the real 2026-07-24 reply shape — valid JSON one `}` short — which
    # silently cost a correctly-judged pick before _close_open_brackets existed.
    assert len(_parse('{"picks": [{"ticker": "BBB", "line": "BBB $10 — up\\n'
                      'Invalid below: $9.10"}]')) == 1
    assert len(_parse('{"picks": [{"ticker": "BBB", "line": "x"')) == 1
    # but a reply that died mid-sentence stays dropped — never send half an alert
    assert _parse('{"picks": [{"ticker": "BBB", "line": "BBB $10 — up') == []
    print("judge-parse self-check ok")
