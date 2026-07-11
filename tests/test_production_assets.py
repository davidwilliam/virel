"""Production asset hashing, caching, and compaction (SPEC 9.1)."""

import re

from virel import ui
from virel.compiler import compile_page
from virel.registry import active_registry
from virel.server import create_asgi_app
from virel.theme import Theme, asset_version, build_stylesheet, compact, runtime_js

from conftest import asgi_request


def _page():
    @ui.page("/")
    def home():
        count = ui.state(0)
        return ui.Page(ui.Text(f"{count}"),
                       ui.Button("Add", on_click=lambda: count.set(1)))
    return active_registry().pages["/"]


def test_hashed_builds_reference_content_hashed_modules():
    page = _page()
    result = compile_page(page, hashed=True)
    assert re.fullmatch(r"index\.[0-9a-f]{8}\.js", result.js_module)
    assert f"/_virel/page/{result.js_module}" in result.html
    # Shared assets are version-busted.
    version = asset_version(None)
    assert f"/_virel/app.css?v={version}" in result.html
    assert f"/_virel/runtime.js?v={version}" in result.js
    # Deterministic: same content, same name.
    assert compile_page(page, hashed=True).js_module == result.js_module


def test_dev_builds_keep_plain_names():
    page = _page()
    result = compile_page(page, dev=True)
    assert result.js_module == "index.js"
    assert "?v=" not in result.html


def test_production_server_serves_hashed_module_with_immutable_cache():
    page = _page()
    app = create_asgi_app(dev=False)
    html = asgi_request(app, "GET", "/")
    module = re.search(r"/_virel/page/(index\.[0-9a-f]{8}\.js)", html.text).group(1)
    response = asgi_request(app, "GET", f"/_virel/page/{module}")
    assert response.status == 200
    assert "immutable" in response.headers["cache-control"]
    runtime = asgi_request(app, "GET", "/_virel/runtime.js")
    assert "immutable" in runtime.headers["cache-control"]


def test_dev_server_disables_asset_caching():
    _page()
    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/_virel/runtime.js")
    assert response.headers["cache-control"] == "no-store"


def test_compact_strips_comments_and_blanks_only():
    source = runtime_js()
    small = compact(source)
    assert len(small) < len(source)
    assert "//" not in [line.strip()[:2] for line in small.splitlines()]
    assert "export function signal" in small
    # Compacted stylesheet still parses meaningfully.
    css = compact(build_stylesheet(Theme()))
    assert ".v-btn" in css
    assert "/*" not in css
