from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Каждый тест работает со своим файлом БД, чтобы не делить состояние."""
    import src.db.pending_messages as pending_messages
    import src.db.sessions as sessions

    db_path = tmp_path / "test_pending.db"
    monkeypatch.setattr(sessions, "DB_PATH", db_path)
    monkeypatch.setattr(pending_messages, "DB_PATH", db_path)
    yield


def _iso(seconds_from_now: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).isoformat()


class TestEnqueueAndFetch:
    @pytest.mark.asyncio
    async def test_enqueue_returns_id(self):
        from src.db.pending_messages import enqueue_pending

        row_id = await enqueue_pending("CLIENT_1", "привет", _iso(-5))
        assert isinstance(row_id, int)
        assert row_id > 0

    @pytest.mark.asyncio
    async def test_due_message_is_returned(self):
        from src.db.pending_messages import enqueue_pending, get_due_pending

        await enqueue_pending("CLIENT_1", "привет", _iso(-5))
        due = await get_due_pending(datetime.now(timezone.utc).isoformat())

        assert len(due) == 1
        assert due[0]["recipient_id"] == "CLIENT_1"
        assert due[0]["text"] == "привет"
        assert due[0]["attempts"] == 0

    @pytest.mark.asyncio
    async def test_future_message_not_due(self):
        from src.db.pending_messages import enqueue_pending, get_due_pending

        await enqueue_pending("CLIENT_1", "привет", _iso(3600))
        due = await get_due_pending(datetime.now(timezone.utc).isoformat())

        assert due == []

    @pytest.mark.asyncio
    async def test_due_messages_ordered_by_id(self):
        """Порядок сообщений одного клиента не должен переставляться."""
        from src.db.pending_messages import enqueue_pending, get_due_pending

        await enqueue_pending("CLIENT_1", "первое", _iso(-10))
        await enqueue_pending("CLIENT_1", "второе", _iso(-5))

        due = await get_due_pending(datetime.now(timezone.utc).isoformat())
        assert [d["text"] for d in due] == ["первое", "второе"]


class TestRetryAndDelete:
    @pytest.mark.asyncio
    async def test_mark_pending_retry_increments_attempts_and_reschedules(self):
        from src.db.pending_messages import (
            enqueue_pending,
            get_due_pending,
            mark_pending_retry,
        )

        row_id = await enqueue_pending("CLIENT_1", "привет", _iso(-5))
        await mark_pending_retry(row_id, _iso(3600))

        # Больше не due — время сдвинуто в будущее
        assert await get_due_pending(datetime.now(timezone.utc).isoformat()) == []

        # attempts увеличился
        import src.db.pending_messages as pending_messages

        conn = pending_messages._get_connection()
        row = conn.execute(
            "SELECT attempts FROM pending_messages WHERE id = ?", (row_id,)
        ).fetchone()
        conn.close()
        assert row["attempts"] == 1

    @pytest.mark.asyncio
    async def test_delete_pending_removes_row(self):
        from src.db.pending_messages import (
            delete_pending,
            enqueue_pending,
            get_due_pending,
        )

        row_id = await enqueue_pending("CLIENT_1", "привет", _iso(-5))
        await delete_pending(row_id)

        assert await get_due_pending(datetime.now(timezone.utc).isoformat()) == []

    @pytest.mark.asyncio
    async def test_count_pending(self):
        from src.db.pending_messages import count_pending, enqueue_pending

        assert await count_pending() == 0
        await enqueue_pending("CLIENT_1", "a", _iso(-5))
        await enqueue_pending("CLIENT_2", "b", _iso(-5))
        assert await count_pending() == 2
