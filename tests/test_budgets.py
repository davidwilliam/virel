"""Performance budgets (SPEC 17.2)."""

import re

import pytest

from virel import ui
from virel.budgets import (component_bundle_cost, measure,
                           runtime_gzip_bytes)
from virel.registry import fresh_registry


def test_runtime_meets_the_core_budget():
    # SPEC 17.2: core browser runtime at or below 35 KB gzip.
    assert runtime_gzip_bytes() <= 35_000


def test_static_page_ships_zero_runtime_javascript():
    fresh_registry()

    @ui.page("/")
    def home():
        return ui.Page(ui.Heading("Hi", level=1), ui.Text("static"))

    from virel.compiler import compile_page
    from virel.registry import active_registry
    compiled = compile_page(active_registry().pages["/"])
    assert compiled.js is None
    assert "runtime.js" not in compiled.html
    fresh_registry()


def test_measure_reports_and_enforces_budgets():
    fresh_registry()

    @ui.page("/app")
    def app():
        count = ui.state(0)
        return ui.Page(
            ui.Text(f"Count: {count}"),
            ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)))

    report = measure()
    assert report["ok"] is True
    assert report["runtime_gzip"] <= report["budgets"]["runtime_gzip"]
    assert report["app_gzip"] <= report["budgets"]["app_gzip"]
    names = {c["name"] for c in report["checks"]}
    assert "runtime_gzip" in names and "app_gzip" in names
    fresh_registry()


def test_a_tight_budget_fails():
    fresh_registry()

    @ui.page("/big")
    def big():
        n = ui.state(0)
        return ui.Page(ui.Text(f"{n}"),
                       ui.Button("x", on_click=lambda: n.set(1)))

    report = measure({"runtime_gzip": 100})   # impossibly tight
    assert report["ok"] is False
    assert any(c["name"] == "runtime_gzip" and not c["ok"]
               for c in report["checks"])
    fresh_registry()


def test_components_publish_bundle_cost():
    cost = component_bundle_cost()
    # First-party interactive components report a runtime cost.
    assert cost["DataGrid"] > 0
    assert cost["Menu"] > 0
    # Every value is a byte count.
    assert all(isinstance(v, int) for v in cost.values())


def test_fine_grained_update_touches_one_binding():
    # SPEC 17.2: a fine-grained update must not rerender unrelated
    # subtrees. Each reactive text is its own bindText against one
    # element; updating one signal recomputes only its binding.
    fresh_registry()

    @ui.page("/fine")
    def fine():
        a = ui.state(0)
        b = ui.state(0)
        return ui.Page(
            ui.Text(f"A: {a}"),
            ui.Text(f"B: {b}"),
            ui.Button("bump-a", on_click=lambda: a.update(lambda v: v + 1)),
        )

    from virel.compiler import compile_page
    from virel.registry import active_registry
    js = compile_page(active_registry().pages["/fine"]).js
    # Each text is an independent bindText reading exactly its own state.
    binds = re.findall(r'\$\.bindText\("(\w+)", \(\) => `[^`]*\$\{'
                       r'S\.(\w+)\.get\(\)', js)
    reads = {state for _id, state in binds}
    assert reads == {"s1", "s2"}   # two independent bindings
    # No binding reads both signals (no shared/coarse subtree render).
    for _id, state in binds:
        assert js.count(f'bindText("{_id}"') == 1
    fresh_registry()
