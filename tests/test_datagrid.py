"""The data grid (SPEC 11.1 advanced components)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry

_RUNS = [
    {"model": "atlas-large", "score": 0.93, "started": "2026-07-10"},
    {"model": "baseline", "score": 0.71, "started": "2026-07-08"},
    {"model": "atlas-small", "score": 0.87, "started": "2026-07-11"},
]

_COLUMNS_SRC = """[
    ui.Column("model", "Model"),
    ui.Column("score", "Score", kind="number"),
    ui.Column("started", "Started", kind="date"),
]"""


def _columns():
    return [ui.Column("model", "Model"),
            ui.Column("score", "Score", kind="number"),
            ui.Column("started", "Started", kind="date")]


def test_grid_renders_sortable_headers_and_typed_cells():
    @ui.page("/grid")
    def grid_page():
        return ui.Page(ui.DataGrid(_RUNS, columns=_columns(),
                                   caption="Runs"))

    compiled = compile_page(active_registry().pages["/grid"])
    html = compiled.html
    assert 'aria-sort="none"' in html
    assert 'data-kind="number"' in html
    assert 'data-value="0.9300000000"' in html      # machine-sortable
    assert 'data-value="2026-07-10"' in html
    assert "v-grid-align-end" in html               # numbers right-align
    assert "$.datagrid(" in compiled.js


def test_grid_selection_wires_state():
    @ui.page("/grid-select")
    def grid_select():
        chosen = ui.state([])
        return ui.Page(
            ui.DataGrid(_RUNS, columns=_columns(), key="model",
                        selectable=True,
                        on_selection=ui.set_from_event(chosen,
                                                       "detail.keys")),
            ui.Text(f"Chosen: {ui.length(chosen)}"),
        )

    compiled = compile_page(active_registry().pages["/grid-select"])
    assert 'aria-label="Select all rows"' in compiled.html
    assert 'data-key="atlas-large"' in compiled.html
    assert '"virel-selection"' in compiled.js
    assert "S.s1.set(ev.detail.keys);" in compiled.js


def test_grid_pagination_and_filter_chrome():
    @ui.page("/grid-pages")
    def grid_pages():
        return ui.Page(ui.DataGrid(_RUNS, columns=_columns(),
                                   filterable=True, page_size=2))

    html = compile_page(active_registry().pages["/grid-pages"]).html
    assert 'aria-label="Filter rows"' in html
    assert "v-grid-prev" in html and "v-grid-next" in html


def test_grid_validation():
    with pytest.raises(VirelCompileError, match="ui.Column"):
        ui.DataGrid(_RUNS, columns=["model"])
    with pytest.raises(VirelCompileError, match="requires key="):
        ui.DataGrid(_RUNS, columns=_columns(), selectable=True)
    with pytest.raises(VirelCompileError, match="kind"):
        ui.Column("x", "X", kind="money")
    with pytest.raises(VirelCompileError, match="handler"):
        ui.DataGrid(_RUNS, columns=_columns(), key="model",
                    on_selection="not-a-handler")


def test_sortable_values_are_sanitized():
    from virel.datagrid import _sortable_value
    assert _sortable_value(0.93, "number") == "0.9300000000"
    assert _sortable_value("not a number", "number") == ""
    assert _sortable_value("2026-07-10", "date") == "2026-07-10"
    assert _sortable_value("<script>", "date") == ""
    assert _sortable_value("Ärger", "text") == "ärger"


def test_selection_handler_executes_in_python():
    captured = {}

    @ui.page("/grid-exec")
    def grid_exec():
        chosen = ui.state([])
        grid = ui.DataGrid(_RUNS, columns=_columns(), key="model",
                           selectable=True,
                           on_selection=ui.set_from_event(chosen,
                                                          "detail.keys"))
        captured["grid"] = grid
        return ui.Page(grid)

    view = ui.test.render(grid_exec)
    handler = captured["grid"].events["virel-selection"]
    view._run_handler(handler, ev={"detail": {"keys": ["baseline"]}})
    assert view.state("s1") == ["baseline"]
