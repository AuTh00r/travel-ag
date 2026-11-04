# 0009. Model Tool Transport

## Status
accepted

## Context
JSON Output reproduced whitespace on real context; N29 forced tool probes passed text, manager, silent, photo and ten frames. Installed SDK parses arguments and loses duplicate keys.

## Decision
One strict beta prepare_response tool for text and vision, thinking disabled, no SDK retries. Preserve raw provider message before SDK tool parsing with small ChatOpenAI adapter; validate original arguments against existing reply/manager contract; delivery and recovery remain deterministic.

## Consequences
No DB/history/receipt migration. Plain JSON content is rejected. Explicit tool fixtures and raw SDK regression tests required. No tool execution or extra model call. Deployment separately authorized.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- runtime/deepseek-json-whitespace.md
