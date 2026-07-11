"""AST-based client compiler.

Compiles a documented subset of Python function bodies to JavaScript for
browser execution. Used for named event handlers (which may contain real
control flow) and for @ui.client functions (SPEC 8.4).

The compiler translates the AST into the same expression IR the tracer
produces, so every construct is emitted twice: as JavaScript for the browser
and as executable Python for server rendering and pytest simulation.
Unsupported constructs are build-time errors that name the nearest valid
replacement; code is never silently moved to the server.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any, Callable

from .expr import (
    BinOp,
    BoolOp,
    CallClient,
    CallOp,
    Cast,
    Compare,
    Expr,
    FormatString,
    Index,
    Length,
    ListExpr,
    Lit,
    LocalRef,
    MethodCall,
    MinMax,
    Neg,
    Not,
    PropAccess,
    SetOp,
    StateRead,
    StreamOp,
    Ternary,
    VirelCompileError,
    _JS_METHODS,
    in_trace,
    current_context,
)

_BIN_OPS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.Mod: "%", ast.FloorDiv: "//",
}
_CMP_OPS = {
    ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
    ast.Gt: ">", ast.GtE: ">=",
}


# ---------------------------------------------------------------------------
# Statement IR
# ---------------------------------------------------------------------------

class Stmt:
    def js(self) -> str:
        raise NotImplementedError

    def execute(self, env: dict[str, Any], ev: Any = None) -> Any:
        raise NotImplementedError

    def to_ir(self) -> dict[str, Any]:
        return {"op": self.__class__.__name__.lower(), "js": self.js()}


class LetStmt(Stmt):
    def __init__(self, name: str, value: Expr, declare: bool) -> None:
        self.name, self.value, self.declare = name, value, declare

    def js(self) -> str:
        keyword = "let " if self.declare else ""
        return f"{keyword}{self.name} = {self.value.js()};"

    def execute(self, env: dict[str, Any], ev: Any = None) -> Any:
        env[self.name] = self.value.evaluate(env)


class IfStmt(Stmt):
    def __init__(self, condition: Expr, then: list[Stmt], orelse: list[Stmt]) -> None:
        self.condition, self.then, self.orelse = condition, then, orelse

    def js(self) -> str:
        then_js = " ".join(s.js() for s in self.then)
        out = f"if ({self.condition.js()}) {{ {then_js} }}"
        if self.orelse:
            else_js = " ".join(s.js() for s in self.orelse)
            out += f" else {{ {else_js} }}"
        return out

    def execute(self, env: dict[str, Any], ev: Any = None) -> Any:
        branch = self.then if self.condition.evaluate(env) else self.orelse
        for stmt in branch:
            result = stmt.execute(env, ev)
            if isinstance(result, _Return):
                return result


class ForStmt(Stmt):
    def __init__(self, var: str, iterable: Expr, body: list[Stmt]) -> None:
        self.var, self.iterable, self.body = var, iterable, body

    def js(self) -> str:
        body_js = " ".join(s.js() for s in self.body)
        return f"for (const {self.var} of {self.iterable.js()}) {{ {body_js} }}"

    def execute(self, env: dict[str, Any], ev: Any = None) -> Any:
        for item in self.iterable.evaluate(env):
            env[self.var] = item
            for stmt in self.body:
                result = stmt.execute(env, ev)
                if isinstance(result, _Return):
                    return result


class ReturnStmt(Stmt):
    def __init__(self, value: Expr) -> None:
        self.value = value

    def js(self) -> str:
        return f"return {self.value.js()};"

    def execute(self, env: dict[str, Any], ev: Any = None) -> Any:
        return _Return(self.value.evaluate(env))


class _Return:
    def __init__(self, value: Any) -> None:
        self.value = value


class OpStmt(Stmt):
    """Wraps a traced-op (SetOp/CallOp/StreamOp) as a statement."""

    def __init__(self, op: Any) -> None:
        self.op = op

    def js(self) -> str:
        return self.op.js()

    def execute(self, env: dict[str, Any], ev: Any = None) -> Any:
        self.op.execute(env, ev)

    def to_ir(self) -> dict[str, Any]:
        return self.op.to_ir()


# ---------------------------------------------------------------------------
# Function compiler
# ---------------------------------------------------------------------------

class FnCompiler:
    """Compiles one Python function body to statement IR."""

    def __init__(self, fn: Callable[..., Any], mode: str) -> None:
        self.fn = fn
        self.mode = mode  # "handler" | "client"
        self.locals: set[str] = set()
        self.params: list[str] = list(inspect.signature(fn).parameters)
        self.used_client_fns: set[str] = set()
        try:
            source = textwrap.dedent(inspect.getsource(fn))
        except (OSError, TypeError):
            raise VirelCompileError(
                f"Cannot read the source of {fn.__name__!r} to compile it for "
                "the browser. Define it as a regular named function in a "
                "Python source file."
            ) from None
        tree = ast.parse(source)
        node = tree.body[0]
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise VirelCompileError(
                f"{fn.__name__!r} could not be parsed as a function definition."
            )
        if isinstance(node, ast.AsyncFunctionDef):
            raise VirelCompileError(
                f"{fn.__name__!r}: async functions are not part of the client "
                "subset. Server calls from handlers are already asynchronous; "
                "use a plain def."
            )
        self.node = node
        self.closure = self._closure_env(fn)

    @staticmethod
    def _closure_env(fn: Callable[..., Any]) -> dict[str, Any]:
        env: dict[str, Any] = {}
        if fn.__closure__:
            for name, cell in zip(fn.__code__.co_freevars, fn.__closure__):
                try:
                    env[name] = cell.cell_contents
                except ValueError:
                    continue
        return env

    def error(self, node: ast.AST, message: str) -> VirelCompileError:
        line = getattr(node, "lineno", "?")
        return VirelCompileError(
            f"[{self.fn.__name__}, line {line}] {message}"
        )

    def compile_body(self) -> list[Stmt]:
        body = self.node.body
        # Drop a docstring if present.
        if body and isinstance(body[0], ast.Expr) and isinstance(
                body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body = body[1:]
        return [self.stmt(s) for s in body]

    # -- statements -----------------------------------------------------------

    def stmt(self, node: ast.stmt) -> Stmt:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise self.error(node, "Only simple `name = value` assignments "
                                       "are supported in client code.")
            name = node.targets[0].id
            self._check_shadow(node, name)
            declare = name not in self.locals
            self.locals.add(name)
            return LetStmt(name, self.expr(node.value), declare)

        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise self.error(node, "Augmented assignment is only supported "
                                       "on local variables.")
            name = node.target.id
            if name not in self.locals and name not in self.params:
                raise self.error(
                    node,
                    f"{name!r} is not a local variable. To change reactive "
                    "state, use state.set(...) or state.update(...).",
                )
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise self.error(node, f"Operator {type(node.op).__name__} is "
                                       "not in the client subset.")
            return LetStmt(name, BinOp(op, LocalRef(name), self.expr(node.value)),
                           declare=False)

        if isinstance(node, ast.If):
            return IfStmt(
                self.expr(node.test),
                [self.stmt(s) for s in node.body],
                [self.stmt(s) for s in node.orelse],
            )

        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name):
                raise self.error(node, "Only `for name in iterable:` loops are "
                                       "supported in client code.")
            if node.orelse:
                raise self.error(node, "`for ... else` is not in the client subset.")
            self.locals.add(node.target.id)
            return ForStmt(node.target.id, self.expr(node.iter),
                           [self.stmt(s) for s in node.body])

        if isinstance(node, ast.Return):
            if self.mode != "client":
                raise self.error(node, "Event handlers cannot return values. "
                                       "Write results into state instead.")
            value = self.expr(node.value) if node.value is not None else Lit(None)
            return ReturnStmt(value)

        if isinstance(node, ast.Expr):
            return self.call_stmt(node.value)

        if isinstance(node, ast.Pass):
            return LetStmt("_", Lit(None), declare=True)

        raise self.error(
            node,
            f"`{type(node).__name__}` statements are not in the client subset. "
            "Supported: assignments, if/elif/else, for-loops over lists, "
            "state.set/update, server-action calls, and return "
            "(in @ui.client functions).",
        )

    def _check_shadow(self, node: ast.AST, name: str) -> None:
        resolved = self._resolve(name)
        if resolved is not _UNRESOLVED and _is_reactive(resolved):
            raise self.error(
                node,
                f"Assigning to {name!r} would shadow a reactive value. Use "
                f"{name}.set(...) to change it, or pick a different local name.",
            )

    def call_stmt(self, node: ast.expr) -> Stmt:
        if not isinstance(node, ast.Call):
            raise self.error(node, "Expression statements must be calls "
                                   "(state.set, action.call, ...).")
        call = node
        if isinstance(call.func, ast.Name):
            resolved = self._resolve(call.func.id)
            if getattr(resolved, "__virel_op__", None) == "invalidate":
                return OpStmt(self._compile_invalidate(call))
        if isinstance(call.func, ast.Attribute):
            target = self._try_resolve_node(call.func.value)
            attr = call.func.attr
            if getattr(getattr(target, attr, None), "__virel_op__", None) \
                    == "invalidate":
                return OpStmt(self._compile_invalidate(call))
            from .registry import ServerAction
            from .resources import RefreshOp, Resource
            if _is_reactive(target) and attr in ("set", "update"):
                return OpStmt(self._compile_state_mutation(call, target, attr))
            if isinstance(target, ServerAction):
                return OpStmt(self._compile_action_call(call, target, attr))
            if isinstance(target, Resource):
                if attr != "refresh" or call.args or call.keywords:
                    raise self.error(call, "Resources support .refresh() with "
                                           "no arguments in handlers.")
                return OpStmt(RefreshOp(target))
        # A bare client-function call is allowed only for its value being
        # discarded intentionally; that is almost always a mistake.
        raise self.error(
            node,
            "Only state mutations (state.set/state.update), server-action "
            "calls (action.call/action.stream), and resource.refresh() may "
            "be used as statements.",
        )

    def _compile_invalidate(self, call: ast.Call) -> Any:
        from .registry import ServerAction
        from .resources import InvalidateOp
        if len(call.args) != 1 or call.keywords:
            raise self.error(call, "ui.invalidate takes a single server action.")
        target = self._try_resolve_node(call.args[0])
        if not isinstance(target, ServerAction):
            raise self.error(call, "ui.invalidate takes a @ui.server action.")
        return InvalidateOp(target.name)

    def _compile_state_mutation(self, call: ast.Call, state: Any, attr: str) -> SetOp:
        if attr == "set":
            if len(call.args) != 1 or call.keywords:
                raise self.error(call, "state.set(...) takes exactly one argument.")
            return SetOp(state.name, self.expr(call.args[0]))
        # update(fn): inline the lambda
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Lambda):
            raise self.error(call, "state.update(...) takes a single lambda, "
                                   "e.g. count.update(lambda c: c + 1).")
        lam = call.args[0]
        if len(lam.args.args) != 1:
            raise self.error(call, "The update lambda takes exactly one parameter.")
        param = lam.args.args[0].arg
        # Substitute the lambda parameter with the current state value.
        value = _SubstitutingCompiler(self, {param: StateRead(state.name)}).expr(lam.body)
        return SetOp(state.name, value)

    def _compile_action_call(self, call: ast.Call, action: Any, attr: str) -> Any:
        if attr not in ("call", "stream"):
            raise self.error(call, f"Server actions support .call() and "
                                   f".stream(), not .{attr}().")
        args: dict[str, Expr] = {}
        if call.args:
            if len(call.args) > 1 or not isinstance(call.args[0], ast.Dict):
                raise self.error(call, "Pass action arguments as a dict "
                                       'literal: action.call({"name": value}).')
            for key, value in zip(call.args[0].keys, call.args[0].values):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    raise self.error(call, "Action argument names must be "
                                           "string literals.")
                args[key.value] = self.expr(value)
        into = error_into = None
        done_set = None
        optimistic = None
        for keyword in call.keywords:
            if keyword.arg == "into":
                into = self._resolve_state_kw(call, keyword)
            elif keyword.arg == "error_into":
                error_into = self._resolve_state_kw(call, keyword)
            elif keyword.arg == "optimistic" and attr == "call":
                if not (isinstance(keyword.value, ast.Tuple)
                        and len(keyword.value.elts) == 2):
                    raise self.error(call, "optimistic takes a (state, value) tuple.")
                state = self._try_resolve_node(keyword.value.elts[0])
                if not _is_reactive(state):
                    raise self.error(call, "optimistic's first element must be a state.")
                optimistic = (state, self.expr(keyword.value.elts[1]))
            elif keyword.arg == "done_set" and attr == "stream":
                if not (isinstance(keyword.value, ast.Tuple)
                        and len(keyword.value.elts) == 2):
                    raise self.error(call, "done_set takes a (state, value) tuple.")
                state = self._try_resolve_node(keyword.value.elts[0])
                if not _is_reactive(state):
                    raise self.error(call, "done_set's first element must be a state.")
                done_set = (state, self.expr(keyword.value.elts[1]))
            else:
                raise self.error(call, f"Unknown keyword {keyword.arg!r} for "
                                       f"action.{attr}().")
        # Reuse the ServerAction signature validation.
        action._check_args(args)
        if attr == "call":
            return CallOp(action.name, args, into, error_into,
                          optimistic=optimistic)
        if into is None:
            raise self.error(call, "action.stream(...) requires into=<state>.")
        return StreamOp(action.name, args, into, done_set)

    def _resolve_state_kw(self, call: ast.Call, keyword: ast.keyword) -> Any:
        state = self._try_resolve_node(keyword.value)
        if not _is_reactive(state):
            raise self.error(call, f"{keyword.arg}= must reference a ui.state value.")
        return state

    # -- expressions ----------------------------------------------------------

    def expr(self, node: ast.expr) -> Expr:
        if isinstance(node, ast.Constant):
            if node.value is Ellipsis:
                raise self.error(node, "`...` has no meaning in client code.")
            return Lit(node.value)

        if isinstance(node, ast.Name):
            return self._name_expr(node)

        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise self.error(node, f"Operator {type(node.op).__name__} is "
                                       "not in the client subset.")
            return BinOp(op, self.expr(node.left), self.expr(node.right))

        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            return BoolOp(op, [self.expr(v) for v in node.values])

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return Not(self.expr(node.operand))
            if isinstance(node.op, ast.USub):
                return Neg(self.expr(node.operand))
            raise self.error(node, "Unsupported unary operator.")

        if isinstance(node, ast.Compare):
            return self._compare(node)

        if isinstance(node, ast.IfExp):
            return Ternary(self.expr(node.test), self.expr(node.body),
                           self.expr(node.orelse))

        if isinstance(node, ast.JoinedStr):
            return self._fstring(node)

        if isinstance(node, ast.Call):
            return self._call_expr(node)

        if isinstance(node, ast.Attribute):
            base = self._try_resolve_node(node.value)
            if _is_reactive(base):
                raise self.error(
                    node,
                    f"Reactive values have no attribute {node.attr!r}. Read "
                    "the value directly or use a supported method.",
                )
            return PropAccess(self.expr(node.value), node.attr)

        if isinstance(node, ast.Subscript):
            return Index(self.expr(node.value), self.expr(node.slice))

        if isinstance(node, (ast.List, ast.Tuple)):
            return ListExpr([self.expr(e) for e in node.elts])

        raise self.error(
            node,
            f"`{type(node).__name__}` expressions are not in the client "
            "subset. Supported: literals, arithmetic, comparisons, and/or/not, "
            "conditional expressions, f-strings, list literals, indexing, "
            "supported string methods, len/str/int/float/bool/abs/min/max/"
            "round, and @ui.client function calls.",
        )

    def _name_expr(self, node: ast.Name) -> Expr:
        name = node.id
        if name in self.params or name in self.locals:
            return LocalRef(name)
        if name in ("True", "False", "None"):
            return Lit({"True": True, "False": False, "None": None}[name])
        resolved = self._resolve(name)
        if resolved is _UNRESOLVED:
            raise self.error(
                node,
                f"Name {name!r} is not defined in this function, its "
                "closure, or module globals. If you assign to this name "
                "later in the handler, Python makes it a local variable that "
                "shadows the outer one; use a different local name, or "
                "state.set(...) to change reactive state.",
            )
        if _is_reactive(resolved):
            return StateRead(resolved.name)
        if isinstance(resolved, Expr):
            # e.g. the symbolic item of a ui.Each template captured by a
            # named handler defined inside the render function.
            return resolved
        if resolved is None or isinstance(resolved, (bool, int, float, str)):
            return Lit(resolved)
        if isinstance(resolved, (list, tuple)):
            return Lit(list(resolved))
        if isinstance(resolved, dict):
            return Lit(resolved)
        from .registry import ServerAction
        if isinstance(resolved, ServerAction):
            raise self.error(node, f"Server action {name!r} must be invoked "
                                   f"with {name}.call(...) or {name}.stream(...).")
        raise self.error(
            node,
            f"{name!r} refers to a {type(resolved).__name__}, which cannot be "
            "captured into client code. Only JSON-compatible constants, "
            "reactive values, server actions, and @ui.client functions cross "
            "this boundary.",
        )

    def _resolve(self, name: str) -> Any:
        if name in self.closure:
            return self.closure[name]
        if name in self.fn.__globals__:
            return self.fn.__globals__[name]
        return _UNRESOLVED

    def _try_resolve_node(self, node: ast.expr) -> Any:
        if isinstance(node, ast.Name):
            value = self._resolve(node.id)
            return None if value is _UNRESOLVED else value
        return None

    def _compare(self, node: ast.Compare) -> Expr:
        parts: list[Expr] = []
        left = node.left
        for op, right in zip(node.ops, node.comparators):
            cmp = _CMP_OPS.get(type(op))
            if cmp is None:
                raise self.error(
                    node,
                    f"Comparison {type(op).__name__} is not in the client "
                    "subset (`in`/`is` are not supported).",
                )
            parts.append(Compare(cmp, self.expr(left), self.expr(right)))
            left = right
        if len(parts) == 1:
            return parts[0]
        return BoolOp("and", parts)

    def _fstring(self, node: ast.JoinedStr) -> Expr:
        parts: list[str | Expr] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                if value.format_spec is not None or value.conversion != -1:
                    raise self.error(node, "Format specs and !r/!s conversions "
                                           "are not supported in client f-strings.")
                parts.append(self.expr(value.value))
        return FormatString(parts)

    def _call_expr(self, node: ast.Call) -> Expr:
        # Builtins with JS equivalents
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name == "len":
                if len(node.args) != 1:
                    raise self.error(node, "len() takes one argument.")
                return Length(self.expr(node.args[0]))
            if name in ("str", "int", "float", "bool", "abs", "round"):
                if len(node.args) != 1:
                    raise self.error(node, f"{name}() takes one argument here.")
                return Cast(name, self.expr(node.args[0]))
            if name in ("min", "max"):
                return MinMax(name, [self.expr(a) for a in node.args])
            resolved = self._resolve(name)
            from .registry import ClientFunction
            if isinstance(resolved, ClientFunction):
                self.used_client_fns.add(resolved.fn.__name__)
                resolved.ensure_compiled()
                if in_trace():
                    current_context().client_fns[resolved.fn.__name__] = resolved
                return CallClient(resolved.fn.__name__,
                                  [self.expr(a) for a in node.args])
            raise self.error(
                node,
                f"Function {name!r} cannot be called from client code. Mark "
                "pure helpers with @ui.client, or move the work into a "
                "@ui.server action.",
            )

        # Method calls on expressions (supported string methods)
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in _JS_METHODS:
                return MethodCall(self.expr(node.func.value), method,
                                  [self.expr(a) for a in node.args])
            raise self.error(
                node,
                f"Method {method!r} is not in the supported client subset. "
                f"Supported string methods: {', '.join(sorted(_JS_METHODS))}.",
            )

        raise self.error(node, "This call form is not supported in client code.")


class _SubstitutingCompiler:
    """Compiles an expression with some names mapped to fixed expressions
    (used to inline update-lambda parameters)."""

    def __init__(self, parent: FnCompiler, substitutions: dict[str, Expr]) -> None:
        self.parent = parent
        self.substitutions = substitutions

    def expr(self, node: ast.expr) -> Expr:
        if isinstance(node, ast.Name) and node.id in self.substitutions:
            return self.substitutions[node.id]
        original = self.parent._name_expr
        substitutions = self.substitutions

        def patched(name_node: ast.Name) -> Expr:
            if name_node.id in substitutions:
                return substitutions[name_node.id]
            return original(name_node)

        self.parent._name_expr = patched  # type: ignore[method-assign]
        try:
            return self.parent.expr(node)
        finally:
            self.parent._name_expr = original  # type: ignore[method-assign]


_UNRESOLVED = object()


def _is_reactive(value: Any) -> bool:
    from .expr import State, Derived
    return isinstance(value, (State, Derived))


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

class CompiledHandler:
    def __init__(self, stmts: list[Stmt]) -> None:
        self.stmts = stmts

    def js_body(self) -> str:
        return " ".join(s.js() for s in self.stmts)

    def js(self) -> str:
        return f"(ev) => {{ {self.js_body()} }}"

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        for stmt in self.stmts:
            stmt.execute(env, ev)

    def to_ir(self) -> list[dict[str, Any]]:
        return [s.to_ir() for s in self.stmts]


def compile_handler(fn: Callable[[], None]) -> CompiledHandler:
    compiler = FnCompiler(fn, mode="handler")
    if compiler.params not in ([], ["ev"]):
        raise VirelCompileError(
            f"Event handler {fn.__name__!r} must take no parameters, or a "
            "single `ev` parameter."
        )
    if "ev" in compiler.params:
        compiler.locals.add("ev")
    stmts = compiler.compile_body()
    if not stmts:
        raise VirelCompileError(
            f"Event handler {fn.__name__!r} has an empty body."
        )
    return CompiledHandler(stmts)


def compile_client_function(fn: Callable[..., Any]) -> tuple[list[str], list[Stmt], set[str]]:
    compiler = FnCompiler(fn, mode="client")
    stmts = compiler.compile_body()
    return compiler.params, stmts, compiler.used_client_fns
