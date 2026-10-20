# Backtesting research — stock-agent (2026-10-20)

## 1. TL;DR
- **Backtest the price layer only.** That means the screens, the `rank()` weights and the gates, over about 10 years. Sentiment, analyst targets and the Claude judge can't be honestly backtested for free.
- **Build it ourselves.** A plain-pandas "event study" of about 120 lines reuses `screener.py`'s own math. An event study means: for every day a signal fired, what happened over the next 5 and 20 trading days. No new dependencies, and it runs on your 3.9 venv.
- **The 11 live picks prove nothing.** The error bar is about ±2.4 percentage points (pitfalls report). At the current alert rate, the live scorecard won't mean anything for about 2 years (signals report).
- **The best change to ship now is a shadow log.** Log every candidate the judge sees, not just the picks. That is the only way to ever measure the judge.
- **Expected result** (signals report): the edge most likely sits in **high-volume breakouts at 20d** and **low-volume oversold names at 5d**. Breakouts on normal volume, the overbought −1, and analyst upside probably add nothing.

## 2. What we can and can't backtest for $0

| Component | Free backtest? | How, or why not |
|---|---|---|
| Volume, breakout, RSI, volatility signals | Yes | yfinance daily bars, point-in-time members |
| `rank()` weights, MIN_FAMILIES, vol gate | Yes | Sentiment term set to 0 |
| `stop_ref` exits, 5d/20d grading | Yes | Check each day's Low, fill gap-aware |
| 52-week position, beta | Yes | Computed from the same bars |
| Earnings proximity | Yes, with work | [`stocks-earnings-dates`](https://pypi.org/project/stocks-earnings-dates/) (SEC 8-K dates) |
| P/E | Partly | SEC `companyfacts`, only facts filed before the date ([guide](https://arkolith.com/blog/sec-edgar-api-guide)) |
| Headline sentiment | Partly | [FNSPID](https://arxiv.org/abs/2402.06698) ends in 2023 and uses different news sources. Defer it. |
| Analyst target / upside gate | **No** | No free archive. Run the backtest with the gate on and off. |
| Claude judge | **No, for any date before Feb 2026** | The model remembers what happened next (section 6) |

## 3. Tool decision

**Top pick: build it.** Write `backtest.py` as a pandas event study that calls the same signal functions as `screener.py`.
- Every framework would mean writing a second copy of the screen logic, and the copies would drift apart.
- Most frameworks also need Python 3.11 or newer. Your local venv is 3.9.

**Add-on for later: [alphalens-reloaded](https://github.com/stefan-jansen/alphalens-reloaded).** 671 stars, last commit 2026-10-17, Apache-2.0.
- It reports IC (information coefficient: how well today's score ranks the stocks by their later return) and the returns of each score bucket.
- It needs Python 3.11 or newer, so run it on Actions or after upgrading the venv.

**Runner-up: [vectorbt](https://github.com/polakowo/vectorbt).** 9.5k stars, last commit 2026-10-19, Apache-2.0 plus Commons Clause (free to use, you just can't sell it).
- Only worth it if sweeping hundreds of parameter combinations gets slow in pandas.

**Skip these:**
- backtesting.py: tests one ticker at a time, and it's AGPL.
- backtrader: no commits since 2023.
- zipline: loading our data into it is painful.
- LEAN: its CLI needs a paid organization ([docs](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment)).

## 4. Data plan
- **Prices:** yfinance daily bars from 2015 onward. Pull them once, locally on your Mac, in chunks of 100 with pauses.
  - Yahoo blocks bulk pulls with 429 errors, sometimes for more than 24 hours ([#2422](https://github.com/ranaroussi/yfinance/issues/2422)).
  - Don't pull from Actions. A blocked runner would also break the live screener.
  - Store both adjusted and raw bars (`auto_adjust=False`), and pin the yfinance version.
- **Survivorship fix:** use [fja05680/sp500](https://github.com/fja05680/sp500) (MIT, about 525 stars, updated Jul 2026).
  - Survivorship bias means testing only on companies that survived to today, which makes results look too good.
  - On each date, screen only the stocks that were in the index that day. `sp500_tickers()` gives today's list and inflates results; pre-index returns run about 2× post-index ([Robot Wealth](https://robotwealth.com/how-to-get-historical-spx-constituents-data-for-free/)).
  - **Remaining gap:** Yahoo has no prices for delisted names.
  - Log the share of member-days with missing data, per year.
  - Treat `rsi_oversold` results as an upper bound. The oversold stocks that went bust are exactly the ones missing.
- **Storage:** about 25 MB (`bars.pkl`), gitignored, kept on the Mac.
  - Don't commit it: a changing binary bloats the history of a private repo.
  - Don't keep it in the Actions cache: entries expire after 7 idle days ([changelog](https://github.blog/changelog/2025-11-20-github-actions-cache-size-can-now-exceed-10-gb-per-repository/)).

## 5. Traps, worst first

1. **Partial-bar look-ahead.** Live runs see half a day's volume. A backtest sees the full day.
   - **Fix:** signal on day *t*'s close, buy at day *t+1*'s open. Never enter at the close that made the signal.
   - Later, consider moving live alerts to the existing `"digest"` window, so live and backtest use the same definition.
2. **The judge remembers the past.** In one study, GPT-4o got 80.6% of S&P directions right before its cutoff and 45.7% after ([arXiv 2504.14765](https://arxiv.org/html/2504.14765v2)). Anonymizing the data doesn't fix this.
   - **Fix:** see section 6.
3. **Survivorship.** **Fix:** the fja05680 membership above.
4. **Snapshot fundamentals.** `facts.py` and `sentiment.py` only describe today. **Fix:** leave them out of the backtest.
5. **Overfitting across many trials.** 4 signals × thresholds × weights × gates × 2 horizons is hundreds of combinations, so the best one will look good by luck.
   - **Fix:** keep the grid coarse: RSI {25, 30, 35}, volume {1.5, 2, 3}.
   - Append every configuration you run to `trials.jsonl`.
   - Use the Deflated Sharpe Ratio, which discounts the best result for how many you tried ([SSRN 2460551](https://papers.ssrn.com/abstract=2460551)). It's about 20 lines with scipy.
   - Require t > 3 ([NBER w20592](https://nber.org/papers/w20592)).
6. **Overlapping windows inflate confidence.** 40 signals on one crash day are really one bet.
   - **Fix:** keep only the first signal per ticker per holding period.
   - Build one daily portfolio return series, or use non-overlapping 20-day blocks ([Quantpedia](https://quantpedia.com/?p=812)).
7. **Raw returns with no benchmark.** Today `outcomes.py` grades raw % change, so a bull market looks like skill. **Fix:** subtract SPY over the same window, in both the backtest and live grading.
8. **Stops that gap through.** **Fix:** if the open is below the stop, fill at the open. Otherwise fill at the stop if the day's Low reaches it.
   - Report results with and without names that have earnings within 7 days.
9. **Costs.** Charge 5 bps per side, and stress-test at 20 bps. A signal that dies at 20 bps was never real.
10. **Calendar-day grading.** `HORIZONS = [("5d", 7), ("20d", 28)]` measures calendar days, at whatever price exists when the run happens to fire. **Fix:** use the close 5 and 20 *trading* days after entry.

**Contradictions I resolved:**
- **Test window.** Tools said use today's list over 2–3 years; data said start around 2019. I picked point-in-time membership from 2015, which gives more signals while keeping the bias visible.
- **Where it runs.** Tools said one Actions job; data said run locally. I picked local, because of the rate limits and the minutes budget.

## 6. Testing the Claude judge without look-ahead

The judge runs `claude -p --model claude-sonnet-5` (`analyzer.py:262`). Sonnet 5's knowledge cutoff is **January 2026** ([docs](https://platform.claude.com/docs/en/models/sonnet-5/)). "Never replay the judge" and "replay is fine" disagreed between reports; I resolved it like this:

1. **Never count a replay from before Feb 2026 as evidence.** Use those dates only as a leak check: run named vs anonymized, and if named wins only before the cutoff, that's memory.
2. **Shadow log (now).** After `analyzer.judge(candidates)` (`main.py:223`), append `{date, model, candidates[ticker, score, price, signals], picks, abstained}` to `judge_log.jsonl` on every call, including empty ones. Cache it like `picks_log.jsonl`.
3. **Compare three arms on the same day:**
   - **J** = what the judge picked.
   - **S** = `rank()`'s top-1 from the same candidates.
   - **R** = the average of all candidates.
   - Judge skill is J−S and J−R, net of SPY. On days the judge picks nothing, record what S would have earned.
4. **Optional replay, Feb to Sep 2026.** This is about 160 days of price-only fact packs.
   - Run about 40 calls a night locally and save to a resumable `replay.jsonl`.
   - Run 20 dates twice. If the picks agree less than 70% of the time, most of any "edge" is noise.
   - Report the replay separately from the live log, because the replay judge has no sentiment or facts.
5. **Any model change restarts the clock.** Sonnet 5.5's cutoff is June 2026.

## 7. Metrics and pass bar

For each signal cell (volume, breakout, oversold, overbought, breakout×volume), at 5d and 20d, report:
- mean and median excess return over SPY
- hit rate on excess return
- rank IC
- the overlap-safe t-stat
- stop-hit rate
- the same numbers split by year, by SPY above or below its 200-day average, and by volatility tercile

**Change a weight or drop a signal only if all of these hold:**
- t > 3 on the tune years (2015–2021), with 20 trading days purged at the boundary.
- The same sign holds on the test years (2022–2026). Run the test **once**.
- It survives 20 bps costs.
- It holds in both the up-trend and down-trend split.

Otherwise leave it as it is.

**Judge decision rule:** after 100 pooled judged days, if J−S ≤ 0 and the upper 80% bound is under +0.3%, drop the judge and alert on S.

## 8. Build plan, smallest first

1. **Benchmark live grading.** In `outcomes.py`, subtract SPY over the same window and switch to trading-day horizons.
   - **Works when:** one test with a hand-made price series checks the excess-return math, and the digest shows "vs SPY".
2. **Shadow log.** Change `main.py` to write `judge_log.jsonl`, and add it to the cache step in `run.yml`.
   - **Works when:** a `--force` run writes one line that includes the rejected candidates.
3. **Pure signals.** Pull a `signals(df)` function out of `screener.scan()` without changing its behavior.
   - **Works when:** the existing `screener.py` self-check passes, and a live scan gives the same flags as before.
4. **`backtest.py` plus a one-time `fetch_bars.py`.** Load the fja05680 members and the cached bars, enter at *t+1*'s open, apply the gap-aware stop and costs, dedupe, subtract SPY, and log to `trials.jsonl`. Add `bars.pkl` to `.gitignore`.
   - **Works when:** there is one table per signal cell, and an assert passes on a fake 3-ticker frame with a known answer.
5. **Grade J/S/R.** Extend `outcomes.py` to grade all three arms from `judge_log.jsonl`. Add DSR to the backtest report.
   - **Works when:** a test on a hand-made 3-candidate day passes.

## 9. Open questions
1. Should live alerts move to the post-close digest so they match the backtest, at the cost of same-day timing?
2. Should we spend about 4 nights of plan usage on the Feb–Sep 2026 judge replay, or rely on the shadow log only?
3. If breakout without volume fails the bar, are you OK with moving its +2 onto the breakout×volume cell only?

**Learned:** The key finding is that the backtest can't grade the Claude judge before February 2026, so the judge has to be measured from the live log. I chose a home-built event study over vectorbt or alphalens because it reuses the screener's own code and runs on Python 3.9. The concept worth remembering is *parametric look-ahead*: the model's training data already contains what the market did later, so a replay of those dates rewards memory instead of judgment.