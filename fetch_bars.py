"""One-time, local-only download of the backtest's price history.

Run on the Mac, never on Actions: Yahoo 429-blocks bulk pulls, sometimes for
over a day, and a blocked runner IP would take the live screener down with it.
Resumable — rerun after a block and it fetches only what is still missing.

    .venv/bin/python fetch_bars.py
"""
import pathlib
import pickle
import time

import requests
import yfinance as yf

DATA = pathlib.Path(__file__).parent / "data"
MEMBERS = DATA / "members.csv"
BARS = DATA / "bars.pkl"
# fja05680/sp500 (MIT): every S&P 500 membership change since 1996, one row per
# date with the full member list. Point-in-time membership is the survivorship fix.
MEMBERS_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
               "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv")
START = "2014-06-01"  # warm-up bars before 2015 for the 20-day and 200-day windows
FIRST_TEST_DAY = "2015-01-01"
CHUNK, PAUSE = 100, 30


def yahoo(sym):
    return sym.replace(".", "-")  # BRK.B -> BRK-B


def tickers_since(members_csv, start=FIRST_TEST_DAY):
    """Every ticker that was a member on any day from `start` on, plus SPY."""
    import backtest
    rows = backtest.load_members(members_csv)
    out = {"SPY"} | backtest.members_on(rows, start)  # the list in force on day one
    for date, names in rows:
        if date >= start:
            out |= names
    return sorted(out)


def main():
    DATA.mkdir(exist_ok=True)
    if not MEMBERS.exists():
        MEMBERS.write_bytes(requests.get(MEMBERS_URL, timeout=60).content)
    bars = pickle.loads(BARS.read_bytes()) if BARS.exists() else {}
    # None entries are retried too: a rate limit that starts mid-chunk looks
    # exactly like a delisting, and a delisted name just comes back None again
    todo = [t for t in tickers_since(MEMBERS) if bars.get(t) is None]
    print(f"{len(bars)} cached, {len(todo)} to fetch")
    for k in range(0, len(todo), CHUNK):
        chunk = todo[k:k + CHUNK]
        data = yf.download([yahoo(t) for t in chunk], start=START, group_by="ticker",
                           threads=True, progress=False, auto_adjust=True)
        got = 0
        for t in chunk:
            try:
                df = data[yahoo(t)].dropna()
            except KeyError:
                df = None
            # an empty frame is recorded too: delisted names Yahoo no longer has
            # stay missing, and are counted per year by backtest.py
            bars[t] = df if df is not None and len(df) else None
            got += bars[t] is not None
        if got < len(chunk) and yf.download("SPY", period="5d", progress=False).empty:
            # SPY always exists, so SPY failing too means a 429 block, not
            # delistings — keep nothing from this chunk, rerun later
            for t in chunk:
                bars.pop(t, None)
            print("Yahoo is rate-limiting — rerun later, it resumes from here")
            break
        BARS.write_bytes(pickle.dumps(bars))
        print(f"{k + len(chunk)}/{len(todo)}: {got} of {len(chunk)} had data")
        time.sleep(PAUSE)


if __name__ == "__main__":
    main()
