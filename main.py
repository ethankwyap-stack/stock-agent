"""Orchestrator: screen -> sentiment -> earnings -> rank -> Claude judges -> notify."""
import json
import logging
import pathlib
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("stock-agent")

MIN_SCORE = 3.0      # ponytail: one weak signal alone never pages you; tune if too quiet/noisy
MIN_FAMILIES = 2     # signal families (volume/breakout/RSI/earnings) required before Claude even sees it
RESEND_JUMP = 2.0    # re-alert a ticker the same day only if its score rose by this much
MIN_UPSIDE_PCT = 10.0  # analyst mean target must sit this far above price, else dropped pre-Claude
STATE = pathlib.Path(__file__).parent / "state.json"


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sent": {}, "last_alert": None}


def market_open(now):
    return now.weekday() < 5 and 9 <= now.hour < 16


def main():
    now = datetime.now(ZoneInfo("America/New_York"))
    import screener, sentiment, earnings, facts, analyzer, notify

    state = load_state()
    today = now.date().isoformat()

    if not market_open(now) and "--force" not in sys.argv:
        # weekend cron fires once a day so "at least one message a day" still holds;
        # hour check keeps a pre-open weekday run (8am EST) from firing it early
        if state["last_alert"] != today and (now.weekday() >= 5 or now.hour >= 16):
            notify.send("Market closed today — no scan. Back at it next trading day.")
            state["last_alert"] = today
            STATE.write_text(json.dumps(state))
            log.info("Sent market-closed daily note.")
        else:
            log.info("Market closed, skipping (use --force to override).")
        return

    # ponytail: only today's sends matter for the resend rule — drop older entries
    state["sent"] = {t: v for t, v in state["sent"].items() if v["date"] == today}

    ranked = []
    signals = screener.scan()
    log.info("screener: %d tickers with signals", len(signals))

    if signals:
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
        qualified = [s for s in ranked
                     if s["score"] >= MIN_SCORE
                     and analyzer.signal_types(s) >= MIN_FAMILIES]
        candidates = [s for s in qualified
                      if s["ticker"] not in state["sent"]
                      or s["score"] >= state["sent"][s["ticker"]]["score"] + RESEND_JUMP][:5]
        log.info("%d qualified (score+confluence), %d new/stronger since last alert",
                 len(qualified), len(candidates))

        if candidates:
            packs = facts.fetch([s["ticker"] for s in candidates])
            for s in candidates:
                s["facts"] = packs.get(s["ticker"], {})
            # upside gate: no measurable analyst upside -> not worth risk-weighing at all
            finalists = [s for s in candidates
                         if s["facts"].get("target_upside_pct", -999) >= MIN_UPSIDE_PCT]
            if len(finalists) < len(candidates):
                log.info("upside gate: dropped %s (target upside < %.0f%% or no target)",
                         [s["ticker"] for s in candidates if s not in finalists],
                         MIN_UPSIDE_PCT)
            candidates = finalists

        if candidates:
            picks = analyzer.judge(candidates)
            if picks:
                notify.send("\n\n".join(p["line"] for p in picks))
                scores = {s["ticker"]: s["score"] for s in candidates}
                for p in picks:
                    state["sent"][p["ticker"]] = {"date": today, "score": scores[p["ticker"]]}
                state["last_alert"] = today
                log.info("Claude judged %d of %d actionable — sent to Telegram.",
                         len(picks), len(candidates))
            else:
                log.info("Claude judged none of %d candidates actionable — staying quiet.",
                         len(candidates))

    # daily digest: last scan hour (3pm ET), nothing sent today -> report the day anyway
    if now.hour == 15 and state["last_alert"] != today:
        if ranked:
            def _names(s):
                return ", ".join(n for n, on in [
                    ("volume", s.get("unusual_volume")), ("breakout", s.get("breakout_20d")),
                    ("RSI", s.get("rsi_oversold") or s.get("rsi_overbought")),
                    ("earnings", "earnings" in s)] if on)
            body = "\n".join(f"{s['ticker']} — score {s['score']} ({_names(s)})"
                             for s in ranked[:3])
            notify.send("Daily digest — nothing crossed the alert bar today. "
                        "Top signals seen:\n" + body)
        else:
            notify.send("Daily digest — quiet day, no tickers tripped any screens.")
        state["last_alert"] = today
        log.info("Sent daily digest.")

    STATE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
