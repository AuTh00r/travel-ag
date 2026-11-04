"""The diagnostic must preserve strict parsing and never confuse tools with sends."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from scripts.tool_call_probe import extract_tool_result, response_tool, tool_body
from scripts import tool_call_probe
from src.main import _validate_response


def response(arguments=None):
    return {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': None,
        'tool_calls': [{'id': 'call-test', 'type': 'function', 'function': {
            'name': 'prepare_response', 'arguments': arguments or '{"reply":"Ответ","manager":null}'}}]}}]}


def parse(data, silent=False):
    return extract_tool_result(data, _validate_response, allow_silent=silent)


@pytest.mark.parametrize('reply,manager,silent', [
    ('Ответ', None, False),
    ('Передача', {'context': 'Клиент уточняет места на Эльбрус.', 'type': 'консультация', 'name': ''}, False),
    ('', {'context': 'Нужен контекст недоступной рекламы.', 'type': 'консультация', 'name': ''}, True),
])
def test_three_canonical_outcomes(reply, manager, silent):
    expected = {'reply': reply, 'manager': manager}
    assert parse(response(json.dumps(expected)), silent) == (expected, None)


@pytest.mark.parametrize('mode', ['none', 'missing_choices', 'many_choices', 'length', 'content_filter',
    'stop', 'missing_message', 'content', 'nonstring_content', 'missing_tools', 'many_tools',
    'wrong_name', 'wrong_type', 'missing_id', 'nonstring_arguments'])
def test_malformed_transport_is_not_silent_success(mode):
    data = response()
    choice, message = data['choices'][0], data['choices'][0]['message']
    call = message['tool_calls'][0]
    if mode == 'none':
        data = None
    elif mode == 'missing_choices':
        data.pop('choices')
    elif mode == 'many_choices':
        data['choices'].append(deepcopy(choice))
    elif mode in ('length', 'content_filter', 'stop'):
        choice['finish_reason'] = mode
    elif mode == 'missing_message':
        choice.pop('message')
    elif mode == 'content':
        message['content'] = 'Этот посторонний текст нельзя отправлять клиенту.'
    elif mode == 'nonstring_content':
        message['content'] = []
    elif mode == 'missing_tools':
        message.pop('tool_calls')
    elif mode == 'many_tools':
        message['tool_calls'].append(deepcopy(call))
    elif mode == 'wrong_name':
        call['function']['name'] = 'send_to_manager'
    elif mode == 'wrong_type':
        call['type'] = 'custom'
    elif mode == 'missing_id':
        call.pop('id')
    elif mode == 'nonstring_arguments':
        call['function']['arguments'] = {'reply': 'Ответ', 'manager': None}
    result, error = parse(data, True)
    assert result is None and error


@pytest.mark.parametrize('raw,reason', [
    ('   ', 'empty_response'),
    ('{"reply":', 'invalid_json'),
    ('{"reply":"a","reply":"b","manager":null}', 'duplicate_fields'),
    ('{"reply":"a","manager":{"context":"a","context":"b","type":"контакт","name":""}}', 'duplicate_fields'),
    ('{"reply":"a","manager":null,"phone":"test"}', 'invalid_fields'),
    ('{"reply":"a"}', 'invalid_fields'),
    ('{"reply":null,"manager":null}', 'invalid_field_type'),
    ('{"reply":"","manager":null}', 'empty_reply'),
    ('{"reply":"a","manager":{"context":"","type":"контакт","name":""}}', 'empty_context'),
    ('{"reply":"a","manager":{"context":"test","type":"other","name":""}}', 'invalid_manager_type'),
    ('{"reply":"===МЕНЕДЖЕР===","manager":null}', 'service_marker'),
])
def test_raw_arguments_reach_existing_validator(raw, reason):
    assert parse(response(raw), True) == (None, reason)


def test_empty_reply_requires_explicit_permission():
    raw = json.dumps({'reply': '', 'manager': {'context': 'Нужен менеджер.', 'type': 'консультация', 'name': ''}})
    assert parse(response(raw))[1] == 'empty_reply'
    assert parse(response(raw), True)[1] is None


def test_tool_body_preserves_business_input_and_original():
    original = {'model': 'test', 'max_tokens': 2048, 'response_format': {'type': 'json_object'},
                'messages': [{'role': 'system', 'content': 'catalog\nOLD_FORMAT'},
                             {'role': 'user', 'content': 'question'}]}
    before = deepcopy(original)
    body = tool_body(original, 'OLD_FORMAT', strict=True)
    assert original == before
    assert body['messages'][1:] == original['messages'][1:]
    assert body['messages'][0]['content'].startswith('catalog\n')
    assert 'response_format' not in body
    assert body['extra_body']['thinking'] == {'type': 'disabled'}
    assert body['tool_choice']['function']['name'] == 'prepare_response'
    assert body['tools'] == [response_tool(True)]
    assert body['tools'][0]['function']['parameters']['additionalProperties'] is False


@pytest.mark.parametrize('malformed', [None, [], {'choices': [None]}])
def test_runner_retains_malformed_response_and_strict_failure_without_extra_calls(tmp_path, monkeypatch, malformed):
    from src.services import llm_response_log
    root, bundle = tmp_path / 'root', tmp_path / 'private'
    root.mkdir()
    bundle.mkdir()
    (root / 'runtime.py').write_text('original')
    (root / '.env').write_text('unchanged')
    cases = []
    for name, expected in [('json_control', 'reply'), ('tool_problem', 'reply'),
        ('tool_problem_repeat', 'reply'), ('tool_strict_problem', 'reply'),
        ('tool_manager', 'manager'), ('tool_silent', 'silent')]:
        cases.append([name, {'tools': [response_tool(name == 'tool_strict_problem')]}, expected == 'silent', expected])
    plan = {'cases': cases, 'runtime': {'runtime.py': tool_call_probe.sha(root / 'runtime.py')},
            'env_sha': tool_call_probe.sha(root / '.env')}
    (bundle / 'plan.private.json').write_text(json.dumps(plan))
    fake = SimpleNamespace(boot=lambda: (SimpleNamespace(deepseek_api_key='not-a-key'),
                                       SimpleNamespace(_validate_response=_validate_response)))
    monkeypatch.setattr(tool_call_probe, 'load_bootstrap', lambda _: fake)
    monkeypatch.setattr(llm_response_log, '_redact', lambda text: text)
    calls = []

    def send(body, key, strict):
        calls.append(strict)
        if len(calls) == 1:
            return 200, malformed
        if len(calls) == 2:
            return 200, {'choices': [{'finish_reason': 'tool_calls',
                'message': {'content': None, 'tool_calls': 123}}]}
        if strict:
            return 400, {'error': {'type': 'unsupported_schema'}}
        manager = {'context': 'Нужен менеджер.', 'type': 'консультация', 'name': ''}
        payload = {'reply': '' if len(calls) == 6 else 'Ответ',
                   'manager': manager if len(calls) >= 5 else None}
        return 200, response(json.dumps(payload))

    monkeypatch.setattr(tool_call_probe, 'send', send)
    args = SimpleNamespace(root=root, bundle=bundle, bootstrap=tmp_path / 'fake.py')
    result = tool_call_probe.run(args)
    assert result['calls'] == 6 and calls == [False, False, False, True, False, False]
    rows = [json.loads(line) for line in (bundle / 'responses.private.jsonl').read_text().splitlines()]
    done = [row for row in rows if 'call' in row]
    assert len(done) == 6
    assert done[0]['valid'] is False and done[0]['rejection'] == 'invalid_choices'
    assert done[3]['valid'] is False and done[3]['rejection'] == 'http_400'
    assert done[4]['semantic_ok'] is True and done[5]['semantic_ok'] is True
    assert (root / 'runtime.py').read_text() == 'original' and (root / '.env').read_text() == 'unchanged'
    with pytest.raises(AssertionError, match='Inspect existing'):
        tool_call_probe.run(args)
    assert len(calls) == 6
