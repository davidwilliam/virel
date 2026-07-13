"""Software Bill of Materials and build metadata (SPEC 18.2, 18.4).

``virel sbom`` emits a CycloneDX SBOM of the application and its
installed dependencies; ``virel build`` writes reproducible build
metadata (component versions, a content digest, and a source hash) so a
build can be attested and reproduced.
"""

from __future__ import annotations

import hashlib
import sys
from importlib import metadata
from pathlib import Path
from typing import Any


def _installed_packages() -> list[dict[str, str]]:
    seen: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name and name not in seen:
            seen[name] = dist.version or "0"
    return [{"name": n, "version": v} for n, v in sorted(seen.items())]


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name.lower()}@{version}"


def generate_sbom(root: Path, *, app_name: str = "virel-app",
                  app_version: str = "0.0.0") -> dict[str, Any]:
    """A CycloneDX 1.5 SBOM for the app plus installed dependencies."""
    components = []
    for pkg in _installed_packages():
        components.append({
            "type": "library",
            "name": pkg["name"],
            "version": pkg["version"],
            "purl": _purl(pkg["name"], pkg["version"]),
        })
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": app_name,
                          "version": app_version},
            "tools": [{"vendor": "virel", "name": "virel sbom"}],
        },
        "components": components,
    }


def source_digest(root: Path) -> str:
    """A deterministic digest of the app's Python sources, so an SBOM or
    build metadata pins exactly the code that produced it."""
    digest = hashlib.sha256()
    app_dir = root / "app" if (root / "app").is_dir() else root
    for path in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def build_metadata(root: Path, *, dist_digest: str | None = None) -> dict:
    """Reproducible build metadata (SPEC 18.2). Deterministic: no
    timestamps, only versions and content hashes, so two builds of the
    same source produce the same metadata."""
    virel_version = "0"
    try:
        virel_version = metadata.version("virel")
    except Exception:
        pass
    return {
        "schema": "virel-build/1",
        "virel_version": virel_version,
        "python_version": ".".join(str(p) for p in sys.version_info[:3]),
        "source_digest": source_digest(root),
        "dist_digest": dist_digest,
        "reproducible": True,
    }


def digest_directory(directory: Path) -> str:
    """A content digest of a built dist/ tree, order-independent."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(directory).as_posix().encode())
            digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()
