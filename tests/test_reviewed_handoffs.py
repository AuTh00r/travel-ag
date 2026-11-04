"""21 anonymized routing regressions. Stub decisions do not prove AI semantics."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.db import manager_tasks, sessions
from src.services import llm
from src.services.handoff_review import HandoffDecision
from src.services.telegram_notify import TelegramNotifier
from tests.model_responses import manager_data, model_response
from tests.test_handoff_review import CATALOG, review_response
from tests.test_recovery_pipeline import pipeline as pipeline

CASES = json.loads((Path(__file__).parent / 'fixtures/handoff_cases.json').read_text(encoding='utf-8'))


@pytest.fixture
def reviewed(pipeline, monkeypatch):
    monkeypatch.setattr(settings, 'manager_review_enabled', True)
    monkeypatch.setattr('src.services.tour_loader.get_tours_text', lambda: CATALOG)
    pipeline.notify.return_value = '501'
    pipeline.review = AsyncMock()
    monkeypatch.setattr(llm, 'get_handoff_review_llm', lambda **kwargs: pipeline.review)
    pipeline.edit = AsyncMock(return_value='101')
    monkeypatch.setattr(TelegramNotifier, '_edit', pipeline.edit)
    return pipeline


def prior_task(reviewed, summary):
    with reviewed.store.connection() as conn:
        task_id, operations = manager_tasks.plan(conn, client='pipeline-client', summary=summary,
            decision=HandoffDecision({}), text=summary, destinations=['manager-one'],
            now=reviewed.now[0], source_key='prior')
    assert manager_tasks.begin_legacy(reviewed.store, operations[0])
    reviewed.store.record_delivery(operations[0], 'sent', '101')
    return task_id


@pytest.mark.parametrize('case', CASES, ids=lambda case: str(case['id']) + '-' + case['action'])
async def test_historical_intents_through_real_handler_and_recovery(reviewed, case):
    old_task = prior_task(reviewed, case['prior']) if case.get('prior') else None
    if case.get('limit'):
        with reviewed.store.connection() as conn:
            state, revision = sessions.read_row(conn, 'pipeline-client')
            state['escalation_count'] = 3
            sessions.write_row(conn, 'pipeline-client', state, revision)
    contact = case['action'] == 'contact'
    candidate = manager_data(case['context'], type='контакт' if contact else 'консультация')
    reviewed.invoke.return_value = model_response(case['reply'] + ' Ваш запрос передан менеджеру.', candidate)
    reviewed.review.ainvoke.return_value = review_response({
        'reply': case['reply'], 'manager': None if case['action'] == 'cancel' else candidate,
        'action': case['action'] if not contact else 'new',
        'task_id': old_task if case['action'] == 'update' else ''})
    job = reviewed.job(case['question'])
    await reviewed.recovery.process(job)
    assert reviewed.store.get_job(job['id'])['state'] == 'done'
    reviewed.invoke.assert_awaited_once()
    assert reviewed.review.ainvoke.await_count == int(not contact)
    response = ''.join(call.args[1] for call in reviewed.send.await_args_list)
    if case['action'] == 'cancel':
        assert case['reply'] in response
        assert 'передан менеджеру' not in response
        reviewed.notify.assert_not_awaited()
        reviewed.edit.assert_not_awaited()
    elif case['action'] == 'update':
        reviewed.notify.assert_not_awaited()
        reviewed.edit.assert_awaited_once()
        assert reviewed.edit.await_args.args[2] == '101'
        task = manager_tasks.open_tasks('pipeline-client', store=reviewed.store)[0]
        assert task['id'] == old_task and task['revision'] == 2 and task['summary'] == case['context']
    elif case.get('limit'):
        reviewed.notify.assert_not_awaited()
        assert 'лимит' in response
    else:
        reviewed.notify.assert_awaited_once()
    expected_count = (3 if case.get('limit') else 0 if case['action'] == 'cancel' else
                      1 if contact or case['action'] == 'update' else 1 + bool(old_task))
    assert reviewed.store.read_session('pipeline-client')[0]['escalation_count'] == expected_count
    # Repeating delivery neither regenerates the reply nor repeats a notification.
    send_count, notify_count = reviewed.send.await_count, reviewed.notify.await_count
    await reviewed.recovery.deliver(reviewed.store.get_job(job['id']))
    assert reviewed.send.await_count == send_count and reviewed.notify.await_count == notify_count
    assert reviewed.review.ainvoke.await_count == int(not contact)


@pytest.mark.parametrize('failure', ['provider', 'format'])
async def test_reviewer_failure_preserves_valid_candidate_once(reviewed, failure):
    reviewed.invoke.return_value = model_response('Посадку нужно уточнить.', manager_data('Проверить посадку.'))
    if failure == 'provider':
        reviewed.review.ainvoke.side_effect = RuntimeError('synthetic')
    else:
        reviewed.review.ainvoke.return_value = review_response('{}')
    job = reviewed.job('Посадка в Бобруйске?')
    await reviewed.recovery.process(job)
    reviewed.review.ainvoke.assert_awaited_once()
    reviewed.notify.assert_awaited_once()
    assert reviewed.store.read_session('pipeline-client')[0]['escalation_count'] == 1


async def test_takeover_while_reviewing_cancels_before_notification(reviewed):
    reviewed.invoke.return_value = model_response('Нужно уточнить.', manager_data('Проверить посадку.'))
    async def take_over(messages):
        reviewed.store.mark_legacy_manager('pipeline-client', 'Менеджер ответил')
        return review_response({'reply': 'Нужно уточнить.', 'manager': manager_data('Проверить посадку.'),
                                'action': 'new', 'task_id': ''})
    reviewed.review.ainvoke.side_effect = take_over
    job = reviewed.job('Посадка в Бобруйске?')
    await reviewed.recovery.process(job)
    assert reviewed.store.get_job(job['id'])['state'] == 'cancelled'
    reviewed.notify.assert_not_awaited()
    reviewed.send.assert_not_awaited()


async def test_catalog_metadata_is_exact_primary_and_review_input(reviewed):
    reviewed.invoke.return_value = model_response('Нужно уточнить.', manager_data('Проверить посадку.'))
    reviewed.review.ainvoke.return_value = review_response({'reply': 'Нужно уточнить.',
        'manager': manager_data('Проверить посадку.'), 'action': 'new', 'task_id': ''})
    await reviewed.recovery.process(reviewed.job())
    from src.services import llm_response_log
    rows = [json.loads(line) for line in llm_response_log.LOG_PATH.read_text(encoding='utf-8').splitlines()]
    assert [r['phase'] for r in rows] == ['primary', 'handoff_review']
    assert rows[1]['parent_request_id'] == rows[0]['request_id']
    assert rows[0]['catalog'] == rows[1]['catalog'] == llm_response_log.catalog_metadata(CATALOG)
    assert CATALOG in reviewed.invoke.await_args.args[0][0].content
    assert CATALOG in reviewed.review.ainvoke.await_args.args[0][0].content


async def test_update_at_limit_and_partial_retry_do_not_generate_again(reviewed, monkeypatch):
    task = prior_task(reviewed, 'Проверить посадку в Бобруйске.')
    with reviewed.store.connection() as conn:
        state, revision = sessions.read_row(conn, 'pipeline-client')
        state['escalation_count'] = 3
        sessions.write_row(conn, 'pipeline-client', state, revision)
    reviewed.invoke.return_value = model_response('Уточнить дату.', manager_data('Проверить посадку 15 января.'))
    reviewed.review.ainvoke.return_value = review_response({'reply': 'Учту дату.',
        'manager': manager_data('Проверить посадку 15 января.'), 'action': 'update', 'task_id': task})
    from src.exceptions import TelegramError
    reviewed.edit.side_effect = [TelegramError('retry', delivery_status='retry_wait'), '101']
    job = reviewed.job('15 января')
    await reviewed.recovery.process(job)
    assert reviewed.store.get_job(job['id'])['state'] == 'delivering'
    reviewed.send.assert_not_awaited()
    reviewed.now[0] += settings.default_retry_seconds
    await reviewed.recovery.deliver(reviewed.store.get_job(job['id']))
    reviewed.invoke.assert_awaited_once()
    reviewed.review.ainvoke.assert_awaited_once()
    assert reviewed.edit.await_count == 2 and reviewed.notify.await_count == 0
    assert reviewed.store.read_session('pipeline-client')[0]['escalation_count'] == 3
    assert 'лимит' not in ''.join(call.args[1] for call in reviewed.send.await_args_list)


async def test_legacy_handler_does_not_overwrite_task_counter_with_stale_session(reviewed):
    reviewed.invoke.return_value = model_response('Нужно уточнить.', manager_data('Проверить посадку.'))
    reviewed.review.ainvoke.return_value = review_response({'reply': 'Нужно уточнить.',
        'manager': manager_data('Проверить посадку.'), 'action': 'new', 'task_id': ''})
    await reviewed.main.process_with_ai('pipeline-client', 'Где посадка?')
    assert reviewed.store.read_session('pipeline-client')[0]['escalation_count'] == 1
    task = manager_tasks.open_tasks('pipeline-client', store=reviewed.store)[0]
    reviewed.review.ainvoke.return_value = review_response({'reply': 'Учту дату.',
        'manager': manager_data('Проверить посадку 15 января.'), 'action': 'update', 'task_id': task['id']})
    # Legacy notifier uses the original confirmation from _send, not another task.
    reviewed.edit.return_value = '501'
    await reviewed.main.process_with_ai('pipeline-client', '15 января')
    assert reviewed.store.read_session('pipeline-client')[0]['escalation_count'] == 1
    assert reviewed.notify.await_count == 1 and reviewed.edit.await_count == 1


async def test_recovery_partial_notification_survives_restart_without_model(reviewed, monkeypatch):
    from src.db.inbound import InboundStore
    from src.exceptions import TelegramError

    for name, value in [('telegram_secondary_chat_id', 'two'), ('telegram_tertiary_chat_id', 'three'),
                        ('telegram_extra_chat_id', 'four')]:
        monkeypatch.setattr(settings, name, value)
    reviewed.invoke.return_value = model_response('Нужно уточнить.', manager_data('Проверить посадку.'))
    reviewed.review.ainvoke.return_value = review_response({'reply': 'Нужно уточнить.',
        'manager': manager_data('Проверить посадку.'), 'action': 'new', 'task_id': ''})
    reviewed.notify.side_effect = ['101', TelegramError('retry', delivery_status='retry_wait'), '103', '104', '102']
    job = reviewed.job('Где посадка?')
    await reviewed.recovery.process(job)
    assert reviewed.store.get_job(job['id'])['state'] == 'delivering'
    assert reviewed.notify.await_count == 4
    reviewed.now[0] += settings.default_retry_seconds
    restarted = InboundStore(clock=lambda: reviewed.now[0])
    restarted.recover(startup=True)
    reviewed.recovery.store = restarted
    await reviewed.recovery.deliver(restarted.get_job(job['id']))
    assert reviewed.notify.await_count == 5 and reviewed.notify.await_args.args[1] == 'two'
    reviewed.invoke.assert_awaited_once()
    reviewed.review.ainvoke.assert_awaited_once()
    assert restarted.get_job(job['id'])['state'] == 'done'
    assert restarted.read_session('pipeline-client')[0]['escalation_count'] == 1


def test_stale_task_cas_rolls_back_entire_recovery_draft(reviewed):
    from src.db.inbound import StaleWork
    from src.services.inbound_recovery import ProcessingContext

    task = prior_task(reviewed, 'Проверить посадку.')
    job = reviewed.job('15 января')
    context = ProcessingContext(reviewed.store, job)
    context.session['history'] = [{'role': 'user', 'content': '15 января'}]
    context.plan_notification('Обновление', ['manager-one'], summary='Проверить посадку 15 января.',
                              decision=HandoffDecision({}, action='update', task_id=task, task_revision=0))
    with pytest.raises(StaleWork, match='manager_task_changed'):
        reviewed.store.commit_result(job, context.session, context.revision, context.result(), context.notifications)
    assert reviewed.store.read_session('pipeline-client')[0]['history'] == []
    assert reviewed.store.get_job(job['id'])['state'] == 'processing'
    assert reviewed.store.deliveries(job['id']) == []


async def test_legacy_receipt_during_recovery_refresh_is_a_known_session_writer(reviewed):
    from src.services.inbound_recovery import ProcessingContext

    with reviewed.store.connection() as conn:
        manager_tasks.plan(conn, client='pipeline-client', summary='Уточнить посадку.',
            decision=HandoffDecision({}), text='Уточнить посадку.', destinations=['manager-one'],
            now=reviewed.now[0], source_key='old-legacy')
    job = reviewed.job('Новый понятный вопрос', _api_only=True)
    context = ProcessingContext(reviewed.store, job)
    context.plan_reply('Ответ по каталогу.')
    reviewed.store.commit_result(job, context.session, context.revision, context.result(), [])
    async def refresh(client):
        await reviewed.main._deliver_legacy_manager_tick(reviewed.store)
        return True
    reviewed.recovery.refresh_client.side_effect = refresh
    await reviewed.recovery.deliver(reviewed.store.get_job(job['id']))
    assert reviewed.store.get_job(job['id'])['state'] == 'done'
    reviewed.notify.assert_awaited_once()
    reviewed.send.assert_awaited_once()
    assert reviewed.store.read_session('pipeline-client')[0]['escalation_count'] == 1
