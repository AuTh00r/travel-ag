import pytest

from src.db.sessions import (
    _get_connection,
    get_requests_by_client,
    save_booking_request,
    update_request_status,
)


@pytest.fixture(autouse=True)
def clean_db():
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
async def test_save_and_get_requests():
    await save_booking_request(
        client_id="client_1",
        name="Иван",
        phone="+375291234567",
        email="ivan@mail.com",
        tour="Анталья All-Inclusive",
        destination="Турция",
        budget="2000$",
        travelers=2,
    )

    requests = await get_requests_by_client("client_1")
    assert len(requests) == 1
    assert requests[0]["name"] == "Иван"
    assert requests[0]["phone"] == "+375291234567"
    assert requests[0]["status"] == "Новая"


@pytest.mark.asyncio
async def test_update_request_status():
    await save_booking_request(
        client_id="client_2",
        name="Петр",
        phone="+375331111111",
        email="petr@mail.com",
    )

    result = await update_request_status("client_2", "В обработке")
    assert result is True

    requests = await get_requests_by_client("client_2")
    assert requests[0]["status"] == "В обработке"


@pytest.mark.asyncio
async def test_update_request_status_invalid():
    with pytest.raises(ValueError, match="Неверный статус"):
        await update_request_status("client_x", "Неизвестный статус")


@pytest.mark.asyncio
async def test_update_request_status_not_found():
    result = await update_request_status("nonexistent", "Подтверждена")
    assert result is False


@pytest.mark.asyncio
async def test_get_requests_empty():
    requests = await get_requests_by_client("no_requests")
    assert requests == []


@pytest.mark.asyncio
async def test_full_status_flow():
    statuses = ["Новая", "В обработке", "Подтверждена", "Оплачена"]
    await save_booking_request(
        client_id="flow_test",
        name="Анна",
        phone="+375441234567",
        email="anna@mail.com",
    )

    for status in statuses[1:]:
        result = await update_request_status("flow_test", status)
        assert result is True
        requests = await get_requests_by_client("flow_test")
        assert requests[0]["status"] == status
