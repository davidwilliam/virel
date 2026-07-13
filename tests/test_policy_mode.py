"""Enterprise policy mode (SPEC 18.5)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry, fresh_registry


def test_unknown_policy_flag_rejected():
    with pytest.raises(VirelCompileError, match="Unknown policy"):
        ui.use_policy(mystery=True)


def test_prohibit_raw_javascript_and_html():
    ui.use_policy(raw_javascript=False, raw_html=False)
    with pytest.raises(VirelCompileError, match="prohibited by policy"):
        ui.unsafe.javascript("x()", reason="legacy")
    with pytest.raises(VirelCompileError, match="prohibited by policy"):
        ui.unsafe_html("<b>x</b>", reason="legacy")


def test_approved_components_allowlist():
    ui.use_policy(approved_components={"Page", "Button", "Text"})

    @ui.page("/ok")
    def ok():
        return ui.Page(ui.Button("Hi"), ui.Text("there"))

    compile_page(active_registry().pages["/ok"])  # all approved

    @ui.page("/bad")
    def bad():
        return ui.Page(ui.Card(ui.Text("x")))     # Card not approved

    with pytest.raises(VirelCompileError, match="approved-components"):
        compile_page(active_registry().pages["/bad"])
    fresh_registry()


def test_approved_plugins_allowlist():
    ui.use_policy(approved_plugins={"linter"})

    class Linter(ui.Plugin):
        name = "linter"
        capabilities = ("lint",)

    ui.use_plugin(Linter())   # approved

    class Other(ui.Plugin):
        name = "sneaky"
        capabilities = ("lint",)

    with pytest.raises(VirelCompileError, match="approved-plugins"):
        ui.use_plugin(Other())
    fresh_registry()


def test_accessibility_strict_promotes_warnings():
    ui.use_policy(accessibility_strict=True)
    assert active_registry().strict_accessibility is True

    @ui.page("/skip")
    def skip():
        return ui.Page(ui.Heading("One", level=1),
                       ui.Heading("Deep", level=3))   # heading skip warning

    with pytest.raises(VirelCompileError, match="strict"):
        compile_page(active_registry().pages["/skip"])
    fresh_registry()


def test_csp_connect_src_tightens_outbound():
    ui.use_policy(csp_connect_src="'none'")
    from virel.security import content_security_policy
    csp = content_security_policy(
        [], connect_src=active_registry().policy["csp_connect_src"])
    assert "connect-src 'none';" in csp
    fresh_registry()


def test_deployment_targets_and_dependency_allowlist_are_stored():
    ui.use_policy(deployment_targets={"asgi"},
                  dependency_allowlist={"pydantic"},
                  max_bundle_gzip=20000)
    policy = active_registry().policy
    assert policy["deployment_targets"] == {"asgi"}
    assert policy["dependency_allowlist"] == {"pydantic"}
    assert policy["max_bundle_gzip"] == 20000
    fresh_registry()


def test_dependency_allowlist_scan():
    import tempfile
    from pathlib import Path
    from virel.cli import _check_dependency_allowlist

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = root / "app"
        app.mkdir()
        (app / "page.py").write_text(
            "import json\n"          # stdlib: allowed
            "import virel\n"          # virel: allowed
            "import requests\n"       # third-party: not on allowlist
            "from pandas import DataFrame\n")  # not on allowlist
        offenders = _check_dependency_allowlist(root, {"pandas"})
        # requests is flagged; pandas is allowlisted; json/virel are fine.
        joined = " ".join(offenders)
        assert "requests" in joined
        assert "pandas" not in joined
        assert "json" not in joined
