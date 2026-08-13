import functools
import http.server
import socketserver
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def static_server():
    """Serve the repo over http so ES modules can be imported by the browser."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(REPO_ROOT))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()


@pytest.fixture(scope="module")
def browser():
    # Module-scoped, not session-scoped: playwright's sync API drives its
    # event loop with a greenlet in this OS thread and leaves that loop
    # marked "running" for as long as the `sync_playwright()` context stays
    # open. A session-scoped browser would therefore still be open while
    # later pytest-asyncio tests run in the same thread, and every one of
    # them would fail with "Cannot run the event loop while another loop is
    # running". Module scope still amortises the browser launch across all
    # tests in this file while closing it before the next test module runs.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            # This host's OS predates what the installed playwright package's
            # pinned chromium revision supports, so `playwright install`
            # refuses to fetch it (and the exhibition machine has no network
            # access to fall back on anyway). Reuse whatever chromium build
            # is already present in the local playwright cache instead of
            # requiring an exact revision match.
            candidates = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
            if not candidates:
                raise
            browser = p.chromium.launch(executable_path=str(candidates[-1]))
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    yield page
    page.close()
