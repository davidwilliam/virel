"""Counter: browser-local state, no server involvement (SPEC 6.3)."""

from virel import ui

from ..shared import shell


@ui.page("/counter")
def counter() -> ui.Node:
    count = ui.state(0)
    doubled = ui.derived(lambda: count * 2)

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Counter", level=1),
                ui.Card(
                    ui.Text(f"Count: {count}"),
                    ui.Text(f"Doubled: {doubled}", muted=True),
                    ui.Row(
                        ui.Button(
                            "Increment",
                            on_click=lambda: count.update(lambda c: c + 1),
                            intent="primary",
                        ),
                        ui.Button(
                            "Decrement",
                            on_click=lambda: count.update(lambda c: c - 1),
                        ),
                        ui.Button("Reset", on_click=lambda: count.set(0),
                                  intent="danger"),
                    ),
                    ui.When(
                        count >= 10,
                        then=ui.Alert("That's a big number.", intent="primary"),
                    ),
                ),
            ),
        ),
        title="Counter — Virel Demo",
    )
