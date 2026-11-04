from tests.model_responses import tool_response
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from tests.model_responses import manager_data, model_response, reply_json


@pytest.fixture
def unified(monkeypatch):
    import src.main as main
    from src.services import guard
    guard._user_timestamps.clear()
    state = {'history': [], 'escalation_count': 0}

    async def get(*_):
        return deepcopy(state)

    async def save(_, value):
        state.clear()
        state.update(deepcopy(value))

    for name in ['_locks', '_processing_locks', '_manager_pending']:
        monkeypatch.setattr(main, name, {})
    invoke = AsyncMock(return_value=model_response())
    send, notify, queue = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(main, 'get_session', get)
    monkeypatch.setattr(main, 'save_session', save)
    monkeypatch.setattr('src.services.llm.get_llm', lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr('src.services.llm.get_vision_llm', lambda **_: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr('src.services.tour_loader.get_tours_text', lambda: 'Каталог: Эльбрус')
    monkeypatch.setattr('src.db.faq_db.search_faq', AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), 'get_username', AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), 'send_message', send)
    monkeypatch.setattr(main, 'enqueue_pending', queue)
    monkeypatch.setattr('src.services.telegram_notify.TelegramNotifier.notify_manager', notify)
    journal = Mock()
    monkeypatch.setattr(main, 'log_llm_response', journal)
    return SimpleNamespace(main=main, state=state, invoke=invoke, send=send,
                           notify=notify, queue=queue, journal=journal)


@pytest.mark.parametrize('raw,reason', [
    ('plain answer', 'invalid_json'),
    ('{"reply":"one","reply":"two","manager":null}', 'duplicate_fields'),
    ('{"reply":"one"}', 'invalid_fields'),
    ('{"reply":"one","manager":null,"decision":"answer"}', 'invalid_fields'),
    ('{"reply":null,"manager":null}', 'invalid_field_type'),
    (reply_json('', None), 'empty_reply'),
    (reply_json('one', {'context': 'help', 'type': 'контакт'}), 'invalid_fields'),
    (reply_json('one', {'context': 'help', 'type': 'контакт', 'name': '', 'phone': '+375290000001'}), 'invalid_fields'),
    (reply_json('one', manager_data('help', type='unknown')), 'invalid_manager_type'),
    (reply_json('one', manager_data('')), 'empty_context'),
    (reply_json('one', manager_data('x' * 451)), 'context_too_long'),
    (reply_json('one', manager_data('help', name='x' * 101)), 'name_too_long'),
    (reply_json('visible\n===МЕНЕДЖЕР===\nPRIVATE', None), 'service_marker'),
])
def test_unified_validation_rejects_wrong_envelopes(raw, reason):
    from src.main import _validate_response
    assert _validate_response(raw) == (None, reason)


@pytest.mark.parametrize('route', ['text', 'ad', 'image', 'voice', 'mixed'])
@pytest.mark.parametrize('notify', [False, True])
async def test_all_routes_apply_same_envelope(unified, monkeypatch, route, notify):
    from src.services.story_media import StoryMedia
    request = {}
    if route == 'ad':
        request['referral'] = {'source': 'ADS'}
    if route in {'image', 'mixed'}:
        monkeypatch.setattr('src.config.settings.image_media_enabled', True)
        monkeypatch.setattr('src.services.story_media.prepare_images', AsyncMock(return_value=
            StoryMedia(None, 'IMAGE', [{'label': 'Фото', 'url': 'data:image/jpeg;base64,/9j/AA=='}])))
        request['image_urls'] = ['https://scontent.cdninstagram.com/photo.jpg']
    if route in {'voice', 'mixed'}:
        monkeypatch.setattr('src.services.voice_media.transcribe_voice', AsyncMock(return_value=['Подробнее про Эльбрус']))
        request['voice_parts'] = [{'audio': {'url': 'https://scontent.cdninstagram.com/voice.mp4'}}]
        if route == 'mixed':
            request.pop('image_urls')
            request['visual_parts'] = [{'kind': 'images', 'urls': ['https://scontent.cdninstagram.com/photo.jpg']}]
            monkeypatch.setattr('src.services.story_media.prepare_visual_parts', AsyncMock(return_value=
                StoryMedia(None, 'IMAGE', [{'label': 'Фото', 'url': 'data:image/jpeg;base64,/9j/AA=='}])))
    unified.invoke.return_value = model_response('Ответ по Эльбрусу.', manager_data('Нужны свободные места на Эльбрус.') if notify else None)
    await unified.main.process_with_ai('unified-test', 'Эльбрус', **request)
    unified.invoke.assert_awaited_once()
    assert unified.notify.await_count == int(notify)
    visible = ''.join(call.args[1] for call in unified.send.await_args_list)
    assert 'Ответ по Эльбрусу.' in visible
    assert 'Нужны свободные места' not in visible and '"manager"' not in visible
    assert unified.state['history'][-1]['content'] == visible
    assert unified.journal.call_args.kwargs['validation_reason'] == 'valid'


@pytest.mark.parametrize('ad', [False, True])
async def test_invalid_fields_recovers_once_without_applying_first_response(unified, ad):
    unified.invoke.side_effect = [tool_response(arguments='{"reply":"PRIVATE"}'), model_response('Исправленный ответ.')]
    await unified.main.process_with_ai('unified-test', 'Эльбрус', referral={'source': 'ADS'} if ad else None)
    assert unified.invoke.await_count == 2
    first, second = [c.args[0] for c in unified.invoke.await_args_list]
    assert first[1:] == second[1:] and first[0] is not second[0]
    assert 'PRIVATE' not in str(second)
    assert 'ПОВТОР ПОСЛЕ ОШИБКИ ФОРМАТА' in second[0].content
    assert 'Исправленный ответ.' in str(unified.send.call_args_list)
    unified.notify.assert_not_awaited()
    calls = unified.journal.call_args_list
    assert [c.kwargs['validation_reason'] for c in calls] == ['invalid_fields', 'valid']
    assert calls[0].kwargs['request_id'] == calls[1].kwargs['request_id']


@pytest.mark.parametrize('ad', [False, True])
async def test_three_failures_notify_once_and_keep_all_routes_silent(unified, ad):
    unified.invoke.return_value = tool_response(arguments='{"reply":"PRIVATE"}')
    await unified.main.process_with_ai('unified-test', 'Эльбрус', referral={'source': 'ADS'} if ad else None)
    assert unified.invoke.await_count == 3
    unified.notify.assert_awaited_once()
    unified.send.assert_not_awaited()
    assert 'PRIVATE' not in str(unified.notify.call_args_list) + str(unified.send.call_args_list)


@pytest.mark.parametrize('ad', [False, True])
async def test_ads_no_longer_grants_silent_manager_permission(unified, ad):
    unified.invoke.return_value = model_response('', manager_data('Реклама недоступна, направление неизвестно.'))
    await unified.main.process_with_ai('unified-test', 'Можно подробнее?', referral={'source': 'ADS'} if ad else None)
    assert unified.invoke.await_count == 3
    unified.notify.assert_awaited_once()
    unified.send.assert_not_awaited()


@pytest.mark.parametrize('mode', ['pending', 'persisted', 'cancelled'])
async def test_takeover_or_cancel_between_attempts_stops_every_action(unified, mode):
    async def invoke(_):
        if mode == 'pending':
            unified.main._manager_pending['unified-test'] = True
        elif mode == 'persisted':
            unified.state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
        else:
            raise asyncio.CancelledError()
        return tool_response(arguments='{"reply":"PRIVATE"}')
    unified.invoke.side_effect = invoke
    if mode == 'cancelled':
        with pytest.raises(asyncio.CancelledError):
            await unified.main.process_with_ai('unified-test', 'Эльбрус')
    else:
        await unified.main.process_with_ai('unified-test', 'Эльбрус')
    unified.invoke.assert_awaited_once()
    unified.send.assert_not_awaited()
    unified.notify.assert_not_awaited()
    unified.queue.assert_not_awaited()


def test_one_prompt_contract_without_legacy_actions():
    from src.ai.prompts import build_full_prompt
    for ad in ['', '[Отклик на рекламу]']:
        for count in [0, 3]:
            prompt = build_full_prompt('Каталог', '', [], 'Эльбрус', count, ad_context=ad)[0].content
            assert '"reply"' in prompt and '"manager"' in prompt
            assert '===МЕНЕДЖЕР===' not in prompt and '===БРОНЬ===' not in prompt
            assert '"decision"' not in prompt


def test_all_factories_enable_same_tool_mode(monkeypatch):
    import src.services.llm as module
    monkeypatch.setattr(module.settings, 'deepseek_api_key', 'test')
    constructor = Mock()
    monkeypatch.setattr(module, '_ResponseModel', constructor)
    module.get_llm()
    module.get_vision_llm()
    assert constructor.call_count == 2
    for call in constructor.call_args_list:
        assert 'response_format' not in call.kwargs['model_kwargs']
        assert call.kwargs['model_kwargs']['tools'] == [module.response_tool()]
        assert call.kwargs['max_retries'] == 0


@pytest.mark.parametrize('ad', [False, True])
@pytest.mark.parametrize('failure', ['provider', 'type', 'length', 'oversize'])
async def test_retryable_and_terminal_failures_have_bounded_silent_handoff(unified, ad, failure):
    if failure == 'provider':
        unified.invoke.side_effect = RuntimeError('PRIVATE_PROVIDER_FAILURE')
    elif failure == 'length':
        unified.invoke.return_value = model_response()
        unified.invoke.return_value.response_metadata = {'finish_reason': 'length'}
    else:
        unified.invoke.return_value = tool_response(arguments=None if failure == 'type' else 'x' * 16001)
    await unified.main.process_with_ai('unified-test', 'Эльбрус', referral={'source': 'ADS'} if ad else None)
    assert unified.invoke.await_count == (1 if failure == 'provider' else 3)
    unified.notify.assert_awaited_once()
    unified.send.assert_not_awaited()
    assert 'PRIVATE_PROVIDER_FAILURE' not in str(unified.send.call_args_list) + str(unified.notify.call_args_list)


@pytest.mark.parametrize('question,expected', [
    ('Мой номер +375 29 123-45-67, перезвоните по Эльбрусу.', '+375291234567'),
    ('Меня зовут Иван, телефон +375291234567', '+375291234567'),
    ('Позвоните мне 8 (029) 123-45-67', '+375291234567'),
    ('Телефон 375291234567, хочу Эльбрус', '+375291234567'),
    ('Мой номер +375291234567 или +375257654321, пока не выбрал', None),
    ('На 2026-12-09 бюджет 12000', None),
])
async def test_current_inline_phone_is_extracted_without_model_phone(unified, question, expected):
    unified.invoke.return_value = model_response('Уточню детали.', manager_data('Клиент интересуется Эльбрусом.'))
    await unified.main.process_with_ai('unified-test', question)
    unified.notify.assert_awaited_once()
    assert unified.notify.await_args.kwargs['client_phone'] == expected
    assert unified.notify.await_args.kwargs['tag'] == ('контакт' if expected else 'консультация')


@pytest.mark.parametrize('with_manager', [False, True])
@pytest.mark.parametrize('phone', ['+375 29 123-45-67', '8 (029) 123-45-67'])
@pytest.mark.parametrize('start', ['Хочу', 'Я хочу', 'Я интересуюсь'])
async def test_inline_contact_preserves_current_tour_instead_of_old_history(unified, with_manager, phone, start):
    unified.state['history'] = [
        {'role': 'user', 'content': 'Раньше интересовала Прага'},
        {'role': 'assistant', 'content': 'Вот программа тура в Прагу.'},
    ]
    unified.invoke.return_value = model_response('Уточню детали.',
        manager_data('Клиент интересуется Эльбрусом.') if with_manager else None)
    await unified.main.process_with_ai('unified-test', f'{start} Эльбрус, телефон {phone}. На 2026-12-09, бюджет 12000.')
    data = unified.notify.await_args.kwargs
    assert data['client_phone'] == '+375291234567'
    assert 'Эльбрус' in data['context'] and 'Прага' not in data['context']
    assert '2026-12-09' in data['context'] and '12000' in data['context']
    assert phone not in data['context'] and '123-45-67' not in data['context']


@pytest.mark.parametrize('manager', [None, manager_data('Клиент интересуется Эльбрусом.')])
async def test_first_person_new_request_is_not_a_name_or_phone_label(unified, manager):
    unified.state['history'] = [{'role': 'user', 'content': 'Раньше интересовала Прага'}]
    unified.invoke.return_value = model_response('Уточню детали.', manager)
    await unified.main.process_with_ai('unified-test', 'Я хочу Эльбрус, телефон +375291234567')
    assert 'Эльбрус' in unified.notify.await_args.kwargs['context']
    assert 'Прага' not in unified.notify.await_args.kwargs['context']


@pytest.mark.parametrize('with_manager', [False, True])
@pytest.mark.parametrize('phrase', ['Мой номер +375291234567', 'Телефон +375291234567, перезвоните',
                                   'Меня зовут Иван, телефон +375291234567'])
async def test_contact_only_phrase_keeps_prior_tour_context(unified, with_manager, phrase):
    unified.state['history'] = [
        {'role': 'user', 'content': 'Хочу горнолыжный тур на Эльбрус'},
        {'role': 'assistant', 'content': 'Вот программа тура Эльбрус.'},
    ]
    unified.invoke.return_value = model_response('Уточню детали.',
        manager_data('Клиент интересуется туром Эльбрус и оставил контакт.') if with_manager else None)
    await unified.main.process_with_ai('unified-test', phrase)
    data = unified.notify.await_args.kwargs
    assert data['client_phone'] == '+375291234567'
    assert 'Эльбрус' in data['context'] and '+375291234567' not in data['context']
