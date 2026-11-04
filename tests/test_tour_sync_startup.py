"""Catalog recovery orchestration; external services and sends are stubbed."""
import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.config import settings
from src.services import tour_loader, tour_sync


@pytest.fixture
def startup(monkeypatch):
    import src.main as main

    saved = {"text": "=== ТУР: Свежий ===\nОписание", "tours": [], "hash": "saved"}
    monkeypatch.setattr(settings, "tour_sync_enabled", True)
    monkeypatch.setattr(settings, "tour_sync_folder_id", "fixture-folder")
    monkeypatch.setattr(settings, "google_drive_credentials_file", "fixture-credentials")
    monkeypatch.setattr(tour_loader, "_tours_text", "устаревший DOCX")
    monkeypatch.setattr(tour_loader, "load_snapshot", lambda _: saved)
    save = Mock()
    monkeypatch.setattr(tour_loader, "save_snapshot", save)
    notify = AsyncMock()
    monkeypatch.setattr(main, "_notify_tour_sync", notify)
    monkeypatch.setattr(main._tours_initial_loaded, "wait", lambda *_: True)
    return main, saved, save, notify


@pytest.mark.parametrize("failure", ["network", "auth", "raised"])
def test_startup_publishes_last_good_without_rewriting_or_notifying(startup, monkeypatch, failure):
    main, saved, save, notify = startup

    def sync(*_):
        if failure == "raised":
            raise httpx.ConnectError("offline")
        return None, {"status": "error" if failure == "network" else "auth_error"}

    monkeypatch.setattr(tour_sync, "sync_now", sync)
    main._initial_tour_sync()
    assert tour_loader.get_tours_text() == saved["text"]
    assert main.app.state.tours_text == saved["text"]
    save.assert_not_called()
    notify.assert_not_called()


def test_startup_without_last_good_preserves_local_catalog(startup, monkeypatch):
    main, _, save, notify = startup
    monkeypatch.setattr(tour_loader, "load_snapshot", lambda _: None)
    monkeypatch.setattr(tour_sync, "sync_now", lambda *_: (None, {"status": "error"}))
    main._initial_tour_sync()
    assert tour_loader.get_tours_text() == "устаревший DOCX"
    save.assert_not_called()
    notify.assert_not_called()


def test_startup_disabled_does_not_read_drive(startup, monkeypatch):
    main, _, save, notify = startup
    monkeypatch.setattr(settings, "tour_sync_enabled", False)
    sync = Mock()
    monkeypatch.setattr(tour_sync, "sync_now", sync)
    main._initial_tour_sync()
    sync.assert_not_called()
    assert tour_loader.get_tours_text() == "устаревший DOCX"
    save.assert_not_called()
    notify.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("already_current", [False, True])
async def test_worker_reconciles_unchanged_and_respects_disabled(startup, monkeypatch, enabled, already_current):
    main, saved, save, notify = startup
    monkeypatch.setattr(settings, "tour_sync_enabled", enabled)
    if already_current:
        monkeypatch.setattr(tour_loader, "_tours_text", saved["text"])
    publish = Mock(wraps=tour_loader.publish_tours_text)
    monkeypatch.setattr(tour_loader, "publish_tours_text", publish)
    calls = []
    sleeps = 0

    def sync(*_):
        calls.append(True)
        return saved, {"status": "unchanged"}

    async def one_tick(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(tour_sync, "sync_now", sync)
    monkeypatch.setattr(main.asyncio, "sleep", one_tick)
    with pytest.raises(asyncio.CancelledError):
        await main._tour_sync_worker()
    assert bool(calls) is enabled
    assert tour_loader.get_tours_text() == (saved["text"] if enabled or already_current else "устаревший DOCX")
    assert publish.call_count == int(enabled and not already_current)
    save.assert_not_called()
    notify.assert_not_called()
