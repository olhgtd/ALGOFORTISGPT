"""Phase 5 Slice 2 — PaperTradingRunner: deterministic replay/core orchestration.

Source-independent paper trading core that consumes BoundBarEvents,
delegates to MarketDataCoordinator for canonical ordering/readiness,
evaluates strategies via safe_generate_signal(mode="live"),
and collects immutable Signal/SignalIntent/halt evidence.

This is replay infrastructure (TEST / REPLAY / DEBUG / DETERMINISTIC
VALIDATION).  It does NOT represent operational live paper trading.
Result is always SLICE_2_NON_PROMOTION_EVIDENCE.

Owner-approved scope (BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md §99):
- Replay source orchestration
- Event conversion/binding
- Canonical ordering delegation to MarketDataCoordinator
- EvaluationRequest consumption
- Strategy evaluation
- Signal/intent evidence collection
- Per-strategy exception isolation via run-local halt tracker

Stops before:
- PaperFillAdapter / simulated broker
- Orders / fills / RiskGate / execution
- Portfolio / accounting / MTM
- Protective exit execution
- Option Selector
- LiveDataFeed / WebSocket
- SQLite persistence / safety / D16 logging
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable, Iterable, Mapping

from engine.backtest.engine import BarEvent
from engine.strategy.exceptions import safe_generate_signal
from engine.safety.strategy_halt import StrategyHaltError
from engine.data.feeds.replay_feed import HistoricalReplayFeed
from engine.market.data import (
    BoundBarEvent,
    DataReadiness,
    EvaluationRequest,
    MarketDataCoordinator,
    MarketDataView,
    StreamKey,
)
from engine.orchestration.entry_pipeline import StrategyBinding
from engine.orchestration.signal_intake import SignalIntake, SignalIntakeContext
from engine.strategy.base import Signal


# ---------------------------------------------------------------------------
# Evidence types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategySignalEvidence:
    """One strategy's signal output from one EvaluationRequest."""

    strategy_id: str
    strategy_version: str
    decision_time: datetime
    signal: Signal
    intent: object | None  # SignalIntent | None


@dataclass(frozen=True)
class StrategyHaltEvidence:
    """Per-strategy halt record.  Does NOT imply runner-level halt."""

    strategy_id: str
    reason: str
    halted_at_decision_time: datetime


@dataclass(frozen=True)
class PaperTradingResult:
    """Immutable result from one PaperTradingRunner replay.

    This is replay/core infrastructure evidence only.  It does NOT represent
    operational paper trading output.  Always SLICE_2_NON_PROMOTION_EVIDENCE.
    """

    run_id: str
    status: str = "completed"
    processed_event_count: int = 0
    evaluation_request_count: int = 0
    signals: tuple[StrategySignalEvidence, ...] = ()
    halts: tuple[StrategyHaltEvidence, ...] = ()
    first_market_timestamp: datetime | None = None
    last_market_timestamp: datetime | None = None
    non_promotion_evidence: bool = True


# ---------------------------------------------------------------------------
# Run-local halt isolation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RunLocalHaltTracker:
    """Immutable session-scoped halt facade.

    Wraps per-run halt state so that one independent replay run does not
    inherit another run's local halt state.  Does NOT modify or clear the
    module-level ``strategy_halt._halted`` registry.
    """

    _halted_ids: tuple[str, ...] = ()

    def is_halted(self, strategy_id: str) -> bool:
        return strategy_id in self._halted_ids

    def with_halt(self, strategy_id: str) -> _RunLocalHaltTracker:
        if strategy_id in self._halted_ids:
            return self
        return replace(self, _halted_ids=(*self._halted_ids, strategy_id))


# ---------------------------------------------------------------------------
# PaperTradingRunner
# ---------------------------------------------------------------------------


class PaperTradingRunner:
    """Source-independent paper trading core.

    Consumes BoundBarEvents from any source (replay or future live),
    delegates canonical ordering and readiness to MarketDataCoordinator,
    evaluates strategies via safe_generate_signal(mode="live"),
    and collects immutable Signal/SignalIntent/halt evidence.

    For historical replay, use :meth:`run_replay` which drives
    HistoricalReplayFeed instances through their public API and passes
    all collected events to a single coordinator.process() call.
    """

    def __init__(
        self,
        bindings: Mapping[str, StrategyBinding],
        profiles: object,  # StreamProfileMap
        allocation_priorities: object | None = None,  # AllocationPriorityConfig | None
    ) -> None:
        if not bindings:
            raise ValueError("bindings must contain at least one strategy binding")
        self._bindings = dict(bindings)
        self._profiles = profiles
        self._allocation_priorities = allocation_priorities
        self._intake = SignalIntake()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_replay(
        self,
        feeds: Mapping[StreamKey, HistoricalReplayFeed],
    ) -> PaperTradingResult:
        """Run deterministic replay using HistoricalReplayFeed instances.

        Parameters
        ----------
        feeds :
            Mapping of StreamKey → HistoricalReplayFeed.  One feed per
            declared stream.  The runner advances each feed through its
            public API only (total_bars, remaining_bars, advance_to, fetch).

        Returns
        -------
        PaperTradingResult
            Immutable frozen result with signal/intent/halt evidence.
        """
        run_id = f"paper-replay-{uuid.uuid4().hex[:12]}"

        # --- A. REPLAY COLLECTION ---
        all_events = self._collect_replay_events(feeds)

        # --- B. CANONICAL PROCESSING (single coordinator call) ---
        requirements = [
            binding.requirements for binding in self._bindings.values()
        ]
        coordinator = MarketDataCoordinator(
            requirements,
            self._profiles,
            self._allocation_priorities,
        )

        signals: list[StrategySignalEvidence] = []
        halts: list[StrategyHaltEvidence] = []
        _halt_box: list[_RunLocalHaltTracker] = [_RunLocalHaltTracker()]
        strategy_states: dict[str, dict] = {
            sid: deepcopy(binding.strategy.initial_state())
            for sid, binding in self._bindings.items()
        }

        request_count = [0]

        def _consumer(request: EvaluationRequest) -> None:
            request_count[0] += 1
            sid = request.requirements.strategy_id
            sver = request.requirements.strategy_version
            dt = request.data.decision_time

            # Per-strategy halt check (run-local, not global)
            if _halt_box[0].is_halted(sid):
                halts.append(StrategyHaltEvidence(sid, "previously_halted_this_run", dt))
                return

            binding = self._bindings[sid]
            adapter = _StrategyAdapter(binding.strategy, sid, sver)
            data = self._strategy_data(binding, request.data)

            try:
                signal = safe_generate_signal(adapter, data, strategy_states[sid], "live")
            except StrategyHaltError as error:
                _halt_box[0] = _halt_box[0].with_halt(sid)
                halts.append(StrategyHaltEvidence(sid, error.reason, dt))
                return

            if not isinstance(signal, Signal):
                raise TypeError("strategy generate_signal must return Signal")

            intent: object | None = None
            if signal.action != "HOLD":
                source = request.data.latest(binding.signal_source_stream)
                if source is not None:
                    ctx = SignalIntakeContext(source, sid, sver)
                    intent = self._intake.intake(signal, ctx)

            signals.append(StrategySignalEvidence(sid, sver, dt, signal, intent))

        requests = coordinator.process(all_events, consumer=_consumer)

        # --- C. RESULT ---
        first_ts: datetime | None = None
        last_ts: datetime | None = None
        if all_events:
            timestamps = [
                (evt.bar.timestamp if isinstance(evt, BoundBarEvent) else evt.timestamp)
                for evt in all_events
            ]
            first_ts = min(timestamps)
            last_ts = max(timestamps)

        return PaperTradingResult(
            run_id=run_id,
            processed_event_count=len(all_events),
            evaluation_request_count=request_count[0],
            signals=tuple(signals),
            halts=tuple(halts),
            first_market_timestamp=first_ts,
            last_market_timestamp=last_ts,
        )

    # ------------------------------------------------------------------
    # A. Replay collection
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_replay_events(
        feeds: Mapping[StreamKey, HistoricalReplayFeed],
    ) -> list[BoundBarEvent]:
        """Collect all bars from feeds via public API only.

        Each feed is advanced bar-by-bar using advance_to(cursor + 1).
        Each newly exposed row is converted to a BoundBarEvent.

        Feed iteration order does NOT define market event order.
        The existing MarketDataCoordinator owns canonical ordering.
        """
        events: list[BoundBarEvent] = []

        for stream_key, feed in feeds.items():
            instrument = stream_key.identity.instrument
            timeframe = stream_key.timeframe

            while feed.remaining_bars() > 0:
                feed.advance_to(feed.cursor + 1)
                df = feed.fetch(instrument, timeframe)
                if df.empty:
                    continue
                row = df.iloc[-1]
                bar = BarEvent(
                    symbol=instrument,
                    timestamp=row["timestamp"],
                    timeframe=timeframe,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    is_synthetic=bool(row.get("is_synthetic", False)),
                )
                events.append(BoundBarEvent(bar=bar, stream=stream_key))

        return events

    # ------------------------------------------------------------------
    # Strategy data helper (mirrors BacktestOrchestrator._strategy_data)
    # ------------------------------------------------------------------

    @staticmethod
    def _strategy_data(binding: StrategyBinding, view: MarketDataView):
        instruments = {stream.identity for stream in view.streams}
        if len(instruments) != 1:
            return view
        import pandas as pd
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


# ---------------------------------------------------------------------------
# Internal strategy adapter (mirrors BacktestOrchestrator._Rule7StrategyAdapter)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StrategyAdapter:
    """Bind strategy identity for safe_generate_signal audit trail."""

    strategy: object  # StrategySignalGenerator
    id: str
    interface_version: str

    def generate_signal(self, data, state):
        return self.strategy.generate_signal(data, state)
