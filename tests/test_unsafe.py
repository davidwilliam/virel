"""Escape hatches and policy (SPEC 13.3)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry


def test_raw_javascript_handler_emits_verbatim():
    @ui.page("/raw-js")
    def raw_js():
        return ui.Page(ui.Button(
            "Track",
            on_click=ui.unsafe.javascript(
                "window.vendorSdk.track('click')",
                reason="Vendor SDK has no module API")))

    compiled = compile_page(active_registry().pages["/raw-js"])
    assert "window.vendorSdk.track('click')" in compiled.js
    ir = compiled.ir["tree"]
    assert "unsafe_javascript" in str(ir)  # the reason is inspectable

    view = ui.test.render(raw_js)
    with pytest.raises(AssertionError, match="browser test"):
        view.get_by_role("button", name="Track").click()


def test_raw_javascript_requires_a_reason():
    with pytest.raises(VirelCompileError, match="reason"):
        ui.unsafe.javascript("x()", reason=" ")
    with pytest.raises(VirelCompileError, match="needs code"):
        ui.unsafe.javascript("", reason="because")


def test_policy_prohibits_raw_javascript():
    ui.use_policy(raw_javascript=False)
    with pytest.raises(VirelCompileError, match="prohibited by policy"):
        ui.unsafe.javascript("x()", reason="legacy")


def test_policy_prohibits_raw_html_from_users_not_the_compiler():
    ui.use_policy(raw_html=False)
    with pytest.raises(VirelCompileError, match="prohibited by policy"):
        ui.unsafe_html("<b>x</b>", reason="legacy")
    with pytest.raises(VirelCompileError, match="prohibited by policy"):
        ui.unsafe.html("<b>x</b>", reason="legacy")
    # Compiler-generated raw HTML (charts) is not user input and still
    # works under the policy.
    chart = ui.Chart("donut", [ui.Series("Passed", value=1)])
    assert chart is not None


def test_unknown_policy_flags_are_rejected():
    with pytest.raises(VirelCompileError, match="Unknown policy"):
        ui.use_policy(allow_everything=True)
