# Редизайн эскалации в Telegram

> Статус: **план, утверждён к реализации**
> Дата: 2026-06-25

## Проблемы текущей эскалации

1. Имя/телефон/email показывают «Не указано» — берутся из `booking_data`, который пуст при эскалации без брони
2. `request_summary` и `tag` дублируются (`escalation_reason` передаётся в оба поля)
3. Телефон ломается Markdown-экранированием (`_escape_markdown` экранирует `+`)
4. История переписки (20 сообщений × 300 символов) превышает лимит Telegram 4096 и не нужна менеджеру
5. Нет Instagram username менеджера — только голый PSID
6. Нет таймстемпа эскалации

---

## 1. Instagram username — новый метод `InstagramChannel.get_username()`

**Файл:** `src/channels/instagram.py`

### Эндпоинт (User Profile API)

```
GET https://graph.instagram.com/v25.0/{sender_id}
  ?fields=name,username
  &access_token={instagram_access_token}
```

**Документация:** Instagram User Profile API — `/<INSTAGRAM_SCOPED_ID>`.

`sender_id` из webhook — это как раз `INSTAGRAM_SCOPED_ID`. Домен `graph.instagram.com` (не `graph.facebook.com`), токен тот же.

### Код

```python
_username_cache: dict[str, str] = {}
_USERNAME_CACHE_MAX = 500

async def get_username(self, sender_id: str) -> str | None:
    if sender_id in self._username_cache:
        return self._username_cache[sender_id]

    if not settings.instagram_access_token:
        return None

    url = f"https://graph.instagram.com/v25.0/{sender_id}"
    params = {
        "fields": "name,username",
        "access_token": settings.instagram_access_token,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            username = data.get("username") or data.get("name")
            if username:
                self._username_cache[sender_id] = username
                if len(self._username_cache) > _USERNAME_CACHE_MAX:
                    self._username_cache.pop(next(iter(self._username_cache)))
                return username
        except Exception:
            logger.debug("instagram.get_username.failed", sender_id=sender_id)
    return None
```

### Кеш

- In-memory `dict[str, str]` на экземпляре `InstagramChannel`
- Максимум 500 записей, при превышении — удаляется самая старая
- Username между сообщениями не меняется, TTL не нужен
- При ошибке API — `None`, без retry

---

## 2. Маркер `===МЕНЕДЖЕР===` — добавить поле `Контекст:`

**Файл:** `src/ai/prompts.py`

### Текущая инструкция (строки 93-97)

```
Если нужно передать диалог менеджеру (клиент просит менеджера, жалоба,
не нашёл подходящих туров, сложный запрос) — добавь в самом конце:

===МЕНЕДЖЕР===
Причина: {причина}
===МЕНЕДЖЕР===
```

### Новая инструкция

```
Если нужно передать диалог менеджеру (клиент просит менеджера, жалоба,
не нашёл подходящих туров, сложный запрос) — добавь в самом конце:

===МЕНЕДЖЕР===
Причина: {краткая причина, 1 предложение}
Контекст: {суть диалога для менеджера: что клиент ищет, какие параметры назвал,
           что не подошло. 2-4 предложения, чтобы менеджер сразу понял ситуацию}
===МЕНЕДЖЕР===

Заполни ОБА поля. Контекст — самое важное, менеджер не видит историю переписки.
```

---

## 3. Парсинг маркера — `_extract_escalation()` возвращает `(reason, context)`

**Файл:** `src/main.py`

### Текущий код (строки 193-202)

```python
_ESCALATION_RE = re.compile(
    r"===МЕНЕДЖЕР===\s*\n(.*?)\n===МЕНЕДЖЕР===", re.DOTALL
)

def _extract_escalation(text: str) -> str | None:
    m = _ESCALATION_RE.search(text)
    if not m:
        return None
    for line in m.group(1).strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            if key.strip().lower() == "причина":
                return val.strip()
    return m.group(1).strip()
```

### Новый код

```python
def _extract_escalation(text: str) -> tuple[str, str] | None:
    """Парсит ===МЕНЕДЖЕР=== и возвращает (причина, контекст).

    Контекст опционален — если не заполнен, дублирует причину.
    Если маркера нет — None.
    """
    m = _ESCALATION_RE.search(text)
    if not m:
        return None
    reason = ""
    context = ""
    for line in m.group(1).strip().split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key_s = key.strip().lower()
        if key_s == "причина":
            reason = val.strip()
        elif key_s == "контекст":
            context = val.strip()
    if not reason:
        reason = m.group(1).strip()
    return reason, context or reason
```

**Обратная совместимость:** если `Контекст:` не заполнен — `context = reason`. Если нет ни `Причина:` ни `Контекст:` — оба поля = сырой текст маркера.

---

## 4. Telegram `_build_notification_text` — новый формат

**Файл:** `src/services/telegram_notify.py`

### Изменения

- Убрать `conversation_history` и `_format_conversation()`
- Убрать `MAX_HISTORY_LINES`
- Добавить обязательные `sender_id: str` и `context: str`
- Добавить опциональный `instagram_handle: str | None`
- Заменить `client_name/phone/email` на опциональные `str | None`
- Убрать `_escape_markdown` для телефона — телефон выводится обычным текстом

### Сигнатура `notify_manager()`

```python
async def notify_manager(
    self,
    sender_id: str,
    instagram_handle: str | None = None,
    context: str = "",
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    tag: str = "Нужен звонок",
) -> None:
```

### Новый текст уведомления

```python
def _build_notification_text(
    sender_id: str,
    instagram_handle: str | None,
    context: str,
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    tag: str = "Нужен звонок",
) -> str:
    sheets_id = settings.google_requests_sheet_id
    sheets_link = (
        f"https://docs.google.com/spreadsheets/d/{sheets_id}"
        if sheets_id else "_не указан_"
    )

    handle = f"@{instagram_handle}" if instagram_handle else sender_id
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")

    lines = [
        "\U0001f6a8 *Новая эскалация*",
        "",
        f"\U0001f464 *Клиент:* {handle}",
        f"\U0001f550 {now}",
        "",
        "\U0001f4cb *Суть:*",
        context,
        "",
    ]

    contacts = []
    if client_name:
        contacts.append(f"\U0001f464 {client_name}")
    if client_phone:
        contacts.append(f"\U0001f4de {client_phone}")
    if client_email:
        contacts.append(f"\U0001f4e7 {client_email}")
    if contacts:
        lines.append("\U0001f4cb *Контакты:*")
        lines.extend(contacts)
        lines.append("")

    lines.append(f"\U0001f3f7 *Тег:* `{tag}`")
    lines.append(f"\U0001f517 *Google Sheets:* [Открыть заявки]({sheets_link})")

    return "\n".join(lines)
```

### Пример результата

```
🚨 Новая эскалация

👤 Клиент: @ivan_petrov
🕐 25.06.2026 14:30

📋 Суть:
Клиент ищет тур в Турцию на август, бюджет до 2000$, 2 взрослых.
Подходящих вариантов в базе не нашлось — запросил менеджера.

📇 Контакты:
   👤 Иван Петров
   📞 +375291234567

🏷 Тег: #Нужен_звонок
🔗 Google Sheets: Открыть заявки
```

---

## 5. `process_with_ai` — интеграция

**Файл:** `src/main.py`

### Изменения в `process_with_ai()`

```python
# Получаем username (не критично, fallback на sender_id)
instagram_handle = await instagram.get_username(sender_id)

# ... llm.ainvoke ...

extracted = _extract_escalation(raw_reply)
escalation_reason, escalation_context = extracted if extracted else (None, None)

# Проверка нераспарсенных маркеров (Task 3)
if "===МЕНЕДЖЕР" in raw_reply and not extracted:
    logger.warning("marker.parse_failed", marker_type="escalation", snippet=raw_reply[-500:])

# Уведомление менеджеру
if escalation_reason:
    try:
        notifier = TelegramNotifier()
        await notifier.notify_manager(
            sender_id=sender_id,
            instagram_handle=instagram_handle,
            context=escalation_context,
            client_name=(booking_data or {}).get("name"),
            client_phone=(booking_data or {}).get("phone"),
            client_email=(booking_data or {}).get("email"),
            tag="Нужен звонок",
        )
    except Exception:
        logger.exception("escalation.notify_failed")
```

**Важные детали:**
- `client_name/phone/email` передаются как `None` если booking нет — шаблон сам решает показывать или нет
- Убраны "Не указано" / "Не указан" / "Не указан"
- `tag` стал константой "Нужен звонок" (вместо дублирования `escalation_reason`)
- `instagram.get_username` — best-effort, не блокирует эскалацию при ошибке

---

## 6. Тесты

### 6.1. `tests/test_engine.py`

```python
def test_extract_escalation_with_context():
    text = "ответ\n\n===МЕНЕДЖЕР===\nПричина: просит менеджера\nКонтекст: ищет тур в Турцию\n===МЕНЕДЖЕР==="
    result = _extract_escalation(text)
    assert result == ("просит менеджера", "ищет тур в Турцию")

def test_extract_escalation_without_context():
    text = "ответ\n\n===МЕНЕДЖЕР===\nПричина: просит менеджера\n===МЕНЕДЖЕР==="
    result = _extract_escalation(text)
    assert result == ("просит менеджера", "просит менеджера")

def test_extract_escalation_no_marker():
    text = "обычный ответ"
    assert _extract_escalation(text) is None
```

### 6.2. `tests/test_telegram_notify.py`

```python
def test_build_notification_with_handle():
    text = _build_notification_text(
        sender_id="123",
        instagram_handle="ivan_petrov",
        context="ищет тур",
        client_name="Иван",
        client_phone="+375291234567",
    )
    assert "@ivan_petrov" in text
    assert "+375291234567" in text
    assert "ищет тур" in text

def test_build_notification_no_contacts():
    text = _build_notification_text(
        sender_id="123",
        instagram_handle=None,
        context="ищет тур",
    )
    assert "123" in text
    assert "Контакты:" not in text

def test_notify_manager_called_with_new_params(monkeypatch):
    # Проверить что notify_manager принимает sender_id и context
    pass
```

### 6.3. `tests/test_instagram.py`

```python
class TestGetUsername:
    async def test_get_username_success(self):
        # мок client.get → {username: "ivan_petrov"}
        pass

    async def test_get_username_cached(self):
        # второй вызов не идёт в API
        pass

    async def test_get_username_fallback_on_error(self):
        # ошибка API → None
        pass
```

---

## 7. Файлы для изменения

| Файл | Что делаем |
|------|-----------|
| `src/channels/instagram.py` | + `get_username()`, + `_username_cache` |
| `src/ai/prompts.py` | Обновить `_ACTION_INSTRUCTIONS` — добавить `Контекст:` в маркер |
| `src/main.py` | `_extract_escalation` → кортеж; вызов `notify_manager` с новыми параметрами; вызов `get_username` |
| `src/services/telegram_notify.py` | Новый `_build_notification_text`; новый `notify_manager()`; убрать `conversation_history` |
| `tests/test_engine.py` | Тесты парсинга контекста |
| `tests/test_telegram_notify.py` | Тесты нового формата (убрать старые тесты с историей) |
| `tests/test_instagram.py` | Тесты `get_username` |
| `docs/ARCHITECTURE.md` | Обновить описание маркеров и эскалации |

---

## 8. Порядок выполнения

1. `prompts.py` — добавить `Контекст:` в маркер
2. `instagram.py` — `get_username()` + кеш
3. `test_instagram.py` — тесты `get_username`
4. `main.py` — `_extract_escalation` → кортеж
5. `test_engine.py` — тесты парсинга
6. `telegram_notify.py` — новый формат
7. `test_telegram_notify.py` — тесты нового формата
8. `main.py` — интеграция username + контекст в `process_with_ai`
9. `docs/ARCHITECTURE.md` — синхронизация
10. `pytest tests/ -q` — всё зелёное
