# План: эскалация в Viber вместо/рядом с Telegram

Документ для агента-исполнителя. Содержит контекст, **важные ограничения Viber**, выбранную
архитектуру, что нужно завести у Viber, точные изменения по файлам, форматы API-запросов,
план тестирования и порядок выката.

---

## 0. Задача

Сейчас при эскалации (`===МЕНЕДЖЕР===`), при брони (`===БРОНЬ===`) и при non-text сообщениях
бот шлёт уведомление менеджерам в **Telegram** (`src/services/telegram_notify.py`, рассылка по
списку chat_id). Заказчик хочет, чтобы то же уведомление приходило **в Viber** — «в чат, который
видят все менеджеры».

> Цель — не «перевести бота на Viber-клиентов». Клиенты по-прежнему пишут в Instagram. Меняется
> только **канал уведомления менеджеров**: Telegram → Viber.

---

## 1. ⚠️ Главное, что нужно понять про Viber (прочитать до начала работы)

Модель Viber-бота принципиально отличается от Telegram. Telegram-бота можно добавить в обычную
группу и он шлёт туда сообщения. **В Viber так нельзя.**

1. **Viber-бот работает только в личных 1-на-1 чатах.** Бот создаёт приватный канал между ботом и
   *подписанным* пользователем. Обычный бот **нельзя добавить в групповой чат Viber** и заставить
   писать туда. Это архитектурное ограничение платформы, а не недоработка.
   ([REST API](https://developers.viber.com/docs/api/rest-bot-api/),
   [API Access White Paper](https://developers.viber.com/docs/general/api-access-white-paper/))

2. **Сообщения адресуются по `user id`, а не по номеру/группе.** `user id` бот получает только из
   webhook-колбэков (`conversation_started`, `message`, `subscribed`). `user id` уникален на пару
   «бот↔пользователь», не меняется и не истекает.

3. **Сначала подписка, потом сообщения.** Бот может писать пользователю **только после того, как
   тот сам написал боту хотя бы раз** (первое сообщение = автоподписка). Нельзя написать менеджеру
   «вслепую» по номеру телефона.

4. **С 05.02.2024 боты создаются только на коммерческих условиях** — заявка через Rakuten Viber.
   Это внешний организационный шаг, его делает владелец, и он может занять время/денег. **Заложить
   в сроки.** ([Developers FAQ](https://developers.viber.com/docs/faq/))

### Что это значит для нас

«Общий чат, который видят все» в стиле Telegram-группы в Viber воспроизвести нельзя «в лоб».
Реальных варианта два:

| Вариант | Что видит менеджер | Сложность | Рекомендация |
|---|---|---|---|
| **A. Рассылка подписчикам** (`broadcast_message` / цикл `send_message`) | Каждое уведомление приходит каждому менеджеру в его **личный чат с ботом** | Низкая. **1-в-1 повторяет текущую логику** Telegram (цикл по списку id) | ✅ **Рекомендуется** |
| **B. Viber Community + подключённый бот** | Единый **общий тред**, который видят все участники сообщества | Выше: создать Community, подключить бота, разобраться с контекстом постинга; тоньше документация | Опционально, если заказчику критичен именно общий тред |

**Рекомендация исполнителю: делать Вариант A.** Он надёжен, хорошо задокументирован, и точно
ложится на существующую архитектуру (`TelegramNotifier` уже шлёт в цикле по списку получателей).
Менеджеры всё равно «все видят» уведомление — просто каждый в своём чате с ботом, а не в общем
треде. Вариант B описан в Приложении в конце как развитие.

> 👉 Перед стартом подтвердить у заказчика: устраивает ли «каждому менеджеру в личку от бота»
> (Вариант A), или нужен именно общий тред (Вариант B). Это единственное продуктовое решение,
> которое стоит согласовать заранее.

---

## 2. Что нужно завести на стороне Viber (делает владелец, до кода)

1. **Создать бота** на коммерческих условиях (Rakuten Viber) → получить **`X-Viber-Auth-Token`**
   (он же application key). Токен виден админам в Viber: *More → Settings → Bots → Edit Info*.
2. **Каждый менеджер один раз пишет боту** любое сообщение (находит бота по имени/ссылке и жмёт
   «отправить»). Это подписывает менеджера и порождает webhook-колбэк с его `user id`.
3. **Публичный HTTPS-эндпоинт с валидным сертификатом** для webhook (Viber требует доверенный CA,
   self-signed нельзя). У нас уже есть: см. `docs/SELF-HOSTING.md` (Cloudflare Tunnel / Caddy).
   Тот же домен, что и для Instagram, подойдёт — добавим путь `/webhook/viber`.

**Данные, которые в итоге нужны в `.env`:**
- `VIBER_AUTH_TOKEN` — токен бота;
- `VIBER_MANAGER_IDS` — список `user id` менеджеров (заполнится после шага 2 ниже, см. §4.3);
- (опц.) `VIBER_SENDER_NAME`, `VIBER_SENDER_AVATAR` — имя/аватар, от чьего лица бот пишет
  (обязательное поле `sender` в `send_message`/`broadcast_message`).

---

## 3. Эндпоинты и форматы Viber API (справочник для реализации)

Базовый хост: `https://chatapi.viber.com/pa`. На **каждом** запросе обязателен заголовок
`X-Viber-Auth-Token: <token>`. Тело — JSON. Успех определяется не только HTTP 200, но и полем
`status` в ответе (`0` = OK; иначе ошибка — см. `status_message`).

### 3.1. set_webhook (разовая регистрация webhook)
```
POST https://chatapi.viber.com/pa/set_webhook
{
  "url": "https://<наш-домен>/webhook/viber",
  "event_types": ["subscribed", "unsubscribed", "conversation_started", "message"],
  "send_name": true,
  "send_photo": false
}
```
Viber сразу дёрнет наш URL для проверки — webhook обязан ответить `200`. Установка webhook
включает 1-на-1 переписку с ботом.

### 3.2. send_message (отправка одному получателю)
```
POST https://chatapi.viber.com/pa/send_message
{
  "receiver": "<manager_user_id>",
  "type": "text",
  "sender": { "name": "Сандита-бот", "avatar": "https://.../avatar.jpg" },
  "text": "🚨 Новая эскалация ..."
}
```

### 3.3. broadcast_message (рассылка многим подписчикам за 1 запрос)
```
POST https://chatapi.viber.com/pa/broadcast_message
{
  "type": "text",
  "sender": { "name": "Сандита-бот" },
  "text": "🚨 Новая эскалация ...",
  "broadcast_list": ["id1", "id2", "id3"]
}
```
Лимиты: ≤300 получателей за запрос, ≤500 запросов/10с, размер сообщения ≤30кб. В ответе —
`failed_list` с теми, кто «Not subscribed»/«Not found».

> Для нашего объёма (2–3 менеджера) проще и нагляднее **цикл `send_message`** по списку id —
> ровно как сейчас в `TelegramNotifier._send`. `broadcast_message` оставить как опциональную
> оптимизацию. Рекомендация: реализовать цикл `send_message`.

### 3.4. Webhook-колбэки (входящие, чтобы добыть `user id` менеджеров)
Все приходят `POST` на `/webhook/viber`. Ключевые типы:
- `conversation_started` — менеджер открыл чат с ботом; `user.id` внутри;
- `message` — менеджер написал боту; `sender.id` внутри (первое сообщение = автоподписка,
  отдельного `subscribed` при этом не будет);
- `subscribed` / `unsubscribed` — подписка/отписка; `user.id` / `user_id`.

Из любого такого колбэка достаём `id` — это и есть нужный `VIBER_MANAGER_ID`.

> Подпись/безопасность: Viber присылает заголовок `X-Viber-Content-Signature` (HMAC-SHA256 тела
> по auth-token). Желательно проверять (по аналогии с `instagram.verify_signature`), но для MVP
> приёма колбэков от менеджеров можно временно ограничиться приёмом и логированием — см. §4.3.

---

## 4. Изменения по коду

Принцип: **зеркалим `telegram_notify.py`**, не ломая текущую структуру. Telegram оставляем рабочим
(на время миграции и как fallback), переключение — флагом. Минимум диффа в `main.py`.

### 4.1. `src/config.py` — настройки
Добавить в `Settings`:
```python
    # Viber Bot (уведомления менеджерам)
    viber_auth_token: str = ""
    viber_manager_ids: str = ""          # CSV: "id1,id2,id3"
    viber_sender_name: str = "Сандита"
    viber_sender_avatar: str = ""        # опционально, URL

    # Канал уведомлений менеджеров: "telegram" | "viber" | "both"
    notify_channel: str = "telegram"
```
`viber_manager_ids` — строкой CSV (как уже сделано неявно для нескольких telegram chat id, но тут
явно один параметр). Парсить в список в нотифаере.

### 4.2. `src/services/viber_notify.py` — новый модуль (зеркало telegram_notify)
- Класс `ViberNotifier` с теми же публичными методами, что у `TelegramNotifier`:
  `notify_manager(...)` и `notify_booking(...)` — **идентичные сигнатуры**, чтобы вызовы в
  `main.py` были взаимозаменяемы.
- `_build_notification_text(...)` / текст брони — **переиспользовать** уже существующие билдеры из
  `telegram_notify.py` (вынести общие функции в `src/services/notify_text.py` либо
  импортировать из `telegram_notify`). Тексты одинаковые — не дублировать.
- `_send(text, receiver)`:
  ```python
  url = "https://chatapi.viber.com/pa/send_message"
  payload = {
      "receiver": receiver,
      "type": "text",
      "sender": {"name": settings.viber_sender_name, **({"avatar": settings.viber_sender_avatar} if settings.viber_sender_avatar else {})},
      "text": text,
  }
  async with AsyncClient(timeout=15) as client:
      r = await client.post(url, json=payload, headers={"X-Viber-Auth-Token": settings.viber_auth_token})
  data = r.json()
  if r.status_code != 200 or data.get("status") != 0:
      logger.error("viber.send.failed", receiver=receiver, status=r.status_code, body=r.text)
      raise ViberError(...)        # см. ниже
  ```
  ⚠️ В отличие от Telegram, **обязательно проверять `data["status"] == 0`**, а не только HTTP-код.
- Цикл по `viber_manager_ids` с тем же поведением «копим последнюю ошибку, шлём остальным» —
  один в один как `TelegramNotifier.notify_manager` (строки 136–143).
- Гард: если `viber_auth_token` или список id пусты → `raise ViberError(...)`.

В `src/exceptions.py` добавить:
```python
class ViberError(TravelBotError):
    """Ошибка взаимодействия с Viber Bot API."""
```

### 4.3. `src/main.py` — webhook для приёма `user id` менеджеров
Нужен один раз, чтобы узнать id менеджеров (и поддерживать их актуальными). Добавить:

```python
@app.post("/webhook/viber")
async def receive_viber_callback(request: Request):
    body = await request.json()
    event = body.get("event")
    uid = (body.get("user") or {}).get("id") or (body.get("sender") or {}).get("id") or body.get("user_id")
    if event in ("conversation_started", "message", "subscribed") and uid:
        logger.info("viber.subscriber.seen", event=event, user_id=uid,
                    name=(body.get("user") or body.get("sender") or {}).get("name"))
    # conversation_started ОБЯЗАН ответить 200 в течение 5 мин; можно вернуть приветствие
    return Response(status_code=200)
```
Процедура получения id (разово при настройке):
1. Выкатить код с webhook, выполнить `set_webhook` (можно одноразовым скриптом, см. §6).
2. Каждый менеджер пишет боту «привет».
3. Смотрим логи `viber.subscriber.seen` → выписываем `user_id` каждого → кладём в `.env`
   `VIBER_MANAGER_IDS=...` → рестарт.

> Опционально (улучшение): хранить подписчиков в БД (таблица `viber_subscribers(user_id, name,
> subscribed_at)`), чтобы не править `.env` руками и переживать смену состава менеджеров. Для MVP
> достаточно `.env` + логов. Если делаем БД — добавить в `src/db/` по образцу `sessions.py`.

### 4.4. `src/main.py` — вызовы уведомлений (точки интеграции)
Сейчас `TelegramNotifier()` создаётся в 3 местах: бронь (≈386), эскалация (≈403), non-text (≈484).
Ввести один хелпер вместо прямого создания нотифаера:

```python
def _get_notifiers():
    chan = settings.notify_channel
    out = []
    if chan in ("telegram", "both"):
        from src.services.telegram_notify import TelegramNotifier
        out.append(TelegramNotifier())
    if chan in ("viber", "both"):
        from src.services.viber_notify import ViberNotifier
        out.append(ViberNotifier())
    return out
```
И в каждой из 3 точек заменить одиночный `notifier.notify_*` на цикл по `_get_notifiers()` с
индивидуальным `try/except` на нотифаер (падение Viber не должно глушить Telegram и наоборот —
сохраняем текущую логику «ошибка уведомления логируется, поток не падает»). Сигнатуры
`notify_manager`/`notify_booking` у обоих классов одинаковые, поэтому тело цикла общее.

### 4.5. `.env.example` и `.env`
Добавить в `.env.example`:
```
# Viber Bot (уведомления менеджерам)
VIBER_AUTH_TOKEN=
VIBER_MANAGER_IDS=          # CSV user id менеджеров, заполнить после подписки (см. план)
VIBER_SENDER_NAME=Сандита
VIBER_SENDER_AVATAR=
NOTIFY_CHANNEL=telegram     # telegram | viber | both
```

---

## 5. Тестирование

### 5.1. Юнит-тесты — `tests/test_viber_notify.py` (зеркало `tests/test_telegram_notify.py`)
Мокаем `AsyncClient` (как в существующем тесте, строки 78–104). Покрыть:
- `notify_manager` успешно: в payload есть `receiver`, заголовок `X-Viber-Auth-Token`, текст с
  `@handle`/контекстом; `sender.name` проставлен.
- **Viber-специфика:** ответ HTTP 200, но `{"status": 3, "status_message": "..."}` → должен
  подниматься `ViberError` (это главное отличие от Telegram — нельзя верить только коду 200).
- Несколько id в `VIBER_MANAGER_IDS` → `post` вызван по разу на каждого; падение одного не
  отменяет отправку остальным, в конце пробрасывается последняя ошибка.
- Пустой `viber_auth_token`/пустой список id → `ViberError` без сетевого вызова.
- Текст уведомления (если билдер общий — тест на общий билдер уже есть; добавить проверку, что
  Viber использует тот же текст).

### 5.2. Тест webhook-приёма
- POST на `/webhook/viber` с телом `conversation_started`/`message`/`subscribed` → 200 и
  лог/запись `user_id` (если делаем БД — проверить, что подписчик сохранён).
- `set_webhook`-валидация: эндпоинт отвечает 200 на пустой/служебный POST.

### 5.3. Существующие тесты
Прогнать `pytest` целиком. Проверить, что рефактор точек вызова в `main.py` (через
`_get_notifiers`) не сломал `tests/test_api.py` / `tests/test_engine.py` / `test_telegram_notify.py`.
При `NOTIFY_CHANNEL=telegram` (дефолт) поведение Telegram должно остаться прежним.

### 5.4. Ручной E2E (на сервере с публичным HTTPS)
1. Заполнить `VIBER_AUTH_TOKEN`, выполнить `set_webhook` на `/webhook/viber`.
2. Менеджеры пишут боту → их id появляются в логах → внести в `VIBER_MANAGER_IDS`, рестарт.
3. Поставить `NOTIFY_CHANNEL=both`, спровоцировать эскалацию из Instagram → уведомление приходит
   и в Telegram, и в Viber каждому менеджеру.
4. Проверить бронь и non-text сценарии аналогично.
5. Убедиться, что при `status != 0` (например, отписавшийся менеджер) ошибка логируется
   (`viber.send.failed`), но остальные получают сообщение и основной поток не падает.

---

## 6. Выкат и эксплуатация

- **Разовый скрипт `set_webhook`.** Добавить маленький скрипт (например `scripts/viber_set_webhook.py`)
  или одноразовый `curl`:
  ```bash
  curl -X POST https://chatapi.viber.com/pa/set_webhook \
    -H "X-Viber-Auth-Token: $VIBER_AUTH_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"url":"https://<домен>/webhook/viber","event_types":["subscribed","unsubscribed","conversation_started","message"],"send_name":true}'
  ```
  Снять webhook (если нужно отключить): тот же эндпоинт с `{"url":""}`.
- **Поэтапный выкат:** `telegram` (как сейчас) → подключить Viber → `both` (параллельно, обкатать) →
  при желании `viber` (отключить Telegram). Откат — сменой `NOTIFY_CHANNEL`, без выката кода.
- **Self-hosting:** дополнительной инфраструктуры не нужно — используем тот же публичный HTTPS, что
  и для Instagram (`docs/SELF-HOSTING.md`), добавляется лишь путь `/webhook/viber`. Дописать в
  `SELF-HOSTING.md` короткий раздел про Viber-переменные и `set_webhook` после реализации.
- Документацию для менеджеров («как подписаться на бота») — одну страницу: найти бота → написать
  «привет» один раз.

---

## 7. Чек-лист готовности (Definition of Done)
- [ ] `src/services/viber_notify.py` с `ViberNotifier` (методы-зеркала, проверка `status==0`, цикл по id).
- [ ] `ViberError` в `src/exceptions.py`.
- [ ] Viber-настройки в `config.py` + `.env.example`.
- [ ] `/webhook/viber` принимает колбэки и логирует/сохраняет `user id` менеджеров.
- [ ] `_get_notifiers()` и переключение `NOTIFY_CHANNEL` в 3 точках `main.py` (бронь, эскалация, non-text).
- [ ] `tests/test_viber_notify.py` + тест webhook; весь `pytest` зелёный.
- [ ] Ручной E2E пройден в режиме `both`.
- [ ] Раздел про Viber дописан в `docs/SELF-HOSTING.md`.
- [ ] Подтверждён продуктовый выбор Вариант A vs B (см. §1).

---

## Приложение. Вариант B — Viber Community (общий тред)

Если заказчику нужен именно один общий тред (как Telegram-группа):
- Создать **Community** в Viber и **подключить к нему бота**; настроить webhook так же.
- Постинг в общий чат делается отдельным API (post в публичный чат / Channels Post API), где
  важен `sender id` супер-админа сообщества — его берут из `get_account_info`
  (поле `members`, роль `superadmin`).
- ⚠️ Тоньше документация, есть нюанс: посты в Channel **не порождают webhook-колбэк**; и
  по-прежнему действуют коммерческие условия для ботов.
- Объём работ выше, чем у Варианта A; браться, только если общий тред — твёрдое требование.

Ссылки:
[REST Bot API](https://developers.viber.com/docs/api/rest-bot-api/) ·
[Broadcast (developers)](https://developers.viber.com/docs/guides/broadcast-rest-api/) ·
[Broadcast (creators)](https://creators.viber.com/docs/bots-api/resources/messaging/broadcast-message) ·
[Send a Message](https://creators.viber.com/docs/bots-api/resources/messaging/send-message) ·
[Web Hooks](https://creators.viber.com/docs/bots-api/getting-started/web-hooks) ·
[Channels Post API](https://developers.viber.com/docs/tools/channels-post-api/) ·
[Python Bot API](https://developers.viber.com/docs/api/python-bot-api/) ·
[Developers FAQ](https://developers.viber.com/docs/faq/)
