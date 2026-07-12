"""Browser tests in Python (SPEC 16.2).

``ui.BrowserPage`` wraps a Playwright page in a Virel-flavored,
role-first API so browser tests read like the component tests:
``page.button("Save").click()``, ``page.field("Email").fill(...)``,
``page.select("Role").choose("editor")``, ``page.expect_text(...)``.

Playwright is an optional dependency (the ``browser`` extra); importing
this module without it raises a clear message. The wrapper is
intentionally thin, so the full Playwright API stays reachable through
``page.raw``.
"""

from __future__ import annotations

from typing import Any


class Locator:
    """A thin wrapper over a Playwright locator with Virel verbs."""

    def __init__(self, locator: Any) -> None:
        self._locator = locator

    @property
    def raw(self) -> Any:
        return self._locator

    def click(self) -> None:
        self._locator.click()

    def fill(self, value: str) -> None:
        self._locator.fill(value)

    def choose(self, value: str) -> None:
        """Select an option in a Virel Select (an enhanced control over a
        native select) or a native select."""
        native = self._locator
        # Virel's Select keeps a native <select> as the source of truth.
        try:
            native.select_option(label=value)
            return
        except Exception:
            pass
        native.select_option(value)

    def check(self) -> None:
        self._locator.check()

    def press(self, key: str) -> None:
        self._locator.press(key)

    def text(self) -> str:
        return self._locator.text_content() or ""

    def is_visible(self) -> bool:
        return self._locator.is_visible()

    def wait_for(self, **kwargs: Any) -> None:
        self._locator.wait_for(**kwargs)


class BrowserPage:
    """A Virel-flavored page for browser tests (SPEC 16.2)."""

    def __init__(self, page: Any, base_url: str = "") -> None:
        self._page = page
        self._base_url = base_url.rstrip("/")

    @property
    def raw(self) -> Any:
        """The underlying Playwright page, for anything not wrapped."""
        return self._page

    # -- navigation ----------------------------------------------------------

    def goto(self, path: str) -> None:
        url = path if path.startswith("http") else self._base_url + path
        self._page.goto(url)

    # -- role-first locators -------------------------------------------------

    def button(self, name: str) -> Locator:
        return Locator(self._page.get_by_role("button", name=name,
                                              exact=True))

    def link(self, name: str) -> Locator:
        return Locator(self._page.get_by_role("link", name=name))

    def field(self, label: str) -> Locator:
        return Locator(self._page.get_by_label(label))

    def select(self, label: str) -> Locator:
        # Virel's Select renders an enhanced combobox over a native
        # <select> that stays the source of truth; both carry the label,
        # so narrow to the native select element.
        labeled = self._page.get_by_label(label)
        native = labeled.and_(self._page.locator("select"))
        return Locator(native if native.count() else labeled)

    def text(self, value: str) -> Locator:
        return Locator(self._page.get_by_text(value))

    def role(self, role: str, *, name: str | None = None) -> Locator:
        return Locator(self._page.get_by_role(role, name=name))

    # -- assertions ----------------------------------------------------------

    def expect_text(self, text: str, *, timeout: int = 5000) -> None:
        self._page.get_by_text(text).first.wait_for(
            state="visible", timeout=timeout)

    def expect_no_text(self, text: str) -> None:
        assert not self._page.get_by_text(text).count(), \
            f"unexpected text on the page: {text!r}"

    def press(self, key: str) -> None:
        self._page.keyboard.press(key)


def browser_page(page: Any, base_url: str = "") -> BrowserPage:
    """Wrap a Playwright page. Requires the ``browser`` extra."""
    try:
        import playwright  # noqa: F401
    except ImportError as error:  # pragma: no cover - dependency guard
        raise ImportError(
            "ui.browser_page needs Playwright: pip install virel[browser] "
            "and run `playwright install chromium`.") from error
    return BrowserPage(page, base_url)
