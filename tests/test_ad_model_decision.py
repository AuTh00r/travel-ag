from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.exceptions import StoryMediaError
from src.services import story_media
from tests.test_inbound_business_context import pipeline as pipeline


def response(outcome='answer', reply='Программа тура доступна по ссылке.', context='', manager=None):
    from tests.model_responses import model_response, manager_data
    return model_response(reply, manager_data(context) if outcome == 'handoff' else manager)


@pytest.fixture
def model(pipeline, monkeypatch):
    pipeline.invoke.side_effect = None
    monkeypatch.setattr(settings, 'ads_media_enabled', True)
    monkeypatch.setattr('src.services.llm.get_llm', lambda: SimpleNamespace(ainvoke=pipeline.invoke))
    monkeypatch.setattr('src.services.tour_loader.get_tours_text', lambda:
        '=== ТУР: Варшава - Дрезден - Прага ===\n=== ТУР: Варшава - Берлин - Познань ===')
    prepare = AsyncMock(side_effect=StoryMediaError('ad_graph_unavailable'))
    monkeypatch.setattr(story_media, 'prepare_visual_parts', prepare)
    pipeline.prepare = prepare
    pipeline.invoke.return_value = response()
    return pipeline


@pytest.mark.parametrize('question', [
    'Виза есть! Пришлите программу тура ВДП',
    'Здравствуйте. Есть ли у вас тур в Прагу в январе?',
    'Есть ли поездки в город, которого нет в вашем каталоге?',
    'Хочу познакомиться с вашим предложением',
    'Можно подробнее?',
])
async def test_model_answer_is_authoritative_without_catalog_word_gate(model, question):
    await model.main.process_with_ai('context-client', question,
        referral={'source': 'ADS', 'ad_id': '10'})
    model.invoke.assert_awaited_once()
    prompt = model.invoke.await_args.args[0]
    assert question in str(prompt[-1].content)
    assert 'Варшава' in prompt[0].content and 'Дрезден' in prompt[0].content
    assert '"manager"' in prompt[0].content and 'Молчаливая передача' in prompt[0].content
    model.send.assert_awaited_once_with('context-client', 'Программа тура доступна по ссылке.')
    model.notify.assert_not_awaited()
    assert not model.state.get('ad_dialog_context')


async def test_media_guard_blocks_bytes_but_not_ads_text_request_to_model(model):
    model.prepare.side_effect = StoryMediaError('ad_account_mismatch')
    await model.main.process_with_ai('context-client', 'ВДП', referral={'source': 'ADS', 'ad_id': '10'})
    model.invoke.assert_awaited_once()
    assert isinstance(model.invoke.await_args.args[0][-1].content, str)
    model.send.assert_awaited_once()


async def test_takeover_after_model_prevents_reply_and_notification(model):
    async def invoke(_):
        model.main._manager_pending['context-client'] = True
        return response('handoff', '', 'Менеджер нужен.')
    model.invoke.side_effect = invoke
    await model.main.process_with_ai('context-client', 'Подробнее', referral={'source': 'ADS', 'ad_id': '10'})
    model.invoke.assert_awaited_once()
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()


async def test_story_mention_keeps_silent_route_without_model(model):
    await model.main._dispatch_user_event({'kind': 'user_silent_handoff', 'silent_reason': 'story_mention',
                                         'sender_id': 'context-client', 'text': ''})
    model.invoke.assert_not_awaited()
    model.notify.assert_awaited_once()
