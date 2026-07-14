# Stock Alert Agent

Hourly scanner that screens S&P 500 stocks for unusual volume, 20-day breakouts,
and RSI extremes, cross-references Yahoo sentiment and upcoming earnings, then has
Claude *judge* which candidates (0–5) a cautious trader would actually act on today.
Only the ones that clear that bar reach you on Telegram — most runs send nothing.

Runs free on GitHub Actions. No servers.

## How it works

```
screener.py  -> technical signals + 30d volatility (yfinance, S&P 500 from Wikipedia)
sentiment.py -> Yahoo Finance comments + news headline sentiment (free, no key)
earnings.py  -> earnings within 7 days + avg historical post-earnings move
facts.py     -> finalist fact pack: analyst target, 52wk position, P/E, beta
analyzer.py  -> composite score + Claude (claude-sonnet-4-6) as skeptical judge
notify.py    -> Telegram bot message
main.py      -> orchestrates; gates candidates, remembers what it already sent
```

Gates a ticker must clear, in order:

1. Score >= 3 AND at least 2 independent signal families
   (volume / breakout / RSI / earnings).
2. Not already alerted today, unless its score jumped by 2+.
3. Analyst mean price target at least 10% above current price
   (the measurable-upside floor; no target = dropped).
4. Claude, prompted as a skeptic whose default is DO NOT BUY, builds the bear
   case from the fact pack and includes the ticker only if the upside clearly
   outweighs it. Zero picks is a normal outcome.

Alerts are 2-3 lines per pick: the setup and upside, the top reasons NOT to
buy, and the verdict on why it's worth it anyway. If a whole week goes by with
no alerts, you get one "still scanning" heartbeat Friday afternoon (alert
memory lives in `state.json`, carried between runs by the Actions cache).

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
- `MIN_FAMILIES` in `main.py` (default 2) — signal families required before
  Claude even sees a ticker; set to 1 to loosen, 3 to only hear about monsters.
- `RESEND_JUMP` in `main.py` (default 2.0) — same-day re-alerts need this much
  score improvement.
- `MIN_UPSIDE_PCT` in `main.py` (default 10.0) — required analyst-target upside.
  Note: analyst targets skew optimistic and lag news, so this is a sanity floor,
  not a prediction.
- Claude's bar lives in `SYSTEM` in `analyzer.py` — edit the prompt to make the
  judge stricter or looser.
- Scoring weights live in `analyzer.rank()`: volume 2, breakout 2, RSI 1,
  Yahoo sentiment up to 4, earnings 2.
