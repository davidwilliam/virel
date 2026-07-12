"""Visualization adapters (SPEC 12.3).

Virel does not invent a chart grammar. Established Python libraries
render server-side to SVG, and one typed container supplies the common
contract: sizing, theme integration, export, events, and accessibility.

Adapters (detected by module, imported lazily, never required):

- matplotlib figures and axes (and therefore seaborn) via ``savefig``
- Altair charts via vl-convert (pure Python, no Node.js)
- Plotly figures via kaleido, when installed

``ui.figure_style()`` returns matplotlib rcParams built from the active
theme, so library output follows the design tokens.
"""

from __future__ import annotations

import io
import re
from typing import Any

from .expr import VirelCompileError
from .nodes import Element, Node, RawHTML, TextNode


def Figure(figure: Any, *, label: str, description: str | None = None,
           caption: str | None = None, height: str | None = None,
           export: bool = False, on_click: Any = None,
           class_name: str | None = None) -> Element:
    """A visualization from an established library in the common
    container contract (SPEC 12.3):

        with plt.rc_context(ui.figure_style()):
            fig, ax = plt.subplots()
            ax.plot(months, scores)
        ui.Figure(fig, label="Pass rate by month", export=True)

    label= is the required accessible name; the SVG renders server-side
    (no plotting library ships to the browser), scales responsively, and
    export= adds an SVG download of exactly what is on screen."""
    if not label or not str(label).strip():
        raise VirelCompileError(
            "Figure requires label=, the accessible name of the chart.")
    svg = _finalize_svg(_to_svg(figure), label, description)
    from .elements import _classes, _css_length, _handler
    children: list[Node] = []
    toolbar: list[Node] = []
    if export:
        toolbar.append(Element(
            "button", [TextNode("Download SVG")],
            attrs={"type": "button",
                   "class": "v-btn v-btn-neutral v-btn-sm v-figure-export"}))
    if toolbar:
        children.append(Element("div", toolbar,
                                attrs={"class": "v-figure-toolbar"}))
    children.append(RawHTML(
        svg, reason="Server-rendered SVG from a visualization library, "
                    "sanitized and labeled by the Figure adapter."))
    if caption:
        children.append(Element("figcaption", [TextNode(caption)],
                                attrs={"class": "v-figure-caption"}))
    events = {}
    if on_click is not None:
        events["click"] = _handler(on_click)
    style = f"max-height: {_css_length(height)}" if height else None
    return Element("figure", children,
                   attrs={"class": _classes("v-figure", class_name),
                          "style": style},
                   events=events,
                   runtime_binding="figure" if export else None)


def figure_style() -> dict[str, Any]:
    """Matplotlib rcParams derived from the active theme, so library
    output follows the design tokens:

        with plt.rc_context(ui.figure_style()):
            fig, ax = plt.subplots()

    Server rendering bakes one palette; the light tokens are used, and
    the transparent background keeps figures readable on both modes."""
    from .registry import active_registry
    from .theme import Theme
    theme = active_registry().theme or Theme()
    fg = "#16181d"
    muted = "#5c6270"
    border = "#cdd0d8"
    # The theme's first family is usually a web font the plotting
    # backend does not have; only request it when it is installed.
    family = re.sub(r"['\"]", "", theme.font_body.split(",")[0]).strip()
    try:
        from matplotlib import font_manager
        available = {f.name for f in font_manager.fontManager.ttflist}
        if family not in available:
            family = "sans-serif"
    except ImportError:
        family = "sans-serif"
    return {
        "figure.facecolor": "none",
        "axes.facecolor": "none",
        "savefig.facecolor": "none",
        "savefig.transparent": True,
        "text.color": fg,
        "axes.labelcolor": muted,
        "axes.edgecolor": border,
        "xtick.color": muted,
        "ytick.color": muted,
        "grid.color": border,
        "axes.grid": True,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.family": family,
        "font.size": 11,
        "axes.prop_cycle": _cycler(theme),
        "figure.autolayout": True,
    }


def _cycler(theme: Any) -> Any:
    from cycler import cycler  # ships with matplotlib
    return cycler(color=[theme.accent, theme.success, theme.danger,
                         "#5c6270"])


def _to_svg(figure: Any) -> str:
    module = type(figure).__module__ or ""
    if module.startswith("matplotlib"):
        target = getattr(figure, "figure", None) or figure
        buffer = io.StringIO()
        target.savefig(buffer, format="svg", bbox_inches="tight")
        return buffer.getvalue()
    if module.startswith("altair"):
        try:
            import vl_convert
        except ImportError:
            raise VirelCompileError(
                "Altair figures need the vl-convert-python package to "
                "render server-side: pip install vl-convert-python."
            ) from None
        import json
        return vl_convert.vegalite_to_svg(json.dumps(figure.to_dict()))
    if module.startswith("plotly"):
        try:
            image = figure.to_image(format="svg")
        except Exception as error:
            raise VirelCompileError(
                "Plotly figures render server-side through kaleido "
                f"(pip install kaleido). Underlying error: {error}"
            ) from None
        return image.decode("utf-8")
    raise VirelCompileError(
        f"Figure cannot render {type(figure).__name__!r} from "
        f"{module or 'an unknown module'!r}; supported: matplotlib "
        "figures and axes (including seaborn), Altair charts, and "
        "Plotly figures.")


def _finalize_svg(svg: str, label: str, description: str | None) -> str:
    """The container contract applied to library output: strip the XML
    document wrapper, refuse active content, make the root responsive,
    and attach the accessible name."""
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
    lowered = svg.lower()
    for marker in ("<script", "javascript:", "<foreignobject"):
        if marker in lowered:
            raise VirelCompileError(
                "The rendered SVG contains active content "
                f"({marker!r}); refusing to embed it.")
    if re.search(r"\son\w+\s*=", lowered):
        raise VirelCompileError(
            "The rendered SVG contains inline event handlers; refusing "
            "to embed it.")
    match = re.search(r"<svg\b[^>]*>", svg)
    if not match:
        raise VirelCompileError("The library did not produce an SVG root.")
    import html as _html
    root = match.group(0)
    updated = re.sub(r'\s(width|height)="[^"]*"', "", root)
    updated = updated[:-1] + (
        f' role="img" aria-label="{_html.escape(str(label), quote=True)}"'
        ' class="v-figure-svg">')
    accessible = f"<title>{_html.escape(str(label))}</title>"
    if description:
        accessible += f"<desc>{_html.escape(str(description))}</desc>"
    return svg.replace(root, updated + accessible, 1)
