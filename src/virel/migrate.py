"""Migration patches (SPEC 15.1: virel migrate, SPEC 14.4).

A migration is a set of source rewrites for a deprecated or renamed
API. Each is a named collection of safe, reviewable substitutions
applied across the project's Python files; ``--apply`` writes them,
otherwise a unified diff is shown. Rewrites are deliberately
conservative (literal token replacements, never speculative rewrites of
program logic).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Callable

# name -> (description, list of (compiled pattern, replacement))
_MIGRATIONS: dict[str, tuple[str, list[tuple[re.Pattern, str]]]] = {
    "unsafe-html-namespace": (
        "Move ui.unsafe_html(...) calls to ui.unsafe.html(...).",
        [(re.compile(r"\bui\.unsafe_html\("), "ui.unsafe.html(")],
    ),
    "heading-size": (
        "Flag Heading(level=3) so you can add size= for the visual "
        "scale (manual review recommended).",
        [(re.compile(r"ui\.Heading\((.*?)level=3\)"),
          r"ui.Heading(\1level=2, size=3)")],
    ),
}


def available_migrations() -> dict[str, str]:
    return {name: description
            for name, (description, _rules) in _MIGRATIONS.items()}


def run_migration(name: str, root: Path, *,
                  apply: bool = False) -> list[dict[str, Any]]:
    from .expr import VirelCompileError
    if name not in _MIGRATIONS:
        raise VirelCompileError(
            f"Unknown migration {name!r}. Available: "
            f"{', '.join(_MIGRATIONS)}.")
    _description, rules = _MIGRATIONS[name]
    search_dirs = [root / "app"] if (root / "app").is_dir() else [root]
    patches: list[dict[str, Any]] = []
    for directory in search_dirs:
        for path in sorted(directory.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            original = path.read_text("utf-8")
            updated = original
            changes = 0
            for pattern, replacement in rules:
                updated, count = pattern.subn(replacement, updated)
                changes += count
            if changes == 0:
                continue
            diff = "".join(difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=str(path), tofile=str(path)))
            if apply:
                path.write_text(updated, "utf-8")
            patches.append({"path": str(path.relative_to(root)),
                            "changes": changes, "diff": diff})
    return patches
