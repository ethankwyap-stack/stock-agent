"""Per-ticker fact pack for the finalists: analyst target, 52-week position, valuation."""
import logging

import yfinance as yf

log = logging.getLogger("stock-agent")


def fetch(tickers):
    """Only called for the <=5 finalists — one yfinance info request each."""
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
        except Exception:
            log.warning("facts: info fetch failed for %s", t)
            continue
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        f = {}
        target = info.get("targetMeanPrice")
        if price and target:
            f["analyst_mean_target"] = target
            f["target_upside_pct"] = round((target / price - 1) * 100, 1)
        hi, lo = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
        if price and hi and lo and hi > lo:
            f["pct_of_52wk_range"] = round((price - lo) / (hi - lo) * 100)
        if info.get("trailingPE"):
            f["trailing_pe"] = round(info["trailingPE"], 1)
        if info.get("beta"):
            f["beta"] = round(info["beta"], 2)
        out[t] = f
    return out
