"""Typed style objects (SPEC 10.4)."""

import pytest

from virel import ui
from virel.expr import VirelCompileError
from virel.theme import build_stylesheet


def test_style_compiles_the_spec_example():
    card_style = ui.style(
        padding=6,
        radius="lg",
        background="surface.1",
        border="subtle",
        hover={"shadow": "md"},
    )
    assert card_style.class_name.startswith("vs-")
    assert "padding: calc(var(--v-space) * 6)" in card_style.css
    assert "border-radius: var(--v-radius-lg)" in card_style.css
    assert "background: var(--v-surface-1)" in card_style.css
    assert "border: 1px solid var(--v-border)" in card_style.css
    assert f".{card_style.class_name}:hover" in card_style.css
    assert "box-shadow: var(--v-shadow-md)" in card_style.css


def test_styles_land_in_the_application_stylesheet():
    accent = ui.style(background="accent.soft", color="accent")
    assert accent.css in build_stylesheet()


def test_identical_styles_deduplicate():
    a = ui.style(padding=4, radius="md")
    b = ui.style(padding=4, radius="md")
    assert a.class_name == b.class_name
    from virel.registry import active_registry
    assert list(active_registry().styles).count(a.class_name) == 1


def test_style_objects_pass_as_class_name():
    s = ui.style(padding=2)
    assert ui.Card(ui.Text("x"), class_name=s).attrs["class"] == \
        f"v-card v-stack {s.class_name}"
    both = ui.Box(class_name=[s, "extra"])
    assert both.attrs["class"] == f"v-box {s.class_name} extra"


def test_style_vocabulary_is_validated():
    with pytest.raises(VirelCompileError, match="Unknown style property"):
        ui.style(padding=2, float="left")
    with pytest.raises(VirelCompileError, match="color token"):
        ui.style(background="url(javascript:x)")
    with pytest.raises(VirelCompileError, match="space units"):
        ui.style(padding="12px; position: fixed")
    with pytest.raises(VirelCompileError, match="must be one of"):
        ui.style(radius="xl")
    with pytest.raises(VirelCompileError, match="dict of style"):
        ui.style(padding=2, hover="shadow")
    with pytest.raises(VirelCompileError, match="at least one"):
        ui.style()


def test_state_variants_focus_and_active():
    s = ui.style(color="fg.muted",
                 focus={"color": "accent"},
                 active={"opacity": 0.7})
    assert f".{s.class_name}:focus-visible" in s.css
    assert f".{s.class_name}:active" in s.css
    assert "opacity: 0.7" in s.css


def test_hex_colors_pass_validation():
    s = ui.style(background="#0f172a")
    assert "background: #0f172a" in s.css


def test_use_css_ships_raw_rules_last():
    ui.use_css(".viz { container-type: inline-size; }")
    ui.use_css("@container (min-width: 30rem) { .viz p { columns: 2; } }")
    css = build_stylesheet()
    assert ".viz { container-type: inline-size; }" in css
    assert "@container (min-width: 30rem)" in css
    # Raw rules come after everything so they can override any default.
    assert css.index(".viz {") > css.index(".v-card")


def test_use_css_reaches_the_served_stylesheet():
    from virel.server import create_asgi_app
    from conftest import asgi_request

    ui.use_css(".invoice-grid { display: grid; }")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(create_asgi_app(dev=True), "GET", "/_virel/app.css")
    assert ".invoice-grid { display: grid; }" in response.text


def test_use_css_rejects_empty_input():
    with pytest.raises(VirelCompileError, match="non-empty"):
        ui.use_css("   ")
