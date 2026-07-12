"""Notifications (SPEC 11.1): toasts raised from event handlers.

``ui.notify`` is a handler op like state mutation: it compiles to a
runtime call in the browser and records into the test view in Python.
The runtime renders toasts into a polite live region, so screen readers
announce them without stealing focus.
"""

from __future__ import annotations

import json
from typing import Any

from .expr import Expr, VirelCompileError, current_recorder, lift

_INTENTS = ("neutral", "primary", "success", "danger")


class NotifyOp:
    def __init__(self, message: Expr, intent: str, duration: int) -> None:
        self.message = message
        self.intent = intent
        self.duration = duration

    def js(self) -> str:
        opts = json.dumps({"intent": self.intent, "duration": self.duration})
        return f"$.notify({self.message.js()}, {opts});"

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        env.setdefault("__notifications__", []).append(
            {"message": self.message.evaluate(env), "intent": self.intent})

    def to_ir(self) -> dict[str, Any]:
        return {"op": "notify", "message": self.message.js(),
                "intent": self.intent, "duration": self.duration}


def notify(message: Any, *, intent: str = "neutral",
           duration: int = 5000) -> None:
    """Inside a handler: raise a toast notification.

        ui.Button("Save", on_click=lambda: ui.notify("Saved.",
                                                     intent="success"))

    Messages may be reactive (f-strings over state). duration is in
    milliseconds; 0 keeps the toast until dismissed. Toasts land in an
    aria-live region, pause their timer on hover, and animate out."""
    if intent not in _INTENTS:
        raise VirelCompileError(
            f"notify intent must be one of {', '.join(_INTENTS)}, "
            f"got {intent!r}.")
    if isinstance(duration, bool) or not isinstance(duration, int) \
            or duration < 0 or duration > 60_000:
        raise VirelCompileError(
            "notify duration is milliseconds between 0 and 60000 "
            "(0 keeps the toast until dismissed).")
    current_recorder().ops.append(NotifyOp(lift(message), intent, duration))


notify.__virel_op__ = "notify"  # type: ignore[attr-defined]
