from pathlib import Path

from virel import ui

from . import routes  # noqa: F401  (importing registers pages and actions)

# Organization brands (SPEC 10.1): every built-in preset is available as
# a runtime-switchable brand from the settings page. "mono" is the black
# and white look; the accent flips to white in dark mode.
ui.use_theme(ui.Theme(brands={
    name: ui.Theme.preset(name)
    for name in ui.Theme.preset_names() if name != "indigo"
}))

# The widgets page binds to vanilla custom elements that stand in for an
# external JavaScript package; serve that package under /vendor/widgets.
ui.use_static("/vendor/widgets",
              Path(__file__).resolve().parents[2] / "third-party-widgets")
