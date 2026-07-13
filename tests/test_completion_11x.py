"""The final SPEC 11 pieces: media elements, listbox, filter chips,
onboarding tour, and charts."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.nodes import template_html
from virel.registry import active_registry


def test_article_and_media_elements():
    article = ui.Article(ui.Heading("Post", level=2), ui.Text("Body"))
    assert article.tag == "article"

    video = ui.Video("/public/clip.mp4", label="Release demo",
                     poster="/public/poster.png",
                     captions="/public/clip.vtt")
    html = template_html([video], {})
    assert 'aria-label="Release demo"' in html
    assert 'kind="captions"' in html
    assert "controls" in html and "autoplay" not in html

    audio = ui.Audio("/public/talk.mp3", label="Episode 4")
    assert audio.attrs["aria-label"] == "Episode 4"

    with pytest.raises(VirelCompileError, match="blocked URL scheme"):
        ui.Video("javascript:x", label="Bad")


def test_listbox_selection_reaches_state():
    @ui.page("/listbox")
    def listbox_page():
        picked = ui.state("qa-hard-v2")
        return ui.Page(
            ui.Listbox(picked, label="Dataset",
                       options=["qa-hard-v2", "summarize-v1", "extract-v3"]),
            ui.Text(f"Dataset: {picked}"),
        )

    compiled = compile_page(active_registry().pages["/listbox"])
    assert 'role="listbox"' in compiled.html
    assert 'aria-selected="true"' in compiled.html  # initial from state
    assert "$.listbox(" in compiled.js
    assert "S.s1.set(ev.detail.value);" in compiled.js

    view = ui.test.render(listbox_page)
    view.get_by_role("listbox").emit("virel-change",
                                     detail={"value": "extract-v3"})
    assert "Dataset: extract-v3" in view.query_text()


def test_listbox_multiple_uses_values():
    @ui.page("/listbox-multi")
    def multi():
        picked = ui.state([])
        return ui.Page(ui.Listbox(picked, label="Datasets", multiple=True,
                                  options=["a", "b"]))

    compiled = compile_page(active_registry().pages["/listbox-multi"])
    assert 'aria-multiselectable="true"' in compiled.html
    assert "ev.detail.values" in compiled.js


def test_filter_chips_write_selected_values():
    @ui.page("/chips")
    def chips_page():
        active = ui.state(["passed"])
        return ui.Page(
            ui.FilterChips(active, options=["passed", "failed", "skipped"]),
            ui.Text(f"Showing: {ui.length(active)}"),
        )

    compiled = compile_page(active_registry().pages["/chips"])
    assert 'aria-pressed="true"' in compiled.html   # initial from state
    assert 'aria-pressed="false"' in compiled.html
    assert "$.chips(" in compiled.js

    view = ui.test.render(chips_page)
    view.get_by_role("group").emit(
        "virel-change", detail={"values": ["passed", "failed"]})
    assert "Showing: 2" in view.query_text()


def test_tour_compiles_steps_and_close_writes_state():
    @ui.page("/tour")
    def tour_page():
        touring = ui.state(False)
        return ui.Page(
            ui.Button("Start tour", on_click=lambda: touring.set(True)),
            ui.Tour(steps=[
                ui.TourStep(".v-datagrid", "The grid", "Sort and filter."),
                ui.TourStep(".v-tree", "The tree", "Arrow keys move."),
            ], open=touring),
        )

    compiled = compile_page(active_registry().pages["/tour"])
    assert "$.tour_overlay(" in compiled.js
    assert "The grid" in compiled.html
    assert '"virel-close"' in compiled.js
    assert "S.s1.set(false);" in compiled.js

    with pytest.raises(VirelCompileError, match="CSS selector"):
        ui.TourStep("<script>", "x", "y")
    with pytest.raises(VirelCompileError, match="at least one"):
        @ui.page("/tour-empty")
        def empty():
            flag = ui.state(False)
            return ui.Page(ui.Tour(steps=[], open=flag))
        compile_page(active_registry().pages["/tour-empty"])


def test_charts_compile_to_accessible_svg():
    line = ui.Chart("line", [
        ui.Series("Pass rate", points=[71, 74, 82, 87]),
        ui.Series("Baseline", points=[64, 66, 65, 70]),
    ], labels=["Apr", "May", "Jun", "Jul"])
    html = template_html([line], {})
    assert 'role="img"' in html and "Line chart." in html
    assert "<title>Pass rate: 87</title>" in html
    # Series colors come from a fixed, theme-independent palette.
    assert "#6366f1" in html and "#10b981" in html
    assert "var(--v-accent)" not in html
    assert "v-chart-legend" in html

    bars = ui.Chart("bar", [ui.Series("Runs", points=[12, 30, 22])],
                    labels=["A", "B", "C"], legend=False)
    bars_html = template_html([bars], {})
    assert "v-chart-bar" in bars_html and "v-chart-legend" not in bars_html

    donut = ui.Chart("donut", [ui.Series("Passed", value=42),
                               ui.Series("Failed", value=3)], height=170)
    donut_html = template_html([donut], {})
    assert "(93%)" in donut_html and ">45<" in donut_html
    # The donut is capped at its height so it does not balloon to the
    # full column width.
    assert "max-width:170px" in donut_html


def test_chart_values_are_validated():
    with pytest.raises(VirelCompileError, match="numbers"):
        ui.Series("x", points=[1, "<svg>"])
    with pytest.raises(VirelCompileError, match="exactly one"):
        ui.Series("x", points=[1], value=2)
    with pytest.raises(VirelCompileError, match="kind"):
        ui.Chart("radar", [ui.Series("x", points=[1])])
    with pytest.raises(VirelCompileError, match="sum above zero"):
        ui.Chart("donut", [ui.Series("x", value=0)])


def test_chart_labels_are_escaped():
    chart = ui.Chart("line", [
        ui.Series('<img src=x onerror=alert(1)>', points=[1, 2])])
    html = template_html([chart], {})
    assert "<img" not in html
    assert "&lt;img" in html
