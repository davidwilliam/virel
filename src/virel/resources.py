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


class InvalidateOp:
    """Handler op: drop cached data for an action and refetch the
    resources bound to it."""

    def __init__(self, action_name: str) -> None:
        self.action_name = action_name

    def js(self) -> str:
        return f'$.invalidate("{self.action_name}");'

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        env.setdefault("__invalidated__", []).append(self.action_name)

    def to_ir(self) -> dict[str, Any]:
        return {"op": "invalidate", "action": self.action_name}


def invalidate(action: Any) -> None:
    """Inside a handler: clear the cache for a server action and refetch
    every resource bound to it (SPEC 8.7 invalidation)."""
    from .registry import ServerAction
    if not isinstance(action, ServerAction):
        raise VirelCompileError(
            "ui.invalidate takes a @ui.server action."
        )
    current_recorder().ops.append(InvalidateOp(action.name))


invalidate.__virel_op__ = "invalidate"


class Resource:
    def __init__(self, action: Any, *, params: dict[str, Any] | None = None,
                 server_render: bool = False,
                 stale_for: float | None = None,
                 retry: int = 0) -> None:
        from .registry import ServerAction
        if not isinstance(action, ServerAction):
            raise VirelCompileError(
                "ui.resource requires a @ui.server action as its first "
                "argument."
            )
        if action.stream_response and server_render:
            raise VirelCompileError(
                "A streaming resource cannot be server-rendered; drop "
                "server_render=True."
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
        if retry < 0:
            raise VirelCompileError("retry must be a non-negative attempt count.")
        self.retry = retry
        self.streaming = action.stream_response

        initial_value: Any = None
        initial_error: Any = None
        # On a render="stream" page, server-rendered resources do not block
        # the response: the shell flushes first and the data streams in as
        # inline data blocks the runtime picks up (SPEC 9.6).
        self.streamed_ssr = bool(server_render
                                 and getattr(ctx, "stream_ssr", False))
        loaded = False
        if server_render and not self.streamed_ssr:
            env = {name: state.initial for name, state in ctx.states.items()}
            for name, derived in ctx.derived.items():
                env[name] = derived.expr.evaluate(env)
            initial_value, initial_error = self._run_action(env)
            loaded = True
        if self.streamed_ssr:
            env = {name: state.initial for name, state in ctx.states.items()}
            for name, derived in ctx.derived.items():
                env[name] = derived.expr.evaluate(env)
            self.stream_args = {k: v.evaluate(env)
                                for k, v in self.params.items()}
        self.value_state = State(initial_value)
        self.loading = State(not loaded)
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
        from .expr import _collect_stream
        from .registry import to_jsonable
        args = {k: v.evaluate(env) for k, v in self.params.items()}
        try:
            kwargs = self.action.prepare(args)
            if self.streaming:
                chunks = _collect_stream(self.action.fn(**kwargs))
                return "".join(str(c) for c in chunks), None
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
        if self.retry:
            parts.append(f"retry: {self.retry}")
        if self.streaming:
            parts.append("stream: true")
        if self.streamed_ssr:
            parts.append('ssr: "streamed"')
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


class Subscription:
    """A live one-way feed from a streaming action over server-sent
    events (SPEC 9.5). Text chunks append into a string state, or JSON
    events append into a list state; the browser reconnects automatically
    and reopens when reactive parameters change."""

    def __init__(self, action: Any, *, params: dict[str, Any] | None = None,
                 into: State | None = None,
                 into_events: State | None = None) -> None:
        from .registry import ServerAction
        if not isinstance(action, ServerAction) or not action.stream_response:
            raise VirelCompileError(
                "ui.subscribe takes a @ui.server(stream=True) action."
            )
        if (into is None) == (into_events is None):
            raise VirelCompileError(
                "ui.subscribe takes exactly one of into= (text) or "
                "into_events= (JSON events)."
            )
        ctx = current_context()
        self.id = ctx.next_id("sub")
        self.action = action
        self.params = {k: lift(v) for k, v in (params or {}).items()}
        action._check_args(self.params)
        self.into = into
        self.into_events = into_events
        ctx.subscriptions.append(self)

    def binding_js(self) -> str:
        parts = [f'"{self.action.name}"']
        if self.params:
            parts.append(f"() => ({DictExpr(self.params).js()})")
        else:
            parts.append("null")
        target = (f"{{ into: S.{self.into.name} }}" if self.into is not None
                  else f"{{ events: S.{self.into_events.name} }}")
        parts.append(target)
        return f"$.sse({', '.join(parts)});"

    def drain_into(self, env: dict[str, Any]) -> None:
        """Test mode: collect the whole (finite) stream synchronously."""
        from .expr import _collect_stream
        from .registry import to_jsonable
        args = {k: v.evaluate(env) for k, v in self.params.items()}
        chunks = _collect_stream(self.action.fn(**args))
        if self.into is not None:
            env[self.into.name] = (env.get(self.into.name) or "") + "".join(
                str(c) for c in chunks)
        else:
            events = [to_jsonable(c) for c in chunks
                      if isinstance(c, (dict, list))]
            env[self.into_events.name] = (env.get(self.into_events.name)
                                          or []) + events


def subscribe(action: Any, *, params: dict[str, Any] | None = None,
              into: State | None = None,
              into_events: State | None = None) -> Subscription:
    return Subscription(action, params=params, into=into,
                        into_events=into_events)


def resource(action: Any, *, params: dict[str, Any] | None = None,
             server_render: bool = False,
             stale_for: float | None = None,
             retry: int = 0) -> Resource:
    return Resource(action, params=params, server_render=server_render,
                    stale_for=stale_for, retry=retry)
