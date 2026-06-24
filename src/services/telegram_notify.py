from datetime import datetime, timezone

from httpx import AsyncClient
from structlog import get_logger

from src.config import settings
from src.exceptions import TelegramError

logger = get_logger()

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _build_notification_text(
    sender_id: str,
    instagram_handle: str | None = None,
    context: str = "",
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    tag: str = "Нужен звонок",
) -> str:
    sheets_id = settings.google_requests_sheet_id
    sheets_link = (
        f"https://docs.google.com/spreadsheets/d/{sheets_id}"
        if sheets_id
        else "_не указан_"
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


class TelegramNotifier:
    def __init__(self) -> None:
        self._token: str = settings.telegram_bot_token
        self._chat_id: str = settings.telegram_manager_chat_id

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
        if not self._token or not self._chat_id:
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

        url = TELEGRAM_API_URL.format(token=self._token)

        async with AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )

        if response.status_code != 200:
            raise TelegramError(
                f"Telegram API error: {response.status_code} {response.text}"
            )

        logger.info(
            "telegram.notification.sent",
            sender_id=sender_id,
            tag=tag,
            chat_id=self._chat_id,
        )
