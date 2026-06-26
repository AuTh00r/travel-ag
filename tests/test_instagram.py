from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

client = TestClient(app)


class TestWebhookVerification:
    """GET /webhook/instagram — верификация webhook (hub.challenge)."""

    def test_valid_verify_token_returns_challenge(self):
        settings.instagram_verify_token = "test_token"
        response = client.get(
            "/webhook/instagram",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "12345",
                "hub.verify_token": "test_token",
            },
        )
        assert response.status_code == 200
        assert response.text == "12345"

    def test_invalid_verify_token_returns_forbidden(self):
        settings.instagram_verify_token = "real_token"
        response = client.get(
            "/webhook/instagram",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "12345",
                "hub.verify_token": "wrong_token",
            },
        )
        assert response.status_code == 403

    def test_wrong_mode_returns_forbidden(self):
        settings.instagram_verify_token = "test_token"
        response = client.get(
            "/webhook/instagram",
            params={
                "hub.mode": "unsubscribe",
                "hub.challenge": "12345",
                "hub.verify_token": "test_token",
            },
        )
        assert response.status_code == 403


class TestSignatureVerification:
    def test_valid_signature_passes(self):
        import hashlib
        import hmac

        from src.channels.instagram import InstagramChannel

        settings.instagram_app_secret = "test_secret"
        body = b'{"test":"data"}'
        expected = (
            "sha256=" + hmac.new(b"test_secret", body, hashlib.sha256).hexdigest()
        )
        ch = InstagramChannel()
        assert ch.verify_signature(body, expected)

    def test_missing_signature_fails(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_app_secret = "test_secret"
        ch = InstagramChannel()
        assert not ch.verify_signature(b"{}", None)

    def test_wrong_signature_fails(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_app_secret = "test_secret"
        ch = InstagramChannel()
        assert not ch.verify_signature(b"{}", "sha256=deadbeef")

    def test_no_secret_skips_check(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_app_secret = ""
        ch = InstagramChannel()
        assert ch.verify_signature(b"{}", None)


class TestWebhookReceive:
    """POST /webhook/instagram — приём сообщений."""

    def setup_method(self):
        settings.instagram_access_token = ""
        settings.instagram_app_secret = ""  # отключаем проверку подписи для тестов

    @patch("src.main._process_safely")
    def test_receive_valid_message(self, mock_process):
        mock_process.return_value = None
        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "12345"},
                            "message": {
                                "text": "Привет! Хочу тур в Турцию",
                                "mid": "mid_001",
                            },
                        }
                    ]
                }
            ]
        }
        response = client.post("/webhook/instagram", json=payload)
        assert response.status_code == 200
        # Вебхук отвечает мгновенно пустым телом, обработка идёт в фоне.
        assert response.text == ""
        mock_process.assert_awaited_once_with("12345", "Привет! Хочу тур в Турцию")

    def test_receive_empty_payload(self):
        response = client.post("/webhook/instagram", json={"entry": []})
        assert response.status_code == 200
        assert response.text == ""

    @patch("src.main._process_safely")
    def test_dedup_skips_duplicate_mid(self, mock_process):
        """Повторный webhook с тем же mid не должен запускать обработку."""
        mock_process.return_value = None
        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "12345"},
                            "message": {"text": "Дубликат", "mid": "mid_dup_1"},
                        }
                    ]
                }
            ]
        }
        # Первый запрос — обрабатывается
        response1 = client.post("/webhook/instagram", json=payload)
        assert response1.status_code == 200
        assert mock_process.await_count == 1

        # Второй запрос с тем же mid — пропускается
        response2 = client.post("/webhook/instagram", json=payload)
        assert response2.status_code == 200
        assert mock_process.await_count == 1  # не вырос

    @patch("src.main._process_safely")
    def test_no_mid_skipped(self, mock_process):
        """Сообщение без mid пропускается (нет mid для дедупа)."""
        mock_process.return_value = None
        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "12345"},
                            "message": {"text": "Тест без mid"},
                        }
                    ]
                }
            ]
        }
        response = client.post("/webhook/instagram", json=payload)
        assert response.status_code == 200
        mock_process.assert_not_awaited()

    def test_last_seen_updated_after_post(self):
        # Любой валидный POST обновляет last_seen (in-memory, глобально).
        client.post("/webhook/instagram", json={"entry": []})
        response = client.get("/webhook/instagram/last_seen")
        assert response.status_code == 200
        data = response.json()
        assert data["received_ever"] is True
        assert data["last_received_at"] is not None

    def test_receive_message_without_text(self):
        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "12345"},
                            "message": {"attachments": [{"type": "image"}]},
                        }
                    ]
                }
            ]
        }
        response = client.post("/webhook/instagram", json=payload)
        assert response.status_code == 200


class TestInstagramChannelSend:
    """InstagramChannel.send_message — отправка сообщений."""

    @pytest.mark.asyncio
    @patch("src.channels.instagram.httpx.AsyncClient")
    async def test_send_message_success(self, mock_client):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        settings.instagram_access_token = "test_token"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = Mock(return_value={"message_id": "mid_sent_1"})
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        channel = InstagramChannel()
        mid = await channel.send_message("12345", "Hello")
        assert mid == "mid_sent_1"
        assert "mid_sent_1" in InstagramChannel._sent_mids

        mock_client.return_value.__aenter__.return_value.post.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.channels.instagram.httpx.AsyncClient")
    async def test_send_message_raises_on_http_error(self, mock_client):
        from src.channels.instagram import InstagramChannel
        from src.exceptions import InstagramError

        settings.instagram_access_token = "test_token"

        error_response = AsyncMock()
        error_response.status_code = 400
        error_response.text = "error_text"

        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "error",
                request=Mock(spec=httpx.Request),
                response=error_response,
            )
        )

        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        channel = InstagramChannel()
        with pytest.raises(InstagramError):
            await channel.send_message("12345", "Hello")

    @pytest.mark.asyncio
    async def test_send_message_without_token(self):
        from src.channels.instagram import InstagramChannel
        from src.exceptions import InstagramError

        settings.instagram_access_token = ""

        channel = InstagramChannel()
        with pytest.raises(InstagramError, match="ACCESS_TOKEN"):
            await channel.send_message("12345", "Hello")


class TestGetUsername:
    @pytest.mark.asyncio
    async def test_get_username_success(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_access_token = "test_token"
        InstagramChannel._username_cache.clear()

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = Mock(return_value={"username": "ivan_petrov"})

        channel = InstagramChannel()
        with patch.object(httpx.AsyncClient, "get", new=AsyncMock()) as mock_get:
            mock_get.return_value = mock_response
            result = await channel.get_username("12345")

        assert result == "ivan_petrov"

    @pytest.mark.asyncio
    async def test_get_username_cached(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_access_token = "test_token"
        InstagramChannel._username_cache.clear()
        InstagramChannel._username_cache["12345"] = "cached_user"

        channel = InstagramChannel()
        with patch.object(httpx.AsyncClient, "get") as mock_get:
            result = await channel.get_username("12345")

        assert result == "cached_user"
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_username_fallback_on_error(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_access_token = "test_token"
        InstagramChannel._username_cache.clear()

        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "error", request=Mock(spec=httpx.Request), response=mock_response
            )
        )

        channel = InstagramChannel()
        with patch.object(httpx.AsyncClient, "get", new=AsyncMock()) as mock_get:
            mock_get.return_value = mock_response
            result = await channel.get_username("12345")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_username_no_token(self):
        from src.channels.instagram import InstagramChannel

        settings.instagram_access_token = ""
        InstagramChannel._username_cache.clear()

        channel = InstagramChannel()
        result = await channel.get_username("12345")
        assert result is None


class TestNonTextParser:
    """InstagramChannel._extract_non_text_metadata — определение non-text сигналов."""

    @pytest.mark.asyncio
    async def test_attachment_without_text(self):
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "attachments": [{"type": "image"}],
                        "mid": "mid_att_1",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 1
        ev = events[0]
        assert ev["kind"] == "user_non_text"
        assert ev["sender_id"] == "CLIENT_42"
        assert ev["text"] == ""
        assert "image" in ev["non_text"]["types"]

    @pytest.mark.asyncio
    async def test_attachment_with_text(self):
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "text": "Смотри фото",
                        "attachments": [{"type": "image"}],
                        "mid": "mid_att_2",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 1
        ev = events[0]
        assert ev["kind"] == "user_non_text"
        assert ev["text"] == "Смотри фото"
        assert ev["non_text"]["has_text"] is True

    @pytest.mark.asyncio
    async def test_reply_to(self):
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "reply_to": {"mid": "some_mid"},
                        "mid": "mid_reply_1",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 1
        ev = events[0]
        assert ev["kind"] == "user_non_text"
        assert "story_reply_or_reply" in ev["non_text"]["types"]

    @pytest.mark.asyncio
    async def test_referral(self):
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "referral": {"source": "story"},
                        "mid": "mid_ref_1",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 1
        ev = events[0]
        assert ev["kind"] == "user_non_text"
        assert "referral_or_shared_post" in ev["non_text"]["types"]

    @pytest.mark.asyncio
    async def test_plain_text_stays_user(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_99"},
                    "message": {
                        "text": "Хочу тур",
                        "mid": "mid_user_1",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert events == [
            {"kind": "user", "sender_id": "CLIENT_99", "text": "Хочу тур", "mid": "mid_user_1"}
        ]

    @pytest.mark.asyncio
    async def test_non_text_echo_bot_ignored(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        InstagramChannel._sent_mids.add("mid_bot_non_text")
        settings.instagram_app_id = ""
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "BUSINESS_ACC"},
                    "recipient": {"id": "CLIENT_42"},
                    "message": {
                        "is_echo": True,
                        "mid": "mid_bot_non_text",
                        "attachments": [{"type": "image"}],
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert events == []

    @pytest.mark.asyncio
    async def test_merge_non_text_with_user_event(self):
        """user_non_text и user одного sender мержатся в одно событие."""
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [
                    {
                        "sender": {"id": "CLIENT_42"},
                        "message": {
                            "attachments": [{"type": "ig_post"}],
                            "mid": "mid_post_1",
                        },
                    },
                    {
                        "sender": {"id": "CLIENT_42"},
                        "message": {
                            "text": "смотри какой тур",
                            "mid": "mid_text_1",
                        },
                    },
                ]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 1
        ev = events[0]
        assert ev["kind"] == "user_non_text"
        assert ev["text"] == "смотри какой тур"
        assert ev["non_text"]["has_text"] is True

    @pytest.mark.asyncio
    async def test_merge_only_same_sender(self):
        """Разные sender'ы не мержатся."""
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [
                    {
                        "sender": {"id": "CLIENT_42"},
                        "message": {
                            "attachments": [{"type": "ig_post"}],
                            "mid": "mid_post_1",
                        },
                    },
                    {
                        "sender": {"id": "CLIENT_43"},
                        "message": {
                            "text": "просто текст",
                            "mid": "mid_text_2",
                        },
                    },
                ]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 2
        kinds = [ev["kind"] for ev in events]
        assert "user_non_text" in kinds
        assert "user" in kinds

    @pytest.mark.asyncio
    async def test_no_merge_without_non_text(self):
        """Два user-события без non_text не мержатся."""
        from src.channels.instagram import InstagramChannel

        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [
                    {
                        "sender": {"id": "CLIENT_42"},
                        "message": {
                            "text": "первое",
                            "mid": "mid_1",
                        },
                    },
                    {
                        "sender": {"id": "CLIENT_42"},
                        "message": {
                            "text": "второе",
                            "mid": "mid_2",
                        },
                    },
                ]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 2
        assert all(ev["kind"] == "user" for ev in events)

    @pytest.mark.asyncio
    async def test_non_text_echo_manager(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        settings.instagram_app_id = ""
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "BUSINESS_ACC"},
                    "recipient": {"id": "CLIENT_42"},
                    "message": {
                        "is_echo": True,
                        "mid": "mid_human_non_text",
                        "attachments": [{"type": "image"}],
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert len(events) == 1
        assert events[0]["kind"] == "manager"
        assert events[0]["client_id"] == "CLIENT_42"
        assert events[0]["text"] == ""


class TestNonTextWebhook:
    """POST /webhook/instagram — обработка non-text сообщений."""

    def setup_method(self):
        settings.instagram_access_token = ""
        settings.instagram_app_secret = ""

    @patch("src.main._process_non_text_safely")
    def test_attachment_triggers_non_text_handler(self, mock_process):
        mock_process.return_value = None
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "attachments": [{"type": "image"}],
                        "mid": "mid_nt_webhook_1",
                    },
                }]
            }]
        }
        response = client.post("/webhook/instagram", json=payload)
        assert response.status_code == 200
        mock_process.assert_awaited_once()
        args, _ = mock_process.await_args
        assert args[0] == "CLIENT_42"

    @patch("src.main._process_non_text_safely")
    def test_dedup_skips_duplicate_non_text_mid(self, mock_process):
        mock_process.return_value = None
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "attachments": [{"type": "image"}],
                        "mid": "mid_nt_dedup_1",
                    },
                }]
            }]
        }
        client.post("/webhook/instagram", json=payload)
        assert mock_process.await_count == 1
        client.post("/webhook/instagram", json=payload)
        assert mock_process.await_count == 1

    @patch("src.main._process_non_text_safely")
    def test_non_text_no_mid_skipped(self, mock_process):
        mock_process.return_value = None
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_42"},
                    "message": {
                        "attachments": [{"type": "image"}],
                    },
                }]
            }]
        }
        response = client.post("/webhook/instagram", json=payload)
        assert response.status_code == 200
        mock_process.assert_not_awaited()


class TestEchoClassification:
    """InstagramChannel.receive_message — классификация эхо-сообщений."""

    @pytest.mark.asyncio
    async def test_human_manager_echo(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        settings.instagram_app_id = ""
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "BUSINESS_ACC"},
                    "recipient": {"id": "CLIENT_42"},
                    "message": {
                        "is_echo": True,
                        "mid": "mid_human_1",
                        "text": "Здравствуйте!",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert events == [
            {"kind": "manager", "client_id": "CLIENT_42", "text": "Здравствуйте!", "mid": "mid_human_1"}
        ]

    @pytest.mark.asyncio
    async def test_own_bot_echo_by_mid(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        InstagramChannel._sent_mids.add("mid_bot_1")
        settings.instagram_app_id = ""
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "BUSINESS_ACC"},
                    "recipient": {"id": "CLIENT_42"},
                    "message": {
                        "is_echo": True,
                        "mid": "mid_bot_1",
                        "text": "Ваш ответ",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert events == []

    @pytest.mark.asyncio
    async def test_own_bot_echo_by_app_id(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        settings.instagram_app_id = "APP_X"
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "BUSINESS_ACC"},
                    "recipient": {"id": "CLIENT_42"},
                    "message": {
                        "is_echo": True,
                        "mid": "mid_unfamiliar",
                        "app_id": "APP_X",
                        "text": "Ваш ответ",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert events == []
        settings.instagram_app_id = ""

    @pytest.mark.asyncio
    async def test_user_message_passthrough(self):
        from src.channels.instagram import InstagramChannel

        InstagramChannel._sent_mids.clear()
        channel = InstagramChannel()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "CLIENT_99"},
                    "message": {
                        "text": "Хочу тур",
                        "mid": "mid_user_1",
                    },
                }]
            }]
        }
        events = await channel.receive_message(payload)
        assert events == [
            {"kind": "user", "sender_id": "CLIENT_99", "text": "Хочу тур", "mid": "mid_user_1"}
        ]


class TestNonTextProcessing:
    """_process_non_text_safely — эскалация non-text сообщений."""

    @pytest.mark.asyncio
    @patch("src.services.telegram_notify.TelegramNotifier")
    @patch("src.main.instagram.send_message")
    @patch("src.main.instagram.get_username")
    @patch("src.main.get_session")
    @patch("src.main.save_session")
    @patch("src.main.is_manager_active")
    async def test_non_text_sends_ack_and_notifies(
        self,
        mock_is_active,
        mock_save,
        mock_get_session,
        mock_get_username,
        mock_send,
        mock_notifier_cls,
    ):
        from src.main import _process_non_text_safely

        mock_is_active.return_value = False
        mock_get_session.return_value = {"history": [], "escalation_count": 0}
        mock_get_username.return_value = "test_user"
        mock_send.return_value = None
        mock_notifier = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        await _process_non_text_safely(
            "CLIENT_42",
            "",
            {"types": ["image"], "summary": "вложение: image"},
        )

        # Клиент получил acknowledgement
        mock_send.assert_awaited_once()
        ack_text = mock_send.await_args[0][1]
        assert "передала вопрос менеджеру" in ack_text

        # Менеджер уведомлён
        mock_notifier.notify_manager.assert_awaited_once()

        # Эскалация сохранена
        saved_session = mock_save.await_args[0][1]
        assert saved_session["escalation_count"] == 1

    @pytest.mark.asyncio
    @patch("src.services.telegram_notify.TelegramNotifier")
    @patch("src.main.instagram.send_message")
    @patch("src.main.instagram.get_username")
    @patch("src.main.get_session")
    @patch("src.main.save_session")
    @patch("src.main.is_manager_active")
    async def test_non_text_limit_reached_skips_telegram(
        self,
        mock_is_active,
        mock_save,
        mock_get_session,
        mock_get_username,
        mock_send,
        mock_notifier_cls,
    ):
        from src.main import _process_non_text_safely

        mock_is_active.return_value = False
        mock_get_session.return_value = {"history": [], "escalation_count": 3}
        mock_get_username.return_value = "test_user"
        mock_send.return_value = None
        mock_notifier = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        await _process_non_text_safely(
            "CLIENT_42",
            "текст",
            {"types": ["image"], "summary": "вложение: image"},
        )

        # Telegram НЕ вызван
        mock_notifier.notify_manager.assert_not_awaited()

        # Клиент получил "запрос уже передан"
        ack_text = mock_send.await_args[0][1]
        assert "уже передан" in ack_text

    @pytest.mark.asyncio
    @patch("src.main.instagram.send_message")
    @patch("src.main.get_session")
    @patch("src.main.is_manager_active")
    async def test_non_text_manager_takeover_silent(
        self,
        mock_is_active,
        mock_get_session,
        mock_send,
    ):
        from src.main import _process_non_text_safely

        mock_is_active.return_value = True
        mock_get_session.return_value = {
            "history": [],
            "escalation_count": 0,
            "manager_last_at": "2026-06-26T12:00:00+00:00",
        }

        await _process_non_text_safely(
            "CLIENT_42",
            "",
            {"types": ["image"], "summary": "вложение: image"},
        )

        # Ничего не отправлено
        mock_send.assert_not_awaited()
