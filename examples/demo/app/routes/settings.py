"""Sidebar shell, request context from a guard, and guarded actions."""

from virel import ui

from ..shared import current_user, shell


def load_session(request: ui.Request) -> None:
    # A real application would look the session cookie up in a store; the
    # demo derives a user so the flow is visible end to end.
    name = request.query.get("as", "Ada Lovelace")
    current_user.provide({"name": name,
                          "email": f"{name.split()[0].lower()}@example.com"})


_TABS = ("profile", "workspace", "billing")


@ui.layout("/settings")
def settings_layout(content: ui.Node) -> ui.Node:
    """Nested layout (SPEC 8.10): every /settings page renders inside the
    sidebar shell without repeating it."""
    sidebar = ui.Nav(
        ui.Link("Profile", to="/settings"),
        ui.Link("Workspace", to="/settings?tab=workspace"),
        ui.Link("Billing", to="/settings?tab=billing"),
        ui.Link("Members", to="/invite"),
        label="Settings",
    )
    return shell(content, sidebar=sidebar)


@ui.page("/settings", guard=load_session)
def settings(tab: str = "profile") -> ui.Node:
    if tab not in _TABS:
        tab = "profile"
    user = current_user.get()
    display_name = ui.state(user["name"])
    saved = ui.state("")

    return ui.Page(
            ui.Section(
                ui.Heading(tab.title(), level=1),
                ui.Text(f"Signed in as {user['name']} ({user['email']}). "
                        "This page is server-rendered per request: the guard "
                        "reads the session and provides the user through "
                        "ui.context. Try /settings?as=Grace+Hopper.",
                        muted=True),
                ui.Card(
                    ui.TextField(display_name, label="Display name"),
                    ui.Row(
                        ui.Button("Save", intent="primary",
                                  on_click=lambda: saved.set("Saved.")),
                        ui.When(saved != "", then=ui.Badge(saved,
                                                           intent="primary")),
                        gap=3,
                    ),
                    gap=4,
                ),
            ),
        title="Settings — Virel Demo",
    )
