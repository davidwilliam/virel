"""Animation (SPEC 10.8).

Everything here compiles to real CSS animations and transitions: no
animation loop ships in the runtime, no server traffic occurs, the
browser compositor does the work, and the native devtools Animations
panel inspects every timeline. The runtime's only job is orchestration
at the edges CSS cannot see: enter/exit lifecycles, FLIP layout
animation, and gestures.

Springs are computed at compile time: a damped harmonic oscillator is
simulated in Python and emitted as a CSS linear() easing curve, so
spring physics cost zero JavaScript.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

from .expr import VirelCompileError

# --------------------------------------------------------------------------
# Easing
# --------------------------------------------------------------------------

_EASINGS = {
    "linear": "linear",
    "in": "cubic-bezier(0.32, 0, 0.67, 0)",
    "out": "cubic-bezier(0.16, 1, 0.3, 1)",
    "in-out": "cubic-bezier(0.65, 0, 0.35, 1)",
}


@dataclass(frozen=True)
class Easing:
    """A timing function, optionally carrying the natural duration a
    physical simulation settled in."""
    css: str
    natural_duration: int | None = None


def spring(stiffness: float = 170.0, damping: float = 24.0,
           mass: float = 1.0) -> Easing:
    """Spring physics as a compile-time easing curve. The oscillator is
    simulated in Python and emitted as CSS linear(), so the browser
    plays real spring motion with no JavaScript per frame. Animations
    using a spring inherit its settling time unless given an explicit
    duration."""
    for name, value in (("stiffness", stiffness), ("damping", damping),
                        ("mass", mass)):
        if not isinstance(value, (int, float)) or value <= 0:
            raise VirelCompileError(f"spring {name} must be a positive "
                                    f"number, got {value!r}.")
    position, velocity = 0.0, 0.0
    dt = 0.001
    samples = [0.0]
    settled = 0
    step = 0
    while step < 3000:
        step += 1
        acceleration = (-stiffness * (position - 1.0)
                        - damping * velocity) / mass
        velocity += acceleration * dt
        position += velocity * dt
        if step % 16 == 0:
            samples.append(position)
        if abs(position - 1.0) < 0.001 and abs(velocity) < 0.005:
            settled += 1
            if settled >= 24:
                break
        else:
            settled = 0
    samples.append(1.0)
    points = ", ".join(f"{value:.4f}".rstrip("0").rstrip(".") or "0"
                       for value in samples)
    return Easing(css=f"linear({points})",
                  natural_duration=int(round(step / 10) * 10))


def _easing_css(value: Any) -> str:
    if isinstance(value, Easing):
        return value.css
    if value in _EASINGS:
        return _EASINGS[value]
    raise VirelCompileError(
        f"Easing must be one of {', '.join(_EASINGS)} or a ui.spring(), "
        f"got {value!r}.")


def _duration(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or value < 0 or value > 30_000:
        raise VirelCompileError(
            f"{name} is in milliseconds between 0 and 30000, got {value!r}.")
    return int(value)


# --------------------------------------------------------------------------
# Keyframes
# --------------------------------------------------------------------------

# Properties allowed inside keyframes beyond the ui.style vocabulary.
# These take free-form values (transform lists, filter chains), so the
# values are sanitized rather than typed.
_RAW_FRAME_PROPERTIES = ("transform", "translate", "scale", "rotate",
                         "filter", "offset-distance", "visibility")


def _frame_declarations(props: dict[str, Any], stop: str) -> str:
    from .styles import _PROPERTIES
    parts = []
    for name, value in props.items():
        if name in _RAW_FRAME_PROPERTIES:
            text = str(value)
            if re.search(r"[;{}<>]", text):
                raise VirelCompileError(
                    f"Keyframe value for {name!r} at {stop!r} contains "
                    "characters that are not allowed in a declaration.")
            parts.append(f"{name}: {text}")
            continue
        spec = _PROPERTIES.get(name)
        if spec is None:
            raise VirelCompileError(
                f"Unknown keyframe property {name!r} at {stop!r}; expected "
                f"a style property or one of "
                f"{', '.join(_RAW_FRAME_PROPERTIES)}.")
        css_property, resolve = spec
        parts.append(f"{css_property}: {resolve(name, value)}")
    return "; ".join(parts)


@dataclass(frozen=True)
class Keyframes:
    name: str
    css: str


def keyframes(stops: dict[str, dict[str, Any]]) -> Keyframes:
    """Typed keyframes compiled to a named @keyframes rule:

        pulse = ui.keyframes({"0%": {"opacity": 1},
                              "50%": {"opacity": 0.4},
                              "100%": {"opacity": 1}})

    Stops are percentages (or "from"/"to"); values take the ui.style
    vocabulary plus transform, filter, and friends. Identical keyframes
    deduplicate to one rule."""
    if not isinstance(stops, dict) or not stops:
        raise VirelCompileError("ui.keyframes takes a dict of stops.")
    body_parts = []
    for stop, props in stops.items():
        stop_text = str(stop).strip()
        if stop_text not in ("from", "to"):
            match = re.fullmatch(r"(\d{1,3})%", stop_text)
            if not match or int(match.group(1)) > 100:
                raise VirelCompileError(
                    f"Keyframe stop must be 'from', 'to', or '0%'..'100%', "
                    f"got {stop!r}.")
        if not isinstance(props, dict) or not props:
            raise VirelCompileError(
                f"Keyframe stop {stop!r} takes a dict of properties.")
        body_parts.append(
            f"  {stop_text} {{ {_frame_declarations(props, stop_text)}; }}")
    body = "\n".join(body_parts)
    name = "vk-" + hashlib.sha256(body.encode()).hexdigest()[:8]
    css = f"@keyframes {name} {{\n{body}\n}}"
    from .registry import active_registry
    active_registry().keyframes[name] = css
    return Keyframes(name=name, css=css)


# --------------------------------------------------------------------------
# Style property values: animation= and transition=
# --------------------------------------------------------------------------

_TRANSITIONABLE = (
    "opacity", "transform", "translate", "scale", "rotate", "filter",
    "background", "background-color", "color", "border-color",
    "box-shadow", "outline-color", "width", "height", "max-height",
    "max-width", "flex-basis", "gap", "padding", "margin", "inset",
    "visibility",
)

_DIRECTIONS = ("normal", "reverse", "alternate", "alternate-reverse")
_FILLS = ("none", "forwards", "backwards", "both")


@dataclass(frozen=True)
class TransitionValue:
    css: str


@dataclass(frozen=True)
class AnimationValue:
    css: str
    duration: int
    essential: bool


def transition(*properties: str, duration: int = 180,
               easing: Any = "out", delay: int = 0) -> TransitionValue:
    """A typed CSS transition for ui.style:

        ui.style(transition=ui.transition("transform", "box-shadow",
                                          duration=180, easing="out"),
                 hover={"shadow": "md"})
    """
    if not properties:
        raise VirelCompileError(
            "ui.transition needs at least one property to transition.")
    for prop in properties:
        if prop not in _TRANSITIONABLE:
            raise VirelCompileError(
                f"Cannot transition {prop!r}; supported: "
                f"{', '.join(_TRANSITIONABLE)}.")
    if isinstance(easing, Easing) and easing.natural_duration \
            and duration == 180:
        duration = easing.natural_duration
    ms = _duration("duration", duration)
    wait = _duration("delay", delay)
    timing = _easing_css(easing)
    suffix = f" {wait}ms" if wait else ""
    css = ", ".join(f"{prop} {ms}ms {timing}{suffix}" for prop in properties)
    return TransitionValue(css=css)


def animation(frames: Keyframes, *, duration: int | None = None,
              easing: Any = "out", delay: int = 0,
              iterations: int | str = 1, direction: str = "normal",
              fill: str = "both", essential: bool = False) -> AnimationValue:
    """A typed CSS animation for ui.style:

        ui.style(animation=ui.animation(pulse, duration=1200,
                                        easing="in-out",
                                        iterations="infinite"))

    essential=True exempts the animation from the global reduced-motion
    collapse, for the rare motion that conveys state (progress, live
    indicators) rather than decoration."""
    if not isinstance(frames, Keyframes):
        raise VirelCompileError(
            "ui.animation takes ui.keyframes(...) as its first argument.")
    if duration is None:
        duration = (easing.natural_duration
                    if isinstance(easing, Easing) and easing.natural_duration
                    else 300)
    if iterations != "infinite" and (isinstance(iterations, bool)
                                     or not isinstance(iterations, int)
                                     or iterations < 1):
        raise VirelCompileError(
            f"iterations is a positive integer or 'infinite', "
            f"got {iterations!r}.")
    if direction not in _DIRECTIONS:
        raise VirelCompileError(
            f"direction must be one of {', '.join(_DIRECTIONS)}.")
    if fill not in _FILLS:
        raise VirelCompileError(f"fill must be one of {', '.join(_FILLS)}.")
    ms = _duration("duration", duration)
    wait = _duration("delay", delay)
    css = (f"{ms}ms {_easing_css(easing)} {wait}ms {iterations} "
           f"{direction} {fill} {frames.name}")
    return AnimationValue(css=css, duration=ms, essential=essential)


# --------------------------------------------------------------------------
# Enter/exit and layout animation
# --------------------------------------------------------------------------

# Preset enter keyframes; exits are the same frames reversed by the
# runtime class, so one definition serves both directions.
_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "fade": {"from": {"opacity": 0}, "to": {"opacity": 1}},
    "fade-up": {"from": {"opacity": 0, "transform": "translateY(10px)"},
                "to": {"opacity": 1, "transform": "translateY(0)"}},
    "fade-down": {"from": {"opacity": 0, "transform": "translateY(-10px)"},
                  "to": {"opacity": 1, "transform": "translateY(0)"}},
    "scale": {"from": {"opacity": 0, "transform": "scale(0.94)"},
              "to": {"opacity": 1, "transform": "scale(1)"}},
    "slide-left": {"from": {"opacity": 0, "transform": "translateX(16px)"},
                   "to": {"opacity": 1, "transform": "translateX(0)"}},
    "slide-right": {"from": {"opacity": 0, "transform": "translateX(-16px)"},
                    "to": {"opacity": 1, "transform": "translateX(0)"}},
}


class Motion:
    """Enter, exit, and layout animation for conditional content and
    lists (SPEC 10.8):

        ui.When(show, then=panel, animate=ui.Motion(enter="fade-up",
                                                    exit="fade"))
        ui.Each(items, render=row, key=..., animate=ui.Motion(
            enter="slide-right", exit="fade", layout=True))

    enter= and exit= take a preset name or ui.keyframes(...); layout=True
    adds FLIP animation, so reordered items glide to their new position.
    reduced="none" removes the animation entirely under reduced motion
    (the default collapses it to instant, which suits most cases)."""

    def __init__(self, *, enter: Any = None, exit: Any = None,
                 layout: bool = False, duration: int = 220,
                 easing: Any = "out", reduced: str = "collapse") -> None:
        if enter is None and exit is None and not layout:
            raise VirelCompileError(
                "ui.Motion needs enter=, exit=, or layout=True.")
        if reduced not in ("collapse", "none"):
            raise VirelCompileError(
                "reduced must be 'collapse' or 'none'.")
        if isinstance(easing, Easing) and easing.natural_duration \
                and duration == 220:
            duration = easing.natural_duration
        self.duration = _duration("duration", duration)
        self.easing = _easing_css(easing)
        self.layout = layout
        self.reduced = reduced
        self.enter_class = self._compile(enter, "normal") if enter else None
        self.exit_class = self._compile(exit, "reverse") if exit else None

    def _compile(self, frames: Any, direction: str) -> str:
        if isinstance(frames, str):
            if frames not in _PRESETS:
                raise VirelCompileError(
                    f"Unknown motion preset {frames!r}; available: "
                    f"{', '.join(_PRESETS)}.")
            frames = keyframes(_PRESETS[frames])
        if not isinstance(frames, Keyframes):
            raise VirelCompileError(
                "enter= and exit= take a preset name or ui.keyframes(...).")
        rule = (f"animation: {self.duration}ms {self.easing} 0ms 1 "
                f"{direction} both {frames.name};")
        fingerprint = rule
        name = "vm-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:8]
        css = f".{name} {{ {rule} }}"
        if self.reduced == "none":
            css += (f"\n@media (prefers-reduced-motion: reduce) {{ "
                    f".{name} {{ animation: none !important; }} }}")
        from .registry import active_registry
        active_registry().styles[name] = css
        return name

    def config(self) -> dict[str, Any]:
        """The runtime configuration passed to bindShow/bindList."""
        config: dict[str, Any] = {}
        if self.enter_class:
            config["enter"] = self.enter_class
        if self.exit_class:
            config["exit"] = self.exit_class
        if self.layout:
            config["flip"] = True
            config["flipDuration"] = self.duration
            config["flipEasing"] = self.easing
        return config


def coerce_motion(value: Any) -> Motion | None:
    """animate= accepts a Motion or a preset name shorthand (which
    animates both directions with the same frames)."""
    if value is None:
        return None
    if isinstance(value, Motion):
        return value
    if isinstance(value, str):
        return Motion(enter=value, exit=value)
    raise VirelCompileError(
        "animate= takes a ui.Motion(...) or a preset name.")
