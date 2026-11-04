---
status: deployed-and-verified
date: 2026-10-22
scope: ADS webhook, queued/recovered events and direct handler calls
promoted_to: null
---

# ADS referrals use only the client's text

## Intent and previous behavior

Owner explicitly superseded ad analysis: ignore the advertisement completely as
media/context, process only actual typed text. Previous paths could fetch ad
media/title, mark empty input as a silent manager handoff, attach a story reaction,
or allow silent model output from incomplete recovery metadata.

## Implementation

One event normalizer retains sender/MID/related MIDs/timestamps and actual text,
removes ad referral/media and marks the source privately as text-only. Parser
applies it before phone-card, story/reaction, unsupported, voice and media parsing.
Grouping normalizes old raw events before merge; dispatch and direct AI/background
handlers defend persisted/direct legacy input. Empty ADS is deliberately ignored,
including a real old queued job, with no AI, response, notification or retry.

The private marker prevents a previous story reaction from enriching ADS and
overrides incomplete-source silent permission. It does not strip independent
customer media merged from different MIDs. Existing API/webhook same-MID persistence
replaces the prior API payload with the richer webhook; it must not be changed to
a union of media fields. Both arrival orders are tested for IMAGE/VIDEO.

Known automatic ad annotations in old user history are stripped only in a copied
model-input projection. Stored history/receipts and normal conversation remain.
No ad-ID guessing, fetch, vision, title context or ADS-only escalation. Ordinary
text catalog/guard/phone/manager handling and standalone media remain unchanged.
The old pure ad-media utilities remain independently testable; incoming ADS no
longer reaches them. No settings, permissions, server state or recovery scope change.

## Verification and limitations

Initial 14 new regressions failed before implementation, then passed. Final N35
matrix32PASS includes raw attachment variants, empty input, direct/background
calls, real legacy queued task, incomplete recovery, previous story suppression,
API/webhook source ordering, independent customer media in both message orders,
ordinary guards, manager pause, current phone and prompt-history privacy.

Existing JSON format-retry, phone/privacy, delivery and non-ad incomplete-context
semantic recheck tests were updated to ordinary ADS text behavior and retained.
Forty test functions (98 parameter cases) solely asserting the superseded ADS
media/silent policy were replaced with the new routing matrix; no skips/xfails,
network/model stubs or validation gates were disabled. An explicit retirement map
and before snapshots are retained in the local ad-text-only-20261022 artifacts.
Pure resolver/media/security tests remain. First complete updated suite1492PASS;
the final suite including four additional source-order tests:1496PASS,
8preexisting warnings,60.12s.

Ruff/diff/micro-spec validation PASS. Independent read-only review found no blocker
and confirmed ordinary attachments survive, history originals are unchanged and
API media cannot reappear through the existing replacement semantics. Exactly four
installed source paths differ from the verified deployment manifest: channel,
main, inbound store, recovery coordinator; all other installed source hashes match.

Implementation phase made no paid model calls, production reads/writes,
deployment, restarts or manual messages. The separate rollout follows.

## Deployment

Owner confirmed View ad/source ADS scope and explicitly authorized «деплой».
Release ad-text-only-release-20261022 contains exactly4source paths plus updated
manifest. Local1496PASS; server isolated72PASS with copied external-HTTP-deny
conftest. Exact rollback controller proof passed locally and on the server,
including partial install, preserving new receipts/unknown and refusing drift.

PID11436→15408, 2026-10-22 17:16:18Z/20:16:18 Minsk. All31installed hashes and
local/publichealth verified. env/credentials/launchers/recovery allowlist1 and
first-enable baselines unchanged. All407previous sent receipts retained,
408current; terminal jobs and session revisions preserved;active/pending/unknown0.
Installed synthetic parser proves ADS text becomes user, empty ADS ignored,
separate ordinary photo remains normal. Initial post-restart log interval clear.

Fresh source/manifest and online DB backup retained. Code-only rollback restores
only four source files and manifest, never the live SQLite. No manual messages,
paid model calls or real client test initiated. Package SHA256:
fe169c3a0b20f0bbf35c967a11add4360979866da5b0ea2f47e878daf43a4c7a.
Cloudflare login was renewed after a timed-out first SSH banner; no policy or
session-duration changes. Use only release.py, not the imported old helper CLI.

## References

- .kiro/specs/media-understanding/requirements.md (N35)
- .kiro/decisions/0015-ad-text-only-routing.md
- tests/test_ad_text_only.py
