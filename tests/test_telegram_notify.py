from unittest.mock import AsyncMock, Mock, patch

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


def test_tour_sync_has_no_client_escalation_wrapper():
    message = "🔄 Обновление туров · Google Docs\nИзменены: 1\n✏️ Париж"
    assert _build_notification_text(sender_id="tour_sync", context=message, tag="Tour sync") == message


@pytest.mark.parametrize("handle", ["shelter_0", "_shelter_0", "unknovvnoname", "@SHELTER_0", " @_Shelter_0 ", " @Unknovvnoname "])
def test_test_account_label(handle):
    text = _build_notification_text(sender_id="123", instagram_handle=handle)
    assert "🧪 Тестовый аккаунт" in text
    assert "@@" not in text


@pytest.mark.parametrize("handle", [None, "ivan_petrov", "shelter_01", "unknovvnoname_other"])
def test_regular_account_has_no_test_label(handle):
    text = _build_notification_text(sender_id="123", instagram_handle=handle)
    assert "Тестовый аккаунт" not in text


@pytest.mark.parametrize("sender", ["tour_sync", "123"])
async def test_tour_sync_preview_and_receipt(sender):
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 987}}
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response
    with patch("src.services.telegram_notify.AsyncClient", return_value=mock_client):
        receipt = await TelegramNotifier()._send("synthetic", "manager", sender_id=sender)
    assert receipt == "987"
    payload = mock_client.post.await_args.kwargs["json"]
    assert payload["text"] == "synthetic" and payload["chat_id"] == "manager"
    if sender == "tour_sync":
        assert payload["link_preview_options"] == {"is_disabled": True}
    else:
        assert "link_preview_options" not in payload


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
    mock_response.json = Mock(return_value={"ok": True})

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with (
        patch("src.services.telegram_notify.AsyncClient", return_value=mock_client),
        patch("src.services.telegram_notify.settings.telegram_bot_token", "TEST_TOKEN"),
        patch("src.services.telegram_notify.settings.telegram_manager_chat_id", "TEST_MANAGER"),
        patch("src.services.telegram_notify.settings.telegram_secondary_chat_id", ""),
        patch("src.services.telegram_notify.settings.telegram_tertiary_chat_id", ""),
        patch("src.services.telegram_notify.settings.telegram_extra_chat_id", ""),
    ):
        notifier = TelegramNotifier()
        await notifier.notify_manager(
            sender_id="123",
            instagram_handle="ivan_petrov",
            context="ищет тур в Турцию",
            client_name="Иван",
            client_phone="+375291234567",
            client_email="ivan@mail.com",
            tag="Горящий тур",
        )

    mock_client.post.assert_called_once()
    _, kwargs = mock_client.post.call_args
    assert kwargs["json"]["chat_id"] == "TEST_MANAGER"
    assert "ivan_petrov" in kwargs["json"]["text"]
    assert "ищет тур" in kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_notify_manager_includes_extra_chat():
    """Дополнительный чат (TELEGRAM_EXTRA_CHAT_ID) тоже получает уведомления."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={"ok": True})

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with (
        patch("src.services.telegram_notify.AsyncClient", return_value=mock_client),
        patch(
            "src.services.telegram_notify.settings.telegram_manager_chat_id", "111"
        ),
        patch(
            "src.services.telegram_notify.settings.telegram_secondary_chat_id", ""
        ),
        patch(
            "src.services.telegram_notify.settings.telegram_tertiary_chat_id", ""
        ),
        patch(
            "src.services.telegram_notify.settings.telegram_extra_chat_id",
            "828032935",
        ),
    ):
        notifier = TelegramNotifier()
        await notifier.notify_manager(sender_id="123", context="тест")

    assert mock_client.post.await_count == 2
    chat_ids = [
        call.kwargs["json"]["chat_id"]
        for call in mock_client.post.await_args_list
    ]
    assert chat_ids == ["111", "828032935"]


@pytest.mark.asyncio
async def test_notify_manager_api_error():
    mock_response = AsyncMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with (
        patch("src.services.telegram_notify.AsyncClient", return_value=mock_client),
        patch("src.services.telegram_notify.settings.telegram_secondary_chat_id", ""),
        patch("src.services.telegram_notify.settings.telegram_tertiary_chat_id", ""),
    ):
        notifier = TelegramNotifier()
        with pytest.raises(Exception):
            await notifier.notify_manager(
                sender_id="123",
                context="тест",
            )
