# DeepSeek: единый prepare_response transport

Дата:2026-10-18. Статус: tool transport включён для всех (N32).
Решение: .kiro/decisions/0009-model-tool-transport.md; source spec media-understanding N30.

## Симптом и причина

JSON Output возвращал пробелы на реконструированном контексте тестера. N29
показал работоспособность forced tool, включая фото и десять original кадров.
При интеграции выяснено: установленный langchain_openai разбирает arguments
обычным JSON parser, теряет duplicate keys и не сохраняет raw tool_calls.
Часть неверных типов нормализуется или вызывает исключение до нашего валидатора.

## Решение

Одна strict beta функция prepare_response с reply и nullable manager, thinking
disabled, max_tokens2048, SDK retries0. `_ResponseModel` удаляет tool_calls из
копии перед SDK conversion и сохраняет исходное message в raw_tool_message.
Extractor проверяет одно правильное имя/id/type, finish tool_calls и отсутствие
обычного content; исходные arguments проверяет прежний strict validator.
Parsed SDK tool_calls не используются, обычный content JSON не fallback.
Конфликтующий content/неверный tool конверт сохраняется в ограниченный redacted
журнал; обычный аргументный JSON сохраняется как исходная строка.

max_tokens передаётся через extra_body, чтобы SDK не переименовал его в
max_completion_tokens. Старый текстовый N29 действительно доказал принятие
последнего API, но vision проверял max_tokens; единообразно оставлено
документированное поле. Это не доказательство неподдержки max_completion_tokens.

## Проверка

17 SDK converter/MockTransport tests +12 realSDK→full handler/recovery tests.
Фото/10frames сохраняют original и порядок, voice transcript использует тот же
путь. Проверены duplicate retry, contact phone source, cap и finalizer, silentADS,
manager takeover, готовый ответ/частичные receipts и unknown после restart.
Recovery имеет одну генерацию и повторяет только неполученную подтверждённо часть;
неопределённый результат не переотправляется. Raw tool message не сохраняется
в клиентскую историю или план доставки.

Финально1359pytestPASS/8существующихwarnings, Ruff и diffPASS. Native decoder
в sandbox даёт3decode_failed; тот же полный pytest вне sandbox1359PASS.
Независимое read-only review не нашло блокеров. Общий decisions check имел
до начала N30 несвязанную tour-sync requirements заметку: вне изменения;
связь собственного design с ADR0009 добавлена. Журнал через штатный CLI.

## Границы

Новые проверки offline: HTTP MockTransport, внешние отправки заблокированы,
SQLite изолирован fixtures. Новых платных запросов, изменений сервера, деплоя,
новых зависимостей, миграции истории/БД нет на этапе N30. Остальные клиенты
остаются на прежнем JSON transport до согласования расширения. Не считать offline tests новой
статистикой надёжности провайдера или гарантией правильности всех текстов.

## N31: canary rollout и живой тест

Владелец запросил деплой только тестеру. Добавлен независимый numeric allowlist
DEEPSEEK_TOOL_CLIENT_IDS (default empty/off), отдельный от inbound recovery.
Решение фиксируется на весь запрос/retry. Legacy prompt/AD rules и обеfactory
скопированы с установленного baseline; для остальных клиентов прежний JSON
transport сохранён.12prompt+retry golden cases и2factory payload на сервере
сравнивались с backup без сети. Inherited env/launcher overrides отсутствуют.

1375testsPASS/8existingwarnings, Ruff/diff/reviewPASS. Три inverse rollout tests
доказывают сохранение новых receipts/unknown в SQLite после установки и отката,
отказ перезаписывать посторонние правки и восстановление half-install.
Установлено5sourcefiles+1envkey после Meta identity @_shelter_0 и backup всех
изменений+SQLite. Штатный RestartTravelBot,PID7688→8668,localhealthok,
adsready,recoveryenabledкакраньше,model_toolsallowlist1.28SHA/остальные env и
protected launchers/credentials подтверждены; manifest синхронизирован.
Publichealth с PC:Cloudflare403,не подтверждает внешнюю доступность endpoint.

После нового сообщения владельца:12:57:19UTC,1attempt,finish tool_calls,valid,
1087chars. Одна answered/done job,2IGчасти,обеsent+receipt+attempt1,0новых ошибок
в просмотренном хвосте bot.log. Тестовая паузаfalse/счётчик0 прочитаны, не сброшены.
Ручных дополнительных paid calls/отправок нет. Приватные deployment/installed/live
proof в staging; старые чужие задачи и общие границы не переигрывались.

## N32: глобальное включение

Владелец «давай для всех деплой» явно расширил scope. DEEPSEEK_TOOL_SCOPE
allowlist/all (defaultallowlist) независим от inbound recovery; all включает
подготовленный strict prepare_response для новых и прежних клиентов. Numeric
allowlist сохранён для отката. Healthall не выдумывает общее число клиентов.
ADR0011,1379testsPASS/8existingwarnings,Ruff/diff/read-onlyreviewPASS.
All→canary inverse rollback сохраняет новые receipt/unknown записи SQLite.

3изменённых source в5filepackage,exact code/env/manifest/SQLite backups;
проверено отсутствие override в наследуемом окружении/launchers. Добавлен только
DEEPSEEK_TOOL_SCOPE=all,остальные env/recovery/credentials/паузы/лимиты сохранены.
RestartTravelBot,8668→7228,start13:36:18UTC18Oct2026,healthok/scopeall,
all28SHAverified/manifest synced. Installed offline proof: вне старого allowlist
клиенты получаютtools, обеfactorystrictBeta/thinkingdisabled/SDKretries0,
0networkcalls. Recovery по-прежнемуallowlist1,не расширялся этим действием.
В просмотренных postrestart logs0newerrors,новыхmodelrecordsпока0. Ручныхpaid
прогонов/сообщений не было; не объявлять отсутствиеошибок гарантией всехответов.
