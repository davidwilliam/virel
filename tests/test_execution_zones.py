"""Build-time and shared execution zones (SPEC 8.4)."""

from virel import ui
from virel.compiler import compile_page
from virel.registry import active_registry


def test_build_functions_memoize_across_pages():
    runs = []

    @ui.build
    def load_docs():
        runs.append(1)
        return [{"title": "Intro"}, {"title": "Guide"}]

    @ui.page("/docs")
    def docs():
        pages = load_docs()
        return ui.Page(*[ui.Text(p["title"]) for p in pages])

    @ui.page("/")
    def home():
        return ui.Page(ui.Text(f"{len(load_docs())} documentation pages"))

    registry = active_registry()
    first = compile_page(registry.pages["/docs"])
    second = compile_page(registry.pages["/"])
    assert "Intro" in first.html
    assert "2 documentation pages" in second.html
    assert len(runs) == 1  # ran once for the whole build


def test_build_function_invalidation_reruns():
    runs = []

    @ui.build
    def content():
        runs.append(1)
        return "v1"

    assert content() == "v1"
    assert content() == "v1"
    assert len(runs) == 1
    content.invalidate()
    content()
    assert len(runs) == 2


def test_build_functions_memoize_per_arguments():
    runs = []

    @ui.build
    def section(name: str):
        runs.append(name)
        return f"content for {name}"

    assert section("intro") == "content for intro"
    assert section("intro") == "content for intro"
    assert section("guide") == "content for guide"
    assert runs == ["intro", "guide"]


def test_shared_functions_run_on_both_sides():
    @ui.shared
    def subtotal(price: float, quantity: float) -> float:
        return price * quantity

    # Server side: ordinary Python.
    assert subtotal(9.5, 3) == 28.5

    # Client side: compiled into the page module and usable reactively.
    @ui.page("/")
    def page():
        qty = ui.state(2)
        total = ui.derived(lambda: subtotal(9.5, qty))
        return ui.Page(ui.NumberField(qty, label="Qty"),
                       ui.Text(f"Total: {total}"))

    result = compile_page(active_registry().pages["/"])
    assert "function subtotal(price, quantity)" in result.js
    assert "Total: 19" in result.html
