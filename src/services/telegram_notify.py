from datetime import datetime, timezone

from httpx import AsyncClient
from structlog import get_logger

from src.config import settings
from src.exceptions import TelegramError

logger = get_logger()

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _escape_md(text: str) -> str:
    """Escape Markdown special characters in user-provided text."""
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")


def _build_notification_text(
    sender_id: str,
    instagram_handle: str | None = None,
    context: str = "",
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    tag: str = "Нужен звонок",
) -> str:
    handle = f"@{instagram_handle}" if instagram_handle else sender_id
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")

    escaped_context = _escape_md(context)

    lines = [
        "\U0001f6a8 *Новая эскалация*",
        "",
        f"\U0001f464 *Клиент:* {handle}",
        f"\U0001f550 {now}",
        "",
        "\U0001f4cb *Суть:*",
        escaped_context,
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
    sheets_id = settings.google_requests_sheet_id
    if sheets_id:
        lines.append(f"\U0001f517 *Google Sheets:*")
        lines.append(f"https://docs.google.com/spreadsheets/d/{sheets_id}")
    else:
        lines.append("\U0001f517 *Google Sheets:* не указан")

    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self) -> None:
        self._token: str = settings.telegram_bot_token
        self._chat_ids: list[str] = [
            cid
            for cid in [
                settings.telegram_manager_chat_id,
                settings.telegram_secondary_chat_id,
            ]
            if cid
        ]

    async def _send(
        self,
        text: str,
        chat_id: str,
        sender_id: str | None = None,
        tag: str | None = None,
        tour: str | None = None,
    ) -> None:
        url = TELEGRAM_API_URL.format(token=self._token)
        async with AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
        if response.status_code != 200:
            logger.error(
                "telegram.send.failed",
                chat_id=chat_id,
                status=response.status_code,
                text=response.text,
            )
            raise TelegramError(
                f"Telegram API error for {chat_id}: {response.status_code} {response.text}"
            )
        logger.info(
            "telegram.sent",
            chat_id=chat_id,
            sender_id=sender_id,
            tag=tag,
            tour=tour,
        )

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
        if not self._token or not self._chat_ids:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN или TELEGRAM_MANAGER_CHAT_ID не настроены"
            )

        text = _build_notification_text(
            sender_id=sender_id,
            instagram_handle=instagram_handle,
            context=context,
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            tag=tag,
        )

        last_exc = None
        for cid in self._chat_ids:
            try:
                await self._send(text=text, chat_id=cid, sender_id=sender_id, tag=tag)
            except TelegramError as e:
                last_exc = e
        if last_exc and len(self._chat_ids) > 0:
            raise last_exc

    async def notify_booking(
        self,
        sender_id: str,
        instagram_handle: str | None = None,
        client_name: str | None = None,
        client_phone: str | None = None,
        client_email: str | None = None,
        tour: str = "",
    ) -> None:
        if not self._token or not self._chat_ids:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN или TELEGRAM_MANAGER_CHAT_ID не настроены"
            )

        handle = f"@{instagram_handle}" if instagram_handle else sender_id
        now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")

        lines = [
            "\U0001f4e9 *Новая бронь*",
            "",
            f"\U0001f464 *Клиент:* {handle}",
            f"\U0001f550 {now}",
            "",
        ]
        if tour:
            lines.append(f"\U0001f399 *Тур:* {tour}")
        if client_name:
            lines.append(f"\U0001f464 *Имя:* {client_name}")
        if client_phone:
            lines.append(f"\U0001f4de *Телефон:* {client_phone}")
        if client_email:
            lines.append(f"\U0001f4e7 *Email:* {client_email}")

        sheets_id = settings.google_requests_sheet_id
        lines.append("")
        if sheets_id:
            lines.append("\U0001f517 *Google Sheets:*")
            lines.append(f"https://docs.google.com/spreadsheets/d/{sheets_id}")
        else:
            lines.append("\U0001f517 *Google Sheets:* не указан")

        text = "\n".join(lines)

        last_exc = None
        for cid in self._chat_ids:
            try:
                await self._send(text=text, chat_id=cid, sender_id=sender_id, tour=tour)
            except TelegramError as e:
                last_exc = e
        if last_exc and len(self._chat_ids) > 0:
            raise last_exc
