"""Derived values and reactive conditionals, all client-side."""

from virel import ui

from ..shared import shell


@ui.client
def shout(value: str) -> str:
    """Compiled ahead of time to JavaScript; also callable as plain Python."""
    trimmed = value.strip()
    if len(trimmed) == 0:
        return ""
    return trimmed.upper() + "!"


@ui.page("/search")
def search() -> ui.Node:
    query = ui.state("")
    normalized = ui.derived(lambda: query.strip().lower())
    shouted = ui.derived(lambda: shout(query))

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
                        then=[
                            ui.Text(f"Normalized: {normalized}"),
                            ui.Text(f"Shouted: {shouted}", muted=True),
                        ],
                        otherwise=ui.Text("Waiting for input…", muted=True),
                    ),
                ),
            ),
        ),
        title="Search — Virel Demo",
    )
