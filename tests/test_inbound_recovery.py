"""Recovery failure scenarios use a real temporary SQLite and synthetic sends."""

import asyncio
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from src.config import settings
from src.db import sessions
from src.db.inbound import InboundStore, StaleWork
from src.services.inbound_recovery import ProcessingContext, RecoveryService, current_processing, normalize_api_messages


@pytest.fixture
def clock():
    class Clock:
        now = int(time.time())

        def __call__(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    return Clock()


@pytest.fixture(autouse=True)
def full_scope_for_original_recovery_scenarios(monkeypatch):
    monkeypatch.setattr(settings, "inbound_recovery_scope", "all")
    monkeypatch.setattr(settings, "inbound_recovery_enabled", True)


@pytest.fixture
def store(clock):
    db = InboundStore(clock=clock)
    db.initialize("account")
    return db


def incoming(clock, mid="m1", **extra):
    return {"kind": "user", "mid": mid, "sender_id": "client", "text": "Эльбрус",
            "_event_time": clock(), **extra}


def make_job(store, clock, event=None):
    event = event or incoming(clock)
    store.persist("account", [event], "api" if event.get("_api_only") else "webhook")
    clock.advance(5)
    for rows in store.pending_batches():
        store.create_jobs("account", rows, [json.loads(row["payload"]) for row in rows])
    return store.claim_due()


def test_model_call_budget_survives_crash_and_exhaustion(store, clock):
    job = make_job(store, clock)
    _, revision = store.read_session(job['client_id'])
    assert store.reserve_model_attempt(job, revision) == 1
    store.record_model_attempt(job, dict(attempt=1, stage='invoke', reason='provider_error',
                               error_type='TimeoutError', timeout=120), 'a' * 32)
    clock.advance(181)
    store.recover(startup=True)
    clock.advance(120)
    job = store.claim_due()
    assert json.loads(job['model_attempt_log'])[0]['error_type'] == 'TimeoutError'
    assert store.reserve_model_attempt(job, revision) == 2
    assert store.reserve_model_attempt(job, revision) == 3
    assert store.reserve_model_attempt(job, revision) is None
    assert store.get_job(job['id'])['model_attempts'] == 3


def test_model_budget_reservation_rejects_changed_session_without_consuming(store, clock):
    job = make_job(store, clock)
    context = ProcessingContext(store, job)
    with store.connection() as conn:
        state, revision = sessions.read_row(conn, job['client_id'])
        state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
        store._write_own_session(conn, job['client_id'], state, revision)
    with pytest.raises(StaleWork):
        store.reserve_model_attempt(job, context.revision)
    assert store.get_job(job['id'])['model_attempts'] == 0


def service(store, clock, dispatch=None):
    from src.main import _finalize_recovery_reply, _split_reply
    channel = AsyncMock()
    channel.send_message.return_value = "outgoing-mid"
    recovery = RecoveryService(channel, dispatch or AsyncMock(), lambda events: events,
                               _finalize_recovery_reply, _split_reply, lambda client: False, store, clock)
    recovery.account = "account"
    recovery.refresh_client = AsyncMock(return_value=True)
    return recovery


async def plan_reply(event):
    context = current_processing.get()
    session = await sessions.get_session(event["sender_id"])
    session["history"].append({"role": "user", "content": event["text"]})
    await sessions.save_session(event["sender_id"], session)
    context.plan_reply("Программа Эльбруса")


def test_migration_additive_and_idempotent(store):
    with store.connection() as conn:
        assert "revision" in {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        assert "recovery_delivery_id" in {row[1] for row in conn.execute("PRAGMA table_info(pending_messages)")}
    InboundStore().initialize("account")


async def test_all_session_writers_preserve_revision(store):
    await sessions.save_session("client", {"history": [], "manager_last_at": None})
    state, revision = store.read_session("client")
    assert revision == 1
    await sessions.save_session("client", state)
    assert store.read_session("client")[1] == 2
    with store.connection() as conn:
        assert sessions.write_row(conn, "client", state, 1) is False
    assert store.read_session("client")[1] == 2


def test_webhook_api_dedup_and_richer_webhook(store, clock):
    api = incoming(clock, _api_only=True, _context_incomplete=True)
    assert len(store.persist("account", [api], "api")) == 1
    assert store.persist("account", [api], "api") == []
    webhook = incoming(clock, referral={"source": "ADS", "ad_id": "ad1"})
    assert store.persist("account", [webhook]) == []
    clock.advance(5)
    rows = store.pending_batches()[0]
    payload = json.loads(rows[0]["payload"])
    assert payload["referral"]["ad_id"] == "ad1"
    assert "_context_incomplete" not in payload
    assert rows[0]["version"] == 2
    store.persist("account", [api], "api")
    assert "referral" in json.loads(store.pending_batches()[0][0]["payload"])


def test_original_baseline_excludes_historical_but_not_offline_new(store, clock):
    before = incoming(clock, "old", _event_time=clock()-10)
    store.persist("account", [before])
    clock.advance(600)
    store.persist("account", [incoming(clock, "offline", _event_time=clock()-500)], "api")
    clock.advance(5)
    assert [row["mid"] for row in store.pending_batches()[0]] == ["offline"]


def test_five_seconds_of_silence_extends_for_each_new_mid(store, clock):
    store.persist("account", [incoming(clock)])
    clock.advance(4)
    store.persist("account", [incoming(clock, "m2")])
    assert store.pending_batches() == []
    clock.advance(4)
    store.persist("account", [incoming(clock, "m3")])
    assert store.pending_batches() == []
    clock.advance(4.9)
    assert store.pending_batches() == []
    clock.advance(.1)
    assert [row["mid"] for row in store.pending_batches()[0]] == ["m1", "m2", "m3"]


def test_quiet_gap_keeps_batches_separate_after_delayed_tick(store, clock):
    store.persist('account', [incoming(clock)])
    clock.advance(4)
    store.persist('account', [incoming(clock, 'm2')])
    clock.advance(6)
    store.persist('account', [incoming(clock, 'm3')])
    clock.advance(10)
    rows = store.pending_batches()[0]
    assert [row['mid'] for row in rows] == ['m1', 'm2']
    store.create_jobs('account', rows, [json.loads(row['payload']) for row in rows])
    assert [row['mid'] for row in store.pending_batches()[0]] == ['m3']


def test_same_mid_does_not_extend_silence_but_new_mid_does(store, clock):
    store.persist('account', [incoming(clock)])
    clock.advance(4)
    store.persist('account', [incoming(clock)], 'api')
    clock.advance(1)
    assert [row['mid'] for row in store.pending_batches()[0]] == ['m1']


def test_restart_preserves_last_receipt_deadline_and_identical_text(store, clock):
    store.persist('account', [incoming(clock)])
    clock.advance(4)
    store.persist('account', [incoming(clock, 'm2')])
    restarted = InboundStore(clock=clock)
    restarted.initialize('account')
    clock.advance(1)
    assert restarted.pending_batches() == []
    clock.advance(4)
    rows = restarted.pending_batches()[0]
    assert [row['mid'] for row in rows] == ['m1', 'm2']
    assert [json.loads(row['payload'])['text'] for row in rows] == ['Эльбрус', 'Эльбрус']


def test_quiet_windows_of_clients_are_independent(store, clock):
    store.persist('account', [incoming(clock, 'other', sender_id='other')])
    clock.advance(1)
    store.persist('account', [incoming(clock)])
    clock.advance(3)
    store.persist('account', [incoming(clock, 'm2')])
    clock.advance(1)
    assert [[row['mid'] for row in rows] for rows in store.pending_batches()] == [['other']]


def test_post_and_two_identical_questions_form_one_quiet_batch(store, clock):
    from src.channels.instagram import InstagramChannel
    post = incoming(clock, 'post', kind='user_shared_post', text='',
                    shared_sources=[{'id': '123456789', 'url': None}])
    store.persist('account', [post])
    for mid in ('question', 'repeat'):
        clock.advance(4)
        store.persist('account', [incoming(clock, mid, text='Хочу в тур')])
        assert store.pending_batches() == []
    clock.advance(5)
    rows = store.pending_batches()[0]
    merged = InstagramChannel.merge_events([json.loads(row['payload']) for row in rows])
    assert len(merged) == 1
    assert merged[0]['text'] == 'Хочу в тур\nХочу в тур'
    assert merged[0]['shared_sources'] == post['shared_sources']
    store.create_jobs('account', rows, merged)
    job = store.claim_due()
    assert set(json.loads(job['members'])) == {'post', 'question', 'repeat'}
    assert store.claim_due() is None


def test_claim_lease_and_old_claim_cannot_commit(store, clock):
    job = make_job(store, clock)
    clock.advance(179)
    store.recover()
    assert store.get_job(job["id"])["state"] == "processing"
    clock.advance(2)
    store.recover()
    assert store.get_job(job["id"])["state"] == "retry_wait"
    assert store.get_job(job["id"])["due"] == clock()+120
    with pytest.raises(StaleWork):
        store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])


def test_heartbeat_prevents_slow_model_duplicate(store, clock):
    job = make_job(store, clock)
    clock.advance(170)
    store.heartbeat(job)
    clock.advance(20)
    store.recover()
    assert store.claim_due() is None
    assert store.get_job(job["id"])["state"] == "processing"


def test_two_technical_delays_survive_reinstantiation(store, clock):
    job = make_job(store, clock)
    assert store.retry(job, "json_invalid")
    clock.advance(119)
    assert store.claim_due() is None
    clock.advance(1)
    job = InboundStore(clock=clock).claim_due()
    assert job["technical_attempts"] == 1
    assert store.retry(job, "provider_error")
    clock.advance(479)
    assert store.claim_due() is None
    clock.advance(1)
    job = store.claim_due()
    assert job["technical_attempts"] == 2
    assert not store.retry(job, "provider_error")
    assert store.get_job(job["id"])["state"] == "failed_final"


async def test_staging_has_no_fake_delivery_or_assistant_history(store, clock):
    from src.main import _send_or_queue
    from src.services.telegram_notify import TelegramNotifier
    job = make_job(store, clock)
    context = ProcessingContext(store, job)
    token = current_processing.set(context)
    try:
        notifier = TelegramNotifier()
        notifier._token, notifier._chat_ids = "synthetic", ["manager"]
        receipt = await notifier.notify_manager("client", context="Хочет Эльбрус")
        assert receipt.deferred is True
        assert await _send_or_queue("client", "Готовый ответ") == (False, None)
        assert store.read_session("client")[0]["history"] == []
        assert store.deliveries(job["id"]) == []
        assert context.session["escalation_count"] == 0
    finally:
        current_processing.reset(token)


async def test_real_receipt_appends_history_and_restart_does_not_regenerate(store, clock):
    job = make_job(store, clock)
    recovery = service(store, clock, plan_reply)
    await recovery.process(job)
    assert store.get_job(job["id"])["state"] == "done"
    assert [entry["role"] for entry in store.read_session("client")[0]["history"]] == ["user", "assistant"]
    assert store.own_mid("outgoing-mid")
    recovery.store.recover(startup=True)
    assert store.claim_due() is None
    recovery.channel.send_message.assert_awaited_once()


@pytest.mark.parametrize("status", ["unknown", "missing"])
async def test_unknown_send_blocks_remaining_parts_without_queue_replay(store, clock, status):
    async def draft(event):
        current_processing.get().plan_reply("А"*1500)
    job = make_job(store, clock)
    recovery = service(store, clock, draft)
    if status == "unknown":
        recovery.channel.send_message.side_effect = httpx.ReadTimeout("private url")
    else:
        recovery.channel.send_message.return_value = None
    await recovery.process(job)
    assert store.get_job(job["id"])["state"] == "unknown"
    assert recovery.channel.send_message.await_count == 1
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0
    store.recover(startup=True)
    assert store.claim_due() is None
    assert store.read_session("client")[0]["history"] == []


async def test_rate_limit_retry_reuses_saved_response_and_skips_sent_part(store, clock, monkeypatch):
    from src.exceptions import InstagramRateLimitError
    async def draft(event):
        current_processing.get().plan_reply("А"*1500)
    dispatch = AsyncMock(side_effect=draft)
    job = make_job(store, clock)
    recovery = service(store, clock, dispatch)
    recovery.channel.send_message.side_effect = ["part1", InstagramRateLimitError("limit", retry_after_seconds=60), "part2"]
    await recovery.process(job)
    assert [d["state"] for d in store.deliveries(job["id"])] == ["sent", "retry_wait"]
    clock.advance(59)
    await recovery.deliver(store.get_job(job["id"]))
    assert recovery.channel.send_message.await_count == 2
    clock.advance(1)
    await recovery.deliver(store.get_job(job["id"]))
    assert store.get_job(job["id"])["state"] == "done"
    assert dispatch.await_count == 1
    assert recovery.channel.send_message.await_count == 3
    assert len(store.read_session("client")[0]["history"]) == 2


async def test_manager_cancels_during_model_and_reset_does_not_revive(store, clock):
    async def draft(event):
        context = current_processing.get()
        store.persist("account", [{"kind": "manager", "client_id": "client", "mid": "manager-mid", "text": "Здравствуйте"}])
        context.plan_reply("Поздний ответ")
    job = make_job(store, clock)
    recovery = service(store, clock, draft)
    await recovery.process(job)
    assert store.get_job(job["id"])["state"] == "cancelled"
    recovery.channel.send_message.assert_not_awaited()
    state = await sessions.get_session("client")
    state["manager_last_at"] = None
    await sessions.save_session("client", state)
    assert store.claim_due() is None


async def test_stale_session_revision_does_not_overwrite_manager(store, clock):
    job = make_job(store, clock)
    context = ProcessingContext(store, job)
    await sessions.save_session("client", {"history": [], "client_name": "new", "manager_last_at": None})
    with pytest.raises(StaleWork):
        context.save_session({"history": [], "client_name": "stale"})
    assert (await sessions.get_session("client"))["client_name"] == "new"


async def test_one_silent_recheck_no_duplicate_notification_or_user_history(store, clock, monkeypatch):
    from src.services.telegram_notify import TelegramNotifier
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)
    async def draft(event):
        context = current_processing.get()
        context.outcome = "silent_model_handoff"
        state = await sessions.get_session("client")
        state["history"].append({"role": "user", "content": event["text"]})
        await sessions.save_session("client", state)
        context.plan_notification("Эльбрус", ["manager"])
    send = AsyncMock(return_value="tg-mid")
    monkeypatch.setattr(TelegramNotifier, "_send", send)
    job = make_job(store, clock)
    recovery = service(store, clock, draft)
    await recovery.process(job)
    assert store.get_job(job["id"])["state"] == "semantic_wait"
    clock.advance(119)
    assert store.claim_due() is None
    clock.advance(1)
    again = store.claim_due()
    assert again["semantic_used"] == 1
    await recovery.process(again)
    assert store.get_job(job["id"])["state"] == "done"
    assert send.await_count == 1
    state = store.read_session("client")[0]
    assert len(state["history"]) == 1
    assert state["escalation_count"] == 1


async def test_partial_telegram_only_retry_failed_destination_and_honest_phone_reply(store, clock, monkeypatch):
    from src.exceptions import TelegramError
    from src.services.telegram_notify import TelegramNotifier
    async def draft(event):
        context = current_processing.get()
        context.reply_kind = "phone"
        context.plan_notification("Контакт", ["one", "two"])
        context.plan_reply("Спасибо, ваш номер сохранён.")
    send = AsyncMock(side_effect=["tg1", TelegramError("connect", delivery_status="retry_wait"), "tg2"])
    monkeypatch.setattr(TelegramNotifier, "_send", send)
    job = make_job(store, clock)
    recovery = service(store, clock, draft)
    await recovery.process(job)
    recovery.channel.send_message.assert_not_awaited()
    clock.advance(60)
    await recovery.deliver(store.get_job(job["id"]))
    assert send.await_count == 3
    assert [call.args[1] for call in send.await_args_list] == ["one", "two", "two"]
    assert store.read_session("client")[0]["escalation_count"] == 1
    assert "передал ваш номер" in recovery.channel.send_message.await_args.args[1]


async def test_closed_original_window_does_not_restart_at_discovery(store, clock):
    event = incoming(clock)
    store.persist("account", [event])
    clock.advance(86401)
    rows = store.pending_batches()[0]
    store.create_jobs("account", rows, [event])
    job = store.claim_due()
    recovery = service(store, clock, plan_reply)
    await recovery.process(job)
    assert store.get_job(job["id"])["reason"] == "messaging_window_closed"
    recovery.channel.send_message.assert_not_awaited()


def test_sending_at_crash_becomes_unknown_not_pending(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    store.plan_instagram(job, ["one", "two"])
    delivery = store.deliveries(job["id"])[0]
    assert store.start_delivery(job, delivery, 10080)
    store.recover(startup=True)
    assert store.get_job(job["id"])["state"] == "unknown"
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["manager", "ambiguous_echo", "enrichment"])
def test_cancel_or_enrich_removes_legacy_projections(store, clock, kind):
    job = make_job(store, clock, incoming(clock, _api_only=True, _context_incomplete=True))
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    store.plan_instagram(job, ["stale"])
    if kind == "ambiguous_echo":
        store.start_delivery(job, store.deliveries(job["id"])[0], 10080)
    if kind == "enrichment":
        store.persist("account", [incoming(clock, story={"id": "story"})])
    else:
        store.persist("account", [{"kind": kind, "client_id": "client", "mid": kind, "text": "new"}])
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0


def test_future_retry_keeps_safe_projection_until_dispatch_is_due(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    store.plan_instagram(job, ["retry"])
    delivery = store.deliveries(job["id"])[0]
    store.start_delivery(job, delivery, 10080)
    store.record_delivery(delivery, "retry_wait", delay=60)
    assert not store.start_delivery(job, store.deliveries(job["id"])[0], 10080)
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 1


def test_rate_limit_after_concurrent_manager_does_not_requeue(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    store.plan_instagram(job, ["reply"])
    delivery = store.deliveries(job["id"])[0]
    store.start_delivery(job, delivery, 10080)
    store.persist("account", [{"kind": "manager", "client_id": "client", "mid": "mgr", "text": "manager"}])
    store.record_delivery(delivery, "retry_wait", delay=60)
    assert store.get_job(job["id"])["state"] == "cancelled"
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0


async def test_new_job_does_not_cancel_previous_saved_answer(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered", "reply": "answer A"}, [])
    other = make_job(store, clock, incoming(clock, "question-b"))
    state, revision = store.read_session("client")
    state["history"].append({"role": "user", "content": "question B"})
    store.commit_result(other, state, revision, {"outcome": "answered", "reply": "answer B"}, [])
    recovery = service(store, clock)
    await recovery.deliver(store.get_job(job["id"]))
    assert store.get_job(job["id"])["state"] == "done"
    assert recovery.channel.send_message.await_args.args[1] == "answer A"


def test_delayed_manager_event_never_shortens_pause(store, clock):
    store.persist("account", [{"kind": "manager", "client_id": "client", "mid": "new-manager", "text": "new", "_event_time": clock()+100}])
    store.persist("account", [{"kind": "manager", "client_id": "client", "mid": "old-manager", "text": "old", "_event_time": clock()+1}])
    actual = datetime.fromisoformat(store.read_session("client")[0]["manager_last_at"]).timestamp()
    assert actual == pytest.approx(clock()+100, abs=0.000001)


async def test_permanent_reject_first_part_blocks_remainder(store, clock):
    from src.exceptions import InstagramError
    async def draft(event):
        current_processing.get().plan_reply("А"*1500)
    job = make_job(store, clock)
    recovery = service(store, clock, draft)
    recovery.channel.send_message.side_effect = InstagramError("denied", delivery_status="blocked")
    await recovery.process(job)
    await recovery.deliver(store.get_job(job["id"]))
    assert recovery.channel.send_message.await_count == 1
    assert store.get_job(job["id"])["state"] == "blocked"


def test_live_registered_job_is_not_reclaimed_on_delayed_heartbeat(store, clock):
    job = make_job(store, clock)
    clock.advance(181)
    store.recover(live_jobs={job["id"]})
    assert store.get_job(job["id"])["state"] == "processing"


def test_api_normalization_does_not_invent_ads_or_media_id(store, clock):
    message = {"id": "api-mid", "from": {"id": "client"}, "message": "ВДП", "created_time":
               datetime.fromtimestamp(clock(), timezone.utc).isoformat(), "shares": {"data": [{"id": "not-media-id"}]}}
    event = normalize_api_messages([message], "client", "account", store, {"account"})[0]
    assert event["text"] == "ВДП" and event["_context_incomplete"]
    assert "referral" not in event and "shared_sources" not in event


async def test_restart_requires_fresh_conversation_before_send(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered", "reply": "saved"}, [])
    store.recover(startup=True)
    recovery = service(store, clock, AsyncMock(side_effect=AssertionError("no new model")))
    await recovery.deliver(store.get_job(job["id"]))
    recovery.channel.send_message.assert_not_awaited()
    assert store.get_job(job["id"])["state"] == "delivering"


async def test_webhook_storage_failure_is_503_and_does_not_reserve_mid(monkeypatch):
    import src.main as main
    monkeypatch.setattr(settings, "inbound_recovery_enabled", True)
    monkeypatch.setattr(main.instagram, "verify_signature", lambda *args: True)
    monkeypatch.setattr(main.instagram, "receive_message", AsyncMock(return_value=[{"kind": "user", "sender_id": "client", "mid": "storage-mid", "text": "ВДП"}]))
    recovery = AsyncMock()
    recovery.accept = lambda events: (_ for _ in ()).throw(OSError("disk full"))
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    request = AsyncMock()
    request.body.return_value = b'{}'
    request.json.return_value = {}
    request.headers = {}
    response = await main.receive_instagram_message(request)
    assert response.status_code == 503
    assert "storage-mid" not in main._processed_mids


async def test_known_own_echo_after_restart_and_ambiguous_intent(store, clock):
    from src.channels.instagram import InstagramChannel
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    store.plan_instagram(job, ["reply"])
    delivery = store.deliveries(job["id"])[0]
    store.start_delivery(job, delivery, 10080)
    channel = InstagramChannel()
    def echo(mid):
        return {"entry": [{"messaging": [{"recipient": {"id": "client"}, "message": {"mid": mid, "text": "reply", "is_echo": True}}]}]}
    events = await channel.receive_message(echo("early-mid"), recovery_store=store, merge=False)
    assert events[0]["kind"] == "ambiguous_echo"
    store.record_delivery(delivery, "sent", "confirmed-mid")
    channel = InstagramChannel()
    events = await channel.receive_message(echo("confirmed-mid"), recovery_store=store, merge=False)
    assert events[0]["kind"] == "own_echo"


async def test_api_scanner_does_not_call_model_and_discovers_new_client(store, clock):
    recovery = service(store, clock)
    recovery.channel.list_conversations.return_value = {"data": [{"id": "conversation", "client_id": "new-client"}], "after": None}
    recovery.channel.list_conversation_messages.return_value = {"data": [{"id": "fresh", "from": {"id": "new-client"},
        "created_time": datetime.fromtimestamp(clock()+1, timezone.utc).isoformat(), "message": "Эльбрус"}], "after": None}
    recovery._get = lambda method, *args: method(*args)
    await recovery.reconcile_tick()
    recovery.dispatch.assert_not_awaited()
    assert store.get_sync("complete_scan:account") is not None
    clock.advance(6)
    assert store.pending_batches()[0][0]["client_id"] == "new-client"


async def test_api_failure_keeps_cursor_and_webhook_queue_independent(store, clock):
    recovery = service(store, clock)
    recovery.channel.list_conversations.side_effect = ValueError("auth")
    recovery._get = lambda method, *args: method(*args)
    store.persist("account", [incoming(clock)])
    await recovery.reconcile_tick()
    assert store.get_sync("complete_scan:account") is None
    assert recovery._next_scan == clock()+30
    clock.advance(5)
    assert len(store.pending_batches()) == 1


async def test_reconcile_loop_preserves_large_retry_after(store, clock, monkeypatch):
    from src.exceptions import InstagramRateLimitError
    recovery = service(store, clock)
    recovery.channel.list_conversations.side_effect = InstagramRateLimitError("limit", retry_after_seconds=600)
    recovery._get = lambda method, *args: method(*args)
    monkeypatch.setattr("src.services.inbound_recovery.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await recovery.reconcile_loop()
    assert recovery._next_scan == clock()+600
    assert store.get_sync("next_scan:account") == clock()+600


async def test_invalid_cursor_restarts_scan_without_skipping_saved_work(store, clock):
    from src.exceptions import InstagramError
    recovery = service(store, clock)
    store.set_sync("scan:account", {"after": "expired", "dialogs": []})
    error = InstagramError("invalid cursor")
    error.category = "invalid_cursor"
    recovery.channel.list_conversations.side_effect = error
    recovery._get = lambda method, *args: method(*args)
    await recovery.reconcile_tick()
    assert store.get_sync("scan:account") == {"after": None, "dialogs": []}
    assert store.get_sync("complete_scan:account") is None


async def test_twenty_same_timestamp_with_next_is_explicit_gap(store, clock):
    recovery = service(store, clock)
    rows = [{"id": f"equal-{i}", "from": {"id": "client"}, "message": "ВДП", "created_time":
             datetime.fromtimestamp(clock(), timezone.utc).isoformat()} for i in range(20)]
    recovery.channel.list_conversation_messages.return_value = {"data": rows, "after": "older"}
    recovery._get = lambda method, *args: method(*args)
    assert not await recovery.sync_dialog({"id": "conv", "client_id": "client"})
    assert store.get_sync("dialog:client")["gap"] is True


def test_enrichment_keeps_owner_history_and_finite_budget(store, clock):
    job = make_job(store, clock, incoming(clock, _api_only=True, _context_incomplete=True))
    state = {"history": [{"role": "user", "content": "Эльбрус", "_inbound_job": job["id"]}]}
    store.commit_result(job, state, 0, {"outcome": "answered", "reply": "old draft"}, [])
    store.persist("account", [incoming(clock, story={"id": "real-story"})])
    updated = store.get_job(job["id"])
    assert updated["state"] == "retry_wait" and updated["technical_attempts"] == 1
    clock.advance(120)
    rebuilt = store.claim_due()
    assert rebuilt["id"] == job["id"]
    assert json.loads(rebuilt["payload"])["story"]["id"] == "real-story"
    assert ProcessingContext(store, rebuilt).base_history == []
    store.finish(rebuilt, "done", "test")
    other = make_job(store, clock, incoming(clock, "independent"))
    assert other["technical_attempts"] == 0


async def test_exact_http_receipt_resolves_early_echo_without_false_pause(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    store.plan_instagram(job, ["reply"])
    delivery = store.deliveries(job["id"])[0]
    store.start_delivery(job, delivery, 10080)
    store.persist("account", [{"kind": "ambiguous_echo", "client_id": "client", "mid": "actual-mid", "text": "reply"}])
    assert store.get_job(job["id"])["state"] == "unknown"
    store.record_delivery(delivery, "sent", "actual-mid")
    assert store.get_job(job["id"])["state"] == "delivering"
    assert store.read_session("client")[0].get("manager_last_at") is None


def test_early_echo_does_not_strand_other_jobs_of_same_client(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    other = make_job(store, clock, incoming(clock, "other-question"))
    store.plan_instagram(job, ["reply"])
    delivery = store.deliveries(job["id"])[0]
    store.start_delivery(job, delivery, 10080)
    store.persist("account", [{"kind": "ambiguous_echo", "client_id": "client", "mid": "actual", "text": "reply"}])
    store.record_delivery(delivery, "sent", "actual")
    assert store.get_job(other["id"])["state"] == "processing"


async def test_conversations_token_only_in_header_and_untrusted_next_not_followed(monkeypatch):
    from src.channels.instagram import InstagramChannel
    monkeypatch.setattr(settings, "instagram_access_token", "synthetic-token")
    monkeypatch.setattr(settings, "instagram_page_id", "page")
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-token"
        assert "access_token" not in request.url.params
        return httpx.Response(200, json={"data": [], "paging": {"next": "https://evil.invalid/steal", "cursors": {"after": "opaque"}}})
    factory = httpx.AsyncClient
    monkeypatch.setattr("src.channels.instagram.httpx.AsyncClient", lambda **kwargs: factory(transport=httpx.MockTransport(handler)))
    channel = InstagramChannel()
    page = await channel.list_conversations()
    assert page["after"] == "opaque"
    assert len(requests) == 1 and requests[0].url.host == "graph.facebook.com"


async def test_usage_headers_pause_only_reconcile_calls(monkeypatch):
    from src.channels.instagram import InstagramChannel
    from src.exceptions import InstagramRateLimitError
    monkeypatch.setattr(settings, "instagram_access_token", "synthetic")
    monkeypatch.setattr(settings, "instagram_page_id", "page")
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"data": []}, headers={"x-business-use-case-usage":
            json.dumps({"account": [{"call_count": 90, "total_time": 5}]})})
    factory = httpx.AsyncClient
    monkeypatch.setattr("src.channels.instagram.httpx.AsyncClient", lambda **kwargs: factory(transport=httpx.MockTransport(handler)))
    channel = InstagramChannel()
    await channel.list_conversations()
    with pytest.raises(InstagramRateLimitError):
        await channel.list_conversations()
    assert count == 1


@pytest.mark.parametrize("kind,expected", [("file", "user_non_text"), ("product", "user_non_text"),
                                         ("unsupported_type", "user_silent_handoff"),
                                         ("story_mention", "user_silent_handoff"), ("sticker", "ignored"), ("gif", "ignored")])
def test_api_special_attachments_keep_human_or_ignore_routes(store, clock, kind, expected):
    message = {"id": "api-special", "from": {"id": "client"}, "created_time":
               datetime.fromtimestamp(clock(), timezone.utc).isoformat(), "attachments": {"data": [{"type": kind}]}}
    event = normalize_api_messages([message], "client", "account", store, {"account"})[0]
    assert event["kind"] == expected


def test_confirmed_unsupported_type_precedes_conflicting_mime(store, clock):
    message = {'id': 'api-unsupported', 'from': {'id': 'client'},
        'created_time': datetime.fromtimestamp(clock(), timezone.utc).isoformat(),
        'attachments': {'data': [{'type': 'unsupported_type', 'mime_type': 'image/gif'}]}}
    event = normalize_api_messages([message], 'client', 'account', store, {'account'})[0]
    assert event['kind'] == 'user_silent_handoff' and event['silent_reason'] == 'unsupported_type'


def test_api_known_photo_video_audio_keep_companion_keys(store, clock, monkeypatch):
    monkeypatch.setattr(settings, "voice_media_enabled", True)
    monkeypatch.setattr(settings, "image_media_enabled", True)
    message = {"id": "api-media", "from": {"id": "client"}, "created_time":
        datetime.fromtimestamp(clock(), timezone.utc).isoformat(), "attachments": {"data": [
            {"image_data": {"url": "https://scontent.cdninstagram.com/photo.jpg"}},
            {"video_data": {"url": "https://scontent.cdninstagram.com/video.mp4"}},
            {"audio_data": {"url": "https://scontent.cdninstagram.com/audio.mp4"}}]}}
    event = normalize_api_messages([message], "client", "account", store, {"account"})[0]
    assert len(event["voice_parts"]) == 1
    assert event["visual_parts"][0]["types"] == ["image", "video"]
    assert len(event["visual_parts"][0]["urls"]) == 2


async def test_legacy_pending_is_adopted_once_without_model(store, clock, monkeypatch):
    from src.db.pending_messages import enqueue_pending
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)
    when = datetime.fromtimestamp(clock(), timezone.utc).isoformat()
    await enqueue_pending("client", "Готовый ответ", when)
    store.import_legacy_pending()
    store.import_legacy_pending()
    jobs = store.delivery_jobs()
    assert len(jobs) == 1
    recovery = service(store, clock, AsyncMock(side_effect=AssertionError("model must not run")))
    await recovery.deliver(jobs[0])
    recovery.dispatch.assert_not_awaited()
    assert recovery.channel.send_message.await_args.args == ("client", "Готовый ответ")
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0


def test_payload_cleanup_does_not_delete_unfinished_or_unknown(store, clock):
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered", "reply": "saved"}, [])
    store.plan_instagram(job, ["saved"])
    delivery = store.deliveries(job["id"])[0]
    store.start_delivery(job, delivery, 10080)
    store.record_delivery(delivery, "unknown")
    clock.advance(91*86400)
    store.cleanup()
    assert store.get_job(job["id"])["result"] is not None
    assert store.deliveries(job["id"])[0]["payload"] == "saved"


async def test_admin_diagnostics_are_protected_and_public_health_has_no_counts(monkeypatch):
    import src.main as main
    from fastapi import HTTPException
    monkeypatch.setattr(settings, "admin_api_token", "synthetic-admin")
    monkeypatch.setattr(settings, "inbound_recovery_enabled", False)
    with pytest.raises(HTTPException):
        await main.inbound_recovery_status("wrong")
    assert await main.inbound_recovery_status("synthetic-admin") == {"enabled": False}
    assert "inbound_recovery" not in await main.health()


async def test_disabled_pending_worker_records_linked_receipt_before_reenable(store, clock, monkeypatch):
    import src.main as main
    from src.channels.instagram import InstagramChannel
    monkeypatch.setattr(settings, "inbound_recovery_enabled", False)
    job = make_job(store, clock)
    store.commit_result(job, {"history": []}, 0, {"outcome": "answered", "reply": "saved"}, [])
    store.plan_instagram(job, ["saved"])
    with store.connection() as conn:
        conn.execute("UPDATE pending_messages SET retry_at='2000-01-01T00:00:00+00:00'")
    recovery = service(store, clock)
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    monkeypatch.setattr("src.main.asyncio.sleep", AsyncMock(side_effect=[None, asyncio.CancelledError]))
    with pytest.raises(asyncio.CancelledError):
        await main._pending_messages_worker()
    assert recovery.channel.send_message.await_count == 1
    assert store.get_job(job["id"])["state"] == "done"
    assert InstagramChannel().is_own_message("outgoing-mid")
    store.recover(startup=True)
    assert store.delivery_jobs() == []


async def test_featureoff_normal_send_keeps_existing_own_mid_journal(store, monkeypatch):
    from src.channels.instagram import InstagramChannel
    monkeypatch.setattr(settings, "instagram_access_token", "synthetic")
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"message_id": "while-disabled"}))
    monkeypatch.setattr("src.channels.instagram.httpx.AsyncClient", lambda **kwargs: factory(transport=transport))
    await InstagramChannel().send_message("client", "Обычный ответ")
    assert InstagramChannel().is_own_message("while-disabled")


@pytest.mark.parametrize("journal_failure", [False, True])
async def test_featureoff_unknown_receipt_is_not_blindly_queued(store, monkeypatch, journal_failure):
    import src.main as main
    monkeypatch.setattr(settings, "instagram_access_token", "synthetic")
    factory = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    monkeypatch.setattr("src.channels.instagram.httpx.AsyncClient", lambda **kwargs: factory(transport=transport))
    if journal_failure:
        def broken_commit(*args):
            raise OSError("journal unavailable after send")
        monkeypatch.setattr(InboundStore, "finish_legacy_failure", broken_commit)
    assert await main._send_or_queue("client", "uncertain") == (False, None)
    assert store.unresolved_send("client")
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0


async def test_delivery_backlog_cannot_starve_new_webhook_work(store, clock, monkeypatch):
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)
    for index in range(9):
        job = make_job(store, clock, incoming(clock, f"backlog-{index}"))
        state, revision = store.read_session("client")
        store.commit_result(job, state, revision, {"outcome": "answered", "reply": "old"}, [])
    store.recover(startup=True)
    recovery = service(store, clock, AsyncMock(side_effect=plan_reply))
    gate = asyncio.Event()
    async def failing_refresh(client):
        await gate.wait()
        return False
    recovery.refresh_client = AsyncMock(side_effect=failing_refresh)
    store.persist("account", [incoming(clock, "new-work", sender_id="new-client")])
    clock.advance(5)
    await recovery.tick()
    assert len(recovery.delivery_ids) <= 2
    for _ in range(6):
        await asyncio.sleep(0)
    assert recovery.dispatch.await_count == 1
    assert recovery.channel.send_message.await_args.args[0] == "new-client"
    gate.set()
    await asyncio.gather(*list(recovery.active.values()))
    with store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM inbound_jobs WHERE reason='fresh_context_unavailable' AND due>?", (clock(),)).fetchone()[0] == 2


def test_legacy_success_covers_only_explicit_input_mids_on_reenable(store, clock):
    event = incoming(clock)
    job = make_job(store, clock, event)
    store.record_legacy_receipt("client", "legacy answer", "legacy-receipt", event, "account")
    assert store.get_job(job["id"])["outcome"] == "legacy_covered"
    store.recover(startup=True)
    assert store.claim_due() is None
    assert store.persist("account", [event], "api") == []
    unrelated = make_job(store, clock, incoming(clock, "unanswered"))
    assert unrelated["state"] == "processing"


async def test_incomplete_dialog_does_not_prevent_scanning_next_dialog(store, clock):
    recovery = service(store, clock)
    recovery.channel.list_conversations.return_value = {"data": [
        {"id": "ambiguous", "participants": {"data": []}}, {"id": "valid", "client_id": "client"}], "after": None}
    recovery.channel.list_conversation_messages.return_value = {"data": [], "after": None}
    recovery._get = lambda method, *args: method(*args)
    await recovery.reconcile_tick()
    recovery.channel.list_conversation_messages.assert_awaited_once_with("valid")
    assert store.get_sync("dialog_gap:ambiguous")["reason"] == "incomplete_identity"
    assert store.get_sync("dialog:client") is not None
    assert store.get_sync("complete_scan:account") is None


async def test_repeated_crashes_exhaust_budget_and_notify_without_fourth_model_run(store, clock, monkeypatch):
    from src.services.telegram_notify import TelegramNotifier
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)
    monkeypatch.setattr(settings, "telegram_bot_token", "synthetic")
    monkeypatch.setattr(settings, "telegram_manager_chat_id", "manager")
    for name in ("telegram_secondary_chat_id", "telegram_tertiary_chat_id", "telegram_extra_chat_id"):
        monkeypatch.setattr(settings, name, "")
    notify = AsyncMock(return_value="801")
    monkeypatch.setattr(TelegramNotifier, "_send", notify)
    job = make_job(store, clock)
    for delay in (120, 480):
        clock.advance(181)
        store.recover(startup=True)
        clock.advance(delay)
        job = store.claim_due()
    clock.advance(181)
    store.recover(startup=True)
    job = store.claim_due()
    assert job["launch"] == "failure" and job["technical_attempts"] == 2
    recovery = service(store, clock, AsyncMock(side_effect=AssertionError("fourth model run")))
    await recovery.process(job)
    recovery.dispatch.assert_not_awaited()
    assert notify.await_count == 1
    assert store.get_job(job["id"])["state"] == "failed_final"
