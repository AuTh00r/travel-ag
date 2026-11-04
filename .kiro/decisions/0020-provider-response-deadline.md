# 0020. Provider Response Deadline

## Status
accepted

## Context
SDK may return plain text for non-JSON HTTP200. model_dump then crashes and ends a recoverable series after two calls. HTTP read timeout does not bound full invocation duration.

## Decision
Validate dict or SDK ChatCompletion with a typed safe error. Bound primary ainvoke with asyncio.wait_for120/120/240 and retain persisted three-call budget and final outbox. Show manager action before bounded diagnostics.

## Consequences
Do not retry arbitrary AttributeError or revive failed_final jobs. Wait for cooperative async transport cleanup on cancellation; executor conversion already running cannot be forcibly stopped but has no delivery side effects. No schema or deployment change.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
