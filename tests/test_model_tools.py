"""Exercise the actual SDK conversion without external model requests."""
from copy import deepcopy
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage

from src.config import settings
from src.main import _validate_response
from src.services import llm


def wire(arguments='{"reply":"Ответ","manager":null}'):
    return {'id': 'proof', 'object': 'chat.completion', 'created': 1, 'model': 'deepseek-flash',
            'usage': {'prompt_tokens': 20, 'completion_tokens': 5, 'total_tokens': 25},
            'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': 'call-proof', 'type': 'function', 'function': {
                        'name': 'prepare_response', 'arguments': arguments}}]}}]}


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    return llm.get_llm()


def converted(model, body):
    generation = model._create_chat_result(body).generations[0]
    generation.message.response_metadata = generation.generation_info
    return generation.message


@pytest.mark.parametrize('factory', ['get_llm', 'get_vision_llm'])
def test_shared_factory_payload(monkeypatch, factory):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    model = getattr(llm, factory)()
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,AA==', 'detail': 'original'}}
    payload = model._get_request_payload([HumanMessage(content=[{'type': 'text', 'text': 'Вопрос'}, image])])
    assert 'response_format' not in payload
    assert payload['tools'] == [llm.response_tool()]
    assert payload['tool_choice'] == {'type': 'function', 'function': {'name': 'prepare_response'}}
    assert payload['extra_body']['thinking'] == {'type': 'disabled'}
    assert 'max_completion_tokens' not in payload
    assert payload['extra_body']['max_tokens'] == 2048
    assert payload['messages'][0]['content'][1] == image
    assert str(model.root_async_client.base_url) == 'https://api.deepseek.com/beta/'
    assert model.root_async_client.max_retries == 0


@pytest.mark.parametrize('raw,reason', [
    ('{"reply":"a","reply":"b","manager":null}', 'duplicate_fields'),
    ('{"reply":"a","manager":{"context":"a","context":"b","type":"контакт","name":""}}', 'duplicate_fields'),
    ('{"reply":garbage}', 'invalid_json'),
    ('   ', 'empty_response'),
])
def test_original_arguments_survive_sdk(model, raw, reason):
    body = wire(raw)
    before = deepcopy(body)
    response = converted(model, body)
    arguments, error = llm.response_arguments(response)
    assert error is None and arguments == raw
    assert _validate_response(arguments)[1] == reason
    assert body == before
    assert response.usage_metadata == {'input_tokens': 20, 'output_tokens': 5, 'total_tokens': 25,
                                       'input_token_details': {}, 'output_token_details': {}}


@pytest.mark.parametrize('mode,reason', [
    ('missing', 'invalid_tool_count'), ('multiple', 'invalid_tool_count'),
    ('wrong_name', 'invalid_tool'), ('missing_id', 'invalid_tool'),
    ('nonlist', 'invalid_tool_count'), ('nonstring_args', 'invalid_arguments_type'),
    ('content', 'content_with_tool'), ('stop', 'invalid_finish_reason'),
    ('length', 'response_truncated'), ('plain_json', 'invalid_finish_reason'),
])
def test_sdk_envelopes_fail_closed(model, mode, reason):
    body = wire()
    choice = body['choices'][0]
    message = choice['message']
    if mode == 'missing':
        message.pop('tool_calls')
    elif mode == 'multiple':
        message['tool_calls'] *= 2
    elif mode == 'wrong_name':
        message['tool_calls'][0]['function']['name'] = 'send_message'
    elif mode == 'missing_id':
        message['tool_calls'][0].pop('id')
    elif mode == 'nonlist':
        message['tool_calls'] = 123
    elif mode == 'nonstring_args':
        message['tool_calls'][0]['function']['arguments'] = {'reply': 'bad'}
    elif mode == 'content':
        message['content'] = 'Нельзя отправлять'
    elif mode == 'plain_json':
        message['content'] = '{"reply":"Ответ","manager":null}'
        message.pop('tool_calls')
        choice['finish_reason'] = 'stop'
    else:
        choice['finish_reason'] = mode
    assert llm.response_arguments(converted(model, body)) == (None, reason)


async def test_real_async_sdk_path_uses_one_http_request(monkeypatch):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=wire())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        model = llm.get_llm().model_copy(update={'http_async_client': client})
        # Root OpenAI client must actually use the mocked transport.
        import openai
        root = openai.AsyncOpenAI(api_key='proof-not-secret', base_url='https://api.deepseek.com/beta',
                                  http_client=client, max_retries=0)
        model.root_async_client, model.async_client = root, root.chat.completions
        response = await model.ainvoke([HumanMessage(content='Вопрос')])
    assert len(requests) == 1 and requests[0]['tools'][0]['function']['strict'] is True
    assert requests[0]['max_tokens'] == 2048 and 'max_completion_tokens' not in requests[0]
    assert llm.response_arguments(response) == ('{"reply":"Ответ","manager":null}', None)


async def test_non_json_sdk_response_is_typed_and_safe(monkeypatch):
    from src.exceptions import ProviderResponseError
    from src.services.model_failure import retryable_error
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    import openai
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text='PRIVATE_PROVIDER_BODY'))) as client:
        model = llm.get_llm()
        root = openai.AsyncOpenAI(api_key='proof-not-secret', http_client=client, max_retries=0)
        model.root_async_client, model.async_client = root, root.chat.completions
        with pytest.raises(ProviderResponseError) as caught:
            await model.ainvoke([HumanMessage(content='Вопрос')])
    assert caught.value.response_type == 'str'
    assert caught.value.reason == 'unexpected_response_type'
    assert retryable_error(caught.value)
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('body', [None, [], 42, 'PRIVATE'])
def test_conversion_rejects_non_completion_types(model, body):
    from src.exceptions import ProviderResponseError
    with pytest.raises(ProviderResponseError) as caught:
        model._create_chat_result(body)
    assert caught.value.response_type == type(body).__name__


def test_conversion_rejects_malformed_choices(model):
    from src.exceptions import ProviderResponseError
    with pytest.raises(ProviderResponseError, match='invalid_model_choices'):
        model._create_chat_result({'choices': 'PRIVATE'})
