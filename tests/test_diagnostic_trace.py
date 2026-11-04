"""Private diagnostics never changes model inputs, business effects or receipts."""
from copy import deepcopy
import json
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage, SystemMessage
import pytest

from src.config import settings
from src.services import diagnostic_trace as trace
from src.services import llm_response_log


def rows():
    return [json.loads(line) for line in trace.LOG_PATH.read_text(encoding='utf-8').splitlines()]


def test_full_request_and_credentials_media_are_safe(monkeypatch, caplog, capsys):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'sk_PRIVATE_CONFIGURED')
    messages = [SystemMessage(content='PRIVATE_SYSTEM catalog FAQ'), HumanMessage(content=[
        {'type': 'text', 'text': 'PRIVATE_QUESTION https://sundita.by/tur/elbrus'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,AAAA\nBBBB\nCC=='}}])]
    before = deepcopy(messages)
    model = type('Model', (), {'temperature': .1, 'max_retries': 0, 'model_kwargs': {
        'tools': [{'function': {'name': 'prepare_response'}}]},
        'extra_body': {'api_key': 'NESTED_PRIVATE'}})()
    with trace.trace_scope('private-client'):
        trace.log_model_request(messages, sender_id='private-client', request_id='a' * 32,
                                phase='primary', attempt=1, model='test', llm=model)
        trace.trace_event('debug_data', sender_id='private-client', data={'authorization': 'Bearer HIDDEN',
            'nested': {'api_key': 'NESTED_PRIVATE', 'password': {'value': 'SECRET_CONTAINER'}},
            'value': 'sk_PRIVATE_CONFIGURED', 'url': 'https://media.example/x?X-Goog-Signature=PRIVATE_SIGNED',
            'raw': b'PRIVATE_BINARY', 'wrapped': 'prefix data:audio/aac;base64,AAAA\nBBBB\nCC== suffix'})
    assert messages == before
    records = rows()
    raw = trace.LOG_PATH.read_text(encoding='utf-8')
    assert 'PRIVATE_SYSTEM' in raw and 'PRIVATE_QUESTION' in raw and 'https://sundita.by' in raw
    for value in ('AAAA', 'BBBB', 'CC==', 'PRIVATE_BINARY', 'PRIVATE_SIGNED', 'NESTED_PRIVATE',
                  'sk_PRIVATE_CONFIGURED', 'SECRET_CONTAINER', 'private-client', 'Bearer HIDDEN'):
        assert value not in raw
    assert records[0]['data']['messages'][1]['content'][1]['content_omitted']
    assert records[0]['correlation']['trace_id'] == records[1]['correlation']['trace_id']
    output = capsys.readouterr()
    assert 'PRIVATE_SYSTEM' not in output.out + output.err + caplog.text


def test_byte_limit_is_explicit_and_valid_json(monkeypatch):
    monkeypatch.setattr(trace, 'MAX_RECORD_BYTES', 1600)
    trace.trace_event('large_record', text='абв' * 2000, many=['😀' * 200] * 10)
    raw = trace.LOG_PATH.read_bytes()
    assert len(raw.rstrip(b'\r\n')) <= 1600
    record, = rows()
    assert record['truncated'] and record['data']['reason'] == 'encoded_record_limit'


def test_cycles_unknown_objects_and_no_repr():
    class Dangerous:
        def __repr__(self):
            raise AssertionError('Never serialize arbitrary objects')
    payload = {'object': Dangerous()}
    payload['cycle'] = payload
    trace.trace_event('safe_shape', value=payload)
    record, = rows()
    assert record['data']['value']['object'] == '[UNSUPPORTED_OBJECT]'
    assert record['data']['value']['cycle']['reason'] == 'cycle'


@pytest.mark.parametrize('fault', ['init', 'sanitize', 'encode', 'emit', 'rotation'])
async def test_diagnostic_fault_does_not_change_execution(monkeypatch, caplog, capsys, fault):
    private = 'PRIVATE_PAYLOAD_AND_ERROR'
    def fail(*args, **kwargs):
        raise OSError(private)
    if fault in {'init', 'sanitize', 'encode'}:
        monkeypatch.setattr(trace, {'init': '_get_logger', 'sanitize': 'sanitize', 'encode': '_encode'}[fault], fail)
    else:
        handler = trace._get_logger().handlers[0]
        if fault == 'emit':
            monkeypatch.setattr(handler, 'emit', fail)
        else:
            monkeypatch.setattr(handler, 'shouldRollover', lambda _: True)
            monkeypatch.setattr(handler, 'doRollover', fail)
    operation = AsyncMock(return_value='accepted-mid')
    @trace.traced_flow('test')
    async def run(sender_id, text):
        return await operation(text)
    assert await run('client', private) == 'accepted-mid'
    operation.assert_awaited_once_with(private)
    output = capsys.readouterr()
    assert private not in output.out + output.err + caplog.text
    assert trace._scope.get() is None


def test_off_disables_both_journals(monkeypatch):
    monkeypatch.setattr(settings, 'deepseek_response_log_enabled', False)
    trace.trace_event('disabled', content='text')
    llm_response_log.log_llm_response('text', request_id='a' * 32, sender_id='client', attempt=1,
        model='test', route='text', validation_reason='valid', response_fields={})
    assert not trace.LOG_PATH.exists() and not llm_response_log.LOG_PATH.exists()


def test_response_mirrors_with_request_and_parent():
    llm_response_log.log_llm_response('{"reply":"PRIVATE_ANSWER","manager":null}',
        request_id='b' * 32, parent_request_id='a' * 32, sender_id='client', attempt=1,
        model='test', route='text', phase='handoff_review', validation_reason='valid', response_fields={})
    record, = rows()
    assert record['event'] == 'model_response'
    assert record['data']['response']['request_id'] == 'b' * 32
    assert record['data']['response']['parent_request_id'] == 'a' * 32


def test_wrapped_base64_and_new_signed_urls_are_redacted_in_original_log():
    text = ('data:image/png;base64,AAAA\nBBBB\nCC== '
            'https://private.example/x?X-Goog-Signature=HIDDEN '
            'https://private.example/x?auth_token=HIDDEN2 https://sundita.by/tur/elbrus')
    cleaned = llm_response_log._redact(text)
    assert all(value not in cleaned for value in ('AAAA', 'BBBB', 'CC==', 'HIDDEN', 'HIDDEN2'))
    assert 'https://sundita.by/tur/elbrus' in cleaned


def test_usage_numbers_are_kept_and_env_shaped_credentials_are_not():
    trace.trace_event('usage', input_tokens=200, output_tokens=41, max_tokens=2048,
                      secret_fields={'CF_ACCESS_CLIENT_SECRET': 'CF_PRIVATE', 'SSH_PRIVATE_KEY_B64': 'FAKE_B64_CREDENTIAL_98'},
                      pasted='CF_ACCESS_CLIENT_SECRET=CF_PRIVATE SSH_PRIVATE_KEY_B64=FAKE_B64_CREDENTIAL_98')
    record, = rows()
    assert record['data']['input_tokens'] == 200 and record['data']['output_tokens'] == 41
    assert record['data']['max_tokens'] == 2048
    assert 'CF_PRIVATE' not in trace.LOG_PATH.read_text(encoding='utf-8')
    assert 'FAKE_B64_CREDENTIAL_98' not in record['data']['pasted']


def test_private_trace_rotation_counts_encoded_bytes(monkeypatch):
    monkeypatch.setattr(trace, 'MAX_LOG_BYTES', 1700)
    monkeypatch.setattr(trace, 'BACKUP_COUNT', 2)
    for _ in range(15):
        trace.trace_event('unicode', text='Ж' * 350)
    files = list(trace.LOG_PATH.parent.glob('deepseek-trace.jsonl*'))
    assert len(files) == 3
    assert all(path.stat().st_size <= 1700 for path in files)
    assert all(json.loads(line)['event'] == 'unicode' for path in files
               for line in path.read_text(encoding='utf-8').splitlines())


def test_truncation_is_after_redaction(monkeypatch):
    monkeypatch.setattr(trace, 'MAX_TEXT_CHARS', 12)
    monkeypatch.setattr(settings, 'deepseek_api_key', 'BOUNDARY_PRIVATE_KEY')
    trace.trace_event('boundary', text='prefix BOUNDARY_PRIVATE_KEY suffix')
    raw = trace.LOG_PATH.read_text(encoding='utf-8')
    assert 'BOUNDARY_PRIVATE' not in raw
    assert rows()[0]['data']['text']['truncated']


@pytest.mark.parametrize('variant', ['nested', 'twice', 'truncated', 'unicode_key', 'binary', 'redirect', 'double_redirect'])
def test_encoded_sensitive_content_is_absent_from_both_journals(variant):
    from urllib.parse import quote

    private = 'SYNTHETIC_UNKNOWN_CREDENTIAL_9384'
    raw = json.dumps({'function': {'arguments': json.dumps({'api_key': private})}})
    if variant == 'twice':
        raw = json.dumps({'nested': raw})
    elif variant == 'truncated':
        raw = raw[:-3]
    elif variant == 'unicode_key':
        raw = r'{"api_\u006bey":"' + private + '"}'
    elif variant == 'binary':
        raw = json.dumps({'b64_json': private})
    elif variant in {'redirect', 'double_redirect'}:
        target = 'https://storage.example/image?X-Goog-Signature=' + private
        if variant == 'double_redirect':
            target = quote(target, safe='')
        raw = 'https://redirect.example/view?url=' + quote(target, safe='')
    trace.trace_event('encoded', response=raw)
    llm_response_log.log_llm_response(raw, request_id='a' * 32, sender_id='client', attempt=1,
        model='test', route='text', validation_reason='invalid_json', response_fields={})
    for path in (trace.LOG_PATH, llm_response_log.LOG_PATH):
        assert private not in path.read_text(encoding='utf-8')


def test_ordinary_nested_arguments_stay_raw_for_diagnosis():
    raw = json.dumps({'function': {'arguments': '{"reply":"Про Белосток", "manager":'}}, ensure_ascii=False)
    assert llm_response_log._redact(raw) == raw


def test_nested_clients_do_not_inherit_each_others_trace():
    with trace.trace_scope('first-client'):
        first = trace.correlation('first-client')
        with trace.trace_scope('second-client'):
            second = trace.correlation('second-client')
            assert second['trace_id'] != first['trace_id'] and second['sender_hash'] != first['sender_hash']
        assert trace.correlation('first-client') == first
    assert trace._scope.get() is None


@pytest.mark.parametrize('media_key', sorted(llm_response_log.MEDIA_CONTENT_KEYS))
def test_binary_aliases_are_consistent_in_structured_and_encoded_values(media_key):
    binary = 'UVdFUlRZX1NZTlRIRVRJQ19CSU5BUlk='
    for value in ({media_key: binary}, json.dumps({media_key: binary}),
                  json.dumps({'nested': json.dumps({media_key: binary})})):
        cleaned = trace.sanitize(value)
        assert binary not in json.dumps(cleaned)
