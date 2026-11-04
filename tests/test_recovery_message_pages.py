"""Coverage windows use fake Graph pages, actual SQLite and no external sends."""
from copy import deepcopy
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.exceptions import InstagramError
from src.services.inbound_recovery import RecoveryService, normalize_api_messages
from tests.test_inbound_recovery import make_job, service
from tests.test_recovery_scan_budget import scanner as scanner, clock as clock


def msg(mid, when, sender="1001"):
    return {"id": mid, "created_time": datetime.fromtimestamp(when, timezone.utc).isoformat(),
            "from": {"id": sender}, "message": "Эльбрус"}


def seed(scanner, clock, through):
    scanner.store.set_sync("dialog:1001", {"id": "known", "client_id": "1001", "checked_at": clock()-100,
                                         "through": through, "gap": False})


def pages(scanner, mapping):
    async def read(dialog_id, after=None):
        assert dialog_id == "known"
        value = mapping[after]
        if isinstance(value, BaseException):
            raise value
        return deepcopy(value)
    scanner.channel.list_conversation_messages.side_effect = read


def event_count(scanner):
    with scanner.store.connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM inbound_events").fetchone()[0]


async def test_all_twenty_one_messages_are_normalized_and_do_not_create_false_gap(scanner, clock):
    base = clock()
    rows = [msg(f"m-{i}", base+i) for i in range(21)]
    assert len(normalize_api_messages(rows, "1001", "account", scanner.store, {"account"})) == 21
    seed(scanner, clock, base+5)
    pages(scanner, {None: {"data": rows, "after": "older"}})
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True
    assert event_count(scanner) == 21
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is False and checkpoint["through"] == base+20
    scanner.channel.list_conversation_messages.assert_awaited_once_with("known")


async def test_equal_timestamps_and_overlap_do_not_skip_new_mid_at_boundary(scanner, clock):
    base = clock()
    seed(scanner, clock, base+20)
    pages(scanner, {None: {"data": [msg("new", base+30), msg("equal-a", base+20)], "after": "a"},
                    "a": {"data": [msg("equal-a", base+20), msg("equal-b", base+20), msg("old", base+19)], "after": "unused"}})
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True
    assert event_count(scanner) == 4
    assert scanner.channel.list_conversation_messages.await_count == 2
    scanner.channel.list_conversation_messages.assert_any_await("known", "a")


async def test_budget_continuation_survives_restart_and_head_is_refreshed(scanner, clock, monkeypatch):
    base = clock()
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    seed(scanner, clock, base+10)
    mapping = {None: {"data": [msg("m120", base+120), msg("m110", base+110)], "after": "a"},
               "a": {"data": [msg("m100", base+100), msg("m90", base+90)], "after": "b"},
               "b": {"data": [msg("m40", base+40), msg("m5", base+5)], "after": "unused"}}
    pages(scanner, mapping)
    await scanner.reconcile_tick()
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is True and checkpoint["through"] == base+10
    assert checkpoint["pending"]["after"] == "b" and event_count(scanner) == 4
    assert scanner.store.get_sync("scan_failures:account") == 0
    restarted = service(scanner.store, clock)
    restarted.channel.list_conversations.return_value = {"data": [], "after": None}
    pages(restarted, mapping)
    clock.advance(120)
    await restarted.reconcile_tick()
    assert [call.args for call in restarted.channel.list_conversation_messages.await_args_list] == [("known",), ("known", "b")]
    checkpoint = restarted.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is False and checkpoint["through"] == base+120
    assert not checkpoint.get("pending") and event_count(scanner) == 6
    restarted.dispatch.assert_not_awaited()


async def test_disjoint_new_head_does_not_jump_over_unread_middle(scanner, clock, monkeypatch):
    base = clock()
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    seed(scanner, clock, base+10)
    mapping = {None: {"data": [msg("m200", base+200), msg("m190", base+190)], "after": "a"},
               "a": {"data": [msg("m180", base+180), msg("m170", base+170)], "after": "b"},
               "b": {"data": [msg("m20", base+20), msg("m5", base+5)], "after": None},
               "new": {"data": [msg("m250", base+250), msg("m190", base+190)], "after": None}}
    pages(scanner, mapping)
    await scanner.reconcile_tick()
    mapping[None] = {"data": [msg("m400", base+400), msg("m300", base+300)], "after": "new"}
    clock.advance(120)
    await scanner.reconcile_tick()
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is True and checkpoint["through"] == base+200
    assert checkpoint["pending"]["after"] == "new"
    clock.advance(120)
    await scanner.reconcile_tick()
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is False and checkpoint["through"] == base+400
    with scanner.store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM inbound_events WHERE mid='m250'").fetchone()[0] == 1


async def test_crash_after_events_before_checkpoint_replays_without_duplicate(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    pages(scanner, {None: {"data": [msg("m1", base+2)], "after": None}})
    original = scanner.store.set_sync
    def fail_checkpoint(key, value):
        if key == "dialog:1001":
            raise RuntimeError("synthetic crash")
        original(key, value)
    monkeypatch.setattr(scanner.store, "set_sync", fail_checkpoint)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        await scanner.sync_dialog({"id": "known", "client_id": "1001"})
    assert event_count(scanner) == 1
    monkeypatch.setattr(scanner.store, "set_sync", original)
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True
    assert event_count(scanner) == 1


async def test_overlapping_new_head_extends_pending_window(scanner, clock, monkeypatch):
    base = clock()
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    seed(scanner, clock, base+10)
    mapping = {None: {"data": [msg("m200", base+200), msg("m190", base+190)], "after": "a"},
               "a": {"data": [msg("m180", base+180)], "after": "b"},
               "b": {"data": [msg("m5", base+5)], "after": None}}
    pages(scanner, mapping)
    await scanner.reconcile_tick()
    mapping[None] = {"data": [msg("m300", base+300), msg("m190", base+190)], "after": "unused"}
    clock.advance(120)
    await scanner.reconcile_tick()
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is False and checkpoint["through"] == base+300
    assert not checkpoint.get("pending")
    assert [call.args for call in scanner.channel.list_conversation_messages.await_args_list][-2:] == [("known",), ("known", "b")]
    assert event_count(scanner) == 5


async def test_dirty_older_page_survives_restart_and_prevents_false_coverage(scanner, clock, monkeypatch):
    base = clock()
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    seed(scanner, clock, base+10)
    mapping = {None: {"data": [msg("m200", base+200), msg("m190", base+190)], "after": "a"},
               "a": {"data": [msg("m180", base+180), {"id": "bad", "created_time": "invalid"}], "after": "b"},
               "b": {"data": [msg("m5", base+5)], "after": None}}
    pages(scanner, mapping)
    await scanner.reconcile_tick()
    assert scanner.store.get_sync("dialog:1001")["pending"]["dirty"] is True
    restarted = service(scanner.store, clock)
    restarted.channel.list_conversations.return_value = {"data": [], "after": None}
    pages(restarted, mapping)
    clock.advance(120)
    await restarted.reconcile_tick()
    checkpoint = restarted.store.get_sync("dialog:1001")
    assert checkpoint["gap"] is True and checkpoint["through"] == base+10
    assert not checkpoint.get("pending")
    assert event_count(scanner) == 4
    assert [call.args for call in restarted.channel.list_conversation_messages.await_args_list] == [("known",), ("known", "b")]


@pytest.mark.parametrize("malformed", [{"id": "bad", "created_time": "bad", "from": {"id": "1001"}},
    {"id": "bad", "created_time": False, "from": {"id": "1001"}},
    {"id": ["bad"], "created_time": "2026-10-18T00:00:00Z", "from": {"id": "1001"}},
    {"created_time": "2026-10-18T00:00:00Z", "from": {"id": "1001"}},
    {"id": "bad", "created_time": "2026-10-18T00:00:00Z", "from": {"id": "foreign"}}])
async def test_incomplete_identity_does_not_advance_through(scanner, clock, malformed):
    base = clock()
    seed(scanner, clock, base)
    pages(scanner, {None: {"data": [msg("valid", base+2), malformed], "after": None}})
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is False
    assert scanner.store.get_sync("dialog:1001")["through"] == base


async def test_invalid_message_cursor_does_not_reset_global_discovery(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 2)
    scanner.store.set_sync("scan:account", {"after": "global-cursor", "dialogs": []})
    invalid = InstagramError("synthetic")
    invalid.category = "invalid_cursor"
    pages(scanner, {None: {"data": [msg("m1", base+2)], "after": "expired"}, "expired": invalid})
    await scanner.reconcile_tick()
    assert scanner.store.get_sync("scan:account")["after"] == "global-cursor"
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["through"] == base and checkpoint["gap"] is True and not checkpoint.get("pending")
    assert scanner.store.get_sync("scan_failures:account") == 0


async def test_manager_on_head_cancels_job_while_old_coverage_is_pending(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    job = make_job(scanner.store, clock, {"kind": "user", "mid": "job", "sender_id": "1001",
                                        "text": "Вопрос", "_event_time": base+1})
    pages(scanner, {None: {"data": [msg("manager", clock()+1, "account")], "after": "older"}})
    await scanner.reconcile_tick()
    assert scanner.store.get_job(job["id"])["state"] == "cancelled"
    assert scanner.store.get_sync("dialog:1001")["gap"] is True


async def test_message_after_uses_known_graph_host_and_token_header(monkeypatch):
    monkeypatch.setattr(settings, "instagram_access_token", "synthetic-token")
    factory, requests = httpx.AsyncClient, []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"data": []})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: factory(transport=httpx.MockTransport(respond), **kw))
    await InstagramChannel().list_conversation_messages("known", "opaque-cursor")
    request = requests[0]
    assert request.url.host == "graph.facebook.com" and request.url.params["after"] == "opaque-cursor"
    assert request.headers["authorization"] == "Bearer synthetic-token" and "access_token" not in request.url.params


async def test_repeated_cursor_stays_incomplete_without_looping(scanner, clock):
    base = clock()
    seed(scanner, clock, base)
    mapping = {None: {"data": [msg("m20", base+20)], "after": "a"},
               "a": {"data": [msg("m10", base+10)], "after": "a"}}
    pages(scanner, mapping)
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is False
    assert scanner.channel.list_conversation_messages.await_count == 2
    checkpoint = scanner.store.get_sync("dialog:1001")
    assert checkpoint["through"] == base and checkpoint["gap"] and not checkpoint.get("pending")
    mapping["a"] = {"data": [msg("older", base-1)], "after": None}
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True


async def test_failure_on_older_page_preserves_cursor_and_allows_safe_retry(scanner, clock):
    base = clock()
    seed(scanner, clock, base)
    mapping = {None: {"data": [msg("m20", base+20), msg("m10", base+10)], "after": "a"},
               "a": httpx.ReadTimeout("synthetic")}
    pages(scanner, mapping)
    with pytest.raises(httpx.ReadTimeout):
        await scanner.sync_dialog({"id": "known", "client_id": "1001"})
    assert scanner.store.get_sync("dialog:1001")["pending"]["after"] == "a"
    mapping["a"] = {"data": [msg("older", base-1)], "after": None}
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True
    assert event_count(scanner) == 3


async def test_direct_delivery_refresh_has_own_request_limit(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    monkeypatch.setattr(settings, "instagram_reconcile_max_requests", 1)
    pages(scanner, {None: {"data": [msg("m20", base+20)], "after": "a"}})
    assert await RecoveryService.refresh_client(scanner, "1001") is False
    scanner.channel.list_conversation_messages.assert_awaited_once_with("known")
    assert scanner.store.get_sync("dialog:1001")["pending"]["after"] == "a"


async def test_direct_refresh_deadline_preserves_unread_page(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    now = [0.0]
    monkeypatch.setattr("src.services.inbound_recovery.time", SimpleNamespace(monotonic=lambda: now[0]))
    async def read(dialog_id, after=None):
        now[0] = settings.instagram_reconcile_deadline_seconds+1
        return {"data": [msg("m20", base+20)], "after": "a"}
    scanner.channel.list_conversation_messages.side_effect = read
    assert await RecoveryService.refresh_client(scanner, "1001") is False
    assert scanner.channel.list_conversation_messages.await_count == 1
    assert scanner.store.get_sync("dialog:1001")["pending"]["after"] == "a"


async def test_concurrent_syncs_are_serialized_without_reusing_delivery_lock(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    pages(scanner, {None: {"data": [msg("m20", base+20)], "after": None}})
    entered, release = asyncio.Event(), asyncio.Event()
    original = scanner._sync_dialog_pages
    active, maximum = 0, 0
    async def track(dialog, client):
        nonlocal active, maximum
        active += 1
        maximum = max(active, maximum)
        try:
            entered.set()
            await release.wait()
            return await original(dialog, client)
        finally:
            active -= 1
    monkeypatch.setattr(scanner, "_sync_dialog_pages", track)
    async def delivery():
        async with scanner.client_locks.setdefault("1001", asyncio.Lock()):
            return await RecoveryService.refresh_client(scanner, "1001")
    first = asyncio.create_task(delivery())
    await entered.wait()
    second = asyncio.create_task(scanner.sync_dialog({"id": "known", "client_id": "1001"}))
    release.set()
    assert await asyncio.wait_for(asyncio.gather(first, second), 5) == [True, True]
    assert maximum == 1 and event_count(scanner) == 1


async def test_crash_after_older_page_replays_same_cursor_not_skipping_events(scanner, clock, monkeypatch):
    base = clock()
    seed(scanner, clock, base)
    pages(scanner, {None: {"data": [msg("m30", base+30)], "after": "a"},
                    "a": {"data": [msg("m20", base+20)], "after": "b"},
                    "b": {"data": [msg("m0", base-1)], "after": None}})
    original = scanner.store.set_sync
    def fail_checkpoint(key, value):
        if key == "dialog:1001" and value.get("pending", {}).get("after") == "b":
            raise RuntimeError("synthetic checkpoint crash")
        original(key, value)
    monkeypatch.setattr(scanner.store, "set_sync", fail_checkpoint)
    with pytest.raises(RuntimeError, match="synthetic checkpoint crash"):
        await scanner.sync_dialog({"id": "known", "client_id": "1001"})
    assert event_count(scanner) == 2 and scanner.store.get_sync("dialog:1001")["pending"]["after"] == "a"
    monkeypatch.setattr(scanner.store, "set_sync", original)
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True
    assert event_count(scanner) == 3


async def test_bad_sender_duplicate_mid_is_not_complete_coverage(scanner, clock):
    base = clock()
    seed(scanner, clock, base)
    pages(scanner, {None: {"data": [msg("duplicate", base+1), msg("duplicate", base+1, "foreign")], "after": None}})
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is False
    assert scanner.store.get_sync("dialog:1001")["through"] == base


async def test_unsupported_media_is_recorded_without_inventing_content(scanner, clock):
    base = clock()
    seed(scanner, clock, base)
    row = msg("unsupported", base+1)
    row.update(message="", is_unsupported=True)
    pages(scanner, {None: {"data": [row], "after": None}})
    assert await scanner.sync_dialog({"id": "known", "client_id": "1001"}) is True
    with scanner.store.connection() as conn:
        import json
        event = json.loads(conn.execute("SELECT payload FROM inbound_events WHERE mid='unsupported'").fetchone()[0])
    assert "unsupported_media" in event["_source_issues"] and event["_context_incomplete"] is True
    scanner.dispatch.assert_not_awaited()
