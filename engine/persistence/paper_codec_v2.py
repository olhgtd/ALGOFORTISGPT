"""Deterministic JSON codec for pure Phase-5 paper-domain records."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
import types
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

T = TypeVar("T")


def _encode(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("persisted datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported Phase-5 persistence value: {type(value).__name__}")


def dumps_record(record: object) -> str:
    if not is_dataclass(record):
        raise TypeError("record must be a dataclass instance")
    return json.dumps(_encode(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(annotation: object, value: object) -> object:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is tuple:
        item_type = args[0] if args else Any
        if not isinstance(value, list):
            raise ValueError("stored tuple payload must be a JSON list")
        return tuple(_decode(item_type, item) for item in value)

    if origin in (types.UnionType,):
        if value is None and type(None) in args:
            return None
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                return _decode(candidate, value)
            except (TypeError, ValueError):
                continue
        raise ValueError(f"stored value does not match union {annotation!r}")

    if annotation is datetime:
        if not isinstance(value, str):
            raise ValueError("stored datetime must be text")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("stored datetime must be timezone-aware")
        return parsed
    if annotation is Decimal:
        if not isinstance(value, str):
            raise ValueError("stored Decimal must be text")
        return Decimal(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if annotation is str:
        if not isinstance(value, str):
            raise ValueError("stored string field must be text")
        return value
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("stored integer field must be int")
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise ValueError("stored bool field must be bool")
        return value
    if annotation is Any:
        return value
    return value


def loads_record(payload_json: str, record_type: type[T]) -> T:
    if not isinstance(payload_json, str) or not payload_json:
        raise ValueError("payload_json must be non-empty text")
    raw = json.loads(payload_json)
    if not isinstance(raw, dict):
        raise ValueError("record payload must be a JSON object")
    hints = get_type_hints(record_type)
    expected = {field.name for field in fields(record_type)}
    if set(raw) != expected:
        missing = sorted(expected - set(raw))
        extra = sorted(set(raw) - expected)
        raise ValueError(f"record payload fields mismatch: missing={missing}, extra={extra}")
    values = {name: _decode(hints[name], raw[name]) for name in expected}
    return record_type(**values)


__all__ = ["dumps_record", "loads_record"]
