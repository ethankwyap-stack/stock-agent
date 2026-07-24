"""Score ticker sentiment from Yahoo Finance comments + news headlines (free, no key)."""
import time
import requests
import yfinance as yf

# ponytail: tiny keyword lexicon; swap for vaderSentiment if precision matters
BULLISH = {"buy", "call", "calls", "moon", "bull", "bullish", "long", "rocket",
           "breakout", "squeeze", "undervalued", "rip", "pump", "gains", "rally",
           "beat", "beats", "upgrade", "upgraded", "surge", "soar", "soars", "pop"}
BEARISH = {"sell", "put", "puts", "short", "bear", "bearish", "crash", "dump",
           "overvalued", "tank", "tanks", "bagholder", "loss", "losses", "miss",
           "misses", "downgrade", "downgraded", "plunge", "plunges", "sink", "drop"}

COMMENTS_URL = "https://api-2-0.spot.im/v1.0.0/conversation/read"
SPOT_ID = "sp_Rba9aFpG"  # Yahoo Finance's OpenWeb spot id
MAX_TICKERS = 20  # each ticker costs ~2 HTTP calls; keep the run fast


def _tone(text):
    words = {w.lower().strip(".,!?'\"") for w in text.split()}
    return len(words & BULLISH) - len(words & BEARISH)


def _comments(board_id, count=25):
    r = requests.post(
        COMMENTS_URL, timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (stock-alert-agent)",
                 "x-spot-id": SPOT_ID, "x-post-id": board_id},
        json={"conversation_id": f"{SPOT_ID}_{board_id}", "count": count,
              "offset": 0, "sort_by": "newest"})
    r.raise_for_status()
    texts = []
    for msg in r.json().get("conversation", {}).get("comments", []):
        texts.append(" ".join(b.get("text", "") for b in msg.get("content", [])))
    return texts


def scan(tickers):
    """Return {ticker: {"sentiment": net_tone}}.

    A comment count used to be returned alongside the tone, but Yahoo's OpenWeb
    endpoint has 403'd since Jul 2026, so it was always 0 — the scoring term it
    fed is gone. Comments are still collected in case the endpoint returns; they
    feed the tone like any other text.

    `tickers` is caller-ordered, strongest first, and walked in that order.
    Never sort here: sorting made coverage alphabetical, so the sentiment score
    only ever reached A-names.
    """
    scores = {}
    for t in list(tickers)[:MAX_TICKERS]:
        try:
            tk = yf.Ticker(t)
            texts = []
            board = tk.info.get("messageBoardId")
            if board:
                try:
                    texts += _comments(board)
                except Exception:
                    pass  # OpenWeb 403s since Jul 2026; news headlines below still score
            for item in tk.news or []:
                content = item.get("content", item)
                texts.append(content.get("title") or "")
            if texts:
                scores[t] = {"sentiment": sum(_tone(x) for x in texts)}
        except Exception:
            continue  # one bad ticker shouldn't kill the run
        time.sleep(0.3)  # be polite to the free APIs
    return scores
