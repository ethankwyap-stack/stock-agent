# Stock Alert Agent

Scanner that screens S&P 500 stocks for unusual volume, 20-day breakouts,
and RSI extremes, cross-references Yahoo sentiment and upcoming earnings, then has
Claude *judge* which candidates (0–5) a cautious trader would actually act on today.
Only the ones that clear that bar reach you on Telegram — most runs send nothing.

Runs free on GitHub Actions. No servers.

## How it works

```
screener.py  -> technical signals + 30d volatility (yfinance, S&P 500 from Wikipedia)
sentiment.py -> Yahoo news headline sentiment, top 20 by score (free, no key)
earnings.py  -> earnings within 7 days + avg post-earnings move, top 30 by score
facts.py     -> finalist fact pack: analyst target, 52wk position, P/E, beta
analyzer.py  -> composite score + Claude (claude-sonnet-5) as skeptical judge
notify.py    -> Telegram bot message
outcomes.py  -> grades past picks at 5d/20d, appended to the post-close digest
main.py      -> orchestrates; gates candidates, remembers what it already sent
```

Gates a ticker must clear, in order:

1. Score >= 2.5 AND at least 2 independent signal families
   (volume / breakout / RSI / earnings).
2. Not already alerted today, unless its score jumped by 2+.
3. Believable analyst upside: either 10–40% above the current price, or — for a
   momentum name sitting at 80%+ of its 52-week range — merely not below it.
   Over 40% is dropped as a target nobody has cut yet; no target at all is
   dropped too.
4. 30-day volatility no more than 4× the upside, with a 5% floor on the upside
   so momentum names aren't killed by their own deliberately small target.
5. Claude, prompted as a skeptic whose default is DO NOT BUY, builds the bear
   case from the fact pack and includes the ticker only if the upside clearly
   outweighs it. Zero picks is a normal outcome.

Alerts are 3-4 lines per pick: the setup and upside, the top reasons NOT to
buy, the verdict on why it's worth it anyway, and the invalidation level below
which the setup is simply wrong. You get at least one message
every day: if no alert fired by 3pm ET, a daily digest lists the day's top
signals (or says it was a quiet day). If GitHub's cron skips the 3pm hour
entirely — it often does, see below — the first run after the close scans again
and sends that digest using the day's final data. Post-close runs only
summarize; they never alert, since a BUY landing at 6pm is a different message
from one at 11am. On weekends a single "market closed" note goes out around noon
ET (alert memory lives in `state.json`, carried between runs by the Actions
cache).

## Setup

Do these one at a time.

### 1. Telegram bot

1. In Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
   Copy the token it gives you — that's `TELEGRAM_TOKEN`.
2. Message your new bot anything (say "hi") so it can reply to you.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
   copy the `"chat":{"id": ...}` number — that's `TELEGRAM_CHAT_ID`.

### 2. Claude plan token

Run `claude setup-token` and copy the token. That's `CLAUDE_CODE_OAUTH_TOKEN`. Usage counts against your Claude plan, no per-token bill.
(This is the only paid service — each run that finds signals costs about half a
cent on claude-sonnet-5; quiet runs cost nothing. Measured total: under $1/mo.)

### 3. GitHub

1. Push this repo to GitHub.
2. Repo → Settings → Secrets and variables → Actions → New repository secret.
   Add all three: `CLAUDE_CODE_OAUTH_TOKEN`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
   (Sentiment comes from Yahoo Finance's public comment/news APIs — no key needed.)
3. The workflow (`.github/workflows/run.yml`) asks for a run every 30 minutes,
   9am-4pm ET, Mon-Fri. GitHub treats scheduled runs as best-effort and in
   practice delivers 4-7 a day, spaced 80-100 minutes apart — the code is
   written to be correct at whatever cadence actually shows up.
   Test it now: repo → Actions → stock-alert → "Run workflow". Two checkboxes:
   **test** sends a fake pick through Telegram + the sheet without scanning;
   **force** does a full real scan ignoring market hours, which is how you
   verify the Claude call after changing the model (it may send a real alert).

## Run locally

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=...
python main.py --force   # --force skips the market-hours check
```

Self-checks (no API keys needed):

```bash
python screener.py       # RSI math
python analyzer.py       # scoring/ranking + Claude reply parsing
python main.py --selfcheck   # market hours, end-of-day message, state loading
```

## Tuning

- `MIN_SCORE` in `main.py` (default 2.5) — raise it if you get too many alerts.
- `MIN_FAMILIES` in `main.py` (default 2) — signal families required before
  Claude even sees a ticker; set to 1 to loosen, 3 to only hear about monsters.
- `RESEND_JUMP` in `main.py` (default 2.0) — same-day re-alerts need this much
  score improvement.
- `MIN_UPSIDE_PCT` / `MAX_UPSIDE_PCT` / `MOMENTUM_RANGE_PCT` in `main.py`
  (10.0 / 40.0 / 80.0) — the upside gate. Analyst targets skew optimistic and
  lag price, so the band is a sanity check, not a prediction: under the floor
  there's nothing to weigh, over the ceiling the target is probably just stale.
- `VOL_UPSIDE_MULT` in `main.py` (default 4.0) — how many times its upside a
  stock's 30-day volatility may reach before it's dropped as too noisy to bother
  judging.
- `SENTIMENT_TICKERS` / `EARNINGS_TICKERS` in `main.py` (20 / 30) — how many of
  the top-scoring tickers get the slow sentiment and earnings lookups. These are
  ranked by technical score, never alphabetically. Raising them costs runtime
  (earnings is the slowest stage by far); lowering them risks missing a mover
  that was ranked low on technicals alone.
- Claude's bar lives in `SYSTEM` in `analyzer.py` — edit the prompt to make the
  judge stricter or looser.
- Scoring weights live in `analyzer.rank()`: volume 2.0, breakout 2.0, RSI +1.0
  when oversold and −1.0 when overbought (the alert is a BUY, so an overbought
  breakout is a caution), headline tone ±1.5, earnings 0 — an upcoming report is
  event risk for the judge to weigh, not a merit worth points.
