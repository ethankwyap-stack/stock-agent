"""Smoke-test the Claude judge call with two fake candidates. Costs ~half a cent.

Needs ANTHROPIC_API_KEY in the environment. Nothing is sent to Telegram or the
sheet. Run this after changing the model, its request parameters, or the prompt:

    python judge_smoke.py

Two candidates, not one, because a single reject-me payload can never exercise
the output format — it just returns 0 picks and proves nothing. One is built to
be accepted and one to be rejected, so the same half-cent call tests both the
`Invalid below: $X` line and whether the judge still discriminates.
"""
import os
import sys

import analyzer

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("ANTHROPIC_API_KEY is not set — export it first, then re-run.")

# Built to be ACCEPTED: cheap, low-beta, oversold near its 52wk lows with 22%
# upside and no earnings in the window. The bear case here is genuinely weak, so
# a rejection means the prompt has become too strict to ever alert.
# Score: volume 2.0 + oversold 1.0 + tone 1.0 = 4.0. Gates: upside 22.3% is inside
# the 10-40% band; vol 18% is under the 4x22.3 = 89% ceiling.
GOOD = {
    "ticker": "JNJ", "price": 148.2, "score": 4.0,
    "unusual_volume": True, "breakout_20d": False, "rsi_oversold": True,
    "rsi": 27.4, "volume_ratio": 2.1, "volatility_30d_annualized_pct": 18.0,
    "stop_ref": 143.5,
    "yahoo_sentiment": {"sentiment": 2},
    "facts": {"price": 148.2, "analyst_mean_target": 181.3, "target_upside_pct": 22.3,
              "pct_of_52wk_range": 18, "trailing_pe": 15.2, "beta": 0.62},
}

# Built to be REJECTED: overbought at 88% of its range, rich P/E, and earnings in
# six days whose average move (4.2%) eats a quarter of the 16.4% upside. Passes
# both gates, so the judge is the only thing that can stop it.
BAD = {
    "ticker": "AAPL", "price": 210.5, "score": 4.0,
    "unusual_volume": True, "breakout_20d": True, "rsi_overbought": True,
    "rsi": 72.1, "volume_ratio": 2.4, "volatility_30d_annualized_pct": 24.0,
    "stop_ref": 196.4,
    "yahoo_sentiment": {"sentiment": 2},
    "earnings": {"earnings_date": "2026-07-30", "avg_post_earnings_move_pct": 4.2},
    "facts": {"price": 210.5, "analyst_mean_target": 245.0, "target_upside_pct": 16.4,
              "pct_of_52wk_range": 88, "trailing_pe": 33.1, "beta": 1.21},
}

print("calling claude-sonnet-5 with 2 candidates (JNJ should pass, AAPL should not) ...")
picks = analyzer.judge([GOOD, BAD])

# Unconditional, and first: without it a 0-pick result is indistinguishable from a
# prose-only or truncated reply, which is the failure that cost two live alerts.
print(f"\nstop_reason: {analyzer.LAST_STOP_REASON}")
print(f"raw reply ({len(analyzer.LAST_REPLY)} chars):\n{analyzer.LAST_REPLY}\n")
if analyzer.LAST_STOP_REASON == "max_tokens":
    sys.exit("FAIL: reply hit max_tokens — truncated replies parse as 'no picks' and "
             "would silently stop alerts. Raise max_tokens in analyzer.judge().")

print(f"parsed {len(picks)} pick(s):")
for p in picks:
    print(f"\n[{p['ticker']}]\n{p['line']}")

got = {p["ticker"] for p in picks}
problems = []
if not picks:
    problems.append("0 picks — read the raw reply above: genuine rejection, or a "
                    "format the prompt no longer produces?")
if "JNJ" not in got:
    problems.append("JNJ was rejected — a clean, cheap, oversold setup with 22% "
                    "upside and no earnings should pass, or nothing ever will.")
if "AAPL" in got:
    problems.append("AAPL was accepted — overbought at 88% of range with earnings in "
                    "6 days should lose to its own bear case.")
for p in picks:
    if "Invalid below" not in p["line"]:
        problems.append(f"{p['ticker']} has no 'Invalid below: $X' line.")
    if len(p["line"]) > 480:
        problems.append(f"{p['ticker']} line is {len(p['line'])} chars, over the 480 budget.")

if problems:
    print("\nPROBLEMS:")
    for x in problems:
        print(" -", x)
    sys.exit(1)
print("\njudge smoke test ok — accepted the good setup, rejected the bad one, "
       "and every line carries its invalidation level.")
