# Instagram: восстановление входящих через Conversations API

Дата: 2026-10-15; обновлено 2026-10-16. Локальная реализация завершена,
2026-10-16 пользователь разрешил текущий деплой «для теста»:
только @_shelter_0, без нового приёмника. Canary-v2 выложен и включён.

## Тестовая выкладка — 2026-10-16

Повторный полный pytest: 1283 PASS/8 прежних warnings, Ruff/diff PASS.
Новый пакет из девяти runtime-файлов; старый HOLD не изменён. Независимый
read-only review состава/guarded rollout блокеров не нашёл. До замены
проверены runtime baseline, username тестового числового ID и пустая его
pending очередь; online backup SQLite integrity_check=ok, env/manifest backup.

Первый запуск flags off: PID15716 ->3012, health ok. Затем изменены только
четыре recovery-настройки: оба flags true, scope=allowlist, один тестовый ID.
Второй запуск PID6600/start 2026-10-16T18:13:18.2801004Z. Все 28 manifest SHA,
launcher/restart/watchdog/ads credentials и остальные env values сохранены.
Local/public health ok. Тестовая пауза снята через защищённый admin endpoint,
остальная сессия (включая историю/лимиты) совпала до/после.

Baseline 1792174400.304584; первая живая сверка тестового диалога gap=false.
Старые сообщения не создали jobs, чужих events/jobs=0. Полный обход Meta ещё
не завершился в момент первой проверки. Новые входящие MID/receipts/manager
не проверены: пользователю предложено отправить новый тестовый текст.
Общий режим не включён; недоступные API-only voice/post остаются ограничением.
Откат: flags off на этой же receipt-aware версии, без восстановления старой БД.

Первый новый живой тест: MID hash `8b01a46d5e49b5ec`, одна задача
hash `d3765ee4d03b438d`. Webhook и API объединены, sources=[api,webhook],
version=1. DeepSeek вернул только пробелы: первые ответы 340/368 символов,
после автоматического повтора через 120 секунд — 455/454. Все finish_reason=stop.
Это реальные provider responses до parser/delivery, не ошибка чтения JSON.
Такие же whitespace-only ответы уже были до canary: 6 из 58 записей журнала;
после canary другой клиент legacy-маршрута получил valid JSON. Доказательств
новой причины в recovery нет. Задача сохранена retry_wait, technical_attempts=2,
последний повтор через 480 секунд; отправок/дублей и ложной паузы пока нет.
Последний повтор сработал 18:25:59/18:26:02 UTC: ещё два пробельных ответа,
311/422 символа. Job завершился failed_final/empty_response. После исчерпания
повторов доставлен один резервный ответ: Instagram state=sent, attempts=1,
receipt MID hash `7779ace093d63283`. Отдельный GET Meta по receipt подтвердил
совпадение ID и точного текста. Ложной manager-паузы нет, foreign jobs=0.
Telegram не отправлялся из-за сохранённого escalation_count=3. Обычный ответ
модели не получен; успешный живой semantic/manager сценарий этим не доказан.
DeepSeek официально предупреждает о возможном empty content в JSON Output:
https://api-docs.deepseek.com/guides/json_mode/ . В recovery текстовый prompt,
model и response_format относительно N28 не менялись, API-only flags у job false.

## Повторная проверка полноты — 2026-10-16

Пользователь отклонил выпуск с неполным media recovery. Готовность прежнего
candidate отозвана, пакет помечен HOLD; release verify/preflight отказывает
для HOLD. Этот пакет остаётся запрещённым; для разрешённого теста собран canary-v2.

Исправлены доказанные расхождения: отдельная API-classification заменена
общим parser; неизвестный template больше не исчезает; телефонные карточки,
story reaction и media reply идут прежними маршрутами; API-фото + webhook
текст/voice объединяются как обычные. Late ignored -> meaningful возвращается
в очередь, но не обходит baseline; meaningful -> GIF/story_context закрывает
задачу без модели. Story hint расходуется один раз, не дробит пакет вопросов,
не прилипает к следующему вопросу после restart. Тот же вопрос при позднем
webhook сохраняет исходную story affinity.

43 новых parity-сценария: raw webhook -> SQLite -> новый store -> обычный
dispatch; API с доступными полями, mixed sources и смена типов. Полный pytest
1283 PASS/8 прежних warnings, реальные HTTP/LLM/sends заблокированы. ADR 0008.
Не объявлять эти mocks доказательством получения отсутствующих API медиа.

Официальные источники нужного Facebook Login/PAGE-token маршрута:
- https://developers.facebook.com/documentation/business-messaging/messenger-platform/conversations.md
- https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks/webhook-events/messages.md
- https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks.md
- https://developers.facebook.com/documentation/business-messaging/messenger-platform/faq.md

Через Context7: webhook содержит исходные media URL; исторические webhook
через API не запрашиваются, отдельного разрешения для проверенных недоступных
voice/post не найдено. Официальная Messenger webhook page указывает повторные
попытки и отключение подписки после часа неуспешной доставки; общее IG правило
36 часов сюда переносить нельзя. Подтверждённого точного CDN TTL нет.

Независимый приёмник/архив обсуждался, но 2026-10-16 пользователь его исключил.
Новые ресурсы не создаются. Используются существующий webhook, SQLite и
Conversations API. Содержимое двух конкретных unsupported voice/post пока
не получено; утверждать общий запрет или точную причину Meta оснований нет.
Ниже ссылки относятся только к ранее обсуждённому, отклонённому варианту.
Источники: https://developers.cloudflare.com/workers/platform/pricing/
https://developers.cloudflare.com/queues/platform/pricing/
https://developers.cloudflare.com/r2/pricing/

## Первый выпуск — завершено локально 2026-10-16

Утверждённый scope allowlist/all применяется на ingress, SQL claims/recover/
cleanup, scanner, pending bridge и финальные send guards. Mixed webhook
сначала фиксирует recovery-часть; legacy остальных клиентов продолжает работу.
В Telegram guard проверяет клиента задачи, а не ID менеджерского чата.
Canary baseline постоянна отдельно от первой общей; расширение scope не
переигрывает переписку остальных за время теста. Scope смена сбрасывает только
scan cursor/completion, не jobs/MID/receipts/cancellations.

Проверенные API shares.data[].link идут в прежний resolver; visual-only mixed
flow не запускает STT. Сохраняются incomplete reasons без изменения JSON.
Mandatory file/product/story mention не теряет приоритет из-за companion audio/
images. Поздний webhook заменяет API-медиа целиком, не оставляет старые URL.
Этим исправлена описанная ниже граница адаптации Reels на момент live probe.

Факт: полный pytest **1240 PASS**, 8 прежних warnings; Ruff src/tests/release
helper и diff-check PASS. Новых сценариев первого выпуска 34, с первоначальными
recovery 70 — 104. Native Windows media tests выполнены вне sandbox без
изменения ExecutionPolicy. В тестах отключены реальные HTTP/LLM/отправки.
При первом полном прогоне выявлена и исправлена изоляция instance monkeypatch:
новые main-тесты используют отдельный экземпляр InstagramChannel. Проверки
обязательных маршрутов/старых URL/ошибочного destination добавлены отдельно.

ADR `.kiro/decisions/0007-inbound-recovery-canary.md`: CLI scan/add/review 6/6/
approve выполнены. Два прежних legacy ADR-link замечания остаются известными;
глобальный checker не обходился и чужие спеки формально не перепривязывались.

Локальный release package: 9 runtime файлов, manifest SHA, disabled.env,
recovery_release.py и ROLLOUT.md; build/preflight/verify PASS. Текущие runtime
файлы сервера прочитаны в закрытую локальную копию с baseline SHA. IGSID
`_shelter_0` проверен через production participants; activation.private.env
валидирован как allowlist из одного ID. ID/токен в логи/Git не выводились.
SQLite online backup helper проверен на WAL fixture; снимок production DB
нужно делать непосредственно перед разрешённой выкладкой, сейчас он не делался.
Rollout/rollback: `.kiro/specs/inbound-recovery/rollout.md`. После активации
откат флагами на новой версии сохраняет unknown и receipts; старая DB не
восстанавливается автоматически. Off admin diagnostics показывают журнал.
Deployment, activation, pause reset, реальные sends/paid calls не выполнялись.

Дополнительный read-only Reels gate: permalink из shares сопоставлен с точной
публикацией через первую страницу IG media, затем повторно проверены ID и
permalink результата. media_type=VIDEO, media_url и caption доступны. Это
подтверждение источника, не доказательство отправки нового recovery-ответа.

## Реализация и evidence 2026-10-16

Постоянный журнал inbound_events/jobs/deliveries/sync в sessions.db, CAS
revision, lease 180 с/heartbeat 15 с. Webhook persist до HTTP 200; storage
failure -> 503. Повторы технической обработки 120/480 с и один semantic
recheck через 120 с сохраняются при перезапусках. Watchdog 60 с; batch 5 с.
Применён принятый ADR `.kiro/decisions/0006-inbound-processing-drafts.md`
(CLI scan/add/review 5/6/approve), в дополнение к основе ADR 0001.

ContextVar изолирует draft одного клиента: никакого внешнего send/notify или
фиктивного assistant при подготовке. Единый reply/manager валидатор остаётся
общим. API-only неполный источник допускает молчание без фиктивного ADS.
Счётчик и история assistant обновляются атомарно с настоящим receipt.
Готовый ответ не вызывает модель заново. Telegram tracked per destination;
частичный успех не рассылается заново успешным адресатам. Sending после
падения/неопределённый transport/200 без MID -> unknown, без слепого replay.

Подтверждённый менеджер постоянно отменяет ожидающие задачи и queue projections;
снятие паузы их не возрождает. Early echo с неоднозначным авторством не
создаёт паузу; только точный подтверждённый MID снимает неоднозначность.
Новая реплика не отменяет старый сохранённый ответ по одной лишь revision.
Legacy pending rows адаптируются без нового LLM; journal-aware legacy bridge
сохраняет receipt даже при выключенном feature flag. Source enrichment
перестраивает того же owner, не сбрасывая бюджет и не дублируя user history.

Scanner: после запуска/каждые 120 с, общий limiter 1 GET/с, request timeout
15 с, tick deadline 90 с, budget 100 requests; cursor и частичный проход
постоянны. Не следуем next URL, токен только в Authorization. Backoff
30/120/300 и Retry-After, usage cooldown при 85%. Обычный scan не вызывает LLM.
Неполная identity/больше 20 details/разрыв timestamp boundary не считается
полной сверкой. Бэклог доставок ограничен отдельно от новых webhook jobs.
Первое включение фиксирует baseline; старые запросы не переигрываются,
исходное время определяет 24-часовое окно автоматического ответа.

70 новых сценариев в `tests/test_inbound_recovery.py` и
`tests/test_recovery_pipeline.py`: SQLite и fake clock, реальные бизнес-ветки
с synthetic model/send/notify, API MockTransport, crash до/после commit/send,
technical/semantic retry, JSON invalid, receipt failure, частичные ответы,
менеджер/сброс паузы, source enrichment, own/early echo, rollback, paging/gap,
backoff, backlog isolation и cleanup. Никаких реальных DeepSeek/Instagram/
Telegram вызовов в тестах. Native decoder требует обычной Windows-среды:
под sandbox был ExecutionPolicy failure, те же 3 теста штатно прошли вне
sandbox без изменения политики. Ранний full run: 1203 PASS/8 прежних warnings;
после него добавлены repeated-crash и legacy unknown/journal-failure cases.
Итоговый полный прогон и независимые Ruff/diff-check фиксируются ниже.

Итог: полный `pytest -q --basetemp=.tmp-recovery-verified-full` — **1206 PASS**,
8 прежних предупреждений (Starlette/httpx deprecation и старые AsyncMock
fixtures), 36.35 с. Отдельно 70 новых сценариев PASS, Ruff src/tests PASS,
`git -c core.safecrlf=false diff --check` PASS. Тесты запускались с временным
TEMP/TMP внутри workspace; сервер/рабочая база не использовались.

KNOWN-RED: legacy-adr-links, 2026-10-16, владелец: сопровождающий проекта.
Дополнительный глобальный `node scripts/decisions.mjs check` отмечает два
уже существовавших пропуска формальных ADR-ссылок в media-understanding/design
и tour-sync/requirements (те же два пункта были в scan до новой записи 0006).
Эта проверка не объявляется зелёной и не отключалась. Связность текущей
inbound-recovery спеки и accepted ADR 0001/0006 подтверждена; несвязанные старые
спеки в этой задаче не переписывались.

До реализации, на фазе возобновлённого планирования, выполнены 4 GET с
production PAGE token: HTTP 200, 3 диалога/10 текстовых сообщений. Изменений
токенов, прав, сессий и production-файлов не было. Это подтверждает чтение
текста, не подтверждает все media. Прежний received log не содержал MID;
для последующего gate добавлено `instagram.inbound.observed` с SHA256(MID)[:16],
без тела сообщения/полного ID. После отдельной выкладки с flags off можно
сопоставить хэш реального webhook с хэшем API ID на тестовом сообщении.

Открыто перед включением: реальные photo/video/audio/share/story samples,
API ID↔webhook MID и receipts на тестовом диалоге; TSK-012/013 не закрыты.
Пакет rollout/production разрешение — отдельно. Текущий production manifest
по-прежнему описывает установленный N28, а не локальный recovery candidate.
Два флага должны оставаться false до gate. Без сверки восстановленная после
простоя задача ждёт свежий контекст вместо ответа поверх возможного менеджера.

Далее — историческое evidence фазы Design, его ограничения не являются
утверждением о текущей локальной реализации.

## Симптом и причина

Бот может потерять запрос после HTTP 200: MID и пятисекундные пакеты находятся
в памяти; пакет удаляется до dispatch, исключение только логируется.
`pending_messages` сохраняет готовые исходящие, а не необработанные входящие.
Молчаливая передача — отдельный результат, а не отсутствие MID.

## Подтверждённая проверка Meta

Транспорт: существующий локальный PAGE-токен, Graph API v25.0, только GET.
Первый прогон: список трёх диалогов; в каждом прочитаны ID сообщений и детали
одного сообщения. Доступны участники, время, отправитель/получатель, в том числе
входящий непустой текст и сообщения от аккаунта компании. Тексты и ID в отчёт
не выводились; чтение не означает ответ клиенту и не меняет сессии бота.

Второй прогон: три текущих диалога с расширенными полями сообщений;
проверено восемь записей, из них шесть с непустым текстом.
Доступен `participants`; принимается field expansion
`messages.limit(3){id,created_time,from,to,message,reply_to,attachments,shares}`.
В одном ответе было четыре записи при запросе `limit(3)`, поэтому ограничивать
потребление следует также на стороне клиента; запрос limit сам по себе не
доказывает верхнюю границу размера ответа.

| Поле Message | Результат |
| --- | --- |
| `attachments` | Запрос принят; фактических вложений в выборке нет |
| `shares` | Запрос принят; фактических share в выборке нет |
| `reply_to` | Принимается в details/field expansion; примера reply нет |
| `story` | Запрос принят; значение не получено |
| `referral` | Ожидаемый отрицательный probe: HTTP 400, Meta 100, nonexisting field |

Успех поля не доказывает восстановление всех типов его содержимого.
Отсутствие `referral` в API-ответе не доказывает, что исходное сообщение не было
откликом на рекламу. Webhook-контекст необходимо сохранять отдельно.

## Дополнительная production-проверка 2026-10-16

Через SSH выполнены GET текущим production PAGE-токеном, без импорта
приложения и изменения данных. Тестовый диалог `_shelter_0` найден среди
50 диалогов; прочитаны 19 сообщений, четыре дополнительно запрошены по ID.
Все запросы завершились HTTP 200. В отчёт выведены только структуры полей,
время и SHA-256 MID (первые 16 символов), без текста и URL вложений.

API ID совпал с полем `mid` существующего webhook-журнала:

| MID hash | Сообщение UTC | Событие журнала |
| --- | --- | --- |
| `50afd46dbc91a2c3` | 2026-10-11 14:37:35 | `instagram.non_text.received` |
| `2a0b1acb9e03acb7` | 2026-10-11 14:37:36 | `instagram.referral.received` |

Список и отдельный Message API не вернули `attachments`, `shares`, `reply_to`
для этих старых образцов. Это подтверждает совпадение MID, но не доступность
медиа: HTTP 200 с отсутствующим полем недостаточно. У пользователя запрошены
новые обычные фото, видео и голосовое для проверки свежих вложений.

## Свежие вложения тестового аккаунта — 2026-10-16

Read-only проверка текущим production PAGE-токеном, Graph v25.0. Пользователь
отправил новые вложения при действующей паузе менеджера. Пауза не менялась;
приложение не импортировалось, рабочие файлы/SQLite не менялись, отправок
клиенту/Telegram и вызовов модели проверяющий процесс не делал.

| MID hash | Время UTC | Фактический результат API |
| --- | --- | --- |
| `a5ac1948285a1be9` | 17:02:33 | Голосовое по подтверждению пользователя: `is_unsupported=true`, без вложения |
| `f5efd80c16241307` | 17:02:40 | Фото: `attachments.data[].image_data.url`; CDN HTTP 206, первые 512 байт JPEG |
| `ecdf8e55b38e8ca8` | 17:02:51 | Webhook `ig_post`: API `is_unsupported=true`, без вложения |
| `e7064f448b4391ea` | 17:03:43 | Webhook `ig_reel`: `shares.data[].link`, HTTPS permalink Instagram `/reel/…` |
| `b5f8e2fe3e531a21` | 17:07:50 | Прямое видео: `video_data.url`, полное чтение 73604 байт, HTTP 200, video/mp4, ftyp/isom, 540×960 |
| `3ccb505306561846` | 17:07:57 | Прямое видео: `video_data.url`, полное чтение 560992 байт, HTTP 200, video/mp4, ftyp/isom, 1570×720 |

Два видео, фото, публикация и Reels сопоставлены с webhook по точному MID.
Видео прочитаны в память с лимитом 25 MiB, запретом редиректов и проверкой
CDN host; файлы не сохранялись. В обоих случаях Content-Length совпал.
Это форматы полученных от Meta файлов; исходные форматы в галерее не установлены.

Для двух unsupported MID отдельно запрошены details с field expansion
`attachments{id,file_url,image_data,video_data},shares{link,name,description,id},story,is_unsupported`
и `/MID/attachments`. HTTP 200, `is_unsupported=true`, edge вернул `data: []`.
Это ограничение конкретных образцов, а не доказательство общего запрета
Conversations API на любые голосовые или публикации.

Фото и прямые видео соответствуют ожидаемой схеме локального нормализатора.
У Reels на момент первого probe найдена локальная граница: API возвращает `shares[].link`,
а прежний нормализатор только помечал shares как неполный контекст и ещё не
передаёт permalink в прежний shared-media resolver. Доступность полного Reels
по этой ссылке и маршрут восстановления требуют отдельной проверки/исправления.
Объявлять полный media gate пройденным нельзя.

## Границы доказательства

- Production-токен проверен непосредственно на сервере; сравнение с локальным
  токеном для этого доказательства не требуется.
- API ID и webhook MID сопоставлены на двух событиях тестового аккаунта.
- Свежие фото и два прямых видео доступны через API; скачивание проверено.
- У конкретных голосового и публикации API не раскрыла содержимое. Reels
  permalink теперь проходит локальный resolver flow; точная VIDEO identity
  и доступность media_url/подписи подтверждены дополнительным read-only GET.
  Story/ad samples и own receipts/manager gate остаются непроверенными.
  TSK-012 остаётся открытой; обещание полного восстановления после простоя
  по этим данным не подтверждается.
- Не было вызовов DeepSeek/Telegram, отправки клиентам, обновления токенов,
  прав, рекламных кампаний, клиентских сессий или перезапуска бота.

## Проектируемое исправление

Единый постоянный журнал входящих и явные результаты обработки; webhook
сохраняет событие до HTTP 200. API-сверка находит неизвестные сообщения после
запуска/простоя. Периодический worker подхватывает технические ошибки и один
пересмотр модельной молчаливой передачи. Готовые исходящие и подтверждённые
части повторно не генерируются. Неопределённая отправка требует проверки.

По официальной документации API перечисляет старые ID, но детали доступны
только для двадцати последних сообщений. Превышение этой границы — явный
разрыв данных, а не успешное восстановление. При первом включении нужна
начальная временная граница; бот не отвечает всей старой переписке.

Источники:
- https://developers.facebook.com/documentation/business-messaging/messenger-platform/conversations.md
- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/conversations-api

Спека: `.kiro/specs/inbound-recovery/requirements.md`.

## Утверждение Design и изменение интервалов

2026-10-15 пользователь утвердил Design, увеличив в четыре раза только
времена строки «Проверка обработки»: watchdog 15 → 60 с, технические повторы
30/120 → 120/480 с. API-сверка и semantic recheck остаются 120 с; heartbeat
15 с, lease 180 с, API timeout/backoff не меняются. Это параметры будущей
реализации; production не включался.
