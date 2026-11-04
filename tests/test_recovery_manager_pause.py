"""A manager pause wins before refresh, failure fallback and technical retry."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.db import sessions
from src.db.inbound import StaleWork
from src.config import settings
from tests.test_inbound_recovery import clock as clock, store as store, make_job, service


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "inbound_recovery_scope", "all")
    monkeypatch.setattr(settings, "inbound_recovery_enabled", True)
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)


def pause(store):
    state, _ = store.read_session("client")
    state["manager_last_at"] = datetime.now(timezone.utc).isoformat()
    with store.connection() as conn:
        sessions.write_row(conn, "client", state)


def recovered_job(store, clock, attempts=0):
    job = make_job(store, clock)
    with store.connection() as conn:
        conn.execute("UPDATE inbound_jobs SET recovered=1,technical_attempts=? WHERE id=?", (attempts, job["id"]))
    return {**job, **store.get_job(job["id"])}


def assert_cancelled(recovery, job):
    row = recovery.store.get_job(job["id"])
    assert row["state"] == "cancelled" and row["reason"] == "manager_takeover"
    assert row["technical_attempts"] == job["technical_attempts"]
    assert recovery.store.deliveries(job["id"]) == []
    recovery.dispatch.assert_not_awaited()
    recovery.channel.send_message.assert_not_awaited()


@pytest.mark.parametrize("attempts", [None, 0, 2])
async def test_existing_manager_pause_cancels_before_refresh(store, clock, attempts):
    job = make_job(store, clock) if attempts is None else recovered_job(store, clock, attempts)
    recovery = service(store, clock)
    recovery.refresh_client.return_value = False
    pause(store)
    await recovery.process(job)
    assert_cancelled(recovery, job)
    recovery.refresh_client.assert_not_awaited()
    state, _ = store.read_session("client")
    state["manager_last_at"] = None
    with store.connection() as conn:
        sessions.write_row(conn, "client", state)
    clock.advance(1000)
    assert store.claim_due() is None


@pytest.mark.parametrize("refresh", [False, True, "error"])
@pytest.mark.parametrize("attempts", [0, 2])
async def test_manager_pause_during_refresh_always_cancels(store, clock, refresh, attempts):
    job = recovered_job(store, clock, attempts)
    recovery = service(store, clock)
    async def take_over(client):
        pause(store)
        if refresh == "error":
            raise TimeoutError("synthetic")
        return refresh
    recovery.refresh_client.side_effect = take_over
    await recovery.process(job)
    assert_cancelled(recovery, job)


@pytest.mark.parametrize("during_refresh", [False, True])
async def test_pending_manager_cancels_even_without_persisted_pause(store, clock, during_refresh):
    job = recovered_job(store, clock, 2)
    recovery = service(store, clock)
    pending = [not during_refresh]
    recovery.manager_pending = lambda client: pending[0]
    async def take_over(client):
        pending[0] = True
        return False
    recovery.refresh_client.side_effect = take_over
    await recovery.process(job)
    assert_cancelled(recovery, job)
    assert recovery.refresh_client.await_count == int(during_refresh)


async def test_stale_exception_with_manager_pause_cancels_instead_of_exhausting_retry(store, clock):
    job = recovered_job(store, clock, 2)
    recovery = service(store, clock)
    async def stale(job):
        pause(store)
        raise StaleWork("session_changed")
    recovery.can_resume = AsyncMock(side_effect=stale)
    await recovery.process(job)
    assert_cancelled(recovery, job)


async def test_real_gap_without_manager_keeps_technical_retry(store, clock):
    job = recovered_job(store, clock)
    recovery = service(store, clock)
    recovery.refresh_client.return_value = False
    await recovery.process(job)
    row = store.get_job(job["id"])
    assert row["state"] == "retry_wait" and row["reason"] == "fresh_context_unavailable"
    assert row["technical_attempts"] == 1 and row["due"] == clock()+120
    recovery.dispatch.assert_not_awaited()


@pytest.mark.parametrize("state", ["processing", "cancelled", "done", "unknown", "delivering"])
async def test_stale_worker_does_not_cancel_new_owner_or_change_terminal_state(store, clock, state):
    job = recovered_job(store, clock)
    recovery = service(store, clock)
    with store.connection() as conn:
        conn.execute("UPDATE inbound_jobs SET state=?,claim='new-owner' WHERE id=?", (state, job["id"]))
    pause(store)
    before = store.get_job(job["id"])
    await recovery.process(job)
    assert store.get_job(job["id"]) == before
    recovery.refresh_client.assert_not_awaited()
    recovery.dispatch.assert_not_awaited()
