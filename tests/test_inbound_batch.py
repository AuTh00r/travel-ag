from tests.model_responses import tool_response
from tests.model_responses import reply_json
import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.channels.instagram import InstagramChannel, _MidSet
from src.config import settings


def message(mid, text=None, attachment=None, sender="BATCH_CLIENT"):
    msg = {"mid": mid}
    if text is not None:
        msg["text"] = text
    if attachment is not None:
        msg["attachments"] = [attachment]
    return {"sender": {"id": sender}, "message": msg}


EMPTY = {"type": "template", "payload": {"generic": {"elements": []}}}


@pytest.mark.parametrize("kind", ["sticker", "gif", "animated_image"])
@pytest.mark.parametrize("reply", [None, {"mid": "old"}, {"story": {"id": "123"}}])
async def test_ignored_attachment_reserves_mid_without_starting_batch(batch, kind, reply):
    main, send, flush, _, waits, process, fallback, shared, _ = batch
    item = message("ignored_media", attachment={"type": kind})
    if reply:
        item["message"]["reply_to"] = reply
    await send(item)
    await send(item)
    await flush()
    assert "ignored_media" in main._processed_mids
    assert waits == [] and main._inbound_batches == {}
    process.assert_not_awaited()
    fallback.assert_not_awaited()
    shared.assert_not_awaited()


@pytest.mark.parametrize("kind", ["file", "product", "ig_product"])
@pytest.mark.parametrize("question", [None, "Посмотрите, пожалуйста"])
@pytest.mark.parametrize("story", [False, True])
async def test_file_product_question_goes_to_manager_without_ai(batch, kind, question, story):
    _, send, flush, _, _, process, fallback, _, _ = batch
    item = message("file_product", question, attachment={"type": kind})
    if story:
        item["message"]["reply_to"] = {"story": {"id": "123"}}
    await send(item)
    await flush()
    process.assert_not_awaited()
    fallback.assert_awaited_once()
    assert fallback.await_args.args[:2] == ("BATCH_CLIENT", question or "")
    assert fallback.await_args.args[2]["types"] == ([kind, "story_reply"] if story and question is None else [kind])


async def test_photo_two_videos_and_question_keep_all_sources_in_batch(batch, monkeypatch):
    _, send, flush, _, _, process, fallback, _, _ = batch
    monkeypatch.setattr(settings, "image_media_enabled", True)
    urls = ["https://scontent.cdninstagram.com/" + name for name in ("image.jpg", "clip.mp4", "direct.mp4")]
    for index, kind in enumerate(("image", "video", "video")):
        await send(message(f"mixed_{index}", attachment={"type": kind, "payload": {"url": urls[index]}}))
    await send(message("mixed_question", "Какие даты?"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Какие даты?", image_urls=urls,
                                    image_types=["image", "video", "video"])
    fallback.assert_not_awaited()


@pytest.mark.parametrize('referral_first', [False, True])
async def test_shared_post_and_ad_question_dispatch_once_in_both_orders(batch, monkeypatch, referral_first):
    main, send, flush, _, _, process, fallback, _, _ = batch
    monkeypatch.setattr(settings, 'shared_media_enabled', True)
    source = message('ad_source', attachment={'type': 'share',
        'payload': {'ig_post_media_id': '17943390366326685'}})
    question = message('ad_question', 'Визы нет. Какие варианты с открытием визы?')
    referral = {'source': 'ADS', 'type': 'OPEN_THREAD', 'ad_id': '120252331324000736'}
    question['referral'] = referral
    for event in ([question, source] if referral_first else [source, question]):
        await send(event)
    await flush()
    process.assert_awaited_once_with('BATCH_CLIENT', question['message']['text'],
        shared_sources=[{'id': '17943390366326685', 'url': None}])
    fallback.assert_not_awaited()
    assert {'ad_source', 'ad_question'} <= set(main._processed_mids._data)


@pytest.fixture
async def batch(monkeypatch):
    import src.main as main

    gate = asyncio.Event()
    waits = []

    async def wait():
        waits.append(main._INBOUND_WAIT_SECONDS)
        await gate.wait()

    monkeypatch.setattr(settings, "instagram_app_secret", "")
    monkeypatch.setattr(settings, "instagram_access_token", "")
    monkeypatch.setattr(main, "instagram", InstagramChannel())
    monkeypatch.setattr(main, "_processed_mids", _MidSet())
    monkeypatch.setattr(main, "_inbound_batches", {}, raising=False)
    monkeypatch.setattr(main, "_inbound_tasks", {}, raising=False)
    monkeypatch.setattr(main, "_inbound_locks", {}, raising=False)
    monkeypatch.setattr(main, "_story_reactions", {}, raising=False)
    monkeypatch.setattr(main, "_INBOUND_WAIT_SECONDS", 5, raising=False)
    monkeypatch.setattr(main, "_wait_inbound_window", wait, raising=False)
    monkeypatch.setattr(main, "_manager_pending", {})
    process, fallback, shared, manager = (AsyncMock() for _ in range(4))
    monkeypatch.setattr(main, "_process_safely", process)
    monkeypatch.setattr(main, "_process_non_text_safely", fallback)
    monkeypatch.setattr(main, "_process_silent_handoff", AsyncMock())
    monkeypatch.setattr(main, "_process_shared_post_safely", shared)
    monkeypatch.setattr(main, "_mark_manager_active", manager)
    tasks_before = set(main._background_tasks)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                base_url="http://test") as client:
        async def send(*entries):
            response = await client.post("/webhook/instagram", json={"entry": [{"messaging": list(entries)}]})
            assert response.status_code == 200
            await asyncio.sleep(0)

        async def flush():
            gate.set()
            tasks = set(main._background_tasks) - tasks_before
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                assert all(not isinstance(result, BaseException) or isinstance(result, asyncio.CancelledError)
                           for result in results)

        yield main, send, flush, gate, waits, process, fallback, shared, manager
    for task in set(main._background_tasks) - tasks_before:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("text", ["+375290000000", "Предлагаем сотрудничество. Контакт: +375290000000"])
async def test_separate_posts_collect_text_and_empty_template_once(batch, reverse, text):
    main, send, flush, gate, waits, process, fallback, _, _ = batch
    entries = [message("business", text), message("card", attachment=EMPTY)]
    if reverse:
        entries.reverse()
    await send(entries[0])
    await send(entries[1])
    await send(entries[1])
    process.assert_not_awaited()
    fallback.assert_not_awaited()
    assert waits == [5, 5]  # New card resets the timer; its repeated MID does not.
    assert all(mid in main._processed_mids for mid in ("business", "card"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", text)
    fallback.assert_not_awaited()
    await send(*entries)  # retries after flush are also ignored
    assert process.await_count == 1


async def test_text_order_and_senders_are_independent(batch):
    _, send, flush, _, waits, process, fallback, _, _ = batch
    await send(message("a1", "Хочу Прагу"))
    await send(message("b1", "Хочу Париж", sender="OTHER"))
    await send(message("a2", "Какая цена?"), message("a3", attachment=EMPTY))
    assert waits == [5, 5, 5]  # Each client has its own timer; a2/a3 restart ours.
    await flush()
    assert {call.args for call in process.await_args_list} == {
        ("BATCH_CLIENT", "Хочу Прагу\nКакая цена?"), ("OTHER", "Хочу Париж")}
    fallback.assert_not_awaited()


async def test_late_empty_template_opens_new_window_without_old_phone_cache(batch):
    _, send, flush, gate, waits, process, fallback, _, _ = batch
    await send(message("first", "+375290000000"))
    await flush()
    gate.clear()
    await send(message("late", attachment=EMPTY))
    assert waits == [5, 5]
    fallback.assert_not_awaited()
    await flush()
    assert process.await_count == 1
    fallback.assert_awaited_once()


async def test_nonempty_template_is_preserved_with_all_text(batch):
    _, send, flush, _, _, process, fallback, _, _ = batch
    template = {"type": "template", "payload": {"generic": {"elements": [{"title": "Тур"}]}}}
    await send(message("q1", "Хочу тур"))
    await send(message("q2", "На ноябрь"), message("t1", attachment=template))
    await flush()
    assert process.await_count == 1
    assert "Хочу тур\nНа ноябрь" in process.await_args.args[1]
    assert "template" in process.await_args.args[1]
    fallback.assert_not_awaited()


async def test_distinct_story_contexts_keep_their_questions(batch, monkeypatch):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    first, second = message("s1", "Цена Праги?"), message("s2", "Даты Парижа?")
    first["message"]["reply_to"] = {"story": {"id": "123"}}
    second["message"]["reply_to"] = {"story": {"id": "456"}}
    await send(first, second)
    await flush()
    assert [call.args for call in process.await_args_list] == [
        ("BATCH_CLIENT", "Цена Праги?", {"id": "123"}),
        ("BATCH_CLIENT", "Даты Парижа?", {"id": "456"})]


def reaction(mid="reaction", story_id="123", sender="BATCH_CLIENT"):
    item = message(mid, "👏", sender=sender)
    item["message"]["reply_to"] = {"story": {"id": story_id, "url": "https://example.com/cover.jpg"}}
    return item


@pytest.mark.parametrize("delay", [25, 121, 599])
async def test_story_reaction_then_next_question_within_ten_minutes(batch, monkeypatch, delay):
    main, send, flush, _, waits, process, fallback, shared, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    now = [100.0]
    monkeypatch.setattr(main, "monotonic", lambda: now[0], raising=False)
    await send(reaction())
    assert "reaction" in main._processed_mids
    assert waits == []
    process.assert_not_awaited()
    fallback.assert_not_awaited()
    shared.assert_not_awaited()
    now[0] += delay
    await send(message("question", "можно подробнее"))
    await send(message("dates", "Какие даты?"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "можно подробнее\nКакие даты?", {"id": "123"})
    await send(message("next", "Другой вопрос"))
    await flush()
    assert process.await_args.args == ("BATCH_CLIENT", "Другой вопрос")


@pytest.mark.parametrize("delay", [600, 601])
async def test_story_reaction_expires_without_retry_refresh(batch, monkeypatch, delay):
    main, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    now = [100.0]
    monkeypatch.setattr(main, "monotonic", lambda: now[0], raising=False)
    await send(reaction())
    now[0] += 599
    await send(reaction())  # same MID cannot extend TTL
    now[0] = 100 + delay
    await send(message("expired", "Подробнее"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее")


async def test_reaction_snapshot_does_not_change_when_new_reaction_arrives(batch, monkeypatch):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    await send(message("q1", "Подробнее"))
    await send(reaction("reaction2", "456"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее", {"id": "123"})
    await send(message("q2", "Цена?"))
    await flush()
    assert process.await_args.args == ("BATCH_CLIENT", "Цена?", {"id": "456"})


async def test_reaction_context_is_sender_scoped(batch, monkeypatch):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    await send(message("other", "Подробнее", sender="OTHER"))
    await send(message("mine", "Цена?"))
    await flush()
    assert sorted((call.args for call in process.await_args_list), key=lambda args: args[0]) == [
        ("BATCH_CLIENT", "Цена?", {"id": "123"}), ("OTHER", "Подробнее")]


@pytest.mark.parametrize("previous_question", [False, True])
async def test_reaction_creates_plain_merge_boundary(batch, monkeypatch, previous_question):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    if previous_question:
        await send(message("first", "Первый вопрос"))
    else:
        await send(reaction())
        await send(message("first", "Первый вопрос"))
    await send(reaction("second_reaction", "456"))
    await send(message("second", "Второй вопрос"))
    await send(message("second_dates", "А даты?"))
    await flush()
    assert [call.args for call in process.await_args_list] == [
        (("BATCH_CLIENT", "Первый вопрос") if previous_question else
         ("BATCH_CLIENT", "Первый вопрос", {"id": "123"})),
        ("BATCH_CLIENT", "Второй вопрос\nА даты?", {"id": "456"})]


@pytest.mark.parametrize("invalid", [None, "bad", {}, "9" * 33])
async def test_invalid_reaction_clears_previous_story(batch, monkeypatch, invalid):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    await send(reaction("invalid", invalid))
    await send(message("q", "Подробнее"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее")


@pytest.mark.parametrize("reason", ["unsupported", "attachment", "flag"])
async def test_unusable_reaction_does_not_save_story(batch, monkeypatch, reason):
    main, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", reason != "flag")
    item = reaction()
    if reason == "unsupported":
        item["message"]["is_unsupported"] = True
    elif reason == "attachment":
        item["message"]["attachments"] = [{"type": "file"}]
    await send(item)
    assert not main._story_reactions
    await send(message("q", "Подробнее"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее")


@pytest.mark.parametrize("kind", ["image", "video", "ig_reel", "file", "template"])
async def test_new_media_consumes_story_and_keeps_own_path(batch, monkeypatch, kind):
    main, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    monkeypatch.setattr(settings, "image_media_enabled", True)
    monkeypatch.setattr(settings, "shared_media_enabled", True)
    await send(reaction())
    await send(message("media", attachment={"type": kind, "payload": {"url": "https://scontent.cdninstagram.com/test", "reel_video_id": "456"}}))
    assert not main._story_reactions
    await flush()
    process.reset_mock()
    await send(message("q", "Подробнее"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее")


async def test_media_in_followup_batch_has_priority_over_saved_story(batch, monkeypatch):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    monkeypatch.setattr(settings, "image_media_enabled", True)
    await send(reaction())
    await send(message("q", "Подробнее"))
    url = "https://scontent.cdninstagram.com/new.jpg"
    await send(message("photo", attachment={"type": "image", "payload": {"url": url}}))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее", image_urls=[url])


async def test_explicit_story_overrides_reaction(batch, monkeypatch):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    item = message("explicit", "Подробнее")
    item["message"]["reply_to"] = {"story": {"id": "456"}}
    await send(item)
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее", {"id": "456"})


async def test_manager_clears_reaction_context(batch, monkeypatch):
    main, send, flush, _, _, process, _, _, manager = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    await send({"sender": {"id": "ACCOUNT"}, "recipient": {"id": "BATCH_CLIENT"},
                "message": {"mid": "echo", "is_echo": True, "text": "Отвечает менеджер"}})
    manager.assert_awaited_once()
    assert not main._story_reactions
    await send(message("q", "Подробнее"))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Подробнее")


async def test_reaction_cache_is_bounded_and_prunes_expired(batch, monkeypatch):
    main, send, _, _, _, _, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    monkeypatch.setattr(main, "_STORY_REACTIONS_MAX", 2, raising=False)
    now = [100.0]
    monkeypatch.setattr(main, "monotonic", lambda: now[0], raising=False)
    for index in range(3):
        await send(reaction(f"r{index}", sender=f"S{index}"))
    assert list(main._story_reactions) == ["S1", "S2"]
    now[0] += 600
    await send(reaction("fresh", sender="FRESH"))
    assert list(main._story_reactions) == ["FRESH"]


@pytest.mark.parametrize("phone", ["+375290000000", "Номер в телефонной карточке: +375290000000"])
async def test_multiline_contact_does_not_inherit_reaction(batch, monkeypatch, phone):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    text = "Можно подробнее\n" + phone
    await send(message("contact", text))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", text)


async def test_dates_budget_are_still_story_questions(batch, monkeypatch):
    _, send, flush, _, _, process, _, _, _ = batch
    monkeypatch.setattr(settings, "story_media_enabled", True)
    await send(reaction())
    text = "Можно подробнее\n10-13 декабря\nБюджет 1000"
    await send(message("dates_budget", text))
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", text, {"id": "123"})


async def test_manager_bypasses_wait_and_cancels_collected_input(batch):
    main, send, flush, _, _, process, fallback, _, manager = batch
    await send(message("u1", "Хочу тур"))
    await send(message("u2", "Уточнение"))
    waiting = main._inbound_tasks['BATCH_CLIENT']
    main.instagram.receive_message = AsyncMock(return_value=[{
        "kind": "manager", "sender_id": "ACCOUNT", "client_id": "BATCH_CLIENT",
        "mid": "manager1", "text": "Отвечает менеджер"}])
    await send(message("ignored"))
    manager.assert_awaited_once_with("BATCH_CLIENT", "Отвечает менеджер")
    await flush()
    assert waiting.cancelled()
    assert 'BATCH_CLIENT' not in main._inbound_batches
    process.assert_not_awaited()
    fallback.assert_not_awaited()


async def test_arrivals_during_ai_get_next_batch_and_wait_for_previous(batch):
    _, send, flush, gate, waits, process, _, _, _ = batch
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        if args[1] == "Первый вопрос":
            started.set()
            await release.wait()

    process.side_effect = slow
    await send(message("slow1", "Первый вопрос"))
    gate.set()
    await started.wait()
    gate.clear()
    await send(message("slow2", "Второй вопрос"))
    assert waits == [5, 5]
    gate.set()
    await asyncio.sleep(0)
    assert process.await_count == 1
    release.set()
    await flush()
    assert [call.args[1] for call in process.await_args_list] == ["Первый вопрос", "Второй вопрос"]


async def test_new_mid_replaces_only_waiting_collector_and_keeps_duplicate_text(batch):
    main, send, flush, _, waits, process, _, _, _ = batch
    await send(message('first', 'Хочу в тур'))
    old = main._inbound_tasks['BATCH_CLIENT']
    await send(message('second', 'Хочу в тур'))
    latest = main._inbound_tasks['BATCH_CLIENT']
    assert latest is not old
    await asyncio.sleep(0)
    assert old.cancelled()
    assert not latest.done()
    assert len(main._inbound_batches['BATCH_CLIENT']) == 2
    await send(message('second', 'Хочу в тур'))
    assert main._inbound_tasks['BATCH_CLIENT'] is latest
    assert waits == [5, 5]
    await flush()
    process.assert_awaited_once_with('BATCH_CLIENT', 'Хочу в тур\nХочу в тур')


@pytest.mark.parametrize("kind", ["image", "ig_reel"])
async def test_media_from_separate_post_keeps_exact_source_and_caption(batch, monkeypatch, kind):
    _, send, flush, _, _, process, fallback, _, _ = batch
    monkeypatch.setattr(settings, "image_media_enabled", True)
    monkeypatch.setattr(settings, "shared_media_enabled", True)
    url = "https://scontent.cdninstagram.com/test.jpg"
    attachment = {"type": kind, "payload": {"url": url, "reel_video_id": "123"}}
    await send(message("media", attachment=attachment))
    await send(message("caption", "Цена?"), message("empty", attachment=EMPTY))
    await flush()
    assert process.await_count == 1 and process.await_args.args == ("BATCH_CLIENT", "Цена?")
    assert process.await_args.kwargs == ({"image_urls": [url]} if kind == "image" else {
        "shared_sources": [{"id": "123", "url": url}]})
    fallback.assert_not_awaited()


async def test_legacy_post_and_audio_keep_all_events_and_mids(monkeypatch):
    monkeypatch.setattr(settings, "shared_media_enabled", False)
    events = await InstagramChannel().receive_message({"entry": [{"messaging": [
        message("post", attachment={"type": "ig_post"}),
        message("audio", attachment={"type": "audio"}), message("q", "Цена?")]}]})
    assert len(events) == 2
    assert {mid for ev in events for mid in [ev["mid"], *ev.get("related_mids", [])]} == {"post", "audio", "q"}
    assert any(ev["kind"] == "user_shared_post" for ev in events)


@pytest.mark.parametrize("pending", [True, False])
async def test_failing_ai_is_silent_after_manager_takeover(monkeypatch, pending):
    import src.main as main
    started, release = asyncio.Event(), asyncio.Event()

    async def failing(*args, **kwargs):
        started.set()
        await release.wait()
        raise RuntimeError("MOCK_AI_FAILURE")

    monkeypatch.setattr(main, "process_with_ai", failing)
    monkeypatch.setattr(main, "_manager_pending", {})
    session = {}
    monkeypatch.setattr(main, "get_session", AsyncMock(side_effect=lambda _: session))
    send = AsyncMock()
    monkeypatch.setattr(main, "_send_or_queue", send)
    task = asyncio.create_task(main._process_safely("TAKEOVER", "Цена?"))
    await started.wait()
    if pending:
        main._manager_pending["TAKEOVER"] = 1
    else:
        from datetime import datetime, timezone
        session["manager_last_at"] = datetime.now(timezone.utc).isoformat()
    release.set()
    await task
    send.assert_not_awaited()


@pytest.mark.parametrize("detail", ["2026-12-09", "12000000"])
async def test_collected_date_or_budget_does_not_force_phone_escalation(monkeypatch, detail):
    from types import SimpleNamespace
    from src.services import guard
    import src.main as main
    guard._user_timestamps.clear()
    main._processing_locks.clear()
    main._locks.clear()
    invoke = AsyncMock(return_value=tool_response(arguments=reply_json("Уточню доступность тура.")))
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Каталог")
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), "send_message", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr("src.services.telegram_notify.TelegramNotifier.notify_manager", notify)
    await main.process_with_ai("DATE_BUDGET", "Хочу Прагу\n" + detail)
    notify.assert_not_awaited()
    invoke.assert_awaited_once()


async def test_real_five_second_window_returns_meta_immediately(monkeypatch):
    import time
    import src.main as main
    monkeypatch.setattr(settings, "instagram_app_secret", "")
    monkeypatch.setattr(settings, "instagram_access_token", "")
    monkeypatch.setattr(main, "_inbound_batches", {})
    monkeypatch.setattr(main, "_inbound_tasks", {})
    monkeypatch.setattr(main, "_inbound_locks", {})
    monkeypatch.setattr(main, "_processed_mids", _MidSet())
    monkeypatch.setattr(main, "instagram", InstagramChannel())
    process = AsyncMock()
    monkeypatch.setattr(main, "_process_safely", process)
    started = time.monotonic()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/webhook/instagram", json={"entry": [{"messaging": [message("real_timer", "Цена?")]}]})
        assert response.status_code == 200 and time.monotonic() - started < 1
        task = main._inbound_tasks["BATCH_CLIENT"]
        await asyncio.sleep(1)
        process.assert_not_awaited()
        await asyncio.wait_for(task, timeout=6)
    assert time.monotonic() - started >= 5
    process.assert_awaited_once_with("BATCH_CLIENT", "Цена?")


@pytest.mark.parametrize("reverse", [False, True])
async def test_mention_and_question_keep_independent_silent_and_ai_routes(batch, monkeypatch, reverse):
    main, send, flush, _, waits, process, fallback, _, _ = batch
    monkeypatch.setattr(settings, "image_media_enabled", True)
    url = "https://scontent.cdninstagram.com/mention.jpg"
    entries = [message("mention_photo", attachment={"type": "story_mention", "payload": {"url": url}}),
               message("mention_question", "Спасибо за поездку!")]
    if reverse:
        entries.reverse()
    await send(entries[0])
    await send(entries[1])
    process.assert_not_awaited()
    assert waits == [5, 5]
    await flush()
    process.assert_awaited_once_with("BATCH_CLIENT", "Спасибо за поездку!")
    main._process_silent_handoff.assert_awaited_once_with("BATCH_CLIENT", "", "story_mention")
    fallback.assert_not_awaited()


@pytest.mark.parametrize("enabled", [True, False])
async def test_mention_without_question_is_silent_regardless_image_flag(batch, monkeypatch, enabled):
    main, send, flush, _, _, process, fallback, _, _ = batch
    monkeypatch.setattr(settings, "image_media_enabled", enabled)
    url = "https://scontent.cdninstagram.com/mention.jpg"
    await send(message("mention_only", attachment={"type": "story_mention", "payload": {"url": url}}))
    await flush()
    process.assert_not_awaited()
    fallback.assert_not_awaited()
    main._process_silent_handoff.assert_awaited_once_with("BATCH_CLIENT", "", "story_mention")
