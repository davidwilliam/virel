"""Theme modes: system, light, and dark are all supported by default."""

from virel import ui
from virel.compiler import compile_page
from virel.registry import active_registry
from virel.theme import Theme, build_stylesheet


def test_stylesheet_covers_all_three_modes():
    css = build_stylesheet(Theme())
    # Explicit modes via the data-theme attribute
    assert ':root[data-theme="dark"]' in css
    # System mode via the media query, unless explicitly overridden to light
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root:not([data-theme="light"])' in css


def test_pages_apply_stored_preference_before_first_paint():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("hello"))

    result = compile_page(active_registry().pages["/"])
    bootstrap = result.html.index("virel-theme")
    stylesheet = result.html.index("/_virel/app.css")
    assert bootstrap < stylesheet


def test_theme_toggle_component():
    @ui.page("/")
    def home():
        return ui.Page(ui.ThemeToggle())

    result = compile_page(active_registry().pages["/"])
    assert "$.themeToggle(" in result.js
    assert 'data-icon="system"' in result.html
    assert 'data-icon="light"' in result.html
    assert 'data-icon="dark"' in result.html
    assert 'aria-label="Color scheme: system"' in result.html


def test_stylesheet_bundles_the_font():
    css = build_stylesheet(Theme())
    assert "@font-face" in css
    assert "InterVariable.woff2" in css
    assert "'InterVariable'" in css


def test_font_served_with_immutable_caching():
    from virel.server import create_asgi_app
    from conftest import asgi_request

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/_virel/fonts/InterVariable.woff2")
    assert response.status == 200
    assert response.headers["content-type"] == "font/woff2"
    assert "immutable" in response.headers["cache-control"]
    assert len(response.body) > 100_000
    # Path traversal on the fonts route is refused.
    assert asgi_request(app, "GET",
                        "/_virel/fonts/../app.css").status == 404


def test_custom_font_face_from_project_files():
    from virel.theme import FontFace
    theme = Theme(
        fonts=[FontFace("Recursive", "/public/fonts/Recursive.woff2",
                        weight="300 900")],
        font_body="'Recursive', sans-serif",
    )
    css = build_stylesheet(theme)
    assert "font-family: 'Recursive';" in css
    assert "url('/public/fonts/Recursive.woff2')" in css
    assert "font-weight: 300 900;" in css


def test_google_font_adds_links_and_csp_origins():
    from virel.server import create_asgi_app
    from virel.theme import GoogleFont
    from conftest import asgi_request

    ui.use_theme(ui.Theme(fonts=[GoogleFont("Manrope", weights=(400, 700))],
                          font_body="'Manrope', sans-serif"))

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/")
    assert ("https://fonts.googleapis.com/css2?family=Manrope:wght@400;700"
            "&amp;display=swap") in response.text
    assert 'rel="preconnect" href="https://fonts.gstatic.com"' in response.text
    csp = response.headers["content-security-policy"]
    assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp
    assert "font-src 'self' https://fonts.gstatic.com" in csp


def test_default_csp_has_no_external_font_origins():
    from virel.server import create_asgi_app
    from conftest import asgi_request

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    response = asgi_request(create_asgi_app(dev=True), "GET", "/")
    csp = response.headers["content-security-policy"]
    assert "googleapis" not in csp
    assert "font-src 'self';" in csp


def test_overscroll_bounce_disabled_by_default():
    css = build_stylesheet(Theme())
    assert "overscroll-behavior: none" in css
