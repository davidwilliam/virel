from pathlib import Path

from virel import ui

from . import routes  # noqa: F401  (importing registers pages and actions)

# Organization brands (SPEC 10.1): each derives its full palette from one
# base color and is switchable at runtime from the settings page.
ui.use_theme(ui.Theme(brands={
    "emerald": ui.Theme(color={"accent": "#059669"}),
    "amber": ui.Theme(color={"accent": "#f59e0b"}),
}))

# The widgets page binds to vanilla custom elements that stand in for an
# external JavaScript package; serve that package under /vendor/widgets.
ui.use_static("/vendor/widgets",
              Path(__file__).resolve().parents[2] / "third-party-widgets")
