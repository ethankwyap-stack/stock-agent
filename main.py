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
# Sentiment and earnings are the slow lookups (earnings alone was 6min of a 9min
# run), so they cover the strongest technical names only — ranked by score, never
# alphabetically. An alphabetical cut handed the sentiment bonus, the single
# biggest scoring term at 4 points, to A-tickers and never to WMT or XOM.
# ponytail: 30 is a safety margin, not a tuned number — only the top 5 ever reach
# Claude, so a name below rank 30 can't win even with a full earnings bump.
SENTIMENT_TICKERS = 20
EARNINGS_TICKERS = 30
STATE = pathlib.Path(__file__).parent / "state.json"


def load_state():
    try:
        state = json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    return {"sent": state.get("sent") or {}, "last_alert": state.get("last_alert")}


def market_open(now):
    return now.weekday() < 5 and 9 <= now.hour < 16


def scan_window(now):
    """What this run is allowed to send: "alert", "digest", or None.

    A weekday after the close still scans — the day's data is final by then, so
    it produces the real digest instead of guessing. It must not alert: a BUY
    that lands at 6pm is a different message from one at 11am.

    This is what makes the day's summary independent of GitHub's cron, which is
    best-effort (observed 4-7 of the 18 requested runs a day) and regularly skips
    the 3pm hour entirely.
    """
    if now.weekday() >= 5:
        return None
    if market_open(now):
        return "alert"
    if now.hour >= 16:
        return "digest"
    return None  # pre-open weekday: the day hasn't happened yet, stay quiet


def closing_note(now):
    """The once-a-day note for a day we never scan at all — weekends only."""
    if now.weekday() >= 5:
        return "Market closed today — no scan. Back at it next trading day."
    return None


def main():
    now = datetime.now(ZoneInfo("America/New_York"))
    import screener, sentiment, earnings, facts, analyzer, notify, tracker

    state = load_state()
    today = now.date().isoformat()

    mode = "alert" if "--force" in sys.argv else scan_window(now)

    if mode is None:
        # weekend or pre-open: one note a day so "a message every day" still holds
        note = closing_note(now)
        if note and state["last_alert"] != today:
            notify.send(note)
            state["last_alert"] = today
            STATE.write_text(json.dumps(state))
            log.info("Sent market-closed note.")
        else:
            log.info("Outside scan hours, skipping (use --force to override).")
        return

    if mode == "digest" and state["last_alert"] == today:
        # something already went out today; a post-close scan has nothing to add,
        # and skipping it here is what keeps this to one extra scan per day
        log.info("Already messaged today, skipping post-close digest scan.")
        return

    # ponytail: only today's sends matter for the resend rule — drop older entries
    state["sent"] = {t: v for t, v in state["sent"].items() if v["date"] == today}

    ranked = []
    signals = screener.scan()
    log.info("screener: %d tickers with signals", len(signals))

    if signals:
        # Technicals-only pass first: it decides WHICH tickers earn the slow
        # sentiment/earnings lookups. rank() rebuilds score from scratch every
        # call, so ranking twice is safe.
        pre = analyzer.rank(signals, {}, {})
        focus = [s["ticker"] for s in pre[:SENTIMENT_TICKERS]]
        try:
            sent = sentiment.scan(focus)
            log.info("sentiment: %d of top %d tickers with Yahoo comment/news data",
                     len(sent), len(focus))
        except Exception:
            log.exception("sentiment scan failed, continuing without it")
            sent = {}
        try:
            earn = earnings.check([s["ticker"] for s in pre[:EARNINGS_TICKERS]])
            log.info("earnings: %d of top %d tickers reporting within 7 days",
                     len(earn), min(EARNINGS_TICKERS, len(pre)))
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

        # facts + judge only feed alerts, so a digest-mode run skips both
        if candidates and mode == "alert":
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

        if candidates and mode == "alert":
            picks = analyzer.judge(candidates)
            if picks:
                notify.send("\n\n".join(p["line"] for p in picks))
                tracker.log_picks(picks, candidates)
                scores = {s["ticker"]: s["score"] for s in candidates}
                for p in picks:
                    state["sent"][p["ticker"]] = {"date": today, "score": scores[p["ticker"]]}
                state["last_alert"] = today
                log.info("Claude judged %d of %d actionable — sent to Telegram.",
                         len(picks), len(candidates))
            else:
                log.info("Claude judged none of %d candidates actionable — staying quiet.",
                         len(candidates))

    # digest: the 3pm run if one lands, otherwise the first run after the close.
    # Two triggers, not one, because the cron can't be relied on to hit either.
    if state["last_alert"] != today and (mode == "digest" or now.hour == 15):
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


def _selfcheck():
    """Covers the two branches a flaky cron actually exercises, and can't be
    checked by waiting for 4pm. Run: python main.py --selfcheck
    """
    global STATE
    import tempfile
    ny = ZoneInfo("America/New_York")
    wed_pre = datetime(2026, 7, 22, 8, 30, tzinfo=ny)
    wed_open = datetime(2026, 7, 22, 11, 0, tzinfo=ny)
    wed_close = datetime(2026, 7, 22, 16, 5, tzinfo=ny)
    sat = datetime(2026, 7, 18, 12, 0, tzinfo=ny)

    assert market_open(wed_open)
    assert not market_open(wed_pre) and not market_open(wed_close) and not market_open(sat)
    assert scan_window(wed_open) == "alert"
    # the regression: a weekday after the close scans and reports the real day.
    # It must never claim the market didn't trade, and must never alert.
    assert scan_window(wed_close) == "digest"
    assert closing_note(wed_close) is None
    # weekend and pre-open never scan; only the weekend gets a note
    assert scan_window(sat) is None and scan_window(wed_pre) is None
    assert "Market closed" in closing_note(sat)
    assert closing_note(wed_pre) is None
    print("time/message self-check ok")

    # a state file missing "sent" must not KeyError the whole run
    orig = STATE
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"last_alert": "2026-07-22"}')
            STATE = pathlib.Path(f.name)
        s = load_state()
        assert s["sent"] == {} and s["last_alert"] == "2026-07-22", s
    finally:
        STATE = orig
    print("state self-check ok")


if __name__ == "__main__":
    _selfcheck() if "--selfcheck" in sys.argv else main()
