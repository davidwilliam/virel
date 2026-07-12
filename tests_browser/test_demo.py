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
