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


def _transform(name: str, value: Any) -> str:
    text = str(value)
    if re.search(r"[;{}<>]", text):
        raise VirelCompileError(
            f"{name} contains characters that are not allowed in a "
            "declaration.")
    return text


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
    "transform": ("transform", _transform),
}

def _container_type(name: str, value: Any) -> str:
    if value is True:
        return "inline-size"
    if value in ("inline-size", "size"):
        return value
    raise VirelCompileError(
        f"{name} must be True, 'inline-size', or 'size', got {value!r}.")


_PROPERTIES["container"] = ("container-type", _container_type)

_STATES = {"hover": ":hover", "focus": ":focus-visible", "active": ":active"}

# Media variants (SPEC 10.7): the same viewport breakpoints as Grid
# columns, plus pointer capability so touch interfaces can adapt.
_MEDIA = {
    "md": "(min-width: 768px)",
    "xl": "(min-width: 1200px)",
    "pointer_coarse": "(pointer: coarse)",
    "pointer_fine": "(pointer: fine)",
}


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


def _pop_motion(props: dict[str, Any]) -> tuple[str, list[str]]:
    """transition= and animation= take the typed values from
    ui.transition and ui.animation (SPEC 10.8). An essential animation
    re-declares its duration under reduced motion, exempting it from the
    global collapse: motion that conveys state, not decoration."""
    from .motion import AnimationValue, TransitionValue
    declarations = []
    extra_rules = []
    if "transition" in props:
        value = props.pop("transition")
        if not isinstance(value, TransitionValue):
            raise VirelCompileError(
                "transition= takes ui.transition(...), not a raw string.")
        declarations.append(f"transition: {value.css}")
    if "animation" in props:
        value = props.pop("animation")
        if not isinstance(value, AnimationValue):
            raise VirelCompileError(
                "animation= takes ui.animation(...), not a raw string.")
        declarations.append(f"animation: {value.css}")
        if value.essential:
            extra_rules.append(
                "@media (prefers-reduced-motion: reduce) { .{name} { "
                + f"animation-duration: {value.duration}ms !important; "
                + "} }")
    return "; ".join(declarations), extra_rules


def _variant(kind: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VirelCompileError(f"{kind}= takes a dict of style properties.")
    return value


def style(**props: Any) -> Style:
    """A reusable typed style (SPEC 10.4), compiled to a generated CSS
    class in the application stylesheet:

        card_style = ui.style(padding=6, radius="lg",
                              background="surface.1", border="subtle",
                              hover={"shadow": "md"})
        ui.Stack(..., class_name=card_style)

    Spacing takes theme space units; colors, radii, and shadows take
    token names, so styles follow the theme, brands, and density modes.

    Variants take the same properties (SPEC 10.7): hover=, focus=, and
    active= for states; md= and xl= for the viewport breakpoints;
    pointer_coarse= and pointer_fine= for input capability; and
    container_min={"30rem": {...}} for container queries against the
    nearest ancestor declaring container= (True or 'inline-size').
    """
    motion_decls, motion_rules = _pop_motion(props)
    states = {key: _variant(key, props.pop(key))
              for key in tuple(_STATES) if key in props}
    media = {key: _variant(key, props.pop(key))
             for key in tuple(_MEDIA) if key in props}
    container_min = props.pop("container_min", None) or {}
    if not isinstance(container_min, dict):
        raise VirelCompileError("container_min= takes a dict mapping a "
                                "minimum width to style properties.")
    if not props and not states and not media and not container_min \
            and not motion_decls:
        raise VirelCompileError("ui.style() needs at least one property.")

    base = _declarations(props, "")
    if motion_decls:
        base = "; ".join(filter(None, [base, motion_decls]))
    css_parts = []
    if base:
        css_parts.append(".{name} { " + base + "; }")
    css_parts.extend(motion_rules)
    for state, state_props in states.items():
        css_parts.append(".{name}" + _STATES[state] + " { "
                         + _declarations(state_props, f" in {state}=") + "; }")
    for key, media_props in media.items():
        css_parts.append(f"@media {_MEDIA[key]} {{ .{{name}} {{ "
                         + _declarations(media_props, f" in {key}=") + "; } }")
    for width, query_props in container_min.items():
        from .elements import _css_length
        css_parts.append(
            f"@container (min-width: {_css_length(width)}) {{ .{{name}} {{ "
            + _declarations(_variant("container_min", query_props),
                            " in container_min=") + "; } }")

    fingerprint = "\n".join(css_parts)
    name = "vs-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:8]
    css = "\n".join(part.replace("{name}", name) for part in css_parts)

    from .registry import active_registry
    active_registry().styles[name] = css
    return Style(class_name=name, css=css)


def recipe(*, base: Any, variants: dict[str, dict[str, Any]],
           defaults: dict[str, str] | None = None) -> Any:
    """A component with organization-defined variants (SPEC 10.6). Each
    variant axis becomes a keyword argument on the returned component;
    each option is a dict of ui.style() properties (or a ready Style):

        ProjectCard = ui.recipe(
            base=ui.Card,
            variants={"status": {
                "active": {"border": "accent", "background": "surface.1"},
                "paused": {"background": "surface.2", "opacity": 0.8},
            }},
            defaults={"status": "active"},
        )
        ProjectCard(ui.Text("Atlas"), status="paused", gap=3)

    Everything else passes through to the base component, and a caller's
    class_name composes with the variant classes.
    """
    if not variants:
        raise VirelCompileError("ui.recipe needs at least one variant axis.")
    compiled: dict[str, dict[str, Style]] = {}
    for axis, options in variants.items():
        if not isinstance(options, dict) or not options:
            raise VirelCompileError(
                f"Variant axis {axis!r} takes a dict of named options.")
        compiled[axis] = {
            option: props if isinstance(props, Style) else style(**props)
            for option, props in options.items()
        }
    for axis, choice in (defaults or {}).items():
        if axis not in compiled or choice not in compiled[axis]:
            raise VirelCompileError(
                f"Default {axis}={choice!r} does not match a variant.")

    def component(*children: Any, **kwargs: Any) -> Any:
        classes: list[Any] = []
        for axis, options in compiled.items():
            choice = kwargs.pop(axis, (defaults or {}).get(axis))
            if choice is None:
                continue
            if choice not in options:
                raise VirelCompileError(
                    f"Unknown {axis} variant {choice!r}; expected one of "
                    f"{', '.join(options)}.")
            classes.append(options[choice])
        extra = kwargs.pop("class_name", None)
        if isinstance(extra, (list, tuple)):
            classes.extend(extra)
        elif extra is not None:
            classes.append(extra)
        return base(*children,
                    class_name=classes if classes else None, **kwargs)

    component.variants = {axis: tuple(options)
                          for axis, options in compiled.items()}
    return component
