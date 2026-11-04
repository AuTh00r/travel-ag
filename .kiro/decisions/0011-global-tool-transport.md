# 0011. Global Tool Transport

## Status
accepted

## Context
Owner approved all-client rollout after N31 tester returned one valid tool call with confirmed delivery. Numeric allowlist cannot express all clients.

## Decision
Add explicit independent DEEPSEEK_TOOL_SCOPE allowlist/all, default allowlist, deploy all. Keep frozen per-request gate and existing strict transport; preserve allowlist for rollback and never expand inbound recovery scope.

## Consequences
Compared with enumerating IDs this covers new clients automatically. Global failure exposure increases; exact code/env backups and DB-preserving rollback return to tested canary. No manual paid probes or client messages implied.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
