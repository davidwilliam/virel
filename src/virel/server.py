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

function describeNode(node, depth) {
  const pad = "  ".repeat(depth);
  let lines = [];
  if (node.kind === "element") {
    let head = pad + paint(P.dim, "<") + paint(P.tag, node.tag) + paint(P.dim, ">");
    if (node.component) head += "  " + paint(P.comp, node.component);
    if (node.source) head += "  " + paint(P.src, node.source.split("/").pop());
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
    lines.push(pad + paint(P.kw, "island ") + paint(P.expr, node.load));
    (node.children || []).forEach((c) => lines.push(...describeNode(c, depth + 1)));
  } else if (node.kind === "bind_text") {
    lines.push(pad + paint(P.expr, "{ " + node.expr + " }"));
  } else if (node.kind === "text") {
    const text = node.text.trim();
    if (text) lines.push(pad + paint(P.text, JSON.stringify(text.slice(0, 48))));
  } else if (node.kind === "page") {
    (node.children || []).forEach((c) => lines.push(...describeNode(c, depth)));
  }
  return lines;
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
  panel.innerHTML =
    "<div style='display:flex;align-items:center;gap:10px;padding:12px 16px;" +
    "border-bottom:1px solid #2a2b3d;background:#1a1b26'>" +
    "<span style='color:#7aa2f7;font-weight:700'>virel</span>" +
    "<span style='color:" + P.fg + "'>" + escHtml(ir.route) + "</span>" +
    "<span style='color:" + P.dim + "'>render=" + escHtml(ir.render) +
    " &middot; ir v" + escHtml(ir.version) + "</span>" +
    "<span style='flex:1'></span>" +
    "<button id='virel-close' aria-label='Close inspector' style='border:0;" +
    "background:#2a2b3d;color:" + P.fg + ";border-radius:6px;padding:4px 10px;" +
    "cursor:pointer;font:inherit'>Esc</button></div>" +
    "<div style='overflow:auto;padding:4px 16px 24px'>" +
    section("live state") +
    "<pre style='white-space:pre-wrap;margin:0'>" + liveStates() + "</pre>" +
    section("component tree") +
    "<pre style='white-space:pre;margin:0'>" +
    describeNode(ir.tree, 0).join("\\n") + "</pre></div>";
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
        if scope["type"] != "http":
            raise RuntimeError(f"Unsupported ASGI scope type: {scope['type']}")

        path = scope["path"]
        method = scope["method"]
        try:
            await self._dispatch(path, method, scope, receive, send)
        except VirelCompileError as error:
            await self._send_text(send, 500, f"Virel compile error:\n\n{error}",
                                  content_type="text/plain; charset=utf-8")
        except Exception:
            detail = traceback.format_exc() if self.dev else "internal server error"
            await self._send_text(send, 500, detail,
                                  content_type="text/plain; charset=utf-8")

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
            await self._send_text(send, 200, runtime_js(),
                                  content_type="text/javascript; charset=utf-8")
            return
        if path == "/_virel/app.css":
            theme = self.registry.theme or Theme()
            await self._send_text(send, 200, build_stylesheet(theme),
                                  content_type="text/css; charset=utf-8")
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
            await self._send_json(send, 200, result.ir)
            return
        if path.startswith("/_virel/page/") and path.endswith(".js"):
            await self._serve_page_js(path, send)
            return
        if path.startswith("/_virel/action/"):
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
            await self._serve_public(path.removeprefix("/public/"), send)
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
            method=scope.get("method", "GET"),
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
                self._cache_token = token
        cache_key = f"{path}|{locale}"
        if cache_key in self._page_cache:
            return self._page_cache[cache_key]
        matched = self.registry.match_page(path)
        if not matched:
            return None
        page, params = matched
        result = compile_page(page, params=params, dev=self.dev,
                              inline_js=page.is_dynamic, locale=locale)
        self._page_cache[cache_key] = result
        return result

    async def _serve_page(self, path: str, scope: Scope, send: Send) -> None:
        matched = self.registry.match_page(path)
        if not matched:
            await self._send_text(send, 404, f"No route matches {path!r}.")
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
                params[name] = query.get(name, default)
            result = compile_page(page, params=params, dev=self.dev,
                                  inline_js=True, locale=locale)
        else:
            result = self._compiled(path, locale)
            if result.needs_request_render:
                # Server-rendered resources embed data fetched at render
                # time; compile fresh for every request.
                result = compile_page(page, dev=self.dev, inline_js=True,
                                      locale=locale)
        from .security import content_security_policy
        from .theme import google_fonts
        csp = content_security_policy(
            result.inline_scripts,
            google_fonts=bool(google_fonts(self.registry.theme)))
        headers = [(b"content-security-policy", csp.encode("latin-1"))]
        if locale is not None:
            headers.append((b"vary", b"accept-language"))
        await self._send_text(send, 200, result.html,
                              content_type="text/html; charset=utf-8",
                              extra=headers)

    async def _serve_page_js(self, path: str, send: Send) -> None:
        from .i18n import available_locales
        name = path.removeprefix("/_virel/page/").removesuffix(".js")
        locale = None
        slug = name
        if "." in name:
            slug, _, candidate = name.rpartition(".")
            if candidate in available_locales():
                locale = candidate
            else:
                slug = name
        for page in self.registry.pages.values():
            if page.slug == slug and not page.is_dynamic:
                result = self._compiled(page.path, locale)
                if result and result.js:
                    await self._send_text(send, 200, result.js,
                                          content_type="text/javascript; charset=utf-8")
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
        if content_type and not content_type.startswith("application/json"):
            return "server actions require a JSON request body"
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

        try:
            result = action.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            payload = json.dumps({"result": to_jsonable(result)})
        except Exception as error:
            await self._send_json(send, 500, {"error": _safe_message(error, self.dev)})
            return
        await self._send_text(send, 200, payload,
                              content_type="application/json; charset=utf-8")

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
                await send({
                    "type": "http.response.body",
                    "body": str(chunk).encode("utf-8"),
                    "more_body": True,
                })
        except Exception as error:
            message = f"\n[stream error] {_safe_message(error, self.dev)}"
            await send({"type": "http.response.body",
                        "body": message.encode("utf-8"), "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    # -- static assets ------------------------------------------------------------

    async def _serve_public(self, relative: str, send: Send) -> None:
        base = self.public_dir.resolve()
        target = (base / relative).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            await self._send_text(send, 404, "not found")
            return
        content_type = _guess_type(target.name)
        await self._send_bytes(send, 200, target.read_bytes(), content_type)

    # -- helpers ---------------------------------------------------------------

    def _watch_token(self) -> str:
        latest = 0.0
        for directory in self.watch_dirs:
            for path in directory.rglob("*.py"):
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
                    max_body_bytes: int = 1_000_000) -> VirelASGIApp:
    return VirelASGIApp(registry, dev=dev, public_dir=public_dir,
                        watch_dirs=watch_dirs, allowed_origins=allowed_origins,
                        max_body_bytes=max_body_bytes)


# ---------------------------------------------------------------------------
# Built-in development HTTP server (zero dependencies).
# ---------------------------------------------------------------------------

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
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            try:
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass

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
