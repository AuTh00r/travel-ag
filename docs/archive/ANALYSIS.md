> **УСТАРЕЛО** — описывает удалённую LangGraph-архитектуру (ноды, граф состояний,
> classifier). 24.06.2026 проект переведён на single-LLM-call архитектуру
> (коммит `35baecd`). Оставлено для истории.
>
> Актуальное описание: `docs/ARCHITECTURE.md`

# Travel Agent Bot — Анализ и план улучшения ответов

## 1. Текущая архитектура (as-is)

```
Instagram DM → POST /webhook/instagram → process_with_ai()
  → get_session() → append HumanMessage → graph.ainvoke(session)
    → START → route_from_start()
        → classify → route_by_request_type()
            → clarify (извлечение параметров, итеративно)
            → search_tours → present_tours
            → faq_search
            → book (хардкодный степ-машина)
            → escalate (Telegram уведомление)
    → END
  → отправка AIMessage-ов в Instagram
  → save_session()
```

**Граф:** 8 нод, 6 conditional edges, TypedDict `DialogState` в SQLite.

---

## 2. Ключевые проблемы

### 2.1. Граф обрывается после `present_tours`
- `selected_tour` **никогда не устанавливается** — всегда `None`
- `route_after_presentation()` → `end` (т.к. `selected_tour` is None и `needs_escalation` is False)
- Следующее сообщение пользователя уходит в полный цикл `START → classify`, теряя контекст

### 2.2. Нет селектора тура
- После показа туров пользователь пишет «хочу первый» — это просто текст, не обрабатывается
- Нет ноды, которая парсит ответ и устанавливает `selected_tour`

### 2.3. Каждый вызов — полный проход графа
- Пользователь: «Анталья» → classify → clarify → «бюджет?» → END
- Пользователь: «2000$» → **снова** classify → **снова** clarify
- Это дорого (лишние LLM вызовы) и ненадёжно

### 2.4. Промпты не видят историю диалога
- `EXTRACT_PROMPT` получает только `{message}` и `{known_params}`
- LLM не знает, что **мы уже спросили даты**, и пользователь ответил «август»

### 2.5. `book` — хардкод вместо LLM
- Все ответы зашиты строками в `nodes.py` (строки 170-281)
- Есть неиспользуемый `BOOK_PROMPT` (строка 105 в `prompts.py`)
- Нет обработки естественного языка — пользователь пишет «меня зовут Иван», а бот ждёт строго имя

### 2.6. `present_tours` не передаёт ссылки
- Формат: `f"{i+1}. {Название} — {Направление} — {Цена}"`
- Поле `Ссылка` (Google Doc) не включено в вывод

### 2.7. Нет обработки ошибок JSON
- `classifier.py:18` — если DeepSeek вернёт невалидный JSON, будет unhandled exception
- `nodes.py:63` — в `clarify` есть try, но если fail — пустой `result = {}`

### 2.8. SQLite без WAL-режима
- Каждый `_get_connection()` — новый connect без `PRAGMA journal_mode=WAL`
- При конкурентных запросах возможны блокировки

---

## 3. План исправлений

### Шаг 1-2. Новая нода `handle_tour_selection` + редизайн графа

**Нода `handle_tour_selection`:**
- Принимает последнее сообщение пользователя
- Сравнивает с `found_tours` (по номеру, названию, направлению)
- Если нашла совпадение → устанавливает `selected_tour`, переходит в `book`
- Если пользователь пишет «не то», «другое» → возвращает в `clarify`
- Если пользователь просит менеджера → `escalate`
- Если непонятно → переспрашивает

**Новый роутинг:**
```
present_tours → handle_tour_selection ─┬─ book (тур выбран)
                                        ├─ clarify (ещё варианты)
                                        ├─ escalate (не подходит)
                                        └─ END (переспросили, ждём ответ)
```

### Шаг 3. Контекст диалога во все промпты

Добавить **system message** в начало каждого LLM вызова c последними 3-5 сообщениями.

### Шаг 4. Структурированный `present_tours`

Включить в вывод: ссылку, цену, даты, длительность. Структурировать для LLM.

### Шаг 5. LLM-based booking

Заменить хардкод на `BOOK_PROMPT` + LLM, сохранив валидацию телефона/email.

### Шаг 6. JSON error handling

Оборачивать `json.loads` в try/except с повторным запросом или fallback.

### Шаг 7. SQLite WAL mode

```sql
PRAGMA journal_mode=WAL;
```

### Шаг 8. Чистка промптов

Единый стиль, чёткие инструкции, системный промпт с ролью бота.

### Шаг 9. Тесты

Тесты новой ноды, маршрутов графа, edge cases.

---

## 4. Структура нового графа (to-be)

```
START → route_from_start()
  ├─ (current_step в _BOOKING_STEPS) → book
  ├─ (current_step = "awaiting_selection") → handle_tour_selection
  └─ → classify → route_by_request_type()
       ├─ tour_search → clarify
       │     └─ (current_step="search") → search_tours → present_tours
       │           → handle_tour_selection → route_selection()
       │               ├─ book (тур выбран)
       │               ├─ clarify (ещё варианты, сброс current_step)
       │               ├─ escalate (не подходит)
       │               └─ END (переспрашиваем)
       ├─ faq → faq_search → END|escalate
       ├─ complaint → escalate → END
       ├─ talk_to_manager → escalate → END
       ├─ booking → book → END
       └─ greeting/unknown → clarify → END|search
```

---

## 5. Детали реализации

### 5.1. `handle_tour_selection` (nodes.py)

```python
SELECT_TOUR_PROMPT = """Ты — ИИ-агент турагентства. Пользователь увидел список туров.
Определи, какой тур он выбрал, или что хочет сделать.

Список туров:
{tours}

Сообщение пользователя: {message}

Ответь JSON:
{
  "action": "select|retry|escalate|ask_again",
  "selected_tour_index": null,
  "selected_tour_name": null,
  "reply": "ваш ответ пользователю"
}
"""
```

### 5.2. Context helper

```python
def _build_context(messages: list, max_history: int = 5) -> str:
    """Собрать последние сообщения в текстовый контекст."""
    lines = []
    for msg in messages[-max_history:]:
        role = "Клиент" if isinstance(msg, HumanMessage) else "Агент"
        lines.append(f"{role}: {msg.content[:500]}")
    return "\n".join(lines)
```

### 5.3. Structured present_tours

```python
tours_text = "\n\n".join(
    f"""[Тур {i+1}]
Название: {t.get('Название', '')}
Направление: {t.get('Направление', '')}
Тип: {t.get('Тип', '')}
Даты: {t.get('Даты', '')}
Цена: {t.get('Цена', '')}
Длительность: {t.get('Длительность', '')}
Ссылка: {t.get('Ссылка', '')}
Ключевые слова: {t.get('Ключевые слова', '')}"""
    for i, t in enumerate(tours)
)
```
