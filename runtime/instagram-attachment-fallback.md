# Unknown Instagram attachments

Date: 2026-10-09. Scope: supported image/story/post handling unchanged;
audio transcription and new direct-video decoding excluded.

## Symptom / root cause

Synthetic probes proved type=null/list/dict failed during set/join; message=null
failed during .get; non-string text reached dispatcher .strip. Unsupported-only
and malformed attachment containers disappeared. A single bad event could
abort a webhook before a valid adjacent message. Telegram failure still claimed
successful manager handoff; username await/error paths permitted takeover race.

## Fix

Validate each container and identifier before access/hashing. Normalize only
safe bounded ASCII attachment type, text always string. Explicit unsupported
cannot open media/contact/empty-template fast-path. Unknown message with MID
gets existing non-text fallback; deletion/service events remain ignored.
Visible postback title with MID goes to text; payload not executed. Invalid JSON
returns 400 after signature check. Failed notification gets truthful reply and
does not increment counter. Pending/active manager gates cover lookup, delivery
and technical-error fallback; unavailable session means no unsafe response.

## Verification / limits

24 initial regression failures reproduced defects. Final 44 focused cases,
full local 559 PASS and Ruff PASS. Read-only final review found no remaining
concrete defects. Server isolated QA: 557 PASS/2 previous JPEG-artifact skips,
Ruff PASS. Backup-attachment, 3 files/16 SHA verified, listener 11672 → 3460,
local/public health ok. Real unsupported media understanding not claimed. Synthetic fixtures do not
prove every future Meta schema or unavailable/private media is accessible.
Direct video/audio/file/GIF/product content remains unreadable; question text
is preserved, standalone unreadable media goes to manager. No paid manual API
calls, real outbound test messages, production data/flags/limits changes.
