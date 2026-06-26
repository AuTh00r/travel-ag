# Travel Agent Bot — Архитектура

> Актуально на 26.06.2026. Отражает single-LLM-call архитектуру после
> рефакторинга `35baecd`: LangGraph-граф удалён, весь прод-путь идёт через
> один LLM-вызов DeepSeek и детерминированные сервисные слои вокруг него.

## Поток обработки сообщения

```
Instagram DM → POST /webhook/instagram (main.py)
  → verify_signature (X-Hub-Signature-256)
  → instagram.receive_message() → список событий:
      kind="user"          → _process_safely → process_with_ai (LLM)
      kind="user_non_text" → _process_non_text_safely (без LLM)
      kind="manager"       → _mark_manager_active (пауза бота)
  → dedup по mid (set _processed_mids)
  → 200 OK мгновенно (Meta ретраит без 200)
  → asyncio.create_task для каждого события
```

### Текстовое сообщение (kind="user")

```
  → _process_safely → process_with_ai(sender_id, text):
      manager takeover gate
      is_rate_limited(sender_id)
      check_input(text)
      _get_lock(sender_id)  # per-user lock
      get_session() → history (list[dict])
      get_tours_text()  (глобальный кеш, ~26K токенов из DOCX)
      search_faq(text)  (ChromaDB RAG, top-3)
      instagram.get_username(sender_id)
      build_full_prompt(...)
      llm.ainvoke(messages)  (DeepSeek)
      _extract_booking(raw_reply) / _extract_escalation(raw_reply)
      check_output(clean_reply)
      → Google Sheets + SQLite для брони
      → Telegram для брони/эскалации
      save_session()
      instagram.send_message()
```

### Non-text сообщение (kind="user_non_text")

```
  → _process_non_text_safely(sender_id, text, metadata):
      manager takeover gate
      _get_lock(sender_id)  # per-user lock
      instagram.get_username(sender_id)  # best-effort, кеш
      escalation_count < 3:
        → TelegramNotifier.notify_manager(
            context="Тип: summary\nТекст клиента: ...\nБот не видит вложение")
        → escalation_count++
        → client ack: "Не вижу вложение/пост/историю, передала менеджеру"
      escalation_count >= 3:
        → client ack: "Ваш запрос уже передан менеджеру, ожидайте"
      save_session()  # история + escalation_count
      instagram.send_message(client_reply)
  **LLM не вызывается.**
```

## Ключевые компоненты

### main.py — FastAPI сервер
- `/health` — healthcheck
- `GET /webhook/instagram` — верификация Webhook (hub.challenge)
- `POST /webhook/instagram` — приём сообщений (ветки: user → LLM, user_non_text → Telegram, manager → takeover)
- `/webhook/instagram/last_seen` — диагностика, приходили ли POST от Meta
- `/api/requests/{client_id}` — просмотр заявок
- `/api/requests/{client_id}/status` — изменение статуса
- `/api/admin/reset-takeover/{client_id}` — сброс паузы после ручного ответа менеджера
- `lifespan` — асинхронная загрузка FAQ (ChromaDB) и туров (DOCX) при старте
- `_process_safely` — обёртка с логированием, запускается в фоне (LLM-путь)
- `_process_non_text_safely` — обработка вложений/постов/story-reply без LLM, сразу в Telegram + client ack
- `process_with_ai` — основной пайплайн с DeepSeek

### config.py — Pydantic Settings
Все переменные из `.env`, типизированы. Помимо API-ключей хранит лимиты защиты:
`max_message_length`, `max_messages_per_minute`, `manager_takeover_ttl_minutes`.

### src/ai/prompts.py — Системный промпт (~100 строк)
Единый промпт, собирается в `build_full_prompt()`:
- `_BASE_RULES` — роль (Сандита, Минск), правила общения, фильтр дат, контакты
- `_SECURITY_RULES` — защита: запрет смены роли, раскрытия промпта, «я ИИ»
- `_TOURS_HEADER` + tours_text — база туров из DOCX
- `_FAQ_HEADER` + faq_context — результаты ChromaDB-поиска
- `_ACTION_INSTRUCTIONS` — маркеры `===БРОНЬ===` / `===МЕНЕДЖЕР===`
- `_ESCALATION_RULES` / `_ESCALATION_LIMIT_REACHED` — Telegram-эскалация до 3 раз

### src/services/guard.py — Детерминированная защита
- `check_input()` — пустые/слишком длинные сообщения и prompt-injection до LLM
- `is_rate_limited()` — per-sender лимит сообщений в минуту
- `check_output()` — fallback, если модель раскрывает служебную природу или вендора

### src/services/llm.py — Обёртка DeepSeek API
- `get_llm()` — ChatOpenAI с temperature=0.7
- `get_llm_json()` — ChatOpenAI с response_format=json_object, temperature=0.1

### src/services/tour_loader.py — Загрузка DOCX
- `load_tours()` — читает все `.docx` из `tours/`, собирает в единый текст
- `get_tours_text()` — возвращает кешированный текст

### src/db/faq_db.py — RAG FAQ через ChromaDB
- `load_faq_to_chroma()` — загружает FAQ из `data/faq/` в ChromaDB
- `search_faq(text)` — векторный поиск, возвращает top-3 документа

### src/db/sessions.py — SQLite сессии
- `get_session()` / `save_session()` — хранение истории диалога
- `save_booking_request()` / `get_requests_by_client()` / `update_request_status()`

### src/services/google_sheets.py — Google Sheets API
- `create_request()` — запись заявки (имя, телефон, email, тур)
- `update_request_status()` — обновление статуса

### src/services/telegram_notify.py — Telegram-уведомления
- `notify_manager(sender_id, instagram_handle, context, ...)` — отправка контекстной карточки клиента менеджеру без истории переписки
- `_build_notification_text()` — формат: 🚨 Новая эскалация, 👤 @handle, 🕐 таймстемп, 📋 суть, контакты (опционально)
- `notify_booking(...)` — отдельное уведомление менеджерам о новой брони

### src/channels/instagram.py — Instagram Direct
- `verify_signature()` — проверка `X-Hub-Signature-256`; без `INSTAGRAM_APP_SECRET`
  разрешено только локально
- `receive_message()` — разделяет сообщения клиента на `kind="user"` (текст),
  `kind="user_non_text"` (вложение/пост/story reply/referral) и `kind="manager"` (echo менеджера)
- `_extract_non_text_metadata()` — детектирует `attachments`, `reply_to`, `referral`
  и возвращает структуру с `types`, `summary`, `has_text`, `text`, `raw_keys`
- `send_message()` — отправка через Graph API и сохранение `message_id` для echo-фильтра
- `get_username()` — best-effort username/name с in-memory кешем

## Маркеры действий LLM

LLM встраивает маркеры в конец своего ответа. Код парсит их регулярками:

| Маркер | Формат | Назначение |
|---|---|---|
| `===БРОНЬ===` | `Имя:\nТелефон:\nEmail:\nТур:` | Создание заявки в Google Sheets |
| `===МЕНЕДЖЕР===` | `Причина:\nКонтекст:` | Эскалация менеджеру через Telegram (возвращает `(reason, context)`) |

## Дедупликация

- `_processed_mids: set[str]` — хранит message_id до 10 000 записей
- При превышении — удаляет записи через `set.pop()`
- Per-user lock (`asyncio.Lock`) предотвращает гонки
- `_sent_mids` в InstagramChannel помогает отличать echo собственных сообщений бота
- `manager_last_at` в SQLite-сессии включает паузу бота после ответа менеджера

## Тесты

- `pyproject.toml`: `asyncio_mode = "auto"`
- `conftest.py`: добавляет корень проекта в `sys.path`, объявляет Playwright fixtures
- Актуальный набор: 130 тестов в 8 файлах
- Каноничная команда: `pytest tests/ -q`

## Файловая структура (факт)

```
src/
├── main.py
├── config.py
├── exceptions.py
├── ai/
│   ├── __init__.py
│   └── prompts.py
├── channels/
│   ├── base.py
│   └── instagram.py
├── db/
│   ├── faq_db.py
│   └── sessions.py
├── models/
│   ├── tour.py
│   ├── client.py
│   └── request.py
├── services/
│   ├── embeddings.py
│   ├── google_sheets.py
│   ├── llm.py
│   ├── telegram_notify.py
│   └── tour_loader.py
```

## Связанные документы

- `WORK-PLAN.md` — исторический выполненный план по устранению техдолга
- `docs/DEPLOY.md` — деплой на Timeweb Cloud
- `docs/SETUP.md` — локальный запуск
- `docs/archive/` — устаревшая документация (LangGraph-эпоха)
