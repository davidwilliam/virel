"""Derived values and reactive conditionals, all client-side."""

from virel import ui

from ..shared import shell


@ui.page("/search")
def search() -> ui.Node:
    query = ui.state("")
    normalized = ui.derived(lambda: query.strip().lower())

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Search normalization", level=1),
                ui.Card(
                    ui.TextField(query, label="Query",
                                 placeholder="Type anything…",
                                 description="Normalization runs in the "
                                             "browser as you type."),
                    ui.When(
                        ui.length(normalized) > 0,
                        then=ui.Text(f"Normalized: {normalized}"),
                        otherwise=ui.Text("Waiting for input…", muted=True),
                    ),
                ),
            ),
        ),
        title="Search — Virel Demo",
    )
