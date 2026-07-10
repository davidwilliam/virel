"""Dynamic route with path and query parameters, server-rendered."""

from virel import ui

from ..shared import shell

_TABS = ["overview", "runs", "settings"]


@ui.page("/projects/{project_id}")
def project_page(project_id: str, tab: str = "overview") -> ui.Node:
    if tab not in _TABS:
        tab = "overview"
    return ui.Page(
        shell(
            ui.Section(
                ui.Row(
                    ui.Heading(f"Project: {project_id}", level=1),
                    ui.Badge(tab, intent="primary"),
                ),
                ui.Row(
                    *[
                        ui.Link(name.title(),
                                to=f"/projects/{project_id}?tab={name}")
                        for name in _TABS
                    ],
                    gap=4,
                ),
                ui.Card(
                    ui.Text(f"This page was server-rendered for project "
                            f"'{project_id}' with the '{tab}' tab selected. "
                            "Path and query parameters map to typed Python "
                            "function arguments."),
                ),
            ),
        ),
        title=f"{project_id} — Virel Demo",
    )
