from tests.model_responses import tool_response
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tests.test_ad_model_decision import model as model, pipeline as pipeline, response
from tests.test_ad_response_contract import visual


def blank(content=' ' * 242, finish='tool_calls'):
    return tool_response(arguments=content, response_metadata={'finish_reason': finish},
                           usage_metadata={'input_tokens': 18417, 'output_tokens': 538})


@pytest.mark.parametrize('count', [0, 1, 10], ids=['text', 'image', 'video'])
@pytest.mark.parametrize('content', ['', ' ' * 242], ids=['empty', 'whitespace'])
async def test_empty_then_answer_reuses_request_and_delivers_once(model, monkeypatch, count, content):
    factory = visual(model, monkeypatch, count) if count else None
    model.invoke.side_effect = [blank(content), response()]
    await model.main.process_with_ai('context-client', 'Виза есть! Пришлите программу тура ВДП',
                                    referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    assert model.invoke.await_args_list[0].args[0] is model.invoke.await_args_list[1].args[0]
    model.prepare.assert_not_awaited()
    if factory:
        factory.assert_not_called()
        parts = model.invoke.await_args.args[0][-1].content
        assert isinstance(parts, str)
    model.send.assert_awaited_once_with('context-client', 'Программа тура доступна по ссылке.')
    model.notify.assert_not_awaited()
    model.queue.assert_not_awaited()
    assert [entry['role'] for entry in model.state['history']] == ['user', 'assistant']
    assert all(entry['content'].strip() for entry in model.state['history'])
    assert model.state['escalation_count'] == 0


@pytest.mark.parametrize('count', [0, 10], ids=['text', 'video'])
@pytest.mark.parametrize(('final', 'reason'), [
    ('empty', 'empty_response'), ('invalid', 'invalid_json'),
    ('truncated', 'response_truncated'), ('provider', 'provider_error'),
])
async def test_failure_series_silently_escalates_once_with_final_reason(model, monkeypatch, count, final, reason):
    if count:
        visual(model, monkeypatch, count)
    logger = Mock()
    monkeypatch.setattr(model.main, 'logger', logger)
    last = {'empty': blank(), 'invalid': tool_response(arguments='invalid JSON'),
            'truncated': response(), 'provider': RuntimeError('PRIVATE_PROVIDER_ERROR')}[final]
    if final == 'truncated':
        last.response_metadata = {'finish_reason': 'length'}
    model.invoke.side_effect = [blank(), last, last]
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == (2 if final == 'provider' else 3)
    model.notify.assert_awaited_once()
    model.send.assert_not_awaited()
    model.queue.assert_not_awaited()
    assert [entry['role'] for entry in model.state['history']] == ['user']
    assert model.state['escalation_count'] == 0
    fields = next(call.kwargs for call in logger.warning.call_args_list
                  if call.args[0] == 'llm.invalid_model_response')
    assert fields['reason'] == reason
    assert 'Эльбрус' in model.notify.await_args.kwargs['context']
    if final == 'provider':
        assert fields['response_chars'] is None and fields['input_tokens'] is None
    assert 'PRIVATE_PROVIDER_ERROR' not in str(logger.mock_calls) + str(model.notify.mock_calls)


@pytest.mark.parametrize('limited', [False, True])
async def test_empty_then_semantic_handoff_keeps_reply_and_limit(model, limited):
    model.state['escalation_count'] = 3 if limited else 0
    model.invoke.side_effect = [blank(), response('handoff', 'Для уточнения нужна помощь менеджера.', 'Клиенту нужна консультация по визе.')]
    await model.main.process_with_ai('context-client', 'Вопрос про визу', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    assert model.notify.await_count == int(not limited)
    if not limited:
        assert model.notify.await_args.kwargs['context'] == 'Клиенту нужна консультация по визе.'
    assert model.state['escalation_count'] == (3 if limited else 1)
    model.send.assert_awaited_once()
    model.queue.assert_not_awaited()


@pytest.mark.parametrize('moment', [1, 2], ids=['before-retry', 'during-retry'])
@pytest.mark.parametrize('mode', ['pending', 'persisted'])
async def test_manager_takeover_aborts_retry_and_delivery(model, moment, mode):
    calls = 0

    async def invoke(_):
        nonlocal calls
        calls += 1
        if calls == moment:
            if mode == 'pending':
                model.main._manager_pending['context-client'] = True
            else:
                model.state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
        return blank() if calls == 1 else response()

    model.invoke.side_effect = invoke
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == moment
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()
    model.queue.assert_not_awaited()
    assert not model.state['history']


async def test_cancellation_during_retry_propagates_without_handoff(model):
    model.invoke.side_effect = [blank(), asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError):
        await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()
    model.queue.assert_not_awaited()
    assert not model.state['history']


@pytest.mark.parametrize('count', [0, 3], ids=['notify-available', 'notify-limited'])
async def test_provider_failure_during_takeover_preserves_persisted_pause(model, count):
    model.state['escalation_count'] = count
    paused_at = datetime.now(timezone.utc).isoformat()
    calls = 0

    async def invoke(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return blank()
        model.state['manager_last_at'] = paused_at
        raise RuntimeError('provider failed after manager takeover')

    model.invoke.side_effect = invoke
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    assert model.state.get('manager_last_at') == paused_at
    assert not model.state['history']
    assert model.state['escalation_count'] == count
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()
    model.queue.assert_not_awaited()


@pytest.mark.parametrize('finish', ['length', 'stop'])
async def test_empty_and_truncated_responses_share_three_call_budget(model, finish):
    model.invoke.return_value = blank(finish=finish)
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 3
    model.notify.assert_awaited_once()


async def test_non_ad_empty_response_uses_three_call_budget(model):
    model.invoke.return_value = blank()
    await model.main.process_with_ai('context-client', 'Эльбрус')
    assert model.invoke.await_count == 3


@pytest.mark.parametrize('content', [None, ' ' * 16001], ids=['invalid-type', 'oversize-whitespace'])
async def test_malformed_argument_types_get_three_attempts(model, content):
    model.invoke.return_value = blank(content)
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 3
    model.notify.assert_awaited_once()
    model.send.assert_not_awaited()


async def test_retry_handoff_keeps_current_phone_authoritative(model):
    model.state['history'] = [{'role': 'user', 'content': 'Старый номер +375251111111'}]
    model.invoke.side_effect = [blank(), response('handoff', 'Для уточнения нужна помощь менеджера.', 'Клиент оставил контакт по туру Эльбрус.')]
    await model.main.process_with_ai('context-client', 'Эльбрус\n+375252222222',
                                    referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    model.notify.assert_awaited_once()
    assert model.notify.await_args.kwargs['client_phone'] == '+375252222222'
    assert model.notify.await_args.kwargs['tag'] == 'контакт'
    assert '375251111111' not in str(model.notify.await_args.kwargs)
    model.send.assert_awaited_once()
    model.queue.assert_not_awaited()


async def test_notification_failure_after_retry_is_not_counted_as_delivered(model):
    model.invoke.side_effect = [blank(), blank(), blank()]
    model.notify.side_effect = RuntimeError('notification unavailable')
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 3
    model.notify.assert_awaited_once()
    assert model.state['escalation_count'] == 0
    model.send.assert_not_awaited()
    model.queue.assert_not_awaited()


async def test_retry_log_uses_only_safe_metadata(model, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(model.main, 'logger', logger)
    first = blank('\n\t' * 121)
    first.response_metadata['private'] = 'PRIVATE_METADATA'
    first.usage_metadata['input_tokens'] = 'PRIVATE_USAGE'
    model.invoke.side_effect = [first, response()]
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    fields = next(call.kwargs for call in logger.warning.call_args_list
                  if call.args[0] == 'llm.empty_response_retry')
    assert fields['reason'] == 'empty_response' and fields['attempt'] == 2
    assert fields['response_chars'] == 242 and fields['input_tokens'] is None
    assert 'PRIVATE_' not in str(logger.mock_calls)
    assert not any(call.args[0] == 'llm.invalid_model_response' for call in logger.warning.call_args_list)
