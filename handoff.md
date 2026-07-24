# HANDOFF — stock-agent

Written 2026-07-24 ~18:25 UTC. Project: `/Users/ethanyap/stock-agent`.
Every fact below was re-checked by running a command at 18:19–18:25 UTC, not
remembered from earlier in the session.

## TL;DR

Three code changes were made, pushed, and verified this session. **There is no
known defect outstanding.** `main` is at **`d9fc082`**, in sync with the remote,
and all offline self-checks pass.

**Do not redo any of it.** In particular the two long-standing items from the
previous handoff — the unverifiable smoke test and the `stop_ref` wart — are both
**resolved and closed**.

**The seeding task below is DONE** (2026-07-24 20:25 UTC, `0898297`, pushed and
verified live). `main` is now at `0898297`. Do not redo it — see "Seeding: done"
at the bottom. **There is no pending task in this file.**

## What was accomplished

The session began with the previous handoff's open item: the smoke test could not
prove the Claude judge prompt worked, because it returned 0 picks and a 0 was
indistinguishable from a silent failure.

| Commit | What changed |
|---|---|
| `39fed24` | `judge_smoke.py` rewritten so it is **capable of failing**. Sends two candidates in one call instead of one; prints the raw reply and `stop_reason` unconditionally; exits non-zero on a bad outcome. `analyzer.judge()` now stashes `LAST_REPLY` / `LAST_STOP_REASON` on module globals — no caller changed. |
| `b6cfa80` | `parse_picks` recovers a reply whose closing brackets are missing. New `_close_open_brackets()` helper + 3 new self-check cases. |
| `b41ecb0` | Docs for the above. |
| `9ea9b01` | `stop_ref` can no longer land at or above the current price. New `screener.invalidation_level(price, prior_low)`. |
| `d9fc082` | Docs for the invalidation fix. |

### The bug the new test found — the important part

The rewritten smoke test **failed on its first run** (`30113702531`) and exposed a
real defect in the live alert path.

The log showed Claude had judged both candidates correctly and written a
well-formed pick ending in `Invalid below: $143.5` — and the run still produced
zero picks. Root cause, confirmed by replaying the exact reply offline:

1. The reply ended `..."}]` — valid JSON **one `}` short**, with
   `stop_reason: end_turn`. **This is not a truncation**; raising `max_tokens`
   would never have fixed it. The model simply ended one character early.
2. The greedy `re.search(r"\{.*\}", text, re.S)` then compounded it by matching to
   the **last** `}` in the text, which was the inner pick object's brace — so the
   closing `]` was eaten too, leaving a doubly unbalanced blob.
3. `json.loads` failed → "unparseable response" → `[]` → no alert.

Appending a single `}` to the raw reply makes it parse into 1 valid pick. This is
very likely what actually killed the Jul 20 alerts; the Jul 21 fix addressed prose
preambles, a real but different failure.

The fix keeps `parse_picks` **tolerant, never strict**: on a failed parse it
retries against the text from the first `{` with unclosed brackets appended,
quote-aware so a brace inside an alert line is not miscounted.

### The `stop_ref` fix

`stop_ref` was the *prior* 20-day closing low. An oversold candidate is usually
making a **new** 20-day low — that is the signal firing as designed — so its prior
low sits above where it now trades. Live example: TSLA would have alerted
"Invalid below: $319.69" against a $309.22 close, a level already breached before
the message arrived.

`screener.invalidation_level(price, prior_low)` caps the level at 3% below the
current price, applied at the single site in `scan()` where `stop_ref` is built.
Verified by running the real `screener.scan()` on 30 live tickers: 10 signals
fired, **all 10 carried a level below their price**, and 3 were corrected by the
cap (TSLA, INTC, ORCL — all oversold, confirming the bug was structural rather
than a TSLA quirk).

### Roads taken and not taken (invisible in the filesystem)

- **The smoke test was deliberately NOT re-run after `9ea9b01`.** `judge_smoke.py`
  uses hardcoded `stop_ref` values in its fake candidates, so it never touches
  `screener.py` and would have proven nothing about that change while costing
  another half cent. The live 30-ticker scan above is the stronger evidence.
- **`_close_open_brackets` deliberately refuses to repair a reply with an
  unterminated string.** That reply really did die mid-sentence, and half an alert
  is worse than none. Do not "improve" this.
- **One pre-existing assertion changed meaning, on purpose.**
  `'{"picks": [{"ticker": "BBB", "line": "x"'` was asserted to return `[]` as a
  "truncated" case, but all its strings are closed and its content is complete, so
  it now correctly **recovers to 1 pick**. Three cases were added: the real Jul 24
  reply shape, a genuine mid-sentence truncation that must stay `[]`, and
  `{"picks": 5}`, which used to escape the `try` block as an uncaught `TypeError`.
- **`picks_log.jsonl` was NOT seeded from the screenshot** Ethan sent. See "The
  next task" — the prices must come from the sheet, not from image transcription.
- **`facts.py`, `notify.py`, `earnings.py`, `sentiment.py`, `tracker.py`,
  `sheet_webhook.gs` and `run.yml` were all untouched this session.**

## Verified state

| Thing | Value | How |
|---|---|---|
| Repo path | `/Users/ethanyap/stock-agent` | — |
| GitHub repo | `ethankwyap-stack/stock-agent` (**private**) | — |
| Branch / local HEAD | `main` / `d9fc082` | `git log` |
| Remote `main` | `d9fc082d5dd2` — **in sync, pushed** | `git ls-remote` |
| Working tree | Clean except 2 deliberately-untracked plan `.md` files | `git status` |
| Offline checks | **All pass at `d9fc082`** — main 4, analyzer 2, screener 2, outcomes 1 | ran each |
| Local venv Python | 3.9.6 (`.venv/bin/python`) | — |
| Actions Python | 3.12.13 | run log |
| Last smoke run | `30114251411`, 17:45 UTC, **success** — 1 pick, JNJ accepted, AAPL rejected, `Invalid below: $143.50` present | `gh run view` |
| **Last real scheduled scan** | **`30110825060`, 16:53 UTC, on commit `5445d32`** | `gh run list` |
| `picks_log.jsonl` | Does not exist, locally or in the cache | — |
| `state.json` locally | Does not exist (lives in the Actions cache) | — |
| Newest cache | `state-30110825060`, 225 B, 16:55 UTC | `gh cache list` |
| Secrets | GitHub Actions repo secrets only: `ANTHROPIC_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `SHEET_WEBHOOK_URL`. Nothing sensitive on disk. | — |
| Cost | ~$0.40–1.00/month, all Anthropic. Actions free (private repo, ~400 of 2,000 free min; default $0 spending limit stops rather than bills). This session spent ~1 cent on 2 smoke runs. | — |

### Read this before assuming production is healthy

**RESOLVED 2026-07-24 20:25 UTC — production is healthy, this section is history.**
Scheduled run `30117767128` (18:39 UTC) executed the full pipeline on `0715a4f`,
i.e. all of the code below: 89 signals → sentiment → earnings → gates, DLR dropped
at the vol gate, no alert, no error. `screener.invalidation_level` therefore ran
live across 89 tickers. The `parse_picks` brace fix has still only been exercised
by the smoke test, because no candidate has reached the judge since — that needs a
real alert to prove, and none has fired. The original text follows.

**No scheduled scan has executed ANY of today's code.** The last real scan was
`30110825060` at 16:53 UTC on commit `5445d32`, which predates the entire
pipeline refinement. Every run after it (`30112770396`, `30113702531`,
`30114251411`) was a manual smoke test, and a smoke run executes **only**
`judge_smoke.py` — it never calls `screener.scan()`, `main.py`, or the notify path.

So the first production execution of `3c055e3`..`9ea9b01` has not happened yet.
**First action for the next session: check whether it has since landed and
succeeded.**

```
gh run list --limit 5
gh run view <id> --log        # confirm the scan completes and picks parse
```

If a scheduled run has failed, that is the highest-priority thing in this file —
a broken scan stops alerts silently, which is this project's classic failure mode.

## Performance readout (first ever, measured 18:10 UTC 2026-07-24)

Ethan sent a screenshot of the Google Sheet tracker: 11 picks from Jul 16–22.
Current prices were pulled live from yfinance and compared against the `SPY @
entry` the sheet records for each row.

- Average return **+2.24%**; average **+3.34% relative to SPY**
- **10 of 11 beat SPY.** Only NDAQ lagged (−0.3% relative)
- SPY itself **fell ~1%** over the window (740.49 at time of measurement), so the
  gains were not a rising market
- Best: DHR +9.7% (+10.8% vs SPY). Strip DHR entirely and the other ten still
  average +2.6% vs SPY — the result does not rest on one lucky name

**Do not oversell this to Ethan.** 11 picks over 6 trading days cannot distinguish
skill from luck, the marks are unrealized and ignore transaction costs, and the
window is one in which SPY fell. He was told this plainly and understood it.

**One real observation worth testing later:** the composite `score` did not
predict returns in this sample. The best pick (DHR, +10.8% vs SPY) scored **4**;
the worst (NDAQ) scored **5**; CDNS at **3** beat CME at **6**. If that holds over
a real sample, the score is good at *finding* candidates but not at *ranking*
them. This is exactly what `outcomes.py` exists to reveal — which is why the next
task matters.

## Decisions still open — ASK ETHAN, DO NOT GUESS

1. **The orphaned Actions caches.** Adding `picks_log.jsonl` to `path:` in
   `actions/cache` orphaned the ten pre-existing `state-*` caches (the action
   hashes `path` into a version and only restores matching versions). It is
   self-healing — the next successful save writes a reachable cache — and costs at
   most one reset of alert memory. He was told twice and has never replied.
   Almost certainly needs no action; do not "fix" it unprompted.

(The `stop_ref` wart that sat here unanswered for two sessions is **fixed** at
`9ea9b01`. Do not re-raise it.)

## Gotchas

Lead item is the one that bit this session.

1. **Claude sometimes ends its reply one `}` short of valid JSON**, with
   `stop_reason: end_turn` — not a truncation. The greedy regex then also eats the
   closing `]`. Handled by `_close_open_brackets()` as of `b6cfa80`. **Do not
   "solve" a future instance by raising `max_tokens`** — that is a different bug.
2. **`parse_picks` must stay tolerant.** Never tighten it to a strict
   `json.loads`. A bad reply must mean "no picks", never a dead run.
3. **`stop_ref` must never sit at or above the current price.** Any future alert
   field derived from *past* bars has to be re-checked against the *current* price
   before a human sees it. That is the general lesson.
4. **`judge_smoke.py` now exits non-zero on a bad judgment**, so the workflow step
   fails loudly. That is intended. A test that always prints "ok" is not a test.
5. **A smoke run does NOT exercise the scan.** It runs `judge_smoke.py` only —
   no `screener.scan()`, no `main.py`, no Telegram. Never cite a green smoke run
   as evidence that the pipeline works.
6. **Changing `path:` in `actions/cache` orphans every existing cache.** Do not
   casually change it again.
7. **The local venv is Python 3.9.6, Actions is 3.12.** Code must run on 3.9: no
   `X | Y` unions, no `match`. `tuple[bool, str]` is fine (PEP 585 landed in 3.9).
8. **Never run `.venv/bin/python main.py --force`** — full real scan that
   **really sends a Telegram alert**.
9. **`max_tokens` on the judge call must stay ≥ 4000.** Sonnet 5 runs adaptive
   thinking when `thinking` is omitted; a truncated reply parses as "no picks" and
   silently stops alerts rather than erroring.
10. **Never sort inside `sentiment.scan` or `earnings.check`.** Input is
    pre-ranked by score by `main.py`. Sorting once made coverage alphabetical.
11. **The cron is a request, not a schedule.** `run.yml` asks for a run every 30
    min; GitHub delivers 4–7 a day, 80–100 min apart, up to 22 min late. Never
    write logic needing a run in a specific clock hour.
12. **The smoke test costs ~half a cent** of Anthropic API. Cost is Ethan's #1
    anxiety — always name the figure before running it.
13. **The sheet webhook is write-only.** `sheet_webhook.gs` defines `doPost` and
    no `doGet`. Pick history cannot be read back out of the sheet by code. Do not
    re-investigate this; it is why `outcomes.py` keeps `picks_log.jsonl`.
14. **The Apps Script is standalone, not sheet-bound** — it must use `openById`,
    never `getActiveSpreadsheet`. Never have Ethan paste `.gs` code from chat;
    use `open -e sheet_webhook.gs` and copy from TextEdit.
15. **The agent CAN push and CAN trigger workflows on this repo.** `git push` and
    `gh workflow run run.yml -f smoke=true` both succeeded repeatedly this session.

## Reboot / persistence

Nothing runs locally. The whole agent lives on GitHub Actions and survives any Mac
restart. The only persistent state is the Actions cache: `state.json` for alert
memory and `picks_log.jsonl` for pick history. Cache eviction is harmless — it
resets alert memory and costs at most one scorecard, never an alert. The alert
path never reads `picks_log.jsonl`.

**Weak link:** if a scheduled scan starts crashing, alerts stop and nothing
announces it. That is why checking `gh run list` is the first action above.

## Don't redo

- All three code changes above, plus the 7 earlier pipeline tasks (through
  `3c055e3`). Implemented, self-checked, committed, pushed.
- Running the four offline checks "to verify" — they passed at `d9fc082` at
  18:25 UTC. Only re-run after changing code.
- Investigating whether the sheet webhook supports reads. **It does not.**
- Adding `pct_of_52wk_range` to `facts.py`. **Already there, line 28.**
- Verifying `outcomes.report()` works — it was exercised against live yfinance
  prices, produced a correct scorecard, and correctly refused to grade the same
  pick twice.
- Re-raising the `stop_ref` wart. Fixed at `9ea9b01`.

## Seeding: done 2026-07-24 20:25 UTC — `0898297`

**Do not redo this.** The 11 picks are seeded, committed, pushed, and were read
by a live Actions run. What the section below got wrong, and what to know:

- **The sheet is readable by machine after all.**
  `https://docs.google.com/spreadsheets/d/<id>/export?format=csv` returns HTTP 200
  with every column, no auth. "The webhook is write-only" is true; "the sheet
  cannot be read by code" — repeated in three handoffs — was false. So nothing had
  to be transcribed or confirmed by hand: the file was generated straight from the
  CSV. All 11 values happened to match the screenshot draft below.
- **The prices are confirmed twice.** The card built from the seed
  (ABT +3.8%, DPZ +1.5%, NDAQ −1.9%) matches the sheet's own P/L column exactly.
- **`picks_log.jsonl` was in `.gitignore`** — removed, with a comment saying why.
- **Committed AND cached, and the cache wins.** Checkout lays down the seed, then
  cache restore overwrites it once a cache holds the file. Editing the committed
  copy changes nothing in production after the first run, and a cache eviction
  re-grades the 11 seeds. Both cosmetic: a repeated scorecard, never a lost alert.
- **Verified live on run `30123893147`** (digest mode, $0 — digest skips
  facts+judge, so no Claude call): "Sent daily digest", no exception from
  `outcomes.report()`, and the cache grew 218 B → 485 B, which is the seeded file
  being read and saved back.
- **Not directly observed:** the scorecard text inside the Telegram message. The
  log doesn't print the message body. Ask Ethan to glance at Telegram, or infer it
  from the 20d card on ~2026-08-13.
- Only ABT/DPZ/NDAQ were old enough to grade on the day. The rest mature later:
  07-20 and 07-21 picks at 5d over the following days, everything at 20d from
  2026-08-13.

The original instructions are kept below for provenance only.

## The next task (COMPLETED — see above)

**Ethan asked for this explicitly and is starting a fresh chat to do it.**

**Goal:** seed `picks_log.jsonl` with the real picks already recorded in his
Google Sheet, so `outcomes.py` can grade them retroactively — producing a real
scorecard on the next post-close digest instead of a week from now.

**Why it is worth doing:** `picks_log.jsonl` does not exist, so `outcomes.report()`
returns `""` and has nothing to grade. The sheet already holds 11 genuine picks
with genuine entry prices, the oldest dated 2026-07-16 — already past the 5-day
horizon (`HORIZONS = [("5d", 7), ("20d", 28)]`, calendar days). Seeding turns a
week of waiting into a scorecard on the next digest, and starts answering the
score-does-not-predict-returns question above.

**Get the prices from the sheet, NOT from a screenshot.** Ethan sent an image of
the sheet and the numbers below were transcribed from it **by eye and are
unverified**. A wrong entry price silently corrupts every return computed from it,
forever, with no error. Have him open the sheet and confirm each value, or export
it. Sheet: "Stock Agent Picks", id
`1A5-jj4FTdN1VMwkxj_iTuJlhQ7QUUW1HrL3RbROcDis`.

Transcribed from the screenshot — **treat as a draft to be confirmed**
(date, ticker, score, entry $):

```
2026-07-16 ABT  5  99.32     2026-07-22 CME  6  251.87
2026-07-16 DPZ  5  328.09    2026-07-22 T    5  22.99
2026-07-16 NDAQ 5  93.89     2026-07-22 PCG  5  18.00
2026-07-20 CDNS 3  332.06    2026-07-22 T    7  23.02
2026-07-21 HAS  6  87.33
2026-07-21 DHR  4  174.21
2026-07-21 EFX  4  169.82
```

Note `T` appears twice on 07-22 — that is the legitimate same-day re-alert on a
score jump of ≥2 (`RESEND_JUMP`), not a duplicate row to be deduplicated.

**Required line format** (one JSON object per line — see `outcomes.record()`):

```json
{"ticker": "ABT", "date": "2026-07-16", "price": 99.32, "scored": []}
```

**How to make it reach Actions.** `picks_log.jsonl` normally lives only in the
Actions cache, so writing it locally does nothing. The workable path is to commit
the seeded file to the repo: `actions/checkout` then provides it, and because no
cache currently contains a `picks_log.jsonl`, the restore step cannot overwrite
it. The first successful run saves it into the cache and it carries forward from
there. **Verify that reasoning against `run.yml` before relying on it** — the
cache restore step runs after checkout, so once a cached copy exists it wins.

**How to verify when done:** run `outcomes.report()` locally against the seeded
file with a stubbed `price_fn` first (offline, free), then let a real post-close
digest produce the scorecard. The post-close digest only runs on a weekday after
16:00 ET / 20:00 UTC.

## How to work with Ethan

College student, learning developer — not fluent in git, terminals, or deployment,
but learning, so teach while doing. Typos are common; infer intent and proceed
rather than asking about an obvious one.

- **Terminal steps: numbered, ONE command per step**, say what he should see, then
  wait for his confirmation or screenshot before the next step.
- **Lead with the outcome.** First sentence answers "what happened / what did you
  find." He does not watch the process — everything important must land in the
  final message.
- **Cost questions get certainty, not hedging.** Name every service and whether it
  can ever bill him. "Probably free" reads to him as a bug.
- **Verify before saying done.** Exercise the real feature; if something could not
  be tested, say exactly what was not verified. Never say "should work."
- **Screenshots are usually bug reports or "where do I click" questions.** Read
  the image carefully and answer what it actually shows.
- **Short confirmations** ("push", "run it", "go", "yes do both") mean: do exactly
  the pending step, nothing more.
- If he asks a **question**, answer it — do not start changing code.
