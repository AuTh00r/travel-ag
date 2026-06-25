from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.db.sessions import save_booking_request


@pytest.fixture(autouse=True)
def clean_db():
    from src.db.sessions import _get_connection

    conn = _get_connection()
    conn.execute("DELETE FROM requests")
    conn.commit()
    conn.close()
    yield
    conn = _get_connection()
    conn.execute("DELETE FROM requests")
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_get_requests_not_found():
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/requests/nonexistent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Заявки не найдены"


@pytest.mark.asyncio
async def test_get_requests_found():
    await save_booking_request(
        client_id="client_1",
        name="Иван",
        phone="+375291234567",
        email="ivan@mail.com",
        tour="Анталья",
    )

    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/requests/client_1")

    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == "client_1"
    assert len(data["requests"]) == 1
    assert data["requests"][0]["name"] == "Иван"
    assert data["requests"][0]["status"] == "Новая"


@pytest.mark.asyncio
async def test_update_status_success():
    await save_booking_request(
        client_id="client_2",
        name="Петр",
        phone="+375331111111",
        email="petr@mail.com",
    )

    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "src.main.GoogleSheetsService.update_request_status",
            new=AsyncMock(return_value=True),
        ):
            response = await client.patch(
                "/api/requests/client_2/status",
                json={"status": "Подтверждена"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Подтверждена"
    assert data["updated"] is True


@pytest.mark.asyncio
async def test_update_status_invalid():
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/api/requests/nonexistent/status",
            json={"status": "Неизвестный"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_status_not_found():
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/api/requests/nonexistent/status",
            json={"status": "Оплачена"},
        )

    assert response.status_code == 404


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
        call_args = mock_save.call_args
        assert call_args is not None
        saved_session = call_args[0][1]
        assert saved_session["history"][-1] == {"role": "user", "content": "хочу тур"}
