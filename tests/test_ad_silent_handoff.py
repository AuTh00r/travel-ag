from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.exceptions import StoryMediaError
from src.services import story_media
from tests.test_ad_source_recovery import CATALOG, original
from tests.test_inbound_business_context import pipeline as pipeline, raw


@pytest.fixture
def ads(pipeline, monkeypatch):
    monkeypatch.setattr(settings, 'ads_media_enabled', True)
    monkeypatch.setattr('src.services.tour_loader.get_tours_text', lambda: CATALOG)
    prepare = AsyncMock(return_value=original())
    monkeypatch.setattr(story_media, 'prepare_visual_parts', prepare)
    return SimpleNamespace(**vars(pipeline), prepare=prepare)


@pytest.mark.parametrize('question', ['Эльбрус', 'Пришлите программу Варшава-Берлин-Познань',
    'Визы нет. Пришлите варианты туров с ее открытием.', 'Какие туры у вас есть?'])
async def test_independent_customer_question_keeps_normal_answer(ads, question):
    ads.prepare.side_effect = StoryMediaError('ad_graph_unavailable')
    await ads.main.process_with_ai('context-client', question,
        referral={'source': 'ADS', 'ad_id': '10', 'ad_title': 'Другой рекламный заголовок'})
    ads.invoke.assert_awaited_once()
    ads.send.assert_awaited_once()
    ads.notify.assert_not_awaited()


@pytest.mark.parametrize('case', ['same', 'other_ad', 'stale', 'unrelated_turn', 'title_only'])
async def test_legacy_same_ad_context_never_gates_model(ads, case):
    ads.state['history'] = [
        {'role': 'user', 'content': 'Эльбрус\n[Отклик на рекламу: Скрытый заголовок]'},
        {'role': 'assistant', 'content': 'Тур на Эльбрус.'}]
    ads.state['ad_dialog_context'] = {'ad_id': '10', 'known': True,
        'at': datetime.now(timezone.utc).isoformat()}
    if case == 'other_ad':
        ads.state['ad_dialog_context']['ad_id'] = '11'
    elif case == 'stale':
        ads.state['ad_dialog_context']['at'] = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
    elif case == 'unrelated_turn':
        ads.state['history'].append({'role': 'user', 'content': 'Хотим предложить сотрудничество'})
    elif case == 'title_only':
        ads.state['history'][0]['content'] = 'Подробнее\n[Отклик на рекламу: Эльбрус]'
        ads.state.pop('ad_dialog_context')
    ads.prepare.side_effect = StoryMediaError('ad_graph_unavailable')
    await ads.main.process_with_ai('context-client', 'Сколько стоит?',
        referral={'source': 'ADS', 'ad_id': '10'})
    ads.invoke.assert_awaited_once()
    ads.send.assert_awaited_once()
    ads.notify.assert_not_awaited()
    assert not ads.state.get('ad_dialog_context')


async def test_ad_answer_no_longer_creates_local_clarity_state(ads):
    ads.prepare.side_effect = StoryMediaError('ad_graph_unavailable')
    await ads.main.process_with_ai('context-client', 'Эльбрус', referral={'source': 'ADS', 'ad_id': '10'})
    assert not ads.state.get('ad_dialog_context')
    assert '10' not in str(ads.state['history'])
    await ads.main.process_with_ai('context-client', 'Хочу предложить сотрудничество')
    assert not ads.state.get('ad_dialog_context')


async def test_standalone_ad_without_mid_has_stable_dedup_receipt():
    data = raw(referral={'source': 'ADS', 'ad_id': '10'})
    message = data['entry'][0]['messaging'][0]
    message['message'].pop('mid')
    message['timestamp'] = 1780012345678
    channel = InstagramChannel()
    events = await channel.receive_message(data)
    assert len(events) == 1 and events[0]['mid']
    assert await channel.receive_message(data, processed_mids={events[0]['mid']}) == []
