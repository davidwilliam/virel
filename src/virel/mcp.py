"""The agent interface: a stdio MCP server (SPEC 14.4).

``virel mcp`` speaks the Model Context Protocol over stdin/stdout using
only the standard library, so an agent can inspect the project, query
component schemas, generate context packs, validate a planned component
tree, compile a file, read structured diagnostics, inspect routes and
execution zones, run targeted tests, and estimate bundle impact.

The same operations back the CLI, so the MCP surface is a thin adapter
rather than a parallel implementation.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"


def _tools() -> list[dict[str, Any]]:
    string = {"type": "string"}
    return [
        {"name": "project_structure",
         "description": "List routes, server actions, and their execution "
                        "zones for the app in the working directory.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "component_schema",
         "description": "The structured schema for one component: props, "
                        "types, events, accessibility, examples, "
                        "constraints.",
         "inputSchema": {"type": "object",
                         "properties": {"name": string},
                         "required": ["name"]}},
        {"name": "list_components",
         "description": "Every component name.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "context_pack",
         "description": "A compact, task-specific documentation pack.",
         "inputSchema": {"type": "object", "properties": {
             "components": {"type": "array", "items": string},
             "features": {"type": "array", "items": string},
             "budget": {"type": "integer"}}}},
        {"name": "compile_file",
         "description": "Compile a Python module of Virel pages and return "
                        "structured diagnostics for any failures.",
         "inputSchema": {"type": "object", "properties": {"path": string},
                         "required": ["path"]}},
        {"name": "diagnostics",
         "description": "Compile every route in the app and return "
                        "structured diagnostics (SPEC 14.5).",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "routes",
         "description": "Routes with their render mode and execution zone.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "run_tests",
         "description": "Run the project's pytest suite, optionally "
                        "filtered by a -k expression.",
         "inputSchema": {"type": "object",
                         "properties": {"filter": string}}},
        {"name": "bundle_impact",
         "description": "Per-route JavaScript bundle sizes plus the shared "
                        "runtime size.",
         "inputSchema": {"type": "object", "properties": {}}},
    ]


def _load_app(root: Path) -> None:
    import tomllib
    import importlib
    config = tomllib.loads((root / "virel.toml").read_text("utf-8"))
    module = config["app"]["module"]
    sys.path.insert(0, str(root))
    importlib.import_module(module)


def _call_tool(name: str, args: dict[str, Any], root: Path) -> Any:
    from .expr import VirelCompileError
    if name == "list_components":
        from .schema import list_components
        return {"components": list_components()}
    if name == "component_schema":
        from .schema import component_schema
        return component_schema(args["name"])
    if name == "context_pack":
        from .contextpack import context_pack
        return {"pack": context_pack(
            components=args.get("components"),
            features=args.get("features"),
            budget=args.get("budget", 12000))}

    # The remaining tools need the app loaded.
    _load_app(root)
    from .registry import active_registry
    registry = active_registry()

    if name in ("project_structure", "routes"):
        from .compiler import compile_page
        from .context import ContextMissingError
        routes = []
        for page in registry.pages.values():
            zone = "static"
            try:
                params = {p: f"x" for p in page.param_names}
                compiled = compile_page(page, params=params or None)
                zone = compiled.render_mode
            except ContextMissingError:
                zone = "server (needs request context)"
            except VirelCompileError as error:
                zone = f"error: {error}"
            routes.append({"path": page.path, "zone": zone,
                           "dynamic": page.is_dynamic})
        result: dict[str, Any] = {"routes": routes}
        if name == "project_structure":
            result["actions"] = [
                {"name": action.name,
                 "streaming": action.stream_response,
                 "download": action.download,
                 "zone": "server (CPython)"}
                for action in registry.actions.values()]
        return result

    if name in ("compile_file", "diagnostics"):
        from .compiler import compile_page
        from .context import ContextMissingError
        from .diagnostics import classify
        diagnostics = []
        for page in registry.pages.values():
            try:
                params = {p: "x" for p in page.param_names}
                compiled = compile_page(page, params=params or None)
                for warning in compiled.warnings:
                    diagnostics.append({"severity": "warning",
                                        "route": page.path,
                                        "message": warning})
            except ContextMissingError:
                continue
            except VirelCompileError as error:
                entry = classify(str(error))
                entry["severity"] = "error"
                diagnostics.append(entry)
        return {"diagnostics": diagnostics,
                "ok": not any(d.get("severity") == "error"
                              for d in diagnostics)}

    if name == "bundle_impact":
        from .compiler import compile_page
        from .context import ContextMissingError
        from .theme import runtime_js
        pages = []
        for page in registry.pages.values():
            try:
                params = {p: "x" for p in page.param_names}
                compiled = compile_page(page, params=params or None)
                pages.append({"path": page.path,
                              "page_js_bytes": len(compiled.js or "")})
            except (ContextMissingError, VirelCompileError):
                continue
        return {"runtime_js_bytes": len(runtime_js().encode()),
                "pages": pages}

    if name == "run_tests":
        import subprocess
        command = [sys.executable, "-m", "pytest", "-q"]
        if args.get("filter"):
            command += ["-k", args["filter"]]
        completed = subprocess.run(command, cwd=str(root),
                                   capture_output=True, text=True)
        return {"exit_code": completed.returncode,
                "output": (completed.stdout + completed.stderr)[-4000:]}

    raise ValueError(f"unknown tool {name!r}")


def _handle(request: dict[str, Any], root: Path) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return _ok(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "virel", "version": "0.1.0"}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _ok(request_id, {"tools": _tools()})
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        try:
            # Tool code must not print to stdout: that channel is the
            # protocol transport.
            with redirect_stdout(io.StringIO()), \
                    redirect_stderr(io.StringIO()):
                payload = _call_tool(name, args, root)
            return _ok(request_id, {"content": [
                {"type": "text", "text": json.dumps(payload, indent=2)}]})
        except Exception as error:  # tool errors are results, not crashes
            return _ok(request_id, {"isError": True, "content": [
                {"type": "text", "text": f"{type(error).__name__}: {error}"}]})
    if request_id is not None:
        return _error(request_id, -32601, f"unknown method {method!r}")
    return None


def _ok(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def serve(root: Path | None = None,
          stdin: Any = None, stdout: Any = None) -> None:
    """Run the MCP server over a line-delimited JSON-RPC stream."""
    root = root or Path.cwd()
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(request, root)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
