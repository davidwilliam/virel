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
