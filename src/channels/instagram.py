import hashlib
import hmac
import json
import re
from time import monotonic
from urllib.parse import urlsplit

import httpx
from fastapi import Response
from structlog import get_logger

from src.channels.base import ChannelBase
from src.config import settings
from src.exceptions import InstagramError, InstagramRateLimitError
from src.services.meta_diagnostics import graph_failure_fields
from src.services.diagnostic_trace import trace_event, traced_delivery

logger = get_logger()

_SHARED_POST_TYPES = frozenset({"ig_post", "share", "ig_reel"})
_IGNORED_ATTACHMENT_TYPES = ("sticker", "gif", "animated_image")


def text_only_ad_event(event: dict) -> dict:
    """Discard ADS context while retaining real text and durable routing identity."""
    referral = event.get("referral")
    if not ((isinstance(referral, dict) and referral.get("source") == "ADS")
            or event.get("silent_reason") == "ad_referral"):
        return event
    text = event.get("text") if isinstance(event.get("text"), str) else ""
    result = {key: event[key] for key in ("sender_id", "mid", "related_mids", "_event_time", "_original_time")
              if key in event}
    result.update(kind="user" if text.strip() else "ignored", text=text, _ad_text_only=True)
    return result


def _ad_url_kind(value: object) -> str:
    """Classify optional referral URLs without logging URLs or arbitrary hostnames."""
    if not value:
        return "absent"
    if not isinstance(value, str):
        return "invalid"
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
            return "invalid"
        host = url.hostname.lower()
        if host in ("instagram.com", "www.instagram.com") and re.fullmatch(
                r"/(?:p|reel|reels)/[A-Za-z0-9_-]+/?", url.path):
            return "instagram_permalink"
        if any(host == root or host.endswith("." + root) for root in ("cdninstagram.com", "fbcdn.net", "fbsbx.com")):
            return "meta_cdn"
        return "other_https"
    except ValueError:
        return "invalid"


def _normalize_phone(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\+?[0-9][0-9 ()\u00a0-]{5,30}", value.strip()):
        return None
    number = re.sub(r"[ ()\u00a0-]", "", value.strip())
    if not 7 <= len(number.lstrip("+")) <= 15:
        return None
    if len(number) == 11 and number.startswith("80"):
        return "+375" + number[2:]
    if len(number) == 12 and number.startswith("375"):
        return "+" + number
    return number


def _template_payload(attachment: dict) -> dict:
    payload = attachment.get("payload")
    if not isinstance(payload, dict):
        return {}
    generic = payload.get("generic")
    if set(payload) == {"generic"} and isinstance(generic, dict):
        return {**generic, "template_type": "generic"}
    return payload


def _empty_generic_template(attachment: dict) -> bool:
    payload = attachment.get("payload")
    if attachment.get("type") != "template" or not isinstance(payload, dict) or set(payload) != {"generic"}:
        return False
    generic = payload["generic"]
    return isinstance(generic, dict) and set(generic) <= {"elements"} and generic.get("elements", []) == []


def _phone_card_number(attachment: dict) -> str | None:
    if attachment.get("type") not in ("template", "contact"):
        return None
    payload = _template_payload(attachment)
    if payload.get("template_type") in ("contact", "phone_number") or attachment.get("type") == "contact":
        return _normalize_phone(payload.get("phone_number"))
    elements = payload.get("elements")
    if payload.get("template_type") != "generic" or not isinstance(elements, list) or len(elements) != 1:
        return None
    element = elements[0]
    if not isinstance(element, dict) or str(element.get("title", "")).strip().lower() not in (
            "phone number", "номер телефона", "телефон"):
        return None
    number = _normalize_phone(element.get("subtitle"))
    if not number:
        return None
    buttons = element.get("buttons", [])
    if not isinstance(buttons, list):
        return None
    matching_button = False
    for button in buttons:
        if not isinstance(button, dict):
            return None
        if button.get("type") == "phone_number":
            if _normalize_phone(button.get("payload")) != number:
                return None
            matching_button = True
        elif isinstance(button.get("url"), str) and button["url"].startswith("tel:"):
            if _normalize_phone(button["url"][4:]) != number:
                return None
            matching_button = True
        elif button.get("type") != "web_url":
            return None
    return number if matching_button else None


class _MidSet:
    """Множество message_id с гарантированной FIFO-эвикцией по размеру.

    Обычный `set.pop()` удаляет произвольный элемент (по хешу), а не самый
    старый — здесь же важно вытеснять именно старые записи. Реализовано
    поверх dict, где порядок вставки гарантирован (Python 3.7+), как уже
    сделано для `_username_cache` в этом файле.
    """

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: dict[str, None] = {}

    def add(self, item: str) -> None:
        self._data[item] = None

    def clear(self) -> None:
        self._data.clear()

    def pop_oldest(self) -> str:
        oldest = next(iter(self._data))
        del self._data[oldest]
        return oldest

    def __contains__(self, item: object) -> bool:
        return item in self._data

    def __len__(self) -> int:
        return len(self._data)


class InstagramChannel(ChannelBase):
    """Канал Instagram Direct через Meta Graph API."""

    BASE_URL = "https://graph.facebook.com/v25.0"
    _username_cache: dict[str, str] = {}
    _USERNAME_CACHE_MAX = 500
    _sent_mids: _MidSet = _MidSet()
    _SENT_MIDS_MAX = 10_000

    # Коды ошибок Meta, сигнализирующие rate-limit/throttling (проверено по
    # docs/graph-api/overview/rate-limiting):
    # 4/17/32/613 — platform-level, 80002 — Business Use Case лимит для Instagram.
    _RATE_LIMIT_CODES = {4, 17, 32, 613, 80002}

    def __init__(self) -> None:
        self._pending_sends: dict[tuple[str, str], int] = {}

    def _remember_sent_mid(self, mid: str) -> None:
        self._sent_mids.add(mid)
        while len(self._sent_mids) > self._SENT_MIDS_MAX:
            self._sent_mids.pop_oldest()

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
        """Проверить наличие настоящих non-text сигналов.

        Возвращает пустой dict, если сигналов нет.
        Если сигналы есть — структуру с types, summary, has_text, text, raw_keys.

        referral — это контекст входа из рекламы/ссылки, а обычный reply_to.mid
        — контекст inline-ответа. Они не являются вложениями. Из reply_to
        non-text считается только story без содержательного текста.
        """
        types: list[str] = []
        raw_keys: list[str] = []

        attachments = message.get("attachments")
        if attachments and isinstance(attachments, list):
            for att in attachments:
                atype = att.get("type") if isinstance(att, dict) else None
                if not isinstance(atype, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", atype):
                    atype = "unknown"
                types.append(atype)
            raw_keys.append("attachments")
        elif attachments is not None and not isinstance(attachments, list):
            types.append("unknown")
            raw_keys.append("attachments")
        if message.get("is_unsupported") is True:
            types.append("unsupported")
            raw_keys.append("is_unsupported")

        reply_to = message.get("reply_to")
        text = message.get("text")
        has_meaningful_text = isinstance(text, str) and bool(text.strip())
        if (
            isinstance(reply_to, dict)
            and reply_to.get("story")
            and not has_meaningful_text
        ):
            types.append("story_reply")
            raw_keys.append("reply_to")

        if not types:
            return {}

        text = text if isinstance(text, str) else ""
        has_text = bool(text)
        summary = f"вложение: {'; '.join(dict.fromkeys(types))}"
        return {
            "types": types,
            "summary": summary,
            "has_text": has_text,
            "text": text,
            "raw_keys": raw_keys,
        }

    @staticmethod
    def _is_shared_post(non_text: dict) -> bool:
        """Shared post/Reel; новый ig_reel включается только с media-флагом."""
        types = set(non_text.get("types", []))
        return (bool(types) and types.issubset(_SHARED_POST_TYPES)
                and (settings.shared_media_enabled or "ig_reel" not in types))

    @staticmethod
    def _is_reaction_only(text: str) -> bool:
        """True для непустого текста без букв и цифр: emoji/символы/пунктуация."""
        stripped = text.strip()
        return bool(stripped) and not any(char.isalnum() for char in stripped)

    @staticmethod
    def _extract_referral_metadata(message: dict, messaging: dict) -> dict | None:
        """Bounded referral data; media URLs remain private until validated by the decoder."""
        referral = message.get("referral") or messaging.get("referral")
        if not isinstance(referral, dict):
            return None

        metadata = {}
        for key in ("source", "type", "ad_id"):
            value = referral.get(key)
            if isinstance(value, str) and 0 < len(value) <= 128:
                metadata[key] = value
        ads_context = referral.get("ads_context_data")
        if isinstance(ads_context, dict):
            title = ads_context.get("ad_title")
            if isinstance(title, str) and title.strip() and len(title) <= 500:
                metadata["ad_title"] = title.strip()
            for key in ("post_id", "permalink", "photo_url", "video_url"):
                value = ads_context.get(key)
                if isinstance(value, str) and 0 < len(value) <= (32 if key == "post_id" else 8192):
                    if key != "post_id" or (value.isascii() and value.isdigit()):
                        metadata[key] = value
        return metadata

    async def receive_message(
        self, payload: dict, *, processed_mids: _MidSet | None = None, merge: bool = True,
        recovery_store=None,
    ) -> list[dict]:
        return self.parse_message_payload(payload, processed_mids=processed_mids,
                                          merge=merge, recovery_store=recovery_store)

    def parse_message_payload(
        self, payload: dict, *, processed_mids: _MidSet | None = None, merge: bool = True,
        recovery_store=None,
    ) -> list[dict]:
        """Разобрать входящий webhook от Instagram.

        Возвращает список событий:
          {"kind": "user",        "sender_id", "text", "mid"}        — текстовое сообщение
          {"kind": "user_non_text", "sender_id", "text", "mid", "non_text"} — вложение/пост/story без текста
          {"kind": "manager",     "client_id", "text", "mid"}        — живой менеджер ответил
        Эхо собственных ответов бота отфильтровывается (is_own_message).
        """
        events: list[dict] = []
        entries = payload.get("entry") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return events
        for entry in entries:
            messages = entry.get("messaging") if isinstance(entry, dict) else None
            if not isinstance(messages, list):
                continue
            for messaging in messages:
                if not isinstance(messaging, dict):
                    continue
                message = messaging.get("message", {})
                if not isinstance(message, dict):
                    continue
                postback = messaging.get("postback")
                if not message and isinstance(postback, dict):
                    title = postback.get("title")
                    if (isinstance(title, str) and title.strip() and len(title) <= 1000
                            and isinstance(postback.get("mid"), str) and postback["mid"]):
                        message = {"mid": postback["mid"], "text": _normalize_phone(title) or title.strip()}
                mid = message.get("mid", "")
                if (not isinstance(mid, str) or len(mid) > 2048
                        or not mid.isascii() or any(char.isspace() for char in mid)):
                    continue
                if message.get("is_deleted") is True:
                    continue

                if message.get("is_echo"):
                    app_id = message.get("app_id") or messaging.get("app_id")
                    if not isinstance(app_id, (str, int)):
                        app_id = None
                    if recovery_store is not None:
                        client_id = (messaging.get("recipient") or {}).get("id")
                        own = recovery_store.own_mid(mid) or (app_id and str(app_id) == settings.instagram_app_id)
                        ambiguous = (not own and isinstance(client_id, str)
                                     and not (app_id and settings.instagram_app_id)
                                     and recovery_store.unresolved_send(client_id))
                        events.append({"kind": "own_echo" if own else "ambiguous_echo" if ambiguous else "manager",
                                       "client_id": client_id, "mid": mid,
                                       "text": message.get("text", ""),
                                       "_event_time": messaging.get("timestamp")})
                        continue
                    if self.is_own_message(mid, app_id):
                        continue
                    recipient = messaging.get("recipient")
                    client_id = recipient.get("id") if isinstance(recipient, dict) else None
                    if isinstance(client_id, str) and 0 < len(client_id) <= 128:
                        echo_text = message.get("text")
                        # Webhook может опередить HTTP-ответ с message_id.
                        if (isinstance(echo_text, str)
                                and (not app_id or not settings.instagram_app_id)
                                and self._pending_sends.get((client_id, echo_text), 0)):
                            if mid:
                                self._remember_sent_mid(mid)
                            logger.info("instagram.echo.early_own", client_id=client_id)
                            continue
                        from src.services.inbound_recovery import existing_receipt_store
                        journal = existing_receipt_store()
                        if (journal and not (app_id and settings.instagram_app_id) and journal.unresolved_send(client_id)):
                            logger.warning("instagram.echo.ambiguous")
                            continue
                        logger.info("instagram.manager.detected", client_id=client_id)
                        events.append(
                            {
                                "kind": "manager",
                                "client_id": client_id,
                                "text": message.get("text") if isinstance(message.get("text"), str) else "",
                                "mid": mid,
                            }
                        )
                    continue

                sender = messaging.get("sender")
                sender_id = sender.get("id") if isinstance(sender, dict) else None
                if not isinstance(sender_id, str) or not 0 < len(sender_id) <= 128:
                    continue
                reaction = messaging.get("reaction")
                if isinstance(reaction, dict):
                    logger.info(
                        "instagram.reaction.ignored",
                        sender_id=sender_id,
                        mid=reaction.get("mid"),
                        action=reaction.get("action"),
                    )
                    continue

                mid = message.get("mid", "")
                raw_text = message.get("text")
                text = raw_text if isinstance(raw_text, str) else ""
                ad_referral = message.get("referral") or messaging.get("referral")
                attachments = message.get("attachments")
                if isinstance(attachments, list) and any(
                    isinstance(att, dict) and att.get("type") == "unsupported_type"
                    for att in attachments
                ):
                    events.append({"kind": "user_silent_handoff", "sender_id": sender_id,
                                   "mid": mid, "text": text, "silent_reason": "unsupported_type"})
                    continue
                if isinstance(ad_referral, dict) and ad_referral.get("source") == "ADS":
                    if not mid and isinstance(messaging.get("timestamp"), (int, float)):
                        receipt = f"{sender_id}\0{messaging['timestamp']}\0{ad_referral.get('ad_id', '')}"
                        mid = "adreferral:" + hashlib.sha256(receipt.encode()).hexdigest()
                    events.append(text_only_ad_event({"sender_id": sender_id, "mid": mid,
                                                       "text": text, "referral": ad_referral}))
                    logger.info("instagram.ad_text_only.received", sender_id=sender_id, mid=mid,
                                has_text=bool(text.strip()))
                    continue
                attachments = message.get("attachments")
                if isinstance(attachments, list):
                    filtered = [att for att in attachments if not (
                        isinstance(att, dict) and att.get("type") in _IGNORED_ATTACHMENT_TYPES)]
                    if len(filtered) != len(attachments):
                        message = {**message, "attachments": filtered}
                        attachments = filtered
                        if not filtered and not text.strip():
                            events.append({"kind": "ignored", "sender_id": sender_id, "mid": mid, "text": ""})
                            continue
                if isinstance(attachments, list) and any(
                    isinstance(att, dict) and att.get("type") == "story_mention"
                    for att in attachments
                ):
                    events.append({"kind": "user_silent_handoff", "sender_id": sender_id,
                                   "mid": mid, "text": text, "silent_reason": "story_mention"})
                    logger.info("instagram.silent_handoff.received", sender_id=sender_id,
                                reason="story_mention")
                    continue
                if isinstance(attachments, list):
                    for attachment in attachments:
                        if not isinstance(attachment, dict) or attachment.get("type") != "template":
                            continue
                        template = attachment.get("payload")
                        template = template if isinstance(template, dict) else {}
                        normalized_template = _template_payload(attachment)
                        elements = normalized_template.get("elements")
                        elements = elements if isinstance(elements, list) else []
                        logger.info("instagram.template.context", mid=mid,
                            payload_keys=[key for key in template if isinstance(key, str) and
                                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,49}", key)][:24],
                            generic_keys=[key for key in template.get("generic", {}) if isinstance(key, str) and
                                re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,49}", key)][:24]
                                if isinstance(template.get("generic"), dict) else [],
                            template_type=normalized_template.get("template_type") if normalized_template.get("template_type") in
                            ("generic", "contact", "phone_number", "button") else "unknown",
                            elements_count=len(elements), recognized_phone=bool(_phone_card_number(attachment)))
                if (message.get("is_unsupported") is not True and isinstance(attachments, list)
                        and len(attachments) == 1 and isinstance(attachments[0], dict)):
                    phone = _phone_card_number(attachments[0])
                    if phone:
                        same_phone_text = _normalize_phone(text) == phone
                        contact_text = text if same_phone_text else (
                            text + "\n" if text.strip() else "") + "Номер в телефонной карточке: " + phone
                        reply = message.get("reply_to")
                        if isinstance(reply, dict) and isinstance(reply.get("story"), dict):
                            message = {**message, "text": contact_text, "attachments": []}
                            text = contact_text
                        else:
                            event = {"kind": "user", "sender_id": sender_id, "mid": mid,
                                "text": contact_text, "phone_card": True, "_contact_phone": phone,
                                "_auto_phone_card": not text.strip() or same_phone_text}
                            referral = self._extract_referral_metadata(message, messaging)
                            if referral is not None:
                                event["referral"] = referral
                            events.append(event)
                            continue
                reply_to = message.get("reply_to")
                is_story_reply = (
                    isinstance(reply_to, dict)
                    and isinstance(reply_to.get("story"), dict)
                )
                if is_story_reply:
                    story = reply_to["story"]
                    story_id = story.get("id")
                    valid_story_id = (
                        isinstance(story_id, str)
                        and 0 < len(story_id) <= 32
                        and story_id.isascii()
                        and story_id.isdigit()
                    )
                    story_url = story.get("url")
                    logger.info(
                        "instagram.story_reply.context",
                        mid=mid,
                        story_id=story_id if valid_story_id else None,
                        story_id_present="id" in story,
                        story_id_valid=valid_story_id,
                        has_story_url=isinstance(story_url, str) and bool(story_url.strip()),
                    )
                if (is_story_reply and self._is_reaction_only(text)
                        and not (settings.voice_media_enabled and isinstance(attachments, list)
                                 and any(isinstance(att, dict) and att.get("type") == "audio" for att in attachments))):
                    usable = (valid_story_id and message.get("is_unsupported") is not True
                              and not attachments)
                    logger.info(
                        "instagram.story_reaction.received",
                        sender_id=sender_id,
                        mid=mid,
                        story_id=story_id if usable else None,
                        context_usable=usable,
                    )
                    events.append({"kind": "story_context", "sender_id": sender_id, "mid": mid,
                                   "text": "", "story": {"id": story_id if usable else None}})
                    continue
                if is_story_reply and text.strip():
                    logger.info(
                        "instagram.story_reply.text_received",
                        sender_id=sender_id,
                        mid=mid,
                    )

                referral = self._extract_referral_metadata(message, messaging)
                if referral is not None:
                    logger.info(
                        "instagram.referral.received",
                        sender_id=sender_id,
                        mid=mid,
                        has_text=bool(text),
                        source=referral.get("source"),
                        referral_type=referral.get("type"),
                        ad_id=referral.get("ad_id"),
                        ad_title=referral.get("ad_title"),
                        has_post_source=bool(referral.get("post_id") or referral.get("permalink")),
                        has_photo_url=bool(referral.get("photo_url")),
                        has_video_url=bool(referral.get("video_url")),
                        photo_url_kind=_ad_url_kind(referral.get("photo_url")),
                        video_url_kind=_ad_url_kind(referral.get("video_url")),
                    )

                non_text = self._extract_non_text_metadata(message)
                image_urls = None
                attachments = message.get("attachments")
                if (message.get("is_unsupported") is not True and isinstance(attachments, list) and attachments
                        and all(isinstance(att, dict) and att.get("type") in ("image", "story_mention", "video")
                                for att in attachments)):
                    image_urls = []
                    for attachment in attachments:
                        payload = attachment.get("payload")
                        url = payload.get("url") if isinstance(payload, dict) else None
                        image_urls.append(url if isinstance(url, str) and len(url) <= 8192 else None)
                if (settings.voice_media_enabled and message.get("is_unsupported") is not True
                        and isinstance(attachments, list) and attachments
                        and all(isinstance(att, dict) and att.get("type") in
                                ("audio", "image", "video", "story_mention") for att in attachments)
                        and any(att["type"] == "audio" for att in attachments)
                        and (settings.image_media_enabled or all(att["type"] == "audio" for att in attachments))
                        and (not is_story_reply or settings.story_media_enabled)):
                    parts = [{"text": text}] if text.strip() else []
                    visuals = []
                    urls, kinds = [], []
                    for att in attachments:
                        body = att.get("payload")
                        url = body.get("url") if isinstance(body, dict) else None
                        url = url if isinstance(url, str) and len(url) <= 8192 else None
                        if att["type"] == "audio":
                            parts.append({"audio": url})
                        else:
                            urls.append(url)
                            kinds.append(att["type"])
                    if is_story_reply:
                        visuals.append({"kind": "story", "story": {"id": story_id if valid_story_id else None}})
                    if urls:
                        visuals.append({"kind": "images", "urls": urls, "types": kinds})
                    event = {"kind": "user_voice", "sender_id": sender_id, "mid": mid,
                             "text": text, "voice_parts": parts, "visual_parts": visuals}
                    if referral is not None:
                        event["referral"] = referral
                    events.append(event)
                    continue
                if is_story_reply and text.strip():
                    event = {
                        "kind": "user_non_text" if non_text else "user",
                        "sender_id": sender_id,
                        "text": text,
                        "mid": mid,
                    }
                    if message.get("is_unsupported") is not True:
                        event["story"] = {"id": story_id if valid_story_id else None}
                    if non_text:
                        event["non_text"] = non_text
                    if referral is not None:
                        event["referral"] = referral
                    events.append(event)
                    continue
                if non_text:
                    is_shared_post = self._is_shared_post(non_text)
                    logger.info(
                        "instagram.non_text.received",
                        sender_id=sender_id,
                        mid=mid,
                        types=non_text["types"],
                        has_text=non_text["has_text"],
                    )
                    if is_shared_post and settings.shared_media_enabled:
                        sources = []
                        for attachment in attachments:
                            payload = attachment.get("payload")
                            payload = payload if isinstance(payload, dict) else {}
                            candidate = next((payload.get(key) for key in
                                              ("ig_post_media_id", "media_id", "reel_video_id", "id")
                                              if isinstance(payload.get(key), str)
                                              and payload[key].isascii() and payload[key].isdigit()
                                              and 0 < len(payload[key]) <= 32), None)
                            url = payload.get("url")
                            logger.info(
                                "instagram.shared_media.context",
                                sender_id=sender_id,
                                attachment_type=attachment.get("type"),
                                media_id=candidate,
                                identity_fields=[key for key in ("ig_post_media_id", "media_id", "reel_video_id", "id") if key in payload],
                                has_media_url=isinstance(url, str) and bool(url.strip()),
                            )
                            sources.append({"id": candidate, "url": url if isinstance(url, str) and len(url) <= 8192 else None})
                        events.append({"kind": "user_shared_post", "sender_id": sender_id,
                                       "text": text, "mid": mid, "shared_post": non_text,
                                       "shared_sources": sources})
                    elif is_shared_post and text.strip():
                        logger.info(
                            "instagram.shared_post.with_text",
                            sender_id=sender_id,
                            mid=mid,
                        )
                        events.append(
                            {
                                "kind": "user",
                                "sender_id": sender_id,
                                "text": text,
                                "mid": mid,
                            }
                        )
                    elif is_shared_post:
                        logger.info(
                            "instagram.shared_post.received",
                            sender_id=sender_id,
                            mid=mid,
                        )
                        events.append(
                            {
                                "kind": "user_shared_post",
                                "sender_id": sender_id,
                                "text": "",
                                "mid": mid,
                                "shared_post": non_text,
                            }
                        )
                    else:
                        events.append(
                            {
                                "kind": "user_non_text",
                                "sender_id": sender_id,
                                "text": non_text["text"],
                                "mid": mid,
                                "non_text": non_text,
                            }
                        )
                        if image_urls is not None and not is_story_reply:
                            events[-1]["images"] = image_urls
                            if any(att["type"] != "image" for att in attachments):
                                events[-1]["image_types"] = [att["type"] for att in attachments]
                        if (message.get("is_unsupported") is not True and not is_story_reply and referral is None
                                and isinstance(attachments, list) and len(attachments) == 1
                                and isinstance(attachments[0], dict) and _empty_generic_template(attachments[0])):
                            if text.strip():
                                events[-1]["kind"] = "user"
                                events[-1].pop("non_text")
                            else:
                                events[-1]["_empty_generic"] = True
                    if referral is not None:
                        events[-1]["referral"] = referral
                else:
                    if text:
                        logger.info("instagram.message.received", sender_id=sender_id)
                        event = {
                            "kind": "user",
                            "sender_id": sender_id,
                            "text": text,
                            "mid": mid,
                        }
                        if referral is not None:
                            event["referral"] = referral
                        events.append(event)
                    elif referral is not None:
                        if referral.get("source") == "ADS":
                            timestamp = messaging.get("timestamp")
                            if (not mid and isinstance(timestamp, int) and not isinstance(timestamp, bool)
                                    and 0 <= timestamp < 10**20):
                                receipt = f"{sender_id}\0{timestamp}\0{referral.get('ad_id', '')}"
                                mid = "adreferral:" + hashlib.sha256(receipt.encode()).hexdigest()
                            events.append({"kind": "user_silent_handoff", "sender_id": sender_id,
                                           "text": "", "mid": mid, "referral": referral,
                                           "silent_reason": "ad_referral"})
                        continue
                    elif mid:
                        logger.warning(
                            "instagram.message.unsupported",
                            sender_id=sender_id,
                            mid=mid,
                        )
                        events.append({"kind": "user_non_text", "sender_id": sender_id,
                                       "text": "", "mid": mid,
                                       "non_text": {"types": ["unknown"], "summary": "вложение: unknown",
                                                    "text": "", "has_text": False, "raw_keys": []}})

        fresh_events = []
        seen_mids: set[str] = set()
        for event in events:
            message_id = event.get("mid")
            if message_id and (message_id in seen_mids or
                               (processed_mids is not None and message_id in processed_mids)):
                logger.info("instagram.webhook.dedup_skipped", mid=message_id)
                continue
            if message_id:
                seen_mids.add(message_id)
            fresh_events.append(event)
        events = fresh_events
        if recovery_store is not None:
            times = {}
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("messaging"), list):
                    continue
                for item in entry.get("messaging", []):
                    if not isinstance(item, dict):
                        continue
                    message = item.get("message") or item.get("postback") or {}
                    mid = message.get("mid") if isinstance(message, dict) else None
                    if mid:
                        times[mid] = item.get("timestamp")
            for event in events:
                event.setdefault("_event_time", times.get(event.get("mid")))
        return self.merge_events(events) if merge else events

    @classmethod
    def merge_events(cls, events: list[dict]) -> list[dict]:
        """Объединить только события текущего пакета, без кеша старых телефонов."""
        events = [text_only_ad_event(event) for event in events]
        ad_mids = {mid for event in events if event.get("_ad_text_only")
                   for mid in [event.get("mid"), *event.get("related_mids", [])]}
        merged = cls._merge_events(events)
        for event in merged:
            if ad_mids.intersection([event.get("mid"), *event.get("related_mids", [])]):
                event["_ad_text_only"] = True
        return merged

    @classmethod
    def _merge_events(cls, events: list[dict]) -> list[dict]:
        if any(event.get("kind") == "user_silent_handoff" or event.get("referral") for event in events):
            groups: dict[str, list] = {}
            segments = []
            for index, event in enumerate(events):
                sender = event.get("sender_id", "")
                group = groups.setdefault(sender, [])
                referral = event.get("referral")
                previous = next((item[1].get("referral") for item in group if item[1].get("referral")), None)
                if event.get("kind") == "user_silent_handoff" or (referral and previous and referral != previous):
                    segments.append(group[:])
                    group.clear()
                if event.get("kind") == "user_silent_handoff":
                    segments.append([(index, event)])
                else:
                    group.append((index, event))
            segments.extend(group for group in groups.values() if group)
            result = []
            for segment in sorted((group for group in segments if group), key=lambda group: group[0][0]):
                batch = [item[1] for item in segment]
                referral = next((event["referral"] for event in batch if event.get("referral")), None)
                if batch[0].get("kind") != "user_silent_handoff":
                    batch = cls._merge_group(batch)
                if referral:
                    for event in batch:
                        event["referral"] = referral
                result.extend(batch)
            return result
        return cls._merge_group(events)

    @classmethod
    def _merge_group(cls, events: list[dict]) -> list[dict]:
        events = cls._merge_visual_events(events)
        events = cls._merge_contact_events(events)
        if settings.voice_media_enabled:
            events = cls._merge_voice_events(events)
        return cls._merge_sender_events(events) if len(events) > 1 else events

    @staticmethod
    def _merge_visual_events(events):
        """Use one ordered media grouping for webhook, API and mixed sources."""
        result, group = [], []

        def flush():
            if not group:
                return
            visual_kinds = {kind for event in group for kind in
                            (([part["kind"] for part in event.get("visual_parts", [])]) or
                             (["images"] if "images" in event else ["shared"] if "shared_sources" in event else []))}
            if not any(event.get("visual_parts") for event in group) and len(visual_kinds) <= 1:
                result.extend(group)
            else:
                first = group[0]
                merged = {key: value for key, value in first.items() if key not in
                          ("images", "image_types", "shared_sources", "voice_parts", "non_text")}
                merged["kind"] = "user_visual"
                merged["text"] = "\n".join(event["text"] for event in group if event.get("text"))
                merged["visual_parts"] = [part for event in group for part in event.get("visual_parts",
                    [{"kind": "images", "urls": event["images"], "types": event.get("image_types")}] if "images" in event
                    else [{"kind": "shared", "sources": event["shared_sources"]}] if "shared_sources" in event else [])]
                merged["related_mids"] = list(dict.fromkeys(mid for event in group for mid in
                    [event.get("mid"), *event.get("related_mids", [])] if mid and mid != first.get("mid")))
                if any("voice_parts" in event for event in group):
                    merged["voice_parts"] = [part for event in group for part in event.get("voice_parts",
                                             [{"text": event["text"]}] if event.get("text") else [])]
                merged["_source_issues"] = list(dict.fromkeys(issue for event in group
                                                               for issue in event.get("_source_issues", [])))
                result.append(merged)
            group.clear()

        for event in events:
            types = set(event.get("non_text", {}).get("types", []))
            if (event["kind"] in ("user", "user_visual", "user_voice", "user_shared_post", "user_non_text")
                    and not event.get("phone_card") and "story" not in event
                    and types.issubset(_SHARED_POST_TYPES | {"image", "video", "audio"})):
                group.append(event)
            else:
                flush()
                result.append(event)
        flush()
        return result

    @staticmethod
    def _merge_voice_events(events: list[dict]) -> list[dict]:
        groups: dict[str, list[list[int]]] = {}
        for index, event in enumerate(events):
            supported = ("voice_parts" in event or event["kind"] == "user"
                         or ("story" in event and settings.story_media_enabled)
                         or ("images" in event and settings.image_media_enabled)
                         or ("shared_sources" in event and settings.shared_media_enabled))
            if any(kind not in ("image", "video", "story_mention", "share", "ig_reel")
                   for kind in event.get("non_text", {}).get("types", [])) and "voice_parts" not in event:
                supported = False
            sender_groups = groups.setdefault(event.get("sender_id", ""), [[]])
            if supported:
                sender_groups[-1].append(index)
            elif sender_groups[-1]:
                sender_groups.append([])
        replacements, dropped = {}, set()
        for indices in (group for sender_groups in groups.values() for group in sender_groups):
            if not any("voice_parts" in events[index] for index in indices):
                continue
            parts, visuals = [], []
            for index in indices:
                event = events[index]
                if "voice_parts" in event:
                    parts.extend(event["voice_parts"])
                    visuals.extend(event.get("visual_parts", []))
                    continue
                if event.get("text", "").strip():
                    parts.append({"text": event["text"]})
                if "story" in event:
                    visuals.append({"kind": "story", "story": event["story"]})
                elif "images" in event:
                    visuals.append({"kind": "images", "urls": event["images"],
                                    "types": event.get("image_types", ["image"] * len(event["images"]))})
                elif "shared_sources" in event:
                    visuals.append({"kind": "shared", "sources": event["shared_sources"]})
            first = events[indices[0]]
            replacements[indices[0]] = {"kind": "user_voice", "sender_id": first["sender_id"],
                "mid": first.get("mid"), "voice_parts": parts, "visual_parts": visuals,
                "text": "\n".join(part["text"] for part in parts if "text" in part),
                "related_mids": list(dict.fromkeys(mid for index in indices for mid in
                    [events[index].get("mid"), *events[index].get("related_mids", [])]
                    if mid and mid != first.get("mid")))}
            dropped.update(indices[1:])
        return [replacements.get(index, event) for index, event in enumerate(events) if index not in dropped]

    @staticmethod
    def _merge_contact_events(events: list[dict]) -> list[dict]:
        dropped: set[int] = set()
        for event in events:
            if not event.pop("_empty_generic", False):
                continue
            content = next((other for other in events if other is not event
                            and other["sender_id"] == event["sender_id"]
                            and (other.get("text", "").strip()
                                 or (settings.voice_media_enabled and "voice_parts" in other))), None)
            if content is not None:
                content.setdefault("related_mids", []).extend(
                    mid for mid in [event.get("mid"), *event.get("related_mids", [])] if mid)
                dropped.add(id(event))
                logger.info("instagram.batch.empty_template_ignored", sender_id=event["sender_id"])
        groups: dict[tuple[str, str], list[dict]] = {}
        for event in events:
            if event["kind"] == "user" and "story" not in event:
                number = event.get("_contact_phone") if event.get("_auto_phone_card") else _normalize_phone(event.get("text"))
                if number:
                    groups.setdefault((event["sender_id"], number), []).append(event)
        for key, group in groups.items():
            cards = [event for event in group if event.get("_auto_phone_card")]
            texts = [event for event in group if not event.get("_auto_phone_card")]
            if cards and texts:
                first = texts[0]
                first["phone_card"] = True
                first["related_mids"] = list(dict.fromkeys(
                    mid for event in group for mid in [event.get("mid"), *event.get("related_mids", [])]
                    if mid and mid != first.get("mid")))
                dropped.update(id(event) for event in group if event is not first)
        for event in events:
            event.pop("_contact_phone", None)
            event.pop("_auto_phone_card", None)
        return [event for event in events if id(event) not in dropped]

    @staticmethod
    def _merge_sender_events(events: list[dict]) -> list[dict]:
        """Смержить связанные события одного отправителя внутри webhook.

        Для shared post сохраняется обычное текстовое событие, а `mid`
        публикации добавляется в related_mids для дедупликации. Для остальных
        non-text событий сохраняется прежнее поведение.
        """
        non_text_map: dict[str, list[int]] = {}
        shared_post_map: dict[str, int] = {}
        user_indices: dict[str, list[int]] = {}
        to_drop: set[int] = set()

        # Современный shared flow: источники не теряются при объединении с вопросом.
        shared_groups: dict[str, list[int]] = {}
        for index, event in enumerate(events):
            if "shared_sources" in event:
                shared_groups.setdefault(event["sender_id"], []).append(index)
        for sender_id, post_indices in shared_groups.items():
            indices = [index for index, event in enumerate(events)
                       if event.get("sender_id") == sender_id and "story" not in event
                       and ("shared_sources" in event or event["kind"] == "user")]
            first = events[post_indices[0]]
            first["shared_sources"] = [source for index in post_indices
                                       for source in events[index]["shared_sources"]]
            first["text"] = "\n".join(events[index]["text"] for index in indices
                                      if events[index].get("text", "").strip())
            first["related_mids"] = list(dict.fromkeys(
                mid for index in indices for mid in [events[index].get("mid"), *events[index].get("related_mids", [])]
                if mid and mid != first.get("mid")))
            to_drop.update(index for index in indices if index != post_indices[0])

        # Фото одного webhook: все подписи/файлы/MID, без перезаписи текста.
        image_groups: dict[str, list[int]] = {}
        for index, event in enumerate(events):
            if index not in to_drop and "images" in event and "story" not in event:
                image_groups.setdefault(event["sender_id"], []).append(index)
        for sender_id, photo_indices in image_groups.items():
            # При mixed non-text/shared post нельзя считать любой текст подписью фото.
            if any(event.get("sender_id") == sender_id and "images" not in event
                   and event["kind"] in ("user_non_text", "user_shared_post")
                   for event in events):
                continue
            indices = [index for index, event in enumerate(events)
                       if event.get("sender_id") == sender_id and "story" not in event
                       and ("images" in event or event["kind"] == "user")]
            first = events[photo_indices[0]]
            image_types = [kind for index in photo_indices for kind in
                           events[index].get("image_types", ["image"] * len(events[index]["images"]))]
            if any(kind != "image" for kind in image_types):
                first["image_types"] = image_types
            first["non_text"]["types"] = list(dict.fromkeys(image_types))
            first["images"] = [url for index in photo_indices for url in events[index]["images"]]
            first["text"] = "\n".join(events[index]["text"] for index in indices
                                      if events[index].get("text", "").strip())
            first["non_text"]["text"] = first["text"]
            first["non_text"]["has_text"] = bool(first["text"])
            first["related_mids"] = list(dict.fromkeys(
                mid for index in indices for mid in
                [events[index].get("mid"), *events[index].get("related_mids", [])]
                if mid and mid != first.get("mid")
            ))
            to_drop.update(index for index in indices if index != photo_indices[0])

        for i, ev in enumerate(events):
            if i in to_drop or "story" in ev or "images" in ev or "shared_sources" in ev or ev.get("phone_card"):
                continue
            if ev["kind"] == "user_non_text":
                sid = ev["sender_id"]
                non_text_map.setdefault(sid, []).append(i)
            elif ev["kind"] == "user_shared_post":
                sid = ev["sender_id"]
                shared_post_map[sid] = i
            elif ev["kind"] == "user":
                sid = ev["sender_id"]
                if sid not in user_indices:
                    user_indices[sid] = []
                user_indices[sid].append(i)

        # Merge: переносим текст из user → user_non_text
        for sid, nt_indices in non_text_map.items():
            if sid not in user_indices:
                continue
            nt_idx = nt_indices[0]
            nt_ev = events[nt_idx]
            indices = sorted([*nt_indices, *user_indices[sid]])
            nt_ev["text"] = "\n".join(events[index]["text"] for index in indices if events[index].get("text"))
            nt_ev["non_text"] = {
                "types": list(dict.fromkeys(kind for index in nt_indices
                                            for kind in events[index]["non_text"].get("types", []))),
                "summary": "; ".join(events[index]["non_text"].get("summary", "") for index in nt_indices),
                "text": nt_ev["text"], "has_text": bool(nt_ev["text"]),
            }
            nt_ev["related_mids"] = list(dict.fromkeys(mid for index in indices for mid in
                [events[index].get("mid"), *events[index].get("related_mids", [])]
                if mid and mid != nt_ev.get("mid")))
            to_drop.update(index for index in indices if index != nt_idx)

        # Shared post — контекст, поэтому оставляем первый обычный текст.
        for sid, post_idx in shared_post_map.items():
            if sid not in user_indices:
                continue
            user_idx = next((index for index in user_indices[sid] if index not in to_drop), None)
            if user_idx is None:
                # Текст уже объединён с другим вложением: публикация остаётся отдельной.
                continue
            user_ev = events[user_idx]
            post_mid = events[post_idx].get("mid")
            if post_mid:
                user_ev.setdefault("related_mids", []).append(post_mid)
            to_drop.add(post_idx)
            logger.info(
                "instagram.shared_post.paired_in_webhook",
                sender_id=sid,
            )

        # Несколько обычных сообщений текущего окна — один вопрос по порядку.
        plain_groups: dict[str, list[list[int]]] = {}
        for index, event in enumerate(events):
            if index not in to_drop and event["kind"] == "user" and "story" not in event:
                groups = plain_groups.setdefault(event["sender_id"], [])
                if not groups or "_reaction_story" in event:
                    groups.append([])
                groups[-1].append(index)
        for indices in (group for groups in plain_groups.values() for group in groups):
            first = events[indices[0]]
            first["text"] = "\n".join(events[index]["text"] for index in indices if events[index].get("text"))
            first["related_mids"] = list(dict.fromkeys(mid for index in indices for mid in
                [events[index].get("mid"), *events[index].get("related_mids", [])]
                if mid and mid != first.get("mid")))
            to_drop.update(indices[1:])
        return [ev for i, ev in enumerate(events) if i not in to_drop]

    async def send_message(self, recipient_id: str, text: str) -> str | None:
        from src.services.inbound_recovery import current_delivery, current_processing, existing_receipt_store, legacy_processing
        if current_processing.get() is not None:
            raise InstagramError("recovery_draft_send_blocked", delivery_status="blocked")
        delivery = current_delivery.get()
        if isinstance(delivery, dict) and (delivery["channel"] != "instagram" or
                delivery["destination"] != recipient_id or delivery["client_id"] != recipient_id or (not delivery.get("legacy") and
                not (settings.inbound_recovery_enabled and settings.recovery_allows(delivery["client_id"])))):
            raise InstagramError("recovery_scope_blocked", delivery_status="blocked")
        store = existing_receipt_store() if current_delivery.get() is None else None
        intent = store.begin_legacy_send(recipient_id, text) if store else None
        trace_event('delivery_intent', sender_id=recipient_id, channel='instagram', delivery_id=intent,
                    text=text, durable_journal=store is not None)
        try:
            mid = await self._send_message(recipient_id, text)
        except Exception as exc:
            if store:
                status = "retry_wait" if isinstance(exc, InstagramRateLimitError) else getattr(exc, "delivery_status", "unknown")
                try:
                    store.finish_legacy_failure(intent, status)
                    trace_event('receipt_recorded', sender_id=recipient_id, channel='instagram',
                                delivery_id=intent, status=status)
                except Exception:
                    trace_event('receipt_commit_failed', sender_id=recipient_id,
                                channel='instagram', delivery_id=intent)
                    logger.error("inbound.legacy_receipt.failed")
                    status = "unknown"
                exc.journal_intent = intent
                exc.delivery_status = status
            raise
        if store and not mid:
            try:
                store.finish_legacy_failure(intent, "unknown")
                trace_event('receipt_recorded', sender_id=recipient_id, channel='instagram',
                            delivery_id=intent, status='unknown')
            except Exception:
                trace_event('receipt_commit_failed', sender_id=recipient_id,
                            channel='instagram', delivery_id=intent, provisional_status='unknown')
                logger.error("inbound.legacy_receipt.failed")
            exc = InstagramError("missing_receipt", delivery_status="unknown")
            exc.journal_intent = intent
            raise exc
        if mid and store:
            try:
                store.record_legacy_receipt(recipient_id, text, mid, legacy_processing.get(),
                    settings.instagram_ig_user_id or settings.instagram_page_id or "instagram", intent)
                trace_event('receipt_recorded', sender_id=recipient_id, channel='instagram',
                            delivery_id=intent, status='sent', receipt=mid)
            except Exception:
                trace_event('receipt_commit_failed', sender_id=recipient_id, channel='instagram',
                            delivery_id=intent, provisional_status='sent')
                # The external send already succeeded. A journal failure must
                # not turn that receipt into a legacy automatic resend.
                logger.error("inbound.legacy_receipt.failed")
        return mid

    @traced_delivery('instagram')
    async def _send_message(self, recipient_id: str, text: str) -> str | None:
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
            pending_key = (recipient_id, text)
            self._pending_sends[pending_key] = self._pending_sends.get(pending_key, 0) + 1
            try:
                response = await client.post(url, params=params, json=payload)
            except httpx.RequestError as exc:
                status = "retry_wait" if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)) else "unknown"
                raise InstagramError("Сетевая ошибка при отправке", delivery_status=status) from None
            finally:
                remaining = self._pending_sends[pending_key] - 1
                if remaining:
                    self._pending_sends[pending_key] = remaining
                else:
                    del self._pending_sends[pending_key]

            # Meta не всегда сигнализирует троттлинг отдельным HTTP-статусом —
            # код ошибки может прийти в JSON-теле при формально успешном 200.
            # raise_for_status() ниже такое не поймает, поэтому проверяем сначала.
            rate_limit_exc = self._check_rate_limit(response)
            if rate_limit_exc:
                logger.warning(
                    "instagram.rate_limited",
                    recipient_id=recipient_id,
                    error_code=rate_limit_exc.error_code,
                    retry_after_seconds=rate_limit_exc.retry_after_seconds,
                )
                raise rate_limit_exc

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise InstagramError(
                    f"Ошибка отправки сообщения: HTTP {exc.response.status_code}",
                    delivery_status="unknown" if exc.response.status_code >= 500 else "blocked",
                ) from None

            mid = None
            try:
                data = response.json()
                if isinstance(data, dict):
                    mid = data.get("message_id")
            except Exception:
                mid = None
            if not isinstance(mid, str) or not mid or len(mid) > 2048 or not mid.isascii() or any(c.isspace() for c in mid):
                mid = None
            if mid:
                self._remember_sent_mid(mid)
            self._log_usage_stats(response)
            logger.info("instagram.message.sent", recipient_id=recipient_id)
            return mid

    async def _conversations_get(self, path: str, params: dict) -> dict:
        """Known Graph paths only. Never follow a provider-supplied next URL."""
        operation = "conversations" if path.endswith("/conversations") else "messages"

        def failure(exc, reason, response=None, cause=None):
            fields = graph_failure_fields(reason, response=response, exception=cause)
            exc.meta_diagnostics = fields
            logger.warning("instagram.graph.failed", operation=operation, **fields)
            return exc

        if not settings.instagram_access_token:
            raise InstagramError("missing_token")
        cooldown = getattr(self, "_reconcile_pause_until", 0)-monotonic()
        if cooldown > 0:
            raise InstagramRateLimitError("conversations_usage_cooldown", retry_after_seconds=cooldown)
        if not re.fullmatch(r"[A-Za-z0-9_:=.-]{1,2048}(?:/(?:conversations|messages))?", path):
            raise InstagramError("invalid_graph_path")
        try:
            async with httpx.AsyncClient(timeout=settings.instagram_reconcile_timeout_seconds) as client:
                response = await client.get(f"{self.BASE_URL}/{path}", params=params,
                    headers={"Authorization": "Bearer " + settings.instagram_access_token})
        except httpx.RequestError as exc:
            raise failure(InstagramError("conversations_transport", delivery_status="retry_wait"),
                          "transport_timeout" if isinstance(exc, httpx.TimeoutException) else "transport_error", cause=exc) from None
        limited = self._check_rate_limit(response)
        if limited:
            raise failure(limited, "rate_limit", response)
        if response.status_code == 429:
            raise failure(InstagramRateLimitError("conversations_rate_limit", retry_after_seconds=self._extract_retry_after(response)),
                          "rate_limit", response)
        try:
            data = response.json()
        except ValueError:
            raise failure(InstagramError("conversations_invalid_json"), "invalid_json", response) from None
        if response.status_code != 200 or not isinstance(data, dict) or data.get("error"):
            error = data.get("error") if isinstance(data, dict) else None
            error = error if isinstance(error, dict) else {}
            code = graph_failure_fields("graph_error", response=response).get("meta_code")
            exc = InstagramError(f"conversations_http_{response.status_code}_code_{code}")
            error_message = str(error.get("message", "")).lower()
            exc.category = ("invalid_cursor" if params.get("after") and "cursor" in error_message else
                            "unsupported_field" if code == 100 and "nonexisting field" in error_message else
                            "auth" if code in (10, 190, 200) else "provider")
            raise failure(exc, "graph_error" if error else "http_status" if response.status_code != 200 else "invalid_shape", response)
        rows = data.get("data")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise failure(InstagramError("conversations_invalid_shape"), "invalid_shape", response)
        paging = data.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after") if paging.get("next") else None
        if paging.get("next") and not after:
            raise failure(InstagramError("conversations_missing_cursor"), "missing_cursor", response)
        if after is not None and (not isinstance(after, str) or len(after) > 8192):
            raise failure(InstagramError("conversations_invalid_cursor"), "invalid_cursor", response)
        self._log_usage_stats(response)
        try:
            usage = json.loads(response.headers.get("x-business-use-case-usage", "{}"))
            def high_usage(value):
                if isinstance(value, dict):
                    return any(isinstance(value.get(key), (int, float)) and value[key] >= settings.instagram_usage_warn_pct
                               for key in ("call_count", "total_time", "total_cputime")) or any(high_usage(item) for item in value.values())
                return isinstance(value, list) and any(high_usage(item) for item in value)
            if high_usage(usage):
                self._reconcile_pause_until = monotonic()+max(120, self._extract_retry_after(response) or 0)
        except (ValueError, TypeError):
            pass
        return {"data": rows, "after": after}

    async def list_conversations(self, after: str | None = None) -> dict:
        page = settings.instagram_page_id
        params = {"platform": "instagram", "fields": "id,participants", "limit": "20"}
        if after:
            params["after"] = after
        return await self._conversations_get(f"{page}/conversations", params)

    async def list_conversation_messages(self, conversation_id: str, after: str | None = None) -> dict:
        params = {"fields": "id,created_time,from,to,message,attachments,shares,reply_to,is_unsupported", "limit": "20"}
        if after is not None:
            if not isinstance(after, str) or not after or len(after) > 8192:
                error = InstagramError("conversations_invalid_cursor")
                error.category = "invalid_cursor"
                raise error
            params["after"] = after
        return await self._conversations_get(f"{conversation_id}/messages", params)

    @classmethod
    def _check_rate_limit(cls, response: httpx.Response) -> "InstagramRateLimitError | None":
        """Проверить признак rate-limit внутри JSON-тела ответа.

        Возвращает готовое (но не брошенное) исключение, если найден
        `error.code` из `_RATE_LIMIT_CODES`, иначе None. Не бросает исключений
        сама — при любой проблеме парсинга просто считает, что лимита нет.
        """
        try:
            data = response.json()
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        error = data.get("error")
        if not isinstance(error, dict):
            return None
        code = error.get("code")
        if type(code) is not int or code not in cls._RATE_LIMIT_CODES:
            return None

        return InstagramRateLimitError(
            error.get("message") or f"Instagram API rate limit (code={code})",
            error_code=code,
            retry_after_seconds=cls._extract_retry_after(response),
        )

    @staticmethod
    def _extract_retry_after(response: httpx.Response) -> float | None:
        """Достать оценку времени до снятия троттлинга из заголовка usage.

        Meta кладёт `estimated_time_to_regain_access` (в минутах) внутрь
        JSON-заголовка `X-Business-Use-Case-Usage`, обычно вложенного по
        business-object-id — точная структура вложенности не задокументирована
        явно, поэтому ищем ключ рекурсивно по всему разобранному значению.
        Возвращает секунды, либо None, если заголовка нет/не распарсился.
        """
        try:
            seconds = float(response.headers.get("retry-after", "0"))
            if 0 < seconds <= 7*86400:
                return seconds
        except (ValueError, TypeError):
            pass
        header = response.headers.get("x-business-use-case-usage")
        if not header:
            return None
        try:
            usage = json.loads(header)
        except Exception:
            return None

        def _find(value):
            if isinstance(value, dict):
                if "estimated_time_to_regain_access" in value:
                    return value["estimated_time_to_regain_access"]
                for v in value.values():
                    found = _find(v)
                    if found is not None:
                        return found
            elif isinstance(value, list):
                for item in value:
                    found = _find(item)
                    if found is not None:
                        return found
            return None

        minutes = _find(usage)
        if minutes is None:
            return None
        try:
            return float(minutes) * 60
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _log_usage_stats(response: httpx.Response) -> None:
        """Проактивный мониторинг usage-заголовка (Задача 1).

        Парсит X-Business-Use-Case-Usage на каждом успешном ответе и
        логирует call_count/total_time в процентах. Если процент превышает
        порог instagram_usage_warn_pct — пишет warning.

        Meta не документирует точный потолок для каждого аккаунта, поэтому
        проценты считаются относительно 100 как абсолютные значения из
        заголовка (Meta сама нормализует их в 0..100).
        """
        header = response.headers.get("x-business-use-case-usage")
        if not header:
            return
        try:
            usage = json.loads(header)
        except Exception:
            return

        def _find_stats(value):
            if isinstance(value, dict):
                if "call_count" in value and "total_time" in value:
                    return value
                for v in value.values():
                    found = _find_stats(v)
                    if found is not None:
                        return found
            elif isinstance(value, list):
                for item in value:
                    found = _find_stats(item)
                    if found is not None:
                        return found
            return None

        stats = _find_stats(usage)
        if stats is None:
            return

        call_count = stats.get("call_count", 0)
        total_time = stats.get("total_time", 0)
        logger.debug(
            "instagram.usage",
            call_count_pct=call_count,
            total_time_pct=total_time,
        )

        warn_pct = settings.instagram_usage_warn_pct
        if call_count >= warn_pct or total_time >= warn_pct:
            logger.warning(
                "instagram.usage.high",
                call_count_pct=call_count,
                total_time_pct=total_time,
                warn_pct=warn_pct,
            )

    def is_own_message(self, mid: str, app_id: str | None = None) -> bool:
        """Эхо отправлено самим ботом (а не живым менеджером)?"""
        if app_id and settings.instagram_app_id and str(app_id) == settings.instagram_app_id:
            return True
        if mid and mid in self._sent_mids:
            return True
        if mid:
            from src.services.inbound_recovery import existing_receipt_store
            store = existing_receipt_store()
            if store and store.own_mid(mid):
                return True
        return False

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
                    # debug, не info: username — персональные данные, а в
                    # Privacy Policy заявлен их сбор, так что светить его в
                    # логах (ротация 14 дней) без нужды не стоит. Для
                    # диагностики хватает sender_id. Строка добавлялась как
                    # доказательство вызова Business Asset User Profile Access
                    # для скринкаста Meta App Review — при необходимости
                    # поднимается через LOG_LEVEL=DEBUG.
                    logger.debug(
                        "instagram.get_username.success",
                        sender_id=sender_id,
                        username=username,
                    )
                    return username
            except Exception:
                logger.debug("instagram.get_username.failed", sender_id=sender_id)
        return None

    async def handle_webhook(self, payload: dict) -> list[dict]:
        """Реализация абстрактного метода ChannelBase."""
        return await self.receive_message(payload)
