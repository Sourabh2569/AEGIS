from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar, cast

T = TypeVar("T")


def encode_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"__type__": "Decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: encode_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [encode_value(item) for item in value]
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode_value(item) for key, item in value.items()}
    return value


def decode_value(value: Any, annotation: Any) -> Any:
    if isinstance(value, dict) and value.get("__type__") == "Decimal":
        return Decimal(value["value"])
    if isinstance(value, dict) and value.get("__type__") == "datetime":
        return datetime.fromisoformat(value["value"])
    if isinstance(value, dict) and value.get("__type__") == "date":
        return date.fromisoformat(value["value"])
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    return value


def to_json(value: Any) -> str:
    return json.dumps(encode_value(value), sort_keys=True)


def from_json(payload: str, cls: type[T]) -> T:
    raw = json.loads(payload)
    kwargs = {}
    dataclass_type = cast(Any, cls)
    for field in fields(dataclass_type):
        if field.name in raw:
            kwargs[field.name] = decode_value(raw[field.name], field.type)
    return cls(**kwargs)
