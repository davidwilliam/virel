"""Pagination, notifications, popover, and date selection (SPEC 11.1)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def test_pagination_state_mode_numbers_and_steps():
    @ui.page("/paged")
    def paged():
        page = ui.state(1)
        return ui.Page(
            ui.Pagination(page, 5),
            ui.Text(f"On page {page}"),
        )

    view = ui.test.render(paged)
    view.get_by_role("button", name="3").click()
    assert "On page 3" in view.query_text()
    view.get_by_role("button", name="Next").click()
    assert "On page 4" in view.query_text()
    view.get_by_role("button", name="Previous").click()
    assert "On page 3" in view.query_text()

    js = compile_page(active_registry().pages["/paged"]).js
    assert '$.bindAttr' in js and 'aria-current' in js


def test_pagination_clamps_at_the_edges():
    @ui.page("/edges")
    def edges():
        page = ui.state(1)
        return ui.Page(ui.Pagination(page, 3), ui.Text(f"page: {page}"))

    view = ui.test.render(edges)
    # Previous at page 1 is disabled and cannot go below 1.
    with pytest.raises(AssertionError, match="disabled"):
        view.get_by_role("button", name="Previous").click()
    assert "page: 1" in view.query_text()


def test_pagination_large_totals_use_a_counter():
    @ui.page("/many")
    def many():
        page = ui.state(7)
        return ui.Page(ui.Pagination(page, 40))

    view = ui.test.render(many)
    assert "Page 7 of 40" in view.query_text()
    view.get_by_role("button", name="Next").click()
    assert "Page 8 of 40" in view.query_text()


def test_pagination_href_mode_windows_with_ellipses():
    nav = ui.Pagination(7, 20, href=lambda n: f"?page={n}")
    from virel.nodes import template_html
    html = template_html([nav], {})
    assert 'aria-current="page"' in html
    assert 'href="?page=6"' in html and 'href="?page=8"' in html
    assert 'href="?page=1"' in html and 'href="?page=20"' in html
    assert 'href="?page=3"' not in html  # elided
    assert html.count("v-page-gap") == 2
    with pytest.raises(VirelCompileError, match="blocked URL scheme"):
        ui.Pagination(1, 3, href=lambda n: f"javascript:go({n})")
    with pytest.raises(VirelCompileError, match="current page number"):
        ui.Pagination(0, 3, href=lambda n: f"?page={n}")


def test_notify_compiles_and_records():
    @ui.page("/notifying")
    def notifying():
        saved = ui.state(0)

        def save():
            saved.update(lambda n: n + 1)
            ui.notify(f"Saved {saved} time(s)", intent="success")

        return ui.Page(ui.Button("Save", on_click=save))

    js = compile_page(active_registry().pages["/notifying"]).js
    assert '$.notify(' in js and '"intent": "success"' in js

    view = ui.test.render(notifying)
    view.get_by_role("button", name="Save").click()
    assert view.notifications == [
        {"message": "Saved 1 time(s)", "intent": "success"}]


def test_notify_validates_inputs():
    @ui.page("/bad-notify")
    def bad_notify():
        return ui.Page(ui.Button(
            "x", on_click=lambda: ui.notify("m", intent="loud")))

    with pytest.raises(VirelCompileError, match="intent"):
        ui.test.render(bad_notify)


def test_popover_markup():
    box = ui.Popover(trigger=ui.Button(ui.Icon("info", label="Details")),
                     content=ui.Text("More context here."), align="end")
    assert box.runtime_binding == "popover"
    assert "v-popover-end" in box.attrs["class"]
    assert box.children[-1].attrs["class"] == "v-popover-panel"
    with pytest.raises(VirelCompileError, match="align"):
        ui.Popover(trigger=ui.Text("t"), content=ui.Text("c"), align="top")


def test_date_field_binds_and_validates():
    @ui.page("/dated")
    def dated():
        due = ui.state("2026-07-12")
        return ui.Page(
            ui.DateField(due, label="Due date", min="2026-01-01",
                         max="2026-12-31"),
            ui.Text(f"Due: {due}"),
        )

    view = ui.test.render(dated)
    view.get_by_label("Due date").fill("2026-08-01")
    assert "Due: 2026-08-01" in view.query_text()

    @ui.page("/bad-date")
    def bad_date():
        return ui.Page(ui.DateField(ui.state(""), label="x", min="tomorrow"))

    with pytest.raises(VirelCompileError, match="ISO format"):
        ui.test.render(bad_date)


def test_date_field_kinds():
    @ui.page("/times")
    def times():
        at = ui.state("09:30")
        return ui.Page(ui.DateField(at, label="Start", kind="time"))

    view = ui.test.render(times)
    view.get_by_label("Start")

    @ui.page("/bad-kind")
    def bad_kind():
        return ui.Page(ui.DateField(ui.state(""), label="x", kind="month"))

    with pytest.raises(VirelCompileError, match="kind"):
        ui.test.render(bad_kind)


_FOLDERS = [
    {"name": "src", "children": [
        {"name": "app.py"},
        {"name": "routes", "children": [{"name": "home.py"}]},
    ]},
    {"name": "tests"},
]


def test_tree_builds_the_aria_pattern():
    @ui.page("/tree")
    def tree_page():
        selected = ui.state("")
        return ui.Page(
            ui.Tree(_FOLDERS,
                    label=lambda n: n["name"],
                    on_select=lambda n: selected.set(n["name"])),
            ui.Text(f"Selected: {selected}"),
        )

    view = ui.test.render(tree_page)
    view.get_by_text("home.py").click()
    assert "Selected: home.py" in view.query_text()

    html = compile_page(active_registry().pages["/tree"]).html
    assert 'role="tree"' in html
    assert 'role="treeitem"' in html
    assert 'role="group"' in html
    assert 'aria-expanded="true"' in html
    assert "$.tree(" in compile_page(active_registry().pages["/tree"]).js


def test_tree_requires_items():
    @ui.page("/empty-tree")
    def empty_tree():
        return ui.Page(ui.Tree([], label=lambda n: n["name"]))

    with pytest.raises(VirelCompileError, match="at least one"):
        compile_page(active_registry().pages["/empty-tree"])


def test_command_palette_compiles_commands():
    @ui.page("/palette")
    def palette_page():
        count = ui.state(0)
        return ui.Page(ui.CommandPalette(commands=[
            ui.Command("Go to settings", to="/settings", hint="Navigation"),
            ui.Command("Reset counter",
                       on_run=lambda: count.set(0)),
        ]))

    compiled = compile_page(active_registry().pages["/palette"])
    assert 'role="combobox"' in compiled.html
    assert 'role="listbox"' in compiled.html
    assert 'data-label="go to settings"' in compiled.html
    assert 'href="/settings"' in compiled.html
    assert "$.palette(" in compiled.js

    view = ui.test.render(palette_page)
    view.get_by_role("option", name="Reset counter").click()
    assert view.state("s1") == 0


def test_command_validation():
    with pytest.raises(VirelCompileError, match="exactly one"):
        ui.Command("Both", to="/x", on_run=lambda: None)
    with pytest.raises(VirelCompileError, match="blocked URL scheme"):
        ui.Command("Bad", to="javascript:alert(1)")

    @ui.page("/bad-hotkey")
    def bad_hotkey():
        return ui.Page(ui.CommandPalette(
            commands=[ui.Command("Home", to="/")], hotkey="F1"))

    with pytest.raises(VirelCompileError, match="single letter"):
        compile_page(active_registry().pages["/bad-hotkey"])


def test_reorderable_each_wires_state_writeback():
    @ui.page("/reorder")
    def reorder_page():
        tasks = ui.state(["alpha", "beta", "gamma"])
        return ui.Page(
            ui.Each(tasks, render=lambda t: ui.Text(t), key=lambda t: t,
                    reorderable=True),
        )

    compiled = compile_page(active_registry().pages["/reorder"])
    assert ", true);" in compiled.js          # bindList reorder flag
    assert '"virel-reorder"' in compiled.js
    assert "S.s1.set(ev.detail.items);" in compiled.js


def test_reorderable_requires_key_and_writeback_path():
    @ui.page("/reorder-nokey")
    def nokey():
        tasks = ui.state(["a"])
        return ui.Page(ui.Each(tasks, render=lambda t: ui.Text(t),
                               reorderable=True))

    with pytest.raises(VirelCompileError, match="key="):
        compile_page(active_registry().pages["/reorder-nokey"])

    @ui.page("/reorder-nostate")
    def nostate():
        return ui.Page(ui.Each([{"id": 1}],
                               render=lambda t: ui.Text(t["id"]),
                               key=lambda t: t["id"], reorderable=True))

    with pytest.raises(VirelCompileError, match="on_reorder"):
        compile_page(active_registry().pages["/reorder-nostate"])


def test_reorder_handler_updates_state_in_python():
    captured = {}

    @ui.page("/reorder-exec")
    def reorder_exec():
        tasks = ui.state(["alpha", "beta"])
        each = ui.Each(tasks, render=lambda t: ui.Text(t), key=lambda t: t,
                       reorderable=True)
        captured["each"] = each
        return ui.Page(each, ui.Text(f"Order: {tasks}"))

    view = ui.test.render(reorder_exec)
    view._run_handler(captured["each"].on_reorder,
                      ev={"detail": {"items": ["beta", "alpha"]}})
    assert view.state("s1") == ["beta", "alpha"]
