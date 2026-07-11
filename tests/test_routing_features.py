"""Nested layouts, canonical URLs, typed query parameters, and error
pages (SPEC 8.10)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


def test_layouts_nest_by_prefix():
    @ui.layout("/")
    def site(content):
        return ui.Stack(ui.Text("site header"), content, ui.Text("site footer"))

    @ui.layout("/settings")
    def settings_frame(content):
        return ui.Row(ui.Text("settings nav"), content)

    @ui.page("/settings/profile")
    def profile():
        return ui.Page(ui.Heading("Profile"))

    @ui.page("/about")
    def about():
        return ui.Page(ui.Heading("About"))

    profile_html = compile_page(active_registry().pages["/settings/profile"]).html
    body = profile_html[profile_html.index("<body>"):]
    # Inner layout wraps the page; outer layout wraps both.
    assert body.index("site header") < body.index("settings nav")
    assert body.index("settings nav") < body.index("Profile")
    assert body.index("Profile") < body.index("site footer")

    about_html = compile_page(active_registry().pages["/about"]).html
    assert "site header" in about_html
    assert "settings nav" not in about_html


def test_prefix_matching_requires_a_segment_boundary():
    @ui.layout("/settings")
    def frame(content):
        return ui.Stack(ui.Text("frame"), content)

    @ui.page("/settingsarchive")
    def other():
        return ui.Page(ui.Text("unrelated"))

    html = compile_page(active_registry().pages["/settingsarchive"]).html
    assert "frame" not in html


def test_layouts_can_be_interactive():
    @ui.layout("/")
    def frame(content):
        open_state = ui.state(False)
        return ui.Stack(
            ui.Button("Toggle", on_click=lambda: open_state.set(True)),
            ui.When(open_state, then=ui.Text("panel open")),
            content,
        )

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("page body"))

    result = compile_page(active_registry().pages["/"])
    assert "page body" in result.html
    assert "$.bindShow(" in result.js


def test_canonical_url_in_head():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"), canonical="https://virel.dev/")

    result = compile_page(active_registry().pages["/"])
    assert '<link rel="canonical" href="https://virel.dev/">' in result.html
    with pytest.raises(VirelCompileError, match="blocked scheme"):
        ui.Page(ui.Text("x"), canonical="javascript:alert(1)")


def test_query_parameters_convert_to_annotated_types():
    @ui.page("/report")
    def report(page_number: int = 1, threshold: float = 0.5,
               verbose: bool = False):
        kind = "verbose" if verbose else "summary"
        return ui.Page(ui.Text(
            f"page {page_number} above {threshold} ({kind})"))

    app = create_asgi_app(dev=True)
    text = asgi_request(app, "GET", "/report",
                        query="page_number=3&threshold=0.75&verbose=true").text
    assert "page 3 above 0.75 (verbose)" in text
    # Invalid values fall back to the declared defaults.
    text = asgi_request(app, "GET", "/report", query="page_number=abc").text
    assert "page 1 above 0.5 (summary)" in text


def test_error_pages_are_styled_in_production():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=False)
    missing = asgi_request(app, "GET", "/nope")
    assert missing.status == 404
    assert "Page not found" in missing.text
    assert "<style>" in missing.text
