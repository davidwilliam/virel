"""Shared components used across routes."""

from virel import ui

current_user = ui.context("current_user",
                          default={"name": "Ada Lovelace",
                                   "email": "ada@example.com"})


@ui.component
def app_nav() -> ui.Node:
    return ui.Nav(
        ui.Link("Home", to="/"),
        ui.Link("Counter", to="/counter"),
        ui.Link("Search", to="/search"),
        ui.Link("Invite", to="/invite"),
        ui.Link("Components", to="/components"),
        ui.Link("Runs", to="/runs"),
        ui.Link("Files", to="/files"),
        ui.Link("Stream", to="/stream"),
        ui.Link("Widgets", to="/widgets"),
        ui.Link("AI", to="/ai"),
        ui.Link("Settings", to="/settings"),
    )


@ui.component
def user_menu() -> ui.Node:
    user = current_user.get()
    return ui.Menu(
        trigger=ui.Button(ui.Avatar(user["name"], size=26),
                          emphasis="ghost", size="sm",
                          aria_label="Account menu"),
        items=[
            ui.MenuItem("Settings", to="/settings", icon="settings"),
            ui.MenuItem("Project atlas", to="/projects/atlas", icon="folder"),
            ui.MenuDivider(),
            ui.MenuItem("Sign out", to="/", icon="x", intent="danger"),
        ],
    )


@ui.component
def site_footer() -> ui.Node:
    return ui.Footer(
        ui.Text("Virel Demo", size="sm"),
        ui.Spacer(),
        ui.Row(
            ui.Icon("play", size=14),
            ui.Link("This site is built with Virel",
                    to="https://github.com/davidwilliam/virel", external=True),
            gap=2,
        ),
    )


@ui.component
def shell(content: ui.Node, sidebar: ui.Node = None) -> ui.Node:
    navigation = ui.Row(app_nav(), ui.Spacer(), user_menu(), ui.ThemeToggle(),
                        gap=3, align="center")
    return ui.AppShell(brand="Virel Demo", navigation=navigation,
                       content=content, sidebar=sidebar,
                       footer=site_footer())
