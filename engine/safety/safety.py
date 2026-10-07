"""Phase 5 OD-7 Item 10: Live paper safety management and derived safety state.

Provides:
- SafetyState enum representing effective operational health.
- KillSwitchState immutable durable authority container.
- SafetyAlert, SafetyTransitionResult, SafetyResumeResult.
- SafetyManager pure derived state calculator and kill-switch coordinator.

Derived effective safety precedence:
  PERSISTENCE_FAILED > INTEGRITY_BREACHED > KILL_SWITCH_ACTIVE > DISCONNECTED > OPERATIONAL
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Mapping

from engine.data.feeds.live_feed import FeedConnectionState

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from engine.persistence.sqlite_store import PersistenceHealth


class SafetyState(str, Enum):
    """Derived effective safety state for live paper trading."""

    OPERATIONAL = "OPERATIONAL"
    DISCONNECTED = "DISCONNECTED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    INTEGRITY_BREACHED = "INTEGRITY_BREACHED"


@dataclass(frozen=True)
class KillSwitchState:
    """Immutable model of the durable kill-switch authority.

    Only kill switch is a new durable Item-10 authority. Transport state,
    persistence health, and accounting integrity remain owned by their
    canonical existing components.
    """

    active: bool
    reason: str | None = None
    source: str | None = None
    activated_at: str | None = None  # Diagnostic UTC ISO timestamp (non-market-authority)
    activation_market_timestamp: datetime | None = None  # Authoritative market time if known

    def __post_init__(self) -> None:
        if self.active and (not self.reason or not self.reason.strip()):
            raise ValueError("reason is required when kill switch is active")
        if self.active and (not self.source or not self.source.strip()):
            raise ValueError("source is required when kill switch is active")
        if self.activation_market_timestamp is not None:
            if not isinstance(self.activation_market_timestamp, datetime) or self.activation_market_timestamp.tzinfo is None:
                raise ValueError("activation_market_timestamp must be a timezone-aware datetime")


@dataclass(frozen=True)
class SafetyAlert:
    """Immutable diagnostic safety alert (local only, zero cloud dependencies)."""

    alert_id: str
    severity: str  # "INFO", "WARNING", "CRITICAL", "FATAL"
    source: str
    reason: str
    timestamp: datetime | None = None  # Authoritative market timestamp or None
    operational_timestamp: str | None = None  # Diagnostic operational timestamp
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SafetyTransitionResult:
    """Result of an explicit safety state transition (e.g. kill-switch activation)."""

    success: bool
    prior_state: SafetyState
    current_state: SafetyState
    reason: str | None = None
    cancelled_order_ids: tuple[str, ...] = ()
    alert: SafetyAlert | None = None


@dataclass(frozen=True)
class SafetyResumeResult:
    """Result of an explicit resume attempt from kill switch."""

    success: bool
    current_state: SafetyState
    reason: str | None = None
    failed_prerequisites: tuple[str, ...] = ()
    alert: SafetyAlert | None = None


class SafetyManager:
    """Encapsulated safety state manager for LivePaperCoordinator.

    Owns ONLY the new durable kill-switch authority. Derives effective
    SafetyState deterministically from canonical underlying authorities.
    """

    def __init__(
        self,
        *,
        initial_kill_state: KillSwitchState | None = None,
        on_alert: Callable[[SafetyAlert], None] | None = None,
    ) -> None:
        self._kill_switch = initial_kill_state or KillSwitchState(active=False)
        self._on_alert = on_alert

    @property
    def kill_switch_state(self) -> KillSwitchState:
        return self._kill_switch

    @property
    def is_kill_switch_active(self) -> bool:
        return self._kill_switch.active

    def restore_kill_state(self, state: KillSwitchState) -> None:
        """Hydrate durable kill-switch state on restart."""
        if not isinstance(state, KillSwitchState):
            raise TypeError("state must be a KillSwitchState")
        self._kill_switch = state

    def derive_effective_state(
        self,
        *,
        feed_state: FeedConnectionState,
        persistence_health: PersistenceHealth,
        accounting_integrity_breached: bool,
        has_fresh_market_evidence: bool = True,
    ) -> SafetyState:
        """Compute the derived effective safety state per frozen precedence.

        Precedence:
          PERSISTENCE_FAILED > INTEGRITY_BREACHED > KILL_SWITCH_ACTIVE > DISCONNECTED > OPERATIONAL
        """
        if getattr(persistence_health, "name", "") == "FAILED" or getattr(persistence_health, "value", "") == "FAILED":
            return SafetyState.PERSISTENCE_FAILED
        if accounting_integrity_breached:
            return SafetyState.INTEGRITY_BREACHED
        if self._kill_switch.active:
            return SafetyState.KILL_SWITCH_ACTIVE
        if feed_state is not FeedConnectionState.CONNECTED or not has_fresh_market_evidence:
            return SafetyState.DISCONNECTED
        return SafetyState.OPERATIONAL

    def set_kill_switch(
        self,
        *,
        active: bool,
        reason: str | None = None,
        source: str = "operator",
        market_timestamp: datetime | None = None,
        operational_timestamp: str | None = None,
    ) -> KillSwitchState:
        """Update in-memory kill switch state."""
        if active:
            r = reason or "operator_activated"
            self._kill_switch = KillSwitchState(
                active=True,
                reason=r,
                source=source,
                activated_at=operational_timestamp,
                activation_market_timestamp=market_timestamp,
            )
        else:
            self._kill_switch = KillSwitchState(active=False)
        return self._kill_switch

    def emit_alert(self, alert: SafetyAlert) -> None:
        """Deliver safety alert to registered callback if present.

        F6: callback failure must not be silent; alerts are non-authorizing
        but safety transitions depend on operator visibility.
        """
        if self._on_alert is not None:
            try:
                self._on_alert(alert)
            except Exception:
                logger.critical(
                    "safety alert delivery failed; alert_id=%s severity=%s source=%s reason=%s",
                    getattr(alert, "alert_id", None),
                    getattr(alert, "severity", None),
                    getattr(alert, "source", None),
                    getattr(alert, "reason", None),
                    exc_info=True,
                )
