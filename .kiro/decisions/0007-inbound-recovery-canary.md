# 0007. Inbound Recovery Canary

## Status
accepted

## Context
Первое включение ограничено тестовым аккаунтом, но прежние очереди глобальны. Альтернатива фильтра только webhook оставляет риск чужих отправок.

## Decision
Единый scope ограничивает ingress, SQLite claims, scanner и sends; baseline клиента отделена от первого all. API permalink идёт в прежний shared resolver, unsupported остаётся неполным контекстом.

## Consequences
Другие клиенты сохраняют legacy. Нужны новые проверки смешанных webhook и T1/T2. Недоступное API медиа восстановить нельзя; отдельный always-on receiver в этот выпуск не входит.

## Links
- .kiro/specs/inbound-recovery/design.md
- .kiro/specs/inbound-recovery/requirements.md
