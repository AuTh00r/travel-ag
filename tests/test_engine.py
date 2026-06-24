from unittest.mock import AsyncMock, patch

import pytest

from src.main import _extract_booking, _extract_escalation, _strip_markers


# --- Marker parsing ---


class TestExtractBooking:
    def test_valid_booking(self):
        text = """Ответ клиенту...

===БРОНЬ===
Имя: Иван
Телефон: +375291234567
Email: ivan@mail.com
Тур: Анталья
===БРОНЬ==="""
        result = _extract_booking(text)
        assert result == {
            "name": "Иван",
            "phone": "+375291234567",
            "email": "ivan@mail.com",
            "tour": "Анталья",
        }

    def test_no_booking(self):
        assert _extract_booking("Просто ответ") is None

    def test_missing_required_fields(self):
        text = """===БРОНЬ===
Имя: Иван
===БРОНЬ==="""
        assert _extract_booking(text) is None


class TestExtractEscalation:
    def test_extract_escalation_with_context(self):
        text = "ответ\n\n===МЕНЕДЖЕР===\nПричина: просит менеджера\nКонтекст: ищет тур в Турцию\n===МЕНЕДЖЕР==="
        result = _extract_escalation(text)
        assert result == ("просит менеджера", "ищет тур в Турцию")

    def test_extract_escalation_without_context(self):
        text = "ответ\n\n===МЕНЕДЖЕР===\nПричина: просит менеджера\n===МЕНЕДЖЕР==="
        result = _extract_escalation(text)
        assert result == ("просит менеджера", "просит менеджера")

    def test_extract_escalation_no_marker(self):
        assert _extract_escalation("обычный ответ") is None


class TestStripMarkers:
    def test_strips_both_markers(self):
        text = """Привет! Вот тур.

===БРОНЬ===
Имя: Иван
===БРОНЬ===

Хорошего дня!

===МЕНЕДЖЕР===
Причина: тест
===МЕНЕДЖЕР==="""
        result = _strip_markers(text)
        assert "===БРОНЬ===" not in result
        assert "===МЕНЕДЖЕР===" not in result
        assert "Привет! Вот тур." in result
        assert "Хорошего дня!" in result


# --- Prompt building ---


def test_build_full_prompt_includes_tours():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="=== ТУР: Турция ===\nПляж",
        faq_context="",
        history=[],
        message="Хочу тур",
    )
    assert len(messages) == 2  # system + user
    assert "Турция" in messages[0].content
    assert messages[1].content == "Хочу тур"


def test_build_full_prompt_includes_history():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="",
        history=[
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте!"},
        ],
        message="Хочу тур",
    )
    assert len(messages) == 4  # system + user + assistant + user
    assert messages[1].content == "Привет"
    assert messages[2].content == "Здравствуйте!"


def test_build_full_prompt_includes_faq():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="Виза в Турцию делается за 5 дней",
        history=[],
        message="Нужна виза?",
    )
    assert "Виза в Турцию" in messages[0].content


# --- Integration smoke test ---


@pytest.mark.asyncio
async def test_process_with_ai_smoke():
    """Проверяет, что process_with_ai не падает при вызове с замоканным LLM."""
    fake_response = AsyncMock()
    fake_response.content = "Здравствуйте! Чем могу помочь?"

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=fake_response)

    patches = [
        patch("src.services.llm.get_llm", return_value=fake_llm),
        patch("src.services.tour_loader.get_tours_text", return_value=""),
        patch("src.db.faq_db.search_faq", return_value=[]),
        patch("src.main.save_session"),
        patch("src.main.instagram.send_message"),
        patch("src.main.instagram.get_username", return_value=None),
    ]
    for p in patches:
        p.start()

    try:
        await process_with("test_user", "Привет")
    except Exception as e:
        pytest.fail(f"process_with_ai raised: {e}")
    finally:
        for p in patches:
            p.stop()


async def process_with(sender_id: str, text: str) -> None:
    """Helper — вызывает process_with_ai."""
    from src.main import process_with_ai

    await process_with_ai(sender_id, text)


@pytest.mark.asyncio
async def test_process_with_ai_booking_flow():
    """Проверяет, что process_with_ai создаёт заявку при ===БРОНЬ=== маркере."""
    fake_response = AsyncMock()
    fake_response.content = """Отличный выбор! Бронь подтверждаю.

===БРОНЬ===
Имя: Иван
Телефон: +375291234567
Email: ivan@mail.com
Тур: Анталья
===БРОНЬ==="""

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=fake_response)

    mock_sheets = AsyncMock()
    sheets_create_request = AsyncMock()
    mock_sheets.create_request = sheets_create_request

    patches = [
        patch("src.services.llm.get_llm", return_value=fake_llm),
        patch("src.services.tour_loader.get_tours_text", return_value=""),
        patch("src.db.faq_db.search_faq", return_value=[]),
        patch("src.main.save_session"),
        patch("src.main.instagram.send_message"),
        patch("src.main.instagram.get_username", return_value=None),
        patch("src.main.GoogleSheetsService", return_value=mock_sheets),
        patch("src.main.save_booking_request"),
    ]
    for p in patches:
        p.start()

    try:
        await process_with("test_user_2", "Да, записывайте")
        sheets_create_request.assert_awaited_once_with(
            name="Иван",
            phone="+375291234567",
            email="ivan@mail.com",
            tour="Анталья",
        )
    finally:
        for p in patches:
            p.stop()
