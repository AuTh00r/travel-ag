import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from structlog import get_logger

from src.config import settings

logger = get_logger()

DB_PATH = Path("data/sessions.db")


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout: писателей минимум два независимых — обработка входящих сообщений
    # и фоновый воркер pending_messages (тикает каждые 30 сек). Per-user локи в
    # main.py защищают от гонки по одному клиенту, но не от пересечения воркера
    # с обработкой разных клиентов. Без timeout конфликт даёт мгновенный
    # "database is locked" вместо ожидания.
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL: в режиме journal (по умолчанию) писатель блокирует читателей. Свойство
    # пишется в сам файл БД один раз и сохраняется, повторный вызов безвреден.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            client_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    return conn


async def get_session(client_id: str) -> dict:
    conn = _get_connection()
    row = conn.execute(
        "SELECT state FROM sessions WHERE client_id = ?", (client_id,)
    ).fetchone()
    conn.close()

    if row:
        return json.loads(row["state"])
    return _new_session(client_id)


def _new_session(client_id: str) -> dict:
    return {
        "history": [],
        "client_id": client_id,
        "escalation_count": 0,
        "manager_last_at": None,
        "last_message_at": None,
    }


async def save_session(client_id: str, state: dict) -> None:
    # Обрезаем здесь, в единственной точке записи: историю наращивают шесть
    # разных мест в main.py, и полагаться на то, что каждое помнит про лимит,
    # не стоит. Сохраняем с запасом относительно того, что уходит в LLM, —
    # сессия остаётся читаемой при разборе инцидентов.
    history = state.get("history")
    if isinstance(history, list):
        limit = settings.max_history_messages
        if limit > 0 and len(history) > limit * 2:
            state = {**state, "history": history[-limit * 2:]}

    conn = _get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO sessions (client_id, state, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)""",
        (client_id, json.dumps(state, default=str)),
    )
    conn.commit()
    conn.close()
    logger.debug("session.saved", client_id=client_id)


def trim_history(history: list[dict], max_messages: int) -> list[dict]:
    """Оставить последние max_messages реплик диалога.

    Без обрезки история растёт бессрочно: каждое сообщение постоянного клиента
    тянет в LLM всю переписку за месяцы. Режем с начала — свежий контекст
    важнее давнего. max_messages <= 0 отключает обрезку.
    """
    if max_messages <= 0 or len(history) <= max_messages:
        return history
    return history[-max_messages:]


def effective_escalation_count(session: dict, reset_hours: int) -> int:
    """Счётчик эскалаций с учётом сброса после простоя.

    Возвращает 0, если клиент молчал дольше reset_hours — иначе лимит в 3
    эскалации становится пожизненным и клиент навсегда теряет доступ к
    живому менеджеру. reset_hours <= 0 отключает сброс.
    """
    count = session.get("escalation_count", 0)
    if count == 0 or reset_hours <= 0:
        return count
    last = session.get("last_message_at")
    if not last:
        return count
    try:
        ts = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return count
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hours_since = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    if hours_since >= reset_hours:
        logger.info("escalation.count_reset", hours_since=round(hours_since, 1))
        return 0
    return count


def is_manager_active(session: dict, ttl_minutes: int) -> bool:
    """True, если живой менеджер недавно (в пределах TTL) писал в этот чат."""
    last = session.get("manager_last_at")
    if not last:
        return False
    try:
        ts = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    return age_minutes < ttl_minutes



