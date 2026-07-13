"""Extended client subset: aggregates, range, comprehensions, dicts
(unblocks richer @ui.worker and @ui.client bodies)."""

import pytest

from virel import ui
from virel.expr import VirelCompileError


def _client_js(fn):
    return ui.client(fn).js_definition()


def test_sum_and_aggregates():
    @ui.client
    def total(xs):
        return sum(xs)

    assert total([1, 2, 3]) == 6
    assert "reduce" in total.js_definition()

    @ui.client
    def flags(xs):
        return any(xs) and all(xs)

    assert flags([1, 1]) is True and flags([0, 1]) is False


def test_range_in_expression_and_loop():
    @ui.client
    def squares(n):
        return [i * i for i in range(n)]

    assert squares(4) == [0, 1, 4, 9]

    @ui.client
    def accumulate(n):
        acc = 0
        for i in range(1, n):
            acc = acc + i
        return acc

    assert accumulate(5) == 1 + 2 + 3 + 4
    assert "Array.from" in accumulate.js_definition()


def test_list_comprehension_with_filter():
    @ui.client
    def evens(xs):
        return [x for x in xs if x % 2 == 0]

    assert evens([1, 2, 3, 4]) == [2, 4]
    js = evens.js_definition()
    assert ".filter(" in js and ".map(" in js

    def multi():
        return [a + b for a in [1] for b in [2]]

    with pytest.raises(VirelCompileError, match="single-loop"):
        _client_js(multi)


def test_dict_literals_and_worker_dict_return():
    @ui.worker
    def summarize(nums):
        return {"total": sum(nums), "max": max(nums), "n": len(nums)}

    # Server/test side.
    assert summarize([3, 1, 4]) == {"total": 8, "max": 4, "n": 3}

    @ui.page("/dict-worker")
    def dict_worker():
        data = ui.state([3, 1, 4])
        out = ui.state({})
        return ui.Page(
            ui.Button("Go", on_click=lambda: summarize.run(data, into=out)),
            ui.Text(f"{out}"),
        )

    from virel.compiler import compile_page
    from virel.registry import active_registry
    compiled = compile_page(active_registry().pages["/dict-worker"])
    assert "total" in compiled.js and "reduce" in compiled.js

    view = ui.test.render(dict_worker)
    view.get_by_role("button", name="Go").click()
    assert view.state("s2") == {"total": 8, "max": 4, "n": 3}


def test_dict_keys_must_be_string_literals():
    def bad():
        return {1: "no"}   # non-string key

    with pytest.raises(VirelCompileError, match="string literals"):
        _client_js(bad)
