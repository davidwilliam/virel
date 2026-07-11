"""Resources: async data with loading, error, refresh, and reactive
parameters, rendered with ui.Each."""

import asyncio
import random

from virel import ui

from ..shared import shell

_RUNS = [
    {"name": "atlas-small on qa-hard-v2", "score": 0.87, "status": "passed"},
    {"name": "atlas-large on qa-hard-v2", "score": 0.93, "status": "passed"},
    {"name": "atlas-large on multiturn-v1", "score": 0.89, "status": "passed"},
    {"name": "baseline on qa-hard-v2", "score": 0.71, "status": "regression"},
    {"name": "baseline on multiturn-v1", "score": 0.64, "status": "regression"},
]


@ui.server
async def list_runs(query: str = "") -> list[dict]:
    await asyncio.sleep(0.4)  # make the loading state visible
    needle = query.strip().lower()
    runs = [run for run in _RUNS if needle in run["name"].lower()]
    # Jitter the scores a little so refreshing visibly changes the data.
    return [
        {**run, "score": round(run["score"] + random.uniform(-0.01, 0.01), 3)}
        for run in runs
    ]


@ui.component
def run_row(run) -> ui.Node:
    return ui.Card(
        ui.Row(
            ui.Text(run.name),
            ui.Spacer(),
            ui.Text(f"score {run.score}", muted=True, size="sm"),
            ui.Badge(run.status),
            gap=3,
        ),
        gap=2,
    )


@ui.page("/runs")
def runs_page() -> ui.Node:
    query = ui.state("")
    runs = ui.resource(list_runs, params={"query": query})

    return ui.Page(
        shell(
            ui.Section(
                ui.Row(
                    ui.Heading("Evaluation runs", level=1),
                    ui.Spacer(),
                    ui.Button("Refresh", on_click=lambda: runs.refresh()),
                    gap=4,
                ),
                ui.TextField(query, label="Filter",
                             placeholder="Type to filter runs…",
                             description="Changing the filter refetches from "
                                         "the server; identical in-flight "
                                         "requests are deduplicated."),
                ui.Suspense(
                    runs,
                    content=ui.Each(runs.value, render=run_row),
                    fallback=ui.Skeleton(lines=4),
                ),
            ),
        ),
        title="Runs — Virel Demo",
    )
