from tests.model_responses import tool_response
from unittest.mock import AsyncMock, patch

import pytest

from src.main import _strip_markers, _validate_response
from tests.model_responses import manager_data, model_response, reply_json


# --- Marker parsing ---


class TestStructuredEscalation:
    @pytest.mark.parametrize('type', ['консультация', 'контакт', 'отзыв'])
    def test_manager_data_separate_from_reply(self, type):
        manager = manager_data('Клиент интересуется туром.', type, 'Иван')
        result, error = _validate_response(reply_json('Ответ.', manager))
        assert error is None and result == {'reply': 'Ответ.', 'manager': manager}

    def test_no_notification_is_explicit_null(self):
        assert _validate_response(reply_json('Ответ.')) == ({'reply': 'Ответ.', 'manager': None}, None)

    def test_manager_without_context_is_rejected(self):
        assert _validate_response(reply_json('Ответ.', manager_data('')))[1] == 'empty_context'


class TestStripMarkers:
    def test_strips_escalation_marker(self):
        text = "Привет!\n\n===МЕНЕДЖЕР===\nПричина: тест\n===МЕНЕДЖЕР==="
        result = _strip_markers(text)
        assert "===МЕНЕДЖЕР===" not in result
        assert "Привет!" in result


@pytest.mark.parametrize("ending", ["", "\n===МЕНЕДЖЕР==="])
def test_legacy_contact_block_is_hidden_but_rejected_in_fresh_reply(ending):
    text = ("Спасибо, номер получил.\n\n===МЕНЕДЖЕР===\nТип: контакт\n"
            "Контекст: Клиент оставил контакт для звонка\nТелефон: +375290000000" + ending)
    assert _validate_response(reply_json(text))[1] == 'service_marker'
    assert _strip_markers(text) == "Спасибо, номер получил."


@pytest.mark.parametrize("header", ["===МЕНЕДЖЕР===", "===МЕНЕДЖЕР", "== МЕНЕДЖЕР ==", "===менеджер==="])
def test_incomplete_or_variant_service_header_never_leaks(header):
    assert _strip_markers("Ответ клиенту.\n" + header + "\nКонтекст: PRIVATE SERVICE") == "Ответ клиенту."


@pytest.mark.parametrize("visible", ["Спасибо, номер получил.", ""])
@pytest.mark.parametrize("phone_field", [True, False])
async def test_unclosed_escalation_notifies_and_saves_only_visible_reply(monkeypatch, visible, phone_field):
    from types import SimpleNamespace
    from src.db.sessions import get_session, save_session
    from src.services import guard
    import src.main as main

    guard._user_timestamps.clear()
    main._processing_locks.clear()
    main._locks.clear()
    notify = AsyncMock()
    send = AsyncMock()
    response = model_response(visible or 'Спасибо, номер получил.',
        manager_data('PRIVATE SERVICE', 'контакт') if phone_field else None)
    invoke = AsyncMock(return_value=response)
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Каталог")
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), "send_message", send)
    monkeypatch.setattr("src.services.telegram_notify.TelegramNotifier.notify_manager", notify)
    await save_session("UNCLOSED_CONTACT", {"history": [{"role": "assistant", "content":
        "Старый ответ.\n===МЕНЕДЖЕР===\nКонтекст: OLD PRIVATE SERVICE"}]})
    await main.process_with_ai("UNCLOSED_CONTACT", "+375290000000")
    notify.assert_awaited_once()
    assert notify.await_args.kwargs["client_phone"] == "+375290000000"
    expected = "Спасибо, передал ваш номер менеджерам. Они свяжутся с вами в рабочее время."
    send.assert_awaited_once_with("UNCLOSED_CONTACT", expected)
    history = (await get_session("UNCLOSED_CONTACT"))["history"]
    assert history[-1]["content"] == expected
    assert "PRIVATE SERVICE" not in history[-1]["content"]
    assert "OLD PRIVATE SERVICE" not in str(invoke.await_args.args[0])
    assert "OLD PRIVATE SERVICE" in history[0]["content"]  # БД не переписывается.


@pytest.mark.parametrize("outcome", ["success", "failure", "limit"])
@pytest.mark.parametrize("current_text", ["+375290000000", "Номер в телефонной карточке: +375290000000",
    "Хочу звонок по Дрездену\nНомер в телефонной карточке: +375290000000"])
async def test_actual_phone_notifies_without_ai_marker_and_ack_matches_delivery(monkeypatch, outcome, current_text):
    from types import SimpleNamespace
    from src.db.sessions import get_session, save_session
    from src.services import guard
    import src.main as main

    guard._user_timestamps.clear()
    main._processing_locks.clear()
    main._locks.clear()
    notify = AsyncMock(side_effect=RuntimeError("MOCK_SEND_FAILURE") if outcome == "failure" else None)
    send = AsyncMock()
    invoke = AsyncMock(return_value=model_response("ДЛИННЫЙ СТАРЫЙ ОТВЕТ БЕЗ МАРКЕРА"))
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Каталог")
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), "send_message", send)
    monkeypatch.setattr("src.services.telegram_notify.TelegramNotifier.notify_manager", notify)
    await save_session("PHONE_WITHOUT_MARKER", {"history": [
        {"role": "user", "content": "Хочу тур в Прагу"},
        {"role": "assistant", "content": "Контакт уже передан менеджерам."}],
        "escalation_count": 3 if outcome == "limit" else 0})
    await main.process_with_ai("PHONE_WITHOUT_MARKER", current_text)
    state = await get_session("PHONE_WITHOUT_MARKER")
    if outcome == "limit":
        notify.assert_not_awaited()
        expected = ("Спасибо, ваш номер сохранён. Новое уведомление менеджеру не отправлено: "
            "достигнут лимит повторных обращений. Вы можете связаться с менеджерами напрямую.")
    else:
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["client_phone"] == "+375290000000"
        if "Хочу звонок по Дрездену" in current_text:
            assert "Хочу звонок по Дрездену" in notify.await_args.kwargs["context"]
            assert "Хочу тур в Прагу" not in notify.await_args.kwargs["context"]
        else:
            assert "Хочу тур в Прагу" in notify.await_args.kwargs["context"]
        expected = ("Спасибо, передал ваш номер менеджерам. Они свяжутся с вами в рабочее время."
            if outcome == "success" else "Спасибо, ваш номер сохранён. Не удалось подтвердить передачу нового обращения менеджеру. Пожалуйста, повторите сообщение позже или свяжитесь с менеджерами напрямую.")
    if "Хочу звонок по Дрездену" in current_text:
        receipt = {
            "success": "Ваш запрос передан менеджеру.",
            "failure": "Не удалось подтвердить передачу нового обращения менеджеру. Пожалуйста, повторите сообщение позже или свяжитесь с менеджерами напрямую.",
            "limit": "Новое уведомление менеджеру не отправлено: достигнут лимит повторных обращений. Вы можете связаться с менеджерами напрямую.",
        }[outcome]
        if outcome == "success":
            from datetime import datetime
            from src.config import MINSK_TZ
            if not 10 <= datetime.now(MINSK_TZ).hour < 18:
                receipt += " Менеджер ответит в рабочее время с 10:00 до 18:00."
        expected = "ДЛИННЫЙ СТАРЫЙ ОТВЕТ БЕЗ МАРКЕРА\n\n" + receipt
    send.assert_awaited_once_with("PHONE_WITHOUT_MARKER", expected)
    assert state["history"][-1]["content"] == expected
    assert state["escalation_count"] == (1 if outcome == "success" else 3 if outcome == "limit" else 0)
    invoke.assert_awaited_once()


# --- Prompt building ---


@pytest.mark.parametrize("case", ["video", "photo", "new_topic", "unavailable", "missing", "chunks", "phone_footer", "long", "current_question", "no_caption", "no_caption_unavailable", "post_without_question", "link_before_tour", "link_label_before_tour"])
async def test_contact_escalation_includes_paired_human_media_context(monkeypatch, case):
    from types import SimpleNamespace
    from src.db.sessions import get_session, save_session
    from src.services import guard
    from src.services.telegram_notify import _build_notification_text
    import src.main as main

    guard._user_timestamps.clear()
    main._processing_locks.clear()
    main._locks.clear()
    notify, send = AsyncMock(), AsyncMock()
    invoke = AsyncMock(return_value=model_response("Спасибо. CURRENT_REPLY_MUST_NOT_BE_CONTEXT"))
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Каталог")
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), "send_message", send)
    monkeypatch.setattr("src.services.telegram_notify.TelegramNotifier.notify_manager", notify)
    marker = "[Ответ на историю 17914225719521132, " + ("IMAGE" if case == "photo" else "VIDEO") + "]"
    history = [
        {"role": "user", "content": "Хочу Прагу"},
        {"role": "assistant", "content": "OLD_UNRELATED_PRAGUE"},
        {"role": "user", "content": "можно подробнее\n" + marker}]
    if case.startswith("no_caption"):
        history[-1]["content"] = main._IMAGE_NO_CAPTION + "\n[Изображений: 1]"
    elif case == "post_without_question":
        history[-1]["content"] = main._POST_NO_QUESTION + "\n[Публикация/Reels, медиа обработано]"
    answer = "Это горнолыжный отдых на Эльбрусе. Даты: 10–13 декабря. Цена: 12000."
    if case == "unavailable":
        answer = main._STORY_UNAVAILABLE
    elif case == "no_caption_unavailable":
        answer = main._IMAGE_UNAVAILABLE
    elif case == "phone_footer":
        answer += "\nКонтакт менеджера: +375290000009\n===МЕНЕДЖЕР===\nКонтекст: SECRET_SERVICE"
    elif case == "long":
        answer += "\n" + "Подробности тура. " * 250
    if case in {"link_before_tour", "link_label_before_tour"}:
        label = "Ссылка на тур: " if case == "link_label_before_tour" else ""
        answer = "Здравствуйте!\n" + label + "https://docs.google.com/document/d/example\n" + answer
    if case != "missing":
        history.append({"role": "assistant", "content": answer})
    if case == "chunks":
        history.append({"role": "assistant", "content": "Включены проживание и проезд."})
    if case == "new_topic":
        history.extend([{"role": "user", "content": "Теперь хочу Париж"},
                        {"role": "assistant", "content": "NEW_PARIS_ANSWER"}])
    current = "Хочу звонок по Дрездену\n+375290000001" if case == "current_question" else "+375290000001"
    await save_session("HUMAN_CONTACT_CONTEXT", {"history": history, "escalation_count": 0})
    await main.process_with_ai("HUMAN_CONTACT_CONTEXT", current)
    notify.assert_awaited_once()
    data = notify.await_args.kwargs
    context = data["context"]
    assert data["client_phone"] == "+375290000001" and data["tag"] == "контакт"
    assert "OLD_UNRELATED_PRAGUE" not in context
    assert "17914225719521132" not in context and "VIDEO" not in context and "IMAGE" not in context
    assert "CURRENT_REPLY_MUST_NOT_BE_CONTEXT" not in context
    assert "SECRET_SERVICE" not in context and "+375290000009" not in context
    assert "https://" not in context and "Здравствуйте" not in context
    if case == "current_question":
        assert "Хочу звонок по Дрездену" in context and "Эльбрусе" not in context
    elif case == "new_topic":
        assert "Теперь хочу Париж" in context and "NEW_PARIS_ANSWER" in context and "Эльбрусе" not in context
    else:
        if case.startswith("no_caption"):
            assert "без подписи" in context and "Фото/видео клиента" in context
        elif case == "post_without_question":
            assert "публикацию/Reels без вопроса" in context
        else:
            assert "можно подробнее" in context
            assert ("фотоистории" if case == "photo" else "видеоистории") in context
        if case == "missing":
            assert "Эльбрусе" not in context and "Клиенту ответили" not in context
        else:
            assert "Клиенту ответили" not in context
            assert ("Это горнолыжный отдых на Эльбрусе." if case not in {"unavailable", "no_caption_unavailable"} else answer.split(". ")[0]) in context
        if case == "chunks":
            assert "Включены проживание и проезд." not in context
    assert len(context) <= 450
    assert "Подробности тура." not in context
    assert len(_build_notification_text(**data)) < 4096
    assert (await get_session("HUMAN_CONTACT_CONTEXT"))["history"][:len(history)] == history
    invoke.assert_awaited_once()



@pytest.mark.parametrize("case", ["valid", "visa", "missing_context", "conflicting_phone", "long", "phone", "story_id", "url", "current_question", "no_model_phone", "consultation_valid", "consultation_long"])
async def test_contact_escalation_uses_short_model_gist(monkeypatch, case):
    from types import SimpleNamespace
    from src.db.sessions import get_session, save_session
    from src.services import guard
    import src.main as main

    guard._user_timestamps.clear()
    main._processing_locks.clear()
    main._locks.clear()
    notify, send = AsyncMock(), AsyncMock()
    gist = "Клиент с готовой визой интересуется туром Варшава–Берлин–Познань и спрашивает, есть ли в автобусе Wi-Fi."
    history = [
        {"role": "user", "content": "Виза готова. Есть ли Wi-Fi в автобусе на Варшаву–Берлин–Познань?"},
        {"role": "assistant", "content": "Здравствуйте! Это тур Варшава–Берлин–Познань. " + "Полная программа тура. " * 150}]
    if case == "visa":
        gist = "Клиент с готовой визой заинтересовался туром на Эльбрус из видеоистории, попросил подробности и оставил номер для связи."
        history = [{"role": "user", "content": "Виза уже есть"}, {"role": "assistant", "content": "Хорошо."},
                   {"role": "user", "content": "можно подробнее\n[Ответ на историю 17914225719521132, VIDEO]"},
                   {"role": "assistant", "content": "Это горнолыжный отдых на Эльбрусе. " + "Полная программа тура. " * 150}]
    candidate = {
        "long": gist + " Полная программа тура." * 100,
        "consultation_long": gist + " Полная программа тура." * 100,
        "phone": gist + " Телефон +375290000009",
        "story_id": gist + " [Ответ на историю 17914225719521132, VIDEO]",
        "url": gist + " https://example.com/video",
    }.get(case, gist)
    if case == 'conflicting_phone':
        candidate += ' Старый номер +375290000000.'
    manager = manager_data(candidate)
    if case == 'missing_context':
        manager.pop('context')
    raw = reply_json('Спасибо.', manager)
    invoke = AsyncMock(return_value=tool_response(arguments=raw))
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Каталог")
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), "send_message", send)
    monkeypatch.setattr("src.services.telegram_notify.TelegramNotifier.notify_manager", notify)
    current = "Теперь хочу тур в Дрезден на 2026-12-09, бюджет 12000\n+375290000001" if case == "current_question" else "+375290000001"
    if case.startswith("consultation"):
        current = "Виза готова. Есть ли Wi-Fi в автобусе на Варшаву–Берлин–Познань?"
    await save_session("SHORT_CONTACT_GIST", {"history": history, "escalation_count": 0})
    await main.process_with_ai("SHORT_CONTACT_GIST", current)
    data = notify.await_args.kwargs
    assert data["client_phone"] == (None if case.startswith("consultation") else "+375290000001")
    if case in {'missing_context', 'long', 'consultation_long'}:
        assert data['tag'] == 'техническая ошибка'
        assert 'Диагностика:' in data['context'] and len(data['context']) <= 2000
        assert '+375290000001' not in data['context']
        assert 'Полная программа тура' not in data['context']
        send.assert_not_awaited()
        return
    assert data["tag"] == ("консультация" if case.startswith("consultation") else "контакт")
    context = data["context"]
    assert len(context) <= 450
    assert "Полная программа тура" not in context and "Здравствуйте" not in context
    assert "17914225719521132" not in context and "+375290000009" not in context
    assert "https://" not in context and "===МЕНЕДЖЕР===" not in context
    if case in {"valid", "visa", "no_model_phone", "consultation_valid"}:
        assert context == gist
    elif case == "current_question":
        assert "Дрезден" in context and "2026-12-09" in context and "12000" in context
        assert "Познань" not in context
    elif case == "consultation_long":
        assert "Есть ли Wi-Fi" in context and "Варшаву–Берлин–Познань" in context
    else:
        assert "Есть ли Wi-Fi" in context and "Это тур Варшава–Берлин–Познань." in context
        assert context != candidate
    assert (await get_session("SHORT_CONTACT_GIST"))["history"][:len(history)] == history
    assert invoke.await_count == (2 if case in {'missing_context', 'long', 'consultation_long'} else 1)
    notify.assert_awaited_once()


def test_escalation_prompt_requires_short_gist_with_media_context():
    from src.ai.prompts import build_full_prompt
    prompt = build_full_prompt(tours_text="", faq_context="", history=[], message="+375290000001")[0].content
    assert "не более 450 символов" in prompt
    assert "Не копируй" in prompt and "программу тура" in prompt
    assert "Варшава–Берлин–Познань" in prompt and "Эльбрус" in prompt


@pytest.mark.parametrize("model_marker", [True, False])
@pytest.mark.parametrize("current_text", ["+375290000001", "Номер в телефонной карточке: +375290000001",
    "+375290000000\n+375290000001"])
@pytest.mark.parametrize("suffix", ["", " 12000", " 2026-12-09"])
async def test_changed_phone_overrides_old_marker_and_old_contact_context(monkeypatch, model_marker, current_text, suffix):
    from types import SimpleNamespace
    from src.db.sessions import get_session, save_session
    from src.services import guard
    import src.main as main

    guard._user_timestamps.clear()
    main._processing_locks.clear()
    main._locks.clear()
    notify = AsyncMock()
    send = AsyncMock()
    old_phone, current_phone = "+375290000000", "+375290000001"
    invoke = AsyncMock(return_value=model_response('Старое подтверждение.',
        manager_data('Клиент оставил номер ' + old_phone, name='Клиент ' + old_phone + suffix)
        if model_marker else None))
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Каталог")
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), "send_message", send)
    monkeypatch.setattr("src.services.telegram_notify.TelegramNotifier.notify_manager", notify)
    await save_session("CHANGED_CONTACT", {"history": [
        {"role": "user", "content": "Хочу тур в Прагу на 2026-12-09, бюджет 12000"},
        {"role": "user", "content": "Это мой номер: " + old_phone + suffix},
        {"role": "assistant", "content": "Передал номер " + old_phone},
        {"role": "user", "content": old_phone}], "escalation_count": 0})
    await main.process_with_ai("CHANGED_CONTACT", current_text)
    notify.assert_awaited_once()
    payload = notify.await_args.kwargs
    assert payload["client_phone"] == current_phone
    assert old_phone not in str(payload)
    assert "Хочу тур в Прагу" in payload["context"]
    assert "2026-12-09" in payload["context"] and "12000" in payload["context"]
    assert payload["tag"] == "контакт"
    send.assert_awaited_once_with("CHANGED_CONTACT",
        "Спасибо, передал ваш номер менеджерам. Они свяжутся с вами в рабочее время.")
    assert (await get_session("CHANGED_CONTACT"))["history"][-2]["content"] == current_text


def test_build_full_prompt_includes_tours():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="=== ТУР: Турция ===\nПляж",
        faq_context="",
        history=[],
        message="Хочу тур",
    )
    assert len(messages) == 2  # system + user
    assert "Турция" in messages[0].content
    assert messages[1].content == "Хочу тур"


def test_build_full_prompt_includes_history():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="",
        history=[
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте!"},
        ],
        message="Хочу тур",
    )
    assert len(messages) == 4  # system + user + assistant + user
    assert messages[1].content == "Привет"
    assert messages[2].content == "Здравствуйте!"


def test_build_full_prompt_includes_faq():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="Виза в Турцию делается за 5 дней",
        history=[],
        message="Нужна виза?",
    )
    assert "Виза в Турцию" in messages[0].content


def test_build_full_prompt_distinguishes_ambiguous_query_from_attachment():
    from src.ai.prompts import build_full_prompt

    messages = build_full_prompt(
        tours_text="",
        faq_context="",
        history=[],
        message="Сколько стоит?",
    )
    system_prompt = messages[0].content
    assert "ОДИН конкретный уточняющий вопрос" in system_prompt
    assert "Никогда не подтверждай передачу запроса" in system_prompt
    assert "одновременно сообщи, что передаёшь запрос менеджеру" not in system_prompt
    assert "Только если ТЕКУЩЕЕ сообщение содержит служебную пометку" in system_prompt


# --- DeepSeek prefix cache ---
#
# DeepSeek матчит кэш только по полному совпадению префикса с нулевого токена
# (api-docs.deepseek.com/guides/kv_cache), поэтому всё меняющееся между
# вызовами обязано быть в хвосте промпта. Раньше `Сейчас: ЧЧ:ММ` стоял в
# первых строках и обнулял кэш каждую минуту — ~30 тыс. знаков входа шли по
# цене cache miss вместо cache hit (в 50 раз дороже).


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def test_system_prompt_prefix_stable_across_minutes():
    """Смена минуты не должна менять ничего, кроме хвоста промпта."""
    from src.ai.prompts import _build_system

    tours = "=== ТУР: Турция ===\nПляж"
    at_1015 = _build_system(tours, "", current_time="10:15")
    at_1016 = _build_system(tours, "", current_time="10:16")

    assert at_1015 != at_1016, "время обязано попадать в промпт"
    shared = _common_prefix_len(at_1015, at_1016)
    assert shared / len(at_1015) > 0.95, (
        f"общий префикс всего {shared} из {len(at_1015)} знаков — "
        "что-то переменное уехало в начало промпта и ломает кэш DeepSeek"
    )


def test_tours_base_precedes_variable_blocks():
    """База туров — самая крупная статика, она обязана идти до FAQ и времени."""
    from src.ai.prompts import _build_system

    prompt = _build_system(
        "=== ТУР: Турция ===\nПляж",
        "Вопрос: нужна ли виза?",
        current_time="10:15",
    )
    assert prompt.index("=== ТУР: Турция ===") < prompt.index("нужна ли виза?")
    assert prompt.index("нужна ли виза?") < prompt.index("Сейчас: 10:15")


def test_current_time_is_last_block():
    from src.ai.prompts import _build_system

    prompt = _build_system("", "", current_time="10:15")
    assert prompt.rstrip().endswith(
        "Это поле «Сейчас» из правила [ЧАСЫ] в разделе КОНЦОВКА."
    )


class TestPromptRules:
    """Правила, которые уже ломались в проде — держим тестами."""

    def _system(self, tours_text: str = "") -> str:
        from src.ai.prompts import _build_system

        return _build_system(tours_text, "", current_time="10:15")

    def test_russian_only(self):
        """Разрешение английского было временным, на Meta App Review."""
        prompt = self._system()
        assert "Отвечай только по-русски" in prompt
        assert "английском" not in prompt

    def test_visa_support_never_called_visa_free(self):
        """Клиенты читали «не обязательно» как «поездка без визы»."""
        prompt = self._system()
        assert "визовую поддержку" in prompt
        assert "«виза не нужна», «без визы», «виза не требуется» для таких туров ЗАПРЕЩЕНЫ" in prompt

    @pytest.mark.parametrize('use_tools', [False, True])
    @pytest.mark.parametrize('escalation_count', [0, 3])
    def test_visa_conditions_follow_program_marker(self, use_tools, escalation_count):
        from src.ai.prompts import build_full_prompt

        catalog = ('=== ТУР: Тур с готовой визой ===\nДля туристов с визами\n'
                   '=== ТУР: Тур с оформлением ===\nПрограмма поездки.\n')
        prompt = build_full_prompt(catalog, '', [], 'У меня нет визы.',
                                   escalation_count=escalation_count, use_tools=use_tools)[0].content
        assert 'Есть пометка «для туристов с визами»' in prompt
        assert 'визовую поддержку по этому туру не оказываем' in prompt
        assert 'Нет этой пометки — оказываем визовую поддержку' in prompt
        assert 'если для поездки требуется виза' in prompt
        assert 'Не переноси пометку на другие туры' in prompt
        assert 'отсутствие пометки не означает безвизовую поездку' in prompt
        assert 'У каждого тура есть поле «Виза:»' not in prompt
        assert 'Виза: НУЖНА' not in prompt
        assert catalog in prompt

    def test_dates_hidden_by_default_shown_on_request(self):
        prompt = self._system()
        assert "ДАТЫ УЖЕ ОТФИЛЬТРОВАНЫ" in prompt
        assert "Свободных дат нет" in prompt
        # Даты не называем по умолчанию, только по явной просьбе клиента.
        assert "по умолчанию НЕ называй" in prompt
        assert "актуальные даты смотрите по ссылке на тур" in prompt
        assert "Только если клиент явно попросил даты" in prompt
        # Старое правило требовало от модели самой сравнивать даты и
        # перечислять ВСЕ заезды — теперь это делает загрузчик.
        assert "ФИЛЬТР ДАТ" not in prompt
        assert "ВСЕ будущие даты" not in prompt
        # Старого поведения «даты всегда» быть не должно.
        assert "указывай даты из поля" not in prompt

    def test_male_gender_consistent(self):
        """«Пол — мужской» противоречил примеру «я передала… она свяжется»."""
        prompt = self._system()
        assert "Пол — мужской" in prompt
        assert "передала" not in prompt
        assert "она свяжется" not in prompt

    def test_no_stale_promos_in_prompt(self):
        """Протухшие акции не должны жить в промпте: дедлайн посольства
        02.10.2026 прошёл, повышение цен с 01.10 — тоже, актуальные данные
        только в турах по ссылкам."""
        prompt = self._system()
        assert "02.10.2026" not in prompt
        assert "посольство" not in prompt.lower()
        assert "на следующей неделе" not in prompt


def test_escalation_limit_block_does_not_shift_prefix():
    """Переключение лимита эскалаций не должно двигать базу туров."""
    from src.ai.prompts import _build_system

    tours = "=== ТУР: Турция ===\nПляж"
    under = _build_system(tours, "", escalation_count=0, current_time="10:15")
    over = _build_system(tours, "", escalation_count=3, current_time="10:15")

    assert "ЛИМИТ ИСЧЕРПАН" in over and "ЛИМИТ ИСЧЕРПАН" not in under
    shared = _common_prefix_len(under, over)
    assert shared > under.index("=== ТУР: Турция ===") + len(tours)


# --- Integration smoke test ---


@pytest.mark.asyncio
async def test_process_with_ai_smoke():
    """Проверяет, что process_with_ai не падает при вызове с замоканным LLM."""
    fake_response = tool_response(reply_json("Здравствуйте! Чем могу помочь?"))

    fake_llm = AsyncMock()
    fake_llm.ainvoke = AsyncMock(return_value=fake_response)

    patches = [
        patch("src.services.llm.get_llm", return_value=fake_llm),
        patch("src.services.tour_loader.get_tours_text", return_value=""),
        patch("src.db.faq_db.search_faq", return_value=[]),
        patch("src.main.save_session"),
        patch("src.main.instagram.send_message"),
        patch("src.main.instagram.get_username", return_value=None),
    ]
    for p in patches:
        p.start()

    try:
        await process_with("test_user", "Привет")
    except Exception as e:
        pytest.fail(f"process_with_ai raised: {e}")
    finally:
        for p in patches:
            p.stop()


async def process_with(sender_id: str, text: str) -> None:
    """Helper — вызывает process_with_ai."""
    from src.main import process_with_ai

    await process_with_ai(sender_id, text)
