"""Engine-side validation and neutral translation of frozen strategy signals."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, Mapping

from engine.backtest.engine import BarEvent
from engine.reproducibility.codec import CanonicalCodec
from engine.strategy.base import SUPPORTED_SIGNAL_ACTIONS, Signal


ACTIONABLE_ACTIONS = frozenset({"BUY", "SELL", "EXIT"})


def _require_aware(timestamp: datetime) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("source event timestamp must be timezone-aware")


def signal_intent_identity(
    intent: SignalIntent | None = None,
    *,
    strategy_id: str | None = None,
    strategy_version: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    originating_timestamp: datetime | None = None,
    action: str | None = None,
) -> str:
    """Deterministic canonical signal intent identity (``algofortis-signal-intent/v1``).

    CanonicalCodec only, exact semantic field order: strategy_id,
    strategy_version, symbol, timeframe, originating_timestamp, action.
    Confidence and metadata are EXCLUDED. No delimiter concatenation,
    no JSON-SHA parallel identity, no repr(), no pickle, no Python hash().
    """
    if intent is not None:
        if not isinstance(intent, SignalIntent):
            raise TypeError("intent must be a SignalIntent instance")
        strategy_id = intent.strategy_id
        strategy_version = intent.strategy_version
        symbol = intent.symbol
        timeframe = intent.timeframe
        originating_timestamp = intent.originating_timestamp
        action = intent.action

    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError("strategy_id must be a non-empty string")
    if not isinstance(strategy_version, str) or not strategy_version.strip():
        raise ValueError("strategy_version must be a non-empty string")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe must be a non-empty string")
    if not isinstance(originating_timestamp, datetime):
        raise TypeError("originating_timestamp must be a datetime")
    _require_aware(originating_timestamp)
    if not isinstance(action, str) or action not in SUPPORTED_SIGNAL_ACTIONS:
        raise ValueError(f"action must be a supported signal action: {action!r}")

    return CanonicalCodec.fingerprint(
        "algofortis-signal-intent/v1",
        (
            ("strategy_id", strategy_id),
            ("strategy_version", strategy_version),
            ("symbol", symbol.casefold()),
            ("timeframe", timeframe),
            ("originating_timestamp", originating_timestamp),
            ("action", action),
        ),
    )


@dataclass(frozen=True)
class SignalIntakeContext:
    """Immutable provenance supplied alongside a frozen strategy Signal."""

    source_event: BarEvent
    strategy_id: str
    strategy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_event, BarEvent):
            raise TypeError("source_event must be a BarEvent")
        _require_aware(self.source_event.timestamp)
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be non-empty")


@dataclass(frozen=True)
class SignalIntent:
    """Immutable, non-order instruction preserved for later engine slices."""

    action: Literal["BUY", "SELL", "EXIT"]
    confidence: float
    symbol: str
    timeframe: str
    originating_timestamp: datetime
    strategy_id: str
    strategy_version: str
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.action not in ACTIONABLE_ACTIONS:
            raise ValueError(f"Unsupported actionable signal action: {self.action}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Signal confidence must be between 0.0 and 1.0")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.timeframe:
            raise ValueError("timeframe must not be empty")
        _require_aware(self.originating_timestamp)
        if not self.strategy_id.strip() or not self.strategy_version.strip():
            raise ValueError("strategy identity must be non-empty")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", MappingProxyType(deepcopy(dict(self.metadata))))

    @property
    def identity(self) -> str:
        """Return the deterministic canonical identity for this SignalIntent."""
        return signal_intent_identity(self)


class SignalIntake:
    """Accept frozen Signals and stop at a neutral, non-executable intent."""

    def intake(self, signal: Signal, context: SignalIntakeContext) -> SignalIntent | None:
        """Validate one signal and preserve its source-event provenance.

        BUY, SELL, and EXIT become neutral intents. HOLD is valid but produces
        no intent. The method performs no order, fill, or portfolio mutation.
        """
        self._validate_signal(signal)
        if not isinstance(context, SignalIntakeContext):
            raise TypeError("context must be a SignalIntakeContext")

        if signal.action == "HOLD":
            return None

        return SignalIntent(
            action=signal.action,
            confidence=signal.confidence,
            symbol=context.source_event.symbol.casefold(),
            timeframe=context.source_event.timeframe,
            originating_timestamp=context.source_event.timestamp,
            strategy_id=context.strategy_id,
            strategy_version=context.strategy_version,
            metadata=signal.metadata,
        )

    @staticmethod
    def _validate_signal(signal: Signal) -> None:
        if not isinstance(signal, Signal):
            raise TypeError("signal must be a Signal")
        if signal.action not in SUPPORTED_SIGNAL_ACTIONS:
            raise ValueError(f"Unsupported signal action: {signal.action}")
        if not 0.0 <= signal.confidence <= 1.0:
            raise ValueError("Signal confidence must be between 0.0 and 1.0")
        if not isinstance(signal.metadata, dict):
            raise TypeError("Signal metadata must be a dictionary")
