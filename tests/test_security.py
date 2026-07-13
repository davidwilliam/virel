"""The security guarantees in SECURITY.md, verified."""

import json

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.security import content_security_policy, safe_url, script_hash
from virel.server import create_asgi_app

from conftest import asgi_request


def _page(fn, path="/"):
    ui.page(path)(fn)
    return active_registry().pages[path]


def _simple_app(**kwargs):
    @ui.page("/")
    def home():
        return ui.Page(ui.Text("hello"))

    @ui.server
    def echo(value: str) -> str:
        return value

    return create_asgi_app(dev=True, **kwargs)


# -- content security policy ---------------------------------------------------

def test_html_responses_carry_csp_with_valid_script_hashes():
    app = _simple_app()
    response = asgi_request(app, "GET", "/")
    csp = response.headers["content-security-policy"]
    assert "script-src 'self' 'sha256-" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # The hash in the header must match the inline script in the document.
    inline = response.text.split("<script>")[1].split("</script>")[0]
    assert script_hash(inline) in csp


def test_csp_allows_same_origin_blob_workers_only():
    # @ui.worker runs Web Workers from same-origin Blob URLs; the CSP
    # must permit exactly that (worker-src 'self' blob:) and nothing
    # broader, so a worker cannot be created from a foreign origin.
    csp = content_security_policy([])
    assert "worker-src 'self' blob:;" in csp
    assert "worker-src *" not in csp
    assert "https://" not in csp.split("worker-src")[1].split(";")[0]


def test_csp_covers_inline_page_js_for_request_rendered_pages():
    @ui.server
    def numbers() -> list[int]:
        return [1, 2, 3]

    def page():
        data = ui.resource(numbers, server_render=True)
        return ui.Page(ui.Each(data.value, render=lambda item: ui.Text(item)))

    ui.page("/")(page)
    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/")
    csp = response.headers["content-security-policy"]
    # Two inline scripts: theme bootstrap plus the inline page module.
    assert csp.count("'sha256-") == 2


def test_additional_security_headers_present():
    app = _simple_app()
    response = asgi_request(app, "GET", "/")
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"


# -- cross-site request rejection ------------------------------------------------

def test_actions_reject_cross_site_origin():
    app = _simple_app()
    response = asgi_request(app, "POST", "/_virel/action/echo",
                            body=b'{"value": "x"}',
                            headers=[(b"origin", b"https://evil.example"),
                                     (b"host", b"myapp.example")])
    assert response.status == 403
    assert "not allowed" in response.json["error"]


def test_actions_accept_same_origin_and_allowed_origins():
    app = _simple_app()
    response = asgi_request(app, "POST", "/_virel/action/echo",
                            body=b'{"value": "x"}',
                            headers=[(b"origin", b"https://myapp.example"),
                                     (b"host", b"myapp.example")])
    assert response.status == 200

    from virel.registry import fresh_registry
    fresh_registry()
    app = _simple_app(allowed_origins=["https://partner.example"])
    response = asgi_request(app, "POST", "/_virel/action/echo",
                            body=b'{"value": "x"}',
                            headers=[(b"origin", b"https://partner.example"),
                                     (b"host", b"myapp.example")])
    assert response.status == 200


def test_actions_reject_sec_fetch_site_cross_site():
    app = _simple_app()
    response = asgi_request(app, "POST", "/_virel/action/echo",
                            body=b'{"value": "x"}',
                            headers=[(b"sec-fetch-site", b"cross-site")])
    assert response.status == 403


def test_actions_reject_non_json_content_type():
    app = _simple_app()
    response = asgi_request(app, "POST", "/_virel/action/echo",
                            body=b'{"value": "x"}',
                            headers=[(b"content-type",
                                      b"application/x-www-form-urlencoded")])
    assert response.status == 403
    assert "JSON" in response.json["error"]


def test_actions_reject_oversized_bodies():
    app = _simple_app(max_body_bytes=100)
    payload = json.dumps({"value": "x" * 500}).encode()
    response = asgi_request(app, "POST", "/_virel/action/echo", body=payload)
    assert response.status == 413


# -- URL scheme sanitization ---------------------------------------------------

def test_safe_url_blocks_dangerous_schemes():
    assert safe_url("javascript:alert(1)") == "#"
    assert safe_url("JaVaScRiPt:alert(1)") == "#"
    assert safe_url("vbscript:x") == "#"
    assert safe_url("data:text/html,<script>") == "#"
    assert safe_url("https://example.com/a") == "https://example.com/a"
    assert safe_url("/relative/path") == "/relative/path"
    assert safe_url("mailto:a@b.co") == "mailto:a@b.co"
    assert safe_url("data:image/png;base64,x", image=True).startswith("data:")


def test_link_rejects_javascript_urls_at_compile_time():
    with pytest.raises(VirelCompileError, match="blocked URL scheme"):
        ui.Link("click", to="javascript:alert(1)")


def test_image_rejects_javascript_urls_at_compile_time():
    with pytest.raises(VirelCompileError, match="blocked URL scheme"):
        ui.Image("javascript:alert(1)", alt="x")


def test_dynamic_urls_in_each_templates_are_sanitized_both_sides():
    @ui.server
    def links() -> list[dict]:
        return [{"url": "javascript:alert(1)", "label": "evil"}]

    def page():
        data = ui.resource(links, server_render=True)
        return ui.Page(ui.Each(
            data.value,
            render=lambda item: ui.Link(item.label, to=item.url),
        ))

    result = compile_page(_page(page))
    # Server-rendered HTML neutralizes the scheme in the URL context. The
    # raw string still exists as data inside the embedded JSON (a JS string,
    # already script-context encoded), which is harmless.
    assert 'href="#"' in result.html
    assert 'href="javascript' not in result.html
    # The client template routes the URL through the runtime check.
    assert "$.safeUrl(item.url)" in result.js


def test_bound_url_attributes_are_sanitized():
    def page():
        target = ui.state("javascript:alert(1)")
        from virel.nodes import Element, TextNode
        return ui.Page(Element("a", attrs={"href": target, "class": "v-link"},
                               children=[TextNode("profile")]))

    result = compile_page(_page(page))
    assert 'href="#"' in result.html
    assert "$.safeUrl(" in result.js


# -- output encoding (regression coverage) ----------------------------------------

def test_inline_state_json_cannot_break_script_context():
    def page():
        payload = ui.state("</script><script>alert(1)</script>")
        return ui.Page(ui.TextField(payload, label="x"))

    # Force the inline-JS variant, where the state initial is embedded.
    result = compile_page(_page(page), inline_js=True)
    head = result.html.split("<body>")[0]
    assert "</script><script>alert" not in head
    assert "\\u003c/script\\u003e" in head


def test_public_files_cannot_escape_the_public_directory(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "ok.txt").write_text("fine")
    (tmp_path / "secret.txt").write_text("secret")

    @ui.page("/")
    def home():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True, public_dir=public)
    assert asgi_request(app, "GET", "/public/ok.txt").status == 200
    assert asgi_request(app, "GET", "/public/../secret.txt").status == 404
    assert asgi_request(app, "GET", "/public/%2e%2e/secret.txt").status == 404


def test_unsafe_html_requires_a_reason():
    with pytest.raises(VirelCompileError, match="reason"):
        ui.unsafe_html("<b>x</b>", reason="")
