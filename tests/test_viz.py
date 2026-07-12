"""Visualization adapters (SPEC 12.3)."""

import pytest

from virel import ui
from virel.expr import VirelCompileError
from virel.nodes import template_html
from virel.viz import _finalize_svg


def _mpl():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def test_matplotlib_figures_render_in_the_container():
    plt = _mpl()
    with plt.rc_context(ui.figure_style()):
        fig, ax = plt.subplots(figsize=(4, 2.5))
        ax.plot([1, 2, 3], [70, 81, 93], label="atlas")
        ax.legend()
    figure = ui.Figure(fig, label="Pass rate by month",
                       description="Scores rise from 70 to 93.",
                       caption="Three months of runs.", export=True)
    plt.close(fig)
    html = template_html([figure], {})
    assert 'role="img"' in html
    assert 'aria-label="Pass rate by month"' in html
    assert "<title>Pass rate by month</title>" in html
    assert "<desc>Scores rise from 70 to 93.</desc>" in html
    assert "<figcaption" in html and "Three months of runs." in html
    assert "v-figure-export" in html
    # Responsive: the fixed size is stripped, the viewBox remains.
    root = html.split("<svg")[1].split(">")[0]
    assert "viewBox" in root and 'width="' not in root


def test_axes_and_seaborn_style_objects_resolve_to_their_figure():
    plt = _mpl()
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    figure = ui.Figure(ax, label="Bars")  # an Axes, not a Figure
    plt.close(fig)
    assert 'aria-label="Bars"' in template_html([figure], {})


def test_altair_charts_render_via_vl_convert():
    alt = pytest.importorskip("altair")
    pytest.importorskip("vl_convert")
    pd = pytest.importorskip("pandas")
    chart = alt.Chart(pd.DataFrame({"x": [1, 2, 3], "y": [3, 1, 2]})) \
        .mark_line().encode(x="x", y="y")
    figure = ui.Figure(chart, label="Altair line")
    html = template_html([figure], {})
    assert 'aria-label="Altair line"' in html


def test_figure_requires_a_label_and_known_library():
    plt = _mpl()
    fig, _ = plt.subplots()
    with pytest.raises(VirelCompileError, match="label="):
        ui.Figure(fig, label="  ")
    plt.close(fig)
    with pytest.raises(VirelCompileError, match="supported"):
        ui.Figure(object(), label="Mystery")


def test_container_refuses_active_svg_content():
    hostile = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)' \
              "</script></svg>"
    with pytest.raises(VirelCompileError, match="active content"):
        _finalize_svg(hostile, "x", None)
    with pytest.raises(VirelCompileError, match="event handlers"):
        _finalize_svg('<svg onload="alert(1)"></svg>', "x", None)
    with pytest.raises(VirelCompileError, match="active content"):
        _finalize_svg("<svg><foreignObject></foreignObject></svg>", "x",
                      None)


def test_figure_style_matches_theme_tokens():
    style = ui.figure_style()
    assert style["savefig.transparent"] is True
    assert style["text.color"] == "#16181d"
    assert "#4f46e5" in str(style["axes.prop_cycle"])


def test_figure_click_events_wire_like_any_handler():
    plt = _mpl()

    @ui.page("/fig-click")
    def fig_click():
        clicked = ui.state(0)
        fig, ax = plt.subplots()
        ax.plot([1, 2], [1, 2])
        node = ui.Figure(fig, label="Clickable",
                         on_click=lambda: clicked.update(lambda n: n + 1))
        plt.close(fig)
        return ui.Page(node, ui.Text(f"Clicks: {clicked}"))

    view = ui.test.render(fig_click)
    view.get_by_role("figure").click()
    assert "Clicks: 1" in view.query_text()
