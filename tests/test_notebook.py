"""Notebook integration (SPEC 12.5)."""

import pytest

from virel import ui
from virel.expr import VirelCompileError


def test_preview_uses_the_production_compiler():
    def playground():
        count = ui.state(0)
        return ui.Stack(
            ui.Heading("Playground", level=2),
            ui.Text(f"Count: {count}"),
            ui.Button("Increment",
                      on_click=lambda: count.update(lambda c: c + 1)),
        )

    p = ui.preview(playground)
    assert "Count: 0" in p.document          # server-rendered initial value
    assert "$.bindText(" in p.document       # the production page module
    assert "--v-accent" in p.document        # the compiled stylesheet
    assert "function signal(" in p.document  # the inlined runtime
    assert 'sandbox="allow-scripts"' in p._repr_html_()


def test_preview_accepts_full_pages_and_flags_server_actions():
    @ui.server
    async def save_note(text: str) -> str:
        return text

    def page():
        note = ui.state("")
        return ui.Page(
            ui.TextField(note, label="Note"),
            ui.Button("Save",
                      on_click=lambda: save_note.call({"text": note})),
            title="Notes",
        )

    p = ui.preview(page)
    assert "<title>Notes</title>" in p.document
    assert "need virel dev" in p.document
    assert "save_note" in p.document


def test_preview_runs_the_accessibility_audit():
    def bad():
        clicked = ui.state(0)
        return ui.Button(ui.Icon("settings"),
                         on_click=lambda: clicked.set(1))

    with pytest.raises(VirelCompileError, match="accessible name"):
        ui.preview(bad)
    with pytest.raises(VirelCompileError, match="page or component"):
        ui.preview("not-a-function")


def test_preview_saves_the_standalone_document(tmp_path):
    def static_view():
        return ui.Card(ui.Text("Hello"))

    target = tmp_path / "preview.html"
    ui.preview(static_view).save(str(target))
    content = target.read_text()
    assert content.startswith("<!doctype html>")
    assert "Hello" in content
