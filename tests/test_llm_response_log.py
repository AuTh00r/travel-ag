from tests.model_responses import tool_response
from tests.model_responses import arguments_of
import importlib
import json
from unittest.mock import Mock

import pytest

from src.config import settings
from tests.test_ad_model_decision import model as model, pipeline as pipeline, response
from tests.test_ad_response_contract import visual


@pytest.fixture
def journal(tmp_path, monkeypatch):
    module = importlib.import_module('src.services.llm_response_log')
    module.close_response_log()
    monkeypatch.setattr(module, 'LOG_PATH', tmp_path / 'responses.jsonl')
    monkeypatch.setattr(settings, 'deepseek_response_log_enabled', True)
    yield module
    module.close_response_log()


def write(journal, content, **overrides):
    args = dict(request_id='a' * 32, sender_id='private-client-id', attempt=1,
                model='deepseek-flash', route='ad_vision', validation_reason='invalid_fields',
                response_fields={'finish_reason': 'stop', 'input_tokens': 200, 'output_tokens': 50})
    args.update(overrides)
    journal.log_llm_response(content, **args)


def test_incomplete_tool_reason_and_eof_are_preserved_privately(journal, caplog):
    raw = '{"reply":"PRIVATE_UNDELIVERED_REPLY","manager": '
    write(journal, raw, validation_reason='incomplete_tool_arguments',
          response_fields={'finish_reason': 'tool_calls', 'output_tokens': 231})
    result, = rows(journal)
    assert result['content'] == raw and not result['content_truncated']
    assert result['validation_reason'] == 'incomplete_tool_arguments'
    assert 'PRIVATE_UNDELIVERED_REPLY' not in caplog.text


def rows(journal):
    return [json.loads(line) for line in journal.LOG_PATH.read_text(encoding='utf-8').splitlines()]


@pytest.mark.parametrize('content', ['{"unexpected":"Привет"}', 'не JSON\nВторая строка', '', ' ' * 242])
def test_received_text_is_preserved_as_one_utf8_record(journal, content, capsys, caplog):
    write(journal, content)
    result, = rows(journal)
    assert result['content'] == content and result['content_chars'] == len(content)
    assert result['validation_reason'] == 'invalid_fields' and result['attempt'] == 1
    assert result['request_id'] == 'a' * 32 and len(result['sender_hash']) == 12
    assert 'private-client-id' not in journal.LOG_PATH.read_text(encoding='utf-8')
    assert result['timestamp'].endswith('Z') and not result['content_truncated']
    if content.strip():
        output = capsys.readouterr()
        assert content not in output.out + output.err + caplog.text


def test_secret_and_media_redaction_preserves_public_links(journal, monkeypatch):
    secret = 'sk_CONFIGURED_SECRET_123456'
    monkeypatch.setattr(settings, 'deepseek_api_key', secret)
    text = (f'{secret} Authorization: Bearer UNCONFIGURED_CREDENTIAL '
            'access_token="ANOTHER_CREDENTIAL" data:image/jpeg;base64,aGVsbG8= '
            'https://scontent.cdninstagram.com/video.mp4?x=1 '
            'https://example.com/x?signature=SIGNED_SECRET '
            'https://sundita.by/tur/elbrus')
    write(journal, text)
    result, = rows(journal)
    logged = result['content']
    for value in [secret, 'UNCONFIGURED_CREDENTIAL', 'ANOTHER_CREDENTIAL', 'aGVsbG8=',
                  'scontent.cdninstagram.com', 'SIGNED_SECRET']:
        assert value not in logged
    assert 'https://sundita.by/tur/elbrus' in logged


def test_redaction_happens_before_truncation(journal, monkeypatch):
    monkeypatch.setattr(journal, 'MAX_RESPONSE_CHARS', 20)
    monkeypatch.setattr(settings, 'deepseek_api_key', 'SECRET_CROSSING_THE_CUTOFF')
    write(journal, 'prefix SECRET_CROSSING_THE_CUTOFF suffix')
    result, = rows(journal)
    assert 'SECRET' not in result['content']
    assert len(result['content']) <= 20 and result['content_truncated']
    assert result['content_chars'] == len('prefix SECRET_CROSSING_THE_CUTOFF suffix')


def test_short_configured_secret_is_redacted(journal, monkeypatch):
    monkeypatch.setattr(settings, 'admin_api_token', 'abc12')
    write(journal, 'Ответ содержит abc12 внутри строки')
    assert 'abc12' not in rows(journal)[0]['content']


@pytest.mark.parametrize(('text', 'private'), [
    ('api-key=HEADER_SECRET_123', 'HEADER_SECRET_123'),
    ('X-API-Key: HEADER_SECRET_123', 'HEADER_SECRET_123'),
    ('Authorization: Basic YWxhZGRpbjpvcGVuc2VzYW1l', 'YWxhZGRpbjpvcGVuc2VzYW1l'),
    ('password="secret with spaces"', 'secret with spaces'),
    ('https://api.telegram.org/bot123456789:FAKE_TOKEN_abcdefghijkl/sendMessage', 'FAKE_TOKEN_abcdefghijkl'),
])
def test_recognizable_credentials_are_redacted(journal, text, private):
    write(journal, text)
    logged = rows(journal)[0]['content']
    assert private not in logged
    if text.startswith('password='):
        assert 'with spaces' not in logged


def test_non_text_content_and_arbitrary_metadata_are_not_serialized(journal):
    write(journal, [{'type': 'image_url', 'image_url': 'PRIVATE_BINARY'}],
          response_fields={'finish_reason': 'PRIVATE_FINISH', 'input_tokens': 'PRIVATE_TOKENS',
                           'output_tokens': 3, 'private': 'PRIVATE_METADATA'})
    result, = rows(journal)
    assert result['content'] is None and result['content_type'] == 'list'
    assert result['finish_reason'] == 'unknown' and result['input_tokens'] is None
    assert result['output_tokens'] == 3
    assert 'PRIVATE_' not in journal.LOG_PATH.read_text(encoding='utf-8')


def test_disabled_journal_does_not_create_file(journal, monkeypatch):
    monkeypatch.setattr(settings, 'deepseek_response_log_enabled', False)
    write(journal, 'response')
    assert not journal.LOG_PATH.exists()


def test_rotation_is_bounded_and_logger_handler_is_reused(journal, monkeypatch):
    monkeypatch.setattr(journal, 'MAX_LOG_BYTES', 700)
    monkeypatch.setattr(journal, 'BACKUP_COUNT', 2)
    write(journal, 'first')
    logger = journal._get_logger()
    handler = logger.handlers[0]
    for index in range(12):
        write(journal, f'response number {index}')
    assert journal._get_logger() is logger and logger.handlers == [handler]
    assert not logger.propagate
    files = list(journal.LOG_PATH.parent.glob('responses.jsonl*'))
    assert len(files) == 3
    assert rows(journal)[-1]['content'] == 'response number 11'
    for path in files:
        assert all(isinstance(json.loads(line), dict) for line in path.read_text(encoding='utf-8').splitlines())


@pytest.mark.parametrize('fault', ['init', 'redact', 'format', 'emit', 'rotation'])
def test_journal_failure_does_not_leak_or_raise(journal, monkeypatch, capsys, caplog, fault):
    private = 'PRIVATE_RAW_RESPONSE_AND_ERROR'

    def fail(*args, **kwargs):
        raise OSError(private)

    if fault == 'init':
        monkeypatch.setattr(journal, '_get_logger', fail)
    elif fault == 'redact':
        monkeypatch.setattr(journal, '_redact', fail)
    else:
        handler = journal._get_logger().handlers[0]
        if fault == 'format':
            monkeypatch.setattr(handler, 'format', fail)
        elif fault == 'emit':
            monkeypatch.setattr(handler, 'emit', fail)
        else:
            monkeypatch.setattr(handler, 'shouldRollover', lambda _: True)
            monkeypatch.setattr(handler, 'doRollover', fail)
    write(journal, private)
    output = capsys.readouterr()
    assert private not in output.out + output.err + caplog.text
    assert 'llm.response_log.failed' in output.out + output.err + caplog.text
    if fault == 'redact':
        result, = rows(journal)
        assert result['content'] is None and result['content_omitted']


@pytest.mark.parametrize(('route', 'count', 'is_ad'), [
    ('ad_text', 0, True), ('ad_vision', 10, True), ('text', 0, False), ('vision', 1, False),
])
async def test_all_model_paths_journal_received_answer(model, monkeypatch, route, count, is_ad):
    spy = Mock()
    monkeypatch.setattr(model.main, 'log_llm_response', spy, raising=False)
    if count:
        visual(model, monkeypatch, count)
    kwargs = {'referral': {'source': 'ADS', 'ad_id': '10'}} if is_ad else {}
    if count and not is_ad:
        monkeypatch.setattr(settings, 'image_media_enabled', True)
        monkeypatch.setattr('src.services.story_media.prepare_images', model.prepare)
        kwargs['image_urls'] = ['https://scontent.cdninstagram.com/test.jpg']
    model.invoke.return_value = response()
    await model.main.process_with_ai('context-client', 'Эльбрус', **kwargs)
    spy.assert_called_once()
    assert spy.call_args.args[0] == arguments_of(model.invoke.return_value)
    assert spy.call_args.kwargs['route'] == ('text' if is_ad else route)
    assert spy.call_args.kwargs['validation_reason'] == 'valid'


async def test_empty_retry_journals_each_attempt_with_shared_trace(model, monkeypatch):
    spy = Mock()
    monkeypatch.setattr(model.main, 'log_llm_response', spy, raising=False)
    first = tool_response(arguments=' ' * 242, usage_metadata={})
    model.invoke.side_effect = [first, response()]
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert spy.call_count == 2
    a, b = spy.call_args_list
    assert a.args[0] == ' ' * 242 and b.args[0] == arguments_of(response())
    assert a.kwargs['request_id'] == b.kwargs['request_id']
    assert len(a.kwargs['request_id']) == 32
    assert [a.kwargs['attempt'], b.kwargs['attempt']] == [1, 2]
    assert a.kwargs['validation_reason'] == 'empty_response'
    model.send.assert_awaited_once()
    model.notify.assert_not_awaited()


async def test_received_response_is_journaled_even_when_manager_takes_over(model, monkeypatch):
    spy = Mock()
    monkeypatch.setattr(model.main, 'log_llm_response', spy, raising=False)

    async def invoke(_):
        model.main._manager_pending['context-client'] = True
        return response()

    model.invoke.side_effect = invoke
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    spy.assert_called_once()
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()


async def test_disk_failure_does_not_change_client_answer(journal, model, monkeypatch):
    def fail():
        raise OSError('PRIVATE_DISK_ERROR')
    monkeypatch.setattr(journal, '_get_logger', fail)
    model.invoke.return_value = response()
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    model.invoke.assert_awaited_once()
    model.send.assert_awaited_once_with('context-client', 'Программа тура доступна по ссылке.')
    model.notify.assert_not_awaited()
