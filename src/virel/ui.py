"""The canonical Virel authoring API: ``from virel import ui``.

One obvious way to do each thing (SPEC 6.9). Everything here is re-exported
from the internal modules; the internal modules are not public API.
"""

from __future__ import annotations

from typing import Any, Callable

from .expr import Derived, State, VirelCompileError, cond, length, not_
from .elements import (
    Accordion,
    Alert,
    AppShell,
    Avatar,
    Badge,
    Breadcrumbs,
    Button,
    Card,
    Checkbox,
    Code,
    Container,
    Dialog,
    Divider,
    DownloadButton,
    EmptyState,
    ErrorBoundary,
    ErrorState,
    FileField,
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
    Nav,
    NumberField,
    Page,
    Progress,
    RadioGroup,
    Row,
    Section,
    Select,
    Skeleton,
    Slider,
    Spacer,
    Spinner,
    Stack,
    Stat,
    Switch,
    Table,
    Tabs,
    Text,
    Textarea,
    TextField,
    ThemeToggle,
    Tooltip,
    set_from_event,
    unsafe_html,
)
from .channels import Channel, ChannelClosed, channel, connect
from .context import Context, context
from .elements import Each, Island, Suspense, effect, upload
from .formatting import (format_currency, format_date, format_number,
                         format_percent)
from .forms import Form, FormActions, SubmitButton, form
from .i18n import messages, t
from .icons import Icon, icon_names
from .uploads import FileDownload, UploadFile
from .resources import Resource, invalidate, resource, subscribe
from .nodes import Node, When
from .registry import (Request, build, client, component, deny, layout,
                       page,
                       redirect, server, shared, use_guard,
                       use_middleware, web_component)
from .theme import FontFace, GoogleFont, Theme
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
    "page", "layout", "component", "server", "client", "shared", "build",
    "web_component",
    "use_guard", "use_middleware", "redirect", "deny", "Request",
    "channel", "connect", "Channel", "ChannelClosed",
    "context", "Context",
    "state", "derived", "effect", "cond", "not_", "length", "set_from_event",
    "use_theme", "Theme", "FontFace", "GoogleFont", "Node", "VirelCompileError", "test",
    "messages", "t",
    "format_number", "format_currency", "format_percent", "format_date",
    # layout
    "Page", "Stack", "Row", "Grid", "Container", "Section", "Card",
    "Divider", "Spacer", "AppShell", "Footer", "Hero",
    # semantic elements
    "Heading", "Text", "Code", "Link", "LinkButton", "Image", "List", "Nav",
    "unsafe_html", "When",
    # data loading
    "resource", "Resource", "invalidate", "subscribe", "Each",
    "Suspense", "Island",
    "upload", "UploadFile", "FileDownload", "FileField", "DownloadButton",
    # forms
    "form", "Form", "FormActions", "SubmitButton",
    # form controls
    "Button", "TextField", "Select", "Checkbox", "Textarea",
    "NumberField", "Slider", "Switch", "RadioGroup", "ThemeToggle",
    # interaction patterns
    "Tabs", "Dialog", "Accordion", "Tooltip",
    "Menu", "MenuItem", "MenuDivider",
    # data display and status
    "Table", "Stat", "Progress", "Spinner", "Skeleton", "Avatar",
    "Breadcrumbs", "Alert", "Badge", "EmptyState", "ErrorBoundary",
    "ErrorState", "Icon", "icon_names",
]
