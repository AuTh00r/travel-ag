"""Full existing business handler, real temporary persistence, fake providers."""
from tests.model_responses import tool_response

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.config import settings
from src.db.inbound import InboundStore
from src.services.inbound_recovery import RecoveryService
from tests.model_responses import manager_data, model_response


@pytest.fixture
def pipeline(monkeypatch):
    import time
    import src.main as main
    from src.services import guard
    from src.services.telegram_notify import TelegramNotifier
    now = [time.time()]
    def clock():
        return now[0]
    for name in ("_locks", "_processing_locks", "_manager_pending", "_inbound_locks"):
        monkeypatch.setattr(main, name, {})
    guard._user_timestamps.clear()
    monkeypatch.setattr(settings, "inbound_recovery_enabled", True)
    monkeypatch.setattr(settings, "inbound_recovery_scope", "all")
    monkeypatch.setattr(settings, "instagram_reconcile_enabled", True)
    monkeypatch.setattr(settings, "ads_media_enabled", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "synthetic-token")
    monkeypatch.setattr(settings, "telegram_manager_chat_id", "manager-one")
    for name in ("telegram_secondary_chat_id", "telegram_tertiary_chat_id", "telegram_extra_chat_id"):
        monkeypatch.setattr(settings, name, "")
    invoke = AsyncMock(return_value=model_response("Программа Эльбруса"))
    monkeypatch.setattr("src.services.llm.get_llm", lambda: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.db.faq_db.search_faq", AsyncMock(return_value=[]))
    monkeypatch.setattr("src.services.tour_loader.get_tours_text", lambda: "Проверенный каталог: Эльбрус, ВДП")
    monkeypatch.setattr(type(main.instagram), "get_username", AsyncMock(return_value="synthetic"))
    send = AsyncMock(return_value="instagram-out")
    notify = AsyncMock(return_value="700")
    monkeypatch.setattr(type(main.instagram), "send_message", send)
    monkeypatch.setattr(TelegramNotifier, "_send", notify)
    store = InboundStore(clock=clock)
    store.initialize("account")
    recovery = RecoveryService(main.instagram, main._dispatch_user_event, main._merge_recovery_events,
        main._finalize_recovery_reply, main._split_reply, lambda client: False, store, clock)
    recovery.account = "account"
    recovery.refresh_client = AsyncMock(return_value=True)
    monkeypatch.setattr(main, "_get_recovery", lambda: recovery)

    def job(text="Эльбрус", **extra):
        event = {"kind": "user", "sender_id": "pipeline-client", "mid": "pipeline-mid", "text": text, "_event_time": now[0], **extra}
        store.persist("account", [event], "api" if extra.get("_api_only") else "webhook")
        now[0] += 5
        rows = store.pending_batches()[0]
        store.create_jobs("account", rows, recovery.merge([json.loads(row["payload"]) for row in rows]))
        return store.claim_due()
    return SimpleNamespace(main=main, recovery=recovery, store=store, now=now, invoke=invoke, send=send, notify=notify, job=job)


async def test_full_pipeline_text_draft_receipt_history(pipeline):
    job = pipeline.job()
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job["id"])["state"] == "done"
    pipeline.invoke.assert_awaited_once()
    pipeline.notify.assert_not_awaited()
    pipeline.send.assert_awaited_once()
    assert [entry["role"] for entry in pipeline.store.read_session("pipeline-client")[0]["history"]] == ["user", "assistant"]


@pytest.mark.parametrize("notify_ok", [True, False])
async def test_phone_claim_and_count_follow_real_receipt(pipeline, notify_ok):
    from src.exceptions import TelegramError
    pipeline.invoke.return_value = model_response("Спасибо!", manager_data("Оставил номер", type="контакт"))
    if not notify_ok:
        pipeline.notify.side_effect = TelegramError("denied", delivery_status="blocked")
    job = pipeline.job("+375291111111")
    await pipeline.recovery.process(job)
    reply = pipeline.send.await_args.args[1]
    assert ("передал ваш номер" in reply) == notify_ok
    assert pipeline.store.read_session("pipeline-client")[0]["escalation_count"] == int(notify_ok)


async def test_three_format_failures_are_final_technical_not_semantic(pipeline):
    broken = tool_response(arguments='{"reply":"wrong"}')
    pipeline.invoke.side_effect = [broken, broken, broken, model_response("Must not run")]
    job = pipeline.job()
    await pipeline.recovery.process(job)
    row = pipeline.store.get_job(job['id'])
    assert row['state'] == 'failed_final' and row['semantic_used'] == 0
    assert row['model_attempts'] == 3 and row['technical_attempts'] == 0
    pipeline.send.assert_not_awaited()
    assert pipeline.notify.await_count == 1
    assert pipeline.invoke.await_count == 3
    assert [e['role'] for e in pipeline.store.read_session('pipeline-client')[0]['history']] == ['user']
    pipeline.now[0] += 1000
    assert pipeline.store.claim_due() is None


@pytest.mark.parametrize("incomplete", [False, True])
async def test_silent_model_recheck_can_answer_without_duplicate_notification(pipeline, incomplete):
    pipeline.invoke.side_effect = [model_response("", manager_data("Неясно, о каком туре вопрос")), model_response("Ответ по контексту")]
    extra = {"_api_only": True, "_context_incomplete": True} if incomplete else {"referral": {"source": "ADS"}}
    if not incomplete:
        pipeline.invoke.side_effect = [model_response('Ответ по тексту')]
    job = pipeline.job("Можно подробнее?", **extra)
    await pipeline.recovery.process(job)
    if not incomplete:
        assert pipeline.store.get_job(job['id'])['state'] == 'done'
        assert pipeline.notify.await_count == 0 and pipeline.send.await_count == 1
        assert pipeline.invoke.await_count == 1
        return
    assert pipeline.store.get_job(job["id"])["state"] == "semantic_wait"
    assert pipeline.notify.await_count == 1
    pipeline.send.assert_not_awaited()
    pipeline.now[0] += 120
    job = pipeline.store.claim_due()
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job["id"])["state"] == "done"
    assert pipeline.notify.await_count == 1
    assert pipeline.send.await_count == 1
    history = pipeline.store.read_session("pipeline-client")[0]["history"]
    assert [entry["role"] for entry in history] == ["user", "assistant"]
    messages = pipeline.invoke.await_args.args[0]
    assert sum(message.type == "human" and "Можно подробнее?" in str(message.content) for message in messages) == 1


@pytest.mark.parametrize("kind", ["story_mention", "unsupported_type", "file", "product"])
async def test_required_human_routes_do_not_get_model_or_semantic_retry(pipeline, kind):
    extra = ({"kind": "user_silent_handoff", "silent_reason": kind} if kind in {"story_mention", "unsupported_type"} else
             {"kind": "user_non_text", "non_text": {"types": [kind], "summary": kind}})
    job = pipeline.job("", **extra)
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job["id"])["state"] == "done"
    pipeline.invoke.assert_not_awaited()
    assert pipeline.notify.await_count == 1
    if kind in {"story_mention", "unsupported_type"}:
        pipeline.send.assert_not_awaited()


async def test_technical_final_fallback_is_not_lost_and_has_no_semantic_timer(pipeline):
    broken = tool_response(arguments='wrong JSON')
    pipeline.invoke.return_value = broken
    job = pipeline.job()
    await pipeline.recovery.process(job)
    row = pipeline.store.get_job(job['id'])
    assert row['state'] == 'failed_final' and row['outcome'] == 'failed_final'
    assert pipeline.notify.await_count == 1
    pipeline.send.assert_not_awaited()
    assert 'invalid_json' in pipeline.notify.await_args.args[0]
    assert pipeline.invoke.await_count == 3


async def test_exhausted_budget_after_crash_sends_only_technical_alert(pipeline):
    job = pipeline.job()
    _, revision = pipeline.store.read_session(job['client_id'])
    for attempt in (1, 2, 3):
        assert pipeline.store.reserve_model_attempt(job, revision) == attempt
    pipeline.now[0] += 181
    pipeline.store.recover(startup=True)
    pipeline.now[0] += 120
    resumed = pipeline.store.claim_due()
    await pipeline.recovery.process(resumed)
    pipeline.invoke.assert_not_awaited()
    pipeline.send.assert_not_awaited()
    pipeline.notify.assert_awaited_once()
    assert 'model_budget_exhausted' in pipeline.notify.await_args.args[0]
    assert pipeline.store.get_job(job['id'])['state'] == 'failed_final'


async def test_actual_sdk_503_then_text_response_uses_third_attempt(pipeline, monkeypatch):
    import httpx
    import openai
    from tests.test_model_tools import wire
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    calls = []
    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={'error': {'message': 'PRIVATE'}})
        if len(calls) == 2:
            return httpx.Response(200, text='PRIVATE_NON_JSON')
        return httpx.Response(200, json=wire())
    # Build the real factory even though pipeline patched its public name.
    from src.services.llm import _model
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        real = _model(settings.deepseek_model)
        root = openai.AsyncOpenAI(api_key='proof-not-secret', http_client=client, max_retries=0)
        real.root_async_client, real.async_client = root, root.chat.completions
        monkeypatch.setattr('src.services.llm.get_llm', lambda: real)
        job = pipeline.job('Виза есть! Пришлите программу тура ВДП')
        await pipeline.recovery.process(job)
    row = pipeline.store.get_job(job['id'])
    assert row['state'] == 'done' and row['model_attempts'] == 3
    log = json.loads(row['model_attempt_log'])
    assert log[0]['http_status'] == 503
    assert log[1]['reason'] == 'unexpected_response_type'
    assert log[1]['response_type'] == 'str'
    assert all(type(item['elapsed_ms']) is int for item in log)
    assert len(calls) == 3
    pipeline.send.assert_awaited_once()
    pipeline.notify.assert_not_awaited()
    assert len(pipeline.store.deliveries(job['id'])) == 1
    assert pipeline.store.deliveries(job['id'])[0]['state'] == 'sent'
    pipeline.now[0] += 1000
    pipeline.store.recover(startup=True)
    assert pipeline.store.claim_due() is None


async def test_unexpected_envelopes_exhaust_once_and_do_not_replay(pipeline):
    from src.exceptions import ProviderResponseError
    pipeline.invoke.side_effect = ProviderResponseError('unexpected_response_type', 'PRIVATE')
    job = pipeline.job()
    await pipeline.recovery.process(job)
    row = pipeline.store.get_job(job['id'])
    assert row['state'] == 'failed_final' and row['model_attempts'] == 3
    pipeline.send.assert_not_awaited()
    pipeline.notify.assert_awaited_once()
    assert 'Ответьте клиенту' in pipeline.notify.await_args.args[0]
    pipeline.now[0] += 1000
    pipeline.store.recover(startup=True)
    assert pipeline.store.claim_due() is None
    assert pipeline.invoke.await_count == 3


async def test_restart_with_two_reserved_attempts_only_runs_third(pipeline):
    job = pipeline.job()
    _, revision = pipeline.store.read_session(job['client_id'])
    for attempt in (1, 2):
        assert pipeline.store.reserve_model_attempt(job, revision) == attempt
    pipeline.now[0] += 181
    pipeline.store.recover(startup=True)
    pipeline.now[0] += 120
    resumed = pipeline.store.claim_due()
    await pipeline.recovery.process(resumed)
    assert pipeline.store.get_job(job['id'])['model_attempts'] == 3
    pipeline.invoke.assert_awaited_once()
    assert pipeline.invoke.await_args.kwargs['timeout'] == 240
    pipeline.send.assert_awaited_once()


async def test_total_deadline_closes_real_sdk_http_body_before_retry(pipeline, monkeypatch):
    import asyncio
    import httpx
    import openai
    from src.services.llm import _model
    from tests.test_model_tools import wire
    closed = asyncio.Event()
    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b' '
            await asyncio.sleep(10)
        async def aclose(self):
            closed.set()
    calls = []
    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, stream=SlowBody(), headers={'content-type': 'application/json'})
        assert closed.is_set()
        return httpx.Response(200, json=wire())
    monkeypatch.setattr(settings, 'deepseek_api_key', 'proof-not-secret')
    # Allow cold LangChain setup to reach HTTP before the first deadline.
    # The response body itself blocks for10s, well beyond the1s budget.
    monkeypatch.setattr(pipeline.main, 'CALL_TIMEOUTS', (1, 2, 4))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        real = _model(settings.deepseek_model)
        root = openai.AsyncOpenAI(api_key='proof-not-secret', http_client=client, max_retries=0)
        real.root_async_client, real.async_client = root, root.chat.completions
        monkeypatch.setattr('src.services.llm.get_llm', lambda: real)
        job = pipeline.job()
        await asyncio.wait_for(pipeline.recovery.process(job), 8)
    row = pipeline.store.get_job(job['id'])
    assert row['state'] == 'done' and row['model_attempts'] == 2
    assert json.loads(row['model_attempt_log'])[0]['reason'] == 'call_deadline'
    assert closed.is_set() and len(calls) == 2
    pipeline.send.assert_awaited_once()
    pipeline.notify.assert_not_awaited()


async def test_technical_alert_delivery_does_not_depend_on_meta_refresh(pipeline):
    pipeline.invoke.return_value = tool_response(arguments='not json')
    pipeline.recovery.refresh_client.return_value = False
    job = pipeline.job()
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job['id'])['state'] == 'failed_final'
    pipeline.notify.assert_awaited_once()
    pipeline.send.assert_not_awaited()


async def test_unknown_technical_notification_never_regenerates_or_repeats(pipeline):
    from src.exceptions import TelegramError
    pipeline.invoke.return_value = tool_response(arguments='not json')
    pipeline.notify.side_effect = TelegramError('uncertain', delivery_status='unknown')
    job = pipeline.job()
    await pipeline.recovery.process(job)
    row = pipeline.store.get_job(job['id'])
    assert row['state'] == 'unknown'
    await pipeline.recovery.deliver(row)
    assert pipeline.invoke.await_count == 3
    pipeline.notify.assert_awaited_once()
    pipeline.send.assert_not_awaited()


async def test_semantic_recheck_technical_failure_keeps_old_business_receipt(pipeline):
    pipeline.invoke.side_effect = [model_response('', manager_data('Неясен источник запроса.')),
                                  tool_response(arguments='not json'), tool_response(arguments='not json'),
                                  tool_response(arguments='not json')]
    job = pipeline.job('Можно подробнее?', _api_only=True, _context_incomplete=True)
    await pipeline.recovery.process(job)
    assert pipeline.store.get_job(job['id'])['state'] == 'semantic_wait'
    original = pipeline.store.deliveries(job['id'])[0]
    pipeline.now[0] += 120
    resumed = pipeline.store.claim_due()
    assert resumed['model_attempts'] == 0
    await pipeline.recovery.process(resumed)
    assert pipeline.invoke.await_count == 4
    assert pipeline.notify.await_count == 2
    assert pipeline.store.get_delivery(original['id'])['receipt'] == original['receipt']
    assert {d['part'] for d in pipeline.store.deliveries(job['id'])} == {0, 1}
    pipeline.send.assert_not_awaited()


async def test_late_plain_webhook_enrichment_uses_real_merge_without_nested_transaction(pipeline):
    job = pipeline.job("Эльбрус", _api_only=True, _context_incomplete=True)
    pipeline.store.commit_result(job, {"history": []}, 0, {"outcome": "answered"}, [])
    pipeline.store.persist("account", [{"kind": "user", "sender_id": "pipeline-client", "mid": "pipeline-mid", "text": "Эльбрус"}])
    assert pipeline.store.get_job(job["id"])["state"] == "retry_wait"
