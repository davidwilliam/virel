"""Symbolic expression layer.

Reactive values (``ui.state``, ``ui.derived``) are traced symbolically while a
page function runs. Operations on them build an expression tree instead of
computing a value. The compiler then emits each tree twice:

- as JavaScript, for fine-grained browser updates (``Expr.js()``)
- as Python, to evaluate the initial value for server/static rendering
  (``Expr.evaluate(env)``)

Only a documented subset of Python operations is supported. Unsupported
constructs raise ``VirelCompileError`` at build time — they never silently
fall back to server execution (SPEC 8.4).
"""

from __future__ import annotations

import json
from typing import Any, Callable

SENTINEL = "\x00"


class VirelCompileError(Exception):
    """A construct cannot be compiled for the browser.

    The message must say what is wrong and name the nearest valid
    replacement (SPEC 6.10).
    """


# --------------------------------------------------------------------------
# Trace context
# --------------------------------------------------------------------------

_current: "TraceContext | None" = None


class TraceContext:
    """Collects states, derived values and expressions while a page renders."""

    def __init__(self) -> None:
        self.states: dict[str, "State"] = {}
        self.derived: dict[str, "Derived"] = {}
        self.expr_registry: dict[int, "Expr"] = {}
        self.client_fns: dict[str, Any] = {}  # name -> ClientFunction used by page
        self.workers: dict[str, Any] = {}     # name -> WorkerFunction used by page
        self.resources: dict[str, Any] = {}   # id -> Resource
        self.locale: str | None = None         # active locale for ui.t
        self.uses_request_context = False      # page read a per-request value
        self.effects: list[Any] = []           # ui.effect registrations
        self.subscriptions: list[Any] = []      # ui.subscribe registrations
        self.stream_ssr = False                 # render="stream" page
        self.connections: list[Any] = []        # ui.connect registrations
        self._counter = 0

    def next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def register_expr(self, expr: "Expr") -> str:
        eid = len(self.expr_registry)
        self.expr_registry[eid] = expr
        return f"{SENTINEL}{eid}{SENTINEL}"

    def __enter__(self) -> "TraceContext":
        global _current
        self._previous = _current
        _current = self
        return self

    def __exit__(self, *exc: object) -> None:
        global _current
        _current = self._previous


def current_context() -> TraceContext:
    if _current is None:
        raise VirelCompileError(
            "Reactive values can only be created while a @ui.page or "
            "@ui.component function is being compiled. Move this ui.state()/"
            "ui.derived() call inside a page or component function."
        )
    return _current


def in_trace() -> bool:
    return _current is not None


# --------------------------------------------------------------------------
# Expression nodes
# --------------------------------------------------------------------------

_JS_METHODS: dict[str, str] = {
    # python method -> JS equivalent (same arity)
    "strip": "trim",
    "lstrip": "trimStart",
    "rstrip": "trimEnd",
    "lower": "toLowerCase",
    "upper": "toUpperCase",
    "startswith": "startsWith",
    "endswith": "endsWith",
    "replace": "replaceAll",
    "split": "split",
}

_JS_COMPARE = {"==": "===", "!=": "!==", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


def lift(value: Any) -> "Expr":
    """Wrap a plain Python value or pass through an existing expression."""
    if isinstance(value, Expr):
        return value
    if type(value).__name__ == "ServerOnly":
        raise VirelCompileError(
            "A server-only value cannot be used in a reactive or "
            "client expression (SPEC 18.1). Read it on the server with "
            ".get() and send only the non-secret result to the browser.")
    if value is None or isinstance(value, (bool, int, float, str)):
        return Lit(value)
    if isinstance(value, (list, tuple)):
        if any(isinstance(item, Expr) for item in value):
            return ListExpr([lift(item) for item in value])
        return Lit(list(value))
    if isinstance(value, dict):
        return Lit(value)
    raise VirelCompileError(
        f"Value of type {type(value).__name__!r} cannot be used in a reactive "
        "expression. Use plain JSON-compatible values (str, int, float, bool, "
        "None, list, dict) or another reactive value."
    )


class Expr:
    """Base class for symbolic expressions. Supports a typed operator subset."""

    def is_list(self) -> bool:
        return False

    def js(self) -> str:
        raise NotImplementedError

    def evaluate(self, env: dict[str, Any]) -> Any:
        raise NotImplementedError

    def to_ir(self) -> dict[str, Any]:
        return {"kind": self.__class__.__name__, "js": self.js()}

    # -- arithmetic ---------------------------------------------------------
    def __add__(self, other: Any) -> "Expr":
        return BinOp("+", self, lift(other))

    def __radd__(self, other: Any) -> "Expr":
        return BinOp("+", lift(other), self)

    def __sub__(self, other: Any) -> "Expr":
        return BinOp("-", self, lift(other))

    def __rsub__(self, other: Any) -> "Expr":
        return BinOp("-", lift(other), self)

    def __mul__(self, other: Any) -> "Expr":
        return BinOp("*", self, lift(other))

    def __rmul__(self, other: Any) -> "Expr":
        return BinOp("*", lift(other), self)

    def __truediv__(self, other: Any) -> "Expr":
        return BinOp("/", self, lift(other))

    def __floordiv__(self, other: Any) -> "Expr":
        return BinOp("//", self, lift(other))

    def __mod__(self, other: Any) -> "Expr":
        return BinOp("%", self, lift(other))

    # -- comparisons --------------------------------------------------------
    def __eq__(self, other: Any) -> "Expr":  # type: ignore[override]
        return Compare("==", self, lift(other))

    def __ne__(self, other: Any) -> "Expr":  # type: ignore[override]
        return Compare("!=", self, lift(other))

    def __lt__(self, other: Any) -> "Expr":
        return Compare("<", self, lift(other))

    def __le__(self, other: Any) -> "Expr":
        return Compare("<=", self, lift(other))

    def __gt__(self, other: Any) -> "Expr":
        return Compare(">", self, lift(other))

    def __ge__(self, other: Any) -> "Expr":
        return Compare(">=", self, lift(other))

    __hash__ = None  # type: ignore[assignment]

    # -- unsupported constructs must fail loudly ----------------------------
    def __bool__(self) -> bool:
        raise VirelCompileError(
            "A reactive value cannot be used in a Python `if`/`and`/`or`/`not` "
            "at compile time because its value only exists in the browser. "
            "Use ui.When(condition, then=[...], otherwise=[...]) for reactive "
            "rendering, or ui.cond(condition, a, b) for a reactive expression."
        )

    def __iter__(self):
        raise VirelCompileError(
            "A reactive value cannot be iterated at compile time. Reactive "
            "list rendering is not part of the Phase 0 subset."
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in _JS_METHODS:
            def method(*args: Any) -> "Expr":
                return MethodCall(self, name, [lift(a) for a in args])
            return method
        raise VirelCompileError(
            f"Method or attribute {name!r} is not in the supported reactive "
            f"subset. Supported string methods: {', '.join(sorted(_JS_METHODS))}."
        )

    # -- f-string / str() integration ---------------------------------------
    def __format__(self, spec: str) -> str:
        if spec:
            raise VirelCompileError(
                f"Format spec {spec!r} is not supported on reactive values in "
                "the Phase 0 subset. Format the value inside the expression "
                "instead."
            )
        return current_context().register_expr(self)

    def __str__(self) -> str:
        if in_trace():
            return current_context().register_expr(self)
        return f"<{self.__class__.__name__} {self.js()}>"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.js()}>"


class Lit(Expr):
    def __init__(self, value: Any) -> None:
        self.value = value

    def js(self) -> str:
        return json.dumps(self.value)

    def evaluate(self, env: dict[str, Any]) -> Any:
        return self.value

    def is_list(self) -> bool:
        return isinstance(self.value, list)


class StateRead(Expr):
    def __init__(self, name: str, holds_list: bool = False) -> None:
        self.name = name
        self._holds_list = holds_list

    def js(self) -> str:
        return f"S.{self.name}.get()"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return env[self.name]

    def is_list(self) -> bool:
        return self._holds_list


class BinOp(Expr):
    _PY = {
        "+": lambda a, b: a + b,
        "-": lambda a, b: a - b,
        "*": lambda a, b: a * b,
        "/": lambda a, b: a / b,
        "%": lambda a, b: a % b,
        "//": lambda a, b: a // b,
    }

    def __init__(self, op: str, left: Expr, right: Expr) -> None:
        self.op, self.left, self.right = op, left, right

    def js(self) -> str:
        if self.op == "//":
            return f"Math.floor({self.left.js()} / {self.right.js()})"
        if self.op == "+" and self.is_list():
            # Python list concatenation; JS + on arrays would coerce
            # both sides to strings.
            return f"{self.left.js()}.concat({self.right.js()})"
        return f"({self.left.js()} {self.op} {self.right.js()})"

    def is_list(self) -> bool:
        return self.op == "+" and (self.left.is_list()
                                   or self.right.is_list())

    def evaluate(self, env: dict[str, Any]) -> Any:
        return self._PY[self.op](self.left.evaluate(env), self.right.evaluate(env))


class Compare(Expr):
    _PY = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
    }

    def __init__(self, op: str, left: Expr, right: Expr) -> None:
        self.op, self.left, self.right = op, left, right

    def js(self) -> str:
        return f"({self.left.js()} {_JS_COMPARE[self.op]} {self.right.js()})"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return self._PY[self.op](self.left.evaluate(env), self.right.evaluate(env))


class Not(Expr):
    def __init__(self, operand: Expr) -> None:
        self.operand = operand

    def js(self) -> str:
        return f"(!{self.operand.js()})"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return not self.operand.evaluate(env)


class Ternary(Expr):
    def __init__(self, condition: Expr, then: Expr, otherwise: Expr) -> None:
        self.condition, self.then, self.otherwise = condition, then, otherwise

    def js(self) -> str:
        return f"({self.condition.js()} ? {self.then.js()} : {self.otherwise.js()})"

    def evaluate(self, env: dict[str, Any]) -> Any:
        if self.condition.evaluate(env):
            return self.then.evaluate(env)
        return self.otherwise.evaluate(env)


class Length(Expr):
    def __init__(self, operand: Expr) -> None:
        self.operand = operand

    def js(self) -> str:
        return f"{self.operand.js()}.length"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return len(self.operand.evaluate(env))


class MethodCall(Expr):
    def __init__(self, obj: Expr, method: str, args: list[Expr]) -> None:
        self.obj, self.method, self.args = obj, method, args

    def js(self) -> str:
        js_args = ", ".join(a.js() for a in self.args)
        return f"{self.obj.js()}.{_JS_METHODS[self.method]}({js_args})"

    def evaluate(self, env: dict[str, Any]) -> Any:
        value = self.obj.evaluate(env)
        args = [a.evaluate(env) for a in self.args]
        return getattr(value, self.method)(*args)


class BoolOp(Expr):
    """`and` / `or` with Python short-circuit semantics (JS matches for
    boolean operands)."""

    def __init__(self, op: str, values: list[Expr]) -> None:
        self.op, self.values = op, values

    def js(self) -> str:
        joiner = " && " if self.op == "and" else " || "
        return "(" + joiner.join(v.js() for v in self.values) + ")"

    def evaluate(self, env: dict[str, Any]) -> Any:
        result = self.values[0].evaluate(env)
        for value in self.values[1:]:
            if self.op == "and":
                if not result:
                    return result
            elif result:
                return result
            result = value.evaluate(env)
        return result


class Neg(Expr):
    def __init__(self, operand: Expr) -> None:
        self.operand = operand

    def js(self) -> str:
        return f"(-{self.operand.js()})"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return -self.operand.evaluate(env)


class LocalRef(Expr):
    """A function parameter or local variable in compiled client code."""

    def __init__(self, name: str) -> None:
        self.name = name

    def js(self) -> str:
        return self.name

    def evaluate(self, env: dict[str, Any]) -> Any:
        return env[self.name]


class PropAccess(Expr):
    """Attribute access on a local (e.g. ``ev.target.value``)."""

    def __init__(self, operand: Expr, attr: str) -> None:
        self.operand, self.attr = operand, attr

    def js(self) -> str:
        return f"{self.operand.js()}.{self.attr}"

    def evaluate(self, env: dict[str, Any]) -> Any:
        value = self.operand.evaluate(env)
        if isinstance(value, dict):
            return value.get(self.attr)
        return getattr(value, self.attr)


class Index(Expr):
    def __init__(self, operand: Expr, key: Expr) -> None:
        self.operand, self.key = operand, key

    def js(self) -> str:
        return f"{self.operand.js()}[{self.key.js()}]"

    def evaluate(self, env: dict[str, Any]) -> Any:
        value = self.operand.evaluate(env)
        key = self.key.evaluate(env)
        if isinstance(value, dict):
            # Match JS object indexing: a missing key is undefined, not an error.
            return value.get(key)
        return value[key]


class DictExpr(Expr):
    def __init__(self, pairs: dict[str, Expr]) -> None:
        self.pairs = pairs

    def js(self) -> str:
        inner = ", ".join(f"{json.dumps(k)}: {v.js()}" for k, v in self.pairs.items())
        return "{" + inner + "}"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return {k: v.evaluate(env) for k, v in self.pairs.items()}


class ItemRef(Expr):
    """The loop variable inside a ui.Each template.

    Attribute access builds property reads (``item.name`` compiles to
    ``item.name`` in JS and dict access in Python); supported string methods
    keep working.
    """

    def __init__(self, inner: Expr) -> None:
        object.__setattr__(self, "_inner", inner)

    def js(self) -> str:
        return self._inner.js()

    def evaluate(self, env: dict[str, Any]) -> Any:
        return self._inner.evaluate(env)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in _JS_METHODS:
            def method(*args: Any) -> "Expr":
                return MethodCall(self._inner, name, [lift(a) for a in args])
            return method
        return ItemRef(PropAccess(self._inner, name))

    def __getitem__(self, key: Any) -> "ItemRef":
        return ItemRef(Index(self._inner, lift(key)))


class ListExpr(Expr):
    def __init__(self, items: list[Expr]) -> None:
        self.items = items

    def js(self) -> str:
        return "[" + ", ".join(i.js() for i in self.items) + "]"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return [i.evaluate(env) for i in self.items]

    def is_list(self) -> bool:
        return True


class Cast(Expr):
    """Builtin conversions and math helpers with JS equivalents."""

    _JS = {
        "str": ("String(", ")"),
        "int": ("Math.trunc(Number(", "))"),
        "float": ("Number(", ")"),
        "bool": ("Boolean(", ")"),
        "abs": ("Math.abs(", ")"),
        "round": ("Math.round(", ")"),
    }
    _PY = {
        "str": lambda v: _js_like_str(v),
        "int": lambda v: int(float(v)),
        "float": float,
        "bool": bool,
        "abs": abs,
        "round": lambda v: int(v + 0.5) if v >= 0 else -int(-v + 0.5),
    }

    def __init__(self, fn: str, operand: Expr) -> None:
        self.fn, self.operand = fn, operand

    def js(self) -> str:
        prefix, suffix = self._JS[self.fn]
        return f"{prefix}{self.operand.js()}{suffix}"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return self._PY[self.fn](self.operand.evaluate(env))


class MinMax(Expr):
    def __init__(self, fn: str, args: list[Expr]) -> None:
        self.fn, self.args = fn, args

    def js(self) -> str:
        return f"Math.{self.fn}(" + ", ".join(a.js() for a in self.args) + ")"

    def evaluate(self, env: dict[str, Any]) -> Any:
        values = [a.evaluate(env) for a in self.args]
        return min(values) if self.fn == "min" else max(values)


class Aggregate(Expr):
    """sum() and the other iterable aggregates, compiled to array
    reductions so client and worker code can process lists."""

    def __init__(self, fn: str, arg: Expr) -> None:
        self.fn, self.arg = fn, arg

    def js(self) -> str:
        inner = self.arg.js()
        if self.fn == "sum":
            return f"({inner}).reduce((a, b) => a + b, 0)"
        if self.fn == "any":
            return f"({inner}).some(Boolean)"
        if self.fn == "all":
            return f"({inner}).every(Boolean)"
        if self.fn == "sorted":
            return f"[...({inner})].sort((a, b) => a < b ? -1 : a > b ? 1 : 0)"
        if self.fn == "reversed":
            return f"[...({inner})].reverse()"
        return inner

    def evaluate(self, env: dict[str, Any]) -> Any:
        value = self.arg.evaluate(env)
        return {"sum": sum, "any": any, "all": all,
                "sorted": sorted, "reversed": lambda v: list(reversed(v))
                }[self.fn](value)

    def is_list(self) -> bool:
        return self.fn in ("sorted", "reversed")


class RangeExpr(Expr):
    """range() as an array, so loops and comprehensions over a count
    work in client and worker code."""

    def __init__(self, args: list[Expr]) -> None:
        self.args = args

    def js(self) -> str:
        parts = [a.js() for a in self.args]
        if len(parts) == 1:
            start, stop, step = "0", parts[0], "1"
        elif len(parts) == 2:
            start, stop, step = parts[0], parts[1], "1"
        else:
            start, stop, step = parts
        return (f"Array.from({{length: Math.max(0, Math.ceil((({stop}) - "
                f"({start})) / ({step})))}}, (_, i) => ({start}) + i * "
                f"({step}))")

    def evaluate(self, env: dict[str, Any]) -> Any:
        return list(range(*[int(a.evaluate(env)) for a in self.args]))

    def is_list(self) -> bool:
        return True


class Enumerate(Expr):
    """enumerate() as [index, value] pairs."""

    def __init__(self, arg: Expr) -> None:
        self.arg = arg

    def js(self) -> str:
        return f"({self.arg.js()}).map((v, i) => [i, v])"

    def evaluate(self, env: dict[str, Any]) -> Any:
        return [list(pair) for pair in enumerate(self.arg.evaluate(env))]

    def is_list(self) -> bool:
        return True


class Comprehension(Expr):
    """A list comprehension over a supported iterable, compiled to
    map/filter so client and worker code can transform lists."""

    def __init__(self, element: Expr, var: str, iterable: Expr,
                 condition: Expr | None) -> None:
        self.element = element
        self.var = var
        self.iterable = iterable
        self.condition = condition

    def js(self) -> str:
        src = self.iterable.js()
        if self.condition is not None:
            src = (f"({src}).filter(({self.var}) => "
                   f"{self.condition.js()})")
        return f"({src}).map(({self.var}) => {self.element.js()})"

    def evaluate(self, env: dict[str, Any]) -> Any:
        out = []
        for item in self.iterable.evaluate(env):
            local = dict(env)
            local[self.var] = item
            if self.condition is None or self.condition.evaluate(local):
                out.append(self.element.evaluate(local))
        return out

    def is_list(self) -> bool:
        return True


class CallClient(Expr):
    """Invocation of a @ui.client function from compiled client code."""

    def __init__(self, name: str, args: list[Expr]) -> None:
        self.name, self.args = name, args

    def js(self) -> str:
        return f"{self.name}(" + ", ".join(a.js() for a in self.args) + ")"

    def evaluate(self, env: dict[str, Any]) -> Any:
        from .registry import active_registry
        fn = active_registry().client_functions[self.name].fn
        return fn(*[a.evaluate(env) for a in self.args])


class FormatString(Expr):
    """Alternating static strings and expressions, from f-string sentinels."""

    def __init__(self, parts: list[str | Expr]) -> None:
        self.parts = parts

    def js(self) -> str:
        chunks = []
        for part in self.parts:
            if isinstance(part, Expr):
                chunks.append("${" + part.js() + "}")
            else:
                chunks.append(part.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$"))
        return "`" + "".join(chunks) + "`"

    def evaluate(self, env: dict[str, Any]) -> Any:
        out = []
        for part in self.parts:
            if isinstance(part, Expr):
                value = part.evaluate(env)
                out.append(_js_like_str(value))
            else:
                out.append(part)
        return "".join(out)


def _js_like_str(value: Any) -> str:
    """Stringify the way the emitted JS template literal will."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def parse_sentinels(text: str) -> "Expr | str":
    """Turn a string containing f-string sentinels back into an expression."""
    if SENTINEL not in text:
        return text
    ctx = current_context()
    parts: list[str | Expr] = []
    pieces = text.split(SENTINEL)
    # pieces alternate: static, expr-id, static, expr-id, ...
    for index, piece in enumerate(pieces):
        if index % 2 == 0:
            if piece:
                parts.append(piece)
        else:
            parts.append(ctx.expr_registry[int(piece)])
    if len(parts) == 1 and isinstance(parts[0], Expr):
        return parts[0]
    return FormatString(parts)


# --------------------------------------------------------------------------
# Reactive values
# --------------------------------------------------------------------------

class State(StateRead):
    """Browser-local reactive state (``ui.state``)."""

    def __init__(self, initial: Any, name: str | None = None,
                 persist: str | None = None, url: str | None = None) -> None:
        ctx = current_context()
        lift(initial)  # validate serializability
        super().__init__(name or ctx.next_id("s"))
        self.initial = initial
        # Optional adapters: persist to localStorage under a key, or keep
        # the value synchronized with a URL query parameter.
        self.persist = persist
        self.url = url
        ctx.states[self.name] = self

    def set(self, value: Any) -> None:
        recorder = current_recorder()
        recorder.ops.append(SetOp(self.name, lift(value)))

    def update(self, fn: Callable[[Expr], Any]) -> None:
        recorder = current_recorder()
        read = StateRead(self.name, holds_list=isinstance(self.initial, list))
        recorder.ops.append(SetOp(self.name, lift(fn(read))))

    def to_ir(self) -> dict[str, Any]:
        return {"kind": "state", "name": self.name, "initial": self.initial}


class Derived(StateRead):
    """Computed reactive value (``ui.derived``)."""

    def __init__(self, fn: Callable[[], Any], name: str | None = None) -> None:
        ctx = current_context()
        super().__init__(name or ctx.next_id("d"))
        self.expr = lift(fn())
        self._holds_list = self.expr.is_list()
        ctx.derived[self.name] = self

    def to_ir(self) -> dict[str, Any]:
        return {"kind": "derived", "name": self.name, "js": self.expr.js()}


# --------------------------------------------------------------------------
# Event handlers: recorded imperative ops
# --------------------------------------------------------------------------

class SetOp:
    def __init__(self, state: str, value: Expr) -> None:
        self.state, self.value = state, value

    def js(self) -> str:
        return f"S.{self.state}.set({self.value.js()});"

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        env[self.state] = self.value.evaluate(env)

    def to_ir(self) -> dict[str, Any]:
        return {"op": "set", "state": self.state, "value": self.value.js()}


class WorkerOp:
    """Run a @ui.worker function off the main thread and set its result
    into a state (SPEC 17.3)."""

    def __init__(self, name: str, args: "Expr", into: Any) -> None:
        self.name = name
        self.args = args
        self.into = into

    def js(self) -> str:
        return (f'$.runWorker("{self.name}", {self.args.js()}, '
                f"S.{self.into.name});")

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        # Test-mode: run the function synchronously (no real worker).
        from .registry import active_registry, to_jsonable
        fn = active_registry().workers[self.name].fn
        result = fn(self.args.evaluate(env))
        env[self.into.name] = to_jsonable(result)

    def to_ir(self) -> dict[str, Any]:
        return {"op": "worker", "name": self.name,
                "args": self.args.js(), "into": self.into.name}


class SetFromEventOp:
    """Two-way binding: write an event property into a state."""

    def __init__(self, state: str, event_path: str = "target.value") -> None:
        self.state, self.event_path = state, event_path

    def js(self) -> str:
        return f"S.{self.state}.set(ev.{self.event_path});"

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        value = ev
        for part in self.event_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
        env[self.state] = value

    def to_ir(self) -> dict[str, Any]:
        return {"op": "set_from_event", "state": self.state, "path": self.event_path}


class CallOp:
    """Invoke a server action over HTTP.

    With ``optimistic=(state, value)`` the state updates immediately; if the
    server rejects the call, the previous value is restored before the error
    is surfaced.
    """

    def __init__(self, action: str, args: dict[str, Expr], into: State | None,
                 error_into: State | None,
                 optimistic: "tuple[State, Expr] | None" = None,
                 idempotent: bool = False) -> None:
        self.action, self.args, self.into, self.error_into = action, args, into, error_into
        self.optimistic = optimistic
        self.idempotent = idempotent

    def js(self) -> str:
        js_args = "{" + ", ".join(f"{k}: {v.js()}" for k, v in self.args.items()) + "}"
        options = (", { idempotencyKey: crypto.randomUUID() }"
                   if self.idempotent else "")
        then = f".then((r) => S.{self.into.name}.set(r))" if self.into is not None else ""
        if self.error_into is not None:
            on_error = f"S.{self.error_into.name}.set(String(e.message || e));"
        else:
            on_error = "console.error(e);"
        if self.optimistic is None:
            return (f'$.action("{self.action}", {js_args}{options}){then}'
                    f".catch((e) => {{ {on_error} }});")
        state, value = self.optimistic
        return (
            f"{{ const __prev = S.{state.name}.get(); "
            f"S.{state.name}.set({value.js()}); "
            f'$.action("{self.action}", {js_args}{options}){then}'
            f".catch((e) => {{ S.{state.name}.set(__prev); {on_error} }}); }}"
        )

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        """Test-mode execution: call the Python function synchronously."""
        from .registry import active_registry
        registry = active_registry()
        action = registry.actions[self.action]
        run = registry._action_overrides.get(self.action, action.fn)
        args = {k: v.evaluate(env) for k, v in self.args.items()}
        previous = None
        if self.optimistic is not None:
            state, value = self.optimistic
            previous = env.get(state.name)
            env[state.name] = value.evaluate(env)
        try:
            result = run(**args)
            if inspect_isawaitable(result):
                result = _run_coroutine(result)
        except Exception as error:
            if self.optimistic is not None:
                env[self.optimistic[0].name] = previous
            if self.error_into is not None:
                env[self.error_into.name] = f"{type(error).__name__}: {error}"
                return
            raise
        if self.into is not None:
            from .registry import to_jsonable
            env[self.into.name] = to_jsonable(result)

    def to_ir(self) -> dict[str, Any]:
        return {
            "op": "call",
            "action": self.action,
            "args": {k: v.js() for k, v in self.args.items()},
            "into": self.into.name if self.into is not None else None,
        }


class UploadOp:
    """Invoke an upload action with the files from a ui.FileField."""

    def __init__(self, action: str, file_param: str, file_ref: str,
                 args: dict[str, "Expr"], into: "State | None",
                 progress_into: "State | None",
                 error_into: "State | None") -> None:
        self.action = action
        self.file_param = file_param
        self.file_ref = file_ref
        self.args = args
        self.into = into
        self.progress_into = progress_into
        self.error_into = error_into

    def js(self) -> str:
        js_args = "{" + ", ".join(f"{k}: {v.js()}" for k, v in self.args.items()) + "}"
        opts = [f'fileParam: "{self.file_param}"']
        if self.into is not None:
            opts.append(f"into: S.{self.into.name}")
        if self.progress_into is not None:
            opts.append(f"progress: S.{self.progress_into.name}")
        if self.error_into is not None:
            opts.append(f"error: S.{self.error_into.name}")
        return (f'$.upload("{self.action}", "{self.file_ref}", {js_args}, '
                f'{{ {", ".join(opts)} }});')

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        from .registry import active_registry, to_jsonable
        action = active_registry().actions[self.action]
        files = (env.get("__files__") or {}).get(self.file_ref, [])
        if not files:
            if self.error_into is not None:
                env[self.error_into.name] = "no file selected"
            return
        args = {k: v.evaluate(env) for k, v in self.args.items()}
        from .uploads import file_params
        multiple = file_params(action).get(self.file_param, False)
        args[self.file_param] = files if multiple else files[0]
        if self.progress_into is not None:
            env[self.progress_into.name] = 100
        try:
            result = action.fn(**args)
            if inspect_isawaitable(result):
                result = _run_coroutine(result)
        except Exception as error:
            if self.error_into is not None:
                env[self.error_into.name] = f"{type(error).__name__}: {error}"
                return
            raise
        if self.into is not None:
            env[self.into.name] = to_jsonable(result)

    def to_ir(self) -> dict[str, Any]:
        return {"op": "upload", "action": self.action,
                "file_param": self.file_param}


class StreamOp:
    """Invoke a streaming server action: text chunks append into a string
    state, or with events=True, JSON events append into a list state."""

    def __init__(self, action: str, args: dict[str, Expr], into: State,
                 done_set: tuple[State, Expr] | None,
                 events: bool = False) -> None:
        self.action, self.args, self.into, self.done_set = action, args, into, done_set
        self.events = events

    def js(self) -> str:
        js_args = "{" + ", ".join(f"{k}: {v.js()}" for k, v in self.args.items()) + "}"
        if self.done_set:
            state, value = self.done_set
            on_done = f"() => S.{state.name}.set({value.js()})"
        else:
            on_done = "null"
        if self.events:
            return (f'$.streamEvents("{self.action}", {js_args}, '
                    f"S.{self.into.name}, {on_done});")
        on_chunk = f"(c) => S.{self.into.name}.set(S.{self.into.name}.get() + c)"
        return f'$.stream("{self.action}", {js_args}, {on_chunk}, {on_done});'

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        """Test-mode execution: drain the stream synchronously."""
        from .registry import active_registry, to_jsonable
        registry = active_registry()
        action = registry.actions[self.action]
        run = registry._action_overrides.get(self.action, action.fn)
        args = {k: v.evaluate(env) for k, v in self.args.items()}
        chunks = _collect_stream(run(**args))
        if self.events:
            events = [to_jsonable(c) for c in chunks
                      if isinstance(c, (dict, list))]
            env[self.into.name] = (env.get(self.into.name) or []) + events
        else:
            env[self.into.name] = env.get(self.into.name, "") + "".join(
                str(c) for c in chunks)
        if self.done_set:
            state, value = self.done_set
            env[state.name] = value.evaluate(env)

    def to_ir(self) -> dict[str, Any]:
        return {
            "op": "stream",
            "action": self.action,
            "args": {k: v.js() for k, v in self.args.items()},
            "into": self.into.name,
        }


def inspect_isawaitable(value: Any) -> bool:
    import inspect
    return inspect.isawaitable(value)


def _run_coroutine(coroutine: Any) -> Any:
    import asyncio
    return asyncio.run(coroutine)


def _collect_stream(result: Any) -> list[Any]:
    import inspect
    if inspect.isasyncgen(result):
        async def drain() -> list[Any]:
            return [chunk async for chunk in result]
        return _run_coroutine(drain())
    return list(result)


class HandlerRecorder:
    def __init__(self) -> None:
        self.ops: list[Any] = []


_recorder: HandlerRecorder | None = None


def current_recorder() -> HandlerRecorder:
    if _recorder is None:
        raise VirelCompileError(
            "State mutations (.set/.update) and server-action calls are only "
            "valid inside an event handler such as on_click=lambda: ... . "
            "During rendering, read reactive values instead of mutating them."
        )
    return _recorder


def record_handler(fn: Callable[[], None]) -> "Handler":
    """Run an event-handler lambda symbolically and capture its operations."""
    global _recorder
    previous = _recorder
    _recorder = HandlerRecorder()
    try:
        fn()
        if not _recorder.ops:
            raise VirelCompileError(
                "This event handler produced no state changes or server "
                "calls. Handlers must call state.set()/state.update() or "
                "a server action."
            )
        return Handler(_recorder.ops)
    finally:
        _recorder = previous


class Handler:
    def __init__(self, ops: list[Any], prevent_default: bool = False) -> None:
        self.ops = ops
        self.prevent_default = prevent_default

    def js_body(self) -> str:
        body = " ".join(op.js() for op in self.ops)
        prefix = "ev.preventDefault(); " if self.prevent_default else ""
        return prefix + body

    def js(self) -> str:
        return f"(ev) => {{ {self.js_body()} }}"

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        """Run the handler against a Python state environment (tests)."""
        for op in self.ops:
            op.execute(env, ev)

    def to_ir(self) -> list[dict[str, Any]]:
        return [op.to_ir() for op in self.ops]


# --------------------------------------------------------------------------
# Expression helpers exposed on ui.*
# --------------------------------------------------------------------------

def cond(condition: Any, then: Any, otherwise: Any) -> Expr:
    return Ternary(lift(condition), lift(then), lift(otherwise))


def not_(value: Any) -> Expr:
    return Not(lift(value))


def length(value: Any) -> Expr:
    return Length(lift(value))
