# Agent-efficiency benchmarks

Public, reproducible benchmarks comparing Virel against representative
stacks (SPEC 14.7). The goal is honesty: published prompts, models,
versions, environments, and scoring logic, so anyone can rerun them and
get the same numbers. Nothing here is a launch claim; the targets in
SPEC 14.8 are release gates.

## Status

The harness and task definitions are in place. Reference-implementation
trajectories against comparison stacks are not yet recorded, so no
comparative numbers are published. When a run completes, its full inputs
and outputs are committed under `runs/<date>/` and the aggregate lands
in `RESULTS.md`. Until then, `RESULTS.md` states that the comparison is
pending rather than reporting provisional figures.

## Tasks (SPEC 14.7)

Each task in `tasks.json` has a stable id, a prompt, and an
acceptance-check description. The nine tasks:

1. `landing-page` — responsive landing page
2. `saas-settings` — authenticated SaaS settings page
3. `multi-step-form` — validated multi-step form
4. `data-table` — sortable and filterable data table
5. `ai-chat` — streaming AI chat
6. `file-upload` — file upload with progress
7. `ops-dashboard` — real-time operations dashboard
8. `command-palette` — accessible command palette
9. `stateful-editor` — a complex stateful editor

## Metrics (SPEC 14.7)

Per task and stack: successful completion, functional correctness,
visual correctness, accessibility score, security defects, generated
source tokens, documentation/context tokens, model output tokens,
repair turns, wall-clock time, runtime bundle size, application
performance.

`harness.py` computes the metrics it can derive statically from a
Virel solution directory — source-token count (via the same ~4 chars/
token proxy the context packs use), runtime and per-route bundle sizes,
the accessibility audit result, and whether `virel check` passes. The
agent-trajectory metrics (output tokens, repair turns, wall-clock) come
from the harness that drives the model and are recorded per run.

```bash
python benchmarks/harness.py --solution path/to/solution --task data-table
```

## Release gates (SPEC 14.8)

These are gates, not marketing:

- At least 30% fewer developer-authored source tokens than a
  conventional Python-backend + TypeScript-frontend reference, for the
  median task.
- At least 25% fewer agent output tokens across successful trajectories.
- At least 25% fewer repair iterations.
- No statistically significant reduction in functional or visual
  correctness.
- Higher or equal accessibility correctness.
- Published prompts, models, versions, environments, and scoring logic.
