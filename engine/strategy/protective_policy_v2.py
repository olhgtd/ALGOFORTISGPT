"""Explicit research-only ORB protective economics; no production default."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.reproducibility.codec import CanonicalCodec


class ProtectivePolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProtectivePolicyV2:
    ref: str
    stop_distance: Decimal
    target_distance: Decimal
    trailing_distance: Decimal | None
    oco: bool
    tick_size: Decimal
    rounding: str

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref.startswith(("TEST_ONLY/", "RESEARCH_ONLY/")) or "@" not in self.ref:
            raise ProtectivePolicyError("Phase 4 policy must be explicit TEST_ONLY/ or RESEARCH_ONLY/ and versioned")
        for name in ("stop_distance", "target_distance", "tick_size"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ProtectivePolicyError(f"{name} must be positive finite Decimal")
        if self.trailing_distance is None or not isinstance(self.trailing_distance, Decimal) or not self.trailing_distance.is_finite() or self.trailing_distance <= 0:
            raise ProtectivePolicyError("trailing distance must be explicitly specified")
        if self.oco is not True or self.rounding not in ("ROUND_HALF_UP", "ROUND_DOWN", "ROUND_UP"):
            raise ProtectivePolicyError("explicit OCO and recognized tick rounding required")
        for name in ("stop_distance", "target_distance", "trailing_distance"):
            if getattr(self, name) % self.tick_size:
                raise ProtectivePolicyError(f"{name} must align to tick size")

    @property
    def fingerprint(self) -> str:
        return CanonicalCodec.fingerprint("algofortis-orb-protective-policy/v1", (
            ("ref", self.ref), ("stop_distance", self.stop_distance),
            ("target_distance", self.target_distance), ("trailing_distance", self.trailing_distance),
            ("oco", self.oco), ("tick_size", self.tick_size), ("rounding", self.rounding)))


class PolicyRegistryV2:
    def __init__(self) -> None:
        self._policies: dict[str, ProtectivePolicyV2] = {}

    def register(self, policy: ProtectivePolicyV2) -> None:
        if not isinstance(policy, ProtectivePolicyV2):
            raise ProtectivePolicyError("typed protective policy required")
        previous = self._policies.get(policy.ref)
        if previous is not None and previous.fingerprint != policy.fingerprint:
            raise ProtectivePolicyError("versioned policy reference cannot be overwritten")
        self._policies[policy.ref] = policy

    def resolve(self, ref: str) -> ProtectivePolicyV2:
        try:
            return self._policies[ref]
        except (KeyError, TypeError) as exc:
            raise ProtectivePolicyError("protective policy reference is not registered") from exc
