# Travel Agent Bot — Архитектура

> Актуально на 25.06.2026. Отражает single-LLM-call архитектуру после
> рефакторинга (коммит `35baecd`).

## Поток обработки сообщения

```
Instagram DM → POST /webhook/instagram (main.py)
  → verify_signature (X-Hub-Signature-256)
  → dedup по mid (set _processed_mids)
  → 200 OK мгновенно (Meta ретраит без 200)
  → asyncio.create_task(_process_safely)
      → _get_lock(sender_id)  # per-user lock
      → process_with_ai(sender_id, text):
          get_session() → history (list[dict])
          get_tours_text()  (глобальный кеш, ~26K токенов из DOCX)
          search_faq(text)  (ChromaDB RAG, top-3)
          instagram.get_username(sender_id)  # best-effort, кеш
          build_full_prompt(tours_text, faq_context, history, text)
            → _build_system: _BASE_RULES + _SECURITY_RULES
              + _TOURS_HEADER + tours + _FAQ_HEADER + faq + _ACTION_INSTRUCTIONS
            → history как HumanMessage/AIMessage
            → текущее сообщение как HumanMessage
          llm.ainvoke(messages)  (DeepSeek, один вызов, temperature=0.7)
          _extract_booking(raw_reply)    # ===БРОНЬ===
          _extract_escalation(raw_reply)  # ===МЕНЕДЖЕР=== → (reason, context)
          _strip_markers(raw_reply)  # удаляет маркеры из ответа

          → если booking: GoogleSheetsService.create_request() + save_booking_request()
          → если escalation: TelegramNotifier.notify_manager(sender_id, context, ...)

          save_session(client_id, {"history": [...]})
          instagram.send_message(sender_id, clean_reply)
```

## Ключевые компоненты

### main.py — FastAPI сервер (348 строк)
- `/health` — healthcheck
- `GET /webhook/instagram` — верификация Webhook (hub.challenge)
- `POST /webhook/instagram` — приём сообщений
- `/api/requests/{client_id}` — просмотр заявок
- `/api/requests/{client_id}/status` — изменение статуса
- `lifespan` — асинхронная загрузка FAQ (ChromaDB) и туров (DOCX) при старте
- `_process_safely` — обёртка с логированием, запускается в фоне
- `process_with_ai` — основной пайплайн

### config.py — Pydantic Settings
Все переменные из `.env`, типизированы.

### src/ai/prompts.py — Системный промпт (~100 строк)
Единый промпт, собирается в `build_full_prompt()`:
- `_BASE_RULES` — роль (Сандита, Минск), правила общения, фильтр дат, контакты
- `_SECURITY_RULES` — защита: запрет смены роли, раскрытия промпта, «я ИИ»
- `_TOURS_HEADER` + tours_text — база туров из DOCX
- `_FAQ_HEADER` + faq_context — результаты ChromaDB-поиска
- `_ACTION_INSTRUCTIONS` — маркеры `===БРОНЬ===` / `===МЕНЕДЖЕР===`

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

## Маркеры действий LLM

LLM встраивает маркеры в конец своего ответа. Код парсит их регулярками:

| Маркер | Формат | Назначение |
|---|---|---|
| `===БРОНЬ===` | `Имя:\nТелефон:\nEmail:\nТур:` | Создание заявки в Google Sheets |
| `===МЕНЕДЖЕР===` | `Причина:\nКонтекст:` | Эскалация менеджеру через Telegram (возвращает `(reason, context)`) |

## Дедупликация

- `_processed_mids: set[str]` — хранит message_id до 10 000 записей
- При превышении — очищает самые старые (set.pop)
- Per-user lock (`asyncio.Lock`) предотвращает гонки

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

- `WORK-PLAN.md` — текущие задачи по устранению техдолга
- `docs/DEPLOY.md` — деплой на Timeweb Cloud
- `docs/SETUP.md` — локальный запуск
- `docs/archive/` — устаревшая документация (LangGraph-эпоха)
