"""Full handler and recovery with the real SDK and a local HTTP transport."""
from contextlib import asynccontextmanager
from copy import deepcopy
import json
from unittest.mock import AsyncMock

import httpx
import openai
import pytest

from src.config import settings
from src.exceptions import InstagramRateLimitError
from src.services import llm
from src.services.story_media import StoryMedia
from tests.model_responses import reply_json, manager_data
from tests.test_model_tools import wire
from tests.test_unified_model_response import unified as unified
from tests.test_recovery_pipeline import pipeline as pipeline


@asynccontextmanager
async def sdk(monkeypatch, bodies, before_response=None, timeouts=None):
    requests = []
    async def handle(request):
        requests.append(json.loads(request.content))
        if timeouts is not None:
            timeouts.append(request.extensions['timeout']['read'])
        if before_response:
            before_response()
        body = bodies[len(requests) - 1]
        return body if isinstance(body, httpx.Response) else httpx.Response(200, json=deepcopy(body))
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        model = llm._model(settings.deepseek_model)
        root = openai.AsyncOpenAI(api_key='proof-not-secret', base_url='https://api.deepseek.com/beta',
                                  http_client=client, max_retries=0, timeout=model.request_timeout)
        model.root_async_client, model.async_client = root, root.chat.completions
        monkeypatch.setattr(llm, 'get_llm', lambda: model)
        monkeypatch.setattr(llm, 'get_vision_llm', lambda: model)
        yield requests


async def test_sdk_three_calls_have_real_transport_timeouts_and_no_hidden_retries(unified, monkeypatch):
    timeouts = []
    bodies = [wire('not json'), wire('not json'), wire(reply_json('Готовый ответ.'))]
    async with sdk(monkeypatch, bodies, timeouts=timeouts) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус')
    assert len(requests) == 3 and timeouts == [120, 120, 240]
    unified.send.assert_awaited_once()
    unified.notify.assert_not_awaited()


@pytest.mark.parametrize('status', [401, 403, 408, 409, 429, 500, 503])
async def test_sdk_http_status_retries_only_recoverable_errors(unified, monkeypatch, status):
    retryable = status in {408, 409, 429, 500, 503}
    bodies = [httpx.Response(status, json={'error': {'message': 'PRIVATE_API_BODY'}}),
              wire(reply_json('Готовый ответ.'))]
    async with sdk(monkeypatch, bodies) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус')
    assert len(requests) == (2 if retryable else 1)
    assert unified.send.await_count == int(retryable)
    assert unified.notify.await_count == int(not retryable)
    if not retryable:
        context = unified.notify.await_args.kwargs['context']
        assert f'HTTP {status}' in context and 'PRIVATE_API_BODY' not in context


@pytest.mark.parametrize('route', ['text', 'ad', 'photo', 'video10', 'voice'])
async def test_real_sdk_through_handler_all_routes(unified, monkeypatch, route):
    kwargs, images = {}, []
    if route == 'ad':
        kwargs['referral'] = {'source': 'ADS'}
    if route in {'photo', 'video10'}:
        monkeypatch.setattr(settings, 'image_media_enabled', True)
        images = [{'label': str(i), 'url': 'data:image/jpeg;base64,' + str(i)}
                  for i in range(10 if route == 'video10' else 1)]
        monkeypatch.setattr('src.services.story_media.prepare_images', AsyncMock(return_value=
            StoryMedia(None, 'VIDEO' if route == 'video10' else 'IMAGE', images)))
        kwargs['image_urls'] = ['https://scontent.cdninstagram.com/proof']
    if route == 'voice':
        monkeypatch.setattr('src.services.voice_media.transcribe_voice', AsyncMock(return_value=['Вопрос по Эльбрусу']))
        kwargs['voice_parts'] = [{'audio': {'url': 'https://scontent.cdninstagram.com/proof.mp4'}}]
    async with sdk(monkeypatch, [wire(reply_json('Ответ по Эльбрусу.'))]) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус', **kwargs)
    assert len(requests) == 1 and requests[0]['max_tokens'] == 2048
    assert requests[0]['tool_choice']['function']['name'] == 'prepare_response'
    assert 'response_format' not in requests[0]
    if images:
        sent = [b['image_url'] for b in requests[0]['messages'][-1]['content'] if b['type'] == 'image_url']
        assert sent == [{'url': i['url'], 'detail': 'original'} for i in images]
    assert 'Ответ по Эльбрусу.' in str(unified.send.call_args_list)
    assert 'raw_tool_message' not in str(unified.state['history'])
    unified.notify.assert_not_awaited()


async def test_sdk_duplicate_arguments_retry_does_not_apply_first_reply(unified, monkeypatch):
    async with sdk(monkeypatch, [wire('{"reply":"PRIVATE","reply":"LEAK","manager":null}'),
                                 wire(reply_json('Исправленный ответ.'))]) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус')
    assert len(requests) == 2
    assert requests[0]['messages'][1:] == requests[1]['messages'][1:]
    assert 'PRIVATE' not in str(requests[1])
    assert [c.kwargs['validation_reason'] for c in unified.journal.call_args_list] == ['duplicate_fields', 'valid']
    assert 'LEAK' not in str(unified.send.call_args_list)
    unified.notify.assert_not_awaited()


@pytest.mark.parametrize('limit', [False, True])
async def test_sdk_contact_and_limit_use_program_outcome(unified, monkeypatch, limit):
    unified.state.update(history=[{'role': 'user', 'content': 'Старый номер +375291112233'}],
                         escalation_count=3 if limit else 0)
    body = wire(reply_json('Учту контакт.', manager_data('Клиент просит связаться по новому номеру.', 'контакт')))
    async with sdk(monkeypatch, [body]) as requests:
        await unified.main.process_with_ai('proof-client', '+375294445566')
    assert len(requests) == 1
    assert unified.notify.await_count == int(not limit)
    visible = ''.join(c.args[1] for c in unified.send.call_args_list)
    assert ('лимит' in visible) if limit else ('передал ваш номер менеджерам' in visible)
    if not limit:
        assert unified.notify.call_args.kwargs['client_phone'] == '+375294445566'
        assert '1112233' not in unified.notify.call_args.kwargs['context']


async def test_sdk_takeover_after_response_cancels_all_effects(unified, monkeypatch):
    def takeover():
        unified.main._manager_pending['proof-client'] = True
    async with sdk(monkeypatch, [wire()], takeover) as requests:
        await unified.main.process_with_ai('proof-client', 'Эльбрус')
    assert len(requests) == 1 and unified.state['history'] == []
    unified.send.assert_not_awaited()
    unified.notify.assert_not_awaited()


async def test_sdk_invalid_silent_reply_uses_technical_silent_handoff(unified, monkeypatch):
    body = wire(reply_json('', manager_data('Недоступно объявление, нужен контекст.')))
    async with sdk(monkeypatch, [body, body, body]) as requests:
        await unified.main.process_with_ai('proof-client', 'Можно подробнее?', referral={'source': 'ADS'})
    assert len(requests) == 3
    unified.send.assert_not_awaited()
    unified.notify.assert_awaited_once()


@pytest.mark.parametrize('unknown', [False, True])
async def test_sdk_recovery_keeps_generated_reply_and_partial_receipts(pipeline, monkeypatch, unknown):
    body = wire(reply_json('Описание тура. ' * 100))
    failure = httpx.ReadTimeout('uncertain') if unknown else InstagramRateLimitError('limit', retry_after_seconds=60)
    pipeline.send.side_effect = ['part-one', failure, 'part-two']
    job = pipeline.job()
    async with sdk(monkeypatch, [body]) as requests:
        await pipeline.recovery.process(job)
        deliveries = pipeline.store.deliveries(job['id'])
        assert [d['state'] for d in deliveries] == ['sent', 'unknown' if unknown else 'retry_wait']
        assert deliveries[0]['receipt'] == 'part-one'
        pipeline.store.recover(startup=True)
        pipeline.now[0] += 60
        await pipeline.recovery.deliver(pipeline.store.get_job(job['id']))
    assert len(requests) == 1
    assert pipeline.send.await_count == (2 if unknown else 3)
    assert pipeline.store.get_job(job['id'])['state'] == ('unknown' if unknown else 'done')
    assert 'raw_tool_message' not in str(pipeline.store.read_session('pipeline-client')[0])
