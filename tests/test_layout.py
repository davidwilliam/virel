"""Layout primitives added in the polish pass."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def test_grid_responsive_columns():
    grid = ui.Grid(ui.Text("a"), ui.Text("b"),
                   columns={"base": 1, "md": 3}, gap=4)
    style = grid.attrs["style"]
    assert "--v-cols: 1" in style
    assert "--v-cols-md: 3" in style
    assert "v-grid" in grid.attrs["class"]


def test_grid_plain_int_columns():
    grid = ui.Grid(ui.Text("a"), columns=2)
    assert "--v-cols: 2" in grid.attrs["style"]


def test_grid_rejects_unknown_breakpoints():
    with pytest.raises(VirelCompileError, match="base, md, and xl"):
        ui.Grid(ui.Text("a"), columns={"base": 1, "huge": 9})


def test_class_name_escape_hatch():
    card = ui.Card(ui.Text("x"), class_name="marketing-hero")
    assert card.attrs["class"] == "v-card v-stack marketing-hero"


def test_card_alignment():
    card = ui.Card(ui.Icon("check"), gap=2, align="center")
    assert "align-items: center" in card.attrs["style"]


def test_link_button_is_an_anchor_with_button_classes():
    cta = ui.LinkButton("Start", to="/docs", intent="primary", size="lg")
    assert cta.tag == "a"
    assert cta.attrs["href"] == "/docs"
    assert "v-btn-primary" in cta.attrs["class"]
    with pytest.raises(VirelCompileError, match="blocked URL scheme"):
        ui.LinkButton("x", to="javascript:alert(1)")


def test_theme_tokens_include_elevation_and_ring():
    from virel.theme import Theme
    css = Theme().css_tokens()
    assert "--v-shadow-md" in css
    assert "--v-ring" in css
    assert "--v-surface-glass" in css


def test_wrap_and_cluster_flow_layouts():
    wrap = ui.Wrap(ui.Badge("a"), ui.Badge("b"), gap=2)
    assert "v-wrap" in wrap.attrs["class"]
    assert "gap: calc(var(--v-space) * 2)" in wrap.attrs["style"]
    cluster = ui.Cluster(ui.Button("x"), justify="between")
    assert "v-cluster" in cluster.attrs["class"]
    assert "justify-content: space-between" in cluster.attrs["style"]


def test_center_with_optional_min_height():
    plain = ui.Center(ui.Text("x"))
    assert "v-center" in plain.attrs["class"]
    assert plain.attrs.get("style") is None
    sized = ui.Center(ui.Text("x"), min_height="12rem")
    assert sized.attrs["style"] == "min-height: 12rem"
    with pytest.raises(VirelCompileError, match="CSS length"):
        ui.Center(ui.Text("x"), min_height="12rem; position: fixed")


def test_sidebar_pattern_orders_panes_by_side():
    layout = ui.Sidebar(ui.Text("aside"), ui.Text("main"), width="18rem")
    assert "v-sidebar-layout" in layout.attrs["class"]
    assert "--v-sidebar-w: 18rem" in layout.attrs["style"]
    assert layout.children[0].attrs["class"] == "v-sidebar-aside"
    flipped = ui.Sidebar(ui.Text("aside"), ui.Text("main"), side="right")
    assert flipped.children[0].attrs["class"] == "v-sidebar-main"


def test_aspect_ratio_validates_its_ratio():
    box = ui.AspectRatio(ui.Image(src="/public/x.png", alt=""), ratio="4/3")
    assert box.attrs["style"] == "aspect-ratio: 4/3"
    with pytest.raises(VirelCompileError, match="ratio"):
        ui.AspectRatio(ui.Text("x"), ratio="16/9); background: url(evil")


def test_scroll_area_axes_and_containment():
    area = ui.ScrollArea(ui.Text("x"), max_height=240, axis="y")
    assert "v-scroll-y" in area.attrs["class"]
    assert area.attrs["style"] == "max-height: 240px"
    assert area.attrs["tabindex"] == "0"  # keyboard scrollable
    with pytest.raises(VirelCompileError, match="axis"):
        ui.ScrollArea(ui.Text("x"), axis="diagonal")


def test_resizable_directions():
    box = ui.Resizable(ui.Text("x"), direction="horizontal")
    assert "v-resizable-h" in box.attrs["class"]
    with pytest.raises(VirelCompileError, match="direction"):
        ui.Resizable(ui.Text("x"), direction="up")


def test_splitter_markup_and_runtime_binding():
    split = ui.Splitter(ui.Text("left"), ui.Text("right"),
                        initial=30, min_size=10, max_size=70)
    assert split.attrs["style"] == "--v-split: 30%"
    assert split.attrs["data-min"] == "10"
    handle = split.children[1]
    assert handle.attrs["role"] == "separator"
    assert handle.attrs["aria-valuenow"] == "30"
    assert split.runtime_binding == "splitter"
    with pytest.raises(VirelCompileError, match="min_size"):
        ui.Splitter(ui.Text("a"), ui.Text("b"), initial=90, max_size=80)


def test_splitter_compiles_to_runtime_call():
    from virel.compiler import compile_page
    from virel.registry import active_registry

    @ui.page("/split")
    def split_page():
        return ui.Page(ui.Splitter(ui.Text("a"), ui.Text("b")))

    result = compile_page(active_registry().pages["/split"])
    assert "$.splitter(" in result.js
