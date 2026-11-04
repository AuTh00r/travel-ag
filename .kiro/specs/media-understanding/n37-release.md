# N37 release preparation — 2026-10-29

Initial preparation: local implementation plus separately authorized evaluations. The first19-call
budget found five decision/task failures; corrections passed1597pytest/Ruff/diff.
A separately approved9-call targeted repeat then passed9valid responses/9expected
actions plus independent manual facts/context/link/closing review. Total28calls
used; no paid-call balance remains. At that stage no deployment, client/manager
sends or production state changes were performed. The subsequent authorized
deployment is recorded in the final section.

## Runtime files

Review the N37 changes in these files against the installed source manifest before
packaging; the workspace also contains unrelated preexisting changes.

- src/ai/prompts.py
- src/config.py
- src/main.py
- src/services/llm.py
- src/services/llm_response_log.py
- src/services/handoff_review.py (new)
- src/services/telegram_notify.py
- src/services/inbound_recovery.py
- src/db/inbound.py
- src/db/sessions.py
- src/db/manager_tasks.py (new)

N38 subsequently adds correlated diagnostics and requires these dependencies in
the same reviewed package (14runtime files total):

- src/services/diagnostic_trace.py (new)
- src/channels/instagram.py
- src/db/pending_messages.py

The other11 files above already include shared N37/N38 changes where applicable.
Do not deploy imports without the new diagnostic module. N38 changes observability
only; model decision instructions remain those of the successful9-case repeat.
See n38-diagnostics.md for contents, limits and correlation.

MANAGER_REVIEW_ENABLED defaults to true; MANAGER_REVIEW_TIMEOUT_SECONDS defaults
to25. One extra model call occurs only for a valid proposed ordinary consultation.
Provider/format/timeout failures preserve that proposal. Required routes bypass
review. The ordinary primary prepare_response reply/manager contract is unchanged.

Updates edit only saved confirmed Telegram message IDs. Known-unsent destinations
may receive their first notification; unknown destinations remain held. The
legacy worker runs every30s, respects due/retry budgets and shares the business
client lock. Delivery retries do not generate/review the response again.

## Independent semantic evaluation, after separate paid-call authorization

The21-case synthetic matrix covers19 consultation reviews and2 mandatory contacts
which bypass review. It contains no real handles/client history. Expected action
checks are automatic; assess factual correctness and clarity in the saved reply
manually as well. This evaluates saved candidates, not21 new primary model calls.

Capture the current confirmed production catalog into a local text/snapshot file
using read-only access before evaluation. The repository's local DOCX is older
and lacks Belostok; do not use it to score the Belostok/date cases. Preflight
rejects a catalog without the confirmed08.12.2026 availability for those cases;
if real dates have changed, revise the matrix before paying for tests.

Dry-run (zero calls):

```text
.venv/Scripts/python.exe scripts/handoff_review_eval.py --catalog <catalog.txt>
```

Only after explicit authorization for up to19 calls:

```text
.venv/Scripts/python.exe scripts/handoff_review_eval.py --catalog <catalog.txt> --execute --budget 19 --bundle <new-output-directory>
```

The runner never invokes business handlers, the session DB or Instagram/Telegram.
It reserves and fsyncs each call before sending, caps the budget, refuses an
existing output directory and stops on any unconfirmed review. It writes a
separate model journal; a timeout is not permission to replay the request.

First-run findings and corrections: n37-review-bugfix.md. The separately approved
repeat of cases2/4/5/6/8/10/14/19/21 passed (9calls): the5confirmed failures and
4route/format regressions. All9closings match once at the end;8URL occurrences
(5unique) are canonical catalog program links. No false handoff promises.
Preserve both reports. Further calls require another explicit budget and a new
bundle; the existing budgets are exhausted. The revised candidates include the
primary closing. Subsequent N38 instrumentation changes source files without
changing the model decision instructions or adding any model call.

Limits: this verifies the review stage on synthetic inputs. It does not repeat
all original cases on the final prompt or send real Telegram edits. Nonblocking
observations: the abbreviated catalog list in case10 is worded too categorically;
cases2/4place the program link after an opening description.

## Production rollout, after separate deployment authorization

The first live run failed acceptance; the corrected targeted repeat passed.
Production rollout still requires its own authorization and normal postflight.

1. Compare these14 files with the installed manifest; stop on unrelated divergence.
   Capture source backups and an online consistent SQLite backup before migration.
2. Deploy only the reviewed source delta. Preserve environment, credentials,
   history, pauses, counts, recovery scope/baselines, receipts and unknown states.
   New SQLite tables/columns/indexes are additive and idempotent.
3. Restart normally. Verify health, startup/catalog publication, schema, background
   worker, model phases/catalog metadata and a new test message with one reply.
   Check new/update/cancel decisions and each confirmed Telegram destination.
4. Rollback restores the backed-up source only; do not restore the old DB over
   newer receipts. Additive schema is compatible, but old code cannot execute
   N37 edit operations correctly. Before any replacement, refuse rollback if
   manager tasks remain open or task operations are ready/retry_wait/sending/
   unknown (all clients, future due and both legacy/recovery). Preserve these
   tasks and receipts; keep the N37-aware runtime for their safe resolution.
   The controller permits an automatic inverse only during partial installation
   before any new boot, while the original pre-N37 PID/start still matches.
   Online old-code rollback after restart is always refused: a read-only empty
   outbox check has a race with new writes. A later old-code rollback requires
   offline maintenance with writers stopped throughout the inverse operation.
   Emergency MANAGER_REVIEW_ENABLED=false disables new reviews/task planning;
   already authorized safe legacy deliveries continue. Unknown is never reset.

No recovery-scope expansion or replay of old customer correspondence is part of
N37. Old Telegram cards without stored task IDs are not retroactively guessed or
edited; only newly journaled model consultations can be updated.

## Installed 2026-10-29

Explicit deployment authorization followed the N38 completion. Combined package
6cc07643 installed14files, manifest31 ->34; process3836 ->11164/start19:20:39Z.
Local/public healthok, schema/integrity/catalog8 PASS; env/credentials and recovery
allowlist/baselines unchanged,974old receipts/1659old client sessions retained.
Local and server release proof passed; trace writer verified without manual model
calls or sends. Safe postflight and installed manifest were captured separately.
No complete new model/review/delivery chain has yet been observed after restart.
