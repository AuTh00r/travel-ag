---
name: travel-bot-dev
description: >
  ИИ-помощник турагентства: чат-бот на Python + LangGraph + DeepSeek V4,
  работающий через Instagram Direct, с Google Sheets (базы туров и заявок),
  ChromaDB RAG для FAQ, SQLite сессий и Telegram-уведомлениями менеджерам.
  Деплой на Docker → Timeweb Cloud (РБ).
  Использовать при разработке, отладке, тестировании и деплое любого компонента
  проекта travel-agent-bot. Триггерится на упоминании проекта, агента, тура,
  Instagram-канала, LangGraph, RAG, ChromaDB, Google Sheets интеграции,
  Telegram-уведомлений или деплоя бота.
---

# Travel Bot Dev — Skill для ИИ-помощника турагентства

## Контекст проекта

Чат-бот / агент для турагентства, полностью автоматизирующий первый контакт
с клиентом через Instagram Direct. Язык общения — русский, дружелюбный
экспертный тон с эмодзи.

**Стек:** Python 3.11+ / FastAPI / LangGraph / DeepSeek V4 (DeepSeek-R2)
через API / Google Sheets API / ChromaDB / SQLite / Telegram Bot API / Docker

**Региональные особенности:** Республика Беларусь (РБ). Хостинг — Timeweb Cloud.

Подробный план реализации: `PLAN.md` в корне проекта.

## Стандарты кода

- Все промпты LLM — на русском языке, дружелюбный экспертный тон, эмодзи приветствуются
- Pydantic модели для всех данных (Tour, Client, Request)
- `structlog` для логирования
- Type hints обязательно на всех функциях
- Форматирование: `black` (line-length=100)
- Линтер: `ruff`
- Строки: f-strings
- Импорты: absolute imports от `src.`
- Ошибки: кастомные исключения в `src/exceptions.py`
- Конфиг: Pydantic Settings через `src/config.py`, переменные из `.env`

## Структура проекта

```
travel-agent-bot/
├── PLAN.md
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── src/
│   ├── main.py                  # FastAPI сервер + webhooks
│   ├── config.py                # Pydantic Settings из .env
│   ├── exceptions.py            # Кастомные исключения
│   ├── channels/
│   │   ├── base.py              # Абстрактный интерфейс канала (ABC)
│   │   └── instagram.py         # Instagram Webhook handler
│   ├── ai/
│   │   ├── engine.py            # LangGraph — граф диалога (StateGraph)
│   │   ├── states.py            # TypedDict состояние диалога
│   │   ├── nodes.py             # Функции узлов графа
│   │   ├── classifier.py       # Классификация типа запроса
│   │   ├── tour_search.py       # Поиск туров в Google Sheets
│   │   ├── faq.py               # RAG для FAQ через ChromaDB
│   │   └── prompts.py           # Системные промпты (русский)
│   ├── services/
│   │   ├── llm.py               # Обёртка над DeepSeek API (langchain)
│   │   ├── google_sheets.py     # Чтение туров, запись заявок
│   │   ├── telegram_notify.py   # Уведомления менеджерам
│   │   └── embeddings.py        # Эмбеддинги для RAG (DeepSeek / OpenAI)
│   ├── models/
│   │   ├── tour.py              # Pydantic: Tour
│   │   ├── client.py            # Pydantic: Client
│   │   └── request.py           # Pydantic: BookingRequest
│   └── db/
│       └── sessions.py          # SQLite: хранение сессий диалогов
├── data/
│   └── faq/                     # FAQ‑файлы для RAG (.txt / .md)
├── tests/
│   ├── test_engine.py
│   ├── test_instagram.py
│   └── test_tour_search.py
└── docs/
    └── SETUP.md
```

## Граф состояний LangGraph

```
START → GREETING → CLASSIFY ─┬─ TOUR_REQUEST → CLARIFY → SEARCH_TOURS → PRESENT_TOURS → BOOK
                              │                                                          │
                              ├─ FAQ → FAQ_SEARCH → (ответ) ──────────────────────────┘
                              │                                                          │
                              ├─ COMPLAINT → ESCALATE                                    │
                              │                                                          │
                              └─ TALK_TO_MANAGER → ESCALATE                              │
                                                                   │
                                                                   ▼
                                                              END / ESCALATE
```

### Описание состояний

| Состояние | Что делает | Выход |
|---|---|---|
| GREETING | Приветствие, определение цели клиента | → CLASSIFY |
| CLASSIFY | Классификация: подбор тура / FAQ / жалоба / менеджер | ветвление |
| CLARIFY | Извлечение/уточнение параметров (направление, даты, бюджет, люди, тип) | → SEARCH_TOURS |
| SEARCH_TOURS | Поиск в Google Sheets по параметрам | → PRESENT_TOURS |
| PRESENT_TOURS | Формирование ответа со ссылками на Google Docs | → BOOK |
| BOOK | Предложение записаться, сбор контактов (имя → телефон → email) | → END или ESCALATE |
| FAQ_SEARCH | RAG‑поиск в ChromaDB по FAQ | → END |
| ESCALATE | Формирование карточки для менеджера, отправка в Telegram | → END |

Для детальных шаблонов кода каждого узла см. `references/langgraph-templates.md`.

## Google Sheets — структура

### База туров (лист «Туры»)

| Столбец | Тип | Пример |
|---|---|---|
| Название | string | Анталья All-Inclusive 7 ночей |
| Направление | string | Турция, Анталья |
| Тип | string | Пляжный, All-Inclusive |
| Даты | string | 15.06–22.06.2026 |
| Цена | string | 1200$ |
| Длительность | string | 7 ночей |
| Ключевые слова | string | море, пляж, семья, отель |
| Ссылка | URL | https://docs.google.com/... |
| Доступно | string | Да |

### Заявки (лист «Заявки»)

| Столбец | Тип | Пример |
|---|---|---|
| Дата заявки | datetime | 22.06.2026 14:30 |
| Имя | string | Иван Петров |
| Телефон | string | +375291234567 |
| Email | string | ivan@mail.com |
| Направление | string | Турция |
| Бюджет | string | 2000$ |
| Кол-во человек | int | 2 |
| Выбранный тур | string | Анталья All-Inclusive |
| Статус | enum | Новая / В обработке / Подтверждена / Оплачена |
| Источник | string | Instagram |
| Тег | string | Нужен звонок |

## Конфигурация (.env)

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat
INSTAGRAM_ACCESS_TOKEN=EAAxxx
INSTAGRAM_VERIFY_TOKEN=my_secret_token
INSTAGRAM_PAGE_ID=123456789
INSTAGRAM_IG_USER_ID=123456789
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_TOURS_SHEET_ID=xxx
GOOGLE_REQUESTS_SHEET_ID=xxx
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_MANAGER_CHAT_ID=123456789
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
```

LLM модель переключается через `DEEPSEEK_MODEL` (deepseek-chat для V3, deepseek-reasoner для V4/R2).

## Чеклист этапов

Для отслеживания прогресса. Каждый этап считается готовым, когда выполняются все критерии.

### Этап 1. Настройка окружения
- [ ] requirements.txt с зависимостями
- [ ] Dockerfile + docker-compose.yml
- [ ] .env.example
- [ ] src/config.py (Pydantic Settings)
- [ ] Команда `docker compose up` запускается без ошибок
- [ ] FastAPI health-check на `/health`

### Этап 2. Instagram API
- [x] Webhook endpoint `/webhook/instagram` (GET — верификация, POST — сообщения)
- [x] hub.challenge верификация работает
- [x] Приём текстового сообщения от клиента
- [x] Отправка ответа через Instagram Graph API
- [ ] ngrok туннель для локальной разработки (когда будет реальный Instagram аккаунт)

### Этап 3. AI-движок LangGraph
- [ ] StateGraph с всеми состояниями
- [ ] Классификация запроса (LLM-based)
- [ ] Извлечение параметров тура
- [ ] Системные промпты на русском языке
- [ ] Контекст диалога (память)
- [ ] Тестовый скрипт для локальной проверки графа

### Этап 4. Google Sheets
- [ ] Подключение через google-api-python-client
- [ ] Чтение базы туров
- [ ] Поиск по параметрам (направление, бюджет, даты, тип)
- [ ] Fuzzy matching по ключевым словам
- [ ] Запись заявок

### Этап 5. RAG FAQ
- [ ] ChromaDB инициализация
- [ ] Загрузка FAQ документов
- [ ] Векторный поиск
- [ ] Интеграция в граф LangGraph

### Этап 6. Сбор контактов
- [ ] Последовательный сбор (имя → телефон → email)
- [ ] Валидация (телефон: +375..., email: формат)
- [ ] Сохранение в Google Sheets + SQLite

### Этап 7. Уведомления менеджерам
- [ ] Telegram-бот отправляет уведомления
- [ ] Карточка: контакты + суть запроса + история + тег
- [ ] Все триггеры эскалации работают

### Этап 8. Доп. функции
- [ ] Напоминания клиенту
- [ ] Статусы заявок
- [ ] Ссылка на бронь/оплату (если применимо)

### Этап 9. Тестирование и деплой
- [ ] Unit-тесты (pytest)
- [ ] Integration-тесты
- [ ] Ручное тестирование сценариев
- [ ] Docker-деплой на Timeweb Cloud
- [ ] SSL, домен
- [ ] SETUP.md

## Команды

```bash
# Запуск локально
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Запуск через Docker
docker compose up --build

# Тесты
pytest tests/ -v

# Линтинг
ruff check src/

# Форматирование
black src/ tests/

# ngrok (для Instagram webhook при локальной разработке)
ngrok http 8000
```

## Триггеры эскалации

Агент должен передать диалог менеджеру при обнаружении:
- Прямой запрос на человека: «поговорить с менеджером», «живой человек», «оператор»
- Сложный/нестандартный запрос (LLM определяет как «complex»)
- Ноль результатов поиска туров
- Индивидуальный подбор: «подберите мне», «индивидуально»
- Срочность: «срочно», «побыстрее», «быстро»
- Жалоба: «жалоба», «недоволен», «проблема»
- Клиент выбрал «Получить консультацию менеджера»

## Ссылки на детальные справочники

- Шаблоны LangGraph (код узлов): `references/langgraph-templates.md`
- Instagram API справочник: `references/instagram-api.md`
