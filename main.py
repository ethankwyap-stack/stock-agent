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


def closing_note(now):
    """The once-a-day note for a run that cannot scan. None means stay quiet.

    A weekday after the close is NOT "market closed today" — the market traded and
    we scanned it. GitHub's cron is best-effort (observed 4-7 of the 18 requested
    runs a day), so the 3pm digest window gets missed outright and this branch is
    what the user actually reads on those days.
    """
    if now.weekday() >= 5:
        return "Market closed today — no scan. Back at it next trading day."
    if now.hour >= 16:
        # ponytail: no top-signals list here, the scan was skipped. Accurate beats
        # detailed; scan post-close too if the digest content turns out to matter.
        return "No pick cleared the bar today — nothing worth acting on."
    return None  # pre-open weekday run: the day isn't over, stay quiet


def main():
    now = datetime.now(ZoneInfo("America/New_York"))
    import screener, sentiment, earnings, facts, analyzer, notify, tracker

    state = load_state()
    today = now.date().isoformat()

    if not market_open(now) and "--force" not in sys.argv:
        # one note a day so "at least one message a day" still holds
        note = closing_note(now)
        if note and state["last_alert"] != today:
            notify.send(note)
            state["last_alert"] = today
            STATE.write_text(json.dumps(state))
            log.info("Sent end-of-day note.")
        else:
            log.info("Market closed, skipping (use --force to override).")
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
    # the regression: a weekday after the close must never claim the market didn't trade
    assert "cleared the bar" in closing_note(wed_close)
    assert "Market closed" not in closing_note(wed_close)
    assert "Market closed" in closing_note(sat)
    assert closing_note(wed_pre) is None  # day isn't over yet, stay quiet
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
