"""Mounting inside existing ASGI stacks and middleware (SPEC 9.4, 20.4)."""

import pytest

from virel import ui
from virel.integrations import PathMount, mount
from virel.server import create_asgi_app

from conftest import asgi_request


def _virel_app(**kwargs):
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("virel page"))

    return create_asgi_app(dev=True, **kwargs)


def _echo_app(label):
    async def app(scope, receive, send):
        body = f"{label}: {scope['root_path']}|{scope['path']}".encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
    return app


def test_path_mount_dispatches_prefixes_and_defaults_to_virel():
    application = PathMount(
        default=_virel_app(),
        mounts={"/api": _echo_app("api"), "/api/v2": _echo_app("v2")},
    )
    assert "virel page" in asgi_request(application, "GET", "/").text
    # Prefix apps get submount semantics: prefix moves to root_path.
    assert asgi_request(application, "GET", "/api/users").text == "api: /api|/users"
    # Longest prefix wins.
    assert asgi_request(application, "GET", "/api/v2/users").text == "v2: /api/v2|/users"
    # Boundary matching: /apiarchive is not under /api.
    assert asgi_request(application, "GET", "/apiarchive").status == 404


def test_path_mount_validates_prefixes():
    app = _virel_app()
    with pytest.raises(ValueError, match="prefix"):
        PathMount(default=app, mounts={"api": _echo_app("x")})
    with pytest.raises(ValueError, match="prefix"):
        PathMount(default=app, mounts={"/": _echo_app("x")})


def test_mount_attaches_to_fastapi_style_hosts():
    mounted = {}

    class FakeFastAPI:
        def mount(self, path, app):
            mounted["path"] = path
            mounted["app"] = app

    host = FakeFastAPI()
    virel_app = _virel_app()
    mount(host, virel_app)
    assert mounted["path"] == "/"
    assert "virel page" in asgi_request(mounted["app"], "GET", "/").text
    with pytest.raises(ValueError, match="root path"):
        mount(FakeFastAPI(), virel_app, path="/app")


def test_middleware_wraps_the_app():
    def stamp(app):
        async def wrapped(scope, receive, send):
            async def sending(message):
                if message["type"] == "http.response.start":
                    message["headers"] = list(message.get("headers", []))
                    message["headers"].append((b"x-stamped", b"yes"))
                await send(message)
            await app(scope, receive, sending)
        return wrapped

    app = _virel_app(middleware=[stamp])
    response = asgi_request(app, "GET", "/")
    assert response.headers["x-stamped"] == "yes"
    assert "virel page" in response.text


def test_use_middleware_registers_globally():
    def flag(app):
        async def wrapped(scope, receive, send):
            async def sending(message):
                if message["type"] == "http.response.start":
                    message["headers"] = list(message.get("headers", []))
                    message["headers"].append((b"x-global", b"on"))
                await send(message)
            await app(scope, receive, sending)
        return wrapped

    ui.use_middleware(flag)
    response = asgi_request(_virel_app(), "GET", "/")
    assert response.headers["x-global"] == "on"
