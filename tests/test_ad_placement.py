"""Placement assets retain proven creative media without inventing the shown variant."""

from unittest.mock import AsyncMock

import pytest

from src.exceptions import StoryMediaError
from src.services import ad_media, story_media
from tests.test_ad_media import CDN, graph as graph
from tests.test_inbound_business_context import pipeline as pipeline

PHOTO = 'https://scontent.cdninstagram.com/clicked.jpg?signature=PRIVATE'
FRAME = {'label': 'Кадр', 'url': 'data:image/jpeg;base64,/9j/AA=='}


def placement(graph, kind='VIDEO'):
    graph[0]['30']['asset_feed_spec'] = {
        'optimization_type': 'PLACEMENT',
        'videos' if kind == 'VIDEO' else 'images': [
            {'video_id': '7'} if kind == 'VIDEO' else {'hash': 'first'},
            {'video_id': '8'} if kind == 'VIDEO' else {'hash': 'second'}],
    }
    graph[0]['40']['media_type'] = kind


@pytest.mark.parametrize('kind', ['IMAGE', 'VIDEO'])
async def test_proven_placement_media_is_not_rejected_or_called_exact(graph, kind):
    placement(graph, kind)
    body = await ad_media.resolve_ad_media('10')
    assert body['id'] == '40' and body['media_url'] == CDN
    assert body['_ad_source'] == 'marketing_variant'
    assert [r.url.path for r in graph[1]] == ['/v26.0/10', '/v26.0/30', '/v25.0/40']


@pytest.mark.parametrize('feed', [
    {'videos': [{'video_id': '7'}, {'video_id': '8'}]},
    {'optimization_type': 'LANGUAGE'}, ['PLACEMENT'], 'PLACEMENT', [], 0, False,
])
async def test_unknown_feed_does_not_choose_an_asset(graph, feed):
    graph[0]['30']['asset_feed_spec'] = feed
    with pytest.raises(StoryMediaError, match='ad_variant_unavailable'):
        await ad_media.resolve_ad_media('10')
    assert len(graph[1]) == 2


@pytest.mark.parametrize('failure', ['account', 'creative', 'permalink', 'url'])
async def test_placement_keeps_original_identity_and_url_guards(graph, failure):
    placement(graph)
    if failure == 'account':
        graph[0]['10']['account_id'] = '666'
    elif failure == 'creative':
        graph[0]['30']['id'] = '666'
    elif failure == 'permalink':
        for key in ('40', '50'):
            graph[0][key]['permalink'] = 'https://www.instagram.com/p/Other/'
    else:
        for key in ('40', '50'):
            graph[0][key]['media_url'] = 'https://evil.example/video.mp4'
    with pytest.raises(StoryMediaError):
        await ad_media.resolve_ad_media('10')


async def test_placement_source_fallback_keeps_provenance(graph):
    placement(graph)
    graph[0]['40'] = {'error': {'code': 100, 'message': 'PRIVATE'}}
    result = await ad_media.resolve_ad_media('10')
    assert result['id'] == '50' and result['_ad_source'] == 'marketing_variant'


@pytest.mark.parametrize('kind', ['IMAGE', 'VIDEO'])
async def test_ad_expansion_keeps_context_permalink_missing_from_direct_creative(graph, kind):
    placement(graph, kind)
    graph[0]['10']['creative'] = dict(graph[0]['30'])
    graph[0]['30'].pop('instagram_permalink_url')
    result = await ad_media.resolve_ad_media('10')
    assert result['id'] == '40' and result['_ad_source'] == 'marketing_variant'
    assert [r.url.path for r in graph[1]] == ['/v26.0/10', '/v25.0/40']
    assert 'creative{id,effective_instagram_media_id' in graph[1][0].url.params['fields']


async def test_expanded_creative_without_permalink_is_not_filled_from_other_snapshot(graph):
    placement(graph)
    graph[0]['10']['creative'] = dict(graph[0]['30'])
    graph[0]['10']['creative'].pop('instagram_permalink_url')
    with pytest.raises(StoryMediaError, match='ad_unproved_creative'):
        await ad_media.resolve_ad_media('10')
    assert len(graph[1]) == 1


@pytest.mark.parametrize('kind,count', [('IMAGE', 1), ('VIDEO', 10)])
async def test_placement_and_clicked_photo_both_reach_existing_decoder(graph, monkeypatch, kind, count):
    placement(graph, kind)
    decode = AsyncMock(return_value=[dict(FRAME) for _ in range(count)])
    clicked = AsyncMock(return_value=story_media.StoryMedia(None, 'IMAGE', [dict(FRAME)]))
    monkeypatch.setattr(story_media, '_prepare_file', decode)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'urls': [PHOTO], 'types': ['image']}])
    assert result.ad_source == 'marketing_variant' and len(result.images) == count + 1
    decode.assert_awaited_once()
    assert decode.await_args.args[:2] == (kind, CDN)
    clicked.assert_awaited_once_with([PHOTO], image_types=['image'])
    assert 'креатива' in result.images[0]['label']
    assert 'самого отклика' in result.images[-1]['label']
    assert 'вариант не подтверждён' in result.caption
    assert all('PRIVATE' not in item['label'] for item in result.images)


async def test_unknown_feed_can_use_clicked_photo(graph, monkeypatch):
    graph[0]['30']['asset_feed_spec'] = {'optimization_type': 'OTHER'}
    clicked = AsyncMock(return_value=story_media.StoryMedia(None, 'IMAGE', [dict(FRAME)]))
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'urls': [PHOTO], 'types': ['image']}])
    assert result.ad_source == 'clicked_asset'
    clicked.assert_awaited_once()


@pytest.mark.parametrize('reason', ['download_unavailable', 'invalid_media_url', 'file_too_large'])
async def test_clicked_failure_keeps_availability_and_security_distinct(graph, monkeypatch, reason):
    placement(graph)
    monkeypatch.setattr(story_media, '_prepare_file', AsyncMock(return_value=[dict(FRAME)]))
    monkeypatch.setattr(story_media, 'prepare_images', AsyncMock(side_effect=StoryMediaError(reason)))
    parts = [{'kind': 'ad', 'id': '10', 'urls': [PHOTO], 'types': ['image']}]
    if reason == 'download_unavailable':
        result = await story_media.prepare_visual_parts(parts)
        assert len(result.images) == 1 and result.ad_source == 'marketing_variant'
    else:
        with pytest.raises(StoryMediaError, match=reason):
            await story_media.prepare_visual_parts(parts)


async def test_later_exact_ad_cannot_erase_variant_provenance(monkeypatch):
    first = story_media.StoryMedia(None, 'IMAGE', [dict(FRAME)], ad_source='marketing_variant')
    second = story_media.StoryMedia(None, 'IMAGE', [dict(FRAME)])
    monkeypatch.setattr(story_media, 'prepare_shared_media', AsyncMock(side_effect=[first, second]))
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10'}, {'kind': 'ad', 'id': '11'}])
    assert result.ad_source == 'marketing_variant'


@pytest.mark.parametrize('limit', ['frames', 'bytes'])
async def test_clicked_and_canonical_share_combined_limits(graph, monkeypatch, limit):
    placement(graph)
    frames = 100 if limit == 'frames' else 1
    monkeypatch.setattr(story_media, '_prepare_file', AsyncMock(return_value=[dict(FRAME) for _ in range(frames)]))
    monkeypatch.setattr(story_media, 'prepare_images', AsyncMock(return_value=
        story_media.StoryMedia(None, 'IMAGE', [dict(FRAME)])))
    if limit == 'bytes':
        monkeypatch.setattr(story_media, 'MAX_IMAGE_BYTES', 4)
    with pytest.raises(StoryMediaError, match='images_too_large'):
        await story_media.prepare_visual_parts([
            {'kind': 'ad', 'id': '10', 'urls': [PHOTO], 'types': ['image']}])
