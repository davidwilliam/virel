"""Secure cookies, SBOM, build metadata, and serialization safety."""

from pathlib import Path

import pytest

from virel import ui
from virel.registry import Request, active_registry
from virel.lockfile import (LOCK_NAME, installed_lock, verify_lock,
                            write_lock)
from virel.sbom import (build_metadata, digest_directory, generate_sbom,
                        source_digest)
from virel.server import create_asgi_app

from conftest import asgi_request


# --- secure cookies -------------------------------------------------------

def test_set_cookie_secure_defaults():
    request = Request(method="GET", path="/")
    request.set_cookie("session", "abc123")
    assert len(request.response_cookies) == 1
    cookie = request.response_cookies[0]
    assert "session=abc123" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=Lax" in cookie
    assert "Path=/" in cookie


def test_set_cookie_session_has_no_max_age():
    request = Request(method="GET", path="/")
    request.set_cookie("s", "v")
    assert "Max-Age" not in request.response_cookies[0]
    request.set_cookie("t", "v", max_age=3600)
    assert "Max-Age=3600" in request.response_cookies[1]


def test_clear_cookie_expires_immediately():
    request = Request(method="GET", path="/")
    request.clear_cookie("session")
    assert "Max-Age=0" in request.response_cookies[0]


def test_set_cookie_rejects_bad_name():
    request = Request(method="GET", path="/")
    with pytest.raises(Exception):
        request.set_cookie("bad name", "v")


def test_set_cookie_rejects_unencoded_value():
    request = Request(method="GET", path="/")
    with pytest.raises(Exception):
        request.set_cookie("s", "a; b")


def test_samesite_none_requires_secure():
    request = Request(method="GET", path="/")
    with pytest.raises(Exception):
        request.set_cookie("s", "v", same_site="None", secure=False)


def test_guard_cookie_reaches_response_header():
    def guard(request):
        request.set_cookie("session", "tok", max_age=3600)
        return None

    @ui.page("/dash", guard=guard)
    def dash():
        return ui.Page(ui.Text("Dashboard"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/dash")
    cookie = response.headers.get("set-cookie", "")
    assert "session=tok" in cookie
    assert "HttpOnly" in cookie and "Secure" in cookie


def test_no_cookie_header_without_set_cookie():
    @ui.page("/plain")
    def plain():
        return ui.Page(ui.Text("plain"))

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/plain")
    assert "set-cookie" not in response.headers


def test_guard_cookie_reaches_action_response():
    def guard(request):
        request.set_cookie("session", "tok", max_age=3600)
        return None

    @ui.page("/app")
    def home():
        return ui.Page(ui.Text("home"))

    @ui.server(guard=guard)
    def touch() -> str:
        return "ok"

    app = create_asgi_app(dev=True)
    response = asgi_request(
        app, "POST", "/_virel/action/touch", body=b"{}",
        headers=[(b"content-type", b"application/json"),
                 (b"origin", b"http://testserver"),
                 (b"host", b"testserver")])
    cookie = response.headers.get("set-cookie", "")
    assert "session=tok" in cookie


# --- SBOM -----------------------------------------------------------------

def test_sbom_is_cyclonedx():
    doc = generate_sbom(Path("."), app_name="demo", app_version="1.2.3")
    assert doc["bomFormat"] == "CycloneDX"
    assert doc["specVersion"] == "1.5"
    assert doc["metadata"]["component"]["name"] == "demo"
    assert doc["metadata"]["component"]["version"] == "1.2.3"


def test_sbom_lists_virel_with_purl():
    doc = generate_sbom(Path("."))
    virel = [c for c in doc["components"] if c["name"] == "virel"]
    assert virel, "virel should appear in the SBOM"
    assert virel[0]["purl"].startswith("pkg:pypi/virel@")
    assert all(c["type"] == "library" for c in doc["components"])


def test_sbom_components_sorted_and_deduped():
    doc = generate_sbom(Path("."))
    names = [c["name"] for c in doc["components"]]
    assert names == sorted(names, key=str.lower) or names == sorted(names)
    assert len(names) == len(set(names))


# --- build metadata (reproducible) ----------------------------------------

def test_build_metadata_is_deterministic():
    root = Path(".")
    assert build_metadata(root) == build_metadata(root)


def test_build_metadata_has_no_timestamp():
    meta = build_metadata(Path("."))
    blob = repr(meta).lower()
    assert "time" not in blob and "date" not in blob
    assert meta["reproducible"] is True
    assert meta["source_digest"].startswith("sha256:")


def test_source_digest_changes_with_content(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = source_digest(tmp_path)
    (tmp_path / "a.py").write_text("x = 2\n")
    second = source_digest(tmp_path)
    assert first != second


def test_digest_directory_order_independent(tmp_path):
    (tmp_path / "a.txt").write_text("one")
    (tmp_path / "b.txt").write_text("two")
    assert digest_directory(tmp_path).startswith("sha256:")
    assert digest_directory(tmp_path) == digest_directory(tmp_path)


# --- dependency lockfile and integrity ------------------------------------

def test_installed_lock_pins_virel_with_digest():
    lock = installed_lock()
    assert lock["schema"] == "virel-lock/1"
    names = {p["name"] for p in lock["packages"]}
    assert "virel" in names
    assert all(p["digest"].startswith("sha256:") for p in lock["packages"])


def test_lockfile_write_then_verify_is_clean(tmp_path):
    write_lock(tmp_path)
    assert (tmp_path / LOCK_NAME).exists()
    assert verify_lock(tmp_path) == []


def test_lockfile_detects_version_drift(tmp_path):
    import json
    write_lock(tmp_path)
    data = json.loads((tmp_path / LOCK_NAME).read_text())
    data["packages"][0]["version"] = "999.0.0"
    (tmp_path / LOCK_NAME).write_text(json.dumps(data))
    issues = verify_lock(tmp_path)
    assert any("999.0.0" in i for i in issues)


def test_lockfile_detects_missing_package(tmp_path):
    import json
    write_lock(tmp_path)
    data = json.loads((tmp_path / LOCK_NAME).read_text())
    data["packages"].append(
        {"name": "ghostpkg", "version": "1.0", "digest": "sha256:0"})
    (tmp_path / LOCK_NAME).write_text(json.dumps(data))
    issues = verify_lock(tmp_path)
    assert any("ghostpkg" in i and "not installed" in i for i in issues)


def test_verify_without_lockfile_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_lock(tmp_path)


# --- serialization safety (SPEC 18.3) -------------------------------------

def test_no_pickle_or_eval_in_source():
    src = Path("src/virel")
    banned = ("import pickle", "pickle.loads", "pickle.load",
              "marshal.loads", "eval(", "exec(")
    offenders = []
    for path in src.rglob("*.py"):
        text = path.read_text("utf-8")
        for token in banned:
            if token in text:
                offenders.append(f"{path}: {token}")
    assert not offenders, f"unsafe serialization found: {offenders}"
