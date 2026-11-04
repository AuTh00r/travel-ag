from tests.model_responses import tool_response
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tests.test_ad_model_decision import model as model, pipeline as pipeline, response
from tests.test_ad_response_contract import visual
from tests.model_responses import reply_json, manager_data


INVALID = [
    ('invalid_json', 'PRIVATE_BROKEN_RESPONSE'),
    ('duplicate_fields', '{"reply":"one","reply":"two","manager":null}'),
    ('invalid_fields', '{"reply":"PRIVATE_BROKEN_RESPONSE"}'),
    ('invalid_field_type', '{"reply":null,"manager":null}'),
    ('invalid_manager_type', reply_json('one', manager_data('help', 'unknown'))),
    ('context_too_long', reply_json('one', manager_data('x' * 451))),
    ('empty_reply', reply_json('')),
    ('empty_context', reply_json('one', manager_data(''))),
]


@pytest.mark.parametrize(('reason', 'content'), INVALID)
@pytest.mark.parametrize('count', [0, 10], ids=['text', 'video'])
async def test_malformed_response_is_regenerated_with_trusted_reminder(model, monkeypatch, reason, content, count):
    if count:
        visual(model, monkeypatch, count)
    journal = Mock()
    logger = Mock()
    monkeypatch.setattr(model.main, 'log_llm_response', journal)
    monkeypatch.setattr(model.main, 'logger', logger)
    model.invoke.side_effect = [tool_response(arguments=content), response()]

    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})

    assert model.invoke.await_count == 2
    first, second = [call.args[0] for call in model.invoke.await_args_list]
    assert first is not second and first[0] is not second[0]
    assert first[0].content in second[0].content
    assert 'ПОВТОР ПОСЛЕ ОШИБКИ ФОРМАТА' in second[0].content
    assert reason in second[0].content
    assert first[1:] == second[1:] and first[-1] is second[-1]
    assert 'PRIVATE_BROKEN_RESPONSE' not in str(second)
    assert all('ПОВТОР ПОСЛЕ ОШИБКИ ФОРМАТА' not in str(m.content) for m in first)
    assert journal.call_count == 2
    a, b = journal.call_args_list
    assert a.args[0] == content and a.kwargs['validation_reason'] == reason
    assert b.kwargs['validation_reason'] == 'valid'
    assert a.kwargs['request_id'] == b.kwargs['request_id']
    assert [a.kwargs['attempt'], b.kwargs['attempt']] == [1, 2]
    event = next(c for c in logger.warning.call_args_list if c.args[0] == 'llm.format_response_retry')
    assert event.kwargs['reason'] == reason and event.kwargs['attempt'] == 2
    assert 'PRIVATE_BROKEN_RESPONSE' not in str(logger.mock_calls)
    model.prepare.assert_not_awaited()
    model.send.assert_awaited_once()
    model.notify.assert_not_awaited()
    model.queue.assert_not_awaited()
    assert [m['role'] for m in model.state['history']] == ['user', 'assistant']


@pytest.mark.parametrize('first', ['', INVALID[2][1]])
@pytest.mark.parametrize('last', ['', INVALID[2][1]])
async def test_empty_and_schema_failures_share_a_three_call_budget(model, first, last):
    model.invoke.side_effect = [tool_response(arguments=first), tool_response(arguments=last), response()]
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 3
    model.notify.assert_not_awaited()
    model.send.assert_awaited_once()
    assert [m['role'] for m in model.state['history']] == ['user', 'assistant']


@pytest.mark.parametrize('moment', [1, 2])
@pytest.mark.parametrize('mode', ['pending', 'persisted', 'cancelled'])
async def test_format_recovery_preserves_takeover_and_cancellation(model, moment, mode):
    calls = 0

    async def invoke(_):
        nonlocal calls
        calls += 1
        if calls == moment:
            if mode == 'pending':
                model.main._manager_pending['context-client'] = True
            elif mode == 'persisted':
                model.state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
            else:
                raise asyncio.CancelledError()
        return tool_response(arguments=INVALID[2][1]) if calls == 1 else response()

    model.invoke.side_effect = invoke
    if mode == 'cancelled':
        with pytest.raises(asyncio.CancelledError):
            await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    else:
        await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == moment
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()
    model.queue.assert_not_awaited()
    assert not model.state['history']


async def test_format_recovery_also_applies_to_ordinary_traffic(model):
    model.invoke.return_value = tool_response(arguments=INVALID[2][1])
    await model.main.process_with_ai('context-client', 'Эльбрус')
    assert model.invoke.await_count == 3
    model.notify.assert_awaited_once()


async def test_schema_recovery_handoff_uses_current_phone(model):
    model.state['history'] = [{'role': 'user', 'content': 'Старый номер +375251111111'}]
    model.invoke.side_effect = [tool_response(arguments=INVALID[2][1]),
                               response('handoff', 'Спасибо, свяжемся с вами.', 'Клиент оставил контакт по туру Эльбрус.')]
    await model.main.process_with_ai('context-client', 'Эльбрус\n+375252222222',
                                    referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    model.notify.assert_awaited_once()
    assert model.notify.await_args.kwargs['client_phone'] == '+375252222222'
    assert '+375251111111' not in str(model.notify.mock_calls)


async def test_schema_then_provider_failure_clears_metadata_and_stays_bounded(model, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(model.main, 'logger', logger)
    model.invoke.side_effect = [tool_response(arguments=INVALID[2][1]), RuntimeError('PRIVATE_PROVIDER_FAILURE')]
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert model.invoke.await_count == 2
    final = next(c.kwargs for c in logger.warning.call_args_list
                 if c.args[0] == 'llm.invalid_model_response')
    assert final['reason'] == 'provider_error' and final['response_chars'] is None
    assert 'PRIVATE_PROVIDER_FAILURE' not in str(logger.mock_calls) + str(model.notify.mock_calls)
    model.notify.assert_awaited_once()
    model.send.assert_not_awaited()
