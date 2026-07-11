"""Design tokens compiled to CSS custom properties (SPEC 10.1).

Themes are typed Python objects. Tokens compile to CSS variables with
automatic light/dark support; components consume only semantic tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources


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
        "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    )
    font_heading: str = "inherit"
    font_mono: str = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"

    def css_tokens(self) -> str:
        light = {
            "--v-bg": "#f8f8fa",
            "--v-fg": "#17181c",
            "--v-fg-muted": "#5d616b",
            "--v-surface-1": "#ffffff",
            "--v-surface-2": "#f1f1f4",
            "--v-surface-3": "#e6e6ea",
            "--v-border": "#dcdce2",
            "--v-accent-soft": "#eef2ff",
            "--v-danger-soft": "#fef2f2",
            "--v-success-soft": "#f0fdf4",
        }
        dark = {
            "--v-bg": "#101114",
            "--v-fg": "#ececf0",
            "--v-fg-muted": "#9a9ea8",
            "--v-surface-1": "#191a1f",
            "--v-surface-2": "#222329",
            "--v-surface-3": "#2c2d34",
            "--v-border": "#33343c",
            "--v-accent-soft": "#26264a",
            "--v-danger-soft": "#3a1d1d",
            "--v-success-soft": "#16301e",
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


def build_stylesheet(theme: Theme | None = None) -> str:
    theme = theme or Theme()
    base = resources.files("virel.assets").joinpath("base.css").read_text("utf-8")
    return theme.css_tokens() + "\n" + base


def runtime_js() -> str:
    return resources.files("virel.assets").joinpath("runtime.js").read_text("utf-8")
