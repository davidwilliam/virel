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


def test_cluster_buttons_update_state(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Layout").click()
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_text("Saved", exact=True).wait_for()
    page.get_by_role("button", name="Discard").click()
    page.get_by_text("Draft discarded").wait_for()


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


def test_container_query_restyles_by_container_width(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Styling").click()
    box = page.locator(".v-resizable > .v-box")
    box.wait_for()
    # Both tabs keep a Resizable in the DOM; target the styling one.
    holder = "document.querySelector('.v-resizable:has(> .v-box)')"
    background = (f"getComputedStyle({holder}.firstElementChild)"
                  ".backgroundColor")

    def settle(width, done):
        # Polled from Python: the page CSP (correctly) blocks the
        # injected-eval polling that wait_for_function relies on.
        page.evaluate(f"{holder}.style.width = '{width}'")
        for _ in range(40):
            value = page.evaluate(background)
            if done(value):
                return value
            page.wait_for_timeout(25)
        return page.evaluate(background)

    narrow = page.evaluate(background)
    wide = settle("30rem", lambda value: value != narrow)
    assert wide != narrow
    assert settle("15rem", lambda value: value == narrow) == narrow


def _motion_tab(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Motion").click()


def test_when_animates_enter_and_exit(page, server_url):
    _motion_tab(page, server_url)
    panel = page.get_by_text("This panel fades and rises in")
    panel.wait_for()
    toggle = page.get_by_role("button", name="Toggle panel")

    toggle.click()  # exit: stays visible while animating, then hides
    hidden = False
    for _ in range(40):
        if not panel.is_visible():
            hidden = True
            break
        page.wait_for_timeout(25)
    assert hidden

    toggle.click()  # enter
    panel.wait_for(state="visible")


def test_list_items_animate_in_and_flip_on_reorder(page, server_url):
    _motion_tab(page, server_url)
    page.get_by_text("Design review").wait_for()

    page.get_by_role("button", name="Add task").click()
    page.get_by_text("Task 4").wait_for()

    head = ("document.querySelectorAll('.v-each .v-card')[0].textContent")
    before = page.evaluate(head)
    page.get_by_role("button", name="Rotate").click()
    after = before
    for _ in range(40):
        after = page.evaluate(head)
        if after != before:
            break
        page.wait_for_timeout(25)
    assert after != before  # the last item rotated to the front


def test_swipeable_dismisses_from_the_keyboard(page, server_url):
    _motion_tab(page, server_url)
    note = page.get_by_text("Swipe me away.")
    note.wait_for()
    page.locator(".v-swipeable").focus()
    page.keyboard.press("Delete")
    page.get_by_text("Dismissed.").wait_for()
    page.get_by_role("button", name="Bring it back").click()
    page.get_by_text("Swipe me away.").wait_for()


def test_reduced_motion_still_completes_exit(page, server_url):
    page.emulate_media(reduced_motion="reduce")
    _motion_tab(page, server_url)
    panel = page.get_by_text("This panel fades and rises in")
    panel.wait_for()
    page.get_by_role("button", name="Toggle panel").click()
    hidden = False
    for _ in range(40):
        if not panel.is_visible():
            hidden = True
            break
        page.wait_for_timeout(25)
    assert hidden


def test_toast_notifications_appear_and_dismiss(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Feedback").click()
    page.get_by_role("button", name="Success").click()
    toast = page.get_by_text("Deployment complete.")
    toast.wait_for()
    assert page.evaluate(
        "document.querySelector('.v-toasts').getAttribute('aria-live')"
    ) == "polite"
    page.get_by_label("Dismiss notification").click()
    for _ in range(40):
        if not toast.is_visible():
            break
        page.wait_for_timeout(25)
    assert not toast.is_visible()


def test_popover_opens_and_escape_restores_focus(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Patterns").click()
    trigger = page.get_by_role("button", name="Popover")
    trigger.click()
    page.get_by_text("Anchored panel").wait_for()
    assert page.evaluate(
        "document.querySelector('.v-popover > button')"
        ".getAttribute('aria-expanded')") == "true"
    page.keyboard.press("Escape")
    for _ in range(40):
        if not page.get_by_text("Anchored panel").is_visible():
            break
        page.wait_for_timeout(25)
    assert not page.get_by_text("Anchored panel").is_visible()
    assert page.evaluate("document.activeElement.textContent") == "Popover"


def test_pagination_buttons_drive_state(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Patterns").click()
    page.get_by_text("Showing page 1 of 5").wait_for()
    page.get_by_role("button", name="3", exact=True).click()
    page.get_by_text("Showing page 3 of 5").wait_for()
    assert page.evaluate(
        "document.querySelectorAll("
        "'.v-pagination [aria-current=\"page\"]').length") == 1
    assert page.evaluate(
        "document.querySelector("
        "'.v-pagination [aria-current=\"page\"]').textContent") == "3"
    page.get_by_role("button", name="Next").click()
    page.get_by_text("Showing page 4 of 5").wait_for()


def test_tree_keyboard_navigation_and_selection(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Patterns").click()
    tree = page.locator('[role="tree"]')
    tree.wait_for()

    first = page.locator('[role="treeitem"]').first
    first.focus()
    page.keyboard.press("ArrowDown")   # into src's first child
    page.keyboard.press("Enter")
    page.get_by_text("Selected: app.py").wait_for()

    first.focus()
    page.keyboard.press("ArrowLeft")   # collapse src
    assert page.evaluate(
        "document.querySelector('[role=\"treeitem\"]')"
        ".getAttribute('aria-expanded')") == "false"
    page.keyboard.press("ArrowRight")  # expand again
    assert page.evaluate(
        "document.querySelector('[role=\"treeitem\"]')"
        ".getAttribute('aria-expanded')") == "true"


def test_command_palette_opens_filters_and_runs(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Patterns").click()
    page.keyboard.press("ControlOrMeta+k")
    palette_input = page.get_by_label("Search commands")
    palette_input.wait_for(state="visible")

    palette_input.fill("toast")
    assert page.evaluate(
        "document.querySelectorAll('.v-palette-item:not([hidden])').length"
    ) == 1
    page.keyboard.press("Enter")
    page.get_by_text("Ran from the palette.").wait_for()
    assert not page.evaluate("document.querySelector('.v-palette').open")

    # Filtering to nothing shows the empty state.
    page.keyboard.press("ControlOrMeta+k")
    palette_input.fill("zzzz")
    page.get_by_text("No matching commands.").wait_for()
    page.keyboard.press("Escape")


def test_list_reorders_from_the_keyboard(page, server_url):
    _motion_tab(page, server_url)
    page.get_by_text("Design review").wait_for()
    head = "document.querySelectorAll('.v-each .v-card')[0].textContent"
    assert "Design review" in page.evaluate(head)

    handle = page.get_by_label("Reorder item").first
    handle.focus()
    page.keyboard.press("Space")       # grab
    page.keyboard.press("ArrowDown")   # move below the second item
    page.keyboard.press("Space")       # drop -> state writes back
    for _ in range(40):
        if "Ship the docs" in page.evaluate(head):
            break
        page.wait_for_timeout(25)
    assert "Ship the docs" in page.evaluate(head)
    assert page.evaluate(
        "document.querySelector('.v-each + [role=\"status\"]').textContent"
    ) == "Dropped."

    # Escape cancels: grab, move, cancel restores the order.
    before = page.evaluate(head)
    handle = page.get_by_label("Reorder item").first
    handle.focus()
    page.keyboard.press("Space")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    assert page.evaluate(head) == before


def test_list_reorders_with_a_pointer_drag(page, server_url):
    _motion_tab(page, server_url)
    page.get_by_text("Design review").wait_for()
    head = "document.querySelectorAll('.v-each .v-card')[0].textContent"
    first_handle = page.get_by_label("Reorder item").first
    first_handle.scroll_into_view_if_needed()
    box = first_handle.bounding_box()
    second = page.evaluate(
        "document.querySelectorAll('.v-each .v-card')[1]"
        ".getBoundingClientRect().bottom")

    page.mouse.move(box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2, second + 10, steps=12)
    page.mouse.up()
    for _ in range(40):
        if "Design review" not in page.evaluate(head):
            break
        page.wait_for_timeout(25)
    assert "Design review" not in page.evaluate(head)


def test_datagrid_sorts_filters_selects_and_pages(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    grid = page.locator(".v-datagrid")
    grid.wait_for()
    first_model = ("document.querySelector('.v-datagrid tbody tr:not([hidden])')"
                   ".children[1].textContent")

    # Sort by score ascending, then descending.
    page.get_by_role("button", name="Score").click()
    assert page.evaluate(first_model) == "baseline"
    page.get_by_role("button", name="Score").click()
    assert page.evaluate(first_model) == "atlas-large"
    assert page.evaluate(
        "document.querySelector('th[data-key=\"score\"]')"
        ".getAttribute('aria-sort')") == "descending"

    # Filter narrows the row count.
    page.get_by_label("Filter rows").fill("extract")
    for _ in range(40):
        if "3 of 12 rows" in page.locator(".v-grid-count").text_content():
            break
        page.wait_for_timeout(25)
    assert "3 of 12 rows" in page.locator(".v-grid-count").text_content()
    page.get_by_label("Filter rows").fill("")

    # Select all visible rows; the count reaches Python state.
    page.get_by_label("Select all rows").check()
    page.get_by_text("Selected rows: 6").wait_for()

    # Page forward: the pager advances and new rows appear.
    page.get_by_role("button", name="Next").click()
    assert "Page 2 of 2" in page.locator(".v-grid-pages").text_content()


def test_listbox_keyboard_selection(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Forms").click()
    box = page.get_by_role("listbox")
    box.wait_for()
    box.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.get_by_text("Evaluating against summarize-v1").wait_for()
    assert page.evaluate(
        "document.querySelectorAll("
        "'.v-listbox [role=\"option\"][aria-selected=\"true\"]').length"
    ) == 1


def test_filter_chips_toggle_state(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    page.get_by_text("Facets on: 1").wait_for()
    page.get_by_role("button", name="failed").click()
    page.get_by_text("Facets on: 2").wait_for()
    page.get_by_role("button", name="passed", exact=True).click()
    page.get_by_text("Facets on: 1").wait_for()


def test_tour_walks_steps_and_closes(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    card = page.locator(".v-tour-card")
    page.get_by_role("button", name="Take the tour").click()
    card.get_by_text("The data grid").wait_for()
    assert page.locator(".v-tour-spotlight").is_visible()
    card.get_by_role("button", name="Next").click()
    card.get_by_text("Charts").wait_for()
    card.get_by_role("button", name="Back").click()
    card.get_by_text("The data grid").wait_for()
    page.keyboard.press("Escape")
    for _ in range(40):
        if page.evaluate("!document.querySelector('.v-tour-overlay')"):
            break
        page.wait_for_timeout(25)
    assert page.evaluate("!document.querySelector('.v-tour-overlay')")
    # State went back to False, so the tour restarts cleanly.


def test_charts_render_accessible_svg(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    assert page.evaluate(
        "document.querySelectorAll('.v-chart svg[role=\"img\"]').length") == 2
    label = page.evaluate(
        "document.querySelector('.v-chart svg').getAttribute('aria-label')")
    assert "Line chart" in label
