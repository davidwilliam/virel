"""Hydration boundaries: server-rendered content with deferred bindings."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _island_page(load="visible"):
    @ui.page("/")
    def page():
        count = ui.state(0)
        eager = ui.state("")
        return ui.Page(
            ui.TextField(eager, label="Eager"),
            ui.Island(
                ui.Text(f"Count: {count}"),
                ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)),
                load=load,
            ),
        )
    return active_registry().pages["/"]


def test_island_defers_its_bindings():
    result = compile_page(_island_page())
    assert '$.island("' in result.js
    assert '"visible", () => {' in result.js
    # The island's bindings are inside the deferred closure; the eager
    # field binds at mount.
    island_body = result.js.split("$.island(")[1]
    assert "$.bindText(" in island_body
    assert "$.on(" in island_body
    mount_before_island = result.js.split("$.island(")[0]
    assert "$.bindProp(" in mount_before_island


def test_island_content_is_server_rendered():
    result = compile_page(_island_page())
    assert "Count: 0" in result.html
    assert 'class="v-island"' in result.html


def test_island_strategies_validated():
    with pytest.raises(VirelCompileError, match="not a strategy"):
        ui.Island(ui.Text("x"), load="eventually")


def test_component_tests_interact_through_islands():
    view = ui.test.render(lambda: ui.Page(
        _island_view_root()
    ))
    view.get_by_role("button", name="Add").click()
    assert "Count: 1" in view.query_text()


def _island_view_root():
    count = ui.state(0)
    return ui.Island(
        ui.Text(f"Count: {count}"),
        ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)),
        load="idle",
    )


def test_island_appears_in_ir():
    result = compile_page(_island_page(load="interaction"))
    tree = str(result.ir["tree"])
    assert "'kind': 'island'" in tree
    assert "'load': 'interaction'" in tree
