# Stock Agent

**An S&P 500 scanner that sends me a Telegram alert only when a stock passes five gates, the last one an AI judge that must argue the bear case first. Then I backtested its price signals on 12 years of data to see if they really work. They didn't beat the market.**

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Runs on](https://img.shields.io/badge/runs%20on-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)
![Tests](https://img.shields.io/badge/tests-60-brightgreen)
![Hosting](https://img.shields.io/badge/hosting-%240-success)

Runs once each weekday after the market closes, on GitHub Actions. No server. Most days it sends nothing, and that is on purpose.

## Why I built it

I wanted to learn how real screening works: which signals mean something, and how to keep an AI from cheering on every trade. So I built the whole pipeline, then tested it against history instead of trusting it.

## What I found (the honest part)

I wrote [`backtest.py`](backtest.py), an event study: for every day a price signal fired since 2015, what did the stock do over the next 5 and 20 trading days, compared with the S&P 500 (SPY)?

- **None of the price-only screens showed a reliable edge over the market.** Not volume spikes, breakouts, oversold names, or the score-and-signal-count rules the live agent uses.
- **Some were worse than random picks.** Breakouts on high volume were marked *HARMFUL* by my own pass/fail bar.
- **How I tried to keep it fair:** only companies that were in the S&P 500 on that date, 2015-2021 for tuning and 2022-2026 held out as a test period, trading costs counted, and results checked in both up and down markets.
- **Limits I know about:** older years are missing data for some delisted or renamed stocks (26.5% of 2015 member-days), which makes results look better than they were, not worse. The news, analyst-target and AI-judge layers can't be backtested for free, so they are not in these numbers.

Full tables: [`backtest-results.md`](backtest-results.md). Plan and traps: [`backtest-research.md`](backtest-research.md).

What I took from it: a pipeline that *looks* smart is not evidence. So the agent now logs each judgment the AI makes, including "pass on all of them", to build the data needed to grade the AI judge later.

## How it works

```
screener.py   S&P 500 → volume spikes, 20-day breakouts, RSI, 30-day volatility   (yfinance)
sentiment.py  Yahoo headline tone for the top-scoring names                        (free, no key)
earnings.py   earnings within 7 days + the stock's usual post-earnings move
facts.py      fact pack for finalists: analyst target, 52-week range, P/E, beta
analyzer.py   score, then Claude as a skeptical judge → usually 0 or 1 pick
notify.py     Telegram alert           broker.py   optional: mirrors the pick into a PAPER account
outcomes.py   grades every past pick at 5 and 20 trading days vs SPY
```

A stock must clear every gate, in order:

1. **Score ≥ 2.5 from at least 2 different signal types** (volume, breakout, RSI, earnings). One loud signal is not enough.
2. **Not already sent today**, unless its score jumped by 2+.
3. **Believable analyst upside:** 10-55% above today's price. More than that usually means a stale target. A stock near its 52-week high only needs a target that isn't below the price.
4. **Not too noisy:** when there are several finalists, drop any whose 30-day volatility is far bigger than its upside.
5. **The AI judge.** Claude gets the numbers, must build the strongest bear case for each stock first, and passes only the best setup whose upside clearly beats it. "No picks" is a normal answer. Every alert ends with the price that would prove the setup wrong.

Each alert is 3-4 lines: *setup and upside → top risks → why it's worth it anyway → "invalid below $X"*.

## Tech

Python · pandas · yfinance · Claude (through the Claude Code CLI) · Telegram Bot API · Alpaca paper-trading API · Google Apps Script (a sheet log) · GitHub Actions (schedule + Actions cache for state)

Hosting is free. The AI calls run on my existing Claude subscription.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q          # 60 tests, no keys needed
.venv/bin/python main.py --selfcheck   # market hours, digest, state
```

A real scan also needs a logged-in [Claude Code](https://claude.com/claude-code) CLI and a Telegram bot:

```bash
export TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=...
.venv/bin/python main.py --force       # a real scan, ignores market hours
```

<details>
<summary><b>Full setup on GitHub Actions</b> (Telegram bot, Claude token, secrets)</summary>

1. **Telegram bot.** Message **@BotFather**, send `/newbot`, copy the token (`TELEGRAM_TOKEN`). Send your bot any message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the chat id (`TELEGRAM_CHAT_ID`).
2. **Claude.** Run `claude setup-token` and copy the token (`CLAUDE_CODE_OAUTH_TOKEN`).
3. **GitHub.** Settings → Secrets and variables → Actions: add all three. The workflow is [`.github/workflows/run.yml`](.github/workflows/run.yml). Actions → *Run workflow* has three boxes: **test** sends a fake pick without scanning, **force** runs a real scan outside the normal window, **smoke** makes one real Claude judge call on fake candidates, with no Telegram message.

</details>

<details>
<summary><b>Tuning knobs</b></summary>

All in `main.py` unless noted:

| Setting | Default | What it does |
|---|---|---|
| `MIN_SCORE` | 2.5 | Raise for fewer alerts |
| `MIN_FAMILIES` | 2 | Signal types needed before the judge sees a stock |
| `RESEND_JUMP` | 2.0 | Score jump needed to re-alert the same day |
| `MIN_UPSIDE_PCT` / `MAX_UPSIDE_PCT` | 10 / 55 | The analyst-upside band |
| `VOL_UPSIDE_MULT` | 4.0 | Max volatility as a multiple of upside |
| `SYSTEM` in `analyzer.py` | | The judge's prompt |
| `analyzer.rank()` | | The scoring weights |

</details>

## How I built it

I designed the gates, decided what to test and how, and read every result. I wrote the code with [Claude Code](https://claude.com/claude-code) as my pair programmer. The bug that taught me the most: six weeks with no alerts at all. It was not the market. It was my prompt: the judge's bar was so strict that it rejected everything. I rewrote it to pick the *best* setup whose upside beats its own bear case.

*Not financial advice. This is a learning project, and its own backtest says the price signals don't beat the market.*

---

Built by **Ethan Yap** · UC Davis · [LinkedIn](https://www.linkedin.com/in/ethan-yap-827a45346/)
