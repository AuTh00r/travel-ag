from tests.model_responses import tool_response
from tests.model_responses import arguments_of, set_arguments
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.messages import HumanMessage

from src.config import settings
from src.services.story_media import StoryMedia
from tests.test_ad_model_decision import model as model, pipeline as pipeline, response
from tests.model_responses import reply_json, manager_data


@pytest.mark.parametrize('wrapper', ['{}', '```json\n{}\n```', '```\n{}\n```'], ids=['bare', 'json-fence', 'fence'])
async def test_complete_json_wrappers_keep_the_model_answer(model, wrapper):
    model.invoke.return_value = response()
    set_arguments(model.invoke.return_value, wrapper.format(arguments_of(model.invoke.return_value)))
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    model.invoke.assert_awaited_once()
    model.send.assert_awaited_once_with('context-client', 'Программа тура доступна по ссылке.')
    model.notify.assert_not_awaited()


@pytest.mark.parametrize(('content', 'reason'), [
    (None, 'invalid_type'), ('', 'empty_response'), ('x' * 16001, 'response_too_long'),
    ('Обычный ответ', 'invalid_json'), ('Ответ: {"decision":"answer"}', 'invalid_json'),
    ('```json\n{}\n```\nЕщё текст', 'invalid_json'), ('[]', 'invalid_fields'),
    ('{"reply":"Да","reply":"Нет","manager":null}', 'duplicate_fields'),
    ('{"reply":"Да","manager":null,"extra":true}', 'invalid_fields'),
    ('{"reply":null,"manager":null}', 'invalid_field_type'),
    (reply_json('Да', manager_data('Вопрос', 'other')), 'invalid_manager_type'),
    (reply_json(''), 'empty_reply'),
    (reply_json('Да', manager_data('')), 'empty_context'),
    (reply_json('Да', manager_data('я' * 451)), 'context_too_long'),
], ids=['type', 'empty', 'size', 'prose', 'prefix', 'suffix', 'array', 'duplicate',
        'extra', 'field-type', 'decision', 'empty-reply', 'handoff-reply', 'context-size'])
def test_rejections_have_a_specific_safe_reason(model, content, reason):
    decision, actual = model.main._validate_response(content)
    assert decision is None and actual == reason


def visual(model, monkeypatch, count):
    model.prepare.side_effect = None
    model.prepare.return_value = StoryMedia(None, 'VIDEO' if count == 10 else 'IMAGE',
        [{'label': f'Кадр {i}', 'url': 'data:image/jpeg;base64,/9j/AA=='} for i in range(count)])
    factory = Mock(return_value=SimpleNamespace(ainvoke=model.invoke))
    monkeypatch.setattr('src.services.llm.get_vision_llm', factory)
    return factory


@pytest.mark.parametrize(('question', 'count'), [
    ('Эльбрус', 10), ('Виза есть! Пришлите программу тура ВДП', 1),
])
async def test_observed_visual_queries_request_json_and_answer_once(model, monkeypatch, question, count):
    factory = visual(model, monkeypatch, count)
    model.invoke.return_value = response()
    set_arguments(model.invoke.return_value, '```json\n' + arguments_of(model.invoke.return_value) + '\n```')
    await model.main.process_with_ai('context-client', question, referral={'source': 'ADS', 'ad_id': '10'})
    factory.assert_not_called()
    model.invoke.assert_awaited_once()
    parts = model.invoke.await_args.args[0][-1].content
    assert isinstance(parts, str)
    assert question in str(parts)
    model.send.assert_awaited_once()
    model.notify.assert_not_awaited()


def test_visual_factory_json_mode_keeps_images_and_thinking_settings(monkeypatch):
    from src.services.llm import get_vision_llm
    monkeypatch.setattr(settings, 'deepseek_api_key', 'TEST_KEY')
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,/9j/AA==', 'detail': 'original'}}
    llm = get_vision_llm()
    payload = llm._get_request_payload([HumanMessage(content=[{'type': 'text', 'text': 'JSON'}, image])])
    assert 'response_format' not in payload
    assert payload['tools'][0]['function']['name'] == 'prepare_response'
    assert payload['messages'][0]['content'][1] == image
    assert payload['extra_body'] == {'thinking': {'type': 'disabled'}, 'max_tokens': 2048}
    assert 'max_completion_tokens' not in payload
    assert llm.root_async_client.max_retries == 0


async def test_invalid_answer_logs_metadata_and_preserves_actual_question(model, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(model.main, 'logger', logger)
    private_reply = 'PRIVATE_MODEL_OUTPUT https://secret.invalid/token=PRIVATE'
    model.invoke.return_value = tool_response(arguments=private_reply,
        usage_metadata={'input_tokens': 19383, 'output_tokens': 288},
        response_metadata={'finish_reason': 'tool_calls', 'private': private_reply})
    model.state['history'] = [{'role': 'user', 'content': 'Старый вопрос про Францию'}]
    await model.main.process_with_ai('context-client', 'Виза есть! Пришлите программу тура ВДП',
                                    referral={'source': 'ADS', 'ad_id': '10'})
    fields = next(call.kwargs for call in logger.warning.call_args_list
                  if call.args[0] == 'llm.invalid_model_response')
    assert fields['reason'] == 'invalid_json' and fields['finish_reason'] == 'tool_calls'
    assert fields['output_tokens'] == 288 and fields['response_chars'] == len(private_reply)
    assert private_reply not in str(logger.mock_calls)
    context = model.notify.await_args.kwargs['context']
    assert 'Виза есть! Пришлите программу тура ВДП' in context
    assert 'Диагностика:' in context and 'invalid_json' in context
    assert 'Францию' not in context and private_reply not in context
    assert model.invoke.await_count == 3
    model.send.assert_not_awaited()
    model.queue.assert_not_awaited()


async def test_truncated_response_never_sends_even_a_parseable_envelope(model, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(model.main, 'logger', logger)
    model.invoke.return_value = response()
    model.invoke.return_value.response_metadata = {'finish_reason': 'length'}
    await model.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert any(call.kwargs.get('reason') == 'response_truncated' for call in logger.warning.call_args_list)
    context = model.notify.await_args.kwargs['context']
    assert 'Эльбрус' in context and 'response_truncated' in context
    model.send.assert_not_awaited()
    assert model.invoke.await_count == 3


@pytest.mark.parametrize('count', [0, 10])
async def test_provider_failure_is_technical_silent_and_keeps_question(model, monkeypatch, count):
    if count:
        visual(model, monkeypatch, count)
    logger = Mock()
    monkeypatch.setattr(model.main, 'logger', logger)
    model.invoke.side_effect = RuntimeError('PRIVATE_EXCEPTION https://secret.invalid')
    await model.main._process_safely('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    model.invoke.assert_awaited_once()
    model.send.assert_not_awaited()
    model.queue.assert_not_awaited()
    context = model.notify.await_args.kwargs['context']
    assert 'Эльбрус' in context and 'RuntimeError' in context and 'invoke' in context
    assert 'PRIVATE_EXCEPTION' not in str(logger.mock_calls) + context


async def test_technical_context_separates_current_phone_and_hides_service_data(model):
    model.invoke.return_value = tool_response(arguments='not json', usage_metadata={})
    await model.main.process_with_ai('context-client',
        'Эльбрус https://example.invalid/private\n+375252222222', referral={'source': 'ADS', 'ad_id': '10'})
    fields = model.notify.await_args.kwargs
    assert fields['client_phone'] == '+375252222222'
    assert 'Эльбрус' in fields['context'] and len(fields['context']) <= 2000
    assert 'http' not in fields['context'] and '375252222222' not in fields['context']
    model.send.assert_not_awaited()


def test_response_metadata_does_not_log_unknown_provider_values(model):
    private = 'PRIVATE https://secret.invalid'
    fields = model.main._response_metadata(SimpleNamespace(content=['private'],
        response_metadata={'finish_reason': private},
        usage_metadata={'input_tokens': private, 'output_tokens': True}))
    assert fields == {'finish_reason': 'unknown', 'response_chars': None,
                      'response_kind': 'other', 'input_tokens': None, 'output_tokens': None}
