from unittest.mock import AsyncMock

import httpx
import pytest

from src.config import settings
from src.exceptions import StoryMediaError
from src.services import ad_media
from tests.test_inbound_business_context import pipeline as pipeline

PERMALINK = 'https://www.instagram.com/p/ExactAd/'
CDN = 'https://scontent.cdninstagram.com/ad.mp4?signature=PRIVATE'


@pytest.fixture
def graph(monkeypatch, tmp_path):
    # OpenAI subclasses httpx.AsyncClient at import; load before replacing it.
    __import__('src.services.llm')
    token = tmp_path / 'ads.token'
    token.write_text('TEST_ADS_TOKEN_1234567890', encoding='utf-8')
    monkeypatch.setattr(settings, 'ads_media_enabled', True)
    monkeypatch.setattr(settings, 'instagram_ads_token_file', str(token))
    monkeypatch.setattr(settings, 'instagram_ads_account_id', '20')
    monkeypatch.setattr(settings, 'instagram_access_token', 'TEST_PAGE_TOKEN')
    replies = {
        '10': {'id': '10', 'account_id': '20', 'creative': {'id': '30'}},
        '30': {'id': '30', 'effective_instagram_media_id': '40', 'source_instagram_media_id': '50',
               'instagram_permalink_url': PERMALINK},
        '40': {'id': '40', 'media_type': 'VIDEO', 'media_url': CDN, 'permalink': PERMALINK, 'caption': 'Прага'},
        '50': {'id': '50', 'media_type': 'VIDEO', 'media_url': CDN, 'permalink': PERMALINK},
        'me/permissions': {'data': [{'permission': 'ads_read', 'status': 'granted'},
                                    {'permission': 'public_profile', 'status': 'granted'}]},
        'act_20': {'id': 'act_20', 'account_id': '20'},
    }
    requests = []
    original = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        assert request.url.host == 'graph.facebook.com' and request.method == 'GET'
        marketing = request.url.path.startswith('/v26.0/')
        assert request.headers['authorization'] == ('Bearer TEST_ADS_TOKEN_1234567890' if marketing else 'Bearer TEST_PAGE_TOKEN')
        key = request.url.path.split('/', 2)[2]
        body = replies[key]
        return httpx.Response(400 if 'error' in body else 200, json=body)

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    return replies, requests


async def test_exact_ad_resolves_effective_media_with_separate_tokens(graph):
    body = await ad_media.resolve_ad_media('10')
    assert body['id'] == '40' and body['permalink'] == PERMALINK and body['media_url'] == CDN
    assert [r.url.path for r in graph[1]] == ['/v26.0/10', '/v26.0/30', '/v25.0/40']
    assert all('access_token' not in r.url.params for r in graph[1])


@pytest.mark.parametrize('failure', ['different_permalink', 'inaccessible'])
async def test_source_fallback_requires_exact_creative_permalink(graph, failure):
    if failure == 'different_permalink':
        graph[0]['40']['permalink'] = 'https://www.instagram.com/p/OtherPost/'
    else:
        graph[0]['40'] = {'error': {'code': 100, 'message': 'SECRET'}}
    assert (await ad_media.resolve_ad_media('10'))['id'] == '50'
    assert graph[1][-1].url.path == '/v25.0/50'


@pytest.mark.parametrize('failure', ['account', 'ad_id', 'creative_id', 'permalink', 'dynamic', 'missing_video', 'all_mismatch', 'expired'])
async def test_unproved_or_inaccessible_media_fails_closed_without_secret(graph, failure):
    replies, requests = graph
    if failure == 'account':
        replies['10']['account_id'] = '666'
    elif failure == 'ad_id':
        replies['10']['id'] = '666'
    elif failure == 'creative_id':
        replies['30']['id'] = '666'
    elif failure == 'permalink':
        replies['30']['instagram_permalink_url'] = 'https://evil.example/private'
    elif failure == 'dynamic':
        replies['30']['asset_feed_spec'] = {'videos': [{'video_id': '7'}, {'video_id': '8'}]}
    elif failure == 'missing_video':
        for key in ('40', '50'):
            replies[key].pop('media_url')
            replies[key]['thumbnail_url'] = CDN
    elif failure == 'all_mismatch':
        for key in ('40', '50'):
            replies[key]['permalink'] = 'https://www.instagram.com/p/OtherPost/'
    else:
        replies['10'] = {'error': {'code': 190, 'message': CDN + ' TEST_ADS_TOKEN_1234567890'}}
    with pytest.raises(StoryMediaError) as exc:
        await ad_media.resolve_ad_media('10')
    assert 'SECRET' not in str(exc.value) and 'PRIVATE' not in str(exc.value) and 'TOKEN' not in str(exc.value)
    if failure in ('account', 'ad_id', 'expired'):
        assert len(requests) == 1
    assert not any(r.url.path.endswith('/media') for r in requests)


async def test_disabled_or_invalid_identity_never_calls_graph(graph, monkeypatch):
    monkeypatch.setattr(settings, 'ads_media_enabled', False)
    with pytest.raises(StoryMediaError):
        await ad_media.resolve_ad_media('10')
    monkeypatch.setattr(settings, 'ads_media_enabled', True)
    with pytest.raises(StoryMediaError):
        await ad_media.resolve_ad_media('https://evil.example/')
    assert not graph[1]


async def test_access_health_checks_granted_scope_and_exact_account(graph):
    assert await ad_media.check_ad_access() == {'enabled': True, 'ready': True}
    graph[0]['me/permissions']['data'] = []
    with pytest.raises(StoryMediaError, match='ad_scope_missing'):
        await ad_media.check_ad_access()


@pytest.mark.parametrize('account', ['20', '21', '22'])
async def test_only_explicit_multiple_accounts_resolve_exact_ad(graph, monkeypatch, account):
    monkeypatch.setattr(settings, 'instagram_ads_account_ids', '21,22,21', raising=False)
    graph[0]['10']['account_id'] = account
    assert (await ad_media.resolve_ad_media('10'))['id'] == '40'
    graph[0]['10']['account_id'] = '666'
    graph[1].clear()
    with pytest.raises(StoryMediaError, match='ad_account_mismatch'):
        await ad_media.resolve_ad_media('10')
    assert len(graph[1]) == 1


async def test_multiaccount_health_checks_each_member_once(graph, monkeypatch):
    monkeypatch.setattr(settings, 'instagram_ads_account_ids', ' 21 , 22 ,21 ', raising=False)
    graph[0].update({'act_21': {'id':'act_21', 'account_id':'21'},
                     'act_22': {'id':'act_22', 'account_id':'22'}})
    assert await ad_media.check_ad_access() == {'enabled':True,'ready':True}
    assert [request.url.path for request in graph[1]] == [
        '/v26.0/me/permissions', '/v26.0/act_20', '/v26.0/act_21', '/v26.0/act_22']
    graph[0]['act_22'] = {'error':{'code':100,'message':'PRIVATE SECRET'}}
    with pytest.raises(StoryMediaError, match='ad_graph_unavailable'):
        await ad_media.check_ad_access()


@pytest.mark.parametrize('value', ['21,,22', 'act_21', '２１', ',21', '21,',
    ','.join(str(i) for i in range(11)), '1' * 1025])
async def test_malformed_account_allowlist_never_calls_graph(graph, monkeypatch, value):
    monkeypatch.setattr(settings, 'instagram_ads_account_ids', value, raising=False)
    with pytest.raises(StoryMediaError, match='ad_not_configured'):
        await ad_media.resolve_ad_media('10')
    assert not graph[1]


async def test_multiple_accounts_can_be_configured_without_legacy_id(graph, monkeypatch):
    monkeypatch.setattr(settings, 'instagram_ads_account_id', '')
    monkeypatch.setattr(settings, 'instagram_ads_account_ids', '20', raising=False)
    assert (await ad_media.resolve_ad_media('10'))['id'] == '40'


async def test_ad_part_reuses_shared_decoder_without_published_media_search(graph, monkeypatch):
    from src.services import story_media
    prepare = AsyncMock(return_value=[{'label': f'Кадр {i}', 'url': 'data:image/jpeg;base64,/9j/AA=='} for i in range(10)])
    monkeypatch.setattr(story_media, '_prepare_file', prepare)
    result = await story_media.prepare_visual_parts([{'kind': 'ad', 'id': '10'}])
    assert len(result.images) == 10 and 'Прага' in result.caption
    assert all('Реклама' in frame['label'] for frame in result.images)
    prepare.assert_awaited_once()
    assert prepare.await_args.args[:2] == ('VIDEO', CDN)


async def test_ad_does_not_silently_drop_eleven_part_batch(graph, pipeline):
    parts = [{'kind': 'images', 'urls': [CDN]}] * 10
    from src.services import story_media
    with pytest.raises(StoryMediaError, match='invalid_image_count'):
        await story_media.prepare_visual_parts(parts + [{'kind': 'ad', 'id': '10'}])
    assert not graph[1]
