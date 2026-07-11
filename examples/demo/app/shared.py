"""Shared components used across routes."""

from virel import ui


@ui.component
def app_nav() -> ui.Node:
    return ui.Nav(
        ui.Link("Home", to="/"),
        ui.Link("Counter", to="/counter"),
        ui.Link("Search", to="/search"),
        ui.Link("Invite", to="/invite"),
        ui.Link("Components", to="/components"),
        ui.Link("Runs", to="/runs"),
        ui.Link("Stream", to="/stream"),
        ui.Link("Widgets", to="/widgets"),
        ui.Link("Project", to="/projects/atlas"),
    )


@ui.component
def shell(content: ui.Node) -> ui.Node:
    navigation = ui.Row(app_nav(), ui.Spacer(), ui.ThemeToggle(),
                        gap=4, align="center")
    return ui.AppShell(brand="Virel Demo", navigation=navigation,
                       content=content)
