import os
import re

from docx import Document
from structlog import get_logger

logger = get_logger()

_tours_text: str = ""
_tours_folder: str = "tours"

_URL_RE = re.compile(r"https?://docs\.google\.com\S+")
_KEY_FIELDS = ("Маршрут:", "Даты:", "Стоимость:", "Тип отдыха:", "Виза:")


def _extract_tour_section(filename: str, paragraphs: list[str]) -> str:
    text = "\n".join(paragraphs)

    url_match = _URL_RE.search(text)
    tour_url = url_match.group(0) if url_match else ""
    if tour_url:
        text = _URL_RE.sub("", text).strip()

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("ПОДРОБНАЯ ИНФОРМАЦИЯ И БРОНИРОВАНИЕ НА САЙТЕ", "").strip()

    key_lines = []
    other_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(f) for f in _KEY_FIELDS):
            key_lines.append(line)
        else:
            other_lines.append(line)

    parts = [f"=== ТУР: {filename} ==="]
    if tour_url:
        parts.append(f"Ссылка на тур: {tour_url}")
    parts.extend(key_lines)
    if other_lines:
        parts.append("")
        parts.extend(other_lines)

    return "\n".join(parts)


def _split_tours(paragraphs: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
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


def load_tours(folder_path: str | None = None) -> str:
    global _tours_text

    path = folder_path or _tours_folder
    all_tours = []
    for filename in sorted(os.listdir(path)):
        if not filename.endswith(".docx"):
            continue
        filepath = os.path.join(path, filename)
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        tour_blocks = _split_tours(paragraphs)
        for block in tour_blocks:
            tour_name = block[0].strip().rstrip(":").strip()
            section = _extract_tour_section(tour_name, block)
            all_tours.append(section)
        logger.info("tour_loader.loaded", file=filename, tours=len(tour_blocks))

    _tours_text = "\n\n".join(all_tours)
    logger.info("tour_loader.complete", chars=len(_tours_text), tours=len(all_tours))
    return _tours_text


def get_tours_text() -> str:
    return _tours_text
