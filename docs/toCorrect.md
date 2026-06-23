# Session: 23.06.2026 — Диагностика и исправление ошибки "Произошла техническая ошибка"

## 1. Симптом
- Пользователь пишет в Instagram Direct
- В ответ получает: "Произошла техническая ошибка. Наши специалисты уже работают над этим. Попробуйте позже! 🛠️"
- Текст ошибки определён в `main.py:170-174`

## 2. Полная трассировка вызова

```
POST /webhook/instagram (main.py:146)
├─ 1. raw_body = await request.body()               # main.py:150
├─ 2. verify_signature(raw_body, sig)               # main.py:156 → instagram.py:20
│     INSTAGRAM_APP_SECRET задан (.env:6 = 0219b2cc...)
│     → HMAC-SHA256 проверка, результат: ✅
├─ 3. payload = await request.json()                 # main.py:160
├─ 4. receive_message(payload)                       # main.py:161 → instagram.py:59
│     Парсинг entry[].messaging[].message.text
│     Фильтр is_echo, возврат [(sender_id, text)]
├─ 5. process_with_ai(sender_id, text)               # main.py:167
│  ├─ get_session(sender_id)                         # main.py:126 → sessions.py:46
│  │    SQLite: SELECT state FROM sessions WHERE client_id=?
│  │    Нет записи → _new_session() с current_step="greeting"
│  ├─ session["messages"].append(HumanMessage(text)) # main.py:127
│  ├─ build_graph()                                  # main.py:129 → engine.py:43-100
│  │    StateGraph(DialogState), 8 узлов, 5 conditional edges
│  ├─ graph.ainvoke(session)                         # main.py:130
│  │  └─ ПОЛНЫЙ ОБХОД ГРАФА (см. п.3)
│  ├─ Отправка AI-ответов (main.py:132-141)
│  └─ save_session(sender_id, result)                # main.py:143
└─ 6. Возврат {"status": "ok"}                      # main.py:178
```

## 3. Полный обход графа (что происходит внутри graph.ainvoke)

### 3.1. Маршрутизация START
`route_from_start()` → `engine.py:18-21`
  `current_step = "greeting"` → NOT в `_BOOKING_STEPS` → return `"greeting"`
  → узел `"greeting"`

### 3.2. Узел "greeting" (nodes.py:25-31)
`GREETING_PROMPT` → LLM (`deepseek-v4-flash`, temp=0.7, max_tokens=1024)

Результат: `AIMessage("👋 Здравствуйте! Я — ИИ-помощник турагентства...")`

State после:
```
messages = [HumanMessage(text), AIMessage(greeting)]
current_step = "greeting"
```

→ ребро → узел `"classify"`

### 3.3. Узел "classify" (classifier.py:10-24) ⚠️ **БАГ #1**
`classify_node()` → `nodes.py:34-35` → `classifier.py:10-24`

```python
last_message = state["messages"][-1].content   # ← classifier.py:11
                                               # БЕРЁТ ПОСЛЕДНЕЕ = ПРИВЕТСТВИЕ БОТА
```

Классифицирует: `"👋 Здравствуйте! Я — ИИ-помощник турагентства..."`  
**Вместо** исходного запроса пользователя: `"Хочу в Турцию на море"`

LLM → `response_format=json_object` → `{"request_type": "...", ...}`

```python
result = json.loads(response.content)           # ← classifier.py:18 ⚠️ БАГ #2
                                                # НЕТ try/except
```

Если LLM вернула невалидный JSON → `json.JSONDecodeError` → **EXCEPTION**

#### 3.3.1. Если JSON валиден → `route_by_request_type()` → `engine.py:67-74`
Скорее всего `"greeting"` или `"unknown"` → идёт в `"clarify"`

### 3.4. Узел "clarify" (nodes.py:38-79) — если маршрутизирован сюда
```python
last_message = state["messages"][-1].content  # СНОВА последнее (AIMessage)
```
LLM (json mode) → `EXTRACT_PROMPT` → извлекает null для всех полей

`missing = ["destination", "dates", "budget", "travelers", "tour_type"]`

Если `missing` не пуст и `len(messages) < 8`:
  LLM → `CLARIFY_PROMPT(missing_param=missing[0])`
  → `"Куда планируете полететь?"`

State после: `current_step = "clarify"` (остаётся в clarify)
→ conditional edge: `"ask"` → снова `"clarify"`
→ **ЦИКЛ**, пока не будут собраны все params или `messages >= 8`

### 3.5. При положительном исходе (все params собраны)
`current_step = "search"` → conditional → `"search_tours"`

### 3.6. Узел "search_tours" (tour_search.py:10-34)
`GoogleSheetsService.search_tours(params)`
- Если ошибка → `GoogleSheetsError` → caught → `needs_escalation=True`
- Если найдены → `found_tours = [...]`

### 3.7. Узел "present_tours" (nodes.py:86-115)
- Если tours пустой → `needs_escalation=True`
- Если есть → LLM форматирует ответ → `"presented"`

### 3.8. Терминальные узлы
- `"book"` — сбор контактов (name → phone → email → confirm)
- `"escalate"` → Telegram уведомление менеджеру
- `"faq_search"` → ChromaDB → LLM → ответ

## 4. Причина ошибки (до пополнения баланса)
DeepSeek API: **402 Payment Required**
- `graph.ainvoke()` на первом же LLM-вызове (greet или classify) падает
- exception в `main.py:168`
- отправляется `"Произошла техническая ошибка..."`
- `Instagram.send_message()` работает (токен жив), пользователь видит текст

## 5. Статус после пополнения баланса DeepSeek (23.06.2026)

| Компонент | Статус | Детали |
|---|---|---|
| DeepSeek API | ✅ | `deepseek-v4-flash`, Status 200 |
| LangGraph | ✅ | Граф компилируется, узлы работают |
| classify JSON | ⚠️ | **БАГ #1, #2** — классифицирует не то сообщение |
| Instagram webhook | ✅ | Получает POST, верифицирует подпись |
| Instagram send | ✅ | Токен `EAA...` жив (пока short-lived) |
| Google Sheets | ✅ | `credentials.json` существует, чтение/запись |
| ChromaDB RAG | ✅ | 43 FAQ записи, поиск работает |
| SQLite sessions | ✅ | get/save работают |
| Telegram notify | ✅ | Бот создан, `chat_id` настроен |

## 6. Найденные баги

### БАГ #1: classify() анализирует не то сообщение
- **Файл:** `src/ai/classifier.py:11`
- **Проблема:** `state["messages"][-1].content` — берёт ПОСЛЕДНЕЕ сообщение в истории
- **Последствие:** После node `"greeting"` последнее = `AIMessage(greeting)`, а не запрос пользователя
- **Должно:** брать последнее `HumanMessage` (последнее входящее от пользователя)
- **Влияние:** запрос клиента никогда не классифицируется, маршрутизация ломается, clarify задаёт не те вопросы

### БАГ #2: classify() нет обработки ошибок JSON
- **Файл:** `src/ai/classifier.py:18`
- **Проблема:** `json.loads(response.content)` — нет try/except
- **Сравнение:** `clarify()` в `nodes.py:53-57` имеет try/except
- **Влияние:** если LLM вернёт невалидный JSON → `json.JSONDecodeError` → EXCEPTION → error message
- **Исправление:** обернуть в `try/except (json.JSONDecodeError, TypeError)`

### БАГ #3 (UX): каждое AI-сообщение отправляется отдельным POST
- **Файл:** `src/main.py:132-141`
- **Проблема:** for msg in result["messages"] → 1 API call per message
- **Последствие:** после greet = 1 msg, после clarify = ещё 1 msg → 2 отдельных сообщения в Instagram
- **Влияние:** пользователь получает "кашу" из сообщений вместо одного связного ответа
- **Исправление:** склеивать все `AIMessage` в один текст перед отправкой

### БАГ #4 (причина): неверная маршрутизация из-за БАГА #1
- **Файл:** `src/ai/engine.py:67-74`
- **Проблема:** `classify` возвращает классификацию приветствия бота вместо запроса пользователя
- **Влияние:** неправильные переходы в графе (greeting → clarify вместо tour_search → search_tours)
- **Исправление:** после фикса БАГА #1 маршрутизация станет корректной

## 7. Второстепенные проблемы (не критические)

### 7.1. Instagram токен короткоживущий
- `.env:7` = `EAAWABNZA9rt4BR5prr...`
- Тип: Page Access Token из Graph API Explorer
- Срок жизни: ~2 часа (short-lived) или ~60 дней (extended)
- При истечении: `send_message()` → `InstagramError`
- **Решение:** получить долгоживущий токен через Instagram Business Login (FB Login)

### 7.2. Graph API версия v25.0
- `instagram.py:18`: `BASE_URL = "https://graph.facebook.com/v25.0"`
- Meta поддерживает каждую версию ~2 года
- Если v25.0 депрекейтнута, `send_message()` начнёт падать
- **Рекомендация:** переключиться на latest: `"https://graph.facebook.com/latest"`

### 7.3. Instagram User ID в .env
- `.env:10`: `INSTAGRAM_IG_USER_ID=17841437870938776`
- HANDOVER.md: `27250176798000778`
- Вероятно, токен и ID от разных аккаунтов/страниц
- **Рекомендация:** проверить соответствие при перевыпуске токена

### 7.4. thinking mode в deepseek-v4-flash включён по умолчанию
- Модель возвращает `reasoning_content` + может вернуть пустой `content`
- `langchain-openai` справляется (content заполняется из финального ответа)
- Но при малом `max_tokens` (1024 в `get_llm()`) reasoning может съесть весь лимит
- **Рекомендация:** рассмотреть увеличение `max_tokens` в `get_llm()` до 2048

## 8. Конфигурация (текущая — секреты удалены)

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-v4-flash
INSTAGRAM_APP_SECRET=xxx
INSTAGRAM_ACCESS_TOKEN=xxx
INSTAGRAM_VERIFY_TOKEN=xxx
INSTAGRAM_PAGE_ID=xxx
INSTAGRAM_IG_USER_ID=xxx
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_TOURS_SHEET_ID=xxx
GOOGLE_REQUESTS_SHEET_ID=xxx
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_MANAGER_CHAT_ID=xxx
```

## 9. План исправлений

### Приоритет 1 (сейчас — влияет на качество ответов)
1. **classifier.py:11** — исправить индекс на первое `HumanMessage`
2. **classifier.py:18** — добавить `try/except (json.JSONDecodeError, TypeError)`

### Приоритет 2 (UX)
3. **main.py:132-141** — объединять `AIMessage` в один текст перед отправкой

### Приоритет 3 (безопасность/стабильность)
4. Получить долгоживущий Instagram токен (Business Login)
5. Обновить Graph API до `latest` (v25.0 → latest)
6. Увеличить `max_tokens` в `get_llm()` до 2048

## 10. Проверено (результаты тестов 23.06.2026)

- DeepSeek API — Status 200, модель `deepseek-v4-flash`, JSON mode работает
- `greet()` — 6 сек, возвращает `AIMessage` с приветствием
- `classify()` с корректным HumanMessage — возвращает валидный JSON с `request_type`
- `langchain-openai` 1.3.2 — совместим с DeepSeek API
- `langgraph` 1.2.6 — Graph компилируется
- `chromadb` 1.5.9 — FAQ загружен (43 записи)
- Instagram send — сообщение доходит до пользователя
- Тесты: `pytest tests/ -v` → 87 passed

## 11. Версии пакетов (локально)

| Пакет | Версия |
|---|---|
| langgraph | 1.2.6 |
| langchain-core | 1.4.8 |
| langchain-openai | 1.3.2 |
| chromadb | 1.5.9 |
| openai | (latest) |
| httpx | (latest) |
