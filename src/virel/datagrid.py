"""The data grid (SPEC 11.1 advanced components).

The grid server-renders every row, and the runtime enhances the real
DOM: sorting reorders rows, filtering hides them, selection tracks
checkboxes, and paging shows a window. No reactivity machinery is
involved, so the grid works on any page (including fully static ones)
and stays fast into the thousands of rows.
"""

from __future__ import annotations

import re
from typing import Any

from .expr import Handler, VirelCompileError
from .nodes import Element, Node, TextNode

_KINDS = ("text", "number", "date")


class Column:
    """One grid column: the row key it reads, its header label, and the
    kind that drives sorting and alignment."""

    def __init__(self, key: str, label: str, *, kind: str = "text",
                 align: str | None = None, sortable: bool = True) -> None:
        if kind not in _KINDS:
            raise VirelCompileError(
                f"Column kind must be one of {', '.join(_KINDS)}, "
                f"got {kind!r}.")
        if align not in (None, "start", "end"):
            raise VirelCompileError("Column align must be 'start' or 'end'.")
        self.key = key
        self.label = label
        self.kind = kind
        self.align = align or ("end" if kind == "number" else "start")
        self.sortable = sortable


def DataGrid(rows: Any, *, columns: list[Column] | None = None,
             key: str | None = None, caption: str | None = None,
             filterable: bool = False, page_size: int | None = None,
             selectable: bool = False,
             on_selection: Any = None) -> Element:
    """A data grid over plain rows:

        ui.DataGrid(runs, columns=[
            ui.Column("model", "Model"),
            ui.Column("score", "Score", kind="number"),
            ui.Column("started", "Started", kind="date"),
        ], key="model", filterable=True, page_size=10, selectable=True,
        on_selection=ui.set_from_event(chosen, "detail.keys"))

    Column headers sort (ascending, descending, original), filterable=
    adds a search box over all cells, page_size= pages the rows client
    side, and selectable= adds a checkbox column with select-all; the
    grid dispatches virel-selection with the selected row keys."""
    from .data import infer_columns, records
    rows = records(rows)
    if columns is None:
        columns = infer_columns(rows)
    if not columns:
        raise VirelCompileError("DataGrid needs at least one Column.")
    for column in columns:
        if not isinstance(column, Column):
            raise VirelCompileError(
                "DataGrid columns take ui.Column(...) entries.")
    if selectable and key is None:
        raise VirelCompileError(
            "DataGrid(selectable=True) requires key= naming the column "
            "that identifies a row.")
    if page_size is not None and (not isinstance(page_size, int)
                                  or page_size < 1):
        raise VirelCompileError("page_size must be a positive int.")
    if on_selection is not None and not isinstance(on_selection, Handler):
        raise VirelCompileError(
            "on_selection takes a handler, typically "
            'ui.set_from_event(state, "detail.keys").')

    header_cells: list[Node] = []
    if selectable:
        header_cells.append(Element("th", [Element("input", attrs={
            "type": "checkbox",
            "class": "v-grid-check v-grid-check-all",
            "aria-label": "Select all rows",
        })], attrs={"scope": "col", "class": "v-grid-selcol"}))
    for column in columns:
        label: Node = TextNode(column.label)
        if column.sortable:
            label = Element(
                "button", [TextNode(column.label)],
                attrs={"type": "button", "class": "v-grid-sort"})
        header_cells.append(Element("th", [label], attrs={
            "scope": "col",
            "data-key": column.key,
            "data-kind": column.kind,
            "aria-sort": "none" if column.sortable else None,
            "class": f"v-grid-align-{column.align}",
        }))

    body_rows: list[Node] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise VirelCompileError(
                f"DataGrid row {index} is not a dict: {row!r}.")
        cells: list[Node] = []
        if selectable:
            row_key = str(row.get(key, index))
            cells.append(Element("td", [Element("input", attrs={
                "type": "checkbox",
                "class": "v-grid-check v-grid-check-row",
                "aria-label": f"Select row {row_key}",
            })], attrs={"class": "v-grid-selcol"}))
        for column in columns:
            value = row.get(column.key, "")
            cells.append(Element(
                "td", [TextNode(str(value))],
                attrs={"data-value": _sortable_value(value, column.kind),
                       "class": f"v-grid-align-{column.align}"}))
        attrs = {"data-index": str(index)}
        if key is not None:
            attrs["data-key"] = str(row.get(key, index))
        body_rows.append(Element("tr", cells, attrs=attrs))

    table_children: list[Node] = []
    if caption:
        table_children.append(Element("caption", [TextNode(caption)]))
    table_children.append(Element("thead", [Element("tr", header_cells)]))
    table_children.append(Element("tbody", body_rows))
    table = Element("div", [Element(
        "table", table_children, attrs={"class": "v-table v-grid-table"})],
        attrs={"class": "v-table-wrap"})

    chrome: list[Node] = []
    toolbar: list[Node] = []
    if filterable:
        toolbar.append(Element("input", attrs={
            "type": "search",
            "class": "v-input v-grid-filter",
            "placeholder": "Filter rows…",
            "aria-label": "Filter rows",
        }))
    toolbar.append(Element("span", attrs={
        "class": "v-grid-count", "role": "status"}))
    chrome.append(Element("div", toolbar, attrs={"class": "v-grid-toolbar"}))
    chrome.append(table)
    if page_size is not None:
        chrome.append(Element("div", [
            Element("button", [TextNode("Previous")], attrs={
                "type": "button", "class": "v-page-link v-grid-prev"}),
            Element("span", attrs={"class": "v-grid-pages"}),
            Element("button", [TextNode("Next")], attrs={
                "type": "button", "class": "v-page-link v-grid-next"}),
        ], attrs={"class": "v-grid-pager"}))

    events = {}
    if on_selection is not None:
        events["virel-selection"] = on_selection
    return Element("div", chrome,
                   attrs={"class": "v-datagrid",
                          "data-page-size": str(page_size or 0)},
                   events=events,
                   runtime_binding="datagrid")


def _sortable_value(value: Any, kind: str) -> str:
    """The comparison value carried on each cell. Numbers and dates get
    a machine-sortable form; text sorts by its casefolded content."""
    if kind == "number":
        try:
            return f"{float(value):.10f}"
        except (TypeError, ValueError):
            return ""
    if kind == "date":
        text = str(value)
        if not re.fullmatch(r"[0-9T:.\-+Z ]*", text):
            return ""
        return text
    return str(value).casefold()
