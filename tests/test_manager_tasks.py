"""Real SQLite and HTTP mocks: task identity, edits and delivery uncertainty."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import time

import httpx
import pytest

from src.config import settings
from src.db import manager_tasks, sessions
from src.db.inbound import InboundStore, StaleWork
from src.exceptions import TelegramError
from src.services.handoff_review import HandoffDecision
from src.services.inbound_recovery import current_delivery, legacy_processing
from src.services.telegram_notify import TelegramNotifier


@pytest.fixture
def ledger(monkeypatch):
    now = [time.time()]
    store = InboundStore(clock=lambda: now[0])
    store.initialize('test')
    for name, value in {'telegram_bot_token': 'fake', 'telegram_manager_chat_id': 'one',
                        'telegram_secondary_chat_id': 'two', 'telegram_tertiary_chat_id': 'three',
                        'telegram_extra_chat_id': 'four'}.items():
        monkeypatch.setattr(settings, name, value)
    return SimpleNamespace(store=store, now=now)


def plan(ledger, *, source='m1', decision=None, client='client', summary='Уточнить посадку.', job_id=None):
    with ledger.store.connection() as conn:
        return manager_tasks.plan(conn, client=client, summary=summary,
            decision=decision or HandoffDecision({}), text=summary, destinations=['one', 'two', 'three', 'four'],
            now=ledger.now[0], source_key=source, job_id=job_id)


def confirm(ledger, operation, receipt='100'):
    assert manager_tasks.begin_legacy(ledger.store, operation)
    ledger.store.record_delivery(operation, 'sent', receipt=receipt)


def update(task, revision=1):
    return HandoffDecision({}, action='update', task_id=task, task_revision=revision, reviewed=True)


def test_legacy_duplicate_mid_and_four_receipts_count_once(ledger):
    task, operations = plan(ledger)
    for i, operation in enumerate(operations):
        confirm(ledger, operation, str(100 + i))
    repeated, same = plan(ledger)
    assert repeated == task and [o['id'] for o in same] == [o['id'] for o in operations]
    assert {o['state'] for o in same} == {'sent'}
    assert ledger.store.read_session('client')[0]['escalation_count'] == 1


def test_technical_alert_ignores_quota_is_deduplicated_and_not_reviewed(ledger):
    with ledger.store.connection() as conn:
        state, revision = sessions.read_row(conn, 'client')
        state['escalation_count'] = 3
        ledger.store._write_own_session(conn, 'client', state, revision)
    decision = HandoffDecision({}, action='technical')
    task, operations = plan(ledger, source='technical:m1', decision=decision)
    for i, operation in enumerate(operations):
        confirm(ledger, operation, str(900 + i))
    assert plan(ledger, source='technical:m1', decision=decision)[0] == task
    assert ledger.store.read_session('client')[0]['escalation_count'] == 3
    assert manager_tasks.open_tasks('client', store=ledger.store) == []
    with pytest.raises(StaleWork):
        plan(ledger, source='m2', decision=update(task))


def test_technical_card_has_separate_job_part_from_existing_business_card(ledger):
    _, previous = plan(ledger, job_id='job1')
    _, technical = plan(ledger, source='technical:m1', job_id='job1',
                        decision=HandoffDecision({}, action='technical'))
    assert {d['part'] for d in previous} == {0}
    assert {d['part'] for d in technical} == {1}
    assert {d['id'] for d in previous}.isdisjoint({d['id'] for d in technical})


def test_partial_update_edits_confirmed_chats_and_sends_only_missing(ledger):
    task, operations = plan(ledger)
    confirm(ledger, operations[0], '101')
    confirm(ledger, operations[2], '103')
    ledger.now[0] += 10
    _, revised = plan(ledger, source='m2', decision=update(task), summary='Уточнить посадку 15 января.')
    assert [(o['operation'], o['target_message_id']) for o in revised] == [
        ('edit', '101'), ('send', None), ('edit', '103'), ('send', None)]
    for i, operation in enumerate(revised):
        confirm(ledger, operation, operation['target_message_id'] or str(200 + i))
    assert ledger.store.read_session('client')[0]['escalation_count'] == 1
    assert manager_tasks.open_tasks('other', store=ledger.store) == []
    assert manager_tasks.open_tasks('client', store=ledger.store)[0]['revision'] == 2


def test_unknown_previous_send_does_not_create_replacement(ledger):
    task, operations = plan(ledger)
    assert manager_tasks.begin_legacy(ledger.store, operations[0])
    ledger.store.record_delivery(operations[0], 'unknown')
    confirm(ledger, operations[1], '102')
    _, revised = plan(ledger, source='m2', decision=update(task))
    assert revised[0]['state'] == 'unknown' and revised[0]['target_message_id'] is None
    assert revised[1]['operation'] == 'edit' and revised[1]['target_message_id'] == '102'
    assert not manager_tasks.begin_legacy(ledger.store, revised[0])


@pytest.mark.parametrize('reason', ['foreign_client', 'revision', 'inflight', 'takeover'])
def test_stale_or_foreign_update_never_becomes_new(ledger, reason):
    task, operations = plan(ledger)
    kwargs = {}
    decision = update(task)
    if reason == 'foreign_client':
        kwargs['client'] = 'other'
    elif reason == 'revision':
        decision = update(task, 0)
    elif reason == 'inflight':
        assert manager_tasks.begin_legacy(ledger.store, operations[0])
    else:
        with ledger.store.connection() as conn:
            manager_tasks.close_client(conn, 'client')
    with pytest.raises(StaleWork):
        plan(ledger, source='m2', decision=decision, **kwargs)
    with ledger.store.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM manager_tasks').fetchone()[0] == 1


async def test_takeover_closes_tasks_even_after_pause_removed_and_restart(ledger):
    task, operations = plan(ledger)
    state = await sessions.get_session('client')
    state['manager_last_at'] = datetime.now(timezone.utc).isoformat()
    await sessions.save_session('client', state)
    state['manager_last_at'] = None
    await sessions.save_session('client', state)
    ledger.store = InboundStore(clock=lambda: ledger.now[0])
    assert manager_tasks.open_tasks('client', store=ledger.store) == []
    with pytest.raises(StaleWork):
        manager_tasks.begin_legacy(ledger.store, operations[0])
    with pytest.raises(StaleWork):
        plan(ledger, source='m2', decision=update(task))


def test_restart_marks_legacy_http_unknown(ledger):
    _, operations = plan(ledger)
    assert manager_tasks.begin_legacy(ledger.store, operations[0])
    manager_tasks.recover_legacy_intents()
    assert ledger.store.get_delivery(operations[0]['id'])['state'] == 'unknown'
    assert not manager_tasks.begin_legacy(ledger.store, operations[0])


def test_update_works_at_count_limit_but_independent_task_does_not(ledger):
    task, operations = plan(ledger)
    confirm(ledger, operations[0])
    with ledger.store.connection() as conn:
        state, revision = sessions.read_row(conn, 'client')
        state['escalation_count'] = 3
        sessions.write_row(conn, 'client', state, revision)
    _, revised = plan(ledger, source='m2', decision=update(task))
    confirm(ledger, revised[0], '100')
    assert ledger.store.read_session('client')[0]['escalation_count'] == 3
    with pytest.raises(StaleWork, match='manager_limit'):
        plan(ledger, source='new-question')


def test_cleanup_preserves_open_task_receipts(ledger):
    _, operations = plan(ledger)
    confirm(ledger, operations[0], '123')
    ledger.now[0] += 100 * 86400
    ledger.store.cleanup()
    assert ledger.store.get_delivery(operations[0]['id'])['receipt'] == '123'


@pytest.mark.parametrize('body,status,expected', [
    ({'ok': True, 'result': {'message_id': 123}}, 200, '123'),
    ({'ok': False, 'error_code': 400, 'description': 'Bad Request: message is not modified'}, 400, '123'),
    ({'ok': True, 'result': {'message_id': 456}}, 200, None),
    ({'ok': False, 'error_code': 400, 'description': 'Bad Request: message to edit not found'}, 400, None),
])
async def test_edit_http_uses_exact_saved_target_without_send_fallback(ledger, monkeypatch, body, status, expected):
    requests = []
    async def handle(request):
        requests.append(request)
        return httpx.Response(status, json=body)
    real_client = httpx.AsyncClient
    monkeypatch.setattr('src.services.telegram_notify.AsyncClient',
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    token = current_delivery.set({'channel': 'telegram', 'destination': 'one', 'client_id': 'client',
                                  'legacy': True, 'operation': 'edit', 'target_message_id': '123'})
    try:
        if expected:
            assert await TelegramNotifier()._edit('new text', 'one', '123', sender_id='client') == expected
        else:
            with pytest.raises(TelegramError):
                await TelegramNotifier()._edit('new text', 'one', '123', sender_id='client')
    finally:
        current_delivery.reset(token)
    assert len(requests) == 1 and requests[0].url.path.endswith('/editMessageText')
    assert b'"message_id":123' in requests[0].content


async def test_legacy_notifier_persists_receipts_and_updates_four_chats(ledger, monkeypatch):
    send = AsyncMock(side_effect=['101', '102', '103', '104'])
    edit = AsyncMock(side_effect=['101', '102', '103', '104'])
    monkeypatch.setattr(TelegramNotifier, '_send', send)
    monkeypatch.setattr(TelegramNotifier, '_edit', edit)
    for mid, decision in [('m1', HandoffDecision({})), ('m2', None)]:
        if decision is None:
            task = manager_tasks.open_tasks('client')[0]
            decision = update(task['id'], task['revision'])
        token = legacy_processing.set({'mid': mid})
        try:
            receipt = await TelegramNotifier().notify_manager(sender_id='client', context='Уточнить посадку.',
                                                              tag='консультация', decision=decision)
        finally:
            legacy_processing.reset(token)
        assert receipt.managed and receipt.escalation_count == 1
    assert send.await_count == 4 and edit.await_count == 4
    assert [c.args[2] for c in edit.await_args_list] == ['101', '102', '103', '104']


async def test_missing_legacy_receipt_stays_unknown_without_count(ledger, monkeypatch):
    monkeypatch.setattr(TelegramNotifier, '_send', AsyncMock(return_value=None))
    with pytest.raises(TelegramError):
        await TelegramNotifier().notify_manager(sender_id='client', context='Уточнить посадку.',
                                               tag='консультация', decision=HandoffDecision({}))
    with ledger.store.connection() as conn:
        assert {r[0] for r in conn.execute('SELECT state FROM inbound_deliveries')} == {'unknown'}
    assert ledger.store.read_session('client')[0]['escalation_count'] == 0


async def test_partial_legacy_retry_after_restart_sends_only_missing_and_never_unknown(ledger, monkeypatch):
    import src.main as main

    monkeypatch.setattr(main, '_locks', {})
    monkeypatch.setattr(main, '_manager_pending', {})
    send = AsyncMock(side_effect=[TelegramError('429', delivery_status='retry_wait'), '102',
                                 TelegramError('ambiguous', delivery_status='unknown'), '104', '101'])
    monkeypatch.setattr(TelegramNotifier, '_send', send)
    receipt = await TelegramNotifier().notify_manager(sender_id='client', context='Уточнить посадку.',
                                                     tag='консультация', decision=HandoffDecision({}))
    assert receipt.escalation_count == 1 and len(receipt.receipts) == 2
    with ledger.store.connection() as conn:
        ledger.now[0] = conn.execute("SELECT MAX(due) FROM inbound_deliveries WHERE state='retry_wait'").fetchone()[0] + 1
    manager_tasks.recover_legacy_intents()
    await main._deliver_legacy_manager_tick(InboundStore(clock=lambda: ledger.now[0]))
    assert send.await_count == 5 and send.await_args.args[1] == 'one'
    assert ledger.store.read_session('client')[0]['escalation_count'] == 1
    with ledger.store.connection() as conn:
        assert [(r['destination'], r['state']) for r in conn.execute(
            'SELECT destination,state FROM inbound_deliveries ORDER BY rowid')] == [
                ('one', 'sent'), ('two', 'sent'), ('three', 'unknown'), ('four', 'sent')]


async def test_manager_cancels_ready_legacy_operations_before_worker(ledger, monkeypatch):
    import src.main as main

    monkeypatch.setattr(main, '_locks', {})
    monkeypatch.setattr(main, '_manager_pending', {})
    _, operations = plan(ledger)
    ledger.store.mark_legacy_manager('client', 'Ответ менеджера')
    send = AsyncMock()
    monkeypatch.setattr(TelegramNotifier, '_send', send)
    await main._deliver_legacy_manager_tick(ledger.store)
    send.assert_not_awaited()
    assert ledger.store.get_delivery(operations[0]['id'])['state'] == 'cancelled'


@pytest.mark.parametrize('receipt', [None, '', 'not-a-message', True, -1, '456'])
def test_invalid_edit_receipt_never_counts_or_confirms(ledger, receipt):
    task, operations = plan(ledger)
    confirm(ledger, operations[0], '100')
    _, revised = plan(ledger, source='m2', decision=update(task))
    assert manager_tasks.begin_legacy(ledger.store, revised[0])
    ledger.store.record_delivery(revised[0], 'sent', receipt)
    assert ledger.store.get_delivery(revised[0]['id'])['state'] == 'unknown'
    assert ledger.store.read_session('client')[0]['escalation_count'] == 1


def test_existing_receipt_journal_migrates_without_changing_old_rows(tmp_path):
    import sqlite3

    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE inbound_deliveries(id TEXT PRIMARY KEY,job_id TEXT,client_id TEXT NOT NULL,'
                     'channel TEXT NOT NULL,destination TEXT NOT NULL,part INTEGER NOT NULL,payload TEXT NOT NULL,'
                     'state TEXT NOT NULL,due REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,receipt TEXT,'
                     'intent_at REAL,created_at REAL NOT NULL,updated_at REAL NOT NULL,'
                     'UNIQUE(job_id,channel,destination,part))')
        conn.execute("INSERT INTO inbound_deliveries VALUES ('old',NULL,'client','telegram','one',0,'saved',"
                     "'sent',0,1,'123',0,0,0)")
    store = InboundStore(path=path)
    store.initialize('account')
    row = store.get_delivery('old')
    assert row['receipt'] == '123' and row['payload'] == 'saved' and row['state'] == 'sent'
    assert row['manager_task_id'] is None and row['operation'] == 'send'
    restarted = InboundStore(path=path)
    assert restarted.get_delivery('old') == row
