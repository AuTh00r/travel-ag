from tests.model_responses import tool_response
from tests.model_responses import reply_json
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.exceptions import StoryMediaError
from src.services import story_media
from tests.test_inbound_business_context import pipeline as pipeline

CATALOG = '=== ТУР: Горнолыжный отдых на Эльбрусе ===\nСтоимость: 420 EUR\n\n=== ТУР: Варшава - Берлин - Познань ==='
PHOTO = 'https://scontent.cdninstagram.com/selected.jpg?secret=PRIVATE'


def original():
    return story_media.StoryMedia(None, 'VIDEO',
        [{'label': 'Кадр', 'url': 'data:image/jpeg;base64,/9j/AA=='}])


@pytest.mark.parametrize('question', ['Париж', 'Хочу в Париж', 'Программу ВДП'])
def test_short_catalog_destination_and_abbreviation(question):
    from src.ai.prompts import build_full_prompt
    catalog = '=== ТУР: Зимние каникулы в Париже ===\n\n=== ТУР: ВДП ==='
    prompt = build_full_prompt(catalog, '', [], question, ad_context='Отклик на рекламу')
    assert question in prompt[-1].content
    assert 'ВДП — Варшава–Дрезден–Прага' in prompt[0].content


@pytest.mark.parametrize('question', ['Программа?', 'Зимние каникулы', 'Можно подробнее?', 'Объявление ВДП'])
def test_ad_title_or_generic_words_are_not_catalog_identity(question):
    from src.ai.prompts import build_full_prompt
    prompt = build_full_prompt('=== ТУР: Зимние каникулы в Париже ===', '', [], question, ad_context='Отклик на рекламу')
    assert question in prompt[-1].content and 'не угадывай' in prompt[0].content.lower()


async def test_exact_original_precedes_bad_optional_preview(monkeypatch):
    shared = AsyncMock(return_value=original())
    clicked = AsyncMock(side_effect=StoryMediaError('invalid_media_url'))
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'urls': ['bad-preview'], 'types': ['image']}])
    shared.assert_awaited_once_with([{'ad_id': '10'}], abort=None)
    clicked.assert_not_awaited()
    assert result.images and result.ad_source == 'marketing'


async def test_normal_contact_handoff_survives_catalog_answer(pipeline, monkeypatch):
    monkeypatch.setattr(settings, 'ads_media_enabled', True)
    monkeypatch.setattr('src.services.tour_loader.get_tours_text', lambda: CATALOG)
    monkeypatch.setattr(story_media, 'prepare_shared_media', AsyncMock(side_effect=StoryMediaError('ad_graph_unavailable')))
    pipeline.invoke.return_value = tool_response(arguments=reply_json('Информация о туре.'), usage_metadata={})
    await pipeline.main.process_with_ai('context-client', 'Эльбрус\n+375251234567',
        referral={'source': 'ADS', 'ad_id': '10'})
    pipeline.invoke.assert_awaited_once()
    pipeline.notify.assert_awaited_once()
    assert pipeline.notify.await_args.kwargs['client_phone'] == '+375251234567'
