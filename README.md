# Stock Alert Agent

Hourly scanner that screens S&P 500 stocks for unusual volume, 20-day breakouts,
and RSI extremes, cross-references Reddit sentiment and upcoming earnings, has
Claude summarize the top 5 setups, and sends them to you on Telegram — but only
when something is actually actionable.

Runs free on GitHub Actions. No servers.

## How it works

```
screener.py  -> technical signals (yfinance, S&P 500 from Wikipedia)
sentiment.py -> Yahoo Finance comments + news headline sentiment (free, no key)
earnings.py  -> earnings within 7 days + avg historical post-earnings move
analyzer.py  -> composite score, top 5 -> Claude (claude-sonnet-4-6) summary
notify.py    -> Telegram bot message
main.py      -> orchestrates; only messages you if score >= 3
```

## Setup

Do these one at a time.

### 1. Telegram bot

1. In Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
   Copy the token it gives you — that's `TELEGRAM_TOKEN`.
2. Message your new bot anything (say "hi") so it can reply to you.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
   copy the `"chat":{"id": ...}` number — that's `TELEGRAM_CHAT_ID`.

### 2. Anthropic API key

Get one at https://console.anthropic.com → API Keys. That's `ANTHROPIC_API_KEY`.
(This is the only paid service — each run that finds signals costs a fraction
of a cent on claude-sonnet-4-6; quiet runs cost nothing.)

### 3. GitHub

1. Push this repo to GitHub.
2. Repo → Settings → Secrets and variables → Actions → New repository secret.
   Add all three: `ANTHROPIC_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
   (Sentiment comes from Yahoo Finance's public comment/news APIs — no key needed.)
3. The workflow (`.github/workflows/run.yml`) runs hourly 9am-4pm ET, Mon-Fri.
   Test it now: repo → Actions → stock-alert → "Run workflow".

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=... TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=...
python main.py --force   # --force skips the market-hours check
```

Self-checks (no API keys needed):

```bash
python screener.py   # RSI math
python analyzer.py   # scoring/ranking
```

## Tuning

- `MIN_SCORE` in `main.py` (default 3.0) — raise it if you get too many alerts.
- Scoring weights live in `analyzer.rank()`: volume 2, breakout 2, RSI 1,
  Yahoo sentiment up to 4, earnings 2.
