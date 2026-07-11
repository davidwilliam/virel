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
    # True when the page embeds data fetched at render time (server-rendered
    # resources): it must be compiled per request, never cached or prebuilt.
    needs_request_render: bool = False
    # Exact text content of each inline <script>, for CSP hashes.
    inline_scripts: list[str] = field(default_factory=list)
    # Filename of the external page module (locale-suffixed when the app
    # registers message catalogs).
    js_module: str = ""


def compile_page(page: Page, params: dict[str, Any] | None = None,
                 dev: bool = False, inline_js: bool = False,
                 locale: str | None = None) -> CompiledPage:
    elements._reset_page_modules()
    with TraceContext() as ctx:
        ctx.locale = locale
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
            "resources": [r.to_ir() for r in ctx.resources.values()],
            "tree": root.to_ir(),
        }

        js = _emit_page_js(ctx, emitter, dev=dev)
        actions_used = _actions_in_bindings(emitter.bindings)
        for res in ctx.resources.values():
            if res.action.name not in actions_used:
                actions_used.append(res.action.name)
        needs_request_render = any(
            r.server_render for r in ctx.resources.values())
        render_mode = _resolve_render_mode(page, js, actions_used)
        if needs_request_render:
            render_mode = "server"

        from .registry import active_registry as _registry
        lang = locale or _registry().default_locale
        # Translated reactive strings live in the page module, so localized
        # apps get one module per locale.
        js_module = (f"{page.slug}.{lang}.js" if _registry().catalogs
                     else f"{page.slug}.js")
        html_doc, inline_scripts = _emit_document(
            root, body_html, js_module, js, dev=dev,
            inline_js=inline_js or needs_request_render, lang=lang)
        return CompiledPage(
            route=page.path,
            slug=page.slug,
            title=root.title,
            html=html_doc,
            js=js,
            ir=ir,
            server_actions=actions_used,
            render_mode=render_mode,
            needs_request_render=needs_request_render,
            inline_scripts=inline_scripts,
            js_module=js_module,
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


def _emit_page_js(ctx: TraceContext, emitter: Emitter, dev: bool = False) -> str | None:
    if not ctx.states and not ctx.derived and not emitter.bindings:
        return None
    from .registry import active_registry
    lines = ['import * as $ from "/_virel/runtime.js";']
    for definition in _client_fn_definitions(ctx):
        lines.append(definition)
    # Bindings live inside mount() so client navigation can re-run them
    # against a freshly swapped document; fresh modules mount themselves.
    body = ["const S = {};"]
    for name, state in ctx.states.items():
        body.append(f"S.{name} = $.signal({_js_json(state.initial)});")
    for name, derived in ctx.derived.items():
        body.append(f"S.{name} = $.computed(() => {derived.expr.js()});")
    for res in ctx.resources.values():
        body.append(res.binding_js())
    body.extend(emitter.bindings)
    if active_registry().client_nav:
        body.append("$.router();")
    if dev:
        body.append("window.__virel = { S };")
    lines.append("export function mount() {")
    lines.extend(f"  {line}" for line in body)
    lines.append("}")
    lines.append("mount();")
    return "\n".join(lines) + "\n"


def _js_json(value: Any) -> str:
    """JSON that is safe to embed inside an inline <script> element: a
    literal ``</script>`` or ``<!--`` in the data must not terminate or
    alter the surrounding script context."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e")


def _client_fn_definitions(ctx: TraceContext) -> list[str]:
    """Emit @ui.client functions used by this page, dependencies first."""
    from .registry import active_registry
    registry = active_registry()
    emitted: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        fn = registry.client_functions[name]
        for dep in sorted(fn.deps):
            visit(dep)
        emitted.append(fn.js_definition())

    for name in ctx.client_fns:
        visit(name)
    return emitted


def _emit_document(root: PageNode, body_html: str, js_module: str,
                   js: str | None, dev: bool,
                   inline_js: bool = False,
                   lang: str = "en") -> tuple[str, list[str]]:
    # Applies a stored light/dark preference before first paint so theme
    # switching never flashes. With no stored preference the CSS media
    # query follows the system setting.
    bootstrap_source = (
        '(()=>{try{const t=localStorage.getItem("virel-theme");'
        'if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}'
        "catch{}})()"
    )
    # Every inline script's exact text is tracked so the server can emit
    # a content security policy that allows these scripts by hash and
    # nothing else (SPEC 18.2).
    inline_scripts = [bootstrap_source]
    head = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(root.title)}</title>",
        f"<script>{bootstrap_source}</script>",
        '<link rel="preload" href="/_virel/fonts/InterVariable.woff2" '
        'as="font" type="font/woff2" crossorigin>',
        '<link rel="stylesheet" href="/_virel/app.css">',
    ]
    for name, content in root.meta.items():
        head.append(f'<meta name="{_escape(name)}" content="{_escape(content)}">')
    for module in root.head_modules:
        head.append(f'<script type="module" src="{_escape(module)}"></script>')
    if js is not None:
        if inline_js:
            source = f"\n{js}"
            inline_scripts.append(source)
            head.append(f'<script type="module">{source}</script>')
        else:
            head.append(f'<script type="module" src="/_virel/page/{js_module}"></script>')
    if dev:
        head.append('<script type="module" src="/_virel/dev.js"></script>')

    head_html = "\n    ".join(head)
    document = (
        "<!doctype html>\n"
        f'<html lang="{_escape(lang)}">\n'
        f"  <head>\n    {head_html}\n  </head>\n"
        f"  <body>\n{body_html}\n  </body>\n"
        "</html>\n"
    )
    return document, inline_scripts


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
        result = compile_page(page, dev=dev)
        if result.needs_request_render:
            skipped.append(page.path)
            continue
        compiled.append(result)
    return BuildReport(pages=compiled, skipped_dynamic=skipped)
