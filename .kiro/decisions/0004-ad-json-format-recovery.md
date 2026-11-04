# 0004. Ad Json Format Recovery

## Status
accepted

## Context
Provider JSON may omit required decision/reply/context fields; N25 only retries whitespace.

## Decision
One corrected regeneration for explicitly repairable JSON and schema errors within the existing two-call ADS budget; no guessing or raw bad output in the reminder.

## Consequences
An extra inference is bounded. Strict final validation, terminal errors, takeover, media identity and delivery receipts stay intact. Second failure still calls the manager.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
