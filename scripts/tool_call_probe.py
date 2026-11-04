"""Isolated DeepSeek transport probe. Never executes model tools or sends messages."""

import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.request

FUNCTION = 'prepare_response'
TOOL_RULES = '''
[ФОРМАТ РЕЗУЛЬТАТА — ВЫЗОВ ФУНКЦИИ]
Верни ровно один вызов prepare_response. В его аргументах reply — видимый ответ
клиенту, manager — null либо объект context/type/name по правилам выше.
Обычный ответ: reply непустой, manager=null. При необходимости менеджера заполни
manager с кратким context, type консультация/контакт/отзыв и известным name либо "".
Только в разрешённом случае молчаливой передачи reply="", manager заполнен.
Не добавляй обычный текст вне вызова, другие функции или дополнительные поля.
Не добавляй служебные маркеры и телефон. Функция лишь подготавливает результат:
она не отправляет сообщения и не подтверждает передачу менеджеру.
Это правило формата имеет приоритет над форматом старых ответов в истории.
'''


def response_tool(strict=False):
    manager = {'type': 'object', 'properties': {
        'context': {'type': 'string'},
        'type': {'type': 'string', 'enum': ['консультация', 'контакт', 'отзыв']},
        'name': {'type': 'string'}},
        'required': ['context', 'type', 'name'], 'additionalProperties': False}
    function = {'name': FUNCTION, 'description': 'Подготовить ответ и потребность в менеджере без внешних действий.',
        'parameters': {'type': 'object', 'properties': {
            'reply': {'type': 'string'}, 'manager': {'anyOf': [{'type': 'null'}, manager]}},
            'required': ['reply', 'manager'], 'additionalProperties': False}}
    if strict:
        function['strict'] = True
    return {'type': 'function', 'function': function}


def tool_body(original, response_rules, strict=False):
    body = deepcopy(original)
    body.pop('response_format', None)
    system = body['messages'][0]
    assert system['role'] == 'system' and system['content'].count(response_rules) == 1
    system['content'] = system['content'].replace(response_rules, TOOL_RULES)
    body['tools'] = [response_tool(strict)]
    body['tool_choice'] = {'type': 'function', 'function': {'name': FUNCTION}}
    body['extra_body'] = {**body.get('extra_body', {}), 'thinking': {'type': 'disabled'}}
    return body


def extract_tool_result(data, validator, *, allow_silent=False):
    """Keep original argument text: duplicate keys must reach the old validator."""
    choices = data.get('choices') if isinstance(data, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return None, 'invalid_choices'
    choice = choices[0]
    if choice.get('finish_reason') == 'length':
        return None, 'response_truncated'
    if choice.get('finish_reason') != 'tool_calls':
        return None, 'invalid_finish_reason'
    message = choice.get('message')
    if not isinstance(message, dict):
        return None, 'invalid_message'
    content = message.get('content')
    if content is not None and (not isinstance(content, str) or content.strip()):
        return None, 'content_with_tool'
    calls = message.get('tool_calls')
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        return None, 'invalid_tool_count'
    call = calls[0]
    function = call.get('function')
    if (call.get('type') != 'function' or not isinstance(call.get('id'), str) or not call['id']
            or not isinstance(function, dict) or function.get('name') != FUNCTION):
        return None, 'invalid_tool'
    arguments = function.get('arguments')
    if not isinstance(arguments, str):
        return None, 'invalid_arguments_type'
    return validator(arguments, allow_silent=allow_silent)


@contextmanager
def no_network():
    from unittest.mock import patch
    def deny(*args, **kwargs):
        raise RuntimeError('External I/O forbidden during preparation')
    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket, 'connect_ex', deny):
        yield


def load_bootstrap(path):
    spec = importlib.util.spec_from_file_location('previous_whitespace_bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(args):
    assert not (args.bundle / 'plan.private.json').exists()
    with no_network():
        old = load_bootstrap(args.bootstrap)
        settings, main = old.boot()
        from src.ai.prompts import _RESPONSE_RULES, build_full_prompt
        from src.config import MINSK_TZ
        from src.services.llm import get_llm
        prior = json.loads(args.prior_inputs.read_text(encoding='utf-8'))
        assert all(sha(args.root / name) == value for name, value in prior['runtime'].items())
        baseline = prior['cases'][0][1]
        assert baseline['response_format'] == {'type': 'json_object'}
        tests = [('json_control', baseline, False, 'reply'),
                 ('tool_problem', tool_body(baseline, _RESPONSE_RULES), False, 'reply'),
                 ('tool_problem_repeat', tool_body(baseline, _RESPONSE_RULES), False, 'reply'),
                 ('tool_strict_problem', tool_body(baseline, _RESPONSE_RULES, True), False, 'reply')]
        tours = json.loads((args.root / 'data/tours_snapshot.json').read_text(encoding='utf-8-sig'))['text']
        now = datetime.now(MINSK_TZ)
        for name, question, silent in [
            ('tool_manager', 'По Эльбрусу хочу поговорить с менеджером, уточнить свободные места', False),
            ('tool_silent', 'Здравствуйте! Можно подробнее?', True)]:
            messages = build_full_prompt(tours, '', [], question, 0, current_date=now.date(),
                current_time=now.strftime('%H:%M'), should_greet=False, is_first_message=False,
                ad_context='Источник ADS. Содержимое объявления недоступно; тур неизвестен.' if silent else '')
            original = get_llm()._get_request_payload(messages)
            tests.append((name, tool_body(original, _RESPONSE_RULES), silent, 'silent' if silent else 'manager'))
        for _, body, _, _ in tests:
            assert body.get('max_tokens', body.get('max_completion_tokens')) == 2048
            assert body.get('stream', False) is False
        # Existing validator, not a permissive substitute.
        assert main._validate_response('{"reply":"test","manager":null}')[1] is None
        assert main._validate_response('{"reply":"x","reply":"y","manager":null}')[1] == 'duplicate_fields'
    args.bundle.mkdir(parents=True, exist_ok=True)
    with (args.bundle / 'plan.private.json').open('x', encoding='utf-8') as stream:
        json.dump({'cases': tests, 'runtime': prior['runtime'], 'env_sha': sha(args.root / '.env')}, stream, ensure_ascii=False)
    return {'preflight': True, 'external_calls': 0, 'planned_calls': len(tests),
            'runtime_count': len(prior['runtime']), 'tool_executes_external_actions': False}


def send(body, key, strict):
    wire = deepcopy(body)
    wire.update(wire.pop('extra_body', {}))
    url = 'https://api.deepseek.com/' + ('beta/' if strict else '') + 'chat/completions'
    request = urllib.request.Request(url, data=json.dumps(wire, ensure_ascii=False).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            return response.status, json.loads(response.read(262145))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read(262145))


def run(args):
    report = args.bundle / 'responses.private.jsonl'
    assert not report.exists(), 'Inspect existing reserved calls instead of repeating run'
    plan = json.loads((args.bundle / 'plan.private.json').read_text(encoding='utf-8'))
    assert len(plan['cases']) == 6
    assert all(sha(args.root / name) == value for name, value in plan['runtime'].items())
    assert sha(args.root / '.env') == plan['env_sha']
    with no_network():
        old = load_bootstrap(args.bootstrap)
        settings, main = old.boot()
        from src.services.llm_response_log import _redact
    strict_ok = False
    with report.open('x', encoding='utf-8') as stream:
        for index, (name, body, silent, expected) in enumerate(plan['cases'], 1):
            body = deepcopy(body)
            strict = name == 'tool_strict_problem' or (index >= 5 and strict_ok)
            if strict:
                body['tools'] = [response_tool(True)]
            stream.write(json.dumps({'started_call': index, 'case': name, 'strict': strict}) + '\n')
            stream.flush()
            started = time.monotonic()
            status, data = send(body, settings.deepseek_api_key, strict)
            choices = data.get('choices') if isinstance(data, dict) else None
            valid_choice = isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
            choice = choices[0] if valid_choice else {}
            message = choice.get('message')
            message = message if isinstance(message, dict) else {}
            if status != 200:
                result, reason = None, 'http_' + str(status)
            elif index == 1:
                result, reason = main._validate_response(message.get('content')) if valid_choice else (None, 'invalid_choices')
                if choice.get('finish_reason') == 'length':
                    result, reason = None, 'response_truncated'
            else:
                result, reason = extract_tool_result(data, main._validate_response, allow_silent=silent)
            if name == 'tool_strict_problem':
                strict_ok = result is not None
            semantic_ok = bool(result) and (
                (expected == 'reply' and bool(result['reply'].strip())) or
                (expected == 'manager' and bool(result['reply'].strip()) and result['manager'] is not None) or
                (expected == 'silent' and not result['reply'].strip() and result['manager'] is not None))
            raw = message.get('content')
            calls = message.get('tool_calls')
            row = {'call': index, 'case': name, 'strict': strict, 'http_status': status,
                'seconds': round(time.monotonic() - started, 2), 'valid': result is not None,
                'rejection': reason, 'semantic_ok': semantic_ok, 'finish_reason': choice.get('finish_reason'),
                'content_chars': len(raw) if isinstance(raw, str) else None,
                'whitespace_only': isinstance(raw, str) and bool(raw) and raw.isspace(),
                'tool_count': len(calls) if isinstance(calls, list) else 0,
                'reply_chars': len(result['reply']) if result else None,
                'has_manager': result['manager'] is not None if result else None,
                'model_returned': data.get('model') if isinstance(data, dict) else None,
                'usage': data.get('usage') if isinstance(data, dict) else None}
            stream.write(json.dumps({**row, 'raw_response': _redact(json.dumps(data, ensure_ascii=False))}, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps(row), flush=True)
            if status in (401, 403, 429) or status >= 500:
                raise RuntimeError('Provider unavailable: do not spend remaining calls')
    assert all(sha(args.root / name) == value for name, value in plan['runtime'].items())
    assert sha(args.root / '.env') == plan['env_sha']
    return {'completed': True, 'calls': 6, 'runtime_config_preserved': True, 'customer_or_manager_sends': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'run'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--bootstrap', type=Path, required=True)
    parser.add_argument('--prior-inputs', type=Path, required=True)
    args = parser.parse_args()
    try:
        ast.parse(Path(__file__).read_text(encoding='utf-8'))
        print(json.dumps(preflight(args) if args.action == 'preflight' else run(args)))
    except Exception as error:
        print(json.dumps({'error': type(error).__name__, 'action': args.action}))
        sys.exit(1)


if __name__ == '__main__':
    main()
