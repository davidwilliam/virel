"""AI product components (SPEC 12.4): a playground over a simulated
model. Every primitive here is plain UI wired to states and streaming
actions; nothing knows or cares which model sits behind the action."""

import asyncio

from virel import ui

from ..shared import shell

_REPLY = ("Refunds are honored for thirty days from purchase. Open the "
          "order, choose Request refund, and the credit posts within two "
          "business days. Annual plans are prorated to the day.")


@ui.server(stream=True)
async def complete(prompt: str = "") -> object:
    for word in _REPLY.split(" "):
        yield word + " "
        await asyncio.sleep(0.03)


@ui.page("/ai")
def ai_playground() -> ui.Node:
    prompt = ui.state("")
    answer = ui.state("")
    busy = ui.state(False)
    model = ui.state("atlas-large")
    temperature = ui.state(0.7)
    tokens_in = ui.state(1184)
    tokens_out = ui.state(96)
    rating = ui.state("")
    decision = ui.state("pending")
    job_status = ui.state("running")
    job_pct = ui.state(62)
    voice = ui.FileField(label="Audio note", accept="audio/*")

    def send():
        busy.set(True)
        answer.set("")
        complete.stream({"prompt": prompt}, into=answer,
                        done_set=(busy, False))

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("AI components", level=1),
                ui.Text("Sixteen primitives for AI products, composed "
                        "from the same states and streaming actions as "
                        "everything else. The model here is simulated; "
                        "swap the action and nothing in the UI changes.",
                        muted=True),
                ui.Grid(
                    ui.Card(
                        ui.Heading("Conversation", level=2, size=3),
                        ui.ai.Response(answer, streaming=busy),
                        ui.ai.Feedback(rating),
                        ui.ai.PromptEditor(prompt, on_submit=send),
                        ui.ai.Citations([
                            {"title": "Refund policy",
                             "url": "/projects/atlas?tab=settings",
                             "snippet": "Thirty days, prorated annual "
                                        "plans."},
                            {"title": "Billing FAQ", "url": "/settings"},
                        ]),
                        gap=4,
                    ),
                    ui.Card(
                        ui.Heading("Run controls", level=2, size=3),
                        ui.ai.ModelSelect(model,
                                          models=["atlas-large",
                                                  "atlas-small",
                                                  "baseline"]),
                        ui.ai.Parameters(
                            ui.ai.Param("temperature", temperature,
                                        min=0.0, max=2.0, step=0.1),
                        ),
                        ui.ai.TokenMeter(tokens_in, tokens_out,
                                         input_price=3.0,
                                         output_price=15.0,
                                         budget=4000),
                        ui.ai.Recorder(voice),
                        gap=4,
                    ),
                    columns={"base": 1, "md": 2},
                    gap=5,
                ),
                ui.Card(
                    ui.Heading("Tool use and provenance", level=2, size=3),
                    ui.ai.ToolCall(
                        "search_orders",
                        {"customer": "ada@example.com", "window_days": 30},
                        result={"orders": 2, "latest": "2026-07-08"}),
                    ui.ai.Trace([
                        {"name": "plan", "start_ms": 0,
                         "duration_ms": 140},
                        {"name": "search_orders", "start_ms": 140,
                         "duration_ms": 480, "depth": 1},
                        {"name": "draft", "start_ms": 620,
                         "duration_ms": 900, "depth": 1},
                        {"name": "verify", "start_ms": 1520,
                         "duration_ms": 210, "status": "failed",
                         "depth": 1},
                    ]),
                    gap=4,
                ),
                ui.Grid(
                    ui.Card(
                        ui.Heading("Oversight", level=2, size=3),
                        ui.ai.Approval(
                            title="Send the refund confirmation?",
                            description="One email to ada@example.com "
                                        "with the prorated amount.",
                            on_approve=lambda: decision.set("approved"),
                            on_reject=lambda: decision.set("rejected")),
                        ui.Text(f"Decision: {decision}", muted=True,
                                size="sm"),
                        gap=3,
                    ),
                    ui.Card(
                        ui.Heading("Long-running work", level=2, size=3),
                        ui.ai.JobProgress(status=job_status,
                                          progress=job_pct,
                                          label="Backfill embeddings"),
                        ui.Row(
                            ui.Button("Finish", size="sm",
                                      on_click=lambda: (
                                          job_status.set("done"),
                                          job_pct.set(100))),
                            ui.Button("Fail", size="sm",
                                      on_click=lambda: job_status.set(
                                          "failed")),
                            gap=3,
                        ),
                        gap=3,
                    ),
                    columns={"base": 1, "md": 2},
                    gap=5,
                ),
            ),
        ),
        title="AI — Virel Demo",
    )
