"""Unknown media must reach fallback without breaking adjacent messages."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.channels.instagram import InstagramChannel


def incoming(message):
    return {"sender": {"id": "ATTACH_CLIENT"}, "message": message}


def envelope(*items):
    return {"entry": [{"messaging": list(items)}]}


@pytest.mark.parametrize("attachment", [
    {"type": None}, {"type": []}, {"type": {}}, None, "bad",
    {"type": "https://example.com/PRIVATE"}, {"type": "x" * 100},
])
async def test_bad_attachment_preserves_fallback_and_valid_neighbor(attachment):
    events = await InstagramChannel().receive_message(envelope(
        incoming({"mid": "bad", "attachments": [attachment], "text": {"private": "secret"}}),
        incoming({"mid": "good", "text": "Какие даты?"}),
    ), merge=False)
    assert len(events) == 2
    assert events[0]["kind"] == "user_non_text"
    assert events[0]["text"] == ""
    assert events[0]["non_text"]["types"] == ["unknown"]
    assert "PRIVATE" not in str(events[0]["non_text"])
    assert events[1]["text"] == "Какие даты?"


@pytest.mark.parametrize("message", [
    {"mid": "unsupported", "is_unsupported": True},
    {"mid": "unsupported", "attachments": {"type": "video"}},
    {"mid": "unsupported"},
])
async def test_unknown_message_is_not_silently_lost(message):
    events = await InstagramChannel().receive_message(envelope(incoming(message)))
    assert len(events) == 1
    assert events[0]["kind"] == "user_non_text"
    assert events[0]["mid"] == "unsupported"
    assert events[0]["non_text"]["types"]


@pytest.mark.parametrize("payload", [None, [], {"entry": None}, {"entry": {}},
    {"entry": [None, {"messaging": None}]}, {"entry": [{"messaging": [None]}]},
])
async def test_invalid_envelope_is_ignored(payload):
    assert await InstagramChannel().receive_message(payload) == []


@pytest.mark.parametrize("bad", [
    incoming(None), incoming([]), {"sender": None, "message": {"mid": "bad"}},
    {"sender": {"id": []}, "message": {"mid": "bad"}},
    incoming({"mid": {}, "is_echo": True}), incoming({"mid": [], "text": "bad"}),
    {"sender": {"id": "X"}, "recipient": None, "message": {"mid": "bad", "is_echo": True}},
])
async def test_bad_event_does_not_abort_neighbor(bad):
    events = await InstagramChannel().receive_message(envelope(
        bad, incoming({"mid": "good", "text": "Какие даты?"}),
    ))
    assert events == [{"kind": "user", "sender_id": "ATTACH_CLIENT",
                       "text": "Какие даты?", "mid": "good"}]


@pytest.mark.parametrize("kind", ["video", "audio", "file", "sticker", "animated_image",
                                  "product", "location", "future_media"])
async def test_unreadable_media_is_preserved_without_download(kind):
    events = await InstagramChannel().receive_message(envelope(incoming({
        "mid": "media", "attachments": [{"type": kind, "payload": {"url": "https://example.com/private"}}],
    })))
    assert len(events) == 1
    if kind in ("sticker", "animated_image"):
        assert events[0]["kind"] == "ignored"
        assert events[0]["mid"] == "media" and "https://" not in str(events[0])
        return
    assert events[0]["non_text"]["types"] == [kind]
    assert events[0]["kind"] == "user_non_text"
    if kind == "video":
        assert events[0]["images"] == ["https://example.com/private"]
        assert events[0]["image_types"] == ["video"]
        assert "https://" not in str(events[0]["non_text"])
        return
    assert "images" not in events[0] and "shared_sources" not in events[0]
    assert "https://" not in str(events[0])


async def test_unsupported_flag_does_not_open_photo_route():
    events = await InstagramChannel().receive_message(envelope(incoming({
        "mid": "unsupported", "is_unsupported": True, "text": "Вопрос",
        "attachments": [{"type": "image", "payload": {"url": "https://scontent.cdninstagram.com/a.jpg"}}],
    })))
    assert events[0]["kind"] == "user_non_text"
    assert "unsupported" in events[0]["non_text"]["types"]
    assert "images" not in events[0]


async def test_unsupported_story_does_not_open_story_route():
    events = await InstagramChannel().receive_message(envelope(incoming({
        "mid": "unsupported", "is_unsupported": True, "text": "Вопрос",
        "reply_to": {"story": {"id": "123456"}},
    })))
    assert events[0]["kind"] == "user_non_text"
    assert events[0]["non_text"]["types"] == ["unsupported"]
    assert events[0]["text"] == "Вопрос"
    assert "story" not in events[0]


async def test_postback_preserves_visible_title_not_opaque_payload():
    events = await InstagramChannel().receive_message(envelope({
        "sender": {"id": "ATTACH_CLIENT"},
        "postback": {"mid": "button", "title": "Узнать даты", "payload": "PRIVATE_INSTRUCTIONS"},
    }))
    assert events == [{"kind": "user", "sender_id": "ATTACH_CLIENT",
                       "mid": "button", "text": "Узнать даты"}]


@pytest.mark.parametrize("service", [
    incoming({"mid": "deleted", "is_deleted": True}),
    {"sender": {"id": "ATTACH_CLIENT"}, "read": {"mid": "read"}},
    {"sender": {"id": "ATTACH_CLIENT"}, "reaction": {"mid": "reaction", "action": "react"}},
])
async def test_service_event_gets_no_client_reply(service):
    assert await InstagramChannel().receive_message(envelope(service)) == []


@pytest.mark.parametrize("attachment", [
    {"type": "contact", "payload": {"phone_number": "+375291234567"}},
    {"type": "template", "payload": {"generic": {"elements": []}}},
])
async def test_explicit_unsupported_cannot_become_phone_or_empty_template(attachment):
    events = await InstagramChannel().receive_message(envelope(
        incoming({"mid": "media", "is_unsupported": True, "attachments": [attachment]}),
        incoming({"mid": "question", "text": "Какие даты?"}),
    ))
    assert len(events) == 1
    assert events[0]["kind"] == "user_non_text"
    assert "unsupported" in events[0]["non_text"]["types"]
    assert events[0]["text"] == "Какие даты?"
    assert "phone_card" not in events[0]
    assert events[0]["related_mids"] == ["question"]


async def test_mixed_unreadable_media_preserves_all_types_question_and_mids():
    events = await InstagramChannel().receive_message(envelope(
        incoming({"mid": "media", "attachments": [
            {"type": "image", "payload": {"url": "https://scontent.cdninstagram.com/a.jpg"}},
            {"type": "video"}, {"type": []},
        ]}),
        incoming({"mid": "question", "text": "Что в этом видео?"}),
    ))
    assert len(events) == 1
    assert events[0]["non_text"]["types"] == ["image", "video", "unknown"]
    assert events[0]["text"] == "Что в этом видео?"
    assert events[0]["related_mids"] == ["question"]
    assert "images" not in events[0] and "https://" not in str(events)


def test_invalid_json_returns_400_without_processing(monkeypatch):
    import src.main as main
    monkeypatch.setattr(main.instagram, "verify_signature", lambda *args: True)
    parse = AsyncMock()
    monkeypatch.setattr(main.instagram, "receive_message", parse)
    response = TestClient(main.app).post("/webhook/instagram", content=b"{bad-json")
    assert response.status_code == 400
    parse.assert_not_awaited()


async def test_telegram_failure_does_not_claim_success_or_consume_limit(monkeypatch):
    import src.main as main
    from src.services.telegram_notify import TelegramNotifier

    session = {"history": [], "escalation_count": 0}
    monkeypatch.setattr(main, "get_session", AsyncMock(return_value=session))
    monkeypatch.setattr(main, "save_session", AsyncMock())
    monkeypatch.setattr(main, "is_manager_active", lambda *args: False)
    monkeypatch.setattr(main, "_manager_pending", {})
    monkeypatch.setattr(main, "_processing_locks", {})
    monkeypatch.setattr(main.instagram, "get_username", AsyncMock(return_value="test_user"))
    notify = AsyncMock(side_effect=RuntimeError("synthetic failure"))
    monkeypatch.setattr(TelegramNotifier, "notify_manager", notify)
    send = AsyncMock(return_value=(True, None))
    monkeypatch.setattr(main, "_send_or_queue", send)
    await main._process_non_text_safely("ATTACH_CLIENT", "", {"types": ["audio"], "summary": "вложение: audio"})
    notify.assert_awaited_once()
    assert session["escalation_count"] == 0
    reply = send.await_args.args[1]
    assert "передал" not in reply and "уже передан" not in reply
    assert "текстом" in reply


@pytest.mark.parametrize("fail_lookup", [False, True])
async def test_manager_arriving_during_username_lookup_stops_fallback(monkeypatch, fail_lookup):
    import src.main as main
    from src.services.telegram_notify import TelegramNotifier

    session = {"history": [], "escalation_count": 0}
    pending = {}
    async def username(sender):
        pending[sender] = 1
        if fail_lookup:
            raise RuntimeError("synthetic lookup failure")
        return "test_user"

    monkeypatch.setattr(main, "get_session", AsyncMock(return_value=session))
    save = AsyncMock()
    monkeypatch.setattr(main, "save_session", save)
    monkeypatch.setattr(main, "is_manager_active", lambda *args: False)
    monkeypatch.setattr(main, "_manager_pending", pending)
    monkeypatch.setattr(main, "_processing_locks", {})
    monkeypatch.setattr(main.instagram, "get_username", username)
    notify, send = AsyncMock(), AsyncMock()
    monkeypatch.setattr(TelegramNotifier, "notify_manager", notify)
    monkeypatch.setattr(main, "_send_or_queue", send)
    await main._process_non_text_safely("ATTACH_CLIENT", "", {"types": ["file"]})
    notify.assert_not_awaited()
    send.assert_not_awaited()
    save.assert_not_awaited()
