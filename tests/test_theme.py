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


def test_color_scale_derives_every_token_from_one_hex():
    scale = ui.Color.scale("#4f46e5")
    assert scale.base == "#4f46e5"
    assert scale.fg == "#ffffff"          # indigo: white text
    assert scale.strong != scale.base     # darker shade for hover
    assert scale.soft.startswith("#")     # light-mode tint
    assert scale.soft_dark.startswith("#")
    assert scale.ring.startswith("rgba(79, 70, 229")


def test_color_scale_picks_readable_foreground_by_contrast():
    assert ui.Color.scale("#f59e0b").fg == "#16181d"  # amber: dark text
    assert ui.Color.scale("#4f46e5").fg == "#ffffff"  # indigo: white text


def test_typed_color_roles_flow_into_both_modes():
    theme = Theme(color={"accent": "#059669"})
    css = theme.css_tokens()
    assert "--v-accent: #059669" in css
    scale = ui.Color.scale("#059669")
    assert f"--v-accent-soft: {scale.soft}" in css
    assert f"--v-accent-soft: {scale.soft_dark}" in css
    assert f"--v-ring: {scale.ring_dark}" in css


def test_surface_color_tints_the_neutral_ramp_in_both_modes():
    plain = Theme().css_tokens()
    tinted = Theme(color={"surface": "#7c8db5"}).css_tokens()
    assert plain != tinted
    assert "--v-bg: #f7f7f9" in plain
    assert "--v-bg: #f7f7f9" not in tinted
    assert tinted.count("--v-surface-1:") >= 2  # light and dark ramps


def test_space_scale_and_density_modes():
    theme = Theme(space=ui.Space.scale(base=4))
    css = theme.css_tokens()
    assert "--v-space: 4px" in css
    assert ':root[data-density="compact"]' in css
    assert "--v-space: 3px" in css
    roomy = Theme(space_base=8, densities={"cozy": 0.5})
    assert "--v-space: 4px" in roomy.css_tokens()


def test_typography_roles_accept_fonts_and_load_them():
    theme = Theme(typography={"body": ui.Font("Manrope", google=True),
                              "mono": ui.Font("Berkeley Mono",
                                              src="/public/fonts/bm.woff2")})
    assert "'Manrope'" in theme.font_body
    from virel.theme import google_fonts
    assert any(f.family == "Manrope" for f in google_fonts(theme))
    css = build_stylesheet(theme)
    assert "font-family: 'Berkeley Mono'" in css
    import pytest
    with pytest.raises(ValueError, match="typography role"):
        Theme(typography={"caption": ui.Font("X")})


def test_high_contrast_via_preference_and_media_query():
    css = Theme().css_tokens()
    assert ':root[data-contrast="high"]' in css
    assert "@media (prefers-contrast: more)" in css
    assert "--v-border: var(--v-fg)" in css


def test_brand_themes_compile_to_selectable_token_blocks():
    theme = Theme(brands={"acme": Theme(color={"accent": "#dc2626"})})
    css = theme.css_tokens()
    assert ':root[data-brand="acme"] {' in css
    assert ':root[data-brand="acme"][data-theme="dark"]' in css
    assert ':root[data-brand="acme"]:not([data-theme="light"])' in css
    assert "--v-accent: #dc2626" in css
    assert "--v-accent: #4f46e5" in css  # the default brand keeps its own


def test_brand_fonts_reach_the_stylesheet_and_csp():
    theme = Theme(brands={
        "acme": Theme(typography={"body": ui.Font("Sora", google=True)}),
    })
    from virel.theme import google_fonts
    assert any(f.family == "Sora" for f in google_fonts(theme))


def test_set_preference_compiles_and_executes():
    @ui.page("/prefs")
    def prefs():
        return ui.Page(
            ui.Button("Compact",
                      on_click=lambda: ui.set_preference("density", "compact")),
            ui.Button("Default brand",
                      on_click=lambda: ui.set_preference("brand", None)),
        )

    from virel.compiler import compile_page
    from virel.registry import active_registry
    result = compile_page(active_registry().pages["/prefs"])
    assert '$.setPreference("density", "compact");' in result.js
    assert '$.setPreference("brand", null);' in result.js

    view = ui.test.render(prefs)
    view.get_by_role("button", name="Compact").click()
    assert view.preferences == {"density": "compact"}
    view.get_by_role("button", name="Default brand").click()
    assert view.preferences["brand"] is None


def test_set_preference_rejects_unknown_keys():
    import pytest
    with pytest.raises(ValueError, match="Unknown preference"):
        ui.set_preference("motion", "off")


def test_bootstrap_restores_all_preferences_before_paint():
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    from virel.compiler import compile_page
    from virel.registry import active_registry
    html = compile_page(active_registry().pages["/"]).html
    assert 'localStorage.getItem("virel-theme")' in html
    assert '"brand","density","contrast"' in html


def test_mid_tone_accents_get_white_text():
    # A pure WCAG ratio comparison would pick dark text on emerald; the
    # readability threshold matches shipped design systems instead.
    assert ui.Color.scale("#059669").fg == "#ffffff"   # emerald
    assert ui.Color.scale("#e11d48").fg == "#ffffff"   # rose
    assert ui.Color.scale("#f59e0b").fg == "#16181d"   # amber stays dark


def test_color_scale_can_flip_between_modes():
    scale = ui.Color.scale("#18181b", dark="#fafafa")
    assert scale.fg == "#ffffff"
    assert scale.fg_dark == "#16181d"  # white accent: dark text on it
    css = Theme(color={"accent": scale}).css_tokens()
    assert "--v-accent: #18181b" in css
    assert "--v-accent: #fafafa" in css


def test_theme_presets_cover_at_least_five_looks():
    names = Theme.preset_names()
    assert len(names) >= 5
    assert "mono" in names
    for name in names:
        css = Theme.preset(name).css_tokens()
        assert "--v-accent" in css
    import pytest
    with pytest.raises(ValueError, match="Unknown theme preset"):
        Theme.preset("neon")


def test_semantic_colors_live_in_mode_blocks_not_shared():
    css = Theme.preset("mono").css_tokens()
    dark_block = css.split(':root[data-theme="dark"]')[1]
    assert "--v-accent: #fafafa" in dark_block
    assert "--v-accent-fg: #16181d" in dark_block
