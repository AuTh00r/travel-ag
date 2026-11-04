# Первый выпуск: выкладка и откат

## Новое разрешение на общий scope — 2026-11-02

После успешного теста02Nov23:30–23:33Минск владелец запросил
«пробуем врубать для всех?». Это новое разрешение на scope=all и штатный
restart; прежний отказ18Oct остаётся историческим. Подготовить свежий config-only
пакет против текущих36runtimeSHA; старый пакет18Oct не применять.
Меняется только INBOUND_RECOVERY_SCOPE; флаги уже true. Перед apply проверить
отсутствие global baseline/активных задач/неопределённых отправок, backup
.env/manifest/SQLite и аварийные flags-off. Общую временную границу создаёт
штатный initialize один раз при новом запуске; baseline тестера сохраняется.
История, паузы, лимиты, terminal tasks и receipts не сбрасываются. Verify:
scopeall, новая общая граница не раньше apply, tester baseline прежний,
36SHA/health и сохранность данных. При выключении рабочую SQLite не откатывать.

Выполнено02Nov23:50Минск. Scopeall/health/36SHA проверены; globalcutoff
23:50:29.795800Минск, testerbaseline прежний. Backup/flags-off/inverse/review
PASS.1311старыхreceipts,8terminaljobs,1761старыхsessionstates сохранены.
После запуска34диалога проверены, очереди/unknown0, свежихerrors/warnings0,
старыечужиесообщениявновыезадачинепопали. Перваяноваязаявкаобычногоклиента
получилаодинподтверждённыйответ(1modelcall). Новыйcaseпокапришёлтолькочерез
webhook; егоAPI-dedupотдельнонеутверждается. Общийcomplete_scanпоканет;
известныйgapснедоступнымучастником остаётся. См.TSK-032.

## Story context и10 минут — 2026-10-20, перед выкладкой

Владелец явно запросил «десять минут и деплой». Пакет
`story-context-10min-20261020` переносит TSK-027 и TTL600с в legacy/recovery:
только `src/db/inbound.py`, `src/channels/instagram.py`, `src/main.py` и
manifest31. Recovery scope остаётся allowlist одного тестера; env/настройки,
baseline/история/паузы/лимиты не меняются. Старые вопросы не переигрываются.
Прежний локальный пакет2мин помечен HOLD, на сервер не переносился.

Проверки:20 focused PASS; полный1533 PASS/8 прежних warnings/68.87с;
Ruff/diff/read-only review PASS. Граница599с сохраняет,600/601с истекает,
duplicate MID не продлевает срок. Код исправляет также ms/seconds mismatch
на поиске story hint; реакция сама не отвечает, receipt/attached логируются.
Guarded offline rollback proof PASS; новые receipts/unknown сохраняются.

Package SHA256
`2473eeb4d2a226e17abf86221e9d322d909deb5a10e2c5e6ebb1eceb8204a8cf`.
Prepare: сверить31 SHA, backup3 source/manifest и SQLite online integrity;
apply: атомарная замена этих файлов, штатный RestartTravelBot. Перед verify
дождаться нового процесса и прежнего готового health. Verify:31 SHA, allowlist/1,
protected hashes/baseline, прежние receipts/terminal jobs/tester session.
Rollback — только source/manifest и restart; БД не восстанавливать.

Факт: prepare/apply/verify exit0. PID12736→5380,
start2026-10-20T12:08:23.3109191Z (15:08:23 Минск);31 SHA/health совпали,
оба installed TTL600с проверены. Scope allowlist/1, .env/credentials/launchers
и baseline сохранены; рабочая БД не заменялась. Сохранены292 прежних sent
receipts, terminal jobs и tester session/revision, active/pending/unknown0.
В первом окне до12:09:15Z warning/error не обнаружено. Живую новую реакцию
и ответ пользователь ещё не проверял; старый вопрос автоматически не повторяется.
Контроль12:10:51Z: новый после restart checkpoint1792498181.0418963,
gap=false/pending=false, scan_failures0, queues0 и warning/error0;
292 receipts/tester session/terminal jobs по-прежнему сохранены.

## Исправление раннего таймера Windows — 2026-10-20, перед выкладкой

Владелец ответил «+» после готового локального фикса TSK-026. Разрешена
выкладка только `src/services/inbound_recovery.py` и обновление installed
manifest31. Recovery/reconcile остаются включены только для прежнего
allowlist одного тестера; .env и область включения не меняются. Локальный
`.gitignore`, тесты и документация на сервер этим пакетом не переносятся.

Read-only preflight:31 SHA совпадают, healthok, scope allowlist/1,
active/pending/unknown-sending0. Candidate diff34 строки, только два timeout
scope;1512 pytest PASS, Ruff/diff/review PASS. На серверном Windows candidate
в памяти отдельного процесса60/60 PASS без API/рабочей БД/внешних отправок.

Пакет `deadline-fix-20261020`: prepare создаёт source/manifest backup и
SQLite online backup с integrity_check; .env/credentials/launchers защищены
hash. Apply меняет один исходник и manifest, затем штатный RestartTravelBot.
Verify: новый PID,31 SHA, прежний health/admin allowlist/1, исходные baseline,
protected hashes. Повторять старые задачи и сбрасывать паузу/лимиты запрещено.
Rollback возвращает только source/manifest и штатно перезапускает процесс;
рабочую БД не восстанавливает. Offline inverse/partial failure/unexpected
edit/envguard proof PASS, новые receipts/unknown сохраняются.

Факт: package SHA256
`e59dfda76602d725512b7eff462b157c1409538167bb88f3f8858157dba4a7f6`;
prepare/apply/verify exit0, manifest31 совпал, PID12960→12736,
start2026-10-20T11:32:34.2955092Z (14:32:34 Минск). Health прежний ok;
.env/credentials/launchers и baseline не изменились. Рабочая БД не заменялась.
Сохранены280 старых sent receipts, terminal jobs и tester session/revision.
Active/pending/unknown-sending0. Checkpoint1792496018.7132478→1792496139.5653467
через120.852с, gap=false/pending=false/scan_failures0; ошибок/предупреждений
за окно до11:35:53Z не найдено. Ручных API/модельных/внешних отправок не было.

Первый verify вернул AssertionError без строки проверки; диагностика показала
новый PID, healthok, protected/manifest PASS. Тот же verify после диагностики
завершился exit0, откат не потребовался. Точный первоначальный assert не сохранён;
причину не приписываем доказанному сбою приложения или startup race.

## Разрешённое расширение на всех — 2026-10-18, до активации

Решение владельца после точного запроса all/restart: «пока не».
Общее включение отложено, разрешения на apply сейчас нет. Сохраняется
allowlist тестового аккаунта; подготовленный пакет не применять и бота
не перезапускать. Возобновление — только после нового явного согласия.

Статус: пакет/backup/proof готовы; apply НЕ выполнен. Автоматическая проверка
одобрения отклонила production apply: предыдущее «деплой» не признано явным
разрешением scope=all. У пользователя запрошено точное согласие на all/restart.
После отказа выполнен только read-only check: phase=prepared, admin allowlist,
env_matches_before=true. Повтор apply без нового подтверждения запрещён.

Пакет recovery-all-20261018 SHA256
`c99f509c5d2dbaec62556e82dfd52fd36d8ba08741dd323ebab852fdfecbceae`;
runtime payload нет, три файла controller/base/baseline. Remote prepare PASS:
online backup integrityok, active/pending/unknown0, global baseline отсутствует.
Offline inverse/envguard/partial-failure proof PASS; rollback сохраняет новые
receipts/unknown, сетевых вызовов и настоящих restart0. Первое падение proof
было из-за CRLF синтетического файла; fixture исправлен на точные bytes,
повтор proof exit0. Независимое review без блокеров, Ruff/diff PASS,
дополнительные46 canary/scanner tests PASS/17.18 с; прежний полный1486 PASS.

После описания рисков пользователь явно запросил «деплой». Это отдельное
согласие на scope=all существующей проверенной сборки. Runtime29 файлов и
manifest не заменять: поменять только INBOUND_RECOVERY_SCOPE=all, оба флага
оставить true; client IDs, интервалы, паузы, лимиты и credentials сохранить.
Новые архитектурные решения не добавляются, действуют прежние ADR baseline/scope.

Предпроверка18:29:32 UTC: 29 SHA совпали, admin allowlist/1, активных jobs0,
foreign active0, legacy pending0, unknown/sending0. Global baseline отсутствует,
тестовая1792174400.304584, scope checkpoint соответствует списку. В трёх
startup файлах нет override scope. Проверки последнего кода1486 PASS.

Подготовить config-only controller с exact .env hash guard, backup env/manifest,
SQLite online backup+integrity_check, проверкой всех runtime SHA и protected
credentials/launchers. На изолированной копии доказать apply и аварийное
выключение с сохранением новых receipts/unknown. Производственную БД helper
не пишет и не восстанавливает. Apply атомарно заменяет .env и запускает штатный
RestartTravelBot; новая global baseline создаётся только самим приложением.

После restart: новый PID/health/admin all, те же29 SHA и protected hash;
новая global baseline между apply и verify, прежняя тестовая сохранена.
Проверить сохранение старых sent receipts и cancelled/failed_final, прогресс
двух штатных тиков, backlog/errors/unknown. Полный обход не обещается за120 с.
Историю периода canary не переигрывать. Ручных model calls/отправок нет.

Откат при ошибке — выключить оба флага текущей версии и штатно перезапустить,
scope/baseline/journal/receipts/unknown сохранить. Старую БД не восстанавливать;
чужие незавершённые задачи отдельно контролировать, не скрывать возвратом allowlist.

## Пагинация, приоритет менеджера и EOF — разрешённая выкладка 2026-10-18

Владелец запросил «деплой» после 1480 PASS/Ruff/diff/review. Пакет
recovery-pages-eof-20261018 заменяет только src/channels/instagram.py,
src/services/inbound_recovery.py, src/services/llm.py, src/ai/prompts.py и
обновляет installed manifest. Переносит TSK-021/022 и Micro N33 вместе;
новых настроек нет. Recovery/reconcile остаются allowlist одного тестера,
tool transport — all. Новая общая baseline не создаётся.

Сверить прежние 29 SHA, scope/health и отсутствие активных задач, подготовить
online SQLite backup и code/manifest backup. Controller прежний code-only:
prepare/apply/restart/verify, rollback только исходников и manifest, без
восстановления старой БД. .env/credentials/launchers защищены SHA. Offline
inverse/partial/unexpected edit proof сохраняет новые receipts/unknown.
После штатного restart проверить новый PID, 29 SHA, health, сохранённые
baseline/паузы/лимиты и свежую сверку без gap. Никаких ручных paid calls,
отправок, сбросов паузы и переигрывания старых failed_final задач.
Живое устранение EOF провайдера не объявляется доказанным; подписи webhook
и недоступные рекламные объекты не входят в этот фикс.

Факт: package SHA256
`73ebd759d74c7183479a4bf1a66215980ef4454e37fe3fdceaf0448c9b181c89`;
четыре файла и manifest, 29 SHA/health PASS. PID6872 → 4136, start
2026-10-18T17:07:35.3779553Z. Env/credentials/launchers защищены и сохранены;
baseline и тестовая сессия (полный hash/revision) неизменны. Online SQLite
backup integrity PASS; code-only inverse/partial/unexpected edit proof PASS,
новые receipts/unknown сохраняются при откате. Installed EOF smoke PASS.
Реальный Meta GET: голова21, after сработал, следующая страница19; ручных
paid calls/отправок0. Первая новая сверка checked_at1792343294.8612587,
through1792342978, gap=false; scan_failures0. Рабочая БД не заменялась;
Второй штатный checkpoint1792343415.1479812 через120.286722 с также gap=false,
scan_failures0; нет активных задач/unknown, legacy pending0, sent receipts132.
старые failed_final не переигрывались. Отказы webhook signature mismatch
продолжаются и не исправлены этой выкладкой.

## Разрешённое исправление scanner — 2026-10-18

Владелец отдельно запросил «деплой» после локальных 1431 PASS, Ruff/diff и
review. Пакет `recovery-scan-20261018` заменяет только
`src/services/inbound_recovery.py` и обновляет runtime manifest; настройки
и scope не меняются: recovery/reconcile true, allowlist с одним проверенным
тестовым клиентом. Проверить исходные 29 SHA, backup исходника/manifest и
online SQLite backup. Защитить `.env`, credentials и startup scripts хешами.
Откат только кода/manifest, без старой рабочей БД и потери новых receipts.
Проверить новый PID/health/29 SHA, затем два обновления checkpoint тестового
диалога на штатных тиках, gap и scan_failures. Не сбрасывать cursor, baseline,
паузы/лимиты; не останавливать production для искусственного пропуска webhook.

Факт выкладки: один runtime-файл, package SHA256
`82a8f43319adbf7777e9da5a9139d7e2c877dacd38a5e71ef88d0181abc9fc35`.
29 исходных SHA и online backup проверены. Isolated inverse/partial apply/
unexpected edit proof PASS; откат сохраняет новые receipts. PID 5320 → 6872,
start 2026-10-18T14:32:03.3013366Z, health прежний ok, 29 новых SHA совпали.
Два priority checkpoint 14:33:05.781909Z → 14:35:06.028029Z (120.246 с).
Все timestamps здесь UTC. `.env`, baseline и тестовая сессия сохранены;
scope allowlist/1, active/legacy pending/unknown=0. Working DB не заменялась.
API read-only coverage check: 21 запись при limit=20, все MID уже в журнале;
gap остаётся консервативной отметкой over-limit ответа, не новым send-сбоем.

Статус: 2026-10-16 разрешён деплой текущей версии для теста @_shelter_0.
Сначала установить с flags off и проверить health, затем включить только allowlist
с одним проверенным ID и снять только его текущую паузу для новых тестов.
Историю, лимиты и отменённые задачи сохранить. Других клиентов не включать.
API-only unsupported voice/post остаются известным ограничением. Приёмника нет.
Не применять deploy.ps1: он делает git commit/push и общую замену файлов.
Установленный runtime manifest не обновлять до успешной выкладки.

## Подготовленный пакет

`scripts/recovery_release.py build --package <новый-каталог>` копирует девять
runtime файлов, manifest SHA, disabled.env, helper и эту инструкцию.
`verify --package <каталог>` проверяет SHA и syntax без импорта приложения.
Отдельно в закрытом каталоге хранятся baseline.json и activation.private.env
с проверенным числовым IGSID тестового аккаунта; токенов в пакете нет.
На сервере в этой фазе ничего не записывается.

## После разрешения на выкладку

Перенести пакет в отдельный staging. `preflight --root <checkout> --package
<staging>` проверяет candidate SHA, оба выключенных флага и SHA текущего
runtime против baseline. Если production изменился — остановиться и сверить
изменения, не затирать их. `backup --root <checkout> --package <новый-backup>`
сохраняет runtime и SQLite online backup с integrity_check; не копировать
один sessions.db поверх работающего WAL. Backup вне checkout, доступ закрыт.
Прежние .env/launcher/credentials сохранить закрыто существующими средствами
rollout; не класть их в payload/публичные журналы.

При штатной остановке заменить только девять файлов manifest, сверить SHA,
оба флага оставить false, запустить штатным launcher. Проверить процесс,
health, обычный webhook/ответ и очередь; историю/паузы/лимиты/FAQ не менять.
До активации допустим откат файлов из backup; новые файлы удалять только
при совпадении candidate SHA и отсутствии в baseline, без recursive delete.

## После отдельного разрешения на тестовое включение

Повторно проверить IGSID через participants; применить только четыре настройки
activation.private.env: scope allowlist, один ID, оба флага true.
Снять только тестовую паузу при согласии; историю/лимиты/отмены сохранить.
Штатно перезапустить. Baseline фиксируется впервые; отправлять новые тестовые
сообщения. Admin endpoint должен показать allowlist/count=1, свежую сверку,
jobs и receipts. Проверить один ответ, одну эскалацию и менеджерский перехват,
без дублей. Падение процесса и пропущенный webhook — только в изолированном
стенде. Unknown не повторять вслепую.

## Откат после активации и расширение

Откат: оба флага false на новой версии, штатный restart. Сохранить journal,
jobs/MID/receipts/unknown/cancellations; private admin показывает их и off.
Безопасный pending bridge продолжает работу. Не откатываться на N28 без
receipt-aware bridge, не заменять sessions.db старой копией: потеряются receipts.
Незавершённые jobs остаются для отдельного решения.

Все клиенты: после успешного теста и нового разрешения scope=all; первая общая
baseline новая, тестовая прежняя. Сбросить только scan traversal/completion,
переписку за время canary не переигрывать. Тайминги 60/120/480/120/5 с прежние.
