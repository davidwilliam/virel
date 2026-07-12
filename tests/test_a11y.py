"""Compile-time accessibility audit (SPEC 11.2)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _compiled(fn):
    return compile_page(active_registry().pages[fn])


def test_icon_only_button_without_label_is_rejected():
    @ui.page("/unnamed")
    def unnamed():
        clicked = ui.state(0)
        return ui.Page(ui.Button(
            ui.Icon("settings"),
            on_click=lambda: clicked.update(lambda n: n + 1)))

    with pytest.raises(VirelCompileError, match="accessible name"):
        _compiled("/unnamed")


def test_icon_label_or_aria_label_names_the_button():
    @ui.page("/named")
    def named():
        clicked = ui.state(0)
        bump = lambda: clicked.update(lambda n: n + 1)  # noqa: E731
        return ui.Page(
            ui.Button(ui.Icon("settings", label="Settings"), on_click=bump),
            ui.Button(ui.Icon("x"), on_click=bump, aria_label="Close"),
        )

    assert _compiled("/named").warnings == []


def test_focusable_content_inside_aria_hidden_is_rejected():
    from virel.nodes import Element, TextNode

    @ui.page("/hidden-focus")
    def hidden_focus():
        return ui.Page(Element(
            "div",
            [Element("button", [TextNode("Ghost")],
                     attrs={"type": "button"})],
            attrs={"aria-hidden": "true"},
        ))

    with pytest.raises(VirelCompileError, match="aria-hidden"):
        _compiled("/hidden-focus")


def test_heading_skips_warn_and_size_split_fixes_them():
    @ui.page("/skippy")
    def skippy():
        return ui.Page(ui.Heading("Title", level=1),
                       ui.Heading("Card", level=3))

    warnings = _compiled("/skippy").warnings
    assert any("skips from h1 to h3" in w for w in warnings)

    @ui.page("/sized")
    def sized():
        return ui.Page(ui.Heading("Title", level=1),
                       ui.Heading("Card", level=2, size=3))

    compiled = _compiled("/sized")
    assert compiled.warnings == []
    assert "<h2" in compiled.html and "v-h3" in compiled.html


def test_multiple_h1_headings_warn():
    @ui.page("/twoh1")
    def twoh1():
        return ui.Page(ui.Heading("One", level=1), ui.Heading("Two", level=1))

    assert any("Multiple h1" in w for w in _compiled("/twoh1").warnings)


def test_vague_link_text_warns_and_strict_mode_promotes():
    @ui.page("/vague")
    def vague():
        return ui.Page(ui.Link("click here", to="/docs"))

    assert any("does not describe" in w for w in _compiled("/vague").warnings)

    ui.use_accessibility(strict=True)
    try:
        with pytest.raises(VirelCompileError, match="strict"):
            _compiled("/vague")
    finally:
        ui.use_accessibility(strict=False)


def test_reactive_attributes_do_not_confuse_the_audit():
    @ui.page("/reactive-name")
    def reactive_name():
        label = ui.state("Save draft")
        return ui.Page(ui.Button(f"{label}",
                                 on_click=lambda: label.set("Saved")))

    assert _compiled("/reactive-name").warnings == []
