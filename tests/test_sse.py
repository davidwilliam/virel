"""Server-sent events (SPEC 9.5)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


def _ticker():
    @ui.server(stream=True)
    async def price_ticker(symbol: str = "ATLS", count: int = 2):
        for tick in range(count):
            yield {"symbol": symbol, "price": 100 + tick}
    return price_ticker


def test_sse_endpoint_emits_event_stream():
    ticker = _ticker()

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/_virel/action/price_ticker",
                            query="symbol=VRL&count=2")
    assert response.status == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert 'data: {"symbol": "VRL", "price": 100}' in response.text
    assert 'data: {"symbol": "VRL", "price": 101}' in response.text
    # Typed query conversion applied to count.
    assert response.text.count("data:") == 2


def test_sse_guarded():
    def guard(request: ui.Request):
        if request.query.get("key") != "ok":
            return ui.deny(403, "no")

    @ui.server(stream=True, guard=guard)
    async def feed():
        yield {"n": 1}

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    assert asgi_request(app, "GET", "/_virel/action/feed").status == 403
    assert asgi_request(app, "GET", "/_virel/action/feed",
                        query="key=ok").status == 200


def test_subscribe_emits_sse_binding():
    ticker = _ticker()

    @ui.page("/")
    def page():
        symbol = ui.state("ATLS")
        ticks = ui.state([])
        ui.subscribe(ticker, params={"symbol": symbol}, into_events=ticks)
        return ui.Page(
            ui.TextField(symbol, label="Symbol"),
            ui.Each(ticks, render=lambda t: ui.Text(f"{t.symbol}: {t.price}")),
        )

    result = compile_page(active_registry().pages["/"])
    assert '$.sse("price_ticker", () => ({"symbol": S.s1.get()}), ' \
           "{ events: S.s2 });" in result.js


def test_subscribe_drains_in_component_tests():
    ticker = _ticker()

    def page():
        ticks = ui.state([])
        ui.subscribe(ticker, params={"symbol": "VRL", "count": 3},
                     into_events=ticks)
        return ui.Page(ui.Each(ticks,
                               render=lambda t: ui.Text(f"{t.symbol} {t.price}")))

    view = ui.test.render(page)
    text = view.query_text()
    assert "VRL 100" in text
    assert "VRL 102" in text


def test_subscribe_requires_stream_action_and_one_target():
    @ui.server
    def not_streaming() -> str:
        return "x"

    def bad_action():
        ui.subscribe(not_streaming, into=ui.state(""))
        return ui.Page(ui.Text("x"))

    with pytest.raises(VirelCompileError, match="stream=True"):
        ui.test.render(bad_action)

    ticker = _ticker()

    def bad_targets():
        ui.subscribe(ticker)
        return ui.Page(ui.Text("x"))

    with pytest.raises(VirelCompileError, match="exactly one"):
        ui.test.render(bad_targets)
