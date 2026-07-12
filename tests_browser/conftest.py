"""Fixtures for the real-browser suite: a live demo server and a headless
Chromium page that fails the test on any console or page error.

This suite is not part of the default check run; see scripts/ci browser.
"""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

DEMO_DIR = Path(__file__).resolve().parent.parent / "examples" / "demo"


@pytest.fixture(scope="session")
def server_url():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "virel.cli", "dev", "--port", str(port)],
        cwd=DEMO_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(url + "/", timeout=1):
                    break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("demo server exited during startup")
                if time.monotonic() > deadline:
                    raise RuntimeError("demo server did not become ready")
                time.sleep(0.2)
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=[
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
        ])
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda message: errors.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    context.close()
    assert not errors, f"browser reported errors: {errors}"
