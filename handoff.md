# HANDOFF — stock-agent

Written 2026-07-24 ~17:50 UTC. Project: `/Users/ethanyap/stock-agent`.

## TL;DR

The 7-task pipeline refinement (commits through `3c055e3`) was already done and
pushed. This session did the follow-up: rewrote `judge_smoke.py` into a test that
can actually fail, and **it caught a real bug in the live alert path on its first
run**. Both are fixed, pushed, and verified green on GitHub.

`main` is at **`b6cfa80`**, in sync with the remote. All four offline self-checks
pass. Nothing is half-done.

## What this session did

| Commit | What |
|---|---|
| `39fed24` | `judge_smoke.py` rewritten to be capable of failing. Two candidates in one call instead of one; prints the raw reply and `stop_reason` unconditionally; exits non-zero on a bad outcome. `analyzer.judge()` stashes `LAST_REPLY` / `LAST_STOP_REASON` on module globals — no caller changed. |
| `b6cfa80` | `parse_picks` now recovers a reply whose closing brackets are missing. New `_close_open_brackets()` helper. Self-checks updated + 3 new cases. |

### The bug the test found (this is the important part)

Smoke run **`30113702531`** failed. The log showed Claude had judged both
candidates *correctly* and written a well-formed pick ending in
`Invalid below: $143.5` — and the run still produced zero picks.

Root cause, confirmed by replaying the exact reply offline:

1. The reply ended `..."}]` — valid JSON **one `}` short**. `stop_reason` was
   `end_turn`, so this is **not** a truncation and raising `max_tokens` does not
   help. The model simply ended one character early.
2. The greedy `re.search(r"\{.*\}", text, re.S)` then made it worse: it matches
   to the **last** `}` in the text, which was the inner pick object's brace, so
   the closing `]` got eaten too. The blob was doubly unbalanced.
3. `json.loads` failed → "unparseable response" → `[]` → no alert.

Appending a single `}` to the raw reply makes it parse into 1 valid pick.

This is almost certainly what really killed the Jul 20 alerts — the Jul 21 fix
addressed prose preambles, which was a real but different failure.

**The fix stays tolerant, never strict.** On a failed parse, `parse_picks` retries
against the text from the first `{` with unclosed brackets appended, quote-aware
so a brace inside a `line` value is not counted. **A reply with an unterminated
string is deliberately NOT repaired** — that one died mid-sentence, and sending
half an alert is worse than sending none.

### Self-check change worth knowing about

One pre-existing assertion changed meaning. `'{"picks": [{"ticker": "BBB",
"line": "x"'` was asserted to return `[]` as a "truncated" case, but all its
strings are closed and its content is complete, so it now **recovers to 1 pick** —
that is the correct behavior and the same shape as the real bug. Three cases were
added: the real Jul 24 reply shape, a genuine mid-sentence truncation that must
stay dropped, and `{"picks": 5}`, which used to escape the `try` block as an
uncaught `TypeError`.

## Verified state

Checked by running a command at ~17:50 UTC on 2026-07-24, not remembered.

| Thing | Value |
|---|---|
| Branch / local HEAD | `main` / `b6cfa80` |
| Remote `main` | in sync, pushed |
| Working tree | clean except the 2 deliberately-untracked plan `.md` files |
| Offline checks | all 4 pass at `b6cfa80` |
| Last smoke run | `30114251411`, **success** — 1 pick, JNJ accepted, AAPL rejected, `Invalid below: $143.50` present |
| Previous smoke run | `30113702531`, **failed as designed**, exposed the brace bug |
| Cost this session | 2 smoke runs ≈ 1 cent total, all Anthropic. Actions free. |

**Honest limit:** the green run's reply happened to be well-formed, so the
`_close_open_brackets` recovery path was **not** exercised on the runner. It is
proven by the offline replay of the real broken reply and by the self-check that
now pins that exact shape. Nothing else is unverified.

## Still open — ASK ETHAN, DO NOT GUESS

1. **The `stop_ref` wart, still unanswered from last session.** `stop_ref` is the
   *prior* 20-day closing low, so for an oversold stock making a new low it lands
   **above** the current price. Seen live: TSLA `stop_ref` 319.69 against a 309.22
   close — the alert would say "Invalid below: $319.69" about a stock already
   below it. Fix would be roughly `min(stop_ref, price * 0.97)`. He has been asked
   twice and has not answered.
2. **The orphaned Actions caches** from adding `picks_log.jsonl` to `path:`.
   Self-healing and almost certainly needs nothing; he was told and did not reply.

## Gotchas

1. **Claude ends one `}` short sometimes** — see above. `stop_reason: end_turn`,
   not truncation. Handled now; don't "solve" it by raising `max_tokens`.
2. **`parse_picks` must stay tolerant.** Never a strict `json.loads`. A bad reply
   means no picks, never a dead run.
3. **`judge_smoke.py` now exits non-zero**, so the workflow step fails loudly on a
   bad judgment. That is intended — a test that always prints "ok" is not a test.
4. **Changing `path:` in `actions/cache` orphans every existing cache** (the
   action hashes `path` into a version and only restores matching ones). Don't
   casually change it again.
5. **Local venv is Python 3.9.6, Actions is 3.12.** No `X | Y` unions, no `match`.
6. **Never run `.venv/bin/python main.py --force`** — full real scan, really sends
   a Telegram alert.
7. **`max_tokens` on the judge call must stay ≥ 4000** (Sonnet 5 thinks by
   default).
8. **Never sort inside `sentiment.scan` or `earnings.check`** — input is
   pre-ranked by `main.py`.
9. **The cron is a request, not a schedule** — 4–7 runs a day, not 18.
10. **The smoke test costs ~half a cent.** Always name the figure before running
    it; cost is his #1 anxiety.
11. **The sheet webhook is write-only** (`doPost`, no `doGet`). Don't
    re-investigate.
12. **No scorecard for at least a week** — `picks_log.jsonl` starts empty.
13. **The agent CAN push and CAN trigger workflows on this repo.** `git push` and
    `gh workflow run run.yml -f smoke=true` both succeeded again this session.

## Don't redo

- The 7 pipeline tasks, the smoke-test rewrite, or the parser fix.
- Running the four offline checks "to verify" — they passed at `b6cfa80`. Only
  re-run after changing code.
- Investigating whether the sheet webhook supports reads. **It does not.**
- Adding `pct_of_52wk_range` to `facts.py`. **Already there, line 28.**

## Suggested next steps

Nothing is blocking. In rough priority order:

1. Get an answer on the `stop_ref` wart and fix it — it is the only known defect
   that would put a wrong number in a real alert.
2. Let real alerts accumulate in `picks_log.jsonl` for a week, then check that the
   `outcomes.py` scorecard actually appears in a post-close digest. It has been
   verified against live prices but never seen end-to-end in a digest.

## How to work with Ethan

College student, learning developer — teach while doing. Typos are common; infer
intent rather than asking.

- **Terminal steps: numbered, ONE command per step**, say what he should see, then
  wait for his confirmation.
- **Lead with the outcome.** He does not watch the process; everything important
  must land in the final message.
- **Cost questions get certainty, not hedging.** "Probably free" reads as a bug.
- **Verify before saying done.** Say exactly what was not verified. Never "should
  work."
- **Short confirmations** ("push", "run it", "go") mean: do exactly the pending
  step.
- If he asks a **question**, answer it — do not start changing code.
