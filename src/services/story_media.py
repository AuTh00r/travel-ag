"""Собственная история или image attachments → один безопасный vision-запрос."""

import asyncio
import base64
import hashlib
import json
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import re

import httpx
import structlog

from src.config import settings
from src.exceptions import StoryMediaError

GRAPH = "https://graph.facebook.com/v25.0"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 24 * 1024 * 1024
_preparations = asyncio.Semaphore(2)
_decoder = Path(__file__).with_name("decode_story_media.ps1")
log = structlog.get_logger()
_AD_AVAILABILITY_ERRORS = {
    "post_unavailable", "graph_unavailable", "media_timeout", "download_unavailable",
    "ad_graph_unavailable", "ad_timeout", "ad_media_unavailable", "ad_variant_unavailable",
}
_AD_VARIANT_CONTEXT = (
    "Материал Instagram этого рекламного креатива; показанный клиенту вариант не подтверждён. "
    "Если приложено изображение из самого отклика, оно показывает увиденный клиентом материал. "
    "Не переноси на него отличающиеся цены, даты и условия из другого варианта креатива."
)


@dataclass
class StoryMedia:
    story_id: str | None
    media_type: str
    images: list[dict]
    caption: str = ""
    image_types: list[str] | None = None
    media_types: list[str] | None = None
    ad_source: str | None = None


async def _prepare_ad_part(part: dict, *, abort=None) -> StoryMedia:
    """Prefer exact originals; a referral image is only a last-resort asset."""
    if not valid_id(part.get("id")):
        raise StoryMediaError("ad_invalid_identity")
    attempts = []
    if "sources" in part:
        attempts.append(("referral_post", part["sources"]))
    attempts.append(("marketing", [{"ad_id": part.get("id")}]))
    if "urls" in part:
        attempts.append(("clicked_asset", part["urls"]))
    for index, (source, value) in enumerate(attempts):
        if abort and await abort():
            return StoryMedia(None, "MIXED", [])
        try:
            if source == "clicked_asset":
                media = await prepare_images(value, image_types=part.get("types"))
            else:
                media = await prepare_shared_media(value, abort=abort)
            if abort and await abort():
                return StoryMedia(None, "MIXED", [])
            if not media.images:
                raise StoryMediaError("post_unavailable")
        except StoryMediaError as exc:
            if index == len(attempts) - 1 or str(exc) not in _AD_AVAILABILITY_ERRORS:
                raise
            continue
        if source == "marketing" and media.ad_source == "marketing_variant":
            media.images = [{**item, "label": "Материал креатива (вариант показа не подтверждён). "
                             + item.get("label", "")} for item in media.images]
            media.caption = _AD_VARIANT_CONTEXT + ("\n" + media.caption if media.caption else "")
            if "urls" in part:
                try:
                    clicked = await prepare_images(part["urls"], image_types=part.get("types"))
                except StoryMediaError as exc:
                    if str(exc) not in _AD_AVAILABILITY_ERRORS:
                        raise
                else:
                    media.image_types = (media.image_types or ["image"] * len(media.images)) + (
                        clicked.image_types or ["image"] * len(clicked.images))
                    media.images += [{**item, "label": "Изображение из самого отклика клиента. "
                                      + item.get("label", "")} for item in clicked.images]
                if abort and await abort():
                    return StoryMedia(None, "MIXED", [])
        else:
            media.ad_source = source
        return media
    raise StoryMediaError("ad_media_unavailable")


async def prepare_visual_parts(parts: list[dict], *, abort=None) -> StoryMedia:
    """Prepare the visual companions of a voice batch, with a shared payload cap."""
    if not 1 <= len(parts) <= 10:
        raise StoryMediaError("invalid_image_count")
    images, captions, types, total = [], [], [], 0
    ad_source = None
    for index, part in enumerate(parts):
        if abort and await abort():
            return StoryMedia(None, "MIXED", [])
        kind = part.get("kind")
        if kind == "story":
            media = await prepare_story_media(part.get("story", {}).get("id"))
            label = "Ответ на историю"
        elif kind == "images":
            media = await prepare_images(part.get("urls", []), image_types=part.get("types"))
            label = "Фото/видео клиента"
        elif kind == "shared":
            media = await prepare_shared_media(part.get("sources", []))
            label = "Публикация/Reels"
        elif kind == "ad":
            media = await _prepare_ad_part(part, abort=abort)
            if (ad_source != "marketing_variant"
                    and (ad_source != "clicked_asset" or media.ad_source == "marketing_variant")):
                ad_source = media.ad_source
            label = "Реклама из текущего отклика"
        else:
            raise StoryMediaError("invalid_image_types")
        for image in media.images:
            total += len(base64.b64decode(image["url"].split(",", 1)[1], validate=True))
            if total > MAX_IMAGE_BYTES or len(images) >= 100:
                raise StoryMediaError("images_too_large")
            images.append({**image, "label": f"Источник {index + 1}: {label}. " + image.get("label", "")})
        types.extend(media.image_types or ["image"] * len(media.images))
        if media.caption:
            captions.append(f"Источник {index + 1}: {media.caption}")
    return StoryMedia(None, "MIXED", images, "\n\n".join(captions), image_types=types, ad_source=ad_source)


def valid_id(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 32 and value.isascii() and value.isdigit()


def validate_media_url(value: object) -> str:
    if not isinstance(value, str):
        raise StoryMediaError("invalid_media_url")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        allowed = any(host == root or host.endswith("." + root)
                      for root in ("cdninstagram.com", "fbcdn.net", "fbsbx.com"))
        if (parsed.scheme != "https" or not allowed or parsed.port not in (None, 443)
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError
    except ValueError:
        raise StoryMediaError("invalid_media_url") from None
    return value


def validate_mp4(data: bytes) -> None:
    """Все top-level boxes полностью доступны; обязательны ftyp/moov/mdat."""
    position = 0
    boxes = set()
    while position < len(data):
        if len(data) - position < 8:
            raise StoryMediaError("invalid_mp4")
        size, kind = struct.unpack_from(">I4s", data, position)
        header = 8
        if size == 1:
            if len(data) - position < 16:
                raise StoryMediaError("invalid_mp4")
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header = 16
        elif size == 0:
            size = len(data) - position
        if size < header or position + size > len(data):
            raise StoryMediaError("invalid_mp4")
        boxes.add(kind)
        position += size
    if not {b"ftyp", b"moov", b"mdat"}.issubset(boxes):
        raise StoryMediaError("invalid_mp4")


def video_track_duration(data: bytes) -> float | None:
    def children(start: int, end: int) -> list[tuple[bytes, int, int]]:
        result = []
        while start + 8 <= end:
            size, kind = struct.unpack_from(">I4s", data, start)
            header = 8
            if size == 1:
                if start + 16 > end:
                    return []
                size, header = struct.unpack_from(">Q", data, start + 8)[0], 16
            elif size == 0:
                size = end - start
            if size < header or start + size > end:
                return []
            result.append((kind, start + header, start + size))
            start += size
        return result
    for kind, start, end in children(0, len(data)):
        if kind != b"moov":
            continue
        for kind, start, end in children(start, end):
            if kind != b"trak":
                continue
            for kind, start, end in children(start, end):
                if kind != b"mdia":
                    continue
                atoms = children(start, end)
                if not any(k == b"hdlr" and e - s >= 12 and data[s + 8:s + 12] == b"vide"
                           for k, s, e in atoms):
                    continue
                for kind, start, end in atoms:
                    if kind == b"mdhd":
                        version = data[start] if start < end else -1
                        offset = start + (20 if version == 1 else 12)
                        if version not in (0, 1) or offset + (12 if version else 8) > end:
                            raise StoryMediaError("invalid_video_timing")
                        scale = struct.unpack_from(">I", data, offset)[0]
                        duration = struct.unpack_from(">Q" if version else ">I", data, offset + 4)[0]
                        if not scale or not duration:
                            raise StoryMediaError("invalid_video_timing")
                        return duration / scale
    return None


async def _graph_json(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    response = await client.get(f"{GRAPH}/{path}", params=params)
    if response.status_code != 200:
        raise StoryMediaError("graph_unavailable")
    body = response.json()
    if not isinstance(body, dict) or "error" in body:
        raise StoryMediaError("graph_unavailable")
    return body


async def _source(story_id: str) -> tuple[str, str]:
    if not valid_id(settings.instagram_ig_user_id) or not settings.instagram_access_token:
        raise StoryMediaError("media_not_configured")
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {settings.instagram_access_token}"},
        timeout=20, follow_redirects=False,
    ) as graph:
        params = {"fields": "id", "limit": "100"}
        for _ in range(3):
            body = await _graph_json(graph, f"{settings.instagram_ig_user_id}/stories", params)
            rows = body.get("data")
            if not isinstance(rows, list):
                raise StoryMediaError("graph_unavailable")
            if any(isinstance(row, dict) and row.get("id") == story_id for row in rows):
                break
            paging = body.get("paging", {})
            after = paging.get("cursors", {}).get("after") if isinstance(paging, dict) else None
            if not (isinstance(paging, dict) and paging.get("next")
                    and isinstance(after, str) and 0 < len(after) <= 2048):
                raise StoryMediaError("story_unavailable")
            params["after"] = after
        else:
            raise StoryMediaError("story_unavailable")
        media = await _graph_json(graph, story_id, {"fields": "id,media_type,media_url"})
    if media.get("id") != story_id or media.get("media_type") not in ("VIDEO", "IMAGE"):
        raise StoryMediaError("unsupported_story")
    return media["media_type"], validate_media_url(media.get("media_url"))


async def _download(url: str, media_type: str) -> bytes:
    validate_media_url(url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False,
                                 headers={"Accept-Encoding": "identity"}) as cdn:
        async with cdn.stream("GET", url) as response:
            if response.status_code != 200:
                raise StoryMediaError("download_unavailable")
            content_type = response.headers.get("content-type", "").split(";")[0].lower()
            allowed = ({"video/mp4", "image/gif", "application/octet-stream"} if media_type == "VIDEO"
                       else {"image/jpeg", "image/png", "image/gif", "application/octet-stream"})
            if media_type == "AUTO":
                allowed.add("video/mp4")
            if content_type not in allowed:
                raise StoryMediaError("unsupported_content_type")
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise StoryMediaError("unsupported_content_encoding")
            length = response.headers.get("content-length")
            expected = int(length) if length is not None else None
            if expected is not None and (expected <= 0 or expected > MAX_FILE_BYTES):
                raise StoryMediaError("file_too_large")
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                data.extend(chunk)
                if len(data) > MAX_FILE_BYTES:
                    raise StoryMediaError("file_too_large")
            if not data or (expected is not None and len(data) != expected):
                raise StoryMediaError("incomplete_download")
            return bytes(data)


async def _decode(source: Path, output: Path, media_type: str) -> dict:
    if os.name != "nt":
        raise StoryMediaError("decoder_unavailable")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    process = await asyncio.create_subprocess_exec(
        str(powershell), "-NoProfile", "-NonInteractive", "-File", str(_decoder),
        "-MediaPath", str(source), "-OutputDirectory", str(output), "-MediaType", media_type,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        creationflags=0x08000000,  # CREATE_NO_WINDOW; только наш дочерний декодер.
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=60)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        raise StoryMediaError("decode_failed")
    return json.loads((output / "frames.json").read_text(encoding="utf-8-sig"))


async def _prepare_file(media_type: str, url: str, folder: Path) -> list[dict]:
    data = await _download(url, media_type)
    if data.startswith((b"GIF87a", b"GIF89a")):
        raise StoryMediaError("ignored_gif")
    if media_type == "AUTO":
        media_type = "IMAGE" if data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")) else "VIDEO"
    if media_type == "VIDEO":
        validate_mp4(data)
        video_duration = video_track_duration(data)
        if video_duration is not None:
            if video_duration > 90:
                raise StoryMediaError("video_too_long")
            (folder / "video-timing.json").write_text(json.dumps({"duration": video_duration}), encoding="utf-8")
        mime, suffix = "video/mp4", ".mp4"
    elif data.startswith(b"\xff\xd8\xff"):
        mime, suffix = "image/jpeg", ".jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime, suffix = "image/png", ".png"
    else:
        raise StoryMediaError("unsupported_image")
    source = folder / ("source" + suffix)
    source.write_bytes(data)
    manifest = await _decode(source, folder, media_type)
    frames = manifest.get("frames")
    expected = 10 if media_type == "VIDEO" else 1
    if not isinstance(frames, list) or len(frames) != expected:
        raise StoryMediaError("invalid_frames")
    images, total = [], 0
    for index, frame in enumerate(frames):
        filename = f"frame-{index:03}.jpg" if media_type == "VIDEO" else source.name
        if frame.get("file") != filename:
            raise StoryMediaError("invalid_frames")
        payload = (folder / filename).read_bytes()
        total += len(payload)
        if total > MAX_IMAGE_BYTES:
            raise StoryMediaError("images_too_large")
        if media_type == "VIDEO" and not payload.startswith(b"\xff\xd8\xff"):
            raise StoryMediaError("invalid_frames")
        frame_mime = "image/jpeg" if media_type == "VIDEO" else mime
        label = (f"Кадр {index + 1}/10, {float(frame['target_seconds']):.3f} с."
                 if media_type == "VIDEO" else "Изображение.")
        images.append({"label": label, "url": "data:" + frame_mime + ";base64," +
                       base64.b64encode(payload).decode("ascii")})
    return images


async def prepare_story_media(story_id: object) -> StoryMedia:
    if not valid_id(story_id):
        raise StoryMediaError("invalid_story_id")
    try:
        async with asyncio.timeout(90):
            async with _preparations:
                media_type, url = await _source(story_id)
                with tempfile.TemporaryDirectory(prefix="story-media-") as temporary:
                    images = await _prepare_file(media_type, url, Path(temporary))
                    return StoryMedia(story_id, media_type, images)
    except StoryMediaError:
        raise
    except TimeoutError:
        raise StoryMediaError("media_timeout") from None
    except Exception:
        # HTTP/декодер/JSON могут содержать секретный URL — наружу только код.
        raise StoryMediaError("media_failed") from None


async def prepare_images(urls: list[object], *, image_types: list[str] | None = None) -> StoryMedia:
    """URL вложений живут только здесь; Graph-токен для CDN не используется."""
    if not isinstance(urls, list) or not 1 <= len(urls) <= 10:
        raise StoryMediaError("invalid_image_count")
    if image_types is not None and (not isinstance(image_types, list) or len(image_types) != len(urls)
            or any(kind not in ("image", "story_mention", "video") for kind in image_types)):
        raise StoryMediaError("invalid_image_types")
    kinds = image_types if image_types is not None else ["image"] * len(urls)
    # Проверить весь набор до первого скачивания, не обрезать его молча.
    validated = [validate_media_url(url) for url in urls]
    try:
        async with asyncio.timeout(90):
            async with _preparations:
                with tempfile.TemporaryDirectory(prefix="image-media-") as temporary:
                    folder = Path(temporary)
                    images, total, expanded_types, media_types = [], 0, [], []
                    for index, url in enumerate(validated):
                        if kinds[index] != "image":
                            item_folder = folder / f"attachment-{index:03}"
                            item_folder.mkdir()
                            try:
                                frames = await _prepare_file("AUTO" if kinds[index] == "story_mention" else "VIDEO", url, item_folder)
                            except StoryMediaError as exc:
                                if str(exc) != "ignored_gif":
                                    raise
                                media_types.append("IGNORED")
                                continue
                            media_types.append("VIDEO" if len(frames) == 10 else "IMAGE")
                            for frame in frames:
                                total += len(base64.b64decode(frame["url"].split(",", 1)[1]))
                                frame["label"] = f"Вложение {index + 1}/{len(validated)}. " + frame["label"]
                            images.extend(frames)
                            expanded_types.extend([kinds[index]] * len(frames))
                            if total > MAX_IMAGE_BYTES or len(images) > 100:
                                raise StoryMediaError("images_too_large")
                            continue
                        data = await _download(url, "IMAGE")
                        if data.startswith((b"GIF87a", b"GIF89a")):
                            media_types.append("IGNORED")
                            continue
                        total += len(data)
                        if total > MAX_IMAGE_BYTES:
                            raise StoryMediaError("images_too_large")
                        if data.startswith(b"\xff\xd8\xff"):
                            mime, suffix = "image/jpeg", ".jpg"
                        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                            mime, suffix = "image/png", ".png"
                        else:
                            raise StoryMediaError("unsupported_image")
                        source = folder / (f"image-{index:03}" + suffix)
                        source.write_bytes(data)
                        manifest = await _decode(source, folder, "IMAGE")
                        if manifest.get("frames") != [{"file": source.name}]:
                            raise StoryMediaError("invalid_frames")
                        images.append({
                            "label": f"Изображение {index + 1}/{len(validated)}.",
                            "url": "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii"),
                        })
                        expanded_types.append("image")
                        media_types.append("IMAGE")
                        source.unlink()  # Декодер уже закрыт; не накапливаем файлы.
                    return StoryMedia(None, "VIDEO" if "VIDEO" in media_types else "IMAGE", images,
                                      image_types=expanded_types, media_types=media_types)
    except StoryMediaError:
        raise
    except TimeoutError:
        raise StoryMediaError("media_timeout") from None
    except Exception:
        raise StoryMediaError("media_failed") from None


def _permalink(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname not in ("instagram.com", "www.instagram.com")
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        return None
    match = re.fullmatch(r"/(?:p|reel|reels)/([A-Za-z0-9_-]{1,64})/?", parsed.path)
    return match.group(1) if match else None


async def _post_source(source: dict) -> dict:
    if "ad_id" in source:
        from src.services.ad_media import resolve_ad_media
        return await resolve_ad_media(source["ad_id"])
    candidate = source.get("id")
    url = source.get("url")
    shortcode = _permalink(url)
    asset_candidate = False
    if not valid_id(candidate) and isinstance(url, str) and not shortcode:
        validate_media_url(url)
        asset_ids = parse_qs(urlsplit(url).query).get("asset_id", [])
        candidate = asset_ids[0] if len(asset_ids) == 1 and valid_id(asset_ids[0]) else None
        asset_candidate = valid_id(candidate)
    if not valid_id(candidate) and not shortcode:
        raise StoryMediaError("missing_post_identity")
    log.info("shared.media.identity", source_kind="cdn_asset" if asset_candidate else
             "explicit_id" if valid_id(candidate) else "permalink",
             candidate_id=candidate if valid_id(candidate) else None,
             permalink_hash=hashlib.sha256(shortcode.encode()).hexdigest()[:16] if shortcode else None)
    fields = "id,ig_id,media_type,media_url,permalink,caption,children{id,ig_id,media_type,media_url}"
    async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                headers={"Authorization": f"Bearer {settings.instagram_access_token}"}) as graph:
        if valid_id(candidate):
            try:
                result = await _graph_json(graph, candidate, {"fields": fields})
                if candidate not in (result.get("id"), str(result.get("ig_id", ""))):
                    raise StoryMediaError("post_id_mismatch")
                if shortcode and _permalink(result.get("permalink")) != shortcode:
                    raise StoryMediaError("post_id_mismatch")
                # CDN asset может принадлежать слайду, а не всей публикации.
                if not asset_candidate or result.get("media_type") == "CAROUSEL_ALBUM":
                    return result
            except StoryMediaError as exc:
                if str(exc) != "graph_unavailable":
                    raise
        if not valid_id(settings.instagram_ig_user_id):
            raise StoryMediaError("media_not_configured")
        params = {"fields": "id,ig_id,permalink", "limit": "100"}
        if asset_candidate:
            params["fields"] += ",children{id,ig_id}"
        for _ in range(3):
            body = await _graph_json(graph, f"{settings.instagram_ig_user_id}/media", params)
            for row in body.get("data", []):
                match_id = valid_id(candidate) and candidate in (row.get("id"), str(row.get("ig_id", "")))
                match_child = asset_candidate and any(
                    candidate in (child.get("id"), str(child.get("ig_id", "")))
                    for child in row.get("children", {}).get("data", []))
                match_url = shortcode and _permalink(row.get("permalink")) == shortcode
                if match_id or match_child or match_url:
                    if (valid_id(candidate) and not (match_id or match_child)) or (shortcode and not match_url):
                        raise StoryMediaError("post_id_mismatch")
                    if not valid_id(row.get("id")):
                        raise StoryMediaError("post_id_mismatch")
                    result = await _graph_json(graph, row["id"], {"fields": fields})
                    if result.get("id") != row["id"] or (shortcode and _permalink(result.get("permalink")) != shortcode):
                        raise StoryMediaError("post_id_mismatch")
                    if match_child and (result.get("media_type") != "CAROUSEL_ALBUM" or not any(
                            candidate in (child.get("id"), str(child.get("ig_id", "")))
                            for child in result.get("children", {}).get("data", []))):
                        raise StoryMediaError("post_id_mismatch")
                    log.info("shared.media.resolved", media_id=result["id"], matched_child=bool(match_child))
                    return result
            paging = body.get("paging", {})
            after = paging.get("cursors", {}).get("after")
            if not paging.get("next") or not isinstance(after, str) or not 0 < len(after) <= 2048:
                break
            params["after"] = after
    raise StoryMediaError("post_unavailable")


async def prepare_shared_media(sources: list[dict], *, abort=None) -> StoryMedia:
    if not isinstance(sources, list) or not 1 <= len(sources) <= 10:
        raise StoryMediaError("invalid_post_count")
    try:
        async with asyncio.timeout(90):
            async with _preparations:
                images, captions, identities, seen = [], [], [], set()
                total = 0
                ad_source = None
                with tempfile.TemporaryDirectory(prefix="shared-media-") as temporary:
                    for source in sources:
                        post = await _post_source(source)
                        if abort and await abort():
                            return StoryMedia(None, "SHARED_POST", [])
                        identity = post.get("id")
                        if "ad_id" in source and post.get("_ad_source") == "marketing_variant":
                            ad_source = "marketing_variant"
                        if not valid_id(identity):
                            raise StoryMediaError("post_id_mismatch")
                        if identity in seen:
                            continue
                        seen.add(identity)
                        identities.append(identity)
                        caption = post.get("caption")
                        if isinstance(caption, str) and caption:
                            captions.append(f"Публикация {len(identities)}, подпись (данные):\n" + caption[:8000])
                        media_type = post.get("media_type")
                        if media_type == "CAROUSEL_ALBUM":
                            children = post.get("children", {})
                            items = children.get("data")
                            if (children.get("paging", {}).get("next") or not isinstance(items, list)
                                    or not 1 <= len(items) <= 10):
                                raise StoryMediaError("incomplete_carousel")
                        else:
                            items = [post]
                        for item_index, item in enumerate(items):
                            kind = item.get("media_type")
                            if kind not in ("IMAGE", "VIDEO"):
                                raise StoryMediaError("unsupported_post")
                            url = validate_media_url(item.get("media_url"))
                            folder = Path(temporary) / f"item-{len(images):03}"
                            folder.mkdir()
                            frames = await _prepare_file(kind, url, folder)
                            for frame in frames:
                                total += len(base64.b64decode(frame["url"].split(",", 1)[1]))
                                frame["label"] = f"Публикация {len(identities)}, элемент {item_index + 1}. " + frame["label"]
                            images.extend(frames)
                            if total > MAX_IMAGE_BYTES or len(images) > 100:
                                raise StoryMediaError("images_too_large")
                return StoryMedia(None, "SHARED_POST", images, "\n\n".join(captions), ad_source=ad_source)
    except StoryMediaError:
        raise
    except TimeoutError:
        raise StoryMediaError("media_timeout") from None
    except Exception:
        raise StoryMediaError("media_failed") from None
