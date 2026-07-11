"""ui.effect and the state persistence and URL adapters."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def test_effect_emits_watch_binding():
    @ui.server
    def track(query: str) -> str:
        return query

    @ui.page("/")
    def page():
        query = ui.state("")
        log = ui.state("")
        ui.effect(lambda: track.call({"query": query}, into=log),
                  dependencies=[query])
        return ui.Page(ui.TextField(query, label="Q"), ui.Text(log))

    result = compile_page(active_registry().pages["/"])
    assert "$.watch([() => S.s1.get()], () => {" in result.js
    assert '$.action("track"' in result.js
    assert "}, false);" in result.js


def test_effect_run_on_mount_flag():
    @ui.page("/")
    def page():
        n = ui.state(0)
        seen = ui.state(0)
        ui.effect(lambda: seen.set(n + 0), dependencies=[n],
                  run_on_mount=True)
        return ui.Page(ui.Text(f"{seen}"),
                       ui.Button("x", on_click=lambda: n.set(1)))

    result = compile_page(active_registry().pages["/"])
    assert "}, true);" in result.js


def test_effect_requires_reactive_dependencies():
    def page():
        ui.effect(lambda: None, dependencies=[])
        return ui.Page(ui.Text("x"))

    with pytest.raises(VirelCompileError, match="dependencies"):
        ui.test.render(page)


def test_effects_fire_in_component_tests():
    calls = []

    @ui.server
    def track(query: str) -> str:
        calls.append(query)
        return f"tracked {query}"

    def page():
        query = ui.state("")
        log = ui.state("")
        ui.effect(lambda: track.call({"query": query}, into=log),
                  dependencies=[query])
        return ui.Page(ui.TextField(query, label="Q"), ui.Text(log))

    view = ui.test.render(page)
    view.get_by_label("Q").fill("atlas")
    assert calls == ["atlas"]
    assert "tracked atlas" in view.query_text()
    # Unrelated interactions do not refire the effect.
    view.get_by_label("Q").fill("atlas")
    assert calls == ["atlas"]


def test_effect_with_named_handler_control_flow():
    def page():
        count = ui.state(0)
        label = ui.state("")

        def classify():
            if count > 2:
                label.set("high")
            else:
                label.set("low")

        ui.effect(classify, dependencies=[count])
        return ui.Page(ui.Text(label),
                       ui.Button("Add",
                                 on_click=lambda: count.update(lambda c: c + 1)))

    view = ui.test.render(page)
    add = view.get_by_role("button", name="Add")
    add.click()
    assert "low" in view.query_text()
    add.click()
    add.click()
    assert "high" in view.query_text()


def test_state_persist_and_url_emit_adapters():
    @ui.page("/")
    def page():
        query = ui.state("", url="q")
        theme_choice = ui.state("system", persist="theme-choice")
        return ui.Page(ui.TextField(query, label="Q"),
                       ui.TextField(theme_choice, label="T"))

    result = compile_page(active_registry().pages["/"])
    assert '$.urlSync(S.s1, "q");' in result.js
    assert '$.persist(S.s2, "theme-choice");' in result.js
