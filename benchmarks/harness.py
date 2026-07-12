"""Static metrics for a Virel benchmark solution (SPEC 14.7).

Computes the metrics derivable from a solution directory without driving
a model: source-token count, bundle sizes, the accessibility result, and
whether the app compiles. Agent-trajectory metrics (output tokens,
repair turns, wall-clock) are recorded by the run driver, not here.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def source_tokens(solution: Path) -> int:
    total = 0
    for path in solution.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        total += estimate_tokens(path.read_text("utf-8"))
    return total


def compile_result(solution: Path) -> dict:
    check = subprocess.run(
        [sys.executable, "-m", "virel.cli", "check", "--json"],
        cwd=str(solution), capture_output=True, text=True)
    diagnostics = []
    for line in check.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            diagnostics.append(json.loads(line))
    warnings = sum(1 for d in diagnostics if d.get("severity") == "warning")
    errors = [d for d in diagnostics if d.get("code")]
    return {"compiles": check.returncode == 0,
            "accessibility_warnings": warnings,
            "errors": errors}


def bundle_sizes(solution: Path) -> dict:
    from virel.theme import runtime_js
    return {"runtime_js_bytes": len(runtime_js().encode())}


def measure(solution: Path, task: str | None) -> dict:
    return {
        "task": task,
        "generated_source_tokens": source_tokens(solution),
        "compile": compile_result(solution),
        "bundle": bundle_sizes(solution),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution", required=True, type=Path)
    parser.add_argument("--task")
    args = parser.parse_args()
    if not args.solution.exists():
        parser.error(f"solution {args.solution} does not exist")
    print(json.dumps(measure(args.solution, args.task), indent=2))


if __name__ == "__main__":
    main()
