"""tour_search удалён — логика поиска в промпте LLM.

test_tour_search.py сохранён как заглушка для совместимости
с тестовым раннером; тесты парсинга маркеров в test_engine.py."""

from src.services.tour_loader import _extract_tour_section


def test_extract_tour_section_puts_url_first():
    paragraphs = [
        "Название тура",
        "Маршрут: Минск - Париж",
        "Даты: 10.07.2026 - 20.07.2026",
        "Стоимость: 500 €",
        "Тип отдыха: Экскурсионный",
        "Виза: НУЖНА",
        "Подробное описание тура с разными деталями",
        "ПОДРОБНАЯ ИНФОРМАЦИЯ И БРОНИРОВАНИЕ НА САЙТЕ",
        "https://docs.google.com/document/d/abc123",
    ]
    result = _extract_tour_section("Тестовый_тур", paragraphs)
    lines = [line.strip() for line in result.split("\n")]

    assert lines[0] == "=== ТУР: Тестовый_тур ==="
    assert lines[1] == "Ссылка на тур: https://docs.google.com/document/d/abc123"
    assert "Маршрут:" in lines[2]
    assert "Виза:" in lines[6]
    assert "Подробное описание" in "\n".join(lines)
    assert "ПОДРОБНАЯ ИНФОРМАЦИЯ" not in result


def test_extract_tour_section_no_url():
    paragraphs = ["Название", "Маршрут: A - B", "Виза: НУЖНА", "Описание"]
    result = _extract_tour_section("Без_ссылки", paragraphs)
    assert "Ссылка на тур" not in result
    assert "=== ТУР: Без_ссылки ===" in result


def test_extract_tour_section_key_fields_after_url():
    paragraphs = [
        "Любой текст",
        "Стоимость: 999 €",
        "Что включено",
        "https://docs.google.com/document/d/x1y2z3",
    ]
    result = _extract_tour_section("С_полями", paragraphs)
    lines = [line.strip() for line in result.split("\n") if line.strip()]
    url_idx = next(i for i, line in enumerate(lines) if "Ссылка на тур" in line)
    cost_idx = next(i for i, line in enumerate(lines) if line.startswith("Стоимость:"))
    assert cost_idx > url_idx
