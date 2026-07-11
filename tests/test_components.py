"""The expanded component library: semantics, accessibility, interactivity."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _compile(fn, path="/"):
    ui.page(path)(fn)
    return compile_page(active_registry().pages[path])


def test_tabs_switch_locally():
    def page():
        return ui.Page(ui.Tabs({
            "First": ui.Text("first panel"),
            "Second": ui.Text("second panel"),
        }))

    view = ui.test.render(page)
    assert view.get_by_text("first panel").is_visible()
    assert not view.get_by_text("second panel").is_visible()
    view.get_by_role("tab", name="Second").click()
    assert not view.get_by_text("first panel").is_visible()
    assert view.get_by_text("second panel").is_visible()


def test_tabs_emit_aria_selected():
    result = _compile(lambda: ui.Page(ui.Tabs({
        "A": ui.Text("a"), "B": ui.Text("b"),
    })))
    assert 'role="tab"' in result.html
    assert 'aria-selected="true"' in result.html
    assert 'aria-selected="false"' in result.html
    assert 'role="tablist"' in result.html


def test_dialog_binds_native_element():
    def page():
        open_state = ui.state(False)
        return ui.Page(
            ui.Button("Open", on_click=lambda: open_state.set(True)),
            ui.Dialog(ui.Text("Body"), open=open_state, title="Settings"),
        )

    result = _compile(page)
    assert "$.bindDialog(" in result.js
    assert "<dialog" in result.html

    view = ui.test.render(page)
    dialog = view.get_by_role("dialog")
    assert not dialog.is_visible()
    view.get_by_role("button", name="Open").click()
    assert view.get_by_role("dialog").is_visible()
    view.get_by_role("button", name="Close dialog").click()
    assert not view.get_by_role("dialog").is_visible()


def test_switch_and_radio_group():
    def page():
        on = ui.state(False)
        plan = ui.state("a")
        return ui.Page(
            ui.Switch(on, label="Notifications"),
            ui.RadioGroup(plan, label="Plan", options=["a", "b"]),
            ui.When(on, then=ui.Text("switched on")),
            ui.Text(f"plan: {plan}"),
        )

    view = ui.test.render(page)
    view.get_by_role("switch").toggle()
    assert view.get_by_text("switched on").is_visible()
    radios = [e for e in view._walk() if e.role == "radio"]
    assert len(radios) == 2
    radios[1].fill("b")
    assert "plan: b" in view.query_text()


def test_slider_drives_progress():
    def page():
        volume = ui.state(10)
        return ui.Page(
            ui.Slider(volume, label="Volume", min=0, max=100),
            ui.Progress(volume, max=100, label="Level"),
        )

    view = ui.test.render(page)
    view.get_by_role("slider").fill(70)
    assert view.get_by_role("progressbar").value() == 70


def test_table_validates_row_shape():
    with pytest.raises(VirelCompileError, match="2 cells"):
        ui.Table(columns=["A", "B", "C"], rows=[["x", "y"]])


def test_table_has_semantic_structure():
    result = _compile(lambda: ui.Page(ui.Table(
        columns=["Name", "Score"],
        rows=[["atlas", "0.9"]],
        caption="Runs",
    )))
    assert '<th scope="col">' in result.html
    assert "<caption>Runs</caption>" in result.html


def test_icon_requires_known_name_and_labels_correctly():
    with pytest.raises(VirelCompileError, match="Unknown icon"):
        ui.Icon("sparkles")
    labeled = ui.Icon("check", label="Done")
    assert labeled.attrs["role"] == "img"
    unlabeled = ui.Icon("check")
    assert unlabeled.attrs["aria-hidden"] == "true"


def test_icon_only_button_with_labeled_icon_is_accessible():
    button = ui.Button(ui.Icon("x", label="Close"), on_click=None)
    assert button.tag == "button"


def test_textarea_renders_initial_value_as_content():
    def page():
        notes = ui.state("draft text")
        return ui.Page(ui.Textarea(notes, label="Notes"))

    result = _compile(page)
    assert ">draft text</textarea>" in result.html


def test_avatar_falls_back_to_initials():
    avatar = ui.Avatar("Ada Lovelace")
    from virel.nodes import TextNode
    initials = [c.text for c in avatar.children if isinstance(c, TextNode)]
    assert initials == ["AL"]


def test_accordion_uses_native_disclosure():
    result = _compile(lambda: ui.Page(ui.Accordion({
        "Q1": ui.Text("A1"),
    })))
    assert "<details" in result.html
    assert "<summary>Q1</summary>" in result.html
