"""Model-driven form: one class defines the fields, the browser constraint
attributes, the server validation, and the error display (SPEC 8.9)."""

from dataclasses import dataclass
from typing import Literal

from virel import ui

from ..shared import shell


@dataclass
class InviteInput:
    email: str
    role: Literal["viewer", "editor", "admin"] = "viewer"


_members: list[InviteInput] = []  # demo store; a real app uses a database


@ui.server(idempotent=True)
async def invite_member(data: InviteInput) -> str:
    # The framework has already validated the payload against InviteInput;
    # only domain rules remain.
    if any(member.email == data.email for member in _members):
        raise ValueError(f"{data.email} has already been invited")
    _members.append(data)
    return f"Invitation sent to {data.email} as {data.role}."


@ui.page("/invite")
def invite() -> ui.Node:
    form = ui.form(InviteInput, submit=invite_member)

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Invite a member", level=1),
                ui.Card(
                    ui.Form(
                        ui.TextField(form.email, label="Email",
                                     placeholder="person@example.com"),
                        ui.Select(form.role, label="Role"),
                        ui.FormActions(
                            ui.SubmitButton("Send invitation", form=form),
                        ),
                        ui.When(form.succeeded,
                                then=ui.Alert(form.result, intent="success")),
                        form=form,
                    ),
                ),
                ui.Text("The email field is required and typed from the "
                        "model, so the browser blocks bad submissions "
                        "immediately. The server revalidates against the "
                        "same model and returns field-scoped errors.",
                        muted=True, size="sm"),
            ),
        ),
        title="Invite — Virel Demo",
    )
