"""Form with a typed server action: browser validation UX, server
revalidation, structured errors (SPEC 8.8, 8.9)."""

from virel import ui

from ..shared import shell

_ROLES = ["viewer", "editor", "admin"]
_members: list[dict] = []  # module-level demo store; a real app uses a DB


@ui.server
async def invite_member(email: str, role: str) -> str:
    email = email.strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError(f"{email!r} is not a valid email address")
    if role not in _ROLES:
        raise ValueError(f"unknown role {role!r}")
    _members.append({"email": email, "role": role})
    return f"Invitation sent to {email} as {role}."


@ui.page("/invite")
def invite() -> ui.Node:
    email = ui.state("")
    role = ui.state("viewer")
    result = ui.state("")
    error = ui.state("")

    # A named handler goes through the AST client compiler, so real Python
    # control flow works and compiles to JavaScript.
    def submit() -> None:
        result.set("")
        error.set("")
        if len(email.strip()) < 3:
            error.set("Enter an email address first.")
        else:
            invite_member.call({"email": email, "role": role},
                               into=result, error_into=error)

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Invite a member", level=1),
                ui.Card(
                    ui.TextField(email, label="Email",
                                 placeholder="person@example.com", kind="email"),
                    ui.Select(role, label="Role", options=_ROLES),
                    ui.Row(
                        ui.Button("Send invitation", on_click=submit,
                                  intent="primary",
                                  disabled=ui.length(email.strip()) == 0),
                    ),
                    ui.When(result != "",
                            then=ui.Alert(result, intent="success")),
                    ui.When(error != "",
                            then=ui.Alert(error, intent="danger")),
                ),
                ui.Text("The button stays disabled until you type an email — "
                        "that check runs in the browser. The server always "
                        "revalidates.", muted=True, size="sm"),
            ),
        ),
        title="Invite — Virel Demo",
    )
