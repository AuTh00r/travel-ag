"""Bounded local response journal; never propagate model text to ordinary logs."""

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from structlog import get_logger

from src.config import settings
from src.services.llm import TOOL_RESPONSE_ERRORS

LOG_PATH = Path(__file__).resolve().parents[2] / 'logs' / 'deepseek-responses.jsonl'
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 7
MAX_RESPONSE_CHARS = 64_000
MEDIA_CONTENT_KEYS = frozenset({'base64', 'b64_json', 'b64', 'bytes', 'buffer', 'input_audio',
                                'image_url', 'image_urls', 'images', 'audio', 'video'})
_ENCODED_MEDIA_FIELD = re.compile(r'''["'](?:''' + '|'.join(sorted(MEDIA_CONTENT_KEYS)) + r''')["']\s*:''', re.I)
_lock = threading.RLock()
_logger: logging.Logger | None = None
_FINISH = {'stop', 'length', 'content_filter', 'tool_calls', 'function_call',
           'insufficient_system_resource', 'unknown'}
_VALIDATION = {'valid', 'invalid_type', 'response_too_long',
               'empty_response', 'invalid_json', 'duplicate_fields', 'invalid_fields',
               'invalid_field_type', 'invalid_manager_type', 'context_too_long',
               'empty_context', 'empty_reply', 'name_too_long', 'service_marker',
               'response_truncated', 'provider_error', 'invalid_review'} | TOOL_RESPONSE_ERRORS


class _ResponseHandler(RotatingFileHandler):
    def _open(self):
        descriptor = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        return os.fdopen(descriptor, self.mode, encoding='utf-8', errors='backslashreplace', newline='\n')

    def handleError(self, record):
        # Standard handleError prints record.msg (the private response) to stderr.
        record.response_log_failed = True


def close_response_log() -> None:
    global _logger
    with _lock:
        if _logger is not None:
            for handler in _logger.handlers[:]:
                _logger.removeHandler(handler)
                handler.close()
        _logger = None


def _get_logger() -> logging.Logger:
    global _logger
    with _lock:
        if _logger is not None and Path(_logger.handlers[0].baseFilename) == LOG_PATH.resolve():
            return _logger
        close_response_log()
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handler = _ResponseHandler(LOG_PATH, maxBytes=MAX_LOG_BYTES,
                                   backupCount=BACKUP_COUNT, encoding='utf-8', delay=True)
        handler.setFormatter(logging.Formatter('%(message)s'))
        result = logging.Logger('deepseek.private_responses', level=logging.INFO)
        result.propagate = False
        result.addHandler(handler)
        _logger = result
        return result


def _redact_plain(text: str) -> str:
    secrets = [value for name, value in settings.model_dump().items()
               if isinstance(value, str) and value
               and name.endswith(('_token', '_secret', '_api_key'))]
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'data:[^\s\"\x27<>]+(?:[ \t\r\n]+[A-Za-z0-9+/=]+(?=\s|[\"\x27<>]|$))*',
                  '[OMITTED_DATA_URL]', text, flags=re.IGNORECASE)
    text = re.sub(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----',
                  '[REDACTED_PRIVATE_KEY]', text, flags=re.DOTALL)

    def redact_url(match):
        original = match[0]
        url = urlsplit(original.replace('\\/', '/'))
        host = (url.hostname or '').lower()
        keys = {key.lower() for key, _ in parse_qsl(url.query)}
        sensitive = {'access_token', 'auth_token', 'token', 'api_key', 'key', 'signature', 'sig',
                     'auth', 'authorization', 'hmac', 'expires', 'policy', 'key-pair-id'}
        if (url.username or url.password or host.endswith(('cdninstagram.com', 'fbcdn.net', 'fbsbx.com'))
                or (host == 'api.telegram.org' and re.search(r'/(?:file/)?bot\d+:[^/]+', url.path))
                or keys & sensitive or any(key.startswith(('x-amz-', 'x-goog-'))
                    or re.search(r'token|secret|signature|hmac|authorization|password|api[-_]?key|credential', key)
                    for key in keys)
                or any(re.search(r'https?[:%]', unquote(value), re.I) for _, value in parse_qsl(url.query))):
            return '[REDACTED_URL]'
        return original

    text = re.sub(r'https?:\\?/\\?/[^\s\"\x27<>]+', redact_url, text, flags=re.IGNORECASE)
    text = re.sub(r'(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+', r'\1 [REDACTED]', text)

    def redact_value(match):
        value = match[2]
        quote = value[0] if value[0] in {'"', "'"} else ''
        return match[1] + quote + '[REDACTED]' + quote

    text = re.sub(r'''(?i)(\b[A-Za-z0-9_-]*(?:token|secret|password|authorization|api[-_]?key|cookie|private[-_]?key)[A-Za-z0-9_-]*["']?\s*[:=]\s*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s"',}\]]+)''',
                  redact_value, text)
    return text


def _redact(text: str) -> str:
    # Inspect a decoded *view* only. Never repair/re-encode malformed model JSON.
    # Encoded sensitive blobs are omitted wholesale, preserving the rest verbatim.
    view = text
    for _ in range(5):
        decoded = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match[1], 16)), view)
        decoded = decoded.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
        if decoded == view:
            break
        view = decoded
    if _ENCODED_MEDIA_FIELD.search(view):
        return '[OMITTED_ENCODED_MEDIA_TEXT]'
    if view != text and _redact_plain(view) != view:
        return '[OMITTED_ENCODED_SENSITIVE_TEXT]'
    if view != text and re.search(r'\\(?:u[0-9a-fA-F]{4}|["\\])', view):
        return '[OMITTED_DEEPLY_ENCODED_TEXT]'
    return _redact_plain(text)


def _warn() -> None:
    try:
        get_logger(__name__).warning('llm.response_log.failed')
    except Exception:
        # A failed diagnostic sink must not turn a received answer into a failure.
        return


def catalog_metadata(text: str) -> dict:
    """Describe the exact supplied catalog, never read a possibly newer snapshot."""
    tours = []
    current = None
    for line in text.splitlines():
        title = re.fullmatch(r'=== ТУР: (.+) ===', line.strip())
        if title and len(tours) < 100:
            name = re.sub(r'https?://\S+', '[URL]', _redact(title[1]))[:180]
            current = {'name': name, 'dates': [], 'available': None}
            tours.append(current)
        elif current is not None and line.startswith('Когда (ближайшие свободные даты):'):
            current['dates'] = re.findall(r'\b\d{2}\.\d{2}\.\d{4}\b', line)[:40]
            current['available'] = True
        elif current is not None and line.startswith('Свободных дат нет:'):
            current['available'] = False
    return {'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'chars': len(text), 'tours': tours}


def log_llm_response(content: object, *, request_id: str, sender_id: str, attempt: int,
                     model: str, route: str, validation_reason: str, response_fields: dict,
                     phase: str = 'primary', parent_request_id: str | None = None,
                     catalog: dict | None = None) -> None:
    """Record only received content and explicit metadata, with best-effort writes."""
    if not settings.deepseek_response_log_enabled:
        return
    try:
        cleaned, omitted = None, not isinstance(content, str)
        if isinstance(content, str):
            try:
                cleaned = _redact(content)
            except Exception:
                omitted = True
                _warn()
        truncated = cleaned is not None and len(cleaned) > MAX_RESPONSE_CHARS
        trace = request_id if re.fullmatch(r'[a-f0-9]{32}', request_id) else 'unknown'
        row = {
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'request_id': trace,
            'phase': phase if phase in {'primary', 'handoff_review'} else 'unknown',
            'sender_hash': hashlib.sha256(sender_id.encode('utf-8')).hexdigest()[:12],
            'attempt': attempt if type(attempt) is int and 1 <= attempt <= 3 else None,
            'model': model if re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', model) else 'unknown',
            'route': route if route in {'text', 'vision', 'ad_text', 'ad_vision'} else 'unknown',
            'validation_reason': validation_reason if validation_reason in _VALIDATION else 'unknown',
            'content_type': type(content).__name__ if type(content) in {str, list, dict, type(None)} else 'other',
            'content_chars': len(content) if isinstance(content, str) else None,
            'content': cleaned[:MAX_RESPONSE_CHARS] if cleaned is not None else None,
            'content_truncated': truncated,
            'content_omitted': omitted,
            'finish_reason': response_fields.get('finish_reason') if response_fields.get('finish_reason') in _FINISH else 'unknown',
        }
        if parent_request_id and re.fullmatch(r'[a-f0-9]{32}', parent_request_id):
            row['parent_request_id'] = parent_request_id
        if (isinstance(catalog, dict) and set(catalog) == {'sha256', 'chars', 'tours'}
                and isinstance(catalog['sha256'], str) and re.fullmatch(r'[a-f0-9]{64}', catalog['sha256'])
                and type(catalog['chars']) is int and isinstance(catalog['tours'], list)):
            row['catalog'] = {'sha256': catalog['sha256'], 'chars': catalog['chars'], 'tours': [
                {'name': re.sub(r'https?://\S+', '[URL]', _redact(str(t.get('name', ''))))[:180],
                 'available': t.get('available') if type(t.get('available')) is bool else None,
                 'dates': [d for d in t.get('dates', []) if isinstance(d, str)
                           and re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', d)][:40]}
                for t in catalog['tours'][:100] if isinstance(t, dict)]}
        for key in ['input_tokens', 'output_tokens']:
            value = response_fields.get(key)
            row[key] = value if type(value) is int and 0 <= value <= 1_000_000_000 else None
        encoded = json.dumps(row, ensure_ascii=False)
        from src.services.diagnostic_trace import trace_event
        trace_event('model_response', sender_id=sender_id, response=row)
        with _lock:
            logger = _get_logger()
            record = logger.makeRecord(logger.name, logging.INFO, '', 0, encoded, (), None)
            logger.handle(record)
        if getattr(record, 'response_log_failed', False):
            _warn()
        else:
            get_logger(__name__).info('llm.response.recorded', request_id=trace,
                                     phase=row['phase'],
                                     sender_hash=row['sender_hash'], attempt=row['attempt'],
                                     validation_reason=row['validation_reason'])
    except Exception:
        _warn()
