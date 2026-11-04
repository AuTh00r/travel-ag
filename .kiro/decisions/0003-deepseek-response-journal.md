# 0003. Deepseek Response Journal

## Status
accepted

## Context
The owner requests DeepSeek response logging after invalid_fields errors could not be diagnosed from safe metadata alone. Existing bot logs intentionally omit raw responses and must keep that boundary.

## Decision
Add one separate local UTF-8 JSONL journal at the sole model completion site. Retain redacted response text and bounded explicit metadata with shared request UUID across attempts. Use a dedicated non-propagating size-rotating handler with safe handleError and best-effort failure handling.

## Consequences
Compared with putting raw text in bot.log, the separate journal preserves useful diagnosis without console/general-log propagation. It still contains client answer text and inherits server filesystem access controls; mode0600 applies where supported. Five MiB plus seven archives bounds retained volume near40MiB, not a day-based retention. Known secrets and media payloads are redacted; unknown secrets cannot be guaranteed recognizable. No deployment or extra paid inference is performed.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- runtime/instagram-ad-empty-json.md
