# Tasks: синхронизация туров из Google Drive

## Micro 2026-11-02: даты

- [x] DATE-01 Регрессии: подписи/одиночная дата/пробелы/тире, unknown/mixed,
  неверные даты и обратный диапазон, отсутствие извлечения из программы.
- [x] DATE-02 Общий parser, честная доступность, prompt и metadata.
  Факт: initial24RED/8PASS; затем крайние случаи6RED и1RED закрыты.
  Unknown остаётся existing metadata available=null, mixedfuture=true,
  knownclosed=false. Новая схема/изменения metadata кода не понадобились.
  194profilePASS,8raw полностью совпадают со старым каталогом. Golden12
  обновлены только после inverse proof прежних prompt/retry SHA.
- [x] DATE-03 Профильные/полный pytest, Ruff/diff/review;8реальных программ.
  Факт: финальный1792pytestPASS/8прежних warnings/93.22с, Ruff/diff/reviewPASS.
  Новый файл покрывает44случая. Offline8program proof: весь текст каталога
  и ссылки брони byte-equal с прежним parser на2Nov. Пакет2source подготовлен
  локально; production/флаги/база/отправки/платные вызовы не менялись.
- [x] DATE-04 После отдельного «деплой»: guarded2source+manifest rollout,
  backup/inverse proof, restart, SHA/health/каталог/очереди/состояния проверить.
  Факт:02Nov23:12Минск,2source+manifest36, package SHA
  76ed3179a9696104c679024975c3cb1390e63456df318ec8a97ec17da093ca83.
  Backup/inverse/reviewPASS; PID17976→13652,start20:12:17.3907814Z.
  Первичнаяverifyassert во время запуска; последующая verify-diagnose exit0,
  все36SHA/schema/health/env/credentials/baselines PASS. Сохранены1304receipts,
  все1760session states,8terminal jobs. Postflight23:14:24Минск: healthok,
  fresh errors/warnings/tracebacks0, queues/unknown/sending0, testerrefreshed.
  Installed parser smokePASS;8актуальныхrawпересобранытольковпамяти:
  текст и bookingURLs прежние. Recoveryallowlist/1 сохранён, .env не менялся.

| Progress dates | Статус |
| --- | --- |
| Implementation | Готово локально;1792PASS/Ruff/diff/review,8raw без изменений |
| Deployment | Выложено02Nov23:12Минск;36SHA/health/catalog/scope/state проверки PASS |

## Micro 2026-11-01: подписи ссылок

- [x] TSK-024 Разрешённая выкладка2файлов, backup/restart, проверка8ссылок.
  Факт:01Nov13:04Минск, PID428 ->12328/start10:04:34.4087876Z.
  Source/SQLite/catalog backup проверен;2файла, manifest36entries совпадает.
  tour_loader ранее существовал внеmanifest: зафиксированSHA до замены,
  inverse proof проверяет восстановление старого файла, не удаление.
  Local/public healthok, свежих ошибок/warnings0. Все1711прежних sessionstates
  и1131receipts сохранены, env/credentials/baselines/allowlist прежние.
  Штатный sync13:05пересобрал8туров:6 ->8ссылок, прежние6совпали.
  CatalogSHAcd9392afb2acf6c156d9e38c1d392e49638e09d47029b958575fde316458c7bc.
  Ручных modelcalls/внешних сообщений0; deployment-result в артефактах.

- [x] TSK-021 Расширить подписи без учёта регистра, сохранить приоритет явной
  брони и различие сайта/Google-программы в snapshot, bootstrap и тексте модели.
  Факт:28RED ->149profilePASS; общий helper, GoogleDocs/Drive не бронь.
  Legacy split не расширяет границы по общим ссылкам внутри программы.
- [x] TSK-022 Проверить реальные сохранённые оригиналы без изменений сервера.
  Факт: офлайн-пересборка8туров6 ->8ссылок, прежние6совпали; две новые ссылки
  совпадают с найденными исходными URL. Production writes0, paidcalls0.
- [x] TSK-023 Полныйpytest/Ruff/diff и финальное read-only ревью; обновить статус.
  Факт:1728PASS/8прежних warnings/100.37s, Ruff/diff PASS, независимое
  read-only ревью без блокеров. Артефакты booking-labels-20261101.

| Progress booking labels | Status |
| --- | --- |
| Local | 1728PASS, Ruff/diff/review PASS, offline8tour proof PASS |
| Production | Deployed01Nov;8/8booking links, health/schema/36SHA PASS |

## Микроправка 2026-10-29: визовая пометка

- [x] TSK-017 Проверить действующий источник и подтвердить смысл отсутствия
  пометки, записать micro-контракт до правки промпта.
  - Факт: read-only snapshot8/SHA82aa7b12, старые поля отсутствуют; пометка есть
    у Белостока/Варшавы–Берлина–Познани/Варшавы–Дрездена–Праги. Владелец подтвердил
    «Без пометки — помогаем оформить визу»; loader сохраняет исходный текст.
- [x] TSK-018 Заменить правило в общем primary/reviewer блоке, сохранить
  различие визовой поддержки и безвизовости, остальные инструкции не менять.
  - Факт: AST proof — единственная runtime-правка _BASE_RULES;12golden входов
    сохранены, обновлены только хеши промпта/retry. Primary JSON/tools×лимит0/3,
    reviewer и4варианта исходной пометки проверены;95profile PASS. Независимое
    read-only review без блокеров; реальная семантика API этим не утверждается.
- [x] TSK-019 Полный pytest, Ruff/diff, итоговый статус. Production и платные
  проверки — отдельные действия; не выполнять по запросу локальной правки.
  - Факт:1646PASS/8прежнихпредупреждений/82.93s; Ruff/diff PASS. Ручных API/
    клиентских/менеджерских отправок0, productionwrites0. Проверено построение
    промпта и программные маршруты; живая семантика DeepSeek не проверялась.

| Progress 2026-10-29 | Статус |
| --- | --- |
| TSK-017–018 | Локально готово,95профильных PASS |
| TSK-019 | Полный1646PASS, Ruff/diff PASS до отдельной выкладки |

- [x] TSK-020 После отдельного «деплой»29Oct: one-prompt guarded package,
  baseline/sourcebackup/onlineSQLitebackup/inverse proof, штатный restart,
  installedSHA/health/catalog/прежние receipts/scope/env/logs postflight.
  - Факт:package45b62971, exact N38 fallback23e46f24; local/server inverse proof
    PASS, source/onlineSQLitebackup integrity PASS.11164 ->15260/start19:51:19Z
    (22:51Минск). One source+manifest,34installedSHA/33others unchanged;
    local/publichealthok.1660old clients/975old receipts retained; oldtasks0,
    env/credentials/scope/baselines/catalog8 unchanged, fresherrors0. Ручных
    model/client/manager calls0; новый смысловой ответ модели не утверждается.

| N39 deployment | Статус |
| --- | --- |
| TSK-020 | Выложено29Oct22:51Минск; postflight PASS, настройки/данные сохранены |

## Исправление 2026-10-26

- [x] TSK-011 Диагностика источника, автозапуска и эскалации.
  - Факт: Drive8документов, прежний snapshot6туров;2новых DOCX без URL брони;
    воркер тикает300с; BootTrigger/Start=2; модельный manager найден в журнале.
- [x] TSK-012 Включать корректный тур без брони; сохранить прежние приоритеты URL;
  промпт не придумывает ссылку, справка не требует менеджера только из-за URL.
  - Факт: см. .kiro/decisions/0016-catalog-without-booking.md (accepted,6/6).
- [x] TSK-013 Восстановление last-good при начальном сбое и unchanged, enabled.
  - Факт: network/auth/exception/no snapshot/disabled и unchanged current/diverged
    проверены заглушками; нет повторной записи/уведомлений.
- [x] TSK-014 Регрессии, полный pytest, Ruff, diff, независимое read-only ревью.
  - Факт: 1506PASS/8прежних warnings/70.06с, Ruff src/tests PASS, diff-check PASS;
    read-only review без блокеров. Golden12сценариев сохраняет прежние входы.
- [x] TSK-015 Подготовить пакет и серверный dry-run без отправок; явно указать,
  какие изменения ещё не установлены. Production выкладка отдельным действием.
  - Факт:3source+31-entry candidate manifest+откат3source;138строк source.diff
    относительно точных серверных файлов. Отдельный серверный Python-процесс
    собрал8туров из8реальных экспортов,2новых без выдуманных URL,0пропусков;
    publication=false,outbound_messages=0. Рабочие source/env/DB/tasks не менялись.
- [x] TSK-016 Production выкладка3source+manifest и проверка публикации8туров
  после отдельного разрешения. Историю/лимиты/флаги/базовые границы сохранить.
  - Разрешение: прямое «деплой»26октября2026; выполняется проверенная выкладка
    только каталога/запуска. Бизнес-основания эскалаций и recovery scope не меняются.
  - Факт: пакет1dc4d284, remote rollback-proof/backup integrity PASS;
    PID7744→11852,start2026-10-26T16:00:55.3701370Z. Опубликованы8туров/46041символ;
    31SHA/env/credentials/launchers/baselines/allowlist1 сохранены. Все556sent receipts,
    18terminal jobs,1480sessions сохранены; pending/unknown/sending0. Local/public
    health200, startup errors/warnings0. Серверный urllib→public получилCF1010/403;
    независимый внешний запрос200. Данные/правила Cloudflare не менялись.

| Progress 2026-10-26 | Статус |
| --- | --- |
| TSK-011 | Подтверждено read-only |
| TSK-012–015 | Проверено; пакет и source-only откат сохранены |
| TSK-016 | Выложено и проверено26октября; запуск19:00:55Минск |

## Dependency graph

```
TSK-001 (config) ──┬──> TSK-002 (loader: publish+snapshot) ──> TSK-004 (main: worker)
                   └──> TSK-003 (tour_sync) ──────────────────^
TSK-005 (tests) — параллельно с 002–004, зелёный прогон перед TSK-006
TSK-006 (deploy+прод) — после всех
```

## Progress

| TSK | Статус | Факт |
|---|---|---|
| TSK-001 | completed | 8 полей в `config.py`, `.env.example`, `.gitignore`; импорт проверен |
| TSK-002 | completed | `publish_tours_text` + `save/load_snapshot` (tmp+rename); `load_tours()` не тронут |
| TSK-003 | completed | `tour_sync.py` (~380 строк); приоритет брони и rstrip проверены мутациями |
| TSK-004 | completed | воркер + стартовая цепочка + событие готовности; `import OK` |
| TSK-005 | completed | 34 теста, без сети; 2 мутации пойманы (3-я усилила тест) |
| TSK-006 | completed | deploy 89dd4c5: 247 тестов на сервере, health 200, `tours.ready chars=19656` (DOCX), `tour_sync.disabled` — ждёт доступ |
| TSK-007 | completed | SA-авторизация (приоритет над ключом), скачивание обоих типов файлов, нормализация имён, алиасы, чистка заголовков, сверка первого запуска с базой; dry-run против живого Drive |
| TSK-008 | completed | Ключ SA в `credentials/` + `.env` на сервере; deploy 98ab647; первый живой тик ок (6 туров, TG ушло) |
| TSK-009 | completed | Фикс инцидента 15:56 UTC: алиас→URL, keep_snapshot, событие после sync; 270 тестов; dry-run чистый; deploy 9b03a8c7 — тик 16:44 UTC вернул 6 туров (added=2, removed=0, skipped=0), TG ушло, снапшот ок |

## Tasks

- [x] TSK-010 Компактные уведомления из b0c04146 поверх текущих guards
  - Перенести формат Docs и точные тестовые labels; сохранить recovery/receipt.
  - Профильный и полный pytest, Ruff/diff, независимое review.
  - Backup/SHA/config guards, code-only apply/restart/health/smoke и откат;
    recovery scope остаётся allowlist, БД не восстанавливать.
  - _Requirements: Micro 2026-10-19; отдельное подтверждение «только новые правки кода»._
  - Факт: 12 новых RED → 166 профильных PASS, полный1503 PASS/8 прежних warnings/
    68.97 с, Ruff/diff и независимое review PASS. Package SHA
    d14f70bbbab1f67562582d22ee2b9b9f7bf64a6734a0f6ee02c17ed139729c14;
    four-file apply + manifest31, online SQLite backup integrity PASS,
    inverse/partial/unexpected edit/receipt-preserving rollback proof PASS.
    PID4136→12960, start2026-10-19T11:20:54.3458409Z, health/31SHA/installed
    formatting+preview+receipt smoke PASS. Env/recovery allowlist1/baselines
    сохранены, DB не заменялась. См. runtime/telegram-compact-deployment.md.

| Progress | Статус | Проверка |
| --- | --- | --- |
| TSK-010 | Выложено; общее recovery не включалось | 1503 PASS, health/31SHA/installed smoke, no startup errors на контрольном чтении |

- [x] TSK-001 Настройки синхронизации
  - Добавить в `src/config.py`: `tour_sync_enabled`, `tour_sync_folder_id`, `google_drive_api_key`, `tour_sync_interval_seconds=300`, `tour_sync_min_tours=1`, `tour_sync_max_drop_ratio=0.5`, `tour_sync_snapshot_path="data/tours_snapshot.json"`, `tour_sync_notify=True`
  - Документировать имена в `.env.example` (без значений)
  - Добавить `data/tours_snapshot.json` в `.gitignore`
  - _Requirements: FR-1, FR-6, NFR-безопасность_

- [x] TSK-002 Точка перезагрузки и снапшот в `tour_loader`
  - `publish_tours_text(text)` — атомарная подмена кэша; `get_tours_text()` без изменений
  - `save_snapshot/load_snapshot` — JSON `{tours, text, hash, built_at}`, запись через tmp+rename
  - Не менять поведение `load_tours()` (остаётся fallback и локальный путь)
  - _Requirements: FR-5, FR-6_

- [x] TSK-003 Модуль `src/services/tour_sync.py`
  - `list_drive_docs` (только Google Docs; ключ — параметром, в логи не пишем)
  - `export_doc` (plain text, срез BOM, нормализация пробелов)
  - `build_snapshot` (один документ = один блок в `_extract_tour_section`; ссылка на тур = фактический URL; бронь наследуется по ID; без брони — в `skipped`)
  - `validate_snapshot` (пусто/мин/просадка)
  - `diff_snapshots` (добавлены/удалены/изменения цены/дат/ссылок)
  - `tick(state)` — один проход, исключений наружу нет
  - _Requirements: FR-1, FR-2, FR-3, FR-4, FR-5, FR-7_

- [x] TSK-004 Воркер в `lifespan` (`src/main.py`)
  - Стартовый поток: sync → снапшот → `load_tours()` (первое успешное побеждает)
  - `_tour_sync_worker`: сон по интервалу + `tick()` рядом с `_pending_messages_worker`
  - Уведомления через `TelegramNotifier.notify_manager(sender_id="tour_sync", ...)`
  - _Requirements: FR-1, FR-6, FR-7_

- [x] TSK-005 Тесты `tests/test_tour_sync.py`
  - Сборка из поддельных экспортов, хэш-сравнение, все ветки валидации, пропуск без брони, наследование брони, diff, снапшот roundtrip, пропуск тика при выключенном/ненастроенном sync
  - Без сети; мутационная самопроверка ключевых веток
  - _Requirements: все FR_

- [x] TSK-006 Деплой и проверка прода
- [x] TSK-007 SA-авторизация, два типа файлов, алиасы, сверка первого запуска (код + тесты + dry-run)
- [x] TSK-008 Серверный доступ, деплой, проверка первого живого тика
  - Положить JSON-ключ SA на сервер (вне репозитория), прописать `.env`
  - Деплой, проверка логов первого тика и Telegram-уведомления
  - _Requirements: FR-1, FR-7_
  - Факт: deploy 98ab647, 265 тестов на сервере, health 200; первый тик 15:52 UTC — `tour_sync.built tours=6 removed=2`, `tours.published chars=35552`, TG-уведомление ушло в 3 чата; снапшот 135 КБ на диске; `credentials/` и снапшот в git не светятся
- [x] TSK-009 Фикс прода-инцидента 2026-10-04 (алиас отравлял seed + затирание состояния + раннее событие)
  - Алиасы теперь указывают на URL брони; прямое совпадение идёт первым; `keep_snapshot`; событие готовности после начальной синхронизации; честные суффиксы удалений
  - _Requirements: FR-3 AC4–AC5, FR-5 AC4_
  - Факт: 270 тестов (57 sync), мутации ловятся, dry-run по живому Drive — 6 туров, пропусков ноль, удалены только Париж и Дунай
  - Полный `pytest` локально → `deploy.ps1` (тесты на сервере, рестарт, health)
  - Проверка: лог опроса, `tours.ready`, снапшот на диске, контрольные вопросы боту
  - Напомнить владельцу про API-ключ (без него sync спит, бот работает по DOCX)
  - _Requirements: приёмка из плана_
