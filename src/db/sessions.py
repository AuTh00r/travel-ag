import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from structlog import get_logger

logger = get_logger()

DB_PATH = Path("data/sessions.db")


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
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
    conn = _get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO sessions (client_id, state, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)""",
        (client_id, json.dumps(state, default=str)),
    )
    conn.commit()
    conn.close()
    logger.debug("session.saved", client_id=client_id)


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



