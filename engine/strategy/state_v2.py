"""Deterministic, tamper-evident Strategy SDK v2 state envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from types import MappingProxyType
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec
from engine.strategy.contracts_v2 import StrategyManifestV2


STATE_SCHEMA_VERSION = "algofortis-strategy-state/v2"


class StrategyStateError(ValueError):
    """Raised when strategy state cannot be safely serialized or restored."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyStateError(f"{name} must be a non-empty string")
    return value.strip()


def _freeze(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str, Decimal)):
        if isinstance(value, Decimal) and not value.is_finite():
            raise StrategyStateError("state Decimal values must be finite")
        return value
    if isinstance(value, float):
        raise StrategyStateError("float state is not canonical; use Decimal")
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = _text(raw_key, "state key")
            if key in frozen:
                raise StrategyStateError("duplicate state key")
            frozen[key] = _freeze(raw_value)
        return MappingProxyType(dict(sorted(frozen.items())))
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise StrategyStateError("unordered state collections are forbidden")
    raise StrategyStateError(f"unsupported strategy state type: {type(value).__name__}")


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple((key, _canonical(item)) for key, item in sorted(value.items()))
    if isinstance(value, tuple):
        return tuple(_canonical(item) for item in value)
    return value


def _json_encode(value: object) -> object:
    if isinstance(value, Decimal):
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, Mapping):
        return {key: _json_encode(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_encode(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise StrategyStateError(f"unsupported JSON state type: {type(value).__name__}")


def _json_decode(value: object) -> object:
    if isinstance(value, dict):
        if set(value) == {"$type", "value"} and value.get("$type") == "decimal":
            raw = value.get("value")
            if not isinstance(raw, str):
                raise StrategyStateError("invalid decimal state encoding")
            try:
                decimal = Decimal(raw)
            except Exception as exc:
                raise StrategyStateError("invalid decimal state encoding") from exc
            if not decimal.is_finite():
                raise StrategyStateError("state Decimal values must be finite")
            return decimal
        return {str(key): _json_decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(_json_decode(item) for item in value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise StrategyStateError("JSON float state is not canonical")
    raise StrategyStateError("invalid JSON state value")


def _state_fingerprint(state: Mapping[str, object]) -> str:
    return CanonicalCodec.fingerprint(
        "algofortis-strategy-state-payload/v2",
        (("state", _canonical(state)),),
    )


def _envelope_fingerprint(
    *,
    strategy_id: str,
    strategy_version: str,
    manifest_fingerprint: str,
    state_fingerprint: str,
) -> str:
    return CanonicalCodec.fingerprint(
        STATE_SCHEMA_VERSION,
        (
            ("strategy_id", strategy_id),
            ("strategy_version", strategy_version),
            ("manifest_fingerprint", manifest_fingerprint),
            ("state_fingerprint", state_fingerprint),
        ),
    )


@dataclass(frozen=True, slots=True)
class StrategyStateEnvelope:
    """Manifest-bound immutable state suitable for deterministic restart/replay."""

    strategy_id: str
    strategy_version: str
    manifest_fingerprint: str
    state: Mapping[str, object]
    state_fingerprint: str
    fingerprint: str
    schema_version: str = STATE_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        manifest: StrategyManifestV2,
        state: Mapping[str, object],
    ) -> "StrategyStateEnvelope":
        if not isinstance(manifest, StrategyManifestV2):
            raise StrategyStateError("manifest must be StrategyManifestV2")
        if not isinstance(state, Mapping):
            raise StrategyStateError("state must be a mapping")
        frozen = _freeze(state)
        if not isinstance(frozen, Mapping):
            raise StrategyStateError("state must freeze to a mapping")
        state_fp = _state_fingerprint(frozen)
        envelope_fp = _envelope_fingerprint(
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            manifest_fingerprint=manifest.fingerprint,
            state_fingerprint=state_fp,
        )
        return cls(
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            manifest_fingerprint=manifest.fingerprint,
            state=frozen,
            state_fingerprint=state_fp,
            fingerprint=envelope_fp,
        )

    def to_json(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "manifest_fingerprint": self.manifest_fingerprint,
            "state": _json_encode(self.state),
            "state_fingerprint": self.state_fingerprint,
            "fingerprint": self.fingerprint,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(
        cls,
        serialized: str,
        *,
        expected_manifest: StrategyManifestV2,
    ) -> "StrategyStateEnvelope":
        if not isinstance(serialized, str) or not serialized:
            raise StrategyStateError("serialized state must be non-empty JSON text")
        if not isinstance(expected_manifest, StrategyManifestV2):
            raise StrategyStateError("expected_manifest must be StrategyManifestV2")
        try:
            raw = json.loads(serialized)
        except (json.JSONDecodeError, TypeError) as exc:
            raise StrategyStateError("invalid strategy state JSON") from exc
        if not isinstance(raw, dict):
            raise StrategyStateError("strategy state JSON must be an object")
        if raw.get("schema_version") != STATE_SCHEMA_VERSION:
            raise StrategyStateError("unsupported strategy state schema version")
        if raw.get("strategy_id") != expected_manifest.strategy_id:
            raise StrategyStateError("strategy state strategy_id mismatch")
        if raw.get("strategy_version") != expected_manifest.strategy_version:
            raise StrategyStateError("strategy state strategy_version mismatch")
        if raw.get("manifest_fingerprint") != expected_manifest.fingerprint:
            raise StrategyStateError("strategy state manifest fingerprint mismatch")
        decoded = _json_decode(raw.get("state"))
        if not isinstance(decoded, Mapping):
            raise StrategyStateError("decoded strategy state must be a mapping")
        frozen = _freeze(decoded)
        if not isinstance(frozen, Mapping):
            raise StrategyStateError("decoded strategy state must freeze to a mapping")
        state_fp = _state_fingerprint(frozen)
        if raw.get("state_fingerprint") != state_fp:
            raise StrategyStateError("strategy state payload fingerprint mismatch")
        envelope_fp = _envelope_fingerprint(
            strategy_id=expected_manifest.strategy_id,
            strategy_version=expected_manifest.strategy_version,
            manifest_fingerprint=expected_manifest.fingerprint,
            state_fingerprint=state_fp,
        )
        if raw.get("fingerprint") != envelope_fp:
            raise StrategyStateError("strategy state envelope fingerprint mismatch")
        return cls(
            strategy_id=expected_manifest.strategy_id,
            strategy_version=expected_manifest.strategy_version,
            manifest_fingerprint=expected_manifest.fingerprint,
            state=frozen,
            state_fingerprint=state_fp,
            fingerprint=envelope_fp,
        )


__all__ = [
    "STATE_SCHEMA_VERSION",
    "StrategyStateError",
    "StrategyStateEnvelope",
]
