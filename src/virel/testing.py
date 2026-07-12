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
    "figure": "figure",
    "article": "article",
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


class TestClock:
    """A deterministic clock (SPEC 16.4): time only moves when a test
    advances it, so timer-, latency-, and frame-dependent logic is
    reproducible. Times are in milliseconds."""

    __test__ = False

    def __init__(self) -> None:
        self.now = 0.0
        self._timers: list[tuple[float, Callable[[], None]]] = []
        self._frames: list[Callable[[], None]] = []

    def advance(self, ms: float) -> None:
        target = self.now + ms
        while self._timers:
            self._timers.sort(key=lambda t: t[0])
            due, callback = self._timers[0]
            if due > target:
                break
            self._timers.pop(0)
            self.now = due
            callback()
        self.now = target

    def set_timeout(self, callback: Callable[[], None], ms: float) -> None:
        self._timers.append((self.now + ms, callback))

    def request_frame(self, callback: Callable[[], None]) -> None:
        self._frames.append(callback)

    def flush_frames(self) -> None:
        frames, self._frames = self._frames, []
        for callback in frames:
            callback()


class _Batch:
    """Coalesces state changes so effects fire once at the end."""

    __test__ = False

    def __init__(self, view: "TestView") -> None:
        self.view = view

    def __enter__(self) -> "TestView":
        self.view._batching = True
        return self.view

    def __exit__(self, *exc: Any) -> None:
        self.view._batching = False
        self.view._fire_effects()


class _Queryable:
    """Role/label/text queries shared by the whole view and by any
    single element (so ``dialog.get_by_label(...)`` scopes to the
    dialog). Each host provides ``_candidates()``."""

    __test__ = False

    def _candidates(self) -> list["TestElement"]:
        raise NotImplementedError

    def get_by_role(self, role: str, *,
                    name: str | None = None) -> "TestElement":
        matches = self.get_all_by_role(role, name=name)
        return self._single(matches, f"role={role!r}"
                            + (f" name={name!r}" if name else ""))

    def get_all_by_role(self, role: str, *,
                        name: str | None = None) -> list["TestElement"]:
        return [
            e for e in self._candidates()
            if e.role == role and (name is None or e.accessible_name == name)
        ]

    def get_by_label(self, label: str) -> "TestElement":
        matches = [
            e for e in self._candidates()
            if e.node.tag in ("input", "select", "textarea")
            and e.label_text == label
        ]
        return self._single(matches, f"label={label!r}")

    def get_by_text(self, text: str) -> "TestElement":
        matches = [e for e in self._candidates() if e.own_text() == text]
        if matches:
            inner = [
                e for e in matches
                if not any(other is not e and _contains(e.node, other.node)
                           for other in matches)
            ]
            return self._single(inner, f"text={text!r}")
        matches = [e for e in self._candidates() if text in e.text()]
        matches.sort(key=lambda e: len(e.text()))
        return self._single(matches[:1], f"text={text!r}")

    def _single(self, matches: list["TestElement"],
                description: str) -> "TestElement":
        if len(matches) == 1:
            return matches[0]
        if not matches:
            available = sorted({
                f"{e.role}:{e.accessible_name}" for e in self._candidates()
                if e.role and e.accessible_name
            })
            raise AssertionError(
                f"No element matches {description}. Elements with roles: "
                + (", ".join(available) or "(none)")
            )
        raise AssertionError(
            f"{len(matches)} elements match {description}; expected "
            "exactly one.")


class TestView(_Queryable):
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
            # Deterministic controls (SPEC 16.4).
            self.clock = TestClock()
            self.action_calls: list[dict[str, Any]] = []
            self._mocked_actions: set[str] = set()
            self._batching = False
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
        # In a batch, defer effects so several mutations settle as one
        # concurrent update (SPEC 16.4).
        if self._batching:
            return
        self._fire_effects(before, scope)

    def _fire_effects(self, before: dict | None = None,
                      scope: dict[str, Any] | None = None) -> None:
        # Effects fire when their dependencies changed, like the browser.
        if before is None:
            before = {id(eff): [None] for eff in self.effects}
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

    # -- deterministic control (SPEC 16.4) --------------------------------------

    def mock_action(self, name: str, *, returns: Any = None,
                    raises: Any = None,
                    sequence: list[Any] | None = None,
                    latency: float = 0.0) -> None:
        """Replace a server action's behavior for this view. ``returns``
        gives a fixed response, ``raises`` an exception (test error and
        retry paths), and ``sequence`` a per-call list of responses or
        exceptions (a value that is an Exception is raised) so a
        first-call failure then success models a retry. ``latency`` is
        recorded and advances the test clock, without real waiting."""
        from .registry import active_registry
        registry = active_registry()
        if name not in registry.actions:
            raise AssertionError(f"no server action named {name!r}")
        calls = self.action_calls
        clock = self.clock
        steps = list(sequence) if sequence is not None else None

        def override(**kwargs: Any) -> Any:
            calls.append({"name": name, "args": kwargs,
                          "at": clock.now})
            if latency:
                clock.advance(latency)
            if steps is not None:
                if not steps:
                    raise AssertionError(
                        f"mock_action {name!r} sequence exhausted")
                item = steps.pop(0)
                if isinstance(item, BaseException):
                    raise item
                return item
            if raises is not None:
                raise raises
            return returns

        registry._action_overrides[name] = override
        self._mocked_actions.add(name)

    def mock_stream(self, name: str, chunks: list[Any], *,
                    latency: float = 0.0) -> None:
        """Replace a streaming action so it yields exactly ``chunks``
        (SPEC 16.4 streaming-chunk control)."""
        from .registry import active_registry
        registry = active_registry()
        if name not in registry.actions:
            raise AssertionError(f"no server action named {name!r}")
        calls = self.action_calls
        clock = self.clock
        sequence = list(chunks)

        def override(**kwargs: Any):
            calls.append({"name": name, "args": kwargs, "at": clock.now})
            for chunk in sequence:
                if latency:
                    clock.advance(latency)
                yield chunk

        registry._action_overrides[name] = override
        self._mocked_actions.add(name)

    def batch(self) -> "_Batch":
        """A context that applies several state changes as one concurrent
        update, firing effects once at the end (SPEC 16.4)."""
        return _Batch(self)

    def close(self) -> None:
        """Remove this view's action overrides."""
        from .registry import active_registry
        overrides = active_registry()._action_overrides
        for name in self._mocked_actions:
            overrides.pop(name, None)
        self._mocked_actions.clear()

    def __enter__(self) -> "TestView":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- queries -----------------------------------------------------------------

    def _candidates(self) -> list["TestElement"]:
        return self._walk()

    def query_text(self) -> str:
        """All visible text in the view, for coarse assertions."""
        env = self.eval_env()
        return " ".join(_node_text(self.root, env, visible_only=True,
                                   view=self)).strip()

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


class TestElement(_Queryable):
    __test__ = False

    def __init__(self, view: TestView, node: Element,
                 conditions: list[tuple[Expr, bool]], label: str | None,
                 scope: dict[str, Any] | None = None) -> None:
        self.view = view
        self.node = node
        self.conditions = conditions
        self.label_text = label
        self.scope = scope or {}  # item bindings when inside a ui.Each

    def _candidates(self) -> list["TestElement"]:
        # Scoped queries: this element's own subtree (SPEC 16.1).
        return [e for e in self.view._walk()
                if e.node is self.node or _contains(self.node, e.node)]

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
    """The first labeling span anywhere under the label element; some
    controls (Slider) nest theirs inside layout rows."""
    def find(node: Node) -> str | None:
        if isinstance(node, Element):
            if node.tag in ("span", "legend"):
                classes = str(node.attrs.get("class", ""))
                if "v-label" in classes or node.tag == "legend":
                    texts = [c.text for c in node.children
                             if isinstance(c, TextNode)]
                    if texts:
                        return " ".join(texts)
            for child in node.children:
                found = find(child)
                if found:
                    return found
        return None

    for child in label_el.children:
        found = find(child)
        if found:
            return found
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
    view = TestView(fn, params or None, fetch_resources=fetch_resources,
                    context=context)
    from .plugins import run_test_hooks
    run_test_hooks(view)
    return view


# ---------------------------------------------------------------------------
# Required test modes without a browser (SPEC 16.3)
# ---------------------------------------------------------------------------

def _compile(fn: Callable[..., Any], **params: Any):
    from .compiler import compile_page
    from .nodes import PageNode
    from .registry import Page as PageRecord

    def wrapped():
        from .elements import Page
        result = fn(**params)
        return result if isinstance(result, PageNode) else Page(result)

    return compile_page(PageRecord(path="/__test__", fn=wrapped,
                                   render="auto"))


def assert_accessible(fn: Callable[..., Any], **params: Any) -> None:
    """Fail if compiling the page raises an accessibility error or
    produces any accessibility warning (SPEC 16.3 accessibility). The
    same audit `virel check` runs, at strict level."""
    from .registry import active_registry
    previous = active_registry().strict_accessibility
    active_registry().strict_accessibility = False
    try:
        compiled = _compile(fn, **params)
    finally:
        active_registry().strict_accessibility = previous
    if compiled.warnings:
        raise AssertionError(
            "accessibility warnings:\n  " + "\n  ".join(compiled.warnings))


def assert_bundle_under(fn: Callable[..., Any], *, page_bytes: int,
                        **params: Any) -> int:
    """Fail if the page's JavaScript module exceeds a byte budget
    (SPEC 16.3 performance budgets). Returns the actual size."""
    compiled = _compile(fn, **params)
    size = len(compiled.js or "")
    if size > page_bytes:
        raise AssertionError(
            f"page module is {size} bytes, over the {page_bytes}-byte "
            "budget.")
    return size


def assert_serializable(fn: Callable[..., Any], **params: Any) -> dict:
    """Fail if the compiled IR does not round-trip through JSON with a
    stable version (SPEC 16.3 serialization compatibility). Returns the
    IR."""
    import json
    from .nodes import IR_VERSION
    compiled = _compile(fn, **params)
    ir = compiled.ir
    reloaded = json.loads(json.dumps(ir))
    if reloaded != ir:
        raise AssertionError("IR does not round-trip through JSON.")
    if ir.get("version") != IR_VERSION:
        raise AssertionError(
            f"IR version {ir.get('version')} != current {IR_VERSION}.")
    return ir


def snapshot(fn: Callable[..., Any], name: str, *,
             update: bool = False, **params: Any) -> None:
    """Server-rendered HTML snapshot for visual/structural regression
    (SPEC 16.3 visual regression), stored under tests/__snapshots__.
    The first run records; later runs compare and fail on a difference.
    Run with update=True (or VIREL_UPDATE_SNAPSHOTS=1) to rewrite."""
    import os
    import re
    from pathlib import Path
    compiled = _compile(fn, **params)
    body = compiled.body_html
    # Drop compiler-generated ids so the snapshot tracks structure, not
    # incidental numbering.
    body = re.sub(r'data-v="\d+"', 'data-v', body)
    slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
    directory = Path("tests") / "__snapshots__"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.html"
    should_update = update or os.environ.get("VIREL_UPDATE_SNAPSHOTS")
    if not path.exists() or should_update:
        path.write_text(body, "utf-8")
        return
    stored = path.read_text("utf-8")
    if stored != body:
        raise AssertionError(
            f"snapshot {name!r} changed. Review the diff, then rerun with "
            "update=True or VIREL_UPDATE_SNAPSHOTS=1 to accept it.")
