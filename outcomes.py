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

# Separate log of every judge call, rejected candidates included. picks_log only
# ever sees what the judge chose, so it can never say whether the judge beats
# simply alerting on rank()'s top score. Same cache, same disposability.
JUDGE_LOG = pathlib.Path(__file__).parent / "judge_log.jsonl"

# Horizon name -> trading days after the entry day. Graded on that day's close,
# net of SPY over the same bars, so a rising market is not read as skill.
HORIZONS = [("5d", 5), ("20d", 20)]

SIGNAL_NAMES = [("unusual_volume", "volume"), ("breakout_20d", "breakout"),
                ("rsi_oversold", "oversold"), ("rsi_overbought", "overbought")]


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


def last_price(ticker):
    try:
        return float(yf.Ticker(ticker).fast_info["last_price"])
    except Exception:
        log.warning("outcomes: no current price for %s", ticker)
        return None


def _history(ticker, date):
    """Daily closes from the entry day on: [0] is the entry day, [n] is n trading
    days later. Unadjusted, to match the unadjusted price logged at alert time."""
    try:
        closes = yf.Ticker(ticker).history(start=date, auto_adjust=False)["Close"]
        return [float(c) for c in closes] or None
    except Exception:
        log.warning("outcomes: no history for %s, will retry next run", ticker)
        return None


def record(picks, candidates, path=LOG):
    """Append one line per pick: ticker, date, entry price, SPY. Never raises.

    Called from tracker.log_picks for every alert, whether or not the sheet post
    happens — grading must not depend on the webhook being configured.
    """
    try:
        by_ticker = {s["ticker"]: s for s in candidates}
        today = datetime.date.today().isoformat()
        spy = last_price("SPY")
        with open(path, "a") as f:
            for p in picks:
                price = by_ticker.get(p["ticker"], {}).get("facts", {}).get("price")
                if not price:
                    continue  # no entry price means no return to compute later
                f.write(json.dumps({"ticker": p["ticker"], "date": today,
                                    "price": price, "spy": spy, "scored": []}) + "\n")
    except Exception:
        log.exception("outcomes: could not log picks, alert already sent — continuing")


def log_judgment(candidates, picks, spy, path=JUDGE_LOG, today=None):
    """Append one line per judge call — every candidate, the picks (maybe none),
    the model and SPY. Never raises: this is bookkeeping, never worth an alert."""
    try:
        import analyzer
        row = {"date": (today or datetime.date.today()).isoformat(),
               "model": analyzer.MODEL, "spy": spy,
               "picks": [p["ticker"] for p in picks],
               "candidates": [{"ticker": s["ticker"], "score": s.get("score"),
                               "price": s.get("facts", {}).get("price"),
                               "signals": [name for key, name in SIGNAL_NAMES if s.get(key)]}
                              for s in candidates]}
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        log.exception("outcomes: could not log judgment — continuing")


def _due(rows, today):
    """(row index, horizon, trading days) for every pick that may be gradeable.

    Calendar age >= n is only a cheap pre-filter; whether n trading days have
    actually closed is decided by the length of the price history.
    """
    out = []
    for i, row in enumerate(rows):
        try:
            age = (today - datetime.date.fromisoformat(row["date"])).days
        except (KeyError, TypeError, ValueError):
            continue  # a row without a usable date is not gradeable
        for name, n in HORIZONS:
            if age >= n and name not in row.get("scored", []):
                out.append((i, name, n))
    return out


def report(path=LOG, today=None, history_fn=None):
    """Grade whatever has come due, once per horizon. Returns a summary or "".

    `today` and `history_fn` are injected by test_outcomes.py so grading is
    proven offline.
    """
    rows = _load(path)
    if not rows:
        return ""
    today = today or datetime.date.today()
    history_fn = history_fn or _history
    cache = {}

    def hist(ticker, date):
        if (ticker, date) not in cache:
            cache[ticker, date] = history_fn(ticker, date)
        return cache[ticker, date]

    graded = {}
    for i, horizon, n in _due(rows, today):
        row = rows[i]
        if not row.get("price"):
            continue
        t, s = hist(row["ticker"], row["date"]), hist("SPY", row["date"])
        if not t or not s or len(t) <= n or len(s) <= n:
            continue  # not enough closed bars yet, or no data — try next run
        pct = (t[n] / row["price"] - 1) * 100
        # seeded picks predate the stored SPY price; entry-day close stands in
        spy_pct = (s[n] / (row.get("spy") or s[0]) - 1) * 100
        graded.setdefault(horizon, []).append(
            f"{row['ticker']} {pct:+.1f}% ({pct - spy_pct:+.1f} vs SPY)")
        row.setdefault("scored", []).append(horizon)
    if not graded:
        return ""
    _save(path, rows)
    parts = [f"{name}: " + ", ".join(graded[name])
             for name, _ in HORIZONS if name in graded]
    return "Picks scorecard — " + " | ".join(parts)


def _excess(hist, ticker, row, n, price):
    """% return n trading days after the judgment, minus SPY's, or None."""
    t, s = hist(ticker, row["date"]), hist("SPY", row["date"])
    if not t or not s or len(t) <= n or len(s) <= n:
        return None
    return (t[n] / (price or t[0]) - 1) * 100 - (s[n] / (row.get("spy") or s[0]) - 1) * 100


def judge_report(path=JUDGE_LOG, today=None, history_fn=None, min_days=100):
    """Does the judge beat simply alerting on rank()'s top score? Returns "" or one line.

    Per judged day, net of SPY: J = the judge's picks (0 on a day it abstained —
    sitting out a loser is a win), S = the top-score candidate, R = the average
    candidate. Only the current analyzer.MODEL counts; a model change restarts
    the record. Each day is graded once and stored, so history is fetched once.
    After min_days 20-day grades, the backtest-research.md rule is applied: if
    J-S <= 0 and its upper 80% bound is under +0.3 pts, the judge adds nothing.
    """
    import analyzer
    rows = _load(path)
    today = today or datetime.date.today()
    history_fn = history_fn or _history
    cache, changed = {}, False

    def hist(ticker, date):
        if (ticker, date) not in cache:
            cache[ticker, date] = history_fn(ticker, date)
        return cache[ticker, date]

    for row in rows:
        if row.get("model") != analyzer.MODEL or not row.get("candidates"):
            continue
        try:
            age = (today - datetime.date.fromisoformat(row["date"])).days
        except (KeyError, TypeError, ValueError):
            continue
        for name, n in HORIZONS:
            if age < n or name in row.get("graded", {}):
                continue
            ex = {c["ticker"]: _excess(hist, c["ticker"], row, n, c.get("price"))
                  for c in row["candidates"]}
            if None in ex.values():
                continue  # not closed yet or no data — try next run
            top = max(row["candidates"], key=lambda c: c.get("score") or 0)["ticker"]
            picks = [t for t in row.get("picks", []) if t in ex]
            row.setdefault("graded", {})[name] = {
                "J": round(sum(ex[t] for t in picks) / len(picks), 4) if picks else 0.0,
                "S": round(ex[top], 4), "R": round(sum(ex.values()) / len(ex), 4)}
            changed = True
    if changed:
        _save(path, rows)

    parts, verdict = [], ""
    for name, _ in HORIZONS:
        g = [r["graded"][name] for r in rows
             if r.get("model") == analyzer.MODEL and name in r.get("graded", {})]
        if not g:
            continue
        js = [x["J"] - x["S"] for x in g]
        jr = sum(x["J"] - x["R"] for x in g) / len(g)
        mean = sum(js) / len(js)
        parts.append(f"{name} over {len(g)} day{'s' * (len(g) != 1)}: "
                     f"J-S {mean:+.1f}, J-R {jr:+.1f} pts")
        if name == "20d" and len(g) >= min_days:
            sd = (sum((v - mean) ** 2 for v in js) / (len(js) - 1)) ** 0.5
            upper = mean + 1.2816 * sd / len(js) ** 0.5
            verdict = (f" — DROP THE JUDGE: no better than the top score "
                       f"(upper 80% bound {upper:+.2f})" if mean <= 0 and upper < 0.3
                       else f" — judge earns its keep so far (upper 80% bound {upper:+.2f})")
    return ("Judge vs top score — " + " | ".join(parts) + verdict) if parts else ""
