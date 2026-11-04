"""Bounded primary-call policy and safe manager diagnostics; no external I/O."""

import re

from httpx import TransportError
from openai import APIConnectionError, APIStatusError

from src.exceptions import ProviderResponseError

CALL_TIMEOUTS = (120, 120, 240)


def retryable_error(exc):
    if isinstance(exc, (APIConnectionError, TransportError, TimeoutError, ProviderResponseError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {408, 409, 429} or 500 <= exc.status_code <= 599
    return type(exc) is ValueError and exc.args == ('invalid_model_choices',)


def technical_context(question, reason, request_id, attempts):
    from src.services.llm_response_log import _redact

    # The exception message/body and model output are deliberately not accepted.
    question = _redact(question) if isinstance(question, str) else ''
    question = re.sub(r'https?://\S+|www\.\S+|\[[^\]\n]*\]', '', question)
    question = re.sub(r'\+?\d[\d ()-]{6,20}\d',
                      lambda m: '' if len(re.sub(r'\D', '', m[0])) >= 9 else m[0], question)
    question = re.sub(r'={2,}[^\n]*', '', question)
    question = ' '.join(question.split())[:240]
    def safe_code(value):
        return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_]{1,64}', value) else 'unknown'
    trace_id = request_id if isinstance(request_id, str) and re.fullmatch(r'[a-f0-9]{32}', request_id) else 'unknown'
    descriptions = {
        'unexpected_response_type': 'Сервис ИИ вернул ответ в неподдерживаемом виде.',
        'invalid_model_choices': 'Сервис ИИ вернул некорректную структуру ответа.',
        'call_deadline': 'Сервис ИИ не успел ответить за отведённое время.',
        'provider_error': 'Произошёл сбой при обращении к сервису ИИ.',
        'configuration_error': 'Автоответ недоступен из-за ошибки настройки.',
        'model_budget_exhausted': 'Доступные попытки автоответа исчерпаны.',
    }
    cause = descriptions.get(reason, 'Бот не смог подготовить корректный ответ.')
    model_failure = reason in {
        *descriptions, 'empty_response', 'response_truncated', 'invalid_json',
        'invalid_model_response', 'invalid_tool_message', 'invalid_tool_count',
        'invalid_tool', 'invalid_arguments_type', 'content_with_tool',
        'invalid_finish_reason', 'incomplete_tool_arguments',
    }
    delivery_status = ('Автоматический ответ на этот запрос не отправлен.' if model_failure else
                       'Автоматическая обработка не завершена. Проверьте переписку перед ответом.')
    lines = [cause, delivery_status,
             'Запрос клиента: ' + (question or 'без доступного текста'),
             'Ответьте клиенту вручную. Автоматических повторов этого запроса больше не будет.',
             '', 'Диагностика:', 'Причина: ' + safe_code(reason), 'ID: ' + trace_id]
    for attempt in attempts[-3:]:
        number = attempt.get('attempt')
        number = number if type(number) is int and 0 <= number <= 3 else 0
        detail = f"{number}/3: {safe_code(attempt.get('stage'))}; {safe_code(attempt.get('reason'))}"
        error_type = attempt.get('error_type')
        if error_type:
            detail += '; ' + safe_code(error_type)
        response_type = attempt.get('response_type')
        if response_type:
            detail += '; тип ответа: ' + safe_code(response_type)
        origin = attempt.get('origin')
        if isinstance(origin, str) and re.fullmatch(r'src\.[A-Za-z0-9_.]+:[0-9]{1,7}', origin):
            detail += '; ' + origin
        status = attempt.get('http_status')
        if type(status) is int and 100 <= status <= 599:
            detail += f'; HTTP {status}'
        timeout = attempt.get('timeout')
        if timeout in CALL_TIMEOUTS:
            detail += f'; таймаут {timeout}с'
        elapsed = attempt.get('elapsed_ms')
        if type(elapsed) is int and 0 <= elapsed <= 86_400_000:
            detail += f'; {elapsed / 1000:g}с'
        previous_id = attempt.get('request_id')
        if (isinstance(previous_id, str) and re.fullmatch(r'[a-f0-9]{32}', previous_id)
                and previous_id != trace_id):
            detail += '; ID: ' + previous_id
        lines.append(detail)
    return '\n'.join(lines)
