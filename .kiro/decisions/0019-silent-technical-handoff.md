# 0019. Silent Technical Handoff

## Status
accepted

## Context
Model failures send technical fallback text to clients; recovery can multiply calls and business quota can suppress alerts.

## Decision
Use a primary budget of three calls with 120/120/240 second timeouts, persisted before recovery calls. Exhaustion becomes failed_final without Instagram reply. Deliver safe bounded diagnostics through durable Telegram technical tasks outside consultation quota.

## Consequences
Reuse receipts, source dedup and unknown protection. Add compatible task kind and model budget columns. Preserve reviewer, media routes, recovery scope and timings. No deployment or paid tests.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
