"""The machine-readable component registry (SPEC 14.2).

Every component exposes a structured schema assembled from two sources:
the function signature (props, types, defaults, children) and curated
metadata (purpose, events, examples, accessibility contract,
incompatibilities, deprecations). ``virel schema <Name> --json`` is the
CLI face; agents and the MCP server read the same structures.
"""

from __future__ import annotations

import inspect
from typing import Any

from .expr import VirelCompileError

# Curated metadata. Components not listed still get a schema from their
# signature and docstring; entries here add what introspection cannot
# know. The accessibility text mirrors ACCESSIBILITY.md.
_CURATED: dict[str, dict[str, Any]] = {
    "Button": {
        "events": ["on_click"],
        "accessibility": "Native button; icon-only buttons require "
                         "aria_label= or Icon(label=).",
        "example": 'ui.Button("Save", on_click=lambda: saved.set(True), '
                   'intent="primary")',
    },
    "TextField": {
        "events": ["on input: writes target.value into the bound state"],
        "accessibility": "Label association is required and rendered as "
                         "a real label element.",
        "example": 'ui.TextField(email, label="Email", kind="email")',
    },
    "Textarea": {
        "accessibility": "Label association is required.",
        "example": 'ui.Textarea(notes, label="Notes", rows=4)',
    },
    "NumberField": {
        "accessibility": "Label required; renders a spinbutton.",
        "example": 'ui.NumberField(seats, label="Seats", min=1, max=50)',
    },
    "DateField": {
        "accessibility": "The platform calendar supplies localized, "
                         "accessible date entry.",
        "example": 'ui.DateField(due, label="Due date", min="2026-01-01")',
        "incompatibilities": ["kind must be date, time, or datetime; "
                              "min/max must match the ISO format"],
    },
    "Select": {
        "accessibility": "Enhanced combobox over a native select that "
                         "remains the source of truth; arrows, Enter, "
                         "Escape, type-ahead.",
        "example": 'ui.Select(role, label="Role", options=["viewer", '
                   '"editor"])',
    },
    "Listbox": {
        "events": ["virel-change (managed): selection writes into the "
                   "bound state"],
        "accessibility": "role=listbox with aria-activedescendant; "
                         "arrows move, Home/End jump, Enter/Space select.",
        "example": 'ui.Listbox(dataset, label="Dataset", options=[...], '
                   'multiple=False)',
    },
    "FilterChips": {
        "accessibility": "role=group; each chip carries aria-pressed.",
        "example": 'ui.FilterChips(facets, options=["passed", "failed"])',
    },
    "Checkbox": {"example": 'ui.Checkbox(terms, label="Accept the terms")'},
    "Switch": {"example": 'ui.Switch(notify, label="Email notifications")'},
    "RadioGroup": {
        "example": 'ui.RadioGroup(plan, label="Plan", options=["starter", '
                   '"team"])'},
    "Slider": {
        "accessibility": "Native range input; the live value renders "
                         "beside the label.",
        "example": 'ui.Slider(volume, label="Volume", min=0, max=100)',
    },
    "Tabs": {
        "slots": "A dict of tab label to panel content.",
        "accessibility": "role=tablist; arrows move between tabs; panels "
                         "stay in the document.",
        "example": 'ui.Tabs({"Overview": overview, "Settings": settings})',
    },
    "Dialog": {
        "accessibility": "Native dialog element: focus trapping, "
                         "restoration, and Escape come from the browser.",
        "example": 'ui.Dialog(content, open=dialog_open, title="Confirm")',
    },
    "Menu": {
        "slots": "trigger= any button-like element; items= MenuItem and "
                 "MenuDivider entries.",
        "accessibility": "role=menu; arrows move, Enter activates, Escape "
                         "closes and refocuses the trigger; flips upward "
                         "when space runs out.",
        "example": 'ui.Menu(trigger=ui.Button("Actions"), items=[...])',
    },
    "Popover": {
        "accessibility": "aria-expanded and aria-haspopup on the trigger; "
                         "focus moves in on open and restores on close.",
        "example": "ui.Popover(trigger=ui.Button(\"Details\"), "
                   "content=panel)",
    },
    "Tooltip": {
        "accessibility": "CSS-only; appears on focus as well as hover.",
        "example": 'ui.Tooltip(ui.Badge("beta"), text="Ships next month")',
    },
    "Accordion": {
        "slots": "A dict of summary label to disclosure content.",
        "accessibility": "Native details/summary.",
        "example": 'ui.Accordion({"What is this?": ui.Text("...")})',
    },
    "Tree": {
        "events": ["on_select(node): traced per node"],
        "accessibility": "The ARIA tree pattern: roving tabindex, arrows "
                         "move and expand/collapse, Enter selects.",
        "example": 'ui.Tree(folders, label=lambda n: n["name"], '
                   'on_select=lambda n: picked.set(n["name"]))',
    },
    "CommandPalette": {
        "accessibility": "Combobox over a listbox in a native dialog; "
                         "Ctrl/Cmd+letter opens, typing filters, arrows "
                         "move, Enter runs.",
        "example": "ui.CommandPalette(commands=[ui.Command(\"Home\", "
                   "to=\"/\")])",
    },
    "Pagination": {
        "accessibility": "nav with aria-label; aria-current=page on the "
                         "active page; edges disabled.",
        "example": "ui.Pagination(page, 12)  # or href= for server mode",
        "incompatibilities": ["href= mode takes the current page as an "
                              "int, not a state"],
    },
    "DataGrid": {
        "events": ["virel-selection {keys}", "virel-edit {key, column, "
                   "value}"],
        "accessibility": "aria-sort per sortable column; tri-state "
                         "select-all; arrow keys move cell focus; Enter "
                         "edits editable cells.",
        "example": 'ui.DataGrid(rows, key="id", filterable=True, '
                   'page_size=20)',
        "incompatibilities": [
            "group_by cannot combine with virtual=True",
            "server= cannot combine with virtual= or stream=",
            "editable columns and stream= require key=",
        ],
    },
    "Chart": {
        "accessibility": "role=img with a text summary; every point "
                         "carries a title element.",
        "example": 'ui.Chart("line", [ui.Series("Score", points=[71, 88])],'
                   ' labels=["Q1", "Q2"])',
    },
    "Figure": {
        "accessibility": "label= is required and becomes role=img with "
                         "aria-label plus an embedded title.",
        "example": "ui.Figure(fig, label=\"Latency\", export=True)",
    },
    "Each": {
        "events": ["per-item handlers with (ev, item)",
                   "virel-reorder {items} when reorderable"],
        "accessibility": "reorderable=True adds keyboard drag handles "
                         "with announced moves.",
        "example": 'ui.Each(tasks, render=row, key=lambda t: t["id"], '
                   'animate="fade", reorderable=True)',
        "incompatibilities": ["reorderable=True requires key="],
    },
    "When": {
        "example": 'ui.When(ready, then=panel, otherwise=spinner, '
                   'animate=ui.Motion(enter="fade-up", exit="fade"))',
    },
    "Island": {
        "example": 'ui.Island(comments, load="visible")',
    },
    "FileField": {
        "accessibility": "A labeled drop zone that also accepts dragged "
                         "files.",
        "example": 'files = ui.FileField(label="Attachments", '
                   'multiple=True)',
    },
    "Swipeable": {
        "events": ["virel-dismiss via on_dismiss="],
        "accessibility": "Focusable; Delete/Backspace dismiss from the "
                         "keyboard.",
        "example": "ui.Swipeable(card, on_dismiss=lambda: "
                   "gone.set(True))",
    },
    "Tour": {
        "events": ["virel-close: writes the open state back to False"],
        "accessibility": "role=dialog card; Escape closes; focus returns "
                         "on close.",
        "example": 'ui.Tour(steps=[ui.TourStep(".v-datagrid", "Grid", '
                   '"Sort here.")], open=touring)',
    },
    "Video": {
        "accessibility": "label= required; captions= takes a WebVTT "
                         "track; no autoplay by design.",
        "example": 'ui.Video("/public/demo.mp4", label="Release demo", '
                   'captions="/public/demo.vtt")',
    },
    "Audio": {
        "accessibility": "label= required.",
        "example": 'ui.Audio("/public/talk.mp3", label="Episode 4")',
    },
    "Image": {
        "accessibility": "alt is a required parameter.",
        "example": 'ui.Image("/public/logo.png", "Company logo")',
    },
    "Heading": {
        "accessibility": "level= is the document outline; size= decouples "
                         "visual scale so the outline stays correct.",
        "example": 'ui.Heading("Billing", level=2, size=3)',
    },
    "Splitter": {
        "accessibility": "role=separator with aria-valuenow; arrows move, "
                         "Home/End snap, double-click resets.",
        "example": "ui.Splitter(nav, editor, initial=30)",
    },
    "Box": {
        "example": 'ui.Box(chart, css={"container-type": "inline-size"})',
    },
    "Table": {
        "example": 'ui.Table(columns=["Name", "Score"], rows=[["a", 1]])',
    },
    "Progress": {
        "accessibility": "Native progress element; label= required.",
        "example": 'ui.Progress(percent, max=100, label="Upload")',
    },
}

_DEPRECATIONS: dict[str, str] = {}


# Uppercase callables in these modules that are not components.
_NON_COMPONENTS = {
    "Any", "Callable", "Element", "Node", "PageNode", "RawHTML", "TextNode",
    "When", "Expr", "Handler", "State", "SetOp", "SetFromEventOp",
    "VirelCompileError", "Series", "Column", "GridQuery", "Path",
}


def _is_component(module, name: str) -> bool:
    if name in _NON_COMPONENTS or name.startswith("_"):
        return False
    fn = getattr(module, name, None)
    if fn is None or not callable(fn):
        return False
    if isinstance(fn, type) and issubclass(fn, BaseException):
        return False
    # Components are functions defined in these modules, not imports.
    return getattr(fn, "__module__", "").startswith("virel.")


def list_components() -> list[str]:
    from . import charts, datagrid, elements, viz
    names: list[str] = []
    for module in (elements, datagrid, charts, viz):
        for name in dir(module):
            if name[0].isupper() and _is_component(module, name) \
                    and name not in names:
                names.append(name)
    return sorted(set(names))


def _resolve(name: str):
    from . import charts, datagrid, elements, viz
    for module in (elements, datagrid, charts, viz):
        fn = getattr(module, name, None)
        if fn is not None and callable(fn):
            return fn
    return None


def component_schema(name: str) -> dict[str, Any]:
    """The full structured schema for one component (SPEC 14.2)."""
    fn = _resolve(name)
    if fn is None:
        raise VirelCompileError(
            f"Unknown component {name!r}. `virel schema --list` names "
            "every component.")
    curated = _CURATED.get(name, {})
    signature = inspect.signature(fn)
    doc = inspect.getdoc(fn) or ""
    props: dict[str, Any] = {}
    accepts_children = False
    for param in signature.parameters.values():
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            accepts_children = True
            continue
        annotation = param.annotation
        props[param.name] = {
            "type": (annotation if isinstance(annotation, str)
                     else getattr(annotation, "__name__", str(annotation))),
            "default": (None if param.default is inspect.Parameter.empty
                        else repr(param.default)),
            "required": param.default is inspect.Parameter.empty,
        }
    return {
        "name": name,
        "import": "from virel import ui",
        "usage": f"ui.{name}(...)",
        "purpose": curated.get("purpose")
        or (doc.split("\n\n")[0].replace("\n", " ") if doc else ""),
        "props": props,
        "children": curated.get(
            "slots", "*children" if accepts_children else None),
        "events": curated.get("events", []),
        "example": curated.get("example"),
        "accessibility": curated.get("accessibility"),
        "incompatibilities": curated.get("incompatibilities", []),
        "deprecated": _DEPRECATIONS.get(name),
    }
