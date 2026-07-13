"""Large-data extension points (SPEC 17.3)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def test_worker_runs_off_thread_and_returns_into_state():
    @ui.worker
    def weighted(v: list) -> int:
        return v[0] * 3 + v[1] * 5 + v[2] * 7

    @ui.page("/worker")
    def worker_page():
        data = ui.state([1, 2, 3])
        out = ui.state(0)
        return ui.Page(
            ui.Button("Compute",
                      on_click=lambda: weighted.run(data, into=out)),
            ui.Text(f"Result: {out}"),
        )

    compiled = compile_page(active_registry().pages["/worker"])
    # The worker source ships as a string for the Web Worker; the call
    # dispatches to it.
    assert "registerWorkers" in compiled.js
    assert 'function weighted' in compiled.js
    assert '$.runWorker("weighted"' in compiled.js

    # In tests the worker runs synchronously as ordinary Python.
    view = ui.test.render(worker_page)
    view.get_by_role("button", name="Compute").click()
    assert "Result: 34" in view.query_text()   # 3 + 10 + 21


def test_worker_callable_as_plain_python():
    @ui.worker
    def double(x: int) -> int:
        return x * 2

    assert double(21) == 42   # server/test side


def test_worker_run_requires_into_state():
    @ui.worker
    def w(x: int) -> int:
        return x

    @ui.page("/bad-worker")
    def bad():
        n = ui.state(0)

        def go():
            w.run(n)   # missing into=

        return ui.Page(ui.Button("go", on_click=go))

    with pytest.raises(VirelCompileError, match="into="):
        compile_page(active_registry().pages["/bad-worker"])


def test_canvas_extension_point():
    @ui.page("/canvas")
    def canvas_page():
        return ui.Page(ui.Canvas(
            draw="ctx.clearRect(0, 0, frame.width, frame.height);",
            label="Spectrum", context="webgl", animate=True))

    compiled = compile_page(active_registry().pages["/canvas"])
    assert 'data-context="webgl"' in compiled.html
    assert 'role="img"' in compiled.html
    assert 'aria-label="Spectrum"' in compiled.html
    assert "$.canvas(" in compiled.js
    assert "(ctx, frame) => {" in compiled.js
    assert "clearRect" in compiled.js
    assert "{animate: true}" in compiled.js


def test_canvas_validates_context_draw_and_policy():
    with pytest.raises(VirelCompileError, match="context must be"):
        ui.Canvas(draw="x;", label="x", context="3d")
    with pytest.raises(VirelCompileError, match="function body string"):
        ui.Canvas(draw="", label="x")
    with pytest.raises(VirelCompileError, match="markup-closing"):
        ui.Canvas(draw="ctx.foo(); </script>", label="x")
    ui.use_policy(raw_javascript=False)
    try:
        with pytest.raises(VirelCompileError, match="policy"):
            ui.Canvas(draw="ctx.foo();", label="x")
    finally:
        ui.use_policy(raw_javascript=True)


def test_virtualized_table_covers_large_data():
    # SPEC 17.3 virtualized tables: the data grid windows large data.
    rows = [{"id": i, "v": i} for i in range(1000)]

    @ui.page("/big-grid")
    def big_grid():
        return ui.Page(ui.DataGrid(rows, key="id", virtual=True))

    html = compile_page(active_registry().pages["/big-grid"]).html
    # Rows travel as data, not 1000 <tr> elements.
    assert html.count("<tr") == 1   # header only
    assert 'type="application/json"' in html
