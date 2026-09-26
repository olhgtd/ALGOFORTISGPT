"""Deterministic ORB reference strategy for Phase-4 research/backtest work.

This module produces research signals only.  It contains no broker adapter,
order intent, quantity, live mutation or protective-exit economics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec
from engine.strategy.contracts_v2 import StrategySDKError
from strategies.orb.manifest_v2 import ORB_MANIFEST_V2
from engine.strategy.protective_policy_v2 import PolicyRegistryV2, ProtectivePolicyError


class ORBReferenceError(ValueError):
    """Raised when ORB reference inputs are invalid or ambiguous."""


class ORBAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ORBReferenceError(f"{name} must be a non-empty string")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ORBReferenceError(f"{name} must be timezone-aware")
    return value


def _price(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ORBReferenceError(f"{name} must be a finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class ORBSignalSnapshot:
    """Supplied, already-normalized research inputs for one ORB decision."""

    symbol: str
    timestamp: datetime
    close: Decimal
    opening_range_high: Decimal
    opening_range_low: Decimal

    def __post_init__(self) -> None:
        symbol = _text(self.symbol, "symbol").upper()
        timestamp = _aware(self.timestamp, "timestamp")
        close = _price(self.close, "close")
        high = _price(self.opening_range_high, "opening_range_high")
        low = _price(self.opening_range_low, "opening_range_low")
        if high <= low:
            raise ORBReferenceError("opening_range_high must be greater than opening_range_low")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "close", close)
        object.__setattr__(self, "opening_range_high", high)
        object.__setattr__(self, "opening_range_low", low)


@dataclass(frozen=True, slots=True)
class ORBResearchSignal:
    """Non-executable research output from the ORB reference strategy."""

    symbol: str
    timestamp: datetime
    action: ORBAction
    reason: str
    snapshot_fingerprint: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ORBSimulationPreparation:
    """Research/backtest readiness evidence; never an execution authorization."""

    protective_policy_ref: str
    evidence_scope: str
    promotion_eligible: bool
    manifest_fingerprint: str
    fingerprint: str


class ORBReferenceStrategyV2:
    """Strict supplied-range breakout reference implementation.

    BUY means close > opening-range high, SELL means close < opening-range low,
    and HOLD covers the range and exact boundaries.  These are research signal
    labels only and are not live order instructions.
    """

    manifest = ORB_MANIFEST_V2

    def prepare_policy_bound_simulation(self, protective_policy_ref: str,
                                        registry: PolicyRegistryV2) -> ORBSimulationPreparation:
        """Bind simulation preparation to actual versioned economics."""
        if not isinstance(registry, PolicyRegistryV2):
            raise ProtectivePolicyError("explicit policy registry required")
        policy = registry.resolve(protective_policy_ref)
        prepared = self.prepare_simulation(protective_policy_ref=policy.ref)
        fingerprint = CanonicalCodec.fingerprint("algofortis-orb-policy-bound-preparation/v1", (
            ("preparation", prepared.fingerprint), ("policy", policy.fingerprint)))
        return ORBSimulationPreparation(prepared.protective_policy_ref,
                                        prepared.evidence_scope, False,
                                        prepared.manifest_fingerprint, fingerprint)

    def generate_signal(
        self,
        snapshot: ORBSignalSnapshot,
        parameters: Mapping[str, object] | None = None,
    ) -> ORBResearchSignal:
        if not isinstance(snapshot, ORBSignalSnapshot):
            raise ORBReferenceError("snapshot must be ORBSignalSnapshot")
        resolved = self.manifest.validate_parameters({} if parameters is None else parameters)
        if resolved["signal_price_field"] != "close":
            raise ORBReferenceError("unsupported ORB signal price field")

        if snapshot.close > snapshot.opening_range_high:
            action = ORBAction.BUY
            reason = "CLOSE_ABOVE_OPENING_RANGE_HIGH"
        elif snapshot.close < snapshot.opening_range_low:
            action = ORBAction.SELL
            reason = "CLOSE_BELOW_OPENING_RANGE_LOW"
        else:
            action = ORBAction.HOLD
            reason = "CLOSE_WITHIN_OR_AT_OPENING_RANGE"

        snapshot_fingerprint = CanonicalCodec.fingerprint(
            "algofortis-orb-signal-snapshot/v2",
            (
                ("symbol", snapshot.symbol),
                ("timestamp", snapshot.timestamp),
                ("close", snapshot.close),
                ("opening_range_high", snapshot.opening_range_high),
                ("opening_range_low", snapshot.opening_range_low),
                ("manifest", self.manifest.fingerprint),
            ),
        )
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-orb-research-signal/v2",
            (
                ("snapshot_fingerprint", snapshot_fingerprint),
                ("action", action),
                ("reason", reason),
            ),
        )
        return ORBResearchSignal(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            action=action,
            reason=reason,
            snapshot_fingerprint=snapshot_fingerprint,
            fingerprint=fingerprint,
        )

    def prepare_simulation(
        self,
        *,
        protective_policy_ref: str | None,
    ) -> ORBSimulationPreparation:
        """Validate an explicit protective-policy reference for research simulation.

        Phase-4's built-in policy remains research-only/non-promotable.  A
        TEST_ONLY reference is labelled explicitly; any other valid reference is
        still RESEARCH_ONLY until the later promotion authority evaluates a full
        evidence bundle.
        """

        try:
            validated = self.manifest.assert_executable_ready(protective_policy_ref)
        except StrategySDKError as exc:
            raise ORBReferenceError(str(exc)) from exc
        if validated is None:
            raise ORBReferenceError("protective policy is required")

        scope = "TEST_ONLY" if validated.startswith("TEST_ONLY/") else "RESEARCH_ONLY"
        fingerprint = CanonicalCodec.fingerprint(
            "algofortis-orb-simulation-preparation/v2",
            (
                ("manifest", self.manifest.fingerprint),
                ("protective_policy_ref", validated),
                ("evidence_scope", scope),
                ("promotion_eligible", False),
            ),
        )
        return ORBSimulationPreparation(
            protective_policy_ref=validated,
            evidence_scope=scope,
            promotion_eligible=False,
            manifest_fingerprint=self.manifest.fingerprint,
            fingerprint=fingerprint,
        )


__all__ = [
    "ORBReferenceError",
    "ORBAction",
    "ORBSignalSnapshot",
    "ORBResearchSignal",
    "ORBSimulationPreparation",
    "ORBReferenceStrategyV2",
]
