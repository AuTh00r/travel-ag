# Recovery scope all activation

2026-11-02 owner explicitly requested all-client activation after the new tester
control passed. Fresh config-only package changed INBOUND_RECOVERY_SCOPE only;
both recovery/reconcile flags were already enabled. No runtime source deployed.

Package SHA bb02f665ba7bf12804544f1c38f8d3d81436e08d7650d87377ff7ac0c8c244ee.
Guarded prepare checked36runtime hashes, no global baseline, no active/pending/
unknown sends; online SQLite backup integrity and flags-off inverse PASS.
Independent review and55canary/scanner tests PASS. Previous full1792PASS unchanged.
PID13652->8248; start20:50:21.3409076UTC. New global cutoff
2026-11-02T20:50:29.795800UTC(23:50:29Minsk), old tester baseline retained.
Verify preserved1311sent receipts,8terminal jobs. Later postflight found all
1761previous session states unchanged,34dialogs checked, zero pending/unknown,
scan failure counter0, no new errors/warnings and zero old foreign replay jobs.

First post-cutoff non-tester incoming message: webhook source, done/answered,
one model attempt and one Instagram sent receipt/attempt/part0. This proves a
real new all-scope route; it is not yet a separate API-dedup proof for that MID.
Global complete_scan remains absent; the existing incomplete_identity gap and
missing API voice/media contents remain explicit. Do not call coverage complete.
No clients were manually messaged and no manual paid model calls were made.

Emergency rollback disables both recovery/reconcile flags, keeps scopeall and
all current DB data/new receipts/unknown. Never restore the pre-activation DB.
Evidence bundle recovery-all-20261102: prepare/apply/verify/postflight/new-jobs
reports, config-only controller and private backup remain on the server.

Follow-up at2026-11-03 00:15Minsk (24m39s after activation): healthok,
scopeall and36runtime hashes unchanged;1new job/1client, done/answered,
1Instagram sent receipt,0active/unknown/delivery retries/technical retries,
0old foreign replay jobs.229dialogs checked since activation, newest checkpoint
age4s, scan failure counter0; no new warning/error events in read logs.
The input currently has webhook source only; recovered_jobs0 and no API+webhook
merged events in this small post-activation sample. Thus no actual recovery
incident was exercised in live traffic yet. complete_scan remains absent and
the known incomplete_identity gap1 persists. Do not claim full inbox coverage,
new API-dedup proof or high-volume stability from one completed client job.
Evidence: recovery-all-20261102/observation-20261103-result.json.
