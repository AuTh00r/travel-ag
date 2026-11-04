from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from tests.model_responses import manager_data, model_response

from src.exceptions import TelegramError

CONTENT = 'Тур в Прагу есть. Подробнее: https://sundita.by/tour/prague\n\n'
CONTACTS = 'Наши менеджеры Наталья и Татьяна ответят вам на все ваши вопросы: А1 +375 29 356 83 24 / +375 29 152 37 28'
CLAIM = 'Я передал ваш контакт менеджерам Наталье и Татьяне. Они свяжутся с вами в рабочее время.\n\n'


@pytest.fixture
def ai(monkeypatch):
    import src.main as main
    from src.services import guard
    guard._user_timestamps.clear()
    monkeypatch.setattr(main, '_locks', {})
    monkeypatch.setattr(main, '_processing_locks', {})
    monkeypatch.setattr(main, '_manager_pending', {})
    state = {'history': [], 'escalation_count': 0}
    async def get(*_):
        return deepcopy(state)
    async def save(_sender, value):
        state.clear()
        state.update(deepcopy(value))
    monkeypatch.setattr(main, 'get_session', get)
    monkeypatch.setattr(main, 'save_session', save)
    invoke, notify, send = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr('src.services.llm.get_llm', lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr('src.services.tour_loader.get_tours_text', lambda: 'Каталог')
    monkeypatch.setattr('src.db.faq_db.search_faq', AsyncMock(return_value=[]))
    monkeypatch.setattr(type(main.instagram), 'get_username', AsyncMock(return_value=None))
    monkeypatch.setattr(type(main.instagram), 'send_message', send)
    monkeypatch.setattr('src.services.telegram_notify.TelegramNotifier.notify_manager', notify)
    return SimpleNamespace(main=main, state=state, invoke=invoke, notify=notify, send=send)


@pytest.mark.parametrize('outcome', ['success', 'failure', 'limit', 'no_manager'])
@pytest.mark.parametrize('phone', [False, True])
async def test_handoff_reply_matches_real_delivery(ai, outcome, phone):
    if outcome == 'limit':
        ai.state['escalation_count'] = 3
    if outcome == 'failure':
        ai.notify.side_effect = RuntimeError('test failure')
    ai.invoke.return_value = model_response(CONTENT + CLAIM + CONTACTS,
        None if outcome == 'no_manager' else manager_data('Клиент интересуется туром в Прагу.'))
    await ai.main.process_with_ai('receipt-test', 'Про тур в Прагу' + ('\n+375290000000' if phone else ''))
    reply = ''.join(call.args[1] for call in ai.send.await_args_list)
    attempted = outcome not in {'limit', 'no_manager'} or (phone and outcome != 'limit')
    success = attempted and outcome != 'failure'
    assert ai.notify.await_count == int(attempted)
    assert 'Тур в Прагу есть.' in reply and 'https://sundita.by/tour/prague' in reply
    assert reply.count(CONTACTS) == 1
    assert 'Я передал ваш контакт' not in reply
    assert 'Они свяжутся' not in reply
    assert '===МЕНЕДЖЕР' not in reply
    if success:
        assert 'Ваш запрос передан менеджеру.' in reply
    elif outcome == 'failure':
        assert 'Не удалось подтвердить передачу нового обращения' in reply
    else:
        assert 'Новое уведомление менеджеру не отправлено' in reply
        if outcome == 'limit':
            assert 'лимит' in reply
    assert ai.state['escalation_count'] == (3 if outcome == 'limit' else int(success))
    assert ai.state['history'][-1]['content'] == reply


@pytest.mark.parametrize('claim', ['Ваш запрос уже передан.', 'Я отправил ваше обращение специалисту.',
                                  'Менеджер получил ваш номер.', 'Уведомил менеджеров о вашем вопросе.'])
async def test_claim_without_marker_never_confirms_delivery(ai, claim):
    ai.invoke.return_value = model_response(CONTENT + claim + '\n\n' + CONTACTS)
    await ai.main.process_with_ai('receipt-test', 'Про тур')
    reply = ai.send.await_args.args[1]
    ai.notify.assert_not_awaited()
    assert claim not in reply
    assert 'Тур в Прагу есть.' in reply
    assert 'Новое уведомление менеджеру не отправлено' in reply


async def test_ordinary_advice_keeps_text_and_does_not_add_receipt(ai):
    raw = CONTENT + 'Чтобы уточнить детали, обратитесь к менеджеру.\n\n' + CONTACTS
    ai.invoke.return_value = model_response(raw)
    await ai.main.process_with_ai('receipt-test', 'Про тур')
    ai.notify.assert_not_awaited()
    ai.send.assert_awaited_once_with('receipt-test', raw)


@pytest.mark.parametrize('body', [{'ok': False}, {'ok': 'true'}, {}, [], None])
async def test_telegram_http200_without_ack_is_failure(body):
    from src.services.telegram_notify import TelegramNotifier
    response = httpx.Response(200, json=body, request=httpx.Request('POST', 'https://api.telegram.org/mock'))
    fake = AsyncMock()
    fake.__aenter__.return_value = fake
    fake.post.return_value = response
    with patch('src.services.telegram_notify.AsyncClient', return_value=fake), pytest.raises(TelegramError):
        await TelegramNotifier()._send('proof', 'mock-chat')


@pytest.mark.parametrize('fail_first', [False, True])
async def test_partial_confirmed_telegram_delivery_is_success(fail_first):
    from src.services.telegram_notify import TelegramNotifier
    notifier = TelegramNotifier()
    notifier._token = 'TEST'
    notifier._chat_ids = ['mock-1', 'mock-2']
    notifier._send = AsyncMock(side_effect=([TelegramError('test failure'), None] if fail_first
                                          else [None, TelegramError('test failure')]))
    await notifier.notify_manager('mock-client', context='proof')
    assert notifier._send.await_count == 2


async def test_telegram_bad_json_is_failure():
    from src.services.telegram_notify import TelegramNotifier
    response = Mock(status_code=200)
    response.json.side_effect = ValueError('invalid')
    fake = AsyncMock()
    fake.__aenter__.return_value = fake
    fake.post.return_value = response
    with patch('src.services.telegram_notify.AsyncClient', return_value=fake), pytest.raises(TelegramError):
        await TelegramNotifier()._send('proof', 'mock-chat')


@pytest.mark.parametrize('claim', ['Передам ваш контакт менеджеру.', 'С вами свяжется менеджер.',
                                  'С вами свяжутся в рабочее время.'])
def test_future_transfer_and_callback_are_not_unverified_receipts(claim):
    from src.main import _finalize_handoff_reply
    reply = _finalize_handoff_reply(CONTENT + claim + '\n\n' + CONTACTS, 'none', limited=True)
    assert claim not in reply
    assert 'Новое уведомление менеджеру не отправлено' in reply
    assert CONTENT.strip() in reply and reply.endswith(CONTACTS)


@pytest.mark.parametrize('text', ['Менеджер получил ваш вопрос?', 'Ваш запрос не передан менеджеру.',
                                 'По вашему вопросу: виза уже получена.'])
def test_question_negative_and_unrelated_receipt_are_preserved(text):
    from src.main import _finalize_handoff_reply
    assert _finalize_handoff_reply(text, 'none') == text


@pytest.mark.parametrize('content', ['Подробнее: https://sundita.by/tour/prague, ваш контакт уже передан менеджеру.',
                                    'В тур включён завтрак; я передал ваш запрос менеджеру.'])
def test_useful_clause_and_url_survive_in_same_sentence(content):
    from src.main import _finalize_handoff_reply
    reply = _finalize_handoff_reply(content, 'none', limited=True)
    assert ('https://sundita.by/tour/prague' in reply if 'https' in content else 'В тур включён завтрак' in reply)
    assert 'уже передан' not in reply and 'я передал' not in reply
    assert 'Новое уведомление менеджеру не отправлено' in reply


@pytest.mark.parametrize('text,question', [
    ('Я передал ваш контакт менеджеру, когда вам удобно получить звонок?', 'когда вам удобно получить звонок?'),
    ('Ваш запрос передан менеджеру — расскажите, есть ли у вас виза?', 'есть ли у вас виза?'),
])
def test_transfer_followed_by_question_does_not_hide_false_receipt(text, question):
    from src.main import _finalize_handoff_reply
    reply = _finalize_handoff_reply(text, 'none', limited=True)
    assert 'Я передал' not in reply and 'запрос передан' not in reply
    assert question in reply and 'Новое уведомление менеджеру не отправлено' in reply


async def test_all_telegram_recipients_fail_without_receipt():
    from src.services.telegram_notify import TelegramNotifier
    notifier = TelegramNotifier()
    notifier._token = 'TEST'
    notifier._chat_ids = ['mock-1', 'mock-2']
    notifier._send = AsyncMock(side_effect=TelegramError('test failure'))
    with pytest.raises(TelegramError):
        await notifier.notify_manager('mock-client', context='proof')
    assert notifier._send.await_count == 2


async def test_telegram_transport_error_does_not_expose_token():
    from src.services.telegram_notify import TelegramNotifier
    fake = AsyncMock()
    fake.__aenter__.return_value = fake
    fake.post.side_effect = httpx.ConnectError('SECRET_TOKEN', request=httpx.Request('POST', 'https://api.telegram.org/SECRET_TOKEN'))
    with patch('src.services.telegram_notify.AsyncClient', return_value=fake), pytest.raises(TelegramError) as caught:
        await TelegramNotifier()._send('proof', 'mock-chat')
    assert 'SECRET_TOKEN' not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize('count', [0, 3])
def test_prompt_has_no_preliminary_transfer_instruction(count):
    from src.ai.prompts import _build_system
    prompt = _build_system('Каталог', '', escalation_count=count)
    assert 'Никогда не подтверждай передачу запроса' in prompt
    assert 'после проверки доставки' in prompt
    assert 'Напиши клиенту, что передал вопрос' not in prompt
    assert 'Я передаю ваш запрос нашим менеджерам' not in prompt
    assert 'Я передал ваш контакт менеджерам Наталье и Татьяне.' not in prompt
    if count == 3:
        assert 'Новое уведомление менеджеру не отправлено' in prompt
        assert 'Программа применит лимит' in prompt


def test_verified_success_replaces_wrong_model_failure_once_before_contacts():
    from src.main import _finalize_handoff_reply
    reply = _finalize_handoff_reply(CONTENT + 'Ваш запрос не передан менеджеру.\n\n' + CONTACTS,
                                    'sent', outside_hours=True)
    assert 'не передан' not in reply
    assert reply.count('Ваш запрос передан менеджеру.') == 1
    assert '10:00 до 18:00' in reply and reply.endswith(CONTACTS)
