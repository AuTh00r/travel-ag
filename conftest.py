import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Подменить DB_PATH на временный файл на время каждого теста.

    Без этого тесты, вызывающие реальный `_process_safely`/`process_with_ai`
    с моками только на send_message/AI (напр. tests/test_instagram.py,
    CLIENT_LOST_* сценарии), пишут в боевую data/sessions.db — если тесты
    гоняются на проде (deploy.ps1 шаг 4/5), это создаёт мусорные
    pending_messages с фейковыми recipient_id, которые реальный воркер потом
    пытается доставить и эскалирует в Telegram менеджерам.
    """
    import src.db.pending_messages as pending_module
    import src.db.sessions as sessions_module

    db_path = tmp_path / "test_sessions.db"
    monkeypatch.setattr(sessions_module, "DB_PATH", db_path)
    monkeypatch.setattr(pending_module, "DB_PATH", db_path)
