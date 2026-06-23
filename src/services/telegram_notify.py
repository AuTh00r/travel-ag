from httpx import AsyncClient
from structlog import get_logger

from src.config import settings
from src.exceptions import TelegramError

logger = get_logger()

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

MAX_HISTORY_LINES = 15


def _escape_markdown(text: str | None) -> str:
    if text is None:
        return ""
    special = r"\_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, "\\" + ch)
    return text


def _format_conversation(history: list[dict]) -> str:
    lines = []
    for msg in history[-MAX_HISTORY_LINES:]:
        role = msg.get("role", "user")
        text = msg.get("text", msg.get("content", ""))[:300]
        prefix = "🧑 Клиент" if role == "user" else "🤖 Агент"
        lines.append(f"{prefix}: {_escape_markdown(text)}")
    return "\n".join(lines) if lines else "_Нет сообщений_"


def _build_notification_text(
    client_name: str,
    client_phone: str,
    client_email: str,
    request_summary: str,
    conversation_history: list[dict],
    tag: str,
) -> str:
    sheets_id = settings.google_requests_sheet_id
    sheets_link = (
        f"https://docs.google.com/spreadsheets/d/{sheets_id}"
        if sheets_id
        else "_не указан_"
    )

    return (
        "\U0001f535 *Новая эскалация / заявка*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "\U0001f464 *Клиент:*\n"
        "   Имя: " + _escape_markdown(client_name) + "\n"
        "   \U0001f4de Телефон: `" + _escape_markdown(client_phone) + "`\n"
        "   \U0001f4e7 Email: " + _escape_markdown(client_email) + "\n\n"
        "\U0001f4cb *Запрос:*\n" + _escape_markdown(request_summary) + "\n\n"
        "\U0001f3f7 *Тег:* `" + _escape_markdown(tag) + "`\n\n"
        "\U0001f4c4 *История переписки:*\n"
        + _format_conversation(conversation_history)
        + "\n\n"
        "\U0001f517 *Google Sheets:* [Открыть заявки](" + sheets_link + ")"
    )


class TelegramNotifier:
    def __init__(self) -> None:
        self._token: str = settings.telegram_bot_token
        self._chat_id: str = settings.telegram_manager_chat_id

    async def notify_manager(
        self,
        client_name: str,
        client_phone: str,
        client_email: str,
        request_summary: str,
        conversation_history: list[dict],
        tag: str = "Нужен звонок",
    ) -> None:
        if not self._token or not self._chat_id:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN или TELEGRAM_MANAGER_CHAT_ID не настроены"
            )

        text = _build_notification_text(
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            request_summary=request_summary,
            conversation_history=conversation_history,
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
            client_name=client_name,
            tag=tag,
            chat_id=self._chat_id,
        )
