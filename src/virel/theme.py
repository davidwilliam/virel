"""Design tokens compiled to CSS custom properties (SPEC 10.1).

Themes are typed Python objects. Tokens compile to CSS variables with
automatic light/dark support; components consume only semantic tokens.
Color scales derive their tints, shades, and readable foregrounds from a
single base color, so a brand needs one hex value, not a palette.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from importlib import resources
from typing import Any


# --------------------------------------------------------------------------
# Color math (stdlib only)
# --------------------------------------------------------------------------

def _hex_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raise ValueError(f"Expected a hex color like '#4f46e5', got {value!r}.")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _rgb_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(min(255, max(0, ch))):02x}" for ch in rgb)


def _mix(color: str, into: str, amount: float) -> str:
    """Blend ``color`` toward ``into`` by ``amount`` (0..1)."""
    a, b = _hex_rgb(color), _hex_rgb(into)
    return _rgb_hex(tuple(ca + (cb - ca) * amount for ca, cb in zip(a, b)))


def _lightness(color: str, factor: float) -> str:
    r, g, b = (ch / 255 for ch in _hex_rgb(color))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    rgb = colorsys.hls_to_rgb(h, min(1.0, max(0.0, l * factor)), s)
    return _rgb_hex(tuple(ch * 255 for ch in rgb))


def _luminance(color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _hex_rgb(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _alpha(color: str, alpha: float) -> str:
    r, g, b = _hex_rgb(color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _readable_fg(base: str) -> str:
    """White text on anything but genuinely light colors. A pure WCAG
    ratio comparison prefers dark text on mid-tone colors like emerald,
    which reads worse in practice; a luminance threshold matches how
    every major design system resolves this."""
    return "#ffffff" if _luminance(base) < 0.4 else "#16181d"


@dataclass(frozen=True)
class ColorScale:
    """A semantic color with every derived token components consume:
    the base, a stronger shade for hover and active states, a readable
    foreground, subtle tints for each mode, and focus-ring colors. The
    dark-mode variants let a color flip between modes, as monochrome
    palettes need (near-black in light mode, white in dark mode)."""
    base: str
    strong: str
    fg: str
    soft: str
    soft_dark: str
    ring: str
    ring_dark: str
    base_dark: str
    strong_dark: str
    fg_dark: str


class Color:
    @staticmethod
    def scale(base: str, *, dark: str | None = None,
              strong: str | None = None, fg: str | None = None,
              soft: str | None = None, soft_dark: str | None = None,
              ring: str | None = None,
              ring_dark: str | None = None) -> ColorScale:
        """Derive a full color scale from one base color. Every derived
        value can be overridden, and ``dark=`` swaps in a different base
        for dark mode with its own derived tokens. The foreground is
        picked for readability, so light accents get dark text."""
        _hex_rgb(base)  # validate early with a precise error
        base_dark = dark or base
        return ColorScale(
            base=base,
            strong=strong or _lightness(base, 0.82),
            fg=fg or _readable_fg(base),
            soft=soft or _mix(base, "#ffffff", 0.90),
            soft_dark=soft_dark or _mix(base_dark, "#17181e", 0.78),
            ring=ring or _alpha(base, 0.35),
            ring_dark=ring_dark or _alpha(_lightness(base_dark, 1.35), 0.4),
            base_dark=base_dark,
            strong_dark=_lightness(base_dark, 0.82) if dark
            else (strong or _lightness(base, 0.82)),
            fg_dark=_readable_fg(base_dark) if dark
            else (fg or _readable_fg(base)),
        )


@dataclass(frozen=True)
class Space:
    """The spacing scale: every gap and padding is a multiple of this
    base unit, which is what makes density modes possible."""
    base: int = 4

    @staticmethod
    def scale(base: int = 4) -> "Space":
        return Space(base)


@dataclass(frozen=True)
class Font:
    """A typography role. With ``google=True`` the family loads from
    Google Fonts; with ``src=`` it loads as a self-hosted @font-face.

        ui.Theme(typography={"body": ui.Font("Manrope", google=True)})
    """
    family: str
    fallback: str = "ui-sans-serif, system-ui, sans-serif"
    google: bool = False
    src: str | None = None
    weights: tuple = (400, 500, 600, 700)

    def stack(self) -> str:
        return f"'{self.family}', {self.fallback}"


@dataclass
class FontFace:
    """A self-hosted font: a file the project serves (e.g. from public/).

        ui.Theme(fonts=[ui.FontFace("Recursive", "/public/fonts/Recursive.woff2")],
                 font_body="'Recursive', sans-serif")
    """
    family: str
    src: str
    weight: str = "100 900"
    style: str = "normal"

    def css(self) -> str:
        return (
            "@font-face {\n"
            f"  font-family: '{self.family}';\n"
            f"  font-style: {self.style};\n"
            f"  font-weight: {self.weight};\n"
            "  font-display: swap;\n"
            f"  src: url('{self.src}') format('woff2');\n"
            "}"
        )


@dataclass
class GoogleFont:
    """A font loaded from Google Fonts. The stylesheet link is added to
    every page and the content security policy is extended to allow the
    Google Fonts origins.

        ui.Theme(fonts=[ui.GoogleFont("Manrope")],
                 font_body="'Manrope', sans-serif")
    """
    family: str
    weights: tuple = (400, 500, 600, 700)

    def css_url(self) -> str:
        family = self.family.replace(" ", "+")
        weights = ";".join(str(w) for w in sorted(set(self.weights)))
        return (f"https://fonts.googleapis.com/css2?"
                f"family={family}:wght@{weights}&display=swap")


@dataclass
class Theme:
    accent: str = "#4f46e5"
    accent_strong: str = "#4338ca"
    accent_fg: str = "#ffffff"
    danger: str = "#dc2626"
    danger_strong: str = "#b91c1c"
    success: str = "#16a34a"
    space_base: int = 4  # px
    radius: dict[str, int] = field(default_factory=lambda: {"sm": 4, "md": 8, "lg": 14})
    font_body: str = (
        "'InterVariable', ui-sans-serif, system-ui, -apple-system, "
        "'Segoe UI', Roboto, sans-serif"
    )
    font_heading: str = "inherit"
    font_mono: str = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    # Additional fonts: FontFace (self-hosted files) and GoogleFont entries.
    fonts: list = field(default_factory=list)
    # Typed token forms (SPEC 10.1). color= maps semantic roles to a
    # ColorScale or a base hex; "surface" tints the neutral ramp.
    color: dict[str, Any] | None = None
    space: Space | None = None
    typography: dict[str, Any] | None = None
    # Density modes: data-density="name" rescales the spacing unit.
    densities: dict[str, float] = field(
        default_factory=lambda: {"compact": 0.75})
    # Organization brands and tenant themes: complete themes selected at
    # runtime (or per tenant) with data-brand="name" on the root element.
    brands: dict[str, "Theme"] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.space is not None:
            self.space_base = self.space.base
        for role, font in (self.typography or {}).items():
            if role not in ("body", "heading", "mono"):
                raise ValueError(f"Unknown typography role {role!r}; expected "
                                 "body, heading, or mono.")
            if isinstance(font, Font):
                setattr(self, f"font_{role}", font.stack())
                if font.google:
                    self.fonts.append(GoogleFont(font.family, font.weights))
                elif font.src:
                    self.fonts.append(FontFace(font.family, font.src))
            else:
                setattr(self, f"font_{role}", font)

        color = self.color or {}
        unknown = set(color) - {"accent", "danger", "success", "surface"}
        if unknown:
            raise ValueError(f"Unknown color roles {sorted(unknown)!r}; "
                             "expected accent, danger, success, surface.")

        def resolve(role: str, base: str, **derived: str | None) -> ColorScale:
            value = color.get(role)
            if isinstance(value, ColorScale):
                return value
            if isinstance(value, str):
                return Color.scale(value)
            return Color.scale(base, **derived)

        self._accent = resolve("accent", self.accent,
                               strong=self.accent_strong, fg=self.accent_fg)
        self._danger = resolve("danger", self.danger,
                               strong=self.danger_strong)
        self._success = resolve("success", self.success)
        self.accent = self._accent.base
        self.accent_strong = self._accent.strong
        self.accent_fg = self._accent.fg
        self.danger = self._danger.base
        self.danger_strong = self._danger.strong
        self.success = self._success.base
        surface = color.get("surface")
        self._surface = surface if isinstance(surface, (str, type(None))) \
            else surface.base

    @classmethod
    def preset(cls, name: str) -> "Theme":
        """A built-in look by name. Presets are ordinary themes: use one
        directly, register several as brands, or pass one as a starting
        point and override fields.

        - indigo: the default look
        - mono: black and white, near-black accent flipping to white in
          dark mode
        - emerald, blue, rose, amber: accent-led variations
        """
        factories: dict[str, Any] = {
            "indigo": lambda: cls(),
            "mono": lambda: cls(color={
                "accent": Color.scale("#18181b", dark="#fafafa")}),
            "emerald": lambda: cls(color={"accent": "#059669"}),
            "blue": lambda: cls(color={"accent": "#2563eb"}),
            "rose": lambda: cls(color={"accent": "#e11d48"}),
            "amber": lambda: cls(color={"accent": "#f59e0b"}),
        }
        if name not in factories:
            raise ValueError(f"Unknown theme preset {name!r}; available: "
                             f"{', '.join(sorted(factories))}.")
        return factories[name]()

    @staticmethod
    def preset_names() -> tuple[str, ...]:
        return ("indigo", "mono", "emerald", "blue", "rose", "amber")

    def _neutrals(self) -> tuple[dict[str, str], dict[str, str]]:
        """The neutral ramps for both modes. With a surface color, hue
        and (capped) saturation tint the ramp; lightness steps stay fixed
        so contrast is preserved."""
        if self._surface is None:
            return {}, {}
        r, g, b = (ch / 255 for ch in _hex_rgb(self._surface))
        hue, _, sat = colorsys.rgb_to_hls(r, g, b)
        sat = min(sat, 0.20)

        def tone(lightness: float) -> str:
            rgb = colorsys.hls_to_rgb(hue, lightness, sat)
            return _rgb_hex(tuple(ch * 255 for ch in rgb))

        light = {
            "--v-bg": tone(0.972), "--v-surface-1": tone(0.998),
            "--v-surface-2": tone(0.952), "--v-surface-3": tone(0.915),
            "--v-border": tone(0.897), "--v-border-strong": tone(0.82),
            "--v-fg": tone(0.10), "--v-fg-muted": tone(0.40),
        }
        dark = {
            "--v-bg": tone(0.063), "--v-surface-1": tone(0.104),
            "--v-surface-2": tone(0.141), "--v-surface-3": tone(0.19),
            "--v-border": tone(0.196), "--v-border-strong": tone(0.26),
            "--v-fg": tone(0.93), "--v-fg-muted": tone(0.64),
        }
        return light, dark

    def _token_sets(self) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        light = {
            "--v-bg": "#f7f7f9",
            "--v-fg": "#16181d",
            "--v-fg-muted": "#5c6270",
            "--v-surface-1": "#ffffff",
            "--v-surface-2": "#f0f1f4",
            "--v-surface-3": "#e5e7ec",
            "--v-surface-glass": "rgba(255, 255, 255, 0.82)",
            "--v-border": "#e2e4e9",
            "--v-border-strong": "#cdd0d8",
            "--v-accent-soft": self._accent.soft,
            "--v-danger-soft": self._danger.soft,
            "--v-success-soft": self._success.soft,
            "--v-ring": self._accent.ring,
            "--v-shadow-sm": "0 1px 2px rgba(22, 24, 29, 0.05)",
            "--v-shadow-md": ("0 2px 4px rgba(22, 24, 29, 0.05), "
                              "0 8px 24px rgba(22, 24, 29, 0.07)"),
            "--v-shadow-lg": ("0 4px 8px rgba(22, 24, 29, 0.06), "
                              "0 20px 48px rgba(22, 24, 29, 0.14)"),
            "--v-code-bg": "#fafafa",
            "--v-code-fg": "#383a42",
            "--v-tok-kw": "#a626a4",
            "--v-tok-str": "#50a14f",
            "--v-tok-num": "#986801",
            "--v-tok-com": "#a0a1a7",
            "--v-tok-fn": "#4078f2",
            "--v-tok-dec": "#c18401",
            "--v-tok-blt": "#0184bc",
            "--v-tok-self": "#e45649",
            "--v-tok-op": "#0184bc",
        }
        dark = {
            "--v-bg": "#0e0f13",
            "--v-fg": "#ecedf1",
            "--v-fg-muted": "#9aa0ad",
            "--v-surface-1": "#17181e",
            "--v-surface-2": "#1f2129",
            "--v-surface-3": "#2a2d37",
            "--v-surface-glass": "rgba(23, 24, 30, 0.82)",
            "--v-border": "#2b2e38",
            "--v-border-strong": "#3a3e4a",
            "--v-accent-soft": self._accent.soft_dark,
            "--v-danger-soft": self._danger.soft_dark,
            "--v-success-soft": self._success.soft_dark,
            "--v-ring": self._accent.ring_dark,
            "--v-shadow-sm": "0 1px 2px rgba(0, 0, 0, 0.3)",
            "--v-shadow-md": ("0 2px 4px rgba(0, 0, 0, 0.3), "
                              "0 8px 24px rgba(0, 0, 0, 0.35)"),
            "--v-shadow-lg": ("0 4px 8px rgba(0, 0, 0, 0.35), "
                              "0 20px 48px rgba(0, 0, 0, 0.5)"),
            "--v-code-bg": "#111218",
            "--v-code-fg": "#abb2bf",
            "--v-tok-kw": "#c678dd",
            "--v-tok-str": "#98c379",
            "--v-tok-num": "#d19a66",
            "--v-tok-com": "#5c6370",
            "--v-tok-fn": "#61afef",
            "--v-tok-dec": "#e5c07b",
            "--v-tok-blt": "#56b6c2",
            "--v-tok-self": "#e06c75",
            "--v-tok-op": "#56b6c2",
        }
        # Semantic colors live in the mode blocks, not the shared block,
        # so a scale can flip between modes (monochrome accents are
        # near-black in light mode and white in dark mode).
        light |= {
            "--v-accent": self._accent.base,
            "--v-accent-strong": self._accent.strong,
            "--v-accent-fg": self._accent.fg,
            "--v-danger": self._danger.base,
            "--v-danger-strong": self._danger.strong,
            "--v-success": self._success.base,
        }
        dark |= {
            "--v-accent": self._accent.base_dark,
            "--v-accent-strong": self._accent.strong_dark,
            "--v-accent-fg": self._accent.fg_dark,
            "--v-danger": self._danger.base_dark,
            "--v-danger-strong": self._danger.strong_dark,
            "--v-success": self._success.base_dark,
        }
        shared = {
            "--v-space": f"{self.space_base}px",
            "--v-font-body": self.font_body,
            "--v-font-heading": self.font_heading,
            "--v-font-mono": self.font_mono,
            **{f"--v-radius-{k}": f"{v}px" for k, v in self.radius.items()},
        }
        neutrals_light, neutrals_dark = self._neutrals()
        return shared, light | neutrals_light, dark | neutrals_dark

    def css_tokens(self) -> str:
        def block(tokens: dict[str, str], indent: str = "  ") -> str:
            return "\n".join(f"{indent}{name}: {value};"
                             for name, value in tokens.items())

        def mode_blocks(theme: "Theme", selector: str) -> str:
            # Three modes: explicit light, explicit dark, and system. The
            # inline bootstrap sets data-theme from the stored preference
            # before first paint; without one the media query decides.
            shared, light, dark = theme._token_sets()
            return (
                f"{selector} {{\n" + block(shared | light) + "\n}\n\n"
                f'{selector}[data-theme="dark"] {{\n' + block(dark) + "\n}\n\n"
                "@media (prefers-color-scheme: dark) {\n"
                f'  {selector}:not([data-theme="light"]) {{\n'
                + block(dark, "    ") + "\n  }\n}\n"
            )

        parts = [mode_blocks(self, ":root")]
        for name, brand in self.brands.items():
            parts.append(mode_blocks(brand, f':root[data-brand="{name}"]'))
        for name, factor in self.densities.items():
            if factor == 1.0:
                continue
            unit = round(self.space_base * factor, 2)
            parts.append(f':root[data-density="{name}"] {{\n'
                         f"  --v-space: {unit:g}px;\n}}\n")
        # High contrast: an explicit preference or the system setting.
        # Muted text, borders, and focus rings snap to full-contrast
        # tokens; decorative shadows are dropped.
        contrast = ("--v-fg-muted: var(--v-fg); --v-border: var(--v-fg); "
                    "--v-border-strong: var(--v-fg); "
                    "--v-ring: var(--v-accent); --v-shadow-sm: none; "
                    "--v-shadow-md: none; --v-shadow-lg: none;")
        parts.append(f':root[data-contrast="high"] {{ {contrast} }}\n'
                     "@media (prefers-contrast: more) {\n"
                     f'  :root:not([data-contrast="normal"]) {{ {contrast} }}\n'
                     "}\n")
        return "\n".join(parts)


_FONT_FACE = """\
@font-face {
  font-family: 'InterVariable';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/_virel/fonts/InterVariable.woff2') format('woff2');
}
"""


def _all_fonts(theme: "Theme | None") -> list:
    if theme is None:
        return []
    fonts = list(theme.fonts)
    for brand in theme.brands.values():
        fonts.extend(brand.fonts)
    return fonts


def google_fonts(theme: "Theme | None") -> list[GoogleFont]:
    return [f for f in _all_fonts(theme) if isinstance(f, GoogleFont)]


def build_stylesheet(theme: Theme | None = None) -> str:
    theme = theme or Theme()
    faces = [_FONT_FACE.rstrip()]
    faces.extend(f.css() for f in _all_fonts(theme) if isinstance(f, FontFace))
    base = resources.files("virel.assets").joinpath("base.css").read_text("utf-8")
    return "\n".join(faces) + "\n\n" + theme.css_tokens() + "\n" + base


# --------------------------------------------------------------------------
# Runtime preference switching
# --------------------------------------------------------------------------

_PREFERENCE_KEYS = ("theme", "brand", "density", "contrast")


class SetPreferenceOp:
    """Handler op: switch a design preference at runtime and persist it.
    The value lands on the root element as data-<key> and in localStorage,
    where the bootstrap script restores it before first paint."""

    def __init__(self, key: str, value: str | None) -> None:
        self.key = key
        self.value = value

    def js(self) -> str:
        import json as _json
        return f'$.setPreference("{self.key}", {_json.dumps(self.value)});'

    def execute(self, env: dict[str, Any], ev: Any = None) -> None:
        env.setdefault("__preferences__", {})[self.key] = self.value

    def to_ir(self) -> dict[str, Any]:
        return {"op": "set_preference", "key": self.key, "value": self.value}


def set_preference(key: str, value: str | None) -> None:
    """Inside a handler: switch the theme, brand, density, or contrast
    preference at runtime (SPEC 10.1). ``None`` clears the preference back
    to the default (for theme, back to following the system setting).

        ui.Button("Compact", on_click=lambda: ui.set_preference("density", "compact"))
    """
    if key not in _PREFERENCE_KEYS:
        raise ValueError(f"Unknown preference {key!r}; expected one of "
                         f"{', '.join(_PREFERENCE_KEYS)}.")
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Preference values are strings or None, "
                         f"got {value!r}.")
    from .expr import current_recorder
    current_recorder().ops.append(SetPreferenceOp(key, value))


set_preference.__virel_op__ = "set_preference"  # type: ignore[attr-defined]


def runtime_js() -> str:
    return resources.files("virel.assets").joinpath("runtime.js").read_text("utf-8")


def compact(source: str) -> str:
    """Conservative production compaction: drop full-line comments and
    blank lines. Semantics-preserving by construction; gzip does the rest."""
    out = []
    in_block = False
    for line in source.splitlines():
        stripped = line.strip()
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("/*") and "*/" not in stripped:
            in_block = True
            continue
        if not stripped or stripped.startswith("//") \
                or (stripped.startswith("/*") and stripped.endswith("*/")) \
                or stripped.startswith("* ") or stripped == "*":
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def asset_version(theme: Theme | None = None) -> str:
    """Content hash for the shared assets, used as a cache-busting
    version on runtime.js and app.css URLs in production."""
    import hashlib
    payload = runtime_js() + build_stylesheet(theme)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
