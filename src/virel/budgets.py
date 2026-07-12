"""Performance budgets (SPEC 17.2).

The framework meets its budgets by construction: the browser runtime is
one shared, cached module; static pages ship zero runtime JavaScript;
interactive pages add only a small per-page module (route-level code
splitting). This module measures those sizes and enforces configured
budgets so a regression fails ``virel check`` in CI.

Sizes are gzip byte counts of the production-compacted output, which is
what the spec's budgets are stated in.
"""

from __future__ import annotations

import gzip
from typing import Any

# Defaults track SPEC 17.2. A project overrides them in virel.toml:
#   [budgets]
#   runtime_gzip = 35000
#   page_gzip = 24000
#   app_gzip = 60000
_DEFAULT_BUDGETS = {
    "runtime_gzip": 35_000,   # core browser runtime
    "page_gzip": 24_000,      # any single page module
    "app_gzip": 60_000,       # runtime + the largest page (minimal app)
}


def _gzip_size(text: str) -> int:
    # mtime=0 keeps the gzip header deterministic across runs.
    return len(gzip.compress(text.encode("utf-8"), mtime=0))


def runtime_gzip_bytes() -> int:
    from .theme import compact, runtime_js
    return _gzip_size(compact(runtime_js()))


def measure(budgets: dict[str, int] | None = None) -> dict[str, Any]:
    """Measure every route's page-module size and the framework totals
    against the budgets, returning a structured report."""
    from .compiler import compile_page
    from .context import ContextMissingError
    from .expr import VirelCompileError
    from .registry import active_registry

    limits = {**_DEFAULT_BUDGETS, **(budgets or {})}
    runtime = runtime_gzip_bytes()
    pages: list[dict[str, Any]] = []
    largest_page = 0
    for page in active_registry().pages.values():
        try:
            params = {name: "x" for name in page.param_names}
            compiled = compile_page(page, params=params or None,
                                    hashed=True)
        except (ContextMissingError, VirelCompileError):
            continue
        size = _gzip_size(compiled.js) if compiled.js else 0
        largest_page = max(largest_page, size)
        pages.append({"route": page.path, "page_gzip": size,
                      "over_budget": size > limits["page_gzip"]})

    app_total = runtime + largest_page
    checks = [
        {"name": "runtime_gzip", "actual": runtime,
         "budget": limits["runtime_gzip"],
         "ok": runtime <= limits["runtime_gzip"]},
        {"name": "app_gzip", "actual": app_total,
         "budget": limits["app_gzip"],
         "ok": app_total <= limits["app_gzip"]},
    ]
    for entry in pages:
        checks.append({
            "name": f"page_gzip {entry['route']}",
            "actual": entry["page_gzip"], "budget": limits["page_gzip"],
            "ok": not entry["over_budget"]})
    return {
        "runtime_gzip": runtime,
        "largest_page_gzip": largest_page,
        "app_gzip": app_total,
        "pages": pages,
        "checks": checks,
        "ok": all(c["ok"] for c in checks),
        "budgets": limits,
    }


def component_bundle_cost() -> dict[str, int]:
    """The runtime functions each component needs, as a gzip byte cost
    (SPEC 17.2: first-party components must publish bundle cost). A
    component's cost is the size of the runtime helpers it binds; most
    components are pure HTML and cost nothing beyond the shared runtime."""
    import re
    from .theme import compact, runtime_js
    source = runtime_js()
    # Size each exported runtime function on its own.
    sizes: dict[str, int] = {}
    for match in re.finditer(
            r"^export (?:async )?function (\w+)[\s\S]*?^\}", source,
            re.MULTILINE):
        sizes[match.group(1)] = _gzip_size(compact(match.group(0)))

    # Map components to the runtime bindings they emit.
    bindings = {
        "Menu": ["menu"], "Select": ["select"], "Tabs": ["tabs"],
        "Dialog": ["bindDialog"], "Tree": ["tree"],
        "CommandPalette": ["palette"], "DataGrid": ["datagrid"],
        "Popover": ["popover"], "Listbox": ["listbox"],
        "FilterChips": ["chips"], "Splitter": ["splitter"],
        "Swipeable": ["swipeable"], "Tour": ["tour_overlay"],
        "Slider": ["bindProp"], "TextField": ["bindProp"],
        "ai.Recorder": ["recorder"], "ai.ImageViewer": ["lightbox"],
        "ai.PromptEditor": ["prompt_editor"],
    }
    cost: dict[str, int] = {}
    for component, fns in bindings.items():
        cost[component] = sum(sizes.get(fn, 0) for fn in fns)
    return cost
