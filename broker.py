"""Mirror every alert into an Alpaca PAPER account, so picks get real fills.

Why: the pick log records the price at the moment of the alert, which quietly
assumes a perfect fill. A paper account executes against the real book, so the
scorecard grades what a trade would actually have cost — slippage, gaps and all.

Safety: paper only. `ALPACA_BASE` defaults to the paper host, and `buy()` refuses
to run against a live host unless `ALPACA_ALLOW_LIVE=yes` is set. Nothing here
can raise: a broker failure must never suppress a Telegram alert that already
went out.
"""
import logging
import os
import re

import requests

log = logging.getLogger("stock-agent")

PAPER_BASE = "https://paper-api.alpaca.markets"
SLICE_PCT = 10.0          # share of equity committed to one pick
START_EQUITY = 100_000.0  # Alpaca's default paper stake; override with ALPACA_START_EQUITY

_STOP_RE = re.compile(r"Invalid below:\s*\$?\s*([\d,]+(?:\.\d+)?)")


def _keys():
    key = os.environ.get("ALPACA_KEY", "").strip()
    secret = os.environ.get("ALPACA_SECRET", "").strip()
    return (key, secret) if key and secret else (None, None)


def _api(method, path, body=None):
    """One REST call. Raises on anything that isn't a 2xx — callers catch."""
    key, secret = _keys()
    base = os.environ.get("ALPACA_BASE", PAPER_BASE).rstrip("/")
    r = requests.request(
        method, base + path,
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
        json=body, timeout=30)
    r.raise_for_status()
    # A cancel answers 204 with an empty body — .json() would raise on success.
    return r.json() if r.content else None


def _live_host_blocked():
    base = os.environ.get("ALPACA_BASE", PAPER_BASE)
    if "paper-api" in base or os.environ.get("ALPACA_ALLOW_LIVE") == "yes":
        return False
    log.error("broker: ALPACA_BASE is not the paper host and ALPACA_ALLOW_LIVE "
              "is unset — refusing to send orders to %s", base)
    return True


def stop_from_line(line):
    """Pull the invalidation level out of an alert line. None if it has none.

    Every judged line is required to end `Invalid below: $X` (analyzer enforces
    it), so this is normally a hit — but a schema change must degrade to an
    unprotected order, never to a skipped trade.
    """
    m = _STOP_RE.search(line or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def qty(equity, cash, price, slice_pct=SLICE_PCT):
    """Whole shares to buy: a fixed slice of equity, never more than free cash.

    Both caps matter. The slice keeps one pick from owning the account; the cash
    cap is what stops the fifth alert of a busy day from being rejected outright.
    """
    try:
        price = float(price or 0)
    except (TypeError, ValueError):
        return 0
    if price <= 0:
        return 0
    budget = min(float(equity) * slice_pct / 100.0, float(cash))
    return max(int(budget // price), 0)


def buy(picks, candidates, api=None, slice_pct=SLICE_PCT):
    """Place one paper market order per pick. Returns ["NVDA x50", ...].

    Never raises. Skips a ticker already held — a re-alert (RESEND_JUMP) is a
    stronger signal on the same idea, not a reason to double the position.
    """
    if api is None:
        if _keys() == (None, None):
            log.info("broker: no Alpaca keys, skipping paper orders")
            return []
        if _live_host_blocked():
            return []
        api = _api

    placed = []
    try:
        account = api("GET", "/v2/account")
        equity = float(account["equity"])
        cash = float(account["cash"])
        held = {p["symbol"] for p in api("GET", "/v2/positions")}
        # An after-close order sits unfilled until the open, so it is not a
        # position yet; without this a second run that evening doubles it.
        held |= {o["symbol"] for o in api("GET", "/v2/orders?status=open")}
    except Exception:
        log.exception("broker: could not read the paper account, no orders sent")
        return []

    prices = {s["ticker"]: s.get("facts", {}).get("price") for s in candidates}
    for p in picks:
        ticker = p["ticker"]
        if ticker in held:
            log.info("broker: already holding or ordered %s, no new order", ticker)
            continue
        shares = qty(equity, cash, prices.get(ticker), slice_pct)
        if shares < 1:
            log.info("broker: %s priced out of the remaining cash, skipped", ticker)
            continue
        order = {"symbol": ticker, "qty": str(shares), "side": "buy",
                 "type": "market", "time_in_force": "day"}
        stop = stop_from_line(p.get("line"))
        if stop:
            # OTO: the stop only arms once the entry fills, so a rejected buy
            # cannot leave a naked sell order behind.
            order["time_in_force"] = "gtc"
            order["order_class"] = "oto"
            order["stop_loss"] = {"stop_price": str(round(stop, 2))}
        try:
            api("POST", "/v2/orders", order)
        except Exception:
            log.exception("broker: order rejected for %s, continuing", ticker)
            continue
        cash -= shares * float(prices[ticker])
        placed.append(f"{ticker} x{shares}")
        log.info("broker: paper buy %s x%d, stop %s", ticker, shares, stop)
    return placed


def portfolio_line(api=None, start_equity=None):
    """One line for the daily digest. "" if the account can't be read."""
    if api is None:
        if _keys() == (None, None):
            return ""
        api = _api
    if start_equity is None:
        try:
            start_equity = float(os.environ.get("ALPACA_START_EQUITY", START_EQUITY))
        except ValueError:
            start_equity = START_EQUITY
    try:
        account = api("GET", "/v2/account")
        equity = float(account["equity"])
        open_n = len(api("GET", "/v2/positions"))
    except Exception:
        log.exception("broker: portfolio read failed, digest continues without it")
        return ""
    pct = (equity / start_equity - 1) * 100 if start_equity else 0.0
    return f"Paper account: ${equity:,.0f} ({pct:+.1f}%) · {open_n} open"
