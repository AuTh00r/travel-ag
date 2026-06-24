import os

from docx import Document
from structlog import get_logger

logger = get_logger()

_tours_text: str = ""
_tours_folder: str = "tours"


def load_tours(folder_path: str | None = None) -> str:
    global _tours_text

    path = folder_path or _tours_folder
    all_tours = []
    for filename in sorted(os.listdir(path)):
        if not filename.endswith(".docx"):
            continue
        filepath = os.path.join(path, filename)
        doc = Document(filepath)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        tour_name = filename.replace(".docx", "")
        all_tours.append(f"=== ТУР: {tour_name} ===\n{text}")
        logger.info("tour_loader.loaded", file=filename)

    _tours_text = "\n\n".join(all_tours)
    logger.info("tour_loader.complete", chars=len(_tours_text), tours=len(all_tours))
    return _tours_text


def get_tours_text() -> str:
    return _tours_text
