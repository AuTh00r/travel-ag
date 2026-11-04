# Missing conversation participants

2026-11-01. Read-only production investigation, followed by an authorized
single-source deployment at 13:56 Minsk. Recovery remains tester-only.

The global complete_scan checkpoint is absent while the priority tester dialog
is refreshed normally. One conversation returns only the company's own IG account
in participants. A direct metadata GET and participants.limit(100) both return200,
one own participant, no next page. It does not match the tester checkpoint.
Do not infer deletion or a customer ID, read messages to guess ownership, discard
the gap or claim complete coverage. API data is insufficient to resolve this gap.

Independent local bug: str(item.get('id')) turned None into a foreign client string
and could falsely count scope exclusion as a successful scan. Validate container,
list/item/id types, positive numeric ASCII client IDs and deduplicate IDs before
scope checking. Invalid metadata stays incomplete_identity and cannot read messages.
Known internal client checkpoints retain their existing route.

Evidence:11red participant cases;125profile and1748full tests PASS,8old warnings;
Ruff/diff/independent read-only review PASS. Stubs cover delivery failure/restart,
unknown receipts and manager cancellation; production was never stopped for testing.
Live pair5.34s apart correctly made2jobs. Second pair1.25s apart made1job,1call,
1confirmed reply. Later both mids hadAPI+webhook/version1, no new call/delivery,
tester scanage44seconds, pending0.

Fresh media check at 2026-11-01 13:35 Minsk: photo, direct video and voice each
have one done/answered job, one model attempt and one sent Instagram receipt.
After reconciliation all three MIDs have API+webhook sources at version1;
pending jobs0, tester checkpoint age43seconds. Direct read-only Meta request
returns image_data.url for the photo and video_data.url for the video. The voice
returns is_unsupported=true with no attachments/shares. Its successful live
processing depended on the webhook; API-only audio recovery is not available
from that response. Evidence: recovery-media-api-proof-20261101-result.json.

Deployment evidence: package SHA
190e0f940f05d3f2cff15a6ac62566c5426aafae1f93ad1740d9b1bed99f1840;
one source plus manifest,36runtime hashes verified. PID12328 ->17976;
start10:56:15.3078558Z. Prepare/apply/verify/postflight exit0, backup/inverse/review
PASS. All1712previous session states,1143receipts,8terminal jobs and baselines
preserved; environment and credentials unchanged. At13:57Minsk local/public
health ok, no fresh errors/warnings/tracebacks, queues/unknown/sending0, tester
checkpoint refreshed after restart. No manual paid calls or external sends.

Limits: the identity fix does not supply the absent Meta participant or prove
global coverage. Keep recovery tester-only until a separate scope decision.

Follow-up on missing voice media, 2026-11-01: two read-only requests against
the same fresh tester voice MID confirmed the list result. GET message node
with id,message,attachments,shares,is_unsupported returned200, exact MID,
is_unsupported=true and no attachments/text. GET message attachments edge
returned200 and an empty data list. These read paths supply no audio URL for
the checked recording. Evidence: recovery-identity-release-20261101/
voice-node-probe-result.json. No production source/config/database changes or
sends were made for this probe. URL expiration is not an established cause:
the response contains no URL to test. Main-bot availability and a durable local
media cache would protect future received webhooks, not reconstruct an already
lost event. Voice files currently use a temporary job directory.

Read-only observation at 2026-11-01 19:41 Minsk succeeded after intermittent
Cloudflare SSH failures. All36runtime SHAs match, recovery allowlist/1 remains.
Tester checkpoint age60seconds, scan failure counter0, queue/unassigned/
unknown/sending0. Six known tester jobs remain done/answered, each with one
model attempt and one sent Instagram delivery/attempt/receipt. No new tester
jobs or failed_final jobs since the deployment. Existing8terminal jobs remain.
Log slice since prepare is complete within the2MB cap (bot271743bytes,
stderr198067bytes): no errors or tracebacks;6graph.failed+6reconcile.failed
warnings,5incomplete_identity warnings for one stored gap,1image.media.unavailable.
These are raw mirrored log counts. A later audit deduplicated by event and
timestamp: only three Graph/reconcile failure pairs, each mirrored in bot.log
and stderr.log. All three are transport_timeout/list_conversations/attempt1,
at15:31,16:32,16:53Minsk. Five incomplete_identity lines represent three unique
warnings for the single stored gap. Current successful
tester checkpoint and zero failure counter establish scanner progress now.
This observation adds no fresh incoming tester scenario after deployment.
Evidence: recovery-identity-release-20261101/observation-20261101-result.json.
Detailed follow-up: runtime/meta-warning-audit.md.

Fresh tester control after the date rollout, 2026-11-02 23:30–23:33Minsk:
question about Bialystok ->job51fb4665cbde48d19d4cd54e49042e16, one member,
one model attempt, done/answered, one sent Instagram receipt/part0/attempt1.
Response contains the correct program and booking URLs. Subsequent reconciliation
adds API source to the same webhook MID at version1; no second job/call/delivery,
queue0, no manager pause, scopeallowlist/1 unchanged. Evidence:
tour-dates-release-20261102/live-recovery-check-20261102-result.json.
No failure injection/production outage: this proves live happy path and dedup,
not recovery of unavailable audio. Failure modes remain covered by isolated tests.
