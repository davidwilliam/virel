"""Bidirectional real-time channels over WebSocket (SPEC 9.5).

WebSocket use is capability-driven: nothing in the framework opens a
socket unless a page connects to a declared channel. The server side is
an async handler with a typed send/receive pair; the client side is a
page-level connection whose incoming JSON messages append to a list
state, plus a handler op for sending.

    @ui.channel("echo")
    async def echo(channel: ui.Channel) -> None:
        while True:
            message = await channel.receive()
            await channel.send({"echo": message})

    # In a page:
    messages = ui.state([])
    chat = ui.connect("echo", into_events=messages)
    ...
    ui.Button("Send", on_click=lambda: chat.send({"text": draft}))
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .expr import DictExpr, State, VirelCompileError, current_context, current_recorder, lift


class ChannelClosed(Exception):
    """The peer disconnected."""


class Channel:
    """The server side of a live connection."""

    def __init__(self, receive: Callable, send: Callable) -> None:
        self._receive = receive
        self._send = send

    async def receive(self) -> Any:
        while True:
            message = await self._receive()
            if message["type"] == "websocket.disconnect":
                raise ChannelClosed
            if message["type"] == "websocket.receive":
                text = message.get("text")
                if text is None and message.get("bytes") is not None:
                    text = message["bytes"].decode("utf-8", "replace")
                try:
                    return json.loads(text or "null")
                except ValueError:
                    continue  # ignore malformed frames

    async def send(self, data: Any) -> None:
        from .registry import to_jsonable
        await self._send({"type": "websocket.send",
                          "text": json.dumps(to_jsonable(data))})


class ChannelHandler:
    def __init__(self, name: str, fn: Callable, guard: Callable | None) -> None:
        self.name = name
        self.fn = fn
        self.guard = guard


def channel(name: str, guard: Callable | None = None):
    """Declare a WebSocket channel handled by an async function."""
    import inspect

    def decorate(fn: Callable) -> Callable:
        if not inspect.iscoroutinefunction(fn):
            raise VirelCompileError(
                f"Channel handler {fn.__name__!r} must be an async function."
            )
        from .registry import active_registry
        registry = active_registry()
        if name in registry.channels:
            raise VirelCompileError(f"Channel {name!r} is already registered.")
        registry.channels[name] = ChannelHandler(name, fn, guard)
        return fn

    return decorate


# ---------------------------------------------------------------------------
# Client side
# ---------------------------------------------------------------------------

class ChannelSendOp:
    def __init__(self, channel_name: str, args: dict[str, Any]) -> None:
        self.channel_name = channel_name
        self.args = {k: lift(v) for k, v in args.items()}

    def js(self) -> str:
        return (f'$.channelSend("{self.channel_name}", '
                f"{DictExpr(self.args).js()});")

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        payload = {k: v.evaluate(env) for k, v in self.args.items()}
        env.setdefault("__channel_sends__", []).append(
            (self.channel_name, payload))

    def to_ir(self) -> dict[str, Any]:
        return {"op": "channel_send", "channel": self.channel_name}


class Connection:
    """A page's live connection to a channel."""

    def __init__(self, name: str, *, into_events: State,
                 status_into: State | None = None) -> None:
        from .registry import active_registry
        if name not in active_registry().channels:
            raise VirelCompileError(
                f"No channel named {name!r} is registered; declare one with "
                "@ui.channel."
            )
        if not isinstance(into_events, State):
            raise VirelCompileError(
                "ui.connect requires into_events=<ui.state([])> for incoming "
                "messages."
            )
        ctx = current_context()
        self.name = name
        self.into_events = into_events
        self.status_into = status_into
        ctx.connections.append(self)

    def send(self, args: dict[str, Any]) -> None:
        """Inside a handler: send a JSON message over the connection."""
        current_recorder().ops.append(ChannelSendOp(self.name, args))

    def binding_js(self) -> str:
        opts = [f"events: S.{self.into_events.name}"]
        if self.status_into is not None:
            opts.append(f"status: S.{self.status_into.name}")
        return f'$.channel("{self.name}", {{ {", ".join(opts)} }});'


def connect(name: str, *, into_events: State,
            status_into: State | None = None) -> Connection:
    return Connection(name, into_events=into_events, status_into=status_into)
