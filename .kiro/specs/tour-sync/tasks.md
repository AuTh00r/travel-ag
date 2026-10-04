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
| TSK-006 | in_progress | полный прогон 247 зелёных; дальше deploy |

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

- [ ] TSK-006 Деплой и проверка прода
  - Полный `pytest` локально → `deploy.ps1` (тесты на сервере, рестарт, health)
  - Проверка: лог опроса, `tours.ready`, снапшот на диске, контрольные вопросы боту
  - Напомнить владельцу про API-ключ (без него sync спит, бот работает по DOCX)
  - _Requirements: приёмка из плана_
