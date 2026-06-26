# План: обработка Instagram-постов, вложений и ответов на истории

> Статус: готово к реализации  
> Дата: 2026-06-26  
> Контекст: сейчас `InstagramChannel.receive_message()` обрабатывает только
> `message.text`. Сообщения с вложениями/постами/ответами на истории без текста
> доходят до webhook, но не превращаются в событие и теряются.

## Цель

Научить бота фиксировать не-текстовые Instagram-сообщения и передавать их
менеджеру без вызова DeepSeek, потому что бот не видит содержимое вложения,
поста или истории.

Целевое поведение:

- обычный текст в DM работает как сейчас;
- сообщение клиента с вложением, shared post, story reply или referral создаёт
  отдельное событие;
- если в сообщении есть и текст, и вложение, оно всё равно считается non-text
  событием, чтобы бот не пытался угадать контекст;
- клиент получает короткий автоответ: бот не видит вложение/пост/историю и
  передал вопрос менеджеру;
- менеджер получает Telegram-уведомление с типом события, Instagram handle/client
  id и текстом клиента, если он был;
- событие логируется структурно;
- дедупликация по `mid`, manager takeover и лимит 3 эскалаций сохраняются.

## Текущая проблема

Файл: `src/channels/instagram.py`.

Сейчас parser делает только это:

```python
text = message.get("text", "")
if sender_id and text:
    events.append(...)
```

Последствия:

- `message.attachments` без текста игнорируется;
- ответы на истории/посты, если Meta передаёт их отдельными полями, не
  распознаются;
- правило в `src/ai/prompts.py` про “если клиент прислал пост/фото/вложение —
  передай менеджеру” часто не срабатывает, потому что такие сообщения не доходят
  до LLM.

## Изменения в Instagram parser

Файл: `src/channels/instagram.py`.

Добавить helper:

```python
def _extract_non_text_metadata(message: dict) -> dict:
    ...
```

Он возвращает пустой dict, если non-text сигналов нет. Если сигналы есть,
возвращает структуру:

```python
{
    "types": ["image", "story_reply_or_reply", "referral_or_shared_post"],
    "summary": "вложение: image; ответ/реплай; referral/shared post",
    "has_text": True,
    "text": "текст клиента, если был",
    "raw_keys": ["attachments", "reply_to", "referral"]
}
```

Минимально поддержать:

- `message.attachments`: собрать `attachment["type"]`, например `image`,
  `video`, `audio`, `file`, `share`, `fallback`;
- `message.reply_to`: добавить тип `story_reply_or_reply`;
- `message.referral`: добавить тип `referral_or_shared_post`;
- `message.quick_reply`: не считать non-text, если есть обычный текст;
- неизвестные поля глубоко не парсить.

Не скачивать медиа и не ходить по URL вложений.

### Новые события

Обычный текст без non-text сигналов остаётся прежним:

```python
{
    "kind": "user",
    "sender_id": "...",
    "text": "...",
    "mid": "..."
}
```

Сообщение с вложением/постом/ответом на историю:

```python
{
    "kind": "user_non_text",
    "sender_id": "...",
    "text": "...",  # исходный текст клиента или ""
    "mid": "...",
    "non_text": {
        "types": [...],
        "summary": "...",
        "has_text": True,
        "text": "...",
        "raw_keys": [...]
    }
}
```

Echo-логика не должна сломаться:

- собственные echo бота по `_sent_mids` / `instagram_app_id` игнорируются;
- echo живого менеджера продолжает возвращать `kind="manager"`;
- если echo менеджера без текста, `text` должен быть `""`, но takeover всё равно
  должен сработать.

## Изменения в main.py

Файл: `src/main.py`.

Добавить обработчик:

```python
async def _process_non_text_safely(sender_id: str, text: str, metadata: dict) -> None:
    ...
```

Поведение:

1. Проверить manager takeover так же, как в `process_with_ai()`. Если менеджер
   активен — залогировать `manager.active.skip_non_text` и ничего не отвечать.
2. Получить per-user lock через `_get_lock(sender_id)`.
3. Внутри lock перечитать session.
4. Получить `instagram_handle = await instagram.get_username(sender_id)`.
5. Взять `escalation_count = session.get("escalation_count", 0)`.
6. Если `escalation_count < 3`, вызвать `TelegramNotifier.notify_manager(...)`.
7. Увеличить `escalation_count` только после успешной отправки Telegram.
8. Сохранить историю в SQLite.
9. Ответить клиенту.

Контекст для Telegram:

```text
Клиент отправил не текстовое сообщение в Instagram.
Тип: <metadata["summary"]>
Текст клиента: <text или "без текста">
Бот не видит содержимое вложения/поста/истории.
```

Автоответ клиенту при успешной/первой эскалации:

```text
Не вижу вложение/пост/историю в чате, поэтому передала вопрос менеджеру 🙌
Он посмотрит и поможет.
```

Если `escalation_count >= 3`, Telegram не отправлять. Ответ клиенту:

```text
Ваш запрос уже передан менеджеру, ожидайте, пожалуйста. Он свяжется с вами в ближайшее время.
```

История в `session["history"]`:

- user: `[Instagram non-text] <summary>. Текст клиента: <text или "без текста">`
- assistant: фактический автоответ клиенту

### Webhook branch

В `receive_instagram_message()` добавить ветку после `manager`:

```python
elif ev["kind"] == "user_non_text":
    task = asyncio.create_task(
        _process_non_text_safely(
            ev["sender_id"],
            ev.get("text", ""),
            ev.get("non_text", {}),
        )
    )
else:
    task = asyncio.create_task(_process_safely(ev["sender_id"], ev["text"]))
```

Дедупликацию по `mid` оставить до выбора ветки, как сейчас. Сообщения без `mid`
по-прежнему пропускать.

## Логирование

Добавить структурные логи:

- `instagram.non_text.received`: `sender_id`, `mid`, `types`, `has_text`;
- `instagram.non_text.escalated`: после успешного Telegram notify;
- `instagram.non_text.escalation_skipped_limit`: если лимит 3 достигнут;
- `instagram.non_text.notify_failed`: если Telegram упал;
- `instagram.message.unsupported`: если нет `text`, `attachments`, `reply_to`,
  `referral`, но есть `mid` и `sender_id`.

Не логировать полный raw payload, чтобы не сохранять лишние персональные данные.

## Документация

Обновить:

- `docs/ARCHITECTURE.md`: добавить ветку `user_non_text → Telegram manager +
  client ack`, без LLM;
- `.agents/skills/travel-bot-dev/SKILL.md`: добавить, что вложения/посты/story
  replies обрабатываются детерминированно;
- `docs/DEVELOPMENT.md`: добавить сценарий ручной проверки через тестовый webhook
  payload.

## Тесты

Файл: `tests/test_instagram.py`.

### Parser tests

Добавить проверки:

- `receive_message()` с `attachments=[{"type": "image"}]` без текста возвращает
  `kind="user_non_text"`;
- `receive_message()` с `text` + `attachments` возвращает `kind="user_non_text"`,
  а не `kind="user"`;
- `receive_message()` с `reply_to` возвращает metadata type
  `story_reply_or_reply`;
- `receive_message()` с `referral` возвращает metadata type
  `referral_or_shared_post`;
- обычный текст без вложений остаётся `kind="user"`;
- own bot echo по `mid` и `app_id` по-прежнему игнорируется;
- human manager echo без текста или с вложением по-прежнему возвращает
  `kind="manager"`.

### Webhook/main tests

Добавить проверки:

- POST webhook с attachment и `mid` запускает `_process_non_text_safely`, а не
  `_process_safely`;
- POST webhook с duplicate `mid` не запускает non-text обработку второй раз;
- POST webhook без `mid` по-прежнему пропускается.

### Processing tests

Добавить проверки:

- `_process_non_text_safely()` отправляет клиенту acknowledgement;
- `_process_non_text_safely()` вызывает `TelegramNotifier.notify_manager()` с
  контекстом, где есть тип события и текст клиента;
- при `escalation_count >= 3` Telegram не вызывается, клиент получает “запрос уже
  передан”;
- при active manager takeover обработчик молчит.

Полная проверка:

```bash
pytest tests/ -q
ruff check src tests
```

Ожидание: все текущие 117 тестов плюс новые проходят.

## Ручная проверка

После деплоя на VPS:

1. Сбросить тестовый контекст клиента в SQLite при необходимости.
2. Написать в Instagram обычный текст — бот отвечает как раньше.
3. Отправить фото/пост/ответ на историю без текста — бот отвечает коротким
   acknowledgement, менеджеру приходит Telegram.
4. Отправить фото/пост/ответ на историю с текстом — Telegram содержит тип события
   и текст клиента.
5. Проверить логи:

```bash
journalctl -u travel-bot -n 100 --no-pager | grep instagram.non_text
```

## Ограничения и решения v1

- Вложения, shared posts и story replies нельзя надёжно интерпретировать самим
  ботом, поэтому v1 всегда передаёт их менеджеру без DeepSeek.
- Медиа не скачиваем и не храним.
- Google Sheets не трогаем: non-text событие не является бронью/заявкой.
- SQLite schema не меняем: достаточно сохранить краткую запись в существующей
  `sessions.history`.
- Лимит 3 эскалации на клиента применяется и к non-text сообщениям.
- Если Meta пришлёт незнакомый формат payload без `text`, `attachments`,
  `reply_to` или `referral`, v1 только логирует `instagram.message.unsupported`
  и не запускает LLM.

## Критерии готовности

- Non-text webhook больше не теряется молча.
- Клиент получает понятный автоответ.
- Менеджер видит в Telegram, что клиент прислал вложение/пост/ответ на историю.
- Текст клиента, если был, сохраняется в Telegram-контексте и истории сессии.
- Дедуп, manager takeover и лимит эскалаций работают как раньше.
- `pytest tests/ -q` и `ruff check src tests` проходят.
