from unittest.mock import AsyncMock

import pytest

from tests.test_ad_model_decision import model as model, pipeline as pipeline, response
from tests.test_ad_empty_response_retry import blank


async def test_three_empty_attempts_are_silent_and_have_diagnostics(model):
    model.invoke.side_effect = [blank(), blank(), blank()]
    model.state['escalation_count'] = 3
    await model.main.process_with_ai('context-client', 'Какие туры в Варшаву?')
    assert model.invoke.await_count == 3
    assert model.invoke.await_args_list[-1].kwargs['timeout'] == 240
    model.send.assert_not_awaited()
    model.queue.assert_not_awaited()
    model.notify.assert_awaited_once()
    note = model.notify.await_args.kwargs
    assert note['decision'].action == 'technical'
    assert 'empty_response' in note['context']
    assert '240' in note['context'] and '120' in note['context']
    assert 'ID:' in note['context']
    assert model.state['escalation_count'] == 3
    assert [e['role'] for e in model.state['history']] == ['user']


async def test_transient_failure_retries_then_answers(model):
    model.invoke.side_effect = [TimeoutError('SECRET'), response()]
    await model.main.process_with_ai('context-client', 'ВДП')
    assert model.invoke.await_count == 2
    model.send.assert_awaited_once()
    model.notify.assert_not_awaited()


async def test_terminal_local_failure_is_silent_with_safe_cause(model):
    model.invoke.side_effect = TypeError('SECRET https://example.org/?token=PRIVATE')
    await model.main.process_with_ai('context-client', 'ВДП')
    model.invoke.assert_awaited_once()
    model.send.assert_not_awaited()
    model.notify.assert_awaited_once()
    context = model.notify.await_args.kwargs['context']
    assert 'TypeError' in context and 'invoke' in context
    assert 'SECRET' not in context and 'PRIVATE' not in context


async def test_outer_processing_exception_is_silent(model, monkeypatch):
    monkeypatch.setattr(model.main, 'process_with_ai', AsyncMock(side_effect=ValueError('SECRET')))
    await model.main._process_safely('context-client', 'Подробнее')
    model.send.assert_not_awaited()
    model.notify.assert_awaited_once()
    assert 'ValueError' in model.notify.await_args.kwargs['context']
    assert 'SECRET' not in model.notify.await_args.kwargs['context']


def test_diagnostic_excerpt_is_bounded_and_hides_secrets(monkeypatch):
    from src.config import settings
    from src.services.model_failure import technical_context
    monkeypatch.setattr(settings, 'deepseek_api_key', 'sk_configured_secret')
    note = technical_context('Тур? +375291111111 https://cdn.invalid/a?token=PRIVATE sk_configured_secret ' + 'x' * 10000,
        'provider_error', 'a' * 32, [dict(attempt=3, stage='invoke', reason='provider_error',
            error_type='APIStatusError', http_status=503, timeout=240, body='PRIVATE_BODY')])
    assert len(note) < 2000
    assert 'HTTP 503' in note and 'APIStatusError' in note
    for secret in ['375291111111', 'PRIVATE', 'sk_configured_secret', 'cdn.invalid']:
        assert secret not in note


@pytest.mark.parametrize('exc,expected', [(TimeoutError('private'), True),
    (ValueError('invalid_model_choices'), True), (ValueError('private'), False),
    (TypeError('private'), False), (RuntimeError('private'), False)])
def test_retry_classifier_does_not_retry_local_errors(exc, expected):
    from src.services.model_failure import retryable_error
    assert retryable_error(exc) is expected


async def test_takeover_during_third_attempt_suppresses_all_delivery(model):
    count = 0
    async def invoke(_, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            model.main._manager_pending['context-client'] = True
        return blank()
    model.invoke.side_effect = invoke
    await model.main.process_with_ai('context-client', 'Подробнее')
    assert model.invoke.await_count == 3
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()


async def test_non_text_handler_exception_is_silent(model, monkeypatch):
    monkeypatch.setattr(model.main, 'get_session', AsyncMock(side_effect=[ValueError('PRIVATE'), model.state]))
    await model.main._process_non_text_safely('context-client', 'Файл', {'types': ['file']})
    model.send.assert_not_awaited()
    model.notify.assert_awaited_once()
    assert 'non_text_processing_failed' in model.notify.await_args.kwargs['context']
    assert 'PRIVATE' not in model.notify.await_args.kwargs['context']


async def test_total_deadline_cancels_before_retry(model, monkeypatch):
    import asyncio
    cancelled = asyncio.Event()
    monkeypatch.setattr(model.main, 'CALL_TIMEOUTS', (0.01, 0.02, 0.04))
    calls = 0
    async def invoke(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        assert cancelled.is_set()
        return response()
    model.invoke.side_effect = invoke
    await asyncio.wait_for(model.main.process_with_ai('context-client', 'ВДП'), 2)
    assert calls == 2
    model.send.assert_awaited_once()
    model.notify.assert_not_awaited()


async def test_external_cancel_never_retries_or_notifies(model):
    import asyncio
    model.invoke.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await model.main.process_with_ai('context-client', 'ВДП')
    model.invoke.assert_awaited_once()
    model.notify.assert_not_awaited()
    model.send.assert_not_awaited()


def test_unexpected_attribute_error_is_not_retryable():
    from src.services.model_failure import retryable_error
    assert not retryable_error(AttributeError('PRIVATE'))


def test_manager_card_explains_action_before_diagnostics():
    from src.services.model_failure import technical_context
    note = technical_context('Пришлите программу ВДП', 'unexpected_response_type', 'a' * 32,
        [dict(attempt=2, stage='invoke', reason='unexpected_response_type',
              response_type='str', elapsed_ms=1500, timeout=120)])
    assert 'не отправлен' in note
    assert 'Ответьте клиенту' in note
    assert note.index('Ответьте клиенту') < note.index('Диагностика:')
    assert 'str' in note and '1.5с' in note


def test_processing_failure_card_does_not_claim_no_delivery():
    from src.services.model_failure import technical_context
    note = technical_context('ВДП', 'processing_exception', 'a' * 32, [])
    assert 'Проверьте переписку перед ответом' in note
    assert 'не отправлен' not in note


async def test_three_total_timeouts_are_final_and_each_call_is_cancelled(model, monkeypatch):
    import asyncio
    monkeypatch.setattr(model.main, 'CALL_TIMEOUTS', (0.01, 0.01, 0.02))
    closed = []
    async def invoke(*args, **kwargs):
        number = len(closed)
        try:
            await asyncio.sleep(10)
        finally:
            closed.append(number)
    model.invoke.side_effect = invoke
    await asyncio.wait_for(model.main.process_with_ai('context-client', 'ВДП'), 2)
    assert closed == [0, 1, 2]
    assert model.invoke.await_count == 3
    model.send.assert_not_awaited()
    model.notify.assert_awaited_once()
    note = model.notify.await_args.kwargs['context']
    assert 'call_deadline' in note


async def test_manager_takeover_during_timeout_cancels_remaining_attempts(model, monkeypatch):
    import asyncio
    monkeypatch.setattr(model.main, 'CALL_TIMEOUTS', (0.01, 0.01, 0.02))
    async def invoke(*args, **kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            model.main._manager_pending['context-client'] = True
    model.invoke.side_effect = invoke
    await asyncio.wait_for(model.main.process_with_ai('context-client', 'ВДП'), 2)
    model.invoke.assert_awaited_once()
    model.send.assert_not_awaited()
    model.notify.assert_not_awaited()
