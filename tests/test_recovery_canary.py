"""First-release scope and real Meta response shapes; no external sends."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.channels.instagram import InstagramChannel
from src.config import Settings, settings
from src.db.inbound import InboundStore
from src.exceptions import InstagramError, TelegramError
from src.services.inbound_recovery import current_delivery, normalize_api_messages
from src.services.telegram_notify import TelegramNotifier
from tests.test_inbound_recovery import clock as clock, service
from tests.test_recovery_pipeline import pipeline as pipeline


@pytest.fixture
def canary(monkeypatch):
    monkeypatch.setattr(settings, "inbound_recovery_enabled", True)
    monkeypatch.setattr(settings, "inbound_recovery_scope", "allowlist")
    monkeypatch.setattr(settings, "inbound_recovery_client_ids", "1001")


def event(clock, client="1001", mid="m1", **extra):
    return {"kind": "user", "sender_id": client, "mid": mid, "text": "Эльбрус", "_event_time": clock(), **extra}


def seed(db, clock, client="1001", mid="m1"):
    db.persist("account", [event(clock, client, mid)])
    clock.advance(5)
    for rows in db.pending_batches():
        db.create_jobs("account", rows, [json.loads(row["payload"]) for row in rows])


@pytest.mark.parametrize("ids", ["", " ", "123,", "x", "123,abc", "１２３", "1 2"])
def test_enabled_allowlist_rejects_empty_or_invalid(ids):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, inbound_recovery_enabled=True, inbound_recovery_client_ids=ids)


def test_scope_defaults_fail_closed_and_all_is_explicit():
    off = Settings(_env_file=None)
    assert off.inbound_recovery_scope == "allowlist" and not off.recovery_allows("1001")
    selected = Settings(_env_file=None, inbound_recovery_enabled=True, inbound_recovery_client_ids="1001, 1002")
    assert selected.recovery_allows("1001") and not selected.recovery_allows("1003")
    assert Settings(_env_file=None, inbound_recovery_enabled=True, inbound_recovery_scope="all").recovery_allows("1003")


def test_client_and_global_baselines_survive_restart(clock):
    db = InboundStore(clock=clock)
    t1 = db.initialize("account", ("1001",))
    clock.advance(100)
    during = event(clock, "1002", "during")
    clock.advance(100)
    t2 = db.initialize("account")
    assert t2 > t1 and db.baseline_for("account", "1001") == t1
    db.persist("account", [during, event(clock, "1002", "after"),
                           {**during, "sender_id": "1001", "mid": "test-during"}])
    with db.connection() as conn:
        rows = {r["mid"]: r["job_id"] for r in conn.execute("SELECT mid,job_id FROM inbound_events")}
    assert rows == {"during": "ignored", "after": None, "test-during": None}
    clock.advance(200)
    restarted = InboundStore(clock=clock)
    assert restarted.initialize("account") == t2
    assert restarted.baseline_for("account", "1001") == t1


def test_sql_claim_recovery_cleanup_ignore_foreign_clients(clock, canary):
    db = InboundStore(clock=clock)
    db.initialize("account")
    seed(db, clock, "1002", "foreign")
    foreign = db.claim_due()
    seed(db, clock)
    recovery = service(db, clock)
    selected = db.claim_due()
    assert selected["client_id"] == "1001"
    clock.advance(200)
    db.recover(startup=True)
    assert db.get_job(foreign["id"])["state"] == "processing"
    assert db.get_job(foreign["id"])["technical_attempts"] == 0
    assert db.get_job(selected["id"])["state"] == "retry_wait"
    with db.connection() as conn:
        conn.execute("UPDATE inbound_jobs SET state='done',updated_at=0 WHERE id=?", (foreign["id"],))
    db.cleanup()
    assert json.loads(db.get_job(foreign["id"])["payload"])["text"] == "Эльбрус"
    assert recovery.store.stats()["jobs"] == {"retry_wait": 1}


async def test_scanner_skips_foreign_messages_and_checkpoints(clock, canary):
    db = InboundStore(clock=clock)
    recovery = service(db, clock)
    recovery.start()
    recovery.channel.list_conversations.return_value = {"data": [
        {"id": "foreign", "client_id": "1002"}, {"id": "test", "client_id": "1001"}], "after": None}
    recovery.channel.list_conversation_messages.return_value = {"data": [], "after": None}
    recovery._get = lambda method, *args: method(*args)
    await recovery.reconcile_tick()
    recovery.channel.list_conversation_messages.assert_awaited_once_with("test")
    assert db.get_sync("dialog:1002") is None
    assert db.get_sync("dialog:1001")["id"] == "test"
    db.set_sync("scan:account", {"after": "stale", "dialogs": []})
    db.set_sync("complete_scan:account", clock())
    db.initialize("account")
    assert db.get_sync("scan:account") is None and db.get_sync("complete_scan:account") is None


@pytest.mark.parametrize("channel", ["instagram", "telegram"])
async def test_final_send_checks_job_client_not_manager_chat(clock, canary, channel):
    db = InboundStore(clock=clock)
    db.initialize("account")
    seed(db, clock, "1002")
    job = db.claim_due()
    recovery = service(db, clock)
    delivery = {"id": "not-sent", "client_id": "1002", "channel": channel, "destination": "1001"}
    assert not await recovery.send_part(job, delivery, AsyncMock() if channel == "telegram" else None)
    await recovery.process(job)
    await recovery.deliver(job)
    recovery.channel.send_message.assert_not_awaited()
    recovery.dispatch.assert_not_awaited()
    assert db.get_job(job["id"])["technical_attempts"] == 0


@pytest.mark.parametrize("channel", ["instagram", "telegram"])
async def test_low_level_send_guard_blocks_foreign_context(canary, monkeypatch, channel):
    delivery = {"id": "d", "client_id": "1002", "channel": channel, "destination": "1001", "legacy": False}
    token = current_delivery.set(delivery)
    try:
        if channel == "instagram":
            target = InstagramChannel()
            send = AsyncMock()
            monkeypatch.setattr(target, "_send_message", send)
            with pytest.raises(InstagramError, match="scope_blocked"):
                await target.send_message("1001", "reply")
            send.assert_not_awaited()
        else:
            with pytest.raises(TelegramError, match="scope_blocked"):
                await TelegramNotifier()._send("notice", "1001", sender_id="1002")
    finally:
        current_delivery.reset(token)


def api_message(clock, mid, **extra):
    return {"id": mid, "from": {"id": "1001"}, "created_time":
            datetime.fromtimestamp(clock(), timezone.utc).isoformat(), **extra}


def test_api_media_preserves_photo_reel_video_order(clock, monkeypatch):
    monkeypatch.setattr(settings, "image_media_enabled", True)
    monkeypatch.setattr(settings, "shared_media_enabled", True)
    monkeypatch.setattr(settings, "voice_media_enabled", False)
    db = InboundStore(clock=clock)
    messages = [api_message(clock, "a", attachments={"data": [{"image_data": {"url": "https://scontent.cdninstagram.com/photo.jpg"}}]}),
                api_message(clock, "b", shares={"data": [{"link": "https://www.instagram.com/reel/Example_123/"}]}),
                api_message(clock, "c", attachments={"data": [{"video_data": {"url": "https://scontent.cdninstagram.com/video.mp4"}}]})]
    events = normalize_api_messages(messages, "1001", "account", db, {"account"})
    merged = InstagramChannel.merge_events(events)
    assert len(merged) == 1
    assert [part["kind"] for part in merged[0]["visual_parts"]] == ["images", "shared", "images"]
    assert merged[0]["related_mids"] == ["b", "c"]
    assert "voice_parts" not in merged[0]


@pytest.mark.parametrize("link", ["http://www.instagram.com/p/x/", "https://evil.example/p/x/",
                                   "https://u:p@www.instagram.com/p/x/", "https://www.instagram.com:bad/p/x/"])
def test_untrusted_shares_remain_incomplete(clock, monkeypatch, link):
    monkeypatch.setattr(settings, "shared_media_enabled", True)
    result = normalize_api_messages([api_message(clock, "m", message="Эльбрус", shares={"data": [{"link": link}]})],
                                    "1001", "account", InboundStore(clock=clock), {"account"})[0]
    assert "shared_sources" not in result and "unavailable_share" in result["_source_issues"]
    assert result["text"] == "Эльбрус" and "referral" not in result


async def test_unsupported_still_reaches_unified_model_contract(pipeline):
    job = pipeline.job("Эльбрус", _api_only=True, _context_incomplete=True,
                       _source_issues=["unsupported_media"])
    await pipeline.recovery.process(job)
    pipeline.invoke.assert_awaited_once()
    pipeline.send.assert_awaited_once()
    assert "неполный" in str(pipeline.invoke.await_args.args[0])


@pytest.mark.parametrize("fail", [False, True])
async def test_mixed_webhook_commit_before_legacy_parse(clock, canary, monkeypatch, fail):
    import src.main as main
    monkeypatch.setattr(main, "instagram", InstagramChannel())
    db = InboundStore(clock=clock)
    recovery = service(db, clock)
    recovery.initialize_scope()
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    monkeypatch.setattr(main.instagram, "verify_signature", lambda *args: True)
    calls = []
    async def parse(payload, **kwargs):
        ids = [m["sender"]["id"] for e in payload["entry"] for m in e["messaging"]]
        calls.append(ids)
        if kwargs.get("recovery_store"):
            return [event(clock)]
        assert db.get_sync("persist_marker") is True
        return []
    monkeypatch.setattr(main.instagram, "receive_message", parse)
    original = recovery.accept
    def accept(events):
        if fail:
            raise OSError("disk")
        original(events)
        db.set_sync("persist_marker", True)
    monkeypatch.setattr(recovery, "accept", accept)
    request = AsyncMock()
    request.body.return_value = b"{}"
    request.headers = {}
    request.json.return_value = {"entry": [{"messaging": [
        {"sender": {"id": "1002"}, "message": {"mid": "foreign"}},
        {"sender": {"id": "1001"}, "message": {"mid": "test"}}]}]}
    response = await main.receive_instagram_message(request)
    assert response.status_code == (503 if fail else 200)
    assert calls == ([["1001"]] if fail else [["1001"], ["1002"]])


async def test_legacy_pending_other_client_continues_during_canary(clock, canary, monkeypatch):
    import src.main as main
    monkeypatch.setattr(main, "instagram", InstagramChannel())
    from src.db.pending_messages import enqueue_pending, get_due_pending
    db = InboundStore(clock=clock)
    recovery = service(db, clock)
    recovery.initialize_scope()
    when = datetime.fromtimestamp(clock()-1, timezone.utc).isoformat()
    await enqueue_pending("1001", "test", when)
    await enqueue_pending("1002", "ordinary", when)
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    send = AsyncMock(return_value="legacy-mid")
    monkeypatch.setattr(main.instagram, "send_message", send)
    sleeps = 0
    async def once(*args):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError
    monkeypatch.setattr(main.asyncio, "sleep", once)
    with pytest.raises(asyncio.CancelledError):
        await main._pending_messages_worker()
    send.assert_awaited_once_with("1002", "ordinary")
    rows = await get_due_pending(datetime.now(timezone.utc).isoformat())
    assert len(rows) == 1 and rows[0]["recipient_id"] == "1001"
    assert rows[0]["recovery_delivery_id"] is not None


@pytest.mark.parametrize("mandatory", ["file", "product", "story_mention"])
def test_required_handoff_survives_mixed_api_media(clock, monkeypatch, mandatory):
    for flag in ("voice_media_enabled", "image_media_enabled", "shared_media_enabled"):
        monkeypatch.setattr(settings, flag, True)
    db = InboundStore(clock=clock)
    message = api_message(clock, "mandatory", attachments={"data": [
        {"type": mandatory}, {"audio_data": {"url": "https://scontent.cdninstagram.com/audio.mp4"}},
        {"image_data": {"url": "https://scontent.cdninstagram.com/photo.jpg"}}]})
    result = InstagramChannel.merge_events(normalize_api_messages([message, api_message(clock, "text", message="Можно подробнее")],
                                           "1001", "account", db, {"account"}))
    if mandatory == "story_mention":
        assert any(e["kind"] == "user_silent_handoff" for e in result)
    else:
        assert any(mandatory in e.get("non_text", {}).get("types", []) for e in result)


def test_late_webhook_replaces_stale_api_visual_context(clock):
    db = InboundStore(clock=clock)
    db.initialize("account")
    db.persist("account", [event(clock, _api_only=True, _context_incomplete=True,
        _source_issues=["unknown_attachment"], visual_parts=[{"kind": "images", "urls": ["old"]}])], "api")
    db.persist("account", [event(clock, images=["fresh"], image_types=["image"])], "webhook")
    clock.advance(5)
    payload = json.loads(db.pending_batches()[0][0]["payload"])
    assert payload["images"] == ["fresh"]
    assert "visual_parts" not in payload and "_source_issues" not in payload and "_api_only" not in payload


async def test_visual_only_api_batch_uses_vision_without_voice(pipeline, monkeypatch):
    from types import SimpleNamespace
    from src.services.story_media import StoryMedia
    monkeypatch.setattr(settings, "voice_media_enabled", False)
    monkeypatch.setattr("src.services.llm.get_vision_llm", lambda: SimpleNamespace(ainvoke=pipeline.invoke))
    parts = [{"kind": "images", "urls": ["https://scontent.cdninstagram.com/photo.jpg"], "types": ["image"]},
             {"kind": "shared", "sources": [{"id": None, "url": "https://www.instagram.com/reel/Example/"}]}]
    prepare = AsyncMock(return_value=StoryMedia(None, "MIXED", [{"label": "one", "url": "data:image/jpeg;base64,/9j/"}]))
    monkeypatch.setattr("src.services.story_media.prepare_visual_parts", prepare)
    transcribe = AsyncMock(side_effect=AssertionError("visual-only must not start STT"))
    monkeypatch.setattr("src.services.voice_media.transcribe_voice", transcribe)
    job = pipeline.job("Можно подробнее", kind="user_visual", visual_parts=parts,
                       _api_only=True, _context_incomplete=True)
    await pipeline.recovery.process(job)
    prepare.assert_awaited_once_with(parts)
    transcribe.assert_not_awaited()
    pipeline.invoke.assert_awaited_once()
    pipeline.send.assert_awaited_once()


async def test_disabled_admin_keeps_unknown_visible(clock, monkeypatch):
    import src.main as main
    db = InboundStore(clock=clock)
    seed(db, clock)
    with db.connection() as conn:
        conn.execute("UPDATE inbound_jobs SET state='unknown'")
    monkeypatch.setattr(settings, "inbound_recovery_enabled", False)
    monkeypatch.setattr(main, "_require_admin_token", lambda token: None)
    monkeypatch.setattr("src.services.inbound_recovery.existing_receipt_store", lambda: db)
    result = await main.inbound_recovery_status(None)
    assert result["enabled"] is False and result["jobs"] == {"unknown": 1}


async def test_allowed_job_cannot_send_to_a_different_instagram_client(clock, canary, monkeypatch):
    db = InboundStore(clock=clock)
    db.initialize("account")
    seed(db, clock)
    job = db.claim_due()
    recovery = service(db, clock)
    delivery = {"id": "bad", "client_id": "1001", "destination": "1002", "channel": "instagram"}
    assert not await recovery.send_part(job, delivery, None)
    channel = InstagramChannel()
    send = AsyncMock()
    monkeypatch.setattr(channel, "_send_message", send)
    token = current_delivery.set(delivery)
    try:
        with pytest.raises(InstagramError, match="scope_blocked"):
            await channel.send_message("1002", "wrong destination")
    finally:
        current_delivery.reset(token)
    send.assert_not_awaited()
