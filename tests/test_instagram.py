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
    def test_no_mid_still_processed(self, mock_process):
        """Сообщение без mid обрабатывается (нет возможности дедупить)."""
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
        mock_process.assert_awaited_once_with("12345", "Тест без mid")

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

        settings.instagram_access_token = "test_token"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        channel = InstagramChannel()
        await channel.send_message("12345", "Hello")

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
