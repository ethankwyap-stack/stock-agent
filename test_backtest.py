"""Offline proof of the backtest math on hand-built bars with known answers."""
import pandas as pd
import pytest

import backtest

DAYS = pd.bdate_range("2020-01-01", periods=40)


def bars(opens, highs, lows, closes, volume=1000.0):
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                         "Close": closes, "Volume": volume}, index=DAYS[:len(closes)])


def flat(n=40, px=100.0):
    return bars([px] * n, [px] * n, [px] * n, [px] * n)


def test_members_on_uses_latest_change_at_or_before_date(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text('date,tickers\n2019-01-02,"AAA,BBB"\n2020-01-03,"AAA,CCC"\n')
    rows = backtest.load_members(p)
    assert backtest.members_on(rows, "2020-01-02") == {"AAA", "BBB"}
    assert backtest.members_on(rows, "2020-01-03") == {"AAA", "CCC"}
    assert backtest.members_on(rows, "2018-12-31") == frozenset()


def test_trade_holds_to_horizon_close():
    # signal on day 10, enter day 11 open at 100, day 16 (5 bars later) closes 110
    df = flat()
    df.loc[DAYS[16], "Close"] = 110.0
    t = backtest.trade(df, 10, stop=95.0, h=5, cost=0.0)
    assert t["ret"] == pytest.approx(0.10)
    assert t["exit"] == DAYS[16] and not t["stopped"]


def test_trade_gap_through_stop_fills_at_open():
    df = flat()
    df.loc[DAYS[13], ["Open", "Low"]] = [90.0, 88.0]  # opens below the 95 stop
    t = backtest.trade(df, 10, stop=95.0, h=5, cost=0.0)
    assert t["ret"] == pytest.approx(-0.10) and t["stopped"] and t["exit"] == DAYS[13]


def test_trade_intraday_stop_fills_at_stop_and_charges_costs():
    df = flat()
    df.loc[DAYS[12], "Low"] = 94.0  # opens 100, trades down through 95
    t = backtest.trade(df, 10, stop=95.0, h=5, cost=0.0005)
    assert t["ret"] == pytest.approx(-0.05 - 0.001) and t["stopped"]


def test_trade_without_enough_future_bars_is_skipped():
    assert backtest.trade(flat(), 36, stop=95.0, h=5, cost=0.0) is None


def test_dedupe_keeps_first_signal_per_holding_period():
    ev = pd.DataFrame({"ticker": ["A", "A", "A", "B"], "pos": [0, 2, 6, 1]})
    assert backtest.dedupe(ev, 5)["pos"].tolist() == [0, 6, 1]


def test_block_t_counts_one_crash_day_as_one_bet():
    # 40 identical losers on one day are one observation, not 40
    vals = [-0.05] * 40 + [0.01, 0.02, 0.03]
    blocks = [0] * 40 + [1, 2, 3]
    t, nb = backtest.block_t(vals, blocks)
    assert nb == 4
    means = pd.Series([-0.05, 0.01, 0.02, 0.03])
    assert t == pytest.approx(means.mean() / means.std() * 2)


def test_events_end_to_end_on_three_tickers():
    """AAA (member) and ZZZ (not a member) get the same breakout+volume bars;
    only AAA may produce a trade. SPY is flat, so excess == raw return."""
    n = 40
    closes = [100 + (i % 2) for i in range(28)] + [110.0] * (n - 28)
    vol = [1000.0] * 28 + [3000.0] + [1000.0] * (n - 29)
    up = bars(closes, [c + 0.5 for c in closes], [c - 0.5 for c in closes], closes, vol)
    up.loc[DAYS[35], "Close"] = 121.0  # 5 bars after the day-30 entry
    data = {"AAA": up, "ZZZ": up.copy(), "SPY": flat()}
    rows = [("2019-01-01", frozenset({"AAA", "SPY"}))]
    ev = backtest.find_events(data, rows, workers=1)
    assert set(ev["ticker"]) == {"AAA"}
    first = ev[~ev["sampled"]].iloc[0]
    assert first["date"] == DAYS[28] and first["unusual_volume"] and first["breakout_20d"]
    trades = backtest.simulate(ev[ev["pos"] == 28], data, h=5, cost=0.0)
    # enter day 29 open (110), exit day 34 close (110): flat; SPY flat too
    assert trades["excess"].iloc[0] == pytest.approx(0.0)
    trades = backtest.simulate(ev[ev["pos"] == 29], data, h=5, cost=0.0)
    # enter day 30 open (110), exit day 35 close (121): +10%
    assert trades["excess"].iloc[0] == pytest.approx(0.10)


def test_baseline_samples_every_tenth_member_day_with_the_same_stop_rule():
    """The control group: random member-days, signal or not, same entry and stop.
    Without it an equal-weight drag vs SPY reads as 'every signal is harmful'."""
    quiet = bars([100.0] * 40, [101.0] * 40, [99.0] * 40, [100.0] * 40)  # no breakout
    data = {"AAA": quiet, "SPY": flat()}
    rows = [("2019-01-01", frozenset({"AAA", "SPY"}))]
    ev = backtest.find_events(data, rows, workers=1)
    base = ev[ev["sampled"]]
    assert base["pos"].tolist() == [20, 30]
    assert not base[backtest.FLAGS].any().any()
    assert base["stop"].tolist() == [97.0, 97.0]  # 3% under a flat 100
    assert "random member-day" in backtest.cells(ev)
