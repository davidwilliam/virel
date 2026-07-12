"""Context packs (SPEC 14.3) over canonical patterns (SPEC 14.6).

``virel context`` assembles task-specific documentation from two
sources: component schemas (SPEC 14.2) and the canonical feature guides
below. Each guide shows exactly one recommended pattern; alternatives
live in the full documentation, not here. Output is deterministic,
budgeted in tokens (a four-characters-per-token estimate), and trimmed
with explicit omission notes rather than silent cuts.
"""

from __future__ import annotations

from typing import Any

from .expr import VirelCompileError

# One recommended pattern per topic (SPEC 14.6). Keys are the doc keys
# diagnostics reference.
GUIDES: dict[str, dict[str, str]] = {
    "state": {
        "title": "Browser state",
        "content": """\
State lives in the browser; the server holds none of it.
    count = ui.state(0)                      # persist="key" survives reloads
    doubled = ui.derived(lambda: count * 2)  # recomputes reactively
    ui.Text(f"Count: {count}")               # f-strings bind reactively
    ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1))
Handlers: a lambda for a call sequence; a named function compiles the
client subset (if/for) via the AST compiler. Reactive values cannot be
used in a Python if; use ui.When(cond, then=...) or ui.cond(c, a, b).""",
    },
    "server-actions": {
        "title": "Server actions",
        "content": """\
A typed Python function becomes a validated HTTP endpoint:
    @ui.server
    async def invite(data: InviteInput) -> str: ...
    invite.call({"data": form_values}, into=result, error_into=error)
Streaming: @ui.server(stream=True) with yield; consume with
    action.stream({...}, into=text_state, done_set=(busy, False))
idempotent=True replays stored responses on retried Idempotency-Keys.
The server revalidates every payload; client checks are conveniences.""",
    },
    "validation": {
        "title": "Forms and validation",
        "content": """\
One model drives the field types, browser constraints, server
validation, and error display. Pydantic, dataclass, or TypedDict:
    @dataclass
    class InviteInput:
        email: str
        role: Literal["viewer", "editor"] = "viewer"
    form = ui.form(InviteInput, submit=invite_member)
    ui.Form(ui.TextField(form.email, label="Email"),
            ui.Select(form.role, label="Role"),
            ui.FormActions(ui.SubmitButton("Send", form=form)),
            ui.When(form.succeeded, then=ui.Alert(form.result)),
            form=form)
Enum fields render as selects and coerce back to the member.""",
    },
    "resources": {
        "title": "Loading data",
        "content": """\
    runs = ui.resource(list