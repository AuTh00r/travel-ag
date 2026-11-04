"""Business-route parity: the same real parser, a durable restart, fake sends."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from structlog.testing import capture_logs

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.db.inbound import InboundStore
from src.services.inbound_recovery import normalize_api_messages
from tests.test_inbound_recovery import clock as clock, service

CDN = "https://scontent.cdninstagram.com/source.mp4"
LINK = "https://www.instagram.com/reel/Example/"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    for flag in ("inbound_recovery_enabled", "instagram_reconcile_enabled", "voice_media_enabled",
                 "image_media_enabled", "shared_media_enabled", "story_media_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "inbound_recovery_scope", "all")


def attachment(kind, **payload):
    return {"type": kind, "payload": payload or {"url": CDN}}


CASES = [
    {"text": "Эльбрус"},
    {"attachments": [attachment("image")]},
    {"text": "Подробнее", "attachments": [attachment("video")]},
    {"attachments": [attachment("audio")]},
    {"text": "Подробнее", "attachments": [attachment("image"), attachment("audio"), attachment("video")]},
    {"text": "Подробнее", "reply_to": {"story": {"id": "123456789"}}},
    {"text": "Подробнее", "reply_to": {"story": {"id": "123456789"}}, "attachments": [attachment("image")]},
    {"text": "👏", "reply_to": {"story": {"id": "123456789"}}},
    {"attachments": [attachment("story_mention")]},
    {"attachments": [attachment("file")]},
    {"attachments": [attachment("product")]},
    {"attachments": [attachment("sticker")]},
    {"attachments": [attachment("gif")]},
    {"attachments": [attachment("ig_reel", url=LINK)]},
    {"attachments": [attachment("ig_post", ig_post_media_id="123456789")]},
    {"attachments": [attachment("template", template_type="phone_number", phone_number="+375291111111")]},
    {"attachments": [attachment("template", template_type="generic", elements=[{"title": "Программа тура"}])]},
    {"text": "ВДП", "referral": {"source": "ADS", "ad_id": "123456789"}},
    {"text": "Подробнее", "attachments": [attachment("video")], "referral": {"source": "ADS", "ad_id": "123456789"}},
    {"attachments": [attachment("unsupported_type")]},
    {"text": "Подробнее", "attachments": [attachment("unsupported_type")]},
]


def clean(event):
    return {k: v for k, v in event.items() if k not in
            ("_event_time", "_original_time", "_context_incomplete", "_source_issues", "_api_only")}


@pytest.mark.parametrize("message", CASES)
async def test_full_webhook_payload_survives_restart_with_same_business_route(clock, monkeypatch, message):
    import src.main as main
    channel = InstagramChannel()
    monkeypatch.setattr(main, "instagram", channel)
    db = InboundStore(clock=clock)
    recovery = service(db, clock)
    recovery.channel = channel
    recovery.merge = main._merge_recovery_events
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    recovery.initialize_scope()
    payload = {"entry": [{"messaging": [{"sender": {"id": "client"}, "timestamp": clock()*1000,
                                         "message": {"mid": "m1", **message}}]}]}
    ordinary = await channel.receive_message(deepcopy(payload), merge=False)
    expected = channel.merge_events(deepcopy(ordinary))
    received = await channel.receive_message(deepcopy(payload), recovery_store=db, merge=False)
    recovery.accept(received)
    # Re-open the same SQLite from a new store, as after process restart.
    restarted = InboundStore(clock=clock)
    recovery.store = restarted
    recovery.store.allowed = settings.recovery_allows
    clock.advance(5)
    actual = []
    for rows in restarted.pending_batches():
        merged = recovery.merge([json.loads(row["payload"]) for row in rows])
        restarted.create_jobs("account", rows, merged)
        actual.extend(merged)
    expected = [e for e in expected if e["kind"] not in ("ignored", "story_context")]
    assert [clean(e) for e in actual] == [clean(e) for e in expected]
    for name in ("_process_safely", "_process_non_text_safely", "_process_silent_handoff", "_process_shared_post_safely"):
        monkeypatch.setattr(main, name, AsyncMock())
    for wanted, restored in zip(expected, actual):
        handlers = [main._process_safely, main._process_non_text_safely, main._process_silent_handoff, main._process_shared_post_safely]
        for handler in handlers:
            handler.reset_mock()
        await main._dispatch_user_event(wanted)
        calls = [[(deepcopy(call.args), deepcopy(call.kwargs)) for call in handler.await_args_list] for handler in handlers]
        for handler in handlers:
            handler.reset_mock()
        await main._dispatch_user_event(restored)
        assert [[(call.args, call.kwargs) for call in handler.await_args_list] for handler in handlers] == calls


@pytest.mark.parametrize("other", [{"text": "Можно подробнее"}, {"attachments": [attachment("audio")]}])
@pytest.mark.parametrize("reverse", [False, True])
async def test_api_photo_and_webhook_companion_merge_like_ordinary(clock, other, reverse):
    channel, db = InstagramChannel(), InboundStore(clock=clock)
    base = {"id": "photo", "from": {"id": "client"}, "created_time":
            datetime.fromtimestamp(clock(), timezone.utc).isoformat(),
            "attachments": {"data": [{"image_data": {"url": CDN}}]}}
    api = normalize_api_messages([base], "client", "account", db, {"account"})
    photo = channel.parse_message_payload({"entry": [{"messaging": [{"sender": {"id": "client"},
        "message": {"mid": "photo", "attachments": [attachment("image")]}}]}]}, merge=False)
    companion = channel.parse_message_payload({"entry": [{"messaging": [{"sender": {"id": "client"},
        "message": {"mid": "other", **other}}]}]}, merge=False)
    expected, actual = photo+companion, api+deepcopy(companion)
    if reverse:
        expected.reverse()
        actual.reverse()
    assert [clean(e) for e in channel.merge_events(actual)] == [clean(e) for e in channel.merge_events(expected)]


@pytest.mark.parametrize("kind", ["ignored", "story_context"])
def test_late_terminal_webhook_does_not_create_model_job(clock, kind):
    db = InboundStore(clock=clock)
    db.initialize("account")
    incoming = {"kind": "user", "mid": "m1", "sender_id": "client", "text": "unknown", "_event_time": clock()}
    db.persist("account", [incoming], "api")
    clock.advance(5)
    rows = db.pending_batches()[0]
    db.create_jobs("account", rows, [incoming])
    job = db.claim_due()
    db.persist("account", [{**incoming, "kind": kind, "text": "", "story": {"id": "123"}}], "webhook")
    assert db.get_job(job["id"])["state"] in ("done", "cancelled")
    assert not db.claim_due()


def test_late_meaningful_webhook_reopens_api_only_ignore(clock):
    db = InboundStore(clock=clock)
    db.initialize("account")
    incoming = {"kind": "ignored", "mid": "m1", "sender_id": "client", "text": "", "_event_time": clock()}
    db.persist("account", [incoming], "api")
    db.persist("account", [{**incoming, "kind": "user", "text": "Эльбрус"}], "webhook")
    clock.advance(5)
    assert db.pending_batches()[0][0]["mid"] == "m1"


def test_story_reaction_is_consumed_once_across_questions_and_restart(clock, monkeypatch):
    import src.main as main
    channel, db = InstagramChannel(), InboundStore(clock=clock)
    monkeypatch.setattr(main, "instagram", channel)
    recovery = service(db, clock)
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    recovery.initialize_scope()
    recovery.accept([{"kind": "story_context", "sender_id": "client", "mid": "reaction",
                      "text": "", "story": {"id": "123456789"}, "_event_time": clock()}])
    clock.advance(1)
    for index in range(2):
        recovery.accept([{"kind": "user", "sender_id": "client", "mid": f"q{index}",
                          "text": "Можно подробнее", "_event_time": clock()}])
        clock.advance(1)
    clock.advance(5)
    rows = db.pending_batches()[0]
    merged = main._merge_recovery_events([json.loads(row["payload"]) for row in rows])
    assert len(merged) == 1 and merged[0]["story"] == {"id": "123456789"}
    db.create_jobs("account", rows, merged)
    clock.advance(1)
    recovery.store = InboundStore(clock=clock)
    recovery.accept([{"kind": "user", "sender_id": "client", "mid": "later", "text": "Другой вопрос", "_event_time": clock()}])
    clock.advance(5)
    rows = recovery.store.pending_batches()[0]
    assert "story" not in main._merge_recovery_events([json.loads(row["payload"]) for row in rows])[0]


@pytest.mark.parametrize("message", [CASES[i] for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16)] + CASES[-2:])
def test_available_api_fields_use_identical_classification(clock, message):
    channel, db = InstagramChannel(), InboundStore(clock=clock)
    api = {"id": "m1", "from": {"id": "client"}, "message": message.get("text", ""),
           "created_time": datetime.fromtimestamp(clock(), timezone.utc).isoformat()}
    if "reply_to" in message:
        api["reply_to"] = deepcopy(message["reply_to"])
    attachments = []
    for part in message.get("attachments", []):
        kind = part["type"]
        if kind in ("image", "video", "audio"):
            attachments.append({kind+"_data": {"url": part["payload"]["url"]}})
        else:
            attachments.append(deepcopy(part))
    if attachments:
        api["attachments"] = {"data": attachments}
    expected = channel.parse_message_payload({"entry": [{"messaging": [{"sender": {"id": "client"},
        "message": {"mid": "m1", **message}}]}]}, merge=False)
    actual = normalize_api_messages([api], "client", "account", db, {"account"})
    assert [clean(e) for e in actual] == [clean(e) for e in expected]


def test_late_same_question_retains_original_reaction_story(clock, monkeypatch):
    import src.main as main
    db = InboundStore(clock=clock)
    recovery = service(db, clock)
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    recovery.initialize_scope()
    recovery.accept([{"kind": "story_context", "sender_id": "client", "mid": "reaction",
                      "text": "", "story": {"id": "123456789"}, "_event_time": clock()}])
    clock.advance(1)
    question = {"kind": "user", "sender_id": "client", "mid": "q", "text": "Подробнее", "_event_time": clock()}
    recovery.accept([{**question, "_api_only": True, "_context_incomplete": True}], "api")
    clock.advance(5)
    rows = db.pending_batches()[0]
    db.create_jobs("account", rows, main._merge_recovery_events([json.loads(row["payload"]) for row in rows]))
    job = db.claim_due()
    assert json.loads(job["payload"])["story"] == {"id": "123456789"}
    recovery.accept([question], "webhook")
    assert json.loads(db.get_job(job["id"])["payload"])["story"] == {"id": "123456789"}


@pytest.mark.parametrize("question_source", ["webhook", "api"])
@pytest.mark.parametrize("delay", [53, 119, 120, 121, 599, 600, 601])
async def test_real_story_reaction_timestamp_reaches_next_question_after_restart(clock, monkeypatch, question_source, delay):
    import src.main as main
    channel, db = InstagramChannel(), InboundStore(clock=clock)
    recovery = service(db, clock)
    monkeypatch.setattr(main, "instagram", channel)
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)
    handler = AsyncMock()
    monkeypatch.setattr(main, "_process_safely", handler)
    recovery.initialize_scope()
    story = {"id": "123456789"}
    private_url = CDN + "?signature=private-story"

    def webhook(mid, text, reply=None):
        message = {"mid": mid, "text": text}
        if reply is not None:
            message["reply_to"] = {"story": reply}
        return {"object": "instagram", "entry": [{"messaging": [{
            "sender": {"id": "client"}, "recipient": {"id": "account"},
            "timestamp": int(clock()*1000), "message": message,
        }]}]}

    with capture_logs() as logs:
        reactions = await channel.receive_message(
            webhook("reaction-ms", "🔥", {**story, "url": private_url}),
            merge=False, recovery_store=db,
        )
        assert recovery.accept(reactions) == reactions
        assert db.pending_batches() == []
        await main._dispatch_user_event(reactions[0])
        handler.assert_not_awaited()
        assert reactions[0]["_event_time"] == clock()*1000

        # Durable context survives process restart; no legacy RAM hint is used.
        db = recovery.store = InboundStore(clock=clock)
        db.allowed = settings.recovery_allows
        clock.advance(delay)
        if question_source == "webhook":
            questions = await channel.receive_message(
                webhook("question-ms", "Можно подробнее?"), merge=False, recovery_store=db,
            )
        else:
            questions = normalize_api_messages([{
                "id": "question-ms", "from": {"id": "client"},
                "to": {"data": [{"id": "account"}]},
                "created_time": datetime.fromtimestamp(clock(), timezone.utc).isoformat(),
                "message": "Можно подробнее?",
            }], "client", "account", db, {"account"})
        recovery.accept(questions, question_source)
        clock.advance(5)
        rows = db.pending_batches()[0]
        merged = main._merge_recovery_events([json.loads(row["payload"]) for row in rows])
        assert len(merged) == 1
        assert merged[0].get("story") == (story if delay < 600 else None)
        await main._dispatch_user_event(merged[0])
        handler.assert_awaited_once_with("client", "Можно подробнее?", *([story] if delay < 600 else []))
        db.create_jobs("account", rows, merged)

        # Neither the duplicate reaction nor the next separate question reuses it.
        assert recovery.accept(reactions) == []
        clock.advance(10)
        later = await channel.receive_message(webhook("later-ms", "Ещё вопрос"), merge=False, recovery_store=db)
        recovery.accept(later)
        clock.advance(5)
        rows = db.pending_batches()[0]
        assert "story" not in main._merge_recovery_events([json.loads(row["payload"]) for row in rows])[0]

    received = [row for row in logs if row["event"] == "instagram.story_reaction.received"]
    attached = [row for row in logs if row["event"] == "instagram.story_context.attached"]
    assert len(received) == 1 and received[0]["context_usable"] is True
    assert len(attached) == int(delay < 600)
    if attached:
        assert attached[0]["story_id"] == story["id"]
    assert private_url not in json.dumps(received + attached)
    assert "Можно подробнее?" not in json.dumps(received + attached, ensure_ascii=False)


@pytest.mark.parametrize("before", [None, "not-a-time", float("inf"), float("-inf"), float("nan")])
def test_story_hint_invalid_time_does_not_invent_current_context(clock, before):
    db = InboundStore(clock=clock)
    db.initialize("account")
    db.persist("account", [{"kind": "story_context", "sender_id": "client", "mid": "reaction",
                           "story": {"id": "123456789"}, "text": "", "_event_time": clock()}])
    assert db.story_hint("client", before) is None
