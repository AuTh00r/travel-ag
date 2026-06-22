from unittest.mock import MagicMock, patch

import pytest

from src.services.google_sheets import (
    GoogleSheetsService,
    _build_filters,
    _detect_budget_direction,
    _extract_months,
    _fuzzy_match,
    _match_score,
    _normalize,
    _parse_price,
)

# --- Helper tests ---


class TestNormalize:
    def test_lower_and_strip(self):
        assert _normalize("  Турция  ") == "турция"

    def test_multi_spaces(self):
        assert _normalize("Турция   Анталья") == "турция анталья"

    def test_empty(self):
        assert _normalize("") == ""


class TestFuzzyMatch:
    def test_exact_substring(self):
        assert _fuzzy_match("турция", "турция анталья")

    def test_reverse_substring(self):
        assert _fuzzy_match("турция анталья", "турция")

    def test_close_match(self):
        assert _fuzzy_match("турци", "турция")

    def test_no_match(self):
        assert not _fuzzy_match("египет", "турция")


class TestParsePrice:
    def test_dollar_suffix(self):
        assert _parse_price("1200$") == [1200]

    def test_range(self):
        assert _parse_price("1000-1500$") == [1000, 1500]

    def test_no_numbers(self):
        assert _parse_price("по запросу") == []

    def test_with_spaces(self):
        assert _parse_price("1 200 $") == [1200]


class TestDetectBudgetDirection:
    def test_max(self):
        assert _detect_budget_direction("до 2000$") == "max"
        assert _detect_budget_direction("не больше 1500") == "max"

    def test_min(self):
        assert _detect_budget_direction("от 1000$") == "min"
        assert _detect_budget_direction("не меньше 500") == "min"

    def test_exact(self):
        assert _detect_budget_direction("2000") == "exact"
        assert _detect_budget_direction("1200$") == "exact"


class TestExtractMonths:
    def test_full_month(self):
        months = _extract_months("хочу в августе")
        assert "август" in months or "авг" in months

    def test_short_month(self):
        assert "сен" in _extract_months("сентябрь")

    def test_no_month(self):
        assert _extract_months("хочу тур") == []


class TestBuildFilters:
    def test_all_params(self):
        filters = _build_filters("Турция", "пляж", "до 2000", "август")
        assert filters["destination"] == "турция"
        assert filters["tour_type"] == "пляж"
        assert filters["budget_values"] == [2000]
        assert filters["budget_direction"] == "max"
        assert "авг" in filters["date_months"]

    def test_empty_params(self):
        filters = _build_filters(None, None, None, None)
        assert filters == {}

    def test_budget_range(self):
        filters = _build_filters(None, None, "1000-2000", None)
        assert filters["budget_values"] == [1000, 2000]


class TestMatchScore:
    def _make_tour(self, **overrides):
        return {
            "Название": "Анталья All-Inclusive",
            "Направление": "Турция, Анталья",
            "Тип": "Пляжный, All-Inclusive",
            "Даты": "15.06-22.06.2026",
            "Цена": "1200$",
            "Длительность": "7 ночей",
            "Ключевые слова": "море, пляж, семья, отель",
            "Ссылка": "https://docs.google.com/...",
            "Доступно": "Да",
            **overrides,
        }

    def test_perfect_match(self):
        tour = self._make_tour()
        filters = _build_filters("Турция", "Пляжный", None, "июнь")
        score = _match_score(tour, filters)
        assert score > 0

    def test_destination_mismatch(self):
        tour = self._make_tour()
        filters = _build_filters("Египет", None, None, None)
        score = _match_score(tour, filters)
        assert score == 0.0

    def test_budget_within_max(self):
        tour = self._make_tour(Цена="1200$")
        filters = _build_filters(None, None, "до 2000", None)
        score = _match_score(tour, filters)
        assert score > 0

    def test_budget_exceeds_max(self):
        tour = self._make_tour(Цена="3000$")
        filters = _build_filters(None, None, "до 2000", None)
        score = _match_score(tour, filters)
        assert score < 1.0

    def test_no_filters(self):
        tour = self._make_tour()
        score = _match_score(tour, {})
        assert score == 1.0


# --- GoogleSheetsService tests ---


@pytest.fixture
def mock_sheets_service():
    with patch("src.services.google_sheets.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        yield mock_service


@pytest.mark.asyncio
async def test_search_tours_success(mock_sheets_service):
    mock_sheets_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            [
                "Название",
                "Направление",
                "Тип",
                "Даты",
                "Цена",
                "Длительность",
                "Ключевые слова",
                "Ссылка",
                "Доступно",
            ],
            [
                "Анталья All-Inclusive",
                "Турция, Анталья",
                "Пляжный",
                "15.06-22.06",
                "1200$",
                "7 ночей",
                "море, пляж",
                "link1",
                "Да",
            ],
            [
                "Париж тур",
                "Франция, Париж",
                "Экскурсионный",
                "01.07-08.07",
                "1500$",
                "7 ночей",
                "город, экскурсии",
                "link2",
                "Да",
            ],
        ]
    }

    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_tours_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            results = await svc.search_tours(destination="Турция")

    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_tours_empty(mock_sheets_service):
    mock_sheets_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            [
                "Название",
                "Направление",
                "Тип",
                "Даты",
                "Цена",
                "Длительность",
                "Ключевые слова",
                "Ссылка",
                "Доступно",
            ]
        ]
    }

    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_tours_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            results = await svc.search_tours(destination="Марс")

    assert results == []


@pytest.mark.asyncio
async def test_search_tours_filters_unavailable(mock_sheets_service):
    mock_sheets_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            [
                "Название",
                "Направление",
                "Тип",
                "Даты",
                "Цена",
                "Длительность",
                "Ключевые слова",
                "Ссылка",
                "Доступно",
            ],
            [
                "Анталья тур",
                "Турция, Анталья",
                "Пляжный",
                "15.06-22.06",
                "1200$",
                "7 ночей",
                "море",
                "link",
                "Нет",
            ],
        ]
    }

    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_tours_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            results = await svc.search_tours(destination="Турция")

    assert results == []


@pytest.mark.asyncio
async def test_create_request(mock_sheets_service):
    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_requests_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            await svc.create_request(
                name="Иван Петров",
                phone="+375291234567",
                email="ivan@mail.com",
                tour="Анталья All-Inclusive",
                destination="Турция",
                budget="2000$",
                travelers=2,
            )

    mock_sheets_service.spreadsheets().values().append.assert_called_once()


@pytest.mark.asyncio
async def test_create_request_uses_booking_request(mock_sheets_service):
    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_requests_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            await svc.create_request(
                name="Тест", phone="+375331111111", email="test@test.by"
            )

    call_args = mock_sheets_service.spreadsheets().values().append.call_args
    row = call_args[1]["body"]["values"][0]
    assert row[1] == "Тест"
    assert row[2] == "+375331111111"
    assert row[3] == "test@test.by"
    assert row[8] == "Новая"
    assert row[9] == "Instagram"


@pytest.mark.asyncio
async def test_update_request_status_success(mock_sheets_service):
    mock_sheets_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            [
                "Дата заявки",
                "Имя",
                "Телефон",
                "Email",
                "Направление",
                "Бюджет",
                "Кол-во человек",
                "Выбранный тур",
                "Статус",
                "Источник",
                "Тег",
            ],
            [
                "22.06.2026 14:30",
                "Иван Петров",
                "+375291234567",
                "ivan@mail.com",
                "Турция",
                "2000$",
                "2",
                "Анталья All-Inclusive",
                "Новая",
                "Instagram",
                "",
            ],
        ]
    }

    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_requests_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            result = await svc.update_request_status(
                name="Иван Петров",
                phone="+375291234567",
                new_status="В обработке",
            )

    assert result is True
    mock_sheets_service.spreadsheets().values().update.assert_called_once()


@pytest.mark.asyncio
async def test_update_request_status_not_found(mock_sheets_service):
    mock_sheets_service.spreadsheets().values().get().execute.return_value = {
        "values": [
            [
                "Дата заявки",
                "Имя",
                "Телефон",
                "Email",
                "Направление",
                "Бюджет",
                "Кол-во человек",
                "Выбранный тур",
                "Статус",
                "Источник",
                "Тег",
            ],
        ]
    }

    with patch.object(
        GoogleSheetsService, "_get_service", return_value=mock_sheets_service
    ):
        with patch("src.config.settings.google_requests_sheet_id", "test_id"):
            svc = GoogleSheetsService()
            result = await svc.update_request_status(
                name="Nobody",
                phone="+375000000000",
                new_status="Подтверждена",
            )

    assert result is False


@pytest.mark.asyncio
async def test_update_request_status_invalid():
    with patch("src.config.settings.google_requests_sheet_id", "test_id"):
        svc = GoogleSheetsService()
        with pytest.raises(Exception, match="Неверный статус"):
            await svc.update_request_status(
                name="Тест",
                phone="+375291234567",
                new_status="Неизвестный",
            )
