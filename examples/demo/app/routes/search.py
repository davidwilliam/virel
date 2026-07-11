"""Derived values and reactive conditionals, all client-side."""

from virel import ui

from ..shared import shell


@ui.shared
def shout(value: str) -> str:
    """A shared pure function: compiled to JavaScript for the browser and
    callable as ordinary Python on the server and in tests."""
    trimmed = value.strip()
    if len(trimmed) == 0:
        return ""
    return trimmed.upper() + "!"


@ui.server
def record_search(query: str) -> str:
    return f"last: {query}"


@ui.page("/search")
def search() -> ui.Node:
    # url="q" keeps the query synchronized with ?q=, so searches are
    # shareable links.
    query = ui.state("", url="q")
    normalized = ui.derived(lambda: query.strip().lower())
    shouted = ui.derived(lambda: shout(query))
    last_tracked = ui.state("")
    # ui.effect: runs in the browser whenever the query changes.
    ui.effect(lambda: record_search.call({"query": normalized},
                                         into=last_tracked),
              dependencies=[normalized])

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
                    ui.When(last_tracked != "",
                            then=ui.Text(f"Tracked by an effect: "
                                         f"{last_tracked}",
                                         muted=True, size="sm")),
                ),
            ),
        ),
        title="Search — Virel Demo",
    )
