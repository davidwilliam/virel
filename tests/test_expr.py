"""The symbolic expression layer: JS emission, initial evaluation, and
deterministic errors for unsupported constructs."""

import pytest

from virel import ui
from virel.expr import TraceContext, VirelCompileError, parse_sentinels


def test_arithmetic_and_comparison_emit_js():
    with TraceContext():
        count = ui.state(0)
        expr = (count + 1) * 2
        assert expr.js() == "((S.s1.get() + 1) * 2)"
        cmp = count >= 10
        assert cmp.js() == "(S.s1.get() >= 10)"


def test_expression_evaluates_initial_value():
    with TraceContext():
        count = ui.state(3)
        expr = (count + 1) * 2
        assert expr.evaluate({"s1": 3}) == 8


def test_string_methods_map_to_js():
    with TraceContext():
        query = ui.state("")
        expr = query.strip().lower()
        assert expr.js() == "S.s1.get().trim().toLowerCase()"
        assert expr.evaluate({"s1": "  HeLLo "}) == "hello"


def test_fstring_becomes_reactive_template():
    with TraceContext():
        count = ui.state(0)
        parsed = parse_sentinels(f"Count: {count}")
        assert parsed.js() == "`Count: ${S.s1.get()}`"
        assert parsed.evaluate({"s1": 7}) == "Count: 7"


def test_derived_traces_expression():
    with TraceContext() as ctx:
        query = ui.state("x")
        normalized = ui.derived(lambda: query.strip().lower())
        assert ctx.derived[normalized.name].expr.js() == \
            "S.s1.get().trim().toLowerCase()"


def test_python_if_on_reactive_value_fails_with_guidance():
    with TraceContext():
        flag = ui.state(True)
        with pytest.raises(VirelCompileError, match="ui.When"):
            if flag:  # noqa: SIM108 — intentionally exercising the error
                pass


def test_unsupported_method_names_replacement():
    with TraceContext():
        value = ui.state("a")
        with pytest.raises(VirelCompileError, match="supported reactive subset"):
            value.casefold()


def test_state_outside_page_compilation_fails():
    with pytest.raises(VirelCompileError, match="page or component"):
        ui.state(0)


def test_mutation_outside_handler_fails():
    with TraceContext():
        count = ui.state(0)
        with pytest.raises(VirelCompileError, match="event handler"):
            count.set(1)


def test_cond_helper():
    with TraceContext():
        count = ui.state(0)
        expr = ui.cond(count > 0, "some", "none")
        assert expr.js() == '((S.s1.get() > 0) ? "some" : "none")'
        assert expr.evaluate({"s1": 0}) == "none"
