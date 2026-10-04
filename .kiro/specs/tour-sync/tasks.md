# Tasks: синхронизация туров из Google Drive

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
