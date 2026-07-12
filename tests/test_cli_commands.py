"""The remaining CLI commands (SPEC 15.1)."""

import json
from pathlib import Path

import pytest

from virel import ui
from virel.registry import fresh_registry


@pytest.fixture
def demo_app():
    """A tiny app registered fresh for graph/deploy/doctor tests."""
    fresh_registry()

    @ui.server
    async def save(text: str) -> str:
        return text

    @ui.page("/")
    def home():
        return ui.Page(ui.Link("Settings", to="/settings"),
                       title="Home")

    @ui.page("/settings")
    def settings():
        note = ui.state("")
        return ui.Page(
            ui.TextField(note, label="Note"),
            ui.Button("Save", on_click=lambda: save.call({"text": note})),
        )

    yield
    fresh_registry()


def test_doctor_reports_health(tmp_path):
    from virel.doctor import run_doctor
    report = run_doctor(tmp_path)  # no project here
    assert report["ok"] is True
    names = {c["name"]: c["status"] for c in report["checks"]}
    assert names["python"] == "ok"
    assert names["project"] == "warn"  # no virel.toml


def test_graph_captures_routes_actions_and_links(demo_app):
    from virel.graph import build_graph, graph_dot, graph_text
    graph = build_graph()
    ids = {node["id"] for node in graph["nodes"]}
    assert "route:/" in ids and "route:/settings" in ids
    assert "action:save" in ids
    kinds = {(e["from"], e["to"], e["kind"]) for e in graph["edges"]}
    assert ("route:/settings", "action:save", "calls") in kinds
    assert ("route:/", "route:/settings", "links") in kinds

    dot = graph_dot(graph)
    assert dot.startswith("digraph virel {")
    assert '"route:/settings" -> "action:save"' in dot

    text = graph_text(graph)
    assert "calls action save" in text
    assert "links to /settings" in text


def test_migrate_dry_run_and_apply(tmp_path):
    from virel.migrate import available_migrations, run_migration
    assert "unsafe-html-namespace" in available_migrations()

    app = tmp_path / "app"
    app.mkdir()
    source = 'from virel import ui\nx = ui.unsafe_html("<b>hi</b>", reason="x")\n'
    (app / "page.py").write_text(source)

    patches = run_migration("unsafe-html-namespace", tmp_path, apply=False)
    assert len(patches) == 1 and patches[0]["changes"] == 1
    assert (app / "page.py").read_text() == source  # dry run untouched

    run_migration("unsafe-html-namespace", tmp_path, apply=True)
    assert "ui.unsafe.html(" in (app / "page.py").read_text()

    from virel.expr import VirelCompileError
    with pytest.raises(VirelCompileError, match="Unknown migration"):
        run_migration("nonexistent", tmp_path)


def test_deploy_asgi_generates_artifacts(tmp_path):
    from virel.deploy import generate_artifacts
    written = generate_artifacts(
        tmp_path, {"app": {"module": "app.app"}}, target="asgi")
    assert set(written) == {"asgi.py", "Dockerfile", ".dockerignore"}
    entry = (tmp_path / "asgi.py").read_text()
    assert "import app.app" in entry
    assert "create_asgi_app()" in entry
    assert "uvicorn" in (tmp_path / "Dockerfile").read_text()
    # Existing files are kept, not overwritten.
    again = generate_artifacts(
        tmp_path, {"app": {"module": "app.app"}}, target="asgi")
    assert again == []


def test_deploy_static_rejects_dynamic_routes(demo_app, tmp_path):
    from virel.deploy import generate_artifacts

    @ui.page("/items/{item_id}")
    def item(item_id: str):
        return ui.Page(ui.Text(item_id))

    from virel.expr import VirelCompileError
    with pytest.raises(VirelCompileError, match="dynamic"):
        generate_artifacts(tmp_path, {"app": {"module": "x"}},
                           target="static")


def test_deploy_static_for_a_static_app(tmp_path):
    fresh_registry()

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("Static"))

    from virel.deploy import generate_artifacts
    written = generate_artifacts(tmp_path, {"app": {"module": "app.app"}},
                                target="static")
    assert "DEPLOY-static.md" in written
    fresh_registry()


def test_cli_registers_every_spec_command():
    from virel.cli import main
    import argparse
    import contextlib
    import io
    # Argparse lists the choices in its error; capture them.
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer), \
            pytest.raises(SystemExit):
        main(["not-a-command"])
    listed = buffer.getvalue()
    for command in ("new", "dev", "build", "preview", "check", "test",
                    "inspect", "routes", "graph", "schema", "context",
                    "bind", "migrate", "doctor", "deploy"):
        assert command in listed, f"{command} missing from the CLI"
