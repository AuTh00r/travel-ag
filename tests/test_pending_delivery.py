from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.exceptions import InstagramRateLimitError


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Изолированная БД на каждый тест — main.py читает/пишет sessions и
    pending_messages через реальные функции, но не должен трогать общий
    data/sessions.db.
    """
    import src.db.pending_messages as pending_messages
    import src.db.sessions as sessions

    db_path = tmp_path / "test_delivery.db"
    monkeypatch.setattr(sessions, "DB_PATH", db_path)
    monkeypatch.setattr(pending_messages, "DB_PATH", db_path)
    yield


class TestSendOrQueue:
    """_send_or_queue — общий хелпер отправки с постановкой в очередь при сбое."""

    @pytest.mark.asyncio
    @patch("src.channels.instagram.InstagramChannel.send_message", new=AsyncMock())
    async def test_success_does_not_enqueue(self, ):
        from src.db.pending_messages import count_pending
        from src.main import _send_or_queue

        ok, retry_at = await _send_or_queue("CLIENT_1", "привет")

        assert ok is True
        assert retry_at is None
        assert await count_pending() == 0

    @pytest.mark.asyncio
    @patch("src.channels.instagram.InstagramChannel.send_message")
    async def test_rate_limit_enqueues_with_retry_after(self, mock_send):
        from src.db.pending_messages import get_due_pending
        from src.main import _send_or_queue

        mock_send.side_effect = InstagramRateLimitError(
            "limited", error_code=80002, retry_after_seconds=1.0
        )

        ok, retry_at = await _send_or_queue("CLIENT_1", "привет")

        assert ok is False
        assert retry_at is not None

        # retry_after_seconds=1.0 — должно быть due почти сразу
        import asyncio

        await asyncio.sleep(1.1)
        due = await get_due_pending(datetime.now(timezone.utc).isoformat())
        assert len(due) == 1
        assert due[0]["text"] == "привет"

    @pytest.mark.asyncio
    @patch("src.channels.instagram.InstagramChannel.send_message")
    async def test_other_error_enqueues_with_default_delay(self, mock_send):
        from src.db.pending_messages import count_pending
        from src.main import _send_or_queue

        mock_send.side_effect = RuntimeError("network down")

        ok, retry_at = await _send_or_queue("CLIENT_1", "привет")

        assert ok is False
        assert await count_pending() == 1


class TestPartialChunkDelivery:
    """process_with_ai — история должна отражать только реально доставленное."""

    @pytest.mark.asyncio
    @patch("src.channels.instagram.InstagramChannel.get_username", new=AsyncMock(return_value=None))
    @patch("src.services.tour_loader.get_tours_text", return_value="")
    @patch("src.services.llm.get_llm")
    @patch("src.channels.instagram.InstagramChannel.send_message")
    async def test_history_contains_only_sent_chunks(
        self, mock_send, mock_llm, mock_tours,
    ):
        from src.db.sessions import get_session
        from src.main import _split_reply, process_with_ai

        long_text = "Тур в Турцию, всё включено, вылет из Минска. " * 40
        expected_chunks = _split_reply(long_text)
        assert len(expected_chunks) >= 2, "нужен ответ минимум из 2 chunks для теста"

        mock_llm.return_value.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content=long_text)
        )
        # Первый chunk уходит успешно, второй (и далее) — падает с rate-limit.
        mock_send.side_effect = [None] + [
            InstagramRateLimitError("limited", error_code=4, retry_after_seconds=5.0)
        ] * (len(expected_chunks) - 1)

        sender_id = "CLIENT_PARTIAL_1"
        await process_with_ai(sender_id, "хочу тур")

        session = await get_session(sender_id)
        history = session["history"]
        assistant_messages = [h for h in history if h["role"] == "assistant"]

        assert len(assistant_messages) == 1
        assert assistant_messages[0]["content"] == expected_chunks[0]

        # retry_after_seconds=5.0 уводит retry_at в будущее — get_due_pending
        # его не покажет как due, поэтому проверяем таблицу напрямую.
        import src.db.pending_messages as pending_messages

        conn = pending_messages._get_connection()
        rows = conn.execute(
            "SELECT text FROM pending_messages ORDER BY id"
        ).fetchall()
        conn.close()
        assert [r["text"] for r in rows] == expected_chunks[1:]

    @pytest.mark.asyncio
    @patch("src.channels.instagram.InstagramChannel.get_username", new=AsyncMock(return_value=None))
    @patch("src.services.tour_loader.get_tours_text", return_value="")
    @patch("src.services.llm.get_llm")
    @patch("src.channels.instagram.InstagramChannel.send_message", new=AsyncMock())
    async def test_history_has_single_combined_entry_on_full_success(
        self, mock_llm, mock_tours,
    ):
        from src.db.sessions import get_session
        from src.main import process_with_ai

        mock_llm.return_value.ainvoke = AsyncMock(
            return_value=SimpleNamespace(content="Привет! Вот варианты туров.")
        )

        sender_id = "CLIENT_PARTIAL_2"
        await process_with_ai(sender_id, "хочу тур")

        session = await get_session(sender_id)
        assistant_messages = [h for h in session["history"] if h["role"] == "assistant"]
        assert len(assistant_messages) == 1
        assert assistant_messages[0]["content"] == "Привет! Вот варианты туров."


class TestRescheduleOrGiveup:
    """_reschedule_or_giveup — сдаётся ровно после max_retry_attempts суммарных попыток."""

    @pytest.mark.asyncio
    async def test_reschedules_before_limit(self):
        from src.config import settings
        from src.db.pending_messages import enqueue_pending
        from src.main import _reschedule_or_giveup

        row_id = await enqueue_pending("CLIENT_1", "текст", "2020-01-01T00:00:00+00:00")
        row = {"id": row_id, "recipient_id": "CLIENT_1", "text": "текст", "attempts": 0}

        await _reschedule_or_giveup(row, None)

        import src.db.pending_messages as pending_messages

        conn = pending_messages._get_connection()
        db_row = conn.execute(
            "SELECT attempts FROM pending_messages WHERE id = ?", (row_id,)
        ).fetchone()
        conn.close()
        assert db_row is not None, "запись не должна быть удалена до достижения лимита"
        assert db_row["attempts"] == 1
        assert settings.max_retry_attempts == 5  # документируем допущение теста

    @pytest.mark.asyncio
    @patch("src.services.telegram_notify.TelegramNotifier")
    async def test_gives_up_exactly_at_max_attempts(self, mock_notifier_cls):
        """max_retry_attempts=5 → сдаётся после (attempts=3), т.к. 1 изначальная
        попытка в process_with_ai + attempts воркера + текущая = 5 суммарно.
        """
        from src.config import settings
        from src.db.pending_messages import enqueue_pending
        from src.main import _reschedule_or_giveup

        assert settings.max_retry_attempts == 5
        mock_notifier = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        row_id = await enqueue_pending("CLIENT_1", "текст", "2020-01-01T00:00:00+00:00")
        row = {"id": row_id, "recipient_id": "CLIENT_1", "text": "текст", "attempts": 3}

        await _reschedule_or_giveup(row, None)

        import src.db.pending_messages as pending_messages

        conn = pending_messages._get_connection()
        db_row = conn.execute(
            "SELECT * FROM pending_messages WHERE id = ?", (row_id,)
        ).fetchone()
        conn.close()
        assert db_row is None, "должна быть удалена — попытки исчерпаны"

        mock_notifier.notify_manager.assert_awaited_once()
        _, kwargs = mock_notifier.notify_manager.await_args
        assert kwargs["tag"] == "Сбой доставки"


class TestPendingMessagesWorker:
    """_pending_messages_worker — один проход обработки due-сообщений."""

    @pytest.mark.asyncio
    @patch("src.channels.instagram.InstagramChannel.send_message", new=AsyncMock())
    async def test_successful_resend_deletes_and_appends_history(self):
        from src.db.pending_messages import enqueue_pending, get_due_pending
        from src.db.sessions import get_session
        from src.main import _pending_messages_worker

        import asyncio

        sender_id = "CLIENT_WORKER_1"
        await enqueue_pending(sender_id, "досланное сообщение", "2020-01-01T00:00:00+00:00")

        # asyncio.sleep стоит в НАЧАЛЕ цикла воркера — первый вызов должен
        # пройти как обычно (даёт телу цикла выполниться), обрываем цикл
        # только на втором вызове (начало следующей итерации).
        call_count = 0

        async def _sleep_once_then_stop(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with patch("asyncio.sleep", side_effect=_sleep_once_then_stop):
            with pytest.raises(asyncio.CancelledError):
                await _pending_messages_worker()

        assert await get_due_pending(datetime.now(timezone.utc).isoformat()) == []
        session = await get_session(sender_id)
        assert any(
            h["role"] == "assistant" and h["content"] == "досланное сообщение"
            for h in session["history"]
        )

    @pytest.mark.asyncio
    @patch("src.services.telegram_notify.TelegramNotifier")
    @patch("src.channels.instagram.InstagramChannel.send_message")
    async def test_failed_resend_reschedules(self, mock_send, mock_notifier_cls):
        import asyncio

        from src.db.pending_messages import enqueue_pending, get_due_pending
        from src.main import _pending_messages_worker

        mock_send.side_effect = InstagramRateLimitError(
            "limited", error_code=4, retry_after_seconds=3600.0
        )
        mock_notifier_cls.return_value = AsyncMock()

        row_id = await enqueue_pending("CLIENT_WORKER_2", "текст", "2020-01-01T00:00:00+00:00")

        call_count = 0

        async def _sleep_once_then_stop(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise asyncio.CancelledError

        with patch("asyncio.sleep", side_effect=_sleep_once_then_stop):
            with pytest.raises(asyncio.CancelledError):
                await _pending_messages_worker()

        # Перепланировано далеко в будущее — больше не due
        assert await get_due_pending(datetime.now(timezone.utc).isoformat()) == []

        import src.db.pending_messages as pending_messages

        conn = pending_messages._get_connection()
        db_row = conn.execute(
            "SELECT attempts FROM pending_messages WHERE id = ?", (row_id,)
        ).fetchone()
        conn.close()
        assert db_row["attempts"] == 1
