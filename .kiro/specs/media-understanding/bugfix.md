# Quick bugfix: раннее эхо ответа включает паузу (2026-10-10)

Current: собственный ответ о вложении попал в историю как сообщение менеджера без служебного тега, затем был записан обычным обработчиком с тегом. manager.detected 09:33:57.498Z предшествует message.sent 09:33:57.920Z; INSTAGRAM_APP_ID не настроен. ID отправки известен только после завершения HTTP-запроса, а webhook приходит раньше.

Expected: при незавершённой отправке точное совпадение получателя и фактически отправляемого текста распознаётся как собственное эхо. Его MID сохраняется в существующем ограниченном кеше. Любой другой текст/получатель и последующее сообщение с тем же текстом, но новым MID, остаются сообщениями менеджера. Запись незавершённой отправки очищается при успехе, ошибке и отмене. Сопоставляется уже обрезанный текст, который уходит в API.

Unchanged: подпись webhook, известные MID/app_id, реальный manager takeover, распознавание голосовых, история и лимит эскалаций. Без общего временного игнорирования сообщений менеджера. Выкладка в рамках ранее разрешённого включения голосовых, с проверенным резервированием одного файла; только разрешённое снятие паузы тестового аккаунта через административный API.

Design: локальный для экземпляра канала счётчик отправок по (recipient, text), зарегистрированный непосредственно перед сетевым ожиданием и удаляемый в finally. Общий helper ограниченного MID-кеша применяется к раннему webhook и API-ответу. Нет новых зависимостей и настроек.

Acceptance: воспроизвести раннее эхо внутри mock HTTP post без app_id; собственное эхо не создаёт manager event, повтор по MID игнорируется; другой клиент/текст и новое совпадающее сообщение после завершения не подавляются; обрезанный текст, параллельные одинаковые отправки, ошибка и отмена проверены. Полный pytest/Ruff/diff-check, server source hash/health. Затем только pause reset, история/счётчик без изменений.

Tasks: [x] red reproduction (5 failed before fix); [x] минимальный фикс/регрессии (5 PASS, known чужой app_id сохраняет manager event); [x] QA/backup/deploy/health (714 PASS/Ruff/diff-check, read-only review clear, 20 production SHA/launcher/env preserved, listener7116→14396/local+publichealth); [x] только test pause reset (admin API, единственное изменённое поле manager_last_at, история и escalation_count3 сохранены); [x] свежий live voice (14:16:27Z batch, 14:16:40Z answer, recognized voice marker, вопрос о Сербии, manager_last_at=null).

Факт: runtime/instagram-early-echo-takeover.md. Автоматическая проверка отклонила прямой overwrite локального manifest; обе версии прочитаны/сравнены: ровно20 записей, единственное изменение — разрешённый src/channels/instagram.py; локальная резервная копия SHA проверена, изменены только два поля этой записи. Остальные локальные изменения сохранены.

## Quick bugfix N7: неподтверждённая передача менеджеру (до кода)

Current: count3 сохраняется после reset takeover. Лимит запрещает новый Telegram send, но ответ модели про Сербию содержал «Я передал ваш контакт». Phone-only ветка проверяет результат, остальные ответы не проверяются. Промпт одновременно запрещает новый marker при лимите и требует передачу в шаблоне «нет туров»/подвале. Telegram _send считает один HTTP200 достаточным, а частичная успешная доставка считается общим сбоем.

Expected: модель отвечает по существу без подтверждения передачи; подтверждение формируется кодом только по факту уведомления. WHEN Telegram подтвердил хотя бы один configured manager chat ответом HTTP200+JSON ok=true THEN подтвердить передачу и увеличить счётчик ровно один раз; сбой остальных получателей логировать как partial. WHEN все попытки не подтверждены THEN честно сказать «Не удалось подтвердить передачу нового обращения менеджеру» (таймаут не доказывает отсутствие доставки). WHEN лимит3 исключает отправку THEN явно сообщить «Новое уведомление менеджеру не отправлено: достигнут лимит повторных обращений». WHEN модель обещает передачу без marker/контакта и попытки не было THEN убрать неподтверждённое утверждение, без выдуманной причины/автоэскалации. Содержательный ответ/ссылки/контактная строка сохраняются. Все current LLM и голосовой/non-text fallback пути учитывают статус.

Unchanged: лимит3 и reset720hours, история прошлых сообщений, счётчик/пауза теста и остальных клиентов; один AI запрос; краткий Telegram context450; media/STT/manager takeover. Нет ручных сообщений клиентам/менеджерам, новых paid trial запросов или сбросов. Исправление и deployment разрешены текущим «исправь» в контексте уже выложенного бота.

Design/Tasks: см. N7 в requirements/design/tasks; первичные источники API: https://core.telegram.org/bots/api#making-requests (ok=true — успешный request). Проверки до кода: противоречивый prompt и false claim no marker/count3 подтверждены code/live metadata. Red regression → fix → full QA/read-only review → guarded3-file rollout/backup/source/env/launcher/health, server mocked smoke без внешних отправок.

Status: complete, deployed. Факт:38handoff+2voice regressions, full754PASS/8existingwarnings/Ruff/diff-check/read-only review; three runtime files/backup-v2/21SHA/env/launcher verified, listener14396→2416, local/publichealthok; deployed mocked proof4outcomes+2receipts+partial PASS. Ни одного ручного клиентского/менеджерского сообщения, paid trial вызова или production DB reset. См. runtime/telegram-handoff-receipt.md.

## Quick N8: silent mentions, ad context, cooperation (2026-10-11, до кода)

Current: приглашение стать соавтором Reels получает общий ответ об unreadable attachment; story mention ранее направлялся в media/AI. Ответ на рекламное объявление не содержит понятного источника, бот спрашивает направление. Предложение сотрудничества ошибочно обрабатывается как отвлечение от туров, с неуместным хвостом «с радостью подскажу». Evidence: три предоставленных screenshot; точные webhook discriminators/referral availability проверяются отдельно, не выводятся из внешнего вида карточки.

Expected: распознанные collaboration invitations и story mention молча вызывают существующее уведомление менеджера, без DeepSeek/vision/ответа именно на это событие. Обычные story replies и shared Reels сохраняют обработку. Доступный точный рекламный источник/контекст из webhook проходит в existing media+question pipeline; при недоступности не угадывать по screenshot/похожему посту. Сотрудничество — уважительное отдельное намерение для передачи менеджеру, без отказа «только туры», оборванных фраз и неподтверждённых обещаний. Совместить новые пути с fixed5s collector, MID, guards/takeover, limit3, honest Telegram receipts, brief manager context.

Unchanged: лимиты/история клиентов не сбрасываются, голосовые/GigaAM/direct images/video/carousels/story reply pipeline не упрощается. Root интегрирует, три субагента исследуют независимо/read-only по прямой просьбе владельца. Без установок, новых paid trial запросов и ручных сообщений людям. Реальные поля collaboration/ad должны быть доказаны; неизвестный discriminator остаётся явно открытым, не выдаётся за реализованный.

Plan: N8a classification/silent handler; N8b exact ad source; N8c cooperation prompt/output. До реализации дописать requirements/design/tasks по результатам трёх проверок; meaningful red→green, full QA/read-only review и guarded rollout в рамках существующей авторизации deployment.

Status: known routes deployed, coauthor classifier pending. Факт:791PASS/Ruff/diff-check/3read-only reviews; backup/21SHA/env/launcher/listener2416→11352/local+publichealth/deployed mocked proof PASS. Unsupported_type unchanged по явному «Нет, только доказанное приглашение соавтора». Exact ad full video access not proven. Test BATCH_CLIENT Telegram incident disclosed; network isolation fixed and verified. См. runtime/instagram-business-context.md.

## Quick N9 correction (2026-10-11, до кода)

Current: владелец уточнил, что третий пункт касается «туров. с радостью подскажу.»: неуместный хвост и строчная буква, не политика сотрудничества. N8 cooperation exception был ошибочной интерпретацией root. Read-only transforms сохраняют эту фразу, сами не меняют регистр.
Expected: восстановить прежние action/security/escalation правила из SHA-verified N7 backup и убрать N8 cooperation media instruction; добавить единое правило связной речи, заглавной буквы и отсутствия бессодержательного хвоста. Ads/mentions/N7 receipt unchanged. Не строить regex formatter для произвольного текста/URL.
Boundaries: prompts/tests/docs и existing spec/runtime/manifest. QA prompt across media/limit variants, receipt regressions и существующие checks; guarded single-file rollout/backups/health/deployed mocked proof. Без live paid model calls/data resets/новых permissions. Формулировка модели после prompt fix остаётся вероятностной.

N9 fact:794PASS/8existingwarnings/Ruff/diff-check/review;1prompt file deployed with backup/21SHA/env/launcher/PID11352→8928/local+publichealth/deployed mocked proof. N7 policy equality verified against pinned backup; BASE only adds style. No real messages/paid AI/DB resets.

## Micro N25: empty ADS JSON recovery (2026-10-15, before code)

Current: a successful provider request returning whitespace is rejected as
empty_response and immediately escalated; tests explicitly enforce one call.
Expected: exactly one additional call for an empty/whitespace string, then normal
answer/handoff or the existing technical fallback. Unchanged: strict schema,
non-empty invalid/truncated/error fallback, silent policy, notification limits,
manager priority, current phone, history integrity and non-ad routes. Root cause
and verified log evidence: runtime/instagram-ad-empty-json.md. Owner authorizes
the previously described retry fix; no production mutation or live paid probe.

Status: locally complete.31newcases/90targeted/1009fullpytestPASS,8pre-existing
warnings,Ruff/diff/micro-spec check and read-only review clear. No deployment.
# Незавершённый tool response — 2026-10-18

Микро-исследование и исправление, одобрено «+»; до кода. В 19:14 Minsk
две настоящие попытки deepseek-v4-flash вернули аргументы, заканчивающиеся
`"manager": `, при finish_reason=tool_calls и 277/231 токенах (лимит 2048).
Журнал не обрезал содержимое. Текущая проверка безопасно отвергает оба ответа,
но повтор того же контракта не исправил сбой. Причина генерации требует
сверки официальных ограничений strict schema; не объявлять её доказанной
по одному симптому и не достраивать manager=null самостоятельно.

Ожидание: воспроизвести фактический обрыв через реальный SDK с mock HTTP,
сохранить исходные аргументы/строгую проверку и существующий предел двух
вызовов. Изменение схемы допустимо только по подтверждённому ограничению
документации, с адаптацией к прежнему reply/manager и регрессиями всех маршрутов.
Если API не гарантирует корректную генерацию, явно зафиксировать предел;
не выдавать offline-проверку за живое устранение сбоя провайдера.
Без paid calls, отправок клиентам, production и ослабления валидатора.

Уточнение до реализации: документация DeepSeek поддерживает anyOf и требует
текущие beta/strict параметры (https://api-docs.deepseek.com/guides/tool_calls/).
Nullable schema ранее дала 13 успешных strict ответов; менять её без evidence
нельзя. Локальный hardening: отдельный incomplete_tool_arguments только для
JSONDecodeError на конце ограниченной строки аргументов; исходник остаётся
в журнале, для исполнения ответ непригоден. Один прежний retry получает
доверенное напоминание заново вернуть оба значения и закрыть объект, без
достраивания/подстановки manager и без копирования частичного ответа в prompt.
Два повторных обрыва сохраняют прежний честный fallback. Offline регрессии
SDK→handler проверяют именно EOF после manager; улучшение поведения модели
вживую этой проверкой не доказано.
