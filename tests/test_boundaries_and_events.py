"""Error boundaries (SPEC 8.11) and structured streaming (SPEC 8.12)."""

import json

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


def test_error_boundary_emits_isolated_bindings():
    @ui.page("/")
    def page():
        count = ui.state(0)
        return ui.Page(ui.ErrorBoundary(
            ui.Text(f"Count: {count}"),
            ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)),
        ))

    result = compile_page(active_registry().pages["/"])
    assert '$.boundary("' in result.js
    boundary_body = result.js.split("$.boundary(")[1]
    assert "$.bindText(" in boundary_body
    assert "$.on(" in boundary_body
    assert 'class="v-boundary-content"' in result.html
    assert 'class="v-boundary-fallback"' in result.html
    # Default fallback: ErrorState with a message slot and retry.
    assert "data-error-message" in result.html
    assert "data-retry" in result.html
    assert "Something went wrong" in result.html


def test_error_boundary_custom_fallback():
    @ui.page("/")
    def page():
        return ui.Page(ui.ErrorBoundary(
            ui.Text("healthy content"),
            fallback=ui.Alert("This panel is unavailable.", intent="danger"),
        ))

    result = compile_page(active_registry().pages["/"])
    assert "This panel is unavailable." in result.html
    assert "healthy content" in result.html


def test_boundary_content_visible_in_tests():
    def page():
        flag = ui.state(False)
        return ui.Page(ui.ErrorBoundary(
            ui.Button("Go", on_click=lambda: flag.set(True)),
            ui.When(flag, then=ui.Text("done")),
        ))

    view = ui.test.render(page)
    view.get_by_role("button", name="Go").click()
    assert "done" in view.query_text()
    assert "Something went wrong" not in view.query_text()


def test_structured_stream_into_events():
    @ui.server(stream=True)
    async def run_eval(steps: int = 2):
        for step in range(steps):
            yield {"step": step, "status": "ok", "score": 0.9 + step / 100}
        yield {"step": steps, "status": "done", "score": 1.0}

    def page():
        events = ui.state([])
        running = ui.state(False)

        def start():
            events.set([])
            running.set(True)
            run_eval.stream({"steps": 2}, into_events=events,
                            done_set=(running, False))

        return ui.Page(
            ui.Button("Run", on_click=start),
            ui.Each(events, render=lambda item: ui.Text(
                f"step {item.step}: {item.status}")),
        )

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    assert '$.streamEvents("run_eval"' in result.js

    view = ui.test.render(page)
    view.get_by_role("button", name="Run").click()
    text = view.query_text()
    assert "step 0: ok" in text
    assert "step 2: done" in text
    assert view.state("s2") is False


def test_stream_requires_exactly_one_target():
    @ui.server(stream=True)
    def chunks():
        yield "x"

    def page():
        log = ui.state("")
        events = ui.state([])

        def bad():
            chunks.stream({}, into=log, into_events=events)

        return ui.Page(ui.Button("x", on_click=bad))

    with pytest.raises(VirelCompileError, match="exactly one"):
        ui.test.render(page)


def test_server_encodes_dict_chunks_as_json_lines():
    @ui.server(stream=True)
    async def emit():
        yield {"kind": "progress", "value": 40}
        yield {"kind": "progress", "value": 100}

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    response = asgi_request(create_asgi_app(dev=True), "POST",
                            "/_virel/action/emit", body=b"{}")
    lines = [json.loads(line) for line in response.text.strip().splitlines()]
    assert lines == [{"kind": "progress", "value": 40},
                     {"kind": "progress", "value": 100}]


def test_boundary_isolates_server_rendering_failures():
    @ui.page("/")
    def page():
        broken = ui.state(None)
        return ui.Page(
            ui.Text("page intact"),
            ui.ErrorBoundary(ui.Text(ui.length(broken))),
        )

    result = compile_page(active_registry().pages["/"])
    # The page renders; the broken subtree shows its fallback instead.
    assert "page intact" in result.html
    assert 'class="v-boundary-fallback" style="display:contents"' in result.html
    assert "Something went wrong" in result.html
