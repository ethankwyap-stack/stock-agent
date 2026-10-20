# HANDOFF — stock-agent

Written 2026-10-20 ~19:05 UTC. Project: `/Users/ethanyap/stock-agent`.
Facts below were re-checked by command at 19:01 UTC. The July 2026 handoff this
replaces is in git history (`git show fd4faba:handoff.md`); everything in it was
closed.

## TL;DR

The project goal changed: **measure which signals actually make money, then tune.**
Ethan asked about reinforcement learning; the answer was no (11 graded picks,
noisy rewards, years to get enough trades). The plan is a backtest instead.

- Research done: 5 parallel researchers + 1 synthesizer. Full report:
  **`backtest-research.md`** (read sections 3–8 before building).
- Build plan has 5 steps. **Steps 1 and 2 are done**, pushed as `a61ad43`.
- **Next task: step 3**, then step 4. Ethan said "go A", then asked for this
  handoff — he has not yet said "go step 3". Confirm before starting.

## Verified state (19:01 UTC)

- `main` in sync with `origin/main`. Working tree clean before this handoff.
- `.venv/bin/python -m pytest -q` → 45 passed. `main.py --selfcheck` ok.
- Last scheduled runs all succeeded, but on `cc4fb44` — **no live run has used
  `a61ad43` yet.** The first `judge_log.jsonl` line appears on the first run where
  a candidate reaches the judge. Nothing has proven that path on Actions yet.
- A real `outcomes._history("SPY", "2026-10-01")` call returned prices locally.

## What step 1 + 2 changed (`a61ad43`)

| File | Change |
|---|---|
| `outcomes.py` | Grades on the close **5 / 20 trading days** after entry (was 7 / 28 calendar days at whatever price was current). Shows `TICKER +5.0% (+4.0 vs SPY)`. `record()` now stores `spy` at entry; the 11 seeded picks have none, so SPY's entry-day close stands in. New `log_judgment()` writes `judge_log.jsonl`. Old `__main__` self-check deleted — `test_outcomes.py` replaces it. `_last_price` renamed `last_price`. |
| `main.py` | After `analyzer.judge()`, calls `outcomes.log_judgment(candidates, picks, spy=...)` on every real judgment, empty ones included. A `JudgeFormatError` now sets `picks = None` so it is **not** logged as a judgment. |
| `analyzer.py` | `MODEL = "claude-sonnet-5"` constant; logged with each judgment. |
| `run.yml` | `judge_log.jsonl` added to both cache restore and save paths. |
| `.gitignore` | `judge_log.jsonl` (cache only, no seed). |
| `test_outcomes.py` | 6 tests, written first and seen failing. |

Design notes (not visible in code):
- History is **unadjusted** (`auto_adjust=False`) to match the unadjusted
  `facts.price` logged at alert time. Returns therefore exclude dividends — tiny.
- Ticker and SPY closes are aligned by **position**, not by date. A halted
  ticker would misalign. Accepted; not seen in S&P 500 names.
- Grading only runs in the post-close `digest` mode, so the last bar is final.

## The rest of the plan

**Step 3 — pull out `signals(df)`.** `screener.scan()` (`screener.py:50`) computes
volume ratio, 20-day breakout, RSI and volatility inline while it loops over live
tickers. Move that math into a pure function on one ticker's DataFrame, with no
behavior change. Proof: `.venv/bin/python screener.py` self-check passes, and a
live scan gives the same flags before and after. Why: the backtest must call the
**same** code as the live bot, or the two drift apart.

**Step 4 — `fetch_bars.py` + `backtest.py`.** Pandas event study, no framework.
- Members: [fja05680/sp500](https://github.com/fja05680/sp500) point-in-time
  list (survivorship fix). Not today's `sp500_tickers()`.
- Bars: yfinance daily from 2015, pulled **once, locally**, in chunks of 100 with
  pauses (Yahoo 429-blocks bulk pulls, sometimes >24 h). Never from Actions — a
  blocked runner breaks the live screener. Store `bars.pkl` (~25 MB), gitignored.
- Enter at **t+1 open** (signal is on day t's close). Gap-aware stop at
  `stop_ref`. 5 bps per side, stress test at 20 bps. One signal per ticker per
  holding period. Subtract SPY. Log every config to `trials.jsonl`.
- Tune on 2015–2021, test **once** on 2022–2026. Change a weight only if t > 3,
  same sign out of sample, survives 20 bps, holds in up and down markets.
- Proof: an assert on a fake 3-ticker frame with a known answer.

**Step 5 — grade the judge, in ~3 months.** From `judge_log.jsonl`, compare
J (judge's pick) vs S (`rank()` top-1) vs R (mean of all candidates), net of SPY.
After ~100 judged days: if J−S ≤ 0, drop the judge and alert on S.

## Decisions still open — ASK ETHAN

1. Move live alerts to the post-close digest so they match the backtest's
   close-based signals? Costs same-day timing.
2. Spend ~4 nights of plan usage replaying the judge on Feb–Sep 2026, or rely
   on the shadow log only?
3. If plain breakout (no volume) fails the bar, move its +2 to breakout×volume?

## Gotchas learned this session

- **Never replay the Claude judge on dates before its knowledge cutoff** (Sonnet
  5: Jan 2026) and count it as skill. The model remembers what happened next.
  One study: 81% right before cutoff, 46% after.
- **The old scorecard flattered the bot**: raw % in a rising market.
- `.venv` is Python 3.9; most backtest frameworks (and alphalens-reloaded) need
  3.11+. Another reason to build in pandas.
- The research report's "Learned" footer and some file paths cite line numbers
  from `cc4fb44`; `main.py` shifted ~4 lines in `a61ad43`.

## How to work with Ethan

- ELI5 output style was on: short sentences, simple words, 2 options max with a
  recommendation. Start every reply with "Ethan,".
- Test first: write the failing test, show it fail, then build.
- End real changes with a one-line **Learned:** concept.
- Ask before commit/push.
