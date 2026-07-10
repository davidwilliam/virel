"""The canonical Virel authoring API: ``from virel import ui``.

One obvious way to do each thing (SPEC 6.9). Everything here is re-exported
from the internal modules; the internal modules are not public API.
"""

from __future__ import annotations

from typing import Any, Callable

from .expr import Derived, State, VirelCompileError, cond, length, not_
from .elements import (
    Alert,
    AppShell,
    Badge,
    Button,
    Card,
    Checkbox,
    Code,
    Container,
    Divider,
    EmptyState,
    Heading,
    Image,
    Link,
    List,
    Nav,
    Page,
    Row,
    Section,
    Select,
    Spacer,
    Stack,
    Text,
    TextField,
    set_from_event,
    unsafe_html,
)
from .nodes import Node, When
from .registry import component, page, server, web_component
from .theme import Theme


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
    "page", "component", "server", "web_component",
    "state", "derived", "cond", "not_", "length", "set_from_event",
    "use_theme", "Theme", "Node", "VirelCompileError",
    # layout
    "Page", "Stack", "Row", "Container", "Section", "Card",
    "Divider", "Spacer", "AppShell",
    # semantic + styled components
    "Heading", "Text", "Code", "Link", "Image", "List", "Nav",
    "Button", "TextField", "Select", "Checkbox",
    "Alert", "Badge", "EmptyState", "When", "unsafe_html",
]
