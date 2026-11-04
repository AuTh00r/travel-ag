from asyncio import CancelledError
from datetime import datetime

from httpx import AsyncClient, ConnectError, ConnectTimeout, PoolTimeout, RequestError
from structlog import get_logger

from src.config import MINSK_TZ, settings
from src.exceptions import TelegramError
from src.services.diagnostic_trace import trace_event, traced_delivery

logger = get_logger()

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TEST_INSTAGRAM_HANDLES = frozenset({"shelter_0", "_shelter_0", "unknovvnoname"})





def _build_notification_text(
    sender_id: str,
    instagram_handle: str | None = None,
    context: str = "",
    client_name: str | None = None,
    client_phone: str | None = None,
    client_email: str | None = None,
    tag: str = "Нужен звонок",
) -> str:
    if sender_id == "tour_sync":
        return context

    now = datetime.now(MINSK_TZ).strftime("%d.%m.%Y %H:%M")

    lines = [
        "\U0001f6a8 Новая эскалация",
        "",
    ]

    if instagram_handle:
        instagram_handle = instagram_handle.strip().lstrip("@")
    if instagram_handle:
        link = f"https://www.instagram.com/{instagram_handle}/"
        lines.append(f"\U0001f464 Клиент: @{instagram_handle}")
        if instagram_handle.casefold() in TEST_INSTAGRAM_HANDLES:
            lines.append("🧪 Тестовый аккаунт")
        lines.append(f"\U0001f517 {link}")
    else:
        lines.append(f"\U0001f464 Клиент: {sender_id}")

    lines.append(f"\U0001f550 {now}")
    lines.append("")
    lines.append("\U0001f4cb Суть:")
    lines.append(context)
    lines.append("")

    contacts = []
    if client_name:
        contacts.append(f"\U0001f464 {client_name}")
    if client_phone:
        contacts.append(f"\U0001f4de {client_phone}")
    if client_email:
        contacts.append(f"\U0001f4e7 {client_email}")
    if contacts:
        lines.append("\U0001f4cb Контакты:")
        lines.extend(contacts)
        lines.append("")

    lines.append(f"\U0001f3f7 Тег: {tag}")

    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self) -> None:
        self._token: str = settings.telegram_bot_token
        self._chat_ids: list[str] = [
            cid
            for cid in [
                settings.telegram_manager_chat_id,
                settings.telegram_secondary_chat_id,
                settings.telegram_tertiary_chat_id,
                settings.telegram_extra_chat_id,
            ]
            if cid
        ]

    async def _send(
        self,
        text: str,
        chat_id: str,
        sender_id: str | None = None,
        tag: str | None = None,
        tour: str | None = None,
    ) -> str | None:
        return await self._request(text, chat_id, sender_id=sender_id, tag=tag, tour=tour)

    async def _edit(self, text, chat_id, message_id, sender_id=None, tag=None):
        if not isinstance(message_id, str) or not message_id.isdigit() or int(message_id) <= 0:
            raise TelegramError('invalid_edit_target', delivery_status='blocked')
        return await self._request(text, chat_id, sender_id=sender_id, tag=tag, target=message_id)

    @traced_delivery('telegram')
    async def _request(self, text, chat_id, *, sender_id=None, tag=None, tour=None, target=None):
        from src.services.inbound_recovery import current_delivery, current_processing
        if current_processing.get() is not None:
            raise TelegramError("recovery_draft_send_blocked", delivery_status="blocked")
        delivery = current_delivery.get()
        if isinstance(delivery, dict) and (delivery["channel"] != "telegram" or
                delivery["destination"] != chat_id or delivery["client_id"] != sender_id or
                delivery.get('operation', 'send') != ('edit' if target else 'send') or
                delivery.get('target_message_id') != target or
                (not delivery.get("legacy") and not (settings.inbound_recovery_enabled and
                 settings.recovery_allows(delivery["client_id"])))):
            raise TelegramError("recovery_scope_blocked", delivery_status="blocked")
        if target and not isinstance(delivery, dict):
            raise TelegramError('untracked_edit_blocked', delivery_status='blocked')
        url = TELEGRAM_API_URL.format(token=self._token)
        if target:
            url = url.removesuffix('sendMessage') + 'editMessageText'
        try:
            async with AsyncClient(timeout=15) as client:
                response = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    **({'message_id': int(target)} if target else {}),
                    **({"link_preview_options": {"is_disabled": True}} if sender_id == "tour_sync" else {}),
                })
        except RequestError as exc:
            # The request URL contains a bot token; do not propagate it into logs.
            status = "retry_wait" if isinstance(exc, (ConnectError, ConnectTimeout, PoolTimeout)) else "unknown"
            raise TelegramError("Telegram notification transport failed", delivery_status=status) from None
        if response.status_code != 200:
            if target and response.status_code == 400:
                try:
                    unchanged = response.json()
                    if (unchanged.get('ok') is False and unchanged.get('error_code') == 400
                            and str(unchanged.get('description', '')).startswith('Bad Request: message is not modified')):
                        return target  # Idempotent edit of this exact confirmed target.
                except (ValueError, AttributeError):
                    pass
            logger.error(
                "telegram.send.failed",
                chat_id=chat_id,
                status=response.status_code,
            )
            raise TelegramError(
                f"Telegram API error: HTTP {response.status_code}",
                delivery_status="retry_wait" if response.status_code == 429 else "unknown" if response.status_code >= 500 else "blocked",
                retry_after_seconds=self._retry_after(response) if response.status_code == 429 else None,
            )
        try:
            receipt = response.json()
        except ValueError:
            raise TelegramError("Telegram notification receipt is invalid") from None
        if not isinstance(receipt, dict) or receipt.get("ok") is not True:
            raise TelegramError("Telegram did not confirm notification delivery")
        message_id = (receipt.get("result") or {}).get("message_id")
        if target and (type(message_id) is not int or str(message_id) != target):
            raise TelegramError('Telegram edit receipt is invalid')
        logger.info(
            "telegram.updated" if target else "telegram.sent",
            chat_id=chat_id,
            sender_id=sender_id,
            tag=tag,
            tour=tour,
        )
        return str(message_id) if isinstance(message_id, int) and not isinstance(message_id, bool) else None

    @staticmethod
    def _retry_after(response):
        try:
            value = response.json().get("parameters", {}).get("retry_after")
            return float(value) if value is not None else None
        except (ValueError, TypeError, AttributeError):
            return None

    async def notify_manager(
        self,
        sender_id: str,
        instagram_handle: str | None = None,
        context: str = "",
        client_name: str | None = None,
        client_phone: str | None = None,
        client_email: str | None = None,
        tag: str = "Нужен звонок",
        decision=None,
    ):
        if not self._token or not self._chat_ids:
            raise TelegramError(
                "TELEGRAM_BOT_TOKEN или TELEGRAM_MANAGER_CHAT_ID не настроены"
            )

        text = _build_notification_text(
            sender_id=sender_id,
            instagram_handle=instagram_handle,
            context=context,
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            tag=tag,
        )
        from src.services.inbound_recovery import NotificationReceipt, current_processing
        processing = current_processing.get()
        if processing is not None and processing.client_id == sender_id:
            return processing.plan_notification(text, self._chat_ids, decision=decision, summary=context)
        trace_event('notification_plan', sender_id=sender_id, text=text, destinations=self._chat_ids,
                    action=decision.action if decision else 'required',
                    manager_task_id=decision.task_id if decision else None, deferred=False)
        if decision is not None:
            return await self._notify_task(sender_id, text, context, decision, tag)

        last_exc = None
        delivered = 0
        receipts = []
        for cid in self._chat_ids:
            try:
                receipt = await self._send(text=text, chat_id=cid, sender_id=sender_id, tag=tag)
                receipts.append((cid, receipt))
                delivered += 1
            except TelegramError as e:
                last_exc = e
        if not delivered and last_exc:
            raise last_exc
        if last_exc:
            logger.warning("telegram.partial_delivery", sender_id=sender_id,
                           delivered=delivered, failed=len(self._chat_ids) - delivered)
        return NotificationReceipt(receipts=tuple(receipts))

    async def _notify_task(self, sender_id, text, summary, decision, tag):
        from uuid import uuid4
        from src.db.inbound import InboundStore
        from src.db.manager_tasks import plan
        from src.services.inbound_recovery import legacy_processing

        store = InboundStore()
        event = legacy_processing.get() or {}
        source_key = 'mid:' + event['mid'] if event.get('mid') else 'call:' + uuid4().hex
        if decision.action == 'technical':
            source_key = 'technical:' + source_key
        with store.connection() as conn:
            _, operations = plan(conn, client=sender_id, summary=summary, decision=decision,
                                 text=text, destinations=self._chat_ids, now=store.clock(), source_key=source_key)
        return await self.deliver_task_operations(sender_id, operations, store=store, tag=tag)

    async def deliver_task_operations(self, sender_id, operations, *, store, tag='консультация'):
        from src.db.manager_tasks import begin_legacy
        from src.db.sessions import effective_escalation_count
        from src.services.inbound_recovery import NotificationReceipt, current_delivery

        receipts, last_exc = [], None
        for operation in operations:
            if operation['state'] == 'sent':
                receipts.append((operation['destination'], operation['receipt']))
                continue
            if operation['state'] not in {'ready', 'retry_wait'} or not begin_legacy(store, operation):
                last_exc = TelegramError('manager_notification_unconfirmed')
                continue
            token = current_delivery.set({**operation, 'legacy': True})
            status, receipt = 'unknown', None
            try:
                if operation['operation'] == 'edit':
                    receipt = await self._edit(operation['payload'], operation['destination'],
                                               operation['target_message_id'], sender_id=sender_id, tag=tag)
                else:
                    receipt = await self._send(operation['payload'], operation['destination'], sender_id=sender_id, tag=tag)
                if isinstance(receipt, (str, int)) and str(receipt).isdigit() and int(receipt) > 0:
                    status = 'sent'
                else:
                    last_exc = TelegramError('manager_notification_missing_receipt')
            except CancelledError:
                store.record_delivery(operation, 'unknown', reason='interrupted_send')
                trace_event('receipt_recorded', sender_id=sender_id, channel='telegram',
                            delivery_id=operation['id'], manager_task_id=operation['manager_task_id'], status='unknown')
                raise
            except TelegramError as exc:
                last_exc, status = exc, exc.delivery_status
            except Exception:
                last_exc = TelegramError('manager_notification_unconfirmed')
            finally:
                current_delivery.reset(token)
            if status == 'retry_wait' and operation['attempts'] + 1 >= settings.max_retry_attempts:
                status = 'blocked'
            try:
                recorded = store.record_delivery(operation, status, receipt,
                    reason=None if status == 'sent' else 'manager_notification_' + status,
                    delay=getattr(last_exc, 'retry_after_seconds', None) or settings.default_retry_seconds)
            except Exception as exc:
                trace_event('receipt_commit_failed', sender_id=sender_id, channel='telegram',
                            delivery_id=operation['id'], manager_task_id=operation['manager_task_id'],
                            provisional_status=status, error_type=type(exc).__name__)
                raise
            trace_event('receipt_recorded', sender_id=sender_id, channel='telegram',
                        delivery_id=operation['id'], manager_task_id=operation['manager_task_id'],
                        task_revision=operation['task_revision'], operation=operation['operation'],
                        status=recorded, receipt=receipt)
            if status == 'sent':
                receipts.append((operation['destination'], str(receipt)))
        if not receipts:
            raise last_exc or TelegramError('manager_notification_unconfirmed')
        if last_exc:
            logger.warning('telegram.partial_delivery', sender_id=sender_id,
                           delivered=len(receipts), failed=len(operations) - len(receipts))
        state, _ = store.read_session(sender_id)
        return NotificationReceipt(receipts=tuple(receipts), managed=True,
                                   escalation_count=effective_escalation_count(state, settings.escalation_reset_hours))

