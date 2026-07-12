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


# ----- SPEC 12.2: the professional tier -------------------------------------

_BIG = [{"model": f"m{i:03d}", "dataset": f"ds{i % 3}", "score": i / 100}
        for i in range(200)]


def test_grouping_and_aggregation():
    @ui.page("/grid-groups")
    def grid_groups():
        return ui.Page(ui.DataGrid(
            _RUNS, columns=_columns(), key="model",
            group_by="started", aggregate={"score": "mean"}))

    html = compile_page(active_registry().pages["/grid-groups"]).html
    assert "v-grid-group" in html
    assert 'aria-expanded="true"' in html
    assert "Score mean" in html
    assert 'data-group-of="2026-07-10"' in html


def test_footer_totals_without_grouping():
    @ui.page("/grid-total")
    def grid_total():
        return ui.Page(ui.DataGrid(
            _RUNS, columns=_columns(), aggregate={"score": "max"}))

    html = compile_page(active_registry().pages["/grid-total"]).html
    assert "v-grid-total" in html
    assert "0.93" in html
    with pytest.raises(VirelCompileError, match="aggregate"):
        ui.DataGrid(_RUNS, columns=_columns(),
                    aggregate={"score": "median"})


def test_server_mode_renders_links_not_buttons():
    query = ui.grid_query(sort="score", dir="asc", q="atlas", page=1)
    page_rows, pages = ui.apply_grid_query(_RUNS, query, page_size=1)
    assert pages == 2
    assert page_rows[0]["model"] == "atlas-small"  # 0.87 < 0.93

    @ui.page("/grid-server")
    def grid_server():
        return ui.Page(ui.DataGrid(page_rows, columns=_columns(),
                                   server=query, pages=pages,
                                   filterable=True))

    html = compile_page(active_registry().pages["/grid-server"]).html
    assert 'href="?sort=score&amp;dir=desc&amp;q=atlas"' in html
    assert 'aria-sort="ascending"' in html
    assert 'name="q"' in html and 'method="get"' in html
    assert 'href="?page=2&amp;sort=score&amp;dir=asc&amp;q=atlas"' in html


def test_apply_grid_query_filters_sorts_and_pages():
    query = ui.grid_query(sort="score", dir="desc", page=2)
    rows, pages = ui.apply_grid_query(_BIG, query, page_size=50)
    assert pages == 4
    assert rows[0]["score"] == 1.49  # second page of descending scores
    filtered, _ = ui.apply_grid_query(_BIG, ui.grid_query(q="ds1"))
    assert all(row["dataset"] == "ds1" for row in filtered)
    assert ui.grid_query(dir="sideways", page="x") == ui.grid_query()


def test_editable_cells_and_edit_handler():
    @ui.page("/grid-edit")
    def grid_edit():
        edited = ui.state("")
        return ui.Page(ui.DataGrid(
            _RUNS,
            columns=[Column("model", "Model"),
                     Column("score", "Score", kind="number", editable=True)],
            key="model",
            on_edit=ui.set_from_event(edited, "detail.column")))

    from virel.datagrid import Column
    compiled = compile_page(active_registry().pages["/grid-edit"])
    assert "v-grid-editable" in compiled.html
    assert '"virel-edit"' in compiled.js

    with pytest.raises(VirelCompileError, match="require key="):
        ui.DataGrid(_RUNS, columns=[
            Column("score", "Score", editable=True)])


def test_virtual_mode_embeds_data_instead_of_rows():
    @ui.page("/grid-virtual")
    def grid_virtual():
        return ui.Page(ui.DataGrid(_BIG, key="model", virtual=True,
                                   filterable=True, export=True))

    html = compile_page(active_registry().pages["/grid-virtual"]).html
    assert 'type="application/json"' in html
    assert html.count("<tr") == 1  # header only; rows are data
    assert '"virtual": true' in html.replace("&quot;", '"')
    assert "v-grid-export" in html


def test_virtual_data_is_script_context_safe():
    rows = [{"model": "</script><script>alert(1)</script>", "score": 1}]

    @ui.page("/grid-xss")
    def grid_xss():
        return ui.Page(ui.DataGrid(rows, key="model", virtual=True))

    html = compile_page(active_registry().pages["/grid-xss"]).html
    assert "</script><script>alert" not in html
    assert "\\u003c/script" in html


def test_stream_requires_virtual_and_streaming_action():
    @ui.server(stream=True)
    async def live_runs():
        yield {"model": "x", "score": 1.0}

    @ui.page("/grid-stream")
    def grid_stream():
        return ui.Page(ui.DataGrid(_RUNS, key="model", virtual=True,
                                   stream=live_runs))

    compiled = compile_page(active_registry().pages["/grid-stream"])
    assert '"stream": "live_runs"' in compiled.html.replace("&quot;", '"')

    with pytest.raises(VirelCompileError, match="virtual=True"):
        ui.DataGrid(_RUNS, key="model", stream=live_runs)


def test_column_pinning_and_resizing_flags():
    from virel.datagrid import Column
    pinned = Column("model", "Model", pin="start")
    assert pinned.pin == "start"
    with pytest.raises(VirelCompileError, match="pin"):
        Column("model", "Model", pin="left")

    @ui.page("/grid-pin")
    def grid_pin():
        return ui.Page(ui.DataGrid(
            _RUNS, columns=[pinned, Column("score", "Score", kind="number")],
            resizable=True))

    html = compile_page(active_registry().pages["/grid-pin"]).html
    assert "v-grid-pin-start" in html
    assert '"resizable": true' in html.replace("&quot;", '"')
