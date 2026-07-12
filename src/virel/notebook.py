"""Notebook integration (SPEC 12.5).

``ui.preview(fn)`` renders a page or component inline in Jupyter using
the production compiler: the same trace, the same emitter, the same
accessibility audit, the same runtime. There is no notebook-only API;
whatever previews here ships unchanged.

The preview is a fully self-contained document in a sandboxed iframe:
the stylesheet and runtime are inlined, so browser-local interactivity
(states, handlers, derived values) works with no server. Server-backed
features (actions, resources, uploads) need `virel dev`, and the
preview says so instead of failing silently.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any, Callable

from .expr import VirelCompileError
from .nodes import PageNode


class Preview:
    """A compiled preview. Jupyter renders it through ``_repr_html_``;
    ``document`` is the standalone HTML for anything else (files,
    tests, other tools)."""

    def __init__(self, document: str, height: int) -> None:
        self.document = document
        self.height = height

    def _repr_html_(self) -> str:
        return (
            f'<iframe srcdoc="{_html.escape(self.document, quote=True)}" '
            f'style="width: 100%; height: {self.height}px; border: 1px '
            'solid #d7d9de; border-radius: 10px; background: white" '
            'sandbox="allow-scripts" title="Virel preview"></iframe>'
        )

    def save(self, path: str) -> None:
        """Write the standalone document to a file."""
        from pathlib import Path
        Path(path).write_text(self.document, encoding="utf-8")


def preview(fn: Callable[[], Any], *, height: int = 480) -> Preview:
    """Compile and preview a page or component function inline:

        ui.preview(model_playground)

    ``fn`` is any function returning ``ui.Page(...)`` or a component
    node; components are wrapped in a page automatically. Compilation
    is the production pipeline end to end."""
    if not callable(fn):
        raise VirelCompileError("ui.preview takes a page or component "
                                "function.")

    def wrapped() -> PageNode:
        from .elements import Page
        result = fn()
        if isinstance(result, PageNode):
            return result
        return Page(result, title="Preview")

    from .compiler import compile_page
    from .registry import Page as PageRecord
    record = PageRecord(path="/__preview__", fn=wrapped, render="auto")
    compiled = compile_page(record, inline_js=True)
    return Preview(_standalone_document(compiled), height)


def _standalone_document(compiled: Any) -> str:
    """One self-contained HTML document: inline stylesheet, inline
    runtime, inline page module. Exactly the production artifacts,
    packaged without a server."""
    from .registry import active_registry
    from .theme import Theme, build_stylesheet
    theme = active_registry().theme or Theme()
    stylesheet = build_stylesheet(theme)

    script = ""
    if compiled.js:
        script = _bundle(compiled.js)
    notice = ""
    if compiled.server_actions:
        names = ", ".join(compiled.server_actions)
        notice = (
            '<div class="v-alert v-alert-neutral" role="note">Server '
            f"actions ({_html.escape(names)}) need virel dev; this "
            "preview runs browser-side interactivity only.</div>\n"
        )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">\n'
        f"<title>{_html.escape(compiled.title)}</title>\n"
        f"<style>\n{stylesheet}\n</style>\n</head>\n"
        f'<body class="v-preview">\n<div class="v-container '
        f'v-container-lg" style="padding-block: 16px">\n{notice}'
        f"{compiled.body_html}\n</div>\n"
        + (f'<script type="module">\n{script}\n</script>\n' if script
           else "")
        + "</body>\n</html>\n"
    )


def _bundle(page_js: str) -> str:
    """Inline the runtime into the page module: exports become a local
    namespace, and the module import disappears. The sources are
    byte-identical to production apart from that packaging."""
    from .theme import runtime_js
    runtime = runtime_js()
    names = re.findall(r"^export (?:async )?function (\w+)", runtime,
                       re.MULTILINE)
    body = re.sub(r"^export (?=(?:async )?function )", "", runtime,
                  flags=re.MULTILINE)
    namespace = (
        "const $ = (() => {\n" + body + "\nreturn { "
        + ", ".join(names) + " };\n})();\n"
    )
    module = re.sub(r'^import \* as \$ from "[^"]+";\n', "", page_js,
                    flags=re.MULTILINE)
    module = module.replace("export function mount", "function mount", 1)
    return namespace + module
