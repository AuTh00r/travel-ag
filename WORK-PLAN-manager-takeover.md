# План: пауза бота при вмешательстве живого менеджера

> Статус: **готов к исполнению** (исполняет отдельный агент)
> Дата: 2026-06-25
> Тип: новая фича. Прод-логику вебхуков/дедупа/локов трогаем минимально.

---

## 1. Контекст (зачем)

Бот отвечает на каждое сообщение клиента в Instagram Direct. Если живой менеджер
вручную пишет клиенту из приложения Instagram / Meta Business Suite, бот
продолжает отвечать параллельно — два «голоса» в одном чате.

**Цель:** как только в переписке появляется реплика живого человека от имени
бизнес-аккаунта — бот замолкает **в этом конкретном диалоге** и не мешает.
Возврат бота — автоматический, после недели простоя менеджера. Никаких ручных
команд.

---

## 2. Как Instagram сообщает о вмешательстве человека (механизм)

В IG Messaging **нет** признака «это менеджер». Любое сообщение, отправленное
бизнес-аккаунтом — ботом через Send API **или** человеком из инбокса —
прилетает обратно вебхуком как **эхо** (`message.is_echo == true`).

Сейчас `receive_message` (`src/channels/instagram.py:73`) молча выбрасывает все
эхо. Нужно их разбирать и отличать «эхо своего бота» от «эхо живого менеджера»:

- **По `mid`:** бот при каждой отправке запоминает `message_id`, который вернул
  Send API. Эхо со знакомым `mid` → это сам бот (игнор). Эхо с незнакомым `mid`
  → написал человек → пауза.
- **По `app_id` (страховка):** в эхе от API-отправки присутствует `app_id`
  нашего приложения; у ручного ответа из инбокса его нет (или чужой). Это
  закрывает гонку после рестарта, когда in-memory набор `mid` сброшен.

Для эха **клиент — это `recipient.id`** (в эхе `sender` = бизнес-аккаунт, а
`recipient` = клиент, с которым переписка). Это ключевой нюанс.

---

## 3. Решения (подтверждены заказчиком)

- **Возврат:** авто по простою. Пауза держится, пока
  `now - manager_last_at < TTL`. Каждое новое сообщение менеджера обновляет
  `manager_last_at`. **TTL = 1 неделя (10080 минут)**, вынесен в конфиг.
- **Ручное управление:** нет. Только автоопределение по эхо.
- **Во время паузы:** входящие от клиента молча пишем в `history`, LLM не
  вызываем, **ничего не отправляем** — ни ответ, ни rate-limit/guard-заглушку,
  ни эскалацию.

---

## 4. Изменения по файлам (с готовым кодом)

### 4.1. `src/config.py`

В блок Instagram (после `instagram_ig_user_id`, строка 20) добавить:

```python
    instagram_app_id: str = ""  # для распознавания собственных эхо (опционально)
```

Отдельным блоком (например, после Security, строка 39) добавить:

```python
    # Пауза бота при вмешательстве живого менеджера
    # Сколько бот молчит в чате после последней реплики менеджера. 10080 = 7 дней.
    manager_takeover_ttl_minutes: int = 10080
```

> При желании продублировать обе переменные в `.env.example` (необязательно —
> у обеих есть дефолты).

---

### 4.2. `src/db/sessions.py`

Вверху файла добавить импорт:

```python
from datetime import datetime, timezone
```

В `_new_session` (строка 56-57) добавить поле `manager_last_at`:

```python
def _new_session(client_id: str) -> dict:
    return {
        "history": [],
        "client_id": client_id,
        "escalation_count": 0,
        "manager_last_at": None,
    }
```

Добавить новый хелпер (например, после `save_session`):

```python
def is_manager_active(session: dict, ttl_minutes: int) -> bool:
    """True, если живой менеджер недавно (в пределах TTL) писал в этот чат.

    Состояние паузы выводится из единственной метки manager_last_at
    (ISO-8601, UTC). None или просроченная метка → пауза неактивна.
    Отдельный bool-флаг не держим, чтобы не протухал.
    """
    last = session.get("manager_last_at")
    if not last:
        return False
    try:
        ts = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    return age_minutes < ttl_minutes
```

> `is_manager_active` — синхронная функция (не `async`), как и `_new_session`:
> ввод-вывода нет, читает готовый dict.

---

### 4.3. `src/channels/instagram.py`

`settings` уже импортирован (`from src.config import settings`).

**(а)** В класс `InstagramChannel` рядом с `_username_cache` (строки 20-21)
добавить набор отправленных ботом `mid`:

```python
    _sent_mids: set[str] = set()
    _SENT_MIDS_MAX = 10_000
```

**(б)** В `send_message` (строки 86-130) после `response.raise_for_status()`
распарсить `message_id`, запомнить его и вернуть. Сменить сигнатуру на
`-> str | None`. Итоговый блок отправки:

```python
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(url, params=params, json=payload)
                response.raise_for_status()
                mid = None
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        mid = data.get("message_id")
                except Exception:
                    mid = None
                if mid:
                    self._sent_mids.add(mid)
                    if len(self._sent_mids) > self._SENT_MIDS_MAX:
                        for _ in range(len(self._sent_mids) - self._SENT_MIDS_MAX):
                            self._sent_mids.pop()
                logger.info("instagram.message.sent", recipient_id=recipient_id)
                return mid
            except httpx.HTTPStatusError as exc:
                raise InstagramError(
                    f"Ошибка отправки сообщения: {exc.response.status_code} {exc.response.text}"
                ) from exc
            except httpx.RequestError as exc:
                raise InstagramError(f"Сетевая ошибка при отправке: {exc}") from exc
```

Не забыть сменить аннотацию: `async def send_message(self, recipient_id: str, text: str) -> str | None:`.
Существующие вызовы (`main.py`) возврат игнорируют — обратная совместимость есть.

**(в)** Добавить метод классификации эха:

```python
    def is_own_message(self, mid: str, app_id: str | None = None) -> bool:
        """Эхо отправлено самим ботом (а не живым менеджером)?

        True, если app_id совпадает с нашим приложением ИЛИ mid знаком нам по
        собственным Send API вызовам.
        """
        if app_id and settings.instagram_app_id and str(app_id) == settings.instagram_app_id:
            return True
        return bool(mid) and mid in self._sent_mids
```

**(г)** Переписать `receive_message` (строки 62-84) — возврат `list[dict]`
со смешанными событиями:

```python
    async def receive_message(self, payload: dict) -> list[dict]:
        """Разобрать входящий webhook от Instagram.

        Возвращает список событий:
          {"kind": "user",    "sender_id", "text", "mid"}  — сообщение клиента
          {"kind": "manager", "client_id", "text", "mid"}  — живой менеджер
                                                              ответил в чат
        Эхо собственных ответов бота отфильтровывается (is_own_message).
        mid нужен для дедупликации ретраев.
        """
        events: list[dict] = []

        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                message = messaging.get("message", {})
                mid = message.get("mid", "")

                if message.get("is_echo"):
                    # app_id у эха может лежать в message или в messaging —
                    # берём из обоих мест (проверить по реальным логам).
                    app_id = message.get("app_id") or messaging.get("app_id")
                    if self.is_own_message(mid, app_id):
                        continue  # собственный ответ бота — игнор
                    # В эхе sender = бизнес-аккаунт, клиент = recipient.
                    client_id = messaging.get("recipient", {}).get("id")
                    if client_id:
                        logger.info("instagram.manager.detected", client_id=client_id)
                        events.append(
                            {
                                "kind": "manager",
                                "client_id": client_id,
                                "text": message.get("text", ""),
                                "mid": mid,
                            }
                        )
                    continue

                sender_id = messaging.get("sender", {}).get("id")
                text = message.get("text", "")
                if sender_id and text:
                    logger.info("instagram.message.received", sender_id=sender_id)
                    events.append(
                        {
                            "kind": "user",
                            "sender_id": sender_id,
                            "text": text,
                            "mid": mid,
                        }
                    )

        return events
```

**(д)** `handle_webhook` (строки 165-167): привести аннотацию к новому возврату:

```python
    async def handle_webhook(self, payload: dict) -> list[dict]:
        """Реализация абстрактного метода ChannelBase."""
        return await self.receive_message(payload)
```

> Если `ChannelBase.handle_webhook` имеет более строгий тайп-хинт — синхронизировать
> его (проверить `src/channels/base.py`). Логику не менять.

---

### 4.4. `src/main.py`

**(а)** Импорты. В блок `from src.db.sessions import (...)` (строки 12-18)
добавить `is_manager_active`. Добавить импорт настроек вверху файла:

```python
from src.config import settings
```

(`datetime`, `timezone` уже импортированы — строка 5.)

**(б)** Webhook-цикл (строки 374-402) — итерировать события-словари, ветвить по
`kind`. Заменить от `messages = await instagram.receive_message(payload)` до
`return Response(...)`:

```python
    payload = await request.json()
    events = await instagram.receive_message(payload)
    logger.info("instagram.webhook.received", events=len(events))

    # Запускаем обработку в фоне и отвечаем Meta 200 мгновенно.
    for ev in events:
        mid = ev.get("mid", "")
        if mid:
            if mid in _processed_mids:
                logger.info("instagram.webhook.dedup_skipped", mid=mid)
                continue
            _processed_mids.add(mid)
            if len(_processed_mids) > _PROCESSED_MIDS_MAX:
                excess = len(_processed_mids) - _PROCESSED_MIDS_MAX
                for _ in range(excess):
                    _processed_mids.pop()
        else:
            # Без mid не можем дедуплицировать — пропускаем.
            logger.warning("instagram.message.no_mid", kind=ev.get("kind"))
            continue

        if ev["kind"] == "manager":
            task = asyncio.create_task(
                _mark_manager_active(ev["client_id"], ev.get("text", ""))
            )
        else:  # "user"
            logger.info("instagram.message.processing", sender_id=ev["sender_id"])
            task = asyncio.create_task(_process_safely(ev["sender_id"], ev["text"]))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return Response(status_code=200, content="")
```

**(в)** Новая корутина рядом с `_process_safely` (после строки 357):

```python
async def _mark_manager_active(client_id: str, manager_text: str) -> None:
    """Живой менеджер ответил клиенту — ставим/продлеваем паузу бота.

    Под per-user локом, чтобы не гоняться с идущей обработкой того же клиента.
    Реплику менеджера дописываем в историю как ход ассистента — чтобы при
    авто-возврате у бота был контекст переписки.
    """
    try:
        lock = await _get_lock(client_id)
        async with lock:
            session = await get_session(client_id)
            session["manager_last_at"] = datetime.now(timezone.utc).isoformat()
            if manager_text:
                history = session.get("history", [])
                history.append({"role": "assistant", "content": manager_text})
                session["history"] = history
            await save_session(client_id, session)
        logger.info("manager.takeover", client_id=client_id)
    except Exception:
        logger.exception("manager.takeover.failed", client_id=client_id)
```

**(г)** Гейт паузы в `process_with_ai` (строка 232+). Вставить **сразу после
локальных импортов и ДО `if is_rate_limited(sender_id):`** (строка 240).
Расположение до rate-limit/guard критично: иначе во время паузы бот отправит
клиенту заглушку и нарушит «не мешать».

```python
    # Пауза: если живой менеджер недавно писал в этот чат — бот молчит.
    # Проверяем ДО rate-limit/guard. Перепроверяем под локом, чтобы закрыть
    # гонку с _mark_manager_active.
    pre = await get_session(sender_id)
    if is_manager_active(pre, settings.manager_takeover_ttl_minutes):
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            if is_manager_active(session, settings.manager_takeover_ttl_minutes):
                history = session.get("history", [])
                history.append({"role": "user", "content": text})
                session["history"] = history
                await save_session(sender_id, session)
                logger.info("manager.active.skip_llm", sender_id=sender_id)
                return
```

> Остальной код `process_with_ai` (rate-limit, guard, загрузка сессии под локом,
> LLM, маркеры, отправка) **не меняется**. Да, в непаузном случае добавляется
> один лишний `get_session` сверху — это дешёвый SQLite-read, приемлемо.

---

## 5. Тесты

Цель: не просесть ниже текущих 81 + покрыть новую логику.

### 5.1. `tests/test_instagram.py`

**Обновить** под новый dict-формат `receive_message`:
- `test_send_message_success`: мок ответа должен иметь
  `mock_response.json = Mock(return_value={"message_id": "mid_sent_1"})` (метод
  `json()` синхронный). Проверить, что `send_message` вернул `"mid_sent_1"` и
  что `"mid_sent_1" in InstagramChannel._sent_mids`. Перед тестом —
  `InstagramChannel._sent_mids.clear()`.

**Новые кейсы** (через прямой вызов `await channel.receive_message(payload)`):
- *Эхо живого менеджера* → одно событие `{"kind":"manager", "client_id": <recipient.id>, ...}`:
  ```python
  payload = {"entry": [{"messaging": [{
      "sender": {"id": "BUSINESS_ACC"},
      "recipient": {"id": "CLIENT_42"},
      "message": {"is_echo": True, "mid": "mid_human_1", "text": "Здравствуйте!"},
  }]}]}
  ```
  Перед вызовом `InstagramChannel._sent_mids.clear()`, `settings.instagram_app_id = ""`.
  Ожидать: `events == [{"kind":"manager","client_id":"CLIENT_42","text":"Здравствуйте!","mid":"mid_human_1"}]`.
- *Эхо собственного бота по mid* → событий нет: положить `_sent_mids.add("mid_bot_1")`,
  прислать эхо с `mid":"mid_bot_1"` → `events == []`.
- *Эхо собственного бота по app_id* → событий нет: `settings.instagram_app_id = "APP_X"`,
  эхо с `"app_id":"APP_X"` (и незнакомым mid) → `events == []`.
- *Обычное сообщение клиента* → `{"kind":"user", "sender_id", "text", "mid"}`.

### 5.2. `tests/test_sessions.py`

`is_manager_active`:
- `manager_last_at = None` → `False`.
- метка `datetime.now(timezone.utc).isoformat()` → `True` при ttl=10080.
- метка на 8 дней назад → `False` при ttl=10080
  (`(datetime.now(timezone.utc) - timedelta(days=8)).isoformat()`).
- битая строка → `False`.

### 5.3. `tests/test_api.py` (или новый `tests/test_manager_takeover.py`)

`process_with_ai` при активной паузе:
- Замокать `src.main.get_session` → вернуть сессию с
  `manager_last_at = now`, `history=[]`.
- Замокать `src.main.save_session` (AsyncMock), `src.services.llm.get_llm`,
  `instagram.send_message` (AsyncMock).
- Вызвать `await process_with_ai("CLIENT_42", "хочу тур")`.
- Проверить: `get_llm` / `ainvoke` **не вызваны**; `instagram.send_message`
  **не вызван**; в сессии, переданной в `save_session`, последний ход —
  `{"role":"user","content":"хочу тур"}`.

(Опционально) Поведение webhook-роутинга:
- `@patch("src.main._mark_manager_active")` + payload-эхо менеджера → проверить,
  что вызвана `_mark_manager_active("CLIENT_42", ...)`, а `_process_safely` нет.

---

## 6. Проверка (verification)

1. **Юнит:** `pytest tests/ -q` — зелёные, не ниже 81 + новые.
2. **Линт:** `ruff check .` / `ruff format` (если в проекте используется).
3. **Стейджинг/прод (ручной E2E):**
   - С реального аккаунта **человеком** ответить клиенту в DM из приложения
     Instagram / Meta Business Suite.
   - В логах ожидать `instagram.manager.detected` → `manager.takeover`.
   - Следующее сообщение клиента → в логах `manager.active.skip_llm`, бот молчит.
   - Убедиться, что **собственные** ответы бота НЕ ставят паузу (его эхо
     отфильтровано по `mid`/`app_id`).
   - Для проверки авто-возврата временно снизить
     `manager_takeover_ttl_minutes` (например, до 2) → после простоя бот снова
     отвечает.

---

## 7. Риск №1 — проверить ПЕРВЫМ

Реально ли Meta шлёт `is_echo`-вебхуки для **ручных** ответов в текущей
конфигурации приложения. Без эха фича не работает.

**Как проверить:** после ручного ответа из инбокса посмотреть логи вебхука —
должно прийти событие с `message.is_echo: true`. Если эха нет — включить нужные
webhook-поля (`messages`) / Conversation Routing в дашборде Meta-приложения и
убедиться, что подписка на эхо активна. Заодно по реальному payload уточнить,
где лежит `app_id` (в `message` или в `messaging`).

---

## 8. Порядок выполнения и коммиты

Каждый шаг — отдельный осмысленный коммит:

1. `feat(config): add manager takeover TTL and app_id settings`
2. `feat(sessions): add manager_last_at + is_manager_active helper`
3. `feat(instagram): parse echo events, track bot-sent mids`
4. `feat(main): pause bot when a human manager replies in the chat`
5. `test: cover manager takeover (echo classification, pause gate, TTL)`

Деплой (из `docs/session_2026-06-25.md`):
```bash
git push origin master
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot && git pull origin master && systemctl restart travel-bot
journalctl -u travel-bot -f   # наблюдать manager.takeover / manager.active.skip_llm
```

---

## 9. Принципы (из WORK-PLAN.md)

- Прод-логику вебхуков/дедупа/локов трогаем минимально — она выстрадана.
- Тесты не проседают ниже текущих 81.
- Каждая задача — отдельный коммит с понятным сообщением.
