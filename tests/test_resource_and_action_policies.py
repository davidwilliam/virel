"""Resource retry, invalidation, streaming resources, and action
idempotency, timing, and transport policies."""

import json

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


def test_retry_and_stream_emitted_in_binding():
    @ui.server
    def load() -> list:
        return [1]

    @ui.server(stream=True)
    def tail_logs():
        yield "line\n"

    @ui.page("/")
    def page():
        data = ui.resource(load, retry=2)
        logs = ui.resource(tail_logs)
        return ui.Page(ui.Text(data.value), ui.Text(logs.value))

    result = compile_page(active_registry().pages["/"])
    assert "retry: 2" in result.js
    assert "stream: true" in result.js


def test_streaming_resource_collects_in_tests():
    @ui.server(stream=True)
    def tail_logs(n: int = 2):
        for i in range(n):
            yield f"line {i};"

    def page():
        logs = ui.resource(tail_logs, params={"n": 3})
        return ui.Page(ui.Text(logs.value))

    view = ui.test.render(page)
    assert "line 0;line 1;line 2;" in view.query_text()


def test_invalidate_refetches_bound_resources():
    store = {"items": ["a"]}

    @ui.server
    def list_items() -> list:
        return list(store["items"])

    @ui.server
    def add_item(name: str) -> str:
        store["items"].append(name)
        return name

    def page():
        items = ui.resource(list_items)

        def add():
            add_item.call({"name": "b"})
            ui.invalidate(list_items)

        return ui.Page(
            ui.Button("Add", on_click=add),
            ui.Each(items.value, render=lambda item: ui.Text(item)),
        )

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    assert '$.invalidate("list_items");' in result.js

    view = ui.test.render(page)
    assert "a" in view.query_text()
    assert "b" not in view.query_text()
    view.get_by_role("button", name="Add").click()
    assert "b" in view.query_text()


def test_invalidate_requires_a_server_action():
    def page():
        def handler():
            ui.invalidate("not-an-action")
        return ui.Page(ui.Button("x", on_click=handler))

    with pytest.raises(VirelCompileError, match="server action"):
        ui.test.render(page)


def test_idempotent_action_emits_key_and_server_replays():
    calls = []

    @ui.server(idempotent=True)
    def charge(amount: int) -> str:
        calls.append(amount)
        return f"charged {amount} (call {len(calls)})"

    @ui.page("/")
    def page():
        out = ui.state("")
        return ui.Page(ui.Button(
            "Pay", on_click=lambda: charge.call({"amount": 5}, into=out)))

    result = compile_page(active_registry().pages["/"])
    assert "idempotencyKey: crypto.randomUUID()" in result.js

    app = create_asgi_app(dev=True)
    headers = [(b"content-type", b"application/json"),
               (b"idempotency-key", b"abc-123")]
    first = asgi_request(app, "POST", "/_virel/action/charge",
                         body=b'{"amount": 5}', headers=headers)
    second = asgi_request(app, "POST", "/_virel/action/charge",
                          body=b'{"amount": 5}', headers=headers)
    assert first.json == second.json
    assert calls == [5]  # executed once, replayed after
    assert second.headers.get("idempotency-replayed") == "true"


def test_action_responses_carry_timing_and_request_id():
    @ui.server
    def ping() -> str:
        return "pong"

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    response = asgi_request(create_asgi_app(dev=True), "POST",
                            "/_virel/action/ping", body=b"{}")
    assert "action;dur=" in response.headers["server-timing"]
    assert len(response.headers["x-request-id"]) == 32
