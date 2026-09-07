"""Paper-broker tests. Fully offline — the HTTP layer is injected, never called.

What earns a test here is the money math and the parsing: a wrong stop level or a
wrong share count is silent and permanent. The REST plumbing is not tested; a
wrong URL fails loudly on the first live run.
"""
import json

import pytest

import broker


# ---------------------------------------------------------------- stop parsing

def test_stop_from_line_reads_the_invalidation_level():
    line = ("NVDA $170 breakout, 14% upside\nRisks: rich multiple\n"
            "Verdict: buy\nInvalid below: $158.40")
    assert broker.stop_from_line(line) == 158.40


def test_stop_from_line_handles_commas_and_no_cents():
    assert broker.stop_from_line("x\nInvalid below: $1,204") == 1204.0


def test_stop_from_line_returns_none_when_absent():
    assert broker.stop_from_line("no level here") is None


# ---------------------------------------------------------------- sizing

def test_qty_takes_the_configured_slice_of_equity():
    # 10% of $100,000 = $10,000 / $200 = 50 shares
    assert broker.qty(equity=100_000, cash=100_000, price=200.0, slice_pct=10) == 50


def test_qty_is_capped_by_available_cash():
    # slice wants $10,000 but only $900 is free -> 4 shares, not 50
    assert broker.qty(equity=100_000, cash=900, price=200.0, slice_pct=10) == 4


def test_qty_is_zero_when_cash_cannot_buy_one_share():
    assert broker.qty(equity=100_000, cash=50, price=200.0, slice_pct=10) == 0


def test_qty_is_zero_on_a_missing_or_junk_price():
    assert broker.qty(equity=100_000, cash=100_000, price=0, slice_pct=10) == 0
    assert broker.qty(equity=100_000, cash=100_000, price=None, slice_pct=10) == 0


# ---------------------------------------------------------------- order shape

def _fake_api(state):
    """Stand-in for broker._api. Records every POST body it is handed."""
    def call(method, path, body=None):
        if method == "GET" and path == "/v2/account":
            return {"equity": "100000", "cash": "100000",
                    "last_equity": "99000"}
        if method == "GET" and path == "/v2/positions":
            return state["positions"]
        if method == "POST" and path == "/v2/orders":
            state["orders"].append(body)
            return {"id": "fake", "symbol": body["symbol"]}
        raise AssertionError(f"unexpected call {method} {path}")
    return call


def _picks(*lines):
    return [{"ticker": t, "line": l} for t, l in lines]


def test_buy_sends_a_market_order_with_a_stop_attached():
    state = {"positions": [], "orders": []}
    picks = _picks(("NVDA", "buy it\nInvalid below: $158.40"))
    cands = [{"ticker": "NVDA", "facts": {"price": 200.0}}]

    placed = broker.buy(picks, cands, api=_fake_api(state), slice_pct=10)

    assert placed == ["NVDA x50"], placed
    order = state["orders"][0]
    assert order["symbol"] == "NVDA"
    assert order["qty"] == "50"
    assert order["side"] == "buy"
    assert order["type"] == "market"
    assert order["order_class"] == "oto"
    assert order["stop_loss"]["stop_price"] == "158.4"


def test_buy_skips_a_ticker_already_held():
    state = {"positions": [{"symbol": "NVDA", "qty": "10"}], "orders": []}
    picks = _picks(("NVDA", "buy it\nInvalid below: $158.40"))
    cands = [{"ticker": "NVDA", "facts": {"price": 200.0}}]

    assert broker.buy(picks, cands, api=_fake_api(state), slice_pct=10) == []
    assert state["orders"] == []


def test_buy_sends_a_plain_order_when_the_line_has_no_stop():
    # analyzer enforces the level, but a schema change must not stop the trade
    state = {"positions": [], "orders": []}
    picks = _picks(("MSFT", "no level given"))
    cands = [{"ticker": "MSFT", "facts": {"price": 200.0}}]

    broker.buy(picks, cands, api=_fake_api(state), slice_pct=10)
    assert "order_class" not in state["orders"][0]


def test_buy_never_raises_when_the_api_dies():
    def boom(*a, **k):
        raise RuntimeError("alpaca is down")
    picks = _picks(("NVDA", "buy it\nInvalid below: $158.40"))
    cands = [{"ticker": "NVDA", "facts": {"price": 200.0}}]
    assert broker.buy(picks, cands, api=boom) == []


def test_buy_is_a_noop_without_keys(monkeypatch):
    monkeypatch.delenv("ALPACA_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET", raising=False)
    picks = _picks(("NVDA", "buy it\nInvalid below: $158.40"))
    assert broker.buy(picks, [{"ticker": "NVDA", "facts": {"price": 200.0}}]) == []


# ---------------------------------------------------------------- digest line

def test_portfolio_line_reports_equity_and_return_against_the_starting_stake():
    state = {"positions": [{"symbol": "NVDA", "qty": "50"}], "orders": []}
    line = broker.portfolio_line(api=_fake_api(state), start_equity=100_000)
    assert "$100,000" in line
    assert "1 open" in line


def test_portfolio_line_shows_the_gain_when_the_account_grew():
    def api(method, path, body=None):
        if path == "/v2/account":
            return {"equity": "110000", "cash": "5000", "last_equity": "109000"}
        return []
    line = broker.portfolio_line(api=api, start_equity=100_000)
    assert "+10.0%" in line


def test_portfolio_line_is_empty_when_the_api_dies():
    def boom(*a, **k):
        raise RuntimeError("down")
    assert broker.portfolio_line(api=boom) == ""


# ---------------------------------------------------------------- REST plumbing

def test_api_returns_none_on_an_empty_body(monkeypatch):
    """A cancel answers 204 with no body; .json() used to raise on success."""
    class R:
        content = b""
        def raise_for_status(self): pass
        def json(self): raise ValueError("no body")

    monkeypatch.setenv("ALPACA_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET", "s")
    monkeypatch.setattr(broker.requests, "request", lambda *a, **k: R())
    assert broker._api("DELETE", "/v2/orders/abc") is None
