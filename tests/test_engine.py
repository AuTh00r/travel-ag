from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.ai.engine import build_graph


class FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


def _make_fake_llm():
    class FakeLLM:
        async def ainvoke(self, messages):
            text = messages[0].content if isinstance(messages, list) else str(messages)
            if "Ты — ИИ-туристический агент" in text:
                return FakeLLMResponse(
                    '{"action": "respond", "reply": "Здравствуйте! Чем могу помочь? 😊", "tour_params": {}, "selected_tour": null}'
                )
            if "Извлеки имя" in text or "извлеки имя" in text:
                return FakeLLMResponse('{"name": "Иван"}')
            if "Представь клиенту найденные туры" in text:
                return FakeLLMResponse(
                    "Вот что я нашёл для вас:\n\n1. Анталья All-Inclusive — Турция — 1200$\n\nНапишите номер, если заинтересовало!"
                )
            return FakeLLMResponse("👋 Здравствуйте! Чем могу помочь?")

    return FakeLLM()


@pytest.fixture(autouse=True)
def mock_all_services():
    fake_llm = _make_fake_llm()
    patches = [
        patch("src.ai.nodes.get_llm", return_value=fake_llm),
        patch("src.ai.nodes.get_llm_json", return_value=fake_llm),
    ]
    for p in patches:
        p.start()

    mock_sheets = AsyncMock()
    mock_sheets.search_tours = AsyncMock(return_value=[])
    mock_sheets.create_request = AsyncMock()
    sheets_patch = patch(
        "src.ai.tour_search.GoogleSheetsService", return_value=mock_sheets
    )
    sheets_patch.start()

    mock_save_req = AsyncMock()
    req_patch = patch("src.ai.nodes.save_booking_request", mock_save_req)
    req_patch.start()

    mock_telegram = AsyncMock()
    telegram_patch = patch(
        "src.ai.nodes.TelegramNotifier.notify_manager", mock_telegram
    )
    telegram_patch.start()

    yield fake_llm

    for p in patches:
        p.stop()
    sheets_patch.stop()
    req_patch.stop()
    telegram_patch.stop()


def _make_session(**overrides):
    base = {
        "messages": [],
        "client_id": "test_123",
        "client_name": None,
        "client_phone": None,
        "client_email": None,
        "request_type": None,
        "tour_params": {},
        "found_tours": [],
        "selected_tour": None,
        "faq_answer": None,
        "needs_escalation": False,
        "escalation_reason": None,
        "current_step": "converse",
        "awaiting_field": None,
        "conversation_history": [],
        "next_action": None,
    }
    base.update(overrides)
    return base


def test_graph_builds():
    graph = build_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_greeting_flow(mock_all_services):
    """Первое сообщение → converse → respond (END)."""
    graph = build_graph()

    session = _make_session(messages=[HumanMessage(content="Привет")])

    result = await graph.ainvoke(session)
    assert result is not None
    assert "messages" in result
    assert len(result["messages"]) > 0


@pytest.mark.asyncio
async def test_returning_user_skips_greeting(mock_all_services):
    """Повторное сообщение → converse без лишних шагов."""
    graph = build_graph()

    session = _make_session(messages=[HumanMessage(content="Хочу тур в Турцию")])

    result = await graph.ainvoke(session)
    assert result is not None
    assert len(result["messages"]) > 0


@pytest.mark.asyncio
async def test_state_schema():
    from src.ai.states import DialogState

    state: DialogState = _make_session()
    assert state["client_id"] == "test_123"
    assert state["current_step"] == "converse"


@pytest.mark.asyncio
async def test_validate_phone():
    from src.ai.nodes import validate_phone

    assert validate_phone("+375291234567")
    assert validate_phone("+375 29 123 45 67")
    assert validate_phone("+375-29-123-45-67")
    assert not validate_phone("12345")
    assert not validate_phone("+79123456789")


@pytest.mark.asyncio
async def test_validate_email():
    from src.ai.nodes import validate_email

    assert validate_email("test@mail.com")
    assert validate_email("ivan@tut.by")
    assert not validate_email("test")
    assert not validate_email("test@")


# --- Converse node tests ---


@pytest.mark.asyncio
async def test_converse_responds_to_greeting(mock_all_services):
    """Приветствие → action=respond → END."""
    from src.ai.nodes import converse

    state = _make_session(messages=[HumanMessage(content="Привет! Как дела?")])

    result = await converse(state)
    assert result["next_action"] == "respond"
    assert "reply" not in result  # reply is in messages
    assert len(result["messages"]) == 1


@pytest.mark.asyncio
async def test_converse_handles_search_intent(mock_all_services):
    """Запрос поиска тура → action=search."""
    from src.ai.nodes import converse

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse(
        '{"action": "search", "reply": "Ищу туры в Турцию! 🌴", "tour_params": {"destination": "Турция", "dates": "август"}, "selected_tour": null}'
    ))

    state = _make_session(messages=[HumanMessage(content="Хочу тур в Турцию на август")])

    with patch("src.ai.nodes.get_llm_json", return_value=mock_llm):
        result = await converse(state)
    assert result["next_action"] == "search"
    assert result.get("tour_params", {}).get("destination") == "Турция"


@pytest.mark.asyncio
async def test_converse_extracts_tour_params(mock_all_services):
    """При search action извлекаются параметры тура."""
    from src.ai.nodes import converse

    state = _make_session(messages=[HumanMessage(content="Хочу тур в Турцию на август за 2000")])

    result = await converse(state)
    if result["next_action"] == "search":
        params = result.get("tour_params", state.get("tour_params", {}))
        assert isinstance(params, dict)


# --- Booking flow tests ---


def _make_booking_state(**overrides):
    base = {
        "messages": [],
        "client_id": "book_test",
        "client_name": None,
        "client_phone": None,
        "client_email": None,
        "request_type": "booking",
        "tour_params": {"destination": "Турция", "budget": "2000", "travelers": 2},
        "found_tours": [],
        "selected_tour": "Анталья All-Inclusive",
        "faq_answer": None,
        "needs_escalation": False,
        "escalation_reason": None,
        "awaiting_field": None,
        "conversation_history": [],
        "next_action": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_book_ask_name():
    from src.ai.nodes import book

    state = _make_booking_state(
        messages=[HumanMessage(content="хочу забронировать")],
    )
    result = await book(state)
    assert result["current_step"] == "AWAIT_NAME"
    assert len(result["messages"]) == 1
    assert (
        "имя" in result["messages"][0].content.lower()
        or "зовут" in result["messages"][0].content.lower()
    )


@pytest.mark.asyncio
async def test_book_await_name():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="AWAIT_NAME",
        messages=[HumanMessage(content="Иван")],
    )
    result = await book(state)
    assert result["current_step"] == "AWAIT_PHONE"
    assert result["client_name"] == "Иван"


@pytest.mark.asyncio
async def test_book_await_name_llm_returns_none():
    from src.ai.nodes import book

    with patch("src.ai.nodes.get_llm_json") as mock_fn:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=FakeLLMResponse('{"name": null}'))
        mock_fn.return_value = mock_llm
        state = _make_booking_state(
            current_step="AWAIT_NAME",
            messages=[HumanMessage(content="A")],
        )
        result = await book(state)
    assert result["current_step"] != "AWAIT_PHONE"
    assert "client_name" not in result or result["client_name"] is None


@pytest.mark.asyncio
async def test_book_await_phone():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="AWAIT_PHONE",
        client_name="Иван",
        messages=[HumanMessage(content="+375291234567")],
    )
    result = await book(state)
    assert result["current_step"] == "AWAIT_EMAIL"
    assert result["client_phone"] == "+375291234567"


@pytest.mark.asyncio
async def test_book_await_phone_invalid():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="AWAIT_PHONE",
        messages=[HumanMessage(content="12345")],
    )
    result = await book(state)
    assert result["current_step"] != "AWAIT_EMAIL"
    assert "client_phone" not in result or result["client_phone"] is None


@pytest.mark.asyncio
async def test_book_await_email():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="AWAIT_EMAIL",
        client_name="Иван",
        client_phone="+375291234567",
        messages=[HumanMessage(content="ivan@mail.com")],
    )
    result = await book(state)
    assert result["current_step"] == "CONFIRM"
    assert result["client_email"] == "ivan@mail.com"


@pytest.mark.asyncio
async def test_book_await_email_invalid():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="AWAIT_EMAIL",
        messages=[HumanMessage(content="notanemail")],
    )
    result = await book(state)
    assert result["current_step"] != "CONFIRM"
    assert "client_email" not in result or result["client_email"] is None


@pytest.mark.asyncio
async def test_book_confirm_yes():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="CONFIRM",
        client_name="Иван",
        client_phone="+375291234567",
        client_email="ivan@mail.com",
        messages=[HumanMessage(content="да, всё верно")],
    )
    with patch("src.ai.nodes.save_booking_request", new=AsyncMock()):
        with patch("src.ai.nodes.GoogleSheetsService") as mock_sheets_cls:
            mock_sheets = AsyncMock()
            mock_sheets_cls.return_value = mock_sheets
            mock_sheets.create_request = AsyncMock()
            with patch("src.ai.nodes.settings.booking_form_url", ""):
                result = await book(state)

    assert result["current_step"] == "COMPLETED"
    assert "заявка создана" in result["messages"][0].content.lower()


@pytest.mark.asyncio
async def test_book_confirm_yes_with_booking_link():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="CONFIRM",
        client_name="Иван",
        client_phone="+375291234567",
        client_email="ivan@mail.com",
        messages=[HumanMessage(content="да, всё верно")],
    )
    with patch("src.ai.nodes.save_booking_request", new=AsyncMock()):
        with patch("src.ai.nodes.GoogleSheetsService") as mock_sheets_cls:
            mock_sheets = AsyncMock()
            mock_sheets_cls.return_value = mock_sheets
            mock_sheets.create_request = AsyncMock()
            with patch(
                "src.ai.nodes.settings.booking_form_url", "https://book.example.com"
            ):
                result = await book(state)

    assert result["current_step"] == "COMPLETED"
    content = result["messages"][0].content
    assert "забронировать онлайн" in content
    assert "https://book.example.com" in content


@pytest.mark.asyncio
async def test_book_confirm_no():
    from src.ai.nodes import book

    state = _make_booking_state(
        current_step="CONFIRM",
        client_name="Иван",
        client_phone="+375291234567",
        client_email="ivan@mail.com",
        messages=[HumanMessage(content="нет, неверно")],
    )
    result = await book(state)
    assert result["current_step"] == "ASK_NAME"


@pytest.mark.asyncio
async def test_book_full_flow():
    from src.ai.nodes import book

    steps = [
        ({"messages": [HumanMessage(content="хочу тур")]}, "ASK_NAME", "AWAIT_NAME"),
        (
            {"current_step": "AWAIT_NAME", "messages": [HumanMessage(content="Иван")]},
            "AWAIT_NAME",
            "AWAIT_PHONE",
        ),
        (
            {
                "current_step": "AWAIT_PHONE",
                "client_name": "Иван",
                "messages": [HumanMessage(content="+375291234567")],
            },
            "AWAIT_PHONE",
            "AWAIT_EMAIL",
        ),
        (
            {
                "current_step": "AWAIT_EMAIL",
                "client_name": "Иван",
                "client_phone": "+375291234567",
                "messages": [HumanMessage(content="ivan@mail.com")],
            },
            "AWAIT_EMAIL",
            "CONFIRM",
        ),
    ]

    for idx, (overrides, step_name, next_step) in enumerate(steps):
        state = _make_booking_state(**overrides)
        result = await book(state)
        assert (
            result["current_step"] == next_step
        ), f"Step {idx} ({step_name}): expected {next_step}, got {result['current_step']}"


@pytest.mark.asyncio
async def test_graph_routes_mid_booking_to_book():
    graph = build_graph()

    session = _make_session(
        messages=[HumanMessage(content="+375291234567")],
        client_name="Иван",
        client_phone=None,
        client_email=None,
        current_step="AWAIT_PHONE",
    )

    result = await graph.ainvoke(session)
    assert result.get("client_phone") == "+375291234567"
    assert result.get("current_step") == "AWAIT_EMAIL"
