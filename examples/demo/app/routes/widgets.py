"""Third-party web component integrated through a typed binding (SPEC 13.1).

The binding module is generated from the element's custom elements
manifest:

    virel bind star-rating.manifest.json \
        --module /public/star-rating.js --out app/bindings.py
"""

from virel import ui

from ..bindings import StarRating
from ..shared import shell


@ui.page("/widgets")
def widgets() -> ui.Node:
    rating = ui.state(3)

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Web component binding", level=1),
                ui.Card(
                    ui.Text("star-rating is a vanilla custom element (see "
                            "public/star-rating.js). Virel binds it with "
                            "typed props and events — data flows both ways."),
                    StarRating(
                        value=rating,
                        max=5,
                        on_rating_changed=ui.set_from_event(rating, "detail.value"),
                    ),
                    ui.Text(f"Python-side state sees: {rating} / 5"),
                    ui.Row(
                        ui.Button("Set to 5",
                                  on_click=lambda: rating.set(5)),
                        ui.Button("Clear", on_click=lambda: rating.set(0)),
                    ),
                ),
            ),
        ),
        title="Widgets — Virel Demo",
    )
