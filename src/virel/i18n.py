"""Internationalization (SPEC 11.3).

Message catalogs are plain dictionaries registered per locale. ``ui.t``
resolves at compile time against the active locale, so each locale gets its
own compiled page with translated static HTML. Placeholders accept reactive
values, in which case the translation compiles to a reactive expression and
updates in the browser like any other binding.

    ui.messages("en", {
        "greeting": "Hello {name}",
        "runs": {"one": "{count} run", "other": "{count} runs"},
    })
    ui.messages("pt", {
        "greeting": "Ola {name}",
        "runs": {"one": "{count} execucao", "other": "{count} execucoes"},
    })

    ui.Text(ui.t("greeting", name=user_name))
    ui.Text(ui.t("runs", count=total))

The server negotiates the locale per request from Accept-Language (with a
``?lang=`` override); static builds use the default locale.
"""

from __future__ import annotations

import re
from typing import Any

from .expr import (
    Compare,
    Expr,
    FormatString,
    Lit,
    Ternary,
    VirelCompileError,
    current_context,
    in_trace,
)

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def messages(locale: str, catalog: dict[str, Any]) -> None:
    """Register (or extend) the message catalog for a locale."""
    from .registry import active_registry
    registry = active_registry()
    for key, value in catalog.items():
        if isinstance(value, dict):
            missing = {"one", "other"} - set(value)
            if missing:
                raise VirelCompileError(
                    f"Plural message {key!r} for locale {locale!r} must "
                    "define 'one' and 'other' forms."
                )
        elif not isinstance(value, str):
            raise VirelCompileError(
                f"Message {key!r} for locale {locale!r} must be a string or "
                "a plural dict with 'one' and 'other'."
            )
    registry.catalogs.setdefault(locale, {}).update(catalog)


def available_locales() -> list[str]:
    from .registry import active_registry
    registry = active_registry()
    locales = list(registry.catalogs)
    if registry.default_locale not in locales:
        locales.insert(0, registry.default_locale)
    return locales


def active_locale() -> str:
    from .registry import active_registry
    if in_trace():
        locale = getattr(current_context(), "locale", None)
        if locale:
            return locale
    return active_registry().default_locale


def _lookup(key: str) -> Any:
    from .registry import active_registry
    registry = active_registry()
    locale = active_locale()
    for candidate in (locale, registry.default_locale):
        catalog = registry.catalogs.get(candidate, {})
        if key in catalog:
            return catalog[key]
    known = sorted({
        k for catalog in registry.catalogs.values() for k in catalog
    })
    raise VirelCompileError(
        f"No message {key!r} for locale {locale!r} or the default locale. "
        f"Known keys: {', '.join(known) or '(none)'}."
    )


def t(key: str, **params: Any) -> str | Expr:
    """Resolve a message for the active locale.

    Returns a plain string when every placeholder is a plain value, or a
    reactive expression when any placeholder is reactive.
    """
    message = _lookup(key)
    if isinstance(message, dict):
        return _plural(key, message, params)
    return _fill(key, message, params)


def _fill(key: str, template: str, params: dict[str, Any]) -> str | Expr:
    names = set(_PLACEHOLDER.findall(template))
    missing = names - set(params)
    if missing:
        raise VirelCompileError(
            f"Message {key!r} needs placeholder(s): {', '.join(sorted(missing))}."
        )
    if not any(isinstance(params.get(name), Expr) for name in names):
        return template.format(**{name: params[name] for name in names})
    parts: list[str | Expr] = []
    cursor = 0
    for match in _PLACEHOLDER.finditer(template):
        if match.start() > cursor:
            parts.append(template[cursor:match.start()])
        value = params[match.group(1)]
        parts.append(value if isinstance(value, Expr) else Lit(value))
        cursor = match.end()
    if cursor < len(template):
        parts.append(template[cursor:])
    return FormatString(parts)


def _plural(key: str, forms: dict[str, str], params: dict[str, Any]) -> str | Expr:
    if "count" not in params:
        raise VirelCompileError(
            f"Plural message {key!r} requires a count= placeholder."
        )
    count = params["count"]
    if isinstance(count, Expr):
        one = _fill(key, forms["one"], params)
        other = _fill(key, forms["other"], params)
        def as_expr(value: str | Expr) -> Expr:
            return value if isinstance(value, Expr) else Lit(value)
        return Ternary(Compare("==", count, Lit(1)), as_expr(one), as_expr(other))
    form = forms["one"] if count == 1 else forms["other"]
    return _fill(key, form, params)
