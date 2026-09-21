"""AlgoFortis V2 immutable layered configuration snapshots.

Implements the AF2-ARC-009 foundation without replacing existing V1 config
parsers.  Existing authorities may validate their own layer, then compose the
validated values here into one immutable, replayable run snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Callable, Mapping

from engine.reproducibility.codec import CanonicalCodec, CanonicalEncodingError


_LAYER_ORDER = ("system", "environment", "user", "strategy", "run")
_LAYER_RANK = {name: index for index, name in enumerate(_LAYER_ORDER)}
_SECRET_KEYS = {
    "password",
    "passphrase",
    "secret",
    "api_secret",
    "client_secret",
    "private_key",
    "access_token",
    "refresh_token",
    "broker_token",
}


class ConfigurationError(ValueError):
    """Raised when layered configuration cannot be safely resolved."""


Validator = Callable[[str, Mapping[str, object]], None]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} must be a non-empty string")
    return value.strip()


def _validate_key(key: object) -> str:
    if not isinstance(key, str) or not key:
        raise ConfigurationError("configuration keys must be non-empty strings")
    lowered = key.casefold()
    if lowered != "secret_ref" and (
        lowered in _SECRET_KEYS
        or lowered.endswith("_secret")
        or lowered.endswith("_password")
        or lowered.endswith("_private_key")
    ):
        raise ConfigurationError(f"raw secret field is forbidden: {key}")
    return key


def _normalize(value: object) -> object:
    """Return a deterministic, mapping-free canonical representation."""

    if value is None or isinstance(value, (bool, int, Decimal, str, bytes)):
        return value
    if isinstance(value, float):
        raise ConfigurationError("float values are not canonical configuration; use Decimal/text")
    if isinstance(value, Mapping):
        pairs = []
        for raw_key, raw_value in value.items():
            key = _validate_key(raw_key)
            pairs.append((key, _normalize(raw_value)))
        return tuple(sorted(pairs, key=lambda pair: pair[0]))
    if isinstance(value, (list, tuple)):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise ConfigurationError("unordered set values are not canonical configuration")
    raise ConfigurationError(f"unsupported configuration value type: {type(value).__name__}")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = _validate_key(raw_key)
            frozen[key] = _freeze(raw_value)
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, float):
        raise ConfigurationError("float values are not canonical configuration; use Decimal/text")
    if isinstance(value, (set, frozenset)):
        raise ConfigurationError("unordered set values are not canonical configuration")
    if value is None or isinstance(value, (bool, int, Decimal, str, bytes)):
        return value
    raise ConfigurationError(f"unsupported configuration value type: {type(value).__name__}")


def _deep_merge(base: dict[str, object], overlay: Mapping[str, object]) -> dict[str, object]:
    result = dict(base)
    for raw_key, value in overlay.items():
        key = _validate_key(raw_key)
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(dict(existing), value)
        else:
            result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class ConfigurationLayer:
    """One validated configuration layer in the frozen precedence chain."""

    name: str
    schema_version: str
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        name = _text(self.name, "layer name")
        version = _text(self.schema_version, "schema_version")
        if name not in _LAYER_RANK:
            raise ConfigurationError(f"unsupported configuration layer: {name}")
        if not isinstance(self.values, Mapping):
            raise ConfigurationError("layer values must be a mapping")
        # Validate canonicality and secret policy at construction time while
        # retaining ordinary values for the layer validator.
        _normalize(self.values)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "schema_version", version)
        object.__setattr__(self, "values", _freeze(self.values))


@dataclass(frozen=True, slots=True)
class ConfigurationSnapshot:
    """Deeply immutable resolved configuration and stable identity."""

    values: Mapping[str, object]
    layer_versions: tuple[tuple[str, str], ...]
    snapshot_id: str


class ConfigurationResolver:
    """Resolve system -> environment -> user -> strategy -> run layers."""

    def __init__(self, validators: Mapping[str, Validator]) -> None:
        if not isinstance(validators, Mapping):
            raise TypeError("validators must be a mapping")
        checked: dict[str, Validator] = {}
        for raw_name, validator in validators.items():
            name = _text(raw_name, "validator layer")
            if name not in _LAYER_RANK:
                raise ConfigurationError(f"unsupported validator layer: {name}")
            if not callable(validator):
                raise TypeError(f"validator for {name} must be callable")
            checked[name] = validator
        self._validators = MappingProxyType(checked)

    def resolve(self, *layers: ConfigurationLayer) -> ConfigurationSnapshot:
        if not layers:
            raise ConfigurationError("at least one configuration layer is required")
        if not all(isinstance(layer, ConfigurationLayer) for layer in layers):
            raise TypeError("resolve accepts ConfigurationLayer instances only")

        names = tuple(layer.name for layer in layers)
        if len(names) != len(set(names)):
            raise ConfigurationError("duplicate configuration layer")
        ranks = tuple(_LAYER_RANK[name] for name in names)
        if ranks != tuple(sorted(ranks)):
            raise ConfigurationError("configuration layer order must be system -> environment -> user -> strategy -> run")

        merged: dict[str, object] = {}
        versions: list[tuple[str, str]] = []
        for layer in layers:
            validator = self._validators.get(layer.name)
            if validator is None:
                raise ConfigurationError(f"missing validator for configuration layer {layer.name}")
            try:
                validator(layer.schema_version, layer.values)
            except Exception as exc:
                raise ConfigurationError(
                    f"schema validation failed for configuration layer {layer.name}"
                ) from exc
            merged = _deep_merge(merged, layer.values)
            versions.append((layer.name, layer.schema_version))

        frozen_values = _freeze(merged)
        canonical_values = _normalize(frozen_values)
        try:
            fingerprint = CanonicalCodec.fingerprint(
                "algofortis-configuration-snapshot/v1",
                (
                    ("layer_versions", tuple(versions)),
                    ("values", canonical_values),
                ),
            )
        except CanonicalEncodingError as exc:
            raise ConfigurationError("configuration snapshot cannot be canonically encoded") from exc

        return ConfigurationSnapshot(
            values=frozen_values,
            layer_versions=tuple(versions),
            snapshot_id=f"cfg_{fingerprint}",
        )


__all__ = [
    "ConfigurationError",
    "ConfigurationLayer",
    "ConfigurationSnapshot",
    "ConfigurationResolver",
]
