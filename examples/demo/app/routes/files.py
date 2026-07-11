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
                           description="Uploaded as multipart/form-data with "
                                       "byte-level progress.")

    def start():
        error.set("")
        ui.upload(import_dataset, files=dataset, args={"label": label},
                  into=result, progress_into=progress, error_into=error)

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
