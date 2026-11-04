from unittest.mock import AsyncMock

import pytest
import asyncio
import httpx

from src.channels.instagram import InstagramChannel
from src.config import settings

PHONE = "+375290000000"


def card(number="8 029 000-00-00", title="Phone number"):
    return {"type": "template", "payload": {"template_type": "generic", "elements": [{
        "title": title, "subtitle": number,
        "buttons": [{"type": "phone_number", "title": "Call", "payload": PHONE}]}]}}


def entry(mid, text=None, attachment=None, sender="PHONE_CLIENT"):
    message = {"mid": mid}
    if text is not None:
        message["text"] = text
    if attachment is not None:
        message["attachments"] = [attachment]
    return {"sender": {"id": sender}, "message": message}


def webhook(entries):
    return {"entry": [{"messaging": entries}]}


async def test_nested_generic_phone_card_uses_same_contact_guards():
    attachment = card()
    attachment["payload"] = {"generic": {"elements": attachment["payload"]["elements"]}}
    events = await InstagramChannel().receive_message(webhook([entry("nested_card", attachment=attachment)]))
    assert events[0]["kind"] == "user" and PHONE in events[0]["text"]


@pytest.mark.parametrize("generic", [{}, {"elements": []}])
async def test_empty_nested_template_has_no_cross_request_phone_cache(generic):
    channel = InstagramChannel()
    await channel.receive_message(webhook([entry("nested_phone_text", PHONE)]))
    events = await channel.receive_message(webhook([entry("nested_empty", attachment={
        "type": "template", "payload": {"generic": generic}})]))
    assert events[0]["kind"] == "user_non_text"
    assert not hasattr(channel, "_phone_inputs")


@pytest.mark.parametrize("case", ["no_phone", "ambiguous", "question", "nonempty"])
async def test_empty_nested_template_correlation_does_not_drop_other_input(case):
    channel = InstagramChannel()
    if case != "no_phone":
        await channel.receive_message(webhook([entry("nested_previous", PHONE)]))
    if case == "ambiguous":
        await channel.receive_message(webhook([entry("nested_other", "+375290000001")]))
    attachment = {"type": "template", "payload": {"generic": {"elements": []}}}
    if case == "nonempty":
        attachment["payload"]["generic"]["elements"] = [{"title": "Тур в Прагу"}]
    events = await channel.receive_message(webhook([entry("nested_other_input",
        "Какая цена?" if case == "question" else None, attachment)]))
    assert events[0]["kind"] != "user_contact_duplicate"
    if case == "question":
        assert "Какая цена?" in events[0]["text"]


@pytest.mark.parametrize("attachment", [card(), {"type": "template", "payload": {
    "template_type": "contact", "phone_number": PHONE}}])
async def test_phone_card_is_text_not_blind_attachment(attachment):
    events = await InstagramChannel().receive_message(webhook([entry("phone_card", attachment=attachment)]))
    assert len(events) == 1 and events[0]["kind"] == "user"
    assert PHONE in events[0]["text"]
    assert "non_text" not in events[0]


@pytest.mark.parametrize("reverse", [False, True])
async def test_phone_text_and_card_one_event_all_mids(reverse):
    entries = [entry("phone_text", PHONE), entry("phone_card", attachment=card())]
    if reverse:
        entries.reverse()
    events = await InstagramChannel().receive_message(webhook(entries))
    assert len(events) == 1 and events[0]["kind"] == "user"
    assert events[0]["text"] == PHONE
    assert {events[0]["mid"], *events[0].get("related_mids", [])} == {"phone_text", "phone_card"}


@pytest.mark.parametrize("attachment", [card(), {"type": "template", "payload": {"generic": {"elements": []}}}])
async def test_card_after_phone_in_separate_webhook_no_second_ai(monkeypatch, attachment):
    import src.main as main
    monkeypatch.setattr(settings, "instagram_app_secret", "")
    monkeypatch.setattr(settings, "instagram_access_token", "")
    monkeypatch.setattr(main, "_processed_mids", set())
    channel = InstagramChannel()
    monkeypatch.setattr(main, "instagram", channel)
    process = AsyncMock()
    non_text = AsyncMock()
    monkeypatch.setattr(main, "_process_safely", process)
    monkeypatch.setattr(main, "_process_non_text_safely", non_text)
    gate = asyncio.Event()
    monkeypatch.setattr(main, "_wait_inbound_window", gate.wait)
    monkeypatch.setattr(main, "_inbound_locks", {})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        first = webhook([entry("contact_sep_text", PHONE)])
        second = webhook([entry("contact_sep_card", attachment=attachment)])
        for payload in (first, second, second):
            assert (await client.post("/webhook/instagram", json=payload)).status_code == 200
        process.assert_not_awaited()
        gate.set()
        await main._inbound_tasks["PHONE_CLIENT"]
    process.assert_awaited_once_with("PHONE_CLIENT", PHONE)
    non_text.assert_not_awaited()



@pytest.mark.parametrize("change", ["title", "invalid", "conflict", "multiple"])
async def test_generic_or_ambiguous_card_does_not_claim_customer_phone(change):
    attachment = card()
    element = attachment["payload"]["elements"][0]
    if change == "title":
        element["title"] = "Контакты отеля"
    elif change == "invalid":
        element["subtitle"] = "Позвоните в отель, 5 звёзд"
    elif change == "conflict":
        element["buttons"][0]["payload"] = "+375290000001"
    else:
        attachment["payload"]["elements"].append(dict(element))
    events = await InstagramChannel().receive_message(webhook([entry("phone_rejected", attachment=attachment)]))
    assert events[0]["kind"] == "user_non_text" and events[0]["text"] == ""


async def test_phone_postback_uses_visible_title_and_real_mid():
    event = {"sender": {"id": "PHONE_CLIENT"}, "postback": {
        "mid": "phone_postback", "title": PHONE, "payload": "DO_NOT_EXECUTE"}}
    events = await InstagramChannel().receive_message(webhook([event]))
    assert events == [{"kind": "user", "sender_id": "PHONE_CLIENT", "text": PHONE,
                      "mid": "phone_postback"}]


@pytest.mark.parametrize("postback", [{"title": PHONE}, {"mid": "opaque", "payload": PHONE}])
async def test_phone_postback_without_visible_title_or_mid_stays_ignored(postback):
    events = await InstagramChannel().receive_message(webhook([{
        "sender": {"id": "PHONE_CLIENT"}, "postback": postback}]))
    assert events == []


async def test_phone_card_preserves_question_and_other_client_identity():
    events = await InstagramChannel().receive_message(webhook([
        entry("question_card", "Хочу звонок по Праге", card()),
        entry("other_text", PHONE, sender="OTHER_CLIENT")]))
    assert len(events) == 2 and all(event["kind"] == "user" for event in events)
    assert "Хочу звонок по Праге" in events[0]["text"] and PHONE in events[0]["text"]


@pytest.mark.parametrize("processed", [{"partial_text"}, {"partial_card"}])
async def test_phone_partial_retry_keeps_new_mid(processed):
    events = await InstagramChannel().receive_message(webhook([
        entry("partial_text", PHONE), entry("partial_card", attachment=card())]), processed_mids=processed)
    assert len(events) == 1 and events[0]["kind"] == "user"
    assert events[0]["mid"] not in processed
    assert not events[0].get("related_mids")


async def test_different_number_or_new_question_is_not_a_duplicate():
    channel = InstagramChannel()
    await channel.receive_message(webhook([entry("previous_phone", PHONE)]))
    other = card(number="8 029 000-00-01")
    other["payload"]["elements"][0]["buttons"][0]["payload"] = "+375290000001"
    events = await channel.receive_message(webhook([entry("different_phone", attachment=other),
        entry("new_question", "И уточните цену Праги", card())]))
    assert len(events) == 1 and events[0]["kind"] == "user"
    assert "+375290000001" in events[0]["text"]
    assert "И уточните цену Праги" in events[0]["text"]


async def test_separate_phone_and_card_are_never_suppressed_by_previous_request():
    channel = InstagramChannel()
    await channel.receive_message(webhook([entry("original_phone", PHONE)]))
    events = await channel.receive_message(webhook([entry("later_card", attachment=card())]))
    assert events[0]["kind"] == "user"
    events = await channel.receive_message(webhook([entry("repeated_phone", PHONE)]))
    assert events[0]["kind"] == "user"


@pytest.mark.parametrize("buttons", [[], [{"type": "web_url", "url": "https://example.com/hotel"}],
                                     [{"type": "postback", "payload": PHONE}]])
async def test_phone_label_without_structured_matching_phone_button_is_not_contact(buttons):
    attachment = card()
    attachment["payload"]["elements"][0]["buttons"] = buttons
    events = await InstagramChannel().receive_message(webhook([entry("unproven_card", attachment=attachment)]))
    assert events[0]["kind"] == "user_non_text"


async def test_phone_card_preserves_exact_story_context():
    message = entry("contact_story", "Перезвоните по этому туру", card())
    message["message"]["reply_to"] = {"story": {"id": "123"}}
    events = await InstagramChannel().receive_message(webhook([message]))
    assert events[0]["story"] == {"id": "123"}
    assert "Перезвоните по этому туру" in events[0]["text"] and PHONE in events[0]["text"]


async def test_unknown_template_paired_with_actual_phone_text_is_not_blind_attachment():
    events = await InstagramChannel().receive_message(webhook([
        entry("known_phone", PHONE), entry("unknown_template", attachment={"type": "template", "payload": {"generic": {"elements": []}}})]))
    assert len(events) == 1 and events[0]["kind"] == "user"
    assert events[0]["text"] == PHONE and "non_text" not in events[0]
    assert {events[0]["mid"], *events[0]["related_mids"]} == {"known_phone", "unknown_template"}


async def test_phone_card_mid_survives_shared_media_merge(monkeypatch):
    monkeypatch.setattr(settings, "shared_media_enabled", True)
    events = await InstagramChannel().receive_message(webhook([
        entry("mixed_phone", PHONE), entry("mixed_card", attachment=card()),
        entry("mixed_post", attachment={"type": "ig_post", "payload": {"id": "123"}})]))
    assert len(events) == 1
    assert {events[0]["mid"], *events[0]["related_mids"]} == {"mixed_phone", "mixed_card", "mixed_post"}
