"""Durable Phase-5 Paper Promotion Tracking and Evidence Lifecycle Engine (ADR §122).

This module implements:
- Independent upstream statistical (Gate A) and paper-environment (Gate B) evaluation.
- Per-owner upstream validation provenance binding.
- Contiguous six-calendar-month clean NSE-session tracking.
- Durable current state and append-only session evidence.
- Idempotent session finalization and restart continuity.
- Milestone review evaluation (PF >= 1.5, Max DD <= 15%, OOS profitable).
- Immutable canonical promotion review report (algofortis-paper-promotion-report/v1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from engine.market.profile import MarketProfile, WeekendCalendar
from engine.portfolio.model import as_decimal
from engine.reproducibility.codec import CanonicalCodec
from engine.trades import TradeRecord
from engine.backtest.validation import (
    InstrumentIdentity,
    PromotionDecisionEvidence,
    PromotionGateKind,
    PromotionGateResult,
    ValidationStatus,
)


PROMOTION_REPORT_SCHEMA_VERSION = "algofortis-paper-promotion-report/v1"
UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION = "algofortis-upstream-promotion-bundle/v1"
PROMOTION_SESSION_RECORD_SCHEMA_VERSION = "algofortis-promotion-session-record/v1"
NSE_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class UpstreamPromotionEvidenceBundle:
    """Canonical immutable upstream backtest promotion evidence bundle (ADR §122 OD-W)."""

    strategy_id: str
    strategy_version: str
    manifest_fingerprint: str
    promotion_decision_fingerprint: str
    promotion_decision: PromotionDecisionEvidence
    schema_version: str = UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        if not self.manifest_fingerprint.strip():
            raise ValueError("manifest_fingerprint must not be empty")
        if not self.promotion_decision_fingerprint.strip():
            raise ValueError("promotion_decision_fingerprint must not be empty")
        if not isinstance(self.promotion_decision, PromotionDecisionEvidence):
            raise TypeError("promotion_decision must be PromotionDecisionEvidence")
        if self.promotion_decision.result_fingerprint != self.promotion_decision_fingerprint:
            raise ValueError("promotion_decision_fingerprint does not match promotion_decision.result_fingerprint")
        if self.promotion_decision.manifest_fingerprint != self.manifest_fingerprint:
            raise ValueError("manifest_fingerprint does not match promotion_decision.manifest_fingerprint")

    @property
    def bundle_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION,
            (
                ("strategy_id", self.strategy_id),
                ("strategy_version", self.strategy_version),
                ("manifest_fingerprint", self.manifest_fingerprint),
                ("promotion_decision_fingerprint", self.promotion_decision_fingerprint),
            ),
        )

    @classmethod
    def create(
        cls,
        strategy_id: str,
        strategy_version: str,
        promotion_decision: PromotionDecisionEvidence,
    ) -> UpstreamPromotionEvidenceBundle:
        """Create a canonical bundle binding strategy owner and PromotionDecisionEvidence."""
        return cls(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            manifest_fingerprint=promotion_decision.manifest_fingerprint,
            promotion_decision_fingerprint=promotion_decision.result_fingerprint,
            promotion_decision=promotion_decision,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "manifest_fingerprint": self.manifest_fingerprint,
            "promotion_decision_fingerprint": self.promotion_decision_fingerprint,
            "bundle_fingerprint": self.bundle_fingerprint,
            "promotion_decision": {
                "schema_version": self.promotion_decision.schema_version,
                "policy_fingerprint": self.promotion_decision.policy_fingerprint,
                "manifest_fingerprint": self.promotion_decision.manifest_fingerprint,
                "validation_scope_identity": self.promotion_decision.validation_scope_identity,
                "instrument": {
                    "market": self.promotion_decision.instrument.market,
                    "instrument": self.promotion_decision.instrument.instrument,
                    "segment": self.promotion_decision.instrument.segment,
                },
                "instrument_scope_identity": self.promotion_decision.instrument_scope_identity,
                "aggregate_walk_forward_identity": self.promotion_decision.aggregate_walk_forward_identity,
                "primary_oos_source_identity": self.promotion_decision.primary_oos_source_identity,
                "gate_results": [
                    {
                        "gate_kind": g.gate_kind.value,
                        "applicable": g.applicable,
                        "source_identities": list(g.source_identities),
                        "policy_identity": g.policy_identity,
                        "status": g.status.value,
                        "reason_codes": list(g.reason_codes),
                        "measurements": [[m[0], str(m[1])] for m in g.measurements],
                    }
                    for g in self.promotion_decision.gate_results
                ],
                "blocker_reasons": list(self.promotion_decision.blocker_reasons),
                "status": self.promotion_decision.status.value,
                "promotable": self.promotion_decision.promotable,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UpstreamPromotionEvidenceBundle:
        schema = data.get("schema_version")
        if schema != UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION:
            raise ValueError(f"unsupported bundle schema_version: {schema}")
        pd_data = data["promotion_decision"]
        gates = []
        for g in pd_data.get("gate_results", ()):
            gk = PromotionGateKind(g["gate_kind"])
            g_stat = ValidationStatus(g["status"])
            meas = tuple((m[0], Decimal(str(m[1]))) for m in g.get("measurements", ()))
            gates.append(PromotionGateResult(
                gate_kind=gk,
                applicable=bool(g.get("applicable", True)),
                source_identities=tuple(g.get("source_identities", ())),
                policy_identity=g["policy_identity"],
                status=g_stat,
                reason_codes=tuple(g.get("reason_codes", ())),
                measurements=meas,
            ))
        inst_data = pd_data["instrument"]
        inst = InstrumentIdentity(
            market=inst_data.get("market", "nse"),
            instrument=inst_data.get("instrument", "NIFTY"),
            segment=inst_data.get("segment", "equity"),
        )
        ev = PromotionDecisionEvidence(
            policy_fingerprint=pd_data["policy_fingerprint"],
            manifest_fingerprint=pd_data["manifest_fingerprint"],
            validation_scope_identity=pd_data["validation_scope_identity"],
            instrument=inst,
            instrument_scope_identity=pd_data["instrument_scope_identity"],
            aggregate_walk_forward_identity=pd_data["aggregate_walk_forward_identity"],
            primary_oos_source_identity=pd_data.get("primary_oos_source_identity"),
            gate_results=tuple(gates),
            blocker_reasons=tuple(pd_data.get("blocker_reasons", ())),
            status=ValidationStatus(pd_data["status"]),
            promotable=bool(pd_data.get("promotable", False)),
        )
        bundle = cls(
            strategy_id=data["strategy_id"],
            strategy_version=data["strategy_version"],
            manifest_fingerprint=data["manifest_fingerprint"],
            promotion_decision_fingerprint=data["promotion_decision_fingerprint"],
            promotion_decision=ev,
            schema_version=schema,
        )
        if "bundle_fingerprint" in data and data["bundle_fingerprint"] != bundle.bundle_fingerprint:
            raise ValueError("bundle_fingerprint mismatch in serialized bundle")
        return bundle


class PromotionTrackingStatus(str, Enum):
    NOT_ACTIVATED = "NOT_ACTIVATED"
    TRACKING_ACTIVE = "TRACKING_ACTIVE"
    TRACKING_COMPLETED = "TRACKING_COMPLETED"
    TRACKING_INELIGIBLE = "TRACKING_INELIGIBLE"


class PromotionSessionStatus(str, Enum):
    SESSION_QUALIFIED = "SESSION_QUALIFIED"
    SESSION_DISQUALIFIED = "SESSION_DISQUALIFIED"
    EVIDENCE_ONLY_NO_PROMOTION_CREDIT = "EVIDENCE_ONLY_NO_PROMOTION_CREDIT"


class PromotionMilestoneStatus(str, Enum):
    EVALUATION_PENDING = "EVALUATION_PENDING"
    CRITERIA_MET_PENDING_REVIEW = "CRITERIA_MET_PENDING_REVIEW"
    CRITERIA_FAILED = "CRITERIA_FAILED"


class PromotionDisqualificationReason(str, Enum):
    DATA_GAP = "DATA_GAP"
    RUNTIME_FAILURE = "RUNTIME_FAILURE"
    RECONCILIATION_FAILURE = "RECONCILIATION_FAILURE"
    OFFLINE_REQUIRED_SESSION = "OFFLINE_REQUIRED_SESSION"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    FAULT_INJECTION_ENABLED = "FAULT_INJECTION_ENABLED"
    RESEARCH_ZERO_COST = "RESEARCH_ZERO_COST"
    RESEARCH_ZERO_SLIPPAGE = "RESEARCH_ZERO_SLIPPAGE"
    UPSTREAM_UNPROMOTABLE = "UPSTREAM_UNPROMOTABLE"
    UPSTREAM_PROVENANCE_MISMATCH = "UPSTREAM_PROVENANCE_MISMATCH"
    UPSTREAM_EVIDENCE_ABSENT = "UPSTREAM_EVIDENCE_ABSENT"
    PARTIAL_SESSION_AT_ACTIVATION = "PARTIAL_SESSION_AT_ACTIVATION"
    INCOMPLETE_SESSION_OBSERVATION = "INCOMPLETE_SESSION_OBSERVATION"


def _require_aware(dt: datetime, field_name: str) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class PromotionTrackingState:
    """Authoritative durable current promotion tracking state per strategy owner."""

    strategy_id: str
    strategy_version: str
    paper_session_id: str
    configuration_identity: str
    upstream_promotion_fingerprint: str | None
    tracking_status: PromotionTrackingStatus
    activated_at: datetime | None
    window_start_date: date | None
    clean_days_count: int
    disqualified_days_count: int
    last_evaluated_session_date: date | None
    milestone_status: PromotionMilestoneStatus
    state_generation: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        if not self.paper_session_id.strip():
            raise ValueError("paper_session_id must not be empty")
        if not self.configuration_identity.strip():
            raise ValueError("configuration_identity must not be empty")
        if not isinstance(self.tracking_status, PromotionTrackingStatus):
            object.__setattr__(self, "tracking_status", PromotionTrackingStatus(self.tracking_status))
        if not isinstance(self.milestone_status, PromotionMilestoneStatus):
            object.__setattr__(self, "milestone_status", PromotionMilestoneStatus(self.milestone_status))
        if self.activated_at is not None:
            _require_aware(self.activated_at, "activated_at")
        _require_aware(self.updated_at, "updated_at")
        if self.clean_days_count < 0:
            raise ValueError("clean_days_count must be non-negative")
        if self.disqualified_days_count < 0:
            raise ValueError("disqualified_days_count must be non-negative")
        if self.state_generation < 0:
            raise ValueError("state_generation must be non-negative")


@dataclass(frozen=True)
class PromotionSessionRecord:
    """Authoritative append-only record of one scheduled trading session evaluation."""

    strategy_id: str
    strategy_version: str
    session_date: date
    paper_session_id: str
    configuration_identity: str
    upstream_promotion_fingerprint: str | None
    session_status: PromotionSessionStatus
    reasons: tuple[str, ...]
    recorded_at_utc: datetime
    record_schema_version: str = PROMOTION_SESSION_RECORD_SCHEMA_VERSION
    record_fingerprint: str | None = None

    def compute_fingerprint(self) -> str:
        return CanonicalCodec.fingerprint(
            PROMOTION_SESSION_RECORD_SCHEMA_VERSION,
            (
                ("strategy_id", self.strategy_id),
                ("strategy_version", self.strategy_version),
                ("session_date", self.session_date.isoformat()),
                ("paper_session_id", self.paper_session_id),
                ("configuration_identity", self.configuration_identity),
                ("upstream_promotion_fingerprint", self.upstream_promotion_fingerprint or ""),
                ("session_status", self.session_status.value),
                ("reasons", tuple(sorted(self.reasons))),
            ),
        )

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        if not self.paper_session_id.strip():
            raise ValueError("paper_session_id must not be empty")
        if not self.configuration_identity.strip():
            raise ValueError("configuration_identity must not be empty")
        if not isinstance(self.session_status, PromotionSessionStatus):
            object.__setattr__(self, "session_status", PromotionSessionStatus(self.session_status))
        _require_aware(self.recorded_at_utc, "recorded_at_utc")
        reasons_tuple = tuple(self.reasons)
        object.__setattr__(self, "reasons", reasons_tuple)
        if self.record_fingerprint is None:
            object.__setattr__(self, "record_fingerprint", self.compute_fingerprint())



@dataclass(frozen=True)
class PaperPromotionReport:
    """Immutable, canonically fingerprinted promotion milestone review artifact (algofortis-paper-promotion-report/v1)."""

    strategy_id: str
    strategy_version: str
    paper_session_id: str
    configuration_identity: str
    upstream_promotion_evidence_fingerprint: str | None
    promotion_tracking_generation: int
    activation_timestamp: datetime | None
    clean_window_start: date | None
    qualifying_interval_end: date | None
    clean_sessions_count: int
    performance_metrics: Mapping[str, Any]
    upstream_oos_profitable: bool
    milestone_status: PromotionMilestoneStatus
    generated_at_utc: datetime
    live_vs_paper_status: str = "DEFERRED_TO_PHASE7"
    schema_version: str = PROMOTION_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROMOTION_REPORT_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        if not self.paper_session_id.strip():
            raise ValueError("paper_session_id must not be empty")
        if not self.configuration_identity.strip():
            raise ValueError("configuration_identity must not be empty")
        if not isinstance(self.milestone_status, PromotionMilestoneStatus):
            object.__setattr__(self, "milestone_status", PromotionMilestoneStatus(self.milestone_status))
        if self.activation_timestamp is not None:
            _require_aware(self.activation_timestamp, "activation_timestamp")
        _require_aware(self.generated_at_utc, "generated_at_utc")
        object.__setattr__(self, "performance_metrics", MappingProxyType(dict(self.performance_metrics)))

    @property
    def fingerprint(self) -> str:
        metrics_tuple = tuple(
            (str(k), str(v) if isinstance(v, Decimal) else v)
            for k, v in sorted(self.performance_metrics.items())
        )
        return CanonicalCodec.fingerprint(
            self.schema_version,
            (
                ("schema_version", self.schema_version),
                ("strategy_id", self.strategy_id),
                ("strategy_version", self.strategy_version),
                ("paper_session_id", self.paper_session_id),
                ("configuration_identity", self.configuration_identity),
                ("upstream_promotion_evidence_fingerprint", self.upstream_promotion_evidence_fingerprint),
                ("promotion_tracking_generation", self.promotion_tracking_generation),
                ("activation_timestamp", self.activation_timestamp.isoformat() if self.activation_timestamp else None),
                ("clean_window_start", self.clean_window_start.isoformat() if self.clean_window_start else None),
                ("qualifying_interval_end", self.qualifying_interval_end.isoformat() if self.qualifying_interval_end else None),
                ("clean_sessions_count", self.clean_sessions_count),
                ("performance_metrics", metrics_tuple),
                ("upstream_oos_profitable", self.upstream_oos_profitable),
                ("milestone_status", self.milestone_status.value),
                ("live_vs_paper_status", self.live_vs_paper_status),
                ("generated_at_utc", self.generated_at_utc.isoformat()),
            ),
        )


class PromotionTrackingEngine:
    """State machine and accounting engine for Paper Promotion Lifecycle."""

    @staticmethod
    def initial_state(
        strategy_id: str,
        strategy_version: str,
        paper_session_id: str,
        configuration_identity: str,
        upstream_fingerprint: str | None,
        activation: str,
        promotion_eligible: bool,
        tracking_activated_at: datetime | None,
        now_utc: datetime,
        upstream_promotable: bool = True,
    ) -> PromotionTrackingState:
        """Create deterministic generation-0 promotion tracking state."""
        _require_aware(now_utc, "now_utc")
        if tracking_activated_at is None:
            status = PromotionTrackingStatus.NOT_ACTIVATED
        elif not promotion_eligible:
            status = PromotionTrackingStatus.TRACKING_INELIGIBLE
        elif activation == "observation_only":
            status = PromotionTrackingStatus.TRACKING_INELIGIBLE
        elif upstream_fingerprint is None or not upstream_fingerprint.strip():
            status = PromotionTrackingStatus.TRACKING_INELIGIBLE
        elif not upstream_promotable:
            status = PromotionTrackingStatus.TRACKING_INELIGIBLE
        else:
            status = PromotionTrackingStatus.TRACKING_ACTIVE

        return PromotionTrackingState(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            paper_session_id=paper_session_id,
            configuration_identity=configuration_identity,
            upstream_promotion_fingerprint=upstream_fingerprint,
            tracking_status=status,
            activated_at=tracking_activated_at,
            window_start_date=None,
            clean_days_count=0,
            disqualified_days_count=0,
            last_evaluated_session_date=None,
            milestone_status=PromotionMilestoneStatus.EVALUATION_PENDING,
            state_generation=0,
            updated_at=now_utc,
        )

    @staticmethod
    def evaluate_session_finalization(
        current_state: PromotionTrackingState,
        session_date: date,
        is_clean: bool,
        disqualification_reasons: Sequence[str],
        activation: str,
        now_utc: datetime,
    ) -> tuple[PromotionTrackingState, PromotionSessionRecord]:
        """Atomically transition tracking state and emit append-only session record for a scheduled NSE session."""
        _require_aware(now_utc, "now_utc")

        # Replay/idempotency check: if this date was already evaluated, caller handles no-op.
        reasons_tuple = tuple(disqualification_reasons)
        next_gen = current_state.state_generation + 1

        if current_state.tracking_status in (PromotionTrackingStatus.NOT_ACTIVATED, PromotionTrackingStatus.TRACKING_INELIGIBLE):
            # Not active or ineligible
            record = PromotionSessionRecord(
                strategy_id=current_state.strategy_id,
                strategy_version=current_state.strategy_version,
                session_date=session_date,
                paper_session_id=current_state.paper_session_id,
                configuration_identity=current_state.configuration_identity,
                upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
                session_status=PromotionSessionStatus.EVIDENCE_ONLY_NO_PROMOTION_CREDIT,
                reasons=reasons_tuple or ("TRACKING_INELIGIBLE_OR_NOT_ACTIVATED",),
                recorded_at_utc=now_utc,
            )
            new_state = PromotionTrackingState(
                strategy_id=current_state.strategy_id,
                strategy_version=current_state.strategy_version,
                paper_session_id=current_state.paper_session_id,
                configuration_identity=current_state.configuration_identity,
                upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
                tracking_status=current_state.tracking_status,
                activated_at=current_state.activated_at,
                window_start_date=current_state.window_start_date,
                clean_days_count=current_state.clean_days_count,
                disqualified_days_count=current_state.disqualified_days_count,
                last_evaluated_session_date=session_date,
                milestone_status=current_state.milestone_status,
                state_generation=next_gen,
                updated_at=now_utc,
            )
            return new_state, record

        # Tracking is active or completed
        if activation == "observation_only":
            record = PromotionSessionRecord(
                strategy_id=current_state.strategy_id,
                strategy_version=current_state.strategy_version,
                session_date=session_date,
                paper_session_id=current_state.paper_session_id,
                configuration_identity=current_state.configuration_identity,
                upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
                session_status=PromotionSessionStatus.EVIDENCE_ONLY_NO_PROMOTION_CREDIT,
                reasons=reasons_tuple or ("OBSERVATION_ONLY",),
                recorded_at_utc=now_utc,
            )
            new_state = PromotionTrackingState(
                strategy_id=current_state.strategy_id,
                strategy_version=current_state.strategy_version,
                paper_session_id=current_state.paper_session_id,
                configuration_identity=current_state.configuration_identity,
                upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
                tracking_status=current_state.tracking_status,
                activated_at=current_state.activated_at,
                window_start_date=current_state.window_start_date,
                clean_days_count=current_state.clean_days_count,
                disqualified_days_count=current_state.disqualified_days_count,
                last_evaluated_session_date=session_date,
                milestone_status=current_state.milestone_status,
                state_generation=next_gen,
                updated_at=now_utc,
            )
            return new_state, record

        if is_clean and not reasons_tuple:
            # Clean qualified session
            record = PromotionSessionRecord(
                strategy_id=current_state.strategy_id,
                strategy_version=current_state.strategy_version,
                session_date=session_date,
                paper_session_id=current_state.paper_session_id,
                configuration_identity=current_state.configuration_identity,
                upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
                session_status=PromotionSessionStatus.SESSION_QUALIFIED,
                reasons=(),
                recorded_at_utc=now_utc,
            )
            new_clean_count = current_state.clean_days_count + 1
            new_window_start = current_state.window_start_date or session_date
            
            # Check 6-month continuous completion
            completion_target = new_window_start + relativedelta(months=6)
            new_status = current_state.tracking_status
            if session_date >= completion_target:
                new_status = PromotionTrackingStatus.TRACKING_COMPLETED

            new_state = PromotionTrackingState(
                strategy_id=current_state.strategy_id,
                strategy_version=current_state.strategy_version,
                paper_session_id=current_state.paper_session_id,
                configuration_identity=current_state.configuration_identity,
                upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
                tracking_status=new_status,
                activated_at=current_state.activated_at,
                window_start_date=new_window_start,
                clean_days_count=new_clean_count,
                disqualified_days_count=current_state.disqualified_days_count,
                last_evaluated_session_date=session_date,
                milestone_status=current_state.milestone_status,
                state_generation=next_gen,
                updated_at=now_utc,
            )
            return new_state, record

        # Session Disqualified
        record = PromotionSessionRecord(
            strategy_id=current_state.strategy_id,
            strategy_version=current_state.strategy_version,
            session_date=session_date,
            paper_session_id=current_state.paper_session_id,
            configuration_identity=current_state.configuration_identity,
            upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
            session_status=PromotionSessionStatus.SESSION_DISQUALIFIED,
            reasons=reasons_tuple or ("UNSPECIFIED_DISQUALIFICATION",),
            recorded_at_utc=now_utc,
        )
        new_disq_count = current_state.disqualified_days_count + 1
        # Contiguous window is broken: window_start_date resets to None
        new_state = PromotionTrackingState(
            strategy_id=current_state.strategy_id,
            strategy_version=current_state.strategy_version,
            paper_session_id=current_state.paper_session_id,
            configuration_identity=current_state.configuration_identity,
            upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
            tracking_status=PromotionTrackingStatus.TRACKING_ACTIVE,
            activated_at=current_state.activated_at,
            window_start_date=None,
            clean_days_count=current_state.clean_days_count,
            disqualified_days_count=new_disq_count,
            last_evaluated_session_date=session_date,
            milestone_status=PromotionMilestoneStatus.EVALUATION_PENDING,
            state_generation=next_gen,
            updated_at=now_utc,
        )


        return new_state, record

    @staticmethod
    def calculate_performance_metrics(
        trade_records: Sequence[TradeRecord] | Sequence[Any],
        starting_capital: Decimal = Decimal("2000000.00"),
    ) -> dict[str, Decimal | int]:
        """Compute authoritative Profit Factor, Max Drawdown, Net PnL, and Trade Count from trade records."""
        if not trade_records:
            return {
                "profit_factor": Decimal("0"),
                "max_drawdown_pct": Decimal("0"),
                "net_pnl": Decimal("0"),
                "trade_count": 0,
                "gross_profit": Decimal("0"),
                "gross_loss": Decimal("0"),
            }

        gross_profit = Decimal("0")
        gross_loss = Decimal("0")
        cumulative_pnl = Decimal("0")
        peak_pnl = Decimal("0")
        max_drawdown = Decimal("0")

        for trade in trade_records:
            raw_pnl = getattr(trade, "net_pnl", getattr(trade, "gross_realized_pnl", Decimal("0")))
            pnl = as_decimal(raw_pnl, "pnl")
            if pnl > 0:
                gross_profit += pnl
            elif pnl < 0:
                gross_loss += abs(pnl)

            cumulative_pnl += pnl
            if cumulative_pnl > peak_pnl:
                peak_pnl = cumulative_pnl
            drawdown = peak_pnl - cumulative_pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = Decimal("999.99")  # Infinite / strictly winning
        else:
            profit_factor = Decimal("0")

        max_dd_pct = (max_drawdown / starting_capital) if starting_capital > 0 else max_drawdown

        return {
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd_pct,
            "net_pnl": cumulative_pnl,
            "trade_count": len(trade_records),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
        }

    @staticmethod
    def evaluate_milestone(
        current_state: PromotionTrackingState,
        trade_records: Sequence[TradeRecord] | Sequence[Any],
        upstream_oos_profitable: bool,
        evaluation_date: date,
        now_utc: datetime,
        starting_capital: Decimal = Decimal("2000000.00"),
    ) -> tuple[PromotionTrackingState, PaperPromotionReport | None]:
        """Evaluate pre-live promotion criteria (PF >= 1.5, Max DD <= 15%, OOS profitable, 6mo continuous)."""
        _require_aware(now_utc, "now_utc")

        # 1. Continuous six-month duration check
        if current_state.window_start_date is None:
            return current_state, None

        completion_target = current_state.window_start_date + relativedelta(months=6)
        if evaluation_date < completion_target:
            return current_state, None

        # 2. Performance metrics derivation from authoritative paper trades
        metrics = PromotionTrackingEngine.calculate_performance_metrics(trade_records, starting_capital=starting_capital)
        pf = metrics["profit_factor"]
        max_dd = metrics["max_drawdown_pct"]

        # 3. Threshold checks: PF >= 1.5, Max DD <= 15% (0.15), OOS profitable
        min_pf = Decimal("1.5")
        max_permitted_dd = Decimal("0.15")

        criteria_pass = (
            pf >= min_pf
            and max_dd <= max_permitted_dd
            and upstream_oos_profitable is True
            and current_state.clean_days_count > 0
        )

        next_gen = current_state.state_generation + 1
        milestone_status = (
            PromotionMilestoneStatus.CRITERIA_MET_PENDING_REVIEW
            if criteria_pass
            else PromotionMilestoneStatus.CRITERIA_FAILED
        )

        new_state = PromotionTrackingState(
            strategy_id=current_state.strategy_id,
            strategy_version=current_state.strategy_version,
            paper_session_id=current_state.paper_session_id,
            configuration_identity=current_state.configuration_identity,
            upstream_promotion_fingerprint=current_state.upstream_promotion_fingerprint,
            tracking_status=PromotionTrackingStatus.TRACKING_COMPLETED,
            activated_at=current_state.activated_at,
            window_start_date=current_state.window_start_date,
            clean_days_count=current_state.clean_days_count,
            disqualified_days_count=current_state.disqualified_days_count,
            last_evaluated_session_date=evaluation_date,
            milestone_status=milestone_status,
            state_generation=next_gen,
            updated_at=now_utc,
        )


        report = PaperPromotionReport(
            strategy_id=current_state.strategy_id,
            strategy_version=current_state.strategy_version,
            paper_session_id=current_state.paper_session_id,
            configuration_identity=current_state.configuration_identity,
            upstream_promotion_evidence_fingerprint=current_state.upstream_promotion_fingerprint,
            promotion_tracking_generation=next_gen,
            activation_timestamp=current_state.activated_at,
            clean_window_start=current_state.window_start_date,
            qualifying_interval_end=evaluation_date,
            clean_sessions_count=current_state.clean_days_count,
            performance_metrics=metrics,
            upstream_oos_profitable=upstream_oos_profitable,
            milestone_status=milestone_status,
            generated_at_utc=now_utc,
            live_vs_paper_status="DEFERRED_TO_PHASE7",
        )

        return new_state, report

    @staticmethod
    def evaluate_milestone_from_store(
        store: Any,
        owner: Any,
        upstream_oos_profitable: bool,
        evaluation_date: date,
        now_utc: datetime,
        report_destination_dir: str | Path | None = None,
    ) -> tuple[PromotionTrackingState, PaperPromotionReport | None, Path | None]:
        """Evaluate pre-live promotion milestone strictly derived from authoritative persisted paper trade ledger."""
        states = store.load_promotion_tracking_states()
        current_state = states.get(owner)
        if current_state is None:
            raise ValueError(f"No promotion tracking state found for {owner}")

        trade_records = store.load_completed_trades_for_strategy(owner)
        starting_cap = getattr(store, "_starting_capital", Decimal("2000000.00"))
        next_state, report = PromotionTrackingEngine.evaluate_milestone(
            current_state=current_state,
            trade_records=trade_records,
            upstream_oos_profitable=upstream_oos_profitable,
            evaluation_date=evaluation_date,
            now_utc=now_utc,
            starting_capital=starting_cap,
        )

        report_path = None
        if next_state != current_state:
            store.save_promotion_tracking_state(next_state)

        if report is not None and next_state.milestone_status == PromotionMilestoneStatus.CRITERIA_MET_PENDING_REVIEW:
            if not report_destination_dir or not str(report_destination_dir).strip():
                raise PromotionReportPublicationError(
                    "Cannot publish promotion report without an explicit destination directory"
                )
            report_path = PromotionReportWriter.publish(report, destination_dir=report_destination_dir)

        return next_state, report, report_path


class PromotionReportPublicationError(RuntimeError):
    """Raised when canonical promotion report publication fails or detects contradictory overwrite."""
    pass


class PromotionReportWriter:
    """Atomic publisher for algofortis-paper-promotion-report/v1 artifacts."""

    @staticmethod
    def default_filename(report: PaperPromotionReport) -> str:
        return f"algofortis-paper-promotion-report-{report.strategy_id}-{report.strategy_version}-{report.fingerprint[:12]}.json"

    @classmethod
    def publish(
        cls,
        report: PaperPromotionReport,
        destination_dir: str | Path | None = None,
    ) -> Path:
        if not destination_dir or not str(destination_dir).strip():
            raise PromotionReportPublicationError(
                "Promotion report publication requires an explicit non-empty destination directory"
            )
        dest_dir = Path(destination_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / cls.default_filename(report)
        payload = {
            "schema_version": report.schema_version,
            "fingerprint": report.fingerprint,
            "strategy_id": report.strategy_id,
            "strategy_version": report.strategy_version,
            "paper_session_id": report.paper_session_id,
            "configuration_identity": report.configuration_identity,
            "upstream_promotion_evidence_fingerprint": report.upstream_promotion_evidence_fingerprint,
            "promotion_tracking_generation": report.promotion_tracking_generation,
            "activation_timestamp": report.activation_timestamp.isoformat() if report.activation_timestamp else None,
            "clean_window_start": report.clean_window_start.isoformat() if report.clean_window_start else None,
            "qualifying_interval_end": report.qualifying_interval_end.isoformat() if report.qualifying_interval_end else None,
            "clean_sessions_count": report.clean_sessions_count,
            "performance_metrics": {k: str(v) if isinstance(v, Decimal) else v for k, v in sorted(report.performance_metrics.items())},
            "upstream_oos_profitable": report.upstream_oos_profitable,
            "milestone_status": report.milestone_status.value,
            "live_vs_paper_status": report.live_vs_paper_status,
            "generated_at_utc": report.generated_at_utc.isoformat(),
        }
        raw_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        if target.exists():
            try:
                existing_data = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                existing_data = {}
            if existing_data.get("fingerprint") == report.fingerprint:
                return target
            raise PromotionReportPublicationError(f"Contradictory promotion report already exists at {target}")
        staging = dest_dir / f".{target.name}.staging-{uuid4().hex}"
        try:
            staging.write_bytes(raw_bytes)
            os.replace(staging, target)
            return target
        except Exception as exc:
            if staging.exists():
                staging.unlink()
            raise PromotionReportPublicationError(f"Failed to publish promotion report: {exc}") from exc

