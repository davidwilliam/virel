"""Streaming: text chunks, structured events, server-sent events, and a
bidirectional channel (SPEC 8.12, 9.5)."""

import asyncio
import random

from virel import ui

from ..shared import shell


@ui.server(stream=True)
async def run_job(steps: int = 8):
    yield "Starting evaluation job…\n"
    for step in range(1, steps + 1):
        await asyncio.sleep(0.3)
        yield f"[{step}/{steps}] processed batch {step} — ok\n"
    yield "Done. All batches passed.\n"


@ui.server(stream=True)
async def run_eval(steps: int = 5):
    for step in range(1, steps + 1):
        await asyncio.sleep(0.4)
        yield {"step": step, "total": steps,
               "score": round(0.8 + step * 0.03, 2), "status": "ok"}


@ui.server(stream=True)
async def price_ticker(count: int = 12):
    price = 100.0
    for _ in range(count):
        await asyncio.sleep(0.8)
        price = round(price + random.uniform(-1.5, 1.5), 2)
        yield {"symbol": "VRL", "price": price}


@ui.channel("echo")
async def echo(channel: ui.Channel) -> None:
    while True:
        message = await channel.receive()
        await channel.send({"you_said": message.get("text", ""),
                            "length": len(message.get("text", ""))})


def _events_panel() -> ui.Node:
    events = ui.state([])
    running = ui.state(False)

    def start():
        events.set([])
        running.set(True)
        run_eval.stream({"steps": 5}, into_events=events,
                        done_set=(running, False))

    return ui.Card(
        ui.Heading("Structured events", level=3),
        ui.Text("The server yields dicts; they arrive as JSON lines and "
                "render as they land.", muted=True),
        ui.Row(ui.Button("Run evaluation", on_click=start, disabled=running),
               ui.When(running, then=ui.Spinner()), gap=3),
        ui.Each(events, render=lambda e: ui.Row(
            ui.Badge(e.status),
            ui.Text(f"step {e.step}/{e.total}"),
            ui.Spacer(),
            ui.Text(f"score {e.score}", muted=True, size="sm"),
            gap=3,
        ), gap=2),
        gap=4,
    )


def _sse_panel() -> ui.Node:
    ticks = ui.state([])
    ui.subscribe(price_ticker, into_events=ticks)
    return ui.Card(
        ui.Heading("Live ticker (server-sent events)", level=3),
        ui.Text("A one-way EventSource subscription; the browser "
                "reconnects on its own.", muted=True),
        ui.Each(ticks, render=lambda t: ui.Row(
            ui.Text(t.symbol), ui.Spacer(),
            ui.Text(t.price), gap=3,
        ), gap=1),
        gap=4,
    )


def _channel_panel() -> ui.Node:
    messages = ui.state([])
    draft = ui.state("")
    chat = ui.connect("echo", into_events=messages)

    def submit():
        chat.send({"text": draft})
        draft.set("")

    return ui.Card(
        ui.Heading("Bidirectional channel (WebSocket)", level=3),
        ui.Text("Messages go up the socket; the server echoes them back "
                "with metadata.", muted=True),
        ui.Row(
            ui.TextField(draft, label="Message"),
            ui.Button("Send", intent="primary", on_click=submit),
            gap=3, align="end",
        ),
        ui.Each(messages, render=lambda m: ui.Text(
            f"echo: {m.you_said} ({m.length} chars)", muted=True, size="sm"),
            gap=1),
        gap=4,
    )


@ui.page("/stream")
def stream_page() -> ui.Node:
    log = ui.state("")
    running = ui.state(False)

    def start():
        log.set("")
        running.set(True)
        run_job.stream({"steps": 8}, into=log, done_set=(running, False))

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Streaming", level=1),
                ui.Card(
                    ui.Heading("Text stream", level=3),
                    ui.Row(
                        ui.Button("Run job", on_click=start, intent="primary",
                                  disabled=running),
                        ui.When(running, then=ui.Badge("running…",
                                                       intent="primary")),
                        gap=3,
                    ),
                    ui.When(log != "", then=ui.Code(log, block=True)),
                    gap=4,
                ),
                ui.Grid(_events_panel(), _sse_panel(),
                        columns={"base": 1, "md": 2}, gap=6),
                _channel_panel(),
            ),
        ),
        title="Stream — Virel Demo",
    )
