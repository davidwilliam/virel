"""Gallery of the complete component library."""

from virel import ui

from ..shared import shell

_SNIPPET = '''form = ui.form(InviteInput, submit=invite_member)

ui.Form(
    ui.TextField(form.email, label="Email"),
    ui.Select(form.role, label="Role"),
    ui.FormActions(ui.SubmitButton("Send invitation", form=form)),
    form=form,
)'''


def _actions_tab() -> ui.Node:
    return ui.Stack(
        ui.Text("Buttons", muted=True, size="sm"),
        ui.Row(
            ui.Button("Primary", intent="primary"),
            ui.Button("Neutral"),
            ui.Button("Danger", intent="danger"),
            ui.Button("Disabled", intent="primary", disabled=True),
            ui.Button(ui.Icon("settings", label="Settings")),
            gap=3, wrap=True,
        ),
        ui.Row(
            ui.Button("Small", size="sm"),
            ui.Button("Medium", size="md"),
            ui.Button("Large", size="lg"),
            ui.LinkButton("Link button", to="/counter"),
            gap=3, wrap=True,
        ),
        ui.Text("Badges", muted=True, size="sm"),
        ui.Row(
            ui.Badge("neutral"),
            ui.Badge("primary", intent="primary"),
            ui.Badge("danger", intent="danger"),
            gap=3,
        ),
        ui.Text("Links", muted=True, size="sm"),
        ui.Row(
            ui.Link("Inline link", to="/"),
            ui.Link("External link", to="https://github.com/davidwilliam/virel",
                    external=True),
            gap=5,
        ),
        gap=4,
    )


def _forms_tab() -> ui.Node:
    email = ui.state("")
    role = ui.state("editor")
    notes = ui.state("")
    volume = ui.state(40)
    plan = ui.state("starter")
    notify = ui.state(True)
    terms = ui.state(False)
    seats = ui.state(3)

    return ui.Grid(
        ui.Stack(
            ui.TextField(email, label="Email", placeholder="person@example.com",
                         kind="email", description="Typed from the model."),
            ui.Select(role, label="Role", options=["viewer", "editor", "admin"]),
            ui.Textarea(notes, label="Notes", placeholder="Anything worth recording…"),
            ui.NumberField(seats, label="Seats", min=1, max=50),
            gap=4,
        ),
        ui.Stack(
            ui.Slider(volume, label="Volume", min=0, max=100),
            ui.Switch(notify, label="Email notifications"),
            ui.Checkbox(terms, label="Accept the terms"),
            ui.RadioGroup(plan, label="Plan",
                          options=["starter", "team", "enterprise"]),
            ui.Text(f"Selected plan: {plan}", muted=True, size="sm"),
            gap=4,
        ),
        columns={"base": 1, "md": 2},
        gap=8,
    )


def _data_tab() -> ui.Node:
    return ui.Stack(
        ui.Grid(
            ui.Stat(label="Runs", value="1,284", hint="last 30 days"),
            ui.Stat(label="Pass rate", value="97.2%"),
            ui.Stat(label="P95 latency", value="341 ms"),
            columns={"base": 1, "md": 3},
            gap=6,
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
        ui.Text("Syntax-highlighted code (compiled server-side, zero JS)",
                muted=True, size="sm"),
        ui.Code(_SNIPPET, block=True, language="python"),
        ui.Row(
            ui.Avatar("Ada Lovelace"),
            ui.Avatar("Grace Hopper"),
            ui.Avatar("Alan Turing"),
            gap=3,
        ),
        gap=6,
    )


def _feedback_tab() -> ui.Node:
    return ui.Stack(
        ui.Alert("Neutral status message.", intent="neutral"),
        ui.Alert("Something worth highlighting.", intent="primary"),
        ui.Alert("The run completed successfully.", intent="success"),
        ui.Alert("The deployment failed; check the logs.", intent="danger"),
        ui.Grid(
            ui.Stack(
                ui.Text("Loading", muted=True, size="sm"),
                ui.Row(ui.Spinner(), ui.Text("Fetching results…", muted=True),
                       gap=3),
                ui.Progress(64, max=100, label="Upload progress"),
                ui.Skeleton(lines=3),
                gap=4,
            ),
            ui.Stack(
                ui.Text("Empty state", muted=True, size="sm"),
                ui.EmptyState(title="No members yet",
                              description="Invite the first member to this "
                                          "workspace."),
                gap=4,
            ),
            columns={"base": 1, "md": 2},
            gap=8,
        ),
        gap=4,
    )


def _patterns_tab() -> ui.Node:
    dialog_open = ui.state(False)
    taps = ui.state(0)

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
        ui.Card(
            ui.Heading("Hydration island", level=3),
            ui.Text("This block server-renders like everything else, but its "
                    "JavaScript activates only when it scrolls into view.",
                    muted=True),
            ui.Island(
                ui.Row(
                    ui.Button("Tap", on_click=lambda: taps.update(lambda t: t + 1)),
                    ui.Text(f"Taps: {taps}"),
                    gap=4,
                ),
                load="visible",
            ),
            gap=3,
        ),
        gap=6,
    )


def _icons_tab() -> ui.Node:
    tiles = [
        ui.Stack(
            ui.Icon(name, size=20),
            ui.Text(name, muted=True, size="sm"),
            gap=2,
            align="center",
            class_name="v-card",
        )
        for name in ui.icon_names()
    ]
    return ui.Grid(*tiles, columns={"base": 2, "md": 4, "xl": 6}, gap=3)


@ui.page("/components")
def components() -> ui.Node:
    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("Component library", level=1),
                ui.Text("Every control below is authored in Python and "
                        "runs entirely in the browser.", muted=True),
                ui.Tabs({
                    "Actions": _actions_tab(),
                    "Forms": _forms_tab(),
                    "Data": _data_tab(),
                    "Feedback": _feedback_tab(),
                    "Patterns": _patterns_tab(),
                    "Icons": _icons_tab(),
                }, label="Component groups"),
            ),
        ),
        title="Components — Virel Demo",
    )
