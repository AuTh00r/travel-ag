import json

import pytest

from src.services import diagnostic_trace as trace
from tests.model_responses import model_response, manager_data
from tests.test_handoff_review import review_response
from tests.test_recovery_pipeline import pipeline as pipeline
from tests.test_reviewed_handoffs import reviewed as reviewed


def rows():
    return [json.loads(line) for line in trace.LOG_PATH.read_text(encoding='utf-8').splitlines()]


async def test_primary_review_final_and_durable_receipts_are_correlated(reviewed):
    reviewed.invoke.return_value = model_response('Нужно уточнить.', manager_data('Проверить посадку.'))
    reviewed.review.ainvoke.return_value = review_response({'reply': 'Нужно уточнить.',
        'manager': manager_data('Проверить посадку.'), 'action': 'new', 'task_id': ''})
    job = reviewed.job('Посадка в Бобруйске?')
    await reviewed.recovery.process(job)
    records = rows()
    requests = [r for r in records if r['event'] == 'model_request']
    assert len(requests) == 2
    assert {r['correlation']['trace_id'] for r in requests} == {job['id']}
    primary, secondary = requests
    assert primary['data']['request_id'] == secondary['data']['parent_request_id']
    assert [r['data']['phase'] for r in requests] == ['primary', 'handoff_review']
    assert any('Посадка в Бобруйске?' in str(r['content']) for r in primary['data']['messages'])
    assert any('open_tasks' in str(r['content']) for r in secondary['data']['messages'])
    final, = [r for r in records if r['event'] == 'final_reply']
    actual = ''.join(call.args[1] for call in reviewed.send.await_args_list)
    assert final['data']['reply'] == actual and 'Ваш запрос передан менеджеру.' in actual
    receipts = [r for r in records if r['event'] == 'receipt_recorded']
    assert len(receipts) == 2 and {r['data']['channel'] for r in receipts} == {'instagram', 'telegram'}
    assert all(r['data']['status'] == 'sent' for r in receipts)
    assert len({r['data']['delivery_id'] for r in receipts}) == 2
    reviewed.invoke.assert_awaited_once()
    reviewed.review.ainvoke.assert_awaited_once()
    reviewed.notify.assert_awaited_once()


async def test_format_retry_logs_actual_second_prompt(pipeline):
    from tests.model_responses import tool_response
    pipeline.invoke.side_effect = [tool_response('{"reply":"broken"}'), model_response('Ответ')]
    await pipeline.recovery.process(pipeline.job())
    requests = [r['data'] for r in rows() if r['event'] == 'model_request']
    assert [r['attempt'] for r in requests] == [1, 2]
    assert requests[0]['request_id'] == requests[1]['request_id']
    assert requests[0]['messages'][0]['content'] != requests[1]['messages'][0]['content']
    assert 'ПОВТОР ПОСЛЕ ОШИБКИ ФОРМАТА' in requests[1]['messages'][0]['content']
    assert pipeline.invoke.await_count == 2 and pipeline.send.await_count == 1


@pytest.mark.parametrize('fault', ['sanitize', 'encode', 'sink'])
async def test_trace_failures_do_not_change_reply_count_or_notification(pipeline, monkeypatch, fault):
    def fail(*args, **kwargs):
        raise OSError('PRIVATE_DIAGNOSTIC_FAILURE')
    monkeypatch.setattr(trace, {'sanitize': 'sanitize', 'encode': '_encode', 'sink': '_get_logger'}[fault], fail)
    pipeline.invoke.return_value = model_response('Спасибо.', manager_data('Связаться по туру.', type='контакт'))
    job = pipeline.job('+375290000001')
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job['id'])['state'] == 'done'
    pipeline.invoke.assert_awaited_once()
    pipeline.notify.assert_awaited_once()
    pipeline.send.assert_awaited_once()
    assert pipeline.store.read_session('pipeline-client')[0]['escalation_count'] == 1


async def test_provider_acceptance_is_not_a_durable_receipt(pipeline, monkeypatch):
    @trace.traced_delivery('instagram')
    async def transmit(self, recipient_id, text):
        return await pipeline.send(recipient_id, text)
    monkeypatch.setattr(type(pipeline.main.instagram), 'send_message', transmit)
    def commit_failure(*args, **kwargs):
        raise OSError('PRIVATE_RECEIPT_FAILURE')
    monkeypatch.setattr(pipeline.store, 'record_delivery', commit_failure)
    job = pipeline.job()
    with pytest.raises(OSError):
        await pipeline.recovery.process(job)
    records = rows()
    provider, = [r for r in records if r['event'] == 'provider_result']
    assert provider['data']['status'] == 'accepted'
    assert any(r['event'] == 'receipt_commit_failed' for r in records)
    assert not any(r['event'] == 'receipt_recorded' for r in records)
    pipeline.send.assert_awaited_once()


async def test_api_duplicate_is_logged_without_second_model_call(pipeline):
    job = pipeline.job()
    event = json.loads(job['payload'])
    pipeline.recovery.accept([event], source='api')
    await pipeline.recovery.process(job)
    pipeline.invoke.assert_awaited_once()
    duplicate = [r for r in rows() if r['event'] == 'inbound_event'
                 and r['data']['status'] == 'existing_or_filtered']
    assert len(duplicate) == 1 and duplicate[0]['data']['source'] == 'api'
    assert 'text' not in duplicate[0]['data']['incoming']


async def test_paused_client_has_explicit_skipped_event(pipeline, monkeypatch):
    monkeypatch.setitem(pipeline.main._manager_pending, 'pipeline-client', True)
    await pipeline.main.process_with_ai('pipeline-client', 'Что по турам?')
    pipeline.invoke.assert_not_awaited()
    assert any(r['event'] == 'processing_skipped' and r['data']['reason'] == 'manager_pending' for r in rows())
