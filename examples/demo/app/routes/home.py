"""Landing page: fully static, no framework JavaScript modules."""

from virel import ui

from ..shared import shell

_SNIPPET = '''@ui.page("/")
def home() -> ui.Node:
    count = ui.state(0)
    return ui.Page(
        ui.Heading(f"Count: {count}", level=1),
        ui.Button("Increment",
                  on_click=lambda: count.update(lambda c: c + 1)),
    )'''


def _feature(icon: str, title: str, text: str, link_text: str,
             to: str) -> ui.Node:
    return ui.Card(
        ui.Row(ui.Icon(icon, size=20), ui.Heading(title, level=3), gap=3),
        ui.Text(text, muted=True),
        ui.Spacer(),
        ui.Link(link_text, to=to),
        gap=3,
    )


@ui.page("/", render="static")
def home() -> ui.Node:
    return ui.Page(
        shell(
            ui.Section(
                ui.Hero(
                    eyebrow=ui.Badge("Developer preview", intent="primary"),
                    title="Professional interfaces, written in Python",
                    subtitle="Typed, declarative Python in; fast, accessible, "
                             "browser-native HTML, CSS, and JavaScript out. "
                             "No Node.js, no second language, no virtual DOM.",
                    actions=[
                        ui.LinkButton("Explore the components",
                                      to="/components", intent="primary",
                                      size="lg"),
                        ui.LinkButton("See live data", to="/runs", size="lg"),
                    ],
                    media=ui.Code(_SNIPPET, block=True, language="python"),
                ),
                ui.Grid(
                    _feature("play", "Local interaction",
                             "State lives in the browser. Clicking a button "
                             "updates exactly the DOM nodes that depend on "
                             "it, with no server round trip.",
                             "Try the counter", "/counter"),
                    _feature("upload", "Typed server actions",
                             "Forms and data calls are plain HTTP with "
                             "schema validation on every request. Streaming "
                             "output renders incrementally.",
                             "Send an invite", "/invite"),
                    _feature("square", "Web standards",
                             "Third-party web components bind through typed "
                             "Python generated from their manifests. The "
                             "output is inspectable, standard markup.",
                             "See the widget", "/widgets"),
                    columns={"base": 1, "md": 3},
                    gap=4,
                ),
                ui.Text(
                    "This landing page is a static route: the content and "
                    "the highlighted snippet above are plain server-rendered "
                    "HTML. View source.",
                    muted=True, size="sm"),
                gap=10,
            ),
        ),
        title="Virel Demo",
        meta={"description": "Virel demonstration application."},
    )
