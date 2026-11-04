import os
import re
from datetime import date as date_type

from docx import Document
from structlog import get_logger

from src.config import settings

logger = get_logger()

_tours_text: str = ""
_tours_folder: str = "tours"

_URL_RE = re.compile(r"https?://docs\.google\.com\S+")
_BOOKING_LABEL = r"(?:ссылка\s+на\s+)?(?:бронирование|бронь)(?:\s+на\s+сайте)?"
_SITE_LABEL = r"(?:ссылка(?:\s+на\s+(?:тур(?:\s+на\s+сайте)?|сайт(?:\s+тура)?))?|тур\s+на\s+сайте)"
# Docs/Drive URLs identify the source programme, never its booking page.
_BOOKING_ADDRESS = r"\s*[-–—:]?\s*(https?://(?!(?:www\.)?(?:docs|drive)\.google\.com(?=[:/?#\s]|$))[^\s<>\"']+)"
_EXPLICIT_BOOKING_URL_RE = re.compile(r"(?<!\w)" + _BOOKING_LABEL + _BOOKING_ADDRESS, re.IGNORECASE)
_BOOKING_URL_RE = re.compile(r"(?<!\w)(?:" + _BOOKING_LABEL + "|" + _SITE_LABEL + ")" + _BOOKING_ADDRESS, re.IGNORECASE)


def _booking_url_match(text: str):
    """An explicitly labelled booking link wins over a generic site link."""
    return _EXPLICIT_BOOKING_URL_RE.search(text) or _BOOKING_URL_RE.search(text)
_KEY_FIELDS = ("Маршрут:", "Даты:", "Стоимость:", "Тип отдыха:", "Виза:", "Куда:", "Когда:", "Сколько стоит:")

# --- Визы -------------------------------------------------------------------
#
# В DOCX поле записано четырьмя способами: «Виза - НУЖНА», «Виза - не
# обязательно», «Виза – не обязательно» (en-dash) и «Виза - не нужна»
# (Эльбрус). Клиенты путались: «не обязательно» читалось как «тур совсем без
# визы», хотя виза нужна и агентство лишь помогает её оформить. Приводим к трём
# однозначным состояниям, чтобы у модели не было места для трактовок.
_VISA_LINE_RE = re.compile(r"^Виза\s*[-–—:]\s*(.+?)\s*$", re.IGNORECASE)

VISA_REQUIRED = "НУЖНА — шенгенская виза, оформляется заранее самостоятельно"
VISA_SUPPORTED = "НУЖНА, но мы оказываем визовую поддержку — помогаем оформить"
VISA_NOT_NEEDED = "НЕ НУЖНА вообще — виза для этой поездки не требуется"


def _normalize_visa(value: str) -> str:
    """Свести запись о визе к одному из трёх состояний."""
    v = value.strip().lower()
    # «не нужна» / «не требуется» — виза не нужна в принципе (Эльбрус, Россия).
    if "не нужна" in v or "не требуется" in v or "без визы" in v:
        return VISA_NOT_NEEDED
    # «не обязательно» — виза всё-таки нужна, но оформляем мы.
    if "не обязательно" in v or "поддержк" in v:
        return VISA_SUPPORTED
    if "нужна" in v or "требуется" in v:
        return VISA_REQUIRED
    # Незнакомая формулировка — отдаём как есть, не выдумываем.
    return value.strip()


# --- Даты заездов -----------------------------------------------------------
#
# Даты лежат россыпью: первая в строке «Когда: ...», остальные отдельными
# строками ниже. Регулярки проверяют всю запись (диапазон или дату с годом),
# иначе под них попадают куски программы вида «10 день: ...» и
# «10 ночлегов в отелях».
_DATE_RANGE_RE = re.compile(
    r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*[-–—]\s*"
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*"
    r"(?:\(\s*([^)]*?)\s*\))?\s*$"
)
_DATE_SINGLE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:\(\s*([^)]*?)\s*\))?\s*$")
_DATE_LABEL_RE = re.compile(
    r"^(?:дат[аы]\s+выезда|когда|даты)\b\s*(?:[:\-–—]\s*|(?=\d)|$)", re.IGNORECASE
)
_DATE_RECORD_RE = re.compile(r"^\d{1,2}\s*[./][\d\s./\-–—‐‑−;,]*(?:\([^)]*\))?\s*$")
_TEXT_DATE_RE = re.compile(r"^\d{1,2}\s+[а-яё]+\s+\d{4}(?:\s*\([^)]*\))?$", re.IGNORECASE)
_DATES_UNKNOWN = (
    "Даты требуют уточнения: часть записей отсутствует или не распознана. "
    "Это не означает отсутствие тура или свободных мест."
)

# Пометки, при которых дату нельзя предлагать клиенту.
_SOLD_OUT_MARKERS = ("мест нет", "нет мест", "продан", "закрыт")


def _parse_date_range(line: str) -> tuple[date_type, str, str] | None:
    """Разобрать диапазон или одиночную дату с явным годом.

    Возвращает (дата начала, текст без пометки, пометка в скобках) или None,
    если строка не является корректной записью даты.
    """
    line = re.sub(r"\s*\.\s*", ".", line.strip()).translate(str.maketrans("‐‑−", "---"))
    single = _DATE_SINGLE_RE.fullmatch(line)
    if single:
        day, month, year, note = single.groups()
        try:
            start = date_type(int(year), int(month), int(day))
        except ValueError:
            return None
        return start, start.strftime("%d.%m.%Y"), (note or "").strip()
    m = _DATE_RANGE_RE.match(line)
    if not m:
        return None
    d1, m1, y1, d2, m2, y2, note = m.groups()
    end_year = int(y2)
    if y1:
        start_year = int(y1)
    else:
        # «15.01 - 24.01.2027»: год только у конца. Если начало месяцем позже
        # конца, заезд переходит через новый год («28.12 - 05.01.2027»).
        start_year = end_year - 1 if int(m1) > int(m2) else end_year
    try:
        start = date_type(start_year, int(m1), int(d1))
        end = date_type(end_year, int(m2), int(d2))
    except ValueError:
        return None
    if end < start:
        return None
    start_text = f"{int(d1):02d}.{int(m1):02d}.{start_year} - {int(d2):02d}.{int(m2):02d}.{end_year}"
    return start, start_text, (note or "").strip()


def _is_sold_out(note: str) -> bool:
    low = note.lower()
    return any(marker in low for marker in _SOLD_OUT_MARKERS)


def _plural_zaezd(n: int) -> str:
    """«1 заезд», «2 заезда», «5 заездов» — текст уходит клиенту как есть."""
    if n % 10 == 1 and n % 100 != 11:
        return "заезд"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "заезда"
    return "заездов"


def _extract_tour_section(
    filename: str,
    paragraphs: list[str],
    today: date_type | None = None,
) -> str:
    today = today or date_type.today()
    text = "\n".join(paragraphs)

    url_match = _URL_RE.search(text)
    tour_url = url_match.group(0) if url_match else ""
    if tour_url:
        text = _URL_RE.sub("", text).strip()

    booking_url_match = _booking_url_match(text)
    booking_url = booking_url_match.group(1) if booking_url_match else ""
    if booking_url:
        text = _BOOKING_URL_RE.sub("", text).strip()

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("ПОДРОБНАЯ ИНФОРМАЦИЯ И БРОНИРОВАНИЕ НА САЙТЕ", "").strip()

    key_lines: list[str] = []
    other_lines: list[str] = []
    visa_line = ""
    # (дата начала, текст) — только доступные заезды: будущие и со свободными
    # местами. Фильтруем здесь, а не правилом в промпте: сравнение десятка дат
    # с сегодняшним числом модель делает ненадёжно, а «(мест нет)» она вообще
    # игнорировала и предлагала такие заезды клиентам.
    available: list[tuple[date_type, str]] = []
    dropped_past = 0
    dropped_sold_out = 0
    unknown_dates = False
    date_block = False
    pending_heading = False
    date_section_ended = False

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        visa_match = _VISA_LINE_RE.match(line)
        if visa_match:
            unknown_dates |= pending_heading
            pending_heading = False
            date_section_ended |= date_block
            date_block = False
            visa_line = f"Виза: {_normalize_visa(visa_match.group(1))}"
            continue

        label = _DATE_LABEL_RE.match(line)
        candidate = line[label.end():].strip() if label else line
        if label:
            unknown_dates |= pending_heading
            pending_heading = False
            date_block = True
            date_section_ended = False
            if not candidate:
                pending_heading = True
                continue
        if not label and (date_section_ended or re.match(r"^программа\b", line, re.IGNORECASE)):
            unknown_dates |= pending_heading
            pending_heading = False
            date_block = False
            date_section_ended = True
            other_lines.append(line)
            continue
        parsed = _parse_date_range(candidate)
        # New single-day support is limited to the departure field/block.
        if parsed and " - " not in parsed[1] and not (label or date_block):
            other_lines.append(line)
            continue
        if parsed:
            pending_heading = False
            start, date_text, note = parsed
            if _is_sold_out(note):
                dropped_sold_out += 1
            elif start < today:
                dropped_past += 1
            else:
                suffix = f" ({note})" if note else ""
                available.append((start, date_text + suffix))
            continue

        if label or _DATE_RECORD_RE.fullmatch(candidate) or (date_block and _TEXT_DATE_RE.fullmatch(candidate)):
            unknown_dates = True
            pending_heading = False
            continue
        unknown_dates |= pending_heading
        pending_heading = False
        date_section_ended |= date_block
        date_block = False

        if any(line.startswith(f) for f in _KEY_FIELDS):
            key_lines.append(line)
        else:
            other_lines.append(line)

    unknown_dates |= pending_heading
    available.sort(key=lambda item: item[0])
    limit = settings.max_tour_dates
    shown = available[:limit] if limit > 0 else available

    parts = [f"=== ТУР: {filename} ==="]
    if tour_url:
        parts.append(f"Ссылка на тур: {tour_url}")
    if booking_url:
        parts.append(f"Ссылка на бронирование: {booking_url}")
    parts.extend(key_lines)
    if visa_line:
        parts.append(visa_line)

    if shown:
        parts.append("Когда (ближайшие свободные даты): " + "; ".join(t for _, t in shown))
        hidden = len(available) - len(shown)
        if hidden:
            parts.append(
                f"Есть ещё {hidden} {_plural_zaezd(hidden)} позже — "
                "подробности по ссылке на тур или у менеджера."
            )
    elif not unknown_dates and (dropped_past or dropped_sold_out):
        parts.append(
            "Свободных дат нет: все заезды прошли или распроданы. "
            "Тур клиентам не предлагай — передай запрос менеджеру."
        )

    if unknown_dates or not (available or dropped_past or dropped_sold_out):
        parts.append(_DATES_UNKNOWN)

    if dropped_sold_out or dropped_past:
        logger.debug(
            "tour_loader.dates_filtered",
            tour=filename,
            available=len(available),
            shown=len(shown),
            sold_out=dropped_sold_out,
            past=dropped_past,
        )

    if other_lines:
        parts.append("")
        parts.extend(other_lines)

    return "\n".join(parts)


def _split_tours_by_headings(items: list[tuple[str, bool]]) -> tuple[list[list[str]], list[str]]:
    """Делить туры по заголовкам Heading.

    items — (текст абзаца, это_заголовок). Новый блок начинается
    с каждого заголовка. Блок со ссылкой на бронирование — тур,
    блок без неё (преамбула типа «цены поднимаются») — общая
    информация, а не фантомный тур.
    Возвращает (блоки_туров, абзацы_общей_информации).
    """
    blocks: list[list[str]] = []
    current: list[str] = []
    for text, is_heading in items:
        if is_heading and current:
            blocks.append(current)
            current = []
        current.append(text)
    if current:
        blocks.append(current)
    tour_blocks: list[list[str]] = []
    notes: list[str] = []
    for block in blocks:
        if any(_BOOKING_URL_RE.search(p) for p in block):
            tour_blocks.append(block)
        else:
            notes.extend(block)
    return tour_blocks, notes


def _split_tours(paragraphs: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for p in paragraphs:
        current.append(p)
        # Preserve legacy document boundaries. Generic site links can occur
        # within a programme and must not manufacture additional tours.
        if _EXPLICIT_BOOKING_URL_RE.search(p) and len(current) > 1:
            blocks.append(current)
            current = []
    # Fallback: if no booking URLs found, split on Google Docs URL
    if not blocks:
        current = []
        for p in paragraphs:
            if _URL_RE.search(p) and current:
                current.append(p)
                blocks.append(current)
                current = []
            else:
                current.append(p)
        if current:
            blocks.append(current)
        return blocks
    # Trailing content after last booking URL belongs to last tour
    if current:
        blocks[-1].extend(current)
    return blocks


def load_tours(folder_path: str | None = None) -> str:
    global _tours_text

    path = folder_path or _tours_folder
    all_tours = []
    general_notes = []
    for filename in sorted(os.listdir(path)):
        if not filename.endswith(".docx"):
            continue
        filepath = os.path.join(path, filename)
        doc = Document(filepath)
        items = [
            (p.text, "Heading" in p.style.name)
            for p in doc.paragraphs if p.text.strip()
        ]
        if any(is_heading for _, is_heading in items):
            tour_blocks, notes = _split_tours_by_headings(items)
        else:
            # Fallback для файлов без заголовков: старое деление по ссылкам.
            tour_blocks = _split_tours([text for text, _ in items])
            notes = []
        for block in tour_blocks:
            tour_name = block[0].strip().rstrip(":").strip()
            section = _extract_tour_section(tour_name, block)
            all_tours.append(section)
        general_notes.extend(notes)
        logger.info("tour_loader.loaded", file=filename, tours=len(tour_blocks))

    parts = []
    if general_notes:
        parts.append("=== ОБЩАЯ ИНФОРМАЦИЯ ===\n" + "\n".join(general_notes))
    parts.extend(all_tours)
    _tours_text = "\n\n".join(parts)
    logger.info("tour_loader.complete", chars=len(_tours_text), tours=len(all_tours))
    return _tours_text


def get_tours_text() -> str:
    return _tours_text


def publish_tours_text(text: str) -> None:
    """Атомарно подменить кэш базы туров (точка перезагрузки для tour_sync).

    Простое присваивание глобала: читатели (`get_tours_text`) видят либо
    старую, либо новую версию целиком, половинчатого состояния нет.
    """
    global _tours_text
    _tours_text = text
    logger.info("tours.published", chars=len(text))


def save_snapshot(path: str, snapshot: dict) -> None:
    """Сохранить last-good снапшот (атомарно: tmp + rename)."""
    import json
    import os as _os

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)
    _os.replace(tmp_path, path)


def load_snapshot(path: str) -> dict | None:
    """Прочитать last-good снапшот. Нет файла/битый JSON — None, не исключение."""
    import json

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("text"):
        return None
    return data
