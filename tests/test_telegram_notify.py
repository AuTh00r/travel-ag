from unittest.mock import AsyncMock, patch

import pytest

from src.services.telegram_notify import (
    TelegramNotifier,
    _build_notification_text,
)


def test_build_notification_with_handle():
    text = _build_notification_text(
        sender_id="123",
        instagram_handle="ivan_petrov",
        context="ищет тур",
        client_name="Иван",
        client_phone="+375291234567",
    )
    assert "@ivan_petrov" in text
    assert "+375291234567" in text
    assert "ищет тур" in text
    assert "Иван" in text


def test_build_notification_no_contacts():
    text = _build_notification_text(
        sender_id="123",
        instagram_handle=None,
        context="ищет тур",
    )
    assert "123" in text
    assert "Контакты:" not in text


def test_build_notification_no_handle_falls_back_to_sender_id():
    text = _build_notification_text(
        sender_id="sender_456",
        instagram_handle=None,
        context="жалоба на сервис",
    )
    assert "sender_456" in text
    assert "@" not in text


def test_build_notification_without_sheets_id():
    with patch("src.services.telegram_notify.settings.google_requests_sheet_id", ""):
        text = _build_notification_text(
            sender_id="123",
            instagram_handle="test",
            context="тест",
        )
        assert "не указан" in text.lower()


def test_build_notification_contacts_section_shown_when_any_contact():
    text = _build_notification_text(
        sender_id="123",
        context="тест",
        client_name="Петр",
    )
    assert "Контакты:" in text
    assert "Петр" in text


@pytest.mark.asyncio
async def test_notify_manager_missing_config():
    with patch("src.services.telegram_notify.settings.telegram_bot_token", ""), patch(
        "src.services.telegram_notify.settings.telegram_manager_chat_id", ""
    ):
        notifier = TelegramNotifier()
        with pytest.raises(Exception):
            await notifier.notify_manager(
                sender_id="123",
                context="тест",
            )


@pytest.mark.asyncio
async def test_notify_manager_success():
    mock_response = AsyncMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("src.services.telegram_notify.AsyncClient", return_value=mock_client):
        with patch("src.services.telegram_notify.settings.telegram_secondary_chat_id", ""):
            notifier = TelegramNotifier()
            await notifier.notify_manager(
                sender_id="123",
                instagram_handle="ivan_petrov",
                context="ищет тур в Турцию",
                client_name="Иван",
                client_phone="+375291234567",
                client_email="ivan@mail.com",
                tag="Нужен звонок",
            )

    mock_client.post.assert_called_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["chat_id"] is not None
    assert "ivan_petrov" in kwargs["json"]["text"]
    assert "ищет тур" in kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_notify_manager_api_error():
    mock_response = AsyncMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("src.services.telegram_notify.AsyncClient", return_value=mock_client):
        with patch("src.services.telegram_notify.settings.telegram_secondary_chat_id", ""):
            notifier = TelegramNotifier()
            with pytest.raises(Exception):
                await notifier.notify_manager(
                    sender_id="123",
                    context="тест",
                )
