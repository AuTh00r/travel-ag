from datetime import datetime, timedelta, timezone

from src.db.sessions import is_manager_active


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



