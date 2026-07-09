import logging
import logging.handlers
from pathlib import Path

import structlog

from src.config import settings

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def configure_logging() -> None:
    """Настроить structlog на запись в файл с ежедневной ротацией.

    start-bot.vbs запускает uvicorn в скрытом окне (WshShell.Run(..., 0, False)) —
    весь stdout/stderr процесса без этой настройки теряется безвозвратно, писать
    некуда. Пишем сами, в обход консоли, поэтому же не упираемся в проблему с
    кодировкой консоли (chcp/cp866), которая тут иначе всплывает постоянно.
    """
    LOG_DIR.mkdir(exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "bot.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler()

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[file_handler, stream_handler],
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
