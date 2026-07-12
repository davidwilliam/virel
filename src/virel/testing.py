"""Component testing from pytest, no browser required (SPEC 16.1).

``render()`` compiles a page the same way the real compiler does, then keeps
the IR tree plus a Python state environment. Queries follow accessibility
semantics (roles, labels), and interactions execute the compiled handlers
against the environment: the exact ops that would run as JavaScript in the
browser run as Python here, including real server-action calls.

    view = ui.test.render(invite_page)
    view.get_by_label("Email").fill("person@example.com")
    view.get_by_role("button", name="Send invitation").click()
    assert view.get_by_text("Invitation sent").is_visible()
"""

from __future__ import annotations

from typing import Any, Callable

from .expr import Expr, TraceContext, VirelCompileError, _js_like_str
from .nodes import (
    BindText,
    EachNode,
    Element,
    ErrorBoundaryNode,
    IslandNode,
    Node,
    PageNode,
    RawHTML,
    TextNode,
    When,
)

_IMPLICIT_ROLES = {
    "button": "button",
    "select": "combobox",
    "textarea": "textbox",
    "dialog": "dialog",
    "nav": "navigation",
    "table": "table",
    "progress": "progressbar",
    "form": "form",
    "fieldset": "group",
    "img": "img",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
}
_INPUT_ROLES = {
    "checkbox": "checkbox",
    "radio": "radio",
    "range": "slider",
    "number": "spinbutton",
}


class TestView:
    __test__ = False  # keep pytest from collecting this class

    def __init__(self, fn: Callable[..., Any], params: dict[str, Any] | None = None,
                 fetch_resources: bool = True,
                 context: dict[str, Any] | None = None) -> None:
        from .context import request_context
        # Context values are read while the page function traces; scope the
        # store to construction so it never leaks between tests.
        with request_context(context):
            with TraceContext() as ctx:
                root = fn(**(params or {}))
                if not isinstance(root, (PageNode, Element)):
                    raise VirelCompileError(
                        "ui.test.render expects a page or component function "
                        "that returns ui.Page(...) or a component node."
                    )
                self.root = root
                self.states = dict(ctx.states)
                self.derived = dict(ctx.derived)
                self.resources = dict(ctx.resources)
                self.effects = list(ctx.effects)
                self.subscriptions = list(ctx.subscriptions)
                self.connections = list(ctx.connections)
            self.env: dict[str, Any] = {
                name: state.initial for name, state in self.states.items()
            }
            self._files: dict[str, list[Any]] = {}
            self.channel_sends: list[tuple[str, dict]] = []
            # Design preferences changed by handlers (ui.set_preference).
            self.preferences: dict[str, str | None] = {}
            # Toasts raised by handlers (ui.notify).
            self.notifications: list[dict[str, Any]] = []
            if fetch_resources:
                # Simulate the browser's initial load: every resource fetches
                # (running the real server action) unless server rendering
                # already populated it.
                for res in self.resources.values():
                    if not res.server_render:
                        res.fetch_into(self.env)
                for sub in self.subscriptions:
                    sub.drain_into(self.env)

    # -- state environment ------------------------------------------------------

    def eval_env(self) -> dict[str, Any]:
        env = dict(self.env)
        for name, derived in self.derived.items():
            env[name] = derived.expr.evaluate(env)
        return env

    def state(self, name: str) -> Any:
        """Read a state value by its generated name (debugging aid)."""
        return self.eval_env()[name]

    def _run_handler(self, handler: Any, ev: Any = None,
                     scope: dict[str, Any] | None = None) -> None:
        before = {
            id(eff): [dep.evaluate(self.eval_env()) for dep in eff.dependencies]
            for eff in self.effects
        }
        working = self.eval_env() | (scope or {})
        working["__files__"] = self._files
        handler.execute(working, ev)
        working.pop("__files__", None)
        self.channel_sends.extend(working.pop("__channel_sends__", []))
        self.preferences.update(working.pop("__preferences__", {}))
        self.notifications.extend(working.pop("__notifications__", []))
        for action_name in working.pop("__invalidated__", []):
            for res in self.resources.values():
                if res.action.name == action_name:
                    res.fetch_into(working)
        for name in self.states:
            self.env[name] = working[name]
        # Effects fire when their dependencies changed, like the browser.
        for _ in range(5):
            fired = False
            for eff in self.effects:
                now = [dep.evaluate(self.eval_env())
                       for dep in eff.dependencies]
                if now != before[id(eff)]:
                    before[id(eff)] = now
                    inner = self.eval_env() | (scope or {})
                    eff.handler.execute(inner, None)
                    for name in self.states:
                        self.env[name] = inner[name]
                    fired = True
            if not fired:
                break

    # -- queries -----------------------------------------------------------------

    def get_by_role(self, role: str, *, name: str | None = None) -> "TestElement":
        matches = self.get_all_by_role(role, name=name)
        return self._single(matches, f"role={role!r}"
                            + (f" name={name!r}" if name else ""))

    def get_all_by_role(self, role: str, *, name: str | None = None) -> list["TestElement"]:
        return [
            e for e in self._walk()
            if e.role == role and (name is None or e.accessible_name == name)
        ]

    def get_by_label(self, label: str) -> "TestElement":
        matches = [
            e for e in self._walk()
            if e.node.tag in ("input", "select", "textarea")
            and e.label_text == label
        ]
        return self._single(matches, f"label={label!r}")

    def get_by_text(self, text: str) -> "TestElement":
        matches = [e for e in self._walk() if e.own_text() == text]
        if matches:
            # Prefer the innermost element: drop any match that contains
            # another match.
            inner = [
                e for e in matches
                if not any(other is not e and _contains(e.node, other.node)
                           for other in matches)
            ]
            return self._single(inner, f"text={text!r}")
        matches = [e for e in self._walk() if text in e.text()]
        matches.sort(key=lambda e: len(e.text()))
        return self._single(matches[:1], f"text={text!r}")

    def query_text(self) -> str:
        """All visible text in the view, for coarse assertions."""
        env = self.eval_env()
        return " ".join(_node_text(self.root, env, visible_only=True,
                                   view=self)).strip()

    def _single(self, matches: list["TestElement"], description: str) -> "TestElement":
        if len(matches) == 1:
            return matches[0]
        if not matches:
            available = sorted({
                f"{e.role}:{e.accessible_name}" for e in self._walk()
                if e.role and e.accessible_name
            })
            raise AssertionError(
                f"No element matches {description}. Elements with roles: "
                + (", ".join(available) or "(none)")
            )
        raise AssertionError(
            f"{len(matches)} elements match {description}; expected exactly one."
        )

    # -- traversal ---------------------------------------------------------------

    def _walk(self) -> list["TestElement"]:
        found: list[TestElement] = []

        def visit(node: Node, conditions: list[tuple[Expr, bool]],
                  label: str | None, scope: dict[str, Any]) -> None:
            if isinstance(node, Element):
                element = TestElement(self, node, list(conditions), label,
                                      scope)
                found.append(element)
                child_label = label
                if node.tag in ("label", "fieldset"):
                    child_label = _label_text(node) or label
                for child in node.children:
                    visit(child, conditions, child_label, scope)
            elif isinstance(node, When):
                for child in node.then:
                    visit(child, conditions + [(node.condition, True)], label,
                          scope)
                for child in node.otherwise:
                    visit(child, conditions + [(node.condition, False)], label,
                          scope)
            elif isinstance(node, EachNode):
                items = node.items.evaluate(self.eval_env() | scope) or []
                for item in items:
                    for child in node.template:
                        visit(child, conditions, label, scope | {"item": item})
            elif isinstance(node, (PageNode, IslandNode)):
                for child in node.children:
                    visit(child, conditions, label, scope)
            elif isinstance(node, ErrorBoundaryNode):
                for child in node.content:
                    visit(child, conditions, label, scope)

        visit(self.root, [], None, {})
        return found


class TestElement:
    __test__ = False

    def __init__(self, view: TestView, node: Element,
                 conditions: list[tuple[Expr, bool]], label: str | None,
                 scope: dict[str, Any] | None = None) -> None:
        self.view = view
        self.node = node
        self.conditions = conditions
        self.label_text = label
        self.scope = scope or {}  # item bindings when inside a ui.Each

    def _env(self) -> dict[str, Any]:
        return self.view.eval_env() | self.scope

    # -- semantics ----------------------------------------------------------------

    @property
    def role(self) -> str | None:
        explicit = self.node.attrs.get("role")
        if isinstance(explicit, str):
            return explicit
        tag = self.node.tag
        if tag == "a":
            return "link" if self.node.attrs.get("href") else None
        if tag and len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
            return "heading"
        if tag == "input":
            kind = self.node.attrs.get("type", "text")
            return _INPUT_ROLES.get(kind, "textbox")
        return _IMPLICIT_ROLES.get(tag)

    @property
    def accessible_name(self) -> str | None:
        aria = self.node.attrs.get("aria-label")
        if isinstance(aria, str):
            return aria
        if self.node.tag in ("input", "select", "textarea"):
            return self.label_text
        text = self.own_text()
        if text:
            return text
        # Fall back to a labeled descendant (e.g. an icon-only button).
        labeled = _first_descendant_label(self.node)
        return labeled

    def own_text(self) -> str:
        return " ".join(_node_text(self.node, self._env())).strip()

    def text(self) -> str:
        return self.own_text()

    def value(self) -> Any:
        bound = self.node.bound_props.get("value")
        if bound is not None:
            return bound.evaluate(self._env())
        return self.node.attrs.get("value")

    def is_checked(self) -> bool:
        bound = self.node.bound_props.get("checked")
        if bound is None:
            return False
        return bool(bound.evaluate(self._env()))

    def is_visible(self) -> bool:
        env = self._env()
        for condition, expected in self.conditions:
            if bool(condition.evaluate(env)) is not expected:
                return False
        if self.node.tag == "dialog":
            bound = self.node.bound_props.get("open")
            if bound is not None and not bound.evaluate(env):
                return False
        return True

    # -- interactions -----------------------------------------------------------------

    def click(self) -> None:
        self._require_visible("click")
        handler = self.node.events.get("click")
        if handler is None:
            raise AssertionError(
                f"<{self.node.tag}> has no click handler."
            )
        if "disabled" in self.node.attrs:
            disabled = self.node.attrs["disabled"]
            value = (disabled.evaluate(self._env())
                     if isinstance(disabled, Expr) else disabled)
            if value:
                raise AssertionError(
                    f"<{self.node.tag}> is disabled and cannot be clicked."
                )
        self.view._run_handler(handler, ev={"target": {}}, scope=self.scope)

    def emit(self, event: str, detail: Any = None) -> None:
        """Dispatch a named event: gesture events (virel-dismiss) and
        custom element events both flow through the same handlers."""
        self._require_visible("emit")
        handler = self.node.events.get(event)
        if handler is None:
            raise AssertionError(
                f"<{self.node.tag}> has no {event!r} handler."
            )
        self.view._run_handler(handler,
                               ev={"target": {}, "detail": detail or {}},
                               scope=self.scope)

    def fill(self, value: Any) -> None:
        self._require_visible("fill")
        handler = self.node.events.get("input") or self.node.events.get("change")
        if handler is None:
            raise AssertionError(
                f"<{self.node.tag}> has no input binding to fill."
            )
        ev = {"target": {"value": value, "valueAsNumber": _as_number(value),
                         "checked": bool(value)}}
        self.view._run_handler(handler, ev, scope=self.scope)

    def select(self, value: str) -> None:
        self._require_visible("select")
        options = [
            child.attrs.get("value")
            for child in self.node.children
            if isinstance(child, Element) and child.tag == "option"
        ]
        if options and value not in options:
            raise AssertionError(
                f"Option {value!r} not in {options}."
            )
        handler = self.node.events.get("change")
        if handler is None:
            raise AssertionError(f"<{self.node.tag}> has no change handler.")
        self.view._run_handler(handler, ev={"target": {"value": value}}, scope=self.scope)

    def submit(self) -> None:
        self._require_visible("submit")
        handler = self.node.events.get("submit")
        if handler is None:
            raise AssertionError(f"<{self.node.tag}> has no submit handler.")
        self.view._run_handler(handler, ev={"target": {}}, scope=self.scope)

    def attach(self, filename: str, content: bytes | str,
               content_type: str = "application/octet-stream") -> None:
        """Attach a file to a ui.FileField for the next upload."""
        ref = self.node.attrs.get("data-vf")
        if ref is None:
            raise AssertionError("attach() targets a ui.FileField input.")
        from .uploads import UploadFile, sanitize_filename
        data = content.encode("utf-8") if isinstance(content, str) else content
        self.view._files.setdefault(ref, []).append(UploadFile(
            filename=sanitize_filename(filename),
            content_type=content_type, data=data))

    def toggle(self) -> None:
        self._require_visible("toggle")
        handler = self.node.events.get("change")
        if handler is None:
            raise AssertionError(f"<{self.node.tag}> has no change handler.")
        ev = {"target": {"checked": not self.is_checked()}}
        self.view._run_handler(handler, ev, scope=self.scope)

    def _require_visible(self, action: str) -> None:
        if not self.is_visible():
            raise AssertionError(
                f"Cannot {action} <{self.node.tag}>: the element is not "
                "visible in the current state."
            )


def _contains(parent: Node, target: Node) -> bool:
    if isinstance(parent, Element):
        children: list[Node] = parent.children
    elif isinstance(parent, When):
        children = parent.then + parent.otherwise
    elif isinstance(parent, PageNode):
        children = parent.children
    else:
        return False
    for child in children:
        if child is target or _contains(child, target):
            return True
    return False


def _first_descendant_label(node: Element) -> str | None:
    for child in node.children:
        if isinstance(child, Element):
            aria = child.attrs.get("aria-label")
            if isinstance(aria, str):
                return aria
            nested = _first_descendant_label(child)
            if nested:
                return nested
    return None


def _label_text(label_el: Element) -> str | None:
    for child in label_el.children:
        if isinstance(child, Element) and child.tag in ("span", "legend"):
            classes = child.attrs.get("class", "")
            if "v-label" in str(classes) or child.tag == "legend":
                texts = [c.text for c in child.children if isinstance(c, TextNode)]
                if texts:
                    return " ".join(texts)
    for child in label_el.children:
        if isinstance(child, Element) and child.tag == "legend":
            texts = [c.text for c in child.children if isinstance(c, TextNode)]
            if texts:
                return " ".join(texts)
    return None


def _node_text(node: Node, env: dict[str, Any], visible_only: bool = False,
               view: TestView | None = None) -> list[str]:
    if isinstance(node, TextNode):
        return [node.text]
    if isinstance(node, BindText):
        return [_js_like_str(node.expr.evaluate(env))]
    if isinstance(node, RawHTML):
        return []
    if isinstance(node, When):
        if visible_only:
            branch = node.then if node.condition.evaluate(env) else node.otherwise
            return [t for c in branch for t in _node_text(c, env, visible_only, view)]
        out = []
        for child in node.then + node.otherwise:
            out.extend(_node_text(child, env, visible_only, view))
        return out
    if isinstance(node, EachNode):
        items = node.items.evaluate(env) or []
        out = []
        for item in items:
            item_env = env | {"item": item}
            for child in node.template:
                out.extend(_node_text(child, item_env, visible_only, view))
        return out
    if isinstance(node, (Element, PageNode, IslandNode)):
        out = []
        for child in node.children:
            out.extend(_node_text(child, env, visible_only, view))
        return out
    if isinstance(node, ErrorBoundaryNode):
        out = []
        for child in node.content:
            out.extend(_node_text(child, env, visible_only, view))
        return out
    return []


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def render(fn: Callable[..., Any], *, fetch_resources: bool = True,
           context: dict[str, Any] | None = None,
           **params: Any) -> TestView:
    """Compile a page or component function and return a queryable view.

    Resources fetch eagerly (running their real server actions) so the view
    reflects the loaded page. Pass ``fetch_resources=False`` to assert on
    loading states instead, and ``context={...}`` to provide request-context
    values normally supplied by guards.
    """
    return TestView(fn, params or None, fetch_resources=fetch_resources,
                    context=context)
