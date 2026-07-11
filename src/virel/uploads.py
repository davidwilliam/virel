"""File transfer for server actions (SPEC 8.8).

Uploads travel as multipart/form-data: the file parts map to action
parameters annotated with ``UploadFile`` and the JSON arguments ride in an
``__args`` field, validated like any other action payload. Filenames are
sanitized, sizes are bounded by the server body limit, and cross-site
requests are rejected before parsing. Downloads are GET-only actions that
return a ``FileDownload``; by contract they must not change state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .expr import VirelCompileError

_FILENAME_KEEP = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(raw: str) -> str:
    """Strip path components and control characters from a client-supplied
    filename (SPEC 18.2 safe file naming)."""
    name = raw.replace("\\", "/").split("/")[-1]
    name = _FILENAME_KEEP.sub("_", name).strip("._")
    return name[:128] or "upload"


@dataclass
class UploadFile:
    """A file received by a server action."""

    filename: str
    content_type: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)

    def text(self, encoding: str = "utf-8") -> str:
        return self.data.decode(encoding)

    def save(self, path) -> None:
        from pathlib import Path
        Path(path).write_bytes(self.data)


@dataclass
class FileDownload:
    """A file returned by a download action."""

    content: bytes | str
    filename: str
    content_type: str = "application/octet-stream"

    def body(self) -> bytes:
        if isinstance(self.content, str):
            return self.content.encode("utf-8")
        return self.content


class MultipartError(Exception):
    pass


def parse_multipart(body: bytes, content_type: str,
                    max_files: int = 20) -> tuple[dict[str, str], dict[str, list[UploadFile]]]:
    """Parse a multipart/form-data body into text fields and files.

    Deliberately strict: a malformed body raises rather than guessing.
    """
    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        raise MultipartError("missing multipart boundary")
    boundary = b"--" + match.group(1).encode("latin-1")

    fields: dict[str, str] = {}
    files: dict[str, list[UploadFile]] = {}

    chunks = body.split(boundary)
    # First chunk is a preamble, last is the "--\r\n" epilogue.
    for chunk in chunks[1:-1]:
        part = chunk.strip(b"\r\n")
        if not part:
            continue
        if b"\r\n\r\n" not in part:
            raise MultipartError("malformed part: missing header separator")
        raw_headers, content = part.split(b"\r\n\r\n", 1)
        headers: dict[str, str] = {}
        for line in raw_headers.split(b"\r\n"):
            key, _, value = line.decode("latin-1", "replace").partition(":")
            headers[key.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        name_match = re.search(r'name="([^"]*)"', disposition)
        if not name_match:
            raise MultipartError("part without a field name")
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        if filename_match is not None:
            if sum(len(v) for v in files.values()) >= max_files:
                raise MultipartError("too many files")
            files.setdefault(name, []).append(UploadFile(
                filename=sanitize_filename(filename_match.group(1)),
                content_type=headers.get("content-type",
                                         "application/octet-stream"),
                data=content,
            ))
        else:
            fields[name] = content.decode("utf-8", "replace")
    return fields, files


def file_params(action) -> dict[str, bool]:
    """Map of parameter name -> accepts-multiple for UploadFile params."""
    import typing
    out: dict[str, bool] = {}
    for name, annotation in action.type_hints().items():
        if name == "return":
            continue
        if annotation is UploadFile:
            out[name] = False
        elif (typing.get_origin(annotation) is list
              and typing.get_args(annotation) == (UploadFile,)):
            out[name] = True
    return out
