import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import numpy as np
import pytest

from src.config import settings
from src.exceptions import VoiceMediaError
from src.services import gigaam_worker as worker
from src.services import voice_media as service

CDN = "https://scontent.cdninstagram.com/voice.mp4?secret=PRIVATE"


@pytest.mark.parametrize("target", ["http://cdninstagram.com/a", "https://localhost/a",
    "https://cdninstagram.com.evil.test/a", "https://cdninstagram.com/a#fragment", None])
async def test_untrusted_url_rejected_before_network(monkeypatch, target):
    monkeypatch.setattr(settings, "voice_media_enabled", True)
    download = AsyncMock()
    monkeypatch.setattr(service, "_download", download)
    with pytest.raises(VoiceMediaError, match="invalid_voice_url"):
        await service.VoiceRecognizer().recognize([target])
    download.assert_not_awaited()


@pytest.mark.parametrize("failure", ["redirect", "size", "type", "encoding", "length"])
async def test_downloader_enforces_boundaries_and_does_not_forward_credentials(tmp_path, failure):
    def respond(request):
        assert "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        if failure == "redirect":
            return httpx.Response(302, headers={"location": "https://evil.test/audio"})
        headers = {"content-type": "audio/mp4"}
        if failure == "size":
            headers["content-length"] = str(service.MAX_FILE_BYTES + 1)
        if failure == "type":
            headers["content-type"] = "text/html"
        if failure == "encoding":
            headers["content-encoding"] = "gzip"
        if failure == "length":
            headers["content-length"] = "99"
        return httpx.Response(200, stream=httpx.ByteStream(b"audio"), headers=headers)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond),
                                headers={"Accept-Encoding": "identity"}) as client:
        with pytest.raises(VoiceMediaError):
            await service._download(client, CDN, tmp_path / "voice.bin", service.MAX_TOTAL_BYTES)


async def test_valid_cdn_redirect_and_mp4_audio_download(tmp_path):
    def respond(request):
        if request.url.path.endswith("voice.mp4"):
            return httpx.Response(302, headers={"location": "/actual.m4a"})
        return httpx.Response(200, content=b"AAC", headers={"content-type": "video/mp4"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        target = tmp_path / "voice.bin"
        assert await service._download(client, CDN, target, 20) == 3
        assert target.read_bytes() == b"AAC"


@pytest.fixture
def resident(monkeypatch):
    monkeypatch.setattr(settings, "voice_media_enabled", True)
    instance = service.VoiceRecognizer()
    process = SimpleNamespace(returncode=None, stdin=SimpleNamespace(write=Mock(), drain=AsyncMock()),
                              wait=AsyncMock())
    def kill():
        process.returncode = -9
    process.kill = Mock(side_effect=kill)
    folders = []
    async def download(client, url, target, remaining):
        target.write_bytes(b"audio")
        folders.append(target.parent)
        return 5
    async def start():
        instance.process = process
    monkeypatch.setattr(service, "_download", download)
    monkeypatch.setattr(instance, "_start", start)
    monkeypatch.setattr(instance, "_read", AsyncMock(return_value={"texts": ["Варшава"]}))
    return instance, process, folders


async def test_resident_worker_reused_temp_files_removed(resident):
    instance, process, folders = resident
    assert await instance.recognize([CDN]) == ["Варшава"]
    assert await instance.recognize([CDN]) == ["Варшава"]
    process.kill.assert_not_called()
    assert all(not folder.exists() for folder in folders)
    assert len({str(folder) for folder in folders}) == 2
    request = json.loads(process.stdin.write.call_args.args[0])
    assert all("PRIVATE" not in path for path in request["paths"])
    await instance.close()
    process.kill.assert_called_once()


@pytest.mark.parametrize("mode", ["cancel", "timeout", "protocol"])
async def test_worker_failure_kills_before_file_cleanup_and_releases_queue(resident, mode):
    instance, process, folders = resident
    original_wait = process.wait
    async def wait():
        assert folders[0].exists()
        return await original_wait()
    process.wait = AsyncMock(side_effect=wait)
    instance._read.side_effect = {"cancel": asyncio.CancelledError(), "timeout": TimeoutError(),
                                 "protocol": VoiceMediaError("voice_worker")}[mode]
    with pytest.raises(asyncio.CancelledError if mode == "cancel" else VoiceMediaError):
        await instance.recognize([CDN])
    process.kill.assert_called_once()
    assert instance.pending == 0 and not instance.lock.locked()
    assert not folders[0].exists()


async def test_queue_timeout_does_not_kill_another_clients_worker(resident, monkeypatch):
    instance, process, folders = resident
    instance.process = process
    monkeypatch.setattr(service, "QUEUE_SECONDS", 0.01)
    await instance.lock.acquire()
    try:
        with pytest.raises(VoiceMediaError, match="voice_busy"):
            await instance.recognize([CDN])
        process.kill.assert_not_called()
        assert instance.pending == 0 and not folders
    finally:
        instance.lock.release()


async def test_takeover_after_queue_prevents_download(resident):
    instance, process, folders = resident
    assert await instance.recognize([CDN], abort=AsyncMock(return_value=True)) == []
    assert not folders
    process.stdin.write.assert_not_called()


async def test_admission_cap_prevents_more_jobs(resident):
    instance, _, folders = resident
    instance.pending = service.MAX_PENDING
    with pytest.raises(VoiceMediaError, match="voice_busy"):
        await instance.recognize([CDN])
    assert not folders and instance.pending == service.MAX_PENDING


async def test_cancel_during_spawn_retains_and_terminates_owned_child(resident, monkeypatch, tmp_path):
    instance, process, folders = resident
    python = tmp_path / "isolated-python.exe"
    python.write_bytes(b"test")
    monkeypatch.setattr(settings, "voice_python_executable", str(python))
    monkeypatch.setattr(settings, "voice_model_dir", str(tmp_path))
    monkeypatch.setattr(instance, "_start", service.VoiceRecognizer._start.__get__(instance))
    started, release = asyncio.Event(), asyncio.Event()
    async def create(*_, **__):
        started.set()
        await release.wait()
        return process
    monkeypatch.setattr(service.asyncio, "create_subprocess_exec", create)
    task = asyncio.create_task(instance.recognize([CDN]))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.kill.assert_called_once()
    assert instance.process is None and instance.pending == 0 and not instance.lock.locked()
    assert all(not folder.exists() for folder in folders)


def test_long_chunks_cover_full_audio_and_keep_bounded_overlap():
    # Sample indices reveal every span without a decoder or model.
    audio = np.arange(61 * worker.SAMPLE_RATE, dtype=np.float32)
    spans = list(worker.chunks(audio))
    assert spans[0][0] == 0 and spans[-1][-1] == audio[-1]
    assert all(len(span) <= 25 * worker.SAMPLE_RATE for span in spans)
    for left, right in zip(spans, spans[1:]):
        assert left[-1] - right[0] == worker.SAMPLE_RATE // 2 - 1


def test_boundary_dedup_preserves_different_and_short_repeated_words():
    assert worker.join_transcripts("Тур в Варшаву", "в Варшаву и по визе") == "Тур в Варшаву и по визе"
    assert worker.join_transcripts("да", "да да") == "да да да"
    assert worker.join_transcripts("про Варшаву", "Варшаву, спасибо") == "про Варшаву спасибо"


def test_worker_aggregate_duration_and_empty_voice(monkeypatch):
    remaining = []
    def decode(path, budget):
        remaining.append(budget)
        return np.ones(worker.SAMPLE_RATE * 20, dtype=np.float32)
    monkeypatch.setattr(worker, "decode", decode)
    model = SimpleNamespace(recognize=Mock(return_value="Варшава"))
    assert worker.recognize_paths(model, ["a", "b"])["duration"] == 40
    assert remaining == [180, 160]
    monkeypatch.setattr(worker, "decode", lambda *_: np.zeros(worker.SAMPLE_RATE, dtype=np.float32))
    with pytest.raises(worker.WorkerError, match="voice_empty"):
        worker.recognize_paths(model, ["silence"])


def test_playlist_rejected_before_container_can_follow_urls(tmp_path, monkeypatch):
    opened = Mock()
    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(open=opened))
    path = tmp_path / "voice.bin"
    path.write_bytes(b"#EXTM3U\nhttps://evil.test/audio")
    with pytest.raises(worker.WorkerError, match="voice_format"):
        worker.decode(path, 180)
    opened.assert_not_called()
