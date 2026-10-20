"""Scorecard grades in trading days against SPY; the judge log keeps rejects too.

Run: .venv/bin/python -m pytest test_outcomes.py -q
"""
import datetime
import json

import analyzer
import outcomes

TODAY = datetime.date(2026, 10, 20)


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def closes(n, start, step):
    """n+1 closes: index 0 is the entry day, index k is k trading days later."""
    return [start + step * k for k in range(n + 1)]


def test_grades_on_trading_day_close_net_of_spy(tmp_path):
    log = tmp_path / "picks.jsonl"
    write(log, [{"ticker": "AAA", "date": "2026-09-01", "price": 100.0,
                 "spy": 500.0, "scored": []}])
    hist = {"AAA": closes(25, 100.0, 1.0), "SPY": closes(25, 500.0, 1.0)}
    card = outcomes.report(log, today=TODAY, history_fn=lambda t, d: hist[t])
    # 5d: AAA 105 = +5.0%, SPY 505 = +1.0% -> +4.0 vs SPY
    assert "AAA +5.0% (+4.0 vs SPY)" in card.split("|")[0], card
    # 20d: AAA 120 = +20.0%, SPY 520 = +4.0% -> +16.0 vs SPY
    assert "AAA +20.0% (+16.0 vs SPY)" in card.split("|")[1], card
    # once-only: nothing comes due twice
    assert outcomes.report(log, today=TODAY, history_fn=lambda t, d: hist[t]) == ""


def test_spy_entry_falls_back_to_entry_day_close(tmp_path):
    # the seeded picks predate the stored spy price
    log = tmp_path / "picks.jsonl"
    write(log, [{"ticker": "AAA", "date": "2026-10-01", "price": 100.0, "scored": []}])
    hist = {"AAA": closes(6, 100.0, 1.0), "SPY": closes(6, 400.0, 4.0)}
    card = outcomes.report(log, today=TODAY, history_fn=lambda t, d: hist[t])
    assert "AAA +5.0% (+0.0 vs SPY)" in card, card


def test_not_enough_trading_days_is_not_graded(tmp_path):
    # 7 calendar days old, but a holiday means only 4 trading days have closed
    log = tmp_path / "picks.jsonl"
    write(log, [{"ticker": "AAA", "date": "2026-10-13", "price": 100.0, "scored": []}])
    hist = {"AAA": closes(4, 100.0, 1.0), "SPY": closes(4, 500.0, 1.0)}
    assert outcomes.report(log, today=TODAY, history_fn=lambda t, d: hist[t]) == ""
    assert json.loads(log.read_text())["scored"] == []


def test_missing_history_retries_later(tmp_path):
    log = tmp_path / "picks.jsonl"
    write(log, [{"ticker": "AAA", "date": "2026-09-01", "price": 100.0, "scored": []}])
    assert outcomes.report(log, today=TODAY, history_fn=lambda t, d: None) == ""
    assert json.loads(log.read_text())["scored"] == []


def test_judge_log_keeps_every_candidate_even_on_a_rejection(tmp_path):
    log = tmp_path / "judge.jsonl"
    cands = [{"ticker": "AAA", "score": 4.0, "unusual_volume": True,
              "breakout_20d": True, "facts": {"price": 10.0}},
             {"ticker": "BBB", "score": 2.5, "rsi_oversold": True, "facts": {"price": 20.0}}]
    outcomes.log_judgment(cands, [], spy=500.0, path=log, today=TODAY)
    outcomes.log_judgment(cands, [{"ticker": "BBB", "line": "x"}], spy=501.0, path=log, today=TODAY)
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["picks"] == [] and rows[1]["picks"] == ["BBB"]
    assert rows[0]["date"] == "2026-10-20" and rows[0]["spy"] == 500.0
    assert rows[0]["model"] == analyzer.MODEL
    assert rows[0]["candidates"] == [
        {"ticker": "AAA", "score": 4.0, "price": 10.0, "signals": ["volume", "breakout"]},
        {"ticker": "BBB", "score": 2.5, "price": 20.0, "signals": ["oversold"]}]


def test_judge_log_never_raises(tmp_path):
    outcomes.log_judgment([{"no": "ticker"}], [], spy=None, path=tmp_path / "x" / "y.jsonl")
