# Requirements: media-understanding

## Quick N42: SDK response и общий таймаут (2026-11-03)

Исправить инцидент af52511ba23341be85157893cceff601: HTTP503, затем
AttributeError на model_dump и ранний failed_final после двух вызовов.
Точный исторический тип ответа неизвестен; воспроизведение не доказывает его.

- N42.1: принимать dict/ChatCompletion; неожиданный тип/choices отклонять
  отдельной повторяемой ошибкой провайдера. Логировать безопасный тип, причину
  и длительность без тела/repr. Произвольный AttributeError не повторять.
- N42.2: внешний общий deadline каждой primary-попытки120/120/240с помимо
  сетевого timeout; отменять ожидающий вызов до повторного. Внешняя отмена
  не повторяется. Сохранить persisted budget максимум3 между перезапусками,
  manager takeover, независимую доставку и unknown-защиту.
- N42.3: failed_final после исчерпания либо неповторяемой ошибки;
  старые terminal-задачи автоматически не оживлять.
- N42.4: техническая карточка: понятная причина, запрос клиента, отсутствие
  автоответа и действие менеджера; ниже краткая диагностика попыток/ID.
  Обычные бизнес-уведомления не меняются.

Проверки: настоящий SDK с MockTransport (503/не-JSON/успех), общий таймаут
и отмена, durable budget/перезапуск, финальная доставка и перехват.
Только локальная реализация; без платных вызовов, деплоя, ручных отправок
и изменения production-заявки.

Статус04Nov: локально готово,1809pytestPASS/8прежних warnings,
Ruff/diff PASS. SDK MockTransport воспроизводит503→str→успех без сети;
HTTP body закрывается при deadline до retry. Read-only review выполнено.
Исходный job проверен на сервере только на чтение: failed_final/2попытки,
4Telegram sent; manager_last_at отсутствует (ответ менеджера не подтверждён).
Деплой/переочередь/отправка клиенту не выполнялись.

## Quick N41: silent unsupported_type (2026-10-31)

Owner explicitly changes N8.2: every webhook attachment of type unsupported_type
must silently notify a manager, without claiming it is a collaboration invitation.
Preserve adjacent messages and the existing manager takeover, quota and recovery
rules; no client reply for this event. The exact type takes precedence over ADS;
other advertising replies retain their existing text-only routing.
Verify classification, manager context, batching, and absence of client sends.
Local implementation only; deployment requires separate authorization.

Recheck: preserve a confirmed API attachment type unsupported_type through
normalization, so API/webhook paths use the same silent route with or without
companion text. Do not infer this exact type from generic is_unsupported or a
missing API attachment. Verify recovery delivery and no semantic/model recheck.
Optional username lookup failure must not suppress the manager notification;
use the numeric client ID while retaining the manager takeover gate.

31Oct owner separately authorized N41 deployment: three runtime files
(main.py, channels/instagram.py, services/inbound_recovery.py), source/SQLite
backup, normal restart and read-only postflight. Preserve env, receipts,
session states and test-only recovery scope; no manual paid calls/test sends.

Deployment verified31Oct20:32Minsk:3files/35manifest entries, PID428,
local/public health and SQLite schema/integrity PASS.1707existing sessionstates
and1108receipts retained; env/credentials/baselines/test-only recovery unchanged.
Fresh errors/warnings/tracebacks0; no manual model calls or external test sends.

## Quick N40: молчаливые технические ошибки и ограниченные повторы (2026-10-31)

Intent: убрать технические заглушки из Instagram; после окончательного сбоя
передавать менеджеру запрос и безопасную диагностику. Реализация локальная;
деплой, платные испытания и изменение production-состояния не разрешены.

- N40.1: при ошибке модели/обработчика клиент не получает технический текст,
  подтверждение передачи или выдуманный ответ. Менеджеру готовится уведомление.
- N40.2: три попытки модели ВСЕГО. Повторяются транспортные timeout/connect,
  HTTP408/409/429/5xx, пустой/неполный/невалидный ответ. Таймауты120/120/240с;
  SDK-повторы выключены. Ошибки доступа/настроек и локальные ошибки не повторяются.
- N40.3: каждая попытка фиксирует request_id, номер, таймаут, этап, тип ошибки,
  HTTP-статус или причину валидации. Итоговая карточка содержит краткую безопасную
  выдержку всех попыток и ID для поиска полного приватного журнала. Без секретов,
  сырого исключения/HTTP-body, медиа и полного промпта. Диагностика ограничена.
- N40.4: исчерпанная серия не запускается заново recovery; доставка уведомления
  повторяется отдельно без новой генерации. Подтверждённые/unknown отправки не
  дублируются. Техническое уведомление не теряется из-за бизнес-лимита3эскалации.
- N40.5: менеджерский перехват/отмена прерывают серию и отменяют устаревшую работу.
  Технический финал recovery тоже молчаливый. Сохраняются история пользователя,
  receipts, область recovery только тестового аккаунта и обязательные маршруты.

Boundaries: main.py, llm.py, журналы, telegram_notify.py, inbound_recovery.py,
профильные тесты и текущая спека. Правила туров/виз, семантический reviewer,
распознавание/недоступность исходных медиа и интервалы сверки не меняются.
Проверки используют заглушки модели и внешних отправок; полныйpytest/Ruff/diff.

Результат локальной проверки:1674PASS/8прежних warnings/98.84s,
Ruff и diff PASS, независимое read-only ревью без блокеров. SDK MockTransport
подтвердил фактические120/120/240с и классификацию HTTP. Первый полный запуск
с повышенными правами не смог использовать стандартную папку pytest Temp;
повтор с отдельной временной папкой прошёл. Production не изменялся, платных
API-вызовов и внешних отправок не было. См. tasks N40 и ADR0019.

Выкладка разрешена отдельным «деплой» владельца (2026-10-31): весь пакетN40
из10runtime-файлов, проверка установленного baseline, резервная копия исходников
и SQLite, штатный перезапуск и postflight. Env/паузы/история/лимиты/receipts/
unknown и тестовая область recovery сохраняются. Никаких ручных платных вызовов
или тестовых сообщений клиентам/менеджерам. Миграции только добавочные.

Deployment result31Oct:10файловN40 установлены, manifest35entries совпадает.
PID15300 ->19360/start09:58:38.3318731Z (12:58Минск). Local/public healthok,
SQLite integrity/schema PASS. Все1706прежних session states и1104receipts
сохранены; env/credentials/baselines/allowlist не менялись, каталог8туров
с прежнимSHA82aa7b12…; в свежих журналах ошибок/warnings/tracebacks0.
Public GET требует браузерного User-Agent из-за существующей фильтрации
Cloudflare; правила доступа не менялись. Ручных API-вызовов модели/отправок0.


## Quick N38: полная диагностическая цепочка (2026-10-29, до кода)

Intent: user explicitly requests logging the rest of processing, including model
answers, to investigate causes beyond catalog contents. Extend the existing
private response journal with a separate correlated diagnostic trace. This local
implementation request authorizes no paid calls, deployment or production state
changes. Existing response records remain readable.

Initial local completion:1639pytest PASS with8preexisting
warnings (81.72s), Ruff/diff PASS. New privacy/pipeline regressions and independent
read-only audit completed; encoded JSON/media and nested signed-URL bypasses
closed. No paid model calls, external sends, production writes or deployment.
Accepted ADR: .kiro/decisions/0018-private-processing-trace.md.
Operational contents/limits: n38-diagnostics.md.

Deployment authorized by the owner's subsequent explicit «деплой» (2026-10-29):
install the combined14runtime-file N37/N38 delta, consistent source/SQLite backup,
normal restart and postflight. No recovery-scope expansion, history/counter reset,
manual paid evaluation or dependency installation. Preserve env/credentials.
Code-only rollback must refuse if new manager tasks/outbox are still active:
schema compatibility alone does not make old delivery semantics compatible.

Deployment result (2026-10-29): combined14files installed; runtime manifest34
entries match. Restarted PID3836 ->11164/start19:20:39.3579123Z. Local/public
healthok, schema/integrity PASS;974previous receipts and1659previous client
sessions retained. Env/credentials/recovery allowlist/baselines unchanged.
Trace writer confirmed (deployment marker plus21inbound records); no fresh
startup/log-sink errors. No manual paid calls or client/manager test sends.
Natural model/review/delivery chain after deployment not yet observed.

Acceptance:
- N38.1: capture the normalized incoming event and the actual messages supplied
  on every primary/format-retry/review attempt: system rules, catalog, FAQ, history,
  question, candidate/open tasks and relevant model/tool options. Record before
  invoking the provider so a hang/failure is visible; do not alter these inputs.
- N38.2: preserve sanitized received raw response/arguments, validation/finish/
  usage, model and application decisions, final client text, notification plan
  and delivery outcomes. Distinguish provider acceptance from durable receipt;
  unknown/retry/blocked/cancelled are not successful sends.
- N38.3: correlate by execution trace, hashed client/source MID, existing request/
  parent/job/task/revision/delivery/pending IDs. No diagnostic SQLite migration,
  queue state, retry budget, scope or business decision changes.
- N38.4: text/history is authorized diagnostic content. Remove credentials and
  credential-shaped fields, signed/media URLs and binary/base64 content before
  serialization/truncation. Media retains only type/label/length/hash metadata.
  Never dump HTTP headers/cookies, settings, arbitrary objects or rejected raw
  webhooks. Existing normalized data is the inbound diagnostic boundary.
- N38.5: full content stays out of ordinary bot logs. The private trace rotates
  at20MiB with7backups; each encoded record is bounded at512KiB with explicit
  omission/truncation metadata. Existing deepseek_response_log_enabled disables
  both journals with no file creation. Journal errors cannot affect processing.
- N38.6: verify input immutability, safe serialization/redaction, encoded-byte
  bounds/rotation, sink failure isolation, primary/review/retry correlation,
  final-vs-draft text, pause/skip, partial/edit/unknown and receipt failure paths.
  All external model/delivery effects use stubs; full pytest/Ruff/diff required.

## Quick N37: проверка и обновление эскалаций (2026-10-29, до кода)

Status: implementation authorized by «+» after the three-part proposal. Quick
Spec extends N36; its prohibition on additional verification calls is superseded
only for this approved feature. Production deployment and new paid evaluations
are not authorized by this implementation step.

Initial local verification:1594pytest PASS/8preexisting warnings, Ruff/diff PASS.
The21anonymized cases validate routing with stub model decisions; semantic model
accuracy and real Telegram edits are not claimed. The standalone evaluator and
source-only rollout/rollback notes are prepared in n37-release.md. Subsequent live
evaluation/corrections below update this initial state. No production changes.
Accepted ADR: .kiro/decisions/0017-reviewed-manager-tasks.md.

Live evaluation authorization (2026-10-29): user explicitly approved up to19paid
DeepSeek calls for21synthetic cases (2mandatory contact bypasses). Read the fresh
production catalog only; no real client histories, IG/TG sends, DB changes or
deployment. The budget includes any attempt with an unknown result; never replay
that attempt automatically. Record actual consumption and semantic limitations.

Live findings:19/19valid envelopes,17/19expected actions. See n37-review-bugfix.md
for two wrong cancellations and three context errors. The unchanged acceptance
criteria require preserving unsupported explicit date conditions, distinguishing
catalog departures from a client's selected date and retaining the precise task.
Review must preserve shared primary business/link/closing rules. Correct these
locally; the19-call budget is exhausted and cannot fund another request.

Corrections verified locally:1597pytest PASS/8preexisting warnings, Ruff/diff and
independent composition review PASS. Subsequent explicit «Да, до9вызовов» authorized
the targeted repeat on the same captured catalog/synthetic data:9calls used,
9valid responses/9expected actions; manual review confirmed the five task defects
resolved, canonical program links and closing preserved. Total28calls used (19+9).
No IG/TG sends, production DB writes or deployment. This is reviewer verification,
not a live end-to-end delivery test or a repeat of all21cases on the final prompt.

Intent: prevent consultation handoffs when the bot already answered or can clarify
the tour itself; preserve genuine manager tasks. Updates to an existing question
must update its confirmed Telegram messages instead of consuming a new escalation.
Record the catalog actually supplied to the model, not merely the saved snapshot.

Acceptance:
- N37.1: ordinary clarification/answered alternatives use manager=null. A valid
  consultation candidate receives at most one bounded independent semantic review;
  a failure preserves the valid original candidate and is logged safely.
- N37.2: the primary prepare_response reply/manager contract is unchanged. Internal
  review metadata explicitly distinguishes cancel/new/update; update may reference
  only a current, open, nonexpired task belonging to this client. The reviewed
  visible reply must agree with the final handoff decision.
- N37.3: current contacts, feedback, technical fallbacks and mandatory story mention,
  collaborator invitations, files/products and voice failures retain their routes.
  Explicit manager requests and genuinely missing facts remain valid grounds.
- N37.4: confirmed manager tasks and per-chat delivery receipts survive restart.
  Date/tour/contact-time clarification updates the same question without increasing
  its limit; a new independent question creates a new task. Updates remain possible
  when the limit for new tasks is reached. A manager takeover permanently closes
  prior tasks; removing the pause does not reopen them.
- N37.5: Telegram updates target only saved confirmed message IDs for that client
  and chat. Partial delivery, repeated work, concurrent updates and unknown results
  cannot produce blind duplicate sends or overwrite a newer version. No network
  calls occur while a SQLite transaction is open. Recovery captures drafts and
  receipts with the existing scope and takeover guarantees.
- N37.6: each model response records primary/review phase and catalog hash, length,
  tour names and actual availability lines from the exact supplied catalog text.
  No credentials, URLs, raw prompts or additional client history are logged.
- N37.7: offline regressions cover all 21 historical decisions with anonymized
  inputs, both processing routes, reviewer failures, updates/limits, partial/unknown
  delivery and manager takeover. Full pytest, Ruff and diff checks must pass.
  Stubs validate implementation, not the model's semantic accuracy; live checks
  require an explicit bounded budget before any paid calls.

## Micro N36: обоснование вызова менеджера (2026-10-26, до кода)

Status: approved implementation by «+» after the concrete proposal; subsequently
«+» authorizes up to6paid calls on the prepared synthetic cases, followed by an
explicit separate «+» for2targeted repeats after the context wording refinement.
Evaluation used no sends, working DB changes or deployment. Local implementation complete:
1506PASS/8preexisting warnings/70.33s, Ruff/diff PASS;6live decision checks and
2targeted final-prompt repeats completed. Subsequent explicit «деплой»26Oct
authorized installation: deployed and verified, process start19:36:36Minsk,
31installedSHA/local+publichealth/8tours PASS. Env/client state/recovery scope
preserved. Source: current manager
reply for a visa-alternatives request was useful but also escalated without an
unresolved question. Exact internal model reason is not observable in that record.

Intent: if the current request is fully answered by the confirmed catalog,
manager=null. No visa, an unsuitable original tour or offering suitable alternatives
alone do not justify a consultation escalation. Remove the vague trigger
«запрос сложный». For consultation, manager.context states the specific unresolved
question/action needed, then short relevant context; preserve the450-character cap.
Company-service facts are checked by the manager, not by asking the customer;
clarifying personal wishes/date/tour with the customer remains permitted.

Boundaries: src/ai/prompts.py, approved prompt golden fixtures and a synthetic
semantic evaluation matrix. Keep reply/manager and context/type/name unchanged;
no classifier, new fields, additional model calls per client, handler suppression,
keyword filter or session migration. Explicit manager request, current phone,
complaint, actual missing information, booking assistance and mandatory attachment
routes retain priority even if some information was answered. Production rollout
replaced only prompts.py and its manifest entry, after separate authorization.

Acceptance: align overlapping no-tour/booking/limit instructions so a supported
alternative does not count as «нет подходящих туров». Paired synthetic examples
cover resolved visa alternatives/known information versus missing information,
explicit manager request, contact and complaint. Existing delivery/phone/attachment
regressions, full pytest, Ruff and diff pass. Golden inputs stay unchanged when
approved prompt hashes are refreshed. Stub tests do not prove model semantics;
actual semantic claims require an explicitly authorized bounded live evaluation.

## Micro N35: отклик на рекламу — только текст (2026-10-22, до кода)

Status: deployed and verified 2026-10-22 20:16 Minsk. Owner explicitly replaces previous ad analysis:
«когда клиент откликается на РЕКЛАМУ, игнорируем ее (не анализируем,
не передаем в контекст), обрабатываем сугубо текст».

### N35 Intent

ADS referral does not cause media retrieval, vision, title/ID/link/context
injection, ad-specific fallback or silent escalation. Process the actual client
text as an ordinary message, using the normal catalog/history/guards/manager
contract. An empty referral is ignored without AI, reply or notification.

### N35 Boundaries

Apply to webhook, Meta reconciliation and already persisted/imported events at
the processing boundary. Keep batching5s and independent normal photos, videos,
voice, posts/Reels, story replies and mandatory non-ad handoffs unchanged.
Do not erase DB/history/receipts, change permissions/recovery scope, deploy or
make paid model calls. Old ad-resolution utilities may remain independently
testable, but runtime ADS processing must never call them.

### N35 Acceptance

N35.1 remove ad metadata/media before grouping/dispatch when possible and enforce
text-only again for old queued events/direct process_with_ai calls. Preserve MID,
sender/timestamp and actual typed text for dedup/recovery; never manufacture a
question for an empty referral. No ad placeholder/title/URL in model input,
history or manager summary, and no ad-only silent mode for available text.
N35.2 a referral-only event cannot trigger an escalation, synthetic reply, story
hint, image/STT preparation or DeepSeek. Adjacent ordinary text remains batchable;
independent media retain the normal route. Existing mandatory proven story mention/
coauthor events keep their policy.
N35.3 old recovery tasks get the new text-only policy, no ADS-only allow_silent,
normal delivery receipts/retry/cancellation behavior. Unsupported media attached
to an ADS event does not by itself require a manager.
N35.4 meaningful new/updated tests replace superseded ad-analysis expectations,
mock model/network/sends, full pytest, Ruff/diff and read-only review.
N35.5 known legacy automatic ad annotations are removed only from the user-history
projection passed to the model. Original stored history and ordinary business
conversation remain intact. API/webhook enrichment of one MID cannot restore
ad media; an independently sent customer attachment with another MID remains.

Evidence:32 new policy cases PASS; full pytest1496PASS/8 preexisting warnings/
60.12s; Ruff/diff/micro validation PASS and read-only review clear.98 obsolete
parameter cases/40functions asserting superseded ad-analysis/silent policy were
replaced; JSON retry/privacy/phone/delivery and pure media guards retained.
See runtime/ad-text-only-routing.md and accepted ADR0015. Exactly4source paths
changed relative to installed manifest; no server/model/message operations.

N35 deployment authorization: owner confirmed View ad/source=ADS scope and said
«деплой». Ship only channel/main/inbound/recovery plus runtime manifest after
fresh baseline, isolated candidate and code-only rollback proof. Preserve env,
credentials, launchers, allowlist1, first-enable baselines, live DB/history/limits/
receipts/unknown. Fresh backup is for recovery, never restored by code rollback.
No manual customer messages or paid model trials. Verify31hashes/newPID/health
and state preservation after restart; do not expand recovery to all clients.

N35 deployment fact: installed4sources+manifest,PID11436→15408,
start17:16:18Z/20:16:18 Minsk. Server isolated72PASS/external HTTP denied; exact
rollback proof PASS; all31SHA/local+publichealth verified. env/credentials/
launchers/allowlist1/first-enable baselines preserved. All407prior sent receipts
retained (408current), terminal jobs/session revisions preserved, no active/
pending/unknown. Installed synthetic parser proves ADS text→user, empty→ignored,
ordinary photo preserved. No initial post-restart warnings/errors. No manual
messages or paid model calls; code-only rollback never restores the DB.

## Micro N34: медиа рекламы с настройкой мест показа (2026-10-20, до кода)

Status: deployed and verified 2026-10-20 20:06 Minsk. Owner: «исправь» blanket
asset_feed_spec rejection. Evidence: 29 new regressions, full pytest 1562 passed /
8 preexisting warnings / 63.84s, Ruff/diff/micro-spec validation pass, independent
read-only review clear. Isolated candidate against actual Graph resolves all four
supplied active ads with proven original media; server sources/config unchanged.
See runtime/meta-placement-media.md and accepted ADR0014.
### N34 Intent

Recover proven Instagram material of accessible PLACEMENT creatives rather
than rejecting every nonempty feed. Live read-only proof: all four supplied active
ads return exact creative Instagram ID/permalink, two VIDEO and two IMAGE with
validated CDN URLs. This does not identify which placement variant the client saw.
Second live candidate probe exposed a missing context field: direct GET creative
omits instagram_permalink_url for all four, while the same creative expanded from
its ad returns it. N34 also requests the proven expanded fields on the ad node;
an ID-only reference can retain the old direct-creative fallback. Never infer a
permalink or combine conflicting creative snapshots to manufacture identity.

### N34 Boundaries

ad_media.py, story_media.py, main.py, focused tests and this existing
spec. No ad-ID guessing, arbitrary first asset, new permissions, paid model calls,
deployment or recovery scope changes. Original video remains ten frames,
original detail, no audio; existing combined limits and takeover remain.

### N34 Acceptance

N34.1 accept dictionary asset_feed_spec with optimization_type=PLACEMENT
only after existing ad/account/creative/Instagram ID/permalink/CDN checks; return
canonical Instagram material with marketing_variant provenance, never exact-click
provenance. Other nonempty/malformed feeds use an explicit unavailable reason and
may fall through to a supplied clicked image, never to arbitrary assets.
N34.2 retain clicked image alongside canonical media when supplied, clearly label
both and prefer actual clicked content over differing canonical variant details.
Unavailable clicked image does not discard proven canonical material; URL/size/
format/identity guards remain terminal. Combined limits still apply to both.
N34.3 variant provenance survives shared/ad/mixed paths and is never overwritten
by a later exact source; prompt and stored history never claim exact shown
variant. No-feed exact route remains unchanged. One model request per batch.
N34.4 mocked image/video/unknown feed/guard/fallback/manager takeover regressions,
full pytest, Ruff and diff checks; no live customer sends or paid model calls.

N34 deployment authorization: owner explicitly says «деплой» after verified fix.
Replace only ad_media.py/story_media.py/main.py and runtime manifest, preserving
all other baseline entries, env/credentials/launchers and recovery allowlist1.
Fresh backup and code-only guarded rollback retain live SQLite/receipts/unknown.
Run exact controller rollback proof and isolated staged mocked tests before apply;
verify new PID, all31 hashes, health, baselines and receipt preservation afterward.

N34 deployment fact: three source files plus manifest installed; PID5380→11436,
start17:06:34Z/20:06:34 Minsk. Server isolated60PASS and rollback proof PASS;
all31SHA/local+publichealth verified, env/credentials/launchers unchanged,
recovery scope allowlist1/baselines preserved. All296sent receipts retained;
terminal jobs/session revisions preserved, active/pending/unknown0. Installed
resolver read four actual ads as VIDEO/VIDEO/IMAGE/IMAGE with marketing_variant.
No post-restart warnings/errors in the first54s checked. No manual messages or
paid model calls. Backup and code-only rollback prepared; DB never restored.

## Уточнение S7 для recovery — 2026-10-20, до кода

Реакция на историю должна логироваться и дополнять ближайший plain вопрос
по прежнему S7, в том числе при миллисекундном timestamp webhook и после
перезапуска. Самостоятельный ответ на emoji не добавляется; TTL600с и
одноразовое потребление сохраняются. Исправление находится в inbound-recovery
TSK-027/bugfix.md, без новых таблиц и изменения story mention policy.
Статус: версия10мин выложена20Oct15:08 Минск;1533 pytest PASS/Ruff/diff/review
PASS,31 SHA/health/TTL600 проверены. Scope recovery allowlist/1 сохранён.

## Micro N33: незавершённые аргументы функции — 2026-10-18

Статус: локально готово; 7 EOF/SDK/handler регрессий и private journal case,
1480 PASS/8 прежних warnings; Ruff/diff/review PASS. По отдельному «деплой»
выложено в совместном пакете4: PID4136/29 SHA/health и installed EOF smoke PASS.
Tool scope остаётся all; живая эффективность напоминания не проверялась.

Одобрено «+», до кода см. bugfix.md. Полученный provider EOF после manager
диагностировать как incomplete_tool_arguments, не подставляя недостающее
значение. Сохранить исходник в прежнем приватном журнале с прежними redaction,
limits и валидацией. Один из прежних двух вызовов получает доверенное указание
сформировать полный объект заново; недоверенный частичный ответ в prompt не идёт.
Два отказа дают прежний fallback; не выдавать неполный reply. Schema, transport,
max_tokens и платный бюджет не менять. Offline SDK/handler/journal регрессии,
полный pytest/Ruff/review/diff; улучшение генерации провайдера живьём не доказано.

## Quick N32: tool transport для всех — 2026-10-18, до кода

Статус: deployed scopeall.1379testsPASS/8existingwarnings,Ruff/diff/reviewPASS.
PID8668→7228/start2026-10-18T13:36:18.3387989Z;healthok/model_tools.scopeall,
28installedSHA проверены,manifest synced. Меняется только новый envscopekey;
allowlist/recovery/прочие env/protected сохранены. Installed scope/factories
проверены без сети: новые клиенты вне прежнего списка получают tools.
0новыхошибок в просмотренных postrestart logs; новых model records пока0.
Ручных paid calls/сообщений/сбросов0; live статистика N31 остаётся прежней.

Владелец «давай для всех деплой» разрешил расширение после успешного N31.
Добавить независимый DEEPSEEK_TOOL_SCOPE=allowlist|all (default allowlist),
в all включать единственный prepare_response для всех клиентских запросов
text/vision/voice-transcript, не меняя inbound recovery scope, паузы, лимиты,
истории, текущую очередь/receipts/unknown. Старые готовые ответы не переигрывать.
Прежний allowlist сохраняется как быстрый откат. Health явно сообщает all.
Проверить config invalid/default/all и разные IDs, обе lane/retries/realSDK,
полный pytest/Ruff/diff, read-only review; разрешены install+штатный restart.
Exact backup и inverse rollback без восстановления старой БД; проверка нового
PID/health/28SHA/env и installed factory/scope без ручных paid calls/сообщений.

## Quick N31: tool canary и деплой — 2026-10-18, до кода

Статус: deployed только @_shelter_0. Identity Meta проверен;1375pytestPASS,
Ruff/diff/reviewPASS;28installedSHA проверены.5source replacements+одна новая
allowlist настройка, остальные env/recovery/protected launchers/credentials
сохранены. PID7688→8668, localhealthok, model_tools.client_count=1.
Живой тест после сообщения владельца:1model attempt,valid/tool_calls,1087chars;
1job answered/done,2Instagram parts с receipts,каждая1attempt.
Паузу и лимит не сбрасывали (при проверке false/0); новых ручных API вызовов нет.
Public health с клиентского PC вернул Cloudflare403; наружный health не подтверждён.

Пользователь «деплой для тестового аккаунта?» разрешил ограниченный rollout
только @_shelter_0. N30 локально менял transport всех клиентов; перед rollout
обязателен независимый deny-by-default allowlist DEEPSEEK_TOOL_CLIENT_IDS с
проверенным числовым ID тестера. Пустой список — прежний JSON Output, некорректный
список запрещает запуск. Остальные клиенты сохраняют установленный prompt,
factory/request settings, JSON parser и прежнюю очередь; recovery scope не меняется.
Для тестера text/vision/voice-transcript и retries используют одну tool lane;
другие IDs не могут попасть в неё. Подготовленные replies/receipts не мигрируются.
Offline обе lane, mixed concurrency, restart/config validation, default-off;
полный pytest/Ruff/diff/review, package exact hashes, backup+rollback сохраняет
новые БД/receipts/unknown. Установка и один штатный restart разрешены; health,
installed28SHA и фактическое ограничение проверить без paid/model/client sends.
Для живого теста запросить новое сообщение после успешного rollout. Сбросы
паузы/лимитов не входят в этот шаг без отдельной необходимости/авторизации.

## Quick N30: единый tool transport — 2026-10-18, до реализации

Intent: пользователь «+» одобрил следующий шаг после N29: встроить проверенный
prepare_response в общий обработчик и проверить сохранение/повторы/доставку.
Статус: локально реализовано;1359testsPASS/8existingwarnings, Ruff/diffPASS,
независимое read-only review без блокеров.29 новых SDK/handler проверок включают
HTTP MockTransport, original1/10images, голосовой transcript, contact/cap,
silent, manager takeover, partial delivery и unknown после restart без regeneration.
Дубли полей проходят реальный SDK без потерь до штатного валидатора.
Scope: локальная реализация и offline QA;
production/deploy и новые оплачиваемые API вызовы не разрешены этим шагом.

AC N30.1: text/vision используют одну strict beta function schema reply/manager,
forced prepare_response, thinking.disabled,2048tokens,без response_format и SDK
автоповторов. Фото и десять кадров сохраняют original и порядок; voice transcript
продолжает общий текстовый путь. Нет отдельного JSON Output пути/модельных tools
с внешними действиями или дополнительных вызовов модели для tool result.
AC N30.2: принимать ровно один prepare_response, finish_reason tool_calls,
пустое обычное content; исходная строка arguments проверяется прежним строгим
валидатором, включая duplicate fields, лимиты и разрешение silent. Отказ при
plain content, неизвестном/нескольких tools, пропущенном ID, плохом типе,
обрыве или malformed arguments. Raw arguments не восстанавливать из parsed dict.
AC N30.3: прежние ограниченные повторы формата/технических ошибок, guard,
manager takeover, действующий телефон, Telegram cap и finalizer сохраняются.
Recovery сохраняет готовый результат до отправки; доставка/частичные receipts/
unknown не запускают повторную генерацию. Старые сохранённые результаты/история
читаются без миграции; служебные tool конверты не сохраняются в клиентскую историю.
AC N30.4: логировать redacted исходные tool arguments, результат проверки и
реальные finish/token metadata, без ключей/медиа. Новые unit+handler/recovery
tests используют HTTP/модель/отправки заглушки, включают SDK raw-response parsing.
Полный pytest, Ruff,diff; существующий runtime manifest остаётся installed baseline.

## N29 extension: десять дополнительных проверок — 2026-10-18, до кода

Статус: завершено, ровно10/10 HTTP200 и корректных исходных tool arguments.
Два проблемных контекста больше не возвращают пробелы; photo220€ и video10
Варшава-Дрезден-Прага распознаны. Смысл9/10: модель пропустила предупреждение
об исчерпанном лимите (установленный обработчик отдельно дописывает исход).
Первичный predicate ошибочно ожидал Берлин/Познань для ВДП; исправлен после
ручной проверки, исходный отчёт8/10 сохранён, пересмотр9/10 отдельным proof.
Production28SHA/env/health сохранены. Никаких новых отправок/деплоя.

Пользователь разрешил «10 проверок»: ровно до десяти новых оплачиваемых запросов.
Изолированная матрица transport+prompt: два повтора проблемного контекста, ВДП,
запрос менеджера, неясная и понятная реклама, новый контакт поверх старого,
исчерпанный лимит, настоящее фото и десять original кадров собственного видео.
Проверять исходные tool arguments штатным валидатором и отдельно смысл ответа.
Никаких клиентских/менеджерских отправок, записи рабочей БД, изменения конфигурации
или production. Это не проверка доставки и не установленный новый обработчик.
Каждый запрос резервируется до сети; существующий отчёт запрещает повтор run;
никаких автоматических HTTP повторов. Приватные ответы сохраняются вне Git.

## Quick N29: проверка tool calling — 2026-10-18, до кода

Статус: spike завершён. После явного согласия выполнены ровно 6 вызовов:
JSON control снова 388 пробелов; все 5 tool-вариантов прошли старый валидатор
и проверки трёх исходов. Ordinary 2/2, strict beta 3/3, nullable schema принята.
28 runtime SHA/settings/health сохранены, сообщений клиентам/менеджерам нет.
Ограничение: это direct API text spike, не полная интеграция обработчика,
vision/voice/mixed/tool-history и не статистическая гарантия стабильности.
См. runtime/deepseek-json-whitespace.md. Production на tool calling не переводился.

Intent: пользователь «работай» после предложения сначала проверить tool calling.
Проверить, может ли prepare_response вернуть действующий reply/manager на
реконструированном проблемном запросе и трёх исходах: ответ, ответ+менеджер,
молчаливая передача. Это оценка транспорта, не решение о миграции production.
Boundaries: только изолированный diagnostic/proof, штатный валидатор и текущий
каталог/закрытая история тестера; никаких клиентских отправок, правок runtime,
конфигурации/SQLite, lifespan, перезапуска или новых зависимостей. Предыдущие
восемь разрешённых платных вызовов исчерпаны; новый ограниченный бюджет запросить
перед run. Бесплатные preflight и offline-проверки разрешены этим запросом.
Acceptance: ровно один prepare_response, исходные arguments проходят прежний
строгий валидатор; пустой reply только с manager и allow_silent. Нет принятия
plain content/лишних вызовов/обрывов/дублей ключей как успешного результата.
Сравнить JSON control и обычный forced tool, повтор tool, strict beta, manager
и silent. Для forced tool выключить thinking согласно документации. Strict
nullable schema считается проверяемой гипотезой, а не гарантированно доступной;
при явном отказе strict два бизнес-сценария проверить обычным tool в пределах
общего бюджета. Зафиксировать реальные тела/результаты в приватном staging,
обезличенную выжимку и SHA runtime до/после. Не объявлять малую выборку гарантией.

## Quick V1: отдельные голосовые Instagram (2026-10-10, до кода)

**GigaAM comparison extension (2026-10-10, before implementation):** owner says «делай» after proposal to trial GigaAM-v3-e2e-rnnt on same owner audio plus >25s and spoken contact/date/tour checks. Isolated CPU trial/dependency/model download authorized, production deployment/restart/data changes not included. Reuse common16kHz monoPCM16 owner21.439s/native6.912s and3s silence; retain input/model SHA and provenance. Two CPU inference threads/one request, first+two warm runs, kernel+user CPU, cached initialization, peak/current process RAM, logical disk size, transcript errors and consistency. Prefer official CPU/ONNX-compatible inference with pinned/verified model snapshot, avoid unrestricted remote-code execution. A >25s clip made by joining own existing speech may establish longform mechanics only, not new natural speech accuracy. Numbers/dates/tour-name accuracy requires actual reference audio; a locally synthesized control, if available, must be labeled synthetic and never generalized to real customers. Missing sample is explicitly untested, not invented. Existing Parakeet/Whisper reports preserved, matched-sample comparisons used; any segmentation/precision/VAD differences disclosed. No external STT API/audio uploads/paid requests/client/manager messages. Temporary artifacts/private transcripts outside Git. Acceptance: setup and model provenance verified; actual GigaAM results or diagnosed concrete limitation; longform/control scope honest; production17source SHA/launcher/listener/local+public health unchanged; reproducible report and spec/task/runtime cascade before completion.

**GigaAM result/status:** isolated ONNX FP32 trial complete;42 new passes and36 prior baseline passes verified (78total). Same owner baseline: no-spin2.721/0.854s, default-spinning1.789/0.357s vs Parakeet6.337/2.664s and turbo20.933/19.946s. No-spin averageCPU~12.4%; default~16%/25% but lowerCPU-seconds/request. Same texts both modes, mainRAM1021.92MiB vsParakeet847.67. GigaAM keeps «не быть с программой»/ending; synthetic45.39s numbers/date/price/tours correct, Parakeet «Познань»→«Поздном», turbo fields correct. Joined owner43.13s and synthetic split into shared≤25s chunks; natural long/noise/contact dictation not established. ONNX warns about WindowsServer2019 despite successful actual trial; community export provenance and OS compatibility caveat explicit. Current candidate recommendation is GigaAM no-spin for lower CPU-intensity, default available for latency tradeoff; this supersedes Parakeet trial recommendation, not settled production architecture. Source17SHA/launcher/listener2984 unchanged, local/publichealthok, no trialprocess remains. Evidence: runtime/gigaam-whisper-parakeet-comparison.md. V1d voice integration pending.

**Parakeet comparison extension (2026-10-10, before trial implementation):** owner requests isolated local Parakeet TDT0.6B-v3 Q8 trial and comparison with Whisper across practical parameters. Authorized downloads/portable trial setup and own-recording inference only, not production rollout. Use existing owner M4A21.439s and native Instagram AAC6.912s, plus silence; source SHA retained. Compare transcript meaning/errors/punctuation, model/runtime disk size, cached load, first/warm STT, total latency, CPU seconds/share, peak memory, repeat consistency, installation/format/privacy/offline/operational constraints. Do not invent WER, contacts accuracy, GPU results or concurrent capacity without matching samples/measurements. Application code/config/deps/data/startup and17 runtime source hashes remain unchanged; health verified before/after. Download/version/checksum failures diagnosed before benchmarking. Practical scope:2CPUthreads/1request, short≤180s/10MiB audio. Results and private transcripts retained outside Git; no customer audio uploads/external STT APIs.

**Parakeet stage (historical, recommendation superseded by GigaAM result above):** isolated owner speech trials completed, including Parakeet v3 Q8 vs Whisper small/medium/turbo on identical PCM from two owner files and silence:36 runs. At this stage Parakeet was recommended:6.337s vs turbo20.933s on21.439s speech,2.664s vs19.946s on native6.912s voice; both preserve meaning, Parakeet omits one preposition. Peak RAM856.19 vs1878.79MiB; post-run snapshots847.67 vs981.205MiB, distinct metrics. Verifier/read-only review PASS;17 prod SHA/launcher/listener2984/local+public health unchanged. Evidence: runtime/parakeet-whisper-comparison.md. Production voice integration remains pending. Server read-only initial probe: Python3.12.10,16 logical CPUs,15.77GiB RAM/10.97GiB free, faster-whisper/av/ctranslate2 initially absent. **Intent:** владелец попросил реализовать голосовые. Доступный прежний FR-3 задаёт voice→transcript→existing DeepSeek conversation→text reply; владелец выбрал сначала испытание локального Whisper. Работает только с отдельными audio attachments; звук историй/Reels/прямого видео по-прежнему не расшифровывается.

**Boundaries:** channel/batch routing, отдельный transcription service, config, focused tests и existing specs/docs/runtime/manifest. Сохранять fixed5-second window/MID дедупликацию, порядок сообщений, source разных media, guard/rate-limit/manager takeover, телефонный source и краткую Telegram summary. Аудио временное; URL/bytes/секреты не сохранять в историю/логи. Новые библиотеки/API-ключи/лимиты распознавания определяются после выбора локального STT либо API; production пока без изменений.

**Acceptance draft:** V1.1 — доступное голосовое распознаётся в текст и обрабатывается как вопрос клиента по текущему каталогу/FAQ/истории; нет non-text эскалации только за audio format. V1.2 — voice+text (и поддерживаемые соседние media) одного пакета сохраняют порядок и дают один общий DeepSeek call, не отдельные ответы на каждое вложение. V1.3 — тишина/неразборчивая речь/недоступный или повреждённый файл дают просьбу повторить вопрос голосом/текстом; не выдумывать расшифровку. V1.4 — ограничения скачивания/распознавания, отмена/cleanup и manager takeover проверяются до распознавания и перед доставкой; пауза менеджера не порождает AI/клиентский ответ. V1.5 — распознанные числа/даты/имена не исправляются моделью произвольно; неоднозначные контакты уточняются до handoff. V1.6 — meaningful regressions/full local/server QA и real voice trial отдельно; без неразрешённых paid calls/установок и ручных уведомлений.

**Trial authorization:** ответ владельца «Локальный Whisper — сначала проверка скорости и качества». Isolated environment + official small multilingual model, CPU/INT8/2 threads/1 worker/VAD. No prod environment/code/data/restart. Model load and silence smoke are only setup proof; реальное качество/latency require user audio sample.

Trial extension (before code): owner M4A21.439s yielded small transcription6.584s/706.3MiB, suspicious phrase «Пух Варшаву». Compare medium on the same file without reference hints, preserve raw artifacts and repeat warmed inference. Owner confirmed this file is about visiting mother separately from tour program, different from previously pasted visa text. PyAV compatibility fix exact file PASS; production voice remains disabled.

Research: https://github.com/SYSTRAN/faster-whisper ; https://huggingface.co/Systran/faster-whisper-small ; official CPU/INT8 and VAD supported.

**Trial result:** owner M4A21.439s. Small5.497/6.146s (initial6.584s),706.6MiB, «Пух Варшаву»; medium17.240/16.273s,1767.1MiB, initial noun missing; turbo17.268/18.282s,1908.0MiB, phrase «тур в Варшаву» and mother/program question preserved. Each same-process pair produced identical text. Turbo cached load5.615s; silence3s →0segments/0chars in0.065s. These are CPU/INT8/2threads measurements excluding model load/file decode/5s batch/DeepSeek; turbo decode0.044s. No literal reference/WER or dates/phone evidence, this sample contains no numbers/dates. No production voice rollout/restart or AI/client/manager calls.

**Native Instagram proof (2026-10-10):** owner authorized temporary own-account webhook capture and two restarts, then sent another native voice. Download succeeded HTTP200/36384bytes; MIME video/mp4, MP4/isom container with audio only, AAC48000Hz/stereo,6.912s. Isolated PyAV16.1.0 decoded the full recording. Normal launcher restored,17 application file hashes unchanged,local/public health ok. No transcription or production recognition integration; one sample does not constrain every Instagram client to this codec.

**Open:** integration limits/config and meaningful voice/batch/takeover regressions. Native download is established for the tested own recording. Recommendations evolved from turbo to Parakeet and then GigaAM after matched trials; latest result/status above is current, no production architecture chosen. Numeric/date/tour fields verified only on synthetic control; natural contact dictation/noise/concurrency remain untested. Design/tasks before production implementation.

## Micro N6: краткая суть эскалации (2026-10-10, до кода)

**Status:** deployed; local654 PASS/server652 PASS+2 previous JPEG-artifact skips/Ruff/diff-check PASS, final review clear. Backup-contact-summary,3 files/all17 SHA verified, PID15292→12324, local/public health200/ok, three media flags true. N6 supersedes N5 notification excerpt: владелец проверил live и отклонил большой ответ в «Суть». **Intent:** менеджер получает выжимку (1–2 предложения, не более 450 символов): тур, вопрос клиента, важные условия и причина обращения. Контекст распознанной истории учитывается по разговору; программа тура и полный ответ не копируются.

**Boundaries:** main/prompts/engine tests, existing spec/docs/runtime/manifest. Использовать Контекст уже существующего AI-запроса, без дополнительного AI/Graph, изменения истории/БД, телефонного source, лимитов и manager takeover. Смена вопроса вместе с телефоном не наследует старую тему.

**Acceptance:** N6.1 — краткая модельная выжимка сохраняется, no ID/URL/телефонов/служебных блоков; отдельный текущий телефон авторитетен, конфликт model phone исключает сводку. N6.2 — без валидного Контекста короткий fallback выбранного вопроса и первого содержательного предложения связанного доставленного ответа; unavailable/no-caption не возвращаются к старому туру; весь fallback ≤450. N6.3 — даты/цены/условия визы допустимы; full reply/program/footer не копируются; история unchanged, один AI call. N6.4 — regression red→green/full local/server QA, guarded rollout по прежней авторизации; live генерация оценивается отдельно.

## Micro N5: человеческий контекст контактной эскалации (2026-10-10, до кода)

**Status:** superseded by N6 after owner live feedback; historical deployed;local639 PASS/server637 PASS+2 previous JPEG-artifact skips/Ruff/diff-check PASS,12 new cases, final review clear. Backup-contact-context,2 files/all17 SHA verified, listener5292→15292, local/public health ok. **Intent:** после story→«можно подробнее»→ответ об Эльбрусе→телефон менеджер получает только вопрос и ID. Уведомление должно включать выбранный вопрос и соответствующий реально доставленный ответ бота; известные media-пометки превращаются в понятный источник (видеоистория/фотоистория/фото/публикация). Это выдержка разговора, не новое распознавание и не утверждение о невидимых деталях истории.

**Boundaries:** src/main.py, meaningful engine tests, existing spec/docs/runtime/manifest. Без новых AI/Graph запросов, raw media/caption/URL persistence, изменения history/DB schema, текущего телефонного source, лимитов/manager takeover. Текущий вопрос вместе с телефоном имеет приоритет и не получает ответ на другую прошлую тему.

**Acceptance:** N5.1 — телефонная эскалация содержит вопрос, human source без story ID и доставленный ответ из того же user turn (до следующего user). N5.2 — старые телефоны/служебные блоки не возвращаются ни в context, ни в контакты; текущий actual input phone остаётся единственным contact source; строки с телефонами исключаются из выдержки, даты/цены сохраняются. N5.3 — без ответа/при media unavailable не подставлять старый тур; current question не обогащать чужим старым ответом; длинная выдержка ограничена и помещается в Telegram. N5.4 — регрессия red→green/full local/server QA/read-only review, guarded rollout по прежней авторизации; новый real contact повтор отдельно, без ручной рассылки/сброса сессий.

## Quick bugfix S7: вопрос после реакции на историю (2026-10-09, до кода)

**Status:** deployed; local627 PASS/server625 PASS+2 previous JPEG-artifact skips/Ruff PASS; backup-story-context, 4 files/17 SHA verified, PID10076 → 5292, local/public health ok. Live повтор ещё ожидается. **Intent:** live 16:40:36 UTC передал exact story ID вместе с emoji, который parser отбросил; «можно подробнее» через 25 секунд пришло без истории. На реакцию не отвечать, но её exact ID использовать для следующего текстового пакета того же клиента. Контекст одноразовый, живёт 120 секунд в памяти; новая реакция заменяет предыдущую. Пять секунд сбора сообщений не меняются.

**Boundaries:** channel/main, regression tests, существующие spec/docs/runtime/manifest; без paid/manual AI, изменений БД, сброса лимита/перехвата или новой эвристики распознавания тура. ID проходит прежний exact own-story resolver, фото original/видео10; media unavailable сохраняет честный fallback. Произвольные URL не сохраняются.

**Acceptance:** S7.1 — emoji story event резервирует MID, сохраняет только валидный ID, без AI/уведомления/таймера/ответа. S7.2 — следующий plain text через25с получает snapshot этой истории; соседние plain messages окна объединяются в один вопрос. S7.3 — контекст consume при приёме первого содержательного события, новая media/story/phone/referral/non-text не наследует его; смешанный пакет не получает конкурирующую историю. S7.4 — TTL600с, cap10000, sender isolation, duplicate reaction не продлевает/не воскрешает контекст; invalid/unsupported reaction и manager takeover очищают; shutdown очищает. Новая реакция во время ожидания/AI не подменяет snapshot уже принятого вопроса. S7.5 — red regression → full local/server pytest/Ruff, guarded patch/backup/SHA/restart/health по прежней авторизации; живая повторная отправка владельца отдельно от синтетического доказательства.

## Micro Spec M2: mention VIDEO и direct VIDEO (2026-10-09, до кода)

**Status:** deployed; local601 PASS/server599 PASS+2 previous JPEG-artifact skips/Ruff PASS; native real MP4→20 frames, backup-visual, 8 files/17 SHA verified, PID3460 → 10076, local/public health ok. M2 supersedes M1 image-only mention and A2 direct-video fallback. **Intent:** photo story mention остаётся original IMAGE; video story mention и attachments.type=video используют существующий VIDEO decoder: десять равномерных кадров полного файла, без звука, один vision-запрос с вопросом. Формат mention определяется по байтам JPEG/PNG/MP4, не по URL/обложке. Позиции вложений, подписи кадров и story mention marker сохраняются при смешанных/нескольких фото и видео. GIF/sticker игнорируются, голосовые остаются отложены; file/product направляются менеджеру вместе с текстом вопроса.

**Boundaries:** channel/main/prompts/story_media, meaningful tests, existing spec/docs/runtime/manifest. Reuse IMAGE_MEDIA_ENABLED и _prepare_file/VIDEO decoder без новых библиотек/моделей, изменения БД/лимитов или STT. Existing own story exact-ID, shared post/carousel, safe URL/MID/signature/takeover/fixed five-second batch сохраняются. AUTO разрешён только для story_mention; обычный image не становится видео. GIF bytes допускаются только для определения и игнорирования, не декодируются/не отправляются AI. Невалидный/недоступный источник/частичный decode дают прежний честный fallback без частичного vision.

**Acceptance:** M2.1 — direct VIDEO/mention VIDEO дают ровно10 chronological original frames per video; JPEG/PNG mention сохраняет1 original. M2.2 — mixed/two videos имеют отдельные temporary folders, input attachment index labels, expanded output image_types и resolved input formats для безопасной истории. M2.3 — validate whole input list до скачивания, per-file25MiB/video90s, aggregate images24MiB/100, preparation90s/semaphore2, cleanup/cancel и URL allowlist сохранены. M2.4 — explicit GIF/sticker резервирует MID и не вызывает AI/manager/client reply; GIF disguised as image игнорируется по magic, соседний вопрос/фото сохраняется. M2.5 — file/product с вопросом и без него передаются existing deterministic manager handler, opaque payload/URL не исполняется. M2.6 — regressions/full local/server QA/native local VIDEO proof без paidcalls; guarded rollout по существующей авторизации. Live Meta delivery отдельно от синтетического/native доказательства.

## Micro Spec A2: общий безопасный приём вложений (2026-10-09, до кода)

**Status:** deployed; local 559 PASS, server isolated stage 557 PASS/2 previous JPEG-artifact skips, Ruff PASS; backup-attachment, 3 files applied/16 SHA verified, PID 11672 → 3460, local/public health ok. **Intent:** пользователь просит перечислить типы и обрабатывать все по возможности без ошибок. Все пользовательские сообщения с MID получают поддерживаемый media/text маршрут либо честный fallback; неизвестный тип/нестандартный payload не должны ломать соседние события webhook или исчезать. Понимание контента остаётся в согласованном наборе: JPEG/PNG, photo story mention, exact own story, доступные posts/Reels/carousel. Direct video/GIF/files/product cards пока распознаются как неподдерживаемый контент; voice transcription по-прежнему исключена. Служебные read/reaction/deletion/delivery/referral без вопроса не вызывают ответ.

**Boundaries:** src/channels/instagram.py, src/main.py, focused tests и существующие docs/spec/runtime/manifest. Без установки зависимостей, paid/manual API calls, изменения БД/.env/лимитов, нового декодера или broad media rewrite. Postback обрабатывает видимый непустой title с реальным MID как текст, не исполняет opaque payload/URL. JSON без корректной структуры не получает HTTP 500: invalid JSON — 400 после подписи, некорректные контейнеры пропускаются, валидные соседи сохраняются.

**Acceptance:** A2.1 — unknown/malformed attachment type/list/payload/text не падают; metadata содержит только безопасные типы и строковый текст. A2.2 — is_unsupported и empty unknown message с MID идут в non-text fallback; произвольные URL не скачиваются, deleted/service события игнорируются. A2.3 — валидные соседи, все реальные MID, fixed 5 секунд, manager takeover и existing media flow сохраняются; postback title сохраняется без payload. A2.4 — ошибка Telegram не сопровождается ложным «передал», лимит не увеличивается; manager takeover проверяется перед действием/ответом. A2.5 — meaningful regressions/full pytest/Ruff, staged server QA и guarded rollout по существующей авторизации; live unsupported/video/GIF не выдаётся за проверенное понимание.

Research: Meta overview returned HTTP429 (blocked, не «отсутствует»). Official Meta Postman template example: https://www.postman.com/meta/instagram/folder/rl2amj3/templates . Integration provider incoming type catalogue: https://www.infobip.com/docs/instagram/messaging/message-types . Exact incoming strings вне существующего кода не угадывать; unknown fallback остаётся открытым к новым типам.

## Document Information

- Feature Name: распознавание изображений, голосовых и контекста видеоисторий в Instagram Direct.
- Version: 0.11.
- Date: 2026-10-08.
- Status: story/image/posts/Reels включены в production; live native ig_reel и IMAGE own story прошли vision/send, карусель подтверждена владельцем. N1/N2/N2c выложены 2026-10-09; live новый phone/card после N2c прошёл: duplicate ignored, current input source, Telegram delivered, один clean visible reply.
- Stakeholders: владелец «Сандиты», клиенты Instagram, менеджеры.

## Introduction

## Micro fix N1/N2: телефонная карточка и служебный блок

Micro N1/N2 (2026-10-09, до кода): screenshot phone/template flow и leaked
unclosed manager block. Номер из узкой phone/contact-card схемы нормализуется
как обычный текст, без blind attachment instruction. Совпадающие text/card
MID одного webhook сохраняются; auto phone-card, повторяющая phone-only text
за последние 30 с, не создаёт второй AI/Telegram reply. Cache bounded/transient,
не подавляет обычные повторные тексты/другие номера. Generic cards не извлекают
контакты из произвольного текста. Phone postback требует настоящего MID и
видимого phone title. Маркеры удаляются даже без closing marker; прежние
утекшие assistant blocks очищаются только в prompt-copy без переписывания БД.
Без raw payload/номеров в диагностике, старые сообщения не replayed. См. bugfix.md.

Расширение N1b до кода: фактическая оболочка payload.generic поддерживается
с теми же guards. Empty generic после единственного recent phone-only input
не создаёт второй ответ; это корреляция пустой карточки с подтверждённым текстом,
не извлечение телефона из отсутствующего содержимого. Новый вопрос, несколько
недавних номеров и unrelated template сохраняют прежнюю обработку.

N2b: actual current input phone запускает передачу контакта независимо от наличия
AI marker, с прежним limit/takeover. Phone-only ответ — один короткий ack по факту
успеха/ошибки/лимита notifier; не обещать успешную передачу при ошибке. При вопросе
вместе с карточкой сохранять AI ответ. См. live root cause в bugfix.md.

N2c до кода: при смене подтверждённого current phone весь contact notification
привязан к новому номеру. Старые телефоны из AI context и prior mixed user
контактов не попадают в «Суть»/contact tag; current question имеет приоритет,
иначе последний содержательный user запрос без телефона. Другие виды эскалаций
и прежние limit/takeover/MID/media сохраняются. См. bugfix.md N2c.

Факт N1/N2/N1b: первый live повтор выявил nested generic, marker leak отсутствует
в последних двух сохранённых assistant ответах. После N1b local 457 PASS;
server 455 PASS/2 JPEG-artifact skips/Ruff PASS. После N2b final local 466 PASS,
server 464 PASS/2 JPEG-artifact skips/Ruff PASS; guarded backups, 14 SHA verified,
PID 16256, localhost/public health 200/ok. По разрешению владельца сброшены только
два поля его тестового диалога, history preserved; остальные клиенты сохранены.
Final live phone/card после N2b остаётся N3b.

Факт N2c: local 478 PASS, server 476 PASS/2 JPEG-artifact skips/Ruff PASS.
Два файла, guarded backup-contact-source-v2, 14 SHA verified, PID 2664,
local/public health 200/ok. Никаких reset/replay/ручных paid calls в N2c.
Новый live номер после N2c требует N3b; raw template в последнем phone send отсутствовал.

Live N3b (2026-10-09 01:44 Минск): новый номер normalizes и отличается от всех
предыдущих; nested generic.elements=[] через 1.35 с игнорируется как дубль.
AI phone absent, source current input; Telegram delivered четырём получателям,
один Instagram reply/75 chars без marker. Counter 1→2; без ручных replay/reset.

## Micro fix C2/C3: exact carousel child asset и быстрый IMAGE decode

URL-derived numeric asset_id может указывать на child карусели. Сопоставлять
его только с точным id/ig_id child в собственном Graph /media и повторно
подтвердить принадлежность в полном parent CAROUSEL_ALBUM. Обрабатывать весь
parent, не одну фотографию/обложку. Explicit media ID/совместные ID+permalink
guards, три own /media страницы и лимиты/timeout/cleanup не менять.
JPEG pixel validation сохраняется, но результат byte[] отбрасывается без
PowerShell pipeline enumeration. Для данной карусели 5 фото + 2 видео → 25
original изображений, один vision с вопросом. Нет новых ручных paid calls.

Факт C2/C3 (2026-10-09): shared tests 38 PASS; local full 415 PASS до последнего
дополнительного direct VIDEO-child test case, server full 414 PASS/2 JPEG-artifact
skips, Ruff PASS. Оба seventh child ID → exact parent CAROUSEL_ALBUM/7 children.
Полная original preparation 25 изображений ускорилась 79.6 → 12.6 с; JPEG
validation ~0.4 с вместо 10–19 с, прежние лимиты сохранены. Guarded 3-file
patch с backup-carousel, 12 SHA verified, PID 4388 → 8160, local health ok и
три флага true. Владелец подтвердил live повтор: «работает»; paid calls=0 в пробе.

## Micro bugfix R1: native ig_reel attachment

Реальный webhook после деплоя имеет attachments.type=ig_reel. R1: считать этот
тип shared video вместе с ig_post/share и сохранить ID/URL через существующий
resolver; принимать только полное подтверждённое медиа. Никакого bypass CDN/Graph
guards и распознавания thumbnail. Флаг off сохраняет старый legacy маршрут
неизвестного вложения. Связь: bugfix.md, regression tests и tasks R1/R2.
Факт R1: native ig_reel классифицируется как shared только при enabled флаге;
reel_video_id проходит существующий Graph resolver, safe diagnostic не содержит
URL/текст публикации. 408 local PASS; 406 server PASS/2 skips, Ruff PASS;
fix включён на сервере, 12 SHA и local/public health подтверждены. Старый live
Reels попал в non-text и не был распознан; повторная отправка завершила vision QA.
Факт: webhook 20:27:14.650 UTC, ig_reel/reel_video_id, подготовлено 10 кадров
20:27:22.128; DeepSeek завершён 20:27:26.863 (32617 input/259 output tokens);
Instagram message.sent 20:27:29.062. Один vision-запрос, 14.4 с до отправки.
Сырой payload/URL не записывался; обычная история сохранила processed media marker
и assistant reply. Один проверенный Reels не доказывает доступ к любым чужим медиа.

## Расширение: посты и Reels (Quick Spec, до реализации)

Авторизация: «добавь посты и рилсы», 2026-10-08. P1: сохранить точный доступный
идентификатор/URL shared post (ig_post/share) в transient событии, включая подпись;
не терять его при объединении с вопросом/MID. P2: разрешить публикацию через
официальный Graph media object по точному media ID либо по permalink среди наших
публикаций. Поддержать IMAGE, VIDEO/Reels и CAROUSEL_ALBUM (до 10 элементов);
VIDEO — десять равномерных original кадров, IMAGE — исходный JPEG/PNG,
карусель — все элементы в исходном порядке с общим лимитом 24 MiB и 100 кадров.
Содержание и вопрос идут одним вызовом DeepSeek, без звука/OCR/повторов.

P3: при отсутствующем вопросе кратко распознать публикацию и уточнить интерес.
Существующие каталог, FAQ, история, guard, перехват/очередь и MID-дедуп сохраняются;
история не хранит signed URL/base64. P4: thumbnail и HTML Instagram страницы
не являются полным медиа; не распознавать обложку вместо недоступного Reel.
Если Meta не отдаёт точный media object/media_url, публикация удалена/приватна,
доступ закрыт либо лимиты превышены — честно попросить прислать исходное фото/
видео или сведения текстом. Универсальное получение любых чужих постов/Reels
не обещается; обход ограничений аккаунта/скрейпинг/сторонние скачиватели исключены.

P5: SHARED_MEDIA_ENABLED=false по умолчанию. При off — прежний shared-post путь.
При on — объединённые shared/text события одного webhook сохраняют все источники,
вопросы и MID; разные shared attachments одного сообщения (share + ig_post)
дедуплицируются по точному media ID. Разные POST обрабатываются по порядку;
не добавлять произвольную временную склейку без явной связи. Все текущие лимиты
скачивания/декодера, allowlist/no redirects/no token CDN и cleanup сохраняются.
Размер ролика до 90 секунд/25 MiB: длинные Reels дают уточнение, без тихого обрезания.

Acceptance: parser fixtures поддерживаемых ig_post/share payload, original10/1,
carousel порядок/общий лимит, Graph exact ID/permalink mismatch/access denial,
недоступный Reel с доступным thumbnail → ноль AI, вопросы/без вопросов/повторы/
manager/guards/legacy off, safe logs/history/cleanup; полный pytest/Ruff.
Первоначально новые платные AI-вызовы и rollout не были разрешены отдельно.
Запрос «деплой» ниже авторизовал развёртывание и включение трёх media-режимов.

Факт P1–P5 (2026-10-08): полный pytest 403 PASS (8 прежних предупреждений),
Ruff PASS; read-only review завершён после устранения ID/permalink mismatch
и привязки подписи к номеру публикации. Реальный Graph вернул полный media_url
собственного Reels и семь элементов собственной смешанной IMAGE/VIDEO карусели.
prepare_shared_media собственного Reels успешно дал 10 original кадров,
0.000–8.500 с, без платного AI. Артефакт: reel-preparation-check/evidence.json.
Один vision-запрос/guards/fallback проверены с mock AI. Новая форма share payload
проверена fixtures; Meta webhook docs вернули 429, живой shared webhook пока
не получен. Сквозной ответ клиенту и доступность чужих публикаций не подтверждены.
P1–P5 расширяют прежние ограничения S6/I1–I3 именно для ig_post/share;
голосовые, direct video и чужие/истёкшие истории остаются вне этапа.

Факт rollout (2026-10-08): сервер HEAD 3d6318bb, заменены только 12 файлов
проверенного manifest; сохранены прежние файлы и .env в закрытом backup.
Изолированный server pytest: 401 PASS, 2 JPEG-artifact tests SKIP, Ruff PASS.
Native server smoke VIDEO/IMAGE/VIDEO → 21 изображение по порядку без сети/AI,
синтетический MP4/PNG созданы на сервере. STORY_MEDIA_ENABLED,
IMAGE_MEDIA_ENABLED и SHARED_MEDIA_ENABLED=true; vision=deepseek-flash.
Контролируемый restart: проверены только parent/child бота, listener PID
5512 → 15384. Все 12 deployed SHA совпали; localhost и public /health 200/ok.
Live vision-ответ клиенту не выдаётся за подтверждённый deployment QA.

## Текущий согласованный этап (Quick Spec, 2026-10-08)

Авторизация: «original, делим видео на 10 кадров, отправляем их одним запросом вместе с вопросом клиента» и последующее «+» на внедрение. Реальная связка webhook → точный ID → полный файл проверена для двух VIDEO и одной IMAGE истории. Этот раздел определяет текущий объём; широкие FR ниже остаются предложением для следующих этапов.

- S1: Содержательный текстовый ответ на собственную активную историю сохраняет точный ID. VIDEO превращается в ровно 10 равномерных кадров от начала до последнего доступного кадра; IMAGE отправляется как одно изображение. Звук, OCR, выбор похожего ролика и thumbnail вместо VIDEO исключены.
- S2: Кадры в хронологическом порядке с `detail=original` и исходный вопрос передаются одним пользовательским сообщением в один `deepseek-flash` вызов, без автоматических повторов. Сохраняются системный промпт, каталог, FAQ, история, проверка ответа, эскалация и очередь доставки. Клиент получает единый содержательный ответ (обычное разбиение длинного текста допустимо).
- S3: Сначала проверяются ввод, лимит и перехват менеджером. Подготовка не блокирует установку перехвата; порядок сообщений одного клиента сохраняется. После подготовки, перед AI и доставкой состояние перепроверяется. Повторный MID не запускает второй запрос в пределах текущей дедупликации процесса.
- S4: ID подтверждается списком собственных активных историй. HTTPS-файл скачивается только с разрешённых Meta CDN, без редиректов и передачи Meta-токена CDN. Лимиты: файл 25 MiB, видео 90 секунд, габарит 4096 пикселей, совокупные изображения 24 MiB; общая подготовка 90 секунд, декодер 60 секунд, одновременно 2 подготовки. Временные файлы удаляются при успехе, ошибке и отмене. Неверный ID, чужая/истёкшая история, неполная загрузка, повреждение, неподдерживаемый формат или ошибка AI дают честное уточнение, без угадывания.
- S5: В логах и БД нет подписанных URL, токенов и base64; история хранит вопрос и безопасную пометку ID/типа истории. Windows-декодер использует уже установленную ОС без установки библиотек. Флаг `STORY_MEDIA_ENABLED` по умолчанию выключен; `DEEPSEEK_VISION_MODEL=deepseek-flash`. Сервисный rollout — отдельный проверяемый шаг после локального QA.
- S6: Голосовые клиента, произвольные видео, Reels, чужие/истёкшие истории, расшифровка звука и OCR не входят в этот этап. Обычные изображения включены отдельным расширением ниже. Текстовые сообщения и реакции сохраняют прежнее поведение.

### Расширение: обычные изображения (Micro Spec, до реализации)

Intent: запрос владельца «добавь еще распознавание просто изображений» от 2026-10-08.
Полученное в Direct фото/скриншот в attachments[type=image] передаётся в тот же
vision-поток original с подписью клиента, одним AI-вызовом и прежним каталогом,
FAQ, историей, guard и очередью. Без подписи бот коротко определяет содержание
и уточняет вопрос. Это не разрешение анализировать пересланные видео/Reels.

Boundaries: существующие config/channel/main/prompts/story_media и тесты;
повторно используется Windows IMAGE decoder. Только JPEG/PNG (фактический формат
проверяется), до 10 вложений и 24 MiB суммарно; тот же CDN allowlist/timeout/cleanup,
без токена, редиректов, URL в логах и БД. Флаг IMAGE_MEDIA_ENABLED=false по умолчанию.
Смешанные вложения с аудио/видео, ссылки на пост/Reels и произвольные сайты
сохраняют прежний безопасный путь; thumbnail Reels не выдаётся за полное видео.
Пересланная чужая история не становится собственной историей по похожей картинке.

Acceptance I1: канал сохраняет доступные payload.url изображений только во временном
событии, отсутствующий/невалидный источник приводит к честному fallback; исходные
MID остаются защищены дедупликацией. Подпись и фото одного сообщения анализируются
вместе. Если текст и фото пришли отдельными событиями одного webhook, сохраняются
все подписи и MID, не перезаписываются. Несколько фото анализируются одним запросом.
Отдельные POST-вопросы сохраняют порядок; автоматическое связывание произвольных
вопросов/фото из разных POST в этот микроэтап не входит.

Acceptance I2: не более одного вызова vision, все image_url/detail=original;
фото без вопроса вызывает осмысленное уточнение, без выдуманного запроса клиента.
В истории только подпись либо '[Изображение без подписи]' и безопасная пометка
числа изображений; URL/base64 не персистируются. При отказе guard/лимите/менеджере
не скачивать и не вызывать AI. Перехват во время подготовки/AI/очереди учитывается.

Acceptance I3: флаг off сохраняет прежний маршрут вложений. Невалидный URL,
redirect, неверный формат, повреждение, превышение лимита и API error дают
честный fallback, без обычного текстового AI вместо изображения. Модульные/
интеграционные тесты и реальные JPEG/PNG decoder проверки, полный pytest/Ruff.
Разработка/локальное QA разрешены; rollout и новые платные вызовы не разрешены
этим запросом отдельно от уже pending approval.

Факт I1–I3: полный pytest 378 PASS, Ruff PASS (2026-10-08). Настоящий Windows
decoder прочитал JPEG из имеющегося собственного trial и PNG, созданный stdlib;
JPEG в payload сохранил исходные байты. Фото с вопросом/без подписи, несколько
фото, MID до merge, частичный retry со свежими сообщениями, legacy/off, own-story
priority, неподдерживаемые post/video/mixed, manager/guard/cleanup проверены тестами.
Модель в интеграционных тестах mock; новых платных AI-вызовов и rollout не было.

Проверка: тесты приёма/дедупа, безопасной загрузки и cleanup, один multimodal вызов с 10/1 изображениями, перехват во время подготовки/AI, guard и очередь; реальное извлечение десяти кадров из уже проверенного собственного видео. Полный pytest и Ruff обязательны. Живая доставка через новый поток отмечается отдельно от тестов.

Факт 2026-10-08: полный pytest — 343 PASS (8 прежних предупреждений), Ruff PASS.
Новый production service скачал историю 17951100675316673 и извлёк 10 JPEG
в исходном размере 720×1280, точки 0.000–25.089 с, суммарно 1 810 235 байт;
артефакт `production-ten-frame-check/evidence.json` и все 10 кадров сохранены
в workspace artifacts. Native IMAGE test также PASS. Подготовка не вызывала
платный AI. Один vision-вызов, контекст, очередь и перехват проверены с mock AI;
сквозной production vision-запрос и ответ клиенту пока не проверены.

Исходное поведение (до story/image расширений): InstagramChannel сохранял тип
вложения, но отбрасывал URL и содержимое. Фото/голосовые без подписи направлялись
менеджеру; подпись с типом вложения отправлялась обычному текстовому AI.

### Feature Summary

Бот понимает вопрос из фото/скриншота, голосового или ответа на видеоисторию и отвечает текстом по действующему каталогу и FAQ; при недостаточных данных уточняет или передаёт менеджеру.

### Business Value

Сократить ручную обработку вложений и повторный ввод клиента, сохранив проверку актуальных цен, дат и ссылок по каталогу.

### Scope

Предложение: фото/скриншоты, русскоязычные голосовые и ответы на собственные видеоистории аккаунта с текстовым ответом. Для видео пользователь 2026-10-08 выбрал направление «точное видео → кадры → DeepSeek» и явно исключил расшифровку звука видео. Обязательно получение полного файла именно той истории, на которую ответил клиент. Привязка приблизительно по туру или по похожему ролику условию не соответствует. Полный объём фичи и требования ещё не утверждены. Произвольные входящие видео/Reels, PDF/офисные документы и голосовые ответы требуют отдельного решения; конкретная модель для изображений и поставщик распознавания отдельных голосовых ещё не утверждены.

## Requirements

### FR-1: Приём и связывание медиа

**User Story:** Как клиент, хочу отправлять вложение с пояснением, чтобы бот учитывал вопрос целиком.

#### Acceptance Criteria

1. WHEN подтверждённый webhook содержит поддерживаемое вложение THEN система SHALL сохранить его тип, идентификатор события и доступный источник содержимого для фоновой обработки.
2. WHEN сообщение содержит подпись и вложение THEN система SHALL использовать оба в одном контексте запроса.
3. WHEN события объединяются THEN система SHALL сохранить все тексты и идентификаторы, не перезаписывая более раннюю реплику последующей.
4. WHEN уже принятое событие доставляется повторно THEN система SHALL не запускать повторное распознавание и не создавать повторный ответ.
5. IF доступный webhook не содержит извлекаемого содержимого или источника THEN система SHALL сообщить о невозможности прочитать именно это вложение и предложить переслать его либо обратиться к менеджеру.

### FR-2: Изображения

**User Story:** Как клиент, хочу отправить скриншот рекламы или фото программы тура и задать вопрос о нём.

#### Acceptance Criteria

1. WHEN изображение доступно и формат поддерживается THEN система SHALL извлечь читаемый текст и релевантное вопросу описание изображения.
2. WHEN скриншот содержит название тура, стоимость или даты THEN система SHALL сопоставить сведения с текущим каталогом; актуальные условия SHALL брать из каталога.
3. IF изображение не позволяет однозначно определить тур THEN система SHALL задать конкретный уточняющий вопрос, не выдумывая название тура или место съёмки.
4. IF мелкий/размытый текст не читается THEN система SHALL назвать ограничение и запросить более чёткое изображение или текст вопроса.

### FR-3: Голосовые

**User Story:** Как клиент, хочу задать вопрос голосом и получить обычный текстовый ответ.

#### Acceptance Criteria

1. WHEN доступно поддерживаемое голосовое сообщение THEN система SHALL расшифровать речь и использовать расшифровку как клиентский ввод в существующем диалоге.
2. WHEN в речи названы даты, имена или контакты THEN система SHALL сохранить распознанные значения; при неоднозначности SHALL уточнить их до действия по заявке.
3. IF сообщение не содержит различимой речи THEN система SHALL попросить повторить вопрос голосом или текстом.
4. WHEN распознавание успешно THEN система SHALL не отправлять стандартную фразу «не вижу вложение» и не эскалировать только из-за аудиоформата.

### FR-4: Ответ и передача менеджеру

**User Story:** Как менеджер, хочу получать только обращения, где требуется человек, и видеть распознанный контекст.

#### Acceptance Criteria

1. WHEN распознавание завершено THEN система SHALL использовать существующие каталог, FAQ, историю и правила эскалации при формировании ответа.
2. IF менеджер перехватил диалог THEN система SHALL не начинать платное распознавание и не отправлять автоматические ответы; состояние SHALL перепроверяться после ожидания блокировки и перед доставкой, включая отложенную очередь.
3. WHEN распознавание/загрузка не удалось THEN система SHALL дать честный fallback с предложением повторить отправку или подключить менеджера.
4. WHEN уведомление менеджеру не доставлено THEN система SHALL не утверждать клиенту, что обращение успешно передано.

### FR-5: Включение и ограничения

**User Story:** Как владелец, хочу контролировать доступность и расходы на обработку медиа.

#### Acceptance Criteria

1. IF распознавание выключено или не настроено THEN система SHALL не обращаться к его внешним API и использовать прежний fallback для вложений.
2. WHEN вложение превышает согласованные лимиты количества, размера или длительности THEN система SHALL отклонить распознавание до отправки поставщику и объяснить ограничение.
3. WHEN запросы приходят часто THEN система SHALL ограничить число распознаваний по клиенту и общую параллельность, включая сообщения без текста.
4. WHEN поставщик возвращает usage THEN система SHALL фиксировать его без содержимого вложения, персональных данных и секретных ссылок.

### FR-6: Точное видео истории, на которую ответил клиент

**User Story:** Как клиент, хочу спросить «сколько стоит?» в ответ на видеоисторию и получить ответ с учётом именно этой истории.

#### Acceptance Criteria

1. WHEN webhook содержит ответ на историю THEN система SHALL сохранить `reply_to.story.id`, доступную ссылку и текст клиента, не теряя связь между ними.
2. WHEN история принадлежит подключённому аккаунту и её видео доступно THEN система SHALL получить полный видеофайл, связанный с конкретным идентификатором этой истории; превью, случайный ролик или приблизительное сопоставление SHALL не подменять его.
3. WHEN полный файл получен THEN система SHALL учитывать выбранные кадры и видимые на них надписи вместе с вопросом клиента. Аудиодорожка видео SHALL не извлекаться, не расшифровываться и не передаваться поставщику распознавания.
4. IF точный файл недоступен, история истекла, идентификатор отсутствует либо изображения недостаточно для ответа THEN система SHALL честно уточнить контекст или передать менеджеру, не заявляя, что просмотрела ролик. Отсутствие звука SHALL не препятствовать обработке видео.
5. BEFORE включение этой возможности THEN проверка на реальном ответе клиента SHALL подтвердить цепочку `webhook story.id → эта история → полный видеофайл` и обработку недоступного видео.
6. Под «полным видеофайлом» понимается опубликованная версия, которую возвращает Instagram; идентичность исходному файлу до обработки Instagram не предполагается.
7. WHEN извлекаются кадры видео THEN система SHALL использовать согласованную базовую выборку: один кадр каждые 1,5 секунды, начиная с начала ролика (`t = 0; 1,5; 3; …`, пока `t < длительность`). Интервал SHALL быть настраиваемым с начальным значением 1,5 секунды. Это заменяет предложенные ранее два кадра в секунду; дополнительные проходы и отбор по сменам сцен пока не утверждены.

## Non-Functional Requirements

### Performance Requirements

- WHEN принят корректный webhook THEN система SHALL подтвердить приём, не ожидая скачивания, распознавания или AI-ответа.
- WHEN внешняя обработка превышает настраиваемый timeout THEN система SHALL прекратить ожидание и выполнить fallback; целевые timeout и лимиты согласуются в дизайне.

### Security Requirements

- WHEN скачивается вложение THEN система SHALL проверять источник и каждый redirect, блокировать localhost/приватные адреса и ограничивать реально прочитанный объём, не доверяя только расширению и Content-Length.
- WHEN распознан текст с командами сменить роль/правила THEN система SHALL трактовать его как недоверенный клиентский ввод, а не системную инструкцию.
- WHEN обработка завершена или завершилась ошибкой THEN система SHALL удалять временные локальные файлы; логи SHALL не содержать байты медиа, токены или URL с секретными параметрами.
- IF выбирается внешний поставщик THEN его доступность для сервера/аккаунта и условия обработки данных SHALL быть проверены до включения в production.

### Usability Requirements

- Ответы клиенту — на русском и текстом. Результат распознавания учитывается в истории с указанием происхождения.

### Reliability Requirements

- Ошибки загрузки, распознавания, ответа и уведомления SHALL различаться в логах.
- При повторах доставки SHALL сохраняться порядок частей ответа одному клиенту.

## Constraints and Assumptions

### Technical Constraints

- Проект: Python/FastAPI, текущая текстовая обёртка DeepSeek, SQLite, Windows-сервер.
- Исходники: src/channels/instagram.py:105-147 (metadata), src/main.py:1154-1177 (dispatch).
- Пост/Story/Reel не равнозначны прямому image/audio-вложению: поддержку определяет реально доступное содержимое события.
- Установка библиотек, новые аккаунты/ключи и production-деплой в этом этапе не выполняются. Для отдельно разрешённого локального опыта ниже допускается один пробный вызов DeepSeek; широкое включение фичи ещё не разрешено.

### Business Constraints

- Объём первого этапа, поставщик, бюджет и лимиты требуют согласования.
- Чтение персональных документов и их автоматическая обработка не входят в предложенный первый этап.

### Assumptions

- Выбор пользователя: для видео использовать только кадры с обязательной точной привязкой к истории; расшифровка звука видео исключена. Это не одобрение всех требований и не разрешение на production-деплой. FR-3 про отдельные голосовые сообщения остаётся в черновике.
- Получение полного файла двух собственных активных видеоисторий проверено на аккаунте; реальный webhook ответа клиента ещё не проверен. Evidence: `evidence.md` в этой папке.
- Распознавание даёт сведения о вопросе; каталог остаётся источником коммерческих условий.

## Success Criteria

### Definition of Done

- [ ] Объём и требования утверждены.
- [ ] Дизайн и задачи утверждены до реализации.
- [ ] Фото с подписью, голосовое, нечитаемое изображение, отсутствие речи, неверный URL и лимиты проверены.
- [ ] Реальный ответ клиента связан с точным полным видео истории; недоступное/истёкшее видео обрабатывается честно.
- [ ] Повтор webhook, несколько связанных событий, перехват менеджером и порядок доставки проверены.
- [ ] Текущие тесты и Ruff проходят после реализации.
- [ ] На согласованных образцах проверено реальное распознавание без записи секретов в артефакты.

### Acceptance Metrics

Автоматические проверки должны подтверждать все детерминированные AC. Качество распознавания и длительность на сервере оцениваются на согласованных тестовых образцах; численные обещания до такого замера не делаются.

## Glossary

| Термин | Значение |
| --- | --- |
| Распознавание | Извлечение текста/описания из фото и кадров видео либо речи из аудио |
| Fallback | Ответ при невозможности обработать вложение |
| Перехват менеджером | Пауза автоматических ответов после ручного ответа |

## Requirements Review Checklist

- [x] Есть сценарии успеха, ошибок, повторов и вмешательства менеджера.
- [x] Поставщик не объявлен выбранным без согласования.
- [ ] Подтверждены первый этап, лимиты и бюджет.
- [ ] Получено явное одобрение требований.

## Research Evidence — 2026-10-08

1. DeepSeek: https://api-docs.deepseek.com/guides/vision/ — официальная документация прочитана. На текущем ключе проверен один запрос `deepseek-flash` с изображением: HTTP 200, видимые надписи распознаны корректно; evidence — `trial-results.md`. Production-конфигурация `deepseek-chat` не менялась и её работа с изображениями не проверялась.
2. Изображения Gemini: https://ai.google.dev/gemini-api/docs/image-understanding — официальная документация прочитана.
3. Аудио Gemini: https://ai.google.dev/gemini-api/docs/audio — официальная документация прочитана.
4. Регионы Gemini: https://ai.google.dev/gemini-api/docs/available-regions — Беларусь отсутствует в опубликованном перечне; поставщик не выбран.
5. Локальная расшифровка: https://github.com/SYSTRAN/faster-whisper — официальный репозиторий реализации Whisper, включая CPU/INT8. Производительность на сервере проекта не измерена.
6. Собственные видеоистории: live read-only проверка Meta Graph API v25.0 на подключённом аккаунте, 2026-10-08; результаты и пределы вывода — `evidence.md`.

## Micro Spec: локальная проба видео (2026-10-08)

**Type:** ограниченный исследовательский опыт, менее одного дня. Авторизация: пользователь «давай пробовать» после согласования точного видео, отсутствия обработки звука и интервала 1,5 секунды. Это разрешение на локальную пробу, а не утверждение полной фичи. Первоначальная отправка 17 кадров в DeepSeek была отклонена до выполнения. После обсуждения повторяющихся надписей пользователь ответил «давай» на конкретное предложение отправить первый кадр вместо всех 17: разрешена одна пробная отправка `frame-000.jpg` в DeepSeek API на существующем ключе.

**Status:** локальная проба завершена: 17 кадров извлечены через 1,5 секунды, первый кадр отправлен один раз, DeepSeek корректно прочитал постоянную надпись. Evidence: `trial-results.md`. Полная фича остаётся draft.

### Intent (What + Why)

Получить одно конкретное доступное видео собственной истории аккаунта, извлечь его кадры через 1,5 секунды и проверить их понимание одним запросом DeepSeek Vision на существующем ключе. Показать кадры и сопоставить ответ модели с видимыми надписями, чтобы оценить пригодность выбранной частоты.

### Boundaries (Files + Out-of-scope)

Files: `scripts/video_story_trial.py`, `scripts/extract_story_frames.ps1`, эта секция требований и `trial-results.md` в текущей папке спеки. Локальные артефакты опыта — в выделенной папке артефактов текущего чата, вне Git-репозитория.

Production, `src/`, `.env`, сессии и сообщения клиентам не изменяются. Звук не извлекается. Установки, новые ключи, сообщения людям и деплой не выполняются. Исходный временный MP4 удаляется после извлечения кадров. Собственные кадры/контактный лист и отчёт сохраняются локально для проверки владельцем, токены и подписанные URL не сохраняются.

### How

Read-only Graph API: проверить подключённый аккаунт, получить доступные собственные истории, загрузить одну VIDEO по точному ID с лимитом размера и проверкой CDN-источника. Использовать существующий локальный декодер; если FFmpeg отсутствует, для опыта допустим встроенный Windows Media API без установки. Выбрать кадры в моменты `0; 1,5; 3; … < длительность`, сохранить время каждого кадра; не добавлять отбор по сценам. После просмотра контактного листа повторяющиеся рекламные надписи проверяются одним прямым запросом `deepseek-flash` с первым кадром (`--frame-index 0`) и синтетическим вопросом клиента. Это ручной выбор кадра для опыта, не реализованный автоматический отбор по тексту. Автоматические повторы платного запроса выключены. При сетевом timeout исход запроса считать неизвестным и не повторять автоматически.

### Acceptance

- Подтверждены конкретный story ID, длительность, полный файл и извлечение последовательности кадров с интервалом 1,5 секунды.
- Есть локальный контактный лист с временными отметками; никаких аудиозапросов.
- Пробный запрос Vision либо дал проверяемый ответ с usage, либо записана конкретная безопасная ошибка; секреты не попали в логи/отчёт.
- Указаны фактические затраты/usage и время одного запроса, если API их вернул; цены без проверки не вычисляются.
- Ответ модели проверен по исходным кадрам; ограничение «реальный webhook ответа клиента ещё не проверен» явно сохранено.
- Утилиты проходят проверку синтаксиса и относящийся к ним lint; приложение не изменено.

### Upgrade-гейт

Если опыт требует установок, изменений production или разработки интеграции, остановить расширение его объёма и вернуться к согласованию полного дизайна/задач.

## Micro Spec: проверка локального отбора по тексту (2026-10-08)

**Type:** локальный исследовательский опыт менее одного дня. Авторизация: пользователь «проверь второй вариант, на то что это вообще возможно». Полная интеграция фичи остаётся draft.

**Status:** локальный опыт завершён; техническая работа OCR и группировки подтверждена, безопасное сокращение всей рекламной информации на этих 17 кадрах с Windows OCR не подтверждено. Сохранение изменений проверено на синтетических читаемых карточках. Evidence: `ocr-trial-results.md`.

### Intent (What + Why)

Проверить возможность локально распознать надписи на уже извлечённых 17 кадрах, сгруппировать повторяющийся рекламный текст и сохранить кадры с новой информацией. Измерить фактическое сокращение и обнаружить ошибки, чтобы не обещать непроверенную экономию.

### Boundaries (Files + Out-of-scope)

Files: `scripts/ocr_story_frames.ps1`, `scripts/select_story_frames.py`, эта секция и отчёт `ocr-trial-results.md` в текущей папке. Изображения, OCR-результаты и выбранные кадры — в существующей локальной папке артефактов чата. Не менять исходные 17 кадров, `src/`, `.env`, production и настройки ОС. Не выполнять установки, новые вызовы DeepSeek или другие платные API. Не обрабатывать звук и не отправлять клиентские сообщения.

### How

Использовать существующий локальный OCR Windows, если он поддерживает русский язык. Получить текст и координаты строк на всех 17 кадрах; проверить полный кадр и возможность отделить постоянную рекламную надпись от меняющихся вывесок в фоне. Группировать по нормализованному тексту, сохраняя различия в числах и существенных словах; при неоднозначном OCR не удалять кадр. Представителя группы выбирать по полноте распознанного текста и резкости. На отдельном локальном контрольном изображении/фикстуре проверить, что смена даты, цены и условия остаётся новой группой; не менять исходные кадры. Показывать экспериментальные пороги/области и не объявлять настройку на одном ролике универсальной.

### Acceptance

- Есть реальные локальные OCR-результаты всех 17 кадров, время обработки, число выбранных кадров и контактный лист результата.
- Для результата явно проверены сохранение «9–13 декабря», трёх городов и условия «для туристов с визами»; обнаруженные пропуски/ошибки OCR отражены честно.
- Контроль смены цифр и условия не объединяется с исходным текстом; пустой или явно неполный OCR не объявляется безопасным повтором.
- Разделены выводы о технической возможности локального OCR и о качестве автоматического отбора без ручной области изображения.
- Утилиты проходят синтаксис/линт и полезные локальные проверки, новые платные API не вызываются.

### Upgrade-гейт

Если нужны установка OCR-языков/пакетов, изменения сервера или внедрение алгоритма в бот, не выполнять их в рамках этой пробы. Отдельно согласовать расширение объёма; не считать успех локального опыта утверждением production-дизайна.

## Micro Spec: сравнение качества DeepSeek на другой истории (2026-10-08)

**Status:** опыт завершён: два HTTP 200, основная надпись сохранена обоими режимами; low выдумал имя аккаунта, original ошибся в счётчике видео. Входные токены уменьшились на 50,6%, расчётная полная стоимость этих ответов на 29,4%. Evidence: quality-trial-results.md. Авторизация: «проверь на всех меньших качествах», затем «возьми другую историю с другим текстом». В текущем API единственный пониженный detail — low; high и auto эквивалентны original по официальной документации Vision. Разрешены два платных запроса: original как контроль и low на одном кадре другой собственной истории.

**Intent:** проверить сохранение нового рекламного текста при пониженном detail, фактические usage, время и стоимость относительно original на том же кадре. Использовать другое собственное видео, ID 18130692049755620, если оно ещё доступно; до отправки визуально подтвердить отличие текста. Каждый запрос содержит только самостоятельный вопрос и новый кадр, без прежней переписки.

**Boundaries:** минимальная правка scripts/video_story_trial.py для выбора detail и отдельного результата/маркера low; эта секция и quality-trial-results.md. Артефакты — новая папка текущего чата. Не менять старые результаты, исходные кадры, src, .env, production. Не устанавливать пакеты, не обрабатывать звук, не отправлять сообщения клиентам. Не повторять автоматически платный запрос после ошибки или неизвестного результата.

**How:** получить точное собственное видео существующим безопасным fetch, извлечь кадры с шагом 1,5 с, проверить текст и выбрать один полный кадр. Выполнить по одному original и low с одинаковым промптом и параметрами, сохранив HTTP/usage/время/detail/хеш кадра. Временный MP4 удалить после успешного извлечения. Сопоставить даты, города и существенные условия вручную по новому кадру; одинаковые ответы сами по себе не являются доказательством памяти модели. Кэш токенов учитывать отдельно от числа токенов.

**Acceptance:** новая история и иной текст подтверждены; два результата либо безопасные ошибки сохранены; указаны полнота текста, фактические токены и вычисленная стоимость по текущему тарифу; различены экономия входа и общая цена с выходом. Синтаксис/линт утилиты проходят. Обобщения о всех историях и внедрение в бот не выполняются.

## Micro Spec: диагностика связи ответа с видеоисторией (2026-10-08)

**Status:** живая проверка завершена: два реальных ответа связались с двумя точными VIDEO 18130692049755620 и 17951100675316673, отдельно проверена IMAGE 17915481735467392. Полные MP4 получены по ID из webhook, декодированы и совпали по хешам с ранее проверенными роликами; фото с 220 € тоже совпадает с другой историей. Read-only verify подтвердил кадры и границы вывода. Диагностика выложена и активна; локально и на сервере 289 тестов и Ruff проходят, backup сохранён, health ok. Старые синтетические строки в логах не учитывались. Evidence: story-reply-diagnostic-results.md. Авторизация: пользователь «давай» на план временной диагностической правки, её выкладки на сервер и проверки двух ответов на разные истории; «+» на подтверждение Cloudflare Access. Полная media-фича остаётся draft. Согласованная будущая схема: 10 равномерных кадров всего видео, detail original, один запрос с вопросом клиента; в этой микрозадаче распознавание не внедряется.

**Intent:** наблюдать ID конкретной истории в реальном подписанном webhook и затем проверить получение полного собственного VIDEO строго по этому ID на двух различных активных историях. Входящее событие должно оставлять безопасную диагностическую запись даже при отсутствии текста или реакции.

**Boundaries:** src/channels/instagram.py, тесты диагностики в tests/test_instagram.py, описание в docs/ARCHITECTURE.md и эта секция плюс story-reply-diagnostic-results.md. На сервере разрешены проверка текущей версии, сохранение резервной копии единственного изменяемого production-файла, доставка этой минимальной правки, проверки и штатный перезапуск RestartTravelBot с проверкой health. Не устанавливать зависимости, не коммитить/пушить, не менять .env, БД, клиентские сессии, авторизацию и подписи. Не посылать клиентам тестовые сообщения самостоятельно, не выполнять новые платные AI-вызовы.

**How:** в receive_message для reply_to.story dict до раннего выхода реакций писать instagram.story_reply.context: message mid, числовой story_id при валидном формате, признаки наличия/валидности ID и наличия непустой URL. Не писать URL, исходный payload или текст сообщения. Допускаются только ASCII-цифры в ID длиной до 32 символов; неправильный тип/значение фиксируется без сырого значения. Обычная обработка сообщений, реакции, manager takeover и дедупликация остаются прежними. Сопоставить серверную версию исходного файла с локальной базой до замены; при расхождении подготовить минимальную правку именно серверной версии, не затирать посторонние изменения. Пользователь отвечает с другого аккаунта на две разные истории, после чего читать только диагностические записи и получить exact media по наблюдаемым ID. Временные видео извлекаются и удаляются как в предыдущих пробах.

**Acceptance:** meaningful reply, реакция и отсутствие текста дают безопасную запись; обычный DM не даёт story diagnostic; неправильные/отсутствующие ID и URL не ломают обработчик и не раскрывают содержимое; существующие события и поведение не меняются. Тесты и Ruff проходят локально и на сервере. Факт выкладки подтверждён хешем файла, штатным рестартом и health. Сквозная связь остаётся «ожидает реальных сообщений», пока два сообщения не сопоставлены с правильными полными видео; не выдавать синтетические тесты за live Meta доказательство. Откат — восстановить сохранённый файл и штатно перезапустить сервис; после проверки удалить временную диагностическую вставку отдельной согласованной правкой.

**Расширение проверки (2026-10-08, до правки):** серверный полный прогон выявил падение существующего test_notify_manager_success: тест обнуляет secondary/tertiary, но наследует production extra_chat_id и получает два вызова вместо одного. Добавляется минимальная правка tests/test_telegram_notify.py: изолировать extra_chat_id, bot_token и основной chat_id фиктивными значениями для сценария одного чата, сохранив assert_called_once и отдельный тест дополнительных чатов. Этот тестовый файл также разрешено доставить с backup после сверки серверной базы. Production Telegram-сервис и настройки не меняются. Ошибка assertion вывела токен из конфигурации; дальнейший SSH/test вывод маскируется до возврата инструмента, токен не сохраняется в отчётах. Изменение/отзыв токена не выполняется без отдельного разрешения.
## Micro Spec N4: окно сбора Instagram-сообщений (2026-10-09, до кода)

**Status:** deployed: local 500 pytest PASS; server 498 PASS/2 JPEG-artifact skips, Ruff PASS; 15 SHA verified, backup-batch, PID 3964 → 11532, local/public health ok. Live повтор N4 ожидается. Авторизация: пользователь предложил 5 секунд перед DeepSeek и попросил удалить прежние обходные правки template. Ошибка: текст с телефоном внутри обычного сообщения и пустой generic приходят разными POST; прежний кеш учитывает только phone-only и допускает вторую Non-text эскалацию. Read-only log probe подтверждает 11:04 UTC: второй POST через 1,16 с, generic.elements=[] и отдельная Non-text рассылка. Прежние N1/N1b cache/temporal suppress требования ниже — история реализации, отменены N4.

**Intent / acceptance:** N4.1 — после signature/MID dedup собирать пользовательские события одного sender 5 секунд от первого события, без продления, до AI/Telegram/client reply; Meta получает 200 сразу. N4.2 — текст + действительно пустой generic template в любом порядке дают один текстовый запрос; пустая карточка не становится невидимым вложением, все MID защищены от retry. N4.3 — обычные тексты объединяются по порядку; самостоятельные содержательные карточки, неизвестные вложения и точные story/image/shared sources сохраняются; позднее сообщение открывает новое окно. N4.4 — разные sender независимы, manager echo обрабатывается сразу и отменяет ожидающий пакет, действующие session/processing locks и takeover сохранены. N4.5 — убрать 30-секундный phone cache, user_contact_duplicate и прежнее подавление fallback по AI timestamp: окно сбора заменяет эти обходы. Нормализация реального номера и защита current input остаются; при нескольких phone-only строках текущим считается последний номер. N4.6 — regression + полный pytest/Ruff локально и в изолированном server stage, guarded backup/hash/restart/health; live проверка только по реальным сообщениям пользователя.

**Boundaries / how:** src/main.py (per-sender asyncio collector, прежний dispatcher после flush), src/channels/instagram.py (raw events + stateless merge), соответствующие tests и существующие spec/docs/runtime. Не менять подписи, флаги медиа, .env, БД, лимиты уведомлений, зависимости, paid API; без commit/push. Не отправлять тестовые сообщения людям. Истории с разными ID не объединять; empty generic без соседнего содержательного текста остаётся существующим fallback. Откат — backup изменённых файлов и штатный guarded restart. decisions.mjs в этом репозитории отсутствует; схема зафиксирована здесь, CLI не имитировать.

## Micro Spec M1: story mention как изображение (2026-10-09, до кода)

**Status:** deployed; local 515 PASS/server 513 PASS+2 JPEG-artifact skips/Ruff PASS; 15 SHA verified, backup-mention, PID 11532 → 11672, local/public health ok. Live mention ожидается. Авторизация: пользователь «story mention должна передаваться как и фото, но с пометкой что это story mention». Использовать существующий IMAGE pipeline и IMAGE_MEDIA_ENABLED, fixed 5-second collector. Входящий attachments.type=story_mention с payload.url сохраняет источник и отдельный тип контекста. Vision получает original изображение и явную пометку «story mention — клиент упомянул наш аккаунт в своей истории», вместе с соседним вопросом; без вопроса — распознавание и краткое уточнение. Пометка сохраняется в текстовой истории, URL/base64 туда не попадают. Обычные изображения, story reply, Reels и meaningful template не менять. При неправильном/неизвестном URL/неизображении — честный image fallback без AI; не считать видео картинкой или обложкой. Flag off сохраняет прежний non-text путь. Merge должен сохранить тип упоминания, все изображения/вопросы/MID и отдельные story reply ID, не переносить пометку на посты/обычные фото.

**How / acceptance:** узкие изменения src/channels/instagram.py, src/main.py и src/ai/prompts.py; структурная image context пометка передаётся отдельно от текста клиента до system/media prompt и history, сохраняется при merge. Проверить typed payload, отсутствие URL, оба порядка соседнего текста, mixed photo+mention, off/failure/takeover/MID и один vision request с marker. Full pytest/Ruff, read-only review, docs/runtime/manifest. Продолжение ранее разрешённого rollout: guarded backup/stage QA/hash/restart/health; .env/БД/лимиты/зависимости не менять, без commit/push/ручных paid calls/сообщений людям. Live только реальная отправка владельца. decisions.mjs отсутствует; архитектуру не расширять, существующий media service переиспользовать.

## Micro V1 cleanup (2026-10-10, до удаления)

**Status: complete.** Владелец выбрал GigaAM для дальнейшей интеграции. Whisper/Parakeet trial engines удалены с сервера:27targets и8exclusivepipcache files,4700191930logicalbytes. 27privateevidencefiles сохранены/hashverified локально до удаления; архив/копии снятых результатов на сервере также удалены. Protected6582SHA, production17manifest/launcher/.env/requirements и исходные аудио unchanged; GigaAM offline speech+silence/pipcheckPASS, PID2984 и local/publichealthok. Remaining exclusiveSTT wheel/metadata cache scan empty. V1d остаётся pending, production voices не включены. Факт: runtime/gigaam-server-cleanup.md.

Intent: по явному решению владельца дальнейшая работа ведётся с GigaAM. Полностью удалить с сервера установленные для сравнения Whisper small/medium/large-v3-turbo и Parakeet: отдельные окружения, модели/кэши, portable runtime/архив и относящиеся к ним trial helpers/логи. Это очистка испытаний, не внедрение голосовых и не перезапуск production.

Boundaries: разрешённые targets — проверенные потомки deployment helper directory, отдельные HTTP pip-cache записи только при подтверждённой принадлежности пакету Whisper/Parakeet. GigaAM model/runtime/audio/evidence, исходные собственные аудио, Instagram download probes, production files/.env/data/launcher/processes, общие Hugging Face/pip caches и существующие production Torch/ONNX не удалять. Сначала сохранить частные отчёты снятых моделей вне сервера; не архивировать веса. Перед recursive Remove-Item проверить абсолютные пути, отсутствие reparse points, ожидаемые файлы и отсутствие активного trial process. Не удалять неожиданные файлы без уточнения.

Acceptance: разрешённые удалённые targets отсутствуют; GigaAM пять файлов модели/окружение и исходные аудио совпадают по SHA и offline silence smoke проходит; production source/launcher/.env hashes и listener PID прежние, local/public health ok; удалить только подтверждённые STT cache records; перечислить оставшиеся ограничения и фактический размер удалённых файлов. Локальные отчёты сравнения сохраняются, V1d интеграция остаётся pending. Existing decisions/validate_micro CLI отсутствуют; выбор владельца фиксируется здесь без установки инструментария.

## Quick V2: GigaAM incoming voices (2026-10-10, до реализации)

Авторизация: владелец выбрал GigaAM, после очистки подтвердил «+» следующий этап подключения голосовых; уточнил «+ вызов менеджера сразу» при ошибке; затем явно «Да, выложить и включить». Реализация использует существующие пятисекундный пакет/DeepSeek/сессии/менеджерский перехват. Другие STT модели не возвращать. Status: complete, production enabled, full714PASS/Ruff/native worker+application client+production smoke/source/env/launcher/local+publichealth PASS; fresh owner Instagram voice14:16UTC recognized (Сербия) and answered, manager_last_at=null. Early own echo bug reproduced/fixed per bugfix.md before live retry; authorized test pause reset preserved history/count3. Факт: runtime/gigaam-voice-integration.md и runtime/instagram-early-echo-takeover.md.

- V2.1: WHEN включён VOICE_MEDIA_ENABLED и webhook содержит audio THEN сохранить bounded payload.url/MID/caption/story metadata без signed URL в логах/истории. При выключенном флаге прежний unsupported flow сохраняется. Audio-only MP4 с MIME video/mp4 — голосовое, не direct VIDEO.
- V2.2: WHEN тексты/несколько audio/поддержанные visuals приходят в одном fixed5s window THEN сохранить порядок текстов/расшифровок, все MID и источники, отправить один общий DeepSeek request (vision при visuals). File/product/unknown контент не поглощать в supported voice batch; сохранять прежний fallback. Phone templates/GIF/dedup не ломать.
- V2.3: Local pinned GigaAM FP32 CPU в отдельном resident child process,2intra/1inter/no-spin, один concurrent job; bounded queue8, wait30s, execution90s. До3audio, каждый≤10MiB/суммарно≤20MiB, общая декодированная речь≤180s. Model offline verifiedSHA; PyAV16.1.0 decode→mono16k float32. Обработка >25s отдельными≤25s перекрывающимися блоками с удалением только совпавшей границы текста; не обрезать речь/не выдавать замер как гарантию точности.
- V2.4: WHEN download/decode/STT/пустой transcript/лимит обработки не позволяет прочитать голосовое THEN без DeepSeek немедленно вызвать существующее уведомление менеджеру с краткой человеческой причиной+typed context и попросить повторить голосовое/написать текстом. Не выдумывать transcript/контакты; текущие takeover/escalation-limit сохраняются. Notification failure — честный ответ с контактами, не «передал».
- V2.5: Guard typed text до STT и весь recognized request до AI; превышение1000symbols не truncate, понятный fallback+manager. Takeover проверять до/после slow stages и перед notify/send, queued job перепроверять после ожидания. Cancellation/timeout/shutdown завершает только свой worker и убирает own temp audio; следующий запрос может запустить worker заново.
- V2.6: Сохранять в history только recognized words/человеческие media markers; номер с явным + и валидными цифрами из текущей расшифровки имеет приоритет перед номером модели/истории. Не конвертировать неоднозначную диктовку в угаданный телефон. Short escalation context остаётся≤450символов. Audio из story/direct VIDEO не расшифровывать.
- V2.7: QA parser/ordered batch/mixed media/MID/takeover/failures/phone/worker protocols/longform/cleanup; full pytest/Ruff; реальные сохранённые собственные AAC/MP4 и M4A проходят новую интеграцию на сервере без paid DeepSeek/messages. Подготовить guarded rollout/rollback и dependency/settings manifest до production включения.

## Quick N7: подтверждение эскалации по факту (2026-10-10, до кода)

Авторизация: «исправь» после обсуждения неподтверждённого «передал ваш контакт». Status: complete, deployed;754PASS/Ruff/review,21production SHA/env/launcher/local+publichealth, server mocked proof. Evidence: runtime/telegram-handoff-receipt.md. N7.1: подтверждение текущей передачи добавляет программа после успешного Telegram acknowledgement, а не модель. N7.2: успех минимум одной configured доставки HTTP200+JSON ok=true; partial failures логируются, полный сбой/невалидный ответ не увеличивает счётчик и не подтверждает передачу. N7.3: лимит3/no-attempt/failure не допускают утверждения о новой передаче; limit явно говорит об отсутствии нового уведомления, timeout/error — об отсутствии подтверждения. N7.4: сохранить полезный ответ, URL/контакты и отправленный текст в истории; phone-only/вопрос+телефон/голосовые/обычные и unsupported fallback ответы проверены, не менять существующие лимиты и данные. N7.5: убрать конфликтующие prompt-команды о передаче; новые сообщения не копируют прошлые подтверждения. Модель оставляет только служебный marker, когда допустимо; обещание без marker перехватывается защитой, не становится само по себе командой на внешнюю отправку. N7.6: red regressions/full pytest/Ruff/review, bounded3file deployment и rollback/source hashes/env/health; server proof без реальных внешних сообщений.

## Quick N8: три Instagram исправления (2026-10-11, до реализации)

Status: N8.1/N8.3–N8.6 deployed; N8.2 pending proven discriminator. 791PASS/Ruff/review,21SHA/env/launcher/local+publichealth/deployed mocked proof PASS; см. runtime/instagram-business-context.md. Три read-only субагента выполнили независимые проверки по явной просьбе владельца. N8.1: WHEN attachments.type=story_mention THEN существующий manager handoff молча, без AI/media/client response/queue на любом outcome; guard/takeover/MID/limit3 сохраняются. Это отменяет прежний M1/M2 vision-маршрут mentions, но не story replies. Соседний самостоятельный вопрос не поглощается silent event.

N8.2: Collaboration invitation только при доказанном discriminator. Владелец явно отверг broad unsupported_type. Старый screenshot event: unsupported_type/no text; Graph reread exact MID200/from+id, attachments200/count0. Нельзя назвать это распознанным invite или менять все unsupported карточки. Эта часть pending: нужен доступный отдельный признак нового реального события. Story mention выполняется независимо.

N8.3: Передавать sanitized referral через merge→dispatch→AI отдельно от текста клиента. Заголовок рекламы — недоверенные данные, не caption/действующие цены. ad_id не IG media ID. Точное post_id/permalink из referral использует existing shared resolver; photo_url/video_url — только приватные данные предоставленного рекламного материала, не гарантия полного исходного поста. Все media guards/original/10frames/oneAI сохраняются. Разные ADS источники за5s не подменяют друг друга; voice/photo/plain companions сохраняют свой контекст. В историю и логи не записывать signed URL/bytes/ad payload.

N8.4: Конкретное объявление screenshot получено07:35Z как ad_id120255819105930322/title «Рилс ВДП Рождество». Read-only exact permalink DeI-3NiA_5L →post_unavailable; Marketing GET exactad→HTTP400/code100/GraphMethodException. Не выдавать доступ к этому полному видео за доказанный. Доступный title передавать сейчас; неизвестные подробности уточнять без догадок. Не менять permissions/tokens/accounts.

N8.5: Явное предложение сотрудничества — допустимое деловое обращение. Поблагодарить, уточнить суть одним вопросом если деталей нет, при деталях не переспрашивать. Не отказывать «только туры», не согласовывать условия компании, не добавлять неуместный хвост. Marker/brief context и N7 receipts/limit/error сохраняются. Обычные туры и защита от prompt injection unchanged. Prompt tests + mocked delivery не выдаются за гарантию конкретного live LLM wording.

N8.6: meaningful red→green parser/batch/silent/ads/prompt/integration, full pytest/Ruff/read-only review, existing guarded backup/source/manifest/env/launcher/restart/health/mocked server proof. No installs/paid trial/manual external messages/DB reset/commit/push. Pending invitation discriminator и недоступное exact ad video должны остаться честными ограничениями в status/evidence.

N8.6 extension before repair: первый полный прогон обнаружил отсутствующий mock нового silent handler в legacy batch fixture и реальные тестовые Telegram уведомления BATCH_CLIENT. Все pytest тесты должны блокировать реальные HTTP transports; ASGI/MockTransport сохраняются. Исправить fixture и проверить network guard до следующего полного прогона. Mention имеет приоритет над emoji/story-reaction и подавляет всю исходную карточку, включая смешанные вложения; соседние отдельные сообщения сохраняются.

Quick N9 (до кода): supersedes N8.5 business interpretation. Владелец уточнил: сотрудничество не при чём, исправить странную формулировку и маленькую букву. Восстановить прежние business/security/escalation/media rules из N7 verified backup; common style rule SHALL требовать заглавную букву в начале предложения и содержательное продолжение вместо пустого «с радостью подскажу». Ads/mentions/current receipt и ограничения сохраняются. Acceptance: policy constants equal N7; rule present in plain/media/limit prompt variants; honest outcome regressions/QA/server guarded1file rollout PASS. Не выдавать mock/prompt test за живой ответ модели.

N9 status: complete/deployed.794PASS/Ruff/review, policy SHA-verified equality,1file backup/21server SHA/env/launcher/local+publichealth/deployed mocked proof PASS. BASE отличается от N7 только common style rule; SECURITY/ESCALATION/ACTION неизменны. N8.5 cooperation interpretation отменена.

Quick N10 discovery (2026-10-11): owner asks to find exact ad recognition path after N8 access failure. Research/read-only spike: determine configured token kind/granted permissions and sanitized exact error; check whether supplied exact permalink lies beyond the old300-item scan; verify ad→creative→original asset route using official docs. No production source/settings/auth/permissions changes, external messages/paid AI installs or data resets. Diagnostic artifacts only; never print token, raw debug response, signed media URL or client text. Evidence must distinguish exact-source recovery, optional preview, hypothetical permissions route, and current access limitations. Any feature implementation follows a separate approved/Quick Spec contract after evidence.

N10 fact: configured token is valid PAGE, scopes exclude ads_read/ads_management; exact ad returns100/33. Published media lookup exhausted8pages/767items with no exact supplied shortcode. Official supported route: separate adaccount User/SystemUser credential→ad_id/creative→video.source or adimages exacthash, then existingdecoder10originalframes/oneAI. Source not yet retrieved; adding ad access requires explicit authorization, current bot messaging token stays unchanged. Research limitation: Meta pages429, primary docs accessed viaContext7 and SDK25; no claim of universal access/dynamic creative exact variant.

Quick N10 authorization extension (2026-10-11, before setup): owner explicitly authorized separate read-only advertising access. Configure only ads_read for the Sundita advertising account, preserve messaging credential and campaigns, and verify exact ad120255819105930322→creative→original asset. Human login/2FA remains with owner when needed. Store any new credential separately without emitting it, signed URLs or raw credential-bearing UI in reports. Acceptance: granted scope/account and exact original video verified, or concrete authentication/asset-access blocker documented; no guessed match or preview presented as full video. No production bot feature rollout until actual access/source evidence is available.

N10 setup status: owner completed emailed verification. Separate Employee Sundita Reader61595313984712 has adaccount ANALYZE and exact app TEST only. New token issued after selecting ads_read/60 days; actual /me/permissions returns only ads_read and public_profile. Live Graph Explorer v26.0 proves ad120255819105930322 belongs to account2748504208879634 and creative1392757435898637 matches DeI-3NiA_5L. FB video.source is denied code10. Existing PAGE token at v25.0 reads effective IG media17947642536299061 with exact permalink and VIDEO media_url: full valid MP46595346bytes/26.966667s downloaded, native10originalJPEGframes verified, no audio extracted. Source IG18125669482848686 returns a different permalink and is rejected before download. Read-only source proof completed; existing env/launcher/21runtime files unchanged and bot healthok. New ads credential remains private in official Meta/Explorer handoff tabs, not installed in bot configuration; automatic advertising resolver is not implemented/deployed by this spike. Local copied MP4 SHA matches server report; inspected frame shows Варшава–Дрезден–Прага,9–13декабря,260€.

## Quick N11: постоянная обработка рекламы (2026-10-11, до кода)

Статус: реализовано, выложено и включено 2026-10-11. Evidence: 813 pytest PASS/Ruff PASS, read-only review clear; server guarded apply/verify exit0, 22 runtime hashes and public /health enabled/ready; exact supplied ad video→10originalframes/caption617, token debug expires_at=0/ads_read+public_profile. Voice/photo/ad combined request, fallback and manager takeover verified in isolated mocks. Actual client messages/paid AI not invoked by proof. Tasks N11a–d complete.

Owner: «теперь надо внедрить это навсегда». Использовать доказанный N10 маршрут для всех новых откликов ADS с валидным ad_id, а не хардкод одного объявления. N11.1 WHEN feature enabled THEN exact ad→account guard→creative→effective/source IG candidate с exact permalink guard→existing decoder/10originalframes/caption и вопрос клиента в одном vision-запросе; без расшифровки звука. N11.2 Media и голосовые текущего пакета сохраняются, manager abort и общие ограничения действуют. N11.3 Неверная identity, чужой adaccount, недоступная реклама, expiry/невалидный token не должны приводить к догадке по заголовку или thumbnail; честный существующий media fallback + менеджер, без утечки исходников/секретов. N11.4 Отдельный credential file вне Git, независимый от PAGE messaging token; флаг defaultoff, account/config validation; таймауты и startup access health проверены. Никогда не обещать бессрочный доступ вопреки отзыву/сроку Meta: долгоживущий токен требует отдельной фактической проверки/подтверждения выпуска. N11.5 meaningful MockTransport/handler regressions, fullpytest/Ruff/read-only review; guarded rollout с backup/откатом/manifest/health и no-send server proof. До итогового permission шага подготовить конкретный проверенный код. Существующие кампании/диалоги/лимиты/паузы не менять.

## Quick N12: реклама из нескольких кабинетов (2026-10-11, до кода)

Статус: N12.1/2/4 выполнены и выложены; N12.3 частично, actual incident owner/source unresolved. Approved ANALYZE grants К/С plus Б verified; token sees3.825pytest/Ruff/review PASS; guarded2file/config apply/verify exit0,22hashes/newPID/publichealth ready and known exact video10frames verified. Exact incident120252331324000736 remains400/100/33 and filtered ads empty in all3, so incident recognition is not fixed. Pending owner cabinet or View ad link.

Incident: exact ad120252331324000736 at 21:35 returned Meta400/code100/subcode33; current Reader sees only Б2748504208879634, exact Ads Manager B filter no result. This error alone does not establish owner/deletion. Owner explicitly approved ANALYZE-only Reader access to К281443326930624 and С294605942712824; no personal user grant/campaign changes. N12.1 keep legacy single account config, add explicit bounded CSV allowlist for approved accounts; validate all identities, reject malformed nonempty config, foreign ad account before creative. N12.2 same token/Page identity/permalink/video/frame/onevision/abort guards; startup check all configured accounts, no discovery of unapproved accounts. N12.3 reproduce exact incident read-only after grant, prove actual owner and full media access; no client replay/reset or paid AI. N12.4 meaningful regression tests, full QA/review and guarded deployment preserving all unrelated config/state/credentials. If media still inaccessible, report exact safe stage instead of claiming fixed.

## Micro N13: порядок фото и рекламного контекста (2026-10-11, до кода)

Статус: complete, deployed;842pytest/Ruff/review and server apply/verify22hashes/newPID/publichealth/exactpost image/mockpipeline PASS. Source priority limited to full standalone incoming shared_sources, Marketing exactad fallback only for safe unavailable reasons; guards/partial-source/history regressions verified. No client replay/paidAI. Marketing ad-ID-only access unresolved.

User supplied exact publication Dci_ZT0s-3b and screenshots of visual recognition followed by advertising fallback. Local reproduction confirms photo without referral followed by text ADS referral in same5s batch splits into two; reverse order merges. Fix asymmetric segmentation: first referral attaches to preceding same-sender batch, different explicit referrals still split. Prefer available full incoming post as specified below. Preserve5s window, silent boundaries, texts/MID/order and strict ad/media guards. No inferred ad→publication registry, new grants, client replay/reset or paid AI. Regression both orders/differentads/silent boundaries/source priority; fullQA and guarded two-file deployment. Exact supplied publication lookup is read-only evidence, not proof of Marketing ad ownership.

N13 evidence extension before main implementation: incident shared source17943390366326685 GET200/IMAGE matches exact Dci_ZT0s-3b, but published767-item list excludes it. Log confirms shared post first, visa question ADS second, two dispatches. WHEN shared post and ADS question merge in same batch THEN resolve full incoming post using existing strict shared guards, process question against that source without redundant Marketing dependency. Do not label this as Marketing-proven ad mapping. IF full incoming post unavailable THEN try existing exact Marketing source alone; if both fail retain honest manager fallback. No photo/thumbnail substitution or broad swallowed error; other media/voice/oneAI/takeover/safety unchanged. This supersedes single-file rollout scope: channel+main, two files. Ad_id-only unresolved incidents remain unresolved.

## Micro N14: полное чтение рекламных кабинетов (2026-10-11, до изменения доступа)

Статус: approved fourthasset ANALYZE assigned/UI/API4readsverified.8exactads still3sourcepreparationsPASS/5Meta100/33; all4deletedInsights empty. Additional explicitlyapproved personalaccount UI offers firstcampaignsetup. New cabinet did not recover5sources; production config unchanged, no unsupported ownership/deletion claims.

Owner requests stable general advertising support. Read-only audit of8observed real adIDs found3accessible exact sources and5Meta100/33. Original disabled Сандита1744084415894610 exists but Reader lacks assignment; no inferred ad ownership. Owner explicitly approved ANALYZE-only assignment to that account. Grant only this task; repeat all8exactnodes/creative/permalink/source and actual media preparation. IF asset read and source proofs pass THEN add explicit fourth account to existing bounded allowlist and restart with env backup/hash guard; existing scopes/token/messaging/campaigns/client data unchanged. No broad personal access/account reactivation/paidAI/client replay. Evaluate unavailable IDs honestly; approved asset grant is not proof of source access. Document stable fullpost→exactMarketing routes and gaps; clicked-asset fallback remains a separately testable improvement if needed.

## Micro N15: медиа из самого отклика ADS (2026-10-11, до кода)

Статус: implemented/deployed2026-10-11.17new regressions/859fullpytest/Ruff/reviewPASS,3fileguardedapply/verify/22hashes/envpreserved/newPID/publichealthready. Actual known same-ad video/photo decoder10/1proof and isolated routesPASS. Real webhook URLpresence not yet observed;5oldinaccessibleIDs remainunresolved. No paidAI/clientmessages/replay.

Owner requests stable general advertising support. Actual4-account read/source audit still3/8accessible;5exactIDs100/33, all4deleted Insights queries empty. Additional authorized personal-account UI offers first campaign setup. Do not infer their owner or broaden permissions. Code currently ignores provided referral post/image/video whenever ads_media_enabled and ad_id present. WHEN ADS referral contains supplied fullpost identity THEN try existing strict shared resolver; next use actually supplied video_url (preferred) or photo_url with existing download/decode guards; finally exact Marketing ad source. Continue only on source availability errors, never swallow identity/size/format/security guards. No guessed thumbnails/title-to-post registry. Clicked asset is explicitly labelled as provided advertising media, not proof of full original creative or complete carousel. Preserve onevision with customer question/other media/voice,10originalvideo frames, managerabort/privacy/limits. Meaningful route/failure/guard/combined-pipeline tests and fullQA before guarded rollout; no new credentials/client resets/paidAI/sends.

Primary evidence: https://developers.facebook.com/documentation/instagram-platform/webhooks/examples documents ads_context_data.photo_url/video_url for clicked advertising media; URL presence/full file availability is not guaranteed. Individual old5IDs remain unproven unless actualsource later succeeds.

## N16: обязательное чтение рекламы — повторная диагностика (2026-10-11, до реализации)

Verified status2026-10-12:3file micro-fix deployed/888testsPASS/22SHA/env preserved/newPID/healthready; real Elbrus10originalframes and truthful named/vague/takeover pipeline verified. Independently proved4inaccessible-ID→post associations via official Inbox/latestreferral correlation; C creative index exposes their effective IG IDs, own IG GET exact permalink/fulloriginal preparationPASS. Together with previous3accessible sources,7of8observed originals proved readable. Source discovery is not an implemented runtime registry. Older120252486000910736 cannot be inferred from that client's newer120252331324000736/Viewad. Universal opaqueID→publication auto-binding unproved. Proposed exact adID/IGID/permalink/original archive requires complete new-ad registration/updates; not claimed enabled. Evidence:runtime/instagram-business-context.md N16/n16-full-originals-proof.json.

Owner reports new23:41–23:44 ADS failures including explicit tour names Elbrus and Warsaw-Berlin-Poznan. Investigate actual new referral payload presence, exact ad owner/source/API response, and official Instagram-promoted-media/account discovery alternatives. Current objective is source recovery for all company advertisements; do not present another unproved route or tests alone as restored real access. Separate bug: explicit customer catalog question must not be blocked just because attached advertisement is unavailable; preserve truthful unavailability and existing guard/voice/manager behavior. First capture bounded safe metadata only, no raw webhook/private conversations/signedURLs/tokens; no new grants/install/paidAI/clientreplay/messages without exact authorization. Update concrete design/tasks before any runtime implementation. Existing runtime N15 remains active until a verified replacement is ready.

N16 concrete micro-fix (2026-10-12, до кода): observed current Elbrus ad120252561601750736 has a readable exact Marketing source, while supplied video_url stops N15 with invalid_media_url. Official full webhook example explicitly describes video_url as THUMBNAIL_URL_FOR_THE_AD_VIDEO; supersedes N15's full-video assumption. Prefer proven incoming fullpost, then exact Marketing original; only after availability failure consider supplied photo_url as an image. Never decode video_url as a video or describe its preview as the full creative. Existing identity/account/download/format/carousel guards remain terminal for media. Add safe URL classification diagnostics only (HTTPS/CDN/permalink/invalid, never full URL).

If only ADS media failed and no independent visual companion exists, a question explicitly naming a current catalog destination/title may still use the ordinary text model with catalog plus explicit unavailable-ad status. This is a separate text answer, not recovered advertisement. Vague questions still ask clarification and call manager. No video/thumbnail facts, prices or identity inferred from ad title; regular contact/AI escalation/receipts and takeover remain. Invalid optional ADS URL never downloads or enters the model; independent known-catalog text can still be answered. Other identity/format/size/completeness guards do not take this route. Source recovery for the five inaccessible IDs remains an open investigation, not a condition falsely marked achieved by this fix.

## N17: автоматическое восстановление рекламного источника (2026-10-12, до spike)

Owner rejects manual advertisement registration because campaigns are operated by management. Supersedes N16 proposed manual/new-ad registration workflow. Find and prove an automatic exact incoming referral.ad_id→actual original source route, using existing read-only access. Consider official Business Suite visible-UI automation only if it can prove the exact incoming advertisement rather than the latest different ad in a conversation. No inference by title/tour/approximate image, no hand-maintained mapping, no unapproved broader permissions/persistent browser credential storage/install/campaign writes/clientreplay/paidAI. A fully automatic source index/cache is allowed as an internal implementation detail; people registering ads is not accepted. Existing N16 runtime stays unchanged during investigation.

Verified investigation status: not implemented; universal exact automatic binding remains unproved. Owner has no company Instagram login, so that browser route is unavailable and the unrelated saved profile was not used. Existing Facebook Business Suite remains readable. Four original associations were recovered there in N16, but the current UI has one latest-ad link and no per-message interactive View ad link; old910 must not receive newer331's source. Official Ad/Boost probes,589 ads across four accounts, maximum historical Insights with two positive controls, message shares for all five failures, and exact preview for failed331 did not recover missing identities. Recorded logs contain220 text referrals for the five IDs and zero standalone referral events; only three have photo URLs. No alternate company IG actor found. Absence/100/33 does not prove deletion or ownership. Evidence: runtime/instagram-business-context.md N17 and isolated n17 identity/insights/context/preview-message reports. No new permission grant, runtime deployment, client send or paid AI was performed in N17.

Identity review requires a visible exact Ad ID or source link bound to the incoming message before automatic cache insertion. A stable latest MID/adID before/after reading the global header does not prove header freshness. Case-specific original retrieval must not be described as a proved general automatic binding algorithm. Runtime N17 implementation remains open; bot public health is enabled/ready, with no N17 source deployment.

## Micro N18: молчаливая передача рекламных откликов (2026-10-12, до кода)

Status: complete, deployed.31newcases/919fullpytestPASS/8existingwarnings/Ruff/diff-check/source+rollout review. Two-file guarded backup/apply verified by22runtime hashes/env/credential/launcher preservation, newPID5188→11348 and local/publichealth enabled/ready. Staged and installed same mocked silence/named/visa/error/limit/takeover/card/standalone-dedup scenariosPASS; no real client replay/messages or paid model calls. N17 universal source recovery implementation is deferred under this new owner policy. Evidence: runtime/instagram-business-context.md N18 and n18-applied.json.

Intent: owner explicitly changes policy: any ADS referral goes to manager silently unless the actual customer request/recent confirmed dialog makes the request understandable without guessing the advertisement. A known destination/title such as «Эльбрус» and an independent explicit catalog/visa-support request are exceptions and follow the ordinary answer pipeline. An ad title or readable ad media alone is not customer context. This supersedes N16's clarification/failure reply for vague advertising and pauses N17 universal source recovery implementation.

Boundaries: main.py routing/silent notification and instagram.py standalone-referral preservation only, plus meaningful tests/spec/evidence. Reuse existing silent Story mention handoff, per-customer serialization, session locks, manager takeover, confirmed delivery/count limits and private-source rules. Existing original decoder/voice/STT/non-ad messages, media guards and five-second batching remain. No new dependencies, credentials, scopes, manual ad registry, paid trial, client replay/reset or external manual notification. An unanswered standalone ADS is its own event boundary; neighboring independently meaningful messages remain processable. Current phone must be supplied to manager from current customer text, never an older contact.

Acceptance: vague ADS—including accessible creative, title-only, no question, notify failure/limit/username failure—causes zero DeepSeek/media download/client send/queue; at most one actual notification attempt and count only after success. Known current catalog subject or independent explicit general tour/visa-support request proceeds normally. Recent named dialog may clarify a follow-up only for the same exact ad ID with a server-recorded customer-derived context, within12hours and without an intervening unrelated customer turn; unknown/different ad and raw ad titles never establish context. Recognized voice text participates before advertising media lookup; STT failure in unclear ADS is also a silent handoff. Standalone ADS preserves receipt identity and is not merged into the neighboring plain question. Different ads, normal media/voice and manager takeover regressions pass. Before authorized source-only deployment, full pytest/Ruff/read-only review and guarded backup/manifest/env/new-process/health/mock proof pass; no real client messages are sent by tests.

## Quick N19: DeepSeek решает понятность рекламы (2026-10-14, до кода)

Status: complete, deployed.33new regression cases/952fullpytestPASS/8existingwarnings/50.61s/Ruff/diff-check/source+rollout reviewPASS. Guarded two-file backup/apply/22SHA/env/credential/launcher preservation verified, newPID11348→8456/start2026-10-14T11:21:16Z/local+publichealthok. Staged and installed13mocked scenarios/standalone boundary+dedupPASS. No live paid AI/client replay/reset or real manual external messages; real semantic quality remains unverified by mocks. Evidence: runtime/instagram-business-context.md N19/n19-applied.json.

Intent: owner explicitly requires every eligible ADS customer request to reach DeepSeek and asks the model to decide whether it is understandable. Supersedes N18 lexical/catalog/abbreviation/history clarity gates. One existing model call performs both understanding and answer generation. Vague ADS remains a silent manager handoff after the model decision; no bot clarification/refusal/greeting. Current customer text, normal history and catalog are authoritative; inaccessible advertising is not invented. «ВДП» means Варшава–Дрезден–Прага; inflections such as «в Прагу» are understood semantically by the model, not by a local word-prefix list.

Boundaries: main.py and ai/prompts.py, tests and spec/evidence only. Remove local clarity functions and future ad_dialog_context writes; preserve ordinary non-ad behavior, original-media bounds/security guards, takeover, rate/input protections, one request per eligible merged event and existing receipt/count rules. Even a missing advertisement, standalone ADS, no numeric ad ID or unsupported ADS card reaches the model with truthful availability context. Media guard failure does not forward rejected bytes to the model; only safe text/status is available. Voice still uses GigaAM; when recognition fails, tell the model that audio is unavailable, never invent transcript. Files/products retain human-only handling after the model call. No new dependencies/scopes/credentials/session reset/client replay/manual external notifications/live paid trial. Existing account/production media deployment authorization persists.

Acceptance: model receives both actual screenshot questions and vague/unknown/novel-direction requests regardless of catalog substring match. A validated ADS-only response envelope decision=answer sends its ordinary answer (existing service/contact escalation remains); decision=handoff sends a bounded gist to managers and no client response/queue on success/failure/limit. Invalid envelope, empty/malformed/model failure falls back to silent handoff after at most one call. Model handoff may not be overridden by phone-only acknowledgement. Current actual phone remains authoritative, never a historical/model-only guessed contact. Standalone ADS remains a receipt/merge boundary but now invokes DeepSeek. Paused/unsafe/rate-rejected requests retain protections and are not clarity-classified. Full QA/source review/guarded staged+installed mock proof precede source-only rollout; model semantic quality is not falsely claimed from mock tests.

## N20 read-only source investigation (2026-10-14, before probes)

Owner asks for reliable exact creative recovery for Instagram View ad requests.
Revisit primary Meta documentation and actual screenshot conversation, distinguish
one readable source from universal coverage. Compare the current resolver for the
verified screenshot ad with one previously inaccessible ID; inspect existing
subscription metadata only if useful for a newly documented automated source.
No production code/configuration/client-data changes, new permissions, paid model
calls, messages, or speculative ad-to-post mappings. Report exact source evidence,
unresolved identity/access gaps and bounded new candidates honestly.

N20 result: read-only investigation complete; universal retrieval requirement
remains unresolved. Actual screenshot ad120255819105930322 resolves to exact
DeI-3NiA_5L video with10frames/649caption characters on the installed server.
Prior failure120252331324000736 still100/33; exact-oid activities returns zero
rows across four accounts in the checked three-month window, with a successful
three-row positive control. Official comments webhook can supply an explicit
ad_id/original_media_id pair, but only on a corresponding comment event and is
not universal or implemented. Evidence: runtime/instagram-business-context.md
N20 and safe n20-source-check/n20-activities-check reports. No runtime changes.

## N21 read-only permissions investigation (2026-10-14, before probes)

Owner requests an official API/permissions explanation, rejecting comment-based
source indexing. Inspect current Meta requirements and existing token metadata,
asset assignments and minimal Ad reads with positive controls. No new grants,
credential rotation, production configuration/code edits or client messages.
Differentiate app access level, token scope, asset task and ad identity. Record
only safe metadata; no tokens, signed URLs, secrets or client conversations.

N21 result: audit complete, underlying ad access unresolved. Current valid
ads_read SYSTEM_USER sees four accounts and reads two controls, but failed331
id-only remains100/33. IG scopes reside on separate PAGE token; official IG
requirements describe a combined permission set for BM-assigned Page roles.
New documented IGMedia boost_ads_list is ACTIVE-only, unlike the rejected
comment index; bounded live probes returned no mapping with existing tokens.
Do not claim ads_management is necessary or that combined scopes will fix331.
Evidence: runtime/instagram-business-context.md N21 and three safe n21 reports.

N21 follow-up authorization (2026-10-14, before issuance): owner approves a
temporary Facebook USER token for confirmed Danila profile with ads_read,
instagram_basic and pages_read_engagement, used only for company diagnostic
GETs. Preserve production credentials/configuration and existing grants; stop
before any consent that would revoke prior bot permissions or expand beyond
the approved read scope. Compare failed331, working Ad and original-media
controls; do not describe a successful token issuance as an access fix.

N22 outcome: authorized combined USER test completed. Original shared PAGE
grants briefly lost pages_messaging/pages_manage_metadata during Explorer flow;
restored and verified server-side before continuing, with approved ads_read also
propagated. Original token values/config not replaced. USER reads working Ad and
returns exact organic18125669482848686→ad120255819105930322 boost mapping, but
failed331 still100/33 and four problematic publication fields return no mapping.
Production page/IG/subscription/health GETs pass. Universal recovery unresolved.
Evidence: runtime/instagram-business-context.md N22 and n22 safe health/restore
reports. No new runtime implementation; do not repeat Explorer Clear on shared
production grants or represent temporary USER tokens as permission-isolated.

## N23 read-only incident investigation (2026-10-15)

Owner requests why two clear ADS queries silently escalated and forbids server
changes. Investigation complete:18:17 «Эльбрус»/10images/output295 and18:58 «Виза
есть! Пришлите программу тура ВДП»/1image/output288 both successfully invoke vision,
then log instagram.ad.invalid_model_decision and notify managers. Installed
sources match expected N19. Raw model response/rejection subtype are not logged;
exact malformed content remains unknown. Vision factory lacks JSON response mode,
while parser strictly requires JSON. No source/config/grant/data changes, restart,
uploaded probe or client/model replay; SQLite read with mode=ro. Evidence runtime
N23 and current bot.log lines1258..1268/1287..1297. No implementation authorized.

## Micro N24: advertising response-contract repair (2026-10-15, before code)

Status: deployed and verified.27new cases/60targeted/979fullpytestPASS
(8pre-existing warnings,37.57s), Ruff/diff check and independent read-only review
clear. Native decoder sandbox failures were resolved by the same tests outside
sandbox using a fresh temporary folder after shared pytest ACL failure; no skip
or decoder/code workaround. Authorized guarded two-file rollout verified by22
runtime hashes/env/launcher/credential preservation, newPID17644 and local/public
healthok. Staged and installed18mocked scenariosPASS. No live paid model validation.

Owner approves the four proposed repairs after N23: request JSON mode for visual
ADS when supported by current primary DeepSeek documentation; normalize only
whole-response JSON Markdown fences; log bounded rejection reason/finish status
without model content; technical manager gist includes actual sanitized customer
question. Intent: prevent valid answers with harmless formatting from becoming
silent generic handoffs while retaining model-owned answer/handoff semantics.

Files: existing main.py, services/llm.py, focused ADS/factory tests and existing
spec/runtime notes. Preserve non-ad vision behavior, strict three-string-field
schema/duplicate-key/size/decision checks, one model invocation, current phone,
notification limit/takeover/silence and original media pipeline. No dependencies,
extra classifier/retry/paid model request, source guessing, token/settings changes
or server mutation/deployment. Approval to implement is not a live rollout.

Acceptance: (1) ADS image and video requests send response_format=json_object;
ordinary visual requests keep their current format. (2) A complete bare JSON or
complete fenced JSON object validates, but prose/partial/extra/duplicate/invalid
fields and inconsistent decisions still reject. (3) Every rejected response logs
a fixed reason code plus safe scalar response metadata only; length finish status
is explicit and never sends a partial reply. (4) Rejection/provider failure gives
manager a concise technical cause and real sanitized current question, without
raw JSON/URLs/phone/response content; customer remains silent. (5) Both observed
queries with1image/10frames, guards, limits, takeover and non-ad regressions pass
under mocks; no live semantic understanding claimed from mocked tests.

Provider evidence: official JSON Output guide explicitly uses deepseek-flash;
Vision guide and Chat Completions schema support image_url with thinking disabled
and response_format=json_object. Existing prompt already contains JSON/examples.
https://api-docs.deepseek.com/guides/json_mode/
https://api-docs.deepseek.com/guides/vision/
https://api-docs.deepseek.com/api/create-chat-completion/

N24 deployment authorization (2026-10-15): owner explicitly requests rollout.
Deploy only main.py and services/llm.py after exact current22-file manifest/env/
launcher baseline verification and isolated staged proof. Back up both files and
manifest, prepare rollback, preserve credentials/client data, then verify new
listener identity/health and installed mocked scenarios. No real model/client
replay or manual messages. Report uncertain restart transport separately from
actual file/process/health verification; do not reapply blindly.

## Micro N25: one empty ADS response retry (2026-10-15, before code)

Status: deployed with N26 and verified. Local:31 new cases/90 targeted/1009 full pytest
PASS (8 pre-existing warnings,36.25s), Ruff/diff/micro-spec check and independent
read-only review clear. Production proof/23SHA/newPID/health verified with N26;
no live paid model validation.
Intent: an ADS request must not immediately become a silent technical handoff
when DeepSeek returns an empty/whitespace-only string. The observed 22:27 case
had empty_response, 242 characters, finish_reason=stop. Existing tests correctly
enforced the former one-call fallback, but did not require recovery.

Boundaries: main.py, focused ADS tests, existing spec/runtime/development notes.
Supersede N19/N24's single-call rule only for this exact failure: retry once
using the same model, prompt and prepared media. No extra classifier, content
repair, dependencies, provider/format/settings changes, live paid probes, replay,
deployment or resumption of the paused inbound-recovery feature. Existing SDK
transport retry settings remain unchanged; maximum two ainvoke calls per eligible
ADS processing attempt (vision transport retries are already disabled).
All other invalid envelopes, truncated responses and provider exceptions retain
the existing fallback. Never repeat a semantic answer/handoff decision.

Acceptance: N25.1 empty/whitespace -> valid answer yields one client reply, no
technical notification, no empty assistant history and no duplicate user entry.
N25.2 empty -> valid semantic handoff yields one concise notification and silence.
N25.3 empty -> empty/invalid/truncated/provider failure yields the existing
technical fallback once, never a third call; limits/current phone are retained.
N25.4 manager pending/active before retry or after either await aborts the result
without further calls/reply/notification; task cancellation propagates.
N25.5 text/image/video ADS retry the identical messages and prepared media once;
ordinary non-ADS paths and non-empty invalid results retain their call counts.
N25.6 retry logs only fixed reason/attempt and existing allowlisted metadata,
never prompt, model content, signed media URLs or raw provider errors. Red/green
regressions, full pytest/Ruff/diff check and independent read-only review required.

Evidence: runtime/instagram-ad-empty-json.md N25 and accepted CLI decision
.kiro/decisions/0002-ad-empty-response-retry.md. The previous one-empty-call test
is superseded by recovery/final-failure tests; all other no-retry checks remain.

## Micro N27: recover malformed ADS response fields (2026-10-16, before code)

Status: verified and subsequently incorporated into N28; old two-file deployment
superseded before production apply. Automatic approval review rejected the original apply. Owner: after confirming invalid_fields remains unhandled,
"ну?". Extend the existing single retry to recover invalid JSON/application schema
without guessing, renaming or dropping returned fields. Both text and vision use
at most two total application-level model calls, including empty-response recovery.
This supersedes N25's no-retry rule only for the explicit repairable format errors.

Boundaries: existing invocation loop in src/main.py, format-only reminder in
src/ai/prompts.py, focused tests and current spec/runtime evidence. Preserve
ordinary messages, schema validation, media identity/preparation, fresh-session
takeover checks, cancellation, current-phone authority, actual delivery receipts,
private response journal and the paused inbound-recovery work. No new provider,
schema guessing, unlimited retries or changes to sessions/settings.

Acceptance: N27.1 invalid_json, duplicate_fields, invalid_fields,
invalid_field_type, invalid_decision, context_too_long, empty_reply and
inconsistent_handoff may trigger one corrected regeneration; empty_response keeps
its one retry. N27.2 second call uses a copied system message with a trusted reminder
of exact decision/reply/context contract; all other original messages/images are
reused and the final user message remains last. Do not send the malformed response
back as instructions or modify original messages/images. N27.3 length truncation,
oversized/non-string responses and provider exceptions do not trigger this retry.
N27.4 a second failure uses existing safe handoff; no third call. Takeover before
or during recovery cancels response delivery and notification. N27.5 log each
response under the same request ID with attempt/reason; ordinary logs contain no
body, prompt, media URLs or secrets. N27.6 red/green regressions, full checks,
read-only review and isolated real API repair checks without client/manager sends.

N27 evidence:29new/146focused/1071fullpytestPASS (8existingwarnings,31.07s),
Ruff/diff/micro-spec checksPASS; source/helper reviews clear. Initial run21RED/
6GREEN before implementation. Three real corrective API calls (two text/one image)
valid after synthetic first invalid_fields/invalid_field_type/inconsistent_handoff
failures. This verifies regeneration, not the historical missing provider body.
Rollback proof and server prepare24SHA/backupPASS. Production apply rejected
before execution for lack of explicit approval; no workaround. Deployed manifest
unchanged. См. .kiro/decisions/0004-ad-json-format-recovery.md (CLI5/6 accepted).

N27 live reproduction, owner "воспроизведи" then explicit max12paid-call approval:
4completed synthetic-text scenarios/6actual HTTP calls through staged full
process_with_ai. Natural provider invalid_fields:decision/reply,missing context,
finish_reason=stop,1198chars. The actual automatic format retry produced valid
decision/reply/context under the same request0694c2f98c6a4c23b92cab47662293e6.
All6wire/AIMessage hashes equal; saved original response pair hashes verified.
Also naturally reproduced388ASCIIspaces -> valid unchanged-prompt retry.
First-prompt AST equals installed production; current catalog/time/emptyFAQ used,
no real client histories/media.24runtimeSHA/PID15500/localhealth unchanged;
0real client/manager sends and session writes. Trial stopped on reproduction.
This proves the failure class/recovery; unavailable historical bodies cannot
establish which exact fields were missing in those older failures.

## Micro N26: DeepSeek response journal (2026-10-15, before code)

Status: deployed and verified;27new/117targeted/1036fullpytestPASS (8pre-existing
warnings,38.72s), Ruff/diff/micro-spec checks and independent privacy re-review
clear. Guarded3-file rollout/23SHA/newPID/local+publichealth/29staged+installed
mockedcasesPASS; no live model trial. Owner: "давай логировать ответы
дипсика". Intent: retain each received textual DeepSeek response before parsing
so invalid_fields can be diagnosed rather than guessed. Include first/second
attempts, ordinary text/vision and ADS; empty whitespace remains distinguishable.

Boundaries: main.py single ainvoke call site, one stdlib journal helper, config
toggle/example, isolated tests/conftest, existing spec/development/runtime notes.
Private local logs/deepseek-responses.jsonl, UTF-8 JSONL; five MiB per segment and
seven archives (~40MiB), 64k characters per response, explicit truncation flag.
This is size-based retention, not seven days. Existing logs/ gitignore applies.
Default enabled by this explicit owner request, disable via configuration. No
prompt/history/request/media dump, external logging service, dependencies, model
calls/replays or source guessing. Initial implementation was local-only; the
separately authorized deployment below includes N25 and N26.

Acceptance: N26.1 every returned response is journaled before manager/validation
gates, with UTC timestamp, per-processing UUID, attempt, SHA-pseudonymized sender,
requested model/route, allowlisted finish/token counts and validation reason.
N26.2 store original textual answer subject to redaction/truncation; invalid JSON
and whitespace survive unchanged when no redaction applies. Non-text blocks and
arbitrary metadata are not serialized. UUID is shared across an empty retry.
N26.3 known configured secrets, credential/Bearer patterns, data URLs and signed
media URLs are redacted before limiting length; sanitization errors omit content
instead of falling back to the raw answer. Unknown arbitrary secrets cannot be
reliably recognized; journal remains server-private and contains client answers.
N26.4 content never reaches stdout/stderr/bot.log; use non-propagating dedicated
handler with safe handleError. Init/redaction/format/emit/rotation errors emit a
fixed safe diagnostic and never change reply/notification/history/retry behavior.
N26.5 stable handler count, UTF-8 single-line JSON escaping, bounded rotation,
off switch, per-test temp log isolation, red/green regression tests, full pytest,
Ruff/diff/micro-spec checks and independent read-only privacy review required.

Evidence: runtime/deepseek-response-journal.md and accepted CLI record
.kiro/decisions/0003-deepseek-response-journal.md. Old provider replies were not
retrospectively recovered; production logging starts only after deployment.

N25+N26 deployment authorization (2026-10-15): owner explicitly says "деплой это".
Deploy main.py/config.py/new llm_response_log.py only, preserving all other22
baseline source entries/env/launcher/ads credentials/client data. Existing N24
baseline22SHA/env/launcher and absent new module verified read-only before code
replacement. Back up existing files and manifest; rollback restores both and
removes only the exact newly created module if it still matches staged SHA.
Run staged/installed mocked recovery/journal/guard proofs with external HTTP
forbidden and journal path redirected to bundle test files. Verify23SHA,new
process identity, local/publichealth and enabled logger configuration. Never
print journal body/credentials or replay a real client; do not reapply blindly
after transport/restart failure. Deploying N25 does not resume inbound-recovery.

N26 deployment fact:29staged+installedcases/boundary+dedupPASS, backup and isolated
rollback proof verified,23runtimeSHA/env/launcher/ads credentials preserved. PID
17644->17148,start2026-10-15T20:52:43Z; local and publichealth200ok. Apply stdout
applied=true/SSHexit1 at restart; independent verifyexit0 confirmed installed state,
no reapply/rollback. Preflight ConsoleRenderer/cp1251 failure fixed in helper only.
No paid model trial or manual messages; production journal is lazy and had no
records yet at immediate post-restart check. Evidence:n26-applied.json and
runtime/deepseek-response-journal.md. Cloudflare app-info timeouts were transport
failures; no session-policy/credential changes were needed.

## Quick N28: единый JSON для всех ответов модели (2026-10-16, до кода)

Status: deployed and verified. Owner: «давай единый json делать.
не будем путать модель». Supersedes the ADS-only JSON and fresh manager-marker
contracts, including N27's ADS-only recovery. One model response format for text,
ADS, images/video/Reels and transcribed voice. Keep deterministic no-model routes.

N28.1 Every model response is exactly {reply:string, manager:null|object}; manager
has exactly context/type/name string fields, context1–450characters, name0–100,
type one of консультация/контакт/отзыв. No model phone/reason/decision fields.
Normal answer: nonempty reply and manager=null. Answer+escalation: nonempty reply
and manager object. Silent handoff: empty reply and manager object, permitted only
for ADS; ordinary requests always get a visible response. Keep ADS semantic rules.
N28.2 All text/vision factories use JSON object mode. Prompt contains one global
contract and structured escalation instructions; no request to produce embedded
service markers. Booking remains a URL in reply. Client sees only reply; history
stores only actual delivered visible reply. Old stored markers are stripped as
defence without migrating sessions; fresh marker-containing reply is invalid.
N28.3 Strict nested/duplicate/type/key validation, bounded two-call recovery on
all routes, terminal truncation/oversize/non-string/provider errors. Retry copies
system reminder only, retains original messages/media and cancellation/takeover.
Second failure: one technical escalation; ADS silent, ordinary honest fixed reply
with delivery-based receipt. Program-generated media/guard/STT fallbacks bypass
model parsing. Existing privacy-safe journal records actual validation per route.
N28.4 Preserve batching5s, media identity/preparation, rate guards, pauses, limits,
actual delivery receipts, short manager summary and current phone from input/STT,
never a guessed model phone. Names may come only from provided conversation.
No unsupported API/storage migration/new dependencies/production mutation.
N28.5 Explicit envelope fixtures (no automatic raw-text-to-JSON conversion),
meaningful red/green parser/pipeline regressions, full tests/Ruff/review. Real paid
checks and deployment require their existing exact authorizations; neither is
implied by this implementation request. Inbound recovery remains paused.

N28 phone/context review additions before their fixes: recognize a unique explicit
international/BY number inside typed text, preserve typed-over-STT priority and
latest standalone phone. In manager summary remove only the known phone from
the same phrase, retain current tour/date/budget; contact-only labels retain the
prior conversation. First-person new request must not be mistaken for a name.
No arbitrary date/budget or ambiguous inline pair may become a guessed contact.

N28 evidence:68new unified regressions,187targeted/1136fullpytestPASS
(8pre-existingwarnings,62.57s), Ruff/diff/reviewPASS. Three real calls through
isolated staged full process_with_ai: reply only, reply+manager, silent ADS,
all valid first attempt with exact wire/AIMessage hashes and semantic effects
asserted.3newcalls+6previous=9of12explicitlyapproved; no further calls. No real
client histories/media/sends/session writes.24production/4stagedSHA, PID15500
and health unchanged. Runtime evidence:runtime/unified-model-json.md. Existing
canonical runtime-manifest still describes installed production, not staged N28.

N28 deployment override and evidence (owner «деплой»,2026-10-16): exact4files
main/prompts/llm/llm_response_log and manifest installed; no configs/client data
changed. Guarded backup5SHA/rollback proof/review/apply/restart/24runtimeSHA,
newPID15716/local+externalpublichealth/installed-validator+factory smokePASS.
Canonical manifest now synchronized to installed N28. First actual post-restart
model response recorded valid; no new paid test calls or manual customer sends.
Server-origin public self-probeCloudflare403 was isolated by client-origin200;
no application rollback or Cloudflare/auth changes were required.
