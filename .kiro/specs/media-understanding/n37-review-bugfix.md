# N37 live review corrections — 2026-10-29, before corrections

Initial finding:19authorized calls completed,19valid structures,17action matches. Cases2
and10 wrongly cancel an already specified unsupported date period. Manual review
also found case14 replacing booking-possibility with an unrelated transport task,
case19 choosing the first catalog departure without the client choosing it, and
case21 losing the known Elbrus/date context in a new independent question.
AllURLs were present in the catalog, but the review system lacked shared business
rules for canonical program links and closing; the shortened synthetic candidates
did not validate preservation of a complete primary reply.

Expected: unsupported explicit client conditions remain a concrete manager task;
an alternative outside the requested period does not resolve it. Never invent
client dates/conditions or replace their unanswered questions. Independent new
tasks retain an unambiguous known tour/date without merging different questions.
The review system reuses the same trusted business/link/closing/security rules
as the primary, without importing its prepare_response/JSON transport contract.

Root cause evidence: cancel rules broadly allowed clarification of dates without
requiring the date to be genuinely unknown; the remaining new-task rule was less
specific. Catalog facts were not explicitly separated from client selections.
Dropping every primary SystemMessage also dropped necessary business rules.

Correction: narrow cancel eligibility, state the explicit-period priority and
source boundary for client conditions, retain every unanswered task and known
trip context, and compose shared business rules into the dedicated review system.
Keep the21expected actions unchanged; do not relax them to match failed outputs.

Unchanged: one bounded review/max_retries0, primary reply/manager, mandatory routes,
task IDs/CAS, counters, delivery journal, takeover, no blind repeats and no sends
from evaluation. The19-call budget is exhausted. Corrections are offline until
additional bounded live evaluation is explicitly authorized. No deployment.

Local verification after correction:1597pytest PASS/8preexisting warnings,
Ruff/diff PASS; independent read-only composition review found no blocker. The
original21expected actions are unchanged. The revised evaluation candidates now
contain the canonical primary closing. At that stage, the targeted repeat was
prepared with no remaining first-run budget.

Subsequent separate authorization «Да, до9вызовов» funded9targeted checks on the
same captured catalog. Result:9valid tool responses/9expected actions; independent
manual review and data-only assertions confirm the five defects resolved in those
cases. Nine exact canonical closings and8URL occurrences (5unique), all confirmed
program URLs; no false handoff promises. Source hashes match the corrected code.
Nonblocking: case10's abbreviated catalog list is too categorical;2/4place the
program link after the opening description. No further prompt edits or calls.
Total19+9=28calls used; production unchanged, no sends. This is targeted reviewer
acceptance, not a claim of universal model accuracy or live end-to-end delivery.
