"""Deterministic diagnostics (SPEC 14.5).

Compile failures carry a stable error code, a JSON form, an
explanation, a documentation key, and suggested fixes, so agents and
tools consume diagnostics without scraping prose. Codes are assigned by
matching the error message against known patterns; unmatched errors get
a generic code rather than failing.
"""

from __future__ import annotations

import re
from typing import Any

# code -> (message pattern, explanation, doc key, suggested fixes)
_RULES: list[tuple[str, re.Pattern, str, str, list[str]]] = [
    ("VRL001", re.compile(r"reactive value cannot be used in a Python `if`"),
     "A reactive value's value only exists in the browser, so it cannot "
     "drive a Python if/and/or/not at compile time.",
     "reactivity/conditionals",
     ["Use ui.When(condition, then=..., otherwise=...) for rendering.",
      "Use ui.cond(condition, a, b) for a reactive expression."]),
    ("VRL002", re.compile(r"(not in the client subset|client subset)"),
     "This Python construct has no client-side equivalent in the handler "
     "compiler.",
     "handlers/client-subset",
     ["Keep handlers to the supported subset, or move logic into a "
      "@ui.server action and call it.",
      "Compute derived values with ui.derived instead."]),
    ("VRL003", re.compile(r"has no accessible name"),
     "An interactive element must have a name for assistive technology.",
     "accessibility/names",
     ["Add text content, or pass aria_label=.",
      "For icon-only buttons, use Icon(label=...)."]),
    ("VRL004", re.compile(r"blocked URL scheme|blocked scheme"),
     "The URL uses a scheme outside the safe allowlist (http, https, "
     "mailto, tel, relative).",
     "security/urls",
     ["Use a relative path or an http(s) URL.",
      "For inline data, use a data: URL only where explicitly allowed."]),
    ("VRL005", re.compile(r"requires alt text|Image requires alt"),
     "Images require alternative text for accessibility.",
     "accessibility/images",
     ['Pass alt="a description".',
      'Use alt="" only for purely decorative images.']),
    ("VRL006", re.compile(r"must return ui\.Page"),
     "A @ui.page function must return ui.Page(...).",
     "pages/return",
     ["Wrap the page content in ui.Page(..., title=...)."]),
    ("VRL007", re.compile(r"requires a `reason`|requires a reason"),
     "Escape hatches require a written reason for review.",
     "escape-hatches/reason",
     ['Pass reason="why the typed API is not enough".',
      "Prefer a typed component if one fits."]),
    ("VRL008", re.compile(r"prohibited by policy"),
     "A deployment policy prohibits this construct.",
     "policy",
     ["Remove the prohibited construct.",
      "Relax the policy with ui.use_policy(...) if appropriate."]),
    ("VRL009", re.compile(r"(is required|takes exactly one|needs at least|"
                          r"must be one of|requires )"),
     "A component or API was called with invalid arguments.",
     "components/arguments",
     ["Check the component schema with `virel schema <Name>`."]),
    ("VRL010", re.compile(r"Assigning to .* would shadow a reactive"),
     "Assigning to a reactive name shadows it with a local variable.",
     "handlers/state",
     ["Use state.set(...) or state.update(...) to change reactive state.",
      "Pick a different local name."]),
]

_GENERIC = ("VRL000", "A construct could not be compiled.",
            "compiler", ["Read the message for the specific fix named."])


def classify(message: str) -> dict[str, Any]:
    """Structured diagnostic for a compile error message (SPEC 14.5)."""
    route = None
    range_info = None
    route_match = re.search(r"\[route ([^\]]+)\]", message)
    if route_match:
        route = route_match.group(1)
    handler_match = re.search(r"\[(\w+), line (\d+)\]", message)
    if handler_match:
        range_info = {"handler": handler_match.group(1),
                      "line": int(handler_match.group(2))}
    for code, pattern, explanation, doc_key, fixes in _RULES:
        if pattern.search(message):
            return {
                "code": code,
                "message": message,
                "explanation": explanation,
                "documentation": f"https://virelui.com/errors/{doc_key}",
                "route": route,
                "range": range_info,
                "fixes": fixes,
            }
    code, explanation, doc_key, fixes = _GENERIC
    return {
        "code": code, "message": message, "explanation": explanation,
        "documentation": f"https://virelui.com/errors/{doc_key}",
        "route": route, "range": range_info, "fixes": fixes,
    }
