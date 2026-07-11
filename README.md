# Virel

Professional interfaces, written in Python.

Virel is a compiler-first frontend framework. You write typed, declarative
Python; Virel compiles it to browser-native HTML, CSS, and JavaScript. CPython
stays on the server. The browser never downloads a Python interpreter.

The project follows the roadmap in [SPEC.md](SPEC.md). The architecture
validation phase is complete, and the current tree adds the first
developer-preview features: an AST-based client compiler for event handlers
and shared functions, a component library of around forty controls, component
testing from pytest without a browser, and a development inspector.

```python
from virel import ui

@ui.page("/")
def home() -> ui.Node:
    count = ui.state(0)

    return ui.Page(
        ui.Stack(
            ui.Heading("Hello from Python", level=1),
            ui.Text(f"Count: {count}"),
            ui.Button("Increment",
                      on_click=lambda: count.update(lambda c: c + 1),
                      intent="primary"),
        ),
        title="Virel",
    )
```

This page compiles to static HTML with the initial value already rendered,
plus a page module of about 230 bytes that wires up fine-grained updates.
Clicking the button changes exactly one DOM text node. There is no virtual
DOM, no server round trip for local interaction, and no WebSocket.

## Getting started

Virel has no dependencies beyond Python 3.11+. No Node.js is required.

```bash
git clone git@github.com:davidwilliam/virel.git
cd virel
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

virel new my_app
cd my_app
virel dev
```

Then open http://127.0.0.1:8000.

## The demo application

The example under `examples/demo` exercises everything the prototype can do:

```bash
cd examples/demo
virel dev
```

| Route | What it shows |
|---|---|
| `/` | Static landing page, ships zero framework JavaScript |
| `/counter` | Local state, derived values, conditional rendering |
| `/search` | Two-way input binding, `ui.derived`, `ui.When` |
| `/invite` | Form with a control-flow handler and a typed server action |
| `/components` | Gallery: tabs, dialog, switches, tables, icons, and more |
| `/stream` | Streaming server action rendered incrementally |
| `/widgets` | Third-party web component through a typed binding |
| `/projects/{id}` | Server-rendered dynamic route with query parameters |

The invite button stays disabled until you type an email address. That check
runs in the browser; the server revalidates on submit. The stream page reads
chunked HTTP from an async generator, not a WebSocket.

## CLI

```text
virel new <name>       scaffold an application
virel dev              development server with reload
virel build            build for a target: --target static | asgi
virel check            compile every route and report diagnostics
virel routes           list routes and rendering modes
virel inspect <route>  print the intermediate representation as JSON
virel schema <name>    print a component schema as JSON
```

`virel build --target static` fails with a precise, per-route report if
anything requires a server (dynamic parameters, server actions). It never
emits a site that looks static but breaks at runtime.

## How it works

A page function runs once at compile time under a trace context. Reactive
values created with `ui.state()` and `ui.derived()` are symbolic: operations
on them build expression trees instead of computing values. Each tree is then
emitted twice. It is evaluated in Python to produce the server-rendered
initial HTML, and compiled to JavaScript for fine-grained updates in the
browser.

Event handlers come in two forms. A lambda is traced symbolically, which
suits one-liners like `on_click=lambda: count.set(0)`. A named function goes
through the AST client compiler and may use real control flow:

```python
def submit() -> None:
    result.set("")
    error.set("")
    if len(email.strip()) < 3:
        error.set("Enter an email address first.")
    else:
        invite_member.call({"email": email, "role": role},
                           into=result, error_into=error)

ui.Button("Send invitation", on_click=submit, intent="primary")
```

The `if` compiles to JavaScript and runs in the browser; the server action is
an HTTP call. Pure helpers can be shared with `@ui.client`, which compiles
the function to JavaScript once and keeps it callable as ordinary Python on
the server and in tests:

```python
@ui.client
def shout(value: str) -> str:
    trimmed = value.strip()
    if len(trimmed) == 0:
        return ""
    return trimmed.upper() + "!"
```

```
Python source
  -> trace          page function runs under a TraceContext     src/virel/expr.py
  -> UI IR          versioned, deterministic, serializable      src/virel/nodes.py
  -> emission       initial HTML + per-page JS module           src/virel/compiler.py
  -> runtime        signals, bindings, HTTP actions (~3.4 KB)   src/virel/assets/runtime.js
  -> server         ASGI app + built-in dev HTTP bridge         src/virel/server.py
```

Some consequences of this design:

- Execution zones are explicit. Pages trace at compile or render time,
  `@ui.server` functions run in CPython, and event handlers compile to
  browser JavaScript. Code never silently moves across that boundary.
- Unsupported constructs fail at build time with the fix named. Using a
  reactive value in a Python `if`, for example, is a compile error that
  points you to `ui.When` or `ui.cond`.
- The server is stateless. UI state lives in the browser; server actions are
  plain HTTP endpoints with schema validation, so the app scales horizontally
  without sticky sessions.
- Everything is inspectable. `virel inspect` prints the IR, `dist/` contains
  readable HTML and JavaScript, and each build writes the IR for every route
  to `.virel/ir/`.
- Escaping is automatic. Raw HTML requires an explicit call with a written
  reason. Serialization is JSON only. Responses carry sensible security
  headers.
- Accessibility violations the compiler can detect are errors, not warnings.
  An image without alt text or an icon-only button without an accessible
  label will not compile.

## Components

The library covers the essentials in four groups, all with accessibility
built in:

- Layout: `Stack`, `Row`, `Container`, `Section`, `Card`, `AppShell`,
  `Divider`, `Spacer`
- Form controls: `Button`, `TextField`, `Textarea`, `NumberField`, `Select`,
  `Checkbox`, `Switch`, `RadioGroup`, `Slider`
- Interaction patterns: `Tabs`, `Dialog` (on the native dialog element),
  `Accordion` (on details/summary), `Tooltip`, `When`
- Data display and status: `Table`, `Stat`, `Progress`, `Spinner`,
  `Skeleton`, `Avatar`, `Badge`, `Alert`, `Breadcrumbs`, `EmptyState`,
  `Icon` (a built-in inline SVG set)

Run `virel schema <Name>` for the machine-readable schema of any component.

## Testing

Component tests run from pytest without a browser. Queries follow
accessibility semantics, and interactions execute the same compiled handler
operations that would run as JavaScript, including real server-action calls:

```python
from virel import ui

def test_invitation_flow():
    view = ui.test.render(invite_page)
    view.get_by_label("Email").fill("person@example.com")
    view.get_by_label("Role").select("editor")
    view.get_by_role("button", name="Send invitation").click()
    assert view.get_by_text("Invitation sent to person@example.com "
                            "as editor.").is_visible()
```

Hidden elements cannot be interacted with, disabled buttons refuse clicks,
and streaming actions are drained synchronously, so tests stay deterministic.

Run the framework's own suite with:

```bash
python -m pytest
```

## Inspector

In `virel dev`, every page gets a small floating button (or Alt+V) that opens
the inspector: the compiled component tree with source locations, the
intermediate representation, and live signal values read from the running
page.

## Current scope

The supported client subset is documented and deliberately bounded:
arithmetic, comparisons, boolean operators, conditional expressions,
f-strings, list literals and indexing, a set of string methods, common
builtins (`len`, `str`, `int`, `float`, `bool`, `abs`, `min`, `max`,
`round`), assignments, `if`/`elif`/`else`, `for` over lists, and calls to
`@ui.client` functions and server actions. Anything outside it is a build
error that names the nearest replacement.

Not implemented yet, in rough priority order: model-driven forms with
Pydantic integration, the `ui.resource` data layer with caching and suspense,
client-side routing and partial hydration, `virel bind` for npm packages, and
internationalization.

## License

MIT. See [LICENSE](LICENSE).
