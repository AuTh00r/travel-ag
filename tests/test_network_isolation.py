import httpx
import pytest


def test_real_sync_http_is_blocked_before_network():
    with httpx.Client() as client:
        with pytest.raises(RuntimeError, match="Real HTTP network disabled"):
            client.get("https://example.invalid")


async def test_real_async_http_is_blocked_before_network():
    async with httpx.AsyncClient() as client:
        with pytest.raises(RuntimeError, match="Real HTTP network disabled"):
            await client.get("https://example.invalid")


async def test_mock_transport_still_works():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    async with httpx.AsyncClient(transport=transport) as client:
        assert (await client.get("https://example.invalid")).json() == {"ok": True}
