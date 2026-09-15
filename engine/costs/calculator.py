"""Deterministic Slice 8 calculation over immutable completed trades."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Iterable

from engine.execution import ExecutionOutcome, ExecutionResult
from engine.portfolio import AccountingOutcome
from engine.portfolio.model import INTERNAL_DECIMAL_CONTEXT, as_decimal, quantize_monetary
from engine.trades import TradeLeg, TradeRecord, TradeRole

from .model import (
    CostAssessment, CostLegAssessment, CostBasis, CostComponentResult, CostComponentRule,
    CostSchedule, CostScheduleAmbiguityError, CostSide, CostUnavailableError,
    assessment_identity, leg_assessment_identity, leg_evidence_fingerprint, trade_evidence_fingerprint,
)


def _side(leg: TradeLeg) -> CostSide:
    return CostSide.BUY if leg.role is TradeRole.ENTRY else CostSide.SELL


class CostCalculator:
    """Stateless calculator; identical immutable inputs reproduce equal results."""

    def resolve_schedule(
        self, trade: TradeRecord, timestamp, schedules: Iterable[CostSchedule]
    ) -> CostSchedule:
        candidates = tuple(schedule for schedule in schedules if schedule.applies_to(trade, timestamp))
        if not candidates:
            raise CostUnavailableError("COST_UNAVAILABLE")
        if len(candidates) != 1:
            raise CostScheduleAmbiguityError("ambiguous applicable cost schedules")
        schedule = candidates[0]
        if schedule.currency != trade.currency:
            raise ValueError("cost schedule currency mismatch")
        return schedule

    def assess(
        self, trade: TradeRecord, schedules: CostSchedule | Iterable[CostSchedule]
    ) -> CostAssessment:
        if not isinstance(trade, TradeRecord):
            raise TypeError("trade must be a TradeRecord")
        schedule_values = (schedules,) if isinstance(schedules, CostSchedule) else tuple(schedules)
        if not schedule_values or not all(isinstance(value, CostSchedule) for value in schedule_values):
            raise TypeError("schedules must contain CostSchedule values")
        results: list[CostComponentResult] = []
        references = set()
        for leg in (*trade.entry_legs, *trade.exit_legs):
            self._validate_economic_leg(leg)
            schedule = self.resolve_schedule(trade, leg.execution_timestamp, schedule_values)
            references.add(schedule.reference)
            results.extend(self._assess_leg(leg, schedule, trade.contract_multiplier))
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            raw_total = sum((result.amount for result in results), Decimal("0"))
            total = quantize_monetary(raw_total, trade.monetary_quantum)
            gross = quantize_monetary(
                as_decimal(trade.gross_realized_pnl, "gross_realized_pnl"),
                trade.monetary_quantum,
            )
            net = quantize_monetary(gross - total, trade.monetary_quantum)
        schedule_references = tuple(sorted(references))
        evidence_fingerprint = trade_evidence_fingerprint(trade)
        assessment_id = assessment_identity(evidence_fingerprint, schedule_references)
        return CostAssessment(
            assessment_id, evidence_fingerprint, trade.trade_id, trade.account_id, trade.currency,
            schedule_references, tuple(results), total, gross, net, trade,
        )

    def assess_leg(
        self, leg: TradeLeg, *, account_id: str, currency: str, instrument_identity,
        contract_multiplier: Decimal, monetary_quantum: Decimal, schedules: CostSchedule | Iterable[CostSchedule],
    ) -> CostLegAssessment:
        """Produce pre-closure authoritative cost evidence from one accepted leg."""
        self._validate_economic_leg(leg)
        schedule_values = (schedules,) if isinstance(schedules, CostSchedule) else tuple(schedules)
        candidates = tuple(schedule for schedule in schedule_values if (
            schedule.effective_from <= leg.execution_timestamp
            and (schedule.effective_to is None or leg.execution_timestamp <= schedule.effective_to)
            and (schedule.market is None or schedule.market == instrument_identity.market)
            and (schedule.instrument is None or schedule.instrument == instrument_identity.instrument)
            and (schedule.segment is None or schedule.segment == instrument_identity.segment)
        ))
        if not candidates:
            raise CostUnavailableError("COST_UNAVAILABLE")
        if len(candidates) != 1:
            raise CostScheduleAmbiguityError("ambiguous applicable cost schedules")
        schedule = candidates[0]
        if schedule.currency != currency:
            raise ValueError("cost schedule currency mismatch")
        multiplier = as_decimal(contract_multiplier, "contract_multiplier")
        quantum = as_decimal(monetary_quantum, "monetary_quantum")
        if multiplier <= 0 or quantum <= 0:
            raise ValueError("contract_multiplier and monetary_quantum must be positive")
        results = self._assess_leg(leg, schedule, multiplier)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total = quantize_monetary(sum((result.amount for result in results), Decimal("0")), quantum)
        evidence = leg_evidence_fingerprint(leg, account_id, currency, instrument_identity, multiplier)
        reference = schedule.reference
        return CostLegAssessment(
            "sentinelx-cost-leg-assessment/v2", leg_assessment_identity(leg.event_key, reference, evidence),
            leg.event_key, account_id, currency, instrument_identity, _side(leg), leg.execution_timestamp,
            leg.execution_price, leg.execution_quantity, multiplier, quantum, reference, results, total, evidence,
        )

    def compose_completed(
        self, trade: TradeRecord, leg_assessments: Iterable[CostLegAssessment]
    ) -> CostAssessment:
        """Compose completed-trade evidence from already recognized leg evidence."""
        values = tuple(leg_assessments)
        expected_keys = {leg.event_key for leg in (*trade.entry_legs, *trade.exit_legs)}
        if {value.leg_event_key for value in values} != expected_keys or len(values) != len(expected_keys):
            raise ValueError("completed trade requires exactly one assessment per economic leg")
        if any(value.account_id != trade.account_id or value.currency != trade.currency for value in values):
            raise ValueError("leg assessment account/currency does not match trade")
        references = tuple(sorted({value.schedule_reference for value in values}))
        results = tuple(result for value in values for result in value.component_results)
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            total = quantize_monetary(sum((value.total_cost for value in values), Decimal("0")), trade.monetary_quantum)
            gross = quantize_monetary(trade.gross_realized_pnl, trade.monetary_quantum)
            net = quantize_monetary(gross - total, trade.monetary_quantum)
        evidence = trade_evidence_fingerprint(trade)
        return CostAssessment(assessment_identity(evidence, references), evidence, trade.trade_id, trade.account_id,
                              trade.currency, references, results, total, gross, net, trade)

    def _validate_economic_leg(self, leg: TradeLeg) -> None:
        evidence = leg.accounting_result.source_evidence
        if (
            leg.accounting_result.outcome is not AccountingOutcome.ACCEPTED
            or not isinstance(evidence, ExecutionResult)
            or evidence.outcome is not ExecutionOutcome.FILLED
        ):
            raise ValueError("non-economic trade evidence cannot be costed")

    def _assess_leg(
        self, leg: TradeLeg, schedule: CostSchedule, multiplier: Decimal
    ) -> tuple[CostComponentResult, ...]:
        selected = [rule for rule in schedule.component_rules if rule.side in (CostSide.BOTH, _side(leg))]
        pending = {rule.component_id: rule for rule in selected}
        completed: dict[str, CostComponentResult] = {}
        while pending:
            ready = [
                rule for rule in pending.values()
                if all(dependency in completed for dependency in rule.dependency_ids)
            ]
            if not ready:
                missing = sorted({dep for rule in pending.values() for dep in rule.dependency_ids if dep not in pending and dep not in completed})
                if missing:
                    raise ValueError(f"missing dependency: {', '.join(missing)}")
                raise ValueError("circular cost component dependency")
            for rule in sorted(ready, key=lambda value: value.component_id):
                completed[rule.component_id] = self._calculate(rule, leg, schedule, multiplier, completed)
                pending.pop(rule.component_id)
        return tuple(completed[component_id] for component_id in sorted(completed))

    def _calculate(
        self, rule: CostComponentRule, leg: TradeLeg, schedule: CostSchedule,
        multiplier: Decimal, completed: dict[str, CostComponentResult],
    ) -> CostComponentResult:
        price = as_decimal(leg.execution_price, "execution_price")
        quantity = as_decimal(leg.execution_quantity, "execution_quantity")
        with localcontext(INTERNAL_DECIMAL_CONTEXT):
            if rule.basis is CostBasis.FIXED:
                input_amount, unrounded = Decimal("1"), rule.rate
            elif rule.basis is CostBasis.PER_UNIT:
                input_amount, unrounded = quantity, rule.rate * quantity
            elif rule.basis is CostBasis.NOTIONAL:
                input_amount = price * quantity * multiplier
                unrounded = rule.rate * input_amount
            else:
                input_amount = sum((completed[key].amount for key in rule.dependency_ids), Decimal("0"))
                unrounded = rule.rate * input_amount
            capped = max(unrounded, rule.minimum) if rule.minimum is not None else unrounded
            capped = min(capped, rule.maximum) if rule.maximum is not None else capped
            amount = capped.quantize(rule.rounding_quantum, rounding={"ROUND_HALF_EVEN": "ROUND_HALF_EVEN"}[rule.rounding_mode])
        return CostComponentResult(
            rule.component_id, leg.event_key, rule.basis, schedule.schedule_id,
            schedule.version, schedule.fingerprint, input_amount, rule.rate,
            unrounded, amount,
        )
