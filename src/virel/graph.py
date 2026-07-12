"""The route and dependency graph (SPEC 15.1: virel graph).

Nodes are routes, layouts, and server actions; edges connect a route to
the actions it calls, the layouts that wrap it, and the pages it links
to. The graph exposes how a change ripples through the app, in JSON,
Graphviz DOT, or a readable text tree.
"""

from __future__ import annotations

import re
from typing import Any

_LINK_RE = re.compile(r'href="(/[^"?#]*)')


def build_graph() -> dict[str, Any]:
    from .compiler import compile_page
    from .context import ContextMissingError
    from .expr import VirelCompileError
    from .registry import active_registry
    registry = active_registry()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    action_names = set(registry.actions)

    for name, action in registry.actions.items():
        nodes.append({"id": f"action:{name}", "kind": "action",
                      "label": name, "zone": "server",
                      "streaming": action.stream_response})
    for prefix in registry.layouts:
        nodes.append({"id": f"layout:{prefix}", "kind": "layout",
                      "label": prefix})

    for page in registry.pages.values():
        node: dict[str, Any] = {"id": f"route:{page.path}", "kind": "route",
                                "label": page.path,
                                "dynamic": page.is_dynamic}
        actions_used: list[str] = []
        links: list[str] = []
        try:
            params = {p: "x" for p in page.param_names}
            compiled = compile_page(page, params=params or None)
            node["render"] = compiled.render_mode
            actions_used = list(compiled.server_actions)
            links = sorted({m.group(1) for m in _LINK_RE.finditer(
                compiled.html)})
        except ContextMissingError:
            node["render"] = "server"
        except VirelCompileError as error:
            node["error"] = str(error)
        nodes.append(node)

        for action in actions_used:
            if action in action_names:
                edges.append({"from": f"route:{page.path}",
                              "to": f"action:{action}", "kind": "calls"})
        for prefix in registry.layouts:
            if page.path == prefix or page.path.startswith(
                    prefix.rstrip("/") + "/") or prefix == "/":
                edges.append({"from": f"layout:{prefix}",
                              "to": f"route:{page.path}", "kind": "wraps"})
        for target in links:
            if any(p.path == target for p in registry.pages.values()):
                edges.append({"from": f"route:{page.path}",
                              "to": f"route:{target}", "kind": "links"})

    return {"nodes": nodes, "edges": edges}


def graph_dot(graph: dict[str, Any]) -> str:
    styles = {"route": "box", "action": "ellipse", "layout": "folder"}
    lines = ["digraph virel {", "  rankdir=LR;",
             '  node [fontname="monospace" fontsize=10];']
    for node in graph["nodes"]:
        shape = styles.get(node["kind"], "box")
        lines.append(f'  "{node["id"]}" [label="{node["label"]}" '
                     f"shape={shape}];")
    edge_styles = {"calls": "solid", "wraps": "dashed", "links": "dotted"}
    for edge in graph["edges"]:
        style = edge_styles.get(edge["kind"], "solid")
        lines.append(f'  "{edge["from"]}" -> "{edge["to"]}" '
                     f'[style={style} label="{edge["kind"]}"];')
    lines.append("}")
    return "\n".join(lines)


def graph_text(graph: dict[str, Any]) -> str:
    by_route: dict[str, dict[str, list[str]]] = {}
    for node in graph["nodes"]:
        if node["kind"] == "route":
            by_route[node["id"]] = {"calls": [], "links": [],
                                    "wrapped_by": [],
                                    "render": node.get("render", "?")}
    for edge in graph["edges"]:
        if edge["kind"] == "calls" and edge["from"] in by_route:
            by_route[edge["from"]]["calls"].append(
                edge["to"].split(":", 1)[1])
        elif edge["kind"] == "links" and edge["from"] in by_route:
            by_route[edge["from"]]["links"].append(
                edge["to"].split(":", 1)[1])
        elif edge["kind"] == "wraps" and edge["to"] in by_route:
            by_route[edge["to"]]["wrapped_by"].append(
                edge["from"].split(":", 1)[1])
    lines = []
    for route_id, info in sorted(by_route.items()):
        path = route_id.split(":", 1)[1]
        lines.append(f"{path}  [{info['render']}]")
        for layout in info["wrapped_by"]:
            lines.append(f"    wrapped by layout {layout}")
        for action in sorted(set(info["calls"])):
            lines.append(f"    calls action {action}")
        for link in sorted(set(info["links"])):
            lines.append(f"    links to {link}")
    return "\n".join(lines)
