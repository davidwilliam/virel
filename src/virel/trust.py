"""Trust boundaries (SPEC 18.1).

Code and data are classified by where they may live:

- client-safe: JSON-compatible constants, reactive state, @ui.client
  and @ui.worker functions, and server actions (by reference) may cross
  into browser-compiled code.
- server-only: values marked ``ui.server_only(...)`` or read with
  ``ui.secret(...)`` never cross; referencing one from client-compilable
  code (an event handler, @ui.client, @ui.worker, or a reactive
  expression) is a build error.
- public build-time and secret build-time are the two ends of
  build-time data: ``ui.build`` results are public; a secret build value
  wraps in ``ui.server_only``.
- explicitly shared: @ui.shared functions run on both sides by design.

The rule the spec names -- importing a server secret into
client-compilable code must be a build error -- is enforced by the
client compiler and the symbolic layer refusing to lift a ServerOnly.
"""

from __future__ import annotations

import os
from typing import Any

from .expr import VirelCompileError


class ServerOnly:
    """A value that must never reach the browser. Readable on the server
    with ``.get()``; any attempt to compile it into client code fails."""

    __slots__ = ("_value", "_label")

    def __init__(self, value: Any, label: str = "value") -> None:
        self._value = value
        self._label = label

    def get(self) -> Any:
        """Read the value on the server (server actions, guards, build
        functions, SSR)."""
        return self._value

    def _refuse(self, *_a: Any, **_k: Any):
        raise VirelCompileError(
            f"Server-only {self._label!r} cannot cross the client boundary "
            "(SPEC 18.1). Read it on the server with .get() inside a "
            "@ui.server action or a guard, and send only the derived, "
            "non-secret result to the browser.")

    # Any use in a reactive/client context routes through the compiler,
    # which checks for ServerOnly; these guard direct misuse too.
    __bool__ = _refuse
    __str__ = _refuse
    __iter__ = _refuse

    def __repr__(self) -> str:
        return f"<ServerOnly {self._label!r}>"


def server_only(value: Any, *, label: str = "value") -> ServerOnly:
    """Mark a value as server-only (SPEC 18.1): it may be read on the
    server but never compiled into client code.

        DATABASE_URL = ui.server_only(os.environ["DATABASE_URL"],
                                      label="DATABASE_URL")
    """
    return ServerOnly(value, label)


def secret(name: str, *, default: Any = None) -> ServerOnly:
    """Read a secret from the environment as a server-only value
    (SPEC 18.1). Referencing the result in client code is a build error.

        STRIPE_KEY = ui.secret("STRIPE_KEY")
    """
    value = os.environ.get(name, default)
    return ServerOnly(value, label=name)


def is_server_only(value: Any) -> bool:
    return isinstance(value, ServerOnly)
