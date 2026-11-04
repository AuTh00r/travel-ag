"""Missed webhook through scanner, actual business dispatch and durable restarts."""
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import httpx

from src.config import settings
from src.db.inbound import InboundStore
from src.services.inbound_recovery import RecoveryService
from tests.test_recovery_pipeline import pipeline as pipeline
from tests.model_responses import manager_data, model_response


@pytest.mark.parametrize("crash_after_claim", [False, True])
async def test_api_only_message_survives_restart_and_late_webhook(pipeline, monkeypatch, crash_after_claim):
    client, mid, account = "1001", "missed-webhook-mid", "account"
    monkeypatch.setattr(settings, "inbound_recovery_scope", "allowlist")
    monkeypatch.setattr(settings, "inbound_recovery_client_ids", client)
    main = pipeline.main
    list_dialogs = AsyncMock(return_value={"data": [{"id": "dialog", "client_id": client}], "after": None})
    list_messages = AsyncMock()
    monkeypatch.setattr(type(main.instagram), "list_conversations", list_dialogs)
    monkeypatch.setattr(type(main.instagram), "list_conversation_messages", list_messages)

    def restart():
        store = InboundStore(clock=lambda: pipeline.now[0])
        recovery = RecoveryService(main.instagram, main._dispatch_user_event, main._merge_recovery_events,
            main._finalize_recovery_reply, main._split_reply, lambda _: False, store, lambda: pipeline.now[0])
        recovery.account = account
        monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
        recovery.start()
        return recovery

    recovery = restart()
    pipeline.now[0] += 1
    event_time = pipeline.now[0]
    list_messages.return_value = {"data": [{"id": mid, "from": {"id": client},
        "to": {"data": [{"id": account}]},
        "created_time": datetime.fromtimestamp(event_time, timezone.utc).isoformat(),
        "message": "Пришлите программу Эльбруса"}], "after": None}
    await recovery.reconcile_tick()
    pipeline.invoke.assert_not_awaited()
    pipeline.send.assert_not_awaited()
    assert recovery.store.get_sync("dialog:"+client)["gap"] is False
    first_scan_reads = list_messages.await_count
    response = pipeline.invoke.return_value
    reads_at_model = []

    async def model_result(messages, **kwargs):
        assert list_messages.await_count > first_scan_reads
        reads_at_model.append(list_messages.await_count)
        humans = [str(message.content) for message in messages if message.type == "human"]
        assert sum("Пришлите программу Эльбруса" in text for text in humans) == 1
        return response

    async def send_result(recipient, text):
        assert recipient == client and "Программа Эльбруса" in text
        assert list_messages.await_count > reads_at_model[-1]
        return "instagram-out"

    pipeline.invoke.side_effect = model_result
    pipeline.send.side_effect = send_result

    pipeline.now[0] += 5
    if crash_after_claim:
        for rows in recovery.store.pending_batches():
            recovery.store.create_jobs(account, rows, recovery.merge([json.loads(row["payload"]) for row in rows]))
        interrupted = recovery.store.claim_due()
        assert interrupted is not None
        pipeline.now[0] = interrupted["lease_until"]+1

    recovery = restart()
    if crash_after_claim:
        waiting = recovery.store.get_job(interrupted["id"])
        assert waiting["state"] == "retry_wait" and waiting["technical_attempts"] == 1
        assert waiting["due"] == pipeline.now[0]+120
        await recovery.tick()
        assert not recovery.active
        pipeline.now[0] += 120

    await recovery.tick()
    await asyncio.gather(*list(recovery.active.values()))
    pipeline.invoke.assert_awaited_once()
    pipeline.send.assert_awaited_once()
    pipeline.notify.assert_not_awaited()
    # Recovered work uses real sync_dialog, rather than a mocked freshness result.
    assert list_messages.await_count >= 2
    with recovery.store.connection() as conn:
        job = conn.execute("SELECT * FROM inbound_jobs WHERE client_id=?", (client,)).fetchone()
        assert job["state"] == "done" and job["outcome"] == "answered"
        assert conn.execute("SELECT COUNT(*) FROM inbound_jobs").fetchone()[0] == 1
    deliveries = recovery.store.deliveries(job["id"])
    assert len(deliveries) == 1
    assert (deliveries[0]["state"], deliveries[0]["receipt"], deliveries[0]["attempts"]) == ("sent", "instagram-out", 1)
    pipeline.send.assert_awaited_once_with(client, deliveries[0]["payload"])
    assert [entry["role"] for entry in recovery.store.read_session(client)[0]["history"]] == ["user", "assistant"]
    assert "Пришлите программу Эльбруса" in recovery.store.read_session(client)[0]["history"][0]["content"]

    recovery = restart()
    await recovery.reconcile_tick()
    recovery.accept([{"kind": "user", "sender_id": client, "mid": mid,
        "text": "Пришлите программу Эльбруса", "_event_time": event_time}], "webhook")
    pipeline.now[0] += 5
    await recovery.tick()
    await asyncio.gather(*list(recovery.active.values()))
    pipeline.invoke.assert_awaited_once()
    pipeline.send.assert_awaited_once()
    with recovery.store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM inbound_jobs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM inbound_events WHERE mid=?", (mid,)).fetchone()[0] == 1
        sources = conn.execute("SELECT sources FROM inbound_events WHERE mid=?", (mid,)).fetchone()[0]
        assert set(json.loads(sources)) == {"api", "webhook"}
    assert recovery.store.get_job(job["id"])["state"] == "done"
    assert recovery.store.deliveries(job["id"]) == deliveries
    assert [entry["role"] for entry in recovery.store.read_session(client)[0]["history"]] == ["user", "assistant"]


def restart_business_pipeline(pipeline, monkeypatch, job):
    """Keep SQLite and real freshness/dispatch; replace only the Graph boundary."""
    main = pipeline.main
    payload = json.loads(job["payload"])
    client = job["client_id"]
    graph = AsyncMock(return_value={"data": [{"id": "pipeline-mid", "from": {"id": client},
        "created_time": datetime.fromtimestamp(payload["_original_time"], timezone.utc).isoformat(),
        "message": payload["text"]}], "after": None})
    monkeypatch.setattr(type(main.instagram), "list_conversation_messages", graph)
    recovery = RecoveryService(main.instagram, main._dispatch_user_event, main._merge_recovery_events,
        main._finalize_recovery_reply, main._split_reply, lambda _: False,
        InboundStore(clock=lambda: pipeline.now[0]), lambda: pipeline.now[0])
    recovery.account = "account"
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    recovery.start()
    recovery.store.set_sync("dialog:"+client, {"id": "synthetic-dialog", "client_id": client,
        "through": payload["_original_time"], "checked_at": pipeline.now[0], "gap": False})
    return recovery, graph


async def test_business_partial_reply_restart_reuses_exact_saved_parts(pipeline, monkeypatch):
    from src.exceptions import InstagramRateLimitError

    pipeline.invoke.return_value = model_response("Программа Эльбруса. "+"Маршрут. "*160)
    pipeline.send.side_effect = ["part-one", InstagramRateLimitError("synthetic", retry_after_seconds=60), "part-two"]
    job = pipeline.job()
    await pipeline.recovery.process(job)
    parts = pipeline.store.deliveries(job["id"])
    assert [d["state"] for d in parts] == ["sent", "retry_wait"]
    assert [d["receipt"] for d in parts] == ["part-one", None]
    assert pipeline.send.await_count == 2
    pipeline.invoke.assert_awaited_once()
    saved_result = pipeline.store.get_job(job["id"])["result"]
    initial_history = pipeline.store.read_session(job["client_id"])[0]["history"]
    assert [entry["role"] for entry in initial_history] == ["user", "assistant"]
    assert initial_history[1]["content"] == parts[0]["payload"]

    recovery, graph = restart_business_pipeline(pipeline, monkeypatch, job)
    pipeline.now[0] = parts[1]["due"]-1
    await recovery.deliver(recovery.store.get_job(job["id"]))
    assert pipeline.send.await_count == 2
    pipeline.now[0] += 1
    await recovery.deliver(recovery.store.get_job(job["id"]))
    assert graph.await_count >= 2
    assert recovery.store.get_job(job["id"])["state"] == "done"
    assert recovery.store.get_job(job["id"])["result"] == saved_result
    assert [d["receipt"] for d in recovery.store.deliveries(job["id"])] == ["part-one", "part-two"]
    assert [d["attempts"] for d in recovery.store.deliveries(job["id"])] == [1, 2]
    assert [call.args for call in pipeline.send.await_args_list] == [
        (job["client_id"], parts[0]["payload"]), (job["client_id"], parts[1]["payload"]),
        (job["client_id"], parts[1]["payload"])]
    pipeline.invoke.assert_awaited_once()
    pipeline.notify.assert_not_awaited()
    history = recovery.store.read_session(job["client_id"])[0]["history"]
    assert [entry["role"] for entry in history] == ["user", "assistant", "assistant"]
    assert history[0] == initial_history[0]
    assert [entry["content"] for entry in history[1:]] == [d["payload"] for d in parts]
    recovery, _ = restart_business_pipeline(pipeline, monkeypatch, job)
    await recovery.tick()
    await asyncio.gather(*list(recovery.active.values()))
    assert pipeline.send.await_count == 3
    pipeline.invoke.assert_awaited_once()
    assert recovery.store.read_session(job["client_id"])[0]["history"] == history


@pytest.mark.parametrize("unknown", ["timeout", "missing_receipt"])
async def test_business_unknown_survives_restart_and_duplicate_sources(pipeline, monkeypatch, unknown):
    pipeline.invoke.return_value = model_response("Программа Эльбруса. "+"Маршрут. "*160)
    if unknown == "timeout":
        pipeline.send.side_effect = httpx.ReadTimeout("synthetic")
    else:
        pipeline.send.return_value = None
    job = pipeline.job()
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job["id"])["state"] == "unknown"
    deliveries = pipeline.store.deliveries(job["id"])
    assert [d["state"] for d in deliveries] == ["unknown", "ready"]
    saved_result = pipeline.store.get_job(job["id"])["result"]
    initial_history = pipeline.store.read_session(job["client_id"])[0]["history"]
    assert [entry["role"] for entry in initial_history] == ["user"]
    assert initial_history[0]["content"] == "Эльбрус"
    pipeline.send.assert_awaited_once()
    pipeline.invoke.assert_awaited_once()

    recovery, _ = restart_business_pipeline(pipeline, monkeypatch, job)
    await recovery.refresh_client(job["client_id"])
    recovery.accept([{"kind": "user", "mid": "pipeline-mid", "sender_id": job["client_id"],
        "text": "Эльбрус", "_event_time": json.loads(job["payload"])["_original_time"]}])
    pipeline.now[0] += 1000
    await recovery.tick()
    await asyncio.gather(*list(recovery.active.values()))
    assert recovery.store.get_job(job["id"])["state"] == "unknown"
    assert recovery.store.get_job(job["id"])["result"] == saved_result
    assert recovery.store.deliveries(job["id"]) == deliveries
    pipeline.send.assert_awaited_once()
    pipeline.invoke.assert_awaited_once()
    pipeline.notify.assert_not_awaited()
    assert recovery.store.read_session(job["client_id"])[0]["history"] == initial_history
    with recovery.store.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM inbound_jobs").fetchone()[0] == 1


async def test_business_manager_arrives_during_model_and_reset_never_revives(pipeline, monkeypatch):
    from src.db import sessions

    started, release = asyncio.Event(), asyncio.Event()
    async def delayed_model(messages, **kwargs):
        started.set()
        await release.wait()
        return model_response("Менеджер поможет.", manager_data("Запрос консультации"))
    pipeline.invoke.side_effect = delayed_model
    job = pipeline.job("Соедините с менеджером")
    task = asyncio.create_task(pipeline.recovery.process(job))
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        pipeline.store.persist("account", [{"kind": "manager", "client_id": job["client_id"],
            "mid": "manager-during-model", "text": "Я подключился", "_event_time": pipeline.now[0]}])
        assert pipeline.store.get_job(job["id"])["state"] == "cancelled"
        manager_session = pipeline.store.read_session(job["client_id"])
        release.set()
        await asyncio.wait_for(task, timeout=3)
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert pipeline.store.get_job(job["id"])["reason"] == "manager_takeover"
    assert pipeline.store.read_session(job["client_id"]) == manager_session
    assert pipeline.store.get_job(job["id"])["result"] is None
    assert pipeline.store.deliveries(job["id"]) == []
    pipeline.invoke.assert_awaited_once()
    pipeline.send.assert_not_awaited()
    pipeline.notify.assert_not_awaited()
    state = await sessions.get_session(job["client_id"])
    assert state["manager_last_at"] is not None
    state["manager_last_at"] = None
    await sessions.save_session(job["client_id"], state)
    recovery, _ = restart_business_pipeline(pipeline, monkeypatch, job)
    pipeline.now[0] += 1000
    await recovery.refresh_client(job["client_id"])
    await recovery.tick()
    await asyncio.gather(*list(recovery.active.values()))
    assert recovery.store.get_job(job["id"])["state"] == "cancelled"
    pipeline.invoke.assert_awaited_once()
    pipeline.send.assert_not_awaited()
    pipeline.notify.assert_not_awaited()
