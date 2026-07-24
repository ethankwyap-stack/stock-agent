"""Score past picks so the system can see its own hit rate.

Picks were logged and never graded, so nothing here could tell a good call from a
lucky one. This keeps a local history and reports returns at two horizons.

The tracking sheet cannot be the source of truth for that: `sheet_webhook.gs`
exposes only `doPost`, so the webhook is write-only and the rows can't be read
back. Hence `picks_log.jsonl`, written alongside every sheet post.
"""
import datetime
import json
import logging
import pathlib

import yfinance as yf

log = logging.getLogger("stock-agent")

# Sits next to state.json in the repo dir and rides the same Actions cache. A
# cache eviction loses the history, which only costs one scorecard — the alerts
# themselves never depend on this file.
LOG = pathlib.Path(__file__).parent / "picks_log.jsonl"

# Horizon name -> calendar days of age that make it due.
# ponytail: 5 and 20 trading days approximated as 7 and 28 calendar days rather
# than pulling in a market calendar; a holiday shifts a scorecard by a day, which
# does not change a hit-rate readout.
HORIZONS = [("5d", 7), ("20d", 28)]


def _load(path):
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # one truncated line must not lose the whole history
    except FileNotFoundError:
        return []
    return rows


def _save(path, rows):
    # ponytail: plain rewrite, not write-and-rename — the file is disposable by
    # design, and _load already skips any line a crash left half-written
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _last_price(ticker):
    try:
        return float(yf.Ticker(ticker).fast_info["last_price"])
    except Exception:
        log.warning("outcomes: no current price for %s, will retry next run", ticker)
        return None


def record(picks, candidates, path=LOG):
    """Append one line per pick: ticker, date, entry price. Never raises.

    Called from tracker.log_picks for every alert, whether or not the sheet post
    happens — grading must not depend on the webhook being configured.
    """
    try:
        by_ticker = {s["ticker"]: s for s in candidates}
        today = datetime.date.today().isoformat()
        with open(path, "a") as f:
            for p in picks:
                price = by_ticker.get(p["ticker"], {}).get("facts", {}).get("price")
                if not price:
                    continue  # no entry price means no return to compute later
                f.write(json.dumps({"ticker": p["ticker"], "date": today,
                                    "price": price, "scored": []}) + "\n")
    except Exception:
        log.exception("outcomes: could not log picks, alert already sent — continuing")


def _due(rows, today):
    """(row index, horizon) for every pick old enough to grade and not yet graded."""
    out = []
    for i, row in enumerate(rows):
        try:
            age = (today - datetime.date.fromisoformat(row["date"])).days
        except (KeyError, TypeError, ValueError):
            continue  # a row without a usable date is not gradeable
        for name, cal_days in HORIZONS:
            if age >= cal_days and name not in row.get("scored", []):
                out.append((i, name))
    return out


def report(path=LOG, today=None, price_fn=None):
    """Grade whatever has come due, once per horizon. Returns a summary or "".

    `today` and `price_fn` are injected by the self-check so the bucketing can be
    proven offline.
    """
    rows = _load(path)
    if not rows:
        return ""
    today = today or datetime.date.today()
    price_fn = price_fn or _last_price
    graded = {}
    for i, horizon in _due(rows, today):
        row = rows[i]
        if not row.get("price"):
            continue
        now_price = price_fn(row["ticker"])
        if now_price is None:
            continue  # leave it unmarked and try again next run
        pct = (now_price / row["price"] - 1) * 100
        graded.setdefault(horizon, []).append(f"{row['ticker']} {pct:+.1f}%")
        row.setdefault("scored", []).append(horizon)
    if not graded:
        return ""
    _save(path, rows)
    parts = [f"{name}: " + ", ".join(graded[name])
             for name, _ in HORIZONS if name in graded]
    return "Picks scorecard — " + " | ".join(parts)


if __name__ == "__main__":
    import tempfile

    today = datetime.date(2026, 7, 24)

    def _ago(n):
        return (today - datetime.timedelta(days=n)).isoformat()

    rows = [{"ticker": "NEW", "date": _ago(3), "price": 100.0, "scored": []},
            {"ticker": "MID", "date": _ago(10), "price": 100.0, "scored": []},
            {"ticker": "OLD", "date": _ago(30), "price": 100.0, "scored": []}]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
        path = pathlib.Path(f.name)

    prices = {"NEW": 110.0, "MID": 103.0, "OLD": 90.0}  # stubbed: fully offline

    # bucketing: 10 days old is 5d-due only, 30 days old is due at both horizons,
    # 3 days old is too new to grade at all
    card = report(path, today=today, price_fn=prices.get)
    assert "5d:" in card and "MID +3.0%" in card, card
    assert "20d:" in card and "OLD -10.0%" in card, card
    assert "NEW" not in card, card

    # once-only: nothing comes due twice on the same day
    assert report(path, today=today, price_fn=prices.get) == ""

    # ...but a horizon that matures later still fires exactly once
    card2 = report(path, today=today + datetime.timedelta(days=20), price_fn=prices.get)
    assert "20d: MID +3.0%" in card2, card2   # MID's 20d matured
    assert "5d: NEW +10.0%" in card2, card2   # NEW's 5d matured
    assert "OLD" not in card2, card2          # OLD was already graded at both

    # a price lookup that fails must not mark the pick graded
    fresh = [{"ticker": "GONE", "date": _ago(10), "price": 100.0, "scored": []}]
    _save(path, fresh)
    assert report(path, today=today, price_fn=lambda t: None) == ""
    assert _load(path)[0]["scored"] == []
    assert "GONE" in report(path, today=today, price_fn=lambda t: 105.0)

    # an empty or missing log is silence, not a crash
    assert report(pathlib.Path("/nonexistent/picks_log.jsonl"), today=today) == ""
    path.unlink()
    print("outcomes self-check ok")
