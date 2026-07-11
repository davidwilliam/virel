"""Request context and the application chrome components."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


# -- request context ---------------------------------------------------------

def test_guard_provides_context_to_the_page():
    viewer = ui.context("viewer")

    def load(request: ui.Request):
        viewer.provide({"name": request.query.get("as", "Ada")})

    @ui.page("/me", guard=load)
    def me():
        user = viewer.get()
        return ui.Page(ui.Text(f"Hello {user['name']}"))

    app = create_asgi_app(dev=True)
    assert "Hello Ada" in asgi_request(app, "GET", "/me").text
    # Per-request rendering: another request sees its own value, never a
    # cached page from the previous one.
    assert "Hello Grace" in asgi_request(app, "GET", "/me",
                                         query="as=Grace").text
    assert "Hello Ada" in asgi_request(app, "GET", "/me").text


def test_context_default_keeps_page_compile_safe():
    role = ui.context("role", default="guest")

    @ui.page("/")
    def page():
        return ui.Page(ui.Text(f"role: {role.get()}"))

    result = compile_page(active_registry().pages["/"])
    assert "role: guest" in result.html
    assert not result.needs_request_render


def test_missing_context_names_the_fix():
    secret = ui.context("secret_value")

    @ui.page("/")
    def page():
        return ui.Page(ui.Text(secret.get()))

    with pytest.raises(VirelCompileError, match="provide"):
        compile_page(active_registry().pages["/"])


def test_provide_outside_request_is_an_error():
    thing = ui.context("thing")
    with pytest.raises(VirelCompileError, match="request"):
        thing.provide(1)


def test_render_accepts_context_values():
    account = ui.context("account")

    def page():
        user = account.get()
        return ui.Page(ui.Text(f"plan: {user['plan']}"))

    view = ui.test.render(page, context={"account": {"plan": "pro"}})
    assert "plan: pro" in view.query_text()


# -- menus --------------------------------------------------------------------

def _menu_page():
    def page():
        note = ui.state("")
        return ui.Page(ui.Menu(
            trigger=ui.Button("Account"),
            items=[
                ui.MenuItem("Profile", to="/profile", icon="user"),
                ui.MenuDivider(),
                ui.MenuItem("Sign out",
                            on_click=lambda: note.set("signed out"),
                            intent="danger"),
            ],
        ), ui.Text(note))
    return page


def test_menu_markup_and_runtime_binding():
    ui.page("/")(_menu_page())
    result = compile_page(active_registry().pages["/"])
    assert "$.menu(" in result.js
    assert 'role="menu"' in result.html
    assert 'role="menuitem"' in result.html
    assert 'role="separator"' in result.html
    assert 'href="/profile"' in result.html


def test_menu_action_items_work_in_tests():
    view = ui.test.render(_menu_page())
    view.get_by_role("menuitem", name="Sign out").click()
    assert "signed out" in view.query_text()


def test_menu_item_requires_exactly_one_behavior():
    with pytest.raises(VirelCompileError, match="exactly one"):
        ui.MenuItem("Both", to="/x", on_click=lambda: None)
    with pytest.raises(VirelCompileError, match="exactly one"):
        ui.MenuItem("Neither")


# -- shell, footer, hero -------------------------------------------------------

def test_appshell_with_sidebar_and_footer():
    def page():
        return ui.Page(ui.AppShell(
            navigation=ui.Nav(ui.Link("Home", to="/")),
            content=ui.Text("body"),
            sidebar=ui.Nav(ui.Link("Profile", to="/settings"),
                           label="Settings"),
            footer=ui.Footer(ui.Text("Built with Virel")),
        ))

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    assert '<aside class="v-sidebar">' in result.html
    assert '<footer class="v-footer">' in result.html
    assert "v-sidebar-toggle" in result.html
    # The drawer toggle drives a bound attribute on the shell.
    assert 'data-sidebar-open="false"' in result.html
    assert "$.bindAttr(" in result.js


def test_appshell_without_sidebar_has_no_toggle():
    def page():
        return ui.Page(ui.AppShell(
            navigation=ui.Nav(ui.Link("Home", to="/")),
            content=ui.Text("body"),
        ))

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    assert "v-sidebar-toggle" not in result.html
    assert "data-sidebar-open" not in result.html


def test_hero_structure():
    hero = ui.Hero(
        eyebrow=ui.Badge("Preview"),
        title="Ship interfaces in Python",
        subtitle="One language, end to end.",
        actions=[ui.LinkButton("Start", to="/docs", intent="primary")],
        media=ui.Code("x = 1", block=True, language="python"),
    )
    from virel.nodes import Emitter
    html = Emitter({}).emit(hero)
    assert 'class="v-hero v-hero-center"' in html
    assert '<h1 class="v-hero-title">Ship interfaces in Python</h1>' in html
    assert "v-hero-subtitle" in html
    assert "v-hero-actions" in html
    assert "v-hero-media" in html
    with pytest.raises(VirelCompileError, match="align"):
        ui.Hero(title="x", align="left")
