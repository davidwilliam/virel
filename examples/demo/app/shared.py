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
        ui.Link("Stream", to="/stream"),
        ui.Link("Widgets", to="/widgets"),
        ui.Link("Project", to="/projects/atlas"),
    )


@ui.component
def shell(content: ui.Node, theme_toggle: bool = True) -> ui.Node:
    """App shell with navigation. The home route passes theme_toggle=False
    to stay completely JavaScript-free; it still follows the system color
    scheme through CSS alone."""
    navigation = ui.Row(app_nav(), gap=4, align="center")
    if theme_toggle:
        navigation = ui.Row(app_nav(), ui.Spacer(), ui.ThemeToggle(),
                            gap=4, align="center")
    return ui.AppShell(brand="Virel Demo", navigation=navigation,
                       content=content)
