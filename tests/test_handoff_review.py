import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage
import pytest

from src.config import settings
from src.main import _validate_response
from src.services import llm
from src.services.handoff_review import REVIEW_FUNCTION, review_manager_candidate, review_tool
from src.services.llm_response_log import catalog_metadata
from tests.model_responses import tool_response


CATALOG = '=== ТУР: Белосток ===\nКогда (ближайшие свободные даты): 08.12.2026 - 10.12.2026\n'
CANDIDATE = {'reply': 'Передал вопрос менеджеру.', 'manager': {
    'context': 'Уточнить посадку в Бобруйске.', 'type': 'консультация', 'name': ''}}
TASK = {'id': 'a' * 32, 'revision': 2, 'summary': 'Уточнить посадку в Бобруйске.'}


def review_response(value):
    response = tool_response(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)
    response.additional_kwargs['raw_tool_message']['tool_calls'][0]['function']['name'] = REVIEW_FUNCTION
    return response


async def run(monkeypatch, response, *, candidate=None, tasks=None, model=None, allow_silent=False):
    monkeypatch.setattr(settings, 'manager_review_enabled', True)
    model = model or AsyncMock()
    if isinstance(response, Exception):
        model.ainvoke.side_effect = response
    else:
        model.ainvoke.return_value = response
    monkeypatch.setattr(llm, 'get_handoff_review_llm', lambda **kwargs: model)
    result = await review_manager_candidate([HumanMessage(content='15 января')],
        deepcopy(CANDIDATE if candidate is None else candidate), tours_text=CATALOG, faq_context='',
        open_tasks=tasks or [], sender_id='test', request_id='1' * 32,
        catalog=catalog_metadata(CATALOG), validate=_validate_response,
        metadata=lambda r: {'finish_reason': r.response_metadata.get('finish_reason', 'tool_calls')},
        allow_silent=allow_silent)
    return result, model


async def test_cancel_fully_answered_candidate(monkeypatch):
    value = {'reply': 'Вот программа Белостока.', 'manager': None, 'action': 'cancel', 'task_id': ''}
    result, model = await run(monkeypatch, review_response(value))
    assert result.reviewed and result.action == 'cancel'
    assert result.response == {'reply': value['reply'], 'manager': None}
    model.ainvoke.assert_awaited_once()
    sent = model.ainvoke.call_args.args[0]
    assert CATALOG in sent[0].content
    assert '15 января' in sent[1].content


async def test_existing_question_update_has_trusted_revision(monkeypatch):
    value = {**CANDIDATE, 'action': 'update', 'task_id': TASK['id']}
    result, _ = await run(monkeypatch, review_response(value), tasks=[TASK])
    assert result.action == 'update' and result.task_id == TASK['id']
    assert result.task_revision == 2


async def test_independent_question_is_new_even_when_task_open(monkeypatch):
    value = {**CANDIDATE, 'action': 'new', 'task_id': ''}
    result, _ = await run(monkeypatch, review_response(value), tasks=[TASK])
    assert result.action == 'new' and result.task_id is None and result.reviewed


@pytest.mark.parametrize('value', [
    {**CANDIDATE, 'action': 'update', 'task_id': 'another-client-task'},
    {**CANDIDATE, 'action': 'cancel', 'task_id': ''},
    {'reply': '', 'manager': None, 'action': 'cancel', 'task_id': ''},
    {**CANDIDATE, 'action': 'new', 'task_id': TASK['id']},
    {**CANDIDATE, 'action': 'unknown', 'task_id': ''},
    {**CANDIDATE, 'action': 'new', 'task_id': '', 'extra': True},
    {**CANDIDATE, 'action': 'new', 'task_id': None},
    '{"reply":"ok","manager":null,"action":"cancel","task_id":"","action":"new"}',
    '{"reply":"incomplete',
])
async def test_bad_review_preserves_original_candidate(monkeypatch, value):
    result, model = await run(monkeypatch, review_response(value), tasks=[TASK])
    assert result.response == CANDIDATE and not result.reviewed
    model.ainvoke.assert_awaited_once()


async def test_provider_failure_is_not_a_failed_client_request(monkeypatch):
    result, model = await run(monkeypatch, RuntimeError('private diagnostic must not escape'))
    assert result.response == CANDIDATE and not result.reviewed
    model.ainvoke.assert_awaited_once()


async def test_timeout_preserves_original_candidate(monkeypatch):
    monkeypatch.setattr(settings, 'manager_review_timeout_seconds', 0.01)
    model = AsyncMock()

    async def delayed(*args):
        await asyncio.sleep(10)

    model.ainvoke.side_effect = delayed
    result, _ = await run(monkeypatch, None, model=model)
    assert result.response == CANDIDATE and not result.reviewed


async def test_cancelled_request_is_not_revived(monkeypatch):
    model = AsyncMock()
    model.ainvoke.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await run(monkeypatch, None, model=model)


@pytest.mark.parametrize('manager', [None, {**CANDIDATE['manager'], 'type': 'контакт'},
                                    {**CANDIDATE['manager'], 'type': 'отзыв'}])
async def test_non_consultation_never_calls_reviewer(monkeypatch, manager):
    candidate = {**CANDIDATE, 'manager': manager}
    result, model = await run(monkeypatch, None, candidate=candidate)
    assert result.response == candidate
    model.ainvoke.assert_not_awaited()


def test_primary_schema_does_not_change():
    tool = review_tool()
    assert set(tool['function']['parameters']['properties']) == {'reply', 'manager', 'action', 'task_id'}
    assert set(llm.response_tool()['function']['parameters']['properties']) == {'reply', 'manager'}


def test_catalog_diagnostics_come_from_actual_supplied_text():
    meta = catalog_metadata(CATALOG + 'Client secret in program body must not be logged\n')
    assert meta['chars'] > len(CATALOG)
    assert meta['tours'] == [{'name': 'Белосток', 'available': True,
                              'dates': ['08.12.2026', '10.12.2026']}]
    assert 'secret' not in json.dumps(meta)


async def test_incomplete_source_constraint_is_visible_to_reviewer(monkeypatch):
    result, model = await run(monkeypatch, review_response({**CANDIDATE, 'reply': '',
                              'action': 'new', 'task_id': ''}), allow_silent=True)
    assert result.reviewed and result.response['reply'] == ''
    rules = model.ainvoke.await_args.args[0][0].content
    assert 'Источник текущего запроса неполный' in rules and 'без выдуманной отметки о рекламе' in rules


async def test_length_finish_never_overrides_valid_primary(monkeypatch):
    response = review_response({'reply': 'Уточните тур.', 'manager': None, 'action': 'cancel', 'task_id': ''})
    response.response_metadata['finish_reason'] = 'length'
    result, model = await run(monkeypatch, response)
    assert not result.reviewed and result.response == CANDIDATE
    model.ainvoke.assert_awaited_once()


@pytest.mark.parametrize('vision', [False, True])
def test_actual_sdk_review_payload_has_one_forced_tool_and_no_retries(monkeypatch, vision):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'not-a-real-key')
    model = llm.get_handoff_review_llm(vision=vision)
    payload = model._get_request_payload([HumanMessage(content='Проверить задачу')])
    assert payload['tools'] == [review_tool()]
    assert payload['tool_choice'] == {'type': 'function', 'function': {'name': REVIEW_FUNCTION}}
    assert payload['extra_body']['thinking'] == {'type': 'disabled'}
    assert model.root_async_client.max_retries == 0
    assert model.request_timeout == settings.manager_review_timeout_seconds


async def test_review_inherits_shared_business_rules_without_primary_transport(monkeypatch):
    from datetime import datetime
    from src.ai.prompts import _BASE_RULES, _SECURITY_RULES, _ACTION_INSTRUCTIONS, _CLOSING_RULES
    from src.config import MINSK_TZ

    _, model = await run(monkeypatch, review_response({**CANDIDATE, 'action': 'new', 'task_id': ''}))
    system = model.ainvoke.await_args.args[0][0].content
    assert _BASE_RULES.format(today=datetime.now(MINSK_TZ).strftime('%d.%m.%Y')) in system
    assert all(block in system for block in (_SECURITY_RULES, _ACTION_INSTRUCTIONS, _CLOSING_RULES))
    assert 'Есть пометка «для туристов с визами»' in system
    assert 'Нет этой пометки — оказываем визовую поддержку' in system
    assert 'отсутствие пометки не означает безвизовую поездку' in system
    assert 'У каждого тура есть поле «Виза:»' not in system
    assert 'ЕДИНЫЙ ФОРМАТ ОТВЕТА — PREPARE_RESPONSE' not in system
    assert 'ЕДИНЫЙ ФОРМАТ ОТВЕТА — JSON' not in system
    assert 'Уже указанный клиентом период — обязательное условие' in system
    assert 'Не выбирай\nза него первый заезд каталога' in system


async def test_review_preserves_complete_candidate_and_task_conditions(monkeypatch):
    from src.ai.prompts import _CLOSING_RULES

    footer = next(line.strip('«»') for line in _CLOSING_RULES.splitlines()
                  if line.startswith('«Наши менеджеры '))
    complete = {'reply': 'Здравствуйте! Программа: https://example.com/program\n\n' + footer,
                'manager': {'context': 'Уточнить срок брони Эльбруса 15 января.',
                            'type': 'консультация', 'name': ''}}
    decision, model = await run(monkeypatch, review_response({**complete, 'action': 'new', 'task_id': ''}),
                                candidate=complete)
    assert decision.reviewed and decision.response == complete
    received = model.ainvoke.await_args.args[0][-1].content
    assert json.dumps(complete, ensure_ascii=False) in received
    assert decision.response['reply'].count(footer) == 1
