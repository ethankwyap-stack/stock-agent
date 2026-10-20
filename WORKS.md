# WORKS.md — stock-agent

What this project promises, and the exact command that proves each promise.
Run these after any change (`/still-works`).

## Judge output is strict structured JSON

**Promise:** Claude's judge reply must match a fixed schema
(`{"picks": [{"ticker", "line"}]}`, ticker from the candidates, line ≤480 chars
ending in `Invalid below: $<level>`). A reply that does not match is retried once
with the exact validation error quoted back, then **fails loudly** — it is never
silently read as "no picks today".

**Prove it:**
```bash
.venv/bin/python -m pytest test_analyzer.py -q     # 21 passed
.venv/bin/python analyzer.py                       # rank + judge-parse self-check ok
```
Covers: good replies parse; `{"picks": []}` is a legitimate rejection, not an
error; prose/code fences/one-missing-brace still recover; prose-only, wrong
schema, hallucinated ticker, missing `line`, non-string `line`, missing
invalidation level, over-length line, duplicate tickers and unknown keys all
raise `analyzer.JudgeFormatError`; `judge()` retries exactly once and then
raises; a valid empty reply is not retried.

## The judge still discriminates (real Claude call)

**Promise:** JNJ (cheap, oversold, 22% upside, no earnings) is accepted; AAPL
(overbought at 88% of range, earnings in 6 days) is rejected; every accepted line
carries its invalidation level. Exits non-zero otherwise.

**Prove it:** needs the `claude` CLI logged in (Mac) or `CLAUDE_CODE_OAUTH_TOKEN` (Actions).
```bash
.venv/bin/python judge_smoke.py        # one real call, plan usage
```
Or on GitHub: Actions → stock-alert → Run workflow → **smoke**.

## Every alert is mirrored into an Alpaca PAPER account

**Promise:** when the judge returns picks, `broker.buy()` places one paper market
order per pick — a fixed slice of equity, capped by free cash, with a stop-loss
at the alert's own `Invalid below: $X` level. A ticker already held is skipped. A
broker failure never suppresses the Telegram alert. It cannot trade real money:
`ALPACA_BASE` defaults to the paper host and a non-paper host is refused unless
`ALPACA_ALLOW_LIVE=yes`, which is set nowhere.

**Prove it:**
```bash
.venv/bin/python -m pytest test_broker.py -q    # 15 passed
```
Covers: stop level parsed (commas, no cents, absent); share count from the equity
slice, capped by cash, zero on an unaffordable or junk price; the order body
(market + OTO + stop_price); held tickers skipped; a missing stop degrades to a
plain order rather than no trade; a dead API and missing keys both return `[]`.

**Live check:** Actions → stock-alert → Run workflow → **force**, then look at
the Alpaca paper dashboard for the order.

## The scorecard grades against SPY, and every judgment is logged

**Promise:** past picks are graded on the close 5 and 20 *trading* days after
entry, shown as raw % and as points vs SPY over the same bars. A pick without
enough closed bars, or without data, stays ungraded and retries next run. Each
horizon is graded once. Every judge call appends to `judge_log.jsonl` with all
candidates, even when it picks nothing; logging never raises. The digest also
grades the judge (J) against `rank()`'s top score (S) and the average candidate
(R), net of SPY, once per judged day, current model only; abstaining scores 0.
After 100 graded 20-day days it states whether to drop the judge.

**Prove it:**
```bash
.venv/bin/python -m pytest test_outcomes.py -q    # 10 passed
```

## Alerts fire only after the close

**Promise:** a weekday run from 4pm ET scans final bars, judges, alerts, then
sends the digest + scorecard. Runs before the close and on weekends never scan;
later runs the same day exit early.

**Prove it:**
```bash
.venv/bin/python main.py --selfcheck   # time/message self-check ok
```

## The backtest measures the live signal code

**Promise:** `screener.signals()` is the one place the signal math lives;
`scan()` and `backtest.py` both call it. The backtest enters at the next open,
fills a gap-through stop at the open, charges costs, keeps one trade per ticker
per holding period, counts a crash day once in its t-stat, screens only
point-in-time S&P members, and compares every cell with a random member-day.

**Prove it:**
```bash
.venv/bin/python screener.py                     # signals self-check ok
.venv/bin/python -m pytest test_backtest.py -q   # 9 passed
.venv/bin/python backtest.py                     # needs data/ from fetch_bars.py; ~4 min
```

## The offline pipeline still runs

```bash
.venv/bin/python main.py --selfcheck   # time/message, state, upside-gate, vol-gate ok
.venv/bin/python screener.py           # invalidation, RSI, signals ok
```

## Not covered

- `notify.py` / `tracker.py` are never exercised locally on purpose — running them
  sends a real Telegram message and writes a real sheet row. Use Actions → **test**.
