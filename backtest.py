"""Event study of the price-only screens, 2015 on. Local only; needs fetch_bars.py first.

For every member-day a signal fired: enter at the NEXT day's open, hold 5 or 20
trading days with a gap-aware stop at stop_ref, net of costs and of SPY over the
same days. The signals come from screener.signals() itself, so this measures the
live code, not a copy of it. Sentiment, analyst targets, earnings and the Claude
judge are absent: none of them can be replayed honestly (backtest-research.md).

    .venv/bin/python backtest.py            # writes backtest-results.md
    .venv/bin/python backtest.py --fresh    # recompute the cached signal events
"""
import bisect
import csv
import datetime
import json
import multiprocessing
import pathlib
import sys

import pandas as pd

import analyzer
import screener
from main import MIN_FAMILIES, MIN_SCORE

DATA = pathlib.Path(__file__).parent / "data"
BARS, MEMBERS, EVENTS = DATA / "bars.pkl", DATA / "members.csv", DATA / "events.pkl"
TRIALS = pathlib.Path(__file__).parent / "trials.jsonl"
RESULTS = pathlib.Path(__file__).parent / "backtest-results.md"

START = "2015-01-01"
SPLIT = "2022-01-01"   # tune on 2015-2021, test once on 2022 on
WINDOW = 63            # bars per signals() call — the live scan's period="3mo"
COST = 0.0005          # per side; COST_STRESS is the "was it ever real" check
COST_STRESS = 0.002
HORIZONS = (5, 20)
T_BAR = 3.0
FLAGS = ["unusual_volume", "breakout_20d", "rsi_oversold", "rsi_overbought"]
SAMPLE_EVERY = 10      # control group: every 10th member-day, signal or not


def load_members(path):
    """[(date, frozenset of tickers)], oldest first, one row per index change."""
    with open(path, newline="") as f:
        rows = [(r["date"], frozenset(r["tickers"].split(",")))
                for r in csv.DictReader(f)]
    return sorted(rows, key=lambda r: r[0])


def members_on(rows, date):
    i = bisect.bisect_right([d for d, _ in rows], str(date)[:10])
    return rows[i - 1][1] if i else frozenset()


def _scan_ticker(args):
    """Every member-day signal for one ticker, plus the sampled control days
    (worker process)."""
    ticker, df, member_days = args
    out = []
    for pos in range(20, len(df) - 1):
        if df.index[pos] not in member_days:
            continue
        window = df.iloc[max(0, pos - WINDOW + 1):pos + 1]
        sig = screener.signals(window)
        sampled = pos % SAMPLE_EVERY == 0
        if not sig and not sampled:
            continue
        close = window["Close"]
        stop = sig["stop_ref"] if sig else screener.invalidation_level(
            round(float(close.iloc[-1]), 2), float(close.iloc[-21:-1].min()))
        row = {"ticker": ticker, "pos": pos, "date": df.index[pos], "stop": stop,
               "sampled": sampled, **{k: bool(sig and sig.get(k)) for k in FLAGS}}
        analyzer.rank([row], {}, {})  # no sentiment or earnings in a backtest
        row["families"] = analyzer.signal_types(row)
        out.append(row)
    return out


def member_days(data, rows, start=START):
    """{ticker: set of index dates it was a member}, and the missing-data count
    per year — member-days Yahoo has no bar for (mostly delisted names)."""
    days = {}
    for d in data["SPY"].index[data["SPY"].index >= start]:
        for t in members_on(rows, d):
            days.setdefault(t, set()).add(d)
    missing = {}
    for t, ds in days.items():
        have = set(data[t].index) if data.get(t) is not None else set()
        for d in ds:
            y = missing.setdefault(d.year, [0, 0])
            y[0] += d not in have
            y[1] += 1
    return days, missing


def find_events(data, rows, workers=None):
    days, _ = member_days(data, rows, start="1900-01-01")
    jobs = [(t, df, days[t]) for t, df in data.items()
            if t != "SPY" and df is not None and t in days]
    if workers == 1:
        found = map(_scan_ticker, jobs)
    else:
        with multiprocessing.Pool(workers) as pool:
            found = pool.map(_scan_ticker, jobs, chunksize=4)
    return pd.DataFrame([r for rs in found for r in rs])


def trade(df, i, stop, h, cost):
    """Signal on bar i's close; buy bar i+1's open, sell bar i+1+h's close —
    unless the stop goes first: an open at or under it fills at that open
    (a gap straight through), otherwise a low that touches it fills at it."""
    e, x = i + 1, i + 1 + h
    if x >= len(df):
        return None
    o, lo, c = df["Open"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy()
    for d in range(e, x + 1):
        if o[d] <= stop:
            fill, stopped = o[d], True
            break
        if lo[d] <= stop:
            fill, stopped = stop, True
            break
    else:
        d, fill, stopped = x, c[x], False
    return {"entry": df.index[e], "exit": df.index[d], "stopped": stopped,
            "ret": fill / o[e] - 1 - 2 * cost}


def simulate(events, data, h, cost):
    """One trade per event, with SPY over the same entry-open to exit-close."""
    spy = data["SPY"]
    cal = {d: k for k, d in enumerate(spy.index)}
    out = []
    for ev in events.itertuples(index=False):
        t = trade(data[ev.ticker], ev.pos, ev.stop, h, cost)
        if t is None or t["entry"] not in cal or t["exit"] not in cal:
            continue
        spy_ret = spy["Close"][t["exit"]] / spy["Open"][t["entry"]] - 1
        out.append({**ev._asdict(), **t, "excess": t["ret"] - spy_ret,
                    "block": cal[t["entry"]] // h})
    return pd.DataFrame(out)


def dedupe(ev, h):
    """First signal per ticker per holding period — overlapping trades on the
    same name are one bet, not several."""
    keep, last = [], {}
    for idx, t, p in sorted(zip(ev.index, ev["ticker"], ev["pos"]), key=lambda r: (r[1], r[2])):
        if t not in last or p > last[t] + h:  # last exits on bar last+1+h's close
            keep.append(idx)
            last[t] = p
    return ev[ev.index.isin(keep)]


def block_t(vals, blocks):
    """t-stat over per-block means: every signal entering in the same h-day
    block counts once, so a crash day with 40 signals is one observation.
    ponytail: neighbouring blocks still overlap (a trade entering late in block
    k runs into k+1), so t reads somewhat high — it can only overstate an edge,
    never hide one. Newey-West if a cell ever lands near the bar."""
    m = pd.Series(list(vals)).groupby(list(blocks)).mean()
    if len(m) < 2 or m.std() == 0:
        return float("nan"), len(m)
    return float(m.mean() / m.std() * len(m) ** 0.5), len(m)


def cells(ev):
    """Signal cell name -> boolean mask over events."""
    q = (ev["score"] >= MIN_SCORE) & (ev["families"] >= MIN_FAMILIES)
    ranked = ev[q].sort_values(["date", "score", "ticker"], ascending=[True, False, True])
    nth = ranked.groupby("date").cumcount()
    return {
        "random member-day": ev["sampled"],
        "volume": ev["unusual_volume"],
        "breakout": ev["breakout_20d"],
        "breakout, no volume": ev["breakout_20d"] & ~ev["unusual_volume"],
        "breakout x volume": ev["breakout_20d"] & ev["unusual_volume"],
        "oversold": ev["rsi_oversold"],
        "overbought": ev["rsi_overbought"],
        "qualified (live gates)": q,
        "top 5 qualified/day": ev.index.isin(nth[nth < 5].index),
        "top 1 qualified/day": ev.index.isin(nth[nth < 1].index),
    }


def stats(tr, extra_cost=0.0):
    if tr.empty:
        return {"n": 0}
    x = tr["excess"] - extra_cost
    t, nb = block_t(x, tr["block"])
    return {"n": len(tr), "blocks": nb, "mean": x.mean() * 100, "median": x.median() * 100,
            "hit": (x > 0).mean() * 100, "t": t, "stop": tr["stopped"].mean() * 100}


def verdict(tune, test, stress_tune, stress_test, up, down):
    """The research report's bar: t > 3 in-sample, same sign out of sample,
    survives 20 bps, holds in up- and down-trends. Anything else: no evidence."""
    if tune.get("n", 0) < 30 or not abs(tune["t"]) > T_BAR:
        return "no evidence"
    sign = 1 if tune["mean"] > 0 else -1
    ok = (test.get("n", 0) and sign * test["mean"] > 0
          and sign * stress_tune["mean"] > 0 and sign * stress_test["mean"] > 0
          and up.get("n", 0) and down.get("n", 0)
          and sign * up["mean"] > 0 and sign * down["mean"] > 0)
    return ("EDGE" if sign > 0 else "HARMFUL") if ok else "no evidence"


def report(events, data):
    spy = data["SPY"]["Close"]
    ma = spy.rolling(200).mean()
    # NaN until 200 bars exist (Mar 2015): neither up nor down, not "down"
    uptrend = (spy > ma).where(ma.notna()).to_dict()
    events = events[events["date"] >= START].reset_index(drop=True)
    lines, results = [], []
    extra = 2 * (COST_STRESS - COST)
    for h in HORIZONS:
        trades = simulate(events, data, h, COST)
        lines += [f"\n## {h}-day hold\n",
                  "| cell | period | n | mean vs SPY % | vs random % | median % | hit % | t "
                  "| stop % | mean @20bps % | up-trend % | down-trend % | verdict |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        base = {}
        mask_by_cell = cells(trades)
        for name, mask in mask_by_cell.items():
            tr = dedupe(trades[mask], h)
            # purge: a tune trade still open on the split date leaks test data
            tune = tr[tr["exit"] < SPLIT]
            test = tr[tr["entry"] >= SPLIT]
            trend = tune["date"].map(uptrend)
            up, down = tune[trend == 1.0], tune[trend == 0.0]
            s = {"tune": stats(tune), "test": stats(test),
                 "tune20": stats(tune, extra), "test20": stats(test, extra),
                 "up": stats(up), "down": stats(down)}
            v = verdict(s["tune"], s["test"], s["tune20"], s["test20"], s["up"], s["down"])
            if name == "random member-day":
                base = {k: s[k].get("mean", 0.0) for k in ("tune", "test")}
            s["vs_random"] = {k: s[k].get("mean", 0.0) - base[k] for k in ("tune", "test")}
            results.append({"h": h, "cell": name, "verdict": v, **s})
            for period, key, key20 in (("2015-21", "tune", "tune20"), ("2022-26", "test", "test20")):
                a = s[key]
                if not a["n"]:
                    lines.append(f"| {name} | {period} | 0 |" + " |" * 10)
                    continue
                tail = (f"{s['up'].get('mean', 0):+.2f} | {s['down'].get('mean', 0):+.2f} | {v}"
                        if key == "tune" else " | | ")
                lines.append(f"| {name} | {period} | {a['n']} | {a['mean']:+.2f} | "
                             f"{s['vs_random'][key]:+.2f} | "
                             f"{a['median']:+.2f} | {a['hit']:.0f} | {a['t']:.1f} | "
                             f"{a['stop']:.0f} | {s[key20]['mean']:+.2f} | {tail} |")
    return lines, results


def main():
    if not BARS.exists():
        sys.exit("no data/bars.pkl — run fetch_bars.py first")
    data = pd.read_pickle(BARS)
    rows = load_members(MEMBERS)
    fresh = "--fresh" in sys.argv or not EVENTS.exists() or any(
        p.stat().st_mtime > EVENTS.stat().st_mtime
        for p in (BARS, pathlib.Path(screener.__file__)))
    if fresh:
        events = find_events(data, rows)
        events.to_pickle(EVENTS)
    else:
        events = pd.read_pickle(EVENTS)
    _, missing = member_days(data, rows)
    lines, results = report(events, data)

    first, last = events["date"].min().date(), events["date"].max().date()
    head = [
        "# Backtest results — price-only screens",
        "",
        f"Generated {datetime.date.today()} by `backtest.py`. Signals {first} to {last}, "
        f"S&P 500 point-in-time members only. Entry next open, gap-aware stop at "
        f"`stop_ref`, {COST * 1e4:.0f} bps per side, returns minus SPY over the same days. "
        f"Tune {START[:4]}-2021, test 2022 on (test run once). t is over non-overlapping "
        f"h-day blocks. Verdict bar: |t| > {T_BAR:.0f} in tune, same sign in test, "
        f"survives {COST_STRESS * 1e4:.0f} bps, holds in up- and down-trends (SPY vs its 200-day).",
        "",
        "Not in here: sentiment, analyst targets, earnings, the Claude judge. The families "
        "count has no earnings family, so `qualified` is a little stricter than live.",
        "",
        "**Missing data** — member-days with no Yahoo bars (delisted or renamed names). "
        "Results lean optimistic where this is high, oversold most of all:",
        "",
        "| year | missing % |", "|---|---|",
        *[f"| {y} | {m / n * 100:.1f} |" for y, (m, n) in sorted(missing.items())],
    ]
    RESULTS.write_text("\n".join(head + lines) + "\n")
    with open(TRIALS, "a") as f:
        f.write(json.dumps({
            "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "config": {"window": WINDOW, "cost": COST, "cost_stress": COST_STRESS,
                       "split": SPLIT, "min_score": MIN_SCORE, "min_families": MIN_FAMILIES,
                       "t_bar": T_BAR},
            "results": [{"h": r["h"], "cell": r["cell"], "verdict": r["verdict"],
                         "tune": r["tune"], "test": r["test"], "vs_random": r["vs_random"]}
                        for r in results],
        }, default=float) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {RESULTS.name}, appended {TRIALS.name}")


if __name__ == "__main__":
    main()
