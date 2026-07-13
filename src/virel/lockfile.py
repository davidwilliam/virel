"""Dependency lockfile and integrity verification (SPEC 18.2).

``virel lock`` pins every installed distribution to a version and a digest
derived from the hashes pip records in each package's ``RECORD``. ``virel
lock --verify`` recomputes those digests from the current environment and
reports any drift, so a build can prove its dependencies match the lock.
"""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path
from typing import Any

LOCK_NAME = "virel.lock"
SCHEMA = "virel-lock/1"


def _package_digest(dist: metadata.Distribution) -> str:
    """A digest over the package's file list and the per-file hashes pip
    recorded at install time — its integrity fingerprint, computed without
    re-reading file contents."""
    digest = hashlib.sha256()
    files = dist.files or []
    for path in sorted(files, key=str):
        digest.update(str(path).encode())
        recorded = getattr(path, "hash", None)
        if recorded is not None:
            digest.update(f"{recorded.mode}:{recorded.value}".encode())
    return "sha256:" + digest.hexdigest()


def installed_lock() -> dict[str, Any]:
    """A lockfile document pinning every installed distribution."""
    packages: dict[str, dict[str, str]] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name or name in packages:
            continue
        packages[name] = {
            "name": name,
            "version": dist.version or "0",
            "digest": _package_digest(dist),
        }
    ordered = [packages[name] for name in sorted(packages, key=str.lower)]
    return {"schema": SCHEMA, "packages": ordered}


def write_lock(root: Path) -> Path:
    """Write ``virel.lock`` for the current environment; return its path."""
    path = root / LOCK_NAME
    path.write_text(json.dumps(installed_lock(), indent=2) + "\n")
    return path


def verify_lock(root: Path) -> list[str]:
    """Compare the current environment against ``virel.lock``. Return a
    list of human-readable drift messages; empty means the environment
    matches the lock exactly."""
    path = root / LOCK_NAME
    if not path.exists():
        raise FileNotFoundError(f"no {LOCK_NAME} found; run `virel lock` first")
    locked = json.loads(path.read_text())
    if locked.get("schema") != SCHEMA:
        return [f"unrecognized lockfile schema {locked.get('schema')!r}"]
    expected = {pkg["name"]: pkg for pkg in locked.get("packages", [])}
    current = {pkg["name"]: pkg for pkg in installed_lock()["packages"]}

    issues: list[str] = []
    for name in sorted(set(expected) - set(current), key=str.lower):
        issues.append(f"{name}: locked but not installed")
    for name in sorted(set(current) - set(expected), key=str.lower):
        issues.append(f"{name}: installed but not in the lockfile")
    for name in sorted(set(expected) & set(current), key=str.lower):
        want, have = expected[name], current[name]
        if want["version"] != have["version"]:
            issues.append(
                f"{name}: locked {want['version']} but "
                f"{have['version']} installed")
        elif want["digest"] != have["digest"]:
            issues.append(f"{name}: integrity digest mismatch (files changed "
                          "since the lock was written)")
    return issues
