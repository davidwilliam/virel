"""Design tokens compiled to CSS custom properties (SPEC 10.1).

Themes are typed Python objects. Tokens compile to CSS variables with
automatic light/dark support; components consume only semantic tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources


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

    def css_tokens(self) -> str:
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
            "--v-accent-soft": "#eef1ff",
            "--v-danger-soft": "#fef2f2",
            "--v-success-soft": "#f0fdf4",
            "--v-ring": "rgba(79, 70, 229, 0.35)",
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
            "--v-accent-soft": "#24264a",
            "--v-danger-soft": "#3a1d1d",
            "--v-success-soft": "#16301e",
            "--v-ring": "rgba(129, 140, 248, 0.4)",
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
        shared = {
            "--v-accent": self.accent,
            "--v-accent-strong": self.accent_strong,
            "--v-accent-fg": self.accent_fg,
            "--v-danger": self.danger,
            "--v-danger-strong": self.danger_strong,
            "--v-success": self.success,
            "--v-space": f"{self.space_base}px",
            "--v-font-body": self.font_body,
            "--v-font-heading": self.font_heading,
            "--v-font-mono": self.font_mono,
            **{f"--v-radius-{k}": f"{v}px" for k, v in self.radius.items()},
        }

        def block(tokens: dict[str, str], indent: str = "  ") -> str:
            return "\n".join(f"{indent}{name}: {value};" for name, value in tokens.items())

        # Three modes by default: explicit light, explicit dark, and system.
        # The inline bootstrap sets data-theme from the stored preference
        # before first paint; with no preference the media query decides.
        return (
            ":root {\n" + block(shared | light) + "\n}\n\n"
            ':root[data-theme="dark"] {\n' + block(dark) + "\n}\n\n"
            "@media (prefers-color-scheme: dark) {\n"
            '  :root:not([data-theme="light"]) {\n' + block(dark, "    ") + "\n  }\n}\n"
        )


_FONT_FACE = """\
@font-face {
  font-family: 'InterVariable';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('/_virel/fonts/InterVariable.woff2') format('woff2');
}
"""


def google_fonts(theme: "Theme | None") -> list[GoogleFont]:
    if theme is None:
        return []
    return [f for f in theme.fonts if isinstance(f, GoogleFont)]


def build_stylesheet(theme: Theme | None = None) -> str:
    theme = theme or Theme()
    faces = [_FONT_FACE.rstrip()]
    faces.extend(f.css() for f in theme.fonts if isinstance(f, FontFace))
    base = resources.files("virel.assets").joinpath("base.css").read_text("utf-8")
    return "\n".join(faces) + "\n\n" + theme.css_tokens() + "\n" + base


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
