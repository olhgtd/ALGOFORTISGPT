"""Deterministic parameter-stability evidence for AlgoFortis V2 research."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec, CanonicalEncodingError


class StabilityError(ValueError):
    """Raised when parameter-stability evidence is invalid or ambiguous."""


def _freeze_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str, Decimal)):
        if isinstance(value, Decimal) and not value.is_finite():
            raise StabilityError("parameter Decimal values must be finite")
        return value
    if isinstance(value, float):
        raise StabilityError("float parameters are not canonical; use Decimal")
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    raise StabilityError(f"unsupported parameter value: {type(value).__name__}")


def _freeze_parameters(parameters: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(parameters, Mapping) or not parameters:
        raise StabilityError("parameters must be a non-empty mapping")
    frozen: dict[str, object] = {}
    for raw_name, raw_value in parameters.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise StabilityError("parameter names must be non-empty strings")
        name = raw_name.strip()
        if name in frozen:
            raise StabilityError("duplicate parameter name")
        value = _freeze_value(raw_value)
        try:
            CanonicalCodec.encode_value(value)
        except CanonicalEncodingError as exc:
            raise StabilityError(f"parameter {name} is not canonical") from exc
        frozen[name] = value
    return MappingProxyType(dict(sorted(frozen.items())))


@dataclass(frozen=True, slots=True)
class ParameterObservation:
    parameters: Mapping[str, object]
    score: Decimal
    fingerprint: str = ""

    def __post_init__(self) -> None:
        parameters = _freeze_parameters(self.parameters)
        if not isinstance(self.score, Decimal) or not self.score.is_finite():
            raise StabilityError("score must be a finite Decimal")
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-parameter-observation/v1",
            (
                ("parameters", tuple(parameters.items())),
                ("score", self.score),
            ),
        )
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "fingerprint", fingerprint)


@dataclass(frozen=True, slots=True)
class ParameterStabilityReport:
    observation_count: int
    top_n: int
    consensus: Mapping[str, object | None]
    top_observation_fingerprints: tuple[str, ...]
    fingerprint: str

    @classmethod
    def create(
        cls,
        observations: tuple[ParameterObservation, ...] | list[ParameterObservation],
        *,
        top_n: int,
    ) -> "ParameterStabilityReport":
        items = tuple(observations)
        if not items or any(not isinstance(item, ParameterObservation) for item in items):
            raise StabilityError("observations must contain ParameterObservation values")
        if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
            raise StabilityError("top_n must be a positive integer")
        if top_n > len(items):
            raise StabilityError("top_n cannot exceed observation count")
        if len({item.fingerprint for item in items}) != len(items):
            raise StabilityError("duplicate parameter observations are not permitted")

        parameter_names = tuple(items[0].parameters)
        for item in items[1:]:
            if tuple(item.parameters) != parameter_names:
                raise StabilityError("all observations must have the same parameter schema")

        ranked = tuple(sorted(items, key=lambda item: (-item.score, item.fingerprint)))
        top = ranked[:top_n]
        consensus_dict: dict[str, object | None] = {}
        for name in parameter_names:
            values = tuple(item.parameters[name] for item in top)
            first = values[0]
            consensus_dict[name] = first if all(value == first for value in values[1:]) else None
        consensus = MappingProxyType(consensus_dict)
        top_fingerprints = tuple(item.fingerprint for item in top)
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-parameter-stability-report/v1",
            (
                ("observation_count", len(items)),
                ("top_n", top_n),
                ("consensus", tuple(consensus.items())),
                ("top_observation_fingerprints", top_fingerprints),
            ),
        )
        return cls(
            observation_count=len(items),
            top_n=top_n,
            consensus=consensus,
            top_observation_fingerprints=top_fingerprints,
            fingerprint=fingerprint,
        )


__all__ = ["StabilityError", "ParameterObservation", "ParameterStabilityReport"]
