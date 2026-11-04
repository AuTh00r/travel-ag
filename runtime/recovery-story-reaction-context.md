---
status: verified
date: 2026-10-20
scope: webhook timestamp; story reaction hint 600 seconds; deployed
evidence: inbound-recovery TSK-027; test_recovery_parity; read-only tester audit
promoted_to: .kiro/specs/inbound-recovery/bugfix.md
---

# Контекст истории терялся после реакции

## Симптом

Тестер обсудил ВДП, затем отреагировал emoji на другую историю и отдельным
сообщением спросил «Можно подробнее?». Бот продолжил старую тему.

## Investigation и root cause

Read-only production подтвердил валидный story ID и сохранённую story_context
из webhook/API. Вопрос пришёл через53.220с, внутри TTL120с. Его `_event_time`
в payload был в миллисекундах, отдельная SQLite-колонка event_time — в секундах:
отношение1000. story_hint строил SQL-окно из ненормализованного аргумента.
На тех же строках raw lookup не находит историю; lookup по секундной колонке
возвращает точную историю. Следующий отдельный вопрос уже закономерно не
получает её, поскольку первый содержательный вопрос потребляет реакцию.

Потеря story ID, отсутствие webhook или истёкший TTL этот живой случай
не объясняют. Старый parity-тест использовал вручную заданные секунды,
поэтому расхождение формата настоящего webhook не воспроизводилось.

## Fix

В story_hint нормализовать before существующей timestamp(); None/nonfinite
возвращают отсутствие hint без подмены текущим временем. Поля payload,
MID, схема, TTL, порядок и одноразовое потребление не изменяются.
Parser пишет story_reaction.received с context_usable и exact ID; recovery
merge пишет story_context.attached с источником и MID hash. Новые логи
не содержат текст, emoji или signed media URL. Реакция сама не отвечает.

## Verification

13 новых cases: настоящий parser webhook-ms → SQLite → restart → следующий
webhook/API-вопрос → business dispatch с точной story; задержки53/119/120/121с,
однократное потребление, duplicate MID, invalid/None/inf/nan, безопасные логи.
До фикса10 FAIL/3 PASS, после13 PASS. Профиль431 PASS/25.80с;
полный1525 PASS/8 прежних warnings/68.84с; Ruff/diff/read-only review PASS.
Внешние HTTP/model/Telegram/Instagram в автотестах заблокированы.

Локальный пакет story-context-fix-20261020, SHA256
`3aa48170c8c9e2132a1864bffab1e7738344bce461b6746f011be7343a7fcdd2`.
Три source и manifest31; fallback — точные установленные версии. Offline
guarded controller proof PASS: inverse, partial install, сохранение новых
receipts/unknown, отказ при постороннем изменении target/env. На сервер
пакет не загружен, backup/apply/restart production не выполнялись.

## Границы

Нет автоматического переигрывания старого ответа или сброса состояния клиента.
Story mention/coauthor по-прежнему молча менеджеру. Generic messaging.reaction
без доказанной истории не связывается с ней по догадке. Получение самого
медиа использует прежний exact story resolver; просроченное/недоступное медиа
этот фикс не восстанавливает. Recovery scope/baseline не меняются.

## Выбор10 минут и выкладка

После первоначальной проверки2мин владелец явно выбрал10мин и деплой.
Оба срока — legacy cache и default story_hint — изменены на600с.20 focused
PASS:25/53/119/120/121/599с сохраняют hint,600/601с истекает; duplicate MID
не продлевает срок. Новые8 FAIL до изменения →20 PASS после. Полный1533
PASS/8 прежних warnings/68.87с, Ruff/diff/read-only review PASS.

Новый пакет story-context-10min-20261020 SHA256
`2473eeb4d2a226e17abf86221e9d322d909deb5a10e2c5e6ebb1eceb8204a8cf`.
Старый2мин пакет помечен HOLD и никогда не выкладывался. Guarded rollback
proof PASS с сохранением новых receipts/unknown. Prepare/apply/verify exit0,
20Oct15:08:23 Минск PID12736→5380,31 SHA/health/installed TTL600 PASS.
.env/credentials/launchers/baseline прежние;292 старых sent receipts,
terminal jobs и tester session/revision сохранены, queues0. Live story
reaction+question после этой выкладки пока не подтверждены пользователем.
