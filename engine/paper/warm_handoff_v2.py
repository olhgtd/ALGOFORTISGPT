"""Warm, non-authorizing Paper handoff after RiskGate approval."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from engine.orders.contracts_v2 import ApprovedOrder, RunMode
from engine.paper.execution_adapter_v2 import PaperExecutionAdapterV2
from engine.paper.fill_simulator_v2 import FillSimulationPolicy, QuoteSnapshot, SimulatedExecutionResult


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware datetime")
    return value


@dataclass(frozen=True, slots=True)
class WarmPaperContext:
    context_id: str
    instrument_mapping_ref: str
    serializer_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_id", _text(self.context_id, "context_id"))
        object.__setattr__(self, "instrument_mapping_ref", _text(self.instrument_mapping_ref, "instrument_mapping_ref"))
        object.__setattr__(self, "serializer_ref", _text(self.serializer_ref, "serializer_ref"))


class WarmPaperHandoff:
    def __init__(self, execution_adapter: PaperExecutionAdapterV2) -> None:
        if not isinstance(execution_adapter, PaperExecutionAdapterV2):
            raise TypeError("execution_adapter must be PaperExecutionAdapterV2")
        self._execution_adapter = execution_adapter
        self._claimed_client_order_ids: set[str] = set()
        self._handoff_count = 0

    @property
    def handoff_count(self) -> int:
        return self._handoff_count

    def prepare_static(self, *, instrument_mapping_ref: str, serializer_ref: str) -> WarmPaperContext:
        mapping = _text(instrument_mapping_ref, "instrument_mapping_ref")
        serializer = _text(serializer_ref, "serializer_ref")
        context_id = f"paper-warm:{mapping}:{serializer}"
        return WarmPaperContext(context_id, mapping, serializer)

    def handoff(
        self,
        approved_order: ApprovedOrder,
        context: WarmPaperContext,
        quote: QuoteSnapshot,
        policy: FillSimulationPolicy,
        *,
        now: datetime,
    ) -> SimulatedExecutionResult:
        if not isinstance(approved_order, ApprovedOrder):
            raise TypeError("approved_order must be a RiskGate-minted ApprovedOrder")
        if approved_order.run_mode is not RunMode.PAPER:
            raise ValueError("warm handoff accepts PAPER ApprovedOrder only")
        if not isinstance(context, WarmPaperContext):
            raise TypeError("context must be WarmPaperContext")
        current = _aware(now, "now")
        if current >= approved_order.expires_at:
            raise ValueError("ApprovedOrder capability expired before handoff")
        if approved_order.client_order_id in self._claimed_client_order_ids:
            raise ValueError("ApprovedOrder already handed off")
        self._claimed_client_order_ids.add(approved_order.client_order_id)
        self._handoff_count += 1
        return self._execution_adapter.execute(
            approved_order,
            quote,
            policy,
            now=current,
        )


__all__ = ["WarmPaperContext", "WarmPaperHandoff"]
