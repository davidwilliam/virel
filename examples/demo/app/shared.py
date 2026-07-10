"""Shared components used across routes."""

from virel import ui


@ui.component
def app_nav() -> ui.Node:
    return ui.Nav(
        ui.Link("Home", to="/"),
        ui.Link("Counter", to="/counter"),
        ui.Link("Search", to="/search"),
        ui.Link("Invite", to="/invite"),
        ui.Link("Stream", to="/stream"),
        ui.Link("Widgets", to="/widgets"),
        ui.Link("Project", to="/projects/atlas"),
    )


@ui.component
def shell(content: ui.Node) -> ui.Node:
    return ui.AppShell(brand="Virel Demo", navigation=app_nav(), content=content)
