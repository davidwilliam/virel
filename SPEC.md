# Virel: Professional Interfaces in Pure Python

**Document:** `SPEC.md`  
**Status:** Product and architecture proposal  
**Version:** 0.1  
**Proposed package:** `virel`  
**Tagline:** Professional interfaces, written in Python.  
**Name expansion:** Visual Interface Rendering and Expression Layer  
**Naming note:** “Virel” is a working name and must receive formal package, domain, and trademark clearance before public launch.

## 1. Executive Summary

Virel is a compiler-first frontend framework that enables Python developers to build professional web interfaces without authoring JavaScript, TypeScript, JSX, HTML, or CSS for ordinary application development.

The developer writes typed, declarative Python. Virel compiles that Python into optimized browser-native HTML, CSS, and JavaScript, while preserving direct access to the Python ecosystem for server-side logic, data processing, machine learning, and application services.

Virel is designed for:

- Python developers who need to build complete, polished products rather than temporary dashboards.
- ML, AI, data, scientific, and backend engineers who should not need to adopt a second application stack to deliver excellent interfaces.
- Product teams that want one primary language, one type system, one testing culture, and one dependency workflow.
- Coding agents that benefit from a compact, deterministic, strongly typed, machine-readable UI API.

The product promise is not merely “build a UI in Python.” Existing tools already demonstrate versions of that proposition. Virel’s stronger promise is:

> A Python developer can build a fast, accessible, responsive, secure, scalable, designer-quality web product using Python as the sole application authoring language, without surrendering browser-native performance, frontend capability, deployment flexibility, or escape hatches.

Virel is a framework, compiler, runtime, component system, design system, testing toolkit, and CLI distributed as a coherent Python developer experience.

## 2. Product Thesis

Python is already the operating language of a large portion of AI, ML, data science, automation, backend services, and scientific computing. Yet shipping a professional interactive product commonly requires a separate frontend stack, separate package manager, separate build system, separate type system, separate framework conventions, and often a separate team.

This division creates avoidable costs:

1. **Language switching:** Developers move between Python, TypeScript, JSX, HTML, CSS, framework configuration, and API schemas.
2. **Duplicated models:** Types and validation rules are recreated across frontend and backend boundaries.
3. **Integration overhead:** Application logic, data models, authentication, transport, serialization, and error handling must be connected manually.
4. **Higher agent cost:** Coding agents must retrieve and reason across multiple ecosystems, generate more boilerplate, and repair more integration failures.
5. **Prototype traps:** Python-first UI tools can be excellent for demonstrations or internal applications but may become limiting when teams require refined design, browser-native behavior, advanced interaction, accessibility, SEO, scale, or frontend ecosystem interoperability.
6. **Operational complexity:** Development, testing, packaging, and deployment frequently depend on unrelated toolchains.
7. **Talent fragmentation:** Python specialists may know the product domain deeply but remain dependent on frontend specialists for routine product delivery.

Virel should eliminate these costs without pretending that the web does not exist. It should translate web concepts into a coherent Python API rather than hide them behind a simplistic abstraction that becomes restrictive under professional use.

## 3. Differentiated Position

The category already includes Python tools for dashboards, data applications, browser UIs, full-stack applications, and cross-platform interfaces. Virel must therefore compete on a stricter standard.

Virel is:

- **Frontend-first**, not dashboard-first.
- **Compiler-first**, not remote-widget-first.
- **Browser-native by default**, not dependent on a Python interpreter in every browser session.
- **Local-state-first**, not dependent on a server round trip for ordinary interaction.
- **Stateless-server-first**, not dependent on per-user Python objects held in server memory.
- **Design-system-native**, not a thin wrapper around unstructured styling utilities.
- **Accessible by construction**, not accessible only after manual remediation.
- **Typed across boundaries**, not loosely serialized.
- **Deploy-anywhere**, not dependent on a proprietary hosting service.
- **Agent-native**, not merely documented for humans.
- **Extensible through web standards**, not confined to a closed component catalog.
- **Suitable for public products**, not limited to internal tools.
- **Progressively adoptable**, not necessarily an all-or-nothing application rewrite.

The closest strategic analogy is not “Streamlit with more components.” It is “a Python-native frontend platform with the professional ambition of a modern TypeScript framework.”

## 4. Goals

### 4.1 Primary Goals

Virel must allow a Python developer to:

1. Build production-grade responsive web applications using Python as the only required authoring language.
2. Create refined interfaces using accessible components, design tokens, responsive layouts, animation, forms, navigation, data visualization, and advanced interaction.
3. execute low-latency UI behavior directly in the browser.
4. Call Python services and use Python libraries without manually designing a frontend API layer for ordinary use cases.
5. deploy as:
   - a static website,
   - a client-rendered application,
   - a server-rendered application,
   - a Python ASGI application,
   - a hybrid application with static, client, and server-rendered routes,
   - a progressive web application.
6. scale horizontally without requiring sticky sessions or per-user server state by default.
7. integrate third-party web components and JavaScript packages through typed Python bindings.
8. test components and complete browser flows from `pytest`.
9. preserve accessibility, security, observability, and performance as framework defaults.
10. give coding agents a smaller, more deterministic problem space than a conventional multi-language frontend stack.

### 4.2 Secondary Goals

Virel should:

- Provide excellent notebook previews without creating a separate “notebook application” programming model.
- Integrate naturally with Pydantic, dataclasses, FastAPI, Starlette, Django, NumPy, pandas, Polars, Arrow, Plotly, Altair, PyTorch, and common model-serving libraries.
- Support self-hosted, private-cloud, VPC, on-premises, and air-gapped deployment.
- Produce inspectable and exportable standard web assets.
- Support application templates for AI products, SaaS products, internal systems, analytics products, public websites, and documentation.
- Permit design teams to define organization-wide themes and component recipes.
- Support incremental adoption inside existing web applications.

### 4.3 Non-Goals for Version 1.0

Virel 1.0 will not attempt to:

- Replace Python backend frameworks.
- Run arbitrary CPython code in the browser.
- Guarantee that every Python package works client-side.
- Create native iOS, Android, macOS, Windows, or Linux widgets.
- Replace professional product design.
- Provide a drag-and-drop low-code application builder.
- conceal all browser concepts.
- duplicate every package in the JavaScript ecosystem.
- require Virel Cloud or any proprietary service.
- generate interfaces from prompts as its primary programming model.
- support every Python syntax construct inside client-compiled functions.
- make token savings, performance, or coding-agent accuracy claims without benchmark evidence.

Web and PWA quality take priority over premature cross-platform breadth.

## 5. Target Users

### 5.1 Primary Personas

#### AI and ML Engineer

Needs to build model playgrounds, evaluation systems, annotation tools, streaming inference interfaces, experiment dashboards, multimodal inputs, model configuration forms, and customer-facing AI features.

#### Data and Scientific Developer

Needs interactive exploration, large tables, charts, filters, file workflows, domain-specific visualizations, and production deployment without rewriting analysis logic in another language.

#### Python Backend Engineer

Needs to deliver complete web products without maintaining a separate TypeScript codebase and duplicated schemas.

#### Small Product Team

Needs a coherent stack that a limited engineering team can own from database to interface.

#### Enterprise Platform Team

Needs reusable design systems, access controls, predictable releases, supply-chain controls, observability, private deployment, and long-term API stability.

#### Coding Agent

Needs concise API context, deterministic component signatures, machine-readable contracts, high-quality error feedback, and a limited number of canonical solutions.

### 5.2 Secondary Personas

- Educators and students.
- Automation engineers.
- Security and compliance engineers.
- Researchers publishing interactive demonstrations.
- Existing Python framework users who need greater frontend depth.
- Frontend teams that want to expose approved components to Python teams.

## 6. Design Principles

### 6.1 Python Is the Authoring Language, Not Necessarily the Browser Runtime

Developers write Python. Virel compiles appropriate code to browser-native assets. CPython remains the server runtime. A Python interpreter is not downloaded into the browser unless a developer explicitly selects an optional browser-Python execution mode for a specialized use case.

### 6.2 Make Execution Location Explicit

Every operation must have an understandable execution location:

- browser,
- server,
- build time,
- or shared pure logic.

The framework must not silently move expensive or sensitive operations across trust boundaries.

### 6.3 Local Interaction Must Remain Local

Opening a menu, typing into a field, filtering a local list, changing tabs, validating a simple field, dragging an item, or playing an animation must not require a server round trip.

### 6.4 Professional Defaults, Complete Escape Hatches

The default path should produce excellent results. Advanced users must still be able to use:

- semantic HTML,
- raw CSS,
- CSS variables,
- web components,
- browser APIs,
- third-party JavaScript packages,
- custom build plugins,
- custom transport,
- and carefully isolated raw JavaScript when no typed binding is practical.

Escape hatches must be explicit, auditable, and uncommon.

### 6.5 Accessibility Is a Correctness Property

Keyboard access, focus management, labels, semantic roles, contrast, reduced motion, and screen-reader behavior are part of component correctness.

### 6.6 Design Systems Before Styling Fragments

Applications should be built from tokens, semantic roles, variants, recipes, and layout primitives. Arbitrary one-off styling remains possible but is not the primary path.

### 6.7 Static Where Possible, Dynamic Where Necessary

Virel should produce static HTML and CSS whenever possible, hydrate only interactive regions, and load server connectivity only for features that need it.

### 6.8 No Mandatory Per-User Server Object Graph

Server actions should be stateless by default. Shared and durable state should live in explicit stores, databases, caches, queues, or collaboration services.

### 6.9 One Obvious Canonical API

Synonyms, hidden magic, and multiple equivalent component patterns increase documentation burden and agent uncertainty. Virel should favor a compact, orthogonal, composable API.

### 6.10 Errors Must Explain the Repair

Compiler and runtime errors must identify:

- what is wrong,
- where it is wrong,
- which execution boundary is involved,
- why the construct is unsupported,
- the nearest valid replacement,
- and, where safe, an automatically applicable fix.

### 6.11 Generated Output Must Be Inspectable

Developers must be able to inspect the UI tree, compiled assets, CSS tokens, network messages, action traces, dependencies, bundle composition, and source mappings.

### 6.12 Deployment Is a Property of the Code, Not the Vendor

A Virel application must remain deployable without a commercial Virel service.

## 7. Proposed Developer Experience

### 7.1 Installation

```bash
uv add virel
```

or:

```bash
pip install virel
```

Create an application:

```bash
virel new my_app
cd my_app
virel dev
```

No separate Node.js installation should be required for normal development. The Virel toolchain may internally bundle a JavaScript/CSS bundler, but that toolchain is managed as part of Virel.

### 7.2 Minimal Application

```python
from virel import ui


@ui.page("/")
def home() -> ui.Node:
    count = ui.state(0)

    return ui.Page(
        ui.Stack(
            ui.Heading("Hello from Python", level=1),
            ui.Text(f"Count: {count}"),
            ui.Button(
                "Increment",
                on_click=lambda: count.set(count + 1),
                intent="primary",
            ),
            gap=4,
            align="start",
        ),
        title="Virel",
    )
```

The compiler recognizes reactive values used in expressions and emits the minimum browser update required when `count` changes.

### 7.3 A Production-Oriented Example

```python
from pydantic import BaseModel, EmailStr
from virel import ui


class InviteInput(BaseModel):
    email: EmailStr
    role: str


class Member(BaseModel):
    id: str
    email: EmailStr
    role: str


@ui.server
async def list_members() -> list[Member]:
    return await repository.members.list()


@ui.server
async def invite_member(data: InviteInput) -> Member:
    return await repository.members.invite(data)


@ui.component
def member_table(members: list[Member]) -> ui.Node:
    return ui.DataTable(
        rows=members,
        columns=[
            ui.Column("Email", value=lambda member: member.email),
            ui.Column("Role", value=lambda member: member.role),
        ],
        empty=ui.EmptyState(
            title="No members",
            description="Invite the first member to this workspace.",
        ),
    )


@ui.page("/settings/members")
def members_page() -> ui.Node:
    members = ui.resource(list_members, cache="workspace")
    form = ui.form(InviteInput, submit=invite_member)

    return ui.AppShell(
        navigation=app_navigation(),
        content=ui.Section(
            ui.Row(
                ui.Heading("Members", level=1),
                ui.Dialog.trigger(
                    ui.Button("Invite member", intent="primary"),
                    ui.Dialog(
                        title="Invite member",
                        body=ui.Form(
                            ui.TextField(form.email, label="Email"),
                            ui.Select(
                                form.role,
                                label="Role",
                                options=["viewer", "editor", "admin"],
                            ),
                            ui.FormActions(
                                ui.Button("Cancel", closes_dialog=True),
                                ui.SubmitButton("Send invitation"),
                            ),
                        ),
                    ),
                ),
                justify="between",
                align="center",
            ),
            ui.Suspense(
                content=lambda: member_table(members.value),
                fallback=ui.TableSkeleton(rows=5),
            ),
            gap=6,
        ),
    )
```

### 7.4 Project Structure

```text
my_app/
├── pyproject.toml
├── virel.toml
├── app/
│   ├── __init__.py
│   ├── app.py
│   ├── routes/
│   │   ├── home.py
│   │   └── settings.py
│   ├── components/
│   ├── models/
│   ├── services/
│   ├── theme.py
│   └── assets/
├── tests/
│   ├── components/
│   └── browser/
└── public/
```

No generated frontend source belongs in the developer-maintained tree. Generated artifacts live in `.virel/` and `dist/`.

## 8. Programming Model

### 8.1 Components

A component is a typed Python function that returns a `ui.Node`.

```python
@ui.component
def user_badge(user: User, compact: bool = False) -> ui.Node:
    return ui.Row(
        ui.Avatar(name=user.name, src=user.avatar_url),
        ui.Text(user.name),
        gap=2 if compact else 3,
        align="center",
    )
```

Requirements:

- Props use normal Python type annotations.
- Defaults use normal Python defaults.
- Components are composable.
- Children may be passed positionally or through typed slots.
- Component names are stable in inspector output.
- Component purity is checked where possible.
- Source locations survive compilation through source maps.

### 8.2 Reactive Values

`ui.state(initial)` creates browser-local reactive state.

```python
query = ui.state("")
selected = ui.state[set[str]](set())
```

Reactive values support:

- reads in component expressions,
- `.set(value)`,
- `.update(function)`,
- derived values,
- effects,
- persistence adapters,
- URL synchronization,
- and developer inspection.

```python
normalized = ui.derived(lambda: query.strip().lower())
```

The compiler creates a dependency graph and updates only affected DOM bindings.

### 8.3 Control Flow

Normal Python syntax should be supported when statically analyzable:

```python
return ui.Stack(
    ui.Text("Administrator") if user.is_admin else ui.Text("Member"),
    [
        project_card(project)
        for project in projects
        if project.visible
    ],
)
```

The compiler must provide deterministic errors for unsupported dynamic constructs.

### 8.4 Execution Zones

#### Build-Time Python

Runs while routes, assets, and static content are compiled.

```python
@ui.build
def documentation_index() -> list[DocPage]:
    return load_markdown_tree("docs/")
```

#### Client Python Subset

Compiled ahead of time to JavaScript.

```python
@ui.client
def normalize_search(value: str) -> str:
    return " ".join(value.lower().split())
```

Supported client syntax should be explicit and versioned. Unsupported functions must fail at build time rather than silently fall back to server execution.

#### Server Python

Runs in CPython.

```python
@ui.server
async def run_inference(request: InferenceInput) -> InferenceOutput:
    return await model_service.predict(request)
```

#### Shared Pure Functions

Compiled for the browser and executable in CPython.

```python
@ui.shared
def calculate_total(lines: list[Line]) -> Decimal:
    return sum(line.price * line.quantity for line in lines)
```

Shared functions must be deterministic, side-effect-free, serializable, and restricted to the supported cross-runtime standard library.

### 8.5 Effects

Effects are explicit:

```python
ui.effect(
    lambda: analytics.track("search", {"query": query}),
    dependencies=[query],
)
```

Effects must not run during server rendering unless declared for that phase.

### 8.6 Context

Typed context supports themes, authenticated users, workspace state, localization, and application services without global mutable variables.

```python
current_user = ui.context[User]("current_user")
```

### 8.7 Resources and Data Loading

`ui.resource` represents asynchronous data with loading, value, error, refresh, and invalidation states.

```python
projects = ui.resource(
    list_projects,
    params=lambda: {"query": query},
    cache="workspace",
    stale_for=30,
)
```

Features:

- request deduplication,
- typed inputs and outputs,
- cancellation,
- optimistic mutation,
- retry policies,
- server rendering,
- streaming,
- cache keys,
- invalidation,
- and suspense integration.

### 8.8 Server Actions

Server actions are typed remote procedure calls generated from Python functions.

Requirements:

- explicit `@ui.server`,
- schema generated from annotations,
- authentication and authorization hooks,
- CSRF protection,
- structured errors,
- cancellation,
- idempotency keys,
- streaming responses,
- file upload and download,
- progress events,
- tracing,
- configurable transport,
- and no arbitrary Python object serialization.

### 8.9 Forms

Forms should be generated from Pydantic models, dataclasses, or explicit field definitions.

```python
form = ui.form(
    ProjectInput,
    submit=create_project,
    validate="change",
)
```

The same model drives:

- field types,
- client validation,
- server validation,
- labels and descriptions where supplied,
- serialization,
- error messages,
- generated documentation,
- and test factories.

The browser performs safe deterministic validation immediately. The server always revalidates.

### 8.10 Routing

Routes support:

- static parameters,
- dynamic parameters,
- nested layouts,
- typed query parameters,
- route guards,
- redirects,
- loading boundaries,
- error boundaries,
- metadata,
- canonical URLs,
- server rendering,
- static generation,
- and client navigation.

```python
@ui.page("/projects/{project_id}")
def project_page(project_id: str, tab: str = "overview") -> ui.Node:
    ...
```

### 8.11 Error Boundaries

Components may isolate runtime and data errors:

```python
ui.ErrorBoundary(
    content=project_panel(),
    fallback=lambda error: ui.ErrorState(
        title="Project unavailable",
        detail=error.safe_message,
        retry=error.retry,
    ),
)
```

### 8.12 Streaming

Streaming is a first-class requirement for AI applications.

```python
@ui.server(stream=True)
async def generate(prompt: Prompt):
    async for chunk in model.stream(prompt):
        yield chunk
```

The UI can bind the stream to text, structured events, progress, tool calls, citations, logs, or custom components without replacing the entire component tree.

## 9. Rendering Architecture

### 9.1 Compiler Pipeline

```text
Python source
    ↓
Python AST + type information
    ↓
Virel semantic analysis
    ↓
Versioned Virel UI Intermediate Representation
    ↓
Static extraction and execution-zone partitioning
    ↓
HTML / CSS / browser modules / server action manifest
    ↓
Optimization, tree shaking, code splitting, asset hashing
    ↓
Deployable application
```

### 9.2 Stable UI Intermediate Representation

The UI IR is the central architectural boundary.

It must describe:

- component trees,
- semantic elements,
- reactive expressions,
- event bindings,
- state dependencies,
- styles and tokens,
- routes,
- resources,
- server actions,
- data schemas,
- accessibility metadata,
- imports,
- assets,
- and source locations.

The IR must be:

- versioned,
- deterministic,
- serializable,
- inspectable,
- testable,
- independent of developer source formatting,
- and suitable for alternative renderers in the future.

The IR is internal infrastructure, not a second language developers must author.

### 9.3 Browser Runtime

Virel Web should use a small fine-grained reactive runtime that updates concrete DOM bindings rather than rerendering complete virtual component trees.

Characteristics:

- browser-native DOM,
- signal-based updates,
- event delegation,
- route-level code splitting,
- component-level lazy loading,
- partial hydration,
- resumable or island-style interactivity where practical,
- zero runtime for fully static components,
- and no WebSocket unless the application requires real-time communication.

### 9.4 Server Runtime

The server runtime is an ASGI application compatible with standard Python deployment.

It provides:

- server rendering,
- server actions,
- streaming,
- static asset serving in simple deployments,
- route middleware,
- authentication hooks,
- observability,
- development hot reload,
- and integration adapters.

Virel must support mounting inside existing FastAPI, Starlette, and Django deployments.

### 9.5 Transport

Default transport:

- HTTP for actions and resources,
- streamed HTTP for incremental output,
- server-sent events for one-way live updates,
- WebSocket for bidirectional real-time features,
- direct browser execution for local interaction.

Payloads use schema-validated JSON by default for transparency and interoperability. Optional binary encodings may be used for large typed arrays, Arrow data, media, or high-volume streams.

### 9.6 Rendering Modes

Each route may select or infer:

- `static`: generated at build time,
- `client`: static shell plus browser rendering,
- `server`: rendered for each request,
- `hybrid`: server-rendered with selective hydration,
- `stream`: progressively rendered,
- `auto`: compiler chooses and reports the decision.

```python
@ui.page("/", render="static")
def landing():
    ...
```

### 9.7 Hydration Boundaries

Interactive boundaries should be inferred but overrideable.

```python
ui.Island(
    model_playground(),
    load="visible",
)
```

Load strategies:

- immediate,
- idle,
- visible,
- interaction,
- media query,
- explicit.

### 9.8 No Hidden Server Dependency

`virel build --static` must fail with a precise report if a route or dependency requires a server. It must never emit an application that appears static but fails at runtime.

## 10. Styling and Design System

### 10.1 Design Tokens

Virel themes use typed semantic tokens.

```python
theme = ui.Theme(
    color={
        "surface": ui.Color.scale(...),
        "accent": ui.Color.scale(...),
        "danger": ui.Color.scale(...),
    },
    space=ui.Space.scale(base=4),
    radius={
        "sm": 4,
        "md": 8,
        "lg": 14,
    },
    typography={
        "body": ui.Font(...),
        "heading": ui.Font(...),
        "mono": ui.Font(...),
    },
)
```

Tokens compile to CSS custom properties and may support:

- light and dark modes,
- high contrast,
- organization brands,
- tenant themes,
- density modes,
- reduced motion,
- and runtime theme switching.

### 10.2 Semantic Properties

Components expose semantic properties rather than arbitrary implementation details:

```python
ui.Button("Delete", intent="danger", emphasis="solid", size="md")
```

### 10.3 Layout Primitives

Core layout:

- `Stack`
- `Row`
- `Grid`
- `Wrap`
- `Cluster`
- `Sidebar`
- `Center`
- `Container`
- `AspectRatio`
- `ScrollArea`
- `Splitter`
- `Resizable`
- `AppShell`

Responsive values are typed:

```python
columns={"base": 1, "md": 2, "xl": 4}
```

### 10.4 Style Objects

Developers may create reusable typed styles:

```python
card_style = ui.style(
    padding=6,
    radius="lg",
    background="surface.1",
    border="subtle",
    hover={"shadow": "md"},
)
```

### 10.5 CSS Escape Hatch

```python
ui.Box(
    class_name="specialized-visualization",
    css={
        "container-type": "inline-size",
        "--plot-density": 0.8,
    },
)
```

Raw style use should remain compatible with normal CSS concepts and browser development tools.

### 10.6 Component Recipes

Organizations can define variants:

```python
ProjectCard = ui.recipe(
    base=ui.Card,
    variants={
        "status": {
            "active": {...},
            "paused": {...},
        }
    },
)
```

### 10.7 Responsive and Adaptive Design

Required support:

- media queries,
- container queries,
- viewport units,
- preference queries,
- touch and pointer capability,
- safe areas,
- responsive typography,
- and server-safe responsive rendering.

### 10.8 Animation

Animation API supports:

- CSS transitions,
- keyframes,
- layout animation,
- enter and exit animation,
- gestures,
- reduced-motion fallback,
- and timeline inspection.

Animations must execute in the browser and avoid server traffic.

## 11. Component System

### 11.1 Core Layers

#### Semantic Elements

Typed wrappers for standard HTML semantics:

- headings,
- paragraphs,
- links,
- lists,
- tables,
- forms,
- sections,
- navigation,
- articles,
- dialogs,
- details,
- media,
- and metadata.

#### Headless Interaction Primitives

Accessible state machines for:

- dialogs,
- menus,
- popovers,
- tabs,
- tooltips,
- comboboxes,
- listboxes,
- disclosure,
- accordion,
- tree view,
- command palette,
- date selection,
- drag and drop,
- and focus management.

#### Styled Product Components

Polished defaults for:

- buttons,
- inputs,
- cards,
- navigation,
- app shells,
- tables,
- filters,
- alerts,
- empty states,
- skeletons,
- pagination,
- file upload,
- notifications,
- and onboarding patterns.

#### Advanced Components

Optional packages for:

- data grids,
- charts,
- code editors,
- rich-text editors,
- document viewers,
- diagramming,
- geospatial maps,
- media timelines,
- node graphs,
- 3D scenes,
- and collaborative editing.

### 11.2 Accessibility Contract

Every official component must document and test:

- keyboard interaction,
- focus order,
- focus restoration,
- semantics,
- ARIA use,
- labels,
- error announcement,
- screen-reader output,
- contrast requirements,
- touch targets,
- reduced-motion behavior,
- and high-contrast behavior.

The compiler should reject or warn on common accessibility failures such as:

- image without alternative text,
- icon-only button without an accessible label,
- unlabeled input,
- invalid heading progression where determinable,
- click handler on a noninteractive element,
- focusable content hidden from assistive technology,
- and insufficiently descriptive link text in strict mode.

### 11.3 Internationalization

First-class support:

- message catalogs,
- plural rules,
- date, time, number, and currency formatting,
- locale-aware sorting,
- bidirectional text,
- right-to-left layout,
- translated route metadata,
- lazy locale loading,
- and extraction tooling.

## 12. Python Ecosystem Integration

### 12.1 Data Structures

Official adapters should support:

- Pydantic models,
- dataclasses,
- TypedDict,
- enums,
- NumPy arrays,
- pandas DataFrames,
- Polars DataFrames,
- Apache Arrow,
- and iterables of typed records.

### 12.2 Data Tables

The professional data-grid package must support:

- virtualization,
- server and client sorting,
- filtering,
- grouping,
- aggregation,
- editable cells,
- keyboard navigation,
- selection,
- column pinning,
- column resizing,
- export,
- large datasets,
- streaming updates,
- and accessible semantics.

### 12.3 Visualization

Virel should not invent a new chart grammar initially. It should provide typed adapters for established Python visualization libraries and a common container contract for sizing, themes, events, export, and accessibility.

### 12.4 AI Product Components

Official AI package:

- streaming response view,
- prompt editor,
- message timeline,
- structured tool-call display,
- citation panel,
- token and cost meter,
- model selector,
- parameter controls,
- file and multimodal input,
- audio recorder,
- image viewer,
- evaluation table,
- trace viewer,
- feedback controls,
- human approval step,
- and long-running job progress.

These are UI primitives, not an opinionated agent framework.

### 12.5 Notebook Integration

```python
ui.preview(model_playground)
```

Notebook preview must use the same component semantics and compiler as production. It must not create a notebook-only API that later requires a rewrite.

## 13. Interoperability and Extensibility

### 13.1 Web Components

Standard web components are the preferred universal extension boundary.

```python
CodeEditor = ui.web_component(
    tag="virel-code-editor",
    package="@vendor/code-editor",
    props=CodeEditorProps,
    events=CodeEditorEvents,
)
```

### 13.2 JavaScript Package Bindings

The CLI generates typed Python bindings from TypeScript declarations where possible:

```bash
virel bind npm @vendor/date-picker
```

Generated bindings include:

- Python types,
- prop mapping,
- event schemas,
- lazy-loading metadata,
- stylesheet imports,
- server-rendering constraints,
- and documentation stubs.

### 13.3 Raw JavaScript

Raw JavaScript is an explicit last resort:

```python
unsafe_handler = ui.unsafe.javascript(
    "...",
    reason="Vendor SDK has no module API",
)
```

Strict enterprise mode may prohibit raw JavaScript.

### 13.4 Existing Web Applications

Virel components should be embeddable as:

- custom elements,
- mountable islands,
- static HTML fragments,
- or route-level applications.

### 13.5 Plugin System

Plugins may participate in:

- compiler passes,
- component registration,
- build configuration,
- asset transformation,
- route generation,
- deployment,
- linting,
- testing,
- and inspector panels.

Plugins must declare capabilities and may be restricted by policy.

## 14. Agent-Native Development

### 14.1 Principle

A smaller source file does not automatically mean lower total agent cost. Virel must reduce the complete problem space:

- fewer languages,
- fewer configuration files,
- fewer duplicated schemas,
- fewer integration boundaries,
- fewer equivalent APIs,
- less documentation retrieval,
- less boilerplate,
- clearer compiler feedback,
- and fewer repair cycles.

Token and accuracy improvements are product hypotheses that must be benchmarked.

### 14.2 Machine-Readable Component Registry

Every component exposes a structured schema:

- canonical name,
- purpose,
- props,
- prop types,
- defaults,
- children and slots,
- events,
- examples,
- accessibility requirements,
- incompatibilities,
- deprecations,
- and import path.

```bash
virel schema Button --json
```

### 14.3 Context Packs

The CLI generates task-specific compact documentation:

```bash
virel context \
  --components form,dialog,data-table \
  --features server-actions,validation \
  --budget 12000
```

The output contains only the API surface required for the task and is suitable for an agent context window.

### 14.4 Agent Interface

Official MCP and CLI tools should support:

- inspect project structure,
- query component schemas,
- search official examples,
- validate a planned component tree,
- compile a file,
- read structured diagnostics,
- inspect routes,
- inspect execution zones,
- run targeted tests,
- retrieve bundle impact,
- apply safe fixes,
- and generate migration patches.

### 14.5 Deterministic Diagnostics

All diagnostics have:

- stable error codes,
- JSON output,
- source ranges,
- explanation,
- documentation key,
- suggested fixes,
- and optional patch operations.

### 14.6 Canonical Patterns

Official documentation should mark one recommended pattern for common tasks. Alternatives are documented as advanced options, not presented as interchangeable defaults.

### 14.7 Agent Benchmarks

The project must maintain public reproducible benchmarks that compare Virel against representative stacks.

Tasks should include:

- responsive landing page,
- authenticated SaaS settings page,
- validated multi-step form,
- sortable and filterable data table,
- streaming AI chat,
- file upload with progress,
- real-time operations dashboard,
- accessible command palette,
- and a complex stateful editor.

Metrics:

- successful completion,
- functional correctness,
- visual correctness,
- accessibility score,
- security defects,
- generated source tokens,
- documentation/context tokens,
- model output tokens,
- repair turns,
- wall-clock time,
- runtime bundle size,
- and application performance.

### 14.8 Initial Agent-Efficiency Targets

These are release gates, not launch claims:

- At least 30% fewer developer-authored source tokens than a conventional Python-backend plus TypeScript-frontend reference implementation for the median benchmark task.
- At least 25% fewer agent output tokens across complete successful task trajectories.
- At least 25% fewer repair iterations.
- No statistically significant reduction in functional or visual correctness.
- Higher or equal accessibility correctness.
- Published benchmark prompts, models, versions, environments, and scoring logic.

## 15. CLI and Tooling

### 15.1 Commands

```text
virel new
virel dev
virel build
virel preview
virel check
virel test
virel inspect
virel routes
virel graph
virel schema
virel context
virel bind
virel migrate
virel doctor
virel deploy
```

### 15.2 Development Server

Requirements:

- sub-second incremental rebuilds for ordinary edits,
- state-preserving hot reload where safe,
- clear fallback to full reload,
- route-aware error overlay,
- server-action trace panel,
- responsive viewport controls,
- theme and locale switching,
- accessibility inspection,
- and bundle impact reporting.

### 15.3 Inspector

The browser inspector must display:

- Python component tree,
- DOM mapping,
- source file and line,
- props,
- reactive dependencies,
- local state,
- resources,
- server actions,
- hydration boundaries,
- rendering mode,
- accessibility metadata,
- style tokens,
- and update timing.

### 15.4 Editor Support

Official language-server integration should provide:

- autocomplete,
- component prop documentation,
- invalid-prop diagnostics,
- token completion,
- route completion,
- server/client boundary warnings,
- generated type previews,
- and navigation from browser component to Python source.

VS Code, PyCharm, Neovim, and generic LSP clients are first-class targets.

## 16. Testing

### 16.1 Component Tests

```python
def test_invite_dialog():
    view = ui.test.render(members_page)

    view.get_by_role("button", name="Invite member").click()

    dialog = view.get_by_role("dialog")
    assert dialog.get_by_label("Email").is_visible()
```

### 16.2 Browser Tests

Browser tests are written in Python and backed by a real browser automation engine.

```python
async def test_member_invitation(page: ui.BrowserPage):
    await page.goto("/settings/members")
    await page.button("Invite member").click()
    await page.field("Email").fill("person@example.com")
    await page.select("Role").choose("editor")
    await page.button("Send invitation").click()
    await page.expect_text("Invitation sent")
```

### 16.3 Required Test Modes

- static component rendering,
- reactive client behavior,
- server-action contracts,
- route behavior,
- browser integration,
- visual regression,
- accessibility,
- performance budgets,
- serialization compatibility,
- and security checks.

### 16.4 Time and Concurrency

The test framework must allow deterministic control of:

- timers,
- animation frames,
- network responses,
- streaming chunks,
- server-action latency,
- retries,
- and concurrent updates.

## 17. Performance Requirements

### 17.1 Performance Philosophy

Python authoring must not excuse slow browser output. Runtime performance is evaluated against browser-native alternatives.

### 17.2 Initial Budgets

For a production minified build, excluding application content and optional component packages:

- Core browser runtime: target at or below 35 KB gzip.
- Static page with no interaction: zero required Virel runtime JavaScript.
- Minimal interactive application: target at or below 60 KB gzip total framework JavaScript.
- Route-level code splitting enabled by default.
- Unused components and utilities tree-shaken.
- Local input-to-paint latency: target below 50 ms at the 95th percentile on reference mid-range hardware.
- Fine-grained state update should not rerender unrelated component subtrees.
- First-party components must publish bundle cost.
- CI may fail when an application exceeds configured budgets.

### 17.3 Large Data

Virel must provide:

- virtualized lists and tables,
- incremental rendering,
- worker execution,
- Arrow transfer,
- typed-array transfer,
- canvas and WebGL/WebGPU extension points,
- and backpressure for streams.

### 17.4 Server Scale

Default server actions must be stateless and horizontally scalable. Real-time state, sessions, and collaboration are explicit services rather than implicit in-process objects.

## 18. Security

### 18.1 Trust Boundaries

The compiler must classify code and data as:

- client-safe,
- server-only,
- public build-time,
- secret build-time,
- or explicitly shared.

Importing a server secret into client-compilable code must be a build error.

### 18.2 Required Controls

- automatic HTML escaping,
- explicit unsafe HTML API,
- CSP support,
- CSRF protection,
- secure cookies,
- same-site defaults,
- origin validation,
- schema validation on every server action,
- upload limits,
- content-type validation,
- safe file naming,
- structured authorization hooks,
- protection against open redirects,
- dependency integrity,
- lockfile support,
- SBOM generation,
- reproducible build metadata,
- and security headers.

### 18.3 Serialization

Virel must not use Python pickle or equivalent arbitrary object deserialization across client/server boundaries.

### 18.4 Supply Chain

Official releases should use:

- signed source tags,
- trusted publishing,
- provenance attestations,
- reproducible wheels where practical,
- pinned toolchain manifests,
- automated dependency review,
- and published security policy.

### 18.5 Enterprise Policy Mode

Organizations can enforce:

- approved components,
- approved plugins,
- prohibited raw HTML,
- prohibited raw JavaScript,
- CSP restrictions,
- dependency allowlists,
- maximum bundle budgets,
- accessibility strictness,
- and deployment constraints.

## 19. Observability

Official OpenTelemetry integration should cover:

- page navigation,
- server rendering,
- server actions,
- resources,
- database spans supplied by existing libraries,
- streaming duration,
- hydration,
- client errors,
- long tasks,
- and core web performance metrics.

Diagnostics must correlate browser events with Python server traces without exposing sensitive payloads.

Development tools should show:

- action duration,
- serialization time,
- network time,
- server execution time,
- render time,
- update count,
- and payload size.

## 20. Deployment

### 20.1 Static

```bash
virel build --target static
```

Output may be hosted on any static file service.

### 20.2 ASGI

```bash
virel build --target asgi
uvicorn app:application
```

### 20.3 Containers

```bash
virel build --target container
```

Generated container definitions should be optional and inspectable.

### 20.4 Existing Python Application

```python
from fastapi import FastAPI
from virel.integrations.fastapi import mount

app = FastAPI()
mount(app, virel_app, path="/")
```

### 20.5 Serverless and Edge

Virel should support serverless Python environments where runtime limits permit. Browser and static output should remain deployable to edge CDNs. Virel must not describe Python server code as “edge” unless the selected deployment environment actually executes it at the edge.

### 20.6 Private and Air-Gapped Environments

Builds must support:

- vendored browser assets,
- private Python indexes,
- private JavaScript package mirrors,
- offline documentation,
- offline component registry,
- no telemetry,
- and deterministic dependency resolution.

## 21. Package Architecture

Proposed repository:

```text
virel/
├── packages/
│   ├── virel/                 # Public Python API
│   ├── virel-compiler/        # Compiler and semantic analysis
│   ├── virel-runtime-web/     # Browser runtime
│   ├── virel-components/      # Official component system
│   ├── virel-testing/         # Python test APIs
│   ├── virel-data/            # Tables and data adapters
│   ├── virel-charts/          # Visualization adapters
│   ├── virel-ai/              # AI product components
│   ├── virel-bind/            # Third-party binding generator
│   └── virel-cli/             # Toolchain and developer commands
├── examples/
├── benchmarks/
├── docs/
├── rfcs/
└── conformance/
```

The user-facing installation may remain a single `virel` package with optional extras:

```bash
uv add "virel[data,charts,ai]"
```

## 22. Public API Governance

### 22.1 Stability

- Semantic versioning.
- Versioned compiler IR.
- Deprecation warnings with migration commands.
- Published compatibility matrix.
- Long-term-support releases for enterprise adoption.
- No undocumented public APIs.

### 22.2 Request for Comments

Material changes to:

- component semantics,
- state model,
- execution zones,
- transport,
- IR,
- styling,
- routing,
- or plugin capability

require a public RFC.

### 22.3 Conformance Suite

Alternative component libraries, renderers, and integrations can run an official conformance suite covering:

- component behavior,
- accessibility,
- serialization,
- reactivity,
- server actions,
- routing,
- and error semantics.

## 23. Documentation Standard

Documentation is a product feature.

Every feature must include:

- concise definition,
- canonical example,
- API reference,
- execution-location explanation,
- accessibility notes,
- performance notes,
- security notes,
- testing example,
- common mistakes,
- migration notes,
- and machine-readable schema.

Documentation layers:

1. **Five-minute start**
2. **Core mental model**
3. **Task guides**
4. **Production application guide**
5. **API reference**
6. **Architecture guide**
7. **Agent context packs**
8. **Enterprise operations guide**

Examples must be tested in CI.

## 24. Success Metrics

### 24.1 Developer Experience

- Median time from installation to working local application below five minutes.
- Median hot-update feedback below one second for reference projects.
- At least 80% of beta users can complete the onboarding application without external assistance.
- Fewer than five concepts required before building a stateful form with a server action.
- Structured diagnostics for 100% of compiler errors.
- No required Node.js knowledge for ordinary development.

### 24.2 Product Capability

Reference applications must demonstrate:

- polished public marketing site,
- authenticated SaaS product,
- responsive operations dashboard,
- large editable data table,
- accessible complex form,
- streaming AI interface,
- real-time collaborative feature,
- rich interactive visualization,
- and embedded Virel component inside a non-Virel site.

### 24.3 Quality

- Official components meet the project’s declared WCAG conformance target.
- Zero known critical security findings at 1.0.
- Public performance benchmark suite.
- Cross-browser support for current stable Chrome, Firefox, Safari, and Edge, plus an explicit support window.
- Framework runtime remains within published bundle budgets.

### 24.4 Agent Outcomes

- Public, reproducible agent benchmark.
- Reduced total successful-trajectory token consumption.
- Reduced repair iterations.
- Equal or better functional, visual, accessibility, and security scores.
- Structured agent tooling used in benchmark runs.

## 25. Roadmap

### Phase 0: Architecture Validation

Deliver:

- Python component syntax experiments,
- UI IR prototype,
- reactive expression compiler,
- minimal DOM runtime,
- server-action prototype,
- source mapping,
- bundle-size measurement,
- and competing architecture benchmarks.

Exit criteria:

- Counter, form, routed application, streaming output, and third-party web component work end to end.
- No architectural dependency on permanent WebSocket state.
- Client interactions execute locally.
- Generated output is inspectable.

### Phase 1: Developer Preview

Deliver:

- CLI,
- component functions,
- local state,
- derived values,
- routing,
- static generation,
- client rendering,
- core styling,
- design tokens,
- 30 essential components,
- hot reload,
- browser inspector,
- and pytest component testing.

Target users:

- internal teams,
- design partners,
- library contributors.

### Phase 2: Alpha

Deliver:

- server rendering,
- server actions,
- resources,
- forms,
- Pydantic integration,
- streaming,
- authentication hooks,
- file transfer,
- accessibility linter,
- web-component bindings,
- visual testing,
- and deployment adapters.

### Phase 3: Beta

Deliver:

- stable core API candidate,
- data grid,
- charts,
- AI component package,
- i18n,
- plugin API,
- performance tooling,
- OpenTelemetry,
- enterprise policy mode,
- migration tooling,
- and public agent benchmark.

### Phase 4: Version 1.0

Release gates:

- API and IR stability policy,
- complete production guide,
- security audit,
- accessibility audit,
- browser conformance,
- performance budgets met,
- at least three substantial production design partners,
- framework-owned reference applications,
- and demonstrated self-hosted deployment.

### Post-1.0

Candidates:

- desktop packaging through a webview,
- optional browser-Python/WASM execution,
- visual component workbench,
- collaborative state service,
- native mobile renderer research,
- and additional renderer backends.

These must not compromise the quality of the web platform.

## 26. Principal Risks and Mitigations

### Risk 1: The Product Is Perceived as Another Dashboard Framework

**Mitigation:** Lead with public product, SaaS, design-system, accessibility, SEO, routing, and frontend capability. Reference applications must look and behave like professional products, not notebooks.

### Risk 2: Pure Python Becomes a Restrictive Abstraction

**Mitigation:** Base rendering on web standards, provide typed bindings, support web components, expose CSS concepts, permit controlled raw integrations, and publish the generated output.

### Risk 3: Client-Compiled Python Feels Unpredictable

**Mitigation:** Define a strict supported subset, provide static validation, never silently relocate code to the server, and show execution zones in the editor and inspector.

### Risk 4: Server-Driven State Limits Latency and Scale

**Mitigation:** Browser-local state is the default. Server state is explicit. HTTP is the default action transport. WebSocket use is capability-driven.

### Risk 5: Building a New Runtime and Component System Is Too Broad

**Mitigation:** Keep the runtime small, rely on browser standards, sequence component depth carefully, and make web-component interoperability a phase-one architectural requirement.

### Risk 6: Generated JavaScript Is Difficult to Debug

**Mitigation:** High-quality source maps, Python component inspector, readable development output, stable diagnostics, and correlated browser/server traces.

### Risk 7: Python Semantics Do Not Map Cleanly to JavaScript

**Mitigation:** Compile only a documented subset for the browser. Keep unrestricted Python on the server. Provide shared standard types and deterministic compile errors.

### Risk 8: “Fewer Tokens” Becomes Unsupported Marketing

**Mitigation:** Treat token savings as a measured engineering outcome. Publish benchmark tasks, full trajectories, model versions, and failures.

### Risk 9: Component Breadth Dilutes Quality

**Mitigation:** Separate semantic primitives, headless behavior, styled components, and optional advanced packages. Require conformance and accessibility tests.

### Risk 10: Framework Lock-In

**Mitigation:** Standard HTML/CSS/JS output, web-component export, typed HTTP contracts, inspectable generated assets, and no mandatory hosting service.

## 27. Key Product Decisions

The following decisions should be treated as foundational unless architecture experiments disprove them:

1. Virel is a compiler-first framework, not only a runtime library.
2. The browser does not download CPython by default.
3. Client interaction runs locally.
4. Execution zones are explicit and statically checked.
5. The server is stateless by default.
6. Web is the only first-class 1.0 rendering target.
7. The UI IR is versioned and renderer-independent.
8. Styling is token- and recipe-based with CSS escape hatches.
9. Accessibility is enforced through components, linting, and tests.
10. Third-party interoperability uses web standards and generated bindings.
11. Virel Cloud is optional.
12. Agent efficiency is benchmarked, not assumed.
13. Normal development does not require direct Node.js toolchain management.
14. Generated output remains inspectable and exportable.
15. One canonical API is preferred over many aliases.

## 28. Initial Minimum Lovable Product

The first release worth placing in front of external developers should support a complete, credible application rather than isolated demos.

Required MLP application:

**AI Evaluation Workspace**

Features:

- authenticated app shell,
- responsive navigation,
- project list,
- model and dataset configuration form,
- file upload,
- run creation through a server action,
- streamed job logs,
- live progress,
- virtualized results table,
- filters and sorting,
- charts,
- result detail dialog,
- keyboard-accessible command palette,
- light and dark themes,
- error boundaries,
- browser and component tests,
- server rendering,
- static landing page,
- container deployment,
- and observability.

This application exercises Virel’s intended advantage for Python and AI teams while proving that the framework can build more than a dashboard.

## 29. Acceptance Criteria for the Core Promise

Virel may claim “professional frontend development in Python” only when all of the following are true:

- A developer can build the reference applications without editing JavaScript, TypeScript, HTML, or CSS.
- The browser executes ordinary interactions without server round trips.
- Applications meet published accessibility checks.
- Static routes can ship without framework JavaScript.
- Dynamic routes can be server-rendered and selectively hydrated.
- Applications can scale horizontally without sticky sessions by default.
- Third-party browser components can be integrated through typed Python bindings.
- Developers can inspect and debug the generated browser behavior from Python source.
- Self-hosted deployment is fully supported.
- Performance and bundle budgets are published and met.
- Agent-efficiency claims are supported by reproducible evidence.
- Escape hatches exist for browser features not yet covered by Virel.

## 30. Final Definition

Virel is not Python syntax layered over remote widgets.

Virel is a Python-native frontend compiler and product UI platform. It gives Python developers a coherent language, component model, design system, state model, testing model, and deployment path while producing browser-native applications that retain the performance, accessibility, interoperability, and flexibility expected from professional frontend engineering.

Its strategic value is the removal of accidental complexity:

- one primary language,
- one schema system,
- one application model,
- fewer integration boundaries,
- less duplicated code,
- less agent context,
- and a shorter path from Python capability to a complete product.

The standard for success is not whether Python can display a button. The standard is whether a demanding product team can choose Virel for a serious application and never need to apologize for the interface, performance, architecture, accessibility, scale, or developer experience.
