# Backtest results — price-only screens

Generated 2026-10-20 by `backtest.py`. Signals 2014-06-30 to 2026-10-19, S&P 500 point-in-time members only. Entry next open, gap-aware stop at `stop_ref`, 5 bps per side, returns minus SPY over the same days. Tune 2015-2021, test 2022 on (test run once). t is over non-overlapping h-day blocks. Verdict bar: |t| > 3 in tune, same sign in test, survives 20 bps, holds in up- and down-trends (SPY vs its 200-day).

Not in here: sentiment, analyst targets, earnings, the Claude judge. The families count has no earnings family, so `qualified` is a little stricter than live.

**Missing data** — member-days with no Yahoo bars (delisted or renamed names). Results lean optimistic where this is high, oversold most of all:

| year | missing % |
|---|---|
| 2015 | 27.7 |
| 2016 | 24.7 |
| 2017 | 21.9 |
| 2018 | 20.2 |
| 2019 | 17.5 |
| 2020 | 14.6 |
| 2021 | 12.7 |
| 2022 | 10.1 |
| 2023 | 7.8 |
| 2024 | 6.3 |
| 2025 | 4.9 |
| 2026 | 3.2 |

## 5-day hold

| cell | period | n | mean vs SPY % | vs random % | median % | hit % | t | stop % | mean @20bps % | up-trend % | down-trend % | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random member-day | 2015-21 | 71107 | -0.07 | +0.00 | -0.26 | 46 | -1.9 | 19 | -0.37 | -0.12 | +0.20 | no evidence |
| random member-day | 2022-26 | 55937 | -0.22 | +0.00 | -0.50 | 44 | -3.2 | 25 | -0.52 |  | |  |
| volume | 2015-21 | 19068 | -0.18 | -0.10 | -0.43 | 44 | -2.9 | 28 | -0.48 | -0.18 | -0.16 | no evidence |
| volume | 2022-26 | 16417 | -0.24 | -0.02 | -0.54 | 44 | -3.2 | 29 | -0.54 |  | |  |
| breakout | 2015-21 | 30075 | -0.22 | -0.15 | -0.18 | 47 | -3.1 | 5 | -0.52 | -0.20 | -0.45 | HARMFUL |
| breakout | 2022-26 | 21439 | -0.21 | +0.01 | -0.26 | 47 | -3.3 | 5 | -0.51 |  | |  |
| breakout, no volume | 2015-21 | 28062 | -0.22 | -0.14 | -0.18 | 47 | -2.7 | 5 | -0.52 | -0.19 | -0.44 | no evidence |
| breakout, no volume | 2022-26 | 20069 | -0.21 | +0.01 | -0.27 | 47 | -3.2 | 5 | -0.51 |  | |  |
| breakout x volume | 2015-21 | 4242 | -0.34 | -0.27 | -0.30 | 46 | -3.5 | 5 | -0.64 | -0.31 | -0.63 | HARMFUL |
| breakout x volume | 2022-26 | 3018 | -0.31 | -0.09 | -0.38 | 46 | -2.1 | 4 | -0.61 |  | |  |
| oversold | 2015-21 | 20761 | -0.12 | -0.05 | -0.48 | 43 | -1.0 | 39 | -0.42 | -0.14 | -0.03 | no evidence |
| oversold | 2022-26 | 19961 | -0.22 | -0.01 | -0.77 | 41 | -2.3 | 44 | -0.52 |  | |  |
| overbought | 2015-21 | 34926 | -0.19 | -0.12 | -0.19 | 47 | -3.4 | 4 | -0.49 | -0.18 | -0.27 | HARMFUL |
| overbought | 2022-26 | 25290 | -0.12 | +0.10 | -0.14 | 48 | -1.6 | 4 | -0.42 |  | |  |
| qualified (live gates) | 2015-21 | 7923 | -0.30 | -0.23 | -0.47 | 44 | -4.5 | 26 | -0.60 | -0.28 | -0.39 | HARMFUL |
| qualified (live gates) | 2022-26 | 6442 | -0.39 | -0.17 | -0.69 | 42 | -3.0 | 27 | -0.69 |  | |  |
| top 5 qualified/day | 2015-21 | 4657 | -0.32 | -0.25 | -0.44 | 44 | -4.4 | 20 | -0.62 | -0.30 | -0.42 | HARMFUL |
| top 5 qualified/day | 2022-26 | 3303 | -0.25 | -0.03 | -0.59 | 43 | -2.4 | 24 | -0.55 |  | |  |
| top 1 qualified/day | 2015-21 | 1464 | -0.32 | -0.25 | -0.35 | 46 | -3.0 | 15 | -0.62 | -0.29 | -0.49 | no evidence |
| top 1 qualified/day | 2022-26 | 1012 | -0.30 | -0.09 | -0.44 | 45 | -2.1 | 19 | -0.60 |  | |  |

## 20-day hold

| cell | period | n | mean vs SPY % | vs random % | median % | hit % | t | stop % | mean @20bps % | up-trend % | down-trend % | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random member-day | 2015-21 | 35554 | -0.13 | +0.00 | -1.09 | 42 | -1.6 | 39 | -0.43 | -0.21 | +0.27 | no evidence |
| random member-day | 2022-26 | 27735 | -0.41 | +0.00 | -1.63 | 38 | -2.3 | 46 | -0.71 |  | |  |
| volume | 2015-21 | 14561 | -0.24 | -0.11 | -1.11 | 40 | -2.8 | 45 | -0.54 | -0.28 | -0.05 | no evidence |
| volume | 2022-26 | 12630 | -0.44 | -0.03 | -1.50 | 38 | -2.7 | 49 | -0.74 |  | |  |
| breakout | 2015-21 | 16483 | -0.38 | -0.25 | -0.58 | 46 | -2.5 | 23 | -0.68 | -0.37 | -0.44 | no evidence |
| breakout | 2022-26 | 11996 | -0.36 | +0.05 | -1.02 | 44 | -1.8 | 24 | -0.66 |  | |  |
| breakout, no volume | 2015-21 | 15674 | -0.38 | -0.24 | -0.56 | 46 | -2.1 | 23 | -0.68 | -0.37 | -0.45 | no evidence |
| breakout, no volume | 2022-26 | 11449 | -0.33 | +0.08 | -1.00 | 44 | -1.7 | 24 | -0.63 |  | |  |
| breakout x volume | 2015-21 | 3965 | -0.43 | -0.30 | -0.54 | 45 | -3.3 | 16 | -0.73 | -0.42 | -0.49 | HARMFUL |
| breakout x volume | 2022-26 | 2820 | -0.38 | +0.03 | -0.76 | 45 | -1.3 | 16 | -0.68 |  | |  |
| oversold | 2015-21 | 11107 | -0.01 | +0.13 | -1.17 | 39 | -0.4 | 59 | -0.31 | -0.01 | +0.01 | no evidence |
| oversold | 2022-26 | 10066 | -0.43 | -0.02 | -1.77 | 32 | -2.0 | 67 | -0.73 |  | |  |
| overbought | 2015-21 | 16082 | -0.34 | -0.20 | -0.58 | 46 | -1.3 | 21 | -0.64 | -0.37 | -0.10 | no evidence |
| overbought | 2022-26 | 11782 | -0.34 | +0.07 | -0.87 | 45 | -2.1 | 23 | -0.64 |  | |  |
| qualified (live gates) | 2015-21 | 6995 | -0.33 | -0.20 | -0.97 | 41 | -3.0 | 38 | -0.63 | -0.33 | -0.34 | HARMFUL |
| qualified (live gates) | 2022-26 | 5753 | -0.55 | -0.14 | -1.61 | 37 | -2.1 | 42 | -0.85 |  | |  |
| top 5 qualified/day | 2015-21 | 4292 | -0.43 | -0.29 | -0.97 | 41 | -3.8 | 34 | -0.73 | -0.43 | -0.39 | HARMFUL |
| top 5 qualified/day | 2022-26 | 3062 | -0.29 | +0.12 | -1.27 | 40 | -1.7 | 38 | -0.59 |  | |  |
| top 1 qualified/day | 2015-21 | 1408 | -0.41 | -0.28 | -0.97 | 42 | -2.3 | 29 | -0.71 | -0.42 | -0.40 | no evidence |
| top 1 qualified/day | 2022-26 | 983 | -0.56 | -0.15 | -1.22 | 41 | -2.0 | 35 | -0.86 |  | |  |
