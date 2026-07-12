"""The language server (SPEC 15.4)."""

from virel import ui
from virel.lsp import LanguageServer
from virel.registry import fresh_registry


def _server_with(text: str, uri: str = "file:///page.py") -> LanguageServer:
    server = LanguageServer()
    server.handle({"id": 1, "method": "initialize", "params": {}})
    server.handle({"method": "textDocument/didOpen", "params": {
        "textDocument": {"uri": uri, "text": text}}})
    return server


def _complete(server, uri, line, char):
    result = server.handle({"id": 2, "method": "textDocument/completion",
                            "params": {"textDocument": {"uri": uri},
                                       "position": {"line": line,
                                                    "character": char}}})
    return result["result"]["items"]


def test_capabilities_declared():
    server = LanguageServer()
    caps = server.handle({"id": 1, "method": "initialize",
                          "params": {}})["result"]["capabilities"]
    assert caps["completionProvider"]
    assert caps["hoverProvider"]
    assert caps["definitionProvider"]


def test_component_completion_after_ui():
    text = "from virel import ui\nx = ui.Sel"
    server = _server_with(text)
    items = _complete(server, "file:///page.py", 1, 10)
    labels = {item["label"] for item in items}
    assert "Select" in labels and "Slider" in labels


def test_prop_completion_inside_a_component_call():
    text = 'from virel import ui\nx = ui.Button("Save", )'
    server = _server_with(text)
    items = _complete(server, "file:///page.py", 1, 21)
    labels = {item["label"] for item in items}
    assert "intent" in labels and "on_click" in labels
    intent = next(i for i in items if i["label"] == "intent")
    assert intent["insertText"] == "intent="


def test_token_completion_in_a_token_prop():
    text = 'from virel import ui\nx = ui.style(background="'
    server = _server_with(text)
    items = _complete(server, "file:///page.py", 1, 38)
    labels = {item["label"] for item in items}
    assert "accent" in labels and "surface.1" in labels


def test_route_completion_in_a_link(tmp_path, monkeypatch):
    fresh_registry()

    @ui.page("/dashboard")
    def dashboard():
        return ui.Page(ui.Text("x"))

    @ui.page("/settings")
    def settings():
        return ui.Page(ui.Text("x"))

    server = LanguageServer()
    server._project_loaded = True  # routes already registered in-process
    server.handle({"id": 1, "method": "initialize", "params": {}})
    text = 'from virel import ui\nx = ui.Link("Go", to="'
    server.handle({"method": "textDocument/didOpen", "params": {
        "textDocument": {"uri": "file:///p.py", "text": text}}})
    items = _complete(server, "file:///p.py", 1, 24)
    labels = {item["label"] for item in items}
    assert "/dashboard" in labels and "/settings" in labels
    fresh_registry()


def test_hover_shows_prop_documentation():
    text = "from virel import ui\nx = ui.DataGrid(rows)"
    server = _server_with(text)
    hover = server.handle({"id": 2, "method": "textDocument/hover",
                           "params": {
                               "textDocument": {"uri": "file:///page.py"},
                               "position": {"line": 1, "character": 8}}})
    value = hover["result"]["contents"]["value"]
    assert "ui.DataGrid" in value
    assert "Accessibility" in value
    assert "```python" in value


def test_invalid_prop_diagnostics():
    text = 'from virel import ui\nx = ui.Button("Hi", intnet="primary")'
    server = LanguageServer()
    server.handle({"id": 1, "method": "initialize", "params": {}})
    note = server.handle({"method": "textDocument/didOpen", "params": {
        "textDocument": {"uri": "file:///page.py", "text": text}}})
    diagnostics = note["params"]["diagnostics"]
    assert any("no prop 'intnet'" in d["message"] for d in diagnostics)
    # A valid prop produces no diagnostic.
    good = 'from virel import ui\nx = ui.Button("Hi", intent="primary")'
    server.handle({"method": "textDocument/didChange", "params": {
        "textDocument": {"uri": "file:///page.py"},
        "contentChanges": [{"text": good}]}})
    note2 = server._diagnostics_notification("file:///page.py")
    assert note2["params"]["diagnostics"] == []


def test_on_handlers_and_class_name_are_not_flagged():
    text = ('from virel import ui\n'
            'x = ui.Button("Hi", on_click=f, class_name="c")')
    server = _server_with(text)
    note = server._diagnostics_notification("file:///page.py")
    assert note["params"]["diagnostics"] == []


def test_lsp_transport_round_trip():
    import io
    import json
    from virel.lsp import serve

    def framed(message):
        body = json.dumps(message).encode()
        return (f"Content-Length: {len(body)}\r\n\r\n".encode() + body)

    requests = (framed({"id": 1, "method": "initialize", "params": {}})
                + framed({"id": 2, "method": "shutdown", "params": {}})
                + framed({"method": "exit", "params": {}}))
    stdin = io.BytesIO(requests)
    stdout = io.BytesIO()
    serve(stdin=stdin, stdout=stdout)
    output = stdout.getvalue().decode()
    assert "Content-Length:" in output
    assert '"virel-lsp"' in output
