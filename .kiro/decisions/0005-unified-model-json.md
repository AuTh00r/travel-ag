# 0005. Unified Model Json

## Status
accepted

## Context
ADS JSON still embeds manager markers while other routes use plain text; natural invalid_fields showed incompatible response contracts complicate processing.

## Decision
All model calls return exactly reply and nullable manager object with context/type/name. No embedded action markers, decision/reason duplication or model phone; all routes share strict validation and bounded recovery.

## Consequences
Update prompts, sole handler and explicit test envelopes together. Current input phone, actual delivery receipts, pauses, silent ADS and legacy history sanitization remain. No DB migration, paid call or deployment implied.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
