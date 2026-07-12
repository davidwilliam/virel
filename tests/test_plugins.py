"""The plugin system (SPEC 13.5)."""

import pytest

from virel import ui
from virel.compiler import compile_page
from virel.expr import VirelCompileError
from virel.plugins import (inspector_panels, run_asset_transforms,
                           run_build_config, run_post_build)
from virel.registry import active_registry


class Everything(ui.Plugin):
    name = "everything"
    capabilities = ("compile", "lint", "components", "routes", "build",
                    "assets", "deploy", "test", "inspector")

    def __init__(self):
        self.seen_routes = []
        self.built_with = None
        self.deployed_to = None
        self.tested = 0

    def compiler_pass(self, root, route):
        self.seen_routes.append(route)

    def lint(self, compiled):
        if "TODO" in compiled.html:
            return ["page ships a TODO"]
        return []

    def components(self):
        def PluginBadge(text):
            return ui.Badge(text, intent="primary")
        return {"PluginBadge": PluginBadge}

    def routes(self):
        def plugin_page():
            return ui.Page(ui.Text("Served by a plugin."),
                           title="Plugin")
        return [("/from-plugin", plugin_page)]

    def build_config(self, config):
        self.built_with = config

    def transform_asset(self, path, content):
        if path.endswith(".css"):
            return content + "\n/* stamped by everything */\n"
        return content

    def post_build(self, dist):
        self.deployed_to = dist

    def on_test_render(self, view):
        self.tested += 1

    def inspector_panel(self):
        return {"routes_seen": len(self.seen_routes)}


def test_plugin_participates_across_the_lifecycle(tmp_path):
    plugin = Everything()
    ui.use_plugin(plugin)

    # Route generation registered a real page.
    assert "/from-plugin" in active_registry().pages
    compiled = compile_page(active_registry().pages["/from-plugin"])
    assert "Served by a plugin." in compiled.html
    assert "/from-plugin" in plugin.seen_routes  # the compiler pass ran

    # Component registration is discoverable and usable.
    badge = active_registry().plugin_components["PluginBadge"]("New")
    assert "v-badge" in badge.attrs["class"]

    # Lint warnings join compile warnings.
    @ui.page("/todo")
    def todo():
        return ui.Page(ui.Text("TODO: replace this copy"))

    warnings = compile_page(active_registry().pages["/todo"]).warnings
    assert "[everything] page ships a TODO" in warnings

    # Build, asset, and deploy hooks.
    run_build_config({"app": {"module": "app.app"}})
    assert plugin.built_with == {"app": {"module": "app.app"}}
    assert "stamped by everything" in run_asset_transforms(
        "_virel/app.css", "body {}")
    assert run_asset_transforms("_virel/runtime.js", "let x;") == "let x;"
    run_post_build(tmp_path)
    assert plugin.deployed_to == tmp_path

    # Test observation and inspector panels.
    ui.test.render(todo)
    assert plugin.tested == 1
    assert inspector_panels() == {"everything": {"routes_seen":
                                                 len(plugin.seen_routes)}}


def test_capabilities_are_a_contract():
    class Undeclared(ui.Plugin):
        name = "sneaky"
        capabilities = ("lint",)

        def transform_asset(self, path, content):  # not declared
            return ""

    with pytest.raises(VirelCompileError, match="assets"):
        ui.use_plugin(Undeclared())

    class Unknown(ui.Plugin):
        name = "wild"
        capabilities = ("terraform",)

    with pytest.raises(VirelCompileError, match="unknown capabilities"):
        ui.use_plugin(Unknown())

    class Nameless(ui.Plugin):
        capabilities = ("lint",)

    with pytest.raises(VirelCompileError, match="name"):
        ui.use_plugin(Nameless())


def test_policy_restricts_plugin_capabilities():
    ui.use_policy(plugin_capabilities={"lint", "inspector"})

    class Linter(ui.Plugin):
        name = "linter"
        capabilities = ("lint",)

    ui.use_plugin(Linter())  # within policy

    class Deployer(ui.Plugin):
        name = "deployer"
        capabilities = ("deploy",)

    with pytest.raises(VirelCompileError, match="policy does not allow"):
        ui.use_plugin(Deployer())


def test_undeclared_hooks_never_run():
    class Quiet(ui.Plugin):
        name = "quiet"
        capabilities = ("lint",)

        def lint(self, compiled):
            return []

    ui.use_plugin(Quiet())
    # An assets transform pass leaves content alone: quiet declared no
    # assets capability, so its default hook is not even consulted.
    assert run_asset_transforms("x.css", "body {}") == "body {}"


def test_duplicate_plugin_names_are_rejected():
    class One(ui.Plugin):
        name = "dup"
        capabilities = ("lint",)

    ui.use_plugin(One())
    with pytest.raises(VirelCompileError, match="already registered"):
        ui.use_plugin(One())
