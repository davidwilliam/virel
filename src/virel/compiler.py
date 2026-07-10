"""Page compiler: Python source → trace → UI IR → HTML + JS.

Pipeline (SPEC 9.1): the page function runs once under a trace context,
producing an IR tree with symbolic reactive expressions. The emitter then
renders initial HTML server-side and generates a small imperative JS module
that binds fine-grained updates. Pages with no reactivity emit zero
JavaScript (SPEC 9.3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import elements
from .expr import TraceContext, VirelCompileError
from .nodes import IR_VERSION, Emitter, PageNode
from .registry import Page, active_registry


@dataclass
class CompiledPage:
    route: str
    slug: str
    title: str
    html: str
    js: str | None          # None => fully static, zero framework JS
    ir: dict[str, Any]
    server_actions: list[str] = field(default_factory=list)
    render_mode: str = "static"


def compile_page(page: Page, params: dict[str, Any] | None = None,
                 dev: bool = False, inline_js: bool = False) -> CompiledPage:
    elements._reset_page_modules()
    with TraceContext() as ctx:
        kwargs = dict(params or {})
        try:
            root = page.fn(**kwargs)
        except VirelCompileError as error:
            raise VirelCompileError(
                f"[route {page.path}] {error}"
            ) from None
        if not isinstance(root, PageNode):
            raise VirelCompileError(
                f"[route {page.path}] Page function {page.name!r} must return "
                "ui.Page(...). Got "
                f"{type(root).__name__!r}."
            )

        env = {name: state.initial for name, state in ctx.states.items()}
        # Derived values participate in the initial environment in
        # declaration order (a derived may read earlier deriveds).
        for name, derived in ctx.derived.items():
            env[name] = derived.expr.evaluate(env)

        emitter = Emitter(env)
        body_html = emitter.emit(root)

        ir = {
            "version": IR_VERSION,
            "route": page.path,
            "render": page.render,
            "title": root.title,
            "states": [s.to_ir() for s in ctx.states.values()],
            "derived": [d.to_ir() for d in ctx.derived.values()],
            "tree": root.to_ir(),
        }

        js = _emit_page_js(ctx, emitter)
        actions_used = _actions_in_bindings(emitter.bindings)
        render_mode = _resolve_render_mode(page, js, actions_used)

        html_doc = _emit_document(root, body_html, page.slug, js, dev=dev,
                                  inline_js=inline_js)
        return CompiledPage(
            route=page.path,
            slug=page.slug,
            title=root.title,
            html=html_doc,
            js=js,
            ir=ir,
            server_actions=actions_used,
            render_mode=render_mode,
        )


def _resolve_render_mode(page: Page, js: str | None, actions: list[str]) -> str:
    if page.render != "auto":
        _validate_declared_mode(page, js, actions)
        return page.render
    if page.is_dynamic:
        return "server"
    if js is None:
        return "static"
    return "client"


def _validate_declared_mode(page: Page, js: str | None, actions: list[str]) -> None:
    if page.render == "static":
        problems = []
        if page.is_dynamic:
            problems.append(f"route has dynamic parameters {page.param_names}")
        if actions:
            problems.append(f"route calls server actions: {', '.join(actions)}")
        if problems:
            raise VirelCompileError(
                f"[route {page.path}] declared render='static' but "
                + "; ".join(problems)
                + ". Remove the server dependency or use render='server'."
            )


def _actions_in_bindings(bindings: list[str]) -> list[str]:
    names = []
    for line in bindings:
        for marker in ('$.action("', '$.stream("'):
            start = 0
            while True:
                index = line.find(marker, start)
                if index == -1:
                    break
                begin = index + len(marker)
                end = line.index('"', begin)
                name = line[begin:end]
                if name not in names:
                    names.append(name)
                start = end
    return names


def _emit_page_js(ctx: TraceContext, emitter: Emitter) -> str | None:
    if not ctx.states and not ctx.derived and not emitter.bindings:
        return None
    lines = [
        'import * as $ from "/_virel/runtime.js";',
        "const S = {};",
    ]
    for name, state in ctx.states.items():
        lines.append(f"S.{name} = $.signal({json.dumps(state.initial)});")
    for name, derived in ctx.derived.items():
        lines.append(f"S.{name} = $.computed(() => {derived.expr.js()});")
    lines.extend(emitter.bindings)
    return "\n".join(lines) + "\n"


def _emit_document(root: PageNode, body_html: str, slug: str,
                   js: str | None, dev: bool, inline_js: bool = False) -> str:
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(root.title)}</title>",
        '<link rel="stylesheet" href="/_virel/app.css">',
    ]
    for name, content in root.meta.items():
        head.append(f'<meta name="{_escape(name)}" content="{_escape(content)}">')
    for module in root.head_modules:
        head.append(f'<script type="module" src="{_escape(module)}"></script>')
    if js is not None:
        if inline_js:
            head.append(f'<script type="module">\n{js}</script>')
        else:
            head.append(f'<script type="module" src="/_virel/page/{slug}.js"></script>')
    if dev:
        head.append('<script type="module" src="/_virel/dev.js"></script>')

    head_html = "\n    ".join(head)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        f"  <head>\n    {head_html}\n  </head>\n"
        f"  <body>\n{body_html}\n  </body>\n"
        "</html>\n"
    )


def _escape(text: str) -> str:
    import html
    return html.escape(str(text), quote=True)


# --------------------------------------------------------------------------
# Whole-application build
# --------------------------------------------------------------------------

@dataclass
class BuildReport:
    pages: list[CompiledPage]
    skipped_dynamic: list[str]

    @property
    def total_js_bytes(self) -> int:
        return sum(len(p.js or "") for p in self.pages)


def build_static(check_only: bool = False) -> BuildReport:
    """Compile all routes for a static target.

    Fails with a precise report if any route requires a server
    (SPEC 9.8: no hidden server dependency).
    """
    registry = active_registry()
    problems: list[str] = []
    compiled: list[CompiledPage] = []
    for page in registry.pages.values():
        if page.is_dynamic:
            problems.append(
                f"  {page.path}: dynamic route parameters {page.param_names} "
                "require request-time rendering"
            )
            continue
        result = compile_page(page)
        if result.server_actions:
            problems.append(
                f"  {page.path}: calls server actions "
                f"({', '.join(result.server_actions)}) which need a running "
                "Python server"
            )
            continue
        compiled.append(result)
    if problems:
        raise VirelCompileError(
            "This application cannot build as a static site. The following "
            "routes require a server:\n"
            + "\n".join(problems)
            + "\nDeploy with `virel build --target asgi`, or remove the "
            "server dependencies from these routes."
        )
    return BuildReport(pages=compiled, skipped_dynamic=[])


def build_all(dev: bool = False) -> BuildReport:
    """Compile every static-parameter route (ASGI/dev target).

    Dynamic routes are rendered per request by the server.
    """
    registry = active_registry()
    compiled = []
    skipped = []
    for page in registry.pages.values():
        if page.is_dynamic:
            skipped.append(page.path)
            continue
        compiled.append(compile_page(page, dev=dev))
    return BuildReport(pages=compiled, skipped_dynamic=skipped)
