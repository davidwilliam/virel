"""Streaming server action bound to reactive state (SPEC 8.12).

Transport is plain streamed HTTP — no WebSocket (SPEC 9.5).
"""

import asyncio

from virel import ui

from ..shared import shell


@ui.server(stream=True)
async def run_job(steps: int = 8):
    yield "Starting evaluation job…\n"
    for step in range(1, steps + 1):
        await asyncio.sleep(0.35)
        yield f"[{step}/{steps}] processed batch {step} — ok\n"
    yield "Done. All batches passed.\n"


@ui.page("/stream")
def stream_page() -> ui.Node:
    log = ui.state("")
    running = ui.state(False)

    def start() -> None:
        log.set("")
        running.set(True)
        run_job.stream({"steps": 8}, into=log, done_set=(running, False))

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Streamed job logs", level=1),
                ui.Card(
                    ui.Row(
                        ui.Button("Run job", on_click=start, intent="primary",
                                  disabled=running),
                        ui.When(running, then=ui.Badge("running…",
                                                       intent="primary")),
                    ),
                    ui.When(
                        log != "",
                        then=ui.Code(log, block=True),
                        otherwise=ui.EmptyState(
                            title="No output yet",
                            description="Run the job to stream logs from the "
                                        "Python server over HTTP.",
                        ),
                    ),
                ),
            ),
        ),
        title="Stream — Virel Demo",
    )
