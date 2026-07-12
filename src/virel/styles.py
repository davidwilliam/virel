"""Reusable typed style objects (SPEC 10.4).

``ui.style()`` turns typed properties into a generated CSS class:
spacing in theme space units, colors and radii and shadows as token
references, borders as semantic names, and state variants for hover,
focus, and active. Styles deduplicate by content, compile into the
application stylesheet, and read as ordinary classes in browser
development tools.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .expr import VirelCompileError

_COLOR_TOKENS = {
    "bg": "var(--v-bg)",
    "fg": "var(--v-fg)",
    "fg.muted": "var(--v-fg-muted)",
    "surface.1": "var(--v-surface-1)",
    "surface.2": "var(--v-surface-2)",
    "surface.3": "var(--v-surface-3)",
    "accent": "var(--v-accent)",
    "accent.soft": "var(--v-accent-soft)",
    "accent.fg": "var(--v-accent-fg)",
    "danger": "var(--v-danger)",
    "danger.soft": "var(--v-danger-soft)",
    "success": "var(--v-success)",
    "success.soft": "var(--v-success-soft)",
    "transparent": "transparent",
}

_BORDERS = {
    "subtle": "1px solid var(--v-border)",
    "strong": "1px solid var(--v-border-strong)",
    "accent": "1px solid var(--v-accent)",
    "none": "none",
}


def _space(name: str, value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VirelCompileError(
            f"{name} takes a number of space units, got {value!r}.")
    return f"calc(var(--v-space) * {value:g})"


def _color(name: str, value: Any) -> str:
    if value in _COLOR_TOKENS:
        return _COLOR_TOKENS[value]
    if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{3,8}", value):
        return value
    raise VirelCompileError(
        f"{name} must be a color token ({', '.join(sorted(_COLOR_TOKENS))}) "
        f"or a hex color, got {value!r}.")


def _token(prefix: str, allowed: tuple[str, ...]):
    def resolve(name: str, value: Any) -> str:
        if value not in allowed:
            raise VirelCompileError(
                f"{name} must be one of {', '.join(allowed)}, got {value!r}.")
        return f"var(--v-{prefix}-{value})"
    return resolve


def _border(name: str, value: Any) -> str:
    if value not in _BORDERS:
        raise VirelCompileError(
            f"{name} must be one of {', '.join(sorted(_BORDERS))}, "
            f"got {value!r}.")
    return _BORDERS[value]


def _length(name: str, value: Any) -> str:
    from .elements import _css_length
    return _css_length(value)


def _number(name: str, value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VirelCompileError(f"{name} takes a number, got {value!r}.")
    return f"{value:g}"


# Python property name -> (CSS property, resolver). This is the typed
# vocabulary; anything beyond it belongs in the ui.Box css= escape hatch.
_PROPERTIES: dict[str, tuple[str, Any]] = {
    "padding": ("padding", _space),
    "padding_x": ("padding-inline", _space),
    "padding_y": ("padding-block", _space),
    "margin": ("margin", _space),
    "margin_x": ("margin-inline", _space),
    "margin_y": ("margin-block", _space),
    "gap": ("gap", _space),
    "radius": ("border-radius", _token("radius", ("sm", "md", "lg"))),
    "shadow": ("box-shadow", _token("shadow", ("sm", "md", "lg"))),
    "background": ("background", _color),
    "color": ("color", _color),
    "border": ("border", _border),
    "width": ("width", _length),
    "height": ("height", _length),
    "max_width": ("max-width", _length),
    "min_width": ("min-width", _length),
    "max_height": ("max-height", _length),
    "min_height": ("min-height", _length),
    "opacity": ("opacity", _number),
    "weight": ("font-weight", _number),
}

_STATES = {"hover": ":hover", "focus": ":focus-visible", "active": ":active"}


def _declarations(props: dict[str, Any], context: str) -> str:
    parts = []
    for name, value in props.items():
        spec = _PROPERTIES.get(name)
        if spec is None:
            raise VirelCompileError(
                f"Unknown style property {name!r}{context}; available: "
                f"{', '.join(sorted(_PROPERTIES))}. For anything else use "
                "the ui.Box css= escape hatch.")
        css_property, resolve = spec
        parts.append(f"{css_property}: {resolve(name, value)}")
    return "; ".join(parts)


@dataclass(frozen=True)
class Style:
    """A compiled style object. Pass it anywhere class_name is accepted."""
    class_name: str
    css: str

    def __str__(self) -> str:
        return self.class_name


def style(**props: Any) -> Style:
    """A reusable typed style (SPEC 10.4), compiled to a generated CSS
    class in the application stylesheet:

        card_style = ui.style(padding=6, radius="lg",
                              background="surface.1", border="subtle",
                              hover={"shadow": "md"})
        ui.Stack(..., class_name=card_style)

    Spacing takes theme space units; colors, radii, and shadows take
    token names, so styles follow the theme, brands, and density modes.
    hover=, focus=, and active= take the same properties as variants.
    """
    states = {key: props.pop(key) for key in tuple(_STATES) if key in props}
    if not props and not states:
        raise VirelCompileError("ui.style() needs at least one property.")
    base = _declarations(props, "")
    rules = []
    body = []
    if base:
        body.append(base)
    for state, state_props in states.items():
        if not isinstance(state_props, dict):
            raise VirelCompileError(
                f"{state}= takes a dict of style properties.")
        rules.append((_STATES[state],
                      _declarations(state_props, f" in {state}=")))
    fingerprint = base + "".join(f"{sel}{{{decl}}}" for sel, decl in rules)
    name = "vs-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:8]
    css_parts = []
    if base:
        css_parts.append(f".{name} {{ {base}; }}")
    for selector, declarations in rules:
        css_parts.append(f".{name}{selector} {{ {declarations}; }}")
    css = "\n".join(css_parts)

    from .registry import active_registry
    active_registry().styles[name] = css
    return Style(class_name=name, css=css)
