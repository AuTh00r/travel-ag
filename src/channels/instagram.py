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
    _sent_mids: set[str] = set()
    _SENT_MIDS_MAX = 10_000

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

    @staticmethod
    def _extract_non_text_metadata(message: dict) -> dict:
        """Проверить наличие non-text сигналов: attachments, reply_to, referral.

        Возвращает пустой dict, если сигналов нет.
        Если сигналы есть — структуру с types, summary, has_text, text, raw_keys.
        """
        types: list[str] = []
        raw_keys: list[str] = []

        attachments = message.get("attachments")
        if attachments and isinstance(attachments, list):
            for att in attachments:
                atype = att.get("type", "unknown")
                types.append(atype)
            raw_keys.append("attachments")

        if message.get("reply_to"):
            types.append("story_reply_or_reply")
            raw_keys.append("reply_to")

        if message.get("referral"):
            types.append("referral_or_shared_post")
            raw_keys.append("referral")

        if not types:
            return {}

        text = message.get("text", "")
        has_text = bool(text)
        summary = f"вложение: {'; '.join(t for t in set(types))}"
        return {
            "types": types,
            "summary": summary,
            "has_text": has_text,
            "text": text,
            "raw_keys": raw_keys,
        }

    async def receive_message(self, payload: dict) -> list[dict]:
        """Разобрать входящий webhook от Instagram.

        Возвращает список событий:
          {"kind": "user",        "sender_id", "text", "mid"}        — текстовое сообщение
          {"kind": "user_non_text", "sender_id", "text", "mid", "non_text"} — вложение/пост/story reply
          {"kind": "manager",     "client_id", "text", "mid"}        — живой менеджер ответил
        Эхо собственных ответов бота отфильтровывается (is_own_message).
        """
        events: list[dict] = []

        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                message = messaging.get("message", {})
                mid = message.get("mid", "")

                if message.get("is_echo"):
                    app_id = message.get("app_id") or messaging.get("app_id")
                    if self.is_own_message(mid, app_id):
                        continue
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
                if not sender_id:
                    continue
                mid = message.get("mid", "")

                non_text = self._extract_non_text_metadata(message)
                if non_text:
                    logger.info(
                        "instagram.non_text.received",
                        sender_id=sender_id,
                        mid=mid,
                        types=non_text["types"],
                        has_text=non_text["has_text"],
                    )
                    events.append(
                        {
                            "kind": "user_non_text",
                            "sender_id": sender_id,
                            "text": non_text["text"],
                            "mid": mid,
                            "non_text": non_text,
                        }
                    )
                else:
                    text = message.get("text", "")
                    if text:
                        logger.info("instagram.message.received", sender_id=sender_id)
                        events.append(
                            {
                                "kind": "user",
                                "sender_id": sender_id,
                                "text": text,
                                "mid": mid,
                            }
                        )
                    elif mid:
                        logger.warning(
                            "instagram.message.unsupported",
                            sender_id=sender_id,
                            mid=mid,
                        )

        if len(events) > 1:
            events = self._merge_sender_events(events)

        return events

    @staticmethod
    def _merge_sender_events(events: list[dict]) -> list[dict]:
        """Смержить user и user_non_text события одного отправителя.

        Meta часто присылает shared post и текст как два отдельных messaging-события
        в одном webhook. Если у отправителя есть оба типа в одном батче:
        - текст из user-события переносится в user_non_text
        - одно из событий удаляется (дубль)
        """
        non_text_map: dict[str, int] = {}  # sender_id → index in events
        user_indices: dict[str, list[int]] = {}
        to_drop: set[int] = set()

        for i, ev in enumerate(events):
            if ev["kind"] == "user_non_text":
                sid = ev["sender_id"]
                non_text_map[sid] = i
            elif ev["kind"] == "user":
                sid = ev["sender_id"]
                if sid not in user_indices:
                    user_indices[sid] = []
                user_indices[sid].append(i)

        # Merge: переносим текст из user → user_non_text
        for sid, nt_idx in non_text_map.items():
            if sid not in user_indices:
                continue
            for ui in user_indices[sid]:
                user_ev = events[ui]
                if user_ev.get("text"):
                    nt_ev = events[nt_idx]
                    nt_ev["text"] = user_ev["text"]
                    nt_ev["non_text"]["text"] = user_ev["text"]
                    nt_ev["non_text"]["has_text"] = True
                to_drop.add(ui)

        return [ev for i, ev in enumerate(events) if i not in to_drop]

    async def send_message(self, recipient_id: str, text: str) -> str | None:
        """Отправить текстовое сообщение через Instagram Graph API.

        Возвращает message_id, если API вернул, иначе None.
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

    def is_own_message(self, mid: str, app_id: str | None = None) -> bool:
        """Эхо отправлено самим ботом (а не живым менеджером)?"""
        if app_id and settings.instagram_app_id and str(app_id) == settings.instagram_app_id:
            return True
        return bool(mid) and mid in self._sent_mids

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

        url = f"{self.BASE_URL}/{sender_id}"
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

    async def handle_webhook(self, payload: dict) -> list[dict]:
        """Реализация абстрактного метода ChannelBase."""
        return await self.receive_message(payload)
