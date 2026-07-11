"""Gallery of the component library. Everything here is client-local."""

from virel import ui

from ..shared import shell


def _forms_tab() -> ui.Node:
    notes = ui.state("")
    volume = ui.state(40)
    plan = ui.state("starter")
    notify = ui.state(True)
    seats = ui.state(3)

    return ui.Stack(
        ui.Row(
            ui.Stack(
                ui.Textarea(notes, label="Notes", placeholder="Anything worth recording…"),
                ui.NumberField(seats, label="Seats", min=1, max=50),
                gap=4,
            ),
            ui.Stack(
                ui.Slider(volume, label="Volume", min=0, max=100),
                ui.Progress(volume, max=100, label="Volume level"),
                ui.Switch(notify, label="Email notifications"),
                ui.When(notify, then=ui.Badge("subscribed", intent="primary"),
                        otherwise=ui.Badge("muted")),
                gap=4,
            ),
            gap=8,
            align="start",
        ),
        ui.RadioGroup(plan, label="Plan", options=["starter", "team", "enterprise"]),
        ui.Text(f"Selected plan: {plan}", muted=True),
        gap=6,
    )


def _data_tab() -> ui.Node:
    return ui.Stack(
        ui.Row(
            ui.Stat(label="Runs", value="1,284", hint="last 30 days"),
            ui.Stat(label="Pass rate", value="97.2%"),
            ui.Stat(label="P95 latency", value="341 ms"),
            gap=10,
        ),
        ui.Table(
            columns=["Model", "Dataset", "Score", "Status"],
            rows=[
                ["atlas-small", "qa-hard-v2", "0.87", ui.Badge("passed", intent="primary")],
                ["atlas-large", "qa-hard-v2", "0.93", ui.Badge("passed", intent="primary")],
                ["baseline", "qa-hard-v2", "0.71", ui.Badge("regression", intent="danger")],
            ],
            caption="Latest evaluation runs",
        ),
        ui.Row(
            ui.Avatar("Ada Lovelace"),
            ui.Avatar("Grace Hopper"),
            ui.Avatar("Alan Turing"),
            ui.Spinner(label="Loading more"),
            gap=3,
        ),
        ui.Skeleton(lines=3),
        gap=6,
    )


def _patterns_tab() -> ui.Node:
    dialog_open = ui.state(False)

    return ui.Stack(
        ui.Breadcrumbs([("Home", "/"), ("Components", "/components"),
                        ("Patterns", None)]),
        ui.Row(
            ui.Button("Open dialog", intent="primary",
                      on_click=lambda: dialog_open.set(True)),
            ui.Tooltip(ui.Badge("hover me"), text="Tooltips are CSS-only"),
            gap=4,
        ),
        ui.Dialog(
            ui.Text("Dialogs use the native dialog element, so focus "
                    "trapping and the Escape key come from the browser."),
            ui.Row(
                ui.Button("Done", intent="primary",
                          on_click=lambda: dialog_open.set(False)),
                justify="end",
            ),
            open=dialog_open,
            title="Native dialog",
        ),
        ui.Accordion({
            "What renders this page?": ui.Text(
                "Typed Python, compiled to HTML and a small JS module."),
            "Where does state live?": ui.Text(
                "In the browser. The server holds no per-user objects."),
        }),
        ui.Row(
            *[ui.Tooltip(ui.Icon(name, size=18), text=name)
              for name in ["check", "x", "plus", "search", "star", "user",
                           "mail", "settings", "trash", "edit", "upload",
                           "download", "external-link", "alert-triangle"]],
            gap=3,
            wrap=True,
        ),
        gap=6,
    )


@ui.page("/components")
def components() -> ui.Node:
    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Component library", level=1),
                ui.Text("Every control below is authored in Python and "
                        "runs entirely in the browser.", muted=True),
                ui.Tabs({
                    "Forms": _forms_tab(),
                    "Data": _data_tab(),
                    "Patterns": _patterns_tab(),
                }, label="Component groups"),
            ),
        ),
        title="Components — Virel Demo",
    )
