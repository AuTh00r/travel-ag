"""Bounded CDN download and one isolated, resident GigaAM process."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urljoin

import httpx

from src.config import settings
from src.exceptions import StoryMediaError, VoiceMediaError
from src.services.story_media import validate_media_url

MAX_VOICES = 3
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_PENDING = 8
QUEUE_SECONDS = 30
JOB_SECONDS = 90
_MIMES = {"audio/mp4", "audio/mpeg", "audio/ogg", "audio/wav", "audio/x-wav",
          "audio/aac", "audio/x-m4a", "audio/flac", "video/mp4", "application/octet-stream"}


def _url(value: object) -> str:
    try:
        if not isinstance(value, str) or len(value) > 8192:
            raise StoryMediaError("invalid_media_url")
        return validate_media_url(value)
    except StoryMediaError:
        raise VoiceMediaError("invalid_voice_url") from None


async def _download(client: httpx.AsyncClient, url: str, target: Path, remaining: int) -> int:
    for hop in range(4):
        url = _url(url)
        async with client.stream("GET", url) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                if hop == 3 or not response.headers.get("location"):
                    raise VoiceMediaError("voice_redirect")
                url = _url(urljoin(url, response.headers["location"]))
                continue
            if response.status_code != 200:
                raise VoiceMediaError("voice_download")
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise VoiceMediaError("voice_encoding")
            if response.headers.get("content-type", "").split(";", 1)[0].lower() not in _MIMES:
                raise VoiceMediaError("voice_format")
            declared = response.headers.get("content-length")
            try:
                size = int(declared) if declared is not None else None
            except ValueError:
                raise VoiceMediaError("voice_download") from None
            limit = min(MAX_FILE_BYTES, remaining)
            if size is not None and (size < 1 or size > limit):
                raise VoiceMediaError("voice_size")
            written = 0
            with target.open("wb") as output:
                async for chunk in response.aiter_bytes():
                    written += len(chunk)
                    if written > limit:
                        raise VoiceMediaError("voice_size")
                    output.write(chunk)
            if written == 0 or (size is not None and written != size):
                raise VoiceMediaError("voice_download")
            return written
    raise VoiceMediaError("voice_redirect")


class VoiceRecognizer:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.pending = 0
        self.process = None

    async def _stop(self):
        process, self.process = self.process, None
        if process is not None:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()

    async def close(self):
        async with self.lock:
            await self._stop()

    async def _read(self) -> dict:
        line = await self.process.stdout.readline()
        try:
            if not line or len(line) > 65536:
                raise ValueError
            reply = json.loads(line)
            if not isinstance(reply, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            raise VoiceMediaError("voice_worker") from None
        if "error" in reply:
            allowed = {"voice_format", "voice_duration", "voice_empty", "voice_decode", "voice_model"}
            raise VoiceMediaError(reply["error"] if reply["error"] in allowed else "voice_worker")
        return reply

    async def _start(self):
        if self.process is not None and self.process.returncode is None:
            return
        python = Path(settings.voice_python_executable)
        model = Path(settings.voice_model_dir)
        if (not settings.voice_python_executable or not python.is_file()
                or not settings.voice_model_dir or not model.is_dir()):
            raise VoiceMediaError("voice_not_configured")
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
               "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
               "PYTHONIOENCODING": "utf-8"}
        creation = asyncio.create_task(asyncio.create_subprocess_exec(
            str(python), "-u", str(Path(__file__).with_name("gigaam_worker.py")), str(model),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=65536, env=env,
            creationflags=0x08000000 if os.name == "nt" else 0,
        ))
        try:
            self.process = await asyncio.shield(creation)
        except asyncio.CancelledError:
            # Creation can already have spawned the child; retain ownership before cancellation.
            self.process = await creation
            raise
        if await self._read() != {"ready": 1}:
            raise VoiceMediaError("voice_worker")

    async def recognize(self, urls: list[object], *, abort: Callable[[], Awaitable[bool]] | None = None) -> list[str]:
        if not settings.voice_media_enabled:
            raise VoiceMediaError("voice_disabled")
        if not 1 <= len(urls) <= MAX_VOICES:
            raise VoiceMediaError("voice_count")
        validated = [_url(value) for value in urls]
        if self.pending >= MAX_PENDING:
            raise VoiceMediaError("voice_busy")
        self.pending += 1
        acquired = False
        try:
            try:
                await asyncio.wait_for(self.lock.acquire(), QUEUE_SECONDS)
                acquired = True
            except TimeoutError:
                raise VoiceMediaError("voice_busy") from None
            if abort and await abort():
                return []
            try:
                # Files stay inside the job lifetime. Kill/wait precedes their cleanup.
                with tempfile.TemporaryDirectory(prefix="sundita-voice-") as folder:
                    try:
                        async with asyncio.timeout(JOB_SECONDS):
                            paths, total = [], 0
                            async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                                        headers={"Accept-Encoding": "identity"}, trust_env=False) as client:
                                for index, url in enumerate(validated):
                                    if abort and await abort():
                                        return []
                                    path = Path(folder) / f"voice-{index}.bin"
                                    total += await _download(client, url, path, MAX_TOTAL_BYTES - total)
                                    paths.append(str(path))
                            if abort and await abort():
                                return []
                            await self._start()
                            if abort and await abort():
                                return []
                            self.process.stdin.write((json.dumps({"paths": paths}) + "\n").encode())
                            await self.process.stdin.drain()
                            reply = await self._read()
                            texts = reply.get("texts")
                            if (not isinstance(texts, list) or len(texts) != len(paths)
                                    or any(not isinstance(text, str) or not text.strip() for text in texts)):
                                raise VoiceMediaError("voice_empty")
                            return [text.strip() for text in texts]
                    except BaseException:
                        await self._stop()
                        raise
            except VoiceMediaError:
                raise
            except TimeoutError:
                raise VoiceMediaError("voice_timeout") from None
            except asyncio.CancelledError:
                raise
            except Exception:
                raise VoiceMediaError("voice_worker") from None
        finally:
            self.pending -= 1
            if acquired:
                self.lock.release()


recognizer = VoiceRecognizer()


async def transcribe_voice(urls: list[object], *, abort=None) -> list[str]:
    return await recognizer.recognize(urls, abort=abort)


async def close_voice_worker() -> None:
    await recognizer.close()
