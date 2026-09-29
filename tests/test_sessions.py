from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.db.sessions import (
    effective_escalation_count,
    get_session,
    is_manager_active,
    save_session,
    trim_history,
)


class TestManagerTakeover:
    def test_none_not_active(self):
        assert is_manager_active({"manager_last_at": None}, 10080) is False

    def test_recent_mark_active(self):
        session = {"manager_last_at": datetime.now(timezone.utc).isoformat()}
        assert is_manager_active(session, 10080) is True

    def test_old_mark_expired(self):
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        session = {"manager_last_at": old}
        assert is_manager_active(session, 10080) is False

    def test_broken_string(self):
        session = {"manager_last_at": "not-a-date"}
        assert is_manager_active(session, 10080) is False


def _msgs(n: int) -> list[dict]:
    return [{"role": "user", "content": str(i)} for i in range(n)]


class TestTrimHistory:
    def test_short_history_untouched(self):
        history = _msgs(5)
        assert trim_history(history, 20) is history

    def test_exact_limit_untouched(self):
        history = _msgs(20)
        assert trim_history(history, 20) is history

    def test_keeps_newest_messages(self):
        trimmed = trim_history(_msgs(50), 20)
        assert len(trimmed) == 20
        # Режем с начала: свежий контекст важнее давнего.
        assert trimmed[0]["content"] == "30"
        assert trimmed[-1]["content"] == "49"

    def test_zero_disables_trimming(self):
        history = _msgs(50)
        assert trim_history(history, 0) is history

    def test_does_not_mutate_input(self):
        history = _msgs(50)
        trim_history(history, 20)
        assert len(history) == 50


class TestEffectiveEscalationCount:
    def test_zero_stays_zero(self):
        assert effective_escalation_count({"escalation_count": 0}, 24) == 0

    def test_recent_activity_keeps_count(self):
        session = {
            "escalation_count": 3,
            "last_message_at": datetime.now(timezone.utc).isoformat(),
        }
        assert effective_escalation_count(session, 24) == 3

    def test_resets_after_idle_period(self):
        """Лимит в 3 эскалации не должен быть пожизненным."""
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        session = {"escalation_count": 3, "last_message_at": old}
        assert effective_escalation_count(session, 24) == 0

    def test_just_under_threshold_keeps_count(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=23)).isoformat()
        session = {"escalation_count": 3, "last_message_at": recent}
        assert effective_escalation_count(session, 24) == 3

    def test_missing_timestamp_keeps_count(self):
        session = {"escalation_count": 2, "last_message_at": None}
        assert effective_escalation_count(session, 24) == 2

    def test_broken_timestamp_keeps_count(self):
        session = {"escalation_count": 2, "last_message_at": "not-a-date"}
        assert effective_escalation_count(session, 24) == 2

    def test_naive_timestamp_treated_as_utc(self):
        naive = (datetime.now(timezone.utc) - timedelta(hours=25)).replace(tzinfo=None)
        session = {"escalation_count": 3, "last_message_at": naive.isoformat()}
        assert effective_escalation_count(session, 24) == 0

    def test_zero_hours_disables_reset(self):
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        session = {"escalation_count": 3, "last_message_at": old}
        assert effective_escalation_count(session, 0) == 3


class TestSaveSessionHistoryCap:
    """save_session — единственная точка записи, там же и потолок истории.

    Историю наращивают шесть разных мест в main.py; полагаться на то, что
    каждое помнит про лимит, не стоит.
    """

    @pytest.mark.asyncio
    async def test_keeps_history_at_threshold(self):
        limit = settings.max_history_messages
        history = [{"role": "user", "content": str(i)} for i in range(limit * 2)]
        await save_session("cap_1", {"history": history, "escalation_count": 0})

        stored = (await get_session("cap_1"))["history"]
        assert len(stored) == limit * 2

    @pytest.mark.asyncio
    async def test_caps_runaway_history(self):
        limit = settings.max_history_messages
        history = [{"role": "user", "content": str(i)} for i in range(200)]
        await save_session("cap_2", {"history": history, "escalation_count": 0})

        stored = (await get_session("cap_2"))["history"]
        assert len(stored) == limit * 2
        assert stored[-1]["content"] == "199", "новейшая реплика обязана выжить"

    @pytest.mark.asyncio
    async def test_does_not_mutate_caller_state(self):
        """Вызывающий код продолжает работать со своим списком после сохранения."""
        history = [{"role": "user", "content": str(i)} for i in range(200)]
        session = {"history": history, "escalation_count": 0}
        await save_session("cap_3", session)

        assert len(history) == 200
        assert session["history"] is history



