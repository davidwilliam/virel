"""Explicit escape hatches (SPEC 13.3), as ``ui.unsafe``.

Raw JavaScript and raw HTML are last resorts: each requires a written
reason, each is inspectable in the compiled output, and both can be
prohibited outright by policy (``ui.use_policy(raw_javascript=False)``),
which strict enterprise deployments use to make the escape hatches
unrepresentable.
"""

from __future__ import annotations

from typing import Any

from .expr import VirelCompileError


class RawJavaScript:
    """A raw JavaScript event handler. It emits verbatim into the page
    module; in Python tests it refuses to run rather than pretending."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason

    def js_body(self) -> str:
        return self.code

    def js(self) -> str:
        return f"(ev) => {{ {self.code} }}"

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        raise AssertionError(
            "This element's handler is raw JavaScript "
            f"(reason: {self.reason}); it cannot execute in Python tests. "
            "Cover it with a browser test instead.")

    def to_ir(self) -> list[dict[str, Any]]:
        return [{"op": "unsafe_javascript", "reason": self.reason}]


def javascript(code: str, *, reason: str) -> RawJavaScript:
    """Raw JavaScript as an event handler, the explicit last resort:

        on_click=ui.unsafe.javascript("window.vendorSdk.track()",
                                      reason="Vendor SDK has no module API")

    A written reason is required, and policy may prohibit this entirely.
    """
    if not reason or not str(reason).strip():
        raise VirelCompileError(
            "ui.unsafe.javascript requires a `reason` explaining why the "
            "typed API is not sufficient.")
    if not code or not str(code).strip():
        raise VirelCompileError("ui.unsafe.javascript needs code.")
    from .registry import active_registry
    if not active_registry().policy.get("raw_javascript", True):
        raise VirelCompileError(
            "Raw JavaScript is prohibited by policy "
            "(ui.use_policy(raw_javascript=False)).")
    return RawJavaScript(str(code), str(reason))


def html(markup: str, *, reason: str):
    """Raw HTML, aliasing ui.unsafe_html under the unsafe namespace."""
    from .elements import unsafe_html
    return unsafe_html(markup, reason=reason)
