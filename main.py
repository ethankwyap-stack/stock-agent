"""Orchestrator: screen -> sentiment -> earnings -> analyze -> notify."""
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("stock-agent")

MIN_SCORE = 3.0  # ponytail: one weak signal alone never pages you; tune if too quiet/noisy


def market_open():
    now = datetime.now(ZoneInfo("America/New_York"))
    return now.weekday() < 5 and 9 <= now.hour < 16


def main():
    if not market_open() and "--force" not in sys.argv:
        log.info("Market closed, skipping (use --force to override).")
        return

    import screener, sentiment, earnings, analyzer, notify

    signals = screener.scan()
    log.info("screener: %d tickers with signals", len(signals))
    if not signals:
        return

    universe = {s["ticker"] for s in signals}

    try:
        sent = sentiment.scan(universe)
        log.info("sentiment: %d tickers with Yahoo comment/news data", len(sent))
    except Exception:
        log.exception("sentiment scan failed, continuing without it")
        sent = {}

    try:
        earn = earnings.check(sorted(universe))
        log.info("earnings: %d tickers reporting within 7 days", len(earn))
    except Exception:
        log.exception("earnings check failed, continuing without it")
        earn = {}

    ranked = analyzer.rank(signals, sent, earn)
    actionable = [s for s in ranked if s["score"] >= MIN_SCORE][:5]
    if not actionable:
        log.info("No actionable signals (best score %.1f) — staying quiet.",
                 ranked[0]["score"])
        return

    summary = analyzer.analyze(actionable)
    notify.send(summary)
    log.info("Sent %d ideas to Telegram.", len(actionable))


if __name__ == "__main__":
    main()
