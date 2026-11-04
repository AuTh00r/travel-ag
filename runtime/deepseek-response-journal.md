# DeepSeek: отдельный журнал полученных ответов

Дата:2026-10-15. N25+N26 выложены и проверены на сервере.

## Причина

Ошибку invalid_fields 22:51 невозможно объяснить точнее по N24:605символов,
finish_reason=stop, но исходный JSON и его ключи намеренно не записывались.
Владелец явно попросил логировать ответы DeepSeek. Старые ответы не восстановлены.

## Реализация

Единственный ainvoke completion в main.py пишет полученное content до
manager/validation gates в logs/deepseek-responses.jsonl. UTC-время, UUID попытки
обработки, номер вызова, SHA-псевдоним клиента, настроенная модель/маршрут,
allowlisted finish/token counts и причина валидации. UUID общий у N25 retry.
Пустые/пробельные строки сохраняются. Нет prompt, request/history, медиа-блоков,
произвольных metadata или raw provider exception. Нестроковое content — только тип.

Известные непустые configured secrets любой длины маскируются; поддержаны
Bearer/Basic, API-key/X-API-Key, credential-поля с quoted values, data URLs,
подписанные/CDN media URLs и Telegram bot-token URLs. Редактирование предшествует
ограничению64тыс.символов; есть признаки обрезки/пропуска. При сбое redactor
содержимое пропускается. Неизвестные произвольные строки нельзя гарантированно
распознать как секрет; текст ответов остаётся персональными данными на сервере.

Отдельный непропагирующий logger, UTF-8 JSONL и RotatingFileHandler5MiB+7архивов,
примерно40MiB. Это объём, не7дней. Новые файлы0600 где ОС поддерживает;
на Windows наследуются ACL серверного каталога logs. Каталог уже gitignored.
DEEPSEEK_RESPONSE_LOG_ENABLED=false отключает журнал, default=true по запросу
владельца. Обычный bot.log получает UUID/метаданные без body.

## Проверка границ и исправления ревью

Стандартный logging.handleError может вывести failed record.msg в stderr даже
при внешнем try/except. Специальный handler переопределяет handleError без вывода
record/exception; все ошибки дают фиксированный llm.response_log.failed и не
меняют отправку/передачу/историю. Проверены init/redactor/formatter/emit/rotation.
Тесты перенаправляют журнал в tmp_path и закрывают handler после каждого случая.

Первичные6integration regressions были RED до кода. После реализации исправлен
неверный ordinary image fixture (реальный путь prepare_images должен быть mock).
Privacy review нашло короткие configured secrets и дополнительные credential
формы;6отдельных regressions подтвердили пробелы RED, затем117targetedPASS,
включая27новыхcases. Повторное read-only ревью clear. Финальный полный прогон:
1036PASS/8прежнихпредупреждений/38.72s; Ruff/diff/micro-spec checksPASS.

Факт решения: .kiro/decisions/0003-deepseek-response-journal.md, создано CLI,
review5/6, accepted. Никаких paid model trials, replay, production data writes,
реальных клиентских/менеджерских сообщений или серверных перезапусков.

## Авторизованная выкладка N25+N26

Владелец явно сказал «деплой это». Baseline N24/22runtimeSHA/env/launcher/newmodule
absent подтверждён до замены. Установлены только main/config/new journal helper,
манифест23записи. Backup двух прежних sources и manifest проверен; откат сначала
валидирует все файлы и удаляет только ожидаемый новый модуль по SHA. Изолированная
проверка bad-backup подтверждает отсутствие частичного отката. Replacement atomic;
неопределённый restart не вызывает слепую повторную установку/автооткат.

Staged и installed proof:18старых+11дополнительныхcases и boundary/dedupPASS.
AI/сессии/уведомления/отправки подменены, HTTP запрещён, synthetic journal только
в bundle. Preflight cp1251/ConsoleRenderer failure воспроизведён безопасным stack
trace и исправлен переводом proof logging в отключённый stdlib logger; приложение
не менялось ради теста. Helper read-only review после исправлений clear.

Apply stdoutapplied=true/SSHexit1 на restart. Независимый verifyexit0 подтвердил
23SHA/env/launcher/ads-token preservation, PID17644->17148/start20:52:43Z
(23:52:43Минск), local/publichealth200ok; повторная установка/откат не выполнялись.
Локальный canonical manifest синхронизирован ровно3entries. Safe report:
n26-applied.json. После рестарта response_recorded=0/journal_failed=0/empty_retry=0,
production journal ещё не создан: он появится при первом полученном ответе.
Реальный DeepSeek/клиентский replay вручную не вызывались. Старые605символов из
ошибки22:51 не восстановлены. Inbound-recovery остаётся на паузе.

## Проверка настоящего API 2026-10-16

По запросу владельца «проверяй теперь с логами ... на живых вызовах» сначала
прочитаны production журналы. На 00:42 Минск после N26 было 3 ответа (2 vision,
1 text), 0 ADS JSON; ошибок парсинга JSONL и response_log.failed нет. Это ещё не
проверка JSON на реальных рекламных сообщениях клиентов.

В 00:50:25–00:50:47 выполнены пять изолированных диагностических сценариев на
настоящем API с установленными промптом, фабриками моделей, чистым FAQ и актуальным
snapshot-каталогом. Четыре текстовых сценария: программа ВДП, «Эльбрус», неясный
отклик, синтетическая передача телефона; один vision — ранее использованное
собственное изображение истории. Text deepseek-v4-flash, vision deepseek-flash.
Тот же серверный валидатор извлечён через AST без импорта приложения.

Сбой воспроизведён на первой попытке phone_handoff: content состоит ровно из
311 ASCII-пробелов (код32), strip length0, finish_reason=stop, input17977 /
output480 токенов. Request ID bc2ed4aa492e4c9481b141b65d125190. Повтор с неизменным
prompt/input17977 вернул корректные decision/reply/context, decision=answer;
служебный блок остался внутри reply. Всего 6 реальных ответов:5valid+1empty_response;
после одного повтора все5сценариев завершились valid. invalid_fields, invalid_json
и finish_reason=length в этой малой выборке не встречались. Не выводить из неё
частоту ошибок на всём трафике и не приписывать ей восстановление старого JSON22:51.

Результаты хранятся отдельно: приватный bundle json-live-check-20261016,
controlled-live.jsonl. Официальный журнал не смешивался с диагностикой. Вся сеть
ограничена асинхронным HTTPS POST только к api.deepseek.com; синхронный HTTP
запрещён. Нет Instagram/Telegram/session импортов, клиентских отправок или
уведомлений, main импорт исключён из-за глобального configure_logging. Секреты
в сохранённом content маскируются; наружу выводятся только метаданные и allowlist
полей. Повторный запуск блокируется существующим report, чтобы не повторять
платные вызовы при неопределённом исходе SSH. После проверки24runtimeSHA и health
подтвердили сохранение рабочего приложения. Код/настройки/сессии не менялись.

## N27: восстановление неверных полей (готово, не выложено)

По запросу владельца после статуса незакрытого invalid_fields добавлен один
корректирующий повтор для ошибок JSON/прикладной схемы. Общий бюджет с пустым
ответом остаётся2вызова. Системное сообщение копируется и дополняется доверенным
контрактом; исходный ошибочный ответ в prompt не передаётся, медиа/последний user
сохраняются. length/oversize/non-string/provider_error остаются терминальными.

29новых регрессий,146targeted/1071fullPASS/8existingwarnings/31.07s; Ruff/diff/
micro-spec и read-only review clear. См. ADR0004 (CLI5/6 accepted). Приватный
bundle json-format-recovery-20261016: три реальных исправляющих API-вызова valid
после ЯВНО синтетических первых ошибок invalid_fields/invalid_field_type/
inconsistent_handoff. Это проверка восстановления, не воспроизведение старого
ответа. SSH оборвался после первой строки stdout, отдельное чтение доказало3/3
сохранённых результата; платный запуск не повторяли. Client/TG/session I/O нет.

Rollback/helper proof, повторный verify, stale-temp/bad-backup guards и независимый
reviewPASS. Server prepare24baselineSHA/backup/FAQ-retiredPASS. Замена main/prompts
и restart НЕ выполнены: автоматическая проверка одобрения отклонила action,
поскольку разработка и живые проверки не означали явного согласия на этот новый
деплой. Обход не предпринимался; требуется явное одобрение. Deployed manifest
пока сохранён исходным, N27d открыт. Inbound-recovery остаётся на паузе.

## N27: естественная ошибка и полный обработчик, 2026-10-16

Владелец: «воспроизведи», затем явно «Да, до 12 вызовов DeepSeek».
Первоначальный32-case/48HTTP запуск отклонён automatic approval до исполнения;
объём уменьшен до6синтетических текстовых сценариев, без клиентских историй/медиа.
Отдельный полный staged process_with_ai:4сценария/6реальных HTTP, стоп после
естественного invalid_fields. Вопрос о разговоре с менеджером по Эльбрусу:
DeepSeek вернул завершённый JSON с decision/reply без context (stop,1198символов).
Форматный повтор в том же обработчике получил настоящий valid3-string-fields
ответ, без изменения первого content и без его включения в новый prompt.
Request0694c2f98c6a4c23b92cab47662293e6. Это подтверждает класс ошибки и recovery;
какое поле отсутствовало в недоступных исторических ответах — неизвестно.

Ещё388ASCIIspaces -> valid на штатном unchanged-prompt повторе. Все6wire/AIMessage
SHA совпали, оригинальная пара сверена локально.108127input/5438output tokens.
Initial-prompt AST равен production без нового неиспользуемого retry-helper.
Session/send/Telegram/queue перехвачены, SQLite и прочая сеть запрещены;
logging отключён до import main, lifespan не вызывался, -B/dont_write_bytecode
включены.24runtimeSHA/PID15500/localhealth после прогона прежние.0реальных
клиентских/менеджерских отправок и записей сессий. Новый деплой не разрешён и
не выполнялся. Evidence: приватный json-natural-repro-20261016 с probe.py,
captured-pair.json,verified-proof.json,evidence.md. Не экстраполировать частоту
ошибок из этой намеренно выбранной малой выборки.
