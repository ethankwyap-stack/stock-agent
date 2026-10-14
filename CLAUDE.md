# stock-agent

Screens the S&P 500 for technical signals, has Claude judge which candidates are
actually worth acting on, and sends the survivors to Telegram. Python 3.12 +
yfinance/pandas, runs entirely on GitHub Actions. No server.

## Live deployment
- Repo `ethankwyap-stack/stock-agent` (**private**), workflow `.github/workflows/run.yml`.
- Secrets are GitHub Actions repo secrets: `CLAUDE_CODE_OAUTH_TOKEN`, `TELEGRAM_TOKEN`,
  `TELEGRAM_CHAT_ID`, `SHEET_WEBHOOK_URL`, `ALPACA_KEY`, `ALPACA_SECRET`.
  Nothing sensitive is on disk (a local `.env` for the Alpaca keys is gitignored).
- Cost: $0. The judge runs `claude -p` (CLI pinned in run.yml) on the Claude plan via
  `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (token lasts ~1 year). No API key. Actions uses ~400 of the 2,000 free
  private-repo minutes; GitHub's default $0 spending limit means it stops rather
  than bills.

## Layout
- `main.py` — orchestrator: market-hours gate, ranking pre-pass, gates, digest.
- `screener.py` — unusual volume / 20-day breakout / RSI extremes + volatility.
- `sentiment.py` — Yahoo news-headline tone for the top-scoring tickers.
- `earnings.py` — earnings within 7 days + average post-earnings move.
- `facts.py` — fact pack (analyst target, 52wk position, P/E, beta) for finalists only.
- `analyzer.py` — `rank()` composite score, `judge()` the Claude call, `parse_picks()`.
- `notify.py` — Telegram send. `tracker.py` — appends picks to the Google Sheet.
- `outcomes.py` — grades past picks at 5d/20d from `picks_log.jsonl`, into the digest.
- `broker.py` — mirrors every alert into the Alpaca **paper** account: one market
  order per pick, 10% of equity, stop-loss at the alert's own invalidation level.
- `sheet_webhook.gs` — Apps Script source for that sheet (deployed separately).

## Local run
```bash
.venv/bin/python main.py --selfcheck   # offline: time/message branches, state loading
.venv/bin/python analyzer.py           # offline: scoring + 7 Claude-reply shapes
.venv/bin/python screener.py           # offline: RSI math
.venv/bin/python judge_smoke.py        # ONE real Claude call on 2 candidates, plan usage, needs `claude` logged in
.venv/bin/python main.py --force       # full run, needs all keys, really sends Telegram
```
Local `.venv` is Python 3.9; Actions runs 3.12.

Or test on GitHub with the stored key — Actions → stock-alert → Run workflow:
- **smoke** — one real Claude judge call. Use this after any model change; a
  forced scan can't verify the judge because the upside gate often empties the
  candidate list first (it dropped all 5 on run 30043084820).
- **force** — full real scan ignoring market hours; may send a real alert.
- **test** — fake pick through Telegram + the sheet, no scan, no Claude.

## Gotchas
- **The cron is a request, not a schedule.** It asks for a run every 30 min
  (18/weekday); GitHub delivers 4–7, 80–100 min apart, up to 22 min late. Never
  write logic requiring a run to land in a specific clock hour — the 3pm ET
  digest window gets skipped outright. Estimate minutes from `gh run list`.
- **`scan_window(now)` decides what a run may send**, not `market_open` alone:
  `"alert"` during market hours, `"digest"` after the close on a weekday (scans
  with final data, never alerts), `None` on weekends and pre-open. The
  post-close run is the backstop that makes the daily digest independent of the
  cron; it returns early if anything already went out today, so it costs at most
  one extra scan a day.
- **Never sort inside `sentiment.scan`.** Its input is pre-ranked by score by
  `main.py`. It used to sort alphabetically, which gave the sentiment score only
  to A-tickers. Same rule for `earnings.check`.
- **Sonnet 5 thinks by default.** Omitting `thinking` enables adaptive thinking
  (4.6 did not), so `max_tokens` must cover thinking + the JSON. A truncated
  reply parses as "no picks" and silently stops alerts — it does not error.
- **The judge prompt is the real alert valve, not the gates.** Aug 2026: 60 runs,
  15 reached the judge, 0 picks in six weeks. The gates were fine — the prompt
  said "default verdict DO NOT BUY" and "reject on any doubt", so it always
  rejected, and `effort: "low"` made it lazier still. Rewritten Sep 1 2026 as
  choose-the-best-of-N with effort `medium`. If alerts ever go quiet for weeks
  again, read the `judged none of N` lines first: candidates reaching the judge
  means the screens work and the prompt is the wall.
- **Extraction is tolerant, validation is strict — do not merge the two.**
  `_extract_json` still regex-extracts `{...}` from anywhere in the reply and
  repairs unclosed brackets (prose and code fences are model quirks, not schema
  violations). `validate_picks` then judges the *contents* strictly and raises
  `JudgeFormatError`. Superseded Sep 6 2026 the old "parse_picks must stay
  tolerant, a bad reply means no picks" rule: that tolerance was hiding real
  breakage, because a mangled reply logged identically to a genuine rejection —
  the exact shape that already cost two live alerts. Never go back to `try:
  parse ... except: return []`.
- **`judge()` retries exactly once, then raises.** On a `JudgeFormatError` it
  re-sends with the assistant's bad reply plus `SCHEMA_REMINDER` quoting the
  precise error, then gives up. Bounded on purpose — an unbounded retry loop
  against a model that has decided to write prose burns real money per attempt.
  `{"picks": []}` is a valid answer and is never retried.
- **The schema lives in three places and they must move together:** the contract
  comment above `SCHEMA_REMINDER`, the tail of `SYSTEM`, and `validate_picks`.
  Adding a field to the alert means editing all three plus `test_analyzer.py`.
- **`main.py` catches `JudgeFormatError` and keeps going.** It logs
  `JUDGE FORMAT FAILURE` with a traceback and sends no alert, but does not kill
  the run — the digest block below it must still get its chance. That catch is
  the *only* place the error may be absorbed; `judge_smoke.py` lets it exit
  non-zero so the workflow step fails.
- **`pytest` is a local-only dev dependency**, deliberately absent from
  `requirements.txt` — Actions runs the agent, not the tests. Install it with
  `.venv/bin/pip install pytest` on a fresh clone.
- **Claude sometimes ends one `}` short of valid JSON** (seen Jul 24 2026 with
  `stop_reason: end_turn` — not a max_tokens truncation), and the greedy regex
  then also eats the closing `]`, silently dropping a good pick.
  `_close_open_brackets()` retries with the unclosed brackets appended. It
  deliberately refuses to repair a reply with an **unterminated string** — that
  one died mid-sentence, and half an alert is worse than none.
- **`stop_ref` must never sit at or above the current price.** It starts as the
  prior 20-day closing low, but an oversold candidate is usually making a *new*
  20-day low, so the raw figure lands above where the stock trades and the alert
  states an already-breached level. `screener.invalidation_level()` caps it 3%
  under price — keep every new alert field that derives from past bars honest
  against the current one.
- **`judge_smoke.py` exits non-zero on a bad judgment**, so the workflow step
  fails loudly. It sends two candidates in one call — JNJ must be accepted, AAPL
  must be rejected — and prints the raw reply and `stop_reason` every time, which
  is the only way to tell a real rejection from a malformed one.
- **Yahoo's OpenWeb comments endpoint 403s since Jul 2026** — sentiment is
  headlines only; the always-0 `mentions` count and the scoring bonus it fed are
  both gone as of Jul 24 2026. If sentiment logs 0 tickers,
  suspect yfinance `.info`/news, and note `sentiment.py` swallows per-ticker errors.
- **The sheet webhook is write-only** — `sheet_webhook.gs` defines `doPost` and no
  `doGet`, so pick history cannot be read back out of the sheet. That is why
  `outcomes.py` keeps its own `picks_log.jsonl`, which rides the same Actions
  cache as `state.json`; eviction costs one scorecard and never an alert.
- **`picks_log.jsonl` is committed AND cached, and the cache wins.** The repo copy
  is a seed of the 11 picks from Jul 16–22 2026 (generated from the sheet's CSV
  export, never typed by hand — a wrong entry price corrupts every return computed
  from it, silently and forever). `actions/checkout` lays down the seed, then the
  cache restore overwrites it once any cache contains the file. So editing the
  committed copy changes nothing in production after that first run, and a cache
  eviction re-grades the 11 seeded picks. Both are cosmetic — a repeated scorecard,
  never a missed alert. Note it is deliberately absent from `.gitignore`.
- **`state.json` lives in the Actions cache**, not the repo. Cache keys are
  immutable: save under `state-${{ github.run_id }}`, restore by prefix `state-`.
  Eviction just resets alert memory — harmless.
- **`broker.py` is paper-only by construction.** `ALPACA_BASE` defaults to
  `paper-api.alpaca.markets`, and `buy()` refuses to send orders to any other host
  unless `ALPACA_ALLOW_LIVE=yes` — which is set nowhere, in no workflow, on purpose.
  Do not add it without a deliberate decision; the account it would reach is real money.
- **Alpaca answers a cancel with 204 and an empty body**, so `r.json()` raises on
  *success*. `_api` returns `None` when `r.content` is empty. Any new endpoint that
  can return 204 hits the same trap.
- **A paper order placed outside market hours is accepted, not filled** — it sits
  `accepted` and executes at the next open, and the OTO stop leg sits `held` until
  the entry fills. So a `--force` run after the close proves the order path but
  proves nothing about fills.
- **Never double a position on a re-alert.** `buy()` skips any ticker already in
  `/v2/positions`; a `RESEND_JUMP` re-alert is a stronger signal on the same idea,
  not a second trade.
- **The Apps Script is standalone, not sheet-bound** — it must use `openById`,
  never `getActiveSpreadsheet`, and needs `installTrigger()` for on-open refresh.
  A row appearing in the sheet is the only real test; curl probes of `/exec`
  mislead (200 can be an error page). Never paste `.gs` code from chat — use
  `open -e sheet_webhook.gs` and copy from TextEdit.
