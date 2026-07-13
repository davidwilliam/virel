"""Checks that only a real browser can prove: custom element upgrades,
event delegation on live DOM, shadow-root rendering, and client-side
navigation remounting page modules (SPEC 16.2).

Run with:

    pip install -e ".[browser]"
    playwright install chromium
    ./scripts/ci browser
"""

import re

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


def test_datagrid_sorts_filters_and_selects(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    grid = page.locator(".v-datagrid").first
    grid.wait_for()

    # Sort by score: aria-sort tracks the cycle.
    grid.get_by_role("button", name="Score").click()
    grid.get_by_role("button", name="Score").click()
    assert page.evaluate(
        "document.querySelector('th[data-key=\"score\"]')"
        ".getAttribute('aria-sort')") == "descending"

    # Filter narrows the row count.
    grid.get_by_label("Filter rows").fill("extract")
    for _ in range(40):
        if "3 of 12 rows" in grid.locator(".v-grid-count").text_content():
            break
        page.wait_for_timeout(25)
    assert "3 of 12 rows" in grid.locator(".v-grid-count").text_content()
    grid.get_by_label("Filter rows").fill("")

    # Select all visible rows; the count reaches Python state.
    grid.get_by_label("Select all rows").check()
    page.get_by_text("Selected rows: 12").wait_for()


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


def test_grid_groups_collapse_and_aggregate(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    grid = page.locator(".v-datagrid").first
    grid.wait_for()
    toggle = grid.locator(".v-grid-group-toggle").first
    label = toggle.text_content()
    assert "(" in label  # group name with member count
    assert "Score mean:" in grid.locator(
        ".v-grid-group-summary").first.text_content()

    visible = ("document.querySelectorAll('.v-datagrid tbody "
               "tr[data-group-of]:not([hidden])').length")
    before = page.evaluate(visible)
    toggle.click()
    after = page.evaluate(visible)
    assert after < before
    toggle.click()
    assert page.evaluate(visible) == before


def test_grid_cell_edits_reach_state(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    grid = page.locator(".v-datagrid").first
    cell = grid.locator("td.v-grid-editable").first
    cell.scroll_into_view_if_needed()
    cell.dblclick()
    field = grid.locator(".v-grid-edit-input")
    field.fill("0.99")
    field.press("Enter")
    page.get_by_text("Last edit: 0.99").wait_for()
    assert cell.text_content() == "0.99"


def test_virtual_grid_windows_and_filters(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    virtual = page.locator(".v-datagrid").nth(1)
    virtual.scroll_into_view_if_needed()
    for _ in range(40):
        if "2000 rows" in virtual.locator(".v-grid-count").text_content():
            break
        page.wait_for_timeout(25)
    rendered = page.evaluate(
        "document.querySelectorAll('.v-datagrid')[1]"
        ".querySelectorAll('tbody tr:not(.v-grid-spacer)').length")
    assert rendered < 60  # 2000 rows of data, only a window in the DOM

    virtual.locator(".v-grid-filter").fill("run-1999")
    for _ in range(40):
        if "1 of 2000 rows" in virtual.locator(
                ".v-grid-count").text_content():
            break
        page.wait_for_timeout(25)
    assert "1 of 2000 rows" in virtual.locator(
        ".v-grid-count").text_content()


def test_grid_csv_export_downloads(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    with page.expect_download() as download_info:
        page.get_by_role("button", name="Export CSV").click()
    download = download_info.value
    assert download.suggested_filename == "grid.csv"
    path = download.path()
    content = open(path).read()
    assert '"model"' in content and '"atlas-large"' in content


def test_library_figure_or_its_fallback_renders(page, server_url):
    page.goto(f"{server_url}/components")
    page.get_by_role("tab", name="Data").click()
    page.get_by_text("Library figures").wait_for()
    # The browser CI environment installs only the browser extra, so the
    # card may show the graceful fallback instead of the SVG.
    has_figure = page.evaluate(
        "!!document.querySelector('.v-figure svg[role=\"img\"]')")
    has_hint = page.evaluate(
        "[...document.querySelectorAll('.v-alert')].some(a => "
        "a.textContent.includes('Install matplotlib'))")
    assert has_figure or has_hint


def test_ai_prompt_streams_into_the_response(page, server_url):
    page.goto(f"{server_url}/ai")
    page.get_by_label("Prompt").fill("What is the refund policy?")
    page.keyboard.press("ControlOrMeta+Enter")
    # The cursor pulses while streaming, then the done signal hides it.
    page.locator(".v-ai-cursor").wait_for(state="visible")
    page.get_by_text("prorated to the day").wait_for(timeout=15000)
    for _ in range(80):
        if not page.locator(".v-ai-cursor").is_visible():
            break
        page.wait_for_timeout(50)
    assert not page.locator(".v-ai-cursor").is_visible()


def test_ai_feedback_and_approval(page, server_url):
    page.goto(f"{server_url}/ai")
    page.get_by_role("button", name="Thumbs up").click()
    assert page.evaluate(
        "document.querySelector('[aria-label=\"Thumbs up\"]')"
        ".getAttribute('aria-pressed')") == "true"
    page.get_by_role("button", name="Approve").click()
    page.get_by_text("Decision: approved").wait_for()


def test_ai_recorder_captures_fake_audio(page, server_url):
    page.goto(f"{server_url}/ai")
    record = page.get_by_role("button", name="Record")
    record.scroll_into_view_if_needed()
    record.click()
    page.get_by_text("Recording…").wait_for()
    page.wait_for_timeout(400)
    page.get_by_role("button", name="Stop").click()
    page.get_by_text("Recorded").wait_for()
    files = page.evaluate(
        "document.querySelector('.v-ai-recorder input[type=file]')"
        ".files.length")
    assert files == 1


def test_ai_job_progress_updates(page, server_url):
    page.goto(f"{server_url}/ai")
    badge = page.locator(".v-ai-job .v-badge:visible").first
    assert "running" in badge.text_content()
    page.get_by_role("button", name="Finish").click()
    for _ in range(40):
        visible = page.locator(".v-ai-job .v-badge:visible").first
        if "done" in visible.text_content():
            break
        page.wait_for_timeout(25)
    assert "done" in page.locator(
        ".v-ai-job .v-badge:visible").first.text_content()


def test_notebook_preview_bundle_is_interactive(page, server_url):
    # The preview document is fully self-contained: loaded with no
    # server at all, its compiled handlers still run.
    import subprocess
    import sys
    document = subprocess.run(
        [sys.executable, "-c", (
            "from virel import ui\n"
            "def playground():\n"
            "    count = ui.state(0)\n"
            "    return ui.Stack(\n"
            "        ui.Text(f'Count: {count}'),\n"
            "        ui.Button('Increment',\n"
            "                  on_click=lambda: count.update(\n"
            "                      lambda c: c + 1)),\n"
            "    )\n"
            "print(ui.preview(playground).document)\n")],
        capture_output=True, text=True, check=True).stdout
    page.set_content(document)
    page.get_by_text("Count: 0").wait_for()
    page.get_by_role("button", name="Increment").click()
    page.get_by_role("button", name="Increment").click()
    page.get_by_text("Count: 2").wait_for()


def _embed_source(kind):
    import subprocess
    import sys
    return subprocess.run(
        [sys.executable, "-c", (
            "from virel import ui\n"
            "def counter():\n"
            "    count = ui.state(0)\n"
            "    return ui.Card(\n"
            "        ui.Text(f'Count: {count}'),\n"
            "        ui.Button('Add',\n"
            "                  on_click=lambda: count.update(\n"
            "                      lambda c: c + 1)),\n"
            "        gap=3,\n"
            "    )\n"
            f"print(ui.{kind})\n")],
        capture_output=True, text=True, check=True).stdout


def test_custom_element_instances_have_independent_state(page, server_url):
    source = _embed_source(
        "as_custom_element(counter, tag='virel-counter')")
    page.set_content(
        "<html><body>"
        "<h1>A host page that is not Virel</h1>"
        "<virel-counter id='one'></virel-counter>"
        "<virel-counter id='two'></virel-counter>"
        f"<script type='module'>{source}</script>"
        "</body></html>")
    first = page.locator("#one")
    second = page.locator("#two")
    first.get_by_role("button", name="Add").wait_for()

    first.get_by_role("button", name="Add").click()
    first.get_by_role("button", name="Add").click()
    second.get_by_role("button", name="Add").click()
    assert "Count: 2" in first.locator(".v-card").text_content()
    assert "Count: 1" in second.locator(".v-card").text_content()


def test_fragment_script_mounts_inside_a_host_page(page, server_url):
    import subprocess
    import sys
    payload = subprocess.run(
        [sys.executable, "-c", (
            "import json\n"
            "from virel import ui\n"
            "def counter():\n"
            "    count = ui.state(0)\n"
            "    return ui.Card(\n"
            "        ui.Text(f'Count: {count}'),\n"
            "        ui.Button('Add',\n"
            "                  on_click=lambda: count.update(\n"
            "                      lambda c: c + 1)),\n"
            "    )\n"
            "f = ui.render_fragment(counter)\n"
            "print(json.dumps({'html': f.html, 'script': f.script}))\n")],
        capture_output=True, text=True, check=True).stdout
    import json
    fragment = json.loads(payload)
    page.set_content(
        "<html><body><main>Existing content</main>"
        + fragment["html"]
        + f"<script type='module'>{fragment['script']}</script>"
        + "</body></html>")
    page.get_by_role("button", name="Add").click()
    page.get_by_text("Count: 1").wait_for()


def test_inspector_shows_the_enriched_panel(page, server_url):
    page.goto(f"{server_url}/counter")
    page.get_by_role("button", name="Increment").click()
    # Open the inspector (Alt+V).
    page.keyboard.press("Alt+v")
    page.get_by_role("button", name="Close inspector").wait_for()
    panel_text = page.evaluate(
        "document.querySelector('[aria-label=\"Close inspector\"]')"
        ".closest('div').parentElement.textContent")
    for section in ("component tree", "live state", "derived",
                    "server actions", "accessibility", "dom mapping",
                    "style tokens"):
        assert section in panel_text, f"inspector missing {section!r}"
    assert "--v-accent" in panel_text          # style tokens
    assert "data-v=" in panel_text             # DOM mapping
    assert "no accessibility warnings" in panel_text


def test_dev_toolbar_controls_present(page, server_url):
    page.goto(f"{server_url}/counter")
    # The dev toolbar renders viewport, theme, locale, and trace buttons.
    page.get_by_title("Cycle responsive viewport width").wait_for()
    theme = page.get_by_title("Cycle system / light / dark")
    theme.click()
    assert page.evaluate("document.documentElement.dataset.theme") == "light"

    view = page.get_by_title("Cycle responsive viewport width")
    view.click()
    assert page.evaluate("document.documentElement.style.maxWidth") == "390px"


def test_dev_action_trace_records_calls(page, server_url):
    page.goto(f"{server_url}/invite")
    page.get_by_title("Toggle the server-action trace").click()
    page.get_by_text("no server-action calls yet").wait_for()
    # Trigger a server action.
    page.get_by_label("Email").fill("someone@example.com")
    page.get_by_role("button", name="Send invitation").click()
    for _ in range(40):
        text = page.evaluate(
            "document.body.textContent")
        if "invite_member" in text:
            break
        page.wait_for_timeout(50)
    assert "invite_member" in page.evaluate("document.body.textContent")


def _run_search_action(page):
    # Typing on /search triggers the record_search server action through a
    # reactive effect; it returns 200 and has no side effects, so it is
    # safe to call repeatedly.
    page.get_by_label("Query").fill("hello world")
    for _ in range(60):
        last = page.evaluate(
            "window.__virelTelemetry?.last?.name === 'record_search' "
            "? window.__virelTelemetry.last : null")
        if last:
            return last
        page.wait_for_timeout(50)
    raise AssertionError("no action telemetry recorded")


def test_action_records_full_timing_breakdown(page, server_url):
    # SPEC 19 dev tools: action duration, server execution, serialization,
    # network, payload size, and a correlation id.
    page.goto(f"{server_url}/search")
    last = _run_search_action(page)
    assert last["name"] == "record_search"
    for key in ("duration", "server", "serialize", "network", "bytes"):
        assert isinstance(last[key], (int, float)), key
    assert last["network"] >= 0 and last["server"] >= 0
    # x-request-id correlates the browser event with the server trace.
    assert last["requestId"] and len(last["requestId"]) == 32


def test_action_sends_traceparent_header(page, server_url):
    page.goto(f"{server_url}/search")
    seen = {}
    page.on("request", lambda r: seen.update(
        {"tp": r.headers.get("traceparent")})
        if "/_virel/action/" in r.url else None)
    _run_search_action(page)
    assert seen.get("tp"), "action request carried no traceparent"
    assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-01", seen["tp"])


def test_dev_panel_shows_timing_breakdown(page, server_url):
    page.goto(f"{server_url}/search")
    page.get_by_title("Toggle the server-action trace").click()
    _run_search_action(page)
    # The panel polls and renders the labelled breakdown after an action.
    page.wait_for_timeout(600)
    body = page.evaluate("document.body.textContent")
    assert "server" in body and "network" in body and "serialize" in body


def test_vitals_and_hydration_collected(page, server_url):
    page.goto(f"{server_url}/counter")
    for _ in range(40):
        hydration = page.evaluate(
            "window.__virelTelemetry?.vitals?.hydration ?? null")
        if hydration is not None:
            break
        page.wait_for_timeout(50)
    assert isinstance(hydration, (int, float)), "hydration time not recorded"


def test_client_error_is_captured(page, server_url):
    # A synthetic error event exercises the runtime's global error handler
    # without an actual uncaught exception (which the fixture would flag).
    page.goto(f"{server_url}/counter")
    page.wait_for_timeout(100)
    page.evaluate(
        "window.dispatchEvent(new ErrorEvent('error', "
        "{message: 'synthetic-telemetry-error'}))")
    for _ in range(20):
        errors = page.evaluate("window.__virelTelemetry?.errors || []")
        if errors:
            break
        page.wait_for_timeout(50)
    assert any("synthetic-telemetry-error" in e["message"] for e in errors)


def test_state_preserving_hot_reload(page, server_url):
    page.goto(f"{server_url}/counter")
    inc = page.get_by_role("button", name="Increment")
    inc.click()
    inc.click()
    inc.click()
    page.get_by_text("Count: 3").wait_for()

    # Simulate the HMR path: snapshot, then reload as the poll would.
    page.evaluate("window.__virelHmr.snapshot()")
    page.reload()

    # The HMR restore path runs and announces itself; the count holds.
    page.get_by_text("state preserved").wait_for()
    page.get_by_text("Count: 3").wait_for()


def test_hot_reload_falls_back_when_shape_changes(page, server_url):
    page.goto(f"{server_url}/counter")
    page.get_by_text("Count: 0").wait_for()
    # A snapshot whose state names do not match the page is discarded:
    # the restore path does not run, so no "state preserved" badge and
    # the page keeps its fresh state.
    page.evaluate(
        "sessionStorage.setItem('virel:hmr:/counter', "
        "JSON.stringify({sX: 99, sY: 'gone'}))")
    page.reload()
    page.wait_for_timeout(400)
    assert not page.get_by_text("state preserved").is_visible()


def test_browserpage_wrapper_matches_the_spec_api(page, server_url):
    from virel import ui
    # The SPEC 16.2 example, verbatim in shape, over the invite page.
    bp = ui.browser_page(page, base_url=server_url)
    bp.goto("/invite")
    bp.field("Email").fill("person@example.com")
    bp.select("Role").choose("editor")
    bp.button("Send invitation").click()
    bp.expect_text("Invitation sent")
    # The raw Playwright page stays reachable.
    assert bp.raw is page


def test_browserpage_role_and_link_helpers(page, server_url):
    from virel import ui
    bp = ui.browser_page(page, base_url=server_url)
    bp.goto("/counter")
    bp.button("Increment").click()
    bp.button("Increment").click()
    bp.expect_text("Count: 2")
    bp.expect_no_text("Count: 5")


def test_worker_and_canvas_run_in_the_browser(page, server_url):
    # A standalone page compiled inline: a worker computes off-thread and
    # a canvas paints, proving both extension points in a real browser.
    import subprocess
    import sys
    document = subprocess.run(
        [sys.executable, "-c", (
            "from virel import ui\n"
            "@ui.worker\n"
            "def weighted(v):\n"
            "    return v[0] * 3 + v[1] * 5\n"
            "def pg():\n"
            "    data = ui.state([2, 4])\n"
            "    out = ui.state(0)\n"
            "    return ui.Stack(\n"
            "        ui.Button('Compute',\n"
            "                  on_click=lambda: weighted.run(data, into=out)),\n"
            "        ui.Text(f'Result: {out}'),\n"
            "        ui.Canvas(draw='ctx.fillStyle=\"#4f46e5\";"
            "ctx.fillRect(0,0,frame.width,frame.height);', label='Fill'),\n"
            "    )\n"
            "print(ui.preview(pg).document)\n")],
        capture_output=True, text=True, check=True).stdout
    page.set_content(document)
    page.get_by_role("button", name="Compute").click()
    page.get_by_text("Result: 26").wait_for()   # 2*3 + 4*5, off-thread
    # The canvas painted: its backing store has non-zero dimensions.
    painted = page.evaluate(
        "(() => { const c = document.querySelector('canvas'); "
        "return c.width > 0 && c.height > 0; })()")
    assert painted


def test_worker_runs_rich_computation_off_thread(page, server_url):
    import subprocess
    import sys
    document = subprocess.run(
        [sys.executable, "-c", (
            "from virel import ui\n"
            "@ui.worker\n"
            "def even_sum(nums):\n"
            "    return sum([n for n in nums if n % 2 == 0])\n"
            "def pg():\n"
            "    data = ui.state([1, 2, 3, 4, 5, 6])\n"
            "    out = ui.state(0)\n"
            "    return ui.Stack(\n"
            "        ui.Button('Compute',\n"
            "                  on_click=lambda: even_sum.run(data, into=out)),\n"
            "        ui.Text(f'Even sum: {out}'),\n"
            "    )\n"
            "print(ui.preview(pg).document)\n")],
        capture_output=True, text=True, check=True).stdout
    page.set_content(document)
    page.get_by_role("button", name="Compute").click()
    # sum of the evens in [1..6] = 2 + 4 + 6 = 12, computed off-thread
    # with the extended subset (sum over a filtered comprehension).
    page.get_by_text("Even sum: 12").wait_for()


def test_virtual_list_windows_thousands_of_rows(page, server_url):
    import subprocess
    import sys
    document = subprocess.run(
        [sys.executable, "-c", (
            "from virel import ui\n"
            "def pg():\n"
            "    items = ui.state([{'id': i, 'name': f'Row {i}'}\n"
            "                      for i in range(5000)])\n"
            "    return ui.Each(items,\n"
            "                   render=lambda x: ui.Text(x['name']),\n"
            "                   key=lambda x: x['id'], virtual=True,\n"
            "                   item_height=32, height='16rem')\n"
            "print(ui.preview(pg).document)\n")],
        capture_output=True, text=True, check=True).stdout
    page.set_content(document)
    page.get_by_text("Row 0").wait_for()
    # Only a window of the 5000 rows exists in the DOM.
    rendered = page.evaluate(
        "document.querySelectorAll('.v-vrow').length")
    assert 0 < rendered < 60
    # Scrolling reveals later rows without inflating the DOM.
    page.evaluate("document.querySelector('.v-vlist').scrollTop = 3200")
    page.get_by_text("Row 100").wait_for()
    assert page.evaluate(
        "document.querySelectorAll('.v-vrow').length") < 60



def test_worker_receives_transferred_typed_array(page, server_url):
    # A typed array transfers to the worker zero-copy: after posting, the
    # source buffer is detached (byteLength 0), proving move not clone.
    page.goto(f"{server_url}/counter")
    detached = page.evaluate("""async () => {
        const mod = await import('/_virel/runtime.js');
        mod.registerWorkers({ sumArray:
            "function sumArray(a){let s=0;for(let i=0;i<a.length;i++)s+=a[i];return s;}" });
        const arr = new Float64Array([1, 2, 3, 4]);
        const buf = arr.buffer;
        const sig = mod.signal(0);
        mod.runWorker("sumArray", arr, sig);
        // Transferred buffers detach on the sending side immediately.
        return buf.byteLength === 0;
    }""")
    assert detached is True
