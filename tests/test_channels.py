"""WebSocket channels (SPEC 9.5)."""

import asyncio

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import _ws_accept_key, _ws_encode_frame, create_asgi_app


def _echo_channel():
    @ui.channel("echo")
    async def echo(channel: ui.Channel) -> None:
        while True:
            message = await channel.receive()
            await channel.send({"echo": message})
    return echo


async def _ws_session(app, path, client_messages, headers=None):
    """Drive an ASGI websocket exchange; returns the server's messages."""
    sent = []
    incoming = [{"type": "websocket.connect"}]
    incoming += [{"type": "websocket.receive", "text": m}
                 for m in client_messages]
    incoming.append({"type": "websocket.disconnect"})
    iterator = iter(incoming)

    async def receive():
        try:
            return next(iterator)
        except StopIteration:
            await asyncio.sleep(3600)

    async def send(message):
        sent.append(message)

    await app({"type": "websocket", "path": path, "query_string": b"",
               "headers": headers or []}, receive, send)
    return sent


def test_channel_echo_round_trip():
    _echo_channel()

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    sent = asyncio.run(_ws_session(app, "/_virel/channel/echo",
                                   ['{"text": "hello"}']))
    assert sent[0] == {"type": "websocket.accept"}
    assert sent[1]["type"] == "websocket.send"
    assert '"echo": {"text": "hello"}' in sent[1]["text"]


def test_unknown_channel_and_cross_origin_are_refused():
    _echo_channel()

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    sent = asyncio.run(_ws_session(app, "/_virel/channel/nope", []))
    assert sent == [{"type": "websocket.close", "code": 4404}]

    sent = asyncio.run(_ws_session(
        app, "/_virel/channel/echo", [],
        headers=[(b"origin", b"https://evil.example"),
                 (b"host", b"myapp.example")]))
    assert sent == [{"type": "websocket.close", "code": 4403}]


def test_guarded_channel():
    def guard(request: ui.Request):
        if request.query.get("key") != "ok":
            return ui.deny()

    @ui.channel("private", guard=guard)
    async def private(channel: ui.Channel) -> None:
        await channel.send({"ready": True})
        await channel.receive()

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    sent = asyncio.run(_ws_session(app, "/_virel/channel/private", []))
    assert sent == [{"type": "websocket.close", "code": 4401}]


def test_connect_emits_binding_and_send_op():
    _echo_channel()

    def page():
        messages = ui.state([])
        draft = ui.state("")
        chat = ui.connect("echo", into_events=messages)

        def submit():
            chat.send({"text": draft})
            draft.set("")

        return ui.Page(
            ui.TextField(draft, label="Message"),
            ui.Button("Send", on_click=submit),
            ui.Each(messages, render=lambda m: ui.Text(m.echo.text)),
        )

    ui.page("/")(page)
    result = compile_page(active_registry().pages["/"])
    assert '$.channel("echo", { events: S.s1 });' in result.js
    assert '$.channelSend("echo", {"text": S.s2.get()});' in result.js

    view = ui.test.render(page)
    view.get_by_label("Message").fill("hi there")
    view.get_by_role("button", name="Send").click()
    assert view.channel_sends == [("echo", {"text": "hi there"})]


def test_connect_requires_registered_channel():
    def page():
        ui.connect("ghost", into_events=ui.state([]))
        return ui.Page(ui.Text("x"))

    with pytest.raises(VirelCompileError, match="No channel"):
        ui.test.render(page)


def test_channel_handlers_must_be_async():
    with pytest.raises(VirelCompileError, match="async"):
        @ui.channel("sync")
        def not_async(channel):
            pass


def test_ws_frame_codec():
    # RFC 6455 sample handshake key.
    assert _ws_accept_key("dGhlIHNhbXBsZSBub25jZQ==") == \
        "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
    frame = _ws_encode_frame(0x1, b"hello")
    assert frame == b"\x81\x05hello"
    big = _ws_encode_frame(0x1, b"x" * 200)
    assert big[:4] == b"\x81\x7e\x00\xc8"
