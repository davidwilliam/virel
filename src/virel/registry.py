"""Application registry: pages, server actions, components, theme.

Decorators register into the active :class:`AppRegistry`. A default global
registry backs the common single-app case; ``fresh_registry()`` gives tests
isolation.
"""

from __future__ import annotations

import inspect
import re
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


class Page:
    def __init__(self, path: str, fn: Callable[..., Any], render: str) -> None:
        self.path = path
        self.fn = fn
        self.render = render
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

    def __init__(self, fn: Callable[..., Any], stream: bool) -> None:
        self.fn = fn
        self.name = fn.__name__
        self.stream_response = stream
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

    def prepare(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate a JSON payload against the signature and convert any
        model-annotated parameters. Every server action revalidates on the
        server regardless of client checks (SPEC 8.9)."""
        valid = set(self.signature.parameters)
        unknown = set(raw) - valid
        if unknown:
            raise ActionArgumentError(
                f"unknown argument(s): {', '.join(sorted(unknown))}")
        missing = [
            p.name for p in self.signature.parameters.values()
            if p.default is inspect.Parameter.empty and p.name not in raw
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
             error_into: State | None = None) -> None:
        recorder = current_recorder()
        lifted = {k: lift(v) for k, v in (args or {}).items()}
        self._check_args(lifted)
        recorder.ops.append(CallOp(self.name, lifted, into, error_into))

    def stream(self, args: dict[str, Any] | None = None, *, into: State,
               done_set: tuple[State, Any] | None = None) -> None:
        if not self.stream_response:
            raise VirelCompileError(
                f"Server action {self.name!r} is not declared with "
                "@ui.server(stream=True); use .call() instead of .stream()."
            )
        recorder = current_recorder()
        lifted = {k: lift(v) for k, v in (args or {}).items()}
        self._check_args(lifted)
        done = (done_set[0], lift(done_set[1])) if done_set else None
        recorder.ops.append(StreamOp(self.name, lifted, into, done))

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

    def __init__(self, tag: str, module: str, props: dict[str, type] | None = None) -> None:
        if "-" not in tag:
            raise VirelCompileError(
                f"Custom element tag {tag!r} must contain a hyphen (web "
                "standard requirement)."
            )
        self.tag = tag
        self.module = module
        self.props = props or {}

    def __call__(self, **props: Any) -> "Any":
        from .nodes import Element
        from . import elements
        events = {}
        attrs: dict[str, Any] = {}
        bound: dict[str, Any] = {}
        for key, value in props.items():
            if key.startswith("on_"):
                events[key[3:].replace("_", "-")] = elements._handler(value)
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
        self.theme: Any = None  # set via ui.use_theme; None -> default theme
        # Soft navigation between pages (fetch, swap, mount). Configurable
        # via [app] client_nav in virel.toml.
        self.client_nav = True

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

def page(path: str, render: str = "auto") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if not path.startswith("/"):
        raise VirelCompileError(f"Route path {path!r} must start with '/'.")
    if render not in ("auto", "static", "server", "client"):
        raise VirelCompileError(
            f"render={render!r} is not a rendering mode. "
            "Use 'auto', 'static', 'server', or 'client'."
        )

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        registry = active_registry()
        if path in registry.pages:
            raise VirelCompileError(f"Route {path!r} is already registered.")
        registry.pages[path] = Page(path, fn, render)
        return fn

    return decorate


def server(fn: Callable[..., Any] | None = None, *, stream: bool = False):
    def decorate(inner: Callable[..., Any]) -> ServerAction:
        action = ServerAction(inner, stream=stream)
        active_registry().actions[action.name] = action
        return action

    if fn is not None:
        return decorate(fn)
    return decorate


def client(fn: Callable[..., Any]) -> ClientFunction:
    """Mark a pure function for ahead-of-time compilation to JavaScript."""
    wrapped = ClientFunction(fn)
    active_registry().client_functions[wrapped.name] = wrapped
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


def web_component(tag: str, module: str, props: dict[str, type] | None = None) -> WebComponentType:
    return WebComponentType(tag, module, props)
