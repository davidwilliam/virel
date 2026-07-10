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


def _handler(fn: Callable[[], None] | Handler) -> Handler:
    if isinstance(fn, Handler):
        return fn
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


def Stack(*children: Any, gap: int = 4, align: str = "stretch") -> Element:
    style = _gap_style(gap, f"align-items: {_ALIGN[align]}")
    return Element("div", normalize_children(children),
                   attrs={"class": "v-stack", "style": style})


def Row(*children: Any, gap: int = 3, align: str = "center",
        justify: str = "start", wrap: bool = False) -> Element:
    extra = f"align-items: {_ALIGN[align]}; justify-content: {_JUSTIFY[justify]}"
    if wrap:
        extra += "; flex-wrap: wrap"
    return Element("div", normalize_children(children),
                   attrs={"class": "v-row", "style": _gap_style(gap, extra)})


def Container(*children: Any, width: str = "md") -> Element:
    return Element("div", normalize_children(children),
                   attrs={"class": f"v-container v-container-{width}"})


def Section(*children: Any, gap: int = 6) -> Element:
    return Element("section", normalize_children(children),
                   attrs={"class": "v-stack v-section", "style": _gap_style(gap)})


def Card(*children: Any, gap: int = 3) -> Element:
    return Element("div", normalize_children(children),
                   attrs={"class": "v-card v-stack", "style": _gap_style(gap)})


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


def Code(content: Any, block: bool = False) -> Element:
    inner = Element("code", normalize_children((content,)))
    if block:
        return Element("pre", [inner], attrs={"class": "v-code"})
    inner.attrs["class"] = "v-code-inline"
    return inner


def Link(text: Any, to: str, *, external: bool = False) -> Element:
    attrs: dict[str, Any] = {"href": to, "class": "v-link"}
    if external:
        attrs["rel"] = "noopener noreferrer"
        attrs["target"] = "_blank"
    return Element("a", normalize_children((text,)), attrs=attrs)


def Image(src: str, alt: str, *, width: int | None = None) -> Element:
    # Accessibility is a correctness property (SPEC 6.5): alt is required.
    if alt is None:
        raise VirelCompileError("Image requires alt text (use alt='' only for decorative images).")
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
           disabled: Any = None, kind: str = "button",
           aria_label: str | None = None) -> Element:
    if intent not in _INTENTS:
        raise VirelCompileError(
            f"intent={intent!r} is not valid. Use one of: {', '.join(_INTENTS)}."
        )
    attrs: dict[str, Any] = {
        "class": f"v-btn v-btn-{intent} v-btn-{size}",
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
    if not has_text and "aria-label" not in button.attrs:
        raise VirelCompileError(
            "Icon-only buttons must set aria_label so the control has an "
            "accessible name (SPEC 11.2)."
        )


def TextField(state: State, *, label: str, placeholder: str = "",
              kind: str = "text", description: str | None = None) -> Element:
    """Labeled input with two-way binding to a state."""
    if not isinstance(state, State):
        raise VirelCompileError(
            "TextField requires a ui.state(...) value as its first argument."
        )
    input_events = {"input": Handler([SetFromEventOp(state.name, "target.value")])}
    input_el = Element(
        "input",
        attrs={"class": "v-input", "type": kind, "placeholder": placeholder or None},
        events=input_events,
        bound_props={"value": state},
    )
    children: list[Node] = [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        input_el,
    ]
    if description:
        children.append(Element("span", [TextNode(description)], attrs={"class": "v-hint"}))
    return Element("label", children, attrs={"class": "v-field"})


def Select(state: State, *, label: str, options: list[str]) -> Element:
    if not isinstance(state, State):
        raise VirelCompileError("Select requires a ui.state(...) value as its first argument.")
    option_nodes = [
        Element("option", [TextNode(opt)], attrs={"value": opt}) for opt in options
    ]
    select_el = Element(
        "select",
        option_nodes,
        attrs={"class": "v-input"},
        events={"change": Handler([SetFromEventOp(state.name, "target.value")])},
        bound_props={"value": state},
    )
    return Element("label", [
        Element("span", [TextNode(label)], attrs={"class": "v-label"}),
        select_el,
    ], attrs={"class": "v-field"})


def Checkbox(state: State, *, label: str) -> Element:
    if not isinstance(state, State):
        raise VirelCompileError("Checkbox requires a ui.state(...) value as its first argument.")
    box = Element(
        "input",
        attrs={"class": "v-checkbox", "type": "checkbox"},
        events={"change": Handler([SetFromEventOp(state.name, "target.checked")])},
        bound_props={"checked": state},
    )
    return Element("label", [box, Element("span", [TextNode(label)])],
                   attrs={"class": "v-field-inline"})


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
# App shell
# --------------------------------------------------------------------------

def AppShell(*, navigation: Node, content: Any, brand: str = "Virel") -> Element:
    header = Element("header", [
        Element("div", [
            Element("span", [TextNode(brand)], attrs={"class": "v-brand"}),
            navigation,
        ], attrs={"class": "v-shell-header-inner v-container v-container-lg"}),
    ], attrs={"class": "v-shell-header"})
    main = Element("main", normalize_children((content,)),
                   attrs={"class": "v-shell-main v-container v-container-lg"})
    return Element("div", [header, main], attrs={"class": "v-shell"})
