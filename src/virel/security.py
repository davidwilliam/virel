"""Security primitives (SPEC 18).

Centralizes the pieces the rest of the framework uses to stay safe by
default: URL scheme sanitization for link and media attributes, script
hashes for the content security policy, and the policy itself.
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import urlsplit

SAFE_URL_SCHEMES = {"", "http", "https", "mailto", "tel"}
SAFE_IMAGE_SCHEMES = SAFE_URL_SCHEMES | {"data"}
BLOCKED_URL_FALLBACK = "#"


def safe_url(value: object, *, image: bool = False) -> str:
    """Return the URL if its scheme is allowed, otherwise a harmless
    fragment. Used wherever dynamic data flows into href or src."""
    text = str(value if value is not None else "").strip()
    try:
        scheme = urlsplit(text).scheme.lower()
    except ValueError:
        return BLOCKED_URL_FALLBACK
    allowed = SAFE_IMAGE_SCHEMES if image else SAFE_URL_SCHEMES
    if scheme in allowed:
        return text
    return BLOCKED_URL_FALLBACK


def is_safe_url(value: object, *, image: bool = False) -> bool:
    return safe_url(value, image=image) == str(value).strip()


def script_hash(source: str) -> str:
    """CSP hash for an inline script's exact text content."""
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def content_security_policy(inline_scripts: list[str]) -> str:
    """The default policy for HTML responses.

    Scripts run only from same-origin files plus the specific inline
    scripts the compiler emitted (matched by hash). Styles allow inline
    attributes because layout primitives compile to style attributes.
    """
    script_src = "'self'"
    for source in inline_scripts:
        script_src += f" '{script_hash(source)}'"
    return (
        "default-src 'self'; "
        f"script-src {script_src}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )


def same_origin(origin: str, host: str, allowed_origins: list[str]) -> bool:
    """Origin check for state-changing requests (stateless CSRF defense)."""
    if origin in allowed_origins:
        return True
    try:
        origin_host = urlsplit(origin).netloc
    except ValueError:
        return False
    return bool(origin_host) and origin_host == host
