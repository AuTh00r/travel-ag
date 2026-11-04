from tests.model_responses import set_arguments
from tests.model_responses import reply_json, manager_data
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.channels.instagram import InstagramChannel
from src.config import settings


def raw(mid='context', text='', attachment=None, referral=None):
    message = {'mid': mid, 'text': text}
    if attachment:
        message['attachments'] = [attachment]
    event = {'sender': {'id': 'context-client'}, 'message': message}
    if referral:
        event['referral'] = referral
    return {'entry': [{'messaging': [event]}]}


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('url', [None, 'https://scontent.cdninstagram.com/story.mp4'])
async def test_mention_is_silent_before_media_routing(monkeypatch, enabled, url):
    for name in ['image_media_enabled', 'voice_media_enabled', 'shared_media_enabled']:
        monkeypatch.setattr(settings, name, enabled)
    result = await InstagramChannel().receive_message(raw(text='Спасибо!', attachment={
        'type': 'story_mention', 'payload': {'url': url}}))
    assert result[0]['kind'] == 'user_silent_handoff'
    assert result[0]['silent_reason'] == 'story_mention'
    assert result[0]['text'] == 'Спасибо!'
    assert not any(key in result[0] for key in ['images', 'voice_parts', 'shared_sources', 'visual_parts'])


@pytest.mark.parametrize('first', [False, True])
@pytest.mark.parametrize('kind', ['story_mention', 'unsupported_type'])
async def test_silent_event_is_barrier_for_normal_text(first, kind):
    channel = InstagramChannel()
    mention = (await channel.receive_message(raw('mention', attachment={'type': kind}), merge=False))[0]
    q1 = {'kind': 'user', 'sender_id': 'context-client', 'mid': 'q1', 'text': 'Тур в Прагу?'}
    q2 = {'kind': 'user', 'sender_id': 'context-client', 'mid': 'q2', 'text': 'Какая цена?'}
    events = [mention, q1, q2] if first else [q1, mention, q2]
    result = channel.merge_events(deepcopy(events))
    silent = [event for event in result if event['kind'] == 'user_silent_handoff']
    assert len(silent) == 1 and silent[0].get('text', '') == ''
    plain = [event for event in result if event['kind'] == 'user']
    assert len(plain) == (1 if first else 2)
    assert '\n'.join(event['text'] for event in plain) == 'Тур в Прагу?\nКакая цена?'
    mids = {mid for event in result for mid in [event['mid'], *event.get('related_mids', [])]}
    assert mids == {'mention', 'q1', 'q2'}


@pytest.mark.parametrize('kind', ['ig_reel', 'file', 'product', 'template'])
async def test_other_cards_are_not_guessed_to_be_invitations(kind):
    result = await InstagramChannel().receive_message(raw(attachment={'type': kind}))
    assert not any(event['kind'] == 'user_silent_handoff' for event in result)


async def test_unsupported_attachment_is_silent_manager_handoff():
    result = await InstagramChannel().receive_message(raw(attachment={'type': 'unsupported_type'}))
    assert result[0]['kind'] == 'user_silent_handoff'
    assert result[0]['silent_reason'] == 'unsupported_type'


async def test_unsupported_attachment_takes_precedence_over_ads():
    result = await InstagramChannel().receive_message(raw(text='Подробнее',
        attachment={'type': 'unsupported_type'}, referral={'source': 'ADS'}))
    assert result[0]['kind'] == 'user_silent_handoff'
    assert result[0]['silent_reason'] == 'unsupported_type'


async def test_unsupported_handoff_never_replies(pipeline):
    await pipeline.main._dispatch_user_event({'kind': 'user_silent_handoff', 'sender_id': 'context-client',
                                              'silent_reason': 'unsupported_type', 'text': ''})
    pipeline.notify.assert_awaited_once()
    assert 'неподдерживаемое вложение' in pipeline.notify.await_args.kwargs['context']
    pipeline.send.assert_not_awaited()
    pipeline.invoke.assert_not_awaited()


@pytest.mark.parametrize('stage', ['profile', 'notification'])
async def test_unsupported_stale_work_propagates_without_client_response(pipeline, stage):
    from src.db.inbound import StaleWork
    target = pipeline.main.instagram.get_username if stage == 'profile' else pipeline.notify
    target.side_effect = StaleWork('source_changed')
    with pytest.raises(StaleWork):
        await pipeline.main._process_silent_handoff('context-client', '', 'unsupported_type')
    pipeline.send.assert_not_awaited()
    pipeline.invoke.assert_not_awaited()
    assert pipeline.state['history'] == []


def test_ad_referral_keeps_bounded_private_sources_not_raw_payload():
    context = {'ad_title': 'Рилс ВДП Рождество', 'post_id': '179001',
               'photo_url': 'https://scontent.cdninstagram.com/ad.jpg?secret=URL',
               'video_url': 'https://scontent.cdninstagram.com/ad.mp4?secret=URL',
               'permalink': 'https://www.instagram.com/p/DeI-3NiA_5L/', 'unexpected': 'DROP'}
    result = InstagramChannel._extract_referral_metadata({}, {'referral': {
        'source': 'ADS', 'type': 'OPEN_THREAD', 'ad_id': '123', 'ads_context_data': context}})
    assert all(result.get(key) == value for key, value in context.items() if key != 'unexpected')
    assert 'unexpected' not in result and 'ads_context_data' not in result


def test_ad_referral_rejects_malformed_and_oversized_fields():
    result = InstagramChannel._extract_referral_metadata({}, {'referral': {
        'source': [], 'ad_id': {'id': 1}, 'ads_context_data': {
            'ad_title': ['BAD'], 'photo_url': 'x' * 9000, 'video_url': 12, 'post_id': []}}})
    assert result == {}


@pytest.fixture
def pipeline(monkeypatch):
    import src.main as main
    from src.services import guard
    guard._user_timestamps.clear()
    monkeypatch.setattr(main, 'instagram', InstagramChannel())
    state = {'history': [], 'escalation_count': 0}
    async def get(*_):
        return deepcopy(state)
    async def save(_id, value):
        state.clear()
        state.update(deepcopy(value))
    for name in ['_locks', '_processing_locks', '_manager_pending']:
        monkeypatch.setattr(main, name, {})
    monkeypatch.setattr(main, 'get_session', get)
    monkeypatch.setattr(main, 'save_session', save)
    from tests.model_responses import model_response
    invoke = AsyncMock(return_value=model_response())
    notify, send, queue = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr('src.services.llm.get_llm', lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr('src.services.llm.get_vision_llm', lambda **_: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr('src.services.tour_loader.get_tours_text',
        lambda: '=== ТУР: Эльбрус ===\n=== ТУР: Варшава - Берлин - Познань ===\n=== ТУР: Прага ===')
    monkeypatch.setattr('src.db.faq_db.search_faq', AsyncMock(return_value=[]))
    monkeypatch.setattr(main.instagram, 'get_username', AsyncMock(return_value=None))
    monkeypatch.setattr(main.instagram, 'send_message', send)
    monkeypatch.setattr(main, 'enqueue_pending', queue)
    monkeypatch.setattr('src.services.telegram_notify.TelegramNotifier.notify_manager', notify)
    return SimpleNamespace(main=main, state=state, invoke=invoke, notify=notify, send=send, queue=queue)


@pytest.mark.parametrize('outcome', ['sent', 'failed', 'limit', 'takeover', 'pending', 'profile_failed'])
@pytest.mark.parametrize('kind', ['story_mention', 'unsupported_type'])
async def test_silent_mention_never_replies_or_calls_ai(pipeline, outcome, kind):
    from datetime import datetime, timezone
    if outcome == 'failed':
        pipeline.notify.side_effect = RuntimeError('proof failure')
    if outcome == 'profile_failed':
        pipeline.main.instagram.get_username.side_effect = RuntimeError('private profile failure')
    if outcome == 'limit':
        pipeline.state['escalation_count'] = 3
    if outcome == 'takeover':
        pipeline.state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
    if outcome == 'pending':
        pipeline.main._manager_pending['context-client'] = True
    await pipeline.main._dispatch_user_event({'kind': 'user_silent_handoff', 'sender_id': 'context-client',
                                             'silent_reason': kind, 'text': 'Спасибо!'})
    assert pipeline.notify.await_count == int(outcome in {'sent', 'failed', 'profile_failed'})
    pipeline.invoke.assert_not_awaited()
    pipeline.send.assert_not_awaited()
    pipeline.queue.assert_not_awaited()
    assert not any(item['role'] == 'assistant' for item in pipeline.state['history'])
    assert pipeline.state['escalation_count'] == (3 if outcome == 'limit' else int(outcome in {'sent', 'profile_failed'}))


@pytest.mark.parametrize('count', [0, 3])
@pytest.mark.parametrize('with_image', [False, True])
def test_reply_style_is_common_without_business_policy_override(count, with_image):
    from src.ai.prompts import build_full_prompt
    prompt = build_full_prompt('Каталог', '', [], 'Хотим предложить сотрудничество!', count,
        media_images=[{'label': 'Фото', 'url': 'data:image/jpeg;base64,/9j/AA=='}] if with_image else None)[0].content
    assert 'каждое новое предложение начинай с заглавной буквы' in prompt
    assert 'Не добавляй бессодержательные хвосты' in prompt
    assert 'Ты отвечаешь ТОЛЬКО на вопросы о турах и путешествиях' in prompt
    assert 'ПРЕДЛОЖЕНИЕ СОТРУДНИЧЕСТВА:' not in prompt
    assert 'принимаешь деловые предложения' not in prompt
    if count == 3:
            assert 'Программа применит лимит' in prompt


async def test_mention_priority_over_emoji_story_reply():
    data = raw(text='👏', attachment={'type': 'story_mention'})
    data['entry'][0]['messaging'][0]['message']['reply_to'] = {'story': {'id': '17900001'}}
    result = await InstagramChannel().receive_message(data)
    assert result[0]['kind'] == 'user_silent_handoff'


def test_media_keeps_existing_tour_scope_without_cooperation_override():
    from src.ai.prompts import build_full_prompt
    prompt = build_full_prompt('Каталог', '', [], 'Предлагаем сотрудничество',
        media_images=[{'label': 'История', 'url': 'data:image/jpeg;base64,/9j/AA=='}])[0].content
    assert 'Определи тур по видимым данным' in prompt
    assert 'не заменяй явное предложение сотрудничества' not in prompt


@pytest.mark.parametrize('outcome', ['sent', 'failed', 'limit'])
async def test_polite_reply_content_and_receipt_preserved(pipeline, outcome):
    content = 'Спасибо за предложение. Я помогаю с вопросами об автобусных турах.'
    set_arguments(pipeline.invoke.return_value, reply_json(content, manager_data('Клиент предлагает сотрудничество компании, детали ещё не сообщил.')))
    if outcome == 'limit':
        pipeline.state['escalation_count'] = 3
    if outcome == 'failed':
        pipeline.notify.side_effect = RuntimeError('proof failure')
    await pipeline.main.process_with_ai('context-client', 'Здравствуйте! Хотим предложить сотрудничество!)')
    reply = ''.join(call.args[1] for call in pipeline.send.await_args_list)
    assert content in reply and '===МЕНЕДЖЕР===' not in reply
    assert pipeline.notify.await_count == int(outcome != 'limit')
    expected = {'sent': 'Ваш запрос передан менеджеру.', 'failed': 'Не удалось подтвердить передачу',
                'limit': 'Новое уведомление менеджеру не отправлено'}[outcome]
    assert expected in reply
    assert pipeline.state['escalation_count'] == (3 if outcome == 'limit' else int(outcome == 'sent'))
    assert pipeline.state['history'][-1]['content'] == reply


@pytest.mark.parametrize('failed', [False, True])
async def test_silent_username_failure_or_manager_echo_never_sends(pipeline, monkeypatch, failed):
    async def lookup(_):
        if failed:
            raise RuntimeError('proof failure')
        pipeline.main._manager_pending['context-client'] = True
    monkeypatch.setattr(pipeline.main.instagram, 'get_username', lookup)
    await pipeline.main._process_silent_handoff('context-client', '', 'story_mention')
    assert pipeline.notify.await_count == int(failed)
    if failed:
        assert pipeline.notify.await_args.kwargs['instagram_handle'] is None
    pipeline.invoke.assert_not_awaited()
    pipeline.send.assert_not_awaited()
    pipeline.queue.assert_not_awaited()
