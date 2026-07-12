"""Compile-time accessibility audit (SPEC 11.2).

Much of the accessibility contract is enforced by construction: images
require alt text, inputs require labels, icons are hidden from
assistive technology unless labeled, and click handlers cannot be
attached to noninteractive elements because the typed API has no way to
express that. This module covers what construction cannot: whole-tree
properties checked when a page compiles.

Unambiguous failures are errors; judgment calls are warnings, printed
by ``virel check`` and promoted to errors under
``ui.use_accessibility(strict=True)``.
"""

from __future__ import annotations

import re
from typing import Any

from .expr import Expr, VirelCompileError
from .nodes import BindText, Element, Node, TextNode, When

_FOCUSABLE_TAGS = ("button", "a", "input", "select", "textarea")
_VAGUE_LINK_TEXT = ("click here", "here", "link", "read more", "more",
                    "learn more", "this")


def _present(value: Any) -> bool:
    """Attribute presence without triggering reactive truthiness: a
    bound expression counts as present (its value exists in the
    browser), so audits never guess at runtime values."""
    if value is None or value is False:
        return False
    if isinstance(value, Expr):
        return True
    return bool(str(value).strip())


def audit_page(route: str, children: list[Node], strict: bool) -> list[str]:
    """Audit a compiled page tree. Raises VirelCompileError for hard
    failures; returns warnings (raised too in strict mode)."""
    warnings: list[str] = []
    headings: list[int] = []

    def walk(node: Node) -> None:
        if isinstance(node, Element):
            _check_element(route, node, warnings, headings)
            for child in node.children:
                walk(child)
        elif isinstance(node, When):
            for child in (*node.then, *node.otherwise):
                walk(child)
        else:
            for child in getattr(node, "template", []) or []:
                walk(child)
            for child in getattr(node, "children", []) or []:
                walk(child)

    for child in children:
        walk(child)

    if headings.count(1) > 1:
        warnings.append(f"[{route}] Multiple h1 headings; a page should "
                        "have one top-level heading.")
    previous = None
    for level in headings:
        if previous is not None and level > previous + 1:
            warnings.append(
                f"[{route}] Heading progression skips from h{previous} to "
                f"h{level}; use Heading(level={previous + 1}, size={level}) "
                "to keep the visual size with correct semantics.")
        previous = level

    if strict and warnings:
        raise VirelCompileError(
            "Accessibility (strict): " + " ".join(warnings))
    return warnings


def _check_element(route: str, node: Element, warnings: list[str],
                   headings: list[int]) -> None:
    match = re.fullmatch(r"h([1-6])", node.tag)
    if match:
        headings.append(int(match.group(1)))

    hidden = node.attrs.get("aria-hidden")
    if not isinstance(hidden, Expr) and str(hidden) == "true":
        focusable = _find_focusable(node)
        if focusable is not None:
            raise VirelCompileError(
                f"[{route}] <{focusable}> inside an aria-hidden subtree is "
                "focusable but invisible to assistive technology. Remove "
                "the control or the aria-hidden attribute.")

    interactive = node.tag == "button" or (
        node.tag == "a" and _present(node.attrs.get("href")))
    if interactive and not _accessible_name(node):
        raise VirelCompileError(
            f"[{route}] <{node.tag}> has no accessible name: no text "
            "content and no aria-label. Pass aria_label= or use "
            "Icon(label=...).")

    if node.tag == "a" and _present(node.attrs.get("href")):
        text = _text_content(node).strip().lower().rstrip(".")
        if text in _VAGUE_LINK_TEXT:
            warnings.append(
                f"[{route}] Link text {text!r} does not describe its "
                "target; name the destination instead.")


def _find_focusable(node: Element) -> str | None:
    for child in node.children:
        if isinstance(child, Element):
            tabindex = child.attrs.get("tabindex")
            if child.tag in _FOCUSABLE_TAGS and \
                    str(child.attrs.get("tabindex")) != "-1":
                return child.tag
            if tabindex is not None and str(tabindex) != "-1":
                return child.tag
            found = _find_focusable(child)
            if found:
                return found
    return None


def _accessible_name(node: Element) -> bool:
    if _present(node.attrs.get("aria-label")) \
            or _present(node.attrs.get("aria-labelledby")):
        return True
    return bool(_text_content(node).strip()) or _has_dynamic_text(node)


def _has_dynamic_text(node: Node) -> bool:
    if isinstance(node, BindText):
        return True
    for child in getattr(node, "children", []) or []:
        if _has_dynamic_text(child):
            return True
    return False


def _text_content(node: Node) -> str:
    if isinstance(node, TextNode):
        return node.text
    if isinstance(node, Element):
        hidden = node.attrs.get("aria-hidden")
        if not isinstance(hidden, Expr) and str(hidden) == "true":
            # Hidden content contributes nothing to the accessible
            # name, but an aria-label on the element itself does.
            label = node.attrs.get("aria-label")
            return str(label) if _present(label) else ""
    parts = []
    if isinstance(node, Element) and _present(node.attrs.get("aria-label")):
        parts.append(str(node.attrs["aria-label"]))
    for child in getattr(node, "children", []) or []:
        parts.append(_text_content(child))
    return " ".join(parts)