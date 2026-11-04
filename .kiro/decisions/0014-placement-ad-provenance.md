# 0014. Placement Ad Provenance

## Status
accepted

## Context
Current resolver rejects every nonempty asset_feed_spec. Four authorized live ads return PLACEMENT feeds and proven Instagram IDs/permalinks, but the referral contains no placement selector. Selecting the first asset or treating the canonical post as the exact displayed variant can misstate dates and prices.

## Decision
Reuse exact configured account/ad/creative and Instagram ID/permalink checks for PLACEMENT. Carry canonical media with marketing_variant provenance and append any actual clicked image with distinct labels. Keep unknown feeds unavailable with clicked fallback; preserve strict media guards. Alternatives: blanket rejection loses valid source material; arbitrary first asset invents the displayed variant; neither is accepted.

## Consequences
Accessible placement ads can provide original image or ten video frames without new permissions or model calls. Prompt and history explicitly state that the shown variant is unconfirmed; actual clicked image takes precedence for displayed details. Exact clicked video cannot be guaranteed without a selector. Existing unknown ad-ID errors remain unresolved; production deployment is separate.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- https://developers.facebook.com/docs/marketing-api/dynamic-creative/placement-asset-customization/
