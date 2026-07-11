"""File upload and download (SPEC 8.8)."""

import json

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.registry import active_registry
from virel.server import create_asgi_app
from virel.uploads import parse_multipart, sanitize_filename

from conftest import asgi_request


def _import_action():
    @ui.server
    def import_data(file: ui.UploadFile, name: str = "") -> str:
        rows = file.text().strip().splitlines()
        return f"imported {len(rows)} rows from {file.filename} as {name}"
    return import_data


def _upload_page(action):
    def page():
        result = ui.state("")
        progress = ui.state(0)
        error = ui.state("")
        dataset = ui.FileField(label="Dataset", accept=".csv")

        def start():
            ui.upload(action, files=dataset, args={"name": "run-1"},
                      into=result, progress_into=progress, error_into=error)

        return ui.Page(
            dataset,
            ui.Button("Import", on_click=start),
            ui.Progress(progress, max=100, label="Upload progress"),
            ui.Text(result),
            ui.When(error != "", then=ui.Alert(error, intent="danger")),
        )
    return page


def test_upload_emits_multipart_binding():
    action = _import_action()
    ui.page("/")(_upload_page(action))
    result = compile_page(active_registry().pages["/"])
    import re
    ref = re.search(r'data-vf="(f\d+)"', result.html).group(1)
    assert f'$.upload("import_data", "{ref}", {{name: "run-1"}}' in result.js
    assert 'fileParam: "file"' in result.js
    assert "progress: S.s2" in result.js


def test_upload_flow_in_component_tests():
    action = _import_action()
    view = ui.test.render(_upload_page(action))
    view.get_by_label("Dataset").attach("data.csv", "a,b\n1,2\n3,4\n",
                                        content_type="text/csv")
    view.get_by_role("button", name="Import").click()
    assert "imported 3 rows from data.csv as run-1" in view.query_text()


def test_upload_without_file_reports_error():
    action = _import_action()
    view = ui.test.render(_upload_page(action))
    view.get_by_role("button", name="Import").click()
    assert "no file selected" in view.query_text()


def _multipart_body(boundary: str, args: dict, filename: str,
                    content: bytes, field: str = "file") -> bytes:
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="__args"\r\n\r\n'
        f'{json.dumps(args)}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
        f'filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n',
    ]
    return ("".join(parts)).encode() + content + f"\r\n--{boundary}--\r\n".encode()


def test_server_accepts_multipart_upload():
    action = _import_action()

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    boundary = "virelboundary"
    body = _multipart_body(boundary, {"name": "batch-9"}, "runs.csv",
                           b"x,y\n1,2\n")
    response = asgi_request(
        app, "POST", "/_virel/action/import_data", body=body,
        headers=[(b"content-type",
                  f"multipart/form-data; boundary={boundary}".encode())])
    assert response.status == 200
    assert response.json["result"] == "imported 2 rows from runs.csv as batch-9"


def test_server_rejects_upload_to_non_upload_action():
    @ui.server
    def plain(value: str) -> str:
        return value

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    boundary = "b1"
    body = _multipart_body(boundary, {}, "x.csv", b"1")
    response = asgi_request(
        app, "POST", "/_virel/action/plain", body=body,
        headers=[(b"content-type",
                  f"multipart/form-data; boundary={boundary}".encode())])
    assert response.status == 400
    assert "does not accept file uploads" in response.json["error"]


def test_filenames_are_sanitized():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\boot.ini") == "boot.ini"
    assert sanitize_filename("report (final).csv") == "report_final_.csv"
    assert sanitize_filename("") == "upload"
    fields, files = parse_multipart(
        _multipart_body("bb", {}, "../evil.sh", b"x"),
        "multipart/form-data; boundary=bb")
    assert files["file"][0].filename == "evil.sh"


def test_download_action_over_get():
    @ui.server(download=True)
    def export_runs(fmt: str = "csv") -> ui.FileDownload:
        return ui.FileDownload("name,score\natlas,0.9\n",
                               filename=f"runs.{fmt}",
                               content_type="text/csv")

    @ui.page("/")
    def page():
        return ui.Page(ui.DownloadButton("Export", action=export_runs,
                                         args={"fmt": "csv"}))

    result = compile_page(active_registry().pages["/"])
    assert 'href="/_virel/action/export_runs?fmt=csv"' in result.html
    assert "download" in result.html

    app = create_asgi_app(dev=True)
    response = asgi_request(app, "GET", "/_virel/action/export_runs",
                            query="fmt=csv")
    assert response.status == 200
    assert response.headers["content-type"] == "text/csv"
    assert 'filename="runs.csv"' in response.headers["content-disposition"]
    assert "atlas,0.9" in response.text


def test_download_button_requires_download_action():
    @ui.server
    def not_download() -> str:
        return "x"

    with pytest.raises(VirelCompileError, match="download=True"):
        ui.DownloadButton("Export", action=not_download)


def test_get_refused_for_non_download_actions():
    @ui.server
    def mutate(value: str) -> str:
        return value

    @ui.page("/")
    def page():
        return ui.Page(ui.Text("x"))

    app = create_asgi_app(dev=True)
    assert asgi_request(app, "GET", "/_virel/action/mutate").status == 404
