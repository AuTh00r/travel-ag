# 0002. Ad Empty Response Retry

## Status
accepted

## Context
Production ADS JSON request returned whitespace with finish_reason=stop and was immediately handed off. Existing tests enforced this one-call fallback; the owner explicitly authorized one empty-response retry.

## Decision
Retry exactly once only when the first ADS response is a whitespace-only string and is not truncated. Reuse the same model and prepared messages; check pending and persisted manager takeover after each await. Keep strict JSON validation and all other fallbacks unchanged.

## Consequences
An affected request may incur one additional inference and its latency. A second empty, invalid or failed result still produces the existing bounded silent handoff. Transport SDK settings are unchanged. No replay, deployment or live model probes are authorized by this local fix.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- runtime/instagram-ad-empty-json.md
