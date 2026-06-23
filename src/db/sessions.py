import json
import sqlite3
from pathlib import Path

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from structlog import get_logger

from src.ai.states import DialogState

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            tour TEXT DEFAULT '',
            destination TEXT DEFAULT '',
            budget TEXT DEFAULT '',
            travelers INTEGER DEFAULT 1,
            status TEXT DEFAULT 'Новая',
            source TEXT DEFAULT 'Instagram',
            tag TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    return conn


async def get_session(client_id: str) -> DialogState:
    conn = _get_connection()
    row = conn.execute(
        "SELECT state FROM sessions WHERE client_id = ?", (client_id,)
    ).fetchone()
    conn.close()

    if row:
        state = json.loads(row["state"])
        msgs = state.get("messages", [])
        if msgs and isinstance(msgs[0], dict) and "type" in msgs[0]:
            state["messages"] = messages_from_dict(msgs)
        return state
    return _new_session(client_id)


def _new_session(client_id: str) -> DialogState:
    return {
        "messages": [],
        "client_id": client_id,
        "client_name": None,
        "client_phone": None,
        "client_email": None,
        "request_type": None,
        "tour_params": {},
        "found_tours": [],
        "selected_tour": None,
        "faq_answer": None,
        "needs_escalation": False,
        "escalation_reason": None,
        "current_step": "greeting",
        "awaiting_field": None,
        "conversation_history": [],
    }


async def save_session(client_id: str, state: DialogState) -> None:
    conn = _get_connection()

    serializable = dict(state)
    serializable["messages"] = [
        message_to_dict(m) if isinstance(m, BaseMessage) else m
        for m in serializable.get("messages", [])
    ]

    conn.execute(
        """INSERT OR REPLACE INTO sessions (client_id, state, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)""",
        (client_id, json.dumps(serializable)),
    )
    conn.commit()
    conn.close()
    logger.debug("session.saved", client_id=client_id)


async def save_booking_request(
    client_id: str,
    name: str,
    phone: str,
    email: str,
    tour: str = "",
    destination: str = "",
    budget: str = "",
    travelers: int = 1,
) -> None:
    conn = _get_connection()
    conn.execute(
        """INSERT INTO requests (client_id, name, phone, email, tour, destination, budget, travelers)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (client_id, name, phone, email, tour, destination, budget, travelers),
    )
    conn.commit()
    conn.close()
    logger.info("booking_request.saved", client_id=client_id, name=name)


async def update_request_status(
    client_id: str,
    new_status: str,
) -> bool:
    valid_statuses = {"Новая", "В обработке", "Подтверждена", "Оплачена"}
    if new_status not in valid_statuses:
        raise ValueError(
            f"Неверный статус: {new_status}. Допустимые: {', '.join(sorted(valid_statuses))}"
        )

    conn = _get_connection()
    cursor = conn.execute(
        "UPDATE requests SET status = ? WHERE rowid = (SELECT rowid FROM requests WHERE client_id = ? ORDER BY created_at DESC LIMIT 1)",
        (new_status, client_id),
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()

    if affected:
        logger.info("request.status.updated", client_id=client_id, status=new_status)
    else:
        logger.warning("request.status.not_found", client_id=client_id)
    return affected > 0


async def get_requests_by_client(client_id: str) -> list[dict]:
    conn = _get_connection()
    rows = conn.execute(
        """SELECT id, name, phone, email, tour, destination, budget,
                  travelers, status, source, tag, created_at
           FROM requests WHERE client_id = ? ORDER BY created_at DESC""",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
