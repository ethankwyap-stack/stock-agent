"""Append every sent pick to the tracking Google Sheet via its Apps Script webhook."""
import logging
import os

import requests
import yfinance as yf

import outcomes

log = logging.getLogger("stock-agent")


def log_picks(picks, candidates):
    """POST one row per pick. Never raises — tracking must not break alerting."""
    # Local grading history first: the sheet webhook is write-only, and this must
    # be recorded even when SHEET_WEBHOOK_URL isn't set at all.
    outcomes.record(picks, candidates)
    url = os.environ.get("SHEET_WEBHOOK_URL")
    if not url:
        return
    try:
        by_ticker = {s["ticker"]: s for s in candidates}
        try:
            spy = round(yf.Ticker("SPY").fast_info["last_price"], 2)
        except Exception:
            spy = ""
        today = outcomes.market_date().isoformat()
        rows = []
        for p in picks:
            s = by_ticker.get(p["ticker"], {})
            f = s.get("facts", {})
            rows.append({
                "date": today,
                "ticker": p["ticker"],
                "score": s.get("score", ""),
                "entry_price": f.get("price", ""),
                "spy_entry": spy,
                "analyst_target": f.get("analyst_mean_target", ""),
                "upside_pct": f.get("target_upside_pct", ""),
                "verdict": p["line"],
            })
        r = requests.post(url, json={"rows": rows}, timeout=30)
        r.raise_for_status()
        log.info("tracker: logged %d pick(s) to sheet", len(rows))
    except Exception:
        log.exception("tracker: sheet logging failed, alert already sent — continuing")
