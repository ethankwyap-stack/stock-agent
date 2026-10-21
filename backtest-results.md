# Backtest results — price-only screens

Generated 2026-10-20 by `backtest.py`. Signals 2014-06-30 to 2026-10-19, S&P 500 point-in-time members only. Entry next open, gap-aware stop at `stop_ref`, 5 bps per side, returns minus SPY over the same days. Tune 2015-2021, test 2022 on (test run once). t is over non-overlapping h-day blocks. Verdict bar: |t| > 3 in tune, same sign in test, survives 20 bps, holds in up- and down-trends (SPY vs its 200-day).

Not in here: sentiment, analyst targets, earnings, the Claude judge. The families count has no earnings family, so `qualified` is a little stricter than live.

**Missing data** — member-days with no Yahoo bars (delisted or renamed names). Results lean optimistic where this is high, oversold most of all:

| year | missing % |
|---|---|
| 2015 | 26.5 |
| 2016 | 23.4 |
| 2017 | 20.5 |
| 2018 | 18.7 |
| 2019 | 15.9 |
| 2020 | 12.8 |
| 2021 | 10.9 |
| 2022 | 8.3 |
| 2023 | 5.8 |
| 2024 | 4.3 |
| 2025 | 2.9 |
| 2026 | 1.2 |

## 5-day hold

| cell | period | n | mean vs SPY % | vs random % | median % | hit % | t | stop % | mean @20bps % | up-trend % | down-trend % | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random member-day | 2015-21 | 72431 | -0.07 | +0.00 | -0.26 | 46 | -1.9 | 19 | -0.37 | -0.12 | +0.24 | no evidence |
| random member-day | 2022-26 | 57109 | -0.22 | +0.00 | -0.49 | 44 | -3.2 | 25 | -0.52 |  | |  |
| volume | 2015-21 | 18875 | -0.18 | -0.11 | -0.43 | 44 | -2.6 | 28 | -0.48 | -0.18 | -0.27 | no evidence |
| volume | 2022-26 | 16357 | -0.23 | -0.02 | -0.53 | 44 | -3.3 | 29 | -0.53 |  | |  |
| breakout | 2015-21 | 28425 | -0.25 | -0.18 | -0.20 | 47 | -3.3 | 5 | -0.55 | -0.21 | -0.69 | HARMFUL |
| breakout | 2022-26 | 20491 | -0.24 | -0.02 | -0.29 | 47 | -3.7 | 5 | -0.54 |  | |  |
| breakout, no volume | 2015-21 | 26553 | -0.24 | -0.16 | -0.19 | 47 | -3.0 | 5 | -0.54 | -0.20 | -0.65 | no evidence |
| breakout, no volume | 2022-26 | 19221 | -0.23 | -0.01 | -0.29 | 47 | -3.3 | 5 | -0.53 |  | |  |
| breakout x volume | 2015-21 | 4300 | -0.33 | -0.26 | -0.30 | 46 | -3.7 | 5 | -0.63 | -0.30 | -0.95 | HARMFUL |
| breakout x volume | 2022-26 | 3064 | -0.29 | -0.07 | -0.38 | 46 | -2.1 | 4 | -0.59 |  | |  |
| oversold | 2015-21 | 19033 | -0.14 | -0.07 | -0.49 | 43 | -0.3 | 39 | -0.44 | -0.16 | -0.06 | no evidence |
| oversold | 2022-26 | 18373 | -0.22 | +0.00 | -0.77 | 41 | -2.2 | 44 | -0.52 |  | |  |
| overbought | 2015-21 | 31651 | -0.21 | -0.14 | -0.20 | 47 | -2.7 | 4 | -0.51 | -0.20 | -0.36 | no evidence |
| overbought | 2022-26 | 22960 | -0.12 | +0.10 | -0.14 | 48 | -1.3 | 4 | -0.42 |  | |  |
| qualified (live gates) | 2015-21 | 7983 | -0.30 | -0.23 | -0.48 | 44 | -4.7 | 25 | -0.60 | -0.28 | -0.52 | HARMFUL |
| qualified (live gates) | 2022-26 | 6494 | -0.37 | -0.16 | -0.67 | 42 | -3.0 | 27 | -0.67 |  | |  |
| top 5 qualified/day | 2015-21 | 4681 | -0.31 | -0.24 | -0.44 | 44 | -4.4 | 19 | -0.61 | -0.29 | -0.63 | HARMFUL |
| top 5 qualified/day | 2022-26 | 3327 | -0.21 | +0.01 | -0.57 | 44 | -2.2 | 23 | -0.51 |  | |  |
| top 1 qualified/day | 2015-21 | 1470 | -0.30 | -0.23 | -0.33 | 46 | -2.8 | 15 | -0.60 | -0.27 | -0.71 | no evidence |
| top 1 qualified/day | 2022-26 | 1011 | -0.30 | -0.08 | -0.44 | 45 | -2.0 | 19 | -0.60 |  | |  |

## 20-day hold

| cell | period | n | mean vs SPY % | vs random % | median % | hit % | t | stop % | mean @20bps % | up-trend % | down-trend % | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random member-day | 2015-21 | 24280 | +0.12 | +0.00 | -0.86 | 43 | 0.4 | 39 | -0.18 | +0.00 | +1.04 | no evidence |
| random member-day | 2022-26 | 19105 | -0.51 | +0.00 | -1.55 | 37 | -2.4 | 47 | -0.81 |  | |  |
| volume | 2015-21 | 14636 | -0.24 | -0.36 | -1.11 | 40 | -2.7 | 45 | -0.54 | -0.29 | -0.03 | no evidence |
| volume | 2022-26 | 12752 | -0.42 | +0.09 | -1.49 | 38 | -2.6 | 49 | -0.72 |  | |  |
| breakout | 2015-21 | 16446 | -0.39 | -0.51 | -0.60 | 45 | -2.5 | 23 | -0.69 | -0.38 | -0.57 | no evidence |
| breakout | 2022-26 | 11935 | -0.34 | +0.17 | -0.97 | 44 | -1.7 | 24 | -0.64 |  | |  |
| breakout, no volume | 2015-21 | 15641 | -0.38 | -0.50 | -0.57 | 46 | -2.0 | 23 | -0.68 | -0.37 | -0.53 | no evidence |
| breakout, no volume | 2022-26 | 11388 | -0.30 | +0.21 | -0.95 | 45 | -1.6 | 24 | -0.60 |  | |  |
| breakout x volume | 2015-21 | 4036 | -0.42 | -0.54 | -0.53 | 45 | -3.3 | 16 | -0.72 | -0.41 | -0.85 | HARMFUL |
| breakout x volume | 2022-26 | 2877 | -0.32 | +0.18 | -0.72 | 45 | -1.2 | 16 | -0.62 |  | |  |
| oversold | 2015-21 | 11123 | +0.02 | -0.10 | -1.20 | 39 | -0.1 | 59 | -0.28 | -0.01 | +0.23 | no evidence |
| oversold | 2022-26 | 10078 | -0.45 | +0.05 | -1.78 | 32 | -2.4 | 68 | -0.75 |  | |  |
| overbought | 2015-21 | 16012 | -0.34 | -0.46 | -0.60 | 46 | -1.6 | 21 | -0.64 | -0.37 | -0.15 | no evidence |
| overbought | 2022-26 | 11778 | -0.29 | +0.21 | -0.85 | 45 | -1.8 | 23 | -0.59 |  | |  |
| qualified (live gates) | 2015-21 | 7095 | -0.32 | -0.44 | -0.97 | 41 | -2.9 | 38 | -0.62 | -0.33 | -0.42 | no evidence |
| qualified (live gates) | 2022-26 | 5855 | -0.53 | -0.02 | -1.60 | 37 | -1.9 | 42 | -0.83 |  | |  |
| top 5 qualified/day | 2015-21 | 4328 | -0.43 | -0.54 | -0.97 | 41 | -3.7 | 34 | -0.73 | -0.43 | -0.63 | HARMFUL |
| top 5 qualified/day | 2022-26 | 3085 | -0.24 | +0.27 | -1.18 | 41 | -1.4 | 38 | -0.54 |  | |  |
| top 1 qualified/day | 2015-21 | 1416 | -0.40 | -0.52 | -0.92 | 42 | -2.3 | 29 | -0.70 | -0.39 | -0.46 | no evidence |
| top 1 qualified/day | 2022-26 | 980 | -0.53 | -0.02 | -1.18 | 41 | -1.9 | 35 | -0.83 |  | |  |
