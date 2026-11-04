---
status: verified
date: 2026-10-20
scope: recovery deadline; Windows Python 3.12; deployed to existing allowlist
evidence: TSK-026; test_early_timer_keeps_timeout_ownership; isolated Windows runs
promoted_to: .kiro/specs/inbound-recovery/bugfix.md
---

# Ложная ошибка общего deadline на Windows

## Симптом

За19–20 октября в production90 `inbound.reconcile.failed` с reason=deadline_timeout
на list_conversations. Ещё18 сбоев имели отдельные сетевые/HTTP причины.
Диалог тестера оставался свежим, gap=false; очередь доставки пуста.
Нельзя объявлять90 событий90 потерянными заявками или приписывать каждое
историческое событие одной причине без дополнительных метаданных.

## Проверка и причина

В двух местах код ловил TimeoutError от `asyncio.wait_for`, затем считал
deadline штатным только при `time.monotonic() >= deadline`. Windows Python3.12.10
использует monotonic с resolution15.625мс; callback может отработать до
повторного показания deadline. Собственный таймер ошибочно становился
ранней ошибкой провайдера и увеличивал backoff.

В отдельном процессе на той же машине30 коротких wait_for дали22 ранних
монотонных показания; действующий reconcile_tick с in-memory Store/Graph
дал21 ложную ошибку/backoff из30. Cursor сохранился. Ни одной операции Graph,
модели, доставки или рабочей БД в этих измерениях не было.

Официальный контракт допускает ранний callback на одно разрешение часов:
[Python3.12 event loop](https://docs.python.org/3.12/library/asyncio-eventloop.html#asyncio.loop.call_later).

## Исправление

В scanner и самостоятельном sync_dialog используется собственный
`asyncio.timeout` и его `expired()`; чтение часов остаётся дополнительной
проверкой позднего внутреннего исключения. Ранний внутренний TimeoutError
остаётся реальным отказом, внешняя CancelledError распространяется.
Не добавляется произвольный временной допуск или увеличение таймаутов.
См. [контракт Timeout.expired](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.Timeout.expired).

## Verification

- Детерминированные9 случаев: собственный ранний timer, внутренний timeout,
  внешняя отмена × scanner/priority/refresh. До фикса3 FAIL/6 PASS, после9 PASS.
- Проверены сохранение unread cursor/checkpoint, отмена зависшего await,
  освобождение lock и ContextVar. Профиль108 PASS; полный1512 PASS/8 прежних
  warnings/69.83с; Ruff/diff/read-only review PASS.
- Точный локальный candidate в памяти отдельного серверного процесса:
  scanner30 и refresh30, ложных сбоев/backoff0; cursor сохранён60/60,
  зависшие await отменены60/60. Установленная версия не заменялась.

## Границы

Это дефект классификации своего таймера, не исправление HTTP500 или
настоящих transport_timeout Meta. Интервалы, бюджет запросов, scope,
receipts/unknown и схема БД не менялись. Runtime manifest по-прежнему
описывает установленную версию. Нельзя считать устранёнными все исторические
90 событий только по совпадению диагностической сигнатуры.

## Выкладка по отдельному разрешению

Владелец ответил «+» после готового локального исправления.20Oct14:32:34 Минск
заменён один source и runtime manifest31; PID12960→12736. Prepare/backup,
apply и итоговый verify PASS; .env/credentials/launchers/baseline прежние,
scope allowlist/1. Рабочая БД не заменялась. Все280 старых sent receipts,
terminal jobs и tester session/revision сохранились; queues0.

Два checkpoint1792496018.7132478→1792496139.5653467 (120.852с), оба gap=false,
scan_failures0. В логах после startup до14:35:53 Минск нет warning/error.
Это короткое окно проверки, не доказательство отсутствия будущих сетевых сбоев.
Артефакты пакета и rollback описаны в rollout.md, TSK-026 закрыта по факту.
