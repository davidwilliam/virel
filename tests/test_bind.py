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


def _fake_npm(files: dict[str, str], package="@vendor/rating",
              version="2.1.0"):
    """A fake registry fetcher serving one package built in memory."""
    import io
    import json as _json
    import tarfile

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=f"package/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    tarball = buffer.getvalue()
    metadata = _json.dumps({
        "dist-tags": {"latest": version},
        "versions": {version: {
            "dist": {"tarball": "https://registry.npmjs.org/fake.tgz"}}},
    }).encode()

    def fetch(url):
        return tarball if url.endswith(".tgz") else metadata

    return fetch


_MANIFEST = """{
  "schemaVersion": "1.0.0",
  "modules": [{
    "kind": "javascript-module",
    "path": "dist/rating.js",
    "declarations": [{
      "kind": "class", "customElement": true, "tagName": "vendor-rating",
      "summary": "A rating control.",
      "attributes": [{"name": "value", "type": {"text": "number"}}],
      "events": [{"name": "rating-changed"}]
    }]
  }]
}"""


def test_bind_npm_vendors_and_generates(tmp_path):
    from virel.bind import bind_npm

    fetch = _fake_npm({
        "package.json": '{"name": "@vendor/rating", "module": '
                        '"dist/rating.js", "style": "dist/rating.css", '
                        '"customElements": "custom-elements.json"}',
        "custom-elements.json": _MANIFEST,
        "dist/rating.js": "customElements.define('vendor-rating', "
                          "class extends HTMLElement {});",
        "dist/rating.css": ".vendor-rating { display: block; }",
    })
    source, vendor_dir = bind_npm("@vendor/rating", tmp_path, fetcher=fetch)
    assert (vendor_dir / "dist" / "rating.js").exists()
    assert 'ui.use_static("/vendor/rating", _VENDOR)' in source
    assert '@import url("/vendor/rating/dist/rating.css");' in source
    assert 'module="/vendor/rating/dist/rating.js"' in source
    assert 'events=["rating-changed"]' in source
    assert 'ui.Island(load="visible")' in source  # lazy-loading guidance
    assert "@vendor/rating@2.1.0" in source

    # The generated file is importable and registers the mount.
    bindings = tmp_path / "app" / "bindings_rating.py"
    bindings.parent.mkdir()
    bindings.write_text(source)
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(tmp_path / 'app')!r}); "
         "import bindings_rating; "
         "print(bindings_rating.VendorRating.tag)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "vendor-rating"


def test_bind_npm_refuses_hostile_tarballs(tmp_path):
    from virel.bind import bind_npm

    fetch = _fake_npm({"../escape.txt": "outside"})
    with pytest.raises(VirelCompileError, match="escapes the package"):
        bind_npm("@vendor/rating", tmp_path, fetcher=fetch)

    fetch = _fake_npm({"package.json": "{}"})
    with pytest.raises(VirelCompileError, match="custom elements manifest"):
        bind_npm("@vendor/rating", tmp_path, fetcher=fetch)

    with pytest.raises(VirelCompileError, match="Invalid npm package"):
        bind_npm("../evil", tmp_path, fetcher=fetch)


def test_declared_events_are_validated():
    Rating = ui.web_component(tag="vendor-rating",
                              module="/vendor/rating/dist/rating.js",
                              props={"value": float},
                              events=["rating-changed"])
    score = None

    @ui.page("/rated")
    def rated():
        current = ui.state(3)
        return ui.Page(Rating(
            value=current,
            on_rating_changed=ui.set_from_event(current, "detail.value")))

    from virel.compiler import compile_page
    from virel.registry import active_registry
    compile_page(active_registry().pages["/rated"])

    @ui.page("/rated-bad")
    def rated_bad():
        current = ui.state(0)
        return ui.Page(Rating(
            on_exploded=ui.set_from_event(current, "detail.x")))

    with pytest.raises(VirelCompileError, match="declares no event"):
        compile_page(active_registry().pages["/rated-bad"])
