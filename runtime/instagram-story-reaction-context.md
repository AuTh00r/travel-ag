# Instagram story reaction loses follow-up context

Date: 2026-10-09. Scope: own story emoji reaction followed by a plain question.

Symptom: client reacts to a story, then asks «можно подробнее»; bot answers
without seeing the story. Live sanitized logs:16:40:36.755 UTC exact story ID
received, story_reaction.ignored/events0; next plain question24.77s later.

Root cause: parser drops the entire reaction before returning events, losing
exact ID and MID. Next webhook carries no reply_to. Five-second batching cannot
bridge the observed25s gap.

Fix: context-only event, MID reserved before storing; exact ID only, no URL/text.
Monotonic120s TTL, one-shot per sender, cap10000, prune expired; snapshot at next
plain input before any await. New snapshot starts a separate plain merge group;
subsequent plain questions remain grouped. Explicit media/phone/referral/manager
clears or takes precedence. Shared input-phone helper retains the engine's prior
canonical and multiline rules. Shutdown clears memory. Existing story resolver
uses original photo or10 full-video frames and honest unavailable fallback.

Verification: original4 regression FAIL → PASS; review found two merge boundary
cases and two multiline contact cases, each reproduced red then fixed.26 new
cases, full local627 PASS/Ruff/diff-check PASS; read-only final review clear.
Server isolated stage625 PASS/2 previous JPEG-artifact skips/Ruff PASS.
Backup-story-context,4 changed files/all17 runtime SHA verified; listener10076
→5292; localhost/public health200/ok. No paid AI/manual customer or manager sends;
production session/counters/history/config untouched.

Limits: context expires120s or on restart; ordinary messaging.reaction service
events without a story ID remain ignored. Story must still be accessible through
the existing exact own-story resolver. Real reaction+question repeat pending;
synthetic tests prove routing, not the story's tour content or live delivery.
