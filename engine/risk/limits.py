"""AlgoFortis V2 hard-limit hierarchy.

The hierarchy is authoritative risk configuration.  Lower-precedence layers may
only make a limit more restrictive; widening a higher authority is rejected
fail-closed.  Resolved evidence is immutable and fingerprinted deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec


class HardLimitError(ValueError):
    """Raised when hard-limit configuration violates authority or numeric rules."""


class LimitDirection(str, Enum):
    MAXIMUM = "MAXIMUM"
    MINIMUM = "MINIMUM"


_LAYER_NAMES = ("platform", "owner", "user", "strategy", "run")


def _name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HardLimitError(f"{field} must be a non-empty string")
    return value.strip()


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise HardLimitError(f"{field} must be an authoritative Decimal/int/string value")
    if isinstance(value, float):
        raise HardLimitError(f"{field} cannot use float authoritative values")
    if not isinstance(value, (Decimal, int, str)):
        raise HardLimitError(f"{field} must be an authoritative Decimal/int/string value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise HardLimitError(f"{field} must be numeric") from error
    if not result.is_finite():
        raise HardLimitError(f"{field} must be finite")
    if result < 0:
        raise HardLimitError(f"{field} cannot be negative")
    return result


def _normalize_definitions(definitions: Mapping[str, LimitDirection]) -> dict[str, LimitDirection]:
    if not isinstance(definitions, Mapping) or not definitions:
        raise HardLimitError("definitions must be a non-empty mapping")
    normalized: dict[str, LimitDirection] = {}
    for raw_name, direction in definitions.items():
        name = _name(raw_name, "limit name")
        if name in normalized:
            raise HardLimitError(f"duplicate limit definition: {name}")
        if not isinstance(direction, LimitDirection):
            raise HardLimitError(f"definition for {name} must be a LimitDirection")
        normalized[name] = direction
    return normalized


def _normalize_layer(
    layer_name: str,
    raw: Mapping[str, object] | None,
    definitions: Mapping[str, LimitDirection],
) -> dict[str, Decimal]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise HardLimitError(f"{layer_name} limits must be a mapping")
    normalized: dict[str, Decimal] = {}
    for raw_name, raw_value in raw.items():
        name = _name(raw_name, f"{layer_name} limit name")
        if name not in definitions:
            raise HardLimitError(f"{layer_name} declares unknown limit {name}")
        if name in normalized:
            raise HardLimitError(f"{layer_name} duplicates limit {name}")
        normalized[name] = _decimal(raw_value, f"{layer_name}.{name}")
    return normalized


@dataclass(frozen=True, slots=True)
class ResolvedHardLimits:
    """Immutable effective hard limits plus provenance and deterministic identity."""

    values: Mapping[str, Decimal]
    sources: Mapping[str, str]
    definitions: Mapping[str, LimitDirection]
    snapshot_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "sources", MappingProxyType(dict(self.sources)))
        object.__setattr__(self, "definitions", MappingProxyType(dict(self.definitions)))
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.startswith("limits_"):
            raise HardLimitError("snapshot_id must be a limits_ identity")


class HardLimitHierarchy:
    """Resolve platform > owner > user > strategy > run hard-limit authority."""

    def __init__(
        self,
        *,
        definitions: Mapping[str, LimitDirection],
        platform: Mapping[str, object],
        owner: Mapping[str, object] | None = None,
        user: Mapping[str, object] | None = None,
        strategy: Mapping[str, object] | None = None,
        run: Mapping[str, object] | None = None,
    ) -> None:
        normalized_definitions = _normalize_definitions(definitions)
        layers = {
            "platform": _normalize_layer("platform", platform, normalized_definitions),
            "owner": _normalize_layer("owner", owner, normalized_definitions),
            "user": _normalize_layer("user", user, normalized_definitions),
            "strategy": _normalize_layer("strategy", strategy, normalized_definitions),
            "run": _normalize_layer("run", run, normalized_definitions),
        }
        missing = tuple(sorted(set(normalized_definitions) - set(layers["platform"])))
        if missing:
            raise HardLimitError(
                "platform must define every hard-limit authority: " + ", ".join(missing)
            )
        self._definitions = normalized_definitions
        self._layers = layers

    def resolve(self) -> ResolvedHardLimits:
        values: dict[str, Decimal] = dict(self._layers["platform"])
        sources: dict[str, str] = {name: "platform" for name in values}

        for layer_name in _LAYER_NAMES[1:]:
            layer = self._layers[layer_name]
            for name, candidate in layer.items():
                current = values[name]
                direction = self._definitions[name]
                widens = (
                    candidate > current
                    if direction is LimitDirection.MAXIMUM
                    else candidate < current
                )
                if widens:
                    comparator = "above" if direction is LimitDirection.MAXIMUM else "below"
                    raise HardLimitError(
                        f"{layer_name} widens {name} {comparator} higher-authority value "
                        f"{current} -> {candidate}"
                    )
                values[name] = candidate
                sources[name] = layer_name

        ordered_definitions = tuple(
            (name, self._definitions[name].value) for name in sorted(self._definitions)
        )
        ordered_layers = tuple(
            (
                layer_name,
                tuple(
                    (name, self._layers[layer_name][name])
                    for name in sorted(self._layers[layer_name])
                ),
            )
            for layer_name in _LAYER_NAMES
        )
        ordered_resolved = tuple(
            (name, values[name], sources[name]) for name in sorted(values)
        )
        digest = CanonicalCodec.fingerprint(
            "algofortis-hard-limits/v1",
            (
                ("definitions", ordered_definitions),
                ("layers", ordered_layers),
                ("resolved", ordered_resolved),
            ),
        )
        return ResolvedHardLimits(
            values=values,
            sources=sources,
            definitions=self._definitions,
            snapshot_id=f"limits_{digest}",
        )


__all__ = [
    "HardLimitError",
    "LimitDirection",
    "ResolvedHardLimits",
    "HardLimitHierarchy",
]
