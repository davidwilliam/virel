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
         meta: dict[str, str] | None = None) -> PageNode:
    return PageNode(
        children=normalize_children(children),
        title=title,
        meta=meta or {},
        head_modules=list(_page_modules),
    )


def _classes(base: str, class_name: str | None) -> str:
    return f"{base} {class_name}" if class_name else base


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


def Card(*children: Any, gap: int = 3,
         class_name: str | None = None) -> Element:
    return Element("div", normalize_children(children),
                   attrs={"class": _classes("v-card v-stack", class_name),
                          "style": _gap_style(gap)})


def Divider() -> Element:
    return Element("hr", attrs={"class": "v-divider"})


def Spacer() -> Element:
    return Element("div", attrs={"class": "v-spacer", "aria-hidden": "true"})


# --------------------------------------------------------------------------
# Semantic elements
# --------------------------------------------------------------------------

def Heading(text: Any, level: int = 2) -> Element:
    if level not in (1, 2, 3, 4, 5, 6):
        raise VirelCompileError(f"Heading level must be 1-6, got {level!r}.")
    return Element(f"h{level}", normalize_children((text,)), attrs={"class": "v-heading"})


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
         gap: int | None = 3, key: Callable[[Any], Any] | None = None) -> Node:
    """Reactive list rendering. ``render`` receives a symbolic item and is
    traced once into a template. Items may carry event handlers (delegated
    from the container). With ``key``, unchanged items keep their DOM nodes
    across re-renders."""
    from .nodes import EachNode
    return EachNode(items, render, tag=tag, gap=gap, key=key)


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


def Island(*children: Any, load: str = "visible") -> Node:
    """Defer hydration of a subtree. The content is server-rendered and
    visible immediately; its interactivity activates per the load strategy:
    immediate, idle, visible, or interaction."""
    from .nodes import IslandNode
    return IslandNode(normalize_children(children), load)


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
