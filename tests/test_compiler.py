"""Page compilation: IR, server-rendered initial HTML, emitted JS,
zero-JS static pages, and the static-build server-dependency report."""

import pytest

from virel import ui
from virel.compiler import build_static, compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _page(path="/", render="auto"):
    return active_registry().pages[path]


def test_counter_page_compiles_end_to_end():
    @ui.page("/")
    def counter():
        count = ui.state(0)
        return ui.Page(
            ui.Stack(
                ui.Text(f"Count: {count}"),
                ui.Button("Increment",
                          on_click=lambda: count.update(lambda c: c + 1),
                          intent="primary"),
            ),
            title="Counter",
        )

    result = compile_page(_page("/"))

    # Server-rendered initial value appears in the HTML.
    assert "Count: 0" in result.html
    # The page JS declares the signal and binds text + click.
    assert "$.signal(0)" in result.js
    assert "S.s1.set((S.s1.get() + 1));" in result.js
    assert "$.bindText(" in result.js
    # IR is versioned and carries the state.
    assert result.ir["version"] == "0.1"
    assert result.ir["states"] == [{"kind": "state", "name": "s1", "initial": 0}]
    assert result.render_mode == "client"


def test_static_page_emits_zero_javascript():
    @ui.page("/about", render="static")
    def about():
        return ui.Page(ui.Heading("About"), ui.Text("Plain content."),
                       title="About")

    result = compile_page(_page("/about"))
    assert result.js is None
    # No framework modules; the only script allowed is the inline theme
    # bootstrap that applies a stored color-scheme preference pre-paint.
    assert "/_virel/runtime.js" not in result.html
    assert "/_virel/page/" not in result.html
    assert result.html.count("<script") == 1
    assert "virel-theme" in result.html
    assert result.render_mode == "static"


def test_compilation_is_deterministic():
    @ui.page("/")
    def page():
        query = ui.state("")
        return ui.Page(ui.TextField(query, label="Q"),
                       ui.Text(f"You typed: {query}"))

    first = compile_page(_page("/"))
    second = compile_page(_page("/"))
    assert first.html == second.html
    assert first.js == second.js


def test_when_renders_both_branches_with_initial_visibility():
    @ui.page("/")
    def page():
        count = ui.state(0)
        return ui.Page(
            ui.Button("go", on_click=lambda: count.set(1)),
            ui.When(count > 0, then=ui.Text("visible"),
                    otherwise=ui.Text("hidden branch")),
        )

    result = compile_page(_page("/"))
    assert "visible" in result.html
    assert "hidden branch" in result.html
    # then-branch starts hidden because count == 0 initially
    assert 'style="display:none">' in result.html
    assert "$.bindShow(" in result.js


def test_declared_static_route_with_server_action_fails_precisely():
    @ui.server
    def save(value: str) -> str:
        return value

    @ui.page("/broken", render="static")
    def broken():
        text = ui.state("")
        return ui.Page(
            ui.Button("Save", on_click=lambda: save.call({"value": text})),
        )

    with pytest.raises(VirelCompileError) as excinfo:
        compile_page(_page("/broken"))
    message = str(excinfo.value)
    assert "/broken" in message
    assert "save" in message
    assert "render='static'" in message


def test_static_build_reports_all_server_dependencies():
    @ui.server
    def act() -> str:
        return "x"

    @ui.page("/fine")
    def fine():
        return ui.Page(ui.Text("static"))

    @ui.page("/needs-server")
    def needs_server():
        out = ui.state("")
        return ui.Page(ui.Button("Go", on_click=lambda: act.call(into=out)),
                       ui.Text(out))

    @ui.page("/items/{item_id}")
    def item(item_id: str):
        return ui.Page(ui.Text(f"Item {item_id}"))

    with pytest.raises(VirelCompileError) as excinfo:
        build_static()
    message = str(excinfo.value)
    assert "/needs-server" in message
    assert "/items/{item_id}" in message
    assert "/fine" not in message


def test_icon_only_button_requires_accessible_label():
    with pytest.raises(VirelCompileError, match="aria_label"):
        @ui.page("/")
        def page():
            return ui.Page(ui.Button(ui.Image("/x.svg", alt="")))

        compile_page(_page("/"))


def test_html_is_escaped_by_default():
    @ui.page("/")
    def page():
        return ui.Page(ui.Text("<script>alert(1)</script>"))

    result = compile_page(_page("/"))
    assert "<script>alert(1)" not in result.html
    assert "&lt;script&gt;" in result.html


def test_dynamic_route_renders_params_server_side():
    @ui.page("/projects/{project_id}")
    def project(project_id: str, tab: str = "overview"):
        return ui.Page(ui.Heading(f"Project {project_id} — {tab}"))

    page = _page("/projects/{project_id}")
    result = compile_page(page, params={"project_id": "atlas"})
    assert "Project atlas — overview" in result.html
    assert result.render_mode == "server"


def test_component_names_survive_into_ir():
    @ui.component
    def user_badge(name: str):
        return ui.Row(ui.Text(name))

    @ui.page("/")
    def page():
        return ui.Page(user_badge("Ada"))

    result = compile_page(_page("/"))
    tree = str(result.ir["tree"])
    assert "user_badge" in tree
