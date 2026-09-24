"""Deterministic Strategy SDK v2 manifest and parameter contracts.

These contracts are research/backtest authorities only.  They do not create
orders, load broker adapters, arm live execution, or choose strategy economics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec


STRATEGY_INTERFACE_VERSION = "2.0"
MANIFEST_SCHEMA_VERSION = "algofortis-strategy-manifest/v2"


class StrategySDKError(ValueError):
    """Raised when a Strategy SDK contract is invalid or ambiguous."""


class ParameterKind(str, Enum):
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    CHOICE = "CHOICE"
    TEXT = "TEXT"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategySDKError(f"{name} must be a non-empty string")
    return value.strip()


def _unique_text_tuple(values: object, name: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise StrategySDKError(f"{name} must be a tuple/list of strings")
    normalized = tuple(_text(value, name) for value in values)
    if not normalized:
        raise StrategySDKError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise StrategySDKError(f"{name} must not contain duplicates")
    return tuple(sorted(normalized))


def _decimal_bound(value: Decimal | None, name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise StrategySDKError(f"{name} must be a finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """One immutable strategy parameter definition."""

    kind: ParameterKind
    required: bool = True
    default: object | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    choices: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        try:
            kind = ParameterKind(self.kind)
        except (ValueError, TypeError) as exc:
            raise StrategySDKError("unsupported parameter kind") from exc
        if not isinstance(self.required, bool):
            raise StrategySDKError("required must be bool")
        minimum = _decimal_bound(self.minimum, "minimum")
        maximum = _decimal_bound(self.maximum, "maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise StrategySDKError("minimum cannot exceed maximum")
        choices = tuple(self.choices)
        if kind is ParameterKind.CHOICE:
            if not choices or len(choices) != len(set(choices)):
                raise StrategySDKError("CHOICE parameters require unique choices")
        elif choices:
            raise StrategySDKError("choices are only valid for CHOICE parameters")
        if kind not in (ParameterKind.INTEGER, ParameterKind.DECIMAL) and (
            minimum is not None or maximum is not None
        ):
            raise StrategySDKError("bounds are only valid for numeric parameters")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "choices", choices)
        if self.default is not None:
            self.validate(self.default)

    def validate(self, value: object) -> object:
        if self.kind is ParameterKind.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                raise StrategySDKError("INTEGER parameter requires int (not bool)")
            numeric = Decimal(value)
            normalized: object = value
        elif self.kind is ParameterKind.DECIMAL:
            if not isinstance(value, Decimal) or not value.is_finite():
                raise StrategySDKError("DECIMAL parameter requires finite Decimal")
            numeric = value
            normalized = value
        elif self.kind is ParameterKind.BOOLEAN:
            if not isinstance(value, bool):
                raise StrategySDKError("BOOLEAN parameter requires bool")
            numeric = None
            normalized = value
        elif self.kind is ParameterKind.CHOICE:
            if value not in self.choices:
                raise StrategySDKError("CHOICE parameter value is not permitted")
            numeric = None
            normalized = value
        else:
            if not isinstance(value, str) or not value.strip():
                raise StrategySDKError("TEXT parameter requires non-empty string")
            numeric = None
            normalized = value.strip()

        if numeric is not None:
            if self.minimum is not None and numeric < self.minimum:
                raise StrategySDKError("parameter value is below minimum")
            if self.maximum is not None and numeric > self.maximum:
                raise StrategySDKError("parameter value is above maximum")
        return normalized

    @property
    def canonical_fields(self) -> tuple[tuple[str, object], ...]:
        return (
            ("kind", self.kind),
            ("required", self.required),
            ("default", self.default),
            ("minimum", self.minimum),
            ("maximum", self.maximum),
            ("choices", self.choices),
        )


@dataclass(frozen=True, slots=True)
class StrategyManifestV2:
    """Immutable strategy identity, inputs, parameters and dependency lock."""

    strategy_id: str
    strategy_version: str
    parameter_schema: Mapping[str, ParameterSpec]
    required_data_kinds: tuple[str, ...]
    required_timeframes: tuple[str, ...]
    supported_instruments: tuple[str, ...]
    dependency_lock: Mapping[str, str]
    protective_policy_required: bool = False
    interface_version: str = STRATEGY_INTERFACE_VERSION
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        strategy_id = _text(self.strategy_id, "strategy_id")
        strategy_version = _text(self.strategy_version, "strategy_version")
        interface_version = _text(self.interface_version, "interface_version")
        schema_version = _text(self.schema_version, "schema_version")
        if interface_version != STRATEGY_INTERFACE_VERSION:
            raise StrategySDKError(f"unsupported strategy interface version: {interface_version}")
        if schema_version != MANIFEST_SCHEMA_VERSION:
            raise StrategySDKError(f"unsupported manifest schema version: {schema_version}")
        if not isinstance(self.protective_policy_required, bool):
            raise StrategySDKError("protective_policy_required must be bool")
        if not isinstance(self.parameter_schema, Mapping) or not self.parameter_schema:
            raise StrategySDKError("parameter_schema must be a non-empty mapping")
        parameters: dict[str, ParameterSpec] = {}
        for raw_name, spec in self.parameter_schema.items():
            name = _text(raw_name, "parameter name")
            if not isinstance(spec, ParameterSpec):
                raise StrategySDKError("parameter_schema values must be ParameterSpec")
            if name in parameters:
                raise StrategySDKError("duplicate parameter name")
            parameters[name] = spec

        if not isinstance(self.dependency_lock, Mapping) or not self.dependency_lock:
            raise StrategySDKError("dependency_lock must be a non-empty mapping")
        dependencies: dict[str, str] = {}
        for raw_name, raw_version in self.dependency_lock.items():
            name = _text(raw_name, "dependency name")
            version = _text(raw_version, "dependency version")
            if name in dependencies:
                raise StrategySDKError("duplicate dependency name")
            dependencies[name] = version

        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "strategy_version", strategy_version)
        object.__setattr__(self, "interface_version", interface_version)
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "parameter_schema", MappingProxyType(dict(sorted(parameters.items()))))
        object.__setattr__(self, "dependency_lock", MappingProxyType(dict(sorted(dependencies.items()))))
        object.__setattr__(self, "required_data_kinds", _unique_text_tuple(self.required_data_kinds, "required_data_kinds"))
        object.__setattr__(self, "required_timeframes", _unique_text_tuple(self.required_timeframes, "required_timeframes"))
        object.__setattr__(self, "supported_instruments", _unique_text_tuple(self.supported_instruments, "supported_instruments"))

    @property
    def fingerprint(self) -> str:
        parameter_fields = tuple(
            (name, spec.canonical_fields) for name, spec in self.parameter_schema.items()
        )
        return CanonicalCodec.fingerprint(
            MANIFEST_SCHEMA_VERSION,
            (
                ("strategy_id", self.strategy_id),
                ("strategy_version", self.strategy_version),
                ("interface_version", self.interface_version),
                ("parameters", parameter_fields),
                ("required_data_kinds", self.required_data_kinds),
                ("required_timeframes", self.required_timeframes),
                ("supported_instruments", self.supported_instruments),
                ("dependency_lock", tuple(self.dependency_lock.items())),
                ("protective_policy_required", self.protective_policy_required),
            ),
        )

    def validate_parameters(self, values: Mapping[str, object]) -> Mapping[str, object]:
        if not isinstance(values, Mapping):
            raise StrategySDKError("parameter values must be a mapping")
        unknown = set(values) - set(self.parameter_schema)
        if unknown:
            raise StrategySDKError(f"unknown strategy parameters: {','.join(sorted(unknown))}")
        resolved: dict[str, object] = {}
        for name, spec in self.parameter_schema.items():
            if name in values:
                resolved[name] = spec.validate(values[name])
            elif spec.default is not None:
                resolved[name] = spec.validate(spec.default)
            elif spec.required:
                raise StrategySDKError(f"missing required strategy parameter: {name}")
        return MappingProxyType(resolved)

    def assert_executable_ready(self, protective_policy_ref: str | None) -> str | None:
        if not self.protective_policy_required:
            if protective_policy_ref is None:
                return None
            return _text(protective_policy_ref, "protective_policy_ref")
        if protective_policy_ref is None:
            raise StrategySDKError("explicit versioned protective_policy_ref is required")
        value = _text(protective_policy_ref, "protective_policy_ref")
        name, separator, version = value.rpartition("@")
        if separator != "@" or not name.strip() or not version.strip():
            raise StrategySDKError("protective_policy_ref must be versioned as name@version")
        return value


__all__ = [
    "STRATEGY_INTERFACE_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "StrategySDKError",
    "ParameterKind",
    "ParameterSpec",
    "StrategyManifestV2",
]
