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

**Prove it:** needs `ANTHROPIC_API_KEY` (Actions secret; not on this Mac).
```bash
.venv/bin/python judge_smoke.py        # ~half a cent, one real call
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

## The offline pipeline still runs

```bash
.venv/bin/python main.py --selfcheck   # time/message, state, upside-gate, vol-gate ok
.venv/bin/python screener.py           # RSI math ok
```

## Not covered

- `notify.py` / `tracker.py` are never exercised locally on purpose — running them
  sends a real Telegram message and writes a real sheet row. Use Actions → **test**.
