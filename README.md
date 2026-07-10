# Virel

Professional interfaces, written in Python.

Virel is a compiler-first frontend framework. You write typed, declarative
Python; Virel compiles it to browser-native HTML, CSS, and JavaScript. CPython
stays on the server. The browser never downloads a Python interpreter.

This repository currently contains the Phase 0 prototype described in
[SPEC.md](SPEC.md): the smallest end-to-end implementation that validates the
architecture before the framework grows real surface area.

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
| `/invite` | Form calling a typed server action, structured errors |
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

## Scope of the prototype

Phase 0 validates architecture, not breadth. The supported reactive subset is
small: arithmetic, comparisons, a documented set of string methods, f-strings,
and the `ui.cond` / `ui.When` / `ui.length` helpers. Event handlers are traced
symbolically, so Python control flow inside a handler is not supported yet;
that requires the AST-based client compiler planned for Phase 1.

Not implemented yet, in rough priority order: model-driven forms with Pydantic
integration, the `ui.resource` data layer with caching and suspense, client
routing and partial hydration, the component library beyond the current
essentials, `virel bind` for npm packages, internationalization, and the
browser inspector.

## Tests

```bash
python -m pytest
```

The suite covers the expression compiler, page compilation and IR output,
server actions (validation, errors, streaming), and the build targets.

## License

MIT. See [LICENSE](LICENSE).
