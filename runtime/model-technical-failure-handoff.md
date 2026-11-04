# Technical model failures sent to clients

Date:2026-10-31. Scope: N40 implemented, verified and deployed after explicit approval.

Symptom: clients received technical fallback messages after empty/malformed model
output or handler/API exceptions. A previous audit confirmed15historical deliveries.

Root cause: main's invalid-response branch explicitly constructed a visible error;
generic text/nontext exception handlers also sent a fallback. Only empty/schema
responses got one immediate retry. A broad catch mislabeled local errors as provider
failures; recovery's technical retries could multiply full generation attempts.

Fix: three total primary calls, transport120/120/240s, SDKretries0. Retry recoverable
transport/HTTP/status/response errors; auth/config/local failures terminate early.
Exhaustion becomes failed_final and plans only durable Telegram technical delivery,
outside business consultation quota. Include bounded safe stage/type/status/origin,
attempt/timeout and trace IDs, without raw exception/body/media/secrets.

Recovery reserves budget and log before each call; crashes do not replenish it.
Technical source keys/part1 coexist with existing consultation receipts. Unknown
delivery stays unknown; retries send only proven unsent destinations. Meta refresh
failure does not prevent technical Telegram delivery; manager cancellation still
overrides it. Existing media-unavailable guidance and reviewer remain unchanged.

Verification: SDK MockTransport verifies actual120/120/240and HTTP classification;
SQLite regressions cover crashes, quota, semantic reset, duplicate/unknown alerts
and manager takeover. All providers are stubbed, no paid calls or production writes.
Final test evidence is recorded in the N40spec tasks.

Deployment:31Oct12:58Minsk,10runtimefiles/35manifest entries, PID19360.
Local/public health and SQLite integrity/schema PASS.1706existing sessionstates
and1104receipts preserved; env/credentials/baselines/test-only recovery unchanged.
Fresh logs show no errors/warnings/tracebacks. Existing Cloudflare filtering
rejects the default Python User-Agent for public GET; a browser User-Agent gets200.
No Cloudflare access rules changed. Backup and deployment proof retained separately.

Limits: no truthful guarantee of immediate Telegram delivery during Telegram/DB
outage; confirmed and uncertain sends retain the existing outbox safety rules.
Transport timeout is not a strict whole-handler deadline. A crash reservation
records uncertainty rather than inventing a provider response.
