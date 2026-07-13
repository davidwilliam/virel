"""The plugin system (SPEC 13.5).

A plugin subclasses :class:`Plugin`, declares the capabilities it
participates in, and implements the matching hooks. Capabilities are a
contract: a hook whose capability is not declared never runs, declaring
a capability without policy permission fails at registration, and an
implemented hook without its declared capability is a registration
error rather than silence.

Capabilities and their hooks:

- ``compile``: ``compiler_pass(root, route)`` sees every page tree
  before the accessibility audit and emission.
- ``lint``: ``lint(compiled)`` returns warnings that join the compile
  warnings ``virel check`` prints.
- ``components``: ``components()`` returns named constructors,
  registered for discovery.
- ``routes``: ``routes()`` returns ``(path, fn)`` pairs registered as
  ordinary pages.
- ``build``: ``build_config(config)`` sees the parsed virel.toml before
  a build.
- ``assets``: ``transform_asset(path, content)`` rewrites text assets
  as the build writes them.
- ``deploy``: ``post_build(dist)`` runs after a build completes.
- ``test``: ``on_test_render(view)`` observes every ui.test.render.
- ``inspector``: ``inspector_panel()`` contributes a panel to the dev
  inspector's IR endpoint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .expr import VirelCompileError

CAPABILITIES = frozenset({
    "compile", "lint", "components", "routes", "build", "assets",
    "deploy", "test", "inspector",
})

_HOOK_CAPABILITY = {
    "compiler_pass": "compile",
    "lint": "lint",
    "components": "components",
    "routes": "routes",
    "build_config": "build",
    "transform_asset": "assets",
    "post_build": "deploy",
    "on_test_render": "test",
    "inspector_panel": "inspector",
}


class Plugin:
    """Base class for plugins. Subclass, set ``name`` and
    ``capabilities``, and implement the hooks those capabilities name."""

    name: str = ""
    capabilities: tuple[str, ...] = ()

    def compiler_pass(self, root: Any, route: str) -> None: ...

    def lint(self, compiled: Any) -> list[str]:
        return []

    def components(self) -> dict[str, Callable[..., Any]]:
        return {}

    def routes(self) -> list[tuple[str, Callable[..., Any]]]:
        return []

    def build_config(self, config: dict[str, Any]) -> None: ...

    def transform_asset(self, path: str, content: str) -> str:
        return content

    def post_build(self, dist: Path) -> None: ...

    def on_test_render(self, view: Any) -> None: ...

    def inspector_panel(self) -> dict[str, Any]:
        return {}


def use_plugin(plugin: Plugin) -> None:
    """Register a plugin (SPEC 13.5). Capabilities are validated against
    the known set and against policy
    (``ui.use_policy(plugin_capabilities={...})``), and hooks the plugin
    overrides must be covered by its declared capabilities."""
    from .registry import active_registry
    registry = active_registry()
    if not isinstance(plugin, Plugin):
        raise VirelCompileError(
            "use_plugin takes a ui.Plugin instance.")
    if not plugin.name:
        raise VirelCompileError("Plugins must set a name.")
    declared = set(plugin.capabilities)
    unknown = declared - CAPABILITIES
    if unknown:
        raise VirelCompileError(
            f"Plugin {plugin.name!r} declares unknown capabilities "
            f"{sorted(unknown)}; known: {', '.join(sorted(CAPABILITIES))}.")
    approved = registry.policy.get("approved_plugins")
    if approved is not None and plugin.name not in approved:
        raise VirelCompileError(
            f"Plugin {plugin.name!r} is not in the approved-plugins "
            "allowlist (policy).")
    allowed = registry.policy.get("plugin_capabilities")
    if allowed is not None:
        excess = declared - set(allowed)
        if excess:
            raise VirelCompileError(
                f"Plugin {plugin.name!r} requires capabilities "
                f"{sorted(excess)} that policy does not allow.")
    for hook, capability in _HOOK_CAPABILITY.items():
        overridden = getattr(type(plugin), hook, None) is not \
            getattr(Plugin, hook)
        if overridden and capability not in declared:
            raise VirelCompileError(
                f"Plugin {plugin.name!r} implements {hook}() but does not "
                f"declare the {capability!r} capability.")
    if any(existing.name == plugin.name for existing in registry.plugins):
        raise VirelCompileError(
            f"A plugin named {plugin.name!r} is already registered.")
    registry.plugins.append(plugin)

    if "routes" in declared:
        from .registry import page as page_decorator
        for path, fn in plugin.routes():
            page_decorator(path)(fn)
    if "components" in declared:
        for name, constructor in plugin.components().items():
            if name in registry.plugin_components:
                raise VirelCompileError(
                    f"Plugin component {name!r} is already registered.")
            registry.plugin_components[name] = constructor


def _active(capability: str) -> list[Plugin]:
    from .registry import active_registry
    return [plugin for plugin in active_registry().plugins
            if capability in plugin.capabilities]


def run_compiler_passes(root: Any, route: str) -> None:
    for plugin in _active("compile"):
        plugin.compiler_pass(root, route)


def run_lints(compiled: Any) -> list[str]:
    warnings: list[str] = []
    for plugin in _active("lint"):
        for warning in plugin.lint(compiled) or []:
            warnings.append(f"[{plugin.name}] {warning}")
    return warnings


def run_build_config(config: dict[str, Any]) -> None:
    for plugin in _active("build"):
        plugin.build_config(config)


def run_asset_transforms(path: str, content: str) -> str:
    for plugin in _active("assets"):
        content = plugin.transform_asset(path, content)
    return content


def run_post_build(dist: Path) -> None:
    for plugin in _active("deploy"):
        plugin.post_build(dist)


def run_test_hooks(view: Any) -> None:
    for plugin in _active("test"):
        plugin.on_test_render(view)


def inspector_panels() -> dict[str, dict[str, Any]]:
    return {plugin.name: plugin.inspector_panel()
            for plugin in _active("inspector")}
