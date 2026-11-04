"""ADS context is deliberately discarded at every entry point."""
import json
from unittest.mock import AsyncMock

import pytest

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.services import story_media
from tests.test_inbound_business_context import pipeline as pipeline
from tests import test_recovery_pipeline

recovery_pipeline = test_recovery_pipeline.pipeline

AD = {'source': 'ADS', 'ad_id': '12345', 'ad_title': 'SECRET_AD_TITLE',
      'photo_url': 'https://scontent.cdninstagram.com/ad.jpg?secret=AD',
      'permalink': 'https://www.instagram.com/p/SECRET_AD_LINK/'}


@pytest.mark.parametrize('attachment', ['image', 'video', 'audio', 'share', 'file', 'product', 'template'])
async def test_parser_uses_only_original_text_before_any_ad_attachment_logic(attachment):
    event = InstagramChannel().parse_message_payload({'entry': [{'messaging': [{
        'sender': {'id': 'client'}, 'message': {'mid': 'mid', 'text': 'Эльбрус',
            'referral': AD, 'attachments': [{'type': attachment, 'payload': {'url': AD['photo_url']}}],
            'reply_to': {'story': {'id': '777'}}}, 'timestamp': 1000}]}]}, merge=False)[0]
    assert event['kind'] == 'user' and event['text'] == 'Эльбрус'
    assert event['_ad_text_only'] and event['mid'] == 'mid'
    assert not any(key in event for key in ('story', 'images', 'voice_parts', 'non_text', 'shared_sources', 'referral'))


@pytest.mark.parametrize('text', ['', '   '])
async def test_empty_ad_is_ignored_without_synthetic_question(text):
    event = InstagramChannel().parse_message_payload({'entry': [{'messaging': [{
        'sender': {'id': 'client'}, 'message': {'mid': 'mid', 'text': text}, 'referral': AD}]}]}, merge=False)[0]
    assert event['kind'] == 'ignored' and not event['text'].strip()


async def test_direct_ai_call_cannot_reintroduce_ad_context_or_media(pipeline, monkeypatch):
    for name in ('ads_media_enabled', 'shared_media_enabled', 'image_media_enabled', 'story_media_enabled', 'voice_media_enabled'):
        monkeypatch.setattr(settings, name, True)
    prepare = AsyncMock(side_effect=AssertionError('ADS media must not be read'))
    for name in ('prepare_images', 'prepare_shared_media', 'prepare_story_media', 'prepare_visual_parts'):
        monkeypatch.setattr(story_media, name, prepare)
    await pipeline.main.process_with_ai('context-client', 'Эльбрус', referral=AD,
        story={'id': '777'}, image_urls=[AD['photo_url']], shared_sources=[{'url': AD['permalink']}])
    prepare.assert_not_awaited()
    pipeline.invoke.assert_awaited_once()
    prompt = pipeline.invoke.await_args.args[0]
    assert prompt[-1].content == 'Эльбрус'
    assert 'SECRET_AD' not in str(prompt) + str(pipeline.state['history'])
    pipeline.notify.assert_not_awaited()


async def test_old_dispatch_empty_ad_has_deliberate_ignored_outcome(recovery_pipeline):
    p = recovery_pipeline
    job = p.job('placeholder')
    payload = json.loads(job['payload'])
    payload.update(text='', referral=AD, kind='user_silent_handoff', silent_reason='ad_referral',
                   _context_incomplete=True)
    with p.store.connection() as conn:
        conn.execute('UPDATE inbound_jobs SET payload=? WHERE id=?', (json.dumps(payload), job['id']))
    job['payload'] = json.dumps(payload)
    await p.recovery.process(job)
    row = p.store.get_job(job['id'])
    assert row['state'] == 'done' and json.loads(row['result'])['outcome'] == 'ignored', (row['reason'], row['result'])
    p.invoke.assert_not_awaited()
    p.notify.assert_not_awaited()


async def test_old_recovery_ad_context_incomplete_is_ordinary_text(recovery_pipeline):
    p = recovery_pipeline
    job = p.job('Эльбрус', referral=AD, _context_incomplete=True,
        story={'id': '777'}, _story_hint=True)
    await p.recovery.process(job)
    p.invoke.assert_awaited_once()
    prompt = p.invoke.await_args.args[0]
    assert prompt[-1].content == 'Эльбрус'
    assert 'SECRET_AD' not in str(prompt)
    assert 'Контекст источника неполный' not in str(prompt)
    assert p.store.get_job(job['id'])['state'] == 'done'


async def test_ad_text_does_not_contaminate_adjacent_customer_photo(monkeypatch):
    monkeypatch.setattr(settings, 'image_media_enabled', True)
    events = [
        {'kind': 'user', 'sender_id': 'client', 'mid': 'ad', 'text': 'Эльбрус', 'referral': AD},
        {'kind': 'user_non_text', 'sender_id': 'client', 'mid': 'photo', 'text': '',
         'images': ['https://scontent.cdninstagram.com/customer.jpg'], 'image_types': ['image'],
         'non_text': {'types': ['image'], 'text': '', 'has_text': False}}]
    merged = InstagramChannel.merge_events(events)
    assert len(merged) == 1
    assert 'Эльбрус' in merged[0]['text'] and merged[0]['images'] == events[1]['images']
    assert not merged[0].get('referral')
    assert merged[0]['_ad_text_only']


def test_ad_story_reaction_does_not_become_a_story_hint():
    event = InstagramChannel().parse_message_payload({'entry': [{'messaging': [{
        'sender': {'id': 'client'}, 'message': {'mid': 'mid', 'text': '👏',
        'referral': AD, 'reply_to': {'story': {'id': '777'}}}}]}]}, merge=False)[0]
    assert event['kind'] != 'story_context' and not event.get('story')


async def test_old_ad_annotation_is_not_sent_as_history_but_original_history_is_kept(pipeline):
    previous = 'Хочу в Варшаву\n[Отклик на рекламу: SECRET_AD_TITLE]'
    pipeline.state['history'] = [{'role': 'user', 'content': previous}]
    await pipeline.main.process_with_ai('context-client', 'Можно подробнее?', referral=AD)
    prompt = str(pipeline.invoke.await_args.args[0])
    assert 'Хочу в Варшаву' in prompt and 'SECRET_AD_TITLE' not in prompt
    assert pipeline.state['history'][0]['content'] == previous


@pytest.mark.parametrize('kind', ['image', 'shared', 'voice'])
@pytest.mark.parametrize('reverse', [False, True])
def test_separate_customer_media_survives_ad_text_merge(monkeypatch, kind, reverse):
    for name in ('image_media_enabled', 'shared_media_enabled', 'voice_media_enabled'):
        monkeypatch.setattr(settings, name, True)
    ad = {'kind': 'user', 'sender_id': 'client', 'mid': 'ad', 'text': 'Эльбрус', 'referral': AD}
    customer = {'kind': 'user', 'sender_id': 'client', 'mid': 'customer', 'text': 'Мой вопрос'}
    if kind == 'image':
        customer.update(kind='user_non_text', images=['https://scontent.cdninstagram.com/customer.jpg'],
            image_types=['image'], non_text={'types': ['image'], 'text': '', 'has_text': False})
    elif kind == 'shared':
        customer['shared_sources'] = [{'id': '987'}]
    else:
        customer.update(kind='user_voice', voice_parts=[{'audio': 'https://scontent.cdninstagram.com/customer.m4a'}])
    result, = InstagramChannel.merge_events([customer, ad] if reverse else [ad, customer])
    assert {result['mid'], *result.get('related_mids', [])} == {'ad', 'customer'}
    assert not result.get('referral') and result['_ad_text_only']
    assert 'Эльбрус' in result['text']
    key = {'image': 'images', 'shared': 'shared_sources', 'voice': 'voice_parts'}[kind]
    assert result[key] and 'SECRET_AD' not in str(result)


@pytest.mark.parametrize('guard', ['rate', 'input'])
async def test_ads_use_ordinary_visible_guards_without_ad_escalation(pipeline, monkeypatch, guard):
    if guard == 'rate':
        monkeypatch.setattr('src.services.guard.is_rate_limited', lambda _: True)
        question = 'Эльбрус'
    else:
        question = 'x' * 1001
    await pipeline.main.process_with_ai('context-client', question, referral=AD)
    pipeline.invoke.assert_not_awaited()
    pipeline.notify.assert_not_awaited()
    pipeline.send.assert_awaited_once()


@pytest.mark.parametrize('paused', ['pending', 'persisted'])
async def test_ads_still_respect_manager_pause(pipeline, paused):
    from datetime import datetime, timezone
    if paused == 'pending':
        pipeline.main._manager_pending['context-client'] = True
    else:
        pipeline.state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
    await pipeline.main._dispatch_user_event({'kind': 'user', 'sender_id': 'context-client',
        'mid': 'mid', 'text': 'Эльбрус', 'referral': AD})
    pipeline.invoke.assert_not_awaited()
    pipeline.send.assert_not_awaited()
    pipeline.notify.assert_not_awaited()


async def test_outer_processing_exception_is_a_technical_silent_handoff(pipeline, monkeypatch):
    fail = AsyncMock(side_effect=RuntimeError('PRIVATE_ERROR'))
    monkeypatch.setattr(pipeline.main, 'process_with_ai', fail)
    await pipeline.main._process_safely('context-client', 'Эльбрус', referral=AD)
    pipeline.send.assert_not_awaited()
    pipeline.notify.assert_awaited_once()
    assert 'PRIVATE_ERROR' not in str(pipeline.notify.await_args.kwargs)


async def test_actual_current_phone_is_forwarded_without_ad_title_phone(pipeline):
    from tests.model_responses import manager_data, model_response
    pipeline.invoke.return_value = model_response('Свяжемся с вами.', manager_data('Нужна консультация.'))
    await pipeline.main.process_with_ai('context-client', 'Позвоните +375252222222',
        referral={**AD, 'ad_title': 'Звонить +375291111111'})
    pipeline.notify.assert_awaited_once()
    assert pipeline.notify.await_args.kwargs['client_phone'] == '+375252222222'
    assert '+375291111111' not in str(pipeline.invoke.await_args.args[0])


def test_ad_followup_cannot_consume_a_previous_story_hint(pipeline, monkeypatch):
    monkeypatch.setattr(settings, 'story_media_enabled', True)
    hint = pipeline.main._get_recovery
    spy = AsyncMock()
    monkeypatch.setattr(pipeline.main, '_get_recovery', spy)
    event = {'kind': 'user', 'sender_id': 'context-client', 'mid': 'mid', 'text': 'Подробнее?', 'referral': AD}
    result, = pipeline.main._merge_recovery_events([event])
    assert not result.get('story') and not result.get('_reaction_story')
    spy.assert_not_called()
    monkeypatch.setattr(pipeline.main, '_get_recovery', hint)


@pytest.mark.parametrize('api_first', [False, True])
@pytest.mark.parametrize('kind', ['IMAGE', 'VIDEO'])
def test_api_webhook_same_mid_cannot_reintroduce_ad_media(recovery_pipeline, api_first, kind):
    p = recovery_pipeline
    from src.channels.instagram import text_only_ad_event
    api = {'kind': 'user_non_text', 'sender_id': 'pipeline-client', 'mid': 'late-ad',
        'text': 'Эльбрус', '_event_time': p.now[0], '_api_only': True, '_context_incomplete': True,
        'images': [AD['photo_url']], 'non_text': {'types': [kind.lower()]}, 'story': {'id': '777'}}
    webhook = text_only_ad_event({'kind': 'user', 'sender_id': 'pipeline-client', 'mid': 'late-ad',
        'text': 'Эльбрус', '_event_time': p.now[0], 'referral': AD})
    pairs = [(api, 'api'), (webhook, 'webhook')]
    for event, source in pairs if api_first else reversed(pairs):
        p.store.persist('account', [event], source)
    with p.store.connection() as conn:
        payload = json.loads(conn.execute("SELECT payload FROM inbound_events WHERE mid='late-ad'").fetchone()[0])
    assert payload['_ad_text_only'] and payload['text'] == 'Эльбрус'
    assert not any(key in payload for key in ('images', 'non_text', 'story', 'referral'))
