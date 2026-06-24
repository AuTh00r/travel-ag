import hashlib
import hmac
import re

import httpx
from fastapi import Response
from structlog import get_logger

from src.channels.base import ChannelBase
from src.config import settings
from src.exceptions import InstagramError

logger = get_logger()


class InstagramChannel(ChannelBase):
    """Канал Instagram Direct через Meta Graph API."""

    BASE_URL = "https://graph.facebook.com/v25.0"
    _username_cache: dict[str, str] = {}
    _USERNAME_CACHE_MAX = 500

    def verify_signature(self, raw_body: bytes, signature_header: str | None) -> bool:
        if not settings.instagram_app_secret:
            # Подпись НЕ проверяется — допустимо только для локальных тестов.
            # В проде INSTAGRAM_APP_SECRET обязан быть задан, иначе webhook
            # принимает произвольные POST без проверки подлинности.
            logger.warning(
                "instagram.webhook.signature_skipped",
                reason="INSTAGRAM_APP_SECRET is empty",
            )
            return True
        if not signature_header:
            return False

        expected = hmac.new(
            settings.instagram_app_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(f"sha256={expected}", signature_header)

    async def verify_webhook(
        self,
        hub_mode: str | None,
        hub_challenge: str | None,
        hub_verify_token: str | None,
    ) -> Response:
        """Верификация webhook от Meta (hub.challenge)."""

        if (
            hub_mode == "subscribe"
            and hub_verify_token == settings.instagram_verify_token
        ):
            logger.info("instagram.webhook.verified")
            return Response(content=hub_challenge, media_type="text/plain")

        logger.warning("instagram.webhook.verify_failed")
        return Response(status_code=403, content="Forbidden")

    async def receive_message(self, payload: dict) -> list[tuple[str, str, str]]:
        """Разобрать входящий webhook от Instagram.

        Возвращает список (sender_id, text, mid) для каждого сообщения.
        Фильтрует echo-сообщения (собственные ответы бота) чтобы
        избежать бесконечного цикла. mid нужен для дедупликации ретраев.
        """
        messages: list[tuple[str, str, str]] = []

        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                if messaging.get("message", {}).get("is_echo"):
                    continue
                sender_id = messaging.get("sender", {}).get("id")
                message = messaging.get("message", {})
                text = message.get("text", "")
                mid = message.get("mid", "")

                if sender_id and text:
                    logger.info("instagram.message.received", sender_id=sender_id)
                    messages.append((sender_id, text, mid))

        return messages

    async def send_message(self, recipient_id: str, text: str) -> None:
        """Отправить текстовое сообщение через Instagram Graph API.

        Instagram DM лимит — 1000 символов. Если длиннее — обрезаем.
        """

        if not settings.instagram_access_token:
            raise InstagramError("INSTAGRAM_ACCESS_TOKEN не задан")

        max_len = 1000
        if len(text) > max_len:
            urls = re.findall(r"https?://[^\s\n]+", text)
            text = re.sub(r"https?://[^\s\n]+", "", text)
            text = text.strip()[: max_len - 3] + "..."
            for u in urls:
                if len(text) + len(u) + 1 <= max_len:
                    text += "\n" + u
                else:
                    break
            logger.warning(
                "instagram.message.truncated",
                original_len=len(text),
                max_len=max_len,
                urls_preserved=len(urls),
            )

        url = f"{self.BASE_URL}/me/messages"
        params = {"access_token": settings.instagram_access_token}
        payload = {
            "recipient": {"id": recipient_id},
            "messaging_type": "RESPONSE",
            "message": {"text": text},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.post(url, params=params, json=payload)
                response.raise_for_status()
                logger.info("instagram.message.sent", recipient_id=recipient_id)
            except httpx.HTTPStatusError as exc:
                raise InstagramError(
                    f"Ошибка отправки сообщения: {exc.response.status_code} {exc.response.text}"
                ) from exc
            except httpx.RequestError as exc:
                raise InstagramError(f"Сетевая ошибка при отправке: {exc}") from exc

    async def get_username(self, sender_id: str) -> str | None:
        """Получить Instagram username пользователя.

        Использует User Profile API: GET /{sender_id} ?fields=name,username
        Результат кешируется in-memory (макс. 500 записей).
        При ошибке API возвращает None без retry.
        """
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
                    if len(self._username_cache) > self._USERNAME_CACHE_MAX:
                        self._username_cache.pop(next(iter(self._username_cache)))
                    return username
            except Exception:
                logger.debug("instagram.get_username.failed", sender_id=sender_id)
        return None

    async def handle_webhook(self, payload: dict) -> list[tuple[str, str]]:
        """Реализация абстрактного метода ChannelBase."""
        return await self.receive_message(payload)
