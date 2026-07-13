"""The expanded component library: semantics, accessibility, interactivity."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _compile(fn, path="/"):
    ui.page(path)(fn)
    return compile_page(active_registry().pages[path])


def test_example_shows_result_and_source():
    def demo():
        return ui.Button("Press me", intent="primary")

    def page():
        return ui.Page(ui.Example(demo))

    result = _compile(page)
    html = result.html
    # The live result is the real rendered component.
    assert '<div class="v-example-result">' in html
    assert "Press me" in html
    # The source is shown, highlighted, and is the function's own text.
    # (Highlighting tokenizes identifiers into spans, so assert on the
    # fragments rather than the contiguous source.)
    assert '<div class="v-example-code">' in html
    assert "demo" in html and "Button" in html
    # Highlighting ran (Python keyword token present).
    assert 'class="v-tok-kw"' in html


def test_example_live_result_is_interactive():
    def demo():
        count = ui.state(0)
        return ui.Button(f"Count: {count}",
                         on_click=lambda: count.update(lambda c: c + 1))

    def page():
        return ui.Page(ui.Example(demo))

    result = _compile(page)
    # The example's component compiles to real client JS, so it runs live.
    assert "$.signal(0)" in result.js
    assert "Count: 0" in result.html


def test_example_with_explicit_source_and_title():
    node = ui.Text("hello")

    def page():
        return ui.Page(ui.Example(node, source="ui.Text('hello')",
                                  title="greeting.py"))

    html = _compile(page).html
    assert '<div class="v-example-bar">greeting.py</div>' in html
    # Source is highlighted; the string literal appears as a token.
    assert 'v-tok-str' in html and "hello" in html


def test_example_without_source_is_an_error():
    node = ui.Text("hi")
    with pytest.raises(VirelCompileError):
        ui.Example(node)


def test_badge_success_and_warning_intents():
    def page():
        return ui.Page(
            ui.Badge("Healthy", intent="success"),
            ui.Badge("Degraded", intent="warning"))

    html = _compile(page).html
    assert 'class="v-badge v-badge-success"' in html
    assert 'class="v-badge v-badge-warning"' in html


def test_alert_warning_intent():
    def page():
        return ui.Page(ui.Alert("Heads up", intent="warning"))

    assert 'class="v-alert v-alert-warning"' in _compile(page).html


def test_badge_rejects_unknown_intent():
    with pytest.raises(VirelCompileError):
        ui.Badge("x", intent="bogus")


def test_heading_anchor_slugifies_and_links():
    def page():
        return ui.Page(ui.Heading("Getting Started!", level=2, anchor=True))

    html = _compile(page).html
    assert 'id="getting-started"' in html
    assert 'class="v-heading-anchor" href="#getting-started"' in html


def test_heading_explicit_id():
    def page():
        return ui.Page(ui.Heading("Install", level=2, id="setup"))

    html = _compile(page).html
    assert 'id="setup"' in html


def test_heading_without_anchor_has_no_id():
    def page():
        return ui.Page(ui.Heading("Plain", level=2))

    html = _compile(page).html
    assert "<h2" in html and "id=" not in html.split("<h2")[1].split(">")[0]


def test_table_of_contents_derives_from_content():
    content = ui.Stack(
        ui.Heading("Overview", level=2, anchor=True),
        ui.Text("intro"),
        ui.Heading("Details", level=3, anchor=True),
        ui.Heading("Deep note", level=4, anchor=True),  # excluded by levels
    )

    def page():
        return ui.Page(ui.TableOfContents(content), content)

    html = _compile(page).html
    # Links to the h2 and h3 anchors, labeled by their text.
    assert '<a href="#overview" class="v-toc-link">Overview</a>' in html
    assert '<a href="#details" class="v-toc-link">Details</a>' in html
    # h4 is outside the default (2, 3) levels, so it is not in the TOC
    # (though the heading itself still carries its own anchor).
    assert 'v-toc-link">Deep note' not in html
    # The anchor '#' glyph is not pulled into the TOC label.
    assert ">Overview#<" not in html


def test_table_of_contents_empty_when_no_anchored_headings():
    content = ui.Stack(ui.Heading("No anchor", level=2), ui.Text("body"))

    def page():
        return ui.Page(ui.TableOfContents(content), content)

    html = _compile(page).html
    assert 'class="v-toc"' in html
    assert "v-toc-link" not in html


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


def test_select_is_enhanced_by_the_runtime():
    def page():
        role = ui.state("viewer")
        return ui.Page(ui.Select(role, label="Role",
                                 options=["viewer", "editor"]))

    result = _compile(page)
    assert 'class="v-select"' in result.html
    assert "$.select(" in result.js
    # The native element stays in the markup as the source of truth.
    assert "v-select-native" in result.html
    assert '<option value="viewer">' in result.html


def test_button_ghost_emphasis():
    button = ui.Button("Archive", intent="danger", emphasis="ghost")
    assert "v-btn-ghost" in button.attrs["class"]
    assert "v-btn-danger" in button.attrs["class"]
    solid = ui.Button("Save", intent="primary")
    assert "v-btn-ghost" not in solid.attrs["class"]
    with pytest.raises(VirelCompileError, match="emphasis"):
        ui.Button("x", emphasis="outline")
