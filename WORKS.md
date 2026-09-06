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

## The offline pipeline still runs

```bash
.venv/bin/python main.py --selfcheck   # time/message, state, upside-gate, vol-gate ok
.venv/bin/python screener.py           # RSI math ok
```

## Not covered

- `notify.py` / `tracker.py` are never exercised locally on purpose — running them
  sends a real Telegram message and writes a real sheet row. Use Actions → **test**.
