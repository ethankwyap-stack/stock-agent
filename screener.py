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
            sig.update(ticker=t, price=round(float(close.iloc[-1]), 2),
                       rsi=round(r, 1), volume_ratio=round(vol_ratio, 1))
            signals.append(sig)
    return signals


if __name__ == "__main__":
    # self-check: RSI of a monotonically rising series must be 100
    up = pd.Series(range(1, 31), dtype=float)
    assert round(rsi(up).iloc[-1]) == 100
    # and a falling series must be 0
    down = pd.Series(range(30, 0, -1), dtype=float)
    assert round(rsi(down).iloc[-1]) == 0
    print("rsi self-check ok")
