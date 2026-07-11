"""Flag tickers with earnings in the next 7 days + their historical post-earnings moves."""
import datetime as dt
import yfinance as yf


def check(tickers):
    """Return {ticker: {earnings_date, avg_post_earnings_move_pct}}."""
    today = dt.date.today()
    out = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            ed = tk.get_earnings_dates(limit=8)
            if ed is None or ed.empty:
                continue
            dates = sorted({d.date() for d in ed.index}, reverse=True)
            upcoming = [d for d in dates if today <= d <= today + dt.timedelta(days=7)]
            if not upcoming:
                continue
            past = [d for d in dates if d < today][:4]
            moves = []
            if past:
                close = tk.history(period="2y")["Close"]
                for d in past:
                    before = close[close.index.date <= d]
                    after = close[close.index.date > d]
                    if len(before) and len(after):
                        moves.append(abs(after.iloc[0] / before.iloc[-1] - 1) * 100)
            out[t] = {
                "earnings_date": min(upcoming).isoformat(),
                "avg_post_earnings_move_pct": round(sum(moves) / len(moves), 1) if moves else None,
            }
        except Exception:
            continue  # one bad ticker shouldn't kill the run
    return out
