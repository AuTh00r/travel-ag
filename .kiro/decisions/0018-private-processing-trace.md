# 0018. Private Processing Trace

## Status
accepted

## Context
Для глубокого разбора нужны фактические входы модели и связь с решениями и receipts. Существующий response journal имеет стабильный формат и ограниченную редактуру.

## Decision
Добавить отдельный bounded private JSONL trace с явным immutable serializer и ContextVars плюс существующие request/job/task/delivery IDs. Сохранить формат response journal; не добавлять диагностическое состояние в SQLite. Секреты и медиа удалять до сериализации, провайдера и durable receipt различать.

## Consequences
Полный текст контекста доступен локально для диагностики; storage ограничен20MiB с7backups, запись512KiB. Нужны fault/redaction/correlation tests; ошибка лога не влияет на обработку. Без нового AI вызова и автоматического деплоя.

## Links
- .kiro/specs/media-understanding/requirements.md
- .kiro/specs/media-understanding/design.md
- .kiro/specs/media-understanding/tasks.md
