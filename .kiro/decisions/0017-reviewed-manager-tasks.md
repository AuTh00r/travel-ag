# 0017. Reviewed Manager Tasks

## Status
accepted

## Context
N36 оставил лишние консультации и повторные уведомления; реальные вопросы достигают лимита. Контекст и Telegram receipts должны переживать рестарт и manager takeover.

## Decision
Сохранить основной reply/manager. Один отдельный typed review_handoff для консультационного кандидата возвращает cancel/new/update и окончательный ответ. Открытые задачи и версии хранить в SQLite рядом с delivery journal; обновлять подтвержденные Telegram IDs, не session JSON. При отказе review сохранять исходный валидный кандидат. Диагностика каталога вычисляется по точному tours_text.

## Consequences
Один дополнительный ограниченный AI-вызов только для кандидатов. Миграция task/operation metadata и тесты обоих delivery paths необходимы. Обязательные маршруты не фильтруются. Unknown не пересылается; updates не расходуют новый лимит. Офлайн тесты не доказывают семантику модели, платный аудит отдельно.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- .kiro/specs/media-understanding/tasks.md
