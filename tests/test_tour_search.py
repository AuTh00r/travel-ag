from unittest.mock import AsyncMock, patch

import pytest

from src.ai.tour_search import search_tours
from src.exceptions import GoogleSheetsError


@pytest.mark.asyncio
async def test_search_tours_found():
    mock_sheets = AsyncMock()
    mock_sheets.search_tours.return_value = [
        {"Название": "Турция тур", "Направление": "Турция", "Цена": "1000$"}
    ]

    with patch("src.ai.tour_search.GoogleSheetsService", return_value=mock_sheets):
        result = await search_tours(
            {
                "tour_params": {"destination": "Турция", "budget": "1000"},
                "found_tours": [],
                "needs_escalation": False,
            }
        )

    assert len(result["found_tours"]) == 1
    assert result["found_tours"][0]["Название"] == "Турция тур"


@pytest.mark.asyncio
async def test_search_tours_empty():
    mock_sheets = AsyncMock()
    mock_sheets.search_tours.return_value = []

    with patch("src.ai.tour_search.GoogleSheetsService", return_value=mock_sheets):
        result = await search_tours(
            {
                "tour_params": {"destination": "Марс"},
                "found_tours": [],
                "needs_escalation": False,
            }
        )

    assert result["found_tours"] == []


@pytest.mark.asyncio
async def test_search_tours_error():
    mock_sheets = AsyncMock()
    mock_sheets.search_tours.side_effect = GoogleSheetsError("API error")

    with patch("src.ai.tour_search.GoogleSheetsService", return_value=mock_sheets):
        result = await search_tours(
            {
                "tour_params": {},
                "found_tours": [],
                "needs_escalation": False,
            }
        )

    assert result["found_tours"] == []
    assert result["needs_escalation"] is True
