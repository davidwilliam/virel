"""The canonical Virel authoring API: ``from virel import ui``.

One obvious way to do each thing (SPEC 6.9). Everything here is re-exported
from the internal modules; the internal modules are not public API.
"""

from __future__ import annotations

from typing import Any, Callable

from .expr import Derived, State, VirelCompileError, cond, length, not_
from .elements import (
    Accordion,
    Article,
    Audio,
    AspectRatio,
    Center,
    Cluster,
    Alert,
    AppShell,
    Avatar,
    Badge,
    Box,
    BrandLogo,
    Breadcrumbs,
    Canvas,
    Button,
    Card,
    Checkbox,
    Code,
    Command,
    CommandPalette,
    Container,
    DateField,
    Dialog,
    Divider,
    DownloadButton,
    EmptyState,
    Example,
    ErrorBoundary,
    ErrorState,
    FileField,
    FilterChips,
    Footer,
    Grid,
    Hero,
    Menu,
    MenuDivider,
    MenuItem,
    Heading,
    Image,
    Link,
    LinkButton,
    List,
    Listbox,
    Nav,
    NumberField,
    Page,
    Pagination,
    Popover,
    Progress,
    RadioGroup,
    Row,
    Section,
    Select,
    Skeleton,
    Slider,
    Spacer,
    Spinner,
    Swipeable,
    Resizable,
    ScrollArea,
    Sidebar,
    Splitter,
    Stack,
    Wrap,
    Stat,
    Switch,
    Table,
    TableOfContents,
    Tabs,
    Text,
    Tree,
    Video,
    Textarea,
    TextField,
    ThemeToggle,
    Tooltip,
    Tour,
    TourStep,
    set_from_event,
    unsafe_html,
)
from .channels import Channel, ChannelClosed, channel, connect
from .charts import Chart, Series
from .data import records
from .datagrid import GridQuery, apply_grid_query, grid_query
from .viz import Figure, figure_style
from .context import Context, context
from .contextpack import canonical_patterns, context_pack
from .schema import component_schema, list_components
from .datagrid import Column, DataGrid
from .elements import Each, Island, Suspense, effect, upload
from .formatting import (collation_key, format_currency, format_date,
                         format_number, format_percent, locale_sorted)
from .forms import Form, FormActions, SubmitButton, form
from .i18n import messages, t
from .icons import Icon, icon_names
from .uploads import FileDownload, UploadFile
from .resources import Resource, invalidate, resource, subscribe
from .nodes import Node, When
from .registry import (Request, build, client, component, deny, layout,
                       worker,
                       page,
                       redirect, server, shared, use_accessibility,
                       use_css, use_guard,
                       use_favicon, use_middleware, use_policy, use_static,
                       use_telemetry, web_component)
from .embed import Fragment, as_custom_element, render_fragment
from .notebook import Preview, preview
from .notifications import notify
from .plugins import Plugin, use_plugin
from .motion import (Easing, Keyframes, Motion, animation, keyframes,
                     spring, transition)
from .styles import Style, recipe, style
from .trust import ServerOnly, secret, server_only
from .theme import (Color, ColorScale, Font, FontFace, GoogleFont, Space,
                    Theme, set_preference)
from . import ai
from . import unsafe
from .browsertest import BrowserPage, browser_page
from . import testing as test


def state(initial: Any, *, persist: str | None = None,
          url: str | None = None) -> State:
    """Browser-local reactive state (SPEC 8.2). Lives in the browser only;
    the server never holds it. With ``persist="key"`` the value survives
    reloads in localStorage; with ``url="q"`` it stays synchronized with a
    URL query parameter."""
    return State(initial, persist=persist, url=url)


def derived(fn: Callable[[], Any]) -> Derived:
    """Computed reactive value; recalculated when its dependencies change."""
    return Derived(fn)


def use_theme(theme: Theme) -> None:
    """Install an application-wide theme (design tokens)."""
    from .registry import active_registry
    active_registry().theme = theme


__all__ = [
    # programming model
    "page", "layout", "component", "server", "client", "worker", "shared", "build",
    "web_component",
    "use_guard", "use_middleware", "use_static", "use_css",
    "use_accessibility", "use_policy", "use_telemetry", "use_favicon",
    "unsafe", "redirect", "deny",
    "Plugin", "use_plugin",
    "Request",
    "channel", "connect", "Channel", "ChannelClosed",
    "context", "Context",
    "context_pack", "canonical_patterns", "component_schema",
    "list_components",
    "state", "derived", "effect", "cond", "not_", "length", "set_from_event",
    "use_theme", "Theme", "Color", "ColorScale", "Space", "Font",
    "style", "Style", "recipe",
    "server_only", "secret", "ServerOnly",
    "Motion", "keyframes", "Keyframes", "animation", "transition",
    "spring", "Easing", "Swipeable",
    "FontFace", "GoogleFont", "set_preference",
    "Node", "VirelCompileError", "test", "ai", "preview", "Preview",
    "BrowserPage", "browser_page",
    "render_fragment", "Fragment", "as_custom_element",
    "messages", "t",
    "format_number", "format_currency", "format_percent", "format_date",
    "locale_sorted", "collation_key", "records",
    # layout
    "Page", "Stack", "Row", "Grid", "Container", "Section", "Card",
    "Wrap", "Cluster", "Center", "Sidebar", "AspectRatio", "ScrollArea",
    "Resizable", "Splitter", "Box", "Canvas", "BrandLogo",
    "Divider", "Spacer", "AppShell", "Footer", "Hero",
    # semantic elements
    "Heading", "Text", "Code", "Example", "Link", "LinkButton", "Image",
    "List", "Nav", "Article", "Video", "Audio", "TableOfContents",
    "unsafe_html", "When",
    # data loading
    "resource", "Resource", "invalidate", "subscribe", "Each",
    "Suspense", "Island",
    "upload", "UploadFile", "FileDownload", "FileField", "DownloadButton",
    # forms
    "form", "Form", "FormActions", "SubmitButton",
    # form controls
    "Button", "TextField", "Select", "Checkbox", "Textarea", "DateField",
    "Listbox", "FilterChips",
    "NumberField", "Slider", "Switch", "RadioGroup", "ThemeToggle",
    # interaction patterns
    "Tabs", "Dialog", "Accordion", "Tooltip", "Popover",
    "Menu", "MenuItem", "MenuDivider", "Pagination", "notify",
    "Tree", "Command", "CommandPalette", "Tour", "TourStep",
    # data display and status
    "Table", "DataGrid", "Column", "Chart", "Series",
    "grid_query", "apply_grid_query", "GridQuery",
    "Figure", "figure_style",
    "Stat", "Progress", "Spinner", "Skeleton", "Avatar",
    "Breadcrumbs", "Alert", "Badge", "EmptyState", "ErrorBoundary",
    "ErrorState", "Icon", "icon_names",
]


# Enterprise policy: approved-components allowlist (SPEC 18.5). When set,
# constructing a component not on the list is a build error. Wrapping the
# public constructors is one chokepoint; functools.wraps keeps the
# signature so schema introspection is unchanged.
def _install_component_policy() -> None:
    import functools

    _COMPONENTS = {
        name for name in __all__
        if name[0].isupper() and callable(globals().get(name))
        and name not in ("Theme", "Color", "ColorScale", "Space", "Font",
                         "FontFace", "GoogleFont", "Motion", "Keyframes",
                         "Easing", "Style", "Plugin", "Request", "Context",
                         "Channel", "ChannelClosed", "Resource", "Node",
                         "VirelCompileError", "Preview", "BrowserPage",
                         "Fragment", "UploadFile", "FileDownload",
                         "GridQuery", "Column", "Series", "Command",
                         "TourStep", "ServerOnly", "MenuItem", "MenuDivider",
                         "MenuDivider")
    }

    def wrap(name: str, fn: Any) -> Any:
        @functools.wraps(fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            from .registry import active_registry
            approved = active_registry().policy.get("approved_components")
            if approved is not None and name not in approved:
                raise VirelCompileError(
                    f"Component ui.{name} is not in the approved-components "
                    "allowlist (policy).")
            return fn(*args, **kwargs)
        return guarded

    for name in _COMPONENTS:
        globals()[name] = wrap(name, globals()[name])


_install_component_policy()
