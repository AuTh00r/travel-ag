# Meta warnings after identity rollout

Read-only investigation, 2026-11-01. Production source, configuration and data
were not changed; no model calls or outgoing client/manager messages were made.

## Scanner failures

The initial count of six failures was a raw log count. Both bot.log and
stderr.log contain the same events. Deduplicating by timestamp/event gives
three unique failures at15:31:05,16:32:35,16:53:36Minsk. Each has
reason=transport_timeout, operation=conversations, stage=list_conversations,
attempt=1. No HTTP error response/code was obtained for these failures.
The19:41observation has scan failure counter0 and tester checkpoint age60s,
empty queues and no new failed_final jobs. This confirms scanner progress now,
not guaranteed delivery of every unavailable attachment.

The five raw incomplete_identity lines are three unique warnings,15:07:44,
17:16:48,19:13:21Minsk. One stored identity gap remains. Earlier direct and
expanded metadata reads returned only the business account as participant,
not the tester. Do not invent a client, discard the gap or claim global complete
coverage. Priority tester sync proceeds independently.

## Unavailable shared publication

At14:43:35Minsk a client on the legacy route forwarded one publication without
a question. At14:43:40 source_kind=explicit_id, no permalink identity; at14:43:43
the resolver reported post_unavailable. Source media ID18084087092344077.
The resolver tries direct Graph identity, then searches up to300 accessible
account publications. The follow-up direct read returned HTTP400/code100/
subcode33, without media_type/permalink. This establishes unavailability to
the current token; it does not distinguish deletion, private/foreign ownership
or permissions. It is not evidence of an expired CDN URL or image decoder error.

Correlated trace mid-ce655022917696db: input was a publication with no question,
no model call, job_id absent (legacy), handoff_outcome=none, silent=false.
At14:43:46 Instagram accepted the fallback asking for original photo/video
or a tour name and written question; receipt_recorded status=sent. Manager was
not notified. This is existing legacy media-unavailable behavior, separate from
the silent technical model failure route and tester recovery retry route.

## Evidence and limits

Artifacts: warning-observation-20261101-result.json,
media-warning-impact-20261101-result.json,
media-warning-source-20261101-result.json,
observation-20261101-result.json in the identity release evidence bundle.
Only bounded sanitized fields/previews were exported; no tokens/CDN URLs.
No product fix was made; local source/diff inspection and read-only server
evidence confirm the findings. Recovery remains allowlist for one tester.
