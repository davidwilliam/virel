"""Canonical patterns and agent context packs (SPEC 14.3, 14.6).

``ui.context_pack(...)`` (and ``virel context``) generate task-specific
compact documentation: the one recommended pattern for each requested
feature plus the schema of each requested component, trimmed to a token
budget. Canonical patterns (SPEC 14.6) name a single recommended way to
do each common task; the output carries only the API surface a task
needs, sized for an agent context window.
"""

from __future__ import annotations

from typing import Any

from .expr import VirelCompileError

# One recommended pattern per common task (SPEC 14.6). Each body is
# deliberately compact: the API surface an agent needs, nothing more.
_PATTERNS: dict[str, dict[str, Any]] = {
    "state": {
        "title": "Local reactive state",
        "body": '''count = ui.state(0)             # browser-local, typed by initial value
doubled = ui.derived(lambda: count * 2)
# Mutate only inside handlers: count.set(v) or count.update(fn).
# persist="key" survives reloads; url="q" syncs to a query param.''',
    },
    "server-actions": {
        "title": "Server actions",
        "body": '''@ui.server                      # a typed HTTP endpoint; runs in CPython
async def save(data: NoteInput) -> str:
    ...                          # validated against the model automatically
    return "saved"

# In a handler: save.call({"data": ...}, into=result, error_into=error)
# Stream with @ui.server(stream=True) and save.stream(into=text,
# done_set=(busy, False)). Safe retries: @ui.server(idempotent=True).''',
    },
    "forms": {
        "title": "Model-driven forms with validation",
        "body": '''@dataclass                      # or a Pydantic model or TypedDict
class InviteInput:
    email: str
    role: Literal["viewer", "editor", "admin"] = "viewer"

@ui.server
async def invite(data: InviteInput) -> str: ...

form = ui.form(InviteInput, submit=invite)   # browser + server validation
ui.Form(ui.TextField(form.email, label="Email"),
        ui.Select(form.role, label="Role"),
        ui.FormActions(ui.SubmitButton("Send", form=form)),
        ui.When(form.succeeded, then=ui.Alert(form.result, intent="success")),
        form=form)''',
    },
    "validation": {
        "title": "Validation",
        "body": '''# Form fields validate in the browser from the model types and again on
# the server. form.errors[field] holds server messages; ui.When(form.failed,
# ...) shows them. Never trust the client: @ui.server revalidates every call.''',
    },
    "dialog": {
        "title": "Dialog",
        "body": '''open = ui.state(False)
ui.Button("Open", on_click=lambda: open.set(True))
ui.Dialog(ui.Text("Body"),
          ui.Row(ui.Button("Done", on_click=lambda: open.set(False))),
          open=open, title="Confirm")   # native dialog: focus trap + Escape''',
    },
    "data-table": {
        "title": "Sortable, filterable data table",
        "body": '''ui.DataGrid(rows, key="id",           # rows: dicts, dataclasses, DataFrame
            columns=[ui.Column("model", "Model"),
                     ui.Column("score", "Score", kind="number")],
            filterable=True, page_size=20, selectable=True,
            on_selection=ui.set_from_event(chosen, "detail.keys"))
# Also: group_by=, aggregate={"score": "mean"}, Column(editable=True),
# virtual=True for large data, server=ui.grid_query(...) for server sorting.''',
    },
    "streaming": {
        "title": "Streaming AI chat",
        "body": '''@ui.server(stream=True)
async def complete(prompt: str):
    async for token in model(prompt):
        yield token

answer, busy = ui.state(""), ui.state(False)
def send():
    busy.set(True); answer.set("")
    complete.stream({"prompt": prompt}, into=answer, done_set=(busy, False))
ui.ai.Response(answer, streaming=busy)
ui.ai.PromptEditor(prompt, on_submit=send)''',
    },
    "file-upload": {
        "title": "File upload with progress",
        "body": '''files = ui.FileField(label="Attachments", multiple=True)
progress = ui.state(0)

@ui.server
async def receive(docs: list[ui.UploadFile]) -> str: ...

def submit():
    ui.upload(receive, files=files, progress_into=progress)
# progress is 0..100 during the transfer.''',
    },
    "navigation": {
        "title": "Navigation and routing",
        "body": '''@ui.page("/projects/{project_id}")     # path params -> typed arguments
def project(project_id: str, tab: str = "overview"): ...
# ui.Link(to="/x") navigates without a full reload. Query-param defaults
# become typed args. @ui.layout("/prefix") wraps a section.''',
    },
    "command-palette": {
        "title": "Accessible command palette",
        "body": '''ui.CommandPalette(commands=[
    ui.Command("Go to settings", to="/settings", hint="Navigation"),
    ui.Command("New run", on_run=lambda: creating.set(True)),
], hotkey="k")   # Ctrl/Cmd+K opens; typing filters; Enter runs.''',
    },
    "auth": {
        "title": "Authenticated pages (guards and context)",
        "body": '''current_user = ui.context("current_user")

def load_session(request: ui.Request):
    user = lookup(request.cookies.get("session"))
    if user is None:
        return ui.redirect("/login")
    current_user.provide(user)          # read later with current_user.get()

@ui.page("/settings", guard=load_session)
def settings(): ...''',
    },
    "theming": {
        "title": "Theming and design tokens",
        "body": '''ui.use_theme(ui.Theme(
    color={"accent": ui.Color.scale("#4f46e5")},
    typography={"body": ui.Font("Manrope", google=True)},
    brands={"acme": ui.Theme.preset("emerald")}))
# Switch at runtime in a handler: ui.set_preference("brand", "acme").
# System/light/dark ship by default; ui.ThemeToggle() cycles them.''',
    },
}

# Feature names pull in the patterns they need together.
_FEATURE_ALIASES = {
    "validation": ["forms", "validation"],
    "routing": ["navigation"],
    "streaming": ["streaming", "server-actions"],
    "uploads": ["file-upload", "server-actions"],
}

# Component name -> the pattern that best demonstrates it.
_COMPONENT_PATTERNS = {
    "form": "forms", "dialog": "dialog", "data-table": "data-table",
    "datagrid": "data-table", "command-palette": "command-palette",
    "chat": "streaming",
}

_PREAMBLE = '''# Virel context pack

Virel compiles typed, declarative Python to browser-native HTML, CSS, and
JS. One language, no Node.js, no separate frontend. A @ui.page function
runs once at compile time; ui.state values are reactive; handlers compile
to JavaScript; @ui.server functions are typed HTTP endpoints in CPython.
'''


def canonical_patterns() -> dict[str, str]:
    """The recommended pattern per task (SPEC 14.6), name to title."""
    return {key: value["title"] for key, value in _PATTERNS.items()}


def _estimate_tokens(text: str) -> int:
    # A rough ~4 chars/token proxy, so the budget is honored without a
    # tokenizer dependency.
    return (len(text) + 3) // 4


def context_pack(components: list[str] | None = None,
                 features: list[str] | None = None,
                 budget: int = 12000) -> str:
    """Task-specific compact documentation (SPEC 14.3): the canonical
    pattern for each feature plus the schema of each component, trimmed
    to the token budget."""
    from .schema import component_schema, list_components

    pattern_keys: list[str] = []

    def add_pattern(key: str) -> None:
        if key in _PATTERNS and key not in pattern_keys:
            pattern_keys.append(key)

    for feature in features or []:
        key = feature.strip().lower()
        resolved = _FEATURE_ALIASES.get(key, [key])
        if key not in _FEATURE_ALIASES and key not in _PATTERNS:
            raise VirelCompileError(
                f"Unknown feature {feature!r}. Known: "
                f"{', '.join(sorted(set(_FEATURE_ALIASES) | set(_PATTERNS)))}.")
        for resolved_key in resolved:
            add_pattern(resolved_key)

    known = {name.lower(): name for name in list_components()}
    resolved_components: list[str] = []
    for component in components or []:
        slug = component.strip().lower()
        if slug in _COMPONENT_PATTERNS:
            add_pattern(_COMPONENT_PATTERNS[slug])
        canonical = known.get(slug) or known.get(slug.replace("-", ""))
        if canonical:
            if canonical not in resolved_components:
                resolved_components.append(canonical)
        elif slug not in _COMPONENT_PATTERNS:
            raise VirelCompileError(f"Unknown component {component!r}.")

    sections: list[str] = [_PREAMBLE]
    if pattern_keys:
        block = ["## Patterns\n"]
        for key in pattern_keys:
            pattern = _PATTERNS[key]
            block.append(f"### {pattern['title']}\n\n```python\n"
                         f"{pattern['body']}\n```\n")
        sections.append("\n".join(block))
    if resolved_components:
        block = ["## Component reference\n"]
        for name in resolved_components:
            block.append(_schema_markdown(component_schema(name)))
        sections.append("\n".join(block))

    pack = ""
    truncated = False
    for section in sections:
        candidate = (pack + "\n" + section).strip()
        if _estimate_tokens(candidate) > budget and pack:
            truncated = True
            break
        pack = candidate
    if truncated:
        pack += (f"\n\n_Truncated to the {budget}-token budget; request "
                 "fewer components or features for full detail._")
    return pack + "\n"


def _schema_markdown(schema: dict[str, Any]) -> str:
    lines = [f"### {schema['name']}", ""]
    if schema.get("purpose"):
        lines.extend([schema["purpose"], ""])
    props = schema.get("props") or {}
    if props:
        lines.append("Props:")
        for name, info in props.items():
            suffix = " (required)" if info["required"] else \
                f" = {info['default']}" if info["default"] else ""
            lines.append(f"- `{name}`: {info['type']}{suffix}")
        lines.append("")
    if schema.get("events"):
        lines.extend(["Events: " + ", ".join(schema["events"]), ""])
    if schema.get("accessibility"):
        lines.extend([f"Accessibility: {schema['accessibility']}", ""])
    if schema.get("incompatibilities"):
        lines.extend(["Constraints: "
                      + "; ".join(schema["incompatibilities"]), ""])
    if schema.get("example"):
        lines.append(f"```python\n{schema['example']}\n```")
    return "\n".join(lines) + "\n"
