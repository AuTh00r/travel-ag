import httpx
from fastapi import Response
from structlog import get_logger

from src.channels.base import ChannelBase
from src.config import settings
from src.exceptions import InstagramError

logger = get_logger()


class InstagramChannel(ChannelBase):
    """Канал Instagram Direct через Meta Graph API."""

    BASE_URL = "https://graph.facebook.com/v21.0"

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

    async def receive_message(self, payload: dict) -> list[tuple[str, str]]:
        """Разобрать входящий webhook-платеж от Instagram.

        Возвращает список (sender_id, text) для каждого сообщения.
        """
        messages: list[tuple[str, str]] = []

        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                message = messaging.get("message", {})
                text = message.get("text", "")

                if sender_id and text:
                    logger.info("instagram.message.received", sender_id=sender_id)
                    messages.append((sender_id, text))

        return messages

    async def send_message(self, recipient_id: str, text: str) -> None:
        """Отправить текстовое сообщение через Instagram Graph API."""

        if not settings.instagram_access_token:
            raise InstagramError("INSTAGRAM_ACCESS_TOKEN не задан")

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

    async def handle_webhook(self, payload: dict) -> list[tuple[str, str]]:
        """Реализация абстрактного метода ChannelBase."""
        return await self.receive_message(payload)
