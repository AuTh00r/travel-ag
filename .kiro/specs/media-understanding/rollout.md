# Rollout: истории, изображения, публикации и Reels

## N35 View ad/source ADS — text only — 2026-10-22 (deployed)

Owner confirmed only View ad/source=ADS, then explicitly authorized «деплой».
Installed channel/main/inbound/recovery and manifest only; archive SHA256
fe169c3a0b20f0bbf35c967a11add4360979866da5b0ea2f47e878daf43a4c7a.
Local1496PASS, server isolated72PASS with external HTTP denied, exact four-file
controller rollback proofPASS (new receipts/unknown preserved and unexpected
edits refused). Fresh source/manifest and online SQLite backup verified.

PID11436→15408, start17:16:18Z/20:16:18 Minsk. All31hashes and local/publichealth
verified. env/credentials/launchers/recovery allowlist1/first-enable baselines
unchanged;407previous sent receipts retained,408current, terminal jobs/session
revisions preserved, active/pending/unknown0. Installed synthetic parser verifies
ADS text→ordinary user, empty ADS→ignored, separate ordinary photo preserved.
No initial post-restart warning/error. No manual customer/manager sends or paid
model calls; customer-side new ADS conversation was not initiated by this rollout.

Bundle/backup: media-rollout-20261008/ad-text-only-release-20261022. Invoke only
guarded release.py rollback/verify; rollback changes code+manifest, never live DB,
env or launchers. Cloudflare reauthentication succeeded after old banner timeout;
no authorization-policy or session-duration change was required.

## N34 placement creatives — 2026-10-20 (deployed)

Owner «деплой» after local1562PASS/Ruff/review and four exact read-only source
proofs. Applied ad_media.py/story_media.py/main.py and manifest only, package
placement-ad-20261020 SHA256
97ece5426861be89ce1dd6a82466031b2ed5c932d330e6a0bcc073caaefb347f.
Server isolated60PASS; exact guarded controller inverse/partial rollback proof
PASS with new receipts/unknown retained. Fresh source/manifest and online SQLite
backup verified; rollback changes code+manifest only, never DB/env.

PID5380→11436, start17:06:34Z/20:06:34 Minsk.31SHA/local+publichealth verified;
env/credentials/launchers and recovery allowlist1/first-enable baselines preserved.
296sent receipts retained, terminal jobs and session revisions did not regress;
active/pending/unknown0. Installed resolver reads four real ads as twoVIDEO/twoIMAGE
with marketing_variant; no manual model calls or messages. No warnings/errors in
the first54s checked. Client-side response on a new placement referral remains
unverified. Two inaccessible referral IDs100/33 remain separate; exact displayed
variant cannot be inferred without a Meta selector.

Remote artifact/backup: media-rollout-20261008/placement-ad-20261020.
Use only its guarded release.py rollback/verify; do not invoke the imported older
tool_canary_release.py CLI. Rollback refuses unexpected code/config drift.

## N5 contact context — 2026-10-10 (deployed)

Local639 PASS/Ruff/diff-check PASS,12 new cases/read-only review clear.
Prepared contact-context-patch.zip and guarded stage/apply/QA helpers,2 changed
files main.py/test_engine.py,17 before/after hashes. Source: deployed S7 bundle.
Upload initially requested Cloudflare browser login, then completed exit0.
Server isolated QA637 PASS+2 previous JPEG-artifact skips/Ruff PASS; guarded
patch applied, backup-contact-context, all17 SHA verified, listener5292→15292,
local/public health200/ok, three flags true. Docs use docs-story-context baseline.
Rollback2 existing files + prior runtime manifest from backup/bundle-contact-context,
guarded restart/health. No session/limit/config/dependency mutation or paid replay.

## S7 reaction context — 2026-10-09

Applied main/channel/test_instagram/test_inbound_batch after isolated server QA.
Local627 PASS/server625 PASS+2 prior JPEG-artifact skips/Ruff/diff-check PASS;
26 new cases, read-only final review clear. Backup-story-context, all17 runtime
SHA verified, listener10076→5292, local/public health200/ok, three flags true.
No production sessions/counters/history/config/dependencies changed. Rollback:
restore4 files from backup-story-context and manifest-before from
bundle-story-context, guarded restart/health. Live emoji+plain question repeat
still pending; new reaction required after restart because cache is in memory.

Подготовлено 2026-10-08. Выполнено после запроса владельца «деплой»:
story/JPEG/PNG/posts/Reels развёрнуты, три флага включены, backup сохранён.
Ручная платная проверка не выполнялась; live client vision остаётся отдельным шагом.

## Факт выполнения

Micro N1/N2/N1b, 2026-10-09: manager marker без closing delimiter больше не
попадает в visible reply, actual input phone доступен notifier без model field.
Phone-card guards/dedup/MID и safe schema diagnostics. Первый live повтор
показал nested payload.generic вместо flat template; N1b добавлен до кода.
N1b full local 457 PASS, server 455 PASS/2 JPEG-artifact skips, Ruff PASS.
Guarded four-file phone patch и two-file nested patch с backup-phone /
backup-phone-nested, 14 SHA verified; PID 8160 → 13928 → 8992, local/public
health 200/ok. Два latest assistant в тестовом диалоге без service marker.
N3b повтор nested card ожидается. Existing escalation_count=3 и manager takeover
не сброшены, продакшен БД/история не перезаписывались тестами. Для live проверки
использовать другой аккаунт либо явное разрешение владельца на сброс только
двух полей его тестового диалога, сохранив историю и остальных клиентов.

Дополнение N2b: разрешение на reset получено от владельца; сброшены только
escalation_count/manager_last_at одного тестового диалога, backup saved/history
preserved. Следующий live typed phone без карточки не вызвал Telegram: модель
не создала marker, полагаясь на историю. N2b оформлен до кода; current input
phone запускает notifier независимо от marker, short phone-only ack зависит
от факта success/error/limit. Вопрос с карточкой получает приоритет в context.
Local final 466 PASS, server final 464 PASS/2 JPEG-artifact skips/Ruff PASS;
backup-phone-notify/backup-phone-context, 14 SHA verified, PID 8992 → 5048 → 16256,
local/public health 200/ok. Final live повтор после N2b ожидается.

N2c, 2026-10-09: latest live current phone распознан и Telegram delivered,
но владелец заметил старый номер в уведомлении. client_phone уже current;
context/name из AI marker или prior mixed contact могли содержать старый номер.
N2c spec оформлен до кода, regression red 4 FAIL → fix; review greedy contact
с budget/date red 8 FAIL/4 PASS → known spans/strong contact guard.
Local final 478 PASS, server 476 PASS/2 JPEG-artifact skips/Ruff PASS. Initial
contact-source stage не применялся. Final guarded two-file patch с
backup-contact-source-v2, 14 SHA verified, PID 16256 → 2664, local/public health
200/ok. БД/лимиты/история не менялись, ручной paid replay не выполнялся; новый
live номер после N2c остаётся N3b.

Live N3b, 2026-10-09 01:44 Минск: normalized новый номер отличается от всех
предыдущих. Generic.elements=[] card через 1.35 с → empty_duplicate/ignored,
без второго AI/ответа. model_phone_present=false, notifier current input,
Telegram sent четырём configured recipients, один Instagram message.sent,
latest assistant 75 chars/no service marker, counter 1→2/manager_last_at=null.
Точное old Telegram section не прочитано; новый source доказан safe source log,
актуальным input state и regression actual notifier kwargs. N3b completed.

Micro C2/C3, 2026-10-09: exact child/native asset mapping и IMAGE pixel decode
ускорение. Server full 414 PASS/2 JPEG-artifact skips, Ruff PASS; native exact
7-element carousel → 25 original images за 12.562 с (до: 79.594 с), paid calls=0.
Guarded patch только story_media.py/decode_story_media.ps1/test_shared_media.py,
backup-carousel, сверка всех 12 SHA до/после, listener 4388 → 8160, local health
ok, три флага true. Исходный share URL неизвестен; live повтор после fix ждём.
Safe identity diagnostics добавлены для проверки exact источника без URL/payload.
Откат C2/C3: восстановить эти три файла из backup-carousel, прежний manifest
и штатно перезапустить после проверки известных bot parent/child; БД/флаги не менять.

Изолированный server pytest: 401 PASS, 2 SKIP (JPEG artifacts отсутствуют),
Ruff PASS. Native Windows smoke на синтетических серверных MP4/PNG:
VIDEO/IMAGE/VIDEO → 21 изображение по порядку, без сети/AI.
Базовые HEAD/SHA и conftest подтверждены до QA; все 12 deployed SHA сверены.
Backup: профиль deploy.SST/media-rollout-20261008/backup, включает только
прежние заменённые файлы и .env с сохранённым ACL; секреты не выгружались.
STORY_MEDIA_ENABLED/IMAGE_MEDIA_ENABLED/SHARED_MEDIA_ENABLED=true,
DEEPSEEK_VISION_MODEL=deepseek-flash. Штатный restart разрешён только после
native snapshot ровно двух Python-процессов бота с доказанной связью parent/child.
Listener 5512 → 15384, localhost/public /health HTTP 200 {status:ok}.
Отклонённый auto-review архив с тестовым Reels заменён пакетом только кода/тестов;
медиа и .env не передавались с локального компьютера.

## Воспроизводимый план

Micro patch R1 после первого live Reels: фактический type=ig_reel отсутствовал
в allowlist. 2-file patch instagram.py/test_shared_media.py прошёл local 408 PASS,
server 406 PASS/2 skips, Ruff PASS; backup-reel сохранён. Все 12 SHA verified,
listener 15384 → 4388, три media-флага true, local/public health 200/ok.
Первый Reels не анализировался. Повторная отправка владельцем успешно завершила
R2b: ig_reel/reel_video_id → полное Graph media → 10 кадров → один vision
(32617 input/259 output tokens) → Instagram message.sent за 14.4 с.
Прежний payload не сохранялся и автоматически не replayed. Остальные отдельные
live media сценарии требуют T5c; эта проверка относится к одному доступному Reels.

Точный состав runtime (без установок, git commit/push и чужих правок):

- src/config.py
- src/exceptions.py
- src/ai/prompts.py
- src/channels/instagram.py
- src/main.py
- src/services/llm.py
- src/services/story_media.py (новый)
- src/services/decode_story_media.ps1 (новый)

Для server QA: tests/test_story_media.py, tests/test_shared_media.py, tests/test_instagram.py; ранее исправленный
tests/test_telegram_notify.py должен сохранить серверную изоляцию настроек.
Спека/архитектура доставляются отдельно как документация.

Перед копированием сравнить SHA каждого существующего файла с ожидаемым
HEAD 3d6318bb и ранее выложенным instagram.py (SHA
DBC3514702C9D9C31E25AA313E8F030C63C2616E66F5F4661B77F229CD94F694).
Любая другая правка требует разбора, не автоматической перезаписи.
Сделать резервные копии заменяемых файлов и конфигурации в закрытой папке;
конфигурацию/секреты не читать в stdout и не копировать в репозиторий.
Сохранить локальный manifest с SHA новых файлов для точного сравнения.

Порядок: staging → Ruff/full pytest с изолированной БД и новым basetemp
(stdout предварительно очищается от секретных URL/ключей) → реальный Windows
decoder на собственной истории, без AI → перенос проверенных файлов →
STORY_MEDIA_ENABLED=true, IMAGE_MEDIA_ENABLED=true и SHARED_MEDIA_ENABLED=true
в серверной конфигурации → контролируемый restart →
localhost/public /health → один согласованный реальный ответ клиента на историю.
В логах проверять только ID, тип, images=10/1 и числа токенов; не читать payload.
Для plain images — проверить caption/no-caption и несколько фото, `detail=original`,
без автоматического платного повторения. Источники attachments в debug не писать.
Включение нового image-флага также требует авторизации production/paid API.
Shared flag требует той же авторизации. Проверить реальные ig_post/share webhook:
фото-пост, доступный Reels и карусель с вопросом/без вопроса. Сверить точный ID,
полный media_url и 10 кадров каждого видео; обложка не считается исходным видео.
Свой Reels успешно подготовлен локально без AI; server native mixed carousel
также PASS. Shared live payload/платный ответ пока не проверены.
Недоступная/приватная публикация должна дать честный fallback.

Не использовать deploy.ps1: он автоматически коммитит/пушит и устанавливает
зависимости. Существующая RestartTravelBot запускает broad taskkill python.exe:
перед её применением требуется доказать, что затрагивается только известная
пара процессов бота. При посторонних Python процессах использовать адресный
restart только своих PID либо остановиться; MCP-процессы не завершать.
Штатная start-bot.vbs запускает один worker без reload, как требуется декодеру.

Откат: восстановить только перечисленные заменённые файлы/флаг из backup,
убрать только два добавленных runtime-файла и два новых media-test файла при
проверенном соответствии SHA и абсолютных путей внутри корня проекта,
перезапустить адресно и проверить /health. Не откатывать чужие конфиги/БД/историю.
При ошибке AI не повторять платный вызов автоматически: клиенту fallback,
владелец получает безопасный код ошибки для разбора.

## N4 rollout — 2026-10-09

Применены src/main.py, src/channels/instagram.py и шесть соответствующих test
файлов (включая новый test_inbound_batch.py): 8 files, 15 manifest entries.
Server stage 498 PASS/2 JPEG-artifact skips/Ruff PASS; backup-batch, guarded
RestartTravelBot, listener 3964 → 11532, local/public health ok. .env/БД/лимиты
не менялись. Откат: восстановить семь существовавших файлов из backup-batch;
новый test_inbound_batch.py удалять только при совпадении deployed SHA и
проверенном пути внутри корня. Восстановить предыдущий manifest из bundle-batch,
guarded restart/health. Live повтор N4d ожидается.

## M1 story mention rollout — 2026-10-09

Применены src/main.py, src/channels/instagram.py, src/ai/prompts.py,
tests/test_story_media.py и tests/test_inbound_batch.py. Server isolated stage
513 PASS/2 JPEG-artifact skips/Ruff PASS; backup-mention, 15 SHA verified,
listener 11532 → 11672, local/public health ok. IMAGE flag сохранён true,
БД/.env/лимиты/зависимости не менялись. Откат: восстановить только пять файлов
из backup-mention и manifest-before.json из bundle-mention; guarded restart
и health. Live photo mention ожидается; MP4 mention не входит в IMAGE поддержку.

## A2 attachment fallback rollout — 2026-10-09

src/main.py, src/channels/instagram.py and tests/test_attachment_fallback.py
applied after isolated server557 PASS/2 previous JPEG-artifact skips/Ruff PASS.
Local559 PASS. Backup-attachment, 16 SHA verified, listener11672 → 3460,
local/public health ok. No flags/data/limits/dependencies changes or manual
paid API calls/messages. Rollback: restore only two existing source files
from backup-attachment, remove only new known-hash test inside root after
absolute path/hash verification, restore manifest-before from bundle-attachment;
guarded restart and health. Direct video/GIF/audio understanding not added.

## M2 incoming VIDEO rollout — 2026-10-09

Applied main/channel/prompts/story_media and four affected test files, including
new test_incoming_visual_media.py. Local601 PASS/server isolated599 PASS+2 prior
JPEG skips/Ruff PASS. Native local real MP4 mention+direct→20frames without AI.
Read-only review resolved GIF reply and file/story precedence. Backup-visual,
17 SHA verified, listener3460 → 10076, local/public health ok. No config/data/limits
or dependencies mutated. Rollback existing7files from backup-visual and only
new known-hash test within root (verify path/hash), manifest-before from bundle-visual;
guarded restart/health. Real Meta mention/direct VIDEO delivery not yet confirmed.
