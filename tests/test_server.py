"""Server runtime: page serving, typed server actions, schema validation,
streaming over plain HTTP."""

import json

from virel import ui
from virel.server import create_asgi_app

from conftest import asgi_request


def _app(**kwargs):
    return create_asgi_app(dev=True, **kwargs)


def test_serves_compiled_page_with_initial_html():
    @ui.page("/")
    def home():
        count = ui.state(41)
        return ui.Page(ui.Text(f"Count: {count}"),
                       ui.Button("+", aria_label="Increment",
                                 on_click=lambda: count.update(lambda c: c + 1)))

    response = asgi_request(_app(), "GET", "/")
    assert response.status == 200
    assert "Count: 41" in response.text
    assert "text/html" in response.headers["content-type"]


def test_404_for_unknown_route():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("hi"))

    response = asgi_request(_app(), "GET", "/nope")
    assert response.status == 404


def test_action_call_round_trip():
    @ui.server
    def add(a: int, b: int) -> int:
        return a + b

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(_app(), "POST", "/_virel/action/add",
                            body=json.dumps({"a": 2, "b": 3}).encode())
    assert response.status == 200
    assert response.json == {"result": 5}


def test_async_action():
    @ui.server
    async def greet(name: str) -> str:
        return f"hello {name}"

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(_app(), "POST", "/_virel/action/greet",
                            body=b'{"name": "ada"}')
    assert response.json == {"result": "hello ada"}


def test_action_rejects_unknown_and_missing_arguments():
    @ui.server
    def add(a: int, b: int) -> int:
        return a + b

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = _app()
    response = asgi_request(app, "POST", "/_virel/action/add",
                            body=b'{"a": 1, "evil": 2}')
    assert response.status == 400
    assert "unknown argument" in response.json["error"]

    response = asgi_request(app, "POST", "/_virel/action/add", body=b'{"a": 1}')
    assert response.status == 400
    assert "missing argument" in response.json["error"]


def test_action_error_returns_structured_message():
    @ui.server
    def explode(value: str) -> str:
        raise ValueError(f"bad value {value!r}")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(_app(), "POST", "/_virel/action/explode",
                            body=b'{"value": "x"}')
    assert response.status == 500
    assert "bad value" in response.json["error"]


def test_streaming_action_sends_incremental_chunks():
    @ui.server(stream=True)
    async def logs(n: int = 3):
        for i in range(n):
            yield f"line {i}\n"

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(_app(), "POST", "/_virel/action/logs", body=b"{}")
    assert response.status == 200
    assert len(response.chunks) == 3
    assert response.text == "line 0\nline 1\nline 2\n"


def test_dynamic_route_with_query_params():
    @ui.page("/projects/{project_id}")
    def project(project_id: str, tab: str = "overview"):
        return ui.Page(ui.Text(f"{project_id}:{tab}"))

    app = _app()
    response = asgi_request(app, "GET", "/projects/atlas")
    assert "atlas:overview" in response.text
    response = asgi_request(app, "GET", "/projects/atlas", query="tab=runs")
    assert "atlas:runs" in response.text


def test_runtime_and_css_served():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = _app()
    js = asgi_request(app, "GET", "/_virel/runtime.js")
    assert js.status == 200
    assert "export function signal" in js.text
    css = asgi_request(app, "GET", "/_virel/app.css")
    assert css.status == 200
    assert "--v-accent" in css.text


def test_security_headers_present():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(_app(), "GET", "/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_public_assets_never_cache_in_dev(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "widget.js").write_text("export const x = 1;")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True, public_dir=public)
    response = asgi_request(app, "GET", "/public/widget.js")
    assert response.status == 200
    assert response.headers["cache-control"] == "no-store"


def test_public_assets_revalidate_with_etag_in_production(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "widget.js").write_text("export const x = 1;")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=False, public_dir=public)
    first = asgi_request(app, "GET", "/public/widget.js")
    assert first.status == 200
    assert first.headers["cache-control"] == "no-cache"
    etag = first.headers["etag"]

    cached = asgi_request(app, "GET", "/public/widget.js",
                          headers=[(b"if-none-match", etag.encode())])
    assert cached.status == 304
    assert cached.body == b""

    (public / "widget.js").write_text("export const x = 2;")
    changed = asgi_request(app, "GET", "/public/widget.js",
                           headers=[(b"if-none-match", etag.encode())])
    assert changed.status == 200
    assert "x = 2" in changed.text


def test_watch_token_tracks_public_assets(tmp_path):
    import os

    public = tmp_path / "public"
    public.mkdir()
    asset = public / "widget.js"
    asset.write_text("export const x = 1;")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True, public_dir=public)
    before = asgi_request(app, "GET", "/_virel/reload-token").json["token"]
    stamp = asset.stat().st_mtime + 10
    os.utime(asset, (stamp, stamp))
    after = asgi_request(app, "GET", "/_virel/reload-token").json["token"]
    assert after != before


def test_static_mount_serves_files_outside_public(tmp_path):
    vendor = tmp_path / "vendor-pkg"
    vendor.mkdir()
    (vendor / "widget.js").write_text("export const x = 1;")
    (tmp_path / "secret.txt").write_text("top secret")
    ui.use_static("/vendor/widgets", vendor)

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = _app()
    response = asgi_request(app, "GET", "/vendor/widgets/widget.js")
    assert response.status == 200
    assert "x = 1" in response.text
    assert response.headers["cache-control"] == "no-store"
    escape = asgi_request(app, "GET", "/vendor/widgets/../secret.txt")
    assert escape.status == 404


def test_static_mount_rejects_reserved_and_missing_paths(tmp_path):
    import pytest
    from virel.expr import VirelCompileError

    with pytest.raises(VirelCompileError, match="outside /public"):
        ui.use_static("/public/vendor", tmp_path)
    with pytest.raises(VirelCompileError, match="outside /public"):
        ui.use_static("/_virel/vendor", tmp_path)
    with pytest.raises(VirelCompileError, match="does not exist"):
        ui.use_static("/vendor", tmp_path / "nowhere")


def test_watch_token_tracks_static_mounts(tmp_path):
    import os

    vendor = tmp_path / "vendor-pkg"
    vendor.mkdir()
    asset = vendor / "widget.js"
    asset.write_text("export const x = 1;")
    ui.use_static("/vendor/widgets", vendor)

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = _app()
    before = asgi_request(app, "GET", "/_virel/reload-token").json["token"]
    stamp = asset.stat().st_mtime + 10
    os.utime(asset, (stamp, stamp))
    after = asgi_request(app, "GET", "/_virel/reload-token").json["token"]
    assert after != before
