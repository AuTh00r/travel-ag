# 0012. Priority Recovery Scan

## Status
accepted

## Context
Production checkpoint тестового диалога отстал более чем на четыре часа. Общий cursor продолжался каждые 120 секунд, а локальные пропуски чужих диалогов расходовали бюджет Graph. Пользователь разрешил исправление в существующей спекае inbound-recovery.

## Decision
Известные сохранённые диалоги текущего allowlist сверять перед discovery в рамках одного тика. Ограничивать реальные Graph GET через task-local ContextVar в общем rate-limited _get; исчерпание бюджета штатно оставляет cursor на непрочитанном элементе. Scope all сохраняет общий обход. Новых таблиц и служб нет.

## Consequences
Сверка известного тестового диалога не зависит от полного обхода; каждый priority GET расходует общий лимит. Сохраняются deadline, cursor, паузы, baseline и provider backoff; при недостаточном бюджете проверяются сначала старые checkpoint. Новые диалоги требуют discovery. Ошибки проверяются регрессиями и полным pytest, без реальных отправок.

## Links
- .kiro/specs/inbound-recovery/requirements.md
- .kiro/specs/inbound-recovery/design.md
- .kiro/specs/inbound-recovery/tasks.md
