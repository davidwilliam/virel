"""Virel UI Intermediate Representation.

The IR is the central architectural boundary (SPEC 9.2): a versioned,
deterministic, serializable tree describing elements, reactive bindings,
event handlers and accessibility metadata. Pages compile to IR first; HTML
and JavaScript are emitted from the IR, never directly from Python source.
"""

from __future__ import annotations

import html
from typing import Any

from .expr import Expr, Handler, VirelCompileError, lift, parse_sentinels

IR_VERSION = "0.1"

_VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "source"}


class Node:
    """Base IR node."""

    def to_ir(self) -> dict[str, Any]:
        raise NotImplementedError


def normalize_children(children: tuple[Any, ...]) -> list[Node]:
    """Coerce component-call children into IR nodes.

    Accepts nodes, strings (possibly containing reactive f-string
    sentinels), reactive expressions, lists of nodes, and None.
    """
    out: list[Node] = []
    for child in children:
        if child is None:
            continue
        if isinstance(child, Node):
            out.append(child)
        elif isinstance(child, Expr):
            out.append(BindText(child))
        elif isinstance(child, str):
            parsed = parse_sentinels(child)
            out.append(BindText(parsed) if isinstance(parsed, Expr) else TextNode(parsed))
        elif isinstance(child, (int, float)):
            out.append(TextNode(str(child)))
        elif isinstance(child, (list, tuple)):
            out.extend(normalize_children(tuple(child)))
        else:
            raise VirelCompileError(
                f"Cannot render a value of type {type(child).__name__!r} as a "
                "child. Pass ui components, strings, numbers, or reactive "
                "values."
            )
    return out


class TextNode(Node):
    def __init__(self, text: str) -> None:
        self.text = text

    def to_ir(self) -> dict[str, Any]:
        return {"kind": "text", "text": self.text}


class BindText(Node):
    """Text content that tracks a reactive expression."""

    def __init__(self, expr: Expr) -> None:
        self.expr = expr

    def to_ir(self) -> dict[str, Any]:
        return {"kind": "bind_text", "expr": self.expr.js()}


class RawHTML(Node):
    """Explicit unsafe HTML (SPEC 18.2: escaping is automatic elsewhere)."""

    def __init__(self, markup: str, reason: str) -> None:
        if not reason:
            raise VirelCompileError(
                "ui.unsafe_html requires a `reason` explaining why escaped "
                "rendering is not sufficient."
            )
        self.markup, self.reason = markup, reason

    def to_ir(self) -> dict[str, Any]:
        return {"kind": "raw_html", "reason": self.reason}


class Element(Node):
    def __init__(
        self,
        tag: str,
        children: list[Node] | None = None,
        attrs: dict[str, Any] | None = None,
        events: dict[str, Handler] | None = None,
        bound_props: dict[str, Expr] | None = None,
        component: str | None = None,
    ) -> None:
        self.tag = tag
        self.children = children or []
        self.attrs = attrs or {}
        self.events = events or {}
        self.bound_props = bound_props or {}
        self.component = component  # originating @ui.component, for inspection
        self.source: str | None = None  # file:line of the component function

    def to_ir(self) -> dict[str, Any]:
        ir: dict[str, Any] = {"kind": "element", "tag": self.tag}
        if self.component:
            ir["component"] = self.component
        if self.source:
            ir["source"] = self.source
        if self.attrs:
            ir["attrs"] = {
                k: (v.js() if isinstance(v, Expr) else v) for k, v in self.attrs.items()
            }
        if self.bound_props:
            ir["bound_props"] = {k: v.js() for k, v in self.bound_props.items()}
        if self.events:
            ir["events"] = {k: h.to_ir() for k, h in self.events.items()}
        if self.children:
            ir["children"] = [c.to_ir() for c in self.children]
        return ir


class When(Node):
    """Reactive conditional rendering. Both branches stay in the DOM; the
    runtime toggles visibility, so nested bindings keep working."""

    def __init__(self, condition: Any, then: Any, otherwise: Any = None) -> None:
        self.condition = lift(condition)
        self.then = normalize_children(then if isinstance(then, (list, tuple)) else (then,))
        if otherwise is None:
            self.otherwise = []
        else:
            self.otherwise = normalize_children(
                otherwise if isinstance(otherwise, (list, tuple)) else (otherwise,)
            )

    def to_ir(self) -> dict[str, Any]:
        return {
            "kind": "when",
            "condition": self.condition.js(),
            "then": [c.to_ir() for c in self.then],
            "otherwise": [c.to_ir() for c in self.otherwise],
        }


class PageNode(Node):
    """Root of a compiled page."""

    def __init__(self, children: list[Node], title: str, meta: dict[str, str],
                 head_modules: list[str]) -> None:
        self.children = children
        self.title = title
        self.meta = meta
        self.head_modules = head_modules  # extra JS modules (web components)

    def to_ir(self) -> dict[str, Any]:
        return {
            "kind": "page",
            "title": self.title,
            "meta": self.meta,
            "head_modules": self.head_modules,
            "children": [c.to_ir() for c in self.children],
        }


# --------------------------------------------------------------------------
# HTML emission with server-side initial values
# --------------------------------------------------------------------------

class Emitter:
    """Walks IR, emitting static HTML plus JS binding statements.

    Reactive expressions are evaluated against the initial state environment
    so server-rendered HTML shows correct initial content, then the same
    expression is emitted as JavaScript for fine-grained updates.
    """

    def __init__(self, env: dict[str, Any]) -> None:
        self.env = env
        self.bindings: list[str] = []
        self._next_id = 0

    def assign_id(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    def emit_children(self, children: list[Node]) -> str:
        return "".join(self.emit(c) for c in children)

    def emit(self, node: Node) -> str:
        if isinstance(node, TextNode):
            return html.escape(node.text)

        if isinstance(node, RawHTML):
            return node.markup

        if isinstance(node, BindText):
            vid = self.assign_id()
            initial = node.expr.evaluate(self.env)
            from .expr import _js_like_str
            self.bindings.append(f'$.bindText("{vid}", () => {node.expr.js()});')
            return f'<span data-v="{vid}">{html.escape(_js_like_str(initial))}</span>'

        if isinstance(node, When):
            then_id = self.assign_id()
            else_id = self.assign_id()
            visible = bool(node.condition.evaluate(self.env))
            cond_js = node.condition.js()
            self.bindings.append(f'$.bindShow("{then_id}", () => !!{cond_js});')
            self.bindings.append(f'$.bindShow("{else_id}", () => !{cond_js});')
            then_html = self.emit_children(node.then)
            else_html = self.emit_children(node.otherwise)
            then_style = "" if visible else ' style="display:none"'
            else_style = ' style="display:none"' if visible else ""
            return (
                f'<div data-v="{then_id}" class="v-when"{then_style}>{then_html}</div>'
                f'<div data-v="{else_id}" class="v-when"{else_style}>{else_html}</div>'
            )

        if isinstance(node, Element):
            return self._emit_element(node)

        if isinstance(node, PageNode):
            return self.emit_children(node.children)

        raise VirelCompileError(f"Unknown IR node: {type(node).__name__}")

    def _emit_element(self, node: Element) -> str:
        needs_id = bool(node.events or node.bound_props)
        vid = self.assign_id() if needs_id else None

        parts = [f"<{node.tag}"]
        if vid:
            parts.append(f' data-v="{vid}"')
        for key, value in node.attrs.items():
            if value is None or value is False:
                continue
            if isinstance(value, Expr):
                initial = value.evaluate(self.env)
                if vid is None:
                    vid = self.assign_id()
                    parts.insert(1, f' data-v="{vid}"')
                self.bindings.append(f'$.bindAttr("{vid}", "{key}", () => {value.js()});')
                if initial is not None and initial is not False:
                    parts.append(f' {key}="{html.escape(str(initial), quote=True)}"')
            elif value is True:
                parts.append(f" {key}")
            else:
                parts.append(f' {key}="{html.escape(str(value), quote=True)}"')

        textarea_initial = None
        for prop, expr in node.bound_props.items():
            initial = expr.evaluate(self.env)
            if node.tag == "dialog" and prop == "open":
                self.bindings.append(f'$.bindDialog("{vid}", () => !!{expr.js()});')
                if initial:
                    parts.append(" open")
                continue
            self.bindings.append(f'$.bindProp("{vid}", "{prop}", () => {expr.js()});')
            if node.tag == "textarea" and prop == "value":
                textarea_initial = initial
            elif prop == "value" and initial not in (None, ""):
                parts.append(f' value="{html.escape(str(initial), quote=True)}"')
            elif prop == "checked" and initial:
                parts.append(" checked")

        for event, handler in node.events.items():
            self.bindings.append(f'$.on("{vid}", "{event}", {handler.js()});')

        if node.tag in _VOID_TAGS:
            parts.append(">")
            return "".join(parts)

        parts.append(">")
        if textarea_initial not in (None, ""):
            parts.append(html.escape(str(textarea_initial)))
        parts.append(self.emit_children(node.children))
        parts.append(f"</{node.tag}>")
        return "".join(parts)
