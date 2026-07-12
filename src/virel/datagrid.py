"""The data grid (SPEC 11.1 advanced components, SPEC 12.2).

Two data modes share one component. In static mode every row is
server-rendered and the runtime enhances the real DOM: sorting reorders
rows, filtering hides them, groups collapse, cells edit in place. In
virtual mode (``virtual=True``) the rows travel as embedded JSON and
the runtime renders only the visible window, which handles very large
datasets and live streaming updates.

Server-side sorting, filtering, and paging use the server-rendering
idiom instead of JavaScript: pass ``server=ui.grid_query(...)`` from the
page's typed query parameters, and headers, the filter box, and the
pager become plain links and a GET form; ``ui.apply_grid_query`` orders
and slices the rows before they render.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from .expr import Handler, VirelCompileError
from .nodes import Element, Node, RawHTML, TextNode

_KINDS = ("text", "number", "date")
_AGGREGATES = ("count", "sum", "mean", "min", "max")


class Column:
    """One grid column: the row key it reads, its header label, the kind
    that drives sorting and alignment, and its behavior flags."""

    def __init__(self, key: str, label: str, *, kind: str = "text",
                 align: str | None = None, sortable: bool = True,
                 editable: bool = False,
                 pin: str | None = None) -> None:
        if kind not in _KINDS:
            raise VirelCompileError(
                f"Column kind must be one of {', '.join(_KINDS)}, "
                f"got {kind!r}.")
        if align not in (None, "start", "end"):
            raise VirelCompileError("Column align must be 'start' or 'end'.")
        if pin not in (None, "start", "end"):
            raise VirelCompileError("Column pin must be 'start' or 'end'.")
        self.key = key
        self.label = label
        self.kind = kind
        self.align = align or ("end" if kind == "number" else "start")
        self.sortable = sortable
        self.editable = editable
        self.pin = pin


@dataclasses.dataclass(frozen=True)
class GridQuery:
    """The server-mode grid state, typically built from the page's typed
    query parameters: ``ui.grid_query(sort=sort, dir=dir, q=q, page=page)``."""
    sort: str | None = None
    dir: str = "asc"
    q: str = ""
    page: int = 1


def grid_query(sort: str | None = None, dir: str = "asc", q: str = "",
               page: int = 1) -> GridQuery:
    """Normalize grid query parameters (SPEC 12.2 server sorting)."""
    if dir not in ("asc", "desc"):
        dir = "asc"
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    return GridQuery(sort=sort or None, dir=dir, q=str(q or ""), page=page)


def apply_grid_query(rows: Any, query: GridQuery,
                     columns: list[Column] | None = None,
                     page_size: int | None = None) -> tuple[list[dict], int]:
    """Sort, filter, and page rows server-side. Returns the visible rows
    and the total page count."""
    from .data import infer_columns, records
    rows = records(rows)
    columns = columns or (infer_columns(rows) if rows else [])
    if query.q:
        needle = query.q.casefold()
        rows = [row for row in rows
                if any(needle in str(value).casefold()
                       for value in row.values())]
    if query.sort:
        kind = next((c.kind for c in columns if c.key == query.sort), "text")
        rows = sorted(rows, key=lambda row: _sort_key(row.get(query.sort),
                                                      kind),
                      reverse=query.dir == "desc")
    pages = 1
    if page_size:
        pages = max(1, -(-len(rows) // page_size))
        start = (min(query.page, pages) - 1) * page_size
        rows = rows[start:start + page_size]
    return rows, pages


def _sort_key(value: Any, kind: str) -> tuple:
    if kind == "number":
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (1, 0.0)
    return (0, str(value or "").casefold())


def _aggregate(values: list, how: str) -> str:
    numbers = []
    for value in values:
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    if how == "count":
        return str(len(values))
    if not numbers:
        return ""
    if how == "sum":
        total = sum(numbers)
    elif how == "mean":
        total = sum(numbers) / len(numbers)
    elif how == "min":
        total = min(numbers)
    else:
        total = max(numbers)
    return f"{total:g}" if how != "mean" else f"{total:.4g}"


def DataGrid(rows: Any, *, columns: list[Column] | None = None,
             key: str | None = None, caption: str | None = None,
             filterable: bool = False, page_size: int | None = None,
             selectable: bool = False, on_selection: Any = None,
             group_by: str | None = None,
             aggregate: dict[str, str] | None = None,
             on_edit: Any = None,
             resizable: bool = False,
             export: bool = False,
             virtual: bool = False, height: str = "24rem",
             row_height: int = 44,
             server: GridQuery | None = None,
             pages: int | None = None,
             stream: Any = None) -> Element:
    """A data grid over plain rows (SPEC 12.2). Beyond sorting,
    filtering, paging, and selection:

    - group_by= groups rows under collapsible headers, and aggregate=
      ({"score": "mean"}) computes per-group and total summaries in
      Python.
    - Column(editable=True) cells edit in place (Enter commits, Escape
      cancels); the grid dispatches virel-edit with the row key, column,
      and value.
    - Column(pin="start") pins columns while the table scrolls;
      resizable=True adds header drag handles; export=True adds a CSV
      download of the current view (formula-injection safe).
    - virtual=True embeds the rows as data and renders only the visible
      window (large datasets); stream= takes a streaming @ui.server
      action whose events upsert rows live by key.
    - server=ui.grid_query(...) renders headers, filter, and pager as
      plain links and a GET form for server-side sorting (pass pages=
      from ui.apply_grid_query).
    """
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
    editable = [c for c in columns if c.editable]
    if selectable and key is None:
        raise VirelCompileError(
            "DataGrid(selectable=True) requires key= naming the column "
            "that identifies a row.")
    if (editable or stream is not None) and key is None:
        raise VirelCompileError(
            "Editable and streaming grids require key= so rows and cells "
            "keep their identity.")
    if page_size is not None and (not isinstance(page_size, int)
                                  or page_size < 1):
        raise VirelCompileError("page_size must be a positive int.")
    for name, handler in (("on_selection", on_selection),
                          ("on_edit", on_edit)):
        if handler is not None and not isinstance(handler, Handler):
            raise VirelCompileError(
                f"{name} takes a handler, typically "
                f'ui.set_from_event(state, "detail...").')
    if aggregate:
        for column_key, how in aggregate.items():
            if how not in _AGGREGATES:
                raise VirelCompileError(
                    f"aggregate for {column_key!r} must be one of "
                    f"{', '.join(_AGGREGATES)}.")
    if group_by and virtual:
        raise VirelCompileError(
            "group_by is not supported with virtual=True; group "
            "server-side or drop virtualization.")
    if group_by and not any(c.key == group_by for c in columns):
        raise VirelCompileError(f"group_by {group_by!r} is not a column.")
    if server is not None and (virtual or stream is not None):
        raise VirelCompileError(
            "server= replaces client behavior; it cannot combine with "
            "virtual= or stream=.")
    stream_name = None
    if stream is not None:
        if not virtual:
            raise VirelCompileError(
                "stream= requires virtual=True (rows live as data).")
        stream_name = getattr(stream, "name", None)
        if not stream_name or not getattr(stream, "stream_response", False):
            raise VirelCompileError(
                "stream= takes a streaming @ui.server action.")

    header_cells = _header_cells(columns, selectable, server, filterable)
    table_children: list[Node] = []
    if caption:
        table_children.append(Element("caption", [TextNode(caption)]))
    table_children.append(Element("thead", [Element("tr", header_cells)]))

    if virtual:
        table_children.append(Element("tbody", []))
    else:
        table_children.append(Element(
            "tbody", _body_rows(rows, columns, key, selectable, group_by,
                                aggregate)))
        if aggregate and not group_by:
            table_children.append(Element(
                "tfoot", [_aggregate_row(rows, columns, aggregate,
                                         selectable, "All rows")]))

    wrap_style = f"max-height: {height}; overflow-y: auto;" if virtual \
        else None
    table = Element("div", [Element(
        "table", table_children, attrs={"class": "v-table v-grid-table"})],
        attrs={"class": "v-table-wrap v-grid-scroll" if virtual
               else "v-table-wrap",
               "style": wrap_style})

    chrome: list[Node] = []
    toolbar: list[Node] = []
    if filterable and server is None:
        toolbar.append(Element("input", attrs={
            "type": "search", "class": "v-input v-grid-filter",
            "placeholder": "Filter rows…", "aria-label": "Filter rows"}))
    elif filterable:
        toolbar.append(Element("form", [Element("input", attrs={
            "type": "search", "name": "q", "value": server.q or None,
            "class": "v-input v-grid-filter",
            "placeholder": "Filter rows…", "aria-label": "Filter rows"})],
            attrs={"method": "get", "class": "v-grid-filter-form"}))
    if export:
        toolbar.append(Element("button", [TextNode("Export CSV")], attrs={
            "type": "button", "class": "v-btn v-btn-neutral v-btn-sm "
            "v-grid-export"}))
    toolbar.append(Element("span", attrs={
        "class": "v-grid-count", "role": "status"}))
    chrome.append(Element("div", toolbar, attrs={"class": "v-grid-toolbar"}))
    chrome.append(table)
    if server is not None and pages and pages > 1:
        chrome.append(_server_pager(server, pages))
    elif page_size is not None and server is None:
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
    if on_edit is not None:
        events["virel-edit"] = on_edit

    meta = {
        "columns": [{"key": c.key, "kind": c.kind, "align": c.align,
                     "editable": c.editable, "pin": c.pin}
                    for c in columns],
        "key": key, "selectable": selectable, "virtual": virtual,
        "rowHeight": row_height, "resizable": resizable,
        "server": server is not None, "stream": stream_name,
        "groupBy": group_by,
    }
    if virtual:
        from .compiler import _js_json
        chrome.append(Element(
            "script", [RawHTML(_js_json(rows),
                               reason="Script-context-safe JSON rows for "
                                      "the virtual grid.")],
            attrs={"type": "application/json", "class": "v-grid-data"}))
    import json as _json
    return Element("div", chrome,
                   attrs={"class": "v-datagrid",
                          "data-page-size": str(page_size or 0),
                          "data-meta": _json.dumps(meta)},
                   events=events,
                   runtime_binding="datagrid")


def _header_cells(columns: list[Column], selectable: bool,
                  server: GridQuery | None,
                  filterable: bool) -> list[Node]:
    cells: list[Node] = []
    if selectable:
        cells.append(Element("th", [Element("input", attrs={
            "type": "checkbox", "class": "v-grid-check v-grid-check-all",
            "aria-label": "Select all rows",
        })], attrs={"scope": "col", "class": "v-grid-selcol"}))
    for column in columns:
        label: Node = TextNode(column.label)
        aria_sort = None
        if column.sortable and server is not None:
            active = server.sort == column.key
            next_dir = "desc" if active and server.dir == "asc" else "asc"
            params = [f"sort={column.key}", f"dir={next_dir}"]
            if server.q:
                params.append(f"q={server.q}")
            label = Element("a", [TextNode(column.label)], attrs={
                "href": "?" + "&".join(params), "class": "v-grid-sort"})
            aria_sort = ("ascending" if server.dir == "asc" else
                         "descending") if active else "none"
        elif column.sortable:
            label = Element("button", [TextNode(column.label)], attrs={
                "type": "button", "class": "v-grid-sort"})
            aria_sort = "none"
        content: list[Node] = [label]
        classes = f"v-grid-align-{column.align}"
        if column.pin:
            classes += f" v-grid-pin v-grid-pin-{column.pin}"
        cells.append(Element("th", content, attrs={
            "scope": "col", "data-key": column.key,
            "data-kind": column.kind, "aria-sort": aria_sort,
            "class": classes,
        }))
    return cells


def _body_rows(rows: list[dict], columns: list[Column], key: str | None,
               selectable: bool, group_by: str | None,
               aggregate: dict[str, str] | None) -> list[Node]:
    if not group_by:
        return [_row(row, index, columns, key, selectable)
                for index, row in enumerate(rows)]
    groups: dict[Any, list[tuple[int, dict]]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(row.get(group_by, ""), []).append((index, row))
    built: list[Node] = []
    span = len(columns) + (1 if selectable else 0)
    for group_value, members in groups.items():
        group_id = str(group_value)
        member_rows = [row for _, row in members]
        summary = ""
        if aggregate:
            parts = []
            for column_key, how in aggregate.items():
                label = next((c.label for c in columns
                              if c.key == column_key), column_key)
                parts.append(f"{label} {how}: " + _aggregate(
                    [row.get(column_key) for row in member_rows], how))
            summary = " · ".join(parts)
        built.append(Element("tr", [Element("td", [
            Element("button", [TextNode(
                f"{group_id} ({len(members)})")],
                attrs={"type": "button", "class": "v-grid-group-toggle",
                       "aria-expanded": "true"}),
            Element("span", [TextNode(summary)],
                    attrs={"class": "v-grid-group-summary"}),
        ], attrs={"colspan": str(span)})],
            attrs={"class": "v-grid-group", "data-group": group_id}))
        for index, row in members:
            built.append(_row(row, index, columns, key, selectable,
                              group_of=group_id))
    return built


def _row(row: dict, index: int, columns: list[Column], key: str | None,
         selectable: bool, group_of: str | None = None) -> Element:
    cells: list[Node] = []
    if selectable:
        row_key = str(row.get(key, index))
        cells.append(Element("td", [Element("input", attrs={
            "type": "checkbox", "class": "v-grid-check v-grid-check-row",
            "aria-label": f"Select row {row_key}",
        })], attrs={"class": "v-grid-selcol"}))
    for column in columns:
        value = row.get(column.key, "")
        classes = f"v-grid-align-{column.align}"
        if column.pin:
            classes += f" v-grid-pin v-grid-pin-{column.pin}"
        if column.editable:
            classes += " v-grid-editable"
        cells.append(Element(
            "td", [TextNode(str(value))],
            attrs={"data-value": _sortable_value(value, column.kind),
                   "data-col": column.key,
                   "tabindex": "-1",
                   "class": classes}))
    attrs: dict[str, Any] = {"data-index": str(index)}
    if key is not None:
        attrs["data-key"] = str(row.get(key, index))
    if group_of is not None:
        attrs["data-group-of"] = group_of
    return Element("tr", cells, attrs=attrs)


def _aggregate_row(rows: list[dict], columns: list[Column],
                   aggregate: dict[str, str], selectable: bool,
                   label: str) -> Element:
    cells: list[Node] = []
    if selectable:
        cells.append(Element("td", [TextNode("")]))
    for position, column in enumerate(columns):
        if position == 0:
            cells.append(Element("td", [TextNode(label)],
                                 attrs={"class": "v-grid-agg-label"}))
            continue
        how = aggregate.get(column.key)
        text = _aggregate([row.get(column.key) for row in rows], how) \
            if how else ""
        cells.append(Element("td", [TextNode(text)], attrs={
            "class": f"v-grid-align-{column.align} v-grid-agg"}))
    return Element("tr", cells, attrs={"class": "v-grid-total"})


def _server_pager(server: GridQuery, pages: int) -> Element:
    def link(page: int, text: str, disabled: bool) -> Node:
        if disabled:
            return Element("span", [TextNode(text)],
                           attrs={"class": "v-page-link", "aria-disabled":
                                  "true"})
        params = [f"page={page}"]
        if server.sort:
            params.extend([f"sort={server.sort}", f"dir={server.dir}"])
        if server.q:
            params.append(f"q={server.q}")
        return Element("a", [TextNode(text)], attrs={
            "href": "?" + "&".join(params), "class": "v-page-link"})

    current = min(server.page, pages)
    return Element("div", [
        link(current - 1, "Previous", current <= 1),
        Element("span", [TextNode(f"Page {current} of {pages}")],
                attrs={"class": "v-grid-pages"}),
        link(current + 1, "Next", current >= pages),
    ], attrs={"class": "v-grid-pager"})


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
