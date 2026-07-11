"""Internationalization: catalogs, translation, plurals, and locale
negotiation."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import TraceContext, VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app

from conftest import asgi_request


def _catalogs():
    ui.messages("en", {
        "title": "Evaluation runs",
        "greeting": "Hello {name}",
        "runs": {"one": "{count} run", "other": "{count} runs"},
    })
    ui.messages("pt", {
        "title": "Execucoes de avaliacao",
        "greeting": "Ola {name}",
        "runs": {"one": "{count} execucao", "other": "{count} execucoes"},
    })


def _page():
    @ui.page("/")
    def home():
        total = ui.state(1)
        return ui.Page(
            ui.Heading(ui.t("title"), level=1),
            ui.Text(ui.t("greeting", name="Ada")),
            ui.Text(ui.t("runs", count=total)),
            ui.Button("More", on_click=lambda: total.update(lambda t: t + 1)),
        )
    return active_registry().pages["/"]


def test_translation_static_and_placeholder():
    _catalogs()
    with TraceContext():
        assert ui.t("title") == "Evaluation runs"
        assert ui.t("greeting", name="Ada") == "Hello Ada"


def test_missing_key_is_a_compile_error():
    _catalogs()
    with TraceContext():
        with pytest.raises(VirelCompileError, match="No message 'nope'"):
            ui.t("nope")
        with pytest.raises(VirelCompileError, match="placeholder"):
            ui.t("greeting")


def test_fallback_to_default_locale():
    _catalogs()
    ui.messages("pt", {})  # pt lacks a key defined only in en
    ui.messages("en", {"only_en": "English only"})
    with TraceContext() as ctx:
        ctx.locale = "pt"
        assert ui.t("only_en") == "English only"


def test_reactive_placeholder_compiles_to_binding():
    _catalogs()
    page = _page()
    result = compile_page(page)
    # Static plural form for count=1 in the initial HTML.
    assert "1 run" in result.html
    # The reactive plural compiles to a ternary over the count signal.
    assert "=== 1) ?" in result.js
    assert "${S.s1.get()} runs" in result.js


def test_per_locale_compilation():
    _catalogs()
    page = _page()
    english = compile_page(page)
    portuguese = compile_page(page, locale="pt")
    assert "Evaluation runs" in english.html
    assert "Execucoes de avaliacao" in portuguese.html
    assert '<html lang="pt">' in portuguese.html
    assert "1 execucao" in portuguese.html
    # Each locale gets its own page module.
    assert english.js_module == "index.en.js"
    assert portuguese.js_module == "index.pt.js"


def test_server_negotiates_accept_language():
    _catalogs()
    _page()
    app = create_asgi_app(dev=True)

    response = asgi_request(app, "GET", "/",
                            headers=[(b"accept-language",
                                      b"pt-BR,pt;q=0.9,en;q=0.8")])
    assert "Execucoes" in response.text
    assert response.headers["vary"] == "accept-language"

    response = asgi_request(app, "GET", "/")
    assert "Evaluation runs" in response.text

    response = asgi_request(app, "GET", "/", query="lang=pt")
    assert "Execucoes" in response.text


def test_locale_suffixed_page_modules_served():
    _catalogs()
    _page()
    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/_virel/page/index.pt.js")
    assert response.status == 200
    assert "execucao" in response.text
    response = asgi_request(app, "GET", "/_virel/page/index.en.js")
    assert "run" in response.text


def test_single_locale_apps_keep_plain_module_urls():
    @ui.page("/")
    def home():
        count = ui.state(0)
        return ui.Page(ui.Text(f"n: {count}"),
                       ui.Button("Add", on_click=lambda: count.set(1)))

    result = compile_page(active_registry().pages["/"])
    assert result.js_module == "index.js"
    assert "/_virel/page/index.js" in result.html


def test_plural_requires_both_forms():
    with pytest.raises(VirelCompileError, match="'one' and 'other'"):
        ui.messages("en", {"bad": {"one": "x"}})
