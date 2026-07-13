"""Compile-time syntax highlighting for ui.Code.

Highlighting happens during compilation using the standard library
tokenizer, so highlighted code blocks are plain HTML spans: no client
JavaScript, no external highlighter, and the colors come from theme
tokens so they follow light and dark modes.
"""

from __future__ import annotations

import builtins
import io
import keyword
import re
import tokenize

TokenSpan = tuple[str, str]  # (css class suffix, text)

_BUILTIN_NAMES = frozenset(dir(builtins))
_SELF_LIKE = frozenset({"self", "cls"})


def highlight(code: str, language: str) -> list[TokenSpan] | None:
    """Tokenize code into (class, text) spans, or None when the language
    is unsupported or the snippet cannot be tokenized."""
    if language in ("python", "py"):
        try:
            return _python(code)
        except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
            return None
    rules = _REGEX_LANGUAGES.get(language)
    if rules is not None:
        return _scan(code, rules)
    return None


def _python(code: str) -> list[TokenSpan]:
    spans: list[TokenSpan] = []
    lines = code.splitlines(keepends=True)
    row, column = 1, 0

    def advance_to(target_row: int, target_col: int) -> None:
        nonlocal row, column
        while (row, column) < (target_row, target_col):
            line = lines[row - 1] if row - 1 < len(lines) else ""
            if row < target_row:
                spans.append(("ws", line[column:]))
                row += 1
                column = 0
            else:
                spans.append(("ws", line[column:target_col]))
                column = target_col

    tokens = tokenize.generate_tokens(io.StringIO(code).readline)
    previous_name: str | None = None
    in_decorator = False
    for token in tokens:
        kind, text, start, end, _line = token
        if kind in (tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        advance_to(*start)
        cls = _classify(kind, text, previous_name)
        # Decorators color through the whole dotted chain (@ui.page).
        if in_decorator:
            if kind == tokenize.NAME and not keyword.iskeyword(text):
                cls = "dec"
            elif kind == tokenize.OP and text == ".":
                cls = "dec"
            else:
                in_decorator = False
        if kind in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
                    tokenize.DEDENT):
            cls = "ws"
        spans.append((cls, text))
        if kind == tokenize.OP and text == "@":
            in_decorator = True
        if kind == tokenize.NAME:
            previous_name = text
        elif kind == tokenize.OP and text == "@":
            previous_name = "@"
        elif kind not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                          tokenize.DEDENT):
            previous_name = None
        row, column = end

    return _merge(spans)


def _classify(kind: int, text: str, previous: str | None) -> str:
    if kind == tokenize.COMMENT:
        return "com"
    # f-string part tokens exist only on Python 3.12+.
    if kind in (tokenize.STRING,
                getattr(tokenize, "FSTRING_START", -1),
                getattr(tokenize, "FSTRING_MIDDLE", -1),
                getattr(tokenize, "FSTRING_END", -1)):
        return "str"
    if kind == tokenize.NUMBER:
        return "num"
    if kind == tokenize.OP:
        return "op" if text not in "()[]{},:;" else "pun"
    if kind == tokenize.NAME:
        if keyword.iskeyword(text) or keyword.issoftkeyword(text):
            return "kw"
        if previous in ("def", "class"):
            return "fn"
        if previous == "@":
            return "dec"
        if text in _SELF_LIKE:
            return "self"
        if text in _BUILTIN_NAMES:
            return "blt"
    return "txt"


def _merge(spans: list[TokenSpan]) -> list[TokenSpan]:
    """Merge adjacent spans with the same class to keep the HTML small."""
    merged: list[TokenSpan] = []
    for cls, text in spans:
        if not text:
            continue
        if merged and merged[-1][0] == cls:
            merged[-1] = (cls, merged[-1][1] + text)
        else:
            merged.append((cls, text))
    return merged


# --- regex-based highlighters for non-Python languages --------------------
#
# Each language is an ordered list of (compiled pattern, css class). The
# scanner tries each rule at the current position and takes the first
# match; any character no rule matches becomes plain text, so the spans
# always tile the whole input exactly.

def _scan(code: str, rules: list[tuple]) -> list[TokenSpan]:
    spans: list[TokenSpan] = []
    index, length = 0, len(code)
    while index < length:
        for pattern, cls in rules:
            match = pattern.match(code, index)
            if match and match.end() > index:
                spans.append((cls, match.group(0)))
                index = match.end()
                break
        else:
            spans.append(("txt", code[index]))
            index += 1
    return _merge(spans)


def _rules(*pairs: tuple[str, str]) -> list[tuple]:
    return [(re.compile(pattern), cls) for pattern, cls in pairs]


_WS = (r"\s+", "ws")
_DQ_STRING = (r'"(?:[^"\\]|\\.)*"', "str")
_SQ_STRING = (r"'(?:[^'\\]|\\.)*'", "str")

_BASH_RULES = _rules(
    (r"#.*", "com"),
    _DQ_STRING,
    _SQ_STRING,
    (r"\$\{[^}]*\}|\$\w+", "blt"),                 # variables
    (r"(?<![\w-])--?[A-Za-z][\w-]*", "dec"),        # flags
    (r"\b(?:if|then|else|elif|fi|for|while|until|do|done|case|esac|in|"
     r"function|return|export|local)\b", "kw"),
    (r"\b\d+\b", "num"),
    (r"[|&><;]+", "op"),
    _WS,
)

_JSON_RULES = _rules(
    (r'"(?:[^"\\]|\\.)*"(?=\s*:)', "blt"),           # property names
    _DQ_STRING,
    (r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", "num"),
    (r"\b(?:true|false|null)\b", "kw"),
    (r"[{}\[\],:]", "pun"),
    _WS,
)

_TOML_RULES = _rules(
    (r"#.*", "com"),
    (r"\[\[?[A-Za-z0-9_.\s-]+\]\]?", "dec"),         # table headers
    _DQ_STRING,
    _SQ_STRING,
    (r"\b(?:true|false)\b", "kw"),
    (r"[A-Za-z0-9_.-]+(?=\s*=)", "blt"),             # keys
    (r"[+-]?\d[\d:_.T+-]*", "num"),                  # numbers and dates
    (r"=", "op"),
    _WS,
)

_REGEX_LANGUAGES: dict[str, list[tuple]] = {
    "bash": _BASH_RULES, "sh": _BASH_RULES, "shell": _BASH_RULES,
    "console": _BASH_RULES,
    "json": _JSON_RULES,
    "toml": _TOML_RULES,
}
