"""Scan S&P 500 for unusual volume, 20-day breakouts, and RSI extremes."""
import io

import pandas as pd
import requests
import yfinance as yf

# ponytail: fallback list if Wikipedia scrape fails — top liquid names, refresh rarely
FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX",
    "JPM", "V", "MA", "COST", "WMT", "XOM", "UNH", "LLY", "HD", "PG",
    "ORCL", "CRM", "BAC", "KO", "PEP", "MRK", "ABBV", "CVX", "ADBE", "QCOM",
    "INTC", "PLTR", "COIN", "SOFI", "F", "T", "PFE", "DIS", "BA", "UBER",
]


def sp500_tickers():
    try:
        # Wikipedia 403s pandas' default urllib UA — fetch with a real one
        html = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (stock-alert-agent)"},
            timeout=30).text
        table = pd.read_html(io.StringIO(html))[0]
        return [t.replace(".", "-") for t in table["Symbol"]]
    except Exception:
        return FALLBACK


def invalidation_level(price, prior_low):
    """The level that says the setup failed — the prior 20-day closing low, but
    never at or above the current price.

    An oversold name is often making a NEW 20-day low, which is the signal firing
    as designed; its *prior* low then sits above where the stock trades now. Live
    on 2026-07-24, TSLA would have alerted "Invalid below: $319.69" against a
    309.22 close — a level already breached before the message arrived. The 3%
    floor keeps it a real exit instead of an instant stop-out.
    """
    return round(min(prior_low, price * 0.97), 2)


def rsi(closes, period=14):
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)


def scan(tickers=None):
    tickers = tickers or sp500_tickers()
    data = yf.download(tickers, period="3mo", group_by="ticker",
                       threads=True, progress=False, auto_adjust=True)
    signals = []
    for t in tickers:
        try:
            df = data[t].dropna()
        except KeyError:
            continue
        if len(df) < 21:
            continue
        close, vol = df["Close"], df["Volume"]
        # ponytail: intraday runs see partial day volume, so 2x is conservative not inflated
        vol_ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
        breakout = bool(close.iloc[-1] >= df["High"].iloc[-21:-1].max())
        r = float(rsi(close).iloc[-1])

        sig = {}
        if vol_ratio >= 2:
            sig["unusual_volume"] = True
        if breakout:
            sig["breakout_20d"] = True
        if r <= 30:
            sig["rsi_oversold"] = True
        elif r >= 70:
            sig["rsi_overbought"] = True
        if sig:
            price = round(float(close.iloc[-1]), 2)
            sig.update(ticker=t, price=price,
                       rsi=round(r, 1), volume_ratio=round(vol_ratio, 1),
                       stop_ref=invalidation_level(
                           price, float(close.iloc[-21:-1].min())),
                       volatility_30d_annualized_pct=round(
                           float(close.pct_change().tail(30).std()) * 252 ** 0.5 * 100, 1))
            signals.append(sig)
    return signals


if __name__ == "__main__":
    # self-check: a normal setup keeps its prior 20-day low as the exit level
    assert invalidation_level(100.0, 94.0) == 94.0
    # but a stock making a NEW 20-day low never gets a level above where it trades
    # (the live TSLA case: prior low 319.69, close 309.22)
    assert invalidation_level(309.22, 319.69) == 299.94
    # equal is still below-only: a level at the current price is an instant stop-out
    assert invalidation_level(50.0, 50.0) == 48.5
    print("invalidation self-check ok")

    # self-check: RSI of a monotonically rising series must be 100
    up = pd.Series(range(1, 31), dtype=float)
    assert round(rsi(up).iloc[-1]) == 100
    # and a falling series must be 0
    down = pd.Series(range(30, 0, -1), dtype=float)
    assert round(rsi(down).iloc[-1]) == 0
    print("rsi self-check ok")
