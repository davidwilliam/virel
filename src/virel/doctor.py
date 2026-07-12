"""Environment and project health checks (SPEC 15.1: virel doctor)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def run_doctor(root: Path) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    version = sys.version_info
    if version >= (3, 11):
        add("python", "ok", f"{version.major}.{version.minor} meets >=3.11")
    else:
        add("python", "fail",
            f"{version.major}.{version.minor} is below the required 3.11")

    config = root / "virel.toml"
    if not config.exists():
        add("project", "warn",
            "no virel.toml; run from an application directory or "
            "`virel new`")
        add("routes", "warn", "skipped (no project)")
        _dependency_checks(add)
        return _finish(checks)
    add("project", "ok", f"found {config.name}")

    try:
        import tomllib
        parsed = tomllib.loads(config.read_text("utf-8"))
        module = parsed.get("app", {}).get("module")
        if not module:
            add("config", "fail", 'virel.toml has no [app] module = "..."')
        else:
            add("config", "ok", f'app module is "{module}"')
    except Exception as error:  # malformed toml
        add("config", "fail", f"virel.toml is not valid: {error}")
        return _finish(checks)

    try:
        sys.path.insert(0, str(root))
        import importlib
        importlib.import_module(module)
        from .registry import active_registry
        registry = active_registry()
        if registry.pages:
            add("routes", "ok",
                f"{len(registry.pages)} route(s) registered")
        else:
            add("routes", "warn", "the app module registered no routes")
    except Exception as error:
        add("routes", "fail", f"importing the app failed: {error}")
        return _finish(checks)

    # Compile every route so doctor reflects a real build.
    from .compiler import compile_page
    from .context import ContextMissingError
    from .expr import VirelCompileError
    failures = 0
    warnings = 0
    for page in registry.pages.values():
        try:
            params = {name: "x" for name in page.param_names}
            compiled = compile_page(page, params=params or None)
            warnings += len(compiled.warnings)
        except ContextMissingError:
            continue
        except VirelCompileError:
            failures += 1
    if failures:
        add("compile", "fail", f"{failures} route(s) fail to compile; "
                               "run `virel check`")
    elif warnings:
        add("compile", "warn", f"routes compile with {warnings} "
                               "accessibility warning(s)")
    else:
        add("compile", "ok", "every route compiles cleanly")

    _dependency_checks(add)
    return _finish(checks)


def _dependency_checks(add) -> None:
    # Optional dependencies enable optional features; their absence is a
    # note, never a failure, since the core is dependency-free.
    optional = {
        "pydantic": "Pydantic model forms",
        "matplotlib": "matplotlib/seaborn figures (ui.Figure)",
        "pandas": "DataFrame data adapters",
    }
    import importlib.util
    present = [name for name in optional
              if importlib.util.find_spec(name) is not None]
    absent = {name: use for name, use in optional.items()
              if name not in present}
    if present:
        add("optional-deps", "ok",
            f"available: {', '.join(sorted(present))}")
    if absent:
        detail = "; ".join(f"{name} (for {use})"
                          for name, use in absent.items())
        add("optional-deps", "warn", f"not installed: {detail}")


def _finish(checks: list[dict[str, str]]) -> dict[str, Any]:
    fails = sum(1 for c in checks if c["status"] == "fail")
    warns = sum(1 for c in checks if c["status"] == "warn")
    if fails:
        summary = f"{fails} problem(s) need attention."
    elif warns:
        summary = f"Healthy, with {warns} note(s)."
    else:
        summary = "Everything looks healthy."
    return {"checks": checks, "summary": summary,
            "ok": fails == 0}
