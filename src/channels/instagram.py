import hashlib
import hmac
import json
import re

import httpx
from fastapi import Response
from structlog import get_logger

from src.channels.base import ChannelBase
from src.config import settings
from src.exceptions import InstagramError, InstagramRateLimitError

logger = get_logger()


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
                atype = att.get("type", "unknown")
                types.append(atype)
            raw_keys.append("attachments")

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

    @staticmethod
    def _is_reaction_only(text: str) -> bool:
        """True для непустого текста без букв и цифр: emoji/символы/пунктуация."""
        stripped = text.strip()
        return bool(stripped) and not any(char.isalnum() for char in stripped)

    @staticmethod
    def _extract_referral_metadata(message: dict, messaging: dict) -> dict | None:
        """Извлечь безопасный контекст referral без media URL и raw payload."""
        referral = message.get("referral") or messaging.get("referral")
        if not isinstance(referral, dict):
            return None

        metadata = {
            key: referral[key]
            for key in ("source", "type", "ad_id")
            if referral.get(key) is not None
        }
        ads_context = referral.get("ads_context_data")
        if isinstance(ads_context, dict) and ads_context.get("ad_title") is not None:
            metadata["ad_title"] = ads_context["ad_title"]
        return metadata

    async def receive_message(self, payload: dict) -> list[dict]:
        """Разобрать входящий webhook от Instagram.

        Возвращает список событий:
          {"kind": "user",        "sender_id", "text", "mid"}        — текстовое сообщение
          {"kind": "user_non_text", "sender_id", "text", "mid", "non_text"} — вложение/пост/story без текста
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
                reply_to = message.get("reply_to")
                is_story_reply = (
                    isinstance(reply_to, dict)
                    and isinstance(reply_to.get("story"), dict)
                )
                if is_story_reply and self._is_reaction_only(text):
                    logger.info(
                        "instagram.story_reaction.ignored",
                        sender_id=sender_id,
                        mid=mid,
                    )
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
                    )

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
                        # Самостоятельный referral открывает/возобновляет диалог,
                        # но не содержит вопроса, на который нужно отвечать.
                        continue
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
            except httpx.RequestError as exc:
                raise InstagramError(f"Сетевая ошибка при отправке: {exc}") from exc

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
                    f"Ошибка отправки сообщения: {exc.response.status_code} {exc.response.text}"
                ) from exc

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
                        self._sent_mids.pop_oldest()
            self._log_usage_stats(response)
            logger.info("instagram.message.sent", recipient_id=recipient_id)
            return mid

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
        if code not in cls._RATE_LIMIT_CODES:
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
                    logger.info(
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
