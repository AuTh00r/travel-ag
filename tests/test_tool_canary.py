"""Canary routing is independent of inbound recovery and denied by default."""
import pytest
from datetime import date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.config import Settings
from src.services import llm
from src.services.llm import tool_enabled_for as actual_tool_enabled_for
from tests.test_unified_model_response import unified as unified
from tests.model_responses import model_response, reply_json, tool_response


def test_canary_is_off_by_default():
    settings = Settings(_env_file=None, deepseek_tool_client_ids='')
    assert settings.tool_clients() == ()
    assert settings.deepseek_tool_scope == 'allowlist'


def test_all_scope_is_independent_and_includes_new_clients(monkeypatch):
    monkeypatch.setattr(llm.settings, 'deepseek_tool_scope', 'all')
    monkeypatch.setattr(llm.settings, 'deepseek_tool_client_ids', '')
    monkeypatch.setattr(llm.settings, 'inbound_recovery_scope', 'allowlist')
    for client in ['123456', '654321', 'new-client']:
        assert actual_tool_enabled_for(client) is True
    for client in [None, '', 123456]:
        assert actual_tool_enabled_for(client) is False


def test_unknown_tool_scope_fails_configuration():
    with pytest.raises(ValueError):
        Settings(_env_file=None, deepseek_tool_scope='everything')


async def test_all_scope_routes_foreign_clients_and_reports_health(unified, monkeypatch):
    monkeypatch.setattr(llm, 'tool_enabled_for', actual_tool_enabled_for)
    monkeypatch.setattr(llm.settings, 'deepseek_tool_scope', 'all')
    monkeypatch.setattr(llm.settings, 'deepseek_tool_client_ids', '123456')
    legacy = AsyncMock()
    monkeypatch.setattr(llm, 'get_legacy_llm', legacy)
    await unified.main.process_with_ai('654321', 'Эльбрус')
    unified.invoke.assert_awaited_once()
    legacy.assert_not_called()
    assert 'PREPARE_RESPONSE' in unified.invoke.call_args.args[0][0].content
    assert (await unified.main.health())['model_tools'] == {'enabled': True, 'scope': 'all'}


@pytest.mark.parametrize('value', ['abc', '123,', ',123', '１２３', '1.0', '123;456'])
def test_invalid_allowlist_rejected(value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, deepseek_tool_client_ids=value)


def test_canary_does_not_follow_recovery_scope(monkeypatch):
    monkeypatch.setattr(llm.settings, 'deepseek_tool_client_ids', '123456')
    monkeypatch.setattr(llm.settings, 'inbound_recovery_scope', 'all')
    assert actual_tool_enabled_for('123456') is True
    assert actual_tool_enabled_for('654321') is False
    assert actual_tool_enabled_for(None) is False


def test_installed_legacy_prompts_and_retries_remain_exact():
    # Approved date-availability wording; inverse proof preserves all other prompt/transport bytes.
    from src.ai.prompts import build_full_prompt, format_retry_messages
    golden = json.loads((Path(__file__).parent / 'fixtures/tool_canary_legacy.json').read_text())
    def digest(messages):
        return hashlib.sha256(json.dumps([m.model_dump() for m in messages], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    for row in golden:
        images = [{'label': str(i), 'url': 'data:image/jpeg;base64,AA=='} for i in range(row['frames'])] or None
        messages = build_full_prompt('Проверенный каталог: Эльбрус', '',
            [{'role': 'user', 'content': 'Привет'}, {'role': 'assistant', 'content': 'Здравствуйте!'}],
            'Эльбрус', row['count'], current_date=date(2026, 10, 18), current_time='12:34',
            should_greet=False, is_first_message=False, media_images=images, media_kind='image',
            ad_context='Источник ADS' if row['ad'] else '', use_tools=False)
        assert digest(messages) == row['prompt_sha']
        assert digest(format_retry_messages(messages, 'invalid_fields', use_tools=False)) == row['retry_sha']


@pytest.mark.parametrize('image', [False, True])
async def test_actual_gate_keeps_mixed_clients_on_own_transport(unified, monkeypatch, image):
    import asyncio
    monkeypatch.setattr(llm, 'tool_enabled_for', actual_tool_enabled_for)
    monkeypatch.setattr(llm.settings, 'deepseek_tool_client_ids', '123456')
    tool = AsyncMock(return_value=model_response('Тестовый ответ.'))
    legacy = AsyncMock(return_value=SimpleNamespace(content=reply_json('Прежний ответ.'), usage_metadata={}))
    monkeypatch.setattr(llm, 'get_llm', lambda: SimpleNamespace(ainvoke=tool))
    monkeypatch.setattr(llm, 'get_vision_llm', lambda: SimpleNamespace(ainvoke=tool))
    monkeypatch.setattr(llm, 'get_legacy_llm', lambda: SimpleNamespace(ainvoke=legacy))
    monkeypatch.setattr(llm, 'get_legacy_vision_llm', lambda: SimpleNamespace(ainvoke=legacy))
    kwargs = {}
    if image:
        from src.services.story_media import StoryMedia
        monkeypatch.setattr(llm.settings, 'image_media_enabled', True)
        monkeypatch.setattr('src.services.story_media.prepare_images', AsyncMock(return_value=
            StoryMedia(None, 'IMAGE', [{'label': 'Фото', 'url': 'data:image/jpeg;base64,AA=='}])))
        kwargs['image_urls'] = ['https://scontent.cdninstagram.com/proof.jpg']
    await asyncio.gather(unified.main.process_with_ai('123456', 'Эльбрус', **kwargs),
                         unified.main.process_with_ai('654321', 'Эльбрус', **kwargs))
    tool.assert_awaited_once()
    legacy.assert_awaited_once()
    assert 'PREPARE_RESPONSE' in tool.call_args.args[0][0].content
    assert 'ЕДИНЫЙ ФОРМАТ ОТВЕТА — JSON' in legacy.call_args.args[0][0].content
    assert 'PREPARE_RESPONSE' not in legacy.call_args.args[0][0].content
    sends = {c.args[0]: c.args[1] for c in unified.send.call_args_list}
    assert 'Тестовый ответ.' in sends['123456'] and 'Прежний ответ.' in sends['654321']


async def test_canary_retry_freezes_client_lane(unified, monkeypatch):
    monkeypatch.setattr(llm, 'tool_enabled_for', actual_tool_enabled_for)
    monkeypatch.setattr(llm.settings, 'deepseek_tool_client_ids', '123456')
    tool = AsyncMock(side_effect=[tool_response('{"reply":"bad"}'), model_response('Исправлено.')])
    async def invoke(messages):
        # A configuration mutation must not change this request's second attempt.
        monkeypatch.setattr(llm.settings, 'deepseek_tool_client_ids', '')
        return await tool(messages)
    monkeypatch.setattr(llm, 'get_llm', lambda: SimpleNamespace(ainvoke=invoke))
    legacy = AsyncMock()
    monkeypatch.setattr(llm, 'get_legacy_llm', legacy)
    await unified.main.process_with_ai('123456', 'Эльбрус')
    assert tool.await_count == 2 and 'PREPARE_RESPONSE' in tool.call_args.args[0][0].content
    legacy.assert_not_called()


def test_legacy_factories_keep_installed_request_settings(monkeypatch):
    from langchain_core.messages import HumanMessage
    monkeypatch.setattr(llm.settings, 'deepseek_api_key', 'not-real')
    text, vision = llm.get_legacy_llm(), llm.get_legacy_vision_llm()
    for model in (text, vision):
        payload = model._get_request_payload([HumanMessage(content='Вопрос')])
        assert payload['response_format'] == {'type': 'json_object'}
        assert 'tools' not in payload and str(model.root_async_client.base_url) == 'https://api.deepseek.com'
    assert text.root_async_client.max_retries == 0
    assert vision.root_async_client.max_retries == 0
    assert vision._get_request_payload([HumanMessage(content='Вопрос')])['extra_body'] == {'thinking': {'type': 'disabled'}, 'max_tokens': 2048}
