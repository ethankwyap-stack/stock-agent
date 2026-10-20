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


# ------------------------------------------------- judge vs top score (J/S/R)

def judged(date, picks, cands, spy=500.0, model=analyzer.MODEL):
    return {"date": date, "model": model, "spy": spy, "picks": picks,
            "candidates": [{"ticker": t, "score": s, "price": 100.0, "signals": []}
                           for t, s in cands]}


def test_judge_graded_against_top_score_and_average(tmp_path):
    log = tmp_path / "judge.jsonl"
    # judge passed on AAA (top score, +10%) and took BBB (flat); SPY flat
    write(log, [judged("2026-09-01", ["BBB"], [("AAA", 4.0), ("BBB", 3.0)])])
    hist = {"AAA": closes(25, 100.0, 0.5), "BBB": closes(25, 100.0, 0.0),
            "SPY": closes(25, 500.0, 0.0)}
    line = outcomes.judge_report(log, today=TODAY, history_fn=lambda t, d: hist[t])
    # 20d: J = BBB 0, S = AAA +10, R = mean(+10, 0) = +5
    assert "20d over 1 day: J-S -10.0, J-R -5.0 pts" in line, line
    row = json.loads(log.read_text())
    assert row["graded"]["20d"] == {"J": 0.0, "S": 10.0, "R": 5.0}
    # once-only: graded days are never re-fetched
    assert outcomes.judge_report(log, today=TODAY, history_fn=lambda t, d: 1 / 0)


def test_judge_abstaining_scores_zero_so_dodging_a_loser_counts(tmp_path):
    log = tmp_path / "judge.jsonl"
    write(log, [judged("2026-09-01", [], [("AAA", 4.0)])])
    hist = {"AAA": closes(25, 100.0, -0.5), "SPY": closes(25, 500.0, 0.0)}
    line = outcomes.judge_report(log, today=TODAY, history_fn=lambda t, d: hist[t])
    assert "J-S +10.0" in line, line


def test_judge_report_ignores_other_models_and_unclosed_days(tmp_path):
    log = tmp_path / "judge.jsonl"
    write(log, [judged("2026-09-01", ["AAA"], [("AAA", 4.0)], model="old-model"),
                judged("2026-10-19", ["AAA"], [("AAA", 4.0)])])
    hist = {"AAA": closes(1, 100.0, 1.0), "SPY": closes(1, 500.0, 0.0)}
    assert outcomes.judge_report(log, today=TODAY, history_fn=lambda t, d: hist[t]) == ""


def test_judge_decision_rule_fires_after_enough_days(tmp_path):
    log = tmp_path / "judge.jsonl"
    rows = [judged("2026-09-01", ["BBB"], [("AAA", 4.0), ("BBB", 3.0)])] * 3
    write(log, rows)
    hist = {"AAA": closes(25, 100.0, 0.5), "BBB": closes(25, 100.0, 0.0),
            "SPY": closes(25, 500.0, 0.0)}
    line = outcomes.judge_report(log, today=TODAY, history_fn=lambda t, d: hist[t],
                                 min_days=3)
    assert "DROP THE JUDGE" in line, line
