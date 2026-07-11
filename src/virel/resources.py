"""Asynchronous data as a reactive value (SPEC 8.7).

A resource wraps a server action and exposes three reactive states: value,
loading, and error. The browser fetches on load, refetches when reactive
parameters change (with in-flight deduplication), and can be refreshed from
any event handler. With ``server_render=True`` the initial data is fetched
during server rendering, so the page arrives populated and the browser
skips the first fetch.

    runs = ui.resource(list_runs, params={"query": query})

    ui.Suspense(runs,
                content=ui.Each(runs.value, render=run_card),
                fallback=ui.Skeleton())
"""

from __future__ import annotations

from typing import Any

from .expr import (
    Compare,
    DictExpr,
    Expr,
    Lit,
    State,
    VirelCompileError,
    _run_coroutine,
    current_context,
    current_recorder,
    inspect_isawaitable,
    lift,
)


class RefreshOp:
    """Handler op: refetch a resource with its current parameters."""

    def __init__(self, resource: "Resource") -> None:
        self.resource = resource

    def js(self) -> str:
        return f'$.refreshResource("{self.resource.id}");'

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        self.resource.fetch_into(env)

    def to_ir(self) -> dict[str, Any]:
        return {"op": "refresh", "resource": self.resource.id}


class Resource:
    def __init__(self, action: Any, *, params: dict[str, Any] | None = None,
                 server_render: bool = False,
                 stale_for: float | None = None) -> None:
        from .registry import ServerAction
        if not isinstance(action, ServerAction):
            raise VirelCompileError(
                "ui.resource requires a @ui.server action as its first "
                "argument."
            )
        if action.stream_response:
            raise VirelCompileError(
                f"Server action {action.name!r} streams; bind it with "
                ".stream(into=...) from a handler instead of ui.resource."
            )
        ctx = current_context()
        self.action = action
        self.id = ctx.next_id("r")
        self.params: dict[str, Expr] = {
            k: lift(v) for k, v in (params or {}).items()
        }
        action._check_args(self.params)
        self.server_render = server_render
        if stale_for is not None and stale_for < 0:
            raise VirelCompileError("stale_for must be a non-negative number "
                                    "of seconds.")
        self.stale_for = stale_for

        initial_value: Any = None
        initial_error: Any = None
        if server_render:
            env = {name: state.initial for name, state in ctx.states.items()}
            for name, derived in ctx.derived.items():
                env[name] = derived.expr.evaluate(env)
            initial_value, initial_error = self._run_action(env)
        self.value_state = State(initial_value)
        self.loading = State(not server_render)
        self.error = State(initial_error)
        ctx.resources[self.id] = self

    # -- reactive surface --------------------------------------------------------

    @property
    def value(self) -> State:
        return self.value_state

    @property
    def ready(self) -> Expr:
        return Compare("!=", self.value_state, Lit(None))

    def refresh(self) -> None:
        """Record a refetch inside an event handler."""
        current_recorder().ops.append(RefreshOp(self))

    # -- execution (server rendering and tests) -----------------------------------

    def _run_action(self, env: dict[str, Any]) -> tuple[Any, Any]:
        from .registry import to_jsonable
        args = {k: v.evaluate(env) for k, v in self.params.items()}
        try:
            kwargs = self.action.prepare(args)
            result = self.action.fn(**kwargs)
            if inspect_isawaitable(result):
                result = _run_coroutine(result)
            return to_jsonable(result), None
        except Exception as error:
            return None, f"{type(error).__name__}: {error}"

    def fetch_into(self, env: dict[str, Any]) -> None:
        value, error = self._run_action(env)
        env[self.value_state.name] = value
        env[self.error.name] = error
        env[self.loading.name] = False

    # -- emission --------------------------------------------------------------------

    def binding_js(self) -> str:
        parts = [
            f'action: "{self.action.name}"',
            f"value: S.{self.value_state.name}",
            f"loading: S.{self.loading.name}",
            f"error: S.{self.error.name}",
            f"initial: {'true' if self.server_render else 'false'}",
        ]
        if self.stale_for is not None:
            parts.append(f"staleFor: {self.stale_for}")
        if self.params:
            parts.append(f"params: () => ({DictExpr(self.params).js()})")
        return f'$.resource("{self.id}", {{ {", ".join(parts)} }});'

    def to_ir(self) -> dict[str, Any]:
        return {
            "kind": "resource",
            "id": self.id,
            "action": self.action.name,
            "params": {k: v.js() for k, v in self.params.items()},
            "server_render": self.server_render,
        }


def resource(action: Any, *, params: dict[str, Any] | None = None,
             server_render: bool = False,
             stale_for: float | None = None) -> Resource:
    return Resource(action, params=params, server_render=server_render,
                    stale_for=stale_for)
