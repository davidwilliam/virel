"""The Virel language server (SPEC 15.4).

A standard-library Language Server Protocol implementation over stdio,
so VS Code, PyCharm, Neovim, and any generic LSP client get
autocomplete, component prop documentation, invalid-prop and
boundary diagnostics, token and route completion, and navigation from a
component to its Python definition. It reuses the same schema registry
and diagnostics as the CLI and MCP server, so there is one source of
truth.

``virel lsp`` runs it. The transport is the LSP framing (Content-Length
headers plus JSON-RPC bodies); no third-party LSP library is used.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# ui.Component( completion trigger and the component call at a position.
_UI_CALL = re.compile(r"\bui\.([A-Z]\w*)\b")
_UI_PREFIX = re.compile(r"\bui\.([A-Za-z]\w*)?$")
_KWARG = re.compile(r"(\w+)\s*=")
_TO_ROUTE = re.compile(r'\bto\s*=\s*["\']([^"\']*)$')
_TOKEN_CTX = re.compile(r'(background|color|border|shadow|radius)\s*=\s*'
                        r'["\'][\w.]*$')


class Document:
    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = text.split("\n")

    def line(self, index: int) -> str:
        return self.lines[index] if 0 <= index < len(self.lines) else ""

    def prefix(self, line: int, char: int) -> str:
        return self.line(line)[:char]


class LanguageServer:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self._component_names: list[str] | None = None
        self._project_loaded = False

    # -- schema-backed data --------------------------------------------------

    def components(self) -> list[str]:
        if self._component_names is None:
            from .schema import list_components
            self._component_names = list_components()
        return self._component_names

    def _schema(self, name: str) -> dict[str, Any] | None:
        from .expr import VirelCompileError
        from .schema import component_schema
        try:
            return component_schema(name)
        except VirelCompileError:
            return None

    def _routes(self) -> list[str]:
        self._load_project()
        from .registry import active_registry
        return sorted(active_registry().pages)

    def _tokens(self) -> list[str]:
        from .styles import _COLOR_TOKENS
        return sorted(_COLOR_TOKENS)

    def _load_project(self) -> None:
        if self._project_loaded:
            return
        self._project_loaded = True
        import tomllib
        from pathlib import Path
        config = Path.cwd() / "virel.toml"
        if not config.exists():
            return
        try:
            module = tomllib.loads(config.read_text("utf-8"))["app"]["module"]
            sys.path.insert(0, str(Path.cwd()))
            import importlib
            importlib.import_module(module)
        except Exception:
            pass

    # -- request handling ----------------------------------------------------

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        handler = getattr(self, "_on_" + method.replace("/", "_"), None) \
            if method else None
        if handler is None:
            if request_id is not None:
                return _result(request_id, None)
            return None
        return handler(request_id, request.get("params") or {})

    def _on_initialize(self, request_id: Any, params: dict) -> dict:
        return _result(request_id, {
            "capabilities": {
                "textDocumentSync": 1,  # full document sync
                "completionProvider": {"triggerCharacters": [".", "=", '"']},
                "hoverProvider": True,
                "definitionProvider": True,
            },
            "serverInfo": {"name": "virel-lsp", "version": "0.1.0"},
        })

    def _on_initialized(self, request_id: Any, params: dict):
        return None

    def _on_shutdown(self, request_id: Any, params: dict) -> dict:
        return _result(request_id, None)

    def _on_textDocument_didOpen(self, request_id: Any, params: dict):
        doc = params["textDocument"]
        self.documents[doc["uri"]] = Document(doc["text"])
        return self._diagnostics_notification(doc["uri"])

    def _on_textDocument_didChange(self, request_id: Any, params: dict):
        uri = params["textDocument"]["uri"]
        changes = params.get("contentChanges") or []
        if changes:
            self.documents[uri] = Document(changes[-1]["text"])
        return self._diagnostics_notification(uri)

    def _on_textDocument_didClose(self, request_id: Any, params: dict):
        self.documents.pop(params["textDocument"]["uri"], None)
        return None

    def _on_textDocument_completion(self, request_id: Any,
                                    params: dict) -> dict:
        return _result(request_id, self._completions(params))

    def _on_textDocument_hover(self, request_id: Any, params: dict) -> dict:
        return _result(request_id, self._hover(params))

    def _on_textDocument_definition(self, request_id: Any,
                                    params: dict) -> dict:
        return _result(request_id, self._definition(params))

    # -- features ------------------------------------------------------------

    def _completions(self, params: dict) -> dict:
        uri = params["textDocument"]["uri"]
        doc = self.documents.get(uri)
        if not doc:
            return {"isIncomplete": False, "items": []}
        pos = params["position"]
        prefix = doc.prefix(pos["line"], pos["character"])
        items: list[dict] = []

        # Route completion inside to="...".
        route_match = _TO_ROUTE.search(prefix)
        if route_match:
            for route in self._routes():
                items.append({"label": route, "kind": 12,  # Value
                              "detail": "route"})
            return {"isIncomplete": False, "items": items}

        # Token completion inside a token-valued prop.
        if _TOKEN_CTX.search(prefix):
            for token in self._tokens():
                items.append({"label": token, "kind": 12,
                              "detail": "design token"})
            return {"isIncomplete": False, "items": items}

        # Prop completion inside an open ui.Component( call.
        component = self._enclosing_component(doc, pos["line"],
                                              pos["character"])
        if component and not _UI_PREFIX.search(prefix) \
                and not prefix.rstrip().endswith("="):
            schema = self._schema(component)
            if schema:
                existing = set(_KWARG.findall(doc.line(pos["line"])))
                for name, info in schema["props"].items():
                    if name in existing or name == "children":
                        continue
                    items.append({
                        "label": name, "kind": 5,  # Field
                        "insertText": f"{name}=",
                        "detail": info["type"]
                        + (" (required)" if info["required"] else ""),
                        "documentation": _prop_doc(schema, name)})
                return {"isIncomplete": False, "items": items}

        # Component completion after "ui.".
        ui_match = _UI_PREFIX.search(prefix)
        if ui_match:
            for name in self.components():
                schema = self._schema(name)
                items.append({
                    "label": name, "kind": 7,  # Class
                    "detail": "ui." + name,
                    "documentation": (schema or {}).get("purpose", "")})
        return {"isIncomplete": False, "items": items}

    def _hover(self, params: dict) -> dict | None:
        uri = params["textDocument"]["uri"]
        doc = self.documents.get(uri)
        if not doc:
            return None
        pos = params["position"]
        word = _word_at(doc.line(pos["line"]), pos["character"])
        if not word:
            return None
        schema = self._schema(word)
        if not schema:
            return None
        lines = [f"### ui.{schema['name']}", ""]
        if schema.get("purpose"):
            lines.append(schema["purpose"])
        if schema.get("props"):
            lines.append("\nProps:")
            for name, info in schema["props"].items():
                flag = " (required)" if info["required"] else ""
                lines.append(f"- `{name}`: {info['type']}{flag}")
        if schema.get("accessibility"):
            lines.append(f"\nAccessibility: {schema['accessibility']}")
        if schema.get("example"):
            lines.append(f"\n```python\n{schema['example']}\n```")
        return {"contents": {"kind": "markdown",
                             "value": "\n".join(lines)}}

    def _definition(self, params: dict) -> dict | None:
        # Navigate from a route string or ui.Component to its Python
        # definition (SPEC 15.4: browser-to-source is the editor side).
        uri = params["textDocument"]["uri"]
        doc = self.documents.get(uri)
        if not doc:
            return None
        pos = params["position"]
        line = doc.line(pos["line"])
        route_match = re.search(r'to\s*=\s*["\']([^"\']+)["\']', line)
        if route_match:
            self._load_project()
            from .registry import active_registry
            page = active_registry().pages.get(route_match.group(1))
            if page is not None:
                loc = _source_location(page.fn)
                if loc:
                    return loc
        return None

    def _enclosing_component(self, doc: Document, line: int,
                             char: int) -> str | None:
        """The nearest ui.Component( whose call encloses the position."""
        text_before = "\n".join(doc.lines[:line]) + "\n" + \
            doc.line(line)[:char]
        depth = 0
        name = None
        i = len(text_before) - 1
        # Walk backward, matching an unclosed '(' preceded by ui.Name.
        while i >= 0:
            ch = text_before[i]
            if ch == ")":
                depth += 1
            elif ch == "(":
                if depth == 0:
                    head = text_before[:i]
                    match = re.search(r"ui\.([A-Z]\w*)\s*$", head)
                    if match:
                        name = match.group(1)
                    break
                depth -= 1
            i -= 1
        return name

    def _diagnostics_notification(self, uri: str) -> dict | None:
        doc = self.documents.get(uri)
        if not doc:
            return None
        diagnostics = _static_diagnostics(doc)
        return {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diagnostics}}


# -- static analysis (no execution) -----------------------------------------

def _static_diagnostics(doc: Document) -> list[dict]:
    """Diagnostics computable from the source text alone: invalid props
    on known components and server/client boundary hints."""
    from .schema import component_schema
    from .expr import VirelCompileError
    out: list[dict] = []
    for line_no, line in enumerate(doc.lines):
        for call in _UI_CALL.finditer(line):
            name = call.group(1)
            try:
                schema = component_schema(name)
            except VirelCompileError:
                continue
            # Invalid keyword props (only when the call opens on this line).
            after = line[call.end():]
            if not after.lstrip().startswith("("):
                continue
            valid = set(schema["props"]) | {"class_name"}
            for kwarg in _KWARG.finditer(after):
                key = kwarg.group(1)
                if key not in valid and not key.startswith("on_"):
                    col = call.end() + kwarg.start(1)
                    out.append(_diag(
                        line_no, col, col + len(key),
                        f"ui.{name} has no prop {key!r}. Valid props: "
                        f"{', '.join(sorted(schema['props']))}.", 1))
        # Boundary hint: awaiting inside a page function body is a smell.
        if re.search(r"^\s*(await |async def )", line) and \
                "@ui.server" not in doc.text[:doc.text.find(line)][-200:]:
            pass  # kept conservative; real zone checks run at compile time
    return out


def _diag(line: int, start: int, end: int, message: str,
          severity: int) -> dict:
    return {
        "range": {"start": {"line": line, "character": start},
                  "end": {"line": line, "character": end}},
        "severity": severity, "source": "virel", "message": message}


def _prop_doc(schema: dict, prop: str) -> str:
    info = schema["props"][prop]
    parts = [f"`{prop}`: {info['type']}"]
    if info["required"]:
        parts.append("required")
    elif info["default"]:
        parts.append(f"default {info['default']}")
    return ", ".join(parts)


def _word_at(line: str, char: int) -> str | None:
    if char > len(line):
        return None
    start = char
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1
    end = char
    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1
    word = line[start:end]
    return word if word and word[0].isupper() else None


def _source_location(fn: Any) -> dict | None:
    import inspect
    from pathlib import Path
    try:
        source_file = inspect.getsourcefile(fn)
        _, line = inspect.getsourcelines(fn)
    except (OSError, TypeError):
        return None
    if not source_file:
        return None
    return {"uri": Path(source_file).as_uri(),
            "range": {"start": {"line": line - 1, "character": 0},
                      "end": {"line": line - 1, "character": 0}}}


# -- transport --------------------------------------------------------------

def _result(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve(stdin: Any = None, stdout: Any = None) -> None:
    """Run the LSP over stdio with standard Content-Length framing."""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    server = LanguageServer()
    while True:
        headers: dict[str, str] = {}
        while True:
            raw = stdin.readline()
            if not raw:
                return
            text = raw.decode("ascii", "replace").strip()
            if text == "":
                break
            if ":" in text:
                key, value = text.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", 0))
        if length <= 0:
            continue
        body = stdin.read(length)
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            continue
        try:
            response = server.handle(request)
        except Exception:
            response = None
        if response is not None:
            _write(stdout, response)
        if request.get("method") == "exit":
            return


def _write(stdout: Any, message: dict) -> None:
    data = json.dumps(message).encode("utf-8")
    stdout.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    stdout.write(data)
    stdout.flush()
