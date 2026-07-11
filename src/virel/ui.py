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
    EmptyState,
    Heading,
    Image,
    Link,
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
    Tooltip,
    set_from_event,
    unsafe_html,
)
from .icons import Icon, icon_names
from .nodes import Node, When
from .registry import client, component, page, server, web_component
from .theme import Theme
from . import testing as test


def state(initial: Any) -> State:
    """Browser-local reactive state (SPEC 8.2). Lives in the browser only;
    the server never holds it."""
    return State(initial)


def derived(fn: Callable[[], Any]) -> Derived:
    """Computed reactive value; recalculated when its dependencies change."""
    return Derived(fn)


def use_theme(theme: Theme) -> None:
    """Install an application-wide theme (design tokens)."""
    from .registry import active_registry
    active_registry().theme = theme


__all__ = [
    # programming model
    "page", "component", "server", "client", "web_component",
    "state", "derived", "cond", "not_", "length", "set_from_event",
    "use_theme", "Theme", "Node", "VirelCompileError", "test",
    # layout
    "Page", "Stack", "Row", "Container", "Section", "Card",
    "Divider", "Spacer", "AppShell",
    # semantic elements
    "Heading", "Text", "Code", "Link", "Image", "List", "Nav",
    "unsafe_html", "When",
    # form controls
    "Button", "TextField", "Select", "Checkbox", "Textarea",
    "NumberField", "Slider", "Switch", "RadioGroup",
    # interaction patterns
    "Tabs", "Dialog", "Accordion", "Tooltip",
    # data display and status
    "Table", "Stat", "Progress", "Spinner", "Skeleton", "Avatar",
    "Breadcrumbs", "Alert", "Badge", "EmptyState", "Icon", "icon_names",
]
