"""Client navigation: mountable page modules and the router binding."""

from virel import ui
from virel.compiler import compile_page
from virel.registry import active_registry


def _counter_page():
    @ui.page("/")
    def counter():
        count = ui.state(0)
        return ui.Page(
            ui.Text(f"Count: {count}"),
            ui.Button("Add", on_click=lambda: count.update(lambda c: c + 1)),
        )
    return active_registry().pages["/"]


def test_page_modules_export_mount_and_self_mount():
    page = _counter_page()
    result = compile_page(page)
    assert "export function mount() {" in result.js
    assert result.js.rstrip().endswith("mount();")
    # Bindings live inside mount so navigation can re-run them.
    mount_body = result.js.split("export function mount() {")[1]
    assert "$.signal(0)" in mount_body
    assert "$.bindText(" in mount_body


def test_router_enabled_by_default():
    page = _counter_page()
    result = compile_page(page)
    assert "$.router();" in result.js


def test_router_can_be_disabled():
    active_registry().client_nav = False
    page = _counter_page()
    result = compile_page(page)
    assert "$.router();" not in result.js


def test_client_functions_stay_at_module_scope():
    @ui.client
    def double(n: int) -> int:
        return n * 2

    @ui.page("/")
    def page():
        n = ui.state(1)
        result = ui.derived(lambda: double(n))
        return ui.Page(ui.TextField(n, label="N"), ui.Text(f"= {result}"))

    result = compile_page(active_registry().pages["/"])
    # The function definition precedes mount(); only bindings re-run.
    definition = result.js.index("function double(n)")
    mount = result.js.index("export function mount()")
    assert definition < mount


def test_static_pages_remain_zero_javascript():
    @ui.page("/", render="static")
    def home():
        return ui.Page(ui.Heading("Plain"), ui.Text("No bindings here."))

    result = compile_page(active_registry().pages["/"])
    assert result.js is None
