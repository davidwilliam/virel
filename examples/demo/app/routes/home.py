"""Static landing page: ships with zero framework JavaScript (SPEC 9.3)."""

from virel import ui

from ..shared import shell


@ui.page("/", render="static")
def home() -> ui.Node:
    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Virel Phase 0 demo", level=1),
                ui.Text(
                    "Every page on this site is authored in typed Python and "
                    "compiled to browser-native HTML, CSS, and JavaScript.",
                    size="lg",
                ),
                ui.Text(
                    "This landing page is fully static: view source — there is "
                    "no framework JavaScript on this route.",
                    muted=True,
                ),
                ui.Row(
                    ui.Card(
                        ui.Heading("Local interaction", level=3),
                        ui.Text("The counter and search pages update the DOM "
                                "with fine-grained signals. No server round "
                                "trips.", muted=True),
                        ui.Link("Try the counter", to="/counter"),
                    ),
                    ui.Card(
                        ui.Heading("Server actions", level=3),
                        ui.Text("The invite form calls typed Python over "
                                "HTTP; the stream page renders incremental "
                                "output.", muted=True),
                        ui.Link("Send an invite", to="/invite"),
                    ),
                    ui.Card(
                        ui.Heading("Web standards", level=3),
                        ui.Text("Third-party web components integrate through "
                                "typed Python bindings.", muted=True),
                        ui.Link("See the widget", to="/widgets"),
                    ),
                    gap=4,
                    align="stretch",
                    wrap=True,
                ),
            ),
            theme_toggle=False,
        ),
        title="Virel Demo",
        meta={"description": "Virel Phase 0 demonstration application."},
    )
