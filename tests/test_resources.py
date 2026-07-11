"""Resources and list rendering: fetch states, parameters, refresh,
server rendering, and ui.Each templates."""

import pytest

from virel import ui
from virel.compiler import build_static, compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _list_action(payload=None):
    data = payload if payload is not None else [
        {"name": "atlas", "score": 0.9},
        {"name": "baseline", "score": 0.7},
    ]

    @ui.server
    def list_items(query: str = "") -> list[dict]:
        needle = query.lower()
        return [item for item in data if needle in item["name"]]

    return list_items


def _runs_page(action, server_render=False):
    def page():
        query = ui.state("")
        items = ui.resource(action, params={"query": query},
                            server_render=server_render)
        return ui.Page(
            ui.TextField(query, label="Filter"),
            ui.Button("Refresh", on_click=lambda: items.refresh()),
            ui.Suspense(
                items,
                content=ui.Each(items.value,
                                render=lambda item: ui.Text(
                                    f"{item.name}: {item.score}")),
                fallback=ui.Skeleton(),
            ),
        )
    return page


def test_resource_emits_runtime_binding_and_states():
    action = _list_action()
    ui.page("/")(_runs_page(action))
    result = compile_page(active_registry().pages["/"])
    assert '$.resource("r2"' in result.js
    assert 'action: "list_items"' in result.js
    assert "params: () => ({" in result.js
    assert "$.bindList(" in result.js
    assert "$.esc(" in result.js
    assert '$.refreshResource("r2");' in result.js
    # Client fetch on load: loading starts true, no data in the HTML.
    assert "$.signal(true)" in result.js
    assert "atlas" not in result.html


def test_server_rendered_resource_embeds_data():
    action = _list_action()
    ui.page("/")(_runs_page(action, server_render=True))
    result = compile_page(active_registry().pages["/"])
    # Data fetched during render appears in the initial HTML.
    assert "atlas: 0.9" in result.html
    assert "baseline: 0.7" in result.html
    # The browser skips the first fetch.
    assert "initial: true" in result.js
    assert result.render_mode == "server"
    assert result.needs_request_render


def test_static_build_reports_resource_dependency():
    action = _list_action()
    ui.page("/data")(_runs_page(action))

    @ui.page("/plain")
    def plain():
        return ui.Page(ui.Text("static"))

    with pytest.raises(VirelCompileError) as excinfo:
        build_static()
    assert "/data" in str(excinfo.value)
    assert "list_items" in str(excinfo.value)


def test_view_fetches_resources_eagerly():
    action = _list_action()
    view = ui.test.render(_runs_page(action))
    assert "atlas: 0.9" in view.query_text()
    assert "baseline: 0.7" in view.query_text()


def test_loading_state_without_eager_fetch():
    action = _list_action()
    view = ui.test.render(_runs_page(action), fetch_resources=False)
    assert "atlas" not in view.query_text()
    skeleton = [e for e in view._walk() if "v-skeleton" in str(e.node.attrs.get("class", ""))]
    assert skeleton and skeleton[0].is_visible()


def test_refresh_reruns_action_with_current_params():
    action = _list_action()
    view = ui.test.render(_runs_page(action))
    view.get_by_label("Filter").fill("base")
    view.get_by_role("button", name="Refresh").click()
    text = view.query_text()
    assert "baseline: 0.7" in text
    assert "atlas" not in text


def test_refresh_supported_in_ast_handlers():
    action = _list_action()

    def page():
        items = ui.resource(action)

        def reload():
            items.refresh()

        return ui.Page(
            ui.Button("Reload", on_click=reload),
            ui.Each(items.value, render=lambda item: ui.Text(item.name)),
        )

    view = ui.test.render(page)
    view.get_by_role("button", name="Reload").click()
    assert "atlas" in view.query_text()


def test_each_escapes_untrusted_data():
    action = _list_action([{"name": "<script>alert(1)</script>", "score": 1}])

    def page():
        items = ui.resource(action, server_render=True)
        return ui.Page(ui.Each(items.value,
                               render=lambda item: ui.Text(item.name)))

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    assert "<script>alert(1)" not in result.html
    assert "&lt;script&gt;" in result.html


def test_each_rejects_event_handlers_in_templates():
    action = _list_action()

    def page():
        items = ui.resource(action)
        selected = ui.state("")
        return ui.Page(ui.Each(
            items.value,
            render=lambda item: ui.Button(
                "Select", on_click=lambda: selected.set("x")),
        ))

    with pytest.raises(VirelCompileError, match="event handlers"):
        ui.test.render(page)


def test_resource_error_surfaces_in_suspense():
    @ui.server
    def broken() -> list:
        raise RuntimeError("database offline")

    def page():
        items = ui.resource(broken)
        return ui.Page(ui.Suspense(
            items,
            content=ui.Each(items.value, render=lambda item: ui.Text(item.name)),
        ))

    view = ui.test.render(page)
    assert "database offline" in view.query_text()


def test_resource_requires_server_action():
    def page():
        items = ui.resource(lambda: [])
        return ui.Page(ui.Text("x"))

    with pytest.raises(VirelCompileError, match="@ui.server"):
        ui.test.render(page)
