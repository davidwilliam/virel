"""Application registry: pages, server actions, components, theme.

Decorators register into the active :class:`AppRegistry`. A default global
registry backs the common single-app case; ``fresh_registry()`` gives tests
isolation.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any, Callable

from .expr import (
    CallOp,
    Expr,
    State,
    StreamOp,
    VirelCompileError,
    current_recorder,
    lift,
)


from dataclasses import dataclass, field as dataclass_field


@dataclass
class Request:
    """What a guard sees about the incoming request (SPEC 8.10)."""

    method: str
    path: str
    headers: dict[str, str] = dataclass_field(default_factory=dict)
    query: dict[str, str] = dataclass_field(default_factory=dict)
    cookies: dict[str, str] = dataclass_field(default_factory=dict)


class Redirect:
    """Guard decision: send the client elsewhere. Only same-origin
    relative paths are allowed (open-redirect protection, SPEC 18.2)."""

    def __init__(self, to: str) -> None:
        if not to.startswith("/") or to.startswith("//"):
            raise VirelCompileError(
                f"redirect target {to!r} must be a same-origin path starting "
                "with '/'."
            )
        self.to = to


class Deny:
    """Guard decision: refuse the request."""

    def __init__(self, status: int = 403, message: str = "Forbidden") -> None:
        self.status = status
        self.message = message


def redirect(to: str) -> Redirect:
    return Redirect(to)


def deny(status: int = 403, message: str = "Forbidden") -> Deny:
    return Deny(status, message)


class Page:
    def __init__(self, path: str, fn: Callable[..., Any], render: str,
                 guard: Callable[..., Any] | None = None) -> None:
        self.path = path
        self.fn = fn
        self.render = render
        self.guard = guard
        self.name = fn.__name__
        self.param_names = re.findall(r"\{(\w+)\}", path)
        self._regex = re.compile(
            "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path) + "$"
        )
        signature = inspect.signature(fn)
        self.query_params = {
            name: param.default
            for name, param in signature.parameters.items()
            if name not in self.param_names and param.default is not inspect.Parameter.empty
        }
        # Query parameters convert to their annotated types (int, float,
        # bool); anything else stays a string.
        try:
            import typing
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        self.query_types = {
            name: hints.get(name, str) for name in self.query_params
        }

    @property
    def is_dynamic(self) -> bool:
        return bool(self.param_names)

    def match(self, path: str) -> dict[str, str] | None:
        found = self._regex.match(path)
        return found.groupdict() if found else None

    @property
    def slug(self) -> str:
        if self.path == "/":
            return "index"
        return self.path.strip("/").replace("/", "__").replace("{", "").replace("}", "")


class ActionArgumentError(Exception):
    """The request payload does not match the action signature."""


class ActionValidationError(Exception):
    """Model validation failed; carries structured per-field errors."""

    def __init__(self, field_errors: dict[str, str]) -> None:
        super().__init__("validation failed")
        self.field_errors = field_errors


class ServerAction:
    """A typed remote procedure generated from a Python function (SPEC 8.8).

    In page code the action object is symbolic: ``.call()`` and ``.stream()``
    record transport operations compiled to fetch calls. On the server the
    wrapped function runs in CPython.
    """

    def __init__(self, fn: Callable[..., Any], stream: bool,
                 guard: Callable[..., Any] | None = None,
                 idempotent: bool = False,
                 download: bool = False) -> None:
        self.fn = fn
        self.name = fn.__name__
        self.stream_response = stream
        self.guard = guard
        # Download actions answer GET requests with a FileDownload and by
        # contract must not change state.
        self.download = download
        # Idempotent actions replay the stored response when a request
        # carries an already-seen Idempotency-Key (safe retries).
        self.idempotent = idempotent
        self.signature = inspect.signature(fn)
        self.is_async = inspect.iscoroutinefunction(fn)
        self.is_async_gen = inspect.isasyncgenfunction(fn)
        self._hints: dict[str, Any] | None = None
        if stream and not (self.is_async_gen or inspect.isgeneratorfunction(fn)):
            raise VirelCompileError(
                f"@ui.server(stream=True) function {self.name!r} must be a "
                "generator (use `yield` to emit chunks)."
            )

    def type_hints(self) -> dict[str, Any]:
        if self._hints is None:
            import typing
            try:
                self._hints = typing.get_type_hints(self.fn)
            except Exception:
                self._hints = {}
        return self._hints

    def prepare(self, raw: dict[str, Any],
                provided: set[str] | None = None) -> dict[str, Any]:
        """Validate a JSON payload against the signature and convert any
        model-annotated parameters. Every server action revalidates on the
        server regardless of client checks (SPEC 8.9). ``provided`` names
        parameters supplied out of band (uploaded files)."""
        valid = set(self.signature.parameters)
        unknown = set(raw) - valid
        if unknown:
            raise ActionArgumentError(
                f"unknown argument(s): {', '.join(sorted(unknown))}")
        missing = [
            p.name for p in self.signature.parameters.values()
            if p.default is inspect.Parameter.empty and p.name not in raw
            and p.name not in (provided or set())
        ]
        if missing:
            raise ActionArgumentError(
                f"missing argument(s): {', '.join(missing)}")

        from .forms import is_model_type, validate_model
        hints = self.type_hints()
        kwargs: dict[str, Any] = {}
        for name, value in raw.items():
            annotation = hints.get(name)
            if annotation is not None and is_model_type(annotation) \
                    and isinstance(value, dict):
                instance, field_errors = validate_model(annotation, value)
                if field_errors:
                    raise ActionValidationError(field_errors)
                kwargs[name] = instance
            else:
                kwargs[name] = value
        return kwargs

    def call(self, args: dict[str, Any] | None = None, *, into: State | None = None,
             error_into: State | None = None,
             optimistic: tuple[State, Any] | None = None) -> None:
        recorder = current_recorder()
        lifted = {k: lift(v) for k, v in (args or {}).items()}
        self._check_args(lifted)
        lifted_optimistic = None
        if optimistic is not None:
            state, value = optimistic
            if not isinstance(state, State):
                raise VirelCompileError(
                    "optimistic= takes a (state, value) tuple where the first "
                    "element is a ui.state."
                )
            lifted_optimistic = (state, lift(value))
        recorder.ops.append(CallOp(self.name, lifted, into, error_into,
                                   optimistic=lifted_optimistic,
                                   idempotent=self.idempotent))

    def stream(self, args: dict[str, Any] | None = None, *,
               into: State | None = None,
               into_events: State | None = None,
               done_set: tuple[State, Any] | None = None) -> None:
        if not self.stream_response:
            raise VirelCompileError(
                f"Server action {self.name!r} is not declared with "
                "@ui.server(stream=True); use .call() instead of .stream()."
            )
        if (into is None) == (into_events is None):
            raise VirelCompileError(
                "stream() takes exactly one of into= (text chunks into a "
                "string state) or into_events= (JSON events into a list "
                "state)."
            )
        recorder = current_recorder()
        lifted = {k: lift(v) for k, v in (args or {}).items()}
        self._check_args(lifted)
        done = (done_set[0], lift(done_set[1])) if done_set else None
        target = into if into is not None else into_events
        recorder.ops.append(StreamOp(self.name, lifted, target, done,
                                     events=into_events is not None))

    def _check_args(self, args: dict[str, Expr]) -> None:
        valid = set(self.signature.parameters)
        for key in args:
            if key not in valid:
                raise VirelCompileError(
                    f"Server action {self.name!r} has no parameter {key!r}. "
                    f"Declared parameters: {', '.join(sorted(valid)) or '(none)'}."
                )
        for name, param in self.signature.parameters.items():
            if param.default is inspect.Parameter.empty and name not in args:
                raise VirelCompileError(
                    f"Server action {self.name!r} requires argument {name!r}."
                )

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Direct Python call (server-side use and tests)."""
        return self.fn(*args, **kwargs)


def to_jsonable(value: Any) -> Any:
    """Convert action results to JSON-compatible data. Never pickle
    (SPEC 18.3)."""
    import dataclasses
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: to_jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if hasattr(value, "model_dump"):  # pydantic BaseModel
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return str(value)


class ClientFunction:
    """A pure Python function compiled ahead of time to JavaScript
    (SPEC 8.4). Callable from event handlers and other client functions;
    also callable as normal Python on the server and in tests."""

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self.name = fn.__name__
        self._compiled: tuple[list[str], list[Any], set[str]] | None = None

    def ensure_compiled(self) -> None:
        if self._compiled is None:
            from .pycompiler import compile_client_function
            self._compiled = compile_client_function(self.fn)

    @property
    def params(self) -> list[str]:
        self.ensure_compiled()
        return self._compiled[0]

    @property
    def deps(self) -> set[str]:
        self.ensure_compiled()
        return self._compiled[2]

    def js_definition(self) -> str:
        self.ensure_compiled()
        params, stmts, _ = self._compiled
        body = "\n  ".join(s.js() for s in stmts)
        return f"function {self.name}({', '.join(params)}) {{\n  {body}\n}}"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from .expr import CallClient, Expr, current_context, in_trace, lift
        if any(isinstance(a, Expr) for a in args) or any(
                isinstance(v, Expr) for v in kwargs.values()):
            if kwargs:
                raise VirelCompileError(
                    f"@ui.client function {self.name!r} must be called with "
                    "positional arguments when given reactive values."
                )
            self.ensure_compiled()
            if in_trace():
                current_context().client_fns[self.name] = self
            return CallClient(self.name, [lift(a) for a in args])
        return self.fn(*args, **kwargs)


class WebComponentType:
    """Typed binding for a standard web component (SPEC 13.1)."""

    def __init__(self, tag: str, module: str,
                 props: dict[str, type] | None = None,
                 events: list[str] | None = None) -> None:
        if "-" not in tag:
            raise VirelCompileError(
                f"Custom element tag {tag!r} must contain a hyphen (web "
                "standard requirement)."
            )
        self.tag = tag
        self.module = module
        self.props = props or {}
        # Declared event names (SPEC 13.1). When present, on_* handlers
        # are validated against them.
        self.events = list(events or [])

    def __call__(self, **props: Any) -> "Any":
        from .nodes import Element
        from . import elements
        events = {}
        attrs: dict[str, Any] = {}
        bound: dict[str, Any] = {}
        for key, value in props.items():
            if key.startswith("on_"):
                event_name = key[3:].replace("_", "-")
                if self.events and event_name not in self.events:
                    raise VirelCompileError(
                        f"Web component {self.tag!r} declares no event "
                        f"{event_name!r}. Declared events: "
                        f"{', '.join(sorted(self.events))}.")
                events[event_name] = elements._handler(value)
                continue
            if self.props and key not in self.props:
                raise VirelCompileError(
                    f"Web component {self.tag!r} has no prop {key!r}. "
                    f"Declared props: {', '.join(sorted(self.props))}."
                )
            attr = key.replace("_", "-")
            if isinstance(value, Expr):
                attrs[attr] = value
            else:
                attrs[attr] = value
        node = Element(self.tag, attrs=attrs, events=events, component=f"web:{self.tag}")
        elements._require_module(self.module)
        return node


class AppRegistry:
    def __init__(self) -> None:
        self.pages: dict[str, Page] = {}
        self.actions: dict[str, ServerAction] = {}
        self.components: dict[str, Callable[..., Any]] = {}
        self.client_functions: dict[str, ClientFunction] = {}
        # @ui.worker functions (SPEC 17.3), a subset of client functions.
        self.workers: dict[str, Any] = {}
        self.theme: Any = None  # set via ui.use_theme; None -> default theme
        # Soft navigation between pages (fetch, swap, mount). Configurable
        # via [app] client_nav in virel.toml.
        self.client_nav = True
        # Message catalogs per locale (ui.messages) and the fallback locale.
        self.catalogs: dict[str, dict] = {}
        self.default_locale = "en"
        # Explicit writing-direction overrides per locale (ui.messages
        # direction=); unlisted locales infer from the language subtag.
        self.locale_directions: dict[str, str] = {}
        # Guard applied to every page and action before specific guards.
        self.default_guard: Callable[..., Any] | None = None
        # Build-time functions (@ui.build), memoized per build.
        self.build_functions: dict[str, Any] = {}
        # Nested layouts by path prefix (@ui.layout).
        self.layouts: dict[str, Callable[..., Any]] = {}
        # ASGI middleware wrappers (app -> app), outermost first.
        self.middleware: list[Callable[[Any], Any]] = []
        # WebSocket channels (@ui.channel).
        self.channels: dict[str, Any] = {}
        # Extra static directories by URL prefix (ui.use_static).
        self.static_mounts: dict[str, Path] = {}
        # Generated CSS from ui.style() objects, keyed by class name.
        self.styles: dict[str, str] = {}
        # Generated @keyframes rules (ui.keyframes), keyed by name.
        self.keyframes: dict[str, str] = {}
        # Raw CSS registered with ui.use_css (SPEC 10.5).
        self.custom_css: list[str] = []
        # Strict accessibility: audit warnings become compile errors.
        self.strict_accessibility = False
        # Policy switches (SPEC 13.3, 18): escape hatches and plugin
        # capabilities that a deployment may prohibit.
        self.policy: dict[str, Any] = {}
        # Registered plugins (SPEC 13.5) and the components they add.
        self.plugins: list[Any] = []
        self.plugin_components: dict[str, Callable[..., Any]] = {}
        # Test-mode server-action overrides (SPEC 16.4): name -> callable
        # that stands in for the real function during ui.test.render.
        self._action_overrides: dict[str, Callable[..., Any]] = {}

    def match_page(self, path: str) -> tuple[Page, dict[str, str]] | None:
        page = self.pages.get(path)
        if page:
            return page, {}
        for candidate in self.pages.values():
            if candidate.is_dynamic:
                params = candidate.match(path)
                if params is not None:
                    return candidate, params
        return None


_registry = AppRegistry()


def active_registry() -> AppRegistry:
    return _registry


def fresh_registry() -> AppRegistry:
    """Replace the global registry (test isolation, multi-app tooling)."""
    global _registry
    _registry = AppRegistry()
    return _registry


# --------------------------------------------------------------------------
# Decorators
# --------------------------------------------------------------------------

def page(path: str, render: str = "auto",
         guard: Callable[..., Any] | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if not path.startswith("/"):
        raise VirelCompileError(f"Route path {path!r} must start with '/'.")
    if render not in ("auto", "static", "server", "client", "hybrid",
                      "stream"):
        raise VirelCompileError(
            f"render={render!r} is not a rendering mode. Use 'auto', "
            "'static', 'server', 'client', 'hybrid', or 'stream'."
        )

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        registry = active_registry()
        if path in registry.pages:
            raise VirelCompileError(f"Route {path!r} is already registered.")
        registry.pages[path] = Page(path, fn, render, guard=guard)
        return fn

    return decorate


def server(fn: Callable[..., Any] | None = None, *, stream: bool = False,
           guard: Callable[..., Any] | None = None,
           idempotent: bool = False, download: bool = False):
    def decorate(inner: Callable[..., Any]) -> ServerAction:
        action = ServerAction(inner, stream=stream, guard=guard,
                              idempotent=idempotent, download=download)
        active_registry().actions[action.name] = action
        return action

    if fn is not None:
        return decorate(fn)
    return decorate


def layout(prefix: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a nested layout (SPEC 8.10): every page whose path starts
    with the prefix renders inside it. Layouts nest from the shortest
    prefix outward, and each receives the inner content as its argument."""
    if not prefix.startswith("/"):
        raise VirelCompileError(f"Layout prefix {prefix!r} must start with '/'.")

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        registry = active_registry()
        if prefix in registry.layouts:
            raise VirelCompileError(
                f"A layout for prefix {prefix!r} is already registered.")
        registry.layouts[prefix] = fn
        return fn

    return decorate


def use_middleware(wrapper: Callable[[Any], Any]) -> None:
    """Register ASGI middleware (SPEC 9.4): a callable taking an ASGI app
    and returning a wrapped ASGI app. Wrappers registered first sit
    outermost. Any standard ASGI middleware composes:

        ui.use_middleware(lambda app: SomeASGIMiddleware(app, option=1))
    """
    active_registry().middleware.append(wrapper)


def use_guard(fn: Callable[..., Any]) -> None:
    """Install a guard that runs before every page and server action,
    ahead of any route-specific guard."""
    active_registry().default_guard = fn


_POLICY_FLAGS = {
    # Escape hatches (SPEC 13.3).
    "raw_javascript", "raw_html",
    # Plugin restrictions (SPEC 13.5).
    "plugin_capabilities",
    # Enterprise policy mode (SPEC 18.5).
    "approved_components",   # allowlist of component names
    "approved_plugins",      # allowlist of plugin names
    "dependency_allowlist",  # allowlist of importable top-level packages
    "max_bundle_gzip",       # per-page JS gzip ceiling (int bytes)
    "accessibility_strict",  # audit warnings become errors
    "deployment_targets",    # allowlist of deploy targets
    "csp_connect_src",       # tighten connect-src beyond 'self'
}


def use_policy(**flags: Any) -> None:
    """Set deployment and enterprise policy (SPEC 13.3, 18.5).

    Escape hatches: raw_javascript, raw_html (default True).
    Plugins: plugin_capabilities (allowed capability set), and
    approved_plugins (an allowlist of plugin names).
    Components: approved_components (an allowlist; other components fail
    to compile).
    Supply chain: dependency_allowlist (importable top-level packages an
    app may use).
    Budgets: max_bundle_gzip (a per-page JS gzip ceiling enforced by
    virel check).
    Accessibility: accessibility_strict (audit warnings become errors).
    Deployment: deployment_targets (allowed virel deploy targets).
    CSP: csp_connect_src (tighten connect-src for outbound requests).

        ui.use_policy(raw_javascript=False,
                      approved_components={"Button", "Text", "Card"},
                      max_bundle_gzip=20000)
    """
    unknown = set(flags) - _POLICY_FLAGS
    if unknown:
        raise VirelCompileError(
            f"Unknown policy flag(s) {sorted(unknown)}; known: "
            f"{', '.join(sorted(_POLICY_FLAGS))}.")
    registry = active_registry()
    registry.policy.update(flags)
    # accessibility_strict is also the audit's strict switch.
    if "accessibility_strict" in flags:
        registry.strict_accessibility = bool(flags["accessibility_strict"])


def use_accessibility(*, strict: bool = True) -> None:
    """Promote accessibility audit warnings (heading progression, vague
    link text) to compile errors (SPEC 11.2 strict mode). Hard failures
    like unnamed icon-only buttons are always errors."""
    active_registry().strict_accessibility = strict


def use_css(source: str) -> None:
    """Register raw CSS rules (SPEC 10.5), compiled into the application
    stylesheet after the framework and ui.style rules so they can
    override anything. This is where the classes referenced by
    class_name= live: pseudo-elements, container queries, keyframes, and
    whatever else the typed API does not cover.

        ui.use_css(".specialized-visualization { container-type: inline-size; }")

    The rules ship in the same compiled app.css, so they stay compatible
    with normal CSS concepts and browser development tools.
    """
    if not isinstance(source, str) or not source.strip():
        raise VirelCompileError("ui.use_css takes a non-empty CSS string.")
    active_registry().custom_css.append(source.strip())


def use_static(route: str, directory: str | Path) -> None:
    """Serve a directory of static files under a URL prefix, in addition
    to the application's own public directory. This is how assets that
    live outside the project root reach the browser: vendored third-party
    packages, files shipped inside an installed Python package, shared
    design assets, and so on.

        ui.use_static("/vendor/widgets", Path(__file__).parent / "widgets")

    The dev server and the ASGI app serve the directory with the same
    caching and path-traversal rules as /public/, and `virel build`
    copies it into dist/ at the same prefix.
    """
    prefix = route.rstrip("/")
    reserved = not prefix or prefix.startswith(("/public", "/_virel"))
    if not route.startswith("/") or reserved:
        raise VirelCompileError(
            f"Static route must be an absolute prefix outside /public and "
            f"/_virel, got {route!r}.")
    resolved = Path(directory).resolve()
    if not resolved.is_dir():
        raise VirelCompileError(
            f"Static directory for {prefix!r} does not exist: {resolved}")
    active_registry().static_mounts[prefix] = resolved


def client(fn: Callable[..., Any]) -> ClientFunction:
    """Mark a pure function for ahead-of-time compilation to JavaScript."""
    wrapped = ClientFunction(fn)
    active_registry().client_functions[wrapped.name] = wrapped
    return wrapped


class WorkerFunction(ClientFunction):
    """A pure function compiled to JavaScript that runs in a Web Worker,
    off the main thread (SPEC 17.3 worker execution). Call ``.run(args,
    into=state)`` inside a handler; the result posts back and lands in
    the state. Callable as ordinary Python on the server and in tests."""

    def run(self, args: Any, *, into: State) -> None:
        from .expr import WorkerOp, current_recorder, lift
        if not isinstance(into, State):
            raise VirelCompileError(
                "worker .run(...) needs into= a ui.state to receive the "
                "result.")
        self.ensure_compiled()
        from .expr import current_context, in_trace
        if in_trace():
            current_context().workers[self.name] = self
        current_recorder().ops.append(
            WorkerOp(self.name, lift(args), into))


def worker(fn: Callable[..., Any]) -> WorkerFunction:
    """A pure function that runs in a Web Worker (SPEC 17.3):

        @ui.worker
        def summarize(rows: list) -> dict:
            return {"total": sum(r["n"] for r in rows)}

        # in a handler:
        summarize.run(data, into=result)

    The function compiles to JavaScript, runs off the main thread, and
    posts its return value into the result state; the UI stays
    responsive during heavy computation."""
    wrapped = WorkerFunction(fn)
    active_registry().client_functions[wrapped.name] = wrapped
    active_registry().workers[wrapped.name] = wrapped
    return wrapped


def shared(fn: Callable[..., Any]) -> ClientFunction:
    """A pure function usable on both sides of the boundary (SPEC 8.4):
    compiled to JavaScript for the browser and callable as ordinary Python
    in server actions, server rendering, and tests. Shared functions must
    be deterministic and side-effect free."""
    return client(fn)


class BuildFunction:
    """A function that runs in CPython at build time (SPEC 8.4). Results
    are memoized per build, so expensive work (loading content trees,
    reading files) happens once no matter how many pages call it. The dev
    server clears the memo when source files change."""

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn
        self.name = fn.__name__
        self._cache: dict[tuple, Any] = {}

    def __call__(self, *args: Any) -> Any:
        try:
            key = args
            if key not in self._cache:
                self._cache[key] = self.fn(*args)
            return self._cache[key]
        except TypeError:
            # Unhashable arguments: run without memoization.
            return self.fn(*args)

    def invalidate(self) -> None:
        self._cache.clear()


def build(fn: Callable[..., Any]) -> BuildFunction:
    wrapped = BuildFunction(fn)
    active_registry().build_functions[wrapped.name] = wrapped
    return wrapped


def component(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Register a component for inspector/registry output (SPEC 14.2)."""
    active_registry().components[fn.__name__] = fn

    source = f"{fn.__code__.co_filename}:{fn.__code__.co_firstlineno}"

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        node = fn(*args, **kwargs)
        from .nodes import Element
        if isinstance(node, Element) and node.component is None:
            node.component = fn.__name__
            node.source = source
        return node

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def web_component(tag: str, module: str,
                  props: dict[str, type] | None = None,
                  events: list[str] | None = None) -> WebComponentType:
    return WebComponentType(tag, module, props, events)
