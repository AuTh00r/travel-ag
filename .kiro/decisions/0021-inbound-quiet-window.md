# 0021. Inbound Quiet Window

## Status
accepted

## Context
Owner explicitly chose only five seconds of silence instead of fixed batching from the first incoming message. A post followed by two messages can otherwise cross the fixed boundary and create two jobs.

## Decision
Restart only the waiting legacy collector on each new MID. Recovery selects the earliest consecutive prefix with adjacent receipt gaps at most five seconds, ready five seconds after its last receipt. Keep durable timestamps and existing merge and per-client processing.

## Consequences
Repeated delivery of one MID never resets the timer. Identical text with distinct MID remains intact. Running AI is not cancelled; a new message starts the next batch. Continuous messages can delay processing until silence; no cap or text dedup added. No new schema, flags or deployments.

## Links
- .kiro/specs/inbound-recovery/requirements.md
- .kiro/specs/inbound-recovery/design.md
