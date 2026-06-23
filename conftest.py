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
