"""tour_search удалён — логика поиска в промпте LLM.

test_tour_search.py сохранён для тестов парсинга DOCX-туров."""

from datetime import date

import pytest

from src.services.tour_loader import (
    VISA_NOT_NEEDED,
    VISA_REQUIRED,
    VISA_SUPPORTED,
    _extract_tour_section,
    _normalize_visa,
    _parse_date_range,
    _plural_zaezd,
    _split_tours,
    _split_tours_by_headings,
)


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


def test_split_tours_single():
    paragraphs = [
        "Тур A",
        "Маршрут: A - B",
        "https://docs.google.com/document/d/1",
    ]
    result = _split_tours(paragraphs)
    assert len(result) == 1
    assert result[0] == paragraphs


def test_split_tours_multi():
    paragraphs = [
        "Тур A",
        "Маршрут: A - B",
        "https://docs.google.com/document/d/1",
        "Тур B",
        "Маршрут: C - D",
        "https://docs.google.com/document/d/2",
        "Тур C",
        "Маршрут: E - F",
        "https://docs.google.com/document/d/3",
    ]
    result = _split_tours(paragraphs)
    assert len(result) == 3
    assert result[0][0] == "Тур A"
    assert result[1][0] == "Тур B"
    assert result[2][0] == "Тур C"
    assert "https://docs.google.com/document/d/1" in result[0][-1]
    assert "https://docs.google.com/document/d/2" in result[1][-1]
    assert "https://docs.google.com/document/d/3" in result[2][-1]


def test_split_tours_no_url():
    paragraphs = ["Тур A", "Маршрут: A - B", "Описание"]
    result = _split_tours(paragraphs)
    assert len(result) == 1
    assert result[0] == paragraphs


def test_split_tours_trailing_text_after_last_url():
    paragraphs = [
        "Тур A",
        "https://docs.google.com/document/d/1",
        "Тур B",
        "https://docs.google.com/document/d/2",
        "Лишний текст без URL",
    ]
    result = _split_tours(paragraphs)
    assert len(result) == 3
    assert result[2] == ["Лишний текст без URL"]


def test_split_by_headings_preamble_goes_to_notes():
    """Прод-кейс: преамбула-заголовок без ссылки на бронирование —
    общая информация, а не фантомный тур."""
    items = [
        ("С 01.10.2026 цена поднимается.", True),
        ("Зимние каникулы в Париже", True),
        ("Виза: НЕ обязательно", False),
        ("Ссылка на бронирование - https://sundita.by/tur/paris/", False),
    ]
    tour_blocks, notes = _split_tours_by_headings(items)
    assert len(tour_blocks) == 1
    assert tour_blocks[0][0] == "Зимние каникулы в Париже"
    assert notes == ["С 01.10.2026 цена поднимается."]


def test_split_by_headings_multi():
    items = [
        ("Тур A", True),
        ("Маршрут: A - B", False),
        ("Ссылка на бронирование - https://sundita.by/a", False),
        ("Тур B", True),
        ("Маршрут: C - D", False),
        ("Ссылка на бронирование - https://sundita.by/b", False),
    ]
    tour_blocks, notes = _split_tours_by_headings(items)
    assert len(tour_blocks) == 2
    assert tour_blocks[0][0] == "Тур A"
    assert tour_blocks[1][0] == "Тур B"
    assert notes == []


def test_split_by_headings_tour_without_booking_url_goes_to_notes():
    """Тур без ссылки на бронирование не теряет текст — он попадает
    в общую информацию, а не молча склеивается с соседом."""
    items = [
        ("Тур A", True),
        ("Маршрут: A - B", False),
    ]
    tour_blocks, notes = _split_tours_by_headings(items)
    assert tour_blocks == []
    assert notes == ["Тур A", "Маршрут: A - B"]


# --- Визы -------------------------------------------------------------------
#
# В DOCX поле записано четырьмя способами. Клиенты путались: «не обязательно»
# читалось как «тур совсем без визы», хотя виза нужна и агентство лишь помогает
# её оформить.


class TestNormalizeVisa:
    def test_required_uppercase(self):
        assert _normalize_visa("НУЖНА") == VISA_REQUIRED

    def test_support_means_visa_is_still_required(self):
        """«не обязательно» ≠ «визы нет»: она нужна, оформляем мы."""
        result = _normalize_visa("не обязательно")
        assert result == VISA_SUPPORTED
        assert "НУЖНА" in result
        assert "поддержку" in result

    def test_not_needed_at_all(self):
        """Эльбрус — единственный случай, когда визы правда нет."""
        assert _normalize_visa("не нужна") == VISA_NOT_NEEDED

    def test_three_states_are_distinct(self):
        assert len({VISA_REQUIRED, VISA_SUPPORTED, VISA_NOT_NEEDED}) == 3

    def test_unknown_value_passed_through(self):
        """Незнакомую формулировку не выдумываем, отдаём как есть."""
        assert _normalize_visa("по договорённости") == "по договорённости"

    def test_visa_line_variants_from_real_docx(self):
        """Все четыре реальные записи из DOCX, включая en-dash."""
        paragraphs = [
            "Тур",
            "Виза - НУЖНА",
            "Ссылка на бронирование - https://sundita.by/a",
        ]
        assert VISA_REQUIRED in _extract_tour_section("Тур", paragraphs)

        for raw in ("Виза - не обязательно", "Виза – не обязательно"):
            section = _extract_tour_section("Тур", ["Тур", raw])
            assert VISA_SUPPORTED in section, raw
            # Формулировка «виза не нужна» для шенгена запрещена.
            assert "НЕ НУЖНА вообще" not in section

        assert VISA_NOT_NEEDED in _extract_tour_section("Тур", ["Тур", "Виза - не нужна"])


# --- Даты заездов -----------------------------------------------------------


class TestParseDateRange:
    def test_full_dates(self):
        parsed = _parse_date_range("19.08.2026 - 23.08.2026")
        assert parsed is not None
        start, text, note = parsed
        assert start == date(2026, 8, 19)
        assert text == "19.08.2026 - 23.08.2026"
        assert note == ""

    def test_year_only_at_end(self):
        """Эльбрус: «15.01 - 24.01.2027» — год есть только у конца."""
        parsed = _parse_date_range("15.01 - 24.01.2027")
        assert parsed is not None
        start, text, _ = parsed
        assert start == date(2027, 1, 15)
        assert text == "15.01.2027 - 24.01.2027"

    def test_new_year_crossover(self):
        """«28.12 - 05.01.2027» — заезд начинается в предыдущем году."""
        parsed = _parse_date_range("28.12 - 05.01.2027")
        assert parsed is not None
        start, _, _ = parsed
        assert start == date(2026, 12, 28)

    def test_captures_note(self):
        parsed = _parse_date_range("12.12.2026 - 21.12.2026 (мест нет)")
        assert parsed is not None
        assert parsed[2] == "мест нет"

    @pytest.mark.parametrize(
        "line",
        [
            "10 день: Завтрак в отеле. Выселение. Переезд в Будапешт.",
            "10 ночлегов в отелях",
            "10 завтраков во всех отелях, 3 обеда и 4 ужина",
            "Маршрут: Минск - Париж",
            "",
        ],
    )
    def test_ignores_program_text(self, line):
        """Куски программы не должны попадать в даты заездов."""
        assert _parse_date_range(line) is None

    def test_rejects_impossible_date(self):
        assert _parse_date_range("31.02.2027 - 05.03.2027") is None


class TestDateFiltering:
    """Фильтрация дат — в загрузчике, а не правилом в промпте.

    Сравнение десятка дат с сегодняшним числом модель делает ненадёжно, а
    «(мест нет)» игнорировала и предлагала распроданные заезды клиентам.
    """

    TODAY = date(2026, 9, 29)

    def _section(self, *dates: str) -> str:
        paragraphs = ["Тур", "Виза - НУЖНА", *dates]
        return _extract_tour_section("Тур", paragraphs, today=self.TODAY)

    def test_past_dates_dropped(self):
        section = self._section("Когда: 19.08.2026 - 23.08.2026", "03.11.2026 - 07.11.2026")
        assert "19.08.2026" not in section
        assert "03.11.2026 - 07.11.2026" in section

    def test_sold_out_dates_dropped(self):
        """Прод-баг: бот предлагал заезды с пометкой «мест нет»."""
        section = self._section(
            "Когда: 24.10.2026 - 02.11.2026 (мест нет)",
            "13.02.2027 - 22.02.2027",
        )
        assert "24.10.2026" not in section
        assert "мест нет" not in section
        assert "13.02.2027 - 22.02.2027" in section

    def test_few_seats_marker_kept(self):
        """«мало мест» — повод поторопиться, не скрываем."""
        section = self._section("Когда: 22.05.2027 - 31.05.2027 (мало мест)")
        assert "22.05.2027 - 31.05.2027 (мало мест)" in section

    def test_limited_to_three_nearest(self):
        """У «Французского поцелуя» 11 заездов — в ответ должно уйти 3."""
        section = self._section(
            "Когда: 13.02.2027 - 22.02.2027",
            "06.03.2027 - 15.03.2027",
            "17.04.2027 - 26.04.2027",
            "08.05.2027 - 17.05.2027",
            "12.06.2027 - 21.06.2027",
        )
        dates_line = next(
            line for line in section.split("\n") if line.startswith("Когда (")
        )
        assert dates_line.count(" - ") == 3
        assert "08.05.2027" not in dates_line
        assert "Есть ещё 2 заезда позже" in section

    def test_dates_sorted_ascending(self):
        section = self._section(
            "Когда: 11.12.2027 - 20.12.2027",
            "20.03.2027 - 29.03.2027",
            "25.09.2027 - 04.10.2027",
        )
        dates_line = next(
            line for line in section.split("\n") if line.startswith("Когда (")
        )
        assert dates_line.index("20.03.2027") < dates_line.index("25.09.2027")
        assert dates_line.index("25.09.2027") < dates_line.index("11.12.2027")

    def test_all_dates_unavailable_marks_tour_closed(self):
        section = self._section(
            "Когда: 26.07.2026 - 07.08.2026",
            "12.09.2026 - 24.09.2026",
        )
        assert "Свободных дат нет" in section
        assert "не предлагай" in section

    def test_program_days_not_treated_as_dates(self):
        """«10 день: ...» остаётся в тексте программы, а не в датах."""
        section = self._section(
            "Когда: 09.12.2026 - 13.12.2026",
            "10 день: Завтрак в отеле. Выселение.",
        )
        dates_line = next(
            line for line in section.split("\n") if line.startswith("Когда (")
        )
        assert "10 день" not in dates_line
        assert "10 день: Завтрак в отеле. Выселение." in section


class TestPluralZaezd:
    @pytest.mark.parametrize(
        "n,expected",
        [
            (1, "заезд"),
            (2, "заезда"),
            (4, "заезда"),
            (5, "заездов"),
            (11, "заездов"),
            (21, "заезд"),
            (22, "заезда"),
        ],
    )
    def test_plural(self, n, expected):
        assert _plural_zaezd(n) == expected
