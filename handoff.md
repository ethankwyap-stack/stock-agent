# HANDOFF — stock-agent

Written 2026-10-20 ~20:00 UTC. Project: `/Users/ethanyap/stock-agent`.
The previous handoff (backtest plan, steps 1–2 done) is in git history at `9f2530f`.

## TL;DR

All 5 steps of the `backtest-research.md` build plan are done. **The backtest's
answer: the price screens have no edge.** Over 2015–2026, no signal, and not the
live gate stack, beats a random S&P 500 stock held the same way. The live gates
pick slightly *worse* than random. See "Findings".

One decision is open for Ethan — what to do about that. Nothing else is pending.

## What shipped today

| Commit | What |
|---|---|
| `a61ad43` | Step 1+2: scorecard in trading days vs SPY; `judge_log.jsonl` logs every judge call |
| `6db25c8` | Step 3: `screener.signals(df)` pure function; scan output byte-identical on a frozen 503-ticker download |
| `ba70255` | Open question 1 → **B**: alerts only after the close (cron 20:15–02:45 UTC + weekend note) |
| next | Step 4: `fetch_bars.py`, `backtest.py`, `backtest-results.md`, `trials.jsonl`. Step 5: `outcomes.judge_report()` in the digest |

## Findings (from `backtest-results.md`)

Per trade, mean return minus SPY, next-open entry, stop at `stop_ref`, 5 bps/side:

| | 5d tune / test | 20d tune / test | vs random 20d tune / test |
|---|---|---|---|
| random S&P member-day | −0.07 / −0.22 | −0.13 / −0.41 | 0 / 0 |
| qualified (live gates) | −0.30 / −0.39 | −0.33 / −0.55 | −0.20 / −0.14 |
| breakout × volume | −0.34 / −0.31 | −0.43 / −0.38 | −0.30 / +0.03 |
| oversold | −0.12 / −0.22 | −0.01 / −0.43 | +0.13 / −0.02 |

- Even random stocks trail SPY: an equal mix of S&P names lagged the cap-weighted
  index since 2015 (megacap years). That is most of every "HARMFUL" verdict.
- Versus random, no cell passes the bar in either direction consistently.
  The research's expected edges (breakout×volume 20d, oversold 5d) did not appear.
- The stop costs nothing: a one-off check without it gave −0.29% vs −0.24% (random,
  20d) and −0.47% vs −0.44% (live gates, 20d). Not in `trials.jsonl` (ad-hoc script).
- Optimistic caveat: 28% of 2015 member-days have no Yahoo data (delisted). Fixing
  that would make results worse, not better.

**Decisions applied by the research's own rule** ("change a weight only if it passes
the bar, otherwise leave it"): no weights changed. Open question 3 (move breakout's
+2 to breakout×volume) → **no**, breakout×volume fails too. Open question 2 (judge
replay on Feb–Sep 2026) → **no**, the shadow log measures the judge for free.

## The one open decision — ASK ETHAN

The screens alone are a coin flip that trails SPY. Whatever edge exists must come
from the non-price layers (analyst-upside gate, sentiment, the Claude judge), which
only the live `judge_log.jsonl` can measure (~100 judged days, months).
Options he was given: keep running as-is and let the judge log decide, or treat
the bot as a paper experiment only and stop reading alerts as buy signals.

## Verified state

- `pytest -q` → 58 passed. `main.py --selfcheck`, `screener.py` ok.
- No live run has used the new code yet; the first post-close run is tonight.
- `data/` (bars 72 MB, members CSV) is local only and gitignored.

## How to work with Ethan

- Start every reply with "Ethan,". ELI5 style: short sentences, 2 options max.
- Test first; end real changes with a **Learned:** line. Ask before commit/push
  unless he said to.
