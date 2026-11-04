# Unexpected SDK response and per-attempt deadline

Date:2026-11-04. Local fix N42; not deployed.

Symptom: a503 followed by AttributeError at response.model_dump terminates a
recoverable model series after two calls. Observed request
8c466bdbbdc945ad9fd64fc4a0f2402e, jobaf52511ba23341be85157893cceff601.
Historical response type/body was not recorded; its exact type remains unknown.

Root cause: adapter assumed every non-dict response exposed model_dump. Installed
OpenAI2.44.0 can return plain str for non-JSON HTTP200. HTTPX inactivity timeouts
do not impose a total duration on ainvoke. This is a reproduced possible provider
failure, not proof of the historical body or reason for its7m31duration.

Fix: typed ProviderResponseError for unsupported envelope/choices; preserve safe
response_type and monotonic elapsed_ms. Retry within the existing three reserved
calls, not arbitrary AttributeError. External wait_for120/120/240 cancels awaited
HTTP before retry; await cancellation cleanup. Blocking code or suppression of
cancellation is not forcibly killed. Existing terminal statuses, outbox, receipts,
unknown and takeover remain unchanged.

Manager card: human explanation, bounded customer question, action, then safe
attempt summaries and request ID. Processing failures may follow legacy partial
delivery, so request checking conversation rather than claiming nothing was sent.

Verification:8initialRED;39focusedPASS;141expandedPASS;20latestfocusedPASS;
1809fullpytestPASS/8existingwarnings/100.37s. Ruff/diffPASS. Actual SDK MockTransport
503→text→valid result produces one IG receipt and no Telegram. Slow HTTP body is
closed before retry. Budget after restart, cancellation, final notification and
unknown dedup covered. Read-only review issue about delivery wording corrected.

Production check: original job remains failed_final/model_attempts2; four Telegram
deliveries sent. No manager_last_at recorded; this does not prove no human reply
outside captured events. No replay, manual send, restart or paid probe performed.

Evidence: .kiro/specs/media-understanding/{requirements,design,tasks}.md N42;
.kiro/decisions/0020-provider-response-deadline.md. Test doubles isolate all network.
