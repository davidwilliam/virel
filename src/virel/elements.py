"""Component constructors exposed on ``virel.ui``.

Three layers (SPEC 11.1): semantic elements, layout primitives, and styled
product components. Every constructor returns an IR node; nothing here
touches the DOM directly.
"""

from __future__ import annotations

from typing import Any, Callable

from .expr import (
    Expr,
    Handler,
    SetFromEventOp,
    SetOp,
    State,
    VirelCompileError,
    lift,
    record_handler,
)
from .nodes import BindText, Element, Node, PageNode, RawHTML, TextNode, When, normalize_children

_INTENTS = ("neutral", "primary", "danger")
_page_modules: list[str] = []  # extra JS modules required by the current page


def _reset_page_modules() -> None:
    _page_modules.clear()


def _require_module(module: str) -> None:
    if module not in _page_modules:
        _page_modules.append(module)


def _handler(fn: Callable[[], None] | Handler) -> Any:
    """Compile an event handler.

    Lambdas are traced symbolically (fast, but limited to a sequence of
    calls). Named functions go through the AST client compiler and may use
    the full client subset, including if/elif/else and for-loops.
    """
    if isinstance(fn, Handler):
        return fn
    from .pycompiler import CompiledHandler, compile_handler
    if isinstance(fn, CompiledHandler):
        return fn
    if getattr(fn, "__name__", "<lambda>") != "<lambda>":
        return compile_handler(fn)
    return record_handler(fn)


def _gap_style(gap: int | None, extra: str = "") -> str | None:
    parts = []
    if gap is not None:
        parts.append(f"gap: calc(var(--v-space) * {gap})")
    if extra:
        parts.append(extra)
    return "; ".join(parts) if parts else None


_ALIGN = {"start": "flex-start", "center": "center", "end": "flex-end", "stretch": "stretch"}
_JUSTIFY = {
    "start": "flex-start",
    "center": "center",
    "end": "flex-end",
    "between": "space-between",
}


# --------------------------------------------------------------------------
# Page and layout primitives
# --------------------------------------------------------------------------

def Page(*children: Any, title: str = "Virel App",
         meta: dict[str, str] | None = None,
         canonical: str | None = None) -> PageNode:
    if canonical is not None:
        from .security import is_safe_url
        if not is_safe_url(canonical):
            raise VirelCompileError(
                f"canonical URL {canonical!r} uses a blocked scheme."
            )
    return PageNode(
        children=normalize_children(children),
        title=title,
        meta=meta or {},
        head_modules=list(_page_modules),
        canonical=canonical,
    )


def _classes(base: str, class_name: Any) -> str:
    # class_name accepts a plain string or a ui.style() object (or a
    # sequence mixing both).
    if class_name is None:
        return base
    if isinstance(class_name, (list, tuple)):
        return " ".join([base, *(str(c) for c in class_name)])
    return f"{base} {class_name}"


def Stack(*children: Any, gap: int = 4, align: str = "stretch",
          class_name: str | None = None) -> Element:
    style = _gap_style(gap, f"align-items: {_ALIGN[align]}")
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-stack", class_name),
                          "style": style})


def Row(*children: Any, gap: int = 3, align: str = "center",
        justify: str = "start", wrap: bool = False,
        class_name: str | None = None) -> Element:
    extra = f"align-items: {_ALIGN[align]}; justify-content: {_JUSTIFY[justify]}"
    if wrap:
        extra += "; flex-wrap: wrap"
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-row", class_name),
                          "style": _gap_style(gap, extra)})


def Grid(*children: Any, columns: int | dict[str, int] = 2, gap: int = 4,
         class_name: str | None = None) -> Element:
    """Responsive grid. ``columns`` takes an int or typed breakpoints:
    ``{"base": 1, "md": 2, "xl": 4}``."""
    if isinstance(columns, int):
        columns = {"base": columns}
    unknown = set(columns) - {"base", "md", "xl"}
    if unknown:
        raise VirelCompileError(
            f"Grid columns breakpoints {sorted(unknown)} are not supported. "
            "Use base, md, and xl."
        )
    variables = "; ".join(
        f"--v-cols{'' if bp == 'base' else '-' + bp}: {count}"
        for bp, count in columns.items()
    )
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-grid", class_name),
                          "style": _gap_style(gap, variables)})


def Container(*children: Any, width: str = "md",
              class_name: str | None = None) -> Element:
    return Element("div", normalize_children(children),
                   attrs={"class": _classes(f"v-container v-container-{width}",
                                            class_name)})


def Section(*children: Any, gap: int = 6,
            class_name: str | None = None) -> Element:
    return Element("section", normalize_children(children),
                   attrs={"class": _classes("v-stack v-section", class_name),
                          "style": _gap_style(gap)})


def Card(*children: Any, gap: int = 3, align: str = "stretch",
         class_name: str | None = None) -> Element:
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-card v-stack", class_name),
                          "style": _gap_style(gap,
                                              f"align-items: {_ALIGN[align]}")})


def Wrap(*children: Any, gap: int = 3, align: str = "start",
         class_name: str | None = None) -> Element:
    """A row that wraps onto new lines as space runs out."""
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-wrap", class_name),
                          "style": _gap_style(gap,
                                              f"align-items: {_ALIGN[align]}")})


def Cluster(*children: Any, gap: int = 2, justify: str = "start",
            align: str = "center", class_name: str | None = None) -> Element:
    """A group of related items (tags, actions, metadata) with a
    consistent gap, wrapping and justified as one unit."""
    extra = (f"align-items: {_ALIGN[align]}; "
             f"justify-content: {_JUSTIFY[justify]}")
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-cluster", class_name),
                          "style": _gap_style(gap, extra)})


def Center(*children: Any, min_height: str | None = None,
           class_name: str | None = None) -> Element:
    """Centers its content on both axes."""
    style = f"min-height: {_css_length(min_height)}" if min_height else None
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-center", class_name),
                          "style": style})


def Sidebar(aside: Any, content: Any, *, width: str = "16rem",
            side: str = "left", gap: int = 5,
            class_name: str | None = None) -> Element:
    """The sidebar layout pattern: an aside with a preferred width next
    to fluid content, stacking automatically when the content column
    would drop below a readable measure. No media query involved, so it
    works at any nesting depth."""
    if side not in ("left", "right"):
        raise VirelCompileError("Sidebar side must be 'left' or 'right'.")
    aside_el = Element("div", normalize_children((aside,)),
                       attrs={"class": "v-sidebar-aside"})
    main_el = Element("div", normalize_children((content,)),
                      attrs={"class": "v-sidebar-main"})
    ordered = [aside_el, main_el] if side == "left" else [main_el, aside_el]
    style = _gap_style(gap, f"--v-sidebar-w: {_css_length(width)}")
    return Element("div", ordered,
                   attrs={"class": _classes("v-sidebar-layout", class_name),
                          "style": style})


def AspectRatio(*children: Any, ratio: str = "16/9",
                class_name: str | None = None) -> Element:
    """Reserves a fixed width-to-height ratio; media children fill it."""
    import re as _re
    if not _re.fullmatch(r"\d+(\.\d+)?(\s*/\s*\d+(\.\d+)?)?", str(ratio)):
        raise VirelCompileError(
            f"AspectRatio ratio must look like '16/9' or '1', got {ratio!r}.")
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-aspect", class_name),
                          "style": f"aspect-ratio: {ratio}"})


def ScrollArea(*children: Any, max_height: str | None = None,
               axis: str = "y", class_name: str | None = None) -> Element:
    """A scrolling region with styled scrollbars and contained
    overscroll, so inner scrolling never chains to the page."""
    if axis not in ("x", "y", "both"):
        raise VirelCompileError("ScrollArea axis must be 'x', 'y', or 'both'.")
    style = f"max-height: {_css_length(max_height)}" if max_height else None
    return Element("div", normalize_children(children),
                   attrs={"class": _classes(f"v-scroll v-scroll-{axis}",
                                            class_name),
                          "style": style, "tabindex": "0"})


def Resizable(*children: Any, direction: str = "both",
              class_name: str | None = None) -> Element:
    """A container the user can resize by dragging its corner. Pure CSS."""
    suffix = {"both": "both", "horizontal": "h", "vertical": "v"}.get(direction)
    if suffix is None:
        raise VirelCompileError("Resizable direction must be 'both', "
                                "'horizontal', or 'vertical'.")
    return Element("div", normalize_children(children),
                   attrs={"class": _classes(f"v-resizable v-resizable-{suffix}",
                                            class_name)})


def Splitter(first: Any, second: Any, *, direction: str = "row",
             initial: int = 50, min_size: int = 20, max_size: int = 80,
             class_name: str | None = None) -> Element:
    """Two panes separated by a draggable divider. The divider is a
    keyboard-operable separator: arrow keys move it, Home/End snap to
    the limits, double-click resets."""
    if direction not in ("row", "column"):
        raise VirelCompileError("Splitter direction must be 'row' or "
                                "'column'.")
    if not 0 <= min_size <= initial <= max_size <= 100:
        raise VirelCompileError("Splitter sizes must satisfy 0 <= min_size "
                                "<= initial <= max_size <= 100.")
    handle = Element("div", attrs={
        "class": "v-splitter-handle",
        "role": "separator",
        "tabindex": "0",
        "aria-label": "Resize panels",
        "aria-orientation": "vertical" if direction == "row" else "horizontal",
        "aria-valuemin": str(min_size),
        "aria-valuemax": str(max_size),
        "aria-valuenow": str(initial),
    })
    panes = [
        Element("div", normalize_children((first,)),
                attrs={"class": "v-splitter-first"}),
        handle,
        Element("div", normalize_children((second,)),
                attrs={"class": "v-splitter-second"}),
    ]
    classes = "v-splitter" + (" v-splitter-col" if direction == "column" else "")
    return Element("div", panes,
                   attrs={"class": _classes(classes, class_name),
                          "style": f"--v-split: {initial}%",
                          "data-min": str(min_size),
                          "data-max": str(max_size),
                          "data-initial": str(initial)},
                   runtime_binding="splitter")


def Box(*children: Any, css: dict[str, Any] | None = None,
        class_name: str | None = None) -> Element:
    """The CSS escape hatch (SPEC 10.5): a neutral container taking raw
    CSS declarations, including custom properties, for the cases the
    typed styling API does not cover.

        ui.Box(chart, class_name="specialized-visualization",
               css={"container-type": "inline-size", "--plot-density": 0.8})

    Declarations land as a normal inline style, so they stay compatible
    with standard CSS concepts and browser development tools.
    """
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-box", class_name),
                          "style": _css_declarations(css) if css else None})


def _css_declarations(css: dict[str, Any]) -> str:
    """Validate an escape-hatch CSS dict into inline declarations.
    Property names must be real CSS identifiers or custom properties;
    values must be scalars free of characters that could terminate the
    declaration list or the attribute."""
    import re as _re
    parts = []
    for name, value in css.items():
        if not _re.fullmatch(r"--[\w-]+|[a-zA-Z-]+", str(name)):
            raise VirelCompileError(
                f"Invalid CSS property name {name!r}; expected a property "
                "like 'container-type' or a custom property like '--x'.")
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise VirelCompileError(
                f"CSS value for {name!r} must be a string or number, "
                f"got {value!r}.")
        text = str(value)
        if _re.search(r"[;{}<>]", text):
            raise VirelCompileError(
                f"CSS value for {name!r} contains characters that are not "
                "allowed in a declaration: use one property per key.")
        parts.append(f"{name}: {text}")
    return "; ".join(parts)


def Swipeable(*children: Any, on_dismiss: Callable[[], None],
              direction: str = "x", threshold: float = 0.35,
              class_name: str | None = None) -> Element:
    """A gesture container (SPEC 10.8): its content follows the pointer
    horizontally and, past the threshold (or with a quick flick), slides
    away and fires on_dismiss. Below the threshold it springs back. The
    container is focusable, and Delete or Backspace dismisses it, so the
    gesture has keyboard parity."""
    if direction not in ("x", "left", "right"):
        raise VirelCompileError(
            "Swipeable direction must be 'x', 'left', or 'right'.")
    if not isinstance(threshold, (int, float)) or not 0.05 <= threshold <= 0.9:
        raise VirelCompileError(
            "Swipeable threshold is a fraction between 0.05 and 0.9.")
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-swipeable", class_name),
                          "data-direction": direction,
                          "data-threshold": f"{threshold:g}",
                          "tabindex": "0",
                          "role": "group",
                          "aria-label": "Swipe or press Delete to dismiss"},
                   events={"virel-dismiss": _handler(on_dismiss)},
                   runtime_binding="swipeable")


def Tree(items: list, *, label: Callable[[Any], str],
         children: Callable[[Any], list] | None = None,
         on_select: Callable[[Any], None] | None = None,
         aria_label: str = "Tree") -> Element:
    """An accessible tree view (SPEC 11.1) over plain nested data:

        ui.Tree(folders,
                label=lambda n: n["name"],
                children=lambda n: n.get("children", []),
                on_select=lambda n: selected.set(n["name"]))

    Arrow keys move and expand/collapse (the ARIA tree pattern), rows
    select on click or Enter, and each row's handler is traced with its
    own node bound."""
    children_of = children or (lambda node: node.get("children", []))

    def build(nodes: list, depth: int) -> list[Node]:
        built: list[Node] = []
        for node in nodes:
            kids = children_of(node) or []
            row_children: list[Node] = []
            if kids:
                row_children.append(Element(
                    "span", attrs={"class": "v-tree-twist",
                                   "aria-hidden": "true"}))
            events = {}
            if on_select is not None:
                events["click"] = _handler(
                    lambda node=node: on_select(node))
            row_children.append(Element(
                "span", [TextNode(str(label(node)))],
                attrs={"class": "v-tree-label"}, events=events))
            row = Element("span", row_children,
                          attrs={"class": "v-tree-row"})
            item_children: list[Node] = [row]
            attrs: dict[str, Any] = {"role": "treeitem", "tabindex": "-1",
                                     "class": "v-tree-item"}
            if kids:
                attrs["aria-expanded"] = "true"
                item_children.append(Element(
                    "ul", build(kids, depth + 1),
                    attrs={"role": "group", "class": "v-tree-group"}))
            built.append(Element("li", item_children, attrs=attrs))
        return built

    if not items:
        raise VirelCompileError("Tree needs at least one item.")
    return Element("ul", build(items, 0),
                   attrs={"role": "tree", "class": "v-tree",
                          "aria-label": aria_label},
                   runtime_binding="tree")


class Command:
    """One command palette entry: a navigation target or an action."""

    def __init__(self, label: str, *, to: str | None = None,
                 on_run: Callable[[], None] | None = None,
                 hint: str | None = None) -> None:
        if (to is None) == (on_run is None):
            raise VirelCompileError(
                "Command takes exactly one of to= (a link) or on_run= "
                "(an action).")
        if to is not None:
            from .security import is_safe_url
            if not is_safe_url(to):
                raise VirelCompileError(
                    f"Command target {to!r} uses a blocked URL scheme.")
        self.label = label
        self.to = to
        self.on_run = on_run
        self.hint = hint


def CommandPalette(*, commands: list[Command], hotkey: str = "k",
                   placeholder: str = "Type a command…") -> Element:
    """A command palette (SPEC 11.1): Ctrl/Cmd plus the hotkey opens a
    modal search over the registered commands; typing filters, arrows
    move, Enter runs. Built on the native dialog element, so focus
    trapping and Escape come from the browser."""
    import re as _re
    if not _re.fullmatch(r"[a-z]", hotkey):
        raise VirelCompileError("CommandPalette hotkey is a single letter.")
    if not commands:
        raise VirelCompileError("CommandPalette needs at least one command.")
    options: list[Node] = []
    for command in commands:
        entry_children: list[Node] = [
            Element("span", [TextNode(command.label)],
                    attrs={"class": "v-palette-label"})]
        if command.hint:
            entry_children.append(Element(
                "span", [TextNode(command.hint)],
                attrs={"class": "v-palette-hint"}))
        attrs = {"class": "v-palette-item", "role": "option",
                 "data-label": command.label.lower()}
        if command.to is not None:
            entry = Element("a", entry_children,
                            attrs={**attrs, "href": command.to})
        else:
            entry = Element("button", entry_children,
                            attrs={**attrs, "type": "button"},
                            events={"click": _handler(command.on_run)})
        options.append(entry)
    search = Element("input", attrs={
        "class": "v-input v-palette-input",
        "type": "text",
        "placeholder": placeholder,
        "role": "combobox",
        "aria-expanded": "true",
        "aria-label": "Search commands",
        "autocomplete": "off",
    })
    listbox = Element("div", options,
                      attrs={"role": "listbox", "class": "v-palette-list",
                             "aria-label": "Commands"})
    empty = Element("div", [TextNode("No matching commands.")],
                    attrs={"class": "v-palette-empty", "hidden": True})
    return Element("dialog", [search, listbox, empty],
                   attrs={"class": "v-palette", "data-hotkey": hotkey,
                          "aria-label": "Command palette"},
                   runtime_binding="palette")


def _css_length(value: str | int) -> str:
    """A CSS length from an int (pixels) or a validated string. Strings
    are restricted to simple lengths so styles cannot be broken out of."""
    if isinstance(value, int):
        return f"{value}px"
    import re as _re
    if not _re.fullmatch(r"\d+(\.\d+)?(px|rem|em|vh|vw|ch|%)", str(value)):
        raise VirelCompileError(
            f"Expected a CSS length like '16rem' or an int of pixels, "
            f"got {value!r}.")
    return value


def Divider() -> Element:
    return Element("hr", attrs={"class": "v-divider"})


def Spacer() -> Element:
    return Element("div", attrs={"class": "v-spacer", "aria-hidden": "true"})


# --------------------------------------------------------------------------
# Semantic elements
# --------------------------------------------------------------------------

def Heading(text: Any, level: int = 2, size: int | None = None) -> Element:
    """A heading. ``level`` is the document-outline semantics; ``size``
    optionally decouples the visual size, so a card title can stay an h2
    in the outline while looking like an h3."""
    if level not in (1, 2, 3, 4, 5, 6):
        raise VirelCompileError(f"Heading level must be 1-6, got {level!r}.")
    classes = "v-heading"
    if size is not None:
        if size not in (1, 2, 3, 4, 5, 6):
            raise VirelCompileError(f"Heading size must be 1-6, got {size!r}.")
        classes += f" v-h{size}"
    return Element(f"h{level}", normalize_children((text,)),
                   attrs={"class": classes})


def Text(content: Any, *, muted: bool = False, size: str = "md") -> Element:
    classes = "v-text"
    if muted:
        classes += " v-muted"
    if size != "md":
        classes += f" v-text-{size}"
    return Element("p", normalize_children((content,)), attrs={"class": classes})


def Code(content: Any, block: bool = False,
         language: str | None = None) -> Element:
    """Code display. With ``language`` and literal content, the snippet is
    syntax highlighted at compile time (no client JavaScript)."""
    children: list[Node] | None = None
    if language and isinstance(content, str):
        from .highlight import highlight
        spans = highlight(content, language)
        if spans is not None:
            children = [
                TextNode(text) if cls in ("ws", "txt", "pun")
                else Element("span", [TextNode(text)],
                             attrs={"class": f"v-tok-{cls}"})
                for cls, text in spans
            ]
    if children is None:
        children = normalize_children((content,))
    inner = Element("code", children)
    if block:
        return Element("pre", [inner], attrs={"class": "v-code"})
    inner.attrs["class"] = "v-code-inline"
    return inner


def Link(text: Any, to: str | Expr, *, external: bool = False) -> Element:
    if isinstance(to, str):
        from .security import is_safe_url
        if not is_safe_url(to):
            raise VirelCompileError(
                f"Link target {to!r} uses a blocked URL scheme. Allowed: "
                "relative URLs, http(s), mailto, and tel."
            )
    attrs: dict[str, Any] = {"href": to, "class": "v-link"}
    if external:
        attrs["rel"] = "noopener noreferrer"
        attrs["target"] = "_blank"
    return Element("a", normalize_children((text,)), attrs=attrs)


def LinkButton(text: Any, to: str, *, intent: str = "neutral",
               size: str = "md") -> Element:
    """A navigation link styled as a button (real anchor semantics)."""
    if intent not in _INTENTS:
        raise VirelCompileError(
            f"intent={intent!r} is not valid. Use one of: {', '.join(_INTENTS)}."
        )
    from .security import is_safe_url
    if not is_safe_url(to):
        raise VirelCompileError(
            f"Link target {to!r} uses a blocked URL scheme."
        )
    return Element("a", normalize_children((text,)),
                   attrs={"href": to,
                          "class": f"v-btn v-btn-{intent} v-btn-{size}"})


def Image(src: str | Expr, alt: str, *, width: int | None = None) -> Element:
    # Accessibility is a correctness property (SPEC 6.5): alt is required.
    if alt is None:
        raise VirelCompileError("Image requires alt text (use alt='' only for decorative images).")
    if isinstance(src, str):
        from .security import is_safe_url
        if not is_safe_url(src, image=True):
            raise VirelCompileError(
                f"Image source {src!r} uses a blocked URL scheme. Allowed: "
                "relative URLs, http(s), and data:."
            )
    attrs: dict[str, Any] = {"src": src, "alt": alt}
    if width:
        attrs["width"] = width
    return Element("img", attrs=attrs)


def List(*items: Any, ordered: bool = False) -> Element:
    children = [Element("li", normalize_children((item,))) for item in items]
    return Element("ol" if ordered else "ul", children, attrs={"class": "v-list"})


def Nav(*children: Any, label: str = "Main") -> Element:
    return Element("nav", normalize_children(children),
                   attrs={"class": "v-nav", "aria-label": label})


def unsafe_html(markup: str, *, reason: str) -> RawHTML:
    return RawHTML(markup, reason)


class EffectDef:
    def __init__(self, handler: Any, dependencies: list[Expr],
                 run_on_mount: bool) -> None:
        self.handler = handler
        self.dependencies = dependencies
        self.run_on_mount = run_on_mount


def effect(fn: Callable[[], None], *, dependencies: list[Any],
           run_on_mount: bool = False) -> None:
    """Run a handler in the browser whenever a dependency changes
    (SPEC 8.5). Effects never run during server rendering. Dependencies
    are explicit: a list of states or derived values."""
    from .expr import current_context
    if not dependencies:
        raise VirelCompileError(
            "ui.effect requires dependencies=[...] naming at least one "
            "state or derived value."
        )
    deps = [lift(d) for d in dependencies]
    for dep in deps:
        if not hasattr(dep, "name"):
            raise VirelCompileError(
                "ui.effect dependencies must be ui.state or ui.derived "
                "values."
            )
    current_context().effects.append(
        EffectDef(_handler(fn), deps, run_on_mount))


def FileField(*, label: str, accept: str | None = None,
              multiple: bool = False,
              description: str | None = None) -> Element:
    """File picker for upload actions: a drop zone that also accepts
    dragged files, with a summary of the current selection. Pass the
    returned element to ui.upload(files=...) inside a handler."""
    from .expr import current_context
    ref = current_context().next_id("f")
    control = Element("input", attrs={
        "class": "v-file", "type": "file", "data-vf": ref,
        "accept": accept, "multiple": multiple or None,
    })
    prompt = ("Drop files here or browse" if multiple
              else "Drop a file here or browse")
    zone = Element("div", [
        control,
        Element("span", [TextNode(prompt)], attrs={"class": "v-hint"}),
        Element("span", [], attrs={"class": "v-file-summary",
                                   "data-file-summary": "true"}),
    ], attrs={"class": "v-dropzone"}, runtime_binding="dropzone")
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        zone,
    ]
    if description:
        children.append(Element("span", [TextNode(description)],
                                attrs={"class": "v-hint"}))
    wrapper = Element("label", children, attrs={"class": "v-field"})
    wrapper.file_ref = ref
    return wrapper


def upload(action: Any, *, files: Element, args: dict[str, Any] | None = None,
           into: State | None = None, progress_into: State | None = None,
           error_into: State | None = None) -> None:
    """Inside a handler: send the selected files to an upload action over
    multipart, with byte-level progress into a state (SPEC 8.8)."""
    from .expr import UploadOp, current_recorder
    from .registry import ServerAction
    from .uploads import file_params
    if not isinstance(action, ServerAction):
        raise VirelCompileError("ui.upload takes a @ui.server action.")
    ref = getattr(files, "file_ref", None)
    if ref is None:
        raise VirelCompileError(
            "ui.upload(files=...) takes the element returned by "
            "ui.FileField()."
        )
    params = file_params(action)
    if not params:
        raise VirelCompileError(
            f"Server action {action.name!r} has no parameter annotated with "
            "ui.UploadFile (or list[ui.UploadFile])."
        )
    file_param = next(iter(params))
    lifted = {k: lift(v) for k, v in (args or {}).items()}
    current_recorder().ops.append(UploadOp(
        action.name, file_param, ref, lifted, into, progress_into,
        error_into))


upload.__virel_op__ = "upload"


def DownloadButton(label: Any, *, action: Any,
                   args: dict[str, Any] | None = None,
                   intent: str = "neutral", size: str = "md") -> Element:
    """A link styled as a button that downloads the file returned by a
    download action (a GET; the action must not change state)."""
    from urllib.parse import urlencode
    from .registry import ServerAction
    if not isinstance(action, ServerAction) or not action.download:
        raise VirelCompileError(
            "DownloadButton takes a @ui.server(download=True) action."
        )
    for key, value in (args or {}).items():
        if isinstance(value, Expr):
            raise VirelCompileError(
                "DownloadButton args must be plain values; reactive download "
                "parameters are not supported yet."
            )
    query = urlencode(args or {})
    href = f"/_virel/action/{action.name}" + (f"?{query}" if query else "")
    return Element("a", normalize_children((label,)),
                   attrs={"href": href, "download": True,
                          "class": f"v-btn v-btn-{intent} v-btn-{size}"})


def set_from_event(state: State, path: str = "target.value") -> Handler:
    """An event handler that writes an event property into a state.

    Useful for custom-element events: ``on_rating_changed=ui.set_from_event(
    rating, "detail.value")``.
    """
    if not isinstance(state, State):
        raise VirelCompileError("set_from_event requires a ui.state(...) value.")
    return Handler([SetFromEventOp(state.name, path)])


# --------------------------------------------------------------------------
# Interactive components
# --------------------------------------------------------------------------

def Button(label: Any, *, on_click: Callable[[], None] | None = None,
           intent: str = "neutral", size: str = "md",
           emphasis: str = "solid",
           disabled: Any = None, kind: str = "button",
           aria_label: str | None = None) -> Element:
    if intent not in _INTENTS:
        raise VirelCompileError(
            f"intent={intent!r} is not valid. Use one of: {', '.join(_INTENTS)}."
        )
    if emphasis not in ("solid", "ghost"):
        raise VirelCompileError(
            f"emphasis={emphasis!r} is not valid. Use 'solid' or 'ghost'."
        )
    classes = f"v-btn v-btn-{intent} v-btn-{size}"
    if emphasis == "ghost":
        classes += " v-btn-ghost"
    attrs: dict[str, Any] = {
        "class": classes,
        "type": kind,
    }
    if aria_label:
        attrs["aria-label"] = aria_label
    if disabled is not None:
        attrs["disabled"] = lift(disabled) if isinstance(disabled, Expr) else disabled
    events = {}
    if on_click is not None:
        events["click"] = _handler(on_click)
    node = Element("button", normalize_children((label,)), attrs=attrs, events=events)
    _check_accessible_label(node)
    return node


def _check_accessible_label(button: Element) -> None:
    has_text = any(
        isinstance(c, (TextNode, BindText)) for c in button.children
    )
    has_labeled_child = any(
        isinstance(c, Element) and c.attrs.get("aria-label")
        for c in button.children
    )
    if not has_text and not has_labeled_child and "aria-label" not in button.attrs:
        raise VirelCompileError(
            "Icon-only buttons must set aria_label so the control has an "
            "accessible name (SPEC 11.2)."
        )


def _unwrap_field(value: Any, component: str) -> tuple[State, dict[str, Any], Node | None]:
    """Field components accept either a plain state or a form FieldRef.

    A FieldRef contributes model-derived input attributes (required,
    type=email) and a bound per-field error node.
    """
    from .forms import FieldRef
    if isinstance(value, FieldRef):
        return value.state, value.input_attrs(), value.error_node()
    if isinstance(value, State):
        return value, {}, None
    raise VirelCompileError(
        f"{component} requires a ui.state(...) value or a form field "
        "(form.<name>) as its first argument."
    )


def TextField(state: Any, *, label: str, placeholder: str = "",
              kind: str | None = None, description: str | None = None) -> Element:
    """Labeled input with two-way binding to a state or form field."""
    state, extra_attrs, error_node = _unwrap_field(state, "TextField")
    attrs: dict[str, Any] = {"class": "v-input",
                             "placeholder": placeholder or None}
    attrs.update(extra_attrs)
    attrs["type"] = kind or extra_attrs.get("type", "text")
    input_el = Element(
        "input",
        attrs=attrs,
        events={"input": Handler([SetFromEventOp(state.name, "target.value")])},
        bound_props={"value": state},
    )
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        input_el,
    ]
    if description:
        children.append(Element("span", [TextNode(description)], attrs={"class": "v-hint"}))
    if error_node is not None:
        children.append(error_node)
    return Element("label", children, attrs={"class": "v-field"})


def DateField(state: Any, *, label: str, kind: str = "date",
              min: str | None = None, max: str | None = None,
              description: str | None = None) -> Element:
    """Date selection (SPEC 11.1) on the platform's date input: the
    browser supplies the localized, accessible calendar, the state holds
    the ISO string, and no JavaScript ships for it."""
    import re as _re
    kinds = {"date": r"\d{4}-\d{2}-\d{2}",
             "time": r"\d{2}:\d{2}(:\d{2})?",
             "datetime": r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?"}
    if kind not in kinds:
        raise VirelCompileError("DateField kind must be 'date', 'time', or "
                                "'datetime'.")
    for name, value in (("min", min), ("max", max)):
        if value is not None and not _re.fullmatch(kinds[kind], value):
            raise VirelCompileError(
                f"DateField {name}={value!r} does not match the ISO format "
                f"for kind={kind!r}.")
    state, extra_attrs, error_node = _unwrap_field(state, "DateField")
    attrs: dict[str, Any] = {
        "class": "v-input",
        "type": "datetime-local" if kind == "datetime" else kind,
        "min": min, "max": max,
    }
    attrs.update(extra_attrs)
    input_el = Element(
        "input",
        attrs=attrs,
        events={"input": Handler([SetFromEventOp(state.name, "target.value")])},
        bound_props={"value": state},
    )
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        input_el,
    ]
    if description:
        children.append(Element("span", [TextNode(description)],
                                attrs={"class": "v-hint"}))
    if error_node is not None:
        children.append(error_node)
    return Element("label", children, attrs={"class": "v-field"})


def Popover(*, trigger: Any, content: Any, align: str = "start") -> Element:
    """An anchored, non-modal floating panel (SPEC 11.1): click the
    trigger to open, Escape or clicking outside closes and restores
    focus, and the panel flips upward when space below runs out."""
    if align not in ("start", "end"):
        raise VirelCompileError("Popover align must be 'start' or 'end'.")
    panel = Element("div", normalize_children(
        content if isinstance(content, (list, tuple)) else (content,)),
        attrs={"class": "v-popover-panel"})
    return Element("div", [*normalize_children((trigger,)), panel],
                   attrs={"class": f"v-popover v-popover-{align}"},
                   runtime_binding="popover")


def Pagination(page: Any, pages: int, *, href: Callable[[int], str] | None = None,
               label: str = "Pagination") -> Element:
    """Page navigation (SPEC 11.1). Two modes matching how the page is
    rendered:

    - ``href=`` (server-rendered): ``page`` is the current page number
      and each entry is a real link built by the callable, with the
      classic windowed layout and ellipses.
    - state mode (client): ``page`` is reactive state; number buttons
      write to it, with aria-current tracking the value. Lists longer
      than ten pages get previous/next controls and a live counter.
    """
    if not isinstance(pages, int) or pages < 1:
        raise VirelCompileError("Pagination pages must be a positive int.")

    def item(child: Node, current: bool = False) -> Element:
        classes = "v-page-item" + (" v-page-current" if current else "")
        return Element("li", [child], attrs={"class": classes})

    entries: list[Node] = []
    if href is not None:
        if not isinstance(page, int) or not 1 <= page <= pages:
            raise VirelCompileError(
                "With href=, page is the current page number (1-based).")
        from .security import is_safe_url
        window = _page_window(page, pages)
        for token in window:
            if token == "gap":
                entries.append(item(Element(
                    "span", [TextNode("…")],
                    attrs={"class": "v-page-gap", "aria-hidden": "true"})))
                continue
            target = href(token)
            if not is_safe_url(target):
                raise VirelCompileError(
                    f"Pagination link {target!r} uses a blocked URL scheme.")
            attrs = {"href": target, "class": "v-page-link"}
            if token == page:
                attrs["aria-current"] = "page"
            entries.append(item(Element("a", [TextNode(str(token))],
                                        attrs=attrs), current=token == page))
    else:
        from .expr import (BinOp, Compare, FormatString, Handler as _Handler,
                           Lit, SetOp, cond)
        if pages <= 10:
            for number in range(1, pages + 1):
                button = Element(
                    "button", [TextNode(str(number))],
                    attrs={"type": "button", "class": "v-page-link",
                           "aria-current": cond(Compare("==", page, Lit(number)),
                                                "page", False)},
                    events={"click": _Handler([SetOp(page.name, Lit(number))])},
                )
                entries.append(item(button))
        prev_button = Element(
            "button", [TextNode("Previous")],
            attrs={"type": "button", "class": "v-page-link v-page-step",
                   "disabled": Compare("<=", page, Lit(1))},
            events={"click": _Handler([SetOp(
                page.name, cond(Compare(">", page, Lit(1)),
                                BinOp("-", page, Lit(1)), Lit(1)))])},
        )
        next_button = Element(
            "button", [TextNode("Next")],
            attrs={"type": "button", "class": "v-page-link v-page-step",
                   "disabled": Compare(">=", page, Lit(pages))},
            events={"click": _Handler([SetOp(
                page.name, cond(Compare("<", page, Lit(pages)),
                                BinOp("+", page, Lit(1)), Lit(pages)))])},
        )
        entries.insert(0, item(prev_button))
        if pages > 10:
            counter = Element(
                "span",
                [BindText(FormatString(["Page ", page, f" of {pages}"]))],
                attrs={"class": "v-page-counter"})
            entries.append(item(counter))
        entries.append(item(next_button))

    return Element(
        "nav",
        [Element("ul", entries, attrs={"class": "v-pagination-list"})],
        attrs={"class": "v-pagination", "aria-label": label},
    )


def _page_window(page: int, pages: int) -> list:
    """The classic pagination window: first, last, and a neighborhood
    around the current page, with gaps where pages are elided."""
    if pages <= 7:
        return list(range(1, pages + 1))
    window: list = [1]
    start = max(2, page - 1)
    end = min(pages - 1, page + 1)
    if start > 2:
        window.append("gap")
    window.extend(range(start, end + 1))
    if end < pages - 1:
        window.append("gap")
    window.append(pages)
    return window


def Select(state: Any, *, label: str, options: list[str] | None = None) -> Element:
    from .forms import FieldRef
    if isinstance(state, FieldRef) and options is None:
        options = state.spec.options
    if not options:
        raise VirelCompileError(
            "Select requires options=[...], or a form field whose model type "
            "is a Literal."
        )
    state, extra_attrs, error_node = _unwrap_field(state, "Select")
    option_nodes = [
        Element("option", [TextNode(opt)], attrs={"value": opt}) for opt in options
    ]
    select_el = Element(
        "select",
        option_nodes,
        attrs={"class": "v-input v-select-native", **extra_attrs},
        events={"change": Handler([SetFromEventOp(state.name, "target.value")])},
        bound_props={"value": state},
    )
    # The runtime replaces the native control with a styled combobox and
    # keeps the native element as the source of truth.
    enhanced = Element("div", [select_el], attrs={"class": "v-select"},
                       runtime_binding="select")
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        enhanced,
    ]
    if error_node is not None:
        children.append(error_node)
    return Element("label", children, attrs={"class": "v-field"})


def Checkbox(state: Any, *, label: str) -> Element:
    state, _, error_node = _unwrap_field(state, "Checkbox")
    box = Element(
        "input",
        attrs={"class": "v-checkbox", "type": "checkbox"},
        events={"change": Handler([SetFromEventOp(state.name, "target.checked")])},
        bound_props={"checked": state},
    )
    children: list[Node] = [box, Element("span", [TextNode(label)])]
    if error_node is not None:
        children.append(error_node)
    return Element("label", children, attrs={"class": "v-field-inline"})


def Alert(content: Any, *, intent: str = "neutral") -> Element:
    if intent not in _INTENTS + ("success",):
        raise VirelCompileError(f"Alert intent {intent!r} is not valid.")
    return Element("div", normalize_children((content,)),
                   attrs={"class": f"v-alert v-alert-{intent}", "role": "status"})


def Badge(content: Any, *, intent: str = "neutral") -> Element:
    return Element("span", normalize_children((content,)),
                   attrs={"class": f"v-badge v-badge-{intent}"})


def EmptyState(*, title: str, description: str = "") -> Element:
    children: list[Node] = [Element("p", [TextNode(title)], attrs={"class": "v-empty-title"})]
    if description:
        children.append(Element("p", [TextNode(description)], attrs={"class": "v-muted"}))
    return Element("div", children, attrs={"class": "v-empty"})


# --------------------------------------------------------------------------
# Additional form controls
# --------------------------------------------------------------------------

def Textarea(state: State, *, label: str, placeholder: str = "",
             rows: int = 4) -> Element:
    if not isinstance(state, State):
        raise VirelCompileError("Textarea requires a ui.state(...) value.")
    area = Element(
        "textarea",
        attrs={"class": "v-input", "rows": rows,
               "placeholder": placeholder or None},
        events={"input": Handler([SetFromEventOp(state.name, "target.value")])},
        bound_props={"value": state},
    )
    return Element("label", [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        area,
    ], attrs={"class": "v-field"})


def NumberField(state: Any, *, label: str, min: float | None = None,
                max: float | None = None, step: float | None = None) -> Element:
    state, extra_attrs, error_node = _unwrap_field(state, "NumberField")
    field = Element(
        "input",
        attrs={"class": "v-input", "type": "number",
               "min": min, "max": max, "step": step,
               **{k: v for k, v in extra_attrs.items() if k != "type"}},
        events={"input": Handler([SetFromEventOp(state.name, "target.valueAsNumber")])},
        bound_props={"value": state},
    )
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        field,
    ]
    if error_node is not None:
        children.append(error_node)
    return Element("label", children, attrs={"class": "v-field"})


def Slider(state: State, *, label: str, min: float = 0, max: float = 100,
           step: float = 1) -> Element:
    if not isinstance(state, State):
        raise VirelCompileError("Slider requires a ui.state(...) value.")
    control = Element(
        "input",
        attrs={"class": "v-slider", "type": "range",
               "min": min, "max": max, "step": step},
        events={"input": Handler([SetFromEventOp(state.name, "target.valueAsNumber")])},
        bound_props={"value": state},
    )
    return Element("label", [
        Element("div", [
            Element("span", [TextNode(label)], attrs={"class": "v-label"}),
            Element("span", [BindText(state)], attrs={"class": "v-label v-muted"}),
        ], attrs={"class": "v-row", "style": "justify-content: space-between"}),
        control,
    ], attrs={"class": "v-field"})


def Switch(state: State, *, label: str) -> Element:
    if not isinstance(state, State):
        raise VirelCompileError("Switch requires a ui.state(...) value.")
    control = Element(
        "input",
        attrs={"class": "v-switch", "type": "checkbox", "role": "switch"},
        events={"change": Handler([SetFromEventOp(state.name, "target.checked")])},
        bound_props={"checked": state},
    )
    return Element("label", [control, Element("span", [TextNode(label)])],
                   attrs={"class": "v-field-inline"})


def RadioGroup(state: State, *, label: str, options: list[str]) -> Element:
    if not isinstance(state, State):
        raise VirelCompileError("RadioGroup requires a ui.state(...) value.")
    from .expr import Compare, Lit
    items = []
    for option in options:
        radio = Element(
            "input",
            attrs={"class": "v-radio", "type": "radio",
                   "name": state.name, "value": option},
            events={"change": Handler([SetFromEventOp(state.name, "target.value")])},
            bound_props={"checked": Compare("==", state, Lit(option))},
        )
        items.append(Element("label", [radio, Element("span", [TextNode(option)])],
                             attrs={"class": "v-field-inline"}))
    return Element("fieldset", [
        Element("legend", [TextNode(label)], attrs={"class": "v-label"}),
        Element("div", items, attrs={"class": "v-stack",
                                     "style": _gap_style(2)}),
    ], attrs={"class": "v-fieldset"})


# --------------------------------------------------------------------------
# Interaction patterns
# --------------------------------------------------------------------------

def Tabs(tabs: dict[str, Any], *, label: str = "Tabs") -> Element:
    """Accessible tabs. Selection state lives in the browser; both panels
    stay in the DOM so nested bindings keep working."""
    if not tabs:
        raise VirelCompileError("Tabs requires at least one entry.")
    from .expr import Compare, Lit, Ternary
    names = list(tabs)
    selected = State(names[0])
    buttons = []
    for name in names:
        is_selected = Compare("==", selected, Lit(name))
        buttons.append(Element(
            "button",
            [TextNode(name)],
            attrs={
                "class": "v-tab",
                "type": "button",
                "role": "tab",
                "aria-selected": Ternary(is_selected, Lit("true"), Lit("false")),
            },
            events={"click": Handler([SetOp(selected.name, Lit(name))])},
        ))
    tablist = Element("div", buttons,
                      attrs={"class": "v-tablist", "role": "tablist",
                             "aria-label": label})
    panels: list[Node] = []
    for name in names:
        content = Element("div", normalize_children((tabs[name],)),
                          attrs={"class": "v-tabpanel", "role": "tabpanel"})
        panels.append(When(Compare("==", selected, Lit(name)), then=content))
    return Element("div", [tablist, *panels], attrs={"class": "v-tabs"})


def Dialog(*children: Any, open: State, title: str) -> Element:
    """Modal dialog on the native <dialog> element: focus trapping and
    Escape handling come from the platform. Visibility is driven by a
    boolean state so it stays inspectable and testable."""
    if not isinstance(open, State):
        raise VirelCompileError(
            "Dialog requires open=ui.state(False) to control visibility."
        )
    from .expr import Lit
    from .icons import Icon
    close = Handler([SetOp(open.name, Lit(False))])
    header = Element("div", [
        Element("h2", [TextNode(title)], attrs={"class": "v-heading"}),
        Element("button", [Icon("x", label="Close dialog")],
                attrs={"class": "v-btn v-btn-neutral v-btn-sm",
                       "type": "button"},
                events={"click": close}),
    ], attrs={"class": "v-dialog-header"})
    body = Element("div", normalize_children(children),
                   attrs={"class": "v-stack", "style": _gap_style(3)})
    return Element(
        "dialog",
        [header, body],
        attrs={"class": "v-dialog", "aria-label": title},
        events={"cancel": close, "close": close},
        bound_props={"open": open},
    )


def Accordion(items: dict[str, Any]) -> Element:
    """Disclosure list on native <details>/<summary>."""
    sections = []
    for title, content in items.items():
        sections.append(Element("details", [
            Element("summary", [TextNode(title)]),
            Element("div", normalize_children((content,)),
                    attrs={"class": "v-accordion-body"}),
        ], attrs={"class": "v-accordion-item"}))
    return Element("div", sections, attrs={"class": "v-accordion"})


def Tooltip(child: Any, *, text: str) -> Element:
    return Element("span", normalize_children((child,)),
                   attrs={"class": "v-tooltip", "data-tip": text,
                          "tabindex": "0", "aria-label": text})


# --------------------------------------------------------------------------
# Data display
# --------------------------------------------------------------------------

def Table(*, columns: list[str], rows: list[list[Any]],
          caption: str | None = None) -> Element:
    head = Element("thead", [Element("tr", [
        Element("th", normalize_children((col,)), attrs={"scope": "col"})
        for col in columns
    ])])
    body_rows = []
    for row in rows:
        if len(row) != len(columns):
            raise VirelCompileError(
                f"Table row {row!r} has {len(row)} cells but there are "
                f"{len(columns)} columns."
            )
        body_rows.append(Element("tr", [
            Element("td", normalize_children((cell,))) for cell in row
        ]))
    children: list[Node] = []
    if caption:
        children.append(Element("caption", [TextNode(caption)]))
    children.extend([head, Element("tbody", body_rows)])
    return Element("div", [Element("table", children, attrs={"class": "v-table"})],
                   attrs={"class": "v-table-wrap"})


def Stat(*, label: str, value: Any, hint: str | None = None) -> Element:
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-stat-label"}),
        Element("span", normalize_children((value,)), attrs={"class": "v-stat-value"}),
    ]
    if hint:
        children.append(Element("span", [TextNode(hint)],
                                attrs={"class": "v-hint"}))
    return Element("div", children, attrs={"class": "v-stat"})


def Progress(value: Any, *, max: float = 100, label: str) -> Element:
    from .expr import Expr
    bound = {"value": value} if isinstance(value, Expr) else {}
    attrs: dict[str, Any] = {"class": "v-progress", "max": max,
                             "aria-label": label}
    if not bound:
        attrs["value"] = value
    return Element("progress", attrs=attrs, bound_props=bound)


def Spinner(*, label: str = "Loading") -> Element:
    from .icons import Icon
    return Element("span", [Icon("loader", size=18)],
                   attrs={"class": "v-spinner", "role": "status",
                          "aria-label": label})


def Skeleton(*, lines: int = 3) -> Element:
    bars = [Element("div", attrs={"class": "v-skeleton-line"})
            for _ in range(lines)]
    return Element("div", bars, attrs={"class": "v-skeleton",
                                       "aria-hidden": "true"})


def Avatar(name: str, *, src: str | None = None, size: int = 32) -> Element:
    style = f"width: {size}px; height: {size}px"
    if src:
        return Element("img", attrs={"class": "v-avatar", "src": src,
                                     "alt": name, "style": style})
    initials = "".join(part[0].upper() for part in name.split()[:2] if part)
    return Element("span", [TextNode(initials or "?")],
                   attrs={"class": "v-avatar v-avatar-initials",
                          "style": style, "aria-label": name,
                          "role": "img"})


def Breadcrumbs(items: list[tuple[str, str | None]]) -> Element:
    crumbs = []
    for index, (text, target) in enumerate(items):
        last = index == len(items) - 1
        if target and not last:
            crumbs.append(Element("li", [Link(text, to=target)]))
        else:
            crumbs.append(Element("li", [Element(
                "span", [TextNode(text)],
                attrs={"aria-current": "page"} if last else {},
            )]))
    return Element("nav", [Element("ol", crumbs, attrs={"class": "v-breadcrumbs"})],
                   attrs={"aria-label": "Breadcrumb"})


def Each(items: Any, *, render: Callable[[Any], Any], tag: str = "div",
         gap: int | None = 3, key: Callable[[Any], Any] | None = None,
         animate: Any = None, reorderable: bool = False,
         on_reorder: Any = None) -> Node:
    """Reactive list rendering. ``render`` receives a symbolic item and is
    traced once into a template. Items may carry event handlers (delegated
    from the container). With ``key``, unchanged items keep their DOM nodes
    across re-renders. With ``animate`` (a ui.Motion or preset name), new
    items animate in, removed items animate out, and layout=True makes
    reordered items glide to their new position.

    ``reorderable=True`` adds drag-and-drop (SPEC 11.1): every item gets
    a drag handle that also works from the keyboard (Space grabs, arrows
    move, Space drops, Escape cancels, with changes announced to screen
    readers). When ``items`` is a ui.state list, the new order writes
    back automatically; otherwise pass on_reorder=, typically
    ``ui.set_from_event(items, "detail.items")``."""
    from .expr import Handler, SetFromEventOp, State
    from .nodes import EachNode
    handler = None
    if reorderable:
        if on_reorder is not None:
            handler = on_reorder if isinstance(on_reorder, Handler) \
                else _handler(on_reorder)
        elif isinstance(items, State):
            handler = Handler([SetFromEventOp(items.name, "detail.items")])
        else:
            raise VirelCompileError(
                "Each(reorderable=True) over a non-state list needs "
                "on_reorder=, e.g. ui.set_from_event(items, "
                "\"detail.items\").")
    return EachNode(items, render, tag=tag, gap=gap, key=key,
                    animate=animate, reorderable=reorderable,
                    on_reorder=handler)


def Suspense(resource: Any, *, content: Any, fallback: Any = None,
             error: Any = None) -> Node:
    """Loading, error, and ready states for a resource in one place."""
    from .expr import Compare, Lit
    from .resources import Resource
    if not isinstance(resource, Resource):
        raise VirelCompileError(
            "Suspense requires a ui.resource(...) as its first argument."
        )
    content_node = content() if callable(content) else content
    fallback_node = fallback if fallback is not None else Skeleton()
    error_node = error if error is not None else Alert(resource.error,
                                                       intent="danger")
    settled = When(Compare("!=", resource.error, Lit(None)),
                   then=error_node, otherwise=content_node)
    return When(resource.loading, then=fallback_node, otherwise=settled)


def ErrorState(*, title: str = "Something went wrong",
               retry: bool = True) -> Element:
    """Default fallback content for an ErrorBoundary: the error message
    lands in the message slot and the retry button re-binds the content."""
    from .icons import Icon
    children: list[Node] = [
        Element("div", [Icon("alert-triangle", size=20)],
                attrs={"class": "v-error-icon"}),
        Element("p", [TextNode(title)], attrs={"class": "v-empty-title"}),
        Element("p", [], attrs={"class": "v-muted v-text-sm",
                                "data-error-message": "true"}),
    ]
    if retry:
        children.append(Element(
            "button", [TextNode("Try again")],
            attrs={"class": "v-btn v-btn-neutral v-btn-sm",
                   "type": "button", "data-retry": "true"}))
    return Element("div", children, attrs={"class": "v-error-state",
                                           "role": "alert"})


def ErrorBoundary(*children: Any, fallback: Any = None) -> Node:
    """Isolate runtime errors in a subtree: if its bindings throw, the
    fallback renders instead of a broken page region."""
    from .nodes import ErrorBoundaryNode
    fallback_nodes = normalize_children(
        (fallback if fallback is not None else ErrorState(),))
    return ErrorBoundaryNode(normalize_children(children), fallback_nodes)


def Island(*children: Any, load: str = "visible",
           media: str | None = None) -> Node:
    """Defer hydration of a subtree. The content is server-rendered and
    visible immediately; its interactivity activates per the load strategy:
    immediate, idle, visible, interaction, or media (with media="(query)",
    binding when the query matches)."""
    from .nodes import IslandNode
    return IslandNode(normalize_children(children), load, media=media)


def ThemeToggle() -> Element:
    """Cycles the color scheme between system, light, and dark.

    The preference persists in localStorage and applies before first paint
    on every page via the inline theme bootstrap.
    """
    from .icons import Icon
    icons = []
    for mode, name in (("system", "monitor"), ("light", "sun"), ("dark", "moon")):
        icon = Icon(name, size=16)
        icon.attrs["data-icon"] = mode
        icons.append(icon)
    return Element(
        "button",
        icons,
        attrs={"class": "v-btn v-btn-neutral v-btn-sm v-theme-toggle",
               "type": "button", "aria-label": "Color scheme: system"},
        runtime_binding="themeToggle",
    )


# --------------------------------------------------------------------------
# Menus
# --------------------------------------------------------------------------

def Menu(*, trigger: Any, items: list[Any], align: str = "end") -> Element:
    """Dropdown menu. The trigger is any button-like element; items are
    MenuItem and MenuDivider entries. The runtime manages open state,
    keyboard interaction, and flips the panel upward when space below is
    insufficient."""
    if align not in ("start", "end"):
        raise VirelCompileError("Menu align must be 'start' or 'end'.")
    panel = Element("div", normalize_children(tuple(items)),
                    attrs={"class": "v-menu-list", "role": "menu"})
    return Element("div", [*normalize_children((trigger,)), panel],
                   attrs={"class": f"v-menu v-menu-{align}"},
                   runtime_binding="menu")


def MenuItem(label: Any, *, to: str | None = None,
             on_click: Callable[[], None] | None = None,
             icon: str | None = None,
             intent: str = "neutral") -> Element:
    if (to is None) == (on_click is None):
        raise VirelCompileError(
            "MenuItem takes exactly one of to= (a link) or on_click= (an "
            "action)."
        )
    children: list[Node] = []
    if icon:
        from .icons import Icon
        children.append(Icon(icon, size=15))
    children.extend(normalize_children((label,)))
    classes = "v-menu-item"
    if intent == "danger":
        classes += " v-menu-item-danger"
    if to is not None:
        from .security import is_safe_url
        if not is_safe_url(to):
            raise VirelCompileError(f"MenuItem target {to!r} uses a blocked "
                                    "URL scheme.")
        return Element("a", children,
                       attrs={"href": to, "class": classes,
                              "role": "menuitem"})
    return Element("button", children,
                   attrs={"class": classes, "type": "button",
                          "role": "menuitem"},
                   events={"click": _handler(on_click)})


def MenuDivider() -> Element:
    return Element("div", attrs={"class": "v-menu-divider",
                                 "role": "separator"})


# --------------------------------------------------------------------------
# Marketing sections
# --------------------------------------------------------------------------

def Hero(*, title: Any, subtitle: Any = None, eyebrow: Any = None,
         actions: list[Any] | tuple = (), media: Any = None,
         align: str = "center") -> Element:
    """Landing-page hero: eyebrow, display title, subtitle, action row,
    and optional media below or beside the copy."""
    if align not in ("center", "start"):
        raise VirelCompileError("Hero align must be 'center' or 'start'.")
    copy: list[Node] = []
    if eyebrow is not None:
        copy.append(Element("div", normalize_children((eyebrow,)),
                            attrs={"class": "v-hero-eyebrow"}))
    copy.append(Element("h1", normalize_children((title,)),
                        attrs={"class": "v-hero-title"}))
    if subtitle is not None:
        copy.append(Element("p", normalize_children((subtitle,)),
                            attrs={"class": "v-hero-subtitle"}))
    if actions:
        copy.append(Element("div", normalize_children(tuple(actions)),
                            attrs={"class": "v-row v-hero-actions"}))
    children: list[Node] = [Element("div", copy,
                                    attrs={"class": "v-hero-copy"})]
    if media is not None:
        children.append(Element("div", normalize_children((media,)),
                                attrs={"class": "v-hero-media"}))
    return Element("section", children,
                   attrs={"class": f"v-hero v-hero-{align}"})


# --------------------------------------------------------------------------
# App shell
# --------------------------------------------------------------------------

def Footer(*children: Any) -> Element:
    return Element("footer", [
        Element("div", normalize_children(children),
                attrs={"class": "v-footer-inner v-container v-container-lg"}),
    ], attrs={"class": "v-footer"})


def AppShell(*, navigation: Node, content: Any, brand: str = "Virel",
             sidebar: Any = None, footer: Any = None) -> Element:
    """Application frame: sticky header, optional sidebar, main content,
    optional footer. With a sidebar, small screens get an off-canvas
    drawer behind a header toggle."""
    from .expr import Lit, Ternary, not_
    header_children: list[Node] = []
    shell_attrs: dict[str, Any] = {"class": "v-shell"}
    if sidebar is not None:
        from .icons import Icon
        drawer_open = State(False)
        shell_attrs["data-sidebar-open"] = Ternary(drawer_open, Lit("true"),
                                                   Lit("false"))
        header_children.append(Element(
            "button",
            [Icon("menu", label="Toggle navigation")],
            attrs={"class": "v-btn v-btn-neutral v-btn-sm v-btn-ghost "
                            "v-sidebar-toggle", "type": "button"},
            events={"click": Handler([SetOp(drawer_open.name,
                                            not_(drawer_open))])},
        ))
    header_children.append(Element("span", [TextNode(brand)],
                                   attrs={"class": "v-brand"}))
    header_children.append(navigation)
    header = Element("header", [
        Element("div", header_children,
                attrs={"class": "v-shell-header-inner v-container "
                                "v-container-lg"}),
    ], attrs={"class": "v-shell-header"})

    main = Element("main", normalize_children((content,)),
                   attrs={"class": "v-shell-main v-container v-container-lg"})
    if sidebar is not None:
        aside = Element("aside", normalize_children((sidebar,)),
                        attrs={"class": "v-sidebar"})
        body = Element("div", [aside, main], attrs={"class": "v-shell-body"})
    else:
        body = main

    children: list[Node] = [header, body]
    if footer is not None:
        children.extend(normalize_children((footer,)))
    return Element("div", children, attrs=shell_attrs)
