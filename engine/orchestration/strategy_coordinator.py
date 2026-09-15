"""Phase 5 Slice 4C-3 — Provider-neutral live strategy coordinator.

Connects:
completed underlying live BoundBarEvent batch
-> MarketDataCoordinator
-> deterministic EvaluationRequest batch
-> strategy safe_generate_signal(mode="live")
-> SignalIntake
-> SignalIntent
-> LivePaperCoordinator

Guarantees:
- Exact frozen constructor accepting Sequence[StrategyBinding].
- Public return type is tuple[CoordinatorEntryResult, ...]
- Authoritative MarketDataCoordinator instance received via injection.
- Session-aware evaluation expiry boundary via compute_next_evaluation_boundary:
  * Decision time < session close: capped at regular session close.
  * Decision time >= session close: fails closed.
- Strict bounded runtime state: O(N_owners + N_streams * retention_limit) memory over arbitrary duration.
- Forwarding of market-time boundaries and feed-state changes.
- Exact SubscriptionOwnerKey(strategy_id, strategy_version) resolution and policy isolation.
- Fail-closed handling for missing / mismatched option selection policies.
- Run-local strategy halt isolation: one failing strategy does not halt unrelated strategies.
- Selection timestamp uses authoritative decision time.
- Zero wall-clock market authority.
- No direct broker, risk gate, or option selector duplication.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
import re

from engine.audit.model import recorded_at_utc_now
from engine.audit.log import sanitize_error_class
from engine.backtest.engine import BarEvent
from engine.strategy.exceptions import safe_generate_signal
from engine.data.feeds.live_feed import FeedConnectionState, SubscriptionOwnerKey
from engine.audit.sinks import redact_text
from engine.market.data import (
    BoundBarEvent,
    EvaluationRequest,
    MarketDataCoordinator,
    MarketDataView,
    StreamKey,
)
from engine.market.profile import MarketSessionBoundary
from engine.core.numeric import as_decimal
from engine.options.policy import OptionSelectionPolicy
from engine.orchestration.entry_pipeline import StrategyBinding
from engine.paper.coordinator import (
    CoordinatorEntryResult,
    CoordinatorOutcome,
    LivePaperCoordinator,
)
from engine.portfolio.model import InstrumentIdentity
from engine.orchestration.signal_intake import SignalIntake, SignalIntakeContext, SignalIntent
from engine.strategy.base import Signal
from engine.safety.strategy_halt import StrategyHaltError

__all__ = [
    "compute_next_evaluation_boundary",
    "LiveStrategyOutcome",
    "LiveStrategyResult",
    "LiveStrategyCoordinator",
]

logger = logging.getLogger(__name__)

_TIMEFRAME_RE = re.compile(r"^(\d+)(m|h|d)$")


def _timeframe_duration(timeframe: str) -> timedelta:
    match = _TIMEFRAME_RE.fullmatch(timeframe)
    if match is None:
        raise ValueError(f"invalid timeframe: {timeframe!r}")
    quantity, unit = match.groups()
    amount = int(quantity)
    if amount <= 0:
        raise ValueError("timeframe duration must be positive")
    return timedelta(minutes=amount * {"m": 1, "h": 60, "d": 1_440}[unit])


def compute_next_evaluation_boundary(
    decision_time: datetime,
    timeframe: str,
    session_boundary: MarketSessionBoundary,
) -> datetime:
    """Compute the deterministic next strategy evaluation boundary timestamp.

    - Timezone-aware
    - Session-aware:
      * decision_time < session close: caps at regular session close if nominal next boundary exceeds it.
      * decision_time >= session close: fails closed (cannot schedule pending evaluation in closed session).
    - Strictly > decision_time when successful.
    - No wall-clock authority.
    """
    if not isinstance(decision_time, datetime) or decision_time.tzinfo is None:
        raise ValueError("decision_time must be a timezone-aware datetime")
    if not isinstance(session_boundary, MarketSessionBoundary):
        raise TypeError("session_boundary must be a MarketSessionBoundary")

    duration = _timeframe_duration(timeframe)
    dt_exchange = session_boundary.exchange_timestamp(decision_time)
    session_date = dt_exchange.date()
    close_time = session_boundary.profile.regular_session_close
    session_close_dt = datetime.combine(
        session_date,
        close_time,
        tzinfo=session_boundary.profile.timezone,
    )

    if dt_exchange >= session_close_dt:
        raise ValueError(
            f"decision_time {decision_time.isoformat()!r} is at or after regular session close "
            f"{session_close_dt.isoformat()!r}; cannot compute pending evaluation boundary in closed session"
        )

    nominal_next = dt_exchange + duration
    next_boundary = min(nominal_next, session_close_dt)

    return next_boundary.astimezone(decision_time.tzinfo)


# ======================================================================
# 1. Result Data Types (Provided for compatibility & introspection)
# ======================================================================


class LiveStrategyOutcome(str, Enum):
    """Outcome of processing an EvaluationRequest for one strategy."""

    HOLD = "HOLD"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    STRATEGY_HALTED = "STRATEGY_HALTED"


@dataclass(frozen=True)
class LiveStrategyResult:
    """Immutable detailed result of evaluating one strategy against an EvaluationRequest."""

    strategy_id: str
    strategy_version: str
    evaluation_timestamp: datetime
    stream: StreamKey
    outcome: LiveStrategyOutcome
    signal: Signal | None = None
    intent: SignalIntent | None = None
    coordinator_result: CoordinatorEntryResult | None = None
    rejection_reason: str | None = None
    halt_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(self.strategy_version, str) or not self.strategy_version.strip():
            raise ValueError("strategy_version must be a non-empty string")
        if not isinstance(self.evaluation_timestamp, datetime) or self.evaluation_timestamp.tzinfo is None:
            raise ValueError("evaluation_timestamp must be a timezone-aware datetime")
        if not isinstance(self.stream, StreamKey):
            raise TypeError("stream must be a StreamKey")
        if not isinstance(self.outcome, LiveStrategyOutcome):
            raise TypeError("outcome must be a LiveStrategyOutcome")
        if self.signal is not None and not isinstance(self.signal, Signal):
            raise TypeError("signal when provided must be a Signal")
        if self.intent is not None and not isinstance(self.intent, SignalIntent):
            raise TypeError("intent when provided must be a SignalIntent")
        if self.coordinator_result is not None and not isinstance(self.coordinator_result, CoordinatorEntryResult):
            raise TypeError("coordinator_result when provided must be a CoordinatorEntryResult")


# ======================================================================
# 2. Strategy Adapter for Safe Live Execution
# ======================================================================


@dataclass(frozen=True)
class _StrategyAdapter:
    """Bind strategy identity for safe_generate_signal audit trail."""

    strategy: object
    id: str
    interface_version: str

    def generate_signal(self, data: Any, state: Any) -> Signal:
        return self.strategy.generate_signal(data, state)


# ======================================================================
# 3. LiveStrategyCoordinator
# ======================================================================


class LiveStrategyCoordinator:
    """Provider-neutral live strategy coordinator.

    Owns the deterministic boundary from completed underlying live BoundBarEvents
    into MarketDataCoordinator, safe strategy evaluation, SignalIntake, and
    LivePaperCoordinator.
    """

    def __init__(
        self,
        market_coordinator: MarketDataCoordinator,
        strategy_bindings: Sequence[StrategyBinding],
        paper_coordinator: LivePaperCoordinator,
        option_selection_policies: Mapping[SubscriptionOwnerKey, OptionSelectionPolicy],
        signal_intake: SignalIntake | None = None,
        session_boundary: MarketSessionBoundary | None = None,
        persistence_store: Any | None = None,
        initial_strategy_states: Mapping[SubscriptionOwnerKey, Any] | None = None,
        latest_evaluated_decision_times: Mapping[SubscriptionOwnerKey, datetime | None] | None = None,
        *,
        evaluation_observer: Callable[[Mapping[str, Any]], None] | None = None,
        initial_halted_owners: Sequence[SubscriptionOwnerKey] | None = None,
        strategy_halt_bridge: Callable[[str, str], None] | None = None,
        strategy_exception_observer: Callable[[str, str], object] | None = None,
    ) -> None:
        if not isinstance(market_coordinator, MarketDataCoordinator):
            raise TypeError("market_coordinator must be a MarketDataCoordinator instance")
        if not isinstance(paper_coordinator, LivePaperCoordinator):
            raise TypeError("paper_coordinator must be a LivePaperCoordinator instance")
        if not isinstance(strategy_bindings, Sequence) or isinstance(strategy_bindings, (str, bytes)):
            raise TypeError("strategy_bindings must be a Sequence of StrategyBinding")
        if not isinstance(option_selection_policies, Mapping):
            raise TypeError("option_selection_policies must be a Mapping")

        # Validate each binding and normalize by SubscriptionOwnerKey
        normalized_bindings: dict[SubscriptionOwnerKey, StrategyBinding] = {}
        for binding in strategy_bindings:
            if not isinstance(binding, StrategyBinding):
                raise TypeError("strategy_bindings elements must be StrategyBinding instances")
            owner = SubscriptionOwnerKey(
                binding.requirements.strategy_id,
                binding.requirements.strategy_version,
            )
            if owner in normalized_bindings:
                raise ValueError(f"duplicate StrategyBinding for owner {owner!r}")
            normalized_bindings[owner] = binding

        if not normalized_bindings:
            raise ValueError("strategy_bindings must contain at least one StrategyBinding")

        # Validate option policies mapping
        normalized_policies: dict[SubscriptionOwnerKey, OptionSelectionPolicy] = {}
        for owner, policy in option_selection_policies.items():
            if not isinstance(owner, SubscriptionOwnerKey):
                raise TypeError("option_selection_policies keys must be SubscriptionOwnerKey instances")
            if not isinstance(policy, OptionSelectionPolicy):
                raise TypeError("option_selection_policies values must be OptionSelectionPolicy instances")
            if (policy.strategy_id, policy.strategy_version) != (owner.strategy_id, owner.strategy_version):
                raise ValueError(
                    f"OptionSelectionPolicy ({policy.strategy_id}, {policy.strategy_version}) "
                    f"does not match SubscriptionOwnerKey {owner!r}"
                )
            normalized_policies[owner] = policy

        # Validate SignalIntake injection
        if signal_intake is None:
            self._intake = SignalIntake()
        else:
            if not isinstance(signal_intake, SignalIntake):
                raise TypeError("signal_intake must be a SignalIntake instance")
            self._intake = signal_intake

        # Retain references
        self._market_coordinator = market_coordinator
        self._bindings = MappingProxyType(normalized_bindings)
        self._option_policies = MappingProxyType(normalized_policies)
        self._paper_coordinator = paper_coordinator
        self._session_boundary = session_boundary
        self._persistence_store = persistence_store

        # Phase 6 Slice 4 / ADR §123.2: optional observational Q90 evaluation
        # sink. Purely diagnostic: observer failures never affect trading,
        # orders, reservations or the audit journal (§14 failure semantics).
        if evaluation_observer is not None and not callable(evaluation_observer):
            raise TypeError("evaluation_observer must be callable or None")
        self._evaluation_observer = evaluation_observer

        # Phase 8 / ADR §128.8: durable per-strategy halt latch.
        #
        # ``initial_halted_owners`` hydrates the durable latch BEFORE any
        # strategy evaluation can occur (constructor-time, so a restarted
        # process gates halted strategies from its very first decision).
        # Hydration never silently clears a halt; owners without a current
        # binding are retained (fail-safe) and keep blocking re-registration.
        #
        # ``strategy_halt_bridge`` is the AUTHORITATIVE Phase-8 bridge
        # (§128.10): invoked after each NEW halt addition with the owner's
        # (strategy_id, strategy_version).  Unlike the observational Q90
        # sink, bridge failures are authoritative durability failures and
        # PROPAGATE (fail closed) — they must never be swallowed.
        if initial_halted_owners is not None:
            hydrated: set[SubscriptionOwnerKey] = set()
            for owner in initial_halted_owners:
                if not isinstance(owner, SubscriptionOwnerKey):
                    raise TypeError("initial_halted_owners elements must be SubscriptionOwnerKey")
                hydrated.add(owner)
        else:
            hydrated = set()
        if strategy_halt_bridge is not None and not callable(strategy_halt_bridge):
            raise TypeError("strategy_halt_bridge must be callable or None")
        self._strategy_halt_bridge = strategy_halt_bridge
        self._initial_halted_owners = hydrated

        # Phase 8 P1 (§128.1/§128.3): optional escalation bridge invoked for
        # EVERY strategy-owned callback exception (Rule-7 StrategyHaltError).
        # The canonical Phase-8 controller owns the per-session error count
        # and the strategy_error_kill_threshold arithmetic; this coordinator
        # keeps NO private counter.  Like the halt bridge, escalation failures
        # are authoritative safety failures and PROPAGATE (fail closed).
        if strategy_exception_observer is not None and not callable(strategy_exception_observer):
            raise TypeError("strategy_exception_observer must be callable or None")
        self._strategy_exception_observer = strategy_exception_observer

        # Compute max minimum_history per stream for bounded retention
        max_history: dict[StreamKey, int] = {}
        for binding in normalized_bindings.values():
            for sub in binding.requirements.subscriptions:
                curr = max_history.get(sub.stream, 1)
                max_history[sub.stream] = max(curr, sub.minimum_history)
        self._max_history_per_stream = MappingProxyType(max_history)

        # Runtime state per strategy owner: O(N_owners) bound
        strategy_states: dict[SubscriptionOwnerKey, dict] = {}
        decision_times: dict[SubscriptionOwnerKey, datetime] = {}

        for owner, binding in normalized_bindings.items():
            if initial_strategy_states is not None and owner in initial_strategy_states:
                init_val = initial_strategy_states[owner]
                if hasattr(init_val, "state") and isinstance(init_val.state, dict):
                    strategy_states[owner] = deepcopy(init_val.state)
                elif isinstance(init_val, dict):
                    strategy_states[owner] = deepcopy(init_val)
                else:
                    raise TypeError(f"Invalid initial strategy state for owner {owner!r}: {type(init_val).__name__}")

                if hasattr(init_val, "last_evaluated_decision_time") and init_val.last_evaluated_decision_time is not None:
                    decision_times[owner] = init_val.last_evaluated_decision_time
            else:
                strategy_states[owner] = deepcopy(binding.strategy.initial_state())

        if latest_evaluated_decision_times is not None:
            for owner, ldt in latest_evaluated_decision_times.items():
                if ldt is not None:
                    decision_times[owner] = ldt

        self._strategy_states = strategy_states
        self._latest_evaluated_decision_time = decision_times
        # Phase 8 / ADR §128.8: durable latch hydration happens here, BEFORE
        # any strategy evaluation/submission can become eligible.
        self._halted_owners: set[SubscriptionOwnerKey] = set(self._initial_halted_owners)

        # Bounded event history per stream: O(N_streams * retention_limit) bound
        self._stream_history: dict[StreamKey, list[BoundBarEvent]] = {}
        # Bounded recent bars cache for deduplication/conflict detection: O(N_streams * retention_limit) bound
        self._recent_bars: dict[StreamKey, dict[datetime, BarEvent]] = {}
        # Finalized watermark per stream: O(N_streams) bound
        self._latest_bar_timestamp: dict[StreamKey, datetime] = {}

    # ------------------------------------------------------------------
    # Phase 8 / ADR §128.6/§128.8 — durable halt latch introspection
    # ------------------------------------------------------------------

    @property
    def halted_owners(self) -> frozenset[SubscriptionOwnerKey]:
        """Runtime per-strategy gating authority (canonical owner set)."""
        return frozenset(self._halted_owners)

    def is_owner_halted(self, strategy_id: str, strategy_version: str) -> bool:
        return SubscriptionOwnerKey(strategy_id, strategy_version) in self._halted_owners

    def clear_strategy_halt(
        self, strategy_id: str, strategy_version: str
    ) -> bool:
        """Mechanically clear ONE strategy latch after gated operator approval.

        Callers must route approval through the Phase-8 controller
        (:meth:`Phase8SafetyController.request_strategy_resume`, §128.6);
        this method performs only the runtime-authority removal and never
        touches the global kill switch or other owners' latches.
        """
        owner = SubscriptionOwnerKey(strategy_id, strategy_version)
        if owner not in self._halted_owners:
            return False
        self._halted_owners.discard(owner)
        return True

    # ------------------------------------------------------------------
    # Public Batch Processing API
    # ------------------------------------------------------------------

    def process_bar_events(
        self,
        events: Sequence[BoundBarEvent],
    ) -> tuple[CoordinatorEntryResult, ...]:
        """Process a canonical batch of completed BoundBarEvents.

        Drives MarketDataCoordinator, evaluates ready strategies in canonical order,
        processes signals through SignalIntake, and routes non-HOLD intents to
        LivePaperCoordinator.
        """
        if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
            raise TypeError("events must be a Sequence of BoundBarEvent")
        for e in events:
            if not isinstance(e, BoundBarEvent):
                raise TypeError(f"expected BoundBarEvent, got {type(e).__name__}")

        if not events:
            return ()

        # Validate and deduplicate incoming events with bounded state
        new_valid_events: list[BoundBarEvent] = []
        for event in events:
            stream = event.stream
            bar_ts = event.bar.timestamp
            stream_recent = self._recent_bars.setdefault(stream, {})
            latest_ts = self._latest_bar_timestamp.get(stream)

            # 1. Check if bar is within recent retention window
            if bar_ts in stream_recent:
                existing = stream_recent[bar_ts]
                if existing != event.bar:
                    raise ValueError(
                        f"conflicting BarEvent for stream {stream!r} at {bar_ts!r}"
                    )
                # Exact duplicate within recent window -> idempotent skip
                continue

            # 2. Check for stale / out-of-order ancient replay
            history = self._stream_history.get(stream, [])
            if history:
                oldest_retained_ts = history[0].bar.timestamp
                if bar_ts < oldest_retained_ts:
                    raise ValueError(
                        f"stale/out-of-retention BarEvent for stream {stream!r} at {bar_ts!r} "
                        f"is older than oldest retained bar at {oldest_retained_ts!r}"
                    )
            elif latest_ts is not None and bar_ts < latest_ts:
                raise ValueError(
                    f"out-of-order BarEvent for stream {stream!r} at {bar_ts!r} "
                    f"is older than latest seen bar at {latest_ts!r}"
                )

            # 3. Accept valid new bar
            stream_recent[bar_ts] = event.bar
            if latest_ts is None or bar_ts > latest_ts:
                self._latest_bar_timestamp[stream] = bar_ts

            # Bound stream_recent size to retention limit
            max_needed = self._max_history_per_stream.get(stream, 50)
            retention_limit = max(max_needed * 2, 50)
            if len(stream_recent) > retention_limit:
                excess = len(stream_recent) - retention_limit
                for old_key in sorted(stream_recent.keys())[:excess]:
                    del stream_recent[old_key]

            new_valid_events.append(event)

        if not new_valid_events:
            return ()

        # Append to bounded stream histories
        for event in new_valid_events:
            stream = event.stream
            history = self._stream_history.setdefault(stream, [])
            history.append(event)
            max_needed = self._max_history_per_stream.get(stream, 50)
            retention_limit = max(max_needed * 2, 50)
            if len(history) > retention_limit:
                self._stream_history[stream] = history[-retention_limit:]

        # Collect bounded retained events across streams for MarketDataCoordinator
        active_events = [
            bar_event
            for stream_bars in self._stream_history.values()
            for bar_event in stream_bars
        ]

        requests = self._market_coordinator.process(active_events)

        entry_results: list[CoordinatorEntryResult] = []

        for request in requests:
            owner = SubscriptionOwnerKey(
                request.requirements.strategy_id,
                request.requirements.strategy_version,
            )
            dt = request.data.decision_time

            # Monotonic evaluation tracking: O(N_owners) bound
            last_evaluated_dt = self._latest_evaluated_decision_time.get(owner)
            if last_evaluated_dt is not None and dt <= last_evaluated_dt:
                continue
            self._latest_evaluated_decision_time[owner] = dt

            res = self._evaluate_request(request)
            if res is not None:
                entry_results.append(res)

        return tuple(entry_results)

    def process_bar_event(
        self,
        event: BoundBarEvent,
    ) -> tuple[CoordinatorEntryResult, ...]:
        """Single-event convenience helper; strictly delegates to process_bar_events."""
        return self.process_bar_events((event,))

    # ------------------------------------------------------------------
    # Strategy Evaluation & Boundary Forwarding
    # ------------------------------------------------------------------

    def on_market_time_boundary(
        self,
        boundary_timestamp: datetime,
    ) -> tuple[str, ...]:
        """Forward authoritative strategy evaluation boundaries to expire pending bar-bound attempts."""
        if not isinstance(boundary_timestamp, datetime) or boundary_timestamp.tzinfo is None:
            raise ValueError("boundary_timestamp must be a timezone-aware datetime")

        expired: set[str] = set()
        # Canonical iteration order across bindings
        for owner in sorted(self._bindings.keys(), key=lambda o: (o.strategy_id, o.strategy_version)):
            binding = self._bindings[owner]
            tf = binding.signal_source_stream.timeframe
            exp_ids = self._paper_coordinator.on_strategy_evaluation_boundary(
                strategy_id=owner.strategy_id,
                strategy_version=owner.strategy_version,
                timeframe=tf,
                boundary_timestamp=boundary_timestamp,
            )
            expired.update(exp_ids)

        return tuple(sorted(expired))

    def on_feed_state_change(
        self,
        state: FeedConnectionState,
    ) -> tuple[CoordinatorEntryResult, ...]:
        """Forward feed state changes (DISCONNECTED / RECONNECTING / CONNECTED) to LivePaperCoordinator."""
        if not isinstance(state, FeedConnectionState):
            raise TypeError("state must be a FeedConnectionState")
        return self._paper_coordinator.on_feed_state_change(state)

    # ------------------------------------------------------------------
    # Internal Evaluation & Routing
    # ------------------------------------------------------------------

    def _evaluate_request(
        self,
        request: EvaluationRequest,
    ) -> CoordinatorEntryResult | None:
        """Evaluate one ready EvaluationRequest and route resulting signal.

        Phase 6 Slice 4 (§123.2): every ACTUAL evaluation produces exactly one
        Q90 observational record via the optional evaluation_observer —
        including HOLD, rejected downstream actions, and the strategy-halt
        outcome. A previously-halted owner short-circuit performs no new
        evaluation and therefore fabricates no record.
        """
        sid = request.requirements.strategy_id
        sver = request.requirements.strategy_version
        owner = SubscriptionOwnerKey(sid, sver)
        dt = request.data.decision_time

        binding = self._bindings.get(owner)
        if binding is None:
            raise KeyError(f"unregistered strategy binding for owner {owner!r}")

        # Check if strategy was previously halted. No new evaluation occurs on
        # this path, so no Q90 evaluation record is fabricated.
        if owner in self._halted_owners:
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"halted:{sid}:{sver}:{dt.isoformat()}",
                rejection_reason="previously_halted",
            )

        result, eval_signal, halt_error = self._evaluate_request_body(request, binding)
        self._emit_evaluation_record(
            request,
            binding,
            signal=eval_signal,
            halt_error=halt_error,
            result=result,
        )
        return result

    def _emit_evaluation_record(
        self,
        request: EvaluationRequest,
        binding: StrategyBinding,
        *,
        signal: Signal | None,
        halt_error: StrategyHaltError | None,
        result: CoordinatorEntryResult | None,
    ) -> None:
        """Emit ONE bounded Q90 evaluation record; never affects trading."""
        observer = self._evaluation_observer
        if observer is None:
            return
        try:
            source_stream = binding.signal_source_stream
            reason_text = None
            action = None
            confidence = None
            error_class = None
            if halt_error is not None:
                outcome = "strategy_halted"
                error_class = sanitize_error_class(halt_error)
            else:
                assert signal is not None  # noqa: S101 - structural invariant
                action = signal.action
                confidence = signal.confidence
                raw_reason = signal.metadata.get("reason")
                if raw_reason is not None:
                    # §123.7(2): validated/length-bounded/character-sanitized/
                    # redaction-filtered DESCRIPTIVE data only. Arbitrary
                    # Signal.metadata is never serialized.
                    reason_text = redact_text(raw_reason, max_len=512) or None
                if action == "HOLD":
                    outcome = "hold"
                elif result is None:
                    outcome = "hold"
                elif isinstance(result, CoordinatorEntryResult):
                    if result.outcome == CoordinatorOutcome.SUBMITTED:
                        outcome = "forwarded"
                    else:
                        bounded_reason = redact_text(
                            result.rejection_reason or result.outcome.value, max_len=128
                        )
                        outcome = f"rejected:{bounded_reason}"
                else:  # defensive: unexpected result shape stays bounded
                    outcome = f"rejected:{redact_text(type(result).__name__, max_len=64)}"
            record = {
                "record_kind": "q90_strategy_evaluation",
                "strategy_id": request.requirements.strategy_id,
                "strategy_version": request.requirements.strategy_version,
                "interface_version": getattr(binding.strategy, "interface_version", None),
                "instrument": source_stream.identity.instrument,
                "timeframe": source_stream.timeframe,
                "decision_time": request.data.decision_time.isoformat(),
                "action": action,
                "confidence": confidence,
                "reason": reason_text,
                "outcome": outcome,
                "error_class": error_class,
                "recorded_at_utc": recorded_at_utc_now().isoformat(),
            }
            try:
                observer(record)
            except Exception as sink_exc:  # noqa: BLE001 - §14 diagnostic-only failure
                logger.critical(
                    "Q90 strategy-evaluation sink failed without recording; "
                    "trading state unaffected; strategy_id=%r cause=%r",
                    request.requirements.strategy_id,
                    sink_exc,
                )
        except Exception as exc:  # noqa: BLE001 - record construction boundary
            logger.critical(
                "Q90 evaluation-record construction failed; trading state unaffected; "
                "strategy_id=%r cause=%r",
                request.requirements.strategy_id,
                exc,
            )

    def _evaluate_request_body(
        self,
        request: EvaluationRequest,
        binding: StrategyBinding,
    ) -> tuple[CoordinatorEntryResult | None, Signal | None, StrategyHaltError | None]:
        """Run one strategy evaluation and boundary forwarding.

        Returns ``(entry_result_or_none, evaluated_signal_or_none,
        halt_error_or_none)`` so the caller can emit exactly ONE Q90 record.
        """
        sid = request.requirements.strategy_id
        sver = request.requirements.strategy_version
        owner = SubscriptionOwnerKey(sid, sver)
        dt = request.data.decision_time

        source_stream = binding.signal_source_stream

        # Rule-7 error/audit metadata retains the real generator interface
        # version.  Semantic ownership remains the requirements-derived owner.
        adapter = _StrategyAdapter(binding.strategy, sid, binding.strategy.interface_version)
        data = self._format_strategy_data(binding, request.data)
        state = self._strategy_states[owner]

        # Evaluate strategy safely in live mode
        try:
            signal = safe_generate_signal(adapter, data, state, mode="live")
        except StrategyHaltError as error:
            newly_halted = owner not in self._halted_owners
            self._halted_owners.add(owner)
            if newly_halted and self._strategy_halt_bridge is not None:
                # §128.10 authoritative bridge: durability failures here
                # propagate (fail closed) — never swallowed.
                self._strategy_halt_bridge(sid, sver)
            if self._strategy_exception_observer is not None:
                # Phase 8 P1 (§128.1/§128.3): canonical ERROR evidence +
                # per-session error count + strategy_error_kill_threshold
                # arithmetic live in the Phase-8 controller.  Escalation
                # failures propagate (fail closed) — never swallowed.
                self._strategy_exception_observer(sid, sver)
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"halted:{sid}:{sver}:{dt.isoformat()}",
                rejection_reason=error.reason,
            ), None, error

        if not isinstance(signal, Signal):
            raise TypeError(f"strategy generate_signal must return Signal, got {type(signal).__name__}")

        # HOLD produces no option subscription or broker interaction
        if signal.action == "HOLD":
            if self._persistence_store is not None:
                self._persistence_store.save_strategy_state(
                    strategy_id=sid,
                    strategy_version=sver,
                    state=state,
                    last_evaluated_decision_time=dt,
                )
            return None, signal, None

        # Actionable signal (BUY / SELL / EXIT) -> SignalIntake
        source_bar = request.data.latest(source_stream)
        if source_bar is None:
            if self._persistence_store is not None:
                self._persistence_store.save_strategy_state(
                    strategy_id=sid,
                    strategy_version=sver,
                    state=state,
                    last_evaluated_decision_time=dt,
                )
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"unresolved:{sid}:{sver}:{source_stream.identity.instrument}:{dt.isoformat()}",
                rejection_reason="missing_source_bar_evidence",
            ), signal, None

        ctx = SignalIntakeContext(
            source_event=source_bar,
            strategy_id=sid,
            strategy_version=sver,
        )
        intent = self._intake.intake(signal, ctx)

        if intent is None:
            if self._persistence_store is not None:
                self._persistence_store.save_strategy_state(
                    strategy_id=sid,
                    strategy_version=sver,
                    state=state,
                    last_evaluated_decision_time=dt,
                )
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"unresolved:{sid}:{sver}:{source_stream.identity.instrument}:{dt.isoformat()}",
                rejection_reason="signal_intake_rejected",
            ), signal, None

        # Option selection policy lookup by exact SubscriptionOwnerKey
        policy = self._option_policies.get(owner)
        if policy is None:
            if self._persistence_store is not None:
                self._persistence_store.save_strategy_state(
                    strategy_id=sid,
                    strategy_version=sver,
                    state=state,
                    last_evaluated_decision_time=dt,
                )
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"unresolved:{sid}:{sver}:{intent.symbol}:{dt.isoformat()}",
                rejection_reason="missing_option_selection_policy",
            ), signal, None

        # Underlying price from source bar close
        underlying_price = as_decimal(source_bar.close, "underlying_price")
        selection_timestamp = dt
        try:
            expiry_boundary = compute_next_evaluation_boundary(
                decision_time=dt,
                timeframe=source_stream.timeframe,
                session_boundary=self._session_boundary,
            )
        except ValueError as exc:
            if self._persistence_store is not None:
                self._persistence_store.save_strategy_state(
                    strategy_id=sid,
                    strategy_version=sver,
                    state=state,
                    last_evaluated_decision_time=dt,
                )
            return CoordinatorEntryResult(
                outcome=CoordinatorOutcome.REJECTED,
                intent_id=f"unresolved:{sid}:{sver}:{intent.symbol}:{dt.isoformat()}",
                rejection_reason=f"session_boundary_rejected:{exc}",
            ), signal, None

        # Route to LivePaperCoordinator with coupled strategy state
        coord_res = self._paper_coordinator.process_signal(
            intent=intent,
            policy=policy,
            underlying_price=underlying_price,
            selection_timestamp=selection_timestamp,
            expiry_boundary=expiry_boundary,
            strategy_state=deepcopy(state),
            evaluation_decision_time=dt,
        )

        if coord_res.outcome != CoordinatorOutcome.SUBMITTED and self._persistence_store is not None:
            self._persistence_store.save_strategy_state(
                strategy_id=sid,
                strategy_version=sver,
                state=state,
                last_evaluated_decision_time=dt,
            )

        return coord_res, signal, None

    # ------------------------------------------------------------------
    # Strategy Data Formatting Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _format_strategy_data(binding: StrategyBinding, view: MarketDataView) -> Any:
        """Format MarketDataView into DataFrame mapping if single instrument, or return view."""
        instruments = {stream.identity for stream in view.streams}
        if len(instruments) != 1:
            return view
        try:
            import pandas as pd
        except ImportError:
            return view

        output = {}
        for stream, evidence in view.streams.items():
            output[stream.timeframe] = pd.DataFrame(
                [
                    {
                        "timestamp": bar.timestamp,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "is_synthetic": bar.is_synthetic,
                    }
                    for bar in evidence.history
                ]
            )
        return output
