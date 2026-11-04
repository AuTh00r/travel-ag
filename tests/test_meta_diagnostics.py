import hashlib
import hmac
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from starlette.requests import Request

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.exceptions import InstagramError, StoryMediaError
from src.services import ad_media
from src.services.meta_diagnostics import fingerprint, graph_failure_fields, reconcile_failure_fields, webhook_rejection_fields
from tests.test_inbound_recovery import clock as clock, store as store, service


PRIVATE = "PRIVATE_TOKEN_CUSTOMER_TEXT"


@pytest.mark.parametrize("signature,reason", [
    (None, "missing"), ("", "missing"), ("sha1=" + PRIVATE, "malformed"),
    ("sha256=" + "0" * 64, "mismatch"), ("sha256=" + "0" * 64 + "\n", "malformed"),
])
def test_webhook_diagnostics_never_include_untrusted_values(signature, reason):
    headers = {"content-type": "application/json; secret=" + PRIVATE,
               "x-forwarded-for": PRIVATE, "cf-connecting-ip": "203.0.113.9", "cf-ray": PRIVATE}
    fields = webhook_rejection_fields(PRIVATE.encode(), signature, "secret", headers, "127.0.0.1")
    assert fields["reason"] == reason and fields["body_bytes"] == len(PRIVATE)
    assert fields["content_type"] == "json" and fields["forwarded_present"] is True
    assert fields["cf_ray_present"] is True
    assert len(fields["body_fingerprint"]) == len(fields["peer_fingerprint"]) == 16
    assert fields["forwarded_ip_fingerprint"] != fields["peer_fingerprint"]
    assert all(value not in repr(fields) for value in (PRIVATE, "203.0.113.9", "127.0.0.1", "secret"))


def test_fingerprints_are_keyed_stable_and_separated_by_purpose():
    args = (b"127.0.0.1", None, "key", {}, "127.0.0.1")
    fields = webhook_rejection_fields(*args)
    assert fields == webhook_rejection_fields(*args)
    assert fields["body_fingerprint"] != fields["peer_fingerprint"]
    changed = webhook_rejection_fields(b"127.0.0.1", None, "other", {}, "127.0.0.1")
    assert fields["body_fingerprint"] != changed["body_fingerprint"]
    assert fields["peer_fingerprint"] != changed["peer_fingerprint"]
    absent = webhook_rejection_fields(b"x", None, "", {"cf-connecting-ip": PRIVATE}, PRIVATE)
    assert not any("fingerprint" in key for key in absent)


@pytest.mark.parametrize("value", [123, None, [], "\ud800"])
def test_fingerprint_omits_unencodable_or_unsupported_input(value):
    assert fingerprint(value, "dialog", "secret") is None


def test_graph_fields_only_allow_numeric_codes_and_boolean_transient():
    response = httpx.Response(403, json={"error": {"code": 100, "error_subcode": 33,
        "is_transient": False, "message": PRIVATE, "fbtrace_id": PRIVATE}})
    fields = graph_failure_fields("graph_error", response=response)
    assert fields == {"reason": "graph_error", "http_status": 403, "meta_code": 100,
                      "meta_subcode": 33, "meta_transient": False}
    for value in (PRIVATE, True, -1, 2**64, [100], {"secret": PRIVATE}):
        fields = graph_failure_fields("graph_error", response=httpx.Response(400, json={
            "error": {"code": value, "error_subcode": value, "is_transient": PRIVATE}}))
        assert fields == {"reason": "graph_error", "http_status": 400}


@pytest.mark.parametrize("signature,status", [(None, 403), ("malformed", 403), ("valid", 200)])
async def test_webhook_handler_preserves_authentication_and_does_not_parse_rejected_body(monkeypatch, signature, status):
    import src.main as main
    secret = "TEST_SECRET"
    monkeypatch.setattr(settings, "instagram_app_secret", secret)
    monkeypatch.setattr(settings, "inbound_recovery_enabled", False)
    monkeypatch.setattr(main, "instagram", InstagramChannel())
    receive = AsyncMock(return_value=[])
    monkeypatch.setattr(main.instagram, "receive_message", receive)
    log = Mock()
    monkeypatch.setattr(main, "logger", log)
    body = b"{}" if signature == "valid" else PRIVATE.encode()
    headers = [(b"content-type", b"application/json")]
    if signature:
        value = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if signature == "valid" else signature
        headers.append((b"x-hub-signature-256", value.encode()))
    request = Request({"type": "http", "method": "POST", "path": "/webhook/instagram",
                       "headers": headers, "client": ("203.0.113.4", 123)},
                      AsyncMock(return_value={"type": "http.request", "body": body}))
    result = await main.receive_instagram_message(request)
    assert result.status_code == status
    assert receive.await_count == (1 if status == 200 else 0)
    if status == 403:
        assert log.warning.call_args.args == ("instagram.webhook.invalid_signature",)
        assert log.warning.call_args.kwargs["reason"] in {"missing", "malformed"}
        assert PRIVATE not in repr(log.mock_calls) and secret not in repr(log.mock_calls)


@pytest.mark.parametrize("failure,reason,code", [
    ("timeout", "transport_timeout", None), ("network", "transport_error", None),
    ("invalid_json", "invalid_json", None), ("shape", "invalid_shape", None),
    ("graph", "graph_error", 100), ("expired", "graph_error", 190),
    ("http", "http_status", None),
])
async def test_ad_error_diagnostics_preserve_safe_exceptions(monkeypatch, failure, reason, code):
    log = Mock()
    monkeypatch.setattr(ad_media, "logger", log)
    client = AsyncMock()
    if failure in {"timeout", "network"}:
        client.get.side_effect = (httpx.ReadTimeout if failure == "timeout" else httpx.ConnectError)(PRIVATE)
    else:
        response = (httpx.Response(502, text=PRIVATE) if failure == "invalid_json" else
                    httpx.Response(200, json=[PRIVATE]) if failure == "shape" else
                    httpx.Response(503, json={}) if failure == "http" else
                    httpx.Response(400, json={"error": {"code": code, "error_subcode": 33, "message": PRIVATE}}))
        client.get.return_value = response
    expected = "ad_access_expired" if failure == "expired" else "ad_graph_unavailable"
    with pytest.raises(StoryMediaError, match=expected):
        await ad_media._get(client, PRIVATE, PRIVATE, PRIVATE, operation="ad_lookup")
    fields = log.warning.call_args.kwargs
    assert fields["reason"] == reason and fields["operation"] == "ad_lookup"
    if code is not None:
        assert fields["meta_code"] == code and fields["meta_subcode"] == 33
    assert PRIVATE not in repr(log.mock_calls)


@pytest.mark.parametrize("failure", ["timeout", "graph", "invalid_json", "rate_limit", "shape"])
async def test_conversation_errors_keep_safe_diagnostics_for_reconcile(monkeypatch, failure):
    import src.channels.instagram as module
    monkeypatch.setattr(settings, "instagram_access_token", PRIVATE)
    log = Mock()
    monkeypatch.setattr(module, "logger", log)
    client = AsyncMock()
    client.__aenter__.return_value = client
    if failure == "timeout":
        client.get.side_effect = httpx.ReadTimeout(PRIVATE)
    else:
        response = (httpx.Response(502, text=PRIVATE) if failure == "invalid_json" else
                    httpx.Response(200, json={"data": PRIVATE}) if failure == "shape" else
                    httpx.Response(400, json={"error": {"code": 4 if failure == "rate_limit" else 190,
                        "error_subcode": 463, "message": PRIVATE}}))
        client.get.return_value = response
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: client)
    with pytest.raises(InstagramError) as raised:
        await InstagramChannel()._conversations_get("account/conversations", {})
    assert log.warning.call_args.args == ("instagram.graph.failed",)
    fields = log.warning.call_args.kwargs
    assert fields["operation"] == "conversations"
    assert raised.value.meta_diagnostics == {k: v for k, v in fields.items() if k != "operation"}
    assert PRIVATE not in repr(log.mock_calls)


async def test_successful_ad_does_not_create_warning(monkeypatch):
    log = Mock()
    monkeypatch.setattr(ad_media, "logger", log)
    client = AsyncMock()
    client.get.return_value = httpx.Response(200, json={"id": "123"})
    assert await ad_media._get(client, "123", "id", PRIVATE) == {"id": "123"}
    log.warning.assert_not_called()


@pytest.mark.parametrize("error", [None, [], PRIVATE, {"code": []}, {"code": PRIVATE}, {"code": True}])
async def test_malformed_graph_error_never_leaks_or_breaks_classification(monkeypatch, error):
    import src.channels.instagram as module
    monkeypatch.setattr(settings, "instagram_access_token", PRIVATE)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = httpx.Response(400, json={"error": error})
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: client)
    log = Mock()
    monkeypatch.setattr(module, "logger", log)
    with pytest.raises(InstagramError) as raised:
        await InstagramChannel()._conversations_get("account/messages", {})
    assert "meta_code" not in raised.value.meta_diagnostics
    assert log.warning.call_args.kwargs["operation"] == "messages"
    assert PRIVATE not in repr(log.mock_calls) and PRIVATE not in str(raised.value)


async def test_ad_200_graph_error_and_oversize_keep_original_routes(monkeypatch):
    log = Mock()
    monkeypatch.setattr(ad_media, "logger", log)
    client = AsyncMock()
    client.get.return_value = httpx.Response(200, json={"error": {"code": 190, "message": PRIVATE}})
    with pytest.raises(StoryMediaError, match="ad_access_expired"):
        await ad_media._get(client, "123", "id", PRIVATE)
    assert log.warning.call_args.kwargs["http_status"] == 200
    client.get.return_value = httpx.Response(200, text=PRIVATE * (256 * 1024))
    with pytest.raises(StoryMediaError, match="ad_response_too_large"):
        await ad_media._get(client, "123", "id", PRIVATE)
    assert log.warning.call_args.kwargs["reason"] == "response_too_large"
    assert PRIVATE not in repr(log.mock_calls)


@pytest.mark.parametrize("stage", ["list_conversations", "sync_dialog"])
async def test_reconcile_logs_safe_cause_and_preserves_backoff(store, clock, monkeypatch, stage):
    import src.services.inbound_recovery as module
    recovery = service(store, clock)
    error = InstagramError(PRIVATE)
    error.category = "invalid_cursor"
    error.meta_diagnostics = {"reason": "graph_error", "http_status": 400, "meta_code": 100, "meta_subcode": 33,
                              "message": PRIVATE, "error_kind": "network"}
    if stage == "list_conversations":
        recovery.channel.list_conversations.side_effect = error
    else:
        recovery.channel.list_conversations.return_value = {"data": [{"id": PRIVATE, "client_id": "client"}]}
        recovery.sync_dialog = AsyncMock(side_effect=error)
    recovery._get = lambda method, *args: method(*args)
    log = Mock()
    monkeypatch.setattr(module, "logger", log)
    for attempt, delay in enumerate((30, 120, 300), 1):
        await recovery.reconcile_tick()
        assert store.get_sync("scan_failures:account") == attempt
        assert store.get_sync("next_scan:account") == clock() + delay
        assert store.get_sync("scan:account") == {"after": None, "dialogs": []}
        fields = log.warning.call_args.kwargs
        assert fields["attempt"] == attempt and fields["stage"] == stage
        assert fields["category"] == "invalid_cursor" and fields["meta_subcode"] == 33
        assert fields["error_kind"] == "network"
    assert PRIVATE not in repr(log.mock_calls)


def test_exception_metadata_is_revalidated_without_stringifying_unknown_failures():
    error = RuntimeError(PRIVATE)
    error.meta_diagnostics = {"reason": [PRIVATE], "meta_code": PRIVATE, "http_status": True, "error_kind": PRIVATE}
    assert reconcile_failure_fields(error) == {"reason": "unexpected_error", "error_kind": "other"}
    assert reconcile_failure_fields(TimeoutError(PRIVATE)) == {"reason": "deadline_timeout", "error_kind": "timeout"}
    assert PRIVATE not in repr(reconcile_failure_fields(httpx.ConnectError(PRIVATE)))
