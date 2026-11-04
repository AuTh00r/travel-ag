import asyncio
import base64
import struct
from unittest.mock import AsyncMock

import pytest
import httpx

from src.exceptions import StoryMediaError
from src.services import story_media as service

CDN = "https://scontent.cdninstagram.com/source.jpg?private=PRIVATE"
JPEG = b"\xff\xd8\xfforiginal"
PNG = b"\x89PNG\r\n\x1a\noriginal"
MP4 = b"".join(struct.pack(">I4s", 8, kind) for kind in (b"ftyp", b"moov", b"mdat"))


def decoder(monkeypatch, fail_at=None):
    folders = []

    async def decode(source, folder, kind):
        folders.append(folder)
        if len(folders) == fail_at:
            raise StoryMediaError("decode_failed")
        if kind == "IMAGE":
            return {"frames": [{"file": source.name}]}
        assert kind == "VIDEO" and source.suffix == ".mp4"
        result = []
        for index in range(10):
            name = f"frame-{index:03}.jpg"
            (folder / name).write_bytes(JPEG + bytes([index]))
            result.append({"file": name, "target_seconds": index * 1.5})
        return {"frames": result}

    monkeypatch.setattr(service, "_decode", decode)
    return folders


@pytest.mark.parametrize("data,kind,count", [(JPEG, "IMAGE", 1), (PNG, "IMAGE", 1), (MP4, "VIDEO", 10)])
async def test_mention_uses_actual_bytes_and_original_frames(monkeypatch, data, kind, count):
    download = AsyncMock(return_value=data)
    monkeypatch.setattr(service, "_download", download)
    folders = decoder(monkeypatch)
    media = await service.prepare_images([CDN], image_types=["story_mention"])
    download.assert_awaited_once_with(CDN, "AUTO")
    assert len(media.images) == count
    assert media.image_types == ["story_mention"] * count
    assert media.media_types == [kind]
    assert all("Вложение 1/1" in image["label"] for image in media.images)
    assert all(not folder.exists() for folder in folders)
    if kind == "IMAGE":
        assert base64.b64decode(media.images[0]["url"].split(",")[1]) == data
    else:
        assert "Кадр 1/10, 0.000 с." in media.images[0]["label"]
        assert "Кадр 10/10, 13.500 с." in media.images[-1]["label"]


async def test_mixed_visual_batch_keeps_source_positions_and_separate_folders(monkeypatch):
    monkeypatch.setattr(service, "_download", AsyncMock(side_effect=[JPEG, MP4, PNG, MP4]))
    folders = decoder(monkeypatch)
    media = await service.prepare_images([CDN] * 4, image_types=["image", "story_mention", "story_mention", "video"])
    assert len(media.images) == 22
    assert media.image_types == ["image"] + ["story_mention"] * 11 + ["video"] * 10
    assert media.media_types == ["IMAGE", "VIDEO", "IMAGE", "VIDEO"]
    assert "Вложение 2/4" in media.images[1]["label"]
    assert "Вложение 3/4" in media.images[11]["label"]
    assert "Вложение 4/4" in media.images[12]["label"]
    assert folders[1] != folders[3]
    assert all(not folder.exists() for folder in folders)


@pytest.mark.parametrize("mode", ["bad_file", "partial_failure", "aggregate_limit", "cancel"])
async def test_visual_failures_cleanup_and_return_no_partial_set(monkeypatch, mode):
    download = AsyncMock(side_effect=[MP4, b"not media" if mode == "bad_file" else MP4])
    monkeypatch.setattr(service, "_download", download)
    folders = decoder(monkeypatch, fail_at=2 if mode == "partial_failure" else None)
    if mode == "aggregate_limit":
        monkeypatch.setattr(service, "MAX_IMAGE_BYTES", len(JPEG + b"\x00") * 15)
    if mode == "cancel":
        download.side_effect = [MP4, asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError if mode == "cancel" else StoryMediaError):
        await service.prepare_images([CDN, CDN], image_types=["story_mention", "video"])
    assert folders and all(not folder.exists() for folder in folders)


@pytest.mark.parametrize("urls,kinds", [
    ([CDN], []), ([CDN], ["audio"]), ([CDN, None], ["video", "image"]),
])
async def test_visual_validates_whole_batch_before_download(monkeypatch, urls, kinds):
    download = AsyncMock()
    monkeypatch.setattr(service, "_download", download)
    with pytest.raises(StoryMediaError):
        await service.prepare_images(urls, image_types=kinds)
    download.assert_not_awaited()


async def test_ordinary_photo_cannot_become_video(monkeypatch):
    monkeypatch.setattr(service, "_download", AsyncMock(return_value=MP4))
    decode = AsyncMock()
    monkeypatch.setattr(service, "_decode", decode)
    with pytest.raises(StoryMediaError, match="unsupported_image"):
        await service.prepare_images([CDN])
    decode.assert_not_awaited()


async def test_gif_bytes_ignored_without_losing_neighboring_photo(monkeypatch):
    monkeypatch.setattr(service, "_download", AsyncMock(side_effect=[b"GIF89aDATA", JPEG]))
    folders = decoder(monkeypatch)
    media = await service.prepare_images([CDN, CDN], image_types=["image", "image"])
    assert len(media.images) == 1 and media.image_types == ["image"]
    assert media.media_types == ["IGNORED", "IMAGE"]
    assert len(folders) == 1 and all(not folder.exists() for folder in folders)


@pytest.mark.parametrize("content_type", ["video/mp4", "application/octet-stream", "image/jpeg"])
async def test_mention_http_download_supports_actual_media_without_token(monkeypatch, content_type):
    data = JPEG if content_type == "image/jpeg" else MP4
    def respond(request):
        assert "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, content=data, headers={"content-type": content_type})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=httpx.MockTransport(respond), **kwargs))
    decoder(monkeypatch)
    media = await service.prepare_images([CDN], image_types=["story_mention"])
    assert len(media.images) == (1 if data == JPEG else 10)


async def test_video_duration_limit_precedes_decoder(monkeypatch):
    monkeypatch.setattr(service, "_download", AsyncMock(return_value=MP4))
    monkeypatch.setattr(service, "video_track_duration", lambda data: 91.0)
    decode = AsyncMock()
    monkeypatch.setattr(service, "_decode", decode)
    with pytest.raises(StoryMediaError, match="video_too_long"):
        await service.prepare_images([CDN], image_types=["video"])
    decode.assert_not_awaited()
