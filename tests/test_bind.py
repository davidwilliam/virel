"""Binding generation from custom elements manifests."""

import pytest

from virel import ui
from virel.bind import generate_bindings, parse_manifest
from virel.expr import VirelCompileError

MANIFEST = {
    "schemaVersion": "1.0.0",
    "modules": [
        {
            "kind": "javascript-module",
            "path": "src/widgets.js",
            "declarations": [
                {
                    "kind": "class",
                    "name": "DatePicker",
                    "customElement": True,
                    "tagName": "date-picker",
                    "summary": "Calendar-based date input.",
                    "attributes": [
                        {"name": "value", "type": {"text": "string"}},
                        {"name": "min-date", "type": {"text": "string | undefined"}},
                        {"name": "disabled", "type": {"text": "boolean"}},
                        {"name": "step", "type": {"text": "number"}},
                    ],
                    "events": [{"name": "date-selected"}],
                },
                {
                    "kind": "class",
                    "name": "Helper",
                    "customElement": False,
                },
            ],
        }
    ],
}


def test_parse_manifest_extracts_components():
    specs = parse_manifest(MANIFEST)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.tag == "date-picker"
    assert spec.class_name == "DatePicker"
    assert spec.props == {
        "value": "str",
        "min_date": "str",
        "disabled": "bool",
        "step": "float",
    }
    assert spec.events == ["date-selected"]


def test_generated_module_is_valid_python_and_binds():
    specs = parse_manifest(MANIFEST)
    source = generate_bindings(specs, "/public/widgets.js", "widgets.json")
    namespace: dict = {}
    exec(compile(source, "bindings.py", "exec"), namespace)
    DatePicker = namespace["DatePicker"]
    node = DatePicker(value="2026-01-01", min_date="2025-01-01")
    assert node.tag == "date-picker"
    assert node.attrs["value"] == "2026-01-01"
    assert node.attrs["min-date"] == "2025-01-01"


def test_generated_binding_rejects_unknown_props():
    specs = parse_manifest(MANIFEST)
    source = generate_bindings(specs, "/public/widgets.js", "widgets.json")
    namespace: dict = {}
    exec(compile(source, "bindings.py", "exec"), namespace)
    with pytest.raises(VirelCompileError, match="no prop 'color'"):
        namespace["DatePicker"](color="red")


def test_generated_events_documented():
    specs = parse_manifest(MANIFEST)
    source = generate_bindings(specs, "/public/widgets.js", "widgets.json")
    assert "# Events: on_date_selected" in source


def test_manifest_without_elements_is_an_error():
    with pytest.raises(VirelCompileError, match="declares no custom elements"):
        parse_manifest({"modules": [{"declarations": []}]})
    with pytest.raises(VirelCompileError, match="not a custom elements manifest"):
        parse_manifest({"something": "else"})


def test_generated_binding_works_in_a_page():
    specs = parse_manifest(MANIFEST)
    source = generate_bindings(specs, "/public/widgets.js", "widgets.json")
    namespace: dict = {}
    exec(compile(source, "bindings.py", "exec"), namespace)
    DatePicker = namespace["DatePicker"]

    def page():
        chosen = ui.state("")
        return ui.Page(
            DatePicker(value=chosen,
                       on_date_selected=ui.set_from_event(chosen, "detail.value")),
            ui.Text(f"chosen: {chosen}"),
        )

    view = ui.test.render(page)
    assert "chosen:" in view.query_text()
