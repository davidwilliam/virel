"""Locale-aware number, currency, percent, and date formatting (SPEC 11.3).

Static values format at compile time in Python using built-in rules for a
documented set of locales. Reactive values compile to Intl calls that run
in the browser with the page's active locale, so formatted output updates
like any other binding. The Python rules match Intl for the common cases;
for locales outside the table, formatting falls back to English conventions
on the server while the browser still uses full Intl data.
"""

from __future__ import annotations

import datetime
from typing import Any

from .expr import Expr, VirelCompileError
from .i18n import active_locale

# decimal separator, grouping separator
_NUMBER_RULES: dict[str, tuple[str, str]] = {
    "en": (".", ","),
    "pt": (",", "."),
    "es": (",", "."),
    "de": (",", "."),
    "it": (",", "."),
    "nl": (",", "."),
    "fr": (",", " "),
    "ja": (".", ","),
}

_CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
    "BRL": "R$", "CAD": "CA$", "AUD": "A$", "CHF": "CHF", "MXN": "MX$",
}
# Locales that place the currency symbol after the amount.
_SYMBOL_AFTER = {"pt", "es", "de", "it", "nl", "fr"}
# Locales that put a space before the percent sign, matching Intl.
_PERCENT_SPACE = {"de", "fr"}

_MONTHS_ABBR = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "pt": ["jan.", "fev.", "mar.", "abr.", "mai.", "jun.",
           "jul.", "ago.", "set.", "out.", "nov.", "dez."],
    "es": ["ene", "feb", "mar", "abr", "may", "jun",
           "jul", "ago", "sept", "oct", "nov", "dic"],
    "de": ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni",
           "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."],
    "fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin",
           "juil.", "août", "sept.", "oct.", "nov.", "déc."],
}

_MONTHS_FULL = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
           "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre",
           "décembre"],
}

# short-date patterns: tokens D (day), M (month), YYYY
_DATE_SHORT = {
    "en": "M/D/YYYY",
    "pt": "DD/MM/YYYY",
    "es": "D/M/YYYY",
    "de": "DD.MM.YYYY",
    "fr": "DD/MM/YYYY",
}
_DATE_MEDIUM = {
    "en": "{mon} {day}, {year}",
    "pt": "{day} de {mon} de {year}",
    "es": "{day} {mon} {year}",
    "de": "{day}. {mon} {year}",
    "fr": "{day} {mon} {year}",
}
_DATE_LONG = {
    "en": "{month} {day}, {year}",
    "pt": "{day} de {month} de {year}",
    "es": "{day} de {month} de {year}",
    "de": "{day}. {month} {year}",
    "fr": "{day} {month} {year}",
}


def _rules(locale: str) -> tuple[str, str]:
    return _NUMBER_RULES.get(locale.split("-")[0], _NUMBER_RULES["en"])


def _table(table: dict, locale: str):
    return table.get(locale.split("-")[0], table["en"])


# ---------------------------------------------------------------------------
# Python implementations (static values, server rendering, tests)
# ---------------------------------------------------------------------------

def _group_digits(text: str, group: str) -> str:
    out = []
    for index, digit in enumerate(reversed(text)):
        if index and index % 3 == 0:
            out.append(group)
        out.append(digit)
    return "".join(reversed(out))


def _py_number(value: float, digits: int | None, locale: str) -> str:
    decimal, group = _rules(locale)
    negative = value < 0
    value = abs(value)
    if digits is None:
        text = f"{value:f}".rstrip("0").rstrip(".") if value % 1 else str(int(value))
        integer, _, fraction = text.partition(".")
    else:
        text = f"{value:.{digits}f}"
        integer, _, fraction = text.partition(".")
    body = _group_digits(integer, group)
    if fraction:
        body += decimal + fraction
    return ("-" if negative else "") + body


def _py_currency(value: float, currency: str, digits: int, locale: str) -> str:
    amount = _py_number(value, digits, locale)
    symbol = _CURRENCY_SYMBOLS.get(currency, currency)
    if locale.split("-")[0] in _SYMBOL_AFTER:
        return f"{amount} {symbol}"
    return f"{symbol}{amount}"


def _py_percent(value: float, digits: int, locale: str) -> str:
    amount = _py_number(value * 100, digits, locale)
    if locale.split("-")[0] in _PERCENT_SPACE:
        return f"{amount} %"
    return f"{amount}%"


def _coerce_date(value: Any) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value).date()
    raise VirelCompileError(
        f"format_date cannot interpret {value!r}; pass a date, datetime, "
        "ISO string, or reactive value."
    )


def _py_date(value: Any, style: str, locale: str) -> str:
    day = _coerce_date(value)
    if style == "short":
        pattern = _table(_DATE_SHORT, locale)
        return (pattern
                .replace("YYYY", f"{day.year:04d}")
                .replace("DD", f"{day.day:02d}")
                .replace("MM", f"{day.month:02d}")
                .replace("D", str(day.day))
                .replace("M", str(day.month)))
    months = _MONTHS_FULL if style == "long" else _MONTHS_ABBR
    pattern = _table(_DATE_LONG if style == "long" else _DATE_MEDIUM, locale)
    return pattern.format(day=day.day, year=day.year,
                          mon=_table(_MONTHS_ABBR, locale)[day.month - 1],
                          month=_table(months, locale)[day.month - 1])


# ---------------------------------------------------------------------------
# Reactive expressions (browser Intl)
# ---------------------------------------------------------------------------

class _IntlNumber(Expr):
    def __init__(self, operand: Expr, options: str, locale: str,
                 py_format) -> None:
        self.operand = operand
        self.options = options  # JS object literal
        self.locale = locale
        self._py = py_format

    def js(self) -> str:
        return (f'new Intl.NumberFormat("{self.locale}", {self.options})'
                f".format({self.operand.js()})")

    def evaluate(self, env: dict[str, Any]) -> Any:
        return self._py(self.operand.evaluate(env))


class _IntlDate(Expr):
    def __init__(self, operand: Expr, style: str, locale: str) -> None:
        self.operand = operand
        self.style = style
        self.locale = locale

    def js(self) -> str:
        return (f'new Intl.DateTimeFormat("{self.locale}", '
                f'{{ dateStyle: "{self.style}" }})'
                f".format(new Date({self.operand.js()}))")

    def evaluate(self, env: dict[str, Any]) -> Any:
        return _py_date(self.operand.evaluate(env), self.style, self.locale)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_number(value: Any, *, digits: int | None = None) -> str | Expr:
    locale = active_locale()
    if isinstance(value, Expr):
        options = ("{}" if digits is None else
                   f"{{ minimumFractionDigits: {digits}, "
                   f"maximumFractionDigits: {digits} }}")
        return _IntlNumber(value, options, locale,
                           lambda v: _py_number(v, digits, locale))
    return _py_number(value, digits, locale)


def format_currency(value: Any, *, currency: str = "USD",
                    digits: int = 2) -> str | Expr:
    locale = active_locale()
    if isinstance(value, Expr):
        options = (f'{{ style: "currency", currency: "{currency}", '
                   f"minimumFractionDigits: {digits}, "
                   f"maximumFractionDigits: {digits} }}")
        return _IntlNumber(value, options, locale,
                           lambda v: _py_currency(v, currency, digits, locale))
    return _py_currency(value, currency, digits, locale)


def format_percent(value: Any, *, digits: int = 0) -> str | Expr:
    locale = active_locale()
    if isinstance(value, Expr):
        options = (f'{{ style: "percent", minimumFractionDigits: {digits}, '
                   f"maximumFractionDigits: {digits} }}")
        return _IntlNumber(value, options, locale,
                           lambda v: _py_percent(v, digits, locale))
    return _py_percent(value, digits, locale)


def format_date(value: Any, *, style: str = "medium") -> str | Expr:
    if style not in ("short", "medium", "long"):
        raise VirelCompileError(
            f"format_date style {style!r} is not supported. Use 'short', "
            "'medium', or 'long'."
        )
    locale = active_locale()
    if isinstance(value, Expr):
        return _IntlDate(value, style, locale)
    return _py_date(value, style, locale)
