"""Data-structure adapters (SPEC 12.1).

``ui.records`` normalizes the Python data shapes people actually have
into the plain records the UI consumes: lists of dicts, dataclasses,
Pydantic models, TypedDicts, NamedTuples, NumPy structured arrays, and
pandas, Polars, and Arrow tables. Detection is duck-typed by module, so
none of these libraries is imported, required, or even mentioned unless
the caller already holds one of their objects — the framework stays
dependency-free.
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
from typing import Any

from .expr import VirelCompileError


def records(data: Any) -> list[dict[str, Any]]:
    """Normalize tabular data to a list of plain dicts with
    JSON-compatible values (enums become their values, dates become ISO
    strings, NumPy scalars become Python numbers)."""
    rows = _extract_rows(data)
    return [{str(key): _plain(value) for key, value in row.items()}
            for row in rows]


def infer_columns(data: Any) -> list:
    """Column definitions inferred from the data: keys become labels,
    and the first non-missing value of each key decides the kind."""
    from .datagrid import Column
    rows = records(data)
    if not rows:
        raise VirelCompileError(
            "Cannot infer columns from empty data; pass columns=[...].")
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    columns = []
    for key in keys:
        sample = next((row[key] for row in rows
                       if row.get(key) not in (None, "")), None)
        columns.append(Column(key, key.replace("_", " ").title(),
                              kind=_kind_of(sample)))
    return columns


def _module_of(value: Any) -> str:
    return type(value).__module__ or ""


def _extract_rows(data: Any) -> list[dict[str, Any]]:
    module = _module_of(data)
    # pandas.DataFrame
    if module.startswith("pandas") and hasattr(data, "to_dict"):
        return data.to_dict("records")
    # polars.DataFrame
    if module.startswith("polars") and hasattr(data, "to_dicts"):
        return data.to_dicts()
    # pyarrow.Table / RecordBatch
    if module.startswith("pyarrow") and hasattr(data, "to_pylist"):
        return data.to_pylist()
    # numpy structured array
    if module.startswith("numpy"):
        names = getattr(getattr(data, "dtype", None), "names", None)
        if names:
            return [dict(zip(names, row)) for row in data.tolist()]
        raise VirelCompileError(
            "NumPy data needs a structured dtype with named fields (or "
            "convert it to records yourself).")
    if isinstance(data, dict):
        raise VirelCompileError(
            "records() takes a sequence of records, not a single dict.")
    try:
        items = list(data)
    except TypeError:
        raise VirelCompileError(
            f"records() cannot read {type(data).__name__!r}; supported: "
            "lists of dicts/dataclasses/Pydantic models/TypedDicts/"
            "NamedTuples, pandas, Polars, Arrow, and NumPy structured "
            "arrays.") from None
    return [_record(item) for item in items]


def _record(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):  # plain dicts and TypedDict instances
        return item
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        return dataclasses.asdict(item)
    if hasattr(item, "model_dump"):  # Pydantic
        return item.model_dump()
    if hasattr(item, "_asdict"):  # NamedTuple
        return item._asdict()
    raise VirelCompileError(
        f"Cannot convert {type(item).__name__!r} to a record; use a dict, "
        "dataclass, Pydantic model, TypedDict, or NamedTuple.")


def _plain(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return _plain(value.value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if hasattr(value, "item") and _module_of(value).startswith("numpy"):
        return value.item()  # NumPy scalar -> Python scalar
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _kind_of(sample: Any) -> str:
    if isinstance(sample, bool):
        return "text"
    if isinstance(sample, (int, float)):
        return "number"
    if isinstance(sample, str) and len(sample) >= 10 and sample[4:5] == "-" \
            and sample[7:8] == "-" and sample[:4].isdigit():
        return "date"
    return "text"
