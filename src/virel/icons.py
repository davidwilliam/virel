"""Built-in icon set.

Icons are inline SVG compiled into the page like any other element: no icon
font, no extra requests, styled via currentColor. The geometry follows the
common 24x24 stroke convention so third-party sets can be mixed in without
looking foreign.
"""

from __future__ import annotations

from .expr import VirelCompileError
from .nodes import Element, RawHTML

_ICONS: dict[str, str] = {
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "chevron-up": '<polyline points="18 15 12 9 6 15"/>',
    "chevron-left": '<polyline points="15 18 9 12 15 6"/>',
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "arrow-left": '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "info": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/>'
            '<line x1="12" y1="8" x2="12.01" y2="8"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>'
                    '<line x1="12" y1="16" x2="12.01" y2="16"/>',
    "alert-triangle": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 '
                      '1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
                      '<line x1="12" y1="9" x2="12" y2="13"/>'
                      '<line x1="12" y1="17" x2="12.01" y2="17"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 '
            '5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>'
            '<circle cx="12" cy="7" r="4"/>',
    "menu": '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>'
            '<line x1="3" y1="18" x2="21" y2="18"/>',
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
            '<polyline points="9 22 9 12 15 12 15 22"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/>'
            '<polyline points="22 6 12 13 2 6"/>',
    "external-link": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 '
                     '2-2h6"/><polyline points="15 3 21 3 21 9"/>'
                     '<line x1="10" y1="14" x2="21" y2="3"/>',
    "copy": '<rect x="9" y="9" width="13" height="13" rx="2"/>'
            '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/>'
             '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 '
             '2-2h4a2 2 0 0 1 2 2v2"/>',
    "edit": '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
            '<path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
              '<polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                '<polyline points="7 10 12 15 17 10"/>'
                '<line x1="12" y1="15" x2="12" y2="3"/>',
    "loader": '<line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/>'
              '<line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/>'
              '<line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>'
              '<line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/>'
              '<line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/>'
              '<line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>',
    "settings": '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
                '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
                '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
                '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
                '<line x1="17" y1="16" x2="23" y2="16"/>',
    "file": '<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>'
            '<polyline points="13 2 13 9 20 9"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 '
              '2 0 0 1 2 2z"/>',
    "play": '<polygon points="5 3 19 12 5 21 5 3"/>',
    "square": '<rect x="3" y="3" width="18" height="18" rx="2"/>',
    "thumbs-up": '<path d="M7 10v12M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56'
                 'l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 '
                 '2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 '
                 '3.88Z"/>',
    "thumbs-down": '<path d="M17 14V2M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56'
                   'l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 '
                   '2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-'
                   '3.88Z"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>'
           '<path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4"/>'
           '<line x1="12" y1="20" x2="12" y2="22"/>'
           '<line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/>'
           '<line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/>'
           '<line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/>'
           '<line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/>'
           '<line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/>',
    "moon": '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    "monitor": '<rect x="2" y="3" width="20" height="14" rx="2"/>'
               '<line x1="8" y1="21" x2="16" y2="21"/>'
               '<line x1="12" y1="17" x2="12" y2="21"/>',
}


def icon_names() -> list[str]:
    return sorted(_ICONS)


def Icon(name: str, *, size: int = 16, label: str | None = None,
         stroke_width: float = 2) -> Element:
    markup = _ICONS.get(name)
    if markup is None:
        raise VirelCompileError(
            f"Unknown icon {name!r}. Available icons: {', '.join(icon_names())}."
        )
    attrs: dict[str, object] = {
        "class": "v-icon",
        "viewBox": "0 0 24 24",
        "width": size,
        "height": size,
        "fill": "none",
        "stroke": "currentColor",
        "stroke-width": stroke_width,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
    }
    if label:
        attrs["role"] = "img"
        attrs["aria-label"] = label
    else:
        attrs["aria-hidden"] = "true"
    return Element("svg", [RawHTML(markup, reason="built-in icon geometry")],
                   attrs=attrs)
