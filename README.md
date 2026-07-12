# Virel

[![CI](https://github.com/davidwilliam/virel/actions/workflows/ci.yml/badge.svg)](https://github.com/davidwilliam/virel/actions/workflows/ci.yml)

Professional interfaces, written in Python.

Virel is a compiler-first frontend framework. You write typed, declarative
Python; Virel compiles it to browser-native HTML, CSS, and JavaScript. CPython
stays on the server. The browser never downloads a Python interpreter.

The project follows the roadmap in [SPEC.md](SPEC.md). The architecture
validation phase is complete, and the current tree adds the first
developer-preview features: an AST-based client compiler for event handlers
and shared functions, model-driven forms with Pydantic and dataclass support,
a component library of around forty controls, system/light/dark theming by
default, component testing from pytest without a browser, and a development
inspector.

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
| `/` | Static landing, highlighted code, canonical URL, build-time data |
| `/counter` | Local state persisted across reloads, derived values |
| `/search` | URL-synchronized state, effects, a shared function |
| `/invite` | Model-driven form, server revalidation, idempotent action |
| `/components` | Full component gallery, islands, error boundaries |
| `/runs` | Streamed server rendering, cached resource, optimistic actions |
| `/files` | Multipart upload with progress, file download |
| `/stream` | Text streams, structured events, SSE, a WebSocket channel |
| `/widgets` | Web component bound via a generated typed binding |
| `/settings` | Nested layout, sidebar shell, request context from a guard |
| `/projects/{id}` | Dynamic route with typed query parameters |

The invite button stays disabled until you type an email address. That check
runs in the browser; the server revalidates on submit. The stream page reads
chunked HTTP from an async generator.

## CLI

```text
virel new <name>       scaffold an application
virel dev              development server with reload
virel build            build for a target: --target static | asgi
virel check            compile every route and report diagnostics
virel routes           list routes and rendering modes
virel inspect <route>  print the intermediate representation as JSON
virel schema <name>    print a component schema as JSON
virel bind <manifest>  generate typed bindings from custom-elements.json
```

`virel build --target static` fails with a precise, per-route report if
anything requires a server (dynamic parameters, server actions). It never
emits a site that looks static but breaks at runtime.

## Navigation

Same-origin link clicks navigate without a full page load: the router
fetches the target page, swaps the document, disposes the previous page's
reactive bindings, and mounts the new page module, with working history,
back and forward, scroll reset, and an `aria-current` marker on the active
nav link. Pages that compile per request (dynamic parameters or
server-rendered resources) fall back to a normal full load, and modified
clicks, downloads, external links, and fragment links are left to the
browser. Set `client_nav = false` under `[app]` in `virel.toml` to turn
soft navigation off.

`ui.Island` marks a hydration boundary inside a page: the subtree is
server-rendered and visible immediately, but its bindings activate lazily
with `load="immediate"`, `"idle"`, `"visible"`, or `"interaction"`, so
below-the-fold interactivity costs nothing at page load.

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
  -> runtime        signals, router, resources (~4.6 KB gzip)   src/virel/assets/runtime.js
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
- Security is a tenet. Escaping is automatic in every
  rendering context; raw HTML requires an explicit call with a written
  reason. URLs are scheme-checked so data cannot inject javascript: links.
  HTML responses carry a content security policy that allows only
  same-origin scripts plus the compiler's own inline scripts by hash.
  Server actions accept JSON only, validate every payload, reject
  cross-site browser requests, and cap body size. See
  [SECURITY.md](SECURITY.md) for the full list of guarantees.
- Accessibility violations the compiler can detect are errors, not warnings.
  An image without alt text or an icon-only button without an accessible
  label will not compile.

## Guards

Pages and server actions take guards: functions (sync or async) that run
per request before anything is compiled or invoked. A guard returns None
to allow, `ui.redirect(path)` for a same-origin redirect (external targets
are compile errors), or `ui.deny(status, message)`:

```python
def require_session(request: ui.Request):
    if request.cookies.get("session") != "valid":
        return ui.redirect("/login")

@ui.page("/admin", guard=require_session)
def admin() -> ui.Node: ...

@ui.server(guard=require_session)
def delete_project(project_id: str) -> str: ...
```

`ui.use_guard(fn)` installs a default guard ahead of every route-specific
one. Guards see the method, path, headers, query, and cookies. For JSON
action calls a redirect decision becomes a 401 with the redirect target in
the body, and guarded routes are reported as server dependencies by the
static build.

Guards hand values to pages through typed request context:

```python
current_user = ui.context("current_user")

def load_session(request: ui.Request):
    user = sessions.lookup(request.cookies.get("session"))
    if user is None:
        return ui.redirect("/login")
    current_user.provide(user)

@ui.page("/dashboard", guard=load_session)
def dashboard() -> ui.Node:
    user = current_user.get()
    return ui.Page(ui.Text(f"Hello {user['name']}"))
```

A page reading a request-provided value compiles per request and is never
cached; reading a declared default keeps the page static-friendly. Tests
supply values with `ui.test.render(page, context={...})`.

## Forms

One model drives the whole form: field states, input types, native browser
constraint attributes, server revalidation, and per-field error display.
Pydantic models and plain dataclasses both work; Pydantic is optional and
detected at runtime.

```python
from dataclasses import dataclass
from typing import Literal
from virel import ui

@dataclass
class InviteInput:
    email: str
    role: Literal["viewer", "editor", "admin"] = "viewer"

@ui.server
async def invite_member(data: InviteInput) -> str:
    return f"Invitation sent to {data.email} as {data.role}."

@ui.page("/invite")
def invite() -> ui.Node:
    form = ui.form(InviteInput, submit=invite_member)
    return ui.Page(
        ui.Form(
            ui.TextField(form.email, label="Email"),
            ui.Select(form.role, label="Role"),
            ui.FormActions(ui.SubmitButton("Send invitation", form=form)),
            ui.When(form.succeeded, then=ui.Alert(form.result, intent="success")),
            form=form,
        ),
    )
```

The email field renders as `<input type="email" required>`, so the browser
blocks bad submissions before any network traffic. The server validates the
payload against the same model on every request and returns structured,
field-scoped errors that appear under the matching inputs. Nothing is
serialized except JSON.

## Theming

Every application supports three color-scheme modes out of the box: system
(follow the OS), light, and dark. Design tokens compile to CSS custom
properties for each mode, a tiny inline snippet applies the stored
preference before first paint so switching never flashes, and
`ui.ThemeToggle()` gives users a control that cycles the modes and persists
the choice.

Colors are typed scales: give a role one base color and every derived
token follows, including a readable foreground, hover shades, subtle
tints for each mode, and focus rings. A scale can flip between modes
(`ui.Color.scale("#18181b", dark="#fafafa")` is how the monochrome look
gets a near-black accent in light mode and a white one in dark mode).
Organization brands and tenant themes are complete themes selected at
runtime, and density modes rescale the spacing unit every component is
built on:

```python
ui.use_theme(ui.Theme(
    color={"accent": ui.Color.scale("#4f46e5"), "surface": "#7c8db5"},
    space=ui.Space.scale(base=4),
    typography={"body": ui.Font("Manrope", google=True)},
    brands={"acme": ui.Theme(color={"accent": "#059669"})},
))
```

Six looks ship built in: `ui.Theme.preset("indigo")` (the default),
`"mono"` (black and white), `"emerald"`, `"blue"`, `"rose"`, and
`"amber"`. A preset is an ordinary theme: use one as the application
theme, register several as brands, or start from one and override
fields.

Handlers switch any preference at runtime with
`ui.set_preference("brand", "acme")` (likewise `theme`, `density`, and
`contrast`); the choice persists in the browser and is restored before
first paint, so nothing flashes on reload. High contrast also engages
automatically for users whose system requests it, and animations collapse
under reduced-motion preferences.

The default typeface is Inter (bundled, self-hosted). `ui.Font(...,
google=True)` loads from Google Fonts with the stylesheet link and content
security policy handled automatically; `ui.Font(..., src=...)` registers
font files the project serves itself. The lower-level `ui.GoogleFont` and
`ui.FontFace` entries remain available on `Theme(fonts=[...])`.

## Loading data

`ui.resource` turns a server action into a reactive value with loading and
error states. The browser fetches on page load, refetches when a reactive
parameter changes (identical in-flight requests are deduplicated), and any
handler can force a refresh. `ui.Each` renders lists from the data and
`ui.Suspense` handles the loading and error states:

```python
@ui.server
async def list_runs(query: str = "") -> list[dict]:
    return await repository.runs.search(query)

@ui.page("/runs")
def runs_page() -> ui.Node:
    query = ui.state("")
    runs = ui.resource(list_runs, params={"query": query})

    return ui.Page(
        ui.TextField(query, label="Filter"),
        ui.Button("Refresh", on_click=lambda: runs.refresh()),
        ui.Suspense(
            runs,
            content=ui.Each(runs.value,
                            render=lambda run: ui.Text(f"{run.name}: {run.score}")),
            fallback=ui.Skeleton(),
        ),
    )
```

Handlers can update state optimistically: the state changes immediately,
the server result replaces it on success, and a rejected call restores the
captured previous value before the error surfaces:

```python
mark_done.call({"id": task.id}, into=status,
               optimistic=(status, "done"), error_into=error)
```

Fetched values are cached by action and arguments, and the cache survives
soft navigation: returning to a page shows its data instantly. With
`stale_for=30`, entries younger than 30 seconds skip the network entirely,
and older entries render immediately while revalidating in the background,
so lists update without loading flashes.

Pass `server_render=True` and the initial data is fetched during server
rendering instead: the page arrives populated, the browser skips the first
fetch, and the route is compiled per request. Item data is HTML-escaped on
both the server and the client, and values embedded during server rendering
are encoded so they cannot break out of the surrounding script context.

Each templates are data-only for now: elements inside an item cannot carry
event handlers yet, and `ui.When` inside an item is a compile error that
points to `ui.cond`.

## Internationalization

Message catalogs are dictionaries per locale, and `ui.t` resolves at
compile time, so each locale gets its own compiled page with translated
static HTML and its own page module:

```python
ui.messages("en", {"greeting": "Hello {name}",
                   "runs": {"one": "{count} run", "other": "{count} runs"}})
ui.messages("pt", {"greeting": "Ola {name}",
                   "runs": {"one": "{count} execucao", "other": "{count} execucoes"}})

ui.Text(ui.t("greeting", name=user_name))
ui.Text(ui.t("runs", count=total))
```

Placeholders accept reactive values, in which case the translation compiles
to a reactive expression (plurals become a ternary over the count) and
updates in the browser. Missing keys and missing placeholders are compile
errors; locales fall back to the default for untranslated keys. The server
negotiates the locale from Accept-Language with a `?lang=` override and a
`Vary` header; apps without catalogs skip all of this.

Numbers, currencies, percentages, and dates format for the active locale:
`ui.format_number`, `ui.format_currency`, `ui.format_percent`, and
`ui.format_date` render static values at compile time with built-in rules
for common locales, and compile reactive values to Intl calls that run in
the browser with full locale data.

## Components

The library covers the essentials in four groups, all with accessibility
built in:

- Layout and chrome: `Stack`, `Row`, `Grid`, `Wrap`, `Cluster`, `Center`,
  `Sidebar` (aside plus fluid content, stacking without media queries),
  `AspectRatio`, `ScrollArea`, `Resizable`, `Splitter` (draggable,
  keyboard-operable panes), `Container`, `Section`, `Card`, `AppShell`
  (with optional sidebar that becomes an off-canvas drawer on small
  screens, and footer), `Footer`, `Hero`, `Divider`, `Spacer`
- Form controls: `Button`, `TextField`, `Textarea`, `NumberField`, `Select`,
  `DateField` (platform date/time/datetime pickers, zero JS), `Checkbox`,
  `Switch`, `RadioGroup`, `Slider`
- Interaction patterns: `Tabs`, `Dialog` (on the native dialog element),
  `Menu`/`MenuItem`/`MenuDivider` (accessible dropdowns with keyboard
  navigation and flip-up placement), `Popover` (anchored non-modal panel
  with focus management), `Accordion` (on details/summary), `Tooltip`,
  `Swipeable`, `When`
- Data display and status: `Table`, `Stat`, `Progress`, `Spinner`,
  `Skeleton`, `Avatar`, `Badge`, `Alert`, `Breadcrumbs`, `EmptyState`,
  `Pagination` (state-driven buttons or server-rendered windowed links),
  `Icon` (a built-in inline SVG set), plus `ui.notify` toasts raised from
  any handler into a polite live region

`ui.Code` highlights source at compile time using theme-aware token colors,
so code blocks ship as plain HTML spans with no client JavaScript:

```python
ui.Code(snippet, block=True, language="python")
```

Run `virel schema <Name>` for the machine-readable schema of any component.

Reusable styles are typed objects compiled to shared classes in the
application stylesheet. Spacing takes theme space units and colors,
radii, and shadows take token names, so a style follows the theme,
brands, and density modes; `hover=`, `focus=`, and `active=` add state
variants. Anything accepting `class_name` accepts a style object:

```python
card_style = ui.style(padding=6, radius="lg", background="surface.1",
                      border="subtle", hover={"shadow": "md"})
ui.Stack(..., class_name=card_style)
```

Styles adapt without JavaScript (SPEC 10.7): `md=` and `xl=` vary
properties by the same viewport breakpoints Grid uses,
`pointer_coarse=`/`pointer_fine=` adapt to input capability, and
`container_min={"24rem": {...}}` applies container queries against the
nearest ancestor declaring `container=True`. Framework defaults handle
the rest: tap targets grow to 44px on coarse pointers, headings scale
with the viewport within bounds, and the app chrome respects safe-area
insets on notched devices.

Recipes build variants on top of style objects: each axis becomes a
typed keyword argument on the returned component, validated against the
declared options, with everything else passing through to the base:

```python
ProjectCard = ui.recipe(
    base=ui.Card,
    variants={"status": {"active": {"border": "accent"},
                         "paused": {"background": "surface.2"}}},
    defaults={"status": "active"},
)
ProjectCard(ui.Text("Atlas"), status="paused")
```

When the typed API is not enough, `ui.Box` is the CSS escape hatch: raw
declarations, including custom properties, validated and emitted as a
normal inline style so they stay compatible with standard CSS concepts and
browser development tools:

```python
ui.Box(chart, class_name="specialized-visualization",
       css={"container-type": "inline-size", "--plot-density": 0.8})
```

The rules a `class_name` refers to live in `ui.use_css`, which registers
raw CSS compiled into `app.css` after everything else, so it can express
what inline declarations cannot (pseudo-elements, container queries,
keyframes) and override any default.

## Animation

Everything compiles to real CSS animations and transitions: no animation
loop ships in the runtime, the compositor does the work, and the
browser's native Animations devtools panel inspects every timeline.
Spring physics is simulated in Python at compile time and emitted as a
CSS `linear()` easing curve, so springs cost zero JavaScript per frame:

```python
pulse = ui.keyframes({"0%": {"opacity": 1}, "50%": {"opacity": 0.4},
                      "100%": {"opacity": 1}})
ui.style(animation=ui.animation(pulse, duration=1200, iterations="infinite"),
         transition=ui.transition("transform",
                                  easing=ui.spring(stiffness=280, damping=14)))
```

Enter and exit animation attaches to conditional content and lists;
`layout=True` adds FLIP animation, so reordered items glide to their new
positions while removed items freeze in place and fade out:

```python
ui.When(show, then=panel, animate=ui.Motion(enter="fade-up", exit="fade"))
ui.Each(tasks, render=row, key=..., animate=ui.Motion(
    enter="slide-right", exit="fade", layout=True))
```

`ui.Swipeable` adds gestures: content follows the pointer, springs back
below the threshold, and slides away firing `on_dismiss` past it, with
Delete-key parity for keyboard users. Reduced motion collapses every
animation to instant by default; `ui.animation(..., essential=True)`
exempts motion that conveys state (progress, live indicators), and
`ui.Motion(reduced="none")` removes an animation entirely for those
users. Animations run in the browser and generate no server traffic.

Third-party web components integrate through typed bindings generated from
their custom elements manifests (`virel bind`), and static assets that live
outside the project's public directory, such as a vendored package or files
shipped inside an installed Python package, are mounted with
`ui.use_static("/vendor/widgets", path)`. The dev server, the ASGI app, and
`virel build` all serve the mounted directory at that prefix. The demo binds
to the stand-in vendor package in `examples/third-party-widgets` this way.

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

## Development

The whole check suite lives in one script, and CI runs exactly that script,
so a local pass means CI will pass:

```bash
source .venv/bin/activate
./scripts/ci            # tests, demo build, scaffold build

./scripts/ci 3.11       # same, in a throwaway venv on another Python

./scripts/ci browser    # real-browser suite (headless Chromium)
```

The default suite is dependency-free and fast; component behavior is tested
in pure Python. The browser suite is a separate layer that verifies what
only a real engine can: custom element upgrades, shadow DOM rendering, and
client-side navigation. It installs the `browser` extra (Playwright) and a
managed Chromium on first run.

Continuous integration runs the default script on Python 3.11 through 3.14
plus the browser suite for every push to main and every pull request. Day-to-day work goes directly to main;
breaking or risky changes are developed on a branch and merged only after
the checks pass.

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

The rendering architecture from the specification's section 9 is complete:
the compiler pipeline with hashed assets, the versioned IR, the signals
runtime, the ASGI server with mounting and middleware, HTTP, SSE, and
WebSocket transports, all six rendering modes including progressive
streaming, hydration islands with five load strategies, and precise static
build failures.

The programming model from the specification's section 8 is now complete:
components, reactive state with persistence and URL adapters, effects,
control flow, execution zones (client, server, build, shared), context,
resources with caching, retry, invalidation, and streaming, server actions
with optimistic mutation, idempotency, uploads, and downloads, model-driven
forms, routing with layouts, guards, and typed parameters, error
boundaries, and structured streaming.

Not implemented yet: right-to-left layout support, locale-aware collation,
the data grid and visualization adapters, the AI component package, and
observability.

## License

MIT. See [LICENSE](LICENSE). The bundled Inter font is licensed under the
SIL Open Font License; see `src/virel/assets/fonts/LICENSE.txt`.
