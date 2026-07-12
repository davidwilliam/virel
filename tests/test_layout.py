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
