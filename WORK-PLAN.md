# План работ: устранение техдолга

> Статус: **выполнен**
> Дата: 2026-06-25, актуализировано 2026-06-26
> Назначение: исторический выполненный план. Не использовать как текущий backlog;
> актуальная архитектура описана в `docs/ARCHITECTURE.md`.
> Контекст: после рефакторинга `35baecd` (LangGraph → один LLM-вызов) накопились
> рассинхрон документации, недоехавшая в прод защита и мелкий cruft. Этот файл —
> план их устранения.

## Текущая архитектура (факт, на момент написания)

```
Instagram DM → POST /webhook/instagram (main.py)
  → verify_signature → dedup по mid → 200 OK мгновенно
  → asyncio.create_task(_process_safely)
      → process_with_ai(sender_id, text):
          get_session → history
          get_tours_text()        (17 DOCX в системном промпте, ~26K токенов)
          search_faq()            (ChromaDB RAG, top-3)
          build_full_prompt()     (prompts.py: system + history + user)
          llm.ainvoke()           (DeepSeek, один вызов)
          _extract_booking / _extract_escalation / _strip_markers  (регексы)
          → Google Sheets (бронь) + Telegram (эскалация)
          save_session → instagram.send_message
```

Ключевые файлы: `src/main.py`, `src/ai/prompts.py`, `src/services/{llm,tour_loader,google_sheets,telegram_notify}.py`, `src/db/{sessions,faq_db}.py`, `src/channels/instagram.py`.
`bot.py` — standalone референс (gitignored), в прод-пути НЕ участвует.

---

## Задача 1. Синхронизировать документацию

**Проблема:** `ANALYSIS.md`, `FIX-ROOT-CAUSE.md`, `HANDOVER.md` описывают
LangGraph-архитектуру (`converse()`, `nodes.py`, `engine.py`, `classifier.py`),
которой больше нет (удалена в `35baecd`). Кто угодно, открыв их, пойдёт по
ложному следу.

**Действия:**
1. Создать `docs/archive/` и переместить туда `ANALYSIS.md`, `FIX-ROOT-CAUSE.md`,
   `HANDOVER.md` с пометкой в шапке «УСТАРЕЛО — описывает удалённую
   LangGraph-архитектуру, оставлено для истории».
2. Написать актуальный `docs/ARCHITECTURE.md` — описание текущего
   single-LLM-call потока (схема выше + описание маркеров `===БРОНЬ===`/
   `===МЕНЕДЖЕР===`, как работают сессии, FAQ, загрузка туров).
3. Проверить `PLAN.md` — если описывает мёртвую архитектуру, тоже в archive.

**Готово, когда:** в корне нет `.md`, противоречащих коду; есть один
актуальный `docs/ARCHITECTURE.md`.

---

## Задача 2. Достроить детерминированный слой защиты (из `bot.py`)

**Контекст: защита уже есть — но только один слой.**
В проде работает **промптовый** слой: `_SECURITY_RULES` (`src/ai/prompts.py:63-68`)
встраивается в системный промпт при каждом вызове через `_build_system` (запрет
смены роли, раскрытия промпта, «я ИИ»). Это «мягкая» защита: её можно обойти
джейлбрейком, и она всё равно стоит платного вызова DeepSeek.

**Проблема:** отсутствует **детерминированный слой в коде**, который есть в
референсе `bot.py`, но не доехал в `src/`. Это бэкстоп поверх промпта:
- `check_input` — regex-детект инъекций **до** вызова LLM (блокирует
  детерминированно, экономит платный вызов);
- `is_rate_limited` — лимит сообщений/мин (антиспам, защита от расходов);
- `check_output` — ловит утечку «я ИИ / openai / anthropic» в ответе, **если**
  промпт всё-таки пробили.

Итог: нужно не «добавить отсутствующую защиту», а **достроить второй,
детерминированный слой поверх уже работающего промптового**.

| Слой | Где | Можно обойти джейлбрейком | Стоит вызова LLM |
|------|-----|:---:|:---:|
| Промптовый (`_SECURITY_RULES`) — уже в проде | `prompts.py` | да | да |
| Кодовый (`check_input`/`check_output`/rate-limit) — добавляем | `guard.py` | нет | нет |

**Действия:**
1. Новый модуль `src/services/guard.py`:
   - `check_input(text) -> tuple[bool, str]` — лимит длины (вынести в config),
     пустое сообщение, regex промпт-инъекций (перенести `INJECTION_PATTERNS`).
   - `check_output(text) -> str` — `OUTPUT_RED_FLAGS`, подмена на `FALLBACK_RESPONSE`.
   - `is_rate_limited(user_id) -> bool` — скользящее окно, `MAX_MESSAGES_PER_MINUTE`.
     In-memory `defaultdict`, по аналогии с `_processed_mids` в main.py.
2. Вынести пороги в `src/config.py`: `max_message_length`, `max_messages_per_minute`.
3. Подключить в `src/main.py`:
   - rate-limit — в начале `process_with_ai` (или в webhook-цикле), при срабатывании
     ответить вежливым отказом, НЕ дёргать LLM, залогировать `guard.rate_limited`.
   - `check_input` — перед `build_full_prompt`; при `injection`/`too_long` ответить
     заготовкой, залогировать `guard.input_rejected` с reason.
   - `check_output` — после `llm.ainvoke`, до отправки клиенту.
4. Тесты `tests/test_guard.py`: инъекция блокируется, длинное/пустое, rate-limit
   после N сообщений, output red flag → fallback.

**Готово, когда:** прод-путь прогоняет вход/выход через guard; тесты зелёные.

**Решить по ходу:** rate-limit считать per-sender (как в bot.py) — да.
Память чистится так же, как `_processed_mids` (ограничение размера).

---

## Задача 3. Логировать нераспарсенные маркеры

**Проблема:** бронь/эскалация держатся на том, что LLM выдаст ровно
`===БРОНЬ===` с полями. При temperature 0.7 формат иногда плывёт → бронь молча
теряется, в логах ничего.

**Действия:**
1. В `src/main.py` (`_extract_booking`/`_extract_escalation` или в `process_with_ai`):
   если в `raw_reply` встречается подстрока маркера (`===БРОНЬ` / `===МЕНЕДЖЕР`),
   но извлечение вернуло `None` (или нет обязательных полей) — `logger.warning`
   с `marker.parse_failed`, типом маркера и сырым фрагментом.
2. Не менять поведение отправки клиенту — только наблюдаемость.

**Готово, когда:** каждый случай «маркер был, но не распарсился» виден в логах.

---

## Задача 4. Убрать cruft

**Проблема:** `requirements.txt` тянет `langgraph` и `langchain-community`,
которых нет в коде; в рабочей папке scratch-файлы.

**Действия:**
1. `requirements.txt`: удалить `langgraph>=0.2.0` и `langchain-community>=0.3.0`
   (проверено grep'ом — не импортируются). Поправить комментарий-заголовок
   «AI / LangGraph» → «AI / LLM». Оставить `langchain-core`, `langchain-openai`,
   `openai`, `chromadb`, `sentence-transformers`.
2. Почистить незакоммиченный scratch (всё gitignored или untracked, кода не трогает):
   `tours/analyze_dates.py`, `tours/analyze_dates2.py`, `tours/date_analysis*.txt`,
   `check_tour_links.py`, локальные `bot_stderr*.log` / `bot_stdout*.log`, `nul`.
   Удаление согласовать перед запуском.
3. Удалить устаревшие `.pyc` удалённых модулей (`src/ai/__pycache__/engine.*`,
   `states.*`, `nodes.*`, `classifier.*`) — мусор от мёртвого кода.

**Готово, когда:** `requirements.txt` отражает реальные импорты; рабочая папка
без scratch-хлама.

---

## Порядок выполнения

1. Задача 4 (cruft) — быстро, разгружает картину.
2. Задача 1 (docs) — фиксируем актуальную архитектуру до изменений кода.
3. Задача 2 (guard) — основная работа.
4. Задача 3 (логи маркеров) — мелкая, в конце.
5. `pytest tests/ -q` — всё зелёное. Актуальный набор: 117 тестов в 8 файлах.

## Принципы

- Прод-логику (`main.py`, обработка вебхуков, дедуп, локи) не трогаем сверх
  необходимого — она выстрадана и работает.
- Каждая задача — отдельный коммит с понятным сообщением.
- Тесты не должны проседать ниже текущих 117.
