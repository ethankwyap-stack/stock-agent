# stock-agent

Screens the S&P 500 for technical signals, has Claude judge which candidates are
actually worth acting on, and sends the survivors to Telegram. Python 3.12 +
yfinance/pandas, runs entirely on GitHub Actions. No server.

## Live deployment
- Repo `ethankwyap-stack/stock-agent` (**private**), workflow `.github/workflows/run.yml`.
- Secrets are GitHub Actions repo secrets: `ANTHROPIC_API_KEY`, `TELEGRAM_TOKEN`,
  `TELEGRAM_CHAT_ID`, `SHEET_WEBHOOK_URL`. Nothing sensitive is on disk.
- Cost: ~$0.40–1.00/month, all Anthropic. Actions uses ~400 of the 2,000 free
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
- `sheet_webhook.gs` — Apps Script source for that sheet (deployed separately).

## Local run
```bash
.venv/bin/python main.py --selfcheck   # offline: time/message branches, state loading
.venv/bin/python analyzer.py           # offline: scoring + 7 Claude-reply shapes
.venv/bin/python screener.py           # offline: RSI math
.venv/bin/python judge_smoke.py        # ONE real Claude call, ~half a cent, needs the key
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
- **`parse_picks` must stay tolerant.** It regex-extracts `{...}` from anywhere
  in the reply and never raises; a bad reply means no picks, not a dead run.
  Do not "tighten" it back to a strict `json.loads`.
- **Yahoo's OpenWeb comments endpoint 403s since Jul 2026** — sentiment is
  headlines only; the always-0 `mentions` count and the scoring bonus it fed are
  both gone as of Jul 24 2026. If sentiment logs 0 tickers,
  suspect yfinance `.info`/news, and note `sentiment.py` swallows per-ticker errors.
- **The sheet webhook is write-only** — `sheet_webhook.gs` defines `doPost` and no
  `doGet`, so pick history cannot be read back out of the sheet. That is why
  `outcomes.py` keeps its own `picks_log.jsonl`, which rides the same Actions
  cache as `state.json`; eviction costs one scorecard and never an alert.
- **`state.json` lives in the Actions cache**, not the repo. Cache keys are
  immutable: save under `state-${{ github.run_id }}`, restore by prefix `state-`.
  Eviction just resets alert memory — harmless.
- **The Apps Script is standalone, not sheet-bound** — it must use `openById`,
  never `getActiveSpreadsheet`, and needs `installTrigger()` for on-open refresh.
  A row appearing in the sheet is the only real test; curl probes of `/exec`
  mislead (200 can be an error page). Never paste `.gs` code from chat — use
  `open -e sheet_webhook.gs` and copy from TextEdit.
