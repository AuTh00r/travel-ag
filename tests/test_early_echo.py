import asyncio
from unittest.mock import patch

import httpx
import pytest

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.exceptions import InstagramError


def echo(text, recipient='test-owner', mid='early-own-mid'):
    return {'entry': [{'messaging': [{'recipient': {'id': recipient},
                                     'message': {'is_echo': True, 'mid': mid, 'text': text}}]}]}


@pytest.fixture
def channel(monkeypatch):
    monkeypatch.setattr(settings, 'instagram_access_token', 'test-token')
    monkeypatch.setattr(settings, 'instagram_app_id', '')
    InstagramChannel._sent_mids.clear()
    return InstagramChannel()


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['Спасибо, передал менеджеру.', 'т' * 1200], ids=['normal', 'truncated'])
async def test_own_echo_before_http_response(channel, text):
    async def post(client, url, **kwargs):
        sent_text = kwargs['json']['message']['text']
        assert await channel.receive_message(echo(sent_text)) == []
        assert (await channel.receive_message(echo(sent_text, recipient='other', mid='other-mid')))[0]['kind'] == 'manager'
        assert (await channel.receive_message(echo('Реальный менеджер', mid='manager-mid')))[0]['kind'] == 'manager'
        other_app = echo(sent_text, mid='other-app-mid')
        other_app['entry'][0]['messaging'][0]['message']['app_id'] = 'other-app'
        settings.instagram_app_id = 'our-app'
        try:
            assert (await channel.receive_message(other_app))[0]['kind'] == 'manager'
        finally:
            settings.instagram_app_id = ''
        return httpx.Response(200, json={'message_id': 'early-own-mid'}, request=httpx.Request('POST', url))

    with patch.object(httpx.AsyncClient, 'post', post):
        await channel.send_message('test-owner', text)
    assert await channel.receive_message(echo(text)) == []
    assert (await channel.receive_message(echo(text, mid='later-manager-mid')))[0]['kind'] == 'manager'


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_pending_echo_cleanup_after_failed_send(channel, cancel):
    async def post(client, url, **kwargs):
        assert await channel.receive_message(echo('Ответ')) == []
        if cancel:
            raise asyncio.CancelledError
        raise httpx.ConnectError('test', request=httpx.Request('POST', url))

    expected_error = asyncio.CancelledError if cancel else InstagramError
    with patch.object(httpx.AsyncClient, 'post', post), pytest.raises(expected_error):
        await channel.send_message('test-owner', 'Ответ')
    assert await channel.receive_message(echo('Ответ')) == []
    assert (await channel.receive_message(echo('Ответ', mid='new-manager-mid')))[0]['kind'] == 'manager'


@pytest.mark.asyncio
async def test_concurrent_identical_sends_keep_pending_registration(channel):
    first_entered, second_entered, release_first, release_second = [asyncio.Event() for _ in range(4)]
    calls = 0

    async def post(client, url, **kwargs):
        nonlocal calls
        calls += 1
        number = calls
        (first_entered if number == 1 else second_entered).set()
        await (release_first if number == 1 else release_second).wait()
        if number == 2:
            assert await channel.receive_message(echo('Ответ', mid='second-mid')) == []
        return httpx.Response(200, json={'message_id': f'sent-{number}'}, request=httpx.Request('POST', url))

    with patch.object(httpx.AsyncClient, 'post', post):
        first = asyncio.create_task(channel.send_message('test-owner', 'Ответ'))
        await first_entered.wait()
        second = asyncio.create_task(channel.send_message('test-owner', 'Ответ'))
        await second_entered.wait()
        release_first.set()
        await first
        release_second.set()
        await second
    assert (await channel.receive_message(echo('Ответ', mid='later-manager-mid')))[0]['kind'] == 'manager'
