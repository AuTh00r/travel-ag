from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


class TestManagerPauseGate:
    """process_with_ai — пауза при активном менеджере."""

    @pytest.mark.asyncio
    async def test_skip_llm_when_manager_active(self):
        from datetime import datetime, timezone

        from src.main import process_with_ai

        now_iso = datetime.now(timezone.utc).isoformat()
        with (
            patch("src.main.get_session") as mock_get,
            patch("src.main.save_session", new=AsyncMock()) as mock_save,
            patch("src.services.llm.get_llm") as mock_llm,
            patch("src.channels.instagram.InstagramChannel.send_message", new=AsyncMock()) as mock_send,
        ):
            mock_get.return_value = {
                "history": [],
                "client_id": "CLIENT_42",
                "escalation_count": 0,
                "manager_last_at": now_iso,
            }
            await process_with_ai("CLIENT_42", "хочу тур")

        mock_llm.assert_not_called()
        mock_send.assert_not_called()
        mock_save.assert_not_called()


class TestSplitReply:
    """_split_reply — разбивка длинных ответов."""

    def test_short_text_single_chunk(self):
        from src.main import _split_reply

        assert _split_reply("Привет!") == ["Привет!"]

    def test_long_text_splits_by_sentence(self):
        from src.main import _split_reply

        text = "Тур первый. " * 50  # ~650 chars
        chunks = _split_reply(text, max_len=300)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 300
        assert "Тур первый." in chunks[0]

    def test_no_sentence_boundary_splits_at_max(self):
        from src.main import _split_reply

        text = "а" * 500 + "б" * 500 + "в" * 500
        chunks = _split_reply(text, max_len=600)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 600

    def test_empty_text(self):
        from src.main import _split_reply

        assert _split_reply("") == [""]
        assert _split_reply("   ") == ["   "]

    def test_exact_boundary_no_split(self):
        from src.main import _split_reply

        text = "A" * 1000
        assert _split_reply(text, max_len=1000) == [text]

    def test_one_char_over_splits(self):
        from src.main import _split_reply

        text = "A" * 1001
        chunks = _split_reply(text, max_len=1000)
        assert len(chunks) >= 2


ADMIN_TOKEN = "test-admin-token-abc123"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture
def admin_token(monkeypatch):
    """Настроенный admin-токен на время теста."""
    from src.config import settings

    monkeypatch.setattr(settings, "admin_api_token", ADMIN_TOKEN)
    return ADMIN_TOKEN


@pytest.mark.asyncio
async def test_reset_takeover(admin_token):
    from datetime import datetime, timezone

    from src.db.sessions import _new_session, save_session
    from src.main import app

    client_id = "test_reset_client"
    session = _new_session(client_id)
    session["manager_last_at"] = datetime.now(timezone.utc).isoformat()
    await save_session(client_id, session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/admin/reset-takeover/{client_id}", headers=ADMIN_HEADERS
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reset"] is True

    from src.db.sessions import get_session

    updated = await get_session(client_id)
    assert updated["manager_last_at"] is None


@pytest.mark.asyncio
async def test_reset_takeover_already_active(admin_token):
    from src.db.sessions import _new_session, save_session
    from src.main import app

    client_id = "test_already_active"
    await save_session(client_id, _new_session(client_id))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/admin/reset-takeover/{client_id}", headers=ADMIN_HEADERS
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reset"] is False
    assert data["reason"] == "already_active"


class TestAdminAuth:
    """Роут доступен из интернета через Cloudflare Tunnel и пишет в сессию.

    Знание client_id за секрет не считается: это Instagram sender_id, он
    светится в Telegram-уведомлениях менеджерам и в логах.
    """

    PATH = "/api/admin/reset-takeover/auth_probe_client"

    async def _post(self, headers=None):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(self.PATH, headers=headers or {})

    @pytest.mark.asyncio
    async def test_rejects_without_header(self, admin_token):
        assert (await self._post()).status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_wrong_token(self, admin_token):
        resp = await self._post({"X-Admin-Token": "wrong-token"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_near_miss_token(self, admin_token):
        """Отличие в одном символе — тоже отказ."""
        resp = await self._post({"X-Admin-Token": ADMIN_TOKEN[:-1] + "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_empty_header(self, admin_token):
        assert (await self._post({"X-Admin-Token": ""})).status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_token_prefix(self, admin_token):
        """Префикс верного токена не должен проходить."""
        resp = await self._post({"X-Admin-Token": ADMIN_TOKEN[:8]})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unconfigured_token_closes_route(self, monkeypatch):
        """Пустой admin_api_token не должен означать «пускать всех»."""
        from src.config import settings

        monkeypatch.setattr(settings, "admin_api_token", "")
        assert (await self._post(ADMIN_HEADERS)).status_code == 404

    @pytest.mark.asyncio
    async def test_accepts_correct_token(self, admin_token):
        assert (await self._post(ADMIN_HEADERS)).status_code == 200

    def test_non_ascii_token_does_not_crash(self, admin_token):
        """compare_digest на str с не-ASCII бросает TypeError — ловим 404.

        Через HTTP такой заголовок не отправить (httpx блокирует не-ASCII),
        но хелпер обязан быть устойчив и при прямом вызове.
        """
        from fastapi import HTTPException

        from src.main import _require_admin_token

        for bad in ("секрет", "tok\udcff"):
            with pytest.raises(HTTPException) as exc:
                _require_admin_token(bad)
            assert exc.value.status_code == 404

    def test_does_not_leak_auth_state_via_status_code(self, admin_token):
        """Неверный токен и ненастроенный токен отдают одинаковый 404."""
        from fastapi import HTTPException

        from src.config import settings
        from src.main import _require_admin_token

        with pytest.raises(HTTPException) as wrong:
            _require_admin_token("nope")

        original = settings.admin_api_token
        try:
            settings.admin_api_token = ""
            with pytest.raises(HTTPException) as unconfigured:
                _require_admin_token(ADMIN_TOKEN)
        finally:
            settings.admin_api_token = original

        assert wrong.value.status_code == unconfigured.value.status_code == 404
