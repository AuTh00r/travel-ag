"""Private, bounded, best-effort processing trace. Never a queue or receipt store."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import hashlib
import inspect
from itertools import islice
import json
import logging
from pathlib import Path
import re
import threading
from uuid import uuid4

from langchain_core.messages import BaseMessage
from structlog import get_logger
from structlog.contextvars import bind_contextvars, reset_contextvars

from src.config import settings
from src.services import llm_response_log as response_log

LOG_PATH = Path(__file__).resolve().parents[2] / 'logs/deepseek-trace.jsonl'
MAX_LOG_BYTES = 20 * 1024 * 1024
BACKUP_COUNT = 7
MAX_RECORD_BYTES = 512 * 1024
MAX_TEXT_CHARS = 250_000
MAX_ITEMS = 128
MAX_DEPTH = 16
_lock = threading.RLock()
_logger = None
_scope = ContextVar('diagnostic_scope', default=None)
_SECRETS = re.compile(r'(?:token|secret|password|authorization|cookie|api.?key|private.?key)', re.I)
_MEDIA_KEYS = response_log.MEDIA_CONTENT_KEYS
_MEDIA_TYPES = {'image', 'image_url', 'input_image', 'audio', 'input_audio', 'video', 'file', 'input_file'}
_TOKEN_COUNTS = {'input_tokens', 'output_tokens', 'total_tokens', 'max_tokens', 'max_completion_tokens',
                 'prompt_tokens', 'completion_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'}


class _TraceHandler(response_log._ResponseHandler):
    def shouldRollover(self, record):
        if self.stream is None:
            self.stream = self._open()
        self.stream.seek(0, 2)
        return self.maxBytes > 0 and self.stream.tell() + len((self.format(record) + '\n').encode('utf-8')) >= self.maxBytes


def fingerprint(value):
    return hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:16]


def _warn():
    try:
        get_logger(__name__).warning('diagnostic.trace.failed')
    except Exception:
        pass


def close_trace_log():
    global _logger
    with _lock:
        if _logger:
            for handler in _logger.handlers[:]:
                _logger.removeHandler(handler)
                handler.close()
        _logger = None


def _get_logger():
    global _logger
    with _lock:
        if _logger and Path(_logger.handlers[0].baseFilename) == LOG_PATH.resolve():
            return _logger
        close_trace_log()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = _TraceHandler(LOG_PATH, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT,
                                encoding='utf-8', delay=True)
        handler.setFormatter(logging.Formatter('%(message)s'))
        _logger = logging.Logger('deepseek.private_trace', level=logging.INFO)
        _logger.propagate = False
        _logger.addHandler(handler)
        return _logger


def _media(value, kind='media'):
    # Never stringify an arbitrary object or serialize an entire media block.
    raw = value if isinstance(value, (str, bytes)) else None
    if isinstance(value, dict):
        source = value.get('url') or value.get('data')
        raw = source if isinstance(source, (str, bytes)) else None
    return {'kind': kind, 'content_omitted': True,
            **({'items': len(value)} if isinstance(value, (list, tuple)) else {}),
            **({'chars' if isinstance(raw, str) else 'bytes': len(raw),
                'sha256': hashlib.sha256(raw.encode('utf-8') if isinstance(raw, str) else raw).hexdigest()}
               if raw is not None else {})}


def sanitize(value, *, depth=0, seen=None):
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        return value if value == value and abs(value) != float('inf') else '[NON_FINITE]'
    if isinstance(value, bytes):
        return _media(value, 'binary')
    if isinstance(value, str):
        if re.search(r'data:[^,\s]+,', value, re.I):
            return _media(value, 'data_url_text')
        text = response_log._redact(value)
        if len(text) > MAX_TEXT_CHARS:
            return {'text': text[:MAX_TEXT_CHARS], 'truncated': True, 'chars': len(text),
                    'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
        return text
    if not isinstance(value, (dict, list, tuple)):
        return '[UNSUPPORTED_OBJECT]'
    if depth >= MAX_DEPTH:
        return {'omitted': True, 'reason': 'depth_limit'}
    seen = set() if seen is None else seen
    if id(value) in seen:
        return {'omitted': True, 'reason': 'cycle'}
    seen.add(id(value))
    try:
        if isinstance(value, dict):
            kind = value.get('type')
            if isinstance(kind, str) and kind in _MEDIA_TYPES:
                source = value.get('image_url') or value.get('input_audio') or value.get('url')
                detail = source.get('detail') if isinstance(source, dict) else None
                if isinstance(source, dict):
                    source = source.get('url') or source.get('data')
                description = _media(source, kind)
                if isinstance(detail, str) and detail in {'original', 'high', 'low', 'auto'}:
                    description['detail'] = detail
                return description
            result = {}
            for key, item in islice(value.items(), MAX_ITEMS):
                if not isinstance(key, str):
                    continue
                safe_key = response_log._redact(key)[:100]
                if key in _TOKEN_COUNTS and (item is None or type(item) is int):
                    result[safe_key] = item
                elif _SECRETS.search(key):
                    result[safe_key] = '[REDACTED]'
                elif key.lower() in _MEDIA_KEYS:
                    result[safe_key] = _media(item)
                elif key.lower() in {'sender_id', 'recipient_id', 'client_id', 'chat_id', 'destination', 'mid'}:
                    result[safe_key] = {'fingerprint': fingerprint(item)} if isinstance(item, (str, int)) else '[OMITTED_ID]'
                elif key == 'related_mids' and isinstance(item, list):
                    result[safe_key] = [fingerprint(mid) for mid in item[:MAX_ITEMS] if isinstance(mid, str)]
                else:
                    result[safe_key] = sanitize(item, depth=depth + 1, seen=seen)
            if len(value) > MAX_ITEMS:
                result['__omitted_fields__'] = len(value) - MAX_ITEMS
            return result
        result = [sanitize(item, depth=depth + 1, seen=seen) for item in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            result.append({'omitted_items': len(value) - MAX_ITEMS})
        return result
    finally:
        seen.remove(id(value))


def correlation(sender_id=None):
    result = dict(_scope.get() or {})
    if isinstance(sender_id, str):
        sender_hash = hashlib.sha256(sender_id.encode('utf-8')).hexdigest()[:12]
        if result.get('sender_hash') not in (None, sender_hash):
            result = {}
        result['sender_hash'] = sender_hash
    from src.services.inbound_recovery import current_delivery, current_processing, legacy_processing
    processing, delivery, legacy = current_processing.get(), current_delivery.get(), legacy_processing.get()
    if processing is not None and (sender_id is None or processing.client_id == sender_id):
        result['job_id'] = processing.job['id']
    if isinstance(delivery, dict) and (sender_id is None or delivery.get('client_id') == sender_id):
        for name in ('id', 'job_id', 'manager_task_id', 'task_revision', 'operation'):
            if delivery.get(name) is not None:
                result['delivery_id' if name == 'id' else name] = delivery[name]
    if isinstance(legacy, dict) and (sender_id is None or
                                    (legacy.get('sender_id') or legacy.get('client_id')) == sender_id):
        mids = [legacy.get('mid'), *legacy.get('related_mids', [])]
        result['mid_hashes'] = [fingerprint(mid) for mid in dict.fromkeys(mids) if isinstance(mid, str)]
    return result


def _encode(row):
    encoded = json.dumps(row, ensure_ascii=False, allow_nan=False)
    size = len(encoded.encode('utf-8'))
    if size <= MAX_RECORD_BYTES:
        return encoded
    content = json.dumps(row['data'], ensure_ascii=False, allow_nan=False)
    row = {**row, 'truncated': True, 'data': {'omitted': True, 'reason': 'encoded_record_limit',
        'original_record_bytes': size, 'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(), 'preview': ''}}
    available = max(0, (MAX_RECORD_BYTES - len(json.dumps(row, ensure_ascii=False).encode('utf-8')) - 1) // 2)
    row['data']['preview'] = content.encode('utf-8')[:available].decode('utf-8', errors='ignore')
    encoded = json.dumps(row, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode('utf-8')) > MAX_RECORD_BYTES:
        row['data'].pop('preview', None)
        encoded = json.dumps(row, ensure_ascii=False)
    if len(encoded.encode('utf-8')) > MAX_RECORD_BYTES:
        encoded = '{"truncated":true}'
    return encoded


def trace_event(event, *, sender_id=None, **data):
    if not settings.deepseek_response_log_enabled:
        return
    try:
        row = {'timestamp': datetime.now(timezone.utc).isoformat(),
               'event': event if isinstance(event, str) and re.fullmatch(r'[a-z_.]{1,80}', event) else 'unknown',
               'correlation': sanitize(correlation(sender_id)), 'data': sanitize(data)}
        encoded = _encode(row)
        with _lock:
            logger = _get_logger()
            record = logger.makeRecord(logger.name, logging.INFO, '', 0, encoded, (), None)
            logger.handle(record)
        if getattr(record, 'response_log_failed', False):
            _warn()
    except Exception:
        _warn()


@contextmanager
def trace_scope(sender_id=None, event=None, **identifiers):
    """Diagnostic context only; never read or mutate sessions/queues."""
    if not settings.deepseek_response_log_enabled:
        yield
        return
    token, bound = None, None
    try:
        fields = correlation(sender_id)
        fields.update({key: value for key, value in identifiers.items()
                       if key in {'pending_id', 'job_id', 'delivery_id', 'manager_task_id'}
                       and type(value) in (str, int)})
        mids = [event.get('mid'), *event.get('related_mids', [])] if isinstance(event, dict) else []
        if mids:
            fields['mid_hashes'] = [fingerprint(mid) for mid in dict.fromkeys(mids) if isinstance(mid, str)]
        fields['trace_id'] = (fields.get('trace_id') or fields.get('job_id')
                              or ('mid-' + fields['mid_hashes'][0] if fields.get('mid_hashes') else uuid4().hex))
        token = _scope.set(fields)
        bound = bind_contextvars(diagnostic_trace_id=fields['trace_id'])
    except Exception:
        _warn()
    try:
        yield
    finally:
        try:
            if token is not None:
                _scope.reset(token)
            if bound is not None:
                reset_contextvars(**bound)
        except Exception:
            _warn()


def traced_flow(stage):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            if not settings.deepseek_response_log_enabled:
                return await function(*args, **kwargs)
            try:
                arguments = dict(inspect.signature(function).bind(*args, **kwargs).arguments)
                arguments.pop('self', None)
                event = arguments.get('ev')
                sender = arguments.get('sender_id') or (event or {}).get('sender_id')
            except Exception:
                _warn()
                return await function(*args, **kwargs)
            with trace_scope(sender, event):
                trace_event(stage + '.started', sender_id=sender, input=arguments)
                try:
                    result = await function(*args, **kwargs)
                except BaseException as exc:
                    trace_event(stage + '.failed', sender_id=sender, error_type=type(exc).__name__)
                    raise
                trace_event(stage + '.finished', sender_id=sender)
                return result
        return wrapped
    return decorate


def log_inbound(event, *, source, status='received'):
    try:
        with trace_scope(event.get('sender_id') or event.get('client_id'), event):
            trace_event('inbound_event', sender_id=event.get('sender_id') or event.get('client_id'),
                        source=source, status=status, incoming=event)
    except Exception:
        _warn()


def traced_delivery(channel):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            if not settings.deepseek_response_log_enabled:
                return await function(*args, **kwargs)
            try:
                arguments = dict(inspect.signature(function).bind(*args, **kwargs).arguments)
                arguments.pop('self', None)
                sender = arguments.get('sender_id') or arguments.get('recipient_id')
            except Exception:
                _warn()
                return await function(*args, **kwargs)
            with trace_scope(sender):
                trace_event('delivery_started', sender_id=sender, channel=channel, payload=arguments)
                try:
                    receipt = await function(*args, **kwargs)
                except BaseException as exc:
                    trace_event('provider_result', sender_id=sender, channel=channel,
                                **error_details(exc))
                    raise
                trace_event('provider_result', sender_id=sender, channel=channel,
                            status='accepted' if receipt is not None else 'unknown', receipt=receipt)
                return receipt
        return wrapped
    return decorate


def error_details(exc):
    """Useful error category/status, never the exception body or repr."""
    try:
        status = getattr(exc, 'delivery_status', 'unknown')
        http_status = getattr(exc, 'status_code', None)
        details = {'error_type': type(exc).__name__,
                'status': status if status in {'unknown', 'blocked', 'retry_wait', 'cancelled'} else 'unknown',
                'http_status': http_status if type(http_status) is int else None}
        from src.exceptions import ProviderResponseError
        if isinstance(exc, ProviderResponseError):
            response_type = exc.response_type
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', response_type):
                details['response_type'] = response_type
        frame = exc.__traceback__
        while frame is not None:
            module = frame.tb_frame.f_globals.get('__name__', '')
            if isinstance(module, str) and re.fullmatch(r'src\.[a-zA-Z0-9_.]+', module):
                details['origin'] = f'{module}:{frame.tb_lineno}'
            frame = frame.tb_next
        return details
    except Exception:
        return {'error_type': 'unknown', 'status': 'unknown'}


def log_model_request(messages, *, sender_id, request_id, phase, attempt, model, llm, parent_request_id=None,
                      timeout=None):
    if not settings.deepseek_response_log_enabled:
        return
    try:
        snapshots = []
        for message in messages:
            if isinstance(message, BaseMessage):
                snapshots.append({'role': message.type, 'content': message.content})
            else:
                snapshots.append('[UNSUPPORTED_MESSAGE]')
        options = {}
        for name in ('model_name', 'temperature', 'max_tokens', 'request_timeout', 'max_retries', 'model_kwargs', 'extra_body'):
            value = getattr(llm, name, None)
            if value is None or type(value) in (str, bool, int, float, dict, list):
                options[name] = value
        if timeout is not None:
            options['request_timeout'] = timeout
        trace_event('model_request', sender_id=sender_id, request_id=request_id,
                    parent_request_id=parent_request_id, phase=phase, attempt=attempt, model=model,
                    messages=snapshots, options=options)
    except Exception:
        _warn()
