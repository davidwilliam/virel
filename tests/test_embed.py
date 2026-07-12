"""Embedding in existing applications (SPEC 13.4)."""

import pytest

from virel import ui
from virel.expr import VirelCompileError


def _counter():
    count = ui.state(0)
    return ui.Card(
        ui.Text(f"Count: {count}"),
        ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)),
        gap=3,
    )


def test_fragment_has_markup_scoped_script_and_document():
    fragment = ui.render_fragment(_counter)
    assert fragment.html.startswith('<div data-virel-fragment="vf-')
    assert "Count: 0" in fragment.html
    assert "$.setRoot(__root)" in fragment.script
    assert "$.setRoot(document)" in fragment.script
    assert fragment.document.startswith("<!doctype html>")


def test_static_fragment_needs_no_script():
    def banner():
        return ui.Alert("Maintenance window Sunday.", intent="primary")

    fragment = ui.render_fragment(banner)
    assert fragment.script == ""
    assert "Maintenance window" in fragment.html


def test_custom_element_module_structure():
    source = ui.as_custom_element(_counter, tag="virel-counter")
    assert 'customElements.define' in source
    assert 'attachShadow({ mode: "open" })' in source
    assert "adoptedStyleSheets" in source
    assert "captureScope" in source          # per-instance disposal
    assert "disconnectedCallback" in source
    assert "\\u003c" in source               # inline-safe encoding
    with pytest.raises(VirelCompileError, match="hyphen"):
        ui.as_custom_element(_counter, tag="counter")


def test_embeds_run_the_production_audit():
    def bad():
        clicked = ui.state(0)
        return ui.Button(ui.Icon("x"), on_click=lambda: clicked.set(1))

    with pytest.raises(VirelCompileError, match="accessible name"):
        ui.render_fragment(bad)
    with pytest.raises(VirelCompileError, match="accessible name"):
        ui.as_custom_element(bad, tag="virel-bad")
