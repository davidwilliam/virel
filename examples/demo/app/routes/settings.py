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
                _appearance(),
            ),
        title="Settings — Virel Demo",
    )


def _appearance() -> ui.Node:
    """Runtime design preferences (SPEC 10.1): brand, density, and
    contrast switch instantly, persist across reloads, and are applied
    before first paint. Brands are registered on the theme in app.py."""
    return ui.Card(
        ui.Heading("Appearance", level=2, size=3),
        ui.Text("Preferences apply instantly, persist in this browser, "
                "and never flash on reload.", muted=True, size="sm"),
        ui.Row(
            ui.Text("Brand", size="sm"),
            ui.Button("Default", size="sm",
                      on_click=lambda: ui.set_preference("brand", None)),
            ui.Button("Mono", size="sm",
                      on_click=lambda: ui.set_preference("brand", "mono")),
            ui.Button("Emerald", size="sm",
                      on_click=lambda: ui.set_preference("brand", "emerald")),
            ui.Button("Blue", size="sm",
                      on_click=lambda: ui.set_preference("brand", "blue")),
            ui.Button("Rose", size="sm",
                      on_click=lambda: ui.set_preference("brand", "rose")),
            ui.Button("Amber", size="sm",
                      on_click=lambda: ui.set_preference("brand", "amber")),
            gap=3, wrap=True,
        ),
        ui.Row(
            ui.Text("Density", size="sm"),
            ui.Button("Comfortable", size="sm",
                      on_click=lambda: ui.set_preference("density", None)),
            ui.Button("Compact", size="sm",
                      on_click=lambda: ui.set_preference("density",
                                                         "compact")),
            gap=3, wrap=True,
        ),
        ui.Row(
            ui.Text("Contrast", size="sm"),
            ui.Button("Normal", size="sm",
                      on_click=lambda: ui.set_preference("contrast", None)),
            ui.Button("High", size="sm",
                      on_click=lambda: ui.set_preference("contrast", "high")),
            gap=3, wrap=True,
        ),
        gap=4,
    )
