import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _tool_lane_for_business_tests(monkeypatch):
    """Business regressions exercise N30; test_tool_canary restores the real gate."""
    monkeypatch.setattr('src.services.llm.tool_enabled_for', lambda client: True)


@pytest.fixture(autouse=True)
def _review_opt_in_for_business_tests(monkeypatch):
    """Existing primary-response fixtures keep their call budgets; N37 tests opt in.

    The real reviewer is exercised explicitly in test_handoff_review and the
    manager-task integration tests, with the same HTTP isolation as every test.
    """
    monkeypatch.setattr('src.config.settings.manager_review_enabled', False)


@pytest.fixture(autouse=True)
def _disable_real_http(monkeypatch):
    """Keep tests from sending real client or manager messages."""
    import httpx

    def reject_request(*args, **kwargs):
        raise RuntimeError("Real HTTP network disabled in tests; use MockTransport")

    async def reject_async_request(*args, **kwargs):
        raise RuntimeError("Real HTTP network disabled in tests; use MockTransport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async_request)


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


@pytest.fixture(autouse=True)
def _isolate_response_journal(tmp_path, monkeypatch):
    from src.services import llm_response_log
    from src.services import diagnostic_trace

    llm_response_log.close_response_log()
    diagnostic_trace.close_trace_log()
    monkeypatch.setattr(llm_response_log, 'LOG_PATH', tmp_path / 'deepseek-responses.jsonl')
    monkeypatch.setattr(diagnostic_trace, 'LOG_PATH', tmp_path / 'deepseek-trace.jsonl')
    yield
    llm_response_log.close_response_log()
    diagnostic_trace.close_trace_log()
