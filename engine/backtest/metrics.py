"""Deterministic, immutable Slice 10 backtest metrics over authoritative evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

from engine.costs import CostAssessment
from engine.portfolio import InstrumentIdentity
from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT, as_decimal, quantize_monetary
from engine.trades import TradeRecord
from engine.backtest.regime import EntryRegimeSnapshot, Regime, RegimeStatus
from engine.reproducibility.codec import CanonicalCodec


class MetricScopeKind(str, Enum):
    RUN_ACCOUNT = "RUN_ACCOUNT"
    STRATEGY = "STRATEGY"
    INSTRUMENT = "INSTRUMENT"
    STRATEGY_INSTRUMENT = "STRATEGY_INSTRUMENT"


class MetricStatus(str, Enum):
    VALID = "VALID"
    UNDEFINED = "UNDEFINED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class MetricScope:
    kind: MetricScopeKind
    run_id: str
    account_id: str
    strategy_id: str | None = None
    instrument: InstrumentIdentity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MetricScopeKind):
            object.__setattr__(self, "kind", MetricScopeKind(self.kind))
        for field_name in ("run_id", "account_id"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        needs_strategy = self.kind in (MetricScopeKind.STRATEGY, MetricScopeKind.STRATEGY_INSTRUMENT)
        needs_instrument = self.kind in (MetricScopeKind.INSTRUMENT, MetricScopeKind.STRATEGY_INSTRUMENT)
        if needs_strategy != (self.strategy_id is not None):
            raise ValueError("scope strategy_id does not match scope kind")
        if needs_instrument != (self.instrument is not None):
            raise ValueError("scope instrument does not match scope kind")
        if self.strategy_id is not None and not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if self.instrument is not None and not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")


@dataclass(frozen=True)
class MetricCalculationPolicy:
    policy_id: str
    version: str
    annualization_sessions: Decimal | int | str
    market_profile_refs: tuple[str, ...]
    risk_free_rate: Decimal | int | str = Decimal("0")
    sortino_target_rate: Decimal | int | str = Decimal("0")

    def __post_init__(self) -> None:
        for field_name in ("policy_id", "version"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        annualization = as_decimal(self.annualization_sessions, "annualization_sessions")
        if annualization <= 0:
            raise ValueError("annualization_sessions must be positive")
        refs = tuple(self.market_profile_refs)
        if not refs or any(not isinstance(value, str) or not value.strip() for value in refs):
            raise ValueError("market_profile_refs must be non-empty")
        object.__setattr__(self, "annualization_sessions", annualization)
        object.__setattr__(self, "market_profile_refs", refs)
        object.__setattr__(self, "risk_free_rate", as_decimal(self.risk_free_rate, "risk_free_rate"))
        object.__setattr__(self, "sortino_target_rate", as_decimal(self.sortino_target_rate, "sortino_target_rate"))


@dataclass(frozen=True)
class EquityObservation:
    """One completed, ordered gross-equity observation with cost timing evidence."""

    timestamp: datetime
    session_id: str
    gross_equity: Decimal | int | str
    accumulated_cost: Decimal | int | str
    source_id: str
    run_id: str
    account_id: str
    complete: bool = True

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.complete:
            raise ValueError("incomplete valuation evidence is not allowed")
        for field_name in ("session_id", "source_id", "run_id", "account_id"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        gross = as_decimal(self.gross_equity, "gross_equity")
        cost = as_decimal(self.accumulated_cost, "accumulated_cost")
        if gross < 0 or cost < 0:
            raise ValueError("equity and accumulated cost must be non-negative")
        object.__setattr__(self, "gross_equity", gross)
        object.__setattr__(self, "accumulated_cost", cost)

    @property
    def net_equity(self) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            return self.gross_equity - self.accumulated_cost


@dataclass(frozen=True)
class SessionInterval:
    """Authoritative eligible interval supplied from MarketProfile/session evidence."""

    start: datetime
    end: datetime
    profile_ref: str
    run_id: str
    account_id: str
    instrument: InstrumentIdentity | None = None

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.start.utcoffset() is None or self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("interval timestamps must be timezone-aware")
        if self.end <= self.start:
            raise ValueError("interval end must be after start")
        for field_name in ("profile_ref", "run_id", "account_id"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True)
class PositionInterval:
    instrument: InstrumentIdentity
    start: datetime
    end: datetime
    run_id: str
    account_id: str
    strategy_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentIdentity):
            raise TypeError("instrument must be InstrumentIdentity")
        if self.start.tzinfo is None or self.start.utcoffset() is None or self.end.tzinfo is None or self.end.utcoffset() is None or self.end < self.start:
            raise ValueError("position interval must be aware and non-negative")
        for field_name in ("run_id", "account_id"):
            if not isinstance(getattr(self, field_name), str) or not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.strategy_id is not None and (not isinstance(self.strategy_id, str) or not self.strategy_id.strip()):
            raise ValueError("strategy_id must be non-empty when supplied")


@dataclass(frozen=True)
class MetricValue:
    status: MetricStatus
    value: Decimal | timedelta | None = None
    reason: str | None = None
    provenance: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, MetricStatus):
            object.__setattr__(self, "status", MetricStatus(self.status))
        if self.status is MetricStatus.VALID and self.value is None:
            raise ValueError("VALID metric requires a value")
        if self.status is not MetricStatus.VALID and self.value is not None:
            raise ValueError("non-VALID metric cannot have a value")
        if self.status is not MetricStatus.VALID and not self.reason:
            raise ValueError("non-VALID metric requires a reason")
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("metric value must be finite")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


@dataclass(frozen=True)
class MetricSummary:
    scope: MetricScope
    policy: MetricCalculationPolicy
    evidence_id: str
    metrics: Mapping[str, MetricValue]
    net_basis: str = "NET_OF_COSTS"
    regime_buckets: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, MetricScope) or not isinstance(self.policy, MetricCalculationPolicy):
            raise TypeError("scope and policy are required metric contracts")
        if not self.evidence_id:
            raise ValueError("evidence_id must be non-empty")
        values = dict(self.metrics)
        if set(values) != set(MetricsCalculator.METRIC_NAMES) or not all(isinstance(value, MetricValue) for value in values.values()):
            raise ValueError("summary must contain the mandatory metric set")
        object.__setattr__(self, "metrics", MappingProxyType(values))
        buckets = dict(self.regime_buckets)
        required = {"TRENDING", "SIDEWAYS", "VOLATILE", "UNCLASSIFIED_WARMUP"}
        if buckets and set(buckets) != required:
            raise ValueError("regime_buckets must contain the frozen four buckets")
        if any(not isinstance(value, int) or value < 0 for value in buckets.values()):
            raise ValueError("regime bucket values must be non-negative integers")
        object.__setattr__(self, "regime_buckets", MappingProxyType(dict(sorted(buckets.items()))))


def _duration_parts(value: timedelta) -> tuple[int, int, int]:
    """Schema-owned exact timedelta representation for D4 metric identities."""
    if not isinstance(value, timedelta):
        raise TypeError("duration value must be timedelta")
    return value.days, value.seconds, value.microseconds


def _instrument_fields(value: InstrumentIdentity | None) -> object:
    """Canonical D4 fields for one full InstrumentIdentity, established order."""
    if value is None:
        return None
    return (
        value.market,
        value.instrument,
        value.segment,
        value.underlying,
        value.expiry,
        value.strike,
        value.option_type,
    )


def _event_key_fields(value) -> tuple[object, object]:
    return value.run_id, value.accounting_sequence


def _provenance_value(value: object) -> object:
    """Convert one provenance value to D4-encodable typed form."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, datetime):
        return value
    if isinstance(value, timedelta):
        return _duration_parts(value)
    if isinstance(value, Enum):
        return value
    if isinstance(value, Mapping):
        converted = {str(key): _provenance_value(item) for key, item in value.items()}
        return tuple((key, converted[key]) for key in sorted(converted))
    if isinstance(value, (tuple, list)):
        return tuple(_provenance_value(item) for item in value)
    raise TypeError(f"unsupported metric provenance value: {type(value).__name__}")


def _scope_fields(value: MetricScope) -> object:
    return (
        ("kind", value.kind),
        ("run_id", value.run_id),
        ("account_id", value.account_id),
        ("strategy_id", value.strategy_id),
        ("instrument", _instrument_fields(value.instrument)),
    )


def _policy_fields(value: MetricCalculationPolicy) -> object:
    return (
        ("policy_id", value.policy_id),
        ("version", value.version),
        ("annualization_sessions", value.annualization_sessions),
        ("market_profile_refs", tuple(sorted(value.market_profile_refs))),
        ("risk_free_rate", value.risk_free_rate),
        ("sortino_target_rate", value.sortino_target_rate),
    )


def _trade_leg_fields(value) -> object:
    return (
        ("event_key", _event_key_fields(value.event_key)),
        ("role", value.role),
        ("execution_timestamp", value.execution_timestamp),
        ("execution_price", value.execution_price),
        ("execution_quantity", value.execution_quantity),
        ("realized_pnl_delta", value.realized_pnl_delta),
    )


def _trade_fields(value: TradeRecord) -> object:
    return (
        ("trade_id", value.trade_id),
        ("account_id", value.account_id),
        ("currency", value.currency),
        ("monetary_quantum", value.monetary_quantum),
        ("position_key", (
            ("strategy_id", value.position_key.strategy_id),
            ("strategy_version", value.position_key.strategy_version),
            ("identity", _instrument_fields(value.position_key.identity)),
        )),
        ("instrument", _instrument_fields(value.instrument_identity)),
        ("position_side", value.position_side),
        ("opened_at", value.opened_at),
        ("closed_at", value.closed_at),
        ("holding_duration", _duration_parts(value.holding_duration)),
        ("entry_quantity", value.entry_quantity),
        ("exit_quantity", value.exit_quantity),
        ("average_entry_price", value.average_entry_price),
        ("contract_multiplier", value.contract_multiplier),
        ("entry_legs", tuple(_trade_leg_fields(item) for item in value.entry_legs)),
        ("exit_legs", tuple(_trade_leg_fields(item) for item in value.exit_legs)),
        ("gross_realized_pnl", value.gross_realized_pnl),
        ("status", value.status),
        ("opening_event_key", _event_key_fields(value.opening_event_key)),
        ("closing_event_key", _event_key_fields(value.closing_event_key)),
        ("provenance", _provenance_value(value.provenance)),
    )


def _observation_fields(value: EquityObservation) -> object:
    return (
        ("timestamp", value.timestamp),
        ("session_id", value.session_id),
        ("gross_equity", value.gross_equity),
        ("accumulated_cost", value.accumulated_cost),
        ("source_id", value.source_id),
        ("run_id", value.run_id),
        ("account_id", value.account_id),
    )


def _assessment_fields(value: CostAssessment) -> object:
    return (
        ("assessment_id", value.assessment_id),
        ("trade_evidence_fingerprint", value.trade_evidence_fingerprint),
        ("trade_id", value.trade_id),
        ("account_id", value.account_id),
        ("currency", value.currency),
        ("schedule_references", tuple(
            (item.schedule_id, item.version, item.fingerprint)
            for item in value.schedule_references
        )),
        ("component_results", tuple(
            (
                ("component_id", item.component_id),
                ("event_key", _event_key_fields(item.leg_event_key)),
                ("basis", item.basis),
                ("schedule_id", item.schedule_id),
                ("schedule_version", item.schedule_version),
                ("schedule_fingerprint", item.schedule_fingerprint),
                ("input_amount", item.input_amount),
                ("rate", item.rate),
                ("unrounded_amount", item.unrounded_amount),
                ("amount", item.amount),
            )
            for item in value.component_results
        )),
        ("total_cost", value.total_cost),
        ("gross_realized_pnl", value.gross_realized_pnl),
        ("net_realized_pnl", value.net_realized_pnl),
        ("trade", _trade_fields(value.trade_record)),
    )


def _interval_fields(value: SessionInterval) -> object:
    return (
        ("start", value.start),
        ("end", value.end),
        ("profile_ref", value.profile_ref),
        ("run_id", value.run_id),
        ("account_id", value.account_id),
        ("instrument", _instrument_fields(value.instrument)),
    )


def _position_fields(value: PositionInterval) -> object:
    return (
        ("instrument", _instrument_fields(value.instrument)),
        ("start", value.start),
        ("end", value.end),
        ("run_id", value.run_id),
        ("account_id", value.account_id),
        ("strategy_id", value.strategy_id),
    )


class MetricsCalculator:
    METRIC_NAMES = ("profit_factor", "win_rate", "net_profit", "max_drawdown", "sharpe", "sortino", "calmar", "expectancy", "recovery_factor", "cagr", "average_win", "average_loss", "exposure", "average_holding_time", "trade_count")

    def calculate(self, scope: MetricScope, policy: MetricCalculationPolicy, observations: Iterable[EquityObservation], trades: Iterable[TradeRecord], assessments: Iterable[CostAssessment], intervals: Iterable[SessionInterval] = (), positions: Iterable[PositionInterval] = (), regime_snapshots: Iterable[EntryRegimeSnapshot] = (), regime_aware: bool | None = None) -> MetricSummary:
        if not isinstance(scope, MetricScope) or not isinstance(policy, MetricCalculationPolicy):
            raise TypeError("scope and policy are required")
        trade_values = tuple(trades)
        if not all(isinstance(value, TradeRecord) for value in trade_values):
            raise TypeError("trades must contain TradeRecord values")
        selected = tuple(trade for trade in trade_values if self._matches(scope, trade))
        all_assessments = tuple(assessments)
        if not all(isinstance(value, CostAssessment) for value in all_assessments):
            raise TypeError("assessments must contain CostAssessment values")
        assessment_values = tuple(value for value in all_assessments if self._matches(scope, value.trade_record))
        observation_values = tuple(observations)
        if not all(isinstance(value, EquityObservation) for value in observation_values):
            raise TypeError("observations must contain EquityObservation values")
        selected_observations = tuple(value for value in observation_values if self._matches_observation(scope, value))
        interval_values = tuple(intervals)
        if not all(isinstance(value, SessionInterval) for value in interval_values):
            raise TypeError("intervals must contain SessionInterval values")
        selected_intervals = tuple(value for value in interval_values if self._matches_interval(scope, value))
        position_values = tuple(positions)
        if not all(isinstance(value, PositionInterval) for value in position_values):
            raise TypeError("positions must contain PositionInterval values")
        selected_positions = tuple(value for value in position_values if self._matches_position(scope, value))
        snapshots = tuple(regime_snapshots)
        if not all(isinstance(value, EntryRegimeSnapshot) for value in snapshots):
            raise TypeError("regime_snapshots must contain EntryRegimeSnapshot values")
        # Slice 10 callers remain valid unless they explicitly request the
        # P1-4 regime projection.  Supplying authoritative snapshots itself
        # activates that path; active calculations always fail closed.
        if regime_aware is not None and not isinstance(regime_aware, bool):
            raise TypeError("regime_aware must be bool when supplied")
        regime_active = bool(snapshots) if regime_aware is None else regime_aware
        buckets = self._regime_buckets(selected, snapshots) if regime_active else {}
        values = self._net_outcomes(selected, assessment_values)
        timeline = self._timeline(selected_observations, selected, assessment_values)
        monetary_quantum = selected[0].monetary_quantum if selected else Decimal("0.01")
        metrics = self._trade_metrics(values, monetary_quantum)
        metrics.update(self._equity_metrics(timeline, policy, monetary_quantum))
        if len(timeline) >= 2:
            metrics["net_profit"] = MetricValue(
                MetricStatus.VALID,
                quantize_monetary(timeline[-1].net_equity - timeline[0].net_equity, monetary_quantum),
            )
        metrics["exposure"] = self._exposure(scope, selected_intervals, selected_positions)
        metrics["average_holding_time"] = self._holding(selected, selected_intervals)
        evidence_id = self._evidence_id(scope, policy, timeline, selected, assessment_values, selected_intervals, selected_positions)
        return MetricSummary(scope, policy, evidence_id, metrics, regime_buckets=buckets)

    @staticmethod
    def _regime_buckets(trades: tuple[TradeRecord, ...], snapshots: tuple[EntryRegimeSnapshot, ...]) -> dict[str, int]:
        result = {"TRENDING": 0, "SIDEWAYS": 0, "VOLATILE": 0, "UNCLASSIFIED_WARMUP": 0}
        by_key = {value.entry_event_key: value for value in snapshots}
        if len(by_key) != len(snapshots):
            raise ValueError("duplicate entry regime snapshot is ambiguous")
        for trade in trades:
            snapshot = by_key.get(trade.opening_event_key)
            if snapshot is None:
                raise ValueError("completed trade lacks authoritative entry regime evidence")
            bucket = "UNCLASSIFIED_WARMUP" if snapshot.regime_status is RegimeStatus.UNCLASSIFIED_WARMUP else snapshot.regime.value
            result[bucket if isinstance(bucket, str) else bucket.value] += 1
        return result

    @staticmethod
    def _matches(scope: MetricScope, trade: TradeRecord) -> bool:
        if trade.opening_event_key.run_id != scope.run_id or trade.closing_event_key.run_id != scope.run_id or trade.account_id != scope.account_id:
            return False
        if scope.strategy_id is not None and trade.position_key.strategy_id != scope.strategy_id:
            return False
        return scope.instrument is None or trade.instrument_identity == scope.instrument

    @staticmethod
    def _matches_observation(scope: MetricScope, observation: EquityObservation) -> bool:
        return observation.run_id == scope.run_id and observation.account_id == scope.account_id

    @staticmethod
    def _matches_interval(scope: MetricScope, interval: SessionInterval) -> bool:
        return (
            interval.run_id == scope.run_id
            and interval.account_id == scope.account_id
            and (scope.instrument is None or interval.instrument == scope.instrument)
        )

    @staticmethod
    def _matches_position(scope: MetricScope, position: PositionInterval) -> bool:
        return (
            position.run_id == scope.run_id
            and position.account_id == scope.account_id
            and (scope.strategy_id is None or position.strategy_id == scope.strategy_id)
            and (scope.instrument is None or position.instrument == scope.instrument)
        )

    def _net_outcomes(self, trades: tuple[TradeRecord, ...], assessments: Iterable[CostAssessment]) -> tuple[Decimal, ...]:
        values = tuple(assessments)
        if not all(isinstance(value, CostAssessment) for value in values):
            raise TypeError("assessments must contain CostAssessment values")
        by_trade = {assessment.trade_id: assessment for assessment in values}
        if len(by_trade) != len(values):
            raise ValueError("duplicate cost assessment is ambiguous")
        outcomes = []
        for trade in trades:
            assessment = by_trade.get(trade.trade_id)
            if assessment is None or assessment.trade_record != trade:
                raise ValueError("required cost evidence unavailable")
            outcomes.append(assessment.net_realized_pnl)
        return tuple(outcomes)

    def _timeline(self, observations: Iterable[EquityObservation], trades: tuple[TradeRecord, ...], assessments: Iterable[CostAssessment]) -> tuple[EquityObservation, ...]:
        values = tuple(observations)
        if not all(isinstance(value, EquityObservation) for value in values):
            raise TypeError("observations must contain EquityObservation")
        ordered = tuple(sorted(values, key=lambda value: value.timestamp))
        if ordered != values:
            raise ValueError("equity observations must be monotonic")
        if len({value.timestamp for value in values}) != len(values) or len({value.source_id for value in values}) != len(values):
            raise ValueError("conflicting duplicate equity observation")
        costs: list[tuple[datetime, Decimal]] = []
        selected_ids = {trade.trade_id for trade in trades}
        for assessment in assessments:
            if assessment.trade_id not in selected_ids:
                continue
            timestamps = {leg.event_key: leg.execution_timestamp for leg in (*assessment.trade_record.entry_legs, *assessment.trade_record.exit_legs)}
            for component in assessment.component_results:
                costs.append((timestamps[component.leg_event_key], component.amount))
        for observation in ordered:
            expected = sum((amount for timestamp, amount in costs if timestamp <= observation.timestamp), Decimal("0"))
            if observation.accumulated_cost != expected:
                raise ValueError("accumulated cost does not match execution-time cost evidence")
        return ordered

    def _trade_metrics(self, outcomes: tuple[Decimal, ...], quantum: Decimal) -> dict[str, MetricValue]:
        count = Decimal(len(outcomes)); valid = lambda value: MetricValue(MetricStatus.VALID, value)
        undefined = lambda reason: MetricValue(MetricStatus.UNDEFINED, reason=reason)
        insufficient = lambda reason: MetricValue(MetricStatus.INSUFFICIENT_DATA, reason=reason)
        if not outcomes:
            return {"trade_count": valid(Decimal("0")), "win_rate": insufficient("no completed trades"), "average_win": undefined("no winning trades"), "average_loss": undefined("no losing trades"), "profit_factor": insufficient("no completed trades"), "expectancy": insufficient("no completed trades"), "net_profit": valid(Decimal("0"))}
        wins = tuple(value for value in outcomes if value > 0); losses = tuple(value for value in outcomes if value < 0)
        net = quantize_monetary(sum(outcomes, Decimal("0")), quantum)
        result = {"trade_count": valid(count), "win_rate": valid(Decimal(len(wins)) / count), "net_profit": valid(net), "expectancy": valid(quantize_monetary(net / count, quantum)), "average_win": valid(quantize_monetary(sum(wins, Decimal("0")) / Decimal(len(wins)), quantum)) if wins else undefined("no winning trades"), "average_loss": valid(quantize_monetary(sum(losses, Decimal("0")) / Decimal(len(losses)), quantum)) if losses else undefined("no losing trades")}
        result["profit_factor"] = valid(sum(wins, Decimal("0")) / abs(sum(losses, Decimal("0")))) if losses else undefined("no losing trades")
        return result

    def _equity_metrics(self, timeline: tuple[EquityObservation, ...], policy: MetricCalculationPolicy, quantum: Decimal) -> dict[str, MetricValue]:
        undefined=lambda r: MetricValue(MetricStatus.UNDEFINED, reason=r); insufficient=lambda r: MetricValue(MetricStatus.INSUFFICIENT_DATA, reason=r); valid=lambda v,p={}: MetricValue(MetricStatus.VALID,v,provenance=p)
        if not timeline:
            return {key: insufficient("no equity observations") for key in ("max_drawdown", "recovery_factor", "sharpe", "sortino", "cagr", "calmar")}
        peak=timeline[0]; trough=timeline[0]; max_money=Decimal("0")
        for item in timeline:
            if item.net_equity > peak.net_equity: peak=item
            draw=peak.net_equity-item.net_equity
            if draw > max_money: max_money, trough=draw,item; draw_peak=peak
        draw_peak = locals().get("draw_peak", peak)
        fraction=Decimal("0") if draw_peak.net_equity == 0 else max_money/draw_peak.net_equity
        dd=valid(max_money,{"peak_timestamp":CanonicalCodec.timestamp_text(draw_peak.timestamp),"trough_timestamp":CanonicalCodec.timestamp_text(trough.timestamp),"drawdown_fraction":str(fraction)})
        returns=[]; last={}
        for item in timeline: last[item.session_id]=item
        sessions=tuple(last.values())
        for prior,current in zip(sessions,sessions[1:]):
            if prior.net_equity <= 0: return {"max_drawdown":dd,"recovery_factor":insufficient("invalid prior equity"),"sharpe":insufficient("invalid prior equity"),"sortino":insufficient("invalid prior equity"),"cagr":undefined("invalid starting equity"),"calmar":insufficient("invalid prior equity")}
            returns.append(current.net_equity/prior.net_equity-Decimal("1"))
        if len(sessions)<2: return {"max_drawdown":dd,"recovery_factor":undefined("zero maximum drawdown") if max_money==0 else insufficient("insufficient elapsed period"),"sharpe":insufficient("insufficient return observations"),"sortino":insufficient("insufficient return observations"),"cagr":insufficient("insufficient elapsed period"),"calmar":insufficient("insufficient elapsed period")}
        years=Decimal(len(sessions)-1)/policy.annualization_sessions
        cagr=undefined("invalid starting equity") if timeline[0].net_equity<=0 else valid((timeline[-1].net_equity/timeline[0].net_equity) ** (Decimal("1")/years)-Decimal("1"))
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            mean=sum(returns,Decimal("0"))/Decimal(len(returns)); variance=sum(((value-mean)**2 for value in returns),Decimal("0"))/Decimal(len(returns)); std=variance.sqrt()
            annual_root=policy.annualization_sessions.sqrt()
            sharpe=undefined("zero return volatility") if std==0 else valid((mean-policy.risk_free_rate)/std*annual_root)
            downside=[min(Decimal("0"),value-policy.sortino_target_rate) for value in returns]; down=(sum((x*x for x in downside),Decimal("0"))/Decimal(len(downside))).sqrt()
            sortino=undefined("zero downside deviation") if down==0 else valid((mean-policy.sortino_target_rate)/down*annual_root)
        recovery=undefined("zero maximum drawdown") if max_money==0 else valid((timeline[-1].net_equity-timeline[0].net_equity)/max_money)
        calmar=undefined("zero maximum drawdown") if max_money==0 else (valid(cagr.value/fraction) if cagr.status is MetricStatus.VALID else cagr)
        return {"max_drawdown":dd,"recovery_factor":recovery,"sharpe":sharpe,"sortino":sortino,"cagr":cagr,"calmar":calmar}

    def _exposure(self, scope, intervals, positions):
        eligible=self._union(tuple(intervals)); occupied=[]
        for position in positions:
            if scope.instrument is not None and position.instrument != scope.instrument: continue
            if scope.strategy_id is not None and position.strategy_id != scope.strategy_id: continue
            for interval in eligible:
                if interval.instrument is None or interval.instrument == position.instrument:
                    start=max(position.start,interval.start); end=min(position.end,interval.end)
                    if end>start:
                        occupied.append(SessionInterval(start, end, interval.profile_ref, scope.run_id, scope.account_id, position.instrument))
        denominator=sum((item.end-item.start for item in eligible),timedelta())
        if not denominator: return MetricValue(MetricStatus.INSUFFICIENT_DATA,reason="no eligible session interval")
        numerator=sum((item.end-item.start for item in self._union(tuple(occupied))),timedelta())
        return MetricValue(MetricStatus.VALID, self._seconds(numerator) / self._seconds(denominator))

    def _holding(self,trades,intervals):
        durations=[]
        for trade in trades:
            start,end=trade.opened_at,trade.closed_at; total=timedelta()
            applicable = tuple(interval for interval in intervals if interval.instrument == trade.instrument_identity)
            for interval in self._union(applicable):
                if interval.instrument == trade.instrument_identity:
                    total+=max(timedelta(),min(end,interval.end)-max(start,interval.start))
            durations.append(total)
        if not durations:return MetricValue(MetricStatus.INSUFFICIENT_DATA,reason="no completed trades")
        return MetricValue(MetricStatus.VALID,sum(durations,timedelta())/len(durations))

    @staticmethod
    def _union(intervals):
        ordered=sorted(intervals,key=lambda x:x.start); merged=[]
        for item in ordered:
            if merged and item.start<=merged[-1].end:
                previous = merged[-1]
                instrument = previous.instrument if previous.instrument == item.instrument else None
                profile_ref = previous.profile_ref if previous.profile_ref == item.profile_ref else "scope-union"
                merged[-1]=SessionInterval(previous.start, max(previous.end,item.end), profile_ref, previous.run_id, previous.account_id, instrument)
            else: merged.append(item)
        return tuple(merged)

    @staticmethod
    def _seconds(value: timedelta) -> Decimal:
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            return Decimal(value.days * 86_400 + value.seconds) + Decimal(value.microseconds) / Decimal("1000000")

    @staticmethod
    def _evidence_id(scope, policy, timeline, trades, assessments, intervals, positions):
        return CanonicalCodec.fingerprint(
            "algofortis-metric-evidence/v2",
            (
                ("scope", _scope_fields(scope)),
                ("policy", _policy_fields(policy)),
                ("net_basis", "NET_OF_COSTS"),
                ("trades", tuple(sorted((_trade_fields(value) for value in trades), key=CanonicalCodec.encode_value))),
                ("equity_observations", tuple(sorted((_observation_fields(value) for value in timeline), key=CanonicalCodec.encode_value))),
                ("cost_assessments", tuple(sorted((_assessment_fields(value) for value in assessments), key=CanonicalCodec.encode_value))),
                ("session_intervals", tuple(sorted((_interval_fields(value) for value in intervals), key=CanonicalCodec.encode_value))),
                ("position_intervals", tuple(sorted((_position_fields(value) for value in positions), key=CanonicalCodec.encode_value))),
            ),
        )
