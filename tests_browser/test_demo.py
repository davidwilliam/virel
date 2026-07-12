"""Checks that only a real browser can prove: custom element upgrades,
event delegation on live DOM, shadow-root rendering, and client-side
navigation remounting page modules (SPEC 16.2).

Run with:

    pip install -e ".[browser]"
    playwright install chromium
    ./scripts/ci browser
"""

VOLATILE = "12,18,9,21,7,19,11,23,8,20"


def _polyline_points(page):
    return page.evaluate(
        "document.querySelector('spark-line')?.shadowRoot"
        "?.querySelector('polyline')?.getAttribute('points')")


def test_counter_signals_drive_text_bindings(page, server_url):
    page.goto(f"{server_url}/counter")
    increment = page.get_by_role("button", name="Increment")
    increment.click()
    increment.click()
    page.get_by_text("Count: 2").wait_for()
    page.get_by_text("Doubled: 4").wait_for()


def test_spark_line_rerenders_when_bound_attribute_changes(page, server_url):
    page.goto(f"{server_url}/widgets")
    page.wait_for_selector("spark-line")
    before = _polyline_points(page)
    assert before, "spark-line never upgraded or rendered"

    page.get_by_role("button", name="Volatile").click()
    page.wait_for_function(
        f"document.querySelector('spark-line').getAttribute('values')"
        f" === '{VOLATILE}'")
    after = _polyline_points(page)
    assert after and after != before


def test_soft_navigation_mounts_widget_bindings(page, server_url):
    page.goto(f"{server_url}/")
    page.get_by_role("navigation").get_by_text("Widgets", exact=True).click()
    page.wait_for_url("**/widgets")

    page.wait_for_selector("spark-line")
    before = _polyline_points(page)
    assert before, "spark-line never upgraded after client navigation"

    page.get_by_role("button", name="Volatile").click()
    page.wait_for_function(
        f"document.querySelector('spark-line').getAttribute('values')"
        f" === '{VOLATILE}'")
    assert _polyline_points(page) != before


def test_custom_element_events_reach_python_state(page, server_url):
    page.goto(f"{server_url}/widgets")
    page.wait_for_selector("star-rating")

    # The stars live in the element's shadow root; Playwright selectors
    # pierce open shadow DOM, so this exercises the real event path:
    # shadow button click -> rating-changed -> delegated handler -> signal.
    page.get_by_label("4 stars").click()
    page.get_by_text("Python-side state sees: 4 / 5").wait_for()

    page.get_by_role("button", name="Set to 5").click()
    page.get_by_text("Python-side state sees: 5 / 5").wait_for()
    page.wait_for_function(
        "document.querySelector('star-rating').getAttribute('value') === '5'")


def test_design_preferences_switch_and_persist(page, server_url):
    page.goto(f"{server_url}/settings")
    accent = ("getComputedStyle(document.documentElement)"
              ".getPropertyValue('--v-accent').trim()")
    before = page.evaluate(accent)

    page.get_by_role("button", name="Emerald").click()
    page.get_by_role("button", name="Compact").click()
    assert page.evaluate("document.documentElement.dataset.brand") == "emerald"
    assert page.evaluate("document.documentElement.dataset.density") == "compact"
    switched = page.evaluate(accent)
    assert switched != before and switched == "#059669"

    # The bootstrap script restores preferences before first paint.
    page.reload()
    assert page.evaluate("document.documentElement.dataset.brand") == "emerald"
    assert page.evaluate(accent) == "#059669"

    # The mono brand flips its accent between modes: near-black in
    # light, white in dark.
    page.get_by_role("button", name="Mono").click()
    assert page.evaluate(accent) == "#18181b"
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    assert page.evaluate(accent) == "#fafafa"
    page.evaluate("delete document.documentElement.dataset.theme")

    page.get_by_role("button", name="Default", exact=True).click()
    assert page.evaluate("document.documentElement.dataset.brand") is None
    assert page.evaluate(accent) == before


def test_splitter_divider_moves_with_the_keyboard(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Layout").click()
    handle = page.locator(".v-splitter-handle")
    handle.wait_for()
    before = page.evaluate(
        "document.querySelector('.v-splitter').style.getPropertyValue('--v-split')")
    handle.focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    after = page.evaluate(
        "document.querySelector('.v-splitter').style.getPropertyValue('--v-split')")
    assert before == "35%" and after == "39%"
    assert page.evaluate(
        "document.querySelector('.v-splitter-handle').getAttribute('aria-valuenow')") == "39"
    page.keyboard.press("End")
    assert page.evaluate(
        "document.querySelector('.v-splitter-handle').getAttribute('aria-valuenow')") == "70"
