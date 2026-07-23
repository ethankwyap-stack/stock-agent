"""Combine signals into a scored ranking; Claude judges which candidates are truly actionable."""
import json
import re
import anthropic

SYSTEM = (
    "You are a skeptical stock analyst whose default verdict is DO NOT BUY. You "
    "receive JSON for tickers that passed technical screens (volume, breakout, RSI), "
    "each with a facts pack (analyst target upside %, position in 52-week range, "
    "trailing P/E, beta, 30d volatility), Yahoo sentiment, and upcoming earnings. "
    "For EACH candidate, first build the strongest bear case from the actual "
    "numbers: overextension near 52-week highs, rich valuation, earnings gap risk "
    "vs its historical move, volatility that dwarfs the upside, sentiment froth "
    "chasing a move already made. Then include the ticker ONLY if its concrete "
    "upside clearly outweighs that bear case — reject on any doubt; an empty picks "
    "list is a good outcome. Respond with ONLY this JSON, no other text: "
    '{"picks": [{"ticker": "XYZ", "line": "XYZ $price — setup and upside\\n'
    'Risks: the 1-2 strongest reasons NOT to buy\\nVerdict: why it is worth it '
    'anyway"}]}. Each line value is 2-3 short plain-text lines joined by \\n, '
    "under 400 chars, citing the actual numbers, strongest pick first, no "
    "financial-advice disclaimers."
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
        score += 1.0 * (s.get("rsi_oversold", False) or s.get("rsi_overbought", False))
        sent = sentiment.get(t)
        if sent:
            score += min(sent["mentions"], 5) * 0.5
            score += max(-3, min(3, sent["sentiment"])) * 0.5
            s["yahoo_sentiment"] = sent
        if t in earnings:
            score += 2.0
            s["earnings"] = earnings[t]
        s["score"] = round(score, 1)
    return sorted(signals, key=lambda s: s["score"], reverse=True)


def parse_picks(text, valid):
    """Pull the picks out of Claude's reply. Never raises — bad reply means no picks.

    Claude sometimes wraps the JSON in prose or code fences, or just says in plain
    English that nothing qualifies; a quiet run beats a crashed one either way.
    """
    blob = re.search(r"\{.*\}", text, re.S)
    try:
        picks = json.loads(blob.group())["picks"] if blob else []
    except (json.JSONDecodeError, KeyError, TypeError):
        print("judge: unparseable response, treating as no picks:", repr(text[:500]))
        return []
    return [p for p in picks if isinstance(p, dict)
            and p.get("ticker") in valid and p.get("line")]


def judge(candidates):
    """Ask Claude which candidates merit an alert. Returns picks (possibly empty)."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    resp = client.messages.create(
        model="claude-sonnet-5",
        # Sonnet 5 runs adaptive thinking when `thinking` is omitted (4.6 did not),
        # so max_tokens now covers thinking + the JSON. 1500 risked a truncated
        # reply, which parse_picks reads as "no picks" — alerts would just stop.
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},  # judging 5 tickers; effort defaults to "high"
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(candidates)}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return parse_picks(text, {c["ticker"] for c in candidates})


if __name__ == "__main__":
    # self-check: multi-signal ticker with sentiment + earnings outranks a lone RSI hit
    sigs = [{"ticker": "AAA", "rsi_oversold": True},
            {"ticker": "BBB", "unusual_volume": True, "breakout_20d": True}]
    ranked = rank(sigs, {"BBB": {"mentions": 3, "sentiment": 2}},
                  {"BBB": {"earnings_date": "2026-07-14", "avg_post_earnings_move_pct": 5.0}})
    assert ranked[0]["ticker"] == "BBB" and ranked[0]["score"] == 8.5
    assert ranked[1]["score"] == 1.0
    # confluence: BBB fired volume+breakout+earnings = 3 families, AAA only RSI = 1
    assert signal_types(ranked[0]) == 3 and signal_types(ranked[1]) == 1
    print("rank self-check ok")

    # self-check: the response shapes that crashed live runs must all parse or degrade to []
    def _parse(text):
        return parse_picks(text, {"BBB"})

    good = '{"picks": [{"ticker": "BBB", "line": "BBB $10 — up"}]}'
    assert len(_parse(good)) == 1
    assert len(_parse("Here are my picks:\n```json\n" + good + "\n```")) == 1  # prose + fences
    assert _parse("None of these candidates are actionable today.") == []     # plain English
    assert _parse('{"picks": [{"ticker": "ZZZ", "line": "x"}]}') == []        # hallucinated ticker
    assert _parse('{"picks": [{"ticker": "BBB"}]}') == []                     # missing line
    assert _parse('{"picks": [{"ticker": "BBB", "line": "x"') == []           # truncated
    assert _parse('{"verdict": "no"}') == []                                  # wrong schema
    print("judge-parse self-check ok")
