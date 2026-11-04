"""Allowlisted diagnostic metadata; never include provider messages or URLs."""

import hashlib
import hmac
from ipaddress import ip_address
import re

import httpx


def fingerprint(value: str | bytes, purpose: str, secret: str) -> str | None:
    if not secret or not isinstance(value, (str, bytes)):
        return None
    try:
        body = value.encode() if isinstance(value, str) else value
        return hmac.new(secret.encode(), purpose.encode() + b"\0" + body, hashlib.sha256).hexdigest()[:16]
    except UnicodeEncodeError:
        return None


def webhook_rejection_fields(body: bytes, signature: str | None, secret: str,
                             headers, peer_host: str | None) -> dict:
    reason = ("missing" if not signature else "malformed"
              if not re.fullmatch(r"sha256=[0-9a-fA-F]{64}", signature) else "mismatch")
    content = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    fields = {"reason": reason, "body_bytes": len(body), "content_type": {
        "application/json": "json", "application/x-www-form-urlencoded": "form",
        "text/plain": "text", "": "absent"}.get(content, "other"),
        "forwarded_present": bool(headers.get("x-forwarded-for")),
        "cf_ray_present": bool(headers.get("cf-ray"))}
    if digest := fingerprint(body, "webhook-body", secret):
        fields["body_fingerprint"] = digest
    for key, host, purpose in (("peer_fingerprint", peer_host, "peer-ip"),
                              ("forwarded_ip_fingerprint", headers.get("cf-connecting-ip"), "forwarded-ip")):
        try:
            # Forwarded headers remain untrusted hints, even if the IP parses.
            address = str(ip_address(host))
        except (ValueError, TypeError):
            continue
        if digest := fingerprint(address, purpose, secret):
            fields[key] = digest
    return fields


def graph_failure_fields(reason: str, *, response: httpx.Response | None = None,
                         exception: Exception | None = None) -> dict:
    fields = {"reason": reason}
    if exception is not None:
        fields["error_kind"] = ("timeout" if isinstance(exception, (httpx.TimeoutException, TimeoutError)) else
                                "network" if isinstance(exception, httpx.RequestError) else "other")
    if response is not None:
        fields["http_status"] = response.status_code
        try:
            data = response.json()
        except ValueError:
            data = None
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            for source, target in (("code", "meta_code"), ("error_subcode", "meta_subcode")):
                value = error.get(source)
                if type(value) is int and 0 <= value <= 2**31 - 1:
                    fields[target] = value
            if type(error.get("is_transient")) is bool:
                fields["meta_transient"] = error["is_transient"]
    return fields


def reconcile_failure_fields(exception: Exception) -> dict:
    """Revalidate attached metadata; never stringify an exception."""
    fields = graph_failure_fields("unexpected_error", exception=exception)
    attached = getattr(exception, "meta_diagnostics", None)
    if isinstance(attached, dict):
        reasons = {"transport_timeout", "transport_error", "rate_limit", "invalid_json",
                   "invalid_shape", "graph_error", "http_status", "missing_cursor", "invalid_cursor"}
        if isinstance(attached.get("reason"), str) and attached["reason"] in reasons:
            fields["reason"] = attached["reason"]
        if isinstance(attached.get("error_kind"), str) and attached["error_kind"] in {"timeout", "network", "other"}:
            fields["error_kind"] = attached["error_kind"]
        for key in ("http_status", "meta_code", "meta_subcode"):
            value = attached.get(key)
            if type(value) is int and 0 <= value <= 2**31 - 1:
                fields[key] = value
        if type(attached.get("meta_transient")) is bool:
            fields["meta_transient"] = attached["meta_transient"]
    elif isinstance(exception, httpx.TimeoutException):
        fields["reason"] = "transport_timeout"
    elif isinstance(exception, TimeoutError):
        fields["reason"] = "deadline_timeout"
    elif isinstance(exception, httpx.RequestError):
        fields["reason"] = "transport_error"
    category = getattr(exception, "category", None)
    if isinstance(category, str) and category in {"invalid_cursor", "unsupported_field", "auth", "provider"}:
        fields["category"] = category
    return fields
