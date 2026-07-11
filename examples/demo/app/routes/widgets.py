"""Third-party web components integrated through typed bindings
(SPEC 13.1). All three elements are plain vanilla custom elements (see
public/); their bindings are generated from custom elements manifests:

    virel bind star-rating.manifest.json \
        --module /public/star-rating.js --out app/bindings.py
    virel bind widgets.manifest.json \
        --module /public/widgets.js --out app/widgets_bindings.py
"""

import datetime

from virel import ui

from ..bindings import StarRating
from ..shared import shell
from ..widgets_bindings import RelativeTime, SparkLine

_STEADY = "12,14,13,15,16,15,17,18,17,19"
_VOLATILE = "12,18,9,21,7,19,11,23,8,20"


@ui.page("/widgets")
def widgets() -> ui.Node:
    rating = ui.state(3)
    series = ui.state(_STEADY)
    loaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Web component bindings", level=1),
                ui.Text("Each element below is a vanilla custom element with "
                        "no Virel code inside; typed Python bindings are "
                        "generated from their manifests, and data flows "
                        "through standard attributes and events.",
                        muted=True),
                ui.Grid(
                    ui.Card(
                        ui.Heading("Events out", level=3),
                        ui.Text("star-rating dispatches rating-changed; the "
                                "handler writes the detail into state.",
                                muted=True, size="sm"),
                        StarRating(
                            value=rating,
                            max=5,
                            on_rating_changed=ui.set_from_event(
                                rating, "detail.value"),
                        ),
                        ui.Text(f"Python-side state sees: {rating} / 5"),
                        ui.Row(
                            ui.Button("Set to 5",
                                      on_click=lambda: rating.set(5)),
                            ui.Button("Clear",
                                      on_click=lambda: rating.set(0)),
                            gap=3,
                        ),
                        gap=3,
                    ),
                    ui.Card(
                        ui.Heading("Reactive attributes in", level=3),
                        ui.Text("spark-line re-renders whenever its bound "
                                "values attribute changes.",
                                muted=True, size="sm"),
                        SparkLine(values=series, stroke="#4f46e5"),
                        ui.Row(
                            ui.Button("Steady",
                                      on_click=lambda: series.set(_STEADY)),
                            ui.Button("Volatile",
                                      on_click=lambda: series.set(_VOLATILE)),
                            gap=3,
                        ),
                        gap=3,
                    ),
                    ui.Card(
                        ui.Heading("Self-contained display", level=3),
                        ui.Text("relative-time keeps itself current with no "
                                "help from the framework.",
                                muted=True, size="sm"),
                        ui.Row(
                            ui.Text("Page rendered:", muted=True),
                            RelativeTime(datetime=loaded_at),
                            gap=2,
                        ),
                        gap=3,
                    ),
                    columns={"base": 1, "md": 3},
                    gap=5,
                ),
            ),
        ),
        title="Widgets — Virel Demo",
    )
