from unittest.mock import AsyncMock, patch

import pytest

from src.services.telegram_notify import (
    TelegramNotifier,
    _build_notification_text,
    _escape_markdown,
    _format_conversation,
)


def test_escape_markdown():
    text = "Hello _world_ *bold* [link](url)"
    result = _escape_markdown(text)
    assert "\\_" in result
    assert "\\*" in result
    assert "\\[" in result
    assert "\\]" in result


def test_format_conversation_empty():
    assert _format_conversation([]) == "_Нет сообщений_"


def test_format_conversation():
    history = [
        {"role": "user", "text": "Хочу тур в Турцию"},
        {"role": "assistant", "text": "Отличный выбор!"},
    ]
    result = _format_conversation(history)
    assert "Клиент" in result
    assert "Агент" in result
    assert "Турцию" in result
    assert "выбор" in result


def test_format_conversation_truncated():
    long_text = "A" * 500
    history = [{"role": "user", "text": long_text}]
    result = _format_conversation(history)
    assert len(result) < len(long_text) + 100


def test_build_notification_text():
    text = _build_notification_text(
        client_name="Иван Петров",
        client_phone="+375291234567",
        client_email="ivan@mail.com",
        request_summary="Хочу тур в Турцию",
        conversation_history=[{"role": "user", "text": "Привет"}],
        tag="Нужен звонок",
    )
    assert "Иван Петров" in text
    assert "375291234567" in text
    assert "ivan@mail" in text
    assert "Турцию" in text
    assert "Нужен звонок" in text


def test_build_notification_without_sheets_id():
    with patch("src.services.telegram_notify.settings.google_requests_sheet_id", ""):
        text = _build_notification_text(
            client_name="Тест",
            client_phone="+375291234567",
            client_email="test@test.com",
            request_summary="Тест",
            conversation_history=[],
            tag="тег",
        )
        assert "не указан" in text.lower()


@pytest.mark.asyncio
async def test_notify_manager_missing_config():
    with patch("src.services.telegram_notify.settings.telegram_bot_token", ""), patch(
        "src.services.telegram_notify.settings.telegram_manager_chat_id", ""
    ):
        notifier = TelegramNotifier()
        with pytest.raises(Exception):
            await notifier.notify_manager(
                client_name="Тест",
                client_phone="+375291234567",
                client_email="test@test.com",
                request_summary="Тест",
                conversation_history=[],
            )


@pytest.mark.asyncio
async def test_notify_manager_success():
    mock_response = AsyncMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("src.services.telegram_notify.AsyncClient", return_value=mock_client):
        notifier = TelegramNotifier()
        await notifier.notify_manager(
            client_name="Иван",
            client_phone="+375291234567",
            client_email="ivan@mail.com",
            request_summary="Турция",
            conversation_history=[],
            tag="Нужен звонок",
        )

    mock_client.post.assert_called_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["chat_id"] is not None
    assert kwargs["json"]["parse_mode"] == "Markdown"
    assert "Иван" in kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_notify_manager_api_error():
    mock_response = AsyncMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("src.services.telegram_notify.AsyncClient", return_value=mock_client):
        notifier = TelegramNotifier()
        with pytest.raises(Exception):
            await notifier.notify_manager(
                client_name="Иван",
                client_phone="+375291234567",
                client_email="ivan@mail.com",
                request_summary="Турция",
                conversation_history=[],
                tag="тест",
            )


@pytest.mark.asyncio
async def test_escalate_node_calls_notifier():
    from src.ai.nodes import escalate
    from langchain_core.messages import HumanMessage, AIMessage

    state = {
        "messages": [
            HumanMessage(content="Хочу тур"),
            AIMessage(content="Какое направление?"),
            HumanMessage(content="Турция"),
        ],
        "client_id": "test",
        "client_name": "Иван",
        "client_phone": "+375291234567",
        "client_email": "ivan@mail.com",
        "request_type": "tour_search",
        "tour_params": {"destination": "Турция"},
        "found_tours": [],
        "selected_tour": None,
        "faq_answer": None,
        "needs_escalation": True,
        "escalation_reason": "Сложный запрос",
        "current_step": "escalate",
        "awaiting_field": None,
        "conversation_history": [],
    }

    with patch(
        "src.ai.nodes.TelegramNotifier.notify_manager", new=AsyncMock()
    ) as mock_notify:
        result = await escalate(state)

    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert call_kwargs["client_name"] == "Иван"
    assert call_kwargs["client_phone"] == "+375291234567"
    assert call_kwargs["tag"] == "Сложный запрос"
    assert result["conversation_history"]
    assert len(result["conversation_history"]) == 3
