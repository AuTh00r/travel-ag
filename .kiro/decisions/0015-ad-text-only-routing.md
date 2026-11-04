# 0015. Ad Text Only Routing

## Status
accepted

## Context
Owner replaces ad-media and ad-context behavior with ordinary client text only. Webhook parsing, five-second merge and persisted recovery can otherwise reintroduce media, silent escalation or an unrelated story hint. Existing ad media utilities have independent tests and need not be removed.

## Decision
Normalize ADS events before grouping and again at processing boundaries. Preserve actual text and routing identity only, with a private text-only marker to exclude story enrichment and incomplete-source silent mode. Empty ADS is deliberately ignored. Preserve independent non-ad media and existing manager/delivery rules. Supersede runtime ad analysis from ADR0014; retain low-level utilities without calling them for ADS.

## Consequences
No ad downloads, vision, title/ID/link context or ad-only manager fallback. Existing queued ADS follow the new rule. New replies rely on client text plus ordinary history/catalog. Historical records are not deleted, no production settings or permissions changed, deployment is separate. Alternative of disabling only Marketing API is rejected because thumbnails/referral context and recovery paths would still reach the model.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- .kiro/decisions/0014-placement-ad-provenance.md
