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
    print(f"UI IR written to {ir_dir}")
    print(f"Server action manifest written to {ir_dir.parent / 'actions.json'}")


def cmd_check(args: argparse.Namespace) -> None:
    _load_app(Path.cwd())
    registry = active_registry()
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
                print(json.dumps({"route": page.path, "error": str(error)}))
            else:
                print(f"FAIL  {page.path}\n      {error}")
    if failures:
        raise SystemExit(1)
    print(f"{len(registry.pages)} route(s) compile cleanly.")


def cmd_routes(args: argparse.Namespace) -> None:
    _load_app(Path.cwd())
    for page in active_registry().pages.values():
        dynamic = " (dynamic)" if page.is_dynamic else ""
        print(f"{page.path:35s} render={page.render}{dynamic}  -> {page.fn.__module__}.{page.name}")


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
    from . import elements
    name = args.component
    fn = getattr(elements, name, None)
    if fn is None or not callable(fn):
        available = [n for n in elements.__dict__
                     if n[0].isupper() and callable(getattr(elements, n))]
        _fail(f"unknown component {name!r}. Available: {', '.join(sorted(available))}")
    signature = pyinspect.signature(fn)
    schema = {
        "name": name,
        "import": "from virel import ui",
        "purpose": (fn.__doc__ or "").strip().split("\n")[0],
        "props": {
            param.name: {
                "type": str(param.annotation),
                "default": None if param.default is pyinspect.Parameter.empty
                else repr(param.default),
                "required": param.default is pyinspect.Parameter.empty
                and param.kind is not pyinspect.Parameter.VAR_POSITIONAL,
            }
            for param in signature.parameters.values()
        },
    }
    print(json.dumps(schema, indent=2))


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
    p_schema.add_argument("component")
    p_schema.set_defaults(fn=cmd_schema)

    p_element = sub.add_parser(
        "element", help="export a component as a standard custom element")
    p_element.add_argument("function", help="module:function to compile")
    p_element.add_argument("--tag", required=True,
                           help="custom element tag, e.g. virel-counter")
    p_element.add_argument("--out", help="write the module to this file")
    p_element.set_defaults(fn=cmd_element)

    p_messages = sub.add_parser(
        "messages", help="extract ui.t keys and audit catalogs per locale")
    p_messages.add_argument("--json", action="store_true")
    p_messages.set_defaults(fn=cmd_messages)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
