# 0010. Tool Transport Canary

## Status
accepted

## Context
Owner requests deployment only for verified tester. N30 transport is global; installed other-customer JSON behavior must remain exact.

## Decision
Use independent deny-by-default numeric DEEPSEEK_TOOL_CLIENT_IDS. Freeze one per-client protocol decision through prompt, factory, retry and extraction. Restore installed JSON lane byte-identical prompt and payload settings for everyone else; do not couple to recovery scope.

## Consequences
Compared with global rollout this allows isolation but temporarily retains two transports with one reply/manager business schema. Offline golden and mixed-lane tests required. Five source files plus one config value, exact backups and DB-preserving rollback. Paid tests not implied.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
