> **УСТАРЕЛО** — описывает переход с LangGraph на LLM-driven архитектуру,
> который уже выполнен (коммит `35baecd`). Оставлено для истории.
>
> Актуальное описание: `docs/ARCHITECTURE.md`

# Fix Plan: LLM-driven диалог вместо риджидного pipeline

## Текущая проблема

**Симптом:** на любое сообщение от пользователя бот в итоге отвечает «не найдено туров, зову менеджеру» и шлёт уведомление в Telegram.

**Ожидание:** нейросеть сама определяет суть сообщения и решает, что ответить. Ответы должны разниться в зависимости от контекста.

---

## 🔴 Коренная причина 1: Сериализация сессий убивает LangChain-сообщения

**Файл:** `src/db/sessions.py:83`

```python
# Текущий код (СЛОМАН):
conn.execute(
    "...",
    (client_id, json.dumps(state, default=str)),  # default=str !
)
```

`json.dumps(state, default=str)` превращает `HumanMessage`/`AIMessage` (Pydantic-модели LangChain) в обычные строки вида:

```
"content='привет' additional_kwargs={} response_metadata={}"
```

При загрузке (`json.loads`) они становятся **plain str**, а не `HumanMessage`/`AIMessage`.

### Что ломается:

| Последствие | Где | Почему |
|---|---|---|
| `isinstance(m, HumanMessage)` → `False` | `nodes.py:clarify`, `prompts.py:build_context` | Старые сообщения — строки, а не объекты |
| `msg.content` → `AttributeError` | `prompts.py:build_context` | У строк нет атрибута `.content` |
| `ai_msgs` считает ВСЕ старые сообщения как AI | `nodes.py:clarify` | Не-HumanMessage = считается AI |
| После 1-2 обменов `ai_msgs >= 3` → **форсируется `search_tours`** | `nodes.py:clarify` | Даже если пользователь не про туры |

### 🔧 Фикс:

**До** (сломано):
```python
json.dumps(state, default=str)
```

**После** (работает):
```python
from langchain_core.messages import messages_to_dict, messages_from_dict

# save_session
state_copy = dict(state)
state_copy["messages"] = messages_to_dict(state["messages"])
conn.execute("...", (client_id, json.dumps(state_copy, ensure_ascii=False)))

# get_session
raw = json.loads(row["state"])
raw["messages"] = messages_from_dict(raw["messages"])
```

`messages_to_dict` сериализует сообщения в JSON-совместимые dict'ы с полями `type`, `data.content`, `data.additional_kwargs` и т.д. `messages_from_dict` восстанавливает точный тип сообщения (`HumanMessage`, `AIMessage`) со всеми полями. `isinstance` и `.content` работают корректно.

---

## 🔴 Коренная причина 2: Риджидный pipeline вместо LLM-driven диалога

### Текущая архитектура (as-is)

```
START → route_from_start()
  ├─ book (если current_step в _BOOKING_STEPS)
  ├─ handle_tour_selection (если current_step == "awaiting_selection")
  └─ classify → route_by_request_type()
       ├─ tour_search → clarify ──→ (после 3 итераций) ──→ search_tours → present_tours
       │                              (или если все параметры собраны)         │
       │                                                                       ▼
       │                                                              escalate ("не найдено")
       ├─ faq → faq_search → escalate|END
       ├─ complaint → escalate
       ├─ talk_to_manager → escalate
       ├─ booking → book
       └─ greeting/unknown → clarify ──→ ... (тот же pipeline)
```

**Проблема:** LLM используется только для:
1. Классификации типа запроса (classify)
2. Извлечения структурированных полей (clarify)
3. Форматирования результатов (present_tours)

LLM **не управляет диалогом**. Он лишь заполняет поля TypedDict. После 3 итераций `clarify` **принудительно** форсирует `search_tours`, даже если пользователь вообще не про туры спрашивал.

Все нетривиальные запросы в итоге идут через `search_tours`, который при 1 тестовом туре всегда возвращает пустой результат → `escalate`.

### 🔧 Фикс: LLM-driven архитектура (to-be)

```
START → converse() (LLM с ПОЛНЫМ контекстом диалога)
  ├─ action="respond"  → END (LLM сам написал ответ, общаемся)
  ├─ action="search"   → search_tours → present_tours → END|escalate
  ├─ action="book"     → book → END
  ├─ action="escalate" → escalate → END
  └─ action="faq"      → faq_search → END
```

#### Как работает `converse()`:

1. Получает всю историю диалога + `tour_params` (если есть) + `found_tours` (если есть)
2. Вызывает LLM с единым промптом-оракулом
3. LLM возвращает JSON:
   ```json
   {
     "action": "respond|search|book|escalate|faq",
     "reply": "текст ответа пользователю"
   }
   ```
4. Если `action == "respond"` — ответ уже готов, граф идёт в END (LLM просто поболтал с пользователем)
5. Если `action == "search"` — `converse` сохраняет `reply` как временный, граф идёт в `search_tours` → `present_tours`. Если туры найдены — показываются; если нет — говорится «не нашёл, передал менеджеру»
6. Если `action == "book"` — идёт в `book` (существующий степ-машина сбора контактов)
7. Если `action == "escalate"` — идёт в `escalate` (Telegram-уведомление)
8. Если `action == "faq"` — идёт в `faq_search` (RAG)

#### Промпт для `converse` (`prompts.py:CONVERSE_PROMPT`):

```
Ты — ИИ-туристический агент в Instagram. Язык — русский, тон — дружелюбный экспертный, с эмодзи.

У тебя есть:
- История диалога:
{context}

- Параметры поиска (если есть):
{tour_params}

- Найденные туры (если есть):
{tours}

Определи action:
- "respond": пользователь просто общается, задаёт вопросы без явного поиска тура. Ответь сам.
- "search": пользователь ищет/уточняет тур (направление, даты, бюджет). Только если явно про тур!
- "book": пользователь хочет забронировать / записаться / оставить контакты
- "escalate": жалоба, просьба поговорить с менеджером, сложный запрос, индивидуальный подбор
- "faq": вопрос про визы, документы, страховку, погоду, багаж, оплату

ВАЖНО:
- Если пользователь просто здоровается, спрашивает как дела, или говорит что-то не про туры — используй "respond"
- Не выдумывай параметры тура, если пользователь их не называл
- Не иди в search_tours, если пользователь не просил найти тур

В поле "reply" напиши ответ пользователю, который будет отправлен.
```

---

## 🔴 Коренная причина 3: Google Sheets — 1 тестовый тур

**Файл:** `test_out.json` / `credentials.json` / Google Sheets таблица

В Google Sheets всего 1 тур (Анталья All-Inclusive 1200$). Любой запрос, отличный от этого, возвращает 0 результатов → escalate.

### 🔧 Фикс:

1. Добавить больше туров в Google Sheets (разные направления: Турция, Египет, ОАЭ, Таиланд и т.д.)
2. Или реализовать fallback-поиск: при пустом результате не сразу escalate, а предложить похожие направления или спросить, что ещё интересует

---

## 📋 Полный чеклист изменений

### Шаг A. Починить сериализацию сессий (1 файл, критично)

- [ ] `src/db/sessions.py` — заменить `json.dumps(state, default=str)` на `messages_to_dict`/`messages_from_dict`

### Шаг B. LLM-driven архитектура (4 файла)

- [ ] `src/ai/prompts.py` — новый промпт `CONVERSE_PROMPT`, удалить/упростить старые
- [ ] `src/ai/nodes.py` — новая нода `converse()`, убрать `classify_node` и `clarify`
- [ ] `src/ai/engine.py` — новый граф с converse как главной точкой входа
- [ ] `src/ai/classifier.py` — удалить или объединить с converse

### Шаг C. Наполнение данными

- [ ] Добавить туры в Google Sheets (минимум 5-10 разных направлений)

---

## Как тестировать

```bash
# Существующие тесты
python -m pytest tests/ -v

# После изменений — добавить тесты для converse-ноды:
# - respond (привет, как дела)
# - search (хочу тур в турцию)
# - book (хочу забронировать)
# - escalate (жалоба)
# - faq (вопрос про визу)
```
