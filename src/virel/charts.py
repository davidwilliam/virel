"""Charts (SPEC 11.1 advanced components).

Charts compile to inline SVG at render time: no charting library ships
to the browser, every point carries a title for hover and assistive
technology, and the whole figure gets a text summary. Line, area, bar,
and donut cover the everyday cases.

Series colors come from a fixed categorical palette, not the theme, so a
chart looks the same under any brand or color scheme — a chart's colors
encode its data, not the site's accent. The palette hues stay legible on
both light and dark surfaces.
"""

from __future__ import annotations

from typing import Any

from .expr import VirelCompileError
from .nodes import Element, RawHTML

# A fixed, theme-independent categorical palette (readable on light and
# dark backgrounds). Series and donut segments are colored by index.
_SERIES_COLORS = (
    "#6366f1",  # indigo
    "#10b981",  # emerald
    "#f59e0b",  # amber
    "#ef4444",  # red
    "#3b82f6",  # blue
    "#a855f7",  # purple
    "#ec4899",  # pink
    "#14b8a6",  # teal
)

_KINDS = ("line", "area", "bar", "donut")


class Series:
    """One chart series: a label and its numeric points (or a single
    value, for donut segments)."""

    def __init__(self, label: str, points: list | None = None,
                 value: Any = None) -> None:
        if (points is None) == (value is None):
            raise VirelCompileError(
                "Series takes exactly one of points=[...] or value=.")
        values = list(points) if points is not None else [value]
        cleaned = []
        for point in values:
            # Any numeric sequence works: lists, NumPy arrays, pandas
            # Series (SPEC 12.1). Booleans are rejected, not coerced.
            if isinstance(point, bool):
                raise VirelCompileError(
                    f"Series {label!r} points must be numbers, "
                    f"got {point!r}.")
            try:
                cleaned.append(float(point))
            except (TypeError, ValueError):
                raise VirelCompileError(
                    f"Series {label!r} points must be numbers, "
                    f"got {point!r}.") from None
        self.label = label
        self.points = cleaned
        self.value = cleaned[0] if points is None else None


def Chart(kind: str, series: list[Series], *, labels: list[str] | None = None,
          height: int = 220, legend: bool = True,
          description: str | None = None) -> Element:
    """A chart compiled to themed, accessible inline SVG:

        ui.Chart("line", [ui.Series("Pass rate", points=[71, 74, 82, 87])],
                 labels=["Apr", "May", "Jun", "Jul"])
    """
    if kind not in _KINDS:
        raise VirelCompileError(
            f"Chart kind must be one of {', '.join(_KINDS)}, got {kind!r}.")
    if not series:
        raise VirelCompileError("Chart needs at least one Series.")
    for entry in series:
        if not isinstance(entry, Series):
            raise VirelCompileError("Chart series take ui.Series(...).")
    if kind == "donut":
        svg = _donut(series, height)
    else:
        svg = _cartesian(kind, series, labels or [], height)
    summary = description or _summary(kind, series)
    figure_children = [RawHTML(
        svg.replace("<svg ", f'<svg role="img" aria-label="{_escape(summary)}" ', 1),
        reason="Compiler-generated SVG chart with escaped data values.")]
    if legend:
        entries = []
        for index, entry in enumerate(series):
            color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
            entries.append(
                f'<span class="v-chart-key"><span class="v-chart-dot" '
                f'style="background: {color}"></span>{_escape(entry.label)}'
                "</span>")
        figure_children.append(RawHTML(
            f'<div class="v-chart-legend">{"".join(entries)}</div>',
            reason="Compiler-generated legend with escaped labels."))
    return Element("figure", figure_children, attrs={"class": "v-chart"})


def _escape(text: str) -> str:
    import html
    return html.escape(str(text), quote=True)


def _summary(kind: str, series: list[Series]) -> str:
    parts = []
    for entry in series:
        if entry.value is not None:
            parts.append(f"{entry.label}: {entry.value:g}")
        else:
            parts.append(f"{entry.label}: {len(entry.points)} points, "
                         f"latest {entry.points[-1]:g}")
    return f"{kind.capitalize()} chart. " + "; ".join(parts) + "."


def _nice_ticks(low: float, high: float) -> list[float]:
    """Four to five round-numbered ticks spanning the data."""
    import math
    if high == low:
        high = low + 1
    span = high - low
    step = 10 ** math.floor(math.log10(span / 4))
    for multiplier in (1, 2, 2.5, 5, 10):
        if span / (step * multiplier) <= 5:
            step *= multiplier
            break
    start = math.floor(low / step) * step
    ticks = []
    tick = start
    while tick <= high + step / 2:
        ticks.append(round(tick, 10))
        tick += step
    return ticks


def _cartesian(kind: str, series: list[Series], labels: list[str],
               height: int) -> str:
    width = 640
    pad_left, pad_right, pad_top, pad_bottom = 44, 12, 10, 26
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    length = max(len(entry.points) for entry in series)
    every = [point for entry in series for point in entry.points]
    low = min(min(every), 0.0)
    ticks = _nice_ticks(low, max(every))
    y_low, y_high = ticks[0], ticks[-1]

    def x_at(index: int, count: int = length) -> float:
        if kind == "bar":
            return pad_left + plot_w * (index + 0.5) / count
        return pad_left + (plot_w * index / max(1, count - 1))

    def y_at(value: float) -> float:
        return pad_top + plot_h * (1 - (value - y_low) / (y_high - y_low))

    parts = [f'<svg viewBox="0 0 {width} {height}" class="v-chart-svg" '
             'preserveAspectRatio="xMidYMid meet">']
    for tick in ticks:
        y = y_at(tick)
        parts.append(f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - pad_right}" '
                     f'y2="{y:.1f}" class="v-chart-grid"/>')
        parts.append(f'<text x="{pad_left - 8}" y="{y + 4:.1f}" '
                     f'class="v-chart-tick" text-anchor="end">{tick:g}</text>')
    for index, label in enumerate(labels[:length]):
        parts.append(f'<text x="{x_at(index):.1f}" y="{height - 8}" '
                     f'class="v-chart-tick" text-anchor="middle">'
                     f"{_escape(label)}</text>")

    for series_index, entry in enumerate(series):
        color = _SERIES_COLORS[series_index % len(_SERIES_COLORS)]
        coords = [(x_at(i), y_at(point))
                  for i, point in enumerate(entry.points)]
        if kind == "bar":
            band = plot_w / length
            bar_w = band * 0.7 / len(series)
            for i, point in enumerate(entry.points):
                x = (x_at(i) - band * 0.35
                     + series_index * bar_w)
                y = y_at(max(point, 0))
                bar_h = abs(y_at(0) - y_at(point))
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                    f'height="{bar_h:.1f}" rx="3" fill="{color}" '
                    'class="v-chart-bar">'
                    f"<title>{_escape(entry.label)}: {point:g}</title></rect>")
            continue
        path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        if kind == "area":
            base = y_at(max(0.0, y_low))
            area = (path + f" L {coords[-1][0]:.1f} {base:.1f}"
                    f" L {coords[0][0]:.1f} {base:.1f} Z")
            parts.append(f'<path d="{area}" fill="{color}" opacity="0.15"/>')
        parts.append(f'<path d="{path}" fill="none" stroke="{color}" '
                     'stroke-width="2.5" stroke-linecap="round" '
                     'stroke-linejoin="round"/>')
        for i, (x, y) in enumerate(coords):
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}" '
                'class="v-chart-point">'
                f"<title>{_escape(entry.label)}: {entry.points[i]:g}"
                "</title></circle>")
    parts.append("</svg>")
    return "".join(parts)


def _donut(series: list[Series], height: int) -> str:
    import math
    total = sum(entry.value for entry in series)
    if total <= 0:
        raise VirelCompileError("Donut chart values must sum above zero.")
    size = height
    radius = size * 0.36
    center = size / 2
    circumference = 2 * math.pi * radius
    # A donut has a square viewBox, so cap its width at its height and
    # center it — otherwise width:100% would blow it up to the full
    # column width instead of respecting the requested size.
    parts = [f'<svg viewBox="0 0 {size} {size}" class="v-chart-svg" '
             f'style="max-width:{size}px;margin-inline:auto" '
             'preserveAspectRatio="xMidYMid meet">']
    offset = 0.0
    for index, entry in enumerate(series):
        fraction = entry.value / total
        color = _SERIES_COLORS[index % len(_SERIES_COLORS)]
        dash = fraction * circumference
        parts.append(
            f'<circle cx="{center}" cy="{center}" r="{radius:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{size * 0.13:.1f}" '
            f'stroke-dasharray="{dash:.2f} {circumference - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {center} {center})">'
            f"<title>{_escape(entry.label)}: {entry.value:g} "
            f"({fraction:.0%})</title></circle>")
        offset += dash
    parts.append(
        f'<text x="{center}" y="{center + 5}" text-anchor="middle" '
        f'class="v-chart-total">{total:g}</text>')
    parts.append("</svg>")
    return "".join(parts)
