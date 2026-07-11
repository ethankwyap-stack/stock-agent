"""Combine signals into a scored ranking; send top 5 to Claude for a trade-ideas summary."""
import json
import anthropic

SYSTEM = (
    "You are a concise stock-signal analyst. You receive JSON describing tickers "
    "that triggered technical screens (volume, breakout, RSI), Yahoo Finance "
    "community-comment and news-headline sentiment, "
    "and upcoming earnings. Write a short Telegram-ready trade-ideas summary: "
    "one line per ticker with the setup, the key signals, and a one-clause risk "
    "note. Plain text, no markdown tables, no financial-advice disclaimers, "
    "under 1500 characters. Rank strongest idea first."
)


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


def analyze(top_signals):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(top_signals)}],
    )
    return next(b.text for b in resp.content if b.type == "text")


if __name__ == "__main__":
    # self-check: multi-signal ticker with sentiment + earnings outranks a lone RSI hit
    sigs = [{"ticker": "AAA", "rsi_oversold": True},
            {"ticker": "BBB", "unusual_volume": True, "breakout_20d": True}]
    ranked = rank(sigs, {"BBB": {"mentions": 3, "sentiment": 2}},
                  {"BBB": {"earnings_date": "2026-07-14", "avg_post_earnings_move_pct": 5.0}})
    assert ranked[0]["ticker"] == "BBB" and ranked[0]["score"] == 8.5
    assert ranked[1]["score"] == 1.0
    print("rank self-check ok")
