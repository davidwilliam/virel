"""Typed request context (SPEC 8.6).

A context carries per-request values from guards into pages and actions
without global mutable state:

    current_user = ui.context("current_user")

    def load_session(request: ui.Request):
        user = sessions.lookup(request.cookies.get("session"))
        if user is None:
            return ui.redirect("/login")
        current_user.provide(user)

    @ui.page("/dashboard", guard=load_session)
    def dashboard() -> ui.Node:
        user = current_user.get()
        return ui.Page(ui.Text(f"Hello {user['name']}"))

A page that reads a request-provided value compiles per request and is
never cached or prebuilt. Reading a declared ``default`` keeps the page
static-friendly.
"""

from __future__ import annotations

import contextvars
from typing import Any

from .expr import VirelCompileError, current_context, in_trace

_MISSING = object()

_request_context: contextvars.ContextVar[dict[str, Any] | None] = \
    contextvars.ContextVar("virel_request_context", default=None)


class ContextMissingError(VirelCompileError):
    """A context value was read with no provider and no default."""


class Context:
    def __init__(self, name: str, default: Any = _MISSING) -> None:
        self.name = name
        self.default = default

    def __class_getitem__(cls, item: Any) -> type["Context"]:
        # Typing sugar: ui.Context[User] reads naturally in annotations.
        return cls

    def provide(self, value: Any) -> None:
        """Set the value for the current request (called from a guard)."""
        store = _request_context.get()
        if store is None:
            raise VirelCompileError(
                f"Context {self.name!r} can only be provided during a "
                "request (from a guard) or through ui.test.render(context=...)."
            )
        store[self.name] = value

    def get(self) -> Any:
        store = _request_context.get()
        if store is not None and self.name in store:
            if in_trace():
                # Request-provided values vary per request: the page must
                # compile per request and never be cached.
                current_context().uses_request_context = True
            return store[self.name]
        if self.default is not _MISSING:
            return self.default
        raise ContextMissingError(
            f"No value provided for context {self.name!r}. Provide it from "
            "a guard with .provide(value), pass it to ui.test.render("
            f"context={{...}}), or declare a default: "
            f"ui.context({self.name!r}, default=...)."
        )


def context(name: str, default: Any = _MISSING) -> Context:
    return Context(name, default)


class request_context:
    """Installs a fresh per-request context store (server and tests)."""

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self.initial = dict(initial or {})
        self._token: contextvars.Token | None = None

    def __enter__(self) -> dict[str, Any]:
        self._token = _request_context.set(self.initial)
        return self.initial

    def __exit__(self, *exc: Any) -> None:
        if self._token is not None:
            _request_context.reset(self._token)
