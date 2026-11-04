# 0006. Inbound Processing Drafts

## Status
accepted

## Context
Approved inbound recovery must reuse all existing business routes while surviving crashes without false receipts, duplicated history, or obsolete manager claims. Existing handlers write sessions and send messages directly.

## Decision
Use a client-scoped ContextVar for staged session changes and explicit deferred notification receipts. Persist validated drafts with CAS and source ownership before external delivery. Finalize customer text after per-destination Telegram receipts. Keep unified reply/manager JSON and route unclear API-only context without inventing ADS. Retain finite durable retry counters and immutable message membership.

## Consequences
Existing feature-off behavior remains available. Deferred sends never count as delivery; assistant history and escalation count follow actual receipts. Unknown external outcomes block replay, so exactly-once is not promised. Integration touches all send and session paths and requires failure-point tests plus a separate production media and MID gate.

## Links
- .kiro/specs/inbound-recovery/design.md
- .kiro/specs/inbound-recovery/tasks.md
- .kiro/decisions/0001-inbound-recovery-hybrid.md
- tests/test_inbound_recovery.py
- tests/test_recovery_pipeline.py
