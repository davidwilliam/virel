"""Per-item event handlers and keyed updates in ui.Each."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def _items_action():
    @ui.server
    def list_items() -> list[dict]:
        return [
            {"id": 1, "name": "atlas"},
            {"id": 2, "name": "baseline"},
        ]
    return list_items


def test_item_handler_compiles_to_delegated_js():
    action = _items_action()

    def page():
        selected = ui.state("")
        items = ui.resource(action, server_render=True)
        return ui.Page(
            ui.Each(items.value, key=lambda item: item.id,
                    render=lambda item: ui.Button(
                        "Select", on_click=lambda: selected.set(item.name))),
            ui.Text(f"selected: {selected}"),
        )

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    # Handler map keyed by template handler id, receiving (ev, item)
    assert '"h0": { "click": (ev, item) => { S.s1.set(item.name); } }' in result.js
    # Key function emitted for reconciliation
    assert "(item) => item.id" in result.js
    # Server-rendered items carry the handler id and item index
    assert 'data-vh="h0"' in result.html
    assert 'data-vi="0"' in result.html
    assert 'data-vi="1"' in result.html


def test_item_click_selects_item_in_component_test():
    action = _items_action()

    def page():
        selected = ui.state("")
        items = ui.resource(action)
        return ui.Page(
            ui.Each(items.value,
                    render=lambda item: ui.Button(
                        "Select", on_click=lambda: selected.set(item.name))),
            ui.When(selected != "", then=ui.Text(f"selected: {selected}")),
        )

    view = ui.test.render(page)
    buttons = view.get_all_by_role("button", name="Select")
    assert len(buttons) == 2
    buttons[1].click()
    assert "selected: baseline" in view.query_text()
    buttons = view.get_all_by_role("button", name="Select")
    buttons[0].click()
    assert "selected: atlas" in view.query_text()


def test_item_action_call_updates_resource_value():
    data = [{"id": 1, "name": "atlas"}, {"id": 2, "name": "baseline"}]

    @ui.server
    def list_items() -> list[dict]:
        return list(data)

    @ui.server
    def remove_item(id: int) -> list[dict]:
        data[:] = [d for d in data if d["id"] != id]
        return list(data)

    def page():
        items = ui.resource(list_items)
        return ui.Page(
            ui.Each(items.value, key=lambda item: item.id,
                    render=lambda item: ui.Row(
                        ui.Text(item.name),
                        ui.Button("Remove",
                                  on_click=lambda: remove_item.call(
                                      {"id": item.id}, into=items.value)),
                    )),
        )

    view = ui.test.render(page)
    assert "atlas" in view.query_text()
    view.get_all_by_role("button", name="Remove")[0].click()
    text = view.query_text()
    assert "atlas" not in text
    assert "baseline" in text


def test_named_handler_with_item_closure():
    action = _items_action()

    def page():
        log = ui.state("")
        items = ui.resource(action)

        def make_row(item):
            def inspect():
                if item.name == "atlas":
                    log.set("primary model")
                else:
                    log.set(f"other: {item.name}")
            return ui.Button("Inspect", on_click=inspect)

        return ui.Page(
            ui.Each(items.value, render=make_row),
            ui.Text(log),
        )

    view = ui.test.render(page)
    buttons = view.get_all_by_role("button", name="Inspect")
    buttons[0].click()
    assert "primary model" in view.query_text()
    buttons[1].click()
    assert "other: baseline" in view.query_text()


def test_two_way_bindings_still_rejected_in_templates():
    action = _items_action()

    def page():
        q = ui.state("")
        items = ui.resource(action)
        return ui.Page(ui.Each(
            items.value,
            render=lambda item: ui.TextField(q, label="No"),
        ))

    with pytest.raises(VirelCompileError, match="Two-way bindings"):
        ui.test.render(page)
