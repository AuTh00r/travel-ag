"""Persistent work coordinator; existing business dispatch is injected.

No import of main, no network while holding a database transaction. A processing
context captures drafts, never pretends that a deferred send has succeeded.
"""

import asyncio
import hashlib
import json
import math
import sqlite3
import time
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field

from structlog import get_logger

from src.config import settings
from src.exceptions import InstagramError
from src.services.meta_diagnostics import fingerprint, reconcile_failure_fields
from src.db.inbound import InboundStore, StaleWork, timestamp
from src.db.sessions import is_manager_active
from src.services.diagnostic_trace import log_inbound, trace_event

logger = get_logger()
current_processing: ContextVar = ContextVar("inbound_processing", default=None)
current_delivery: ContextVar = ContextVar("inbound_delivery", default=None)
legacy_processing: ContextVar = ContextVar("inbound_legacy_processing", default=None)


@dataclass
class _ScanBudget:
    remaining: int
    deadline: float


class _ScanBudgetExhausted(Exception):
    """Normal scanner boundary; the unread cursor must remain in place."""


def existing_receipt_store():
    """No schema creation when disabled; only bridge an already deployed journal."""
    from src.db import sessions
    path = sessions.DB_PATH
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True, timeout=10)
        try:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbound_deliveries'").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    store = InboundStore() if exists else None
    if store and settings.inbound_recovery_enabled:
        store.allowed = settings.recovery_allows
    return store


def recovery_enabled_for(client):
    return settings.inbound_recovery_enabled and settings.recovery_allows(client)


@dataclass(frozen=True)
class NotificationReceipt:
    deferred: bool = False
    receipts: tuple = ()
    managed: bool = False
    escalation_count: int | None = None


@dataclass
class ProcessingContext:
    store: InboundStore
    job: dict
    session: dict = field(init=False)
    revision: int = field(init=False)
    base_history: list = field(init=False)
    replies: list = field(default_factory=list)
    notifications: list = field(default_factory=list)
    outcome: str | None = None
    reason: str | None = None
    reply_kind: str = "general"
    history_prefix: str = ""
    notification_limited: bool = False
    technical_diagnostic: str = ''

    def __post_init__(self):
        state, self.revision = self.store.read_session(self.client_id)
        self.session = deepcopy(state)
        # Recheck gets the original question exactly once, as the current input.
        self.session["history"] = [entry for entry in state.get("history", [])
            if not (entry.get("_inbound_job") == self.job["id"] and entry.get("role") == "user")]
        self.base_history = deepcopy(self.session["history"])

    @property
    def client_id(self):
        return self.job["client_id"]

    @property
    def allow_silent(self):
        from src.channels.instagram import text_only_ad_event

        payload = text_only_ad_event(json.loads(self.job["payload"]))
        return bool(payload.get("_context_incomplete") and not payload.get("_ad_text_only"))

    def get_session(self):
        if not settings.recovery_allows(self.client_id):
            raise StaleWork("scope_changed")
        state, revision = self.store.read_session(self.client_id)
        if revision != self.revision or is_manager_active(state, settings.manager_takeover_ttl_minutes):
            self.outcome = "manager_cancelled"
            raise StaleWork("session_changed")
        return deepcopy(self.session)

    def save_session(self, state):
        self.get_session()  # staged state must not conceal a concurrent takeover.
        self.session = deepcopy(state)

    def plan_reply(self, text):
        self.get_session()
        self.replies.append(text)
        if self.outcome is None:
            self.outcome = "answered"

    def plan_notification(self, text, destinations, *, decision=None, summary=''):
        self.get_session()
        trace_event('notification_plan', sender_id=self.client_id, job_id=self.job['id'], text=text,
                    destinations=destinations, action=decision.action if decision else 'required',
                    manager_task_id=decision.task_id if decision else None, deferred=True)
        if decision is not None:
            self.notifications.append(dict(text=text, destinations=list(dict.fromkeys(destinations)),
                                           decision=decision, summary=summary))
        else:
            self.notifications.extend((destination, text) for destination in dict.fromkeys(destinations))
        if self.outcome is None:
            self.outcome = "human_only"
        return NotificationReceipt(deferred=True, managed=decision is not None)

    def result(self):
        history = self.session.setdefault("history", [])
        for entry in history[len(self.base_history):]:
            if entry.get("role") == "user":
                entry["_inbound_job"] = self.job["id"]
        # Delivery appends assistant history atomically with a real receipt.
        self.session["history"] = self.base_history + [entry for entry in history[len(self.base_history):]
                                                      if entry.get("role") != "assistant"]
        return {"reply": " ".join(self.replies), "reply_kind": self.reply_kind,
                "outcome": self.outcome or "technical_retry", "history_prefix": self.history_prefix,
                "has_notification": bool(self.notifications), "reason": self.reason,
                "notification_limited": self.notification_limited,
                "error_only": self.outcome == 'failed_final'}


def mark_processing(outcome, reason=None):
    trace_event('processing_outcome', outcome=outcome, reason=reason)
    context = current_processing.get()
    if context is not None and (context.outcome != "technical_retry" or outcome in {'manager_cancelled', 'failed_final'}):
        context.outcome, context.reason = outcome, reason


class RecoveryService:
    def __init__(self, channel, dispatch, merge, finalize_reply, split_reply, manager_pending,
                 store=None, clock=time.time):
        self.channel, self.dispatch, self.merge = channel, dispatch, merge
        self.finalize_reply, self.split_reply = finalize_reply, split_reply
        self.manager_pending = manager_pending
        self.store = store or InboundStore(clock=clock)
        self.store.allowed = settings.recovery_allows
        # Source enrichment runs in one SQLite transaction. Its regrouping must
        # be pure; the initial merge may additionally read persisted story hints.
        self.store.merge = channel.merge_events if hasattr(type(channel), "merge_events") else None
        self.clock = clock
        self.account = settings.instagram_ig_user_id or settings.instagram_page_id or "instagram"
        self.active = {}
        self.processing_ids = set()
        self.delivery_ids = set()
        self.freshness_delays = {}
        self.client_locks = {}
        self.wakeup = asyncio.Event()
        self.scan_lock = asyncio.Lock()
        self._dialog_sync_locks = {}
        self._scan_budget = ContextVar("inbound_scan_budget", default=None)
        self._last_get = 0.0
        self._next_scan = 0.0
        self._last_watchdog = 0.0
        self._last_cleanup = 0.0

    def start(self):
        self.initialize_scope()
        self.store.recover(startup=True)
        self.store.import_legacy_pending()

    def accept(self, events, source="webhook"):
        self.initialize_scope()
        accepted = self.store.persist(self.account, [event for event in events if
            settings.recovery_allows(event.get("sender_id") or event.get("client_id"))], source)
        for event in accepted:
            log_inbound(event, source=source, status='persisted_new')
        accepted_mids = {event.get('mid') for event in accepted}
        for event in events:
            if (settings.recovery_allows(event.get('sender_id') or event.get('client_id'))
                    and event.get('mid') not in accepted_mids):
                # No repeated full history payload for API scans of existing MIDs.
                log_inbound({k: event[k] for k in ('sender_id', 'client_id', 'mid', 'kind') if k in event},
                            source=source, status='existing_or_filtered')
        self.wakeup.set()
        return accepted

    def initialize_scope(self):
        return self.store.initialize(self.account, None if settings.inbound_recovery_scope == "all"
                                     else settings.recovery_clients())

    async def run(self):
        self.start()
        try:
            while True:
                try:
                    await self.tick()
                except Exception:
                    # No exception repr: provider requests can contain secrets.
                    logger.error("inbound.worker.failed")
                self.wakeup.clear()
                try:
                    await asyncio.wait_for(self.wakeup.wait(), timeout=1)
                except TimeoutError:
                    pass
        finally:
            tasks = list(self.active.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def tick(self):
        if self.clock()-self._last_watchdog >= settings.inbound_watchdog_seconds:
            self.store.recover(live_jobs=self.active)
            self._last_watchdog = self.clock()
        for rows in self.store.pending_batches():
            events = [json.loads(row["payload"]) for row in rows]
            self.store.create_jobs(self.account, rows, self.merge(events))
        # Only one live job per client, including during slow STT / vision calls.
        while len(self.processing_ids) < 8:
            job = self.store.claim_due(settings.inbound_lease_seconds)
            if not job:
                break
            task = asyncio.create_task(self.process(job))
            self.active[job["id"]] = task
            self.processing_ids.add(job["id"])
            task.add_done_callback(lambda done, key=job["id"]: self._finished(key, done))
        for job in self.store.delivery_jobs():
            if len(self.delivery_ids) >= 2:
                break
            if job["id"] not in self.active:
                task = asyncio.create_task(self.deliver(job))
                self.active[job["id"]] = task
                self.delivery_ids.add(job["id"])
                task.add_done_callback(lambda done, key=job["id"]: self._finished(key, done))
        if self.clock()-self._last_cleanup >= 3600:
            self.store.cleanup()
            self._last_cleanup = self.clock()

    def _finished(self, key, task):
        self.active.pop(key, None)
        self.processing_ids.discard(key)
        self.delivery_ids.discard(key)
        self.freshness_delays.pop(key, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error("inbound.task.failed", job_id=key)

    async def _heartbeat(self, job):
        while True:
            await asyncio.sleep(settings.inbound_heartbeat_seconds)
            self.store.heartbeat(job, settings.inbound_lease_seconds)

    def _processing_stopped(self, job):
        latest = self.store.get_job(job["id"])
        if not latest or latest["state"] != "processing" or latest["claim"] != job["claim"]:
            return True
        state, _ = self.store.read_session(job["client_id"])
        if self.manager_pending(job["client_id"]) or is_manager_active(state, settings.manager_takeover_ttl_minutes):
            self.store.finish(job, "cancelled", "manager_takeover")
            trace_event('processing_cancelled', sender_id=job['client_id'], job_id=job['id'], reason='manager_takeover')
            return True
        return False

    async def process(self, job):
        if not recovery_enabled_for(job["client_id"]):
            return
        heartbeat = asyncio.create_task(self._heartbeat(job))
        try:
            lock = self.client_locks.setdefault(job["client_id"], asyncio.Lock())
            async with lock:
                if self._processing_stopped(job):
                    return
                payload = json.loads(job["payload"])
                resumable = await self.can_resume(job)
                # Refresh may return False or catch an API error while a manager
                # takes over. Cancellation wins before spending another retry.
                if self._processing_stopped(job):
                    return
                if not resumable:
                    if job["technical_attempts"] < 2:
                        scheduled = self.store.retry(job, "fresh_context_unavailable", self.retry_delays)
                        trace_event('processing_retry', sender_id=job['client_id'], job_id=job['id'],
                                    reason='fresh_context_unavailable', scheduled=scheduled)
                    else:
                        context = ProcessingContext(self.store, job)
                        self.final_failure(context, "fresh_context_unavailable", silent=True)
                        result = context.result()
                        result["error_only"] = True
                        self.store.commit_result(job, context.session, context.revision, result, context.notifications)
                    return
                if self.clock()-payload.get("_original_time", self.clock()) >= 86400:
                    self.store.finish(job, "blocked", "messaging_window_closed")
                    trace_event('processing_skipped', sender_id=job['client_id'], job_id=job['id'],
                                reason='messaging_window_closed')
                    return
                context = ProcessingContext(self.store, job)
                token = current_processing.set(context)
                try:
                    if job["launch"] == "failure":
                        self.final_failure(context, "interrupted_processing")
                    else:
                        await self.dispatch(deepcopy(payload))
                except StaleWork:
                    state, _ = self.store.read_session(job["client_id"])
                    context.outcome = "manager_cancelled" if is_manager_active(state, settings.manager_takeover_ttl_minutes) else "technical_retry"
                    context.reason = "session_changed"
                except Exception as exc:
                    context.outcome, context.reason = "technical_retry", "processing_exception"
                    from src.services.diagnostic_trace import error_details
                    from src.services.model_failure import technical_context
                    details = dict(attempt=0, stage='processing', reason='processing_exception', **error_details(exc))
                    context.technical_diagnostic = technical_context(payload.get('text', ''),
                        'processing_exception', job['id'], [details])
                    trace_event('processing_error', sender_id=job['client_id'], job_id=job['id'], **details)
                finally:
                    current_processing.reset(token)
                result = context.result()
                if not recovery_enabled_for(job["client_id"]):
                    return  # Scope withdrawal holds the job; it is not a technical retry.
                if result["outcome"] == "manager_cancelled" or self.manager_pending(job["client_id"]):
                    self.store.finish(job, "cancelled", "manager_takeover")
                    trace_event('processing_cancelled', sender_id=job['client_id'], job_id=job['id'], reason='manager_takeover')
                    return
                if result["outcome"] == "technical_retry" and job["technical_attempts"] < 2:
                    scheduled = self.store.retry(job, context.reason or "incomplete_processing", self.retry_delays)
                    trace_event('processing_retry', sender_id=job['client_id'], job_id=job['id'],
                                reason=context.reason or 'incomplete_processing', scheduled=scheduled)
                    return
                if result["outcome"] == "technical_retry":
                    self.final_failure(context, context.reason or "retry_exhausted")
                    result = context.result()
                elif result['outcome'] == 'failed_final':
                    self.final_failure(context, context.reason or 'processing_exception')
                    result = context.result()
                self.store.commit_result(job, context.session, context.revision, result, context.notifications)
                trace_event('processing_saved', sender_id=job['client_id'], job_id=job['id'], result=result)
                logger.info("inbound.processing.saved", job_id=job["id"], outcome=result["outcome"],
                            technical_attempts=job["technical_attempts"], semantic_used=job["semantic_used"])
            await self.deliver(self.store.get_job(job["id"]))
        except StaleWork:
            logger.info("inbound.processing.stale", job_id=job["id"])
            current = self.store.get_job(job["id"])
            if current and current["state"] == "processing" and current["claim"] == job["claim"]:
                try:
                    if self._processing_stopped(job):
                        return
                    scheduled = self.store.retry(job, "session_or_source_changed", self.retry_delays)
                    trace_event('processing_retry', sender_id=job['client_id'], job_id=job['id'],
                                reason='session_or_source_changed', scheduled=scheduled)
                except StaleWork:
                    pass  # A newer owner or durable manager cancellation won.
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    @property
    def retry_delays(self):
        return (settings.inbound_retry_first_seconds, settings.inbound_retry_second_seconds)

    def final_failure(self, context, reason, silent=False):
        """Final technical failures never produce an Instagram message."""
        from src.services.handoff_review import HandoffDecision
        from src.services.model_failure import technical_context
        from src.services.telegram_notify import TelegramNotifier, _build_notification_text
        context.outcome, context.reason = "failed_final", reason
        context.replies = []
        if not any(isinstance(n, dict) and n['decision'].action == 'technical' for n in context.notifications):
            context.notifications = []  # Only uncommitted draft plans are replaced.
            notifier = TelegramNotifier()
            if notifier._token and notifier._chat_ids:
                question = json.loads(context.job['payload']).get('text', '')
                summary = context.technical_diagnostic or technical_context(question, reason, context.job['id'], [])
                context.plan_notification(_build_notification_text(context.client_id,
                    context=summary, tag='техническая ошибка'), notifier._chat_ids,
                    decision=HandoffDecision({}, action='technical'), summary=summary)

    async def can_resume(self, job):
        if not recovery_enabled_for(job["client_id"]):
            return False
        if not job["recovered"] and not job["semantic_used"] and not job["technical_attempts"]:
            return True
        if not settings.instagram_reconcile_enabled:
            return False
        try:
            return await self.refresh_client(job["client_id"])
        except Exception as exc:
            logger.warning("inbound.fresh_context.failed", job_id=job["id"])
            self.freshness_delays[job["id"]] = max(settings.instagram_reconcile_interval_seconds,
                                                   getattr(exc, "retry_after_seconds", 0) or 0)
            return False

    async def deliver(self, job):
        if not recovery_enabled_for(job["client_id"]):
            return
        from src.services.telegram_notify import TelegramNotifier

        lock = self.client_locks.setdefault(job["client_id"], asyncio.Lock())
        async with lock:
            if job["state"] != "delivering":
                return
            result = json.loads(job["result"] or '{}')
            if not result.get("error_only") and not await self.can_resume(job):
                self.store.defer_delivery(job, "fresh_context_unavailable",
                    self.freshness_delays.pop(job["id"], settings.instagram_reconcile_interval_seconds))
                return
            deliveries = self.store.deliveries(job["id"])
            for delivery in deliveries:
                if delivery["channel"] != "telegram" or delivery["state"] not in ("ready", "retry_wait"):
                    continue
                await self.send_part(job, delivery, TelegramNotifier())
            job = self.store.get_job(job["id"])
            if job["state"] != "delivering":
                return
            deliveries = self.store.deliveries(job["id"])
            telegram = [delivery for delivery in deliveries if delivery["channel"] == "telegram"]
            if any(delivery["state"] in ("ready", "retry_wait", "sending", "unknown") for delivery in telegram):
                self.store.schedule_delivery(job)
                return
            outcome = "sent" if any(delivery["state"] == "sent" for delivery in telegram) else "failed" if telegram else "none"
            if not any(delivery["channel"] == "instagram" for delivery in deliveries):
                reply = self.finalize_reply(result, outcome)
                trace_event('final_reply', sender_id=job['client_id'], job_id=job['id'],
                            handoff_outcome=outcome, reply=reply)
                self.store.plan_instagram(job, self.split_reply(reply) if reply else [])
            for delivery in self.store.deliveries(job["id"]):
                if delivery["channel"] == "instagram" and delivery["state"] in ("ready", "retry_wait"):
                    if not await self.send_part(job, delivery, None):
                        break
            self.store.complete_delivery(job, settings.inbound_semantic_recheck_seconds)
            self.store.schedule_delivery(job)

    async def send_part(self, job, delivery, notifier, *, legacy_pending=False):
        legacy_allowed = legacy_pending and (not settings.inbound_recovery_enabled or job.get("outcome") == "legacy")
        if (delivery["client_id"] != job["client_id"] or
                (delivery["channel"] == "instagram" and delivery["destination"] != job["client_id"]) or
                not (recovery_enabled_for(job["client_id"]) or legacy_allowed)):
            return False
        payload = json.loads(job["payload"])
        if self.manager_pending(job["client_id"]) or (delivery["channel"] == "instagram" and
                self.clock()-payload.get("_original_time", self.clock()) >= 86400):
            # Use the same session gate as dispatch; never send an expired reply.
            with self.store.connection() as conn:
                conn.execute("UPDATE inbound_jobs SET state='blocked',reason='manager_or_window' WHERE id=?", (job["id"],))
            return False
        if not self.store.start_delivery(job, delivery, settings.manager_takeover_ttl_minutes):
            return False
        status, receipt, reason, delay = "unknown", None, None, settings.default_retry_seconds
        delivery_token = current_delivery.set({"id": delivery["id"], "client_id": job["client_id"],
            "channel": delivery["channel"], "destination": delivery["destination"], "legacy": legacy_allowed,
            "operation": delivery.get('operation', 'send'), "target_message_id": delivery.get('target_message_id'),
            'job_id': job['id'], 'manager_task_id': delivery.get('manager_task_id'),
            'task_revision': delivery.get('task_revision')})
        try:
            if notifier:
                if delivery.get('operation') == 'edit':
                    receipt = await notifier._edit(delivery['payload'], delivery['destination'],
                                                   delivery['target_message_id'], sender_id=job['client_id'])
                else:
                    receipt = await notifier._send(delivery["payload"], delivery["destination"], sender_id=job["client_id"])
            else:
                receipt = await self.channel.send_message(delivery["destination"], delivery["payload"])
            if isinstance(receipt, (str, int)) and str(receipt):
                status, receipt = "sent", str(receipt)
            else:
                reason = "missing_receipt"
        except Exception as exc:
            from src.exceptions import InstagramRateLimitError
            if isinstance(exc, InstagramRateLimitError):
                status, delay = "retry_wait", exc.retry_after_seconds or delay
            else:
                status = getattr(exc, "delivery_status", "unknown")
                delay = getattr(exc, "retry_after_seconds", None) or delay
            reason = "provider_" + status
            if status == "retry_wait" and delivery["attempts"] + 1 >= settings.max_retry_attempts:
                status, reason = "blocked", "delivery_retry_exhausted"
        finally:
            current_delivery.reset(delivery_token)
        try:
            recorded = self.store.record_delivery(delivery, status, receipt, reason, delay)
        except Exception as exc:
            trace_event('receipt_commit_failed', sender_id=job['client_id'], job_id=job['id'],
                        delivery_id=delivery['id'], provisional_status=status, error_type=type(exc).__name__)
            raise
        trace_event('receipt_recorded', sender_id=job['client_id'], job_id=job['id'],
                    delivery_id=delivery['id'], channel=delivery['channel'],
                    manager_task_id=delivery.get('manager_task_id'), operation=delivery.get('operation'),
                    status=recorded, receipt=receipt, part=delivery['part'], attempt=delivery['attempts'] + 1)
        logger.info("inbound.delivery.result", job_id=job["id"], channel=delivery["channel"], status=status)
        return status == "sent"

    async def _get(self, method, *args, **kwargs):
        # Shared scanner + targeted refresh limiter, no burst.
        budget = self._scan_budget.get()
        if budget is not None and (budget.remaining <= 0 or time.monotonic() >= budget.deadline):
            raise _ScanBudgetExhausted
        async with self.scan_lock:
            await asyncio.sleep(max(0, 1.0-(time.monotonic()-self._last_get)))
            if budget is not None:
                if budget.remaining <= 0 or time.monotonic() >= budget.deadline:
                    raise _ScanBudgetExhausted
                budget.remaining -= 1
            try:
                return await method(*args, **kwargs)
            finally:
                self._last_get = time.monotonic()

    async def reconcile_loop(self):
        self._next_scan = max(self._next_scan, self.store.get_sync("next_scan:"+self.account, 0))
        while True:
            if self.clock() >= self._next_scan:
                self._next_scan = self.clock()+settings.instagram_reconcile_interval_seconds
                self.store.set_sync("next_scan:"+self.account, self._next_scan)
                await self.reconcile_tick()
            await asyncio.sleep(1)

    async def reconcile_tick(self):
        state = self.store.get_sync("scan:"+self.account, {"after": None, "dialogs": []})
        deadline = time.monotonic()+settings.instagram_reconcile_deadline_seconds
        budget = _ScanBudget(settings.instagram_reconcile_max_requests, deadline)
        token = self._scan_budget.set(budget)
        stage = "list_conversations"

        async def scan_call(awaitable):
            timer = asyncio.timeout(max(0.01, deadline-time.monotonic()))
            try:
                async with timer:
                    return await awaitable
            except TimeoutError:
                # Windows may fire the timer before the coarse monotonic clock
                # reaches deadline; identify our own timeout by its state.
                if timer.expired() or time.monotonic() >= deadline:
                    raise _ScanBudgetExhausted from None
                raise

        try:
            checked = {}
            if settings.inbound_recovery_scope == "allowlist":
                known = []
                for client in settings.recovery_clients():
                    dialog = self.store.get_sync("dialog:"+client)
                    if (isinstance(dialog, dict) and dialog.get("client_id") == client
                            and isinstance(dialog.get("id"), str) and dialog["id"]):
                        known.append(dialog)
                known.sort(key=lambda dialog: timestamp(dialog.get("checked_at"), 0))
                for dialog in known:
                    if budget.remaining <= 0 or time.monotonic() >= deadline:
                        break
                    if dialog["id"] in checked:
                        continue
                    stage = "priority_dialog"
                    checked[dialog["id"]] = await scan_call(self.sync_dialog(dialog))
                    if not checked[dialog["id"]]:
                        state["incomplete"] = True
                        self.store.set_sync("scan:"+self.account, state)
            while budget.remaining > 0 and time.monotonic() < deadline:
                if not state["dialogs"]:
                    stage = "list_conversations"
                    page = await scan_call(self._get(self.channel.list_conversations, state.get("after")))
                    state = {"after": page.get("after"), "dialogs": page["data"], "end": not page.get("after"),
                             "incomplete": state.get("incomplete", False)}
                    self.store.set_sync("scan:"+self.account, state)
                    if not state["dialogs"] and state["end"]:
                        if not state.get("incomplete"):
                            self.store.set_sync("complete_scan:"+self.account, self.clock())
                        self.store.set_sync("scan:"+self.account, {"after": None, "dialogs": []})
                        break
                if budget.remaining <= 0 or time.monotonic() >= deadline:
                    break
                dialog = state["dialogs"][0]
                stage = "sync_dialog"
                try:
                    if dialog["id"] in checked:
                        complete = checked[dialog["id"]]
                    else:
                        complete = await scan_call(self.sync_dialog(dialog))
                except ValueError:
                    complete = False
                    self.store.set_sync("dialog_gap:"+dialog["id"], {"reason": "incomplete_identity", "checked_at": self.clock()})
                    fields = {}
                    if digest := fingerprint(dialog["id"], "dialog", settings.instagram_app_secret):
                        fields["dialog_fingerprint"] = digest
                    logger.warning("inbound.reconcile.incomplete_identity", **fields)
                checked[dialog["id"]] = complete
                state["incomplete"] = state.get("incomplete", False) or not complete
                state["dialogs"] = state["dialogs"][1:]
                self.store.set_sync("scan:"+self.account, state)
                if not state["dialogs"] and state.get("end"):
                    if not state.get("incomplete"):
                        self.store.set_sync("complete_scan:"+self.account, self.clock())
                    self.store.set_sync("scan:"+self.account, {"after": None, "dialogs": []})
                    break
            self.store.set_sync("scan_failures:"+self.account, 0)
        except _ScanBudgetExhausted:
            self.store.set_sync("scan_failures:"+self.account, 0)
        except Exception as exc:
            if getattr(exc, "category", None) == "invalid_cursor":
                self.store.set_sync("scan:"+self.account, {"after": None, "dialogs": []})
            failures = self.store.get_sync("scan_failures:"+self.account, 0)+1
            self.store.set_sync("scan_failures:"+self.account, failures)
            delay = (30, 120, 300)[min(failures-1, 2)]
            self._next_scan = self.clock()+max(delay, getattr(exc, "retry_after_seconds", 0) or 0)
            self.store.set_sync("next_scan:"+self.account, self._next_scan)
            logger.warning("inbound.reconcile.failed", attempt=failures, stage=stage,
                           **reconcile_failure_fields(exc))
        finally:
            self._scan_budget.reset(token)

    async def sync_dialog(self, dialog):
        client = dialog.get("client_id")
        if not client:
            participants = dialog.get('participants')
            people = participants.get('data') if isinstance(participants, dict) else None
            if not isinstance(people, list):
                raise ValueError('ambiguous_participants')
            ids = []
            own_ids = {self.account, settings.instagram_page_id, settings.instagram_ig_user_id}
            for item in people:
                value = item.get('id') if isinstance(item, dict) else None
                if type(value) not in {str, int}:
                    raise ValueError('ambiguous_participants')
                value = str(value)
                if value in own_ids and value:
                    continue
                if not value.isascii() or not value.isdigit() or len(value) > 128 or int(value) <= 0:
                    raise ValueError('ambiguous_participants')
                if value not in ids:
                    ids.append(value)
            client = ids[0] if len(ids) == 1 else None
        if not client:
            raise ValueError("ambiguous_participants")
        if not settings.recovery_allows(client):
            return True  # Deliberate exclusion, not a failed scan or client checkpoint.
        owned = self._scan_budget.get() is None
        if owned:
            budget = _ScanBudget(settings.instagram_reconcile_max_requests,
                                 time.monotonic()+settings.instagram_reconcile_deadline_seconds)
            token = self._scan_budget.set(budget)

        async def locked():
            async with self._dialog_sync_locks.setdefault(client, asyncio.Lock()):
                if not settings.recovery_allows(client):
                    return True
                return await self._sync_dialog_pages(dialog, client)

        try:
            if owned:
                timer = asyncio.timeout(max(0.01, budget.deadline-time.monotonic()))
                try:
                    async with timer:
                        return await locked()
                except TimeoutError:
                    if not timer.expired() and time.monotonic() < budget.deadline:
                        raise
                    logger.warning("inbound.reconcile.gap")
                    return False
            return await locked()
        except _ScanBudgetExhausted:
            logger.warning("inbound.reconcile.gap")
            if owned:
                return False
            raise
        finally:
            if owned:
                self._scan_budget.reset(token)

    async def _sync_dialog_pages(self, dialog, client):
        previous = self.store.get_sync("dialog:"+client, {})
        baseline = self.store.baseline_for(self.account, client)
        prior_through = timestamp(previous.get("through"), baseline)
        through = max(prior_through, baseline) if math.isfinite(prior_through) else baseline

        def cursor_digest(value):
            if not isinstance(value, str) or not value or len(value) > 8192:
                return None
            try:
                return hashlib.sha256(value.encode()).hexdigest()[:32]
            except UnicodeEncodeError:
                return None

        async def read(after=None):
            args = (dialog["id"],) if after is None else (dialog["id"], after)
            page = await self._get(self.channel.list_conversation_messages, *args)
            rows = page["data"]
            events = normalize_api_messages(rows, client, self.account, self.store,
                                            {settings.instagram_page_id, self.account})
            # Crash here only replays MID: events always precede continuation.
            self.accept(events, "api")
            times = [None if isinstance(row.get("created_time"), bool) else timestamp(row.get("created_time"))
                     for row in rows]
            valid = [value for value in times if value is not None and math.isfinite(value)]
            represented = {event.get("mid") for event in events}
            account_ids = {client, settings.instagram_page_id, self.account} - {""}
            clean = len(valid) == len(rows) and all(
                isinstance(row.get("id"), str) and bool(row["id"]) and row["id"] in represented
                and isinstance(row.get("from"), dict) and str(row["from"].get("id", "")) in account_ids
                for row in rows)
            after = page.get("after")
            if after is not None and cursor_digest(after) is None:
                clean, after = False, None
            return {"low": min(valid, default=None), "high": max(valid, default=None),
                    "clean": clean, "after": after}

        head = await read()
        checked_at = self.clock()

        def save(gap, pending=None):
            checkpoint = {"id": dialog["id"], "client_id": client, "checked_at": checked_at,
                          "gap": gap, "through": through}
            if pending is not None:
                checkpoint["pending"] = pending
            self.store.set_sync("dialog:"+client, checkpoint)

        def reached(page, target):
            # Strict inequality covers unseen MIDs sharing the watermark time.
            return page["after"] is None or (page["low"] is not None and page["low"] < target)

        def new_window():
            return {"id": dialog["id"], "target": through, "upper": max(through, head["high"] or through),
                    "upper_known": head["high"] is not None, "after": head["after"],
                    "dirty": not head["clean"], "seen": []}

        if reached(head, through):
            if head["clean"]:
                through = max(through, head["high"] or through)
            save(not head["clean"])
            if not head["clean"]:
                logger.warning("inbound.reconcile.gap")
            return head["clean"]

        pending = previous.get("pending")
        valid_pending = (isinstance(pending, dict) and pending.get("id") == dialog["id"]
                         and pending.get("target") == through and cursor_digest(pending.get("after")) is not None
                         and type(pending.get("upper")) in (int, float) and math.isfinite(pending["upper"])
                         and pending["upper"] >= through and type(pending.get("dirty")) is bool
                         and type(pending.get("upper_known")) is bool and isinstance(pending.get("seen"), list)
                         and len(pending["seen"]) <= 128
                         and all(isinstance(value, str) and len(value) == 32 for value in pending["seen"]))
        pending = deepcopy(pending) if valid_pending else new_window()
        current_head_covered = not valid_pending
        if valid_pending and head["clean"] and head["low"] is not None and head["low"] < pending["upper"]:
            pending["upper"] = max(pending["upper"], head["high"])
            current_head_covered = True
        save(True, pending)
        while True:
            after = pending["after"]
            digest = cursor_digest(after)
            if digest is None or digest in pending["seen"]:
                save(True)
                logger.warning("inbound.reconcile.message_cursor_repeated")
                return False
            try:
                page = await read(after)
            except InstagramError as exc:
                if getattr(exc, "category", None) != "invalid_cursor":
                    raise
                save(True)
                logger.warning("inbound.reconcile.message_cursor_invalid")
                return False
            pending["seen"] = (pending["seen"]+[digest])[-128:]
            pending["dirty"] = pending["dirty"] or not page["clean"]
            if not pending["upper_known"] and page["high"] is not None:
                pending["upper"], pending["upper_known"] = max(through, page["high"]), True
            if reached(page, pending["target"]):
                if not pending["dirty"]:
                    through = max(through, pending["upper"])
                    if current_head_covered:
                        save(False)
                        return True
                    # Old tail is covered, but a newer disjoint window remains.
                    pending = new_window()
                    current_head_covered = True
                    save(True, pending)
                    continue
                save(True)
                logger.warning("inbound.reconcile.gap")
                return False
            pending["after"] = page["after"]
            save(True, pending)

    async def refresh_client(self, client):
        if not settings.recovery_allows(client):
            return False
        dialog = self.store.get_sync("dialog:"+client)
        if not dialog:
            return False  # Scanner must discover it first, including unknown clients.
        return await self.sync_dialog(dialog)


def normalize_api_messages(messages, client, account, store, account_ids):
    """Adapt proven API fields; classify them with the ordinary webhook parser."""
    from src.channels.instagram import InstagramChannel
    from src.services.story_media import _permalink

    result, channel = [], InstagramChannel()
    account_ids = {value for value in account_ids if value}
    for message in sorted(messages, key=lambda item: (timestamp(item.get("created_time"), 0), str(item.get("id", "")))):
        mid, when = message.get("id"), timestamp(message.get("created_time"))
        source = message.get("from")
        sender = str(source.get("id", "")) if isinstance(source, dict) else ""
        if (not isinstance(mid, str) or not mid or when is None or not math.isfinite(when)
                or isinstance(message.get("created_time"), bool) or sender not in account_ids | {client}):
            continue
        if sender in account_ids:
            kind = "own_echo" if store.own_mid(mid) else "ambiguous_echo" if store.unresolved_send(client) else "manager"
            result.append({"kind": kind, "client_id": client, "mid": mid,
                           "text": message.get("message", ""), "_event_time": when})
            continue
        text = message.get("message") if isinstance(message.get("message"), str) else ""
        incoming = {"mid": mid, "text": text}
        issues, attachments = ["api_context_incomplete"], []
        data = message.get("attachments")
        for attachment in data.get("data", []) if isinstance(data, dict) else []:
            if not isinstance(attachment, dict):
                issues.append("unknown_attachment")
                continue
            kind = attachment.get("type")
            if kind == "unsupported_type":
                attachments.append(deepcopy(attachment))
                continue
            if kind in ("sticker", "gif", "animated_image") or attachment.get("mime_type") == "image/gif":
                attachments.append({"type": "gif", "payload": {}})
                continue
            if kind in ("story_mention", "file", "product", "ig_product", "template", "contact"):
                attachments.append(deepcopy(attachment))
                continue
            for key, kind in (("image_data", "image"), ("video_data", "video"), ("audio_data", "audio")):
                media = attachment.get(key)
                url = media.get("url") if isinstance(media, dict) else None
                if isinstance(url, str) and url.startswith("https://"):
                    attachments.append({"type": kind, "payload": {"url": url}})
                    break
            else:
                issues.append("unknown_attachment")
        shares = message.get("shares")
        for share in shares.get("data", []) if isinstance(shares, dict) else []:
            url = share.get("link") if isinstance(share, dict) else None
            try:
                valid = isinstance(url, str) and len(url) <= 8192 and _permalink(url)
            except ValueError:
                valid = False
            if valid:
                attachments.append({"type": "share", "payload": {"url": url}})
            else:
                issues.append("unavailable_share")
        if attachments:
            incoming["attachments"] = attachments
        reply = message.get("reply_to")
        if isinstance(reply, dict):
            incoming["reply_to"] = deepcopy(reply)
        if message.get("is_unsupported") is True:
            issues.append("unsupported_media")
        # Missing API media is unknown context, not a made-up attachment type.
        if not text and not attachments and not incoming.get("reply_to"):
            incoming["text"] = "[Содержимое сообщения недоступно]"
        events = channel.parse_message_payload({"entry": [{"messaging": [{
            "sender": {"id": client}, "recipient": {"id": account}, "message": incoming,
            "timestamp": when * 1000}]}]}, merge=False)
        for event in events:
            event.update(_event_time=when, _context_incomplete=True, _api_only=True,
                         _source_issues=list(dict.fromkeys(issues)))
        result.extend(events)
    return result
