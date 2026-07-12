"""Scoped queries (SPEC 16.1) and deterministic control (SPEC 16.4)."""

import pytest

from virel import ui


# -- 16.1 scoped queries -----------------------------------------------------

def test_queries_scope_to_an_element():
    @ui.page("/members")
    def members():
        open = ui.state(False)
        email = ui.state("")
        return ui.Page(
            ui.Button("Invite member", on_click=lambda: open.set(True)),
            ui.Dialog(ui.TextField(email, label="Email"),
                      open=open, title="Invite"),
        )

    view = ui.test.render(members)
    view.get_by_role("button", name="Invite member").click()
    dialog = view.get_by_role("dialog")
    assert dialog.get_by_label("Email").is_visible()
    # The scoped query only sees inside the dialog.
    assert dialog.get_by_text("Invite").own_text() == "Invite"


def test_scoped_query_excludes_outside_matches():
    @ui.page("/two")
    def two():
        return ui.Page(
            ui.Nav(ui.Link("Home", to="/"), ui.Button("Act"), label="primary"),
            ui.Nav(ui.Link("Home", to="/"), label="secondary"),
        )

    view = ui.test.render(two)
    navs = view.get_all_by_role("navigation")
    assert len(navs) == 2
    # The button lives only in the first nav; scoping finds it there and
    # not in the second.
    navs[0].get_by_role("button", name="Act")
    with pytest.raises(AssertionError):
        navs[1].get_by_role("button", name="Act")


# -- 16.4 deterministic control ----------------------------------------------

def test_mock_action_response_and_recording():
    @ui.server
    async def save(text: str) -> str:
        return "real: " + text

    @ui.page("/save")
    def save_page():
        result = ui.state("")
        return ui.Page(
            ui.Button("Save",
                      on_click=lambda: save.call({"text": "hi"},
                                                 into=result)),
            ui.Text(f"{result}"),
        )

    with ui.test.render(save_page) as view:
        view.mock_action("save", returns="mocked")
        view.get_by_role("button", name="Save").click()
        assert "mocked" in view.query_text()
        assert view.action_calls == [
            {"name": "save", "args": {"text": "hi"}, "at": 0.0}]


def test_mock_action_error_and_retry_sequence():
    @ui.server
    async def submit(n: int) -> str:
        return "real"

    @ui.page("/retry")
    def retry_page():
        result = ui.state("")
        error = ui.state("")
        return ui.Page(
            ui.Button("Go",
                      on_click=lambda: submit.call({"n": 1}, into=result,
                                                   error_into=error)),
            ui.Text(f"r={result} e={error}"),
        )

    with ui.test.render(retry_page) as view:
        view.mock_action("submit",
                         sequence=[ValueError("boom"), "recovered"])
        view.get_by_role("button", name="Go").click()
        assert "ValueError" in view.query_text()   # first call failed
        view.get_by_role("button", name="Go").click()
        assert "recovered" in view.query_text()     # retry succeeded


def test_latency_advances_the_clock_without_waiting():
    @ui.server
    async def act(x: int) -> str:
        return "real"

    @ui.page("/lat")
    def lat_page():
        out = ui.state("")
        return ui.Page(ui.Button("Do",
                                 on_click=lambda: act.call({"x": 1},
                                                           into=out)))

    with ui.test.render(lat_page) as view:
        view.mock_action("act", returns="ok", latency=120)
        assert view.clock.now == 0.0
        view.get_by_role("button", name="Do").click()
        assert view.clock.now == 120.0


def test_mock_stream_controls_chunks():
    @ui.server(stream=True)
    async def gen(prompt: str):
        yield "real"

    @ui.page("/stream")
    def stream_page():
        answer = ui.state("")
        return ui.Page(
            ui.Button("Run",
                      on_click=lambda: gen.stream({"prompt": "x"},
                                                  into=answer)),
            ui.Text(f"{answer}"),
        )

    with ui.test.render(stream_page) as view:
        view.mock_stream("gen", chunks=["Hel", "lo ", "world"])
        view.get_by_role("button", name="Run").click()
        assert "Hello world" in view.query_text()


def test_test_clock_runs_timers_in_order():
    from virel.testing import TestClock
    clock = TestClock()
    order = []
    clock.set_timeout(lambda: order.append("b"), 200)
    clock.set_timeout(lambda: order.append("a"), 100)
    clock.advance(150)
    assert order == ["a"]           # only the 100ms timer fired
    clock.advance(100)
    assert order == ["a", "b"]
    assert clock.now == 250


def test_test_clock_flushes_animation_frames():
    from virel.testing import TestClock
    clock = TestClock()
    painted = []
    clock.request_frame(lambda: painted.append(1))
    clock.request_frame(lambda: painted.append(2))
    assert painted == []
    clock.flush_frames()
    assert painted == [1, 2]


def test_batched_updates_settle_together():
    @ui.page("/batch")
    def batch_page():
        a = ui.state(0)
        b = ui.state(0)
        runs = ui.state(0)
        ui.effect(lambda: runs.update(lambda r: r + 1),
                  dependencies=[a, b])
        return ui.Page(
            ui.Button("A", on_click=lambda: a.update(lambda v: v + 1)),
            ui.Button("B", on_click=lambda: b.update(lambda v: v + 1)),
            ui.Text(f"runs={runs}"),
        )

    # Unbatched: each click fires the effect once.
    view = ui.test.render(batch_page)
    view.get_by_role("button", name="A").click()
    view.get_by_role("button", name="B").click()
    assert "runs=2" in view.query_text()

    # Batched: two mutations, the effect fires once at the batch end.
    batched = ui.test.render(batch_page)
    with batched.batch() as v:
        v.get_by_role("button", name="A").click()
        v.get_by_role("button", name="B").click()
    assert "runs=1" in batched.query_text()


def test_mocks_do_not_leak_after_close():
    @ui.server
    async def once(x: int) -> str:
        return "real"

    @ui.page("/leak")
    def leak_page():
        out = ui.state("")
        return ui.Page(ui.Button("Go",
                                 on_click=lambda: once.call({"x": 1},
                                                            into=out)),
                       ui.Text(f"{out}"))

    view = ui.test.render(leak_page)
    view.mock_action("once", returns="mocked")
    view.close()
    # A fresh view sees the real action again.
    view2 = ui.test.render(leak_page)
    view2.get_by_role("button", name="Go").click()
    assert "real" in view2.query_text()
