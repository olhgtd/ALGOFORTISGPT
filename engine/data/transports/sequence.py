"""Provider-source sequence contracts for Phase-6 broker-neutral transports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SequenceSemantics(str, Enum):
    STRICT_CONTIGUOUS = "STRICT_CONTIGUOUS"
    MONOTONIC_ONLY = "MONOTONIC_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class SequenceScope(str, Enum):
    CONNECTION = "CONNECTION"
    STREAM = "STREAM"
    INSTRUMENT = "INSTRUMENT"
    NONE = "NONE"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class SourceSequence:
    value: int | None
    semantics: SequenceSemantics
    scope: SequenceScope
    provider_field: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.semantics, SequenceSemantics):
            raise TypeError("semantics must be SequenceSemantics")
        if not isinstance(self.scope, SequenceScope):
            raise TypeError("scope must be SequenceScope")
        if self.semantics is SequenceSemantics.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("UNAVAILABLE source sequence must not carry a fabricated value")
            if self.scope is not SequenceScope.NONE:
                raise ValueError("UNAVAILABLE source sequence must use NONE scope")
            if self.provider_field is not None:
                raise ValueError("UNAVAILABLE source sequence must not name a provider field")
            return
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 0:
            raise ValueError("available source sequence must be a non-negative integer")
        if self.scope is SequenceScope.NONE:
            raise ValueError("available source sequence must declare a non-NONE scope")
        object.__setattr__(self, "provider_field", _text(self.provider_field, "provider_field"))


__all__ = ["SequenceSemantics", "SequenceScope", "SourceSequence"]
