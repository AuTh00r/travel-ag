# Human context in contact escalation

## N6: concise gist supersedes N5 excerpt (2026-10-10)

Owner live feedback: full reply appeared in Telegram instead of the expected short
consultation gist. N5 deterministically replaced the existing model Context with
up to1500 characters of delivered answer; this was the wrong output format.

Fix: reuse a valid standalone manager Context from the same existing AI call,
1–2 sentences ≤450 characters: named tour, question, important conditions, source.
Prompt forbids program/catalog/reply copying and technical IDs/URLs/phone numbers.
Actual input phone remains authoritative. Missing/invalid/overlong context,
conflicting model phone, or a new question together with phone uses bounded
fallback from selected user turn200 + one substantive paired reply sentence160;
skip greetings/ack/footer, never cross a new user turn. History unchanged, no
additional AI/Graph calls. N5 below is historical, not the current output design.

Verification:18 initial FAIL→PASS;2 URL/consultation FAIL→PASS;1 link-label FAIL→PASS;
116 engine/phone PASS,654 full local PASS/Ruff/diff-check PASS, final read-only review
clear;15 new integration/prompt cases. Isolated server652 PASS+2 previous JPEG-artifact
skips/Ruff PASS; guarded backup-contact-summary,3 files/all17 SHA verified,
listener15292→12324, local/public health200/ok, all media flags true.
No reset of customer sessions/limits, no extra paid calls or manual notifications.
Limit: synthetic checks do not prove the next live model generation. A fallback
is deliberately narrower than a semantic model summary; hidden media is not guessed.


## Historical N5 (superseded after owner feedback)

Date: 2026-10-10. Scope: contact handoff after a media question and delivered answer.

Symptom: story reaction→«можно подробнее»→Elbrus answer→phone produced a manager
notification with only «можно подробнее» and a numeric VIDEO story identifier.
Owner supplied the notification and confirmed successful S7 live routing.

Root cause: deterministic actual-input-phone override discarded model context
and scanned only the last eligible user question, ignoring its delivered answer.

Fix: preserve actual phone authority, pair selected historical user request with
the following delivered assistant entries until the next user. A current question
with phone takes priority and has no old answer. Humanize known media marker lines
only in the notification. Strip manager blocks and phone-bearing excerpt lines.
Question1000/answer1500 limits keep context under3000 and Telegram under4096.
Label «Клиенту ответили» distinguishes the reply/catalog from visible story text;
this adds existing conversational detail, not new visual analysis. History keeps
original provenance unchanged. No additional LLM/Graph calls or new DB schema.

Verification:8 initial regression FAIL→PASS;3 reviewed no-caption/source FAIL→PASS;
101 engine/contact PASS,639 full local PASS/Ruff/diff-check PASS;12 new integration
cases cover photo/video, new topic/current question, unavailable/missing/chunked
answer, phone footer, long reply and no-caption media sources. Read-only review
found no remaining concrete defects. Package2 files/17 runtime SHA prepared;
upload initially requested Cloudflare browser login, then finished exit0.
Server isolated QA637 PASS/2 prior JPEG-artifact skips/Ruff PASS; guarded patch
with backup-contact-context,2 files/all17 SHA verified, listener5292→15292,
localhost/public health200/ok, three flags true. Docs/spec/runtime sealed.
No real notification/client send, paid replay, session reset or config changes.

Limit: excerpt contains what the bot actually told the customer; unseen details
of the story are not invented. No delivered answer means only the question/source.
Live new phone handoff remains a separate optional check.
