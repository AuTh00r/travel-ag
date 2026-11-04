---
status: verified
date: 2026-10-29
scope: N38 diagnostics on Windows; offline tests and production startup/writer checks
evidence: tests/test_diagnostic_trace.py; tests/test_diagnostic_pipeline.py; .kiro/decisions/0018-private-processing-trace.md
promoted_to: .kiro/specs/media-understanding/n38-diagnostics.md
---

# Диагностика: от входа модели до подтверждения доставки

## Симптом и причина

Одного журнала ответов и хеша каталога недостаточно: он не объясняет, какая
история/справка/инструкция поступила на конкретной попытке, что изменил reviewer
и на каком этапе остановилась доставка. Подтверждение API также не доказывает,
что receipt уже записан в SQLite.

## Проверенное решение

Отдельный закрытый JSONL trace с явными полями, ContextVars и существующими
request/parent/job/task/delivery/pending IDs. Вход фиксируется непосредственно
перед каждой primary/review/format-retry попыткой; ответ, решение, финальный
текст, API-результат и сохранение receipt связаны этими ID. Диагностический
журнал не управляет очередью и не запускает дополнительную генерацию.

## Находки проверки

- Обычная очистка словаря не закрывала секреты/base64 внутри JSON-строк и
  подписанную ссылку внутри redirect. Очистка проверяет декодированное
  представление без исправления исходного ответа; непрозрачное чувствительное
  содержимое исключается целиком. Бинарные aliases едины для объектов и строк.
- Стандартная ротация считает символы. Для UTF-8/кириллицы trace проверяет байты;
  файл20MiB,7архивов, запись512KiB; усечение явно отмечено.
- Ветка Instagram без MID должна записывать durable unknown после существующего
  перехода состояния; простого provider_result недостаточно.
- Первые многочисленные send-related FAIL оказались утечкой нового mock на
  экземпляре через teardown. Исправлено патчем класса в тесте; изменение
  бизнес-отправки для исправления тестового загрязнения не требовалось.

## Verification

Final full pytest:1639PASS,8прежнихпредупреждений,81.72s. Ruff и diffcheck PASS.
Профильные проверки включают byte limits/rotation, disabled/no-file, сбои
redactor/encoder/sink, неприкосновенность входов, корреляцию retry/review,
разные клиенты, provider acceptance с последующим DB failure, partial/unknown
и менеджерскую паузу. Независимое read-only review выполнено.

## Границы

Исходная реализация проверена локально без production/платного API; отдельно
разрешённая выкладка описана ниже. Ручных платных проверок N38 не было.
ОС применяет0600 только где это поддерживается; Windows наследует ACL logs.
Журнал содержит текст переписки и ограничен объёмом, а не сроком хранения.
Неизвестную произвольную строку нельзя гарантированно распознать как секрет.
Непроверенные webhook-тела, SDK objects, HTTP headers и медиа-байты не дампятся.
DEEPSEEK_RESPONSE_LOG_ENABLED=false выключает оба диагностических журнала.
Шаблонные docs_check.py/skills_validate.mjs в этом репозитории отсутствуют;
это не заявляется как выполненная проверка. Спеки и runtime проверены diffcheck.

## Авторизованная выкладка

29Oct явный «деплой»: combined N37/N38 source-only package6cc07643,14files,
34runtime SHA. Onlinebackup SQLite integrity PASS, нормальный restart,
local/publichealthok;974старыхreceipts/1659старыхclient sessions сохранены.
Env/credentials/recoveryallowlist/baselines прежние. Новая схема проверена.
Trace writer:deployment_verified+21inbound_event, sink/startup error markers0.
Полная свежая модельная цепочка пока не наблюдалась, ручных API/sends0.

Release review выявило TOCTOU между read-only rollback guard и заменой кода:
старый runtime не понимает N37 edit. Поэтому автоматический inverse допускается
лишь до нового запуска при совпадении старого PID/start; после restart_requested
или verified старый код online не возвращается. База и unknown не откатываются.
Старый restart audit также ошибочно считал дочерние GigaAM-процессы посторонними:
потомки учитываются только от listener, siblings его предков остаются запрещены.
