"""The AST client compiler: named handlers with control flow, @ui.client
functions, and deterministic errors outside the subset."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import TraceContext, VirelCompileError
from virel.pycompiler import compile_handler
from virel.registry import active_registry


def test_handler_with_branches_compiles_to_js():
    with TraceContext():
        status = ui.state("")
        count = ui.state(0)

        def apply():
            if count > 3:
                status.set("high")
            elif count > 0:
                status.set("low")
            else:
                status.set("zero")

        handler = compile_handler(apply)
        js = handler.js()
        assert "if ((S.s2.get() > 3))" in js
        assert 'S.s1.set("high");' in js
        assert "else" in js


def test_handler_executes_in_python_for_tests():
    with TraceContext():
        status = ui.state("")
        count = ui.state(5)

        def apply():
            if count > 3:
                status.set("high")
            else:
                status.set("low")

        handler = compile_handler(apply)
        env = {"s1": "", "s2": 5}
        handler.execute(env)
        assert env["s1"] == "high"
        env["s2"] = 1
        handler.execute(env)
        assert env["s1"] == "low"


def test_handler_locals_and_fstrings():
    with TraceContext():
        message = ui.state("")
        n = ui.state(2)

        def build():
            total = n * 10
            label = f"total is {total}"
            message.set(label)

        handler = compile_handler(build)
        js = handler.js()
        assert "let total = (S.s2.get() * 10);" in js
        assert "let label = `total is ${total}`;" in js
        env = {"s1": "", "s2": 2}
        handler.execute(env)
        assert env["s1"] == "total is 20"


def test_handler_update_lambda_is_inlined():
    with TraceContext():
        count = ui.state(0)

        def bump():
            count.update(lambda c: c + 2)

        handler = compile_handler(bump)
        assert "S.s1.set((S.s1.get() + 2));" in handler.js()


def test_for_loop_over_list():
    with TraceContext():
        total = ui.state(0)

        def sum_all():
            acc = 0
            for value in [1, 2, 3]:
                acc = acc + value
            total.set(acc)

        handler = compile_handler(sum_all)
        assert "for (const value of [1, 2, 3])" in handler.js()
        env = {"s1": 0}
        handler.execute(env)
        assert env["s1"] == 6


def test_while_loop_is_rejected_with_guidance():
    with TraceContext():
        count = ui.state(0)

        def spin():
            while True:
                count.set(1)

        with pytest.raises(VirelCompileError, match="not in the client subset"):
            compile_handler(spin)


def test_calling_arbitrary_function_is_rejected():
    import math

    with TraceContext():
        out = ui.state(0.0)

        def compute():
            out.set(math.sqrt(2))

        with pytest.raises(VirelCompileError, match="client subset|cannot be"):
            compile_handler(compute)


def test_read_then_assign_of_state_name_gets_scoping_diagnostic():
    with TraceContext():
        status = ui.state("")
        count = ui.state(0)

        def clobber():
            status.set(f"was {count}")
            count = 5  # noqa: F841  makes `count` local, breaking the read

        with pytest.raises(VirelCompileError, match="local variable that\n?.*shadow|shadows"):
            compile_handler(clobber)


def test_client_function_compiles_and_runs_both_ways():
    @ui.client
    def normalize(value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) == 0:
            return ""
        return trimmed.lower()

    # Python execution (server side / tests)
    assert normalize("  HeLLo ") == "hello"
    # JS definition
    js = normalize.js_definition()
    assert js.startswith("function normalize(value)")
    assert "return trimmed.toLowerCase();" in js


def test_client_function_used_in_page_is_emitted_once():
    @ui.client
    def shout(value: str) -> str:
        return value.upper()

    @ui.page("/")
    def page():
        query = ui.state("hey")
        loud = ui.derived(lambda: shout(query))
        return ui.Page(
            ui.TextField(query, label="Q"),
            ui.Text(f"Loud: {loud}"),
        )

    result = compile_page(active_registry().pages["/"])
    assert result.js.count("function shout(value)") == 1
    assert "shout(S.s1.get())" in result.js
    # Server-rendered initial value used the Python implementation.
    assert "Loud: HEY" in result.html


def test_client_function_calling_client_function():
    @ui.client
    def double(n: int) -> int:
        return n * 2

    @ui.client
    def quadruple(n: int) -> int:
        return double(double(n))

    assert quadruple(3) == 12

    @ui.page("/")
    def page():
        n = ui.state(1)
        result = ui.derived(lambda: quadruple(n))
        return ui.Page(ui.TextField(n, label="N"), ui.Text(f"= {result}"))

    compiled = compile_page(active_registry().pages["/"])
    # Dependency emitted before its caller.
    assert compiled.js.index("function double") < compiled.js.index("function quadruple")
    assert "= 4" in compiled.html


def test_list_concatenation_emits_concat_not_plus():
    from virel.compiler import compile_page
    from virel.registry import active_registry

    @ui.page("/concat")
    def concat_page():
        items = ui.state(["a"])

        def add():
            items.update(lambda xs: xs + ["b"])

        def prepend():
            items.update(lambda xs: ["z"] + xs)

        return ui.Page(
            ui.Button("Add", on_click=add),
            ui.Button("Prepend", on_click=prepend),
            ui.Each(items, render=lambda item: ui.Text(item)),
        )

    js = compile_page(active_registry().pages["/concat"]).js
    # JS + on arrays coerces to strings; list math must emit concat.
    assert '.concat(["b"])' in js
    assert '["z"].concat(' in js

    view = ui.test.render(concat_page)
    view.get_by_role("button", name="Add").click()
    view.get_by_role("button", name="Prepend").click()
    assert view.state("s1") == ["z", "a", "b"]
