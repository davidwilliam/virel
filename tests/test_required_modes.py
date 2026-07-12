"""Required test modes without a browser (SPEC 16.3)."""

import pytest

from virel import ui


def _clean_page():
    def page():
        count = ui.state(0)
        return ui.Page(
            ui.Heading("Title", level=1),
            ui.Text(f"Count: {count}"),
            ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)),
        )
    return page


def test_assert_accessible_passes_and_fails():
    ui.test.assert_accessible(_clean_page())

    def bad():
        clicked = ui.state(0)
        return ui.Page(ui.Heading("One", level=1),
                       ui.Heading("Skip", level=3))  # heading skip -> warning

    with pytest.raises(AssertionError, match="accessibility"):
        ui.test.assert_accessible(bad)


def test_assert_bundle_under_budget():
    size = ui.test.assert_bundle_under(_clean_page(), page_bytes=5000)
    assert size > 0
    with pytest.raises(AssertionError, match="over the"):
        ui.test.assert_bundle_under(_clean_page(), page_bytes=10)


def test_assert_serializable_round_trips():
    ir = ui.test.assert_serializable(_clean_page())
    assert ir["version"]
    assert ir["tree"]


def test_snapshot_records_then_compares(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    page = _clean_page()
    # First run records.
    ui.test.snapshot(page, "clean-page")
    snap = tmp_path / "tests" / "__snapshots__" / "clean-page.html"
    assert snap.exists()
    stored = snap.read_text()
    assert "Count: 0" in stored
    assert 'data-v="' not in stored  # ids normalized out

    # Identical run passes.
    ui.test.snapshot(page, "clean-page")

    # A changed page fails.
    def changed():
        count = ui.state(0)
        return ui.Page(ui.Text(f"Total: {count}"))

    with pytest.raises(AssertionError, match="changed"):
        ui.test.snapshot(changed, "clean-page")

    # update=True accepts the new output.
    ui.test.snapshot(changed, "clean-page", update=True)
    assert "Total: 0" in snap.read_text()
