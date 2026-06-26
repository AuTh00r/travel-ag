---
name: travel-bot-dev
description: >
  ИИ-помощник турагентства: чат-бот на Python + FastAPI + DeepSeek API,
  работающий через Instagram Direct, с DOCX-базой туров, ChromaDB RAG для FAQ,
  SQLite-сессиями, Google Sheets для заявок и Telegram-уведомлениями менеджерам.
  Деплой на Docker → Timeweb Cloud (РБ). Использовать при разработке,
  отладке, тестировании и деплое любого компонента проекта travel-agent-bot.
---

# Travel Bot Dev — Skill для проекта travel-agent-bot

## Контекст проекта

Чат-бот / агент для турагентства «Сандита» (Минск), автоматизирующий первый
контакт с клиентом через Instagram Direct. Язык общения — русский,
дружелюбный экспертный тон.

Актуальная архитектура после рефакторинга `35baecd`: **single-LLM-call**.
LangGraph-граф, `src/ai/engine.py`, `src/ai/nodes.py`, `src/ai/states.py` и
`src/ai/classifier.py` удалены. Документы с LangGraph-эпохой лежат только в
`docs/archive/` и используются как история, а не как рабочая инструкция.

**Стек:** Python 3.11+ / FastAPI / DeepSeek через OpenAI-compatible API /
LangChain OpenAI wrapper / ChromaDB / sentence-transformers / SQLite /
Google Sheets API / Telegram Bot API / Docker.

**Региональные особенности:** Республика Беларусь (РБ). Хостинг — Timeweb Cloud.

Главный источник правды по текущей архитектуре: `docs/ARCHITECTURE.md`.

## Стандарты кода

- Все промпты LLM — на русском языке, дружелюбный экспертный тон.
- Pydantic Settings через `src/config.py`, переменные из `.env`.
- `structlog` для логирования.
- Type hints обязательны на новых функциях.
- Форматирование: `black` (line-length 100 по локальной договорённости).
- Линтер: `ruff`.
- Импорты: absolute imports от `src.`
- Ошибки: кастомные исключения в `src/exceptions.py`.
- Прод-путь webhook/AI не трогать шире задачи: дедупликация, фоновые задачи,
  per-user lock и manager takeover уже выстроены и покрыты тестами.

## Фактическая структура

```text
travel-agent-bot/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── conftest.py
├── WORK-PLAN.md                    # исторический выполненный план техдолга
├── docs/
│   ├── ARCHITECTURE.md             # актуальная архитектура
│   ├── DEVELOPMENT.md              # локальная работа, тесты, git, VPS
│   ├── SETUP.md                    # локальный запуск и VPS
│   ├── ENV-SETUP.md                # переменные окружения
│   ├── DEPLOY.md                   # быстрый деплой на VPS
│   └── archive/                    # устаревшие LangGraph-документы
├── src/
│   ├── main.py                     # FastAPI, webhook, AI-пайплайн
│   ├── config.py                   # Pydantic Settings
│   ├── exceptions.py
│   ├── ai/
│   │   └── prompts.py              # единый системный промпт
│   ├── channels/
│   │   ├── base.py
│   │   └── instagram.py            # Meta Graph API, подпись, echo/manager
│   ├── db/
│   │   ├── faq_db.py               # ChromaDB FAQ
│   │   └── sessions.py             # SQLite сессии и заявки
│   ├── services/
│   │   ├── guard.py                # input/output guard + rate limit
│   │   ├── google_sheets.py        # заявки в Google Sheets
│   │   ├── llm.py                  # DeepSeek API wrapper
│   │   ├── telegram_notify.py      # Telegram эскалации и брони
│   │   └── tour_loader.py          # загрузка DOCX-туров
│   └── models/
├── tests/
│   ├── test_api.py
│   ├── test_engine.py              # парсинг маркеров и ответов, не LangGraph
│   ├── test_google_sheets.py
│   ├── test_guard.py
│   ├── test_instagram.py
│   ├── test_sessions.py
│   ├── test_telegram_notify.py
│   └── test_tour_search.py
├── data/faq/
└── tours/
```

## Поток обработки сообщения

```text
Instagram DM → POST /webhook/instagram
  → проверка X-Hub-Signature-256
  → instagram.receive_message() → список событий:
      kind="user"          → _process_safely → process_with_ai (LLM)
      kind="user_non_text" → _process_non_text_safely (без LLM)
      kind="manager"       → _mark_manager_active (пауза бота)
  → дедупликация по message.mid
  → мгновенный 200 OK для Meta
  → asyncio.create_task для каждого события

Текстовое сообщение (kind="user"):
  → _process_safely → process_with_ai():
      manager takeover gate, rate limit, check_input()
      per-user lock, история, туры, FAQ top-3
      build_full_prompt() → DeepSeek
      парсинг ===БРОНЬ=== / ===МЕНЕДЖЕР===
      Google Sheets + SQLite для брони
      Telegram для брони/эскалации
      сохранение истории → отправка ответа

Non-text сообщение (kind="user_non_text"):
  → _process_non_text_safely():
      manager takeover gate, per-user lock
      escalation_count < 3:
        TelegramNotifier.notify_manager(...) → escalation_count++
        client ack: "Не вижу вложение/пост/историю, передала менеджеру"
      escalation_count >= 3:
        client ack: "Ваш запрос уже передан менеджеру, ожидайте"
      сохранение истории → отправка ответа
  **LLM не вызывается.** Вложения/посты/story replies обрабатываются детерминированно.
```

## Маркеры действий LLM

LLM может добавить служебные блоки в конец ответа. Клиент их не видит:

```text
===БРОНЬ===
Имя: ...
Телефон: ...
Email: ...
Тур: ...
===БРОНЬ===
```

```text
===МЕНЕДЖЕР===
Причина: ...
Контекст: ...
===МЕНЕДЖЕР===
```

Если маркер упоминается, но не парсится, `src/main.py` пишет
`marker.parse_failed`.

## Конфигурация

Основные переменные:

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-chat
INSTAGRAM_APP_SECRET=...
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_VERIFY_TOKEN=...
INSTAGRAM_PAGE_ID=...
INSTAGRAM_IG_USER_ID=...
INSTAGRAM_APP_ID=...
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_TOURS_SHEET_ID=...
GOOGLE_REQUESTS_SHEET_ID=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_MANAGER_CHAT_ID=...
CHROMA_DB_DIR=data/chroma
BOOKING_FORM_URL=
MAX_MESSAGE_LENGTH=1000
MAX_MESSAGES_PER_MINUTE=5
MANAGER_TAKEOVER_TTL_MINUTES=10080
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
```

`INSTAGRAM_APP_SECRET` обязателен для прода: без него подпись webhook не
проверяется и это допустимо только для локальных тестов.

## Команды

```bash
# Локально
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Docker
docker compose up --build

# Тесты: актуальная каноничная команда
pytest tests/ -q

# Линтинг
ruff check src tests

# Форматирование
black src tests
```

`pyproject.toml` задаёт `asyncio_mode = "auto"`. `conftest.py` добавляет корень
проекта в `sys.path` и объявляет Playwright fixtures `browser` / `page`.
Актуальный набор: 130 тестов в 8 файлах.

## Триггеры эскалации

Агент должен передать диалог менеджеру при:

- прямом запросе на человека: «менеджер», «живой человек», «оператор»;
- жалобе или недовольстве;
- сложном/нестандартном запросе;
- отсутствии информации в базе туров или FAQ;
- невозможности увидеть вложение/пост/фото;
- срочном индивидуальном подборе.

После трёх эскалаций для клиента бот больше не отправляет новые Telegram-уведомления,
а просит дождаться менеджера.

## Дополнительные справочники

- `docs/ARCHITECTURE.md` — текущий поток и компоненты.
- `docs/DEVELOPMENT.md` — локальная работа, тесты, git, VPS.
- `docs/SETUP.md` — локальный запуск, Docker, VPS и Instagram webhook.
- `docs/ENV-SETUP.md` — настройка `.env`.
- `docs/DEPLOY.md` — быстрые команды для Timeweb VPS.

Папка `references/` внутри skill может содержать старые LangGraph-шаблоны.
Их не использовать для текущего кода.
