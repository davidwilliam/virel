"""Compile-time syntax highlighting."""

from virel import ui
from virel.compiler import compile_page
from virel.highlight import highlight
from virel.registry import active_registry


def test_python_tokens_classified():
    spans = highlight('@ui.page("/x")\ndef home(n=1):\n    # note\n    return f"{n}"\n',
                      "python")
    classes = {cls for cls, _ in spans}
    assert "kw" in classes       # def, return
    assert "str" in classes      # the string literals
    assert "num" in classes      # 1
    assert "com" in classes      # the comment
    assert "fn" in classes       # home after def
    text = "".join(t for _, t in spans)
    assert 'def home(n=1):' in text


def test_roundtrip_preserves_source():
    code = ('import math\n\n'
            'class Point:\n'
            '    def __init__(self, x: float):\n'
            '        self.x = x  # coordinate\n')
    spans = highlight(code, "python")
    assert "".join(t for _, t in spans) == code


def test_unsupported_language_and_broken_code_fall_back():
    assert highlight("SELECT 1", "sql") is None
    assert highlight("def broken(:", "python") is None


def _classes(code, language):
    spans = highlight(code, language)
    assert spans is not None
    # Spans must tile the whole input exactly (no dropped characters).
    assert "".join(text for _, text in spans) == code
    return {cls for cls, _ in spans}


def test_bash_highlighting():
    classes = _classes('pip install virel --upgrade  # setup', "bash")
    assert "dec" in classes   # the --upgrade flag
    assert "com" in classes   # the comment


def test_json_highlighting():
    classes = _classes('{"name": "virel", "n": 2, "ok": true}', "json")
    assert "blt" in classes   # property names
    assert "str" in classes   # string values
    assert "num" in classes and "kw" in classes  # 2 and true


def test_toml_highlighting():
    classes = _classes('[app]\nname = "demo"\nport = 8000\n', "toml")
    assert "dec" in classes   # the [app] table header
    assert "blt" in classes   # keys
    assert "str" in classes and "num" in classes


def test_toml_array_value_is_not_a_table_header():
    spans = highlight('deps = ["a", "b"]\n', "toml")
    # The bracketed array is not miscolored as a table header.
    assert not any(cls == "dec" for cls, _ in spans)


def test_code_component_emits_token_spans():
    @ui.page("/")
    def page():
        return ui.Page(ui.Code('def go():\n    return "ok"\n',
                               block=True, language="python"))

    result = compile_page(active_registry().pages["/"])
    assert '<span class="v-tok-kw">def</span>' in result.html
    assert '<span class="v-tok-fn">go</span>' in result.html
    assert '<span class="v-tok-str">&quot;ok&quot;</span>' in result.html
    # Highlighted code costs no JavaScript.
    assert result.js is None


def test_code_component_plain_without_language():
    @ui.page("/")
    def page():
        return ui.Page(ui.Code("plain <text>", block=True))

    result = compile_page(active_registry().pages["/"])
    assert "v-tok-" not in result.html
    assert "plain &lt;text&gt;" in result.html
