"""Server runtime: a standard ASGI application plus a zero-dependency
asyncio HTTP bridge for ``virel dev``.

The ASGI app (``create_asgi_app``) works under uvicorn/hypercorn or mounted
inside an existing ASGI deployment (SPEC 9.4). Server actions are stateless
HTTP endpoints — no per-user server object graph, no sticky sessions
(SPEC 6.8). Streaming actions use plain chunked HTTP.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import traceback
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from .compiler import compile_page
from .expr import VirelCompileError
from .registry import AppRegistry, active_registry
from .theme import Theme, build_stylesheet, runtime_js

DEV_JS = """\
// Virel dev helpers: hot reload plus the page inspector.

let token = null;
async function poll() {
  try {
    const res = await fetch("/_virel/reload-token");
    const next = (await res.json()).token;
    if (token !== null && next !== token) location.reload();
    token = next;
  } catch {}
  setTimeout(poll, 1000);
}
poll();

// Inspector: toggle with the floating button or Alt+V. Shows the compiled
// IR (component tree, states, bindings) plus live signal values.
const btn = document.createElement("button");
btn.textContent = "virel";
btn.setAttribute("aria-label", "Toggle Virel inspector");
btn.style.cssText =
  "position:fixed;bottom:14px;right:14px;z-index:99998;padding:6px 12px;" +
  "font:600 12px ui-monospace,monospace;color:#fff;background:#4f46e5;" +
  "border:0;border-radius:999px;cursor:pointer;opacity:.85";
document.addEventListener("DOMContentLoaded", () => document.body.appendChild(btn));
// Client navigation swaps the body; put the button (and panel state) back.
window.addEventListener("virel:navigate", () => {
  document.body.appendChild(btn);
  if (panel) { panel.remove(); panel = null; }
});

let panel = null;

const P = {
  tag: "#7dcfff", comp: "#bb9af7", src: "#565f89", text: "#9ece6a",
  expr: "#e0af68", kw: "#f7768e", dim: "#565f89", fg: "#c0caf5",
};
const escHtml = (s) => String(s).replace(/[&<>]/g,
  (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"})[c]);
const paint = (color, text) =>
  `<span style="color:${color}">${escHtml(text)}</span>`;

function nodeMeta(node) {
  // Props, reactive dependencies, and hydration boundary, inline.
  let bits = [];
  const props = { ...(node.attrs || {}), ...(node.bound_props || {}) };
  const names = Object.keys(props).filter((k) => k !== "class");
  if (names.length) {
    bits.push(paint(P.dim, names.slice(0, 4).map(
      (k) => k + "=" + String(props[k]).slice(0, 22)).join(" ")));
  }
  if (node.depends_on) {
    bits.push(paint(P.expr, "\\u2192 " + node.depends_on.join(",")));
  }
  return bits.length ? "  " + bits.join("  ") : "";
}

function describeNode(node, depth) {
  const pad = "  ".repeat(depth);
  let lines = [];
  if (node.kind === "element") {
    let head = pad + paint(P.dim, "<") + paint(P.tag, node.tag) + paint(P.dim, ">");
    if (node.component) head += "  " + paint(P.comp, node.component);
    if (node.source) head += "  " + paint(P.src, node.source.split("/").pop());
    head += nodeMeta(node);
    lines.push(head);
    (node.children || []).forEach((c) => lines.push(...describeNode(c, depth + 1)));
  } else if (node.kind === "when") {
    lines.push(pad + paint(P.kw, "when ") + paint(P.expr, node.condition));
    (node.then || []).forEach((c) => lines.push(...describeNode(c, depth + 1)));
    if ((node.otherwise || []).length) {
      lines.push(pad + paint(P.kw, "else"));
      node.otherwise.forEach((c) => lines.push(...describeNode(c, depth + 1)));
    }
  } else if (node.kind === "each") {
    lines.push(pad + paint(P.kw, "each ") + paint(P.expr, node.items));
    (node.template || []).forEach((c) => lines.push(...describeNode(c, depth + 1)));
  } else if (node.kind === "island") {
    lines.push(pad + paint(P.kw, "island ") +
               paint(P.tag, "[hydrate: " + node.load + "]"));
    (node.children || []).forEach((c) => lines.push(...describeNode(c, depth + 1)));
  } else if (node.kind === "bind_text") {
    lines.push(pad + paint(P.expr, "{ " + node.expr + " }") + nodeMeta(node));
  } else if (node.kind === "text") {
    const text = node.text.trim();
    if (text) lines.push(pad + paint(P.text, JSON.stringify(text.slice(0, 48))));
  } else if (node.kind === "page") {
    (node.children || []).forEach((c) => lines.push(...describeNode(c, depth)));
  }
  return lines;
}

function domMapping() {
  // Every reactive binding attaches to a data-v element; show the map.
  const nodes = document.querySelectorAll("[data-v]");
  if (!nodes.length) return paint(P.dim, "(no bound DOM nodes)");
  return Array.from(nodes).slice(0, 40).map((n) =>
    paint(P.comp, "data-v=" + n.getAttribute("data-v")) +
    paint(P.dim, " -> <" + n.tagName.toLowerCase() + ">")).join("\\n");
}

function listBlock(items, empty) {
  if (!items || !items.length) return paint(P.dim, empty);
  return items.join("\\n");
}

function liveStates() {
  const S = window.__virel && window.__virel.S;
  if (!S || !Object.keys(S).length) {
    return paint(P.dim, "(no reactive state on this page)");
  }
  return Object.keys(S)
    .map((k) => paint(P.comp, k) + paint(P.dim, " = ") +
                paint(P.text, JSON.stringify(S[k].get())))
    .join("\\n");
}

function closeInspector() {
  if (panel) { panel.remove(); panel = null; }
}

async function toggleInspector() {
  if (panel) { closeInspector(); return; }
  const res = await fetch(
    "/_virel/ir?path=" + encodeURIComponent(location.pathname));
  if (!res.ok) return;
  const ir = await res.json();
  panel = document.createElement("div");
  panel.style.cssText =
    "position:fixed;top:0;right:0;bottom:0;width:min(720px,94vw);" +
    "z-index:99999;display:flex;flex-direction:column;background:#16161e;" +
    "color:" + P.fg + ";font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;" +
    "border-left:1px solid #2a2b3d;box-shadow:-24px 0 48px rgba(0,0,0,.4)";
  const section = (title) =>
    "<div style='color:" + P.dim + ";text-transform:uppercase;font-size:10.5px;" +
    "letter-spacing:.08em;margin:18px 0 6px'>" + title + "</div>";
  const pre = (content) =>
    "<pre style='white-space:pre-wrap;margin:0'>" + content + "</pre>";
  const resources = (ir.resources || []).map((r) =>
    paint(P.comp, r.name || r.id) + paint(P.dim,
      " server_render=" + !!r.server_render));
  const actions = (ir.actions || []).map((a) =>
    paint(P.comp, a.name) + paint(P.dim,
      (a.streaming ? " streaming" : "") + (a.download ? " download" : "")));
  const derived = (ir.derived || []).map((d) =>
    paint(P.comp, d.name) + paint(P.dim, " = ") + paint(P.expr, d.js));
  const a11y = ir.accessibility && ir.accessibility.warnings || [];
  const a11yText = a11y.length
    ? a11y.map((w) => paint(P.expr, w)).join("\\n")
    : paint(P.text, "no accessibility warnings");
  const tokens = Object.entries(ir.tokens || {}).slice(0, 24).map(
    ([k, v]) => paint(P.comp, k) + paint(P.dim, ": ") + paint(P.text, v));

  panel.innerHTML =
    "<div style='display:flex;align-items:center;gap:10px;padding:12px 16px;" +
    "border-bottom:1px solid #2a2b3d;background:#1a1b26'>" +
    "<span style='color:#7aa2f7;font-weight:700'>virel</span>" +
    "<span style='color:" + P.fg + "'>" + escHtml(ir.route) + "</span>" +
    "<span style='color:" + P.dim + "'>render=" +
    escHtml(ir.render_mode || ir.render) +
    " &middot; ir v" + escHtml(ir.version) + "</span>" +
    "<span style='flex:1'></span>" +
    "<button id='virel-close' aria-label='Close inspector' style='border:0;" +
    "background:#2a2b3d;color:" + P.fg + ";border-radius:6px;padding:4px 10px;" +
    "cursor:pointer;font:inherit'>Esc</button></div>" +
    "<div style='overflow:auto;padding:4px 16px 24px'>" +
    section("component tree (props, source, \\u2192 dependencies)") +
    "<pre style='white-space:pre;margin:0'>" +
    describeNode(ir.tree, 0).join("\\n") + "</pre>" +
    section("live state") + pre(liveStates()) +
    section("derived") + pre(listBlock(derived, "(none)")) +
    section("resources") + pre(listBlock(resources, "(none)")) +
    section("server actions") + pre(listBlock(actions, "(none)")) +
    section("accessibility") + pre(a11yText) +
    section("dom mapping") + pre(domMapping()) +
    section("style tokens") + pre(listBlock(tokens, "(default theme)")) +
    "</div>";
  document.body.appendChild(panel);
  panel.querySelector("#virel-close").addEventListener("click", closeInspector);
}

btn.addEventListener("click", toggleInspector);
document.addEventListener("keydown", (ev) => {
  if (ev.altKey && ev.key.toLowerCase() === "v") toggleInspector();
  if (ev.key === "Escape") closeInspector();
});
"""

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class VirelASGIApp:
    def __init__(self, registry: AppRegistry | None = None, *,
                 dev: bool = False, public_dir: Path | None = None,
                 watch_dirs: list[Path] | None = None,
                 allowed_origins: list[str] | None = None,
                 max_body_bytes: int = 1_000_000) -> None:
        self.registry = registry or active_registry()
        self.dev = dev
        self.public_dir = public_dir
        self.watch_dirs = watch_dirs or []
        # Cross-origin callers must be explicitly allowed; by default only
        # same-origin requests may invoke server actions (CSRF defense).
        self.allowed_origins = allowed_origins or []
        self.max_body_bytes = max_body_bytes
        self._page_cache: dict[str, Any] = {}
        self._cache_token: str | None = None

    # -- ASGI entry ----------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] == "websocket":
            await self._serve_websocket(scope, receive, send)
            return
        if scope["type"] != "http":
            raise RuntimeError(f"Unsupported ASGI scope type: {scope['type']}")

        path = scope["path"]
        method = scope["method"]
        from .context import request_context
        try:
            with request_context():
                await self._dispatch(path, method, scope, receive, send)
        except (ConnectionResetError, BrokenPipeError):
            # The client went away mid-response (closed a live stream,
            # navigated off). Nothing to send to.
            return
        except VirelCompileError as error:
            await self._send_text(send, 500, f"Virel compile error:\n\n{error}",
                                  content_type="text/plain; charset=utf-8")
        except Exception:
            if self.dev:
                await self._send_text(send, 500, traceback.format_exc(),
                                      content_type="text/plain; charset=utf-8")
            else:
                await self._send_text(
                    send, 500,
                    _error_html(500, "Something went wrong",
                                "The error has been logged."),
                    content_type="text/html; charset=utf-8")

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    # -- routing --------------------------------------------------------------

    async def _dispatch(self, path: str, method: str, scope: Scope,
                        receive: Receive, send: Send) -> None:
        if path == "/_virel/runtime.js":
            from .theme import compact
            source = runtime_js() if self.dev else compact(runtime_js())
            await self._send_text(send, 200, source,
                                  content_type="text/javascript; charset=utf-8",
                                  extra=self._asset_cache_headers())
            return
        if path == "/_virel/app.css":
            from .theme import compact
            theme = self.registry.theme or Theme()
            stylesheet = build_stylesheet(theme)
            if not self.dev:
                stylesheet = compact(stylesheet)
            await self._send_text(send, 200, stylesheet,
                                  content_type="text/css; charset=utf-8",
                                  extra=self._asset_cache_headers())
            return
        if path.startswith("/_virel/fonts/"):
            from importlib import resources as _resources
            name = path.removeprefix("/_virel/fonts/")
            if "/" in name or name not in ("InterVariable.woff2",):
                await self._send_text(send, 404, "not found")
                return
            # Single-segment joins only: multi-segment joinpath needs 3.12.
            data = (_resources.files("virel.assets") / "fonts" / name).read_bytes()
            await self._send_bytes(send, 200, data, "font/woff2",
                                   extra=[(b"cache-control",
                                           b"public, max-age=31536000, immutable")])
            return
        if path == "/_virel/dev.js":
            await self._send_text(send, 200, DEV_JS,
                                  content_type="text/javascript; charset=utf-8")
            return
        if path == "/_virel/reload-token":
            await self._send_json(send, 200, {"token": self._watch_token()})
            return
        if path == "/_virel/ir":
            if not self.dev:
                await self._send_json(send, 404, {"error": "IR endpoint is dev-only"})
                return
            query = _parse_query(scope.get("query_string", b""))
            target = query.get("path", "/")
            matched = self.registry.match_page(target)
            if not matched:
                await self._send_json(send, 404, {"error": f"no route for {target!r}"})
                return
            page, params = matched
            result = compile_page(page, params=params or None, dev=True,
                                  inline_js=page.is_dynamic)
            from .plugins import inspector_panels
            payload = dict(result.ir)
            payload["render_mode"] = result.render_mode
            payload["actions"] = [
                {"name": name,
                 "streaming": self.registry.actions[name].stream_response,
                 "download": self.registry.actions[name].download}
                for name in result.server_actions
                if name in self.registry.actions]
            # Style tokens for the inspector's design panel (SPEC 15.3).
            theme = self.registry.theme or Theme()
            import re as _re
            tokens = {}
            for match in _re.finditer(r"(--v-[\w-]+):\s*([^;]+);",
                                      theme.css_tokens()):
                tokens.setdefault(match.group(1), match.group(2).strip())
            payload["tokens"] = tokens
            panels = inspector_panels()
            if panels:
                payload["plugins"] = panels
            await self._send_json(send, 200, payload)
            return
        if path.startswith("/_virel/page/") and path.endswith(".js"):
            await self._serve_page_js(path, send)
            return
        if path.startswith("/_virel/action/"):
            if method == "GET":
                name = path.removeprefix("/_virel/action/")
                candidate = self.registry.actions.get(name)
                if candidate is not None and candidate.stream_response:
                    await self._serve_sse(candidate, scope, send)
                    return
                await self._serve_download(name, scope, send)
                return
            if method != "POST":
                await self._send_json(send, 405, {"error": "actions require POST"})
                return
            rejection = self._reject_cross_site(scope)
            if rejection:
                await self._send_json(send, 403, {"error": rejection})
                return
            await self._serve_action(path.removeprefix("/_virel/action/"),
                                     scope, receive, send)
            return
        if self.public_dir and path.startswith("/public/"):
            await self._serve_static(self.public_dir,
                                     path.removeprefix("/public/"),
                                     scope, send)
            return
        for prefix, directory in self.registry.static_mounts.items():
            if path.startswith(prefix + "/"):
                await self._serve_static(directory,
                                         path.removeprefix(prefix + "/"),
                                         scope, send)
                return
        if method not in ("GET", "HEAD"):
            await self._send_text(send, 405, "method not allowed")
            return
        await self._serve_page(path, scope, send)

    # -- pages ----------------------------------------------------------------

    def _request(self, scope: Scope) -> "Any":
        from http.cookies import SimpleCookie
        from .registry import Request
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        cookies: dict[str, str] = {}
        if "cookie" in headers:
            jar = SimpleCookie()
            try:
                jar.load(headers["cookie"])
                cookies = {key: morsel.value for key, morsel in jar.items()}
            except Exception:
                cookies = {}
        return Request(
            method=scope.get("method", "WEBSOCKET"
                             if scope.get("type") == "websocket" else "GET"),
            path=scope.get("path", "/"),
            headers=headers,
            query=_parse_query(scope.get("query_string", b"")),
            cookies=cookies,
        )

    async def _run_guards(self, scope: Scope, specific: Any) -> Any:
        """Evaluate the default guard then the route guard. Returns None
        to allow, or a Redirect/Deny decision."""
        from .registry import Deny, Redirect
        guards = [g for g in (self.registry.default_guard, specific) if g]
        if not guards:
            return None
        request = self._request(scope)
        for guard in guards:
            decision = guard(request)
            if inspect.isawaitable(decision):
                decision = await decision
            if decision is None:
                continue
            if isinstance(decision, (Redirect, Deny)):
                return decision
            raise VirelCompileError(
                f"Guard {guard.__name__!r} returned {decision!r}; guards "
                "must return None, ui.redirect(path), or ui.deny()."
            )
        return None

    def _negotiate_locale(self, scope: Scope) -> str | None:
        """Pick the locale for a request: ?lang= override, then
        Accept-Language, then the default. None when the app registers no
        catalogs (single-locale fast path)."""
        from .i18n import available_locales
        if not self.registry.catalogs:
            return None
        available = available_locales()
        query = _parse_query(scope.get("query_string", b""))
        override = query.get("lang")
        if override in available:
            return override
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        ranges: list[tuple[float, str]] = []
        for part in headers.get("accept-language", "").split(","):
            piece = part.strip()
            if not piece:
                continue
            quality = 1.0
            if ";q=" in piece:
                piece, _, q = piece.partition(";q=")
                try:
                    quality = float(q)
                except ValueError:
                    quality = 0.0
            ranges.append((quality, piece.strip().lower()))
        for _, tag in sorted(ranges, reverse=True):
            if tag in available:
                return tag
            primary = tag.split("-")[0]
            if primary in available:
                return primary
        return self.registry.default_locale

    def _compiled(self, path: str, locale: str | None = None) -> Any | None:
        """Compile (and cache) the page for a concrete request path."""
        if self.dev:
            token = self._watch_token()
            if token != self._cache_token:
                self._page_cache.clear()
                for build_fn in self.registry.build_functions.values():
                    build_fn.invalidate()
                self._cache_token = token
        cache_key = f"{path}|{locale}"
        if cache_key in self._page_cache:
            return self._page_cache[cache_key]
        matched = self.registry.match_page(path)
        if not matched:
            return None
        page, params = matched
        result = compile_page(page, params=params, dev=self.dev,
                              inline_js=page.is_dynamic, locale=locale,
                              hashed=not self.dev)
        self._page_cache[cache_key] = result
        return result

    async def _serve_page(self, path: str, scope: Scope, send: Send) -> None:
        matched = self.registry.match_page(path)
        if not matched:
            await self._send_text(send, 404,
                                  _error_html(404, "Page not found",
                                              "The address may have changed."),
                                  content_type="text/html; charset=utf-8")
            return
        page, params = matched
        from .registry import Deny, Redirect
        decision = await self._run_guards(scope, page.guard)
        if isinstance(decision, Redirect):
            await send({"type": "http.response.start", "status": 303,
                        "headers": _headers("text/plain; charset=utf-8",
                                            length=0,
                                            extra=[(b"location",
                                                    decision.to.encode("latin-1"))])})
            await send({"type": "http.response.body", "body": b""})
            return
        if isinstance(decision, Deny):
            await self._send_text(send, decision.status, decision.message)
            return
        locale = self._negotiate_locale(scope)
        if page.is_dynamic or page.query_params:
            query = _parse_query(scope.get("query_string", b""))
            for name, default in page.query_params.items():
                params[name] = _convert_query(query.get(name),
                                              page.query_types.get(name, str),
                                              default)
            result = compile_page(page, params=params, dev=self.dev,
                                  inline_js=True, locale=locale,
                                  hashed=not self.dev)
        else:
            result = self._compiled(path, locale)
            if result.needs_request_render:
                # Server-rendered resources embed data fetched at render
                # time; compile fresh for every request.
                result = compile_page(page, dev=self.dev, inline_js=True,
                                      locale=locale, hashed=not self.dev)
        from .security import content_security_policy
        from .theme import google_fonts
        csp = content_security_policy(
            result.inline_scripts,
            google_fonts=bool(google_fonts(self.registry.theme)))
        headers = [(b"content-security-policy", csp.encode("latin-1"))]
        if locale is not None:
            headers.append((b"vary", b"accept-language"))
        if result.streamed_resources:
            await self._serve_streamed_page(result, headers, send)
            return
        await self._send_text(send, 200, result.html,
                              content_type="text/html; charset=utf-8",
                              extra=headers)

    async def _serve_streamed_page(self, result: Any,
                                   headers: list, send: Send) -> None:
        """Progressive rendering (SPEC 9.6 stream mode): flush the shell
        immediately, then stream each server-rendered resource's data as an
        inline JSON data block the runtime reads at mount."""
        from .compiler import _js_json
        from .registry import to_jsonable
        prefix, _, _closing = result.html.rpartition("</body>")
        await send({"type": "http.response.start", "status": 200,
                    "headers": _headers("text/html; charset=utf-8",
                                        extra=headers)})
        await send({"type": "http.response.body",
                    "body": prefix.encode("utf-8"), "more_body": True})
        for entry in result.streamed_resources:
            action = self.registry.actions[entry["action"]]
            try:
                kwargs = action.prepare(dict(entry["args"]))
                value = action.fn(**kwargs)
                if inspect.isawaitable(value):
                    value = await value
                payload = {"value": to_jsonable(value)}
            except Exception as error:
                payload = {"error": _safe_message(error, self.dev)}
            block = (f'<script type="application/json" '
                     f'data-virel-stream="{entry["id"]}">'
                     f"{_js_json(payload)}</script>")
            await send({"type": "http.response.body",
                        "body": block.encode("utf-8"), "more_body": True})
        await send({"type": "http.response.body",
                    "body": b"</body>\n</html>\n", "more_body": False})

    def _asset_cache_headers(self) -> list[tuple[bytes, bytes]]:
        if self.dev:
            return [(b"cache-control", b"no-store")]
        # Production URLs are content-versioned, so far-future caching is
        # safe (SPEC 9.1 asset hashing).
        return [(b"cache-control", b"public, max-age=31536000, immutable")]

    async def _serve_page_js(self, path: str, send: Send) -> None:
        import re as _re
        from .i18n import available_locales
        name = path.removeprefix("/_virel/page/").removesuffix(".js")
        # Names look like slug[.locale][.hash8]; strip from the right.
        parts = name.split(".")
        if len(parts) > 1 and _re.fullmatch(r"[0-9a-f]{8}", parts[-1]):
            parts.pop()
        locale = None
        if len(parts) > 1 and parts[-1] in available_locales():
            locale = parts.pop()
        slug = ".".join(parts)
        for page in self.registry.pages.values():
            if page.slug == slug and not page.is_dynamic:
                result = self._compiled(page.path, locale)
                if result and result.js:
                    await self._send_text(send, 200, result.js,
                                          content_type="text/javascript; charset=utf-8",
                                          extra=self._asset_cache_headers())
                    return
        await self._send_text(send, 404, f"No page module {name!r}.")

    # -- server actions ---------------------------------------------------------

    def _reject_cross_site(self, scope: Scope) -> str | None:
        """Stateless CSRF defense (SPEC 18.2): server actions accept
        same-origin requests, explicitly allowed origins, and requests
        with no browser origin metadata (non-browser clients)."""
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site == "cross-site":
            return "cross-site requests to server actions are not allowed"
        origin = headers.get("origin")
        if origin and origin != "null":
            from .security import same_origin
            if not same_origin(origin, headers.get("host", ""),
                               self.allowed_origins):
                return f"origin {origin!r} is not allowed"
        elif origin == "null":
            return "requests from an opaque origin are not allowed"
        content_type = headers.get("content-type", "")
        if content_type and not (
                content_type.startswith("application/json")
                or content_type.startswith("multipart/form-data")):
            return "server actions require a JSON or multipart request body"
        return None

    async def _serve_action(self, name: str, scope: Scope,
                            receive: Receive, send: Send) -> None:
        action = self.registry.actions.get(name)
        if action is None:
            await self._send_json(send, 404, {"error": f"unknown server action {name!r}"})
            return

        from .registry import Deny, Redirect
        decision = await self._run_guards(scope, action.guard)
        if isinstance(decision, Redirect):
            # Redirects are meaningless for JSON calls; treat as
            # authentication required.
            await self._send_json(send, 401, {"error": "authentication required",
                                              "redirect": decision.to})
            return
        if isinstance(decision, Deny):
            await self._send_json(send, decision.status,
                                  {"error": decision.message})
            return

        try:
            body = await _read_body(receive, self.max_body_bytes)
        except _BodyTooLarge:
            await self._send_json(send, 413, {
                "error": f"request body exceeds {self.max_body_bytes} bytes"})
            return

        request_headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                           for k, v in scope.get("headers", [])}
        if request_headers.get("content-type", "").startswith("multipart/form-data"):
            await self._serve_upload(action, body,
                                     request_headers["content-type"], send)
            return
        try:
            args = json.loads(body or b"{}")
            if not isinstance(args, dict):
                raise ValueError("body must be a JSON object")
        except ValueError as error:
            await self._send_json(send, 400, {"error": f"invalid request body: {error}"})
            return

        # Schema validation on every server action (SPEC 18.2): only declared
        # parameters, required parameters present, model parameters validated.
        # JSON only — never pickle (SPEC 18.3).
        from .registry import ActionArgumentError, ActionValidationError, to_jsonable
        try:
            kwargs = action.prepare(args)
        except ActionArgumentError as error:
            await self._send_json(send, 400, {"error": str(error)})
            return
        except ActionValidationError as error:
            await self._send_json(send, 400, {
                "error": "validation failed",
                "field_errors": error.field_errors,
            })
            return

        if action.stream_response:
            await self._stream_action(action, kwargs, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        idempotency_key = headers.get("idempotency-key")
        if action.idempotent and idempotency_key:
            replay = _idempotency_lookup(action.name, idempotency_key)
            if replay is not None:
                await self._send_text(send, 200, replay,
                                      content_type="application/json; charset=utf-8",
                                      extra=_action_headers(0.0, replayed=True))
                return

        import time
        import uuid
        started = time.perf_counter()
        try:
            result = action.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            payload = json.dumps({"result": to_jsonable(result)})
        except Exception as error:
            await self._send_json(send, 500, {"error": _safe_message(error, self.dev)})
            return
        duration = time.perf_counter() - started
        if action.idempotent and idempotency_key:
            _idempotency_store(action.name, idempotency_key, payload)
        await self._send_text(send, 200, payload,
                              content_type="application/json; charset=utf-8",
                              extra=_action_headers(duration))

    async def _serve_upload(self, action: Any, body: bytes,
                            content_type: str, send: Send) -> None:
        import json as _json
        from .registry import (ActionArgumentError, ActionValidationError,
                               to_jsonable)
        from .uploads import MultipartError, file_params, parse_multipart
        params = file_params(action)
        if not params:
            await self._send_json(send, 400, {
                "error": f"action {action.name!r} does not accept file uploads"})
            return
        try:
            fields, files = parse_multipart(body, content_type)
        except MultipartError as error:
            await self._send_json(send, 400, {"error": str(error)})
            return
        try:
            args = _json.loads(fields.get("__args", "{}"))
            if not isinstance(args, dict):
                raise ValueError("__args must be a JSON object")
        except ValueError as error:
            await self._send_json(send, 400, {"error": f"invalid arguments: {error}"})
            return
        try:
            kwargs = action.prepare(args, provided=set(params))
        except ActionArgumentError as error:
            await self._send_json(send, 400, {"error": str(error)})
            return
        except ActionValidationError as error:
            await self._send_json(send, 400, {
                "error": "validation failed",
                "field_errors": error.field_errors})
            return
        for name, multiple in params.items():
            received = files.get(name, [])
            if not received:
                if name in kwargs:
                    continue
                await self._send_json(send, 400, {
                    "error": f"missing file(s) for parameter {name!r}"})
                return
            kwargs[name] = received if multiple else received[0]
        try:
            result = action.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as error:
            await self._send_json(send, 500,
                                  {"error": _safe_message(error, self.dev)})
            return
        await self._send_json(send, 200, {"result": to_jsonable(result)})

    async def _serve_download(self, name: str, scope: Scope, send: Send) -> None:
        from .uploads import FileDownload, sanitize_filename
        action = self.registry.actions.get(name)
        if action is None or not action.download:
            await self._send_text(send, 404, "not found")
            return
        from .registry import Deny, Redirect
        decision = await self._run_guards(scope, action.guard)
        if isinstance(decision, Redirect):
            await self._send_text(send, 401, "authentication required")
            return
        if isinstance(decision, Deny):
            await self._send_text(send, decision.status, decision.message)
            return
        raw = _parse_query(scope.get("query_string", b""))
        hints = action.type_hints()
        valid = set(action.signature.parameters)
        args: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in valid:
                continue
            annotation = hints.get(key)
            try:
                if annotation is int:
                    args[key] = int(value)
                elif annotation is float:
                    args[key] = float(value)
                elif annotation is bool:
                    args[key] = value in ("1", "true", "yes")
                else:
                    args[key] = value
            except ValueError:
                await self._send_text(send, 400, f"invalid value for {key!r}")
                return
        from .registry import ActionArgumentError
        try:
            kwargs = action.prepare(args)
            result = action.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        except ActionArgumentError as error:
            await self._send_text(send, 400, str(error))
            return
        except Exception as error:
            await self._send_text(send, 500, _safe_message(error, self.dev))
            return
        if not isinstance(result, FileDownload):
            await self._send_text(send, 500,
                                  "download actions must return ui.FileDownload")
            return
        filename = sanitize_filename(result.filename)
        await self._send_bytes(
            send, 200, result.body(), result.content_type,
            extra=[(b"content-disposition",
                    f'attachment; filename="{filename}"'.encode("latin-1"))])

    async def _serve_websocket(self, scope: Scope, receive: Receive,
                               send: Send) -> None:
        """Bidirectional channels (SPEC 9.5). Browsers do not enforce the
        same-origin policy on WebSocket, so the Origin header is validated
        before accepting (cross-site hijacking protection)."""
        from .channels import Channel, ChannelClosed
        path = scope.get("path", "")
        handler = None
        if path.startswith("/_virel/channel/"):
            handler = self.registry.channels.get(
                path.removeprefix("/_virel/channel/"))
        message = await receive()
        if message["type"] != "websocket.connect" or handler is None:
            await send({"type": "websocket.close", "code": 4404})
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        origin = headers.get("origin")
        if origin and origin != "null":
            from .security import same_origin
            if not same_origin(origin, headers.get("host", ""),
                               self.allowed_origins):
                await send({"type": "websocket.close", "code": 4403})
                return
        elif origin == "null":
            await send({"type": "websocket.close", "code": 4403})
            return

        from .registry import Deny, Redirect
        decision = await self._run_guards(scope, handler.guard)
        if isinstance(decision, (Redirect, Deny)):
            await send({"type": "websocket.close", "code": 4401})
            return

        await send({"type": "websocket.accept"})
        channel = Channel(receive, send)
        try:
            await handler.fn(channel)
        except ChannelClosed:
            return
        except Exception:
            if self.dev:
                traceback.print_exc()
        try:
            await send({"type": "websocket.close", "code": 1000})
        except Exception:
            pass

    async def _serve_sse(self, action: Any, scope: Scope, send: Send) -> None:
        """One-way live updates over server-sent events (SPEC 9.5). A
        read-only GET: guards run, arguments come typed from the query."""
        from .registry import ActionArgumentError, Deny, Redirect, to_jsonable
        decision = await self._run_guards(scope, action.guard)
        if isinstance(decision, (Redirect, Deny)):
            status = 401 if isinstance(decision, Redirect) else decision.status
            await self._send_text(send, status, "not authorized")
            return
        raw = _parse_query(scope.get("query_string", b""))
        hints = action.type_hints()
        valid = set(action.signature.parameters)
        args: dict[str, Any] = {}
        for key, value in raw.items():
            if key in valid:
                args[key] = _convert_query(value, hints.get(key, str), value)
        try:
            kwargs = action.prepare(args)
        except ActionArgumentError as error:
            await self._send_text(send, 400, str(error))
            return
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": _headers("text/event-stream; charset=utf-8", extra=[
                (b"cache-control", b"no-store"),
                (b"x-accel-buffering", b"no"),
            ]),
        })
        iterator = _iterate_chunks(action.fn(**kwargs))
        try:
            async for chunk in iterator:
                if isinstance(chunk, (dict, list)):
                    payload = json.dumps(to_jsonable(chunk))
                else:
                    payload = str(chunk)
                lines = "".join(f"data: {line}\n"
                                for line in payload.split("\n"))
                await send({"type": "http.response.body",
                            "body": (lines + "\n").encode("utf-8"),
                            "more_body": True})
            # A finished stream ends cleanly: the runtime closes the
            # EventSource instead of letting it reconnect forever.
            await send({"type": "http.response.body",
                        "body": b"event: done\ndata: \n\n",
                        "more_body": True})
        except (ConnectionResetError, BrokenPipeError):
            await iterator.aclose()
            return
        except Exception as error:
            message = _safe_message(error, self.dev).replace("\n", " ")
            await send({"type": "http.response.body",
                        "body": f"event: error\ndata: {message}\n\n".encode("utf-8"),
                        "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def _stream_action(self, action: Any, args: dict[str, Any], send: Send) -> None:
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": _headers("text/plain; charset=utf-8", extra=[
                (b"x-content-type-options", b"nosniff"),
                (b"cache-control", b"no-store"),
            ]),
        })
        try:
            async for chunk in _iterate_chunks(action.fn(**args)):
                if isinstance(chunk, (dict, list)):
                    from .registry import to_jsonable
                    encoded = json.dumps(to_jsonable(chunk)) + "\n"
                else:
                    encoded = str(chunk)
                await send({
                    "type": "http.response.body",
                    "body": encoded.encode("utf-8"),
                    "more_body": True,
                })
        except Exception as error:
            message = f"\n[stream error] {_safe_message(error, self.dev)}"
            await send({"type": "http.response.body",
                        "body": message.encode("utf-8"), "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    # -- static assets ------------------------------------------------------------

    async def _serve_static(self, base_dir: Path, relative: str, scope: Scope,
                            send: Send) -> None:
        base = base_dir.resolve()
        target = (base / relative).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            await self._send_text(send, 404, "not found")
            return
        content_type = _guess_type(target.name)
        # Static files are not content-versioned, so browsers must never hold
        # a stale copy: dev disables caching outright, production forces a
        # revalidation round-trip answered by the ETag.
        stat = target.stat()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.dev:
            extra = [(b"cache-control", b"no-store")]
        else:
            extra = [(b"cache-control", b"no-cache"), (b"etag", etag.encode())]
            for name, value in scope.get("headers", []):
                if name == b"if-none-match" and value.decode("latin-1") == etag:
                    await send({"type": "http.response.start", "status": 304,
                                "headers": extra})
                    await send({"type": "http.response.body", "body": b""})
                    return
        await self._send_bytes(send, 200, target.read_bytes(), content_type,
                               extra=extra)

    # -- helpers ---------------------------------------------------------------

    def _watch_token(self) -> str:
        latest = 0.0
        for directory in self.watch_dirs:
            for path in directory.rglob("*.py"):
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
        # Static assets are part of the page too; a new or edited public file
        # must trigger the same dev reload as a code change.
        asset_dirs = list(self.registry.static_mounts.values())
        if self.public_dir:
            asset_dirs.append(self.public_dir)
        for directory in asset_dirs:
            if not directory.is_dir():
                continue
            for path in directory.rglob("*"):
                try:
                    latest = max(latest, path.stat().st_mtime)
                except OSError:
                    continue
        return str(latest)

    async def _send_text(self, send: Send, status: int, text: str,
                         content_type: str = "text/plain; charset=utf-8",
                         extra: list[tuple[bytes, bytes]] | None = None) -> None:
        await self._send_bytes(send, status, text.encode("utf-8"), content_type,
                               extra=extra)

    async def _send_json(self, send: Send, status: int, payload: dict[str, Any]) -> None:
        await self._send_bytes(send, status, json.dumps(payload).encode("utf-8"),
                               "application/json; charset=utf-8")

    async def _send_bytes(self, send: Send, status: int, body: bytes,
                          content_type: str,
                          extra: list[tuple[bytes, bytes]] | None = None) -> None:
        await send({"type": "http.response.start", "status": status,
                    "headers": _headers(content_type, length=len(body),
                                        extra=extra)})
        await send({"type": "http.response.body", "body": body})


def _headers(content_type: str, length: int | None = None,
             extra: list[tuple[bytes, bytes]] | None = None) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"content-type", content_type.encode("latin-1")),
        # Security headers by default (SPEC 18.2)
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"cross-origin-opener-policy", b"same-origin"),
        (b"cross-origin-resource-policy", b"same-origin"),
    ]
    if length is not None:
        headers.append((b"content-length", str(length).encode("latin-1")))
    if extra:
        headers.extend(extra)
    return headers


async def _iterate_chunks(result: Any) -> AsyncIterator[Any]:
    if inspect.isasyncgen(result):
        async for chunk in result:
            yield chunk
    elif inspect.isgenerator(result):
        for chunk in result:
            yield chunk
            await asyncio.sleep(0)
    else:
        raise TypeError("streaming action must return a generator")


# Idempotency replay: bounded per-process store. Multi-process
# deployments should back this with a shared cache; the contract is the
# HTTP header, not this store.
_IDEMPOTENCY_MAX = 512
_idempotency_cache: "dict[tuple[str, str], str]" = {}


def _idempotency_lookup(action: str, key: str) -> str | None:
    return _idempotency_cache.get((action, key))


def _idempotency_store(action: str, key: str, payload: str) -> None:
    if len(_idempotency_cache) >= _IDEMPOTENCY_MAX:
        _idempotency_cache.pop(next(iter(_idempotency_cache)))
    _idempotency_cache[(action, key)] = payload


def _action_headers(duration: float,
                    replayed: bool = False) -> list[tuple[bytes, bytes]]:
    import uuid
    headers = [
        (b"x-request-id", uuid.uuid4().hex.encode("latin-1")),
        (b"server-timing",
         f"action;dur={duration * 1000:.1f}".encode("latin-1")),
    ]
    if replayed:
        headers.append((b"idempotency-replayed", b"true"))
    return headers


class _BodyTooLarge(Exception):
    pass


async def _read_body(receive: Receive, limit: int | None = None) -> bytes:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if limit is not None and len(body) > limit:
            raise _BodyTooLarge
        if not message.get("more_body"):
            return body


def _parse_query(raw: bytes) -> dict[str, str]:
    from urllib.parse import parse_qsl
    return dict(parse_qsl(raw.decode("latin-1")))


def _convert_query(raw: str | None, annotation: type, default: Any) -> Any:
    """Typed query parameters (SPEC 8.10): convert to the annotated type,
    falling back to the declared default on absent or invalid values."""
    if raw is None:
        return default
    try:
        if annotation is int:
            return int(raw)
        if annotation is float:
            return float(raw)
        if annotation is bool:
            return raw in ("1", "true", "yes", "on")
    except ValueError:
        return default
    return raw


def _error_html(status: int, title: str, detail: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{status} {title}</title>"
        "<style>body{font-family:ui-sans-serif,system-ui,sans-serif;"
        "display:grid;place-items:center;min-height:100vh;margin:0;"
        "background:#f7f7f9;color:#16181d}"
        "@media(prefers-color-scheme:dark){body{background:#0e0f13;"
        "color:#ecedf1}}"
        "main{text-align:center;padding:2rem}"
        "h1{font-size:4rem;margin:0;opacity:.25}"
        "p{margin:.75rem 0 0;font-size:1.05rem}</style></head>"
        f"<body><main><h1>{status}</h1><p>{title}</p>"
        f"<p style=\"opacity:.6;font-size:.9rem\">{detail}</p>"
        "</main></body></html>"
    )


def _safe_message(error: Exception, dev: bool) -> str:
    if dev:
        return f"{type(error).__name__}: {error}"
    return "The server action failed."


def _guess_type(name: str) -> str:
    import mimetypes
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def create_asgi_app(registry: AppRegistry | None = None, *, dev: bool = False,
                    public_dir: Path | None = None,
                    watch_dirs: list[Path] | None = None,
                    allowed_origins: list[str] | None = None,
                    max_body_bytes: int = 1_000_000,
                    middleware: list | None = None):
    app: Any = VirelASGIApp(registry, dev=dev, public_dir=public_dir,
                            watch_dirs=watch_dirs,
                            allowed_origins=allowed_origins,
                            max_body_bytes=max_body_bytes)
    # Registry middleware first (outermost), then call-site middleware.
    wrappers = list((registry or active_registry()).middleware)
    wrappers.extend(middleware or [])
    for wrapper in reversed(wrappers):
        app = wrapper(app)
    return app


# ---------------------------------------------------------------------------
# Built-in development HTTP server (zero dependencies).
# ---------------------------------------------------------------------------

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_accept_key(client_key: str) -> str:
    import base64
    import hashlib
    digest = hashlib.sha1((client_key + _WS_GUID).encode("latin-1")).digest()
    return base64.b64encode(digest).decode("latin-1")


def _ws_encode_frame(opcode: int, payload: bytes) -> bytes:
    """Server-to-client frame (unmasked, FIN set)."""
    header = bytes([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header += bytes([length])
    elif length < 65536:
        header += bytes([126]) + length.to_bytes(2, "big")
    else:
        header += bytes([127]) + length.to_bytes(8, "big")
    return header + payload


async def _ws_read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    """Read one client frame; client frames must be masked (RFC 6455)."""
    first = await reader.readexactly(2)
    opcode = first[0] & 0x0F
    masked = first[1] & 0x80
    length = first[1] & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    if length > 1_000_000:
        raise ValueError("frame too large")
    if not masked:
        raise ValueError("client frames must be masked")
    mask = await reader.readexactly(4)
    data = bytearray(await reader.readexactly(length))
    for index in range(length):
        data[index] ^= mask[index % 4]
    return opcode, bytes(data)


class DevHTTPServer:
    """Minimal HTTP/1.1 bridge onto the ASGI app.

    One request per connection (``Connection: close``); streamed response
    bodies are written as they are produced and terminated by close. This
    keeps the bridge tiny — production deployments use a real ASGI server.
    """

    def __init__(self, app: VirelASGIApp, host: str = "127.0.0.1", port: int = 8000) -> None:
        self.app = app
        self.host = host
        self.port = port

    async def handle(self, reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            try:
                method, target, _version = request_line.decode("latin-1").split()
            except ValueError:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                return

            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                key, _, value = line.decode("latin-1").partition(":")
                headers[key.strip().lower()] = value.strip()

            body = b""
            length = int(headers.get("content-length", "0") or "0")
            if length:
                body = await reader.readexactly(length)

            from urllib.parse import unquote
            path, _, query = target.partition("?")

            if headers.get("upgrade", "").lower() == "websocket":
                await self._handle_websocket(reader, writer, method,
                                             unquote(path), query, headers)
                return

            scope = {
                "type": "http",
                "http_version": "1.1",
                "method": method,
                "path": unquote(path),
                "query_string": query.encode("latin-1"),
                "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            }

            received = False

            async def receive() -> dict[str, Any]:
                nonlocal received
                if received:
                    await asyncio.sleep(3600)
                received = True
                return {"type": "http.request", "body": body, "more_body": False}

            started = False

            async def send(message: dict[str, Any]) -> None:
                nonlocal started
                if message["type"] == "http.response.start":
                    status = message["status"]
                    lines = [f"HTTP/1.1 {status} {_reason(status)}".encode()]
                    for name, value in message.get("headers", []):
                        lines.append(name + b": " + value)
                    lines.append(b"connection: close")
                    writer.write(b"\r\n".join(lines) + b"\r\n\r\n")
                    started = True
                elif message["type"] == "http.response.body":
                    writer.write(message.get("body", b""))
                    await writer.drain()

            await self.app(scope, receive, send)
            if not started:
                writer.write(b"HTTP/1.1 500 Internal Server Error\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionResetError,
                BrokenPipeError):
            pass
        finally:
            try:
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass

    async def _handle_websocket(self, reader, writer, method, path, query,
                                headers) -> None:
        key = headers.get("sec-websocket-key")
        if method != "GET" or not key:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        scope = {
            "type": "websocket",
            "path": path,
            "query_string": query.encode("latin-1"),
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        }
        queue: asyncio.Queue = asyncio.Queue()
        await queue.put({"type": "websocket.connect"})
        accepted = False
        closed = False

        async def receive():
            return await queue.get()

        async def send(message):
            nonlocal accepted, closed
            if message["type"] == "websocket.accept":
                writer.write(
                    b"HTTP/1.1 101 Switching Protocols\r\n"
                    b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    b"Sec-WebSocket-Accept: "
                    + _ws_accept_key(key).encode("latin-1") + b"\r\n\r\n")
                await writer.drain()
                accepted = True
            elif message["type"] == "websocket.send":
                payload = message.get("text", "").encode("utf-8")
                writer.write(_ws_encode_frame(0x1, payload))
                await writer.drain()
            elif message["type"] == "websocket.close":
                if not accepted:
                    writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                else:
                    writer.write(_ws_encode_frame(
                        0x8, message.get("code", 1000).to_bytes(2, "big")))
                await writer.drain()
                closed = True

        async def pump_frames():
            try:
                while not closed:
                    opcode, payload = await _ws_read_frame(reader)
                    if opcode == 0x8:  # close
                        await queue.put({"type": "websocket.disconnect"})
                        return
                    if opcode == 0x9:  # ping -> pong
                        writer.write(_ws_encode_frame(0xA, payload))
                        await writer.drain()
                        continue
                    if opcode in (0x1, 0x2):
                        await queue.put({"type": "websocket.receive",
                                         "text": payload.decode("utf-8",
                                                                "replace")})
            except (asyncio.IncompleteReadError, ValueError,
                    ConnectionResetError):
                await queue.put({"type": "websocket.disconnect"})

        pump = asyncio.create_task(pump_frames())
        try:
            await self.app(scope, receive, send)
        finally:
            pump.cancel()

    async def serve(self) -> None:
        server = await asyncio.start_server(self.handle, self.host, self.port)
        async with server:
            await server.serve_forever()

    def run(self) -> None:
        asyncio.run(self.serve())


def _reason(status: int) -> str:
    return {
        200: "OK", 400: "Bad Request", 404: "Not Found",
        405: "Method Not Allowed", 500: "Internal Server Error",
    }.get(status, "OK")
