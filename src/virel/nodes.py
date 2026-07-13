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


_STATE_READ_RE = None


def _state_reads(js: str) -> set[str]:
    """State names an expression's JS reads, for the inspector's
    reactive-dependency view. State reads serialize as S.<name>.get()."""
    global _STATE_READ_RE
    if _STATE_READ_RE is None:
        import re
        _STATE_READ_RE = re.compile(r"S\.(\w+)\.get\(\)")
    return set(_STATE_READ_RE.findall(js))


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
        ir = {"kind": "bind_text", "expr": self.expr.js()}
        deps = _state_reads(self.expr.js())
        if deps:
            ir["depends_on"] = sorted(deps)
        return ir


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
        runtime_binding: str | None = None,
        runtime_binding_args: str | None = None,
    ) -> None:
        self.tag = tag
        self.children = children or []
        self.attrs = attrs or {}
        self.events = events or {}
        self.bound_props = bound_props or {}
        self.component = component  # originating @ui.component, for inspection
        self.source: str | None = None  # file:line of the component function
        # Name of a runtime function to bind this element to (e.g. a theme
        # toggle). Compiles to $.name("<id>"), or $.name("<id>", <args>)
        # when runtime_binding_args carries extra JS arguments.
        self.runtime_binding = runtime_binding
        self.runtime_binding_args = runtime_binding_args

    def to_ir(self) -> dict[str, Any]:
        ir: dict[str, Any] = {"kind": "element", "tag": self.tag}
        if self.component:
            ir["component"] = self.component
        if self.source:
            ir["source"] = self.source
        deps: set[str] = set()
        if self.attrs:
            ir["attrs"] = {
                k: (v.js() if isinstance(v, Expr) else v) for k, v in self.attrs.items()
            }
            for value in self.attrs.values():
                if isinstance(value, Expr):
                    deps |= _state_reads(value.js())
        if self.bound_props:
            ir["bound_props"] = {k: v.js() for k, v in self.bound_props.items()}
            for value in self.bound_props.values():
                deps |= _state_reads(value.js())
        if self.events:
            ir["events"] = {k: h.to_ir() for k, h in self.events.items()}
        if deps:
            ir["depends_on"] = sorted(deps)
        if self.children:
            ir["children"] = [c.to_ir() for c in self.children]
        return ir


class When(Node):
    """Reactive conditional rendering. Both branches stay in the DOM; the
    runtime toggles visibility, so nested bindings keep working. With
    animate=, showing and hiding run enter and exit animations."""

    def __init__(self, condition: Any, then: Any, otherwise: Any = None,
                 animate: Any = None) -> None:
        from .motion import coerce_motion
        self.condition = lift(condition)
        self.then = normalize_children(then if isinstance(then, (list, tuple)) else (then,))
        if otherwise is None:
            self.otherwise = []
        else:
            self.otherwise = normalize_children(
                otherwise if isinstance(otherwise, (list, tuple)) else (otherwise,)
            )
        self.motion = coerce_motion(animate)

    def to_ir(self) -> dict[str, Any]:
        ir = {
            "kind": "when",
            "condition": self.condition.js(),
            "then": [c.to_ir() for c in self.then],
            "otherwise": [c.to_ir() for c in self.otherwise],
        }
        if self.motion:
            ir["motion"] = self.motion.config()
        return ir


class EachNode(Node):
    """Reactive list rendering with per-item event handlers.

    The render function is traced once with a symbolic item to produce a
    template. In the browser, items are keyed and reconciled (unchanged
    items keep their DOM nodes), and item events are delegated from the
    list container, so handlers survive re-renders.
    """

    def __init__(self, items: Any, render: Any, tag: str = "div",
                 gap: int | None = None, key: Any = None,
                 animate: Any = None, reorderable: bool = False,
                 on_reorder: Any = None, virtual: bool = False,
                 item_height: int = 40, height: str = "24rem") -> None:
        from .expr import ItemRef, LocalRef, lift
        from .motion import coerce_motion
        self.items = lift(items)
        self.tag = tag
        self.gap = gap
        self.motion = coerce_motion(animate)
        self.reorderable = reorderable
        self.on_reorder = on_reorder
        self.virtual = virtual
        self.item_height = item_height
        self.height = height
        if reorderable and key is None:
            raise VirelCompileError(
                "Each(reorderable=True) requires key= so items keep their "
                "identity while they move.")
        item = ItemRef(LocalRef("item"))
        template = render(item)
        self.key = lift(key(item)) if key is not None else None
        self.template = normalize_children((template,))
        self.handlers: dict[str, dict[str, Any]] = {}
        counter = 0
        for node in self.template:
            counter = self._prepare_template(node, counter)

    def _prepare_template(self, node: Node, counter: int) -> int:
        if isinstance(node, Element):
            if node.bound_props or node.runtime_binding:
                raise VirelCompileError(
                    "Two-way bindings are not supported inside a ui.Each "
                    "item yet. Use per-item event handlers instead."
                )
            if node.events:
                hid = f"h{counter}"
                counter += 1
                node.template_hid = hid
                self.handlers[hid] = node.events
            for child in node.children:
                counter = self._prepare_template(child, counter)
        elif isinstance(node, (When, EachNode)):
            raise VirelCompileError(
                "ui.When and nested ui.Each are not supported inside a "
                "ui.Each item yet. Use ui.cond(...) for conditional values."
            )
        return counter

    def handlers_js(self) -> str:
        groups = []
        for hid, events in self.handlers.items():
            fns = ", ".join(
                f'"{event}": (ev, item) => {{ {handler.js_body()} }}'
                for event, handler in events.items()
            )
            groups.append(f'"{hid}": {{ {fns} }}')
        return "{" + ", ".join(groups) + "}"

    def to_ir(self) -> dict[str, Any]:
        return {
            "kind": "each",
            "items": self.items.js(),
            "tag": self.tag,
            "key": self.key.js() if self.key is not None else None,
            "handlers": {
                hid: {event: h.to_ir() for event, h in events.items()}
                for hid, events in self.handlers.items()
            },
            "template": [t.to_ir() for t in self.template],
        }


def _template_js(nodes: list[Node]) -> str:
    """Render template nodes as the body of a JS template literal."""
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, TextNode):
            parts.append(_js_literal_escape(html.escape(node.text)))
        elif isinstance(node, BindText):
            parts.append("${$.esc(" + node.expr.js() + ")}")
        elif isinstance(node, RawHTML):
            parts.append(_js_literal_escape(node.markup))
        elif isinstance(node, Element):
            parts.append(_template_element_js(node))
        else:
            raise VirelCompileError(
                f"{type(node).__name__} is not supported inside a ui.Each item."
            )
    return "".join(parts)


_URL_ATTRS = {"href", "src", "action", "formaction", "poster"}


def _template_element_js(node: Element) -> str:
    out = [f"<{node.tag}"]
    hid = getattr(node, "template_hid", None)
    if hid:
        out.append(f' data-vh="{hid}"')
    for key, value in node.attrs.items():
        if value is None or value is False:
            continue
        if isinstance(value, Expr):
            if key in _URL_ATTRS:
                # Dynamic URLs are scheme-checked at render time so item
                # data cannot inject javascript: links (SPEC 18).
                out.append(f' {key}="' + "${$.esc($.safeUrl(" + value.js() + '))}"')
            else:
                out.append(f' {key}="' + "${$.esc(" + value.js() + ')}"')
        elif value is True:
            out.append(f" {key}")
        else:
            out.append(f' {key}="{_js_literal_escape(html.escape(str(value), quote=True))}"')
    if node.tag in _VOID_TAGS:
        out.append(">")
        return "".join(out)
    out.append(">")
    out.append(_template_js(node.children))
    out.append(f"</{node.tag}>")
    return "".join(out)


def _js_literal_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")


def template_html(nodes: list[Node], env: dict[str, Any]) -> str:
    """Render template nodes to HTML with a concrete item in the env."""
    from .expr import _js_like_str
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, TextNode):
            parts.append(html.escape(node.text))
        elif isinstance(node, BindText):
            parts.append(html.escape(_js_like_str(node.expr.evaluate(env))))
        elif isinstance(node, RawHTML):
            parts.append(node.markup)
        elif isinstance(node, Element):
            out = [f"<{node.tag}"]
            hid = getattr(node, "template_hid", None)
            if hid:
                out.append(f' data-vh="{hid}"')
            for key, value in node.attrs.items():
                if value is None or value is False:
                    continue
                if isinstance(value, Expr):
                    rendered = str(value.evaluate(env))
                    if key in _URL_ATTRS:
                        from .security import safe_url
                        rendered = safe_url(rendered)
                    out.append(f' {key}="{html.escape(rendered, quote=True)}"')
                elif value is True:
                    out.append(f" {key}")
                else:
                    out.append(f' {key}="{html.escape(str(value), quote=True)}"')
            out.append(">")
            if node.tag not in _VOID_TAGS:
                out.append(template_html(node.children, env))
                out.append(f"</{node.tag}>")
            parts.append("".join(out))
    return "".join(parts)


class ErrorBoundaryNode(Node):
    """Isolates runtime errors in a subtree (SPEC 8.11). If binding the
    content throws, the fallback is shown instead, with the error message
    and an optional retry that re-binds the content."""

    def __init__(self, content: list[Node], fallback: list[Node]) -> None:
        self.content = content
        self.fallback = fallback

    def to_ir(self) -> dict[str, Any]:
        return {
            "kind": "error_boundary",
            "content": [c.to_ir() for c in self.content],
            "fallback": [f.to_ir() for f in self.fallback],
        }


_ISLAND_STRATEGIES = ("immediate", "idle", "visible", "interaction", "media")


class IslandNode(Node):
    """A hydration boundary (SPEC 9.7). The subtree server-renders like
    everything else, but its bindings activate lazily by strategy: on idle,
    when scrolled into view, on first interaction, or when a media query
    matches."""

    def __init__(self, children: list[Node], load: str,
                 media: str | None = None) -> None:
        if load not in _ISLAND_STRATEGIES:
            raise VirelCompileError(
                f"Island load={load!r} is not a strategy. Use one of: "
                f"{', '.join(_ISLAND_STRATEGIES)}."
            )
        if load == "media" and not media:
            raise VirelCompileError(
                'Island load="media" requires media="(query)".'
            )
        self.children = children
        self.load = load
        self.media = media

    def to_ir(self) -> dict[str, Any]:
        return {
            "kind": "island",
            "load": self.load,
            "media": self.media,
            "children": [c.to_ir() for c in self.children],
        }


class PageNode(Node):
    """Root of a compiled page."""

    def __init__(self, children: list[Node], title: str, meta: dict[str, str],
                 head_modules: list[str],
                 canonical: str | None = None) -> None:
        self.children = children
        self.title = title
        self.meta = meta
        self.head_modules = head_modules  # extra JS modules (web components)
        self.canonical = canonical

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
            motion = ""
            if node.motion:
                import json as _json
                motion = ", " + _json.dumps(node.motion.config())
            self.bindings.append(
                f'$.bindShow("{then_id}", () => !!{cond_js}{motion});')
            self.bindings.append(
                f'$.bindShow("{else_id}", () => !{cond_js}{motion});')
            then_html = self.emit_children(node.then)
            else_html = self.emit_children(node.otherwise)
            then_style = "" if visible else ' style="display:none"'
            else_style = ' style="display:none"' if visible else ""
            return (
                f'<div data-v="{then_id}" class="v-when"{then_style}>{then_html}</div>'
                f'<div data-v="{else_id}" class="v-when"{else_style}>{else_html}</div>'
            )

        if isinstance(node, ErrorBoundaryNode):
            vid = self.assign_id()
            outer = self.bindings
            self.bindings = []
            # A boundary isolates server-side rendering failures too: the
            # fallback renders in place of the broken content and no client
            # bindings are emitted for the failed subtree.
            try:
                content_html = self.emit_children(node.content)
                captured = self.bindings
                failed = False
            except Exception:
                content_html = ""
                captured = []
                failed = True
            self.bindings = outer
            fallback_html = self.emit_children(node.fallback)
            if failed:
                return (
                    f'<div data-v="{vid}" class="v-boundary" '
                    f'style="display:contents">'
                    f'<div class="v-boundary-content" style="display:none">'
                    f"</div>"
                    f'<div class="v-boundary-fallback" '
                    f'style="display:contents">{fallback_html}</div></div>'
                )
            body = " ".join(captured)
            self.bindings.append(
                f'$.boundary("{vid}", () => {{ {body} }});')
            return (
                f'<div data-v="{vid}" class="v-boundary" style="display:contents">'
                f'<div class="v-boundary-content" style="display:contents">'
                f"{content_html}</div>"
                f'<div class="v-boundary-fallback" style="display:none">'
                f"{fallback_html}</div></div>"
            )

        if isinstance(node, IslandNode):
            vid = self.assign_id()
            # Capture the subtree's bindings so they can be deferred as one
            # unit; server-rendered HTML is emitted normally either way.
            outer = self.bindings
            self.bindings = []
            inner_html = self.emit_children(node.children)
            captured = self.bindings
            self.bindings = outer
            body = " ".join(captured)
            import json as _json
            media = (_json.dumps(node.media) if node.load == "media"
                     else "null")
            self.bindings.append(
                f'$.island("{vid}", "{node.load}", () => {{ {body} }}, '
                f"{media});")
            return (f'<div data-v="{vid}" class="v-island" '
                    f'style="display:contents">{inner_html}</div>')

        if isinstance(node, EachNode):
            vid = self.assign_id()
            js_item = "(item) => `" + _template_js(node.template) + "`"
            js_key = f"(item) => {node.key.js()}" if node.key is not None else "null"
            import json as _json
            initial = node.items.evaluate(self.env) or []
            if node.virtual:
                # Virtual list: only the visible window exists in the DOM.
                self.bindings.append(
                    f'$.bindVirtualList("{vid}", () => {node.items.js()} '
                    f"|| [], {js_item}, {js_key}, {node.handlers_js()}, "
                    f"{{itemHeight: {node.item_height}}});")
                return (f'<div data-v="{vid}" class="v-vlist" '
                        f'style="height: {node.height}; overflow-y: auto">'
                        "</div>")
            js_motion = (_json.dumps(node.motion.config()) if node.motion
                         else "null")
            js_reorder = "true" if node.reorderable else "false"
            self.bindings.append(
                f'$.bindList("{vid}", () => {node.items.js()} || [], '
                f"{js_item}, {js_key}, {node.handlers_js()}, {js_motion}, "
                f"{js_reorder});")
            if node.on_reorder is not None:
                self.bindings.append(
                    f'$.on("{vid}", "virel-reorder", '
                    f"(ev) => {{ {node.on_reorder.js_body()} }});")
            initial = node.items.evaluate(self.env) or []
            rendered = "".join(
                f'<div class="v-each-item" style="display:contents" data-vi="{index}">'
                + template_html(node.template, self.env | {"item": item})
                + "</div>"
                for index, item in enumerate(initial)
            )
            style = ""
            if node.gap is not None:
                style = f' style="gap: calc(var(--v-space) * {node.gap})"'
            return (f'<{node.tag} data-v="{vid}" class="v-each"{style}>'
                    f"{rendered}</{node.tag}>")

        if isinstance(node, Element):
            return self._emit_element(node)

        if isinstance(node, PageNode):
            return self.emit_children(node.children)

        raise VirelCompileError(f"Unknown IR node: {type(node).__name__}")

    def _emit_element(self, node: Element) -> str:
        needs_id = bool(node.events or node.bound_props or node.runtime_binding)
        vid = self.assign_id() if needs_id else None
        if node.runtime_binding:
            extra = (", " + node.runtime_binding_args
                     if node.runtime_binding_args else "")
            self.bindings.append(
                f'$.{node.runtime_binding}("{vid}"{extra});')

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
                if key in _URL_ATTRS:
                    from .security import safe_url
                    self.bindings.append(
                        f'$.bindAttr("{vid}", "{key}", () => $.safeUrl({value.js()}));')
                    if initial is not None and initial is not False:
                        parts.append(
                            f' {key}="{html.escape(safe_url(initial), quote=True)}"')
                else:
                    self.bindings.append(
                        f'$.bindAttr("{vid}", "{key}", () => {value.js()});')
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
