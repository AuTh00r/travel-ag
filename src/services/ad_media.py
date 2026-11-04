"""Точная реклама → Instagram media; отдельный доступ только на чтение."""

import asyncio
from pathlib import Path
import re

import httpx
from structlog import get_logger

from src.config import settings
from src.exceptions import StoryMediaError
from src.services.meta_diagnostics import graph_failure_fields
from src.services.story_media import _permalink, valid_id, validate_media_url

_resolutions = asyncio.Semaphore(2)
logger = get_logger()


def _credentials() -> tuple[str, tuple[str, ...]]:
    extra = getattr(settings, 'instagram_ads_account_ids', '')
    legacy = settings.instagram_ads_account_id
    if not isinstance(extra, str) or len(extra) > 1024:
        raise StoryMediaError("ad_not_configured")
    members = ([legacy] if legacy else []) + (extra.split(',') if extra.strip() else [])
    accounts = tuple(dict.fromkeys(value.strip() for value in members))
    if (not accounts or len(accounts) > 10
            or any(not valid_id(value) or not value.isascii() for value in accounts)
            or not settings.ads_media_enabled
            or not settings.instagram_ads_token_file or not settings.instagram_access_token):
        raise StoryMediaError("ad_not_configured")
    try:
        with Path(settings.instagram_ads_token_file).open("r", encoding="utf-8-sig") as stream:
            token = stream.read(4097).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,4096}", token):
            raise ValueError
    except (OSError, UnicodeError, ValueError):
        raise StoryMediaError("ad_credential_unavailable") from None
    return token, accounts


async def _get(client: httpx.AsyncClient, node: str, fields: str, token: str,
               *, version: str = "v26.0", operation: str = "unknown") -> dict:
    # Operations are call-site constants, never graph paths or provider values.
    operation = operation if operation in {"permissions", "ad_account", "ad_lookup", "creative", "media"} else "unknown"
    response = None
    try:
        response = await client.get(f"https://graph.facebook.com/{version}/{node}",
                                    params={"fields": fields} if fields else {},
                                    headers={"Authorization": "Bearer " + token})
        if len(response.content) > 256 * 1024:
            logger.warning("instagram.ads.graph_failed", operation=operation,
                           **graph_failure_fields("response_too_large"))
            raise StoryMediaError("ad_response_too_large")
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        reason = ("transport_timeout" if isinstance(exc, httpx.TimeoutException) else
                  "transport_error" if isinstance(exc, httpx.HTTPError) else "invalid_json")
        logger.warning("instagram.ads.graph_failed", operation=operation,
                       **graph_failure_fields(reason, response=response, exception=exc))
        raise StoryMediaError("ad_graph_unavailable") from None
    if not isinstance(body, dict):
        logger.warning("instagram.ads.graph_failed", operation=operation,
                       **graph_failure_fields("invalid_shape", response=response))
        raise StoryMediaError("ad_graph_unavailable")
    if response.status_code != 200 or "error" in body:
        error = body.get("error")
        logger.warning("instagram.ads.graph_failed", operation=operation,
                       **graph_failure_fields("graph_error" if "error" in body else "http_status", response=response))
        raise StoryMediaError("ad_access_expired" if isinstance(error, dict) and error.get("code") == 190
                              else "ad_graph_unavailable")
    return body


async def check_ad_access() -> dict:
    """Безопасная диагностика конфигурации; не возвращает credential/сырой ответ."""
    if not settings.ads_media_enabled:
        return {"enabled": False, "ready": False}
    token, accounts = _credentials()
    try:
        async with asyncio.timeout(20):
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                permissions = await _get(client, "me/permissions", "", token, operation="permissions")
                rows = permissions.get("data")
                if not isinstance(rows, list) or not any(isinstance(row, dict)
                        and row.get("permission") == "ads_read" and row.get("status") == "granted" for row in rows):
                    raise StoryMediaError("ad_scope_missing")
                for account in accounts:
                    body = await _get(client, "act_" + account, "id,account_id", token, operation="ad_account")
                    if body.get("id") != "act_" + account or body.get("account_id") != account:
                        raise StoryMediaError("ad_account_mismatch")
    except TimeoutError:
        raise StoryMediaError("ad_timeout") from None
    return {"enabled": True, "ready": True}


async def resolve_ad_media(ad_id: str) -> dict:
    if not valid_id(ad_id):
        raise StoryMediaError("ad_invalid_identity")
    token, accounts = _credentials()
    try:
        async with asyncio.timeout(20):
            async with _resolutions:
                async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                    creative_fields = "id,effective_instagram_media_id,source_instagram_media_id,instagram_permalink_url,asset_feed_spec"
                    # Placement permalinks can be present only in the ad-context expansion.
                    ad = await _get(client, ad_id, "id,account_id,creative{" + creative_fields + "}",
                                    token, operation="ad_lookup")
                    if ad.get("id") != ad_id or ad.get("account_id") not in accounts:
                        raise StoryMediaError("ad_account_mismatch")
                    creative_ref = ad.get("creative")
                    creative_id = creative_ref.get("id") if isinstance(creative_ref, dict) else None
                    if not valid_id(creative_id):
                        raise StoryMediaError("ad_missing_creative")
                    creative = creative_ref
                    if set(creative_ref) == {"id"}:
                        creative = await _get(client, creative_id, creative_fields, token, operation="creative")
                    permalink = creative.get("instagram_permalink_url")
                    shortcode = _permalink(permalink)
                    if creative.get("id") != creative_id or not shortcode:
                        raise StoryMediaError("ad_unproved_creative")
                    feed = creative.get("asset_feed_spec")
                    placement = bool(feed)
                    if ((feed is not None and not isinstance(feed, dict))
                            or (placement and feed.get("optimization_type") != "PLACEMENT")):
                        raise StoryMediaError("ad_variant_unavailable")
                    candidates = list(dict.fromkeys(value for key in
                        ("effective_instagram_media_id", "source_instagram_media_id")
                        if valid_id(value := creative.get(key))))
                    for candidate in candidates:
                        try:
                            media = await _get(client, candidate,
                                "id,media_type,media_url,permalink,caption,children{id,media_type,media_url}",
                                settings.instagram_access_token, version="v25.0", operation="media")
                        except StoryMediaError as exc:
                            if str(exc) != "ad_graph_unavailable":
                                raise
                            continue
                        if media.get("id") != candidate or _permalink(media.get("permalink")) != shortcode:
                            continue
                        if media.get("media_type") not in ("IMAGE", "VIDEO", "CAROUSEL_ALBUM"):
                            continue
                        if media.get("media_type") != "CAROUSEL_ALBUM":
                            try:
                                validate_media_url(media.get("media_url"))
                            except StoryMediaError:
                                continue
                        # The creative proves this IG material, not the variant shown at a placement.
                        return {**media, "_ad_source": "marketing_variant"} if placement else media
    except TimeoutError:
        raise StoryMediaError("ad_timeout") from None
    raise StoryMediaError("ad_media_unavailable")
