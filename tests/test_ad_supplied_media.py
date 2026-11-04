from unittest.mock import AsyncMock

import pytest

from src.exceptions import StoryMediaError
from src.services import story_media
from tests.test_inbound_business_context import pipeline as pipeline

URL = 'https://scontent.cdninstagram.com/clicked.mp4?secret=AD'


def media():
    return story_media.StoryMedia(None, 'VIDEO',
        [{'label': 'Кадр', 'url': 'data:image/jpeg;base64,/9j/AA=='}])


@pytest.mark.parametrize('kind', ['video', 'image'])
async def test_clicked_asset_follows_inaccessible_marketing(monkeypatch, kind):
    shared = AsyncMock(side_effect=StoryMediaError('ad_graph_unavailable'))
    clicked = AsyncMock(return_value=media())
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'urls': [URL], 'types': [kind]}])
    clicked.assert_awaited_once_with([URL], image_types=[kind])
    shared.assert_awaited_once_with([{'ad_id': '10'}], abort=None)
    assert result.images and result.ad_source == 'clicked_asset'


async def test_supplied_post_precedes_clicked_asset_and_marketing(monkeypatch):
    shared = AsyncMock(return_value=media())
    clicked = AsyncMock()
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    sources = [{'id': '179001', 'url': 'https://www.instagram.com/p/Exact/'}]
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'sources': sources, 'urls': [URL], 'types': ['video']}])
    shared.assert_awaited_once_with(sources, abort=None)
    clicked.assert_not_awaited()
    assert result.ad_source == 'referral_post'


async def test_exact_marketing_does_not_attempt_expired_clicked_asset(monkeypatch):
    clicked = AsyncMock(side_effect=StoryMediaError('download_unavailable'))
    shared = AsyncMock(return_value=media())
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'urls': [URL], 'types': ['video']}])
    clicked.assert_not_awaited()
    shared.assert_awaited_once_with([{'ad_id': '10'}], abort=None)
    assert result.ad_source == 'marketing'


@pytest.mark.parametrize('reason', ['invalid_media_url', 'file_too_large', 'incomplete_download', 'post_id_mismatch'])
async def test_terminal_guard_does_not_fall_back(monkeypatch, reason):
    clicked = AsyncMock(side_effect=StoryMediaError(reason))
    shared = AsyncMock(side_effect=StoryMediaError('ad_graph_unavailable'))
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    with pytest.raises(StoryMediaError, match=reason):
        await story_media.prepare_visual_parts([
            {'kind': 'ad', 'id': '10', 'urls': [URL], 'types': ['video']}])
    shared.assert_awaited_once_with([{'ad_id': '10'}], abort=None)


async def test_manager_takeover_after_marketing_failure_stops_clicked_fallback(monkeypatch):
    stopped = False
    async def marketing(*args, **kwargs):
        nonlocal stopped
        stopped = True
        raise StoryMediaError('ad_graph_unavailable')
    async def abort():
        return stopped
    clicked = AsyncMock()
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    monkeypatch.setattr(story_media, 'prepare_shared_media', marketing)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'urls': [URL], 'types': ['video']}], abort=abort)
    assert not result.images
    clicked.assert_not_awaited()


async def test_invalid_ad_identity_is_not_bypassed_by_clicked_asset(monkeypatch):
    clicked, shared = AsyncMock(), AsyncMock()
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    with pytest.raises(StoryMediaError, match='ad_invalid_identity'):
        await story_media.prepare_visual_parts([
            {'kind': 'ad', 'id': 'invalid', 'urls': [URL], 'types': ['video']}])
    clicked.assert_not_awaited()
    shared.assert_not_awaited()


async def test_all_supplied_sources_unavailable_use_marketing_once(monkeypatch):
    sources = [{'id': '179001'}]
    shared = AsyncMock(side_effect=[StoryMediaError('post_unavailable'), media()])
    clicked = AsyncMock(side_effect=StoryMediaError('download_unavailable'))
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    result = await story_media.prepare_visual_parts([
        {'kind': 'ad', 'id': '10', 'sources': sources, 'urls': [URL], 'types': ['video']}])
    assert [call.args[0] for call in shared.await_args_list] == [sources, [{'ad_id': '10'}]]
    clicked.assert_not_awaited()
    assert result.ad_source == 'marketing'


@pytest.mark.parametrize('reason', ['post_id_mismatch', 'incomplete_carousel'])
async def test_supplied_post_guard_stops_all_alternatives(monkeypatch, reason):
    shared = AsyncMock(side_effect=StoryMediaError(reason))
    clicked = AsyncMock()
    monkeypatch.setattr(story_media, 'prepare_shared_media', shared)
    monkeypatch.setattr(story_media, 'prepare_images', clicked)
    with pytest.raises(StoryMediaError, match=reason):
        await story_media.prepare_visual_parts([
            {'kind': 'ad', 'id': '10', 'sources': [{'id': '179001'}], 'urls': [URL], 'types': ['video']}])
    shared.assert_awaited_once_with([{'id': '179001'}], abort=None)
    clicked.assert_not_awaited()
