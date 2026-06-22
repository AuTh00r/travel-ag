# Instagram Graph API — Справочник интеграции

## Общие сведения

Instagram Business API работает через Facebook Graph API. Все запросы идут к
`https://graph.instagram.com` или `https://graph.facebook.com`.

**Необходимые условия:**
1. Instagram Business или Creator аккаунт
2. Facebook Page, связанный с Instagram аккаунтом
3. Facebook Developer App с одобренными разрешениями (App Review)
4. Долгосрочный токен (Long-lived Access Token)

## Токены и разрешения

### Необходимые разрешения (Permissions)
- `instagram_manage_messages` — чтение и отправка сообщений
- `pages_messaging` — управление сообщениями через Facebook Page
- `instagram_basic` — базовый доступ к профилю

### Получение токена
1. Создать Facebook App → Instagram Basic Display
2. Авторизовать пользователя → получить short-lived token
3. Обменять на long-lived token:
```
GET https://graph.instagram.com/access_token
  ?grant_type=ig_exchange_token
  &client_secret={app-secret}
  &access_token={short-lived-token}
```

## Webhook подписка

### 1. Настройка webhook в Facebook App

URL: `https://your-domain.com/webhook/instagram`
Verify Token: произвольная строка (совпадает с `INSTAGRAM_VERIFY_TOKEN` в .env)

Подписка на события:
- `messages` — входящие сообщения

### 2. Endpoint верификации (GET)

```python
from fastapi import FastAPI, Request, Query

app = FastAPI()

VERIFY_TOKEN = "my_secret_token"  # из .env


@app.get("/webhook/instagram")
async def verify_webhook(
    request: Request,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Верификация webhook от Meta."""

    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")

    return Response(status_code=403, content="Forbidden")
```

### 3. Endpoint приёма сообщений (POST)

```python
@app.post("/webhook/instagram")
async def receive_message(request: Request):
    """Обработчик входящих сообщений из Instagram."""

    payload = await request.json()

    for entry in payload.get("entry", []):
        for messaging in entry.get("messaging", []):
            sender_id = messaging.get("sender", {}).get("id")
            message = messaging.get("message", {})
            text = message.get("text", "")

            if text:
                # Отправляем в AI-движок
                await process_message(sender_id, text)

    return {"status": "ok"}


async def process_message(sender_id: str, text: str):
    """Обрабатывает сообщение через AI-движок и отправляет ответ."""

    # Получаем/создаём сессию
    session = await get_or_create_session(sender_id)

    # Добавляем сообщение в граф
    from langchain_core.messages import HumanMessage
    session["messages"].append(HumanMessage(content=text))

    # Запускаем граф
    from src.ai.engine import build_graph
    graph = build_graph()
    result = await graph.ainvoke(session)

    # Отправляем ответ
    for msg in result.get("messages", []):
        if hasattr(msg, "content") and msg.content and not isinstance(msg, HumanMessage):
            await send_instagram_message(sender_id, msg.content)

    # Сохраняем сессию
    await save_session(sender_id, result)
```

## Отправка сообщения

```python
import httpx
from src.config import settings


async def send_instagram_message(recipient_id: str, text: str) -> None:
    """Отправляет текстовое сообщение через Instagram API."""

    url = "https://graph.facebook.com/v21.0/me/messages"
    params = {"access_token": settings.INSTAGRAM_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": text},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, params=params, json=payload)
        response.raise_for_status()
```

## Ограничения API

| Лимит | Значение |
|---|---|
| Сообщений в секунду | ~20 (базовый, можно увеличить через App Review) |
| Длина сообщения | до 2000 символов |
| Webhook timeout | 20 секунд |
| Структура webhook | JSON, Content-Type: application/json |

## Полезные эндпоинты

### Информация об Instagram-профиле
```
GET https://graph.instagram.com/{ig-user-id}
  ?fields=id,username,name,account_type
  &access_token={token}
```

### Список бесед
```
GET https://graph.facebook.com/v21.0/{page-id}/conversations
  ?fields=id,snippet,participants,updated_time
  &access_token={token}
```

## Рекомендации

- **Ngrok для разработки:** `ngrok http 8000` — создаёт HTTPS-туннель для webhook
- **Логирование:** логируй все входящие и исходящие webhook-запросы
- **Retry:** Instagram может отправить webhook повторно — используй id сообщения для дедупликации
- **Timeout:** AI-ответ должен укладываться в 20 секунд (лимит webhook)
