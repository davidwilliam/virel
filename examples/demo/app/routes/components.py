"""Gallery of the complete component library."""

from virel import ui

from ..shared import shell

# Raw CSS escape hatch (SPEC 10.5): rules the typed API cannot express,
# like pseudo-elements, live in ui.use_css and ship inside app.css.
ui.use_css("""
.demo-corner { position: relative; }
.demo-corner::after {
  content: "";
  position: absolute;
  right: 0; bottom: 0;
  width: 22px; height: 22px;
  background: var(--v-accent);
  clip-path: polygon(100% 0, 100% 100%, 0 100%);
  border-radius: 0 0 10px 0;
  opacity: 0.45;
}
""")

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
    due = ui.state("2026-07-15")
    dataset = ui.state("qa-hard-v2")
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
            ui.DateField(due, label="Due date", min="2026-01-01",
                         description="The platform calendar, no JS shipped."),
            ui.Listbox(dataset, label="Dataset",
                       options=["qa-hard-v2", "summarize-v1", "extract-v3"]),
            ui.Text(f"Evaluating against {dataset}", muted=True, size="sm"),
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


import dataclasses as _dataclasses
import datetime as _datetime


@_dataclasses.dataclass
class _RunRecord:
    """Rows reach the grid as typed records (SPEC 12.1): dataclasses,
    Pydantic models, TypedDicts, and DataFrames all normalize the same
    way through ui.records."""
    model: str
    dataset: str
    score: float
    started: _datetime.date


_RUN_ROWS = [
    _RunRecord(name, ds, score, _datetime.date.fromisoformat(day))
    for name, ds, score, day in [
        ("atlas-large", "qa-hard-v2", 0.93, "2026-07-10"),
        ("atlas-small", "qa-hard-v2", 0.87, "2026-07-11"),
        ("baseline", "qa-hard-v2", 0.71, "2026-07-08"),
        ("atlas-large", "summarize-v1", 0.89, "2026-07-09"),
        ("atlas-small", "summarize-v1", 0.83, "2026-07-09"),
        ("baseline", "summarize-v1", 0.64, "2026-07-07"),
        ("atlas-large", "extract-v3", 0.95, "2026-07-12"),
        ("atlas-small", "extract-v3", 0.90, "2026-07-12"),
        ("baseline", "extract-v3", 0.77, "2026-07-06"),
        ("atlas-large", "reasoning-v2", 0.81, "2026-07-11"),
        ("atlas-small", "reasoning-v2", 0.74, "2026-07-10"),
        ("baseline", "reasoning-v2", 0.58, "2026-07-05"),
    ]
]


def _data_tab() -> ui.Node:
    chosen = ui.state([])
    facets = ui.state(["passed"])
    touring = ui.state(False)
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
        ui.Card(
            ui.Heading("Data grid", level=2, size=3),
            ui.Text("Click a header to sort (ascending, descending, back "
                    "to original), filter across all cells, select rows, "
                    "and page through the results.", muted=True, size="sm"),
            ui.DataGrid(
                _RUN_ROWS,
                columns=[
                    ui.Column("model", "Model"),
                    ui.Column("dataset", "Dataset"),
                    ui.Column("score", "Score", kind="number"),
                    ui.Column("started", "Started", kind="date"),
                ],
                key="model",
                filterable=True,
                page_size=6,
                selectable=True,
                on_selection=ui.set_from_event(chosen, "detail.keys"),
            ),
            ui.Text(f"Selected rows: {ui.length(chosen)}", muted=True,
                    size="sm"),
            gap=3,
        ),
        ui.Grid(
            ui.Card(
                ui.Heading("Charts", level=2, size=3),
                ui.Text("Compiled to themed inline SVG: zero JavaScript, "
                        "brand and dark-mode aware, every point titled.",
                        muted=True, size="sm"),
                ui.Chart("line", [
                    ui.Series("atlas-large", points=[78, 83, 86, 89, 93]),
                    ui.Series("baseline", points=[62, 64, 61, 68, 71]),
                ], labels=["Mar", "Apr", "May", "Jun", "Jul"]),
                gap=3,
                class_name="demo-tour-chart",
            ),
            ui.Card(
                ui.Heading("Donut and filters", level=2, size=3),
                ui.Chart("donut", [
                    ui.Series("Passed", value=118),
                    ui.Series("Flaky", value=7),
                    ui.Series("Failed", value=3),
                ], height=170),
                ui.FilterChips(facets,
                               options=["passed", "flaky", "failed"]),
                ui.Text(f"Facets on: {ui.length(facets)}", muted=True,
                        size="sm"),
                gap=3,
                class_name="demo-tour-chips",
            ),
            columns={"base": 1, "md": 2},
            gap=5,
        ),
        ui.Row(
            ui.Button("Take the tour", intent="primary",
                      on_click=lambda: touring.set(True)),
            gap=3,
        ),
        ui.Tour(steps=[
            ui.TourStep(".v-datagrid", "The data grid",
                        "Sort with the headers, filter across every "
                        "cell, select rows, and page through results."),
            ui.TourStep(".demo-tour-chart", "Charts",
                        "Inline SVG compiled from Python. No chart "
                        "library ships to the browser."),
            ui.TourStep(".demo-tour-chips", "Filter chips",
                        "Toggle facets; the selection lands in Python "
                        "state like every other control."),
        ], open=touring),
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
        ui.Text("Toast notifications", muted=True, size="sm"),
        ui.Row(
            ui.Button("Notify", size="sm",
                      on_click=lambda: ui.notify("Report generated.")),
            ui.Button("Success", size="sm",
                      on_click=lambda: ui.notify("Deployment complete.",
                                                 intent="success")),
            ui.Button("Danger", size="sm",
                      on_click=lambda: ui.notify("The run failed; check "
                                                 "the logs.",
                                                 intent="danger")),
            gap=3, wrap=True,
        ),
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


_FILES = [
    {"name": "src", "children": [
        {"name": "app.py"},
        {"name": "routes", "children": [
            {"name": "home.py"}, {"name": "runs.py"}]},
    ]},
    {"name": "tests", "children": [{"name": "test_app.py"}]},
    {"name": "README.md"},
]


def _patterns_tab() -> ui.Node:
    dialog_open = ui.state(False)
    current_page = ui.state(1)
    picked = ui.state("nothing yet")
    taps = ui.state(0)

    return ui.Stack(
        ui.Breadcrumbs([("Home", "/"), ("Components", "/components"),
                        ("Patterns", None)]),
        ui.Row(
            ui.Button("Open dialog", intent="primary",
                      on_click=lambda: dialog_open.set(True)),
            ui.Popover(
                trigger=ui.Button("Popover"),
                content=ui.Stack(
                    ui.Heading("Anchored panel", level=2, size=4),
                    ui.Text("Escape or a click outside closes this and "
                            "returns focus to the trigger.",
                            muted=True, size="sm"),
                    gap=2,
                ),
            ),
            ui.Tooltip(ui.Badge("hover me"), text="Tooltips are CSS-only"),
            gap=4,
        ),
        ui.Grid(
            ui.Card(
                ui.Heading("Tree view", level=2, size=3),
                ui.Text("Arrow keys move, expand, and collapse; Enter "
                        "selects.", muted=True, size="sm"),
                ui.Tree(_FILES,
                        label=lambda n: n["name"],
                        on_select=lambda n: picked.set(n["name"]),
                        aria_label="Project files"),
                ui.Text(f"Selected: {picked}", muted=True, size="sm"),
                gap=3,
            ),
            ui.Card(
                ui.Heading("Command palette", level=2, size=3),
                ui.Text("Press Ctrl or Cmd plus K anywhere on this page: "
                        "type to filter, arrows to move, Enter to run.",
                        muted=True, size="sm"),
                ui.CommandPalette(commands=[
                    ui.Command("Go to settings", to="/settings",
                               hint="Navigation"),
                    ui.Command("Go to runs", to="/runs", hint="Navigation"),
                    ui.Command("Open the dialog",
                               on_run=lambda: dialog_open.set(True)),
                    ui.Command("Raise a toast",
                               on_run=lambda: ui.notify(
                                   "Ran from the palette.",
                                   intent="success")),
                ]),
                ui.Code('ui.CommandPalette(commands=[ui.Command(...)])',
                        block=True, language="python"),
                gap=3,
            ),
            columns={"base": 1, "md": 2},
            gap=5,
        ),
        ui.Card(
            ui.Heading("Pagination", level=2, size=3),
            ui.Text("State-driven page controls; disabled edges, "
                    "aria-current on the active page.",
                    muted=True, size="sm"),
            ui.Pagination(current_page, 5, label="Demo pages"),
            ui.Text(f"Showing page {current_page} of 5", muted=True,
                    size="sm"),
            gap=3,
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
            ui.Heading("Error boundary", level=2, size=3),
            ui.Text("The left panel renders cleanly; the right panel's "
                    "content fails, so its fallback renders instead of a "
                    "broken region.", muted=True),
            ui.Grid(
                ui.ErrorBoundary(ui.Alert("This subtree bound cleanly.",
                                          intent="success")),
                ui.ErrorBoundary(_broken_panel()),
                columns={"base": 1, "md": 2},
                gap=4,
            ),
            gap=3,
        ),
        ui.Card(
            ui.Heading("Hydration island", level=2, size=3),
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


def _broken_panel() -> ui.Node:
    # length of null throws in the browser at bind time, on purpose.
    broken = ui.state(None)
    return ui.Text(ui.length(broken))


def _layout_tab() -> ui.Node:
    lorem = ("Composable layout primitives cover the space between a "
             "single flex row and a full app shell. ")
    last_action = ui.state("")
    return ui.Stack(
        ui.Card(
            ui.Heading("Splitter", level=2, size=3),
            ui.Text("Drag the divider, or focus it and use the arrow "
                    "keys; double-click resets.", muted=True, size="sm"),
            ui.Splitter(
                ui.Stack(ui.Heading("Navigator", level=3, size=4),
                         ui.Text(lorem, muted=True, size="sm"), gap=2),
                ui.Stack(ui.Heading("Editor", level=3, size=4),
                         ui.Text(lorem * 3, muted=True, size="sm"), gap=2),
                initial=35, min_size=20, max_size=70,
            ),
            gap=3,
        ),
        ui.Card(
            ui.Heading("Sidebar pattern", level=2, size=3),
            ui.Text("The aside keeps its width while the content stays "
                    "fluid; both stack when space runs out, with no media "
                    "query.", muted=True, size="sm"),
            ui.Sidebar(
                ui.Card(ui.Text("Aside", size="sm"), gap=2),
                ui.Card(ui.Text(lorem * 2, muted=True, size="sm"), gap=2),
                width="12rem", gap=4,
            ),
            gap=3,
        ),
        ui.Grid(
            ui.Card(
                ui.Heading("Center", level=2, size=3),
                ui.Center(ui.Badge("Centered on both axes",
                                   intent="primary"),
                          min_height="8rem"),
                gap=3,
            ),
            ui.Card(
                ui.Heading("AspectRatio", level=2, size=3),
                ui.AspectRatio(
                    ui.Box(
                        ui.Icon("play", size=28),
                        css={"display": "grid", "place-items": "center",
                             "background": "var(--v-accent-soft)",
                             "color": "var(--v-accent)",
                             "border-radius": "10px"},
                    ),
                    ratio="16/9",
                ),
                gap=3,
            ),
            ui.Card(
                ui.Heading("Resizable", level=2, size=3),
                ui.Resizable(
                    ui.Text("Drag the corner to resize this box.",
                            muted=True, size="sm"),
                ),
                gap=3,
            ),
            columns={"base": 1, "md": 3},
            gap=5,
        ),
        ui.Grid(
            ui.Card(
                ui.Heading("ScrollArea", level=2, size=3),
                ui.ScrollArea(
                    ui.Stack(*[ui.Text(f"Row {i + 1}", size="sm")
                               for i in range(20)], gap=2),
                    max_height="10rem",
                ),
                gap=3,
            ),
            ui.Card(
                ui.Heading("Wrap and Cluster", level=2, size=3),
                ui.Wrap(*[ui.Badge(name) for name in
                          ("alpha", "bravo", "charlie", "delta", "echo",
                           "foxtrot", "golf", "hotel")], gap=2),
                ui.Cluster(
                    ui.Button("Save", intent="primary", size="sm",
                              on_click=lambda: last_action.set("Saved")),
                    ui.Button("Preview", size="sm",
                              on_click=lambda: last_action.set(
                                  "Preview opened")),
                    ui.Button("Discard", emphasis="ghost", size="sm",
                              on_click=lambda: last_action.set(
                                  "Draft discarded")),
                    ui.When(last_action != "",
                            then=ui.Badge(last_action, intent="primary")),
                    gap=2,
                ),
                gap=4,
            ),
            columns={"base": 1, "md": 2},
            gap=5,
        ),
        gap=6,
    )


_ProjectCard = ui.recipe(
    base=ui.Card,
    variants={"status": {
        "active": {"border": "accent"},
        "paused": {"background": "surface.2"},
        "archived": {"background": "surface.2", "opacity": 0.65},
    }},
    defaults={"status": "active"},
)

_STATUS_INTENT = {"active": "primary", "paused": "neutral",
                  "archived": "neutral"}


def _status_card(name: str, status: str, blurb: str) -> ui.Node:
    return _ProjectCard(
        ui.Row(ui.Heading(name, level=3, size=4), ui.Spacer(),
               ui.Badge(status, intent=_STATUS_INTENT[status])),
        ui.Text(blurb, muted=True, size="sm"),
        status=status,
        gap=2,
    )


def _styling_tab() -> ui.Node:
    tile = ui.style(
        padding=4,
        radius="lg",
        background="surface.2",
        border="subtle",
        hover={"shadow": "md", "border": "accent", "background": "surface.1"},
    )
    return ui.Stack(
        ui.Card(
            ui.Heading("Style objects", level=2, size=3),
            ui.Text("ui.style() compiles typed properties to a shared "
                    "class: spacing in theme units, colors and shadows as "
                    "tokens, with hover, focus, and active variants. Hover "
                    "over a tile.", muted=True, size="sm"),
            ui.Wrap(
                *[ui.Box(ui.Text(label, size="sm"), class_name=tile)
                  for label in ("One style object", "Shared by every tile",
                                "Theme and density aware")],
                gap=3,
            ),
            ui.Code('tile = ui.style(padding=4, radius="lg", '
                    'background="surface.2",\n'
                    '                border="subtle", '
                    'hover={"shadow": "md", "border": "accent"})',
                    block=True, language="python"),
            gap=3,
        ),
        ui.Card(
            ui.Heading("Adaptive styles", level=2, size=3),
            ui.Text("This tile is a query container: drag the corner and "
                    "it restyles itself by its own width, not the "
                    "viewport. Styles can also vary by breakpoint and "
                    "pointer capability, and every tap target grows on "
                    "touch screens automatically.", muted=True, size="sm"),
            ui.Resizable(
                ui.Box(
                    ui.Text("Drag my corner past 24rem and I turn accent.",
                            size="sm"),
                    class_name=ui.style(
                        padding=4,
                        radius="md",
                        background="surface.2",
                        container_min={"24rem": {
                            "background": "accent.soft",
                            "border": "accent",
                        }},
                    ),
                ),
                direction="horizontal",
                class_name=ui.style(width="18rem", max_width="100%",
                                    container=True),
            ),
            ui.Code('panel = ui.style(container=True)  # the queried '
                    'ancestor\n'
                    'tile = ui.style(background="surface.2",\n'
                    '                container_min={"24rem": {"background": '
                    '"accent.soft"}})',
                    block=True, language="python"),
            gap=3,
        ),
        ui.Card(
            ui.Heading("Recipes", level=2, size=3),
            ui.Text("ui.recipe() defines a component with named variants; "
                    "each axis becomes a typed keyword argument.",
                    muted=True, size="sm"),
            ui.Grid(
                _status_card("Atlas", "active",
                             "Ingesting eval runs since March."),
                _status_card("Borealis", "paused",
                             "Waiting on the annotation batch."),
                _status_card("Cascade", "archived",
                             "Shipped and wound down in May."),
                columns={"base": 1, "md": 3},
                gap=4,
            ),
            ui.Code('ProjectCard = ui.recipe(base=ui.Card, variants={'
                    '"status": {...}})\n'
                    'ProjectCard(..., status="paused")',
                    block=True, language="python"),
            gap=3,
        ),
        ui.Card(
            ui.Heading("CSS escape hatch", level=2, size=3),
            ui.Text("Two levels below the typed API: ui.Box takes raw "
                    "inline declarations, and ui.use_css registers full "
                    "rules in app.css for what inline styles cannot say. "
                    "The accent corner below is a pseudo-element from a "
                    "ui.use_css rule.", muted=True, size="sm"),
            ui.Box(
                ui.Code("css={\"--stripe\": \"...\", "
                        "\"background\": \"...\"}"),
                class_name="demo-corner",
                css={
                    "--stripe": "var(--v-accent-soft)",
                    "background": ("repeating-linear-gradient(45deg, "
                                   "var(--stripe), var(--stripe) 12px, "
                                   "transparent 12px, transparent 24px)"),
                    "border": "1px dashed var(--v-border-strong)",
                    "border-radius": "10px",
                    "padding": "20px",
                },
            ),
            gap=3,
        ),
        gap=6,
    )


_PULSE = ui.keyframes({
    "0%": {"opacity": 1, "transform": "scale(1)"},
    "50%": {"opacity": 0.55, "transform": "scale(0.92)"},
    "100%": {"opacity": 1, "transform": "scale(1)"},
})

def _motion_tab() -> ui.Node:
    show = ui.state(True)
    tasks = ui.state(["Design review", "Ship the docs", "Triage inbox"])
    next_id = ui.state(4)
    note_visible = ui.state(True)

    def add_task():
        tasks.update(lambda xs: xs + [f"Task {next_id}"])
        next_id.update(lambda n: n + 1)

    def rotate_tasks():
        tasks.update(lambda xs: [xs[len(xs) - 1]] + xs)

    spring = ui.spring(stiffness=280, damping=14)
    springy = ui.style(
        padding=3, radius="md", background="accent.soft", color="accent",
        weight=600,
        transition=ui.transition("transform", easing=spring),
        hover={"transform": "translateY(-8px) scale(1.08)"},
    )
    live_dot = ui.style(
        width="10px", height="10px", radius="lg", background="success",
        animation=ui.animation(_PULSE, duration=1400, easing="in-out",
                               iterations="infinite", essential=True),
    )

    return ui.Stack(
        ui.Grid(
            ui.Card(
                ui.Heading("Enter and exit", level=2, size=3),
                ui.Text("ui.When with animate= runs enter and exit "
                        "animations as the condition flips.",
                        muted=True, size="sm"),
                ui.Row(
                    ui.Button("Toggle panel",
                              on_click=lambda: show.set(ui.not_(show))),
                    gap=3,
                ),
                ui.When(show,
                        then=ui.Alert("This panel fades and rises in, and "
                                      "fades away on exit.",
                                      intent="primary"),
                        animate=ui.Motion(enter="fade-up", exit="fade")),
                gap=3,
            ),
            ui.Card(
                ui.Heading("Springs, compiled", level=2, size=3),
                ui.Text("Spring physics simulated in Python at compile "
                        "time and emitted as a CSS linear() curve. Zero "
                        "JavaScript per frame. Hover the chip.",
                        muted=True, size="sm"),
                ui.Row(
                    ui.Box(ui.Text("Bouncy", size="sm"), class_name=springy,
                           css={"cursor": "default"}),
                    ui.Row(
                        ui.Box(class_name=live_dot),
                        ui.Text("Essential motion survives "
                                "reduced-motion.", muted=True, size="sm"),
                        gap=2,
                    ),
                    gap=5,
                ),
                ui.Code('ui.transition("transform", '
                        'easing=ui.spring(stiffness=280, damping=14))',
                        block=True, language="python"),
                gap=3,
            ),
            columns={"base": 1, "md": 2},
            gap=5,
        ),
        ui.Card(
            ui.Heading("List choreography", level=2, size=3),
            ui.Text("New items animate in, removed items animate out, and "
                    "layout=True FLIPs survivors to their new positions "
                    "when the list reorders. Drag the grip (or focus it "
                    "and press Space, arrows, Space) to reorder by hand.",
                    muted=True, size="sm"),
            ui.Row(
                ui.Button("Add task", intent="primary", size="sm",
                          on_click=add_task),
                ui.Button("Rotate", size="sm", on_click=rotate_tasks),
                gap=3,
            ),
            ui.Each(
                tasks,
                render=lambda task: ui.Card(ui.Text(task), gap=2),
                key=lambda task: task,
                gap=3,
                animate=ui.Motion(enter="slide-right", exit="fade",
                                  layout=True),
                reorderable=True,
            ),
            gap=4,
        ),
        ui.Card(
            ui.Heading("Gestures", level=2, size=3),
            ui.Text("Drag the note sideways past the threshold to dismiss "
                    "it (or focus it and press Delete). Below the "
                    "threshold it springs back.", muted=True, size="sm"),
            ui.When(
                note_visible,
                then=ui.Swipeable(
                    ui.Card(
                        ui.Row(
                            ui.Icon("info", size=16),
                            ui.Text("Swipe me away.", size="sm"),
                            gap=2,
                        ),
                        gap=2,
                    ),
                    on_dismiss=lambda: note_visible.set(False),
                ),
                otherwise=ui.Row(
                    ui.Text("Dismissed.", muted=True, size="sm"),
                    ui.Button("Bring it back", size="sm",
                              on_click=lambda: note_visible.set(True)),
                    gap=3,
                ),
                animate=ui.Motion(enter="fade-up", exit="fade",
                                  duration=180),
            ),
            gap=3,
        ),
        gap=6,
    )


def _icons_tab() -> ui.Node:
    tiles = [
        ui.Card(
            ui.Icon(name, size=20),
            ui.Text(name, muted=True, size="sm"),
            gap=2,
            align="center",
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
                    "Layout": _layout_tab(),
                    "Styling": _styling_tab(),
                    "Motion": _motion_tab(),
                    "Icons": _icons_tab(),
                }, label="Component groups"),
            ),
        ),
        title="Components — Virel Demo",
    )
