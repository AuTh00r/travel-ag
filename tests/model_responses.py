"""Explicit model envelopes. Never normalize a raw provider response here."""
import json
from types import SimpleNamespace


def reply_json(reply='Подробности тура.', manager=None):
    return json.dumps({'reply': reply, 'manager': manager}, ensure_ascii=False)


def manager_data(context, type='консультация', name=''):
    return {'context': context, 'type': type, 'name': name}


def model_response(reply='Подробности тура.', manager=None):
    return tool_response(reply_json(reply, manager))


def tool_response(arguments, *, usage_metadata=None, response_metadata=None):
    """Explicit raw envelope; malformed arguments are preserved, never repaired."""
    return SimpleNamespace(content='', usage_metadata=usage_metadata or {},
        response_metadata=response_metadata if response_metadata is not None else {'finish_reason': 'tool_calls'},
        additional_kwargs={'raw_tool_message': {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': 'call-proof', 'type': 'function', 'function': {
                'name': 'prepare_response', 'arguments': arguments}}]}})


def arguments_of(response):
    return response.additional_kwargs['raw_tool_message']['tool_calls'][0]['function']['arguments']


def set_arguments(response, arguments):
    response.additional_kwargs['raw_tool_message']['tool_calls'][0]['function']['arguments'] = arguments
