# Handover — travel-agent-bot

## Что сделано (Этап 1 — Настройка окружения)

- Python 3.11.9 установлен (`winget install Python.Python.3.11`)
- Все зависимости из `requirements.txt` установлены
  - Core: fastapi, uvicorn, langgraph, langchain-core, chromadb, openai, pydantic
  - Services: google-api-python-client, python-telegram-bot, httpx
  - ML: torch, sentence-transformers
  - Dev: ruff, black, pytest, pytest-asyncio, structlog
- Путь к python: `C:\Users\AUTHOR\AppData\Local\Programs\Python\Python311\`
  (Microsoft Store alias `python` мешает — пришлось использовать полный путь)
- Добавлен `conftest.py` в корень проекта — автоматически добавляет корень в `sys.path`, тесты работают без `PYTHONPATH`

### Файлы

| Файл | Описание |
|---|---|
| `src/main.py` | FastAPI сервер с `/health` |
| `src/config.py` | Pydantic Settings из `.env` |
| `src/exceptions.py` | 7 кастомных исключений |
| `requirements.txt` | 22 зависимости |
| `.env.example` | Шаблон переменных окружения |
| `Dockerfile` | Python 3.11-slim + uvicorn |
| `docker-compose.yml` | Контейнер с env_file и volume |
| `conftest.py` | Корневой conftest для autopep8 PYTHONPATH |

### Замечания

- Microsoft Store alias `python` мешает — при использовании из-под терминала может потребоваться полный путь
- `conftest.py` добавляет корень проекта в `sys.path` — тесты работают без `PYTHONPATH`

### Проверено

```
GET /health → {"status": "ok"}
pip install — без ошибок
Все пакеты импортируются (fastapi, langgraph, chromadb, torch etc.)
```

---

## Что сделано (Этап 2 — Instagram API)

### Файлы

| Файл | Описание |
|---|---|
| `src/channels/base.py` | Абстрактный интерфейс канала (ABC): `send_message`, `handle_webhook` |
| `src/channels/instagram.py` | Instagram Webhook handler: верификация (GET), приём (POST), отправка |
| `tests/test_instagram.py` | 9 тестов: верификация, получение, отправка, ошибки |

### Детали реализации

- **`GET /webhook/instagram`** — верификация webhook (hub.challenge) с проверкой `hub.verify_token`
- **`POST /webhook/instagram`** — приём входящих сообщений, отправка ответа-заглушки (пока AI-движок не готов)
- **`InstagramChannel.send_message()`** — отправка через Instagram Graph API (`graph.facebook.com/v21.0/me/messages`) с обработкой ошибок
- **`InstagramChannel.receive_message()`** — парсинг webhook-пейлоада, возврат списка `(sender_id, text)`
- Ошибки API обёрнуты в `InstagramError` (из `src/exceptions.py`)
- Webhook-роуты защищены try/except — ошибки отправки не ломают ответ Meta

### Проверено

```
pytest tests/ -v  → 9 passed
ruff check src/   → All checks passed
black --check     → файлы отформатированы
```

---

## Что сделано (Этап 3 — AI-движок LangGraph)

### Файлы

| Файл | Описание |
|---|---|
| `src/ai/states.py` | TypedDict `DialogState` + `TourParams` |
| `src/ai/engine.py` | LangGraph StateGraph со всеми состояниями |
| `src/ai/nodes.py` | Функции узлов: greet, classify_node, clarify, search_tours_node, present_tours, book, escalate |
| `src/ai/classifier.py` | LLM-классификация запроса (tour_search/faq/complaint/talk_to_manager/booking/greeting/unknown) |
| `src/ai/prompts.py` | 7 системных промптов на русском |
| `src/ai/tour_search.py` | Поиск туров через GoogleSheetsService |
| `src/ai/faq.py` | RAG для FAQ (заглушка до Этапа 5) |
| `src/services/llm.py` | Обёртка DeepSeek API (get_llm / get_llm_json) |
| `src/services/google_sheets.py` | Google Sheets API клиент (реализован на Этапе 4) |
| `src/services/telegram_notify.py` | Telegram-уведомления менеджеров (реализован на Этапе 7) |
| `src/services/embeddings.py` | Сервис эмбеддингов sentence-transformers (реализован на Этапе 5) |
| `src/db/sessions.py` | SQLite: get_session / save_session |
| `src/models/tour.py` | Pydantic модель тура |
| `src/models/client.py` | Pydantic модель клиента |
| `src/models/request.py` | Pydantic модель заявки |
| `tests/test_engine.py` | 16 тестов (граф, состояния, валидация, booking flow) |

### Граф состояний

```
START → GREETING → CLASSIFY ─┬─ tour_search → CLARIFY → SEARCH_TOURS → PRESENT_TOURS → BOOK
                              │                                              │
                              ├─ faq → FAQ_SEARCH ──────────────────────────┘
                              ├─ complaint → ESCALATE
                              ├─ talk_to_manager → ESCALATE
                              └─ booking → BOOK
```

### Детали реализации

- **`build_graph()`** — StateGraph с 8 узлами, conditional edges для маршрутизации
- **Классификация** — LLM-based (JSON mode), определяет тип запроса + триггеры эскалации
- **Уточнение** — итеративный сбор параметров (до 3 циклов), LLM извлекает destination/dates/budget/travelers/tour_type
- **Поиск** — через GoogleSheetsService, заглушка до Этапа 4
- **Презентация** — LLM форматирует найденные туры с ссылками
- **Бронирование** — сбор имени → телефона → email → подтверждение, валидация +375 и email
- **Эскалация** — триггеры: 0 результатов, срочность, жалоба, запрос менеджера
- **SQLite** — сессии диалогов с автозагрузкой/сохранением
- **main.py** — интеграция AI-движка: process_with_ai загружает сессию, запускает граф, отправляет ответы

### Проверено

```
pytest tests/ -v    → 14 passed
ruff check src/     → All checks passed
```

---

## Что сделано (Этап 4 — Google Sheets интеграция)

### Файлы

| Файл | Описание |
|---|---|
| `src/services/google_sheets.py` | Google Sheets API клиент: auth через Service Account, чтение/поиск туров, запись заявок |
| `src/ai/tour_search.py` | Обёртка поиска с обработкой ошибок и логированием |
| `tests/test_google_sheets.py` | 15 тестов (helper-функции + интеграционные с моками) |
| `tests/test_tour_search.py` | 3 теста (найден/пусто/ошибка) |

### Детали реализации

- **`GoogleSheetsService`** — аутентификация через `credentials.json` (Service Account), чтение листа «Туры» (A:I), запись в лист «Заявки» (A:K)
- **Скоринговая система поиска** — каждый тур получает балл релевантности:
  - Точное совпадение направления / типа → +1.0
  - Совпадение по ключевым словам → +0.5
  - Бюджет: поддержка «до N»/«от N»/точное значение, погрешность 30%
  - Даты: fuzzy match по строке дат + поиск по названиям месяцев
  - Сортировка по убыванию скора
- **Фильтрация** — только `Доступно=Да`
- **Fuzzy matching** — `difflib.SequenceMatcher` (порог 0.35) + substring match
- **`create_request()`** — добавляет строку с датой, именем, телефоном, email, направлением, бюджетом, туристами, выбранным туром, статусом «Новая», источником «Instagram»
- **`tour_search.py`** — обрабатывает `GoogleSheetsError`, логирует количество результатов, возвращает `found_tours` или флаг эскалации

### Проверено

```
pytest tests/ -v    → 47 passed
ruff check src/     → All checks passed
```

---

## Что сделано (Этап 5 — RAG FAQ)

### Файлы

| Файл | Описание |
|---|---|
| `data/faq/visa.txt` | FAQ: визовые вопросы (Турция, Египет, шенген, детские визы) |
| `data/faq/insurance.txt` | FAQ: медстраховка, покрытие, стоимость, COVID-19 |
| `data/faq/weather.txt` | FAQ: погода по сезонам и направлениям |
| `data/faq/documents.txt` | FAQ: документы для выезда, загранпаспорт, копии |
| `data/faq/baggage.txt` | FAQ: багаж и ручная кладь, запрещённые предметы |
| `data/faq/payment.txt` | FAQ: оплата, рассрочка, возврат, скрытые платежи |
| `data/faq/children.txt` | FAQ: детские туры, скидки, питание на борту |
| `data/faq/general.txt` | FAQ: общие вопросы (выбор тура, перелёт, валюта, трансфер, гиды) |
| `src/db/faq_db.py` | ChromaDB клиент: инициализация, парсинг FAQ-файлов, загрузка, векторный поиск |
| `src/services/embeddings.py` | Сервис эмбеддингов на sentence-transformers (all-MiniLM-L6-v2) |
| `src/ai/faq.py` | RAG-узел графа: поиск по ChromaDB → контекст в промпт → ответ LLM |

### Детали реализации

- **ChromaDB** — PersistentClient (`data/chroma/`), коллекция `faq`, метрика `cosine`
- **Embedding function** — `SentenceTransformerEmbeddingFunction` (all-MiniLM-L6-v2) из chromadb.utils
- **Парсинг FAQ** — `_parse_faq_file()` разбивает файлы на пары Вопрос/Ответ по маркерам `Вопрос:` / `Ответ:`
- **Загрузка** — `load_faq_to_chroma()` идемпотентна (проверяет `collection.count()`), вызывается при старте FastAPI через `lifespan`
- **Поиск** — `search_faq()` асинхронная обёртка над ChromaDB (через `run_in_executor`), возвращает топ-3 релевантных записи
- **Интеграция в граф** — `faq_search()` передаёт найденные записи в `FAQ_PROMPT` как `{faq_context}`; если результат пуст — выставляет `needs_escalation=True` с причиной
- **`EmbeddingsService`** — lazy-load модели sentence-transformers, кеширование через `lru_cache`, методы `get_embedding()` / `get_embeddings()`
- **Конфиг** — `settings.chroma_db_dir` (по умолч. `data/chroma`), добавлен в `.env.example`

### Проверено

```
ruff check src/     → All checks passed
pytest tests/ -v    → 58 passed
```

---

## Что сделано (Этап 6 — Сбор контактов)

### Файлы

| Файл | Описание |
|---|---|
| `src/ai/engine.py` | Условная маршрутизация от START: пропуск GREETING при mid-booking (current_step в AWAIT_NAME/AWAIT_PHONE/AWAIT_EMAIL/CONFIRM) |
| `src/ai/nodes.py` | Переработан `book()`: ASK_NAME → AWAIT_NAME → AWAIT_PHONE → AWAIT_EMAIL → CONFIRM → COMPLETED |
| `src/db/sessions.py` | Новая таблица `requests` + `save_booking_request()` для дублирования заявок в SQLite |
| `tests/test_engine.py` | 11 новых тестов для booking flow (всего 16 тестов в файле) |

### Детали реализации

- **Последовательный сбор** — строгий порядок: имя → телефон → email → подтверждение
- **ASK_NAME** — первый шаг всегда спрашивает имя, никогда не вычитывает из last_message (исправлена ошибка, когда «да, хочу» становилось именем)
- **Валидация**:
  - Имя: минимум 2 символа
  - Телефон: regex `+375\d{9}` (с очисткой разделителей)
  - Email: базовый формат `*@*.*`
  - При неверном формате шаг повторяется с сообщением об ошибке
- **Подтверждение** — показ всех собранных данных, ожидание «да»; при отказе — сброс к ASK_NAME
- **Сохранение** — дуальная запись: Google Sheets (через `GoogleSheetsService.create_request()`) + SQLite (таблица `requests` через `save_booking_request()`)
- **Маршрутизация START** — если `current_step` в booking flow (AWAIT_NAME/AWAIT_PHONE/AWAIT_EMAIL/CONFIRM), граф идёт напрямую в `book`, минуя GREETING и CLASSIFY (нет дублирования приветствия)
- **COMPLETED** — терминальное состояние после успешного бронирования

### Исправленные баги

1. `book()` принимал любое сообщение пользователя за имя на первом шаге (например, «да, хочу» → имя = «да, хочу»)
2. После каждого сообщения в середине бронирования граф повторно отправлял GREETING
3. Заявки сохранялись только в Google Sheets, без локальной копии в SQLite

### Проверено

```
pytest tests/ -v    → 58 passed
ruff check src/     → All checks passed
```

---

## Что сделано (Этап 7 — Уведомления менеджерам)

### Файлы

| Файл | Описание |
|---|---|
| `src/services/telegram_notify.py` | TelegramNotifier: отправка уведомлений через Telegram Bot API (httpx, Markdown) |
| `src/ai/nodes.py` | `escalate()`: автозаполнение `conversation_history`, логирование ошибок; `_summarize_request()`: expanded with travelers, tour_type, selected_tour |
| `tests/test_telegram_notify.py` | 11 тестов (форматирование, отправка, ошибки, интеграция с escalate) |

### Детали реализации

- **TelegramNotifier** — использует `httpx.AsyncClient` для вызова `sendMessage` Telegram Bot API
- **Формат уведомления** — Markdown-разметка: клиент (имя, телефон, email), запрос, тег, история переписки (последние 15 сообщений), ссылка на Google Sheets
- **Экранирование Markdown** — `_escape_markdown()` экранирует спецсимволы (`_*[]()~`>#+-=|{}.!`)
- **История переписки** — `escalate()` автоматически собирает из `messages` (user/assistant, последние 20) если `conversation_history` пуст
- **Обработка ошибок** — при недоступности Telegram API ошибка логируется, клиент получает стандартное сообщение об эскалации
- **Конфигурация** — `TELEGRAM_BOT_TOKEN` и `TELEGRAM_MANAGER_CHAT_ID` из `.env`

### Триггеры эскалации (работают)

| Триггер | Где срабатывает |
|---|---|
| Прямой запрос менеджера | CLASSIFY → `talk_to_manager` → `escalate` |
| Жалоба | CLASSIFY → `complaint` → `escalate` |
| 0 результатов поиска | `present_tours()` → `needs_escalation=True` |
| FAQ без ответа | `faq_search()` → `needs_escalation=True` |
| Сложный/нестандартный запрос | CLASSIFY (LLM определяет) |

### Проверено

```
pytest tests/ -v    → 68 passed
ruff check src/     → All checks passed
```

---

## Что сделано (Этап 8 — Доп. функции)

### Файлы

| Файл | Описание |
|---|---|
| `.env.example` | Добавлен `BOOKING_FORM_URL` |
| `src/config.py` | Поле `booking_form_url` в Settings |
| `src/ai/nodes.py` | `book()`: ссылка на бронирование в COMPLETED (если задана) |
| `src/services/google_sheets.py` | `update_request_status()`: обновление статуса в Google Sheets |
| `src/db/sessions.py` | `update_request_status()` + `get_requests_by_client()` для SQLite |
| `src/main.py` | `GET /api/requests/{client_id}` + `PATCH /api/requests/{client_id}/status` |
| `tests/test_engine.py` | +1 тест (booking form link) |
| `tests/test_sessions.py` | Новый файл: 6 тестов (SQLite статусы) |
| `tests/test_api.py` | Новый файл: 5 тестов (API endpoints) |
| `tests/test_google_sheets.py` | +3 теста (update_request_status) |

### Детали реализации

- **BOOKING_FORM_URL** — опциональная ссылка на форму бронирования/оплаты. Если задана в `.env`, добавляется в сообщение после успешного бронирования
- **Статусы заявок** — конечный автомат: `Новая → В обработке → Подтверждена → Оплачена`
- **API endpoints:**
  - `GET /api/requests/{client_id}` — получить список заявок клиента
  - `PATCH /api/requests/{client_id}/status` — обновить статус заявки (обновляет SQLite + Google Sheets best-effort)
- **Google Sheets** — `update_request_status()` находит строку по имени+телефону и обновляет колонку Статус
- **SQLite** — `update_request_status()` обновляет последнюю заявку клиента по `created_at DESC`

### Проверено

```
pytest tests/ -v    → 83 passed
ruff check src/     → All checks passed
black --check       → All done
```

---

## Что сделано (Сессия: 22.06.2026 — Багфикс + инфраструктура)

### Файлы

| Файл | Описание |
|---|---|
| `src/models/request.py` | Исправлен mutable default `datetime.now()` → `Field(default_factory=datetime.now)` |
| `src/db/sessions.py` | Удалён дублирующийся `import json` внутри `get_session()` |
| `.gitignore` | Новый файл: исключены `sessions.db`, `chroma/`, `.env`, `credentials.json`, `__pycache__` и др. |
| `src/__init__.py` | Новый файл |
| `src/channels/__init__.py` | Новый файл |
| `tests/__init__.py` | Новый файл |
| `docs/SETUP.md` | Новый файл — инструкция по установке, Docker, деплой на Timeweb Cloud, Nginx + SSL, Instagram Webhook, мониторинг |

### Детали реализации

- **Баг №1** — `BookingRequest.created_at` имел дефолт `datetime.now()`, который вычислялся один раз при импорте класса. Все заявки получали одинаковый timestamp. Исправлен на `Field(default_factory=...)`.
- **Баг №2** — `import json` дублировался внутри функции `get_session()` при том что уже был импортирован наверху файла (строка 1).
- **__init__.py** — добавлены в `src/`, `src/channels/`, `tests/` для корректной работы пакетного импорта.
- **.gitignore** — добавлен, чтобы `sessions.db`, `chroma/` и другие артефакты не попадали в репозиторий.
- **docs/SETUP.md** — полная документация развёртывания: локальный запуск, Docker Compose, деплой на Timeweb Cloud (VPS + Nginx + certbot), настройка Instagram Webhook через ngrok, мониторинг и API.

### Статус проекта

- **Этапы 1–8**: полностью выполнены (83 теста, ruff clean)
- **Этап 9 (Тестирование и деплой)**: документирован в `docs/SETUP.md`. Остаётся:
  - [x] Заполнить `.env` реальными ключами
  - [x] Создать `credentials.json` для Google Sheets Service Account
  - [ ] Развернуть на Timeweb Cloud (по инструкции SETUP.md)
  - [ ] Настроить домен + SSL
  - [ ] Интеграционные тесты (опционально)

---

## Что сделано (Сессия: 22.06.2026 — Настройка окружения)

### Файлы

| Файл | Описание |
|---|---|
| `docs/ENV-SETUP.md` | Пошаговая инструкция настройки .env (DeepSeek, Google Sheets, Telegram, Instagram) |

### Настроенные сервисы

| Сервис | Статус | Данные |
|---|---|---|
| **DeepSeek API** | ✅ Подключён | `deepseek-v4-flash`, ключ `sk-6047...` |
| **Google Sheets** | ✅ Подключён | Service Account `travel-bot-sa@second-grail-439022-s9`, таблица `1YIU2UL__...`, 1 тестовый тур |
| **Telegram Bot** | ✅ Подключён | Бот `8953016988:AAFga...`, chat_id `904138085`, уведомления работают |
| **Instagram API** | ✅ Подключён | Аккаунт `_shelter_0` (Creator), страница `Test travel Bot` (Page ID: `1176392008892202`, IG User ID: `27250176798000778`), токен получен через Dashboard, App Secret добавлен в `.env` |

### Детали

- **Instagram** настроен через Meta Developer Console:
  - Создано приложение `Travel Bot Test1` (App ID: `1548133150338782`)
  - Instagram аккаунт `_shelter_0` добавлен как тестировщик
  - Токен сгенерирован через вкладку Instagram в Dashboard
  - Facebook-страница `Test travel Bot` создана и связана с Instagram
- **Graph API Explorer** использован для получения Page ID (`1176392008892202`)
- **Верификация разработчика** не пройдена (SMS не приходит на белорусский номер), но Instagram API работает через режим тестировщика

### Известные проблемы

1. **Токен Instagram** (IGAA...) — короткоживущий. Для продакшена нужен долгоживущий через Business Login.
2. **Page Access Token** (EAA...) получен через Explorer — живёт ~2 часа. Для webhook нужен стабильный токен.
3. **Webhook Instagram** не настроен — нет публичного URL. Настроить после деплоя на Timeweb Cloud.
4. **Верификация разработчика Meta** не пройдена — при попытке развернуть продакшен понадобится.
