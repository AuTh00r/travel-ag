"""Replay the observed provider EOF through the actual SDK and handler."""
from copy import deepcopy

import pytest

from src.services import llm
from tests.test_model_tools import model as model, converted, wire
from tests.test_tool_handler import sdk
from tests.test_unified_model_response import unified as unified
from tests.model_responses import reply_json


BROKEN = '{"reply":"PRIVATE_UNDELIVERED_REPLY","manager": '


def test_long_integer_keeps_existing_validator_path_without_provider_exception(model):
    from src.main import _validate_response
    raw = '{"reply":'+('1'*5000)+',"manager":null}'
    response = converted(model, wire(raw))
    assert llm.response_arguments(response) == (raw, None)
    assert _validate_response(raw)[1] == 'duplicate_fields'


@pytest.mark.parametrize("raw", [BROKEN, '{"reply":', '{"reply":"a","manager":null'])
def test_eof_arguments_are_distinguished_without_repair_or_sdk_loss(model, raw):
    body = wire(raw)
    body['usage']['completion_tokens'] = 231
    before = deepcopy(body)
    response = converted(model, body)
    assert llm.response_arguments(response) == (None, 'incomplete_tool_arguments')
    assert llm.response_log_content(response) == raw
    assert body == before and response.response_metadata['finish_reason'] == 'tool_calls'


async def test_observed_eof_regenerates_with_specific_trusted_instruction(unified, monkeypatch):
    async with sdk(monkeypatch, [wire(BROKEN), wire(reply_json('Новый полный ответ.'))]) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус')
    assert len(requests) == 2
    assert [c.kwargs['validation_reason'] for c in unified.journal.call_args_list] == ['incomplete_tool_arguments', 'valid']
    assert unified.journal.call_args_list[0].args[0] == BROKEN
    reminder = requests[1]['messages'][0]['content']
    assert 'Не продолжай частичный ответ' in reminder and 'закрой' in reminder
    assert requests[0]['messages'][1:] == requests[1]['messages'][1:]
    assert 'PRIVATE_UNDELIVERED_REPLY' not in str(requests)
    assert 'PRIVATE_UNDELIVERED_REPLY' not in str(unified.send.call_args_list)
    assert unified.send.await_count == 1
    unified.notify.assert_not_awaited()


@pytest.mark.parametrize('ad', [False, True])
async def test_three_eof_responses_never_send_partial_reply_or_add_fourth_call(unified, monkeypatch, ad):
    async with sdk(monkeypatch, [wire(BROKEN), wire(BROKEN), wire(BROKEN)]) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус', referral={'source': 'ADS'} if ad else None)
    assert len(requests) == 3
    assert [c.kwargs['validation_reason'] for c in unified.journal.call_args_list] == ['incomplete_tool_arguments']*3
    assert 'PRIVATE_UNDELIVERED_REPLY' not in str(unified.send.call_args_list)
    assert 'PRIVATE_UNDELIVERED_REPLY' not in str(unified.state['history'])
    unified.send.assert_not_awaited()
    unified.notify.assert_awaited_once()
