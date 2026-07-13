"""Development-server DX (SPEC 15.2)."""

from virel import ui
from virel.server import create_asgi_app

from conftest import asgi_request


def test_dev_error_overlay_renders_the_diagnostic():
    @ui.page("/broken")
    def broken():
        flag = ui.state(True)
        if flag:  # reactive value in a Python if -> compile error
            return ui.Page(ui.Text("never"))
        return ui.Page(ui.Text("never"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/broken")
    # A route-aware overlay, HTTP 200 so the browser renders it, with the
    # structured diagnostic and a recovery poll.
    assert response.status == 200
    assert "Virel compile error" in response.text
    assert "/broken" in response.text
    assert "VRL001" in response.text          # the stable error code
    assert "ui.When" in response.text         # a suggested fix
    assert "reload-token" in response.text     # auto-recovery poll


def test_production_does_not_leak_the_overlay():
    @ui.page("/broken2")
    def broken2():
        flag = ui.state(True)
        if flag:
            return ui.Page(ui.Text("never"))
        return ui.Page(ui.Text("never"))

    app = create_asgi_app(dev=False)
    response = asgi_request(app, "GET", "/broken2")
    assert response.status == 500
    assert "VRL001" not in response.text      # no diagnostic in prod


def test_dev_js_exposes_locales_and_toolbar():
    ui.messages("en", {"hi": "Hello"})
    ui.messages("pt", {"hi": "Ola"})

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    dev_js = asgi_request(app, "GET", "/_virel/dev.js").text
    assert "__virelLocales" in dev_js
    assert '"pt"' in dev_js
    assert "__virelTelemetry" in dev_js       # the observability panel
    assert "Cycle responsive viewport" in dev_js
