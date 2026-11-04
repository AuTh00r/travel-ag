from copy import deepcopy
import json

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai.types.chat import ChatCompletion

from src.config import settings
from src.exceptions import LLMError, ProviderResponseError

RESPONSE_FUNCTION = 'prepare_response'
TOOL_RESPONSE_ERRORS = frozenset({
    'invalid_tool_message', 'invalid_tool_count', 'invalid_tool',
    'invalid_arguments_type', 'content_with_tool', 'invalid_finish_reason',
    'incomplete_tool_arguments',
})


def tool_enabled_for(client_id: object) -> bool:
    return isinstance(client_id, str) and bool(client_id) and (
        settings.deepseek_tool_scope == 'all' or client_id in settings.tool_clients())


def response_tool() -> dict:
    """Same business result for every route; this function has no side effects."""
    manager = {'type': 'object', 'properties': {
        'context': {'type': 'string'},
        'type': {'type': 'string', 'enum': ['консультация', 'контакт', 'отзыв']},
        'name': {'type': 'string'}},
        'required': ['context', 'type', 'name'], 'additionalProperties': False}
    return {'type': 'function', 'function': {
        'name': RESPONSE_FUNCTION, 'strict': True,
        'description': 'Подготовить ответ клиенту и потребность в менеджере без отправки сообщений.',
        'parameters': {'type': 'object', 'properties': {
            'reply': {'type': 'string'}, 'manager': {'anyOf': [{'type': 'null'}, manager]}},
            'required': ['reply', 'manager'], 'additionalProperties': False}}}


class _ResponseModel(ChatOpenAI):
    """Preserve original arguments before the SDK parses away duplicate keys."""

    def _create_chat_result(self, response, generation_info=None):
        if isinstance(response, dict):
            data = response
        elif isinstance(response, ChatCompletion):
            data = response.model_dump()
        else:
            raise ProviderResponseError('unexpected_response_type', response)
        choices = data.get('choices')
        if (not isinstance(choices, list) or len(choices) != 1
                or not isinstance(choices[0], dict) or not isinstance(choices[0].get('message'), dict)):
            raise ProviderResponseError('invalid_model_choices', response)
        raw_message = deepcopy(choices[0]['message'])
        sanitized = deepcopy(data)
        # SDK normalization is not validation: even malformed tool arguments must
        # reach our own validator, without being coerced to {} or last-key-wins.
        sanitized['choices'][0]['message'].pop('tool_calls', None)
        sanitized['choices'][0]['message']['content'] = ''
        result = super()._create_chat_result(sanitized, generation_info)
        result.generations[0].message.additional_kwargs['raw_tool_message'] = raw_message
        return result


def response_arguments(response: object, *, function_name: str = RESPONSE_FUNCTION) -> tuple[object, str | None]:
    metadata = getattr(response, 'response_metadata', None)
    finish = metadata.get('finish_reason') if isinstance(metadata, dict) else None
    if finish == 'length':
        return None, 'response_truncated'
    if finish != 'tool_calls':
        return None, 'invalid_finish_reason'
    extra = getattr(response, 'additional_kwargs', None)
    message = extra.get('raw_tool_message') if isinstance(extra, dict) else None
    if not isinstance(message, dict) or message.get('role') != 'assistant':
        return None, 'invalid_tool_message'
    content = message.get('content')
    if content is not None and (not isinstance(content, str) or content.strip()):
        return None, 'content_with_tool'
    calls = message.get('tool_calls')
    if not isinstance(calls, list) or len(calls) != 1:
        return None, 'invalid_tool_count'
    call = calls[0]
    function = call.get('function') if isinstance(call, dict) else None
    if (not isinstance(call, dict) or call.get('type') != 'function'
            or not isinstance(call.get('id'), str) or not call['id']
            or not isinstance(function, dict) or function.get('name') != function_name):
        return None, 'invalid_tool'
    raw = function.get('arguments')
    if not isinstance(raw, str):
        return None, 'invalid_arguments_type'
    if raw.strip() and len(raw) <= 16000:
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            # Some provider responses end at `"manager": ` despite tool_calls.
            # Diagnose EOF without repairing it or trusting a partial reply.
            if exc.pos >= len(raw.rstrip()):
                return None, 'incomplete_tool_arguments'
        except (RecursionError, ValueError):
            pass  # Keep the existing validator's depth/numeric rejection path.
    return raw, None


def response_log_content(response: object) -> object:
    """Diagnostics only; never use this permissive extraction as model output."""
    extra = getattr(response, 'additional_kwargs', None)
    message = extra.get('raw_tool_message') if isinstance(extra, dict) else None
    if isinstance(message, dict):
        calls = message.get('tool_calls')
        if isinstance(calls, list) and len(calls) == 1 and isinstance(calls[0], dict):
            function = calls[0].get('function')
            content = message.get('content')
            if (message.get('role') == 'assistant' and (content is None or isinstance(content, str) and not content.strip())
                    and calls[0].get('type') == 'function' and calls[0].get('id')
                    and isinstance(function, dict) and function.get('name') == RESPONSE_FUNCTION
                    and isinstance(function.get('arguments'), str)):
                return function['arguments']
        return json.dumps(message, ensure_ascii=False)
    return getattr(response, 'content', None)


def _model(model: str, *, tool: dict | None = None, timeout: float = 120) -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")

    # 2048, не 1024: промпт требует перечислить ВСЕ подходящие туры со ВСЕМИ
    # датами, а на каждый тур обязательны две ссылки (тур + бронирование).
    # Замер 2026-09-29: ~146 токенов на тур, подборка по 8 турам с контактной
    # строкой ≈ 1200 токенов — в 1024 не влезала, и модель обрывала ответ на
    # полуслове. Терялся как раз хвост: последние туры и обязательная
    # контактная строка. _split_reply такое не спасает — он делит уже
    # полученный текст, а здесь генерация останавливалась на середине.
    return _ResponseModel(
        model=model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/beta",
        temperature=0.1,
        timeout=timeout,
        max_retries=0,
        use_responses_api=False,
        model_kwargs={'tools': [tool or response_tool()], 'tool_choice': {
            'type': 'function', 'function': {'name': (tool or response_tool())['function']['name']}}},
        # The SDK renames its max_tokens option to max_completion_tokens;
        # DeepSeek's documented field stays max_tokens, as in the vision trial.
        extra_body={'thinking': {'type': 'disabled'}, 'max_tokens': 2048},
    )


def get_llm() -> BaseChatModel:
    return _model(settings.deepseek_model)


def get_vision_llm() -> BaseChatModel:
    return _model(settings.deepseek_vision_model)


def get_handoff_review_llm(*, vision: bool = False) -> BaseChatModel:
    from src.services.handoff_review import review_tool

    return _model(settings.deepseek_vision_model if vision else settings.deepseek_model,
                  tool=review_tool(), timeout=settings.manager_review_timeout_seconds)


def get_legacy_llm() -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")

    # 2048, не 1024: промпт требует перечислить ВСЕ подходящие туры со ВСЕМИ
    # датами, а на каждый тур обязательны две ссылки (тур + бронирование).
    # Замер 2026-09-29: ~146 токенов на тур, подборка по 8 турам с контактной
    # строкой ≈ 1200 токенов — в 1024 не влезала, и модель обрывала ответ на
    # полуслове. Терялся как раз хвост: последние туры и обязательная
    # контактная строка. _split_reply такое не спасает — он делит уже
    # полученный текст, а здесь генерация останавливалась на середине.
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.1,
        max_tokens=2048,
        timeout=120,
        max_retries=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def get_legacy_vision_llm() -> BaseChatModel:
    if not settings.deepseek_api_key:
        raise LLMError("DEEPSEEK_API_KEY не задан")
    return ChatOpenAI(
        model=settings.deepseek_vision_model,
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.1,
        timeout=120,
        max_retries=0,
        use_responses_api=False,
        model_kwargs={"response_format": {"type": "json_object"}},
        extra_body={"thinking": {"type": "disabled"}, "max_tokens": 2048},
    )
