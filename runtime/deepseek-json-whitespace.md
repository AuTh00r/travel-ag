# DeepSeek: JSON Output возвращает пробелы

Дата: 2026-10-16. Статус: воспроизведено, исправление runtime не выполнялось.

## Симптом и границы

Обычный текст тестового Instagram-клиента прошёл webhook/API dedup и создал
одну recovery-задачу. Все шесть production-ответов модели (первый проход
и повторы через 120/480 секунд, по два вызова в проходе) состояли только
из ASCII-пробелов. finish_reason=stop, не length; валидатор видел пустой
trimmed content. После исчерпания повторов один резервный ответ доставлен
с подтверждённым Meta receipt. Это не потеря текста при отправке/парсинге.

Пользователь отдельно разрешил сброс только Telegram-лимита тестового аккаунта:
escalation_count 3 -> 0. История, pause и остальные state-поля совпали до/после;
запись выполнена в одной транзакции с revision guard, приватная копия сохранена.
Перезапуска и возрождения failed/cancelled задач не было.

## Проверка гипотез

Пользователь разрешил до восьми платных вызовов с каталогом и только историей
своего тестового аккаунта. Выполнено ровно восемь, без SDK retries, отправок
Instagram/Telegram, lifespan и записи рабочей SQLite. Диагностика в отдельном
процессе; logging отключён, SQLite mode=ro. Каждый начатый запрос записан до
сетевого вызова, существующий report запрещает слепой перезапуск.

Baseline реконструирован из предтестовой session, исходной job и текущего
snapshot-каталога. Зафиксированы исходная job по hash, время приветствия и
проверка finish_reason=length как в production. Это не сохранённый оригинальный
HTTP request; byte-identical исходному не объявляется. Количество input tokens
baseline совпало с production: 18758. Структура: system 48489 символов,
user 9, assistant 11, текущий вопрос 25 символов. JSON-правила и примеры в body есть.

| Вариант относительно baseline | Результат прямого HTTP content |
| --- | --- |
| Baseline и два его повтора | Только пробелы, 399/378/353 символа |
| Только thinking disabled | Только 354 пробела; reasoning отсутствует |
| Тот же JSON-контракт в начале system | Только 374 пробела |
| Assistant history обёрнута в reply/manager JSON | Только 423 пробела |
| Только escalation_count=0 | Только 259 пробелов |
| Убран только response_format=json_object | Связный русский текст 1086 символов, JSON-контракт не выполнен |

Все восемь finish_reason=stop. Семь из семи constrained-ответов пробельные,
ноль из восьми прошли прикладной JSON-валидатор. Запрошенный model alias
deepseek-v4-flash, возвращённый model deepseek-flash. Суммарно 150612 prompt
и 4453 completion tokens. Runtime 28 SHA совпали до/после. Приватные inputs,
responses и диагностический скрипт сохранены отдельно от Git; секретов в отчёте нет.

## Вывод и ограничения

Сбой локализован в сочетании этого контекста и принудительного JSON Output:
изменение только API-ограничения вернуло содержательный текст. Размышление,
место контракта, plain assistant history и лимит 3 не объясняют его по отдельности.
Точный фрагмент/сочетание контекста и внутренний механизм DeepSeek этим прогоном
не установлены. Нельзя объявлять, что весь JSON Output всегда неисправен.
Просто отключить response_format в production недостаточно: модель вернула
текст, который существующий единый контракт закономерно отвергнет.

Немедленный retry для empty_response пересылает неизменный запрос; на таком
воспроизводимом входе шесть попыток не устранили сбой. Новый способ формирования
или исправления ответа требует отдельного проверенного изменения, без принятия
произвольного текста за reply/manager. Платный бюджет этой проверки исчерпан.

Официальная документация предупреждает о возможном empty content в JSON Output:
https://api-docs.deepseek.com/guides/json_mode/ . Параметр thinking по текущей
документации включён по умолчанию, но его явное отключение не исправило этот случай:
https://api-docs.deepseek.com/api/create-chat-completion/ .

## После обновления DeepSeek — 2026-10-18

Владелец сообщил об обновлении вчера. Официальный changelog подтвердил выпуск
DeepSeek-V4.1-Flash-1017 2026-10-17; deepseek-flash и legacy deepseek-v4-flash
обслуживаются новой моделью. В changelog не заявлено исправление JSON whitespace:
https://api-docs.deepseek.com/updates/ .

Read-only просмотр текущего production подтвердил28SHA/health. В журнале
2026-10-18 остаются empty_response: текстовая пара 10:50:23/10:50:31 UTC
(13:50 по Минску),656/651символ,finish=stop. Значит, обновление не устранило
все такие случаи. Отдельного вывода о первоначальном тестовом входе это не даёт.

По «работай» подготовлен N29 tool-calling spike: scripts/tool_call_probe.py,
34 offline-проверки, полный 1317 PASS/8 старых warnings, Ruff/diff. Бесплатный
server preflight: 0 external calls, 6 planned, 28 runtime verified. План начинается
со старого JSON-запроса для контроля после обновления, затем обычный tool
дважды, strict beta, manager и silent (strict для последних только при его успехе).
Готовая функция только создаёт reply/manager; реально ничего не исполняется.
Предыдущий paid budget 8 исчерпан. Новый до 6 запрошен отдельно и разрешён
пользователем. Результат ниже; основной runtime/settings/SQLite не менялись.

### N29: шесть новых реальных вызовов — 2026-10-18

| Сценарий | Результат |
| --- | --- |
| Тот же JSON control после обновления | HTTP200,388ASCIIпробелов,finish=stop,empty_response |
| Ordinary tool, проблемный вопрос | Один prepare_response,reply916символов,manager=null |
| Ordinary tool, повтор | Один prepare_response,reply1144символа,manager=null |
| Strict beta tool, тот же вопрос | Один prepare_response,reply908символов,manager=null |
| Strict beta, просьба менеджера | Один prepare_response,reply802символа,manager заполнен |
| Strict beta, недоступная реклама | Один prepare_response,reply пустой,manager заполнен |

Все пять tool-ответов прошли прежний duplicate-aware _validate_response на
исходной function.arguments и semantic checks для reply/manager/silent.
finish_reason=tool_calls, message.content пустой как ожидается. Это нормальный
tool-ответ, а не ошибка empty_response. Nullable anyOf schema фактически принята
strict beta. Tool result никогда не исполнялся и не считался delivery receipt.

Все6started/6completed сохранены; 110482prompt/2249completion tokens.
28SHA runtime и .env совпали с preflight; health ok. Внешних отправок клиентам
или менеджерам, записей рабочей SQLite, перезапуска/деплоя и установок нет.
Приватные plan/responses/proof сохранены вне Git. Последний offline regression:
1317PASS/8existingwarnings,34новыхпроверки,Ruff/diffPASS. Независимый read-only
review протокола проведён; найденный diagnostic envelope bug воспроизведён
и исправлен до платного запуска. Бюджет нового эксперимента полностью исчерпан.

Вывод: на реконструированном проблемном входе tool calling даёт валидный
результат, когда JSON Output возвращает пробелы. Это проверенная возможность
текстового транспорта, но не полная миграция: реальная интеграция обработчика,
vision/voice/mixed, журналирование raw tool arguments и новая tool-history
ещё не реализованы/не проверены. Малую выборку5успехов не выдавать за гарантию.
## Ten additional authorized checks — 2026-10-18

Owner authorized «10 проверок» after six-call spike. Exactly10 additional strict
beta/forced prepare_response calls, thinking.disabled, current prompt/catalog,
same strict argument validator; no automatic retries or real deliveries.
All10HTTP200,10/10valid original arguments, no whitespace. Two reproductions of
problem context answered normally. Own photo220€ and own video10 original frames
(Warsaw-Dresden-Prague) recognized.9/10 semantic review: escalation-limit case
omitted explicit no-new-notification warning, although handler finalizer already
owns actual notification status. Direct API does not prove full handler/delivery.

Initial automatic report8/10 used an incorrect VDP expectation (Berlin/Poznan);
manual review found correct Dresden/Prague response. Predicate corrected with
regression test; original report preserved and separate reviewed proof records9/10.
New phone scenario tests model intent only, not code extraction of latest phone.
184198prompt/3104completion tokens;1.64–3.28s, mean2.37s. Production28SHA/env
unchanged, localhealthok, zero client/manager sends. Private raw/report/proof outside
Git; no deployment inferred.46initial/47final targeted tests, full1329PASS with
8existingwarnings (outside sandbox; three native decoder failures sandbox-only).
