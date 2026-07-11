"""Optimistic mutation with rollback, route guards, and locale-aware
formatting."""

import datetime

import pytest

from virel import ui
from virel.compiler import build_static, compile_page
from virel.expr import TraceContext, VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


# -- optimistic mutation -------------------------------------------------------

def _togglable(fail=False):
    @ui.server
    def set_status(status: str) -> str:
        if fail:
            raise RuntimeError("storage unavailable")
        return status
    return set_status


def _status_page(action):
    def page():
        status = ui.state("idle")
        error = ui.state("")
        return ui.Page(
            ui.Text(f"status: {status}"),
            ui.Button("Activate",
                      on_click=lambda: action.call(
                          {"status": "active"},
                          into=status,
                          optimistic=(status, "active"),
                          error_into=error)),
            ui.When(error != "", then=ui.Alert(error, intent="danger")),
        )
    return page


def test_optimistic_emits_capture_and_rollback():
    action = _togglable()
    ui.page("/")(_status_page(action))
    result = compile_page(active_registry().pages["/"])
    assert "const __prev = S.s1.get();" in result.js
    assert 'S.s1.set("active");' in result.js
    assert "S.s1.set(__prev);" in result.js


def test_optimistic_success_keeps_server_result():
    action = _togglable()
    view = ui.test.render(_status_page(action))
    view.get_by_role("button", name="Activate").click()
    assert "status: active" in view.query_text()


def test_optimistic_failure_rolls_back_and_reports():
    action = _togglable(fail=True)
    view = ui.test.render(_status_page(action))
    view.get_by_role("button", name="Activate").click()
    text = view.query_text()
    assert "status: idle" in text  # rolled back
    assert "storage unavailable" in text


def test_optimistic_in_ast_handler():
    action = _togglable()

    def page():
        status = ui.state("idle")

        def activate():
            if status == "idle":
                action.call({"status": "active"}, into=status,
                            optimistic=(status, "active"))

        return ui.Page(ui.Text(f"s: {status}"),
                       ui.Button("Go", on_click=activate))

    view = ui.test.render(page)
    view.get_by_role("button", name="Go").click()
    assert "s: active" in view.query_text()


# -- route guards ---------------------------------------------------------------

def _guarded_app(guard=None, default=None, action_guard=None):
    if default:
        ui.use_guard(default)

    @ui.page("/admin", guard=guard)
    def admin():
        return ui.Page(ui.Text("admin area"))

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("public"))

    @ui.server(guard=action_guard)
    def sensitive() -> str:
        return "secret"

    return create_asgi_app(dev=True)


def test_guard_allows_denies_and_redirects():
    def guard(request: ui.Request):
        token = request.query.get("token") or request.headers.get("x-token")
        if token == "letmein":
            return None
        if token:
            return ui.deny(403, "bad token")
        return ui.redirect("/")

    app = _guarded_app(guard=guard)
    allowed = asgi_request(app, "GET", "/admin", query="token=letmein")
    assert allowed.status == 200
    assert "admin area" in allowed.text

    redirected = asgi_request(app, "GET", "/admin")
    assert redirected.status == 303
    assert redirected.headers["location"] == "/"

    denied = asgi_request(app, "GET", "/admin", query="token=wrong")
    assert denied.status == 403
    assert "bad token" in denied.text


def test_guard_reads_cookies_and_supports_async():
    async def guard(request: ui.Request):
        if request.cookies.get("session") != "valid":
            return ui.deny(401, "sign in first")

    app = _guarded_app(guard=guard)
    response = asgi_request(app, "GET", "/admin",
                            headers=[(b"cookie", b"session=valid")])
    assert response.status == 200
    response = asgi_request(app, "GET", "/admin")
    assert response.status == 401


def test_action_guard_returns_json_errors():
    def guard(request: ui.Request):
        if request.headers.get("authorization") != "Bearer ok":
            return ui.redirect("/login")

    app = _guarded_app(action_guard=guard)
    response = asgi_request(app, "POST", "/_virel/action/sensitive", body=b"{}")
    assert response.status == 401
    assert response.json["error"] == "authentication required"
    assert response.json["redirect"] == "/login"

    response = asgi_request(app, "POST", "/_virel/action/sensitive", body=b"{}",
                            headers=[(b"content-type", b"application/json"),
                                     (b"authorization", b"Bearer ok")])
    assert response.status == 200


def test_default_guard_applies_everywhere():
    def guard(request: ui.Request):
        if request.path != "/" and "key" not in request.query:
            return ui.deny(403, "no key")

    app = _guarded_app(default=guard)
    assert asgi_request(app, "GET", "/").status == 200
    assert asgi_request(app, "GET", "/admin").status == 403
    assert asgi_request(app, "GET", "/admin", query="key=1").status == 200


def test_redirect_targets_must_be_same_origin():
    with pytest.raises(VirelCompileError, match="same-origin"):
        ui.redirect("https://evil.example/phish")
    with pytest.raises(VirelCompileError, match="same-origin"):
        ui.redirect("//evil.example")


def test_static_build_reports_guarded_routes():
    def guard(request):
        return None

    @ui.page("/members", guard=guard)
    def members():
        return ui.Page(ui.Text("m"))

    with pytest.raises(VirelCompileError) as excinfo:
        build_static()
    assert "/members" in str(excinfo.value)
    assert "guard" in str(excinfo.value)


# -- locale-aware formatting ------------------------------------------------------

def test_static_number_formatting_by_locale():
    with TraceContext() as ctx:
        assert ui.format_number(1234567.891, digits=2) == "1,234,567.89"
        ctx.locale = "pt"
        assert ui.format_number(1234567.891, digits=2) == "1.234.567,89"
        ctx.locale = "de"
        assert ui.format_number(-1234.5, digits=1) == "-1.234,5"


def test_currency_and_percent():
    with TraceContext() as ctx:
        assert ui.format_currency(1234.5) == "$1,234.50"
        ctx.locale = "pt"
        assert ui.format_currency(1234.5, currency="BRL") == "1.234,50\u00a0R$"
        ctx.locale = "de"
        assert ui.format_currency(9.9, currency="EUR") == "9,90\u00a0€"
        assert ui.format_percent(0.425, digits=1) == "42,5\u00a0%"
        ctx.locale = "en"
        assert ui.format_percent(0.425, digits=1) == "42.5%"


def test_date_formatting_by_locale():
    day = datetime.date(2026, 7, 10)
    with TraceContext() as ctx:
        assert ui.format_date(day, style="short") == "7/10/2026"
        assert ui.format_date(day) == "Jul 10, 2026"
        assert ui.format_date(day, style="long") == "July 10, 2026"
        ctx.locale = "pt"
        assert ui.format_date(day, style="short") == "10/07/2026"
        assert ui.format_date(day) == "10 de jul. de 2026"
        ctx.locale = "de"
        assert ui.format_date(day, style="short") == "10.07.2026"
        assert ui.format_date("2026-07-10", style="long") == "10. Juli 2026"


def test_reactive_values_format_with_intl_in_the_browser():
    ui.messages("pt", {"noop": "x"})

    @ui.page("/")
    def page():
        total = ui.state(1234.5)
        when = ui.state("2026-07-10")
        return ui.Page(
            ui.Text(ui.format_currency(total, currency="BRL")),
            ui.Text(ui.format_date(when)),
        )

    result = compile_page(active_registry().pages["/"], locale="pt")
    assert 'new Intl.NumberFormat("pt", { style: "currency", currency: "BRL"' in result.js
    assert 'new Intl.DateTimeFormat("pt", { dateStyle: "medium" })' in result.js
    # Server-rendered initial values use the Python rules.
    assert "1.234,50\u00a0R$" in result.html
    assert "10 de jul. de 2026" in result.html


def test_unknown_locale_falls_back_to_english_rules():
    with TraceContext() as ctx:
        ctx.locale = "sw"
        assert ui.format_number(1234.5, digits=1) == "1,234.5"
