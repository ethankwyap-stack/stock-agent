"""Smoke-test the Claude judge call with one fake candidate. Costs ~half a cent.

Needs ANTHROPIC_API_KEY in the environment. Nothing is sent to Telegram or the
sheet. Run this after changing the model or its request parameters:

    python judge_smoke.py
"""
import os
import sys

import analyzer

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("ANTHROPIC_API_KEY is not set — export it first, then re-run.")

CANDIDATE = [{
    "ticker": "AAPL", "price": 210.5, "score": 8.5,
    "unusual_volume": True, "breakout_20d": True, "rsi": 72.1,
    "volume_ratio": 2.4, "volatility_30d_annualized_pct": 24.0,
    "yahoo_sentiment": {"mentions": 4, "sentiment": 2},
    "earnings": {"earnings_date": "2026-07-30", "avg_post_earnings_move_pct": 4.2},
    "facts": {"price": 210.5, "analyst_mean_target": 245.0, "target_upside_pct": 16.4,
              "pct_of_52wk_range": 88, "trailing_pe": 33.1, "beta": 1.21},
}]

print("calling", "claude-sonnet-5", "...")
picks = analyzer.judge(CANDIDATE)
print(f"\nreturned {len(picks)} pick(s) — 0 is a valid, common outcome:")
for p in picks:
    print(f"\n[{p['ticker']}]\n{p['line']}")
print("\njudge smoke test ok — the request shape is accepted and parses.")
