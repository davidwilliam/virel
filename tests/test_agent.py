"""Agent-native development (SPEC 14.2-14.5)."""

import io
import json
from pathlib import Path

import pytest

from virel import ui
from virel.diagnostics import classify
from virel.schema import component_schema, list_components


# -- 14.2 machine-readable registry -----------------------------------------

def test_schema_covers_the_full_contract():
    schema = component_schema("DataGrid")
    for field in ("name", "import", "purpose", "props", "events",
                  "accessibility", "incompatibilities", "example",
                  "deprecated"):
        assert field in schema
    assert schema["props"]["key"]["type"]
    assert schema["events"] and schema["incompatibilities"]
    assert "group_by" in " ".join(schema["incompatibilities"])


def test_every_component_produces_a_schema():
    names = list_components()
    assert "Button" in names and "Chart" in names and "Figure" in names
    for name in names:
        schema = component_schema(name)
        assert schema["name"] == name
        assert "props" in schema


def test_unknown_component_is_a_clear_error():
    from virel.expr import VirelCompileError
    with pytest.raises(VirelCompileError, match="Unknown component"):
        component_schema("Nonexistent")


# -- 14.3 context packs ------------------------------------------------------

def test_context_pack_contains_only_requested_surface():
    pack = ui.context_pack(components=["DataGrid"],
                           features=["validation"], budget=12000)
    assert "### Validation" in pack
    assert "### DataGrid" in pack
    assert "### Streaming AI chat" not in pack  # not requested


def test_context_pack_honors_the_budget():
    big = ui.context_pack(components=["DataGrid", "Chart", "Button"],
                          features=["forms", "streaming", "auth"],
                          budget=100000)
    small = ui.context_pack(components=["DataGrid", "Chart", "Button"],
                            features=["forms", "streaming", "auth"],
                            budget=120)
    assert len(small) < len(big)
    assert "Truncated" in small


def test_context_pack_rejects_unknown_requests():
    from virel.expr import VirelCompileError
    with pytest.raises(VirelCompileError, match="Unknown feature"):
        ui.context_pack(features=["telepathy"])
    with pytest.raises(VirelCompileError, match="Unknown component"):
        ui.context_pack(components=["Fictional"])


def test_canonical_patterns_name_one_way_per_task():
    patterns = ui.canonical_patterns()
    assert "forms" in patterns and "data-table" in patterns
    assert patterns["streaming"] == "Streaming AI chat"


# -- 14.5 deterministic diagnostics -----------------------------------------

def test_diagnostics_have_codes_ranges_and_fixes():
    @ui.page("/bad-if")
    def bad_if():
        flag = ui.state(True)
        if flag:  # reactive value in a Python if
            return ui.Page(ui.Text("yes"))
        return ui.Page(ui.Text("no"))

    from virel.compiler import compile_page
    from virel.expr import VirelCompileError
    from virel.registry import active_registry
    try:
        compile_page(active_registry().pages["/bad-if"])
        assert False, "expected a compile error"
    except VirelCompileError as error:
        diag = classify(str(error))
    assert diag["code"] == "VRL001"
    assert diag["fixes"] and "ui.When" in diag["fixes"][0]
    assert diag["documentation"].startswith("https://")
    assert diag["route"] == "/bad-if"


def test_diagnostics_classify_known_errors():
    assert classify("<button> has no accessible name")["code"] == "VRL003"
    assert classify("Image requires alt text")["code"] == "VRL005"
    assert classify("uses a blocked URL scheme")["code"] == "VRL004"
    assert classify("Raw JavaScript is prohibited by policy")["code"] \
        == "VRL008"
    assert classify("something entirely novel")["code"] == "VRL000"


def test_handler_diagnostics_carry_a_source_range():
    diag = classify("[route /x] [submit, line 4] `Slice` expressions are "
                    "not in the client subset.")
    assert diag["code"] == "VRL002"
    assert diag["range"] == {"handler": "submit", "line": 4}


# -- 14.4 MCP interface ------------------------------------------------------

def test_mcp_server_handles_the_protocol():
    from virel.mcp import serve

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "list_components", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "component_schema", "arguments": {"name": "Button"}}},
    ]
    stdin = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    stdout = io.StringIO()
    serve(root=Path("examples/demo"), stdin=stdin, stdout=stdout)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]

    assert lines[0]["result"]["serverInfo"]["name"] == "virel"
    tools = {t["name"] for t in lines[1]["result"]["tools"]}
    assert {"project_structure", "compile_file", "run_tests",
            "bundle_impact", "context_pack"} <= tools
    components = json.loads(lines[2]["result"]["content"][0]["text"])
    assert "Button" in components["components"]
    schema = json.loads(lines[3]["result"]["content"][0]["text"])
    assert schema["name"] == "Button"


def test_mcp_tool_errors_are_results_not_crashes():
    from virel.mcp import serve
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "component_schema",
                          "arguments": {"name": "Nope"}}}
    stdout = io.StringIO()
    serve(root=Path("examples/demo"),
          stdin=io.StringIO(json.dumps(request) + "\n"), stdout=stdout)
    response = json.loads(stdout.getvalue())
    assert response["result"]["isError"] is True


def test_mcp_diagnostics_tool_reports_clean_demo():
    from virel.mcp import serve
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "diagnostics", "arguments": {}}}
    stdout = io.StringIO()
    serve(root=Path("examples/demo"),
          stdin=io.StringIO(json.dumps(request) + "\n"), stdout=stdout)
    payload = json.loads(json.loads(stdout.getvalue())[
        "result"]["content"][0]["text"] if False else
        json.loads(stdout.getvalue())["result"]["content"][0]["text"])
    assert payload["ok"] is True


# -- 14.7 benchmark structure ------------------------------------------------

def test_benchmark_tasks_cover_the_spec_list():
    import json as _json
    from pathlib import Path as _Path
    tasks = _json.loads(
        (_Path("benchmarks") / "tasks.json").read_text())
    ids = {task["id"] for task in tasks["tasks"]}
    expected = {"landing-page", "saas-settings", "multi-step-form",
                "data-table", "ai-chat", "file-upload", "ops-dashboard",
                "command-palette", "stateful-editor"}
    assert ids == expected
    for task in tasks["tasks"]:
        assert task["prompt"] and task["acceptance"]
    # Every SPEC 14.7 metric is named.
    for metric in ("generated_source_tokens", "model_output_tokens",
                   "repair_turns", "accessibility_score",
                   "runtime_bundle_bytes"):
        assert metric in tasks["metrics"]


def test_harness_measures_a_solution():
    import sys
    sys.path.insert(0, "benchmarks")
    import harness
    from pathlib import Path as _Path
    result = harness.measure(_Path("examples/demo"), "data-table")
    assert result["generated_source_tokens"] > 0
    assert result["compile"]["compiles"] is True
    assert result["bundle"]["runtime_js_bytes"] > 0
