import sqlite3
from datetime import datetime, timezone

from structlog import get_logger

from src.db.sessions import DB_PATH

logger = get_logger()


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout + WAL — по той же причине, что в sessions.py: фоновый воркер и
    # обработка входящих пишут в один файл параллельно.
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_id TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            retry_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        )
        """)
    # Индекс на retry_at здесь НЕ создаётся намеренно. Проверено на 5000 строк
    # (EXPLAIN QUERY PLAN): из-за `ORDER BY id` в get_due_pending планировщик
    # всё равно выбирает SCAN — идти по индексу retry_at, а потом сортировать по
    # id дороже, чем просканировать таблицу в порядке rowid. Индекс стал бы
    # мёртвым весом. Без ORDER BY он подхватывается (COVERING INDEX), так что
    # если очередь начнёт реально накапливаться — менять надо запрос, а не
    # добавлять индекс. Сейчас таблица почти всегда пуста: сообщения попадают в
    # неё только при сбоях доставки.
    return conn


async def enqueue_pending(recipient_id: str, text: str, retry_at: str) -> int:
    conn = _get_connection()
    cur = conn.execute(
        """INSERT INTO pending_messages (recipient_id, text, created_at, retry_at)
           VALUES (?, ?, ?, ?)""",
        (recipient_id, text, datetime.now(timezone.utc).isoformat(), retry_at),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    logger.debug("pending.enqueued", id=row_id, recipient_id=recipient_id)
    return row_id


async def get_due_pending(now_iso: str) -> list[dict]:
    conn = _get_connection()
    rows = conn.execute(
        """SELECT id, recipient_id, text, retry_at, attempts
           FROM pending_messages
           WHERE retry_at <= ?
           ORDER BY id""",
        (now_iso,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def mark_pending_retry(id: int, new_retry_at: str) -> None:
    conn = _get_connection()
    conn.execute(
        """UPDATE pending_messages
           SET retry_at = ?, attempts = attempts + 1
           WHERE id = ?""",
        (new_retry_at, id),
    )
    conn.commit()
    conn.close()
    logger.debug("pending.marked_retry", id=id, retry_at=new_retry_at)


async def delete_pending(id: int) -> None:
    conn = _get_connection()
    conn.execute("DELETE FROM pending_messages WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    logger.debug("pending.deleted", id=id)


async def count_pending() -> int:
    conn = _get_connection()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM pending_messages").fetchone()
    conn.close()
    return row["cnt"]
