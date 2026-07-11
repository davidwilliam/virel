"""File transfer: uploads with progress and downloads (SPEC 8.8)."""

from virel import ui

from ..shared import shell

_imports: list[dict] = []


@ui.server
async def import_dataset(file: ui.UploadFile, label: str = "") -> str:
    rows = file.text().strip().splitlines()
    _imports.append({"file": file.filename, "rows": len(rows)})
    return (f"Imported {len(rows)} rows from {file.filename}"
            + (f" as {label}" if label else ""))


@ui.server
async def import_batch(files: list[ui.UploadFile]) -> str:
    total = sum(len(f.text().strip().splitlines()) for f in files)
    names = ", ".join(f.filename for f in files)
    return f"Imported {total} rows across {len(files)} files ({names})"


@ui.server(download=True)
def export_runs(fmt: str = "csv") -> ui.FileDownload:
    body = "name,dataset,score\natlas-small,qa-hard-v2,0.87\n" \
           "atlas-large,qa-hard-v2,0.93\n"
    return ui.FileDownload(body, filename=f"runs.{fmt}",
                           content_type="text/csv")


@ui.page("/files")
def files() -> ui.Node:
    result = ui.state("")
    progress = ui.state(0)
    error = ui.state("")
    label = ui.state("")
    dataset = ui.FileField(label="Dataset (CSV)", accept=".csv,text/csv",
                           description="Click to browse or drag a file onto "
                                       "the zone; uploads are multipart with "
                                       "byte-level progress.")
    batch_result = ui.state("")
    batch_error = ui.state("")
    batch = ui.FileField(label="Batch import", accept=".csv,text/csv",
                         multiple=True,
                         description="Multiple files upload together; the "
                                     "action receives list[ui.UploadFile].")

    def start():
        error.set("")
        ui.upload(import_dataset, files=dataset, args={"label": label},
                  into=result, progress_into=progress, error_into=error)

    def start_batch():
        batch_error.set("")
        ui.upload(import_batch, files=batch, into=batch_result,
                  error_into=batch_error)

    return ui.Page(
        shell(
            ui.Section(
                ui.Heading("File transfer", level=1),
                ui.Grid(
                    ui.Card(
                        ui.Heading("Upload", level=3),
                        dataset,
                        ui.TextField(label, label="Label",
                                     placeholder="optional"),
                        ui.Row(
                            ui.Button("Import", intent="primary",
                                      on_click=start),
                            gap=3,
                        ),
                        ui.Progress(progress, max=100, label="Upload progress"),
                        ui.When(result != "",
                                then=ui.Alert(result, intent="success")),
                        ui.When(error != "",
                                then=ui.Alert(error, intent="danger")),
                        gap=4,
                    ),
                    ui.Card(
                        ui.Heading("Batch upload", level=3),
                        batch,
                        ui.Row(ui.Button("Import all", on_click=start_batch),
                               gap=3),
                        ui.When(batch_result != "",
                                then=ui.Alert(batch_result, intent="success")),
                        ui.When(batch_error != "",
                                then=ui.Alert(batch_error, intent="danger")),
                        gap=4,
                    ),
                    ui.Card(
                        ui.Heading("Download", level=3),
                        ui.Text("Download actions answer GET requests and "
                                "must not change state; guards still run.",
                                muted=True),
                        ui.Row(ui.DownloadButton("Export runs.csv",
                                                 action=export_runs,
                                                 args={"fmt": "csv"}),
                               gap=3),
                        gap=4,
                    ),
                    columns={"base": 1, "md": 2},
                    gap=6,
                ),
            ),
        ),
        title="Files — Virel Demo",
    )
