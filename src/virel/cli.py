"""Virel command-line interface.

Commands (SPEC 15.1 subset for Phase 0):
  virel new       scaffold an application
  virel dev       run the development server (zero extra dependencies)
  virel build     build for a deployment target (static | asgi)
  virel check     compile every route and report diagnostics
  virel routes    list routes with rendering modes
  virel inspect   print the UI IR for a route as JSON
  virel schema    print a component schema (agent-facing, SPEC 14.2)
"""

from __future__ import annotations

import argparse
import importlib
import inspect as pyinspect
import json
import shutil
import sys
import tomllib
from pathlib import Path

from .compiler import build_all, build_static, compile_page
from .context import ContextMissingError
from .expr import VirelCompileError
from .registry import active_registry
from .theme import Theme, build_stylesheet, runtime_js


def _fail(message: str) -> "None":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load_app(root: Path) -> dict:
    config_path = root / "virel.toml"
    if not config_path.exists():
        _fail(f"no virel.toml found in {root}. Run `virel new <name>` to "
              "create an application, or run from the application directory.")
    config = tomllib.loads(config_path.read_text("utf-8"))
    module_name = config.get("app", {}).get("module")
    if not module_name:
        _fail("virel.toml must define [app] module = \"your.module\"")
    sys.path.insert(0, str(root))
    importlib.import_module(module_name)
    registry = active_registry()
    registry.client_nav = bool(config.get("app", {}).get("client_nav", True))
    if not registry.pages:
        _fail(f"module {module_name!r} imported but registered no @ui.page routes.")
    return config


def cmd_new(args: argparse.Namespace) -> None:
    target = Path(args.name)
    if target.exists():
        _fail(f"{target} already exists")
    (target / "app" / "routes").mkdir(parents=True)
    (target / "public").mkdir()
    (target / "tests").mkdir()

    (target / "virel.toml").write_text(
        '[app]\nmodule = "app.app"\npublic = "public"\n'
    )
    (target / "pyproject.toml").write_text(
        f'[project]\nname = "{target.name}"\nversion = "0.1.0"\n'
        'requires-python = ">=3.11"\ndependencies = ["virel"]\n'
    )
    (target / "app" / "__init__.py").write_text("")
    (target / "app" / "app.py").write_text(
        "from . import routes  # noqa: F401  (importing registers pages)\n"
    )
    (target / "app" / "routes" / "__init__.py").write_text(
        "from . import home  # noqa: F401\n"
    )
    (target / "app" / "routes" / "home.py").write_text(
        'from virel import ui\n'
        '\n'
        '\n'
        '@ui.page("/")\n'
        'def home() -> ui.Node:\n'
        '    count = ui.state(0)\n'
        '\n'
        '    return ui.Page(\n'
        '        ui.Container(\n'
        '            ui.Section(\n'
        '                ui.Heading("Hello from Python", level=1),\n'
        '                ui.Text(f"Count: {count}"),\n'
        '                ui.Row(\n'
        '                    ui.Button("Increment",\n'
        '                              on_click=lambda: count.update(lambda c: c + 1),\n'
        '                              intent="primary"),\n'
        '                    ui.Button("Reset", on_click=lambda: count.set(0)),\n'
        '                ),\n'
        '            ),\n'
        '            width="sm",\n'
        '        ),\n'
        '        title="' + target.name + '",\n'
        '    )\n'
    )
    print(f"Created {target}/")
    print(f"  cd {target}")
    print("  virel dev")


def cmd_dev(args: argparse.Namespace) -> None:
    root = Path.cwd()
    config = _load_app(root)
    from .server import DevHTTPServer, create_asgi_app

    public = config.get("app", {}).get("public")
    app = create_asgi_app(
        dev=True,
        public_dir=(root / public) if public else None,
        watch_dirs=[root / "app"] if (root / "app").is_dir() else [root],
    )
    print(f"virel dev server: http://{args.host}:{args.port}")
    for page in active_registry().pages.values():
        print(f"  {page.path}")
    try:
        DevHTTPServer(app, host=args.host, port=args.port).run()
    except KeyboardInterrupt:
        pass


def cmd_build(args: argparse.Namespace) -> None:
    root = Path.cwd()
    config = _load_app(root)
    registry = active_registry()
    dist = root / "dist"
    ir_dir = root / ".virel" / "ir"

    from .plugins import (run_asset_transforms, run_build_config,
                          run_post_build)
    run_build_config(config)
    try:
        if args.target == "static":
            report = build_static(hashed=True)
        else:
            report = build_all(hashed=True)
    except VirelCompileError as error:
        _fail(str(error))

    if dist.exists():
        shutil.rmtree(dist)
    ir_dir.mkdir(parents=True, exist_ok=True)
    for stale in ir_dir.glob("*.json"):
        stale.unlink()

    from .theme import compact
    framework_dir = dist / "_virel"
    (framework_dir / "page").mkdir(parents=True)
    (framework_dir / "runtime.js").write_text(
        run_asset_transforms("_virel/runtime.js", compact(runtime_js())))
    from importlib import resources as _resources
    fonts_dir = framework_dir / "fonts"
    fonts_dir.mkdir()
    fonts = _resources.files("virel.assets") / "fonts"
    for font in fonts.iterdir():
        (fonts_dir / font.name).write_bytes(font.read_bytes())
    theme = registry.theme or Theme()
    (framework_dir / "app.css").write_text(
        run_asset_transforms("_virel/app.css",
                             compact(build_stylesheet(theme))))

    for compiled in report.pages:
        if compiled.route == "/":
            out = dist / "index.html"
        else:
            out = dist / compiled.route.strip("/") / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(compiled.html)
        if compiled.js:
            (framework_dir / "page" / compiled.js_module).write_text(
                run_asset_transforms(f"_virel/page/{compiled.js_module}",
                                     compiled.js))
        (ir_dir / f"{compiled.slug}.json").write_text(
            json.dumps(compiled.ir, indent=2))

    public = config.get("app", {}).get("public")
    if public and (root / public).is_dir():
        shutil.copytree(root / public, dist / "public")
    for prefix, directory in registry.static_mounts.items():
        shutil.copytree(directory, dist / prefix.lstrip("/"),
                        dirs_exist_ok=True)

    runtime_size = len(runtime_js().encode())
    print(f"Built {len(report.pages)} route(s) → {dist}")
    print(f"  runtime.js: {runtime_size / 1024:.1f} KB (uncompressed)")
    for compiled in report.pages:
        js_note = f"{len(compiled.js)} B page JS" if compiled.js else "zero JS"
        print(f"  {compiled.route:30s} [{compiled.render_mode}] {js_note}")
    if report.skipped_dynamic:
        print("  dynamic routes rendered per-request by the server:")
        for route in report.skipped_dynamic:
            print(f"    {route}")
    manifest = {
        name: {
            "params": {
                p.name: {
                    "required": p.default is pyinspect.Parameter.empty,
                    "type": str(action.type_hints().get(p.name, "str")),
                }
                for p in action.signature.parameters.values()
            },
            "stream": action.stream_response,
            "download": action.download,
            "idempotent": action.idempotent,
            "guarded": action.guard is not None,
        }
        for name, action in registry.actions.items()
    }
    (ir_dir.parent / "actions.json").write_text(json.dumps(manifest, indent=2))
    run_post_build(dist)

    from .sbom import build_metadata, digest_directory, generate_sbom
    app_conf = config.get("app", {})
    app_name = app_conf.get("name", "virel-app")
    app_version = str(app_conf.get("version", "0.0.0"))
    sbom_doc = generate_sbom(root, app_name=app_name, app_version=app_version)
    (dist / "sbom.json").write_text(json.dumps(sbom_doc, indent=2))
    meta = build_metadata(root, dist_digest=digest_directory(dist))
    (dist / "build.json").write_text(json.dumps(meta, indent=2))

    print(f"UI IR written to {ir_dir}")
    print(f"Server action manifest written to {ir_dir.parent / 'actions.json'}")
    print(f"SBOM ({len(sbom_doc['components'])} components) written to "
          f"{dist / 'sbom.json'}")
    print(f"Build metadata written to {dist / 'build.json'}")


def _check_dependency_allowlist(root: Path, allowlist) -> list[str]:
    """Third-party top-level imports in the app not on the allowlist
    (SPEC 18.5). Standard-library modules and virel are always allowed."""
    import ast as _ast
    permitted = set(allowlist) | {"virel"} | set(sys.stdlib_module_names)
    app_dir = root / "app" if (root / "app").is_dir() else root
    violations: dict[str, str] = {}
    for path in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = _ast.parse(path.read_text("utf-8"))
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            names = []
            if isinstance(node, _ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, _ast.ImportFrom) and node.level == 0 \
                    and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name and name not in permitted and name not in violations:
                    violations[name] = str(path.relative_to(root))
    return [f"{name} (in {loc})" for name, loc in sorted(violations.items())]


def cmd_check(args: argparse.Namespace) -> None:
    _load_app(Path.cwd())
    registry = active_registry()
    allowlist = registry.policy.get("dependency_allowlist")
    if allowlist is not None:
        offenders = _check_dependency_allowlist(Path.cwd(), allowlist)
        if offenders:
            for offender in offenders:
                print(f"FAIL  policy dependency not allowlisted: {offender}")
            raise SystemExit(1)
    failures = 0
    for page in registry.pages.values():
        try:
            params = {name: f"sample-{name}" for name in page.param_names}
            compiled = compile_page(page, params=params or None)
            print(f"ok    {page.path} [{compiled.render_mode}]")
            for warning in compiled.warnings:
                print(f"warn  {warning}")
        except ContextMissingError as error:
            print(f"ok    {page.path} [server] (needs request context, "
                  f"provided by a guard)")
        except VirelCompileError as error:
            failures += 1
            if args.json:
                from .diagnostics import classify
                print(json.dumps(classify(str(error))))
            else:
                print(f"FAIL  {page.path}\n      {error}")
    if failures:
        raise SystemExit(1)
    print(f"{len(registry.pages)} route(s) compile cleanly.")

    # Enterprise policy budget: a per-page JS ceiling (SPEC 18.5).
    max_bundle = registry.policy.get("max_bundle_gzip")
    if max_bundle is not None:
        from .budgets import measure
        report = measure({"page_gzip": max_bundle})
        over = [c for c in report["checks"]
                if c["name"].startswith("page_gzip") and not c["ok"]]
        if over:
            for check in over:
                print(f"FAIL  policy {check['name']}: "
                      f"{check['actual']} > {check['budget']} bytes gzip")
            raise SystemExit(1)

    # Performance-budget enforcement (SPEC 17.2): CI fails when the app
    # exceeds its configured budgets.
    budgets = _budget_config()
    if budgets is not False:
        from .budgets import measure
        report = measure(budgets or None)
        for check in report["checks"]:
            if not check["ok"]:
                print(f"FAIL  budget {check['name']}: "
                      f"{check['actual']} > {check['budget']} bytes gzip")
        if not report["ok"]:
            raise SystemExit(1)
        print(f"budgets ok (runtime {report['runtime_gzip']} B, "
              f"app {report['app_gzip']} B gzip)")


def _budget_config() -> dict | bool:
    """Budgets from virel.toml [budgets]. Returns False to disable
    (enabled = false), a dict of overrides, or {} for defaults."""
    import tomllib
    config_path = Path.cwd() / "virel.toml"
    if not config_path.exists():
        return {}
    try:
        section = tomllib.loads(config_path.read_text("utf-8")).get(
            "budgets", {})
    except Exception:
        return {}
    if section.get("enabled") is False:
        return False
    return {k: v for k, v in section.items()
            if k != "enabled" and isinstance(v, int)}


def cmd_budget(args: argparse.Namespace) -> None:
    """Report performance-budget measurements (SPEC 17.2)."""
    _load_app(Path.cwd())
    from .budgets import component_bundle_cost, measure
    budgets = _budget_config()
    report = measure(budgets or None)
    if args.json:
        report["component_cost"] = component_bundle_cost()
        print(json.dumps(report, indent=2))
        return
    print(f"runtime:      {report['runtime_gzip']:>6} B gzip  "
          f"(budget {report['budgets']['runtime_gzip']})")
    print(f"largest page: {report['largest_page_gzip']:>6} B gzip  "
          f"(budget {report['budgets']['page_gzip']})")
    print(f"app total:    {report['app_gzip']:>6} B gzip  "
          f"(budget {report['budgets']['app_gzip']})")
    print()
    for entry in sorted(report["pages"], key=lambda p: -p["page_gzip"]):
        flag = "  OVER" if entry["over_budget"] else ""
        print(f"  {entry['route']:30s} {entry['page_gzip']:>6} B{flag}")
    print("\nComponent bundle cost (runtime helpers, gzip bytes):")
    for name, cost in sorted(component_bundle_cost().items(),
                             key=lambda kv: -kv[1]):
        if cost:
            print(f"  {name:22s} {cost:>5} B")
    print("\n" + ("All budgets pass." if report["ok"]
                  else "Some budgets exceeded."))
    if not report["ok"]:
        raise SystemExit(1)


def cmd_routes(args: argparse.Namespace) -> None:
    _load_app(Path.cwd())
    for page in active_registry().pages.values():
        dynamic = " (dynamic)" if page.is_dynamic else ""
        print(f"{page.path:35s} render={page.render}{dynamic}  -> {page.fn.__module__}.{page.name}")


def cmd_preview(args: argparse.Namespace) -> None:
    """Serve the built dist/ directory locally (SPEC 15.1), so a
    production build can be verified before deployment."""
    root = Path.cwd()
    dist = root / "dist"
    if not dist.exists():
        _fail("no dist/ directory; run `virel build` first.")
    import functools
    import http.server
    import socketserver
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(dist))
    with socketserver.TCPServer((args.host, args.port), handler) as httpd:
        print(f"virel preview: http://{args.host}:{args.port} "
              f"(serving {dist})")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def cmd_test(args: argparse.Namespace) -> None:
    """Run the project's test suite (SPEC 15.1), a thin wrapper over
    pytest so agents and humans have one command."""
    import subprocess
    command = [sys.executable, "-m", "pytest"]
    if args.filter:
        command += ["-k", args.filter]
    if args.paths:
        command += args.paths
    raise SystemExit(subprocess.run(command).returncode)


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check the environment and project health (SPEC 15.1)."""
    from .doctor import run_doctor
    report = run_doctor(Path.cwd())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        ok = True
        for check in report["checks"]:
            mark = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}[
                check["status"]]
            print(f"{mark}  {check['name']}: {check['detail']}")
            if check["status"] == "fail":
                ok = False
        print(report["summary"])
        if not ok:
            raise SystemExit(1)


def cmd_graph(args: argparse.Namespace) -> None:
    """Render the route and server-action dependency graph (SPEC 15.1)."""
    _load_app(Path.cwd())
    from .graph import build_graph, graph_dot, graph_text
    graph = build_graph()
    if args.format == "json":
        print(json.dumps(graph, indent=2))
    elif args.format == "dot":
        print(graph_dot(graph))
    else:
        print(graph_text(graph))


def cmd_migrate(args: argparse.Namespace) -> None:
    """Generate migration patches for deprecated or renamed APIs
    (SPEC 15.1, 14.4)."""
    from .migrate import available_migrations, run_migration
    if args.list or not args.name:
        print("Available migrations:")
        for name, description in available_migrations().items():
            print(f"  {name}: {description}")
        return
    root = Path.cwd()
    try:
        patches = run_migration(args.name, root, apply=args.apply)
    except VirelCompileError as error:
        _fail(str(error))
    if not patches:
        print("No changes needed.")
        return
    for patch in patches:
        print(f"{'applied' if args.apply else 'would change'}: "
              f"{patch['path']} ({patch['changes']} change(s))")
        if args.diff and not args.apply:
            print(patch["diff"])
    if not args.apply:
        print(f"\nRun with --apply to write {len(patches)} file(s).")


def cmd_deploy(args: argparse.Namespace) -> None:
    """Generate deployment artifacts for a target (SPEC 15.1)."""
    root = Path.cwd()
    config = _load_app(root)
    allowed = active_registry().policy.get("deployment_targets")
    if allowed is not None and args.target not in allowed:
        _fail(f"deployment target {args.target!r} is not in the policy "
              f"allowlist {sorted(allowed)}.")
    from .deploy import generate_artifacts
    try:
        written = generate_artifacts(root, config, target=args.target)
    except VirelCompileError as error:
        _fail(str(error))
    print(f"Wrote {len(written)} deployment artifact(s) for "
          f"{args.target}:")
    for path in written:
        print(f"  {path}")
    print("\nReview the generated files, then follow their header notes "
          "to deploy.")


def cmd_sbom(args: argparse.Namespace) -> None:
    """Emit a CycloneDX SBOM of the application and its dependencies
    (SPEC 18.2)."""
    root = Path.cwd()
    config = _load_app(root)
    app_conf = config.get("app", {})
    from .sbom import generate_sbom
    doc = generate_sbom(root, app_name=app_conf.get("name", "virel-app"),
                        app_version=str(app_conf.get("version", "0.0.0")))
    text = json.dumps(doc, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"SBOM ({len(doc['components'])} components) written to "
              f"{args.output}")
    else:
        print(text)


def cmd_inspect(args: argparse.Namespace) -> None:
    _load_app(Path.cwd())
    registry = active_registry()
    page = registry.pages.get(args.route)
    if page is None:
        _fail(f"no route {args.route!r}. Known routes: "
              f"{', '.join(registry.pages)}")
    params = {name: f"sample-{name}" for name in page.param_names}
    compiled = compile_page(page, params=params or None)
    print(json.dumps(compiled.ir, indent=2))


def cmd_bind(args: argparse.Namespace) -> None:
    if args.manifest == "npm":
        if not args.package:
            _fail("Usage: virel bind npm <package> [--version v] [--out f]")
        from .bind import bind_npm
        try:
            source, vendor_dir = bind_npm(args.package, Path.cwd(),
                                          version=args.version)
        except VirelCompileError as error:
            _fail(str(error))
        print(f"Vendored {args.package} into {vendor_dir}")
    else:
        from .bind import bind_manifest
        manifest = Path(args.manifest)
        if not manifest.exists():
            _fail(f"manifest {manifest} does not exist")
        if not args.module:
            _fail("--module is required when binding a manifest file")
        try:
            source = bind_manifest(manifest, args.module)
        except VirelCompileError as error:
            _fail(str(error))
    if args.out:
        Path(args.out).write_text(source)
        print(f"Wrote bindings to {args.out}")
    else:
        print(source, end="")


def cmd_schema(args: argparse.Namespace) -> None:
    """Machine-readable component schema for agents (SPEC 14.2)."""
    from .schema import component_schema, list_components
    if args.list or args.component is None:
        print(json.dumps({"components": list_components()}, indent=2))
        return
    try:
        print(json.dumps(component_schema(args.component), indent=2))
    except VirelCompileError as error:
        _fail(str(error))


def extract_message_keys(package_dir: Path) -> tuple[set[str], list[str]]:
    """Scan Python sources for ui.t("key", ...) calls. Returns the
    literal keys plus locations whose key is dynamic (not extractable)."""
    import ast as _ast
    keys: set[str] = set()
    dynamic: list[str] = []
    for path in sorted(package_dir.rglob("*.py")):
        tree = _ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            fn = node.func
            named_t = (isinstance(fn, _ast.Attribute) and fn.attr == "t"
                       and isinstance(fn.value, _ast.Name)
                       and fn.value.id == "ui")
            if not named_t or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, _ast.Constant) and isinstance(first.value, str):
                keys.add(first.value)
            else:
                dynamic.append(f"{path}:{node.lineno}")
    return keys, dynamic


def cmd_element(args: argparse.Namespace) -> None:
    """Export a component as a standard custom element (SPEC 13.4)."""
    _load_app(Path.cwd())
    module_name, _, fn_name = args.function.partition(":")
    if not fn_name:
        _fail("Use module:function, e.g. app.routes.home:pricing_card")
    import importlib
    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, fn_name)
    except (ImportError, AttributeError) as error:
        _fail(f"Cannot import {args.function!r}: {error}")
    from .embed import as_custom_element
    source = as_custom_element(fn, tag=args.tag)
    if args.out:
        Path(args.out).write_text(source, encoding="utf-8")
        print(f"Wrote {args.tag} ({len(source)} bytes) to {args.out}")
    else:
        print(source)


def cmd_mcp(args: argparse.Namespace) -> None:
    """Run the MCP server for agents (SPEC 14.4)."""
    from .mcp import serve
    serve(Path.cwd())


def cmd_lsp(args: argparse.Namespace) -> None:
    """Run the language server for editors (SPEC 15.4)."""
    from .lsp import serve
    serve()


def cmd_context(args: argparse.Namespace) -> None:
    """Generate a task-specific context pack (SPEC 14.3)."""
    from .contextpack import context_pack
    components = [c for c in (args.components or "").split(",") if c]
    features = [f for f in (args.features or "").split(",") if f]
    if not components and not features:
        _fail("Give --components and/or --features, e.g. "
              "virel context --components form,dialog "
              "--features validation")
    try:
        pack = context_pack(components=components, features=features,
                            budget=args.budget)
    except VirelCompileError as error:
        _fail(str(error))
    if args.out:
        Path(args.out).write_text(pack, encoding="utf-8")
        print(f"Wrote context pack ({len(pack)} bytes) to {args.out}")
    else:
        print(pack, end="")


def cmd_messages(args: argparse.Namespace) -> None:
    """Extraction tooling (SPEC 11.3): compare the message keys the app
    uses against every registered catalog."""
    root = Path.cwd()
    _load_app(root)
    registry = active_registry()
    app_dir = root / "app" if (root / "app").is_dir() else root
    used, dynamic = extract_message_keys(app_dir)
    report: dict[str, Any] = {"used": sorted(used), "dynamic": dynamic,
                              "locales": {}}
    missing_total = 0
    for locale in sorted(registry.catalogs):
        catalog = set(registry.catalogs[locale])
        missing = sorted(used - catalog)
        unused = sorted(catalog - used)
        missing_total += len(missing)
        report["locales"][locale] = {"missing": missing, "unused": unused}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{len(used)} message key(s) in use")
        for location in dynamic:
            print(f"  dynamic key (not extractable): {location}")
        if not registry.catalogs:
            print("No catalogs registered (ui.messages).")
        for locale, entry in report["locales"].items():
            status = "ok" if not entry["missing"] else "MISSING"
            print(f"{locale}: {status}")
            for key in entry["missing"]:
                print(f"  missing: {key}")
            for key in entry["unused"]:
                print(f"  unused:  {key}")
    if missing_total:
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="virel",
        description="Professional interfaces, written in Python.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="scaffold a new application")
    p_new.add_argument("name")
    p_new.set_defaults(fn=cmd_new)

    p_dev = sub.add_parser("dev", help="run the development server")
    p_dev.add_argument("--host", default="127.0.0.1")
    p_dev.add_argument("--port", type=int, default=8000)
    p_dev.set_defaults(fn=cmd_dev)

    p_build = sub.add_parser("build", help="build for deployment")
    p_build.add_argument("--target", choices=["static", "asgi"], default="static")
    p_build.set_defaults(fn=cmd_build)

    p_check = sub.add_parser("check", help="compile all routes and report diagnostics")
    p_check.add_argument("--json", action="store_true")
    p_check.set_defaults(fn=cmd_check)

    p_routes = sub.add_parser("routes", help="list routes")
    p_routes.set_defaults(fn=cmd_routes)

    p_preview = sub.add_parser(
        "preview", help="serve the built dist/ directory locally")
    p_preview.add_argument("--host", default="127.0.0.1")
    p_preview.add_argument("--port", type=int, default=8000)
    p_preview.set_defaults(fn=cmd_preview)

    p_test = sub.add_parser("test", help="run the project's test suite")
    p_test.add_argument("paths", nargs="*", help="test paths (default: all)")
    p_test.add_argument("-k", dest="filter", help="pytest -k filter")
    p_test.set_defaults(fn=cmd_test)

    p_doctor = sub.add_parser(
        "doctor", help="check the environment and project health")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.set_defaults(fn=cmd_doctor)

    p_budget = sub.add_parser(
        "budget", help="report performance-budget measurements")
    p_budget.add_argument("--json", action="store_true")
    p_budget.set_defaults(fn=cmd_budget)

    p_graph = sub.add_parser(
        "graph", help="render the route and dependency graph")
    p_graph.add_argument("--format", choices=["text", "json", "dot"],
                         default="text")
    p_graph.set_defaults(fn=cmd_graph)

    p_migrate = sub.add_parser(
        "migrate", help="generate migration patches for API changes")
    p_migrate.add_argument("name", nargs="?", help="migration name")
    p_migrate.add_argument("--list", action="store_true",
                           help="list available migrations")
    p_migrate.add_argument("--apply", action="store_true",
                           help="write the changes (default: dry run)")
    p_migrate.add_argument("--diff", action="store_true",
                           help="show a unified diff in a dry run")
    p_migrate.set_defaults(fn=cmd_migrate)

    p_deploy = sub.add_parser(
        "deploy", help="generate deployment artifacts for a target")
    p_deploy.add_argument("--target", choices=["asgi", "static"],
                          default="asgi")
    p_deploy.set_defaults(fn=cmd_deploy)

    p_sbom = sub.add_parser(
        "sbom", help="emit a CycloneDX SBOM of the app and its dependencies")
    p_sbom.add_argument("-o", "--output", help="write to a file instead of stdout")
    p_sbom.set_defaults(fn=cmd_sbom)

    p_inspect = sub.add_parser("inspect", help="print the UI IR for a route")
    p_inspect.add_argument("route")
    p_inspect.set_defaults(fn=cmd_inspect)

    p_bind = sub.add_parser(
        "bind", help="generate typed bindings from a custom elements manifest")
    p_bind.add_argument("manifest",
                        help="path to custom-elements.json, or 'npm'")
    p_bind.add_argument("package", nargs="?",
                        help="npm package name (with manifest='npm')")
    p_bind.add_argument("--module",
                        help="URL of the JS module that defines the "
                             "elements (manifest mode)")
    p_bind.add_argument("--version", default="latest",
                        help="npm package version (npm mode)")
    p_bind.add_argument("--out", help="write the bindings to this file "
                                      "instead of stdout")
    p_bind.set_defaults(fn=cmd_bind)

    p_schema = sub.add_parser("schema", help="print a component schema as JSON")
    p_schema.add_argument("component", nargs="?")
    p_schema.add_argument("--json", action="store_true",
                          help="JSON output (the default)")
    p_schema.add_argument("--list", action="store_true",
                          help="list every component name")
    p_schema.set_defaults(fn=cmd_schema)

    p_element = sub.add_parser(
        "element", help="export a component as a standard custom element")
    p_element.add_argument("function", help="module:function to compile")
    p_element.add_argument("--tag", required=True,
                           help="custom element tag, e.g. virel-counter")
    p_element.add_argument("--out", help="write the module to this file")
    p_element.set_defaults(fn=cmd_element)

    p_mcp = sub.add_parser(
        "mcp", help="run the MCP server for agent tools (stdio)")
    p_mcp.set_defaults(fn=cmd_mcp)

    p_lsp = sub.add_parser(
        "lsp", help="run the language server for editors (stdio)")
    p_lsp.set_defaults(fn=cmd_lsp)

    p_context = sub.add_parser(
        "context", help="generate a compact context pack for an agent")
    p_context.add_argument("--components", default="",
                           help="comma-separated component names")
    p_context.add_argument("--features", default="",
                           help="comma-separated features")
    p_context.add_argument("--budget", type=int, default=12000,
                           help="approximate token budget")
    p_context.add_argument("--out", help="write the pack to this file")
    p_context.set_defaults(fn=cmd_context)

    p_messages = sub.add_parser(
        "messages", help="extract ui.t keys and audit catalogs per locale")
    p_messages.add_argument("--json", action="store_true")
    p_messages.set_defaults(fn=cmd_messages)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
