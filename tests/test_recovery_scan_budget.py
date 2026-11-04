"""Real scanner scheduling with synthetic Graph, SQLite and delivery only."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.db.inbound import InboundStore
from src.exceptions import InstagramRateLimitError
from tests.test_inbound_recovery import clock as clock, service, plan_reply


@pytest.fixture
def scanner(clock, monkeypatch):
    monkeypatch.setattr(settings, "inbound_recovery_enabled", True)
    monkeypatch.setattr(settings, "inbound_recovery_scope", "allowlist")
    monkeypatch.setattr(settings, "inbound_recovery_client_ids", "1001")
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)
    monkeypatch.setattr("src.services.inbound_recovery.asyncio.sleep", AsyncMock())
    store = InboundStore(clock=clock)
    store.initialize("account", ("1001",))
    recovery = service(store, clock, AsyncMock(side_effect=plan_reply))
    recovery.channel.list_conversations.return_value = {"data": [], "after": None}
    recovery.channel.list_conversation_messages.return_value = {"data": [], "after": None}
    return recovery


def cache(scanner, clock, client="1001", dialog="known", age=10000):
    value = {"client_id": client, "id": dialog, "checked_at": clock()-age, "gap": False, "through": clock()}
    scanner.store.set_sync("dialog:"+client, value)
    return value


def message(clock, mid="missed"):
    return {"id": mid, "from": {"id": "1001"}, "to": {"data": [{"id": "account"}]},
            "created_time": datetime.fromtimestamp(clock()+1, timezone.utc).isoformat(), "message": "Эльбрус"}


async def test_thousand_excluded_dialogs_do_not_consume_get_budget(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 60)
    foreign = [{"id": f"foreign-{i}", "client_id": f"other-{i}"} for i in range(1000)]
    pages = [{"data": foreign[i:i+20], "after": str(i+20)} for i in range(0, 1000, 20)]
    pages.append({"data": [{"id": "target", "client_id": "1001"}], "after": None})
    scanner.channel.list_conversations.side_effect = pages
    await scanner.reconcile_tick()
    assert scanner.channel.list_conversations.await_count == 51
    scanner.channel.list_conversation_messages.assert_awaited_once_with("target")
    assert scanner.store.get_sync("dialog:1001")["checked_at"] == clock()
    assert scanner.store.get_sync("dialog:other-0") is None
    assert scanner.store.get_sync("complete_scan:account") == clock()
    scanner.dispatch.assert_not_awaited()


async def test_priority_sync_after_restart_finds_missed_mid_once_without_global_traversal(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    cache(scanner, clock)
    cursor = {"after": "far-page", "dialogs": [{"id": "foreign", "client_id": "other"}], "end": False}
    scanner.store.set_sync("scan:account", cursor)
    # New coordinator, same durable checkpoint/cursor: restart does not lose priority.
    recovery = service(scanner.store, clock, AsyncMock(side_effect=plan_reply))
    recovery.channel.list_conversation_messages.return_value = {"data": [message(clock)], "after": None}
    for _ in range(2):
        await recovery.reconcile_tick()
        assert recovery.store.get_sync("dialog:1001")["checked_at"] == clock()
        clock.advance(120)
    recovery.channel.list_conversation_messages.assert_any_await("known")
    assert recovery.channel.list_conversation_messages.await_count == 2
    recovery.channel.list_conversations.assert_not_awaited()
    assert recovery.store.get_sync("scan:account") == cursor
    recovery.dispatch.assert_not_awaited()
    with recovery.store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM inbound_events WHERE mid='missed'").fetchone()[0] == 1
    await recovery.tick()
    await asyncio.gather(*list(recovery.active.values()))
    recovery.dispatch.assert_awaited_once()
    recovery.channel.send_message.assert_awaited_once_with("1001", "Программа Эльбруса")


async def test_one_budget_for_priority_and_discovery_keeps_unread_cursor(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    monkeypatch.setattr(settings, "inbound_recovery_client_ids", "1001,1002")
    cache(scanner, clock)
    scanner.channel.list_conversations.return_value = {"data": [
        {"id": "known", "client_id": "1001"}, {"id": "new", "client_id": "1002"}], "after": None}
    await scanner.reconcile_tick()
    scanner.channel.list_conversation_messages.assert_awaited_once_with("known")
    pending = scanner.store.get_sync("scan:account")["dialogs"]
    assert any(row["id"] == "new" for row in pending)
    assert scanner.store.get_sync("scan_failures:account") == 0
    clock.advance(120)
    await scanner.reconcile_tick()
    assert [call.args[0] for call in scanner.channel.list_conversation_messages.await_args_list] == ["known", "known", "new"]
    assert scanner.channel.list_conversations.await_count == 1
    assert scanner.store.get_sync("complete_scan:account") == clock()


async def test_oldest_known_client_first_when_budget_is_tiny(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    monkeypatch.setattr(settings, "inbound_recovery_client_ids", "1001,1002")
    cache(scanner, clock, "1001", "recent", 100)
    cache(scanner, clock, "1002", "old", 1000)
    await scanner.reconcile_tick()
    scanner.channel.list_conversation_messages.assert_awaited_once_with("old")
    clock.advance(120)
    await scanner.reconcile_tick()
    assert scanner.channel.list_conversation_messages.await_args.args == ("recent",)


async def test_priority_never_reads_foreign_checkpoint_or_duplicates_discovery(scanner, clock, monkeypatch):
    cache(scanner, clock)
    cache(scanner, clock, "other", "foreign")
    scanner.channel.list_conversations.return_value = {"data": [
        {"id": "known", "client_id": "1001"}, {"id": "foreign", "client_id": "other"}], "after": None}
    await scanner.reconcile_tick()
    scanner.channel.list_conversation_messages.assert_awaited_once_with("known")
    scanner.store.set_sync("dialog:1001", {"client_id": "other", "id": "foreign"})
    scanner.channel.list_conversation_messages.reset_mock()
    scanner.channel.list_conversations.return_value = {"data": [], "after": None}
    await scanner.reconcile_tick()
    scanner.channel.list_conversation_messages.assert_not_awaited()


async def test_priority_rate_limit_preserves_backoff_cursor_and_refresh_context(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    cache(scanner, clock)
    cursor = {"after": "far-page", "dialogs": []}
    scanner.store.set_sync("scan:account", cursor)
    scanner.channel.list_conversation_messages.side_effect = InstagramRateLimitError("synthetic", retry_after_seconds=600)
    await scanner.reconcile_tick()
    assert scanner.store.get_sync("next_scan:account") == clock()+600
    assert scanner.store.get_sync("scan:account") == cursor
    assert scanner.store.get_sync("scan_failures:account") == 1
    # Budget context must reset even after provider failure, for delivery refresh.
    scanner.channel.list_conversation_messages.side_effect = None
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True


async def test_all_scope_does_not_priority_scan_cached_foreign_clients(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "inbound_recovery_scope", "all")
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    cache(scanner, clock)
    scanner.channel.list_conversations.return_value = {"data": [{"id": "new", "client_id": "new-client"}], "after": None}
    await scanner.reconcile_tick()
    scanner.channel.list_conversation_messages.assert_awaited_once_with("new")


async def test_priority_gap_is_reused_and_never_marks_full_scan_complete(scanner, clock):
    cache(scanner, clock)
    rows = [dict(message(clock, f"same-time-{i}")) for i in range(20)]
    scanner.channel.list_conversation_messages.return_value = {"data": rows, "after": "older"}
    scanner.channel.list_conversations.return_value = {"data": [{"id": "known", "client_id": "1001"}], "after": None}
    await scanner.reconcile_tick()
    # One traversal, including one continuation, reused by discovery.
    assert [call.args for call in scanner.channel.list_conversation_messages.await_args_list] == [("known",), ("known", "older")]
    assert scanner.store.get_sync("dialog:1001")["gap"] is True
    assert scanner.store.get_sync("complete_scan:account") is None
    assert scanner.store.get_sync("scan_failures:account") == 0


@pytest.mark.parametrize("gap", [False, True])
async def test_discovery_reuses_dialog_when_meta_pages_overlap(scanner, clock, gap):
    dialog = {"id": "found", "client_id": "1001"}
    scanner.channel.list_conversations.side_effect = [
        {"data": [dialog], "after": "next"}, {"data": [dialog], "after": None}]
    scanner.channel.list_conversation_messages.return_value = {
        "data": [message(clock, f"m-{i}") for i in range(20)] if gap else [],
        "after": "older" if gap else None}
    await scanner.reconcile_tick()
    assert scanner.channel.list_conversations.await_count == 2
    expected = [("found",), ("found", "older")] if gap else [("found",)]
    assert [call.args for call in scanner.channel.list_conversation_messages.await_args_list] == expected
    assert bool(scanner.store.get_sync("complete_scan:account")) is not gap


async def test_independent_refresh_does_not_inherit_running_scanner_budget(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    known = cache(scanner, clock)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow_priority(dialog_id):
        started.set()
        await release.wait()
        return {"data": [], "after": None}

    scanner.channel.list_conversation_messages.side_effect = slow_priority
    # Independent worker is created before scanner enters its task-local context.
    async def delivery_refresh():
        await started.wait()
        release.set()
        return await scanner.sync_dialog(known)

    delivery = asyncio.create_task(delivery_refresh())
    await scanner.reconcile_tick()
    assert await delivery is True
    assert scanner.channel.list_conversation_messages.await_count == 2
    scanner.channel.list_conversations.assert_not_awaited()
    assert scanner.store.get_sync("scan_failures:account") == 0


async def test_cancelled_scan_releases_budget_and_keeps_unread_cursor(scanner, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    cache(scanner, clock)
    cursor = {"after": "middle", "dialogs": [{"id": "foreign", "client_id": "other"}]}
    scanner.store.set_sync("scan:account", cursor)
    scanner.channel.list_conversation_messages.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await scanner.reconcile_tick()
    assert scanner.store.get_sync("scan:account") == cursor
    scanner.channel.list_conversation_messages.side_effect = None
    assert await scanner.sync_dialog({"client_id": "1001", "id": "known"}) is True


async def test_budget_ends_before_second_dialog_without_popping_it(scanner, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    scanner.channel.list_conversations.return_value = {"data": [
        {"id": "one", "client_id": "1001"}, {"id": "two", "client_id": "1001"}], "after": None}
    await scanner.reconcile_tick()
    assert scanner.channel.list_conversations.await_count == 1
    scanner.channel.list_conversation_messages.assert_awaited_once_with("one")
    assert scanner.store.get_sync("scan:account")["dialogs"] == [{"id": "two", "client_id": "1001"}]
    assert scanner.store.get_sync("scan_failures:account") == 0


@pytest.mark.parametrize("deadline_elapsed", [False, True])
async def test_deadline_is_normal_boundary_but_early_timeout_keeps_backoff(scanner, clock, monkeypatch, deadline_elapsed):
    now = [0.0]
    monkeypatch.setattr("src.services.inbound_recovery.time", SimpleNamespace(monotonic=lambda: now[0]))
    cursor = {"after": "middle", "dialogs": []}
    scanner.store.set_sync("scan:account", cursor)

    async def timeout(after):
        now[0] = settings.instagram_reconcile_deadline_seconds+1 if deadline_elapsed else 1
        raise TimeoutError("synthetic")

    scanner.channel.list_conversations.side_effect = timeout
    await scanner.reconcile_tick()
    assert scanner.store.get_sync("scan:account") == cursor
    assert scanner.store.get_sync("scan_failures:account") == (0 if deadline_elapsed else 1)
    assert scanner.store.get_sync("next_scan:account") == (None if deadline_elapsed else clock()+30)


@pytest.mark.parametrize("route", ["scan", "priority", "refresh"])
@pytest.mark.parametrize("timeout_origin", ["own_timer", "provider", "external_cancel"])
async def test_early_timer_keeps_timeout_ownership(scanner, clock, monkeypatch, route, timeout_origin):
    # Windows timers may fire before monotonic reaches the scheduled deadline.
    # Run the real timeout/cancellation machinery, keeping the comparison clock early.
    monkeypatch.setattr("src.services.inbound_recovery.time", SimpleNamespace(monotonic=lambda: 0.0))
    cursor = {"after": "unread-page", "dialogs": []}
    scanner.store.set_sync("scan:account", cursor)
    checkpoint = cache(scanner, clock) if route != "scan" else None
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def provider(*args):
        if timeout_origin == "provider":
            raise TimeoutError("early provider timeout")
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    method = (scanner.channel.list_conversations if route == "scan"
              else scanner.channel.list_conversation_messages)
    method.side_effect = provider

    if timeout_origin == "own_timer":
        loop = asyncio.get_running_loop()
        call_at = loop.call_at

        def early_timer(when, callback, *args, **kwargs):
            if isinstance(getattr(callback, "__self__", None), asyncio.Timeout):
                return loop.call_soon(callback, *args, **kwargs)
            return call_at(when, callback, *args, **kwargs)

        monkeypatch.setattr(loop, "call_at", early_timer)

    async def run():
        if route == "refresh":
            return await scanner.sync_dialog(checkpoint)
        return await scanner.reconcile_tick()

    if timeout_origin == "external_cancel":
        task = asyncio.create_task(run())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert scanner.store.get_sync("scan_failures:account") is None
        assert scanner.store.get_sync("next_scan:account") is None
    elif timeout_origin == "provider" and route == "refresh":
        with pytest.raises(TimeoutError, match="early provider timeout"):
            await run()
    else:
        result = await run()
        if route == "refresh":
            assert result is False
        else:
            failed = timeout_origin == "provider"
            assert scanner.store.get_sync("scan_failures:account") == int(failed)
            assert scanner.store.get_sync("next_scan:account") == (clock()+30 if failed else None)

    method.assert_awaited_once()
    assert scanner.store.get_sync("scan:account") == cursor
    if checkpoint is not None:
        assert scanner.store.get_sync("dialog:1001") == checkpoint
    if timeout_origin != "provider":
        assert entered.is_set() and cancelled.is_set()
    assert scanner._scan_budget.get() is None
    assert not scanner.scan_lock.locked()
    assert all(not lock.locked() for lock in scanner._dialog_sync_locks.values())
