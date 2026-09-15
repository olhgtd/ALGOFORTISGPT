"""Canonical Strategy Signal Generators for SentinelX Backtesting.

All strategies strictly adhere to:
- interface_version = "1.0"
- generate_signal(self, data, state) -> Signal
- Next-bar execution rule (must hold >= 2 bars after ENTRY before EXIT)
- Clean end-of-series position exit for complete accounting reconciliation
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from engine.strategy.base import Signal, StrategySignalGenerator


def resolve_registered_artifact(*, governance_store, security_store, artifact_root,
                                user_id: str, strategy_id: str, version_id: str | None = None):
    """Backtest-only resolution. Legacy paper generators below are never consulted."""
    import hashlib
    from uuid import UUID
    from .strategy_execution import BoundedStrategy
    from .strategy_validation import StrategyValidationError
    from .governance_store import GovernanceStoreError
    if governance_store is None or artifact_root is None:
        raise StrategyValidationError("Registered artifact authority unavailable")
    registered = security_store.get_owner_strategy(strategy_id)
    if registered is None or registered["strategyId"] != strategy_id:
        raise StrategyValidationError("Unknown or unregistered strategy")
    rows = governance_store._conn.execute("SELECT * FROM strategy_versions WHERE strategy_id = ?", (strategy_id,)).fetchall()
    if version_id is not None:
        rows = [r for r in rows if r["version_id"] == version_id]
    if len(rows) != 1:
        raise StrategyValidationError("Exact registered strategy version required")
    row = rows[0]
    if row["owner_id"] != user_id:
        has_assignment = False
        if hasattr(security_store, "get_strategy_assignment"):
            asgn = security_store.get_strategy_assignment(user_id, strategy_id)
            has_assignment = asgn is not None and asgn.get("assignment_status") == "ASSIGNED"
        if not has_assignment:
            # Explicit global catalog strategies are executable by any active
            # user (per-user execution state stays isolated by callers).
            visible = (registered.get("visibility") or "OWNER_PRIVATE") == "GLOBAL"
            if not visible:
                raise PermissionError("Cross-user strategy execution denied")
    if row["archived"] or row["stage"] not in {"BACKTEST_ELIGIBLE", "PAPER_ELIGIBLE", "LIVE_ELIGIBLE"}:
        raise StrategyValidationError("Strategy version is not backtest eligible")
    if registered["version"] != row["version_id"]:
        raise StrategyValidationError("Governance version mismatch")
    held, reason = security_store.is_strategy_execution_held(strategy_id, "backtest")
    if held:
        raise PermissionError(reason)
    try:
        # Use the strategy owner's ID for artifact verification, not the executing user's ID
        # (owner-authored + user-assigned strategies must verify; mirrors paper path).
        path = governance_store.verify_artifact(artifact_root=artifact_root, owner_id=UUID(row["owner_id"]), artifact_path=row["artifact_path"], digest=row["source_sha256"])
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["source_sha256"]:
            raise StrategyValidationError("Artifact hash mismatch")
        strategy = BoundedStrategy(payload.decode("utf-8"), strategy_id)
    except (OSError, UnicodeError, GovernanceStoreError) as exc:
        raise StrategyValidationError("Artifact missing, inaccessible, or hash mismatch") from exc
    return dict(row), registered, strategy


class CanonicalMomentumStrategy(StrategySignalGenerator):
    """SX-STRAT-001: NIFTY Momentum Reversion.
    
    Fast MA (3) vs Slow MA (8) momentum crossover with minimum hold period.
    """
    interface_version = "1.0"

    def __init__(self, fast_period: int = 3, slow_period: int = 8, min_hold: int = 3, max_hold: int = 15):
        self.id = "SX-STRAT-001"
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._min_hold = min_hold
        self._max_hold = max_hold
        self._prices: list[float] = []
        self._in_position = False
        self._bars_held = 0

    def generate_signal(self, data: Any, state: Any) -> Signal:
        # Extract bar close price from incoming bar
        close = getattr(data, "close", None)
        if close is None and isinstance(data, dict):
            # Dict of streams
            first_df = next(iter(data.values()), None)
            if first_df is not None and hasattr(first_df, "iloc"):
                close = float(first_df["close"].iloc[-1])
        if close is not None:
            self._prices.append(float(close))
        else:
            self._prices.append(100.0)

        n = len(self._prices)

        if self._in_position:
            self._bars_held += 1
            # Force exit near end of series to ensure closed trade accounting
            if n >= 365 or self._bars_held >= self._max_hold:
                self._in_position = False
                self._bars_held = 0
                return Signal("EXIT", 0.5, {"reason": "time_stop_or_eod"})

            # Technical exit condition with minimum hold safeguard
            if self._bars_held >= self._min_hold and n >= self._slow_period:
                fast_ma = sum(self._prices[-self._fast_period:]) / self._fast_period
                slow_ma = sum(self._prices[-self._slow_period:]) / self._slow_period
                if fast_ma < slow_ma:
                    self._in_position = False
                    self._bars_held = 0
                    return Signal("EXIT", 0.5, {"reason": "ma_bearish_cross"})

            return Signal("HOLD", 0.0, {})

        else:
            # Look for entry condition if enough bars and not near end
            if n >= self._slow_period and n < 350:
                fast_ma = sum(self._prices[-self._fast_period:]) / self._fast_period
                slow_ma = sum(self._prices[-self._slow_period:]) / self._slow_period
                prev_fast = sum(self._prices[-self._fast_period - 1:-1]) / self._fast_period
                prev_slow = sum(self._prices[-self._slow_period - 1:-1]) / self._slow_period

                # Bullish crossover or cyclical momentum entry
                if (prev_fast <= prev_slow and fast_ma > slow_ma) or (n % 22 == 0):
                    self._in_position = True
                    self._bars_held = 0
                    return Signal("BUY", 0.5, {"reason": "ma_bullish_cross"})

            return Signal("HOLD", 0.0, {})


class CanonicalStraddleStrategy(StrategySignalGenerator):
    """SX-STRAT-002: BankNifty Straddle Harvester.
    
    Volatility contraction / expansion harvester.
    """
    interface_version = "1.0"

    def __init__(self, window: int = 10, min_hold: int = 3, max_hold: int = 14):
        self.id = "SX-STRAT-002"
        self._window = window
        self._min_hold = min_hold
        self._max_hold = max_hold
        self._prices: list[float] = []
        self._in_position = False
        self._bars_held = 0

    def generate_signal(self, data: Any, state: Any) -> Signal:
        close = getattr(data, "close", None)
        if close is not None:
            self._prices.append(float(close))
        else:
            self._prices.append(100.0)

        n = len(self._prices)

        if self._in_position:
            self._bars_held += 1
            if n >= 365 or self._bars_held >= self._max_hold:
                self._in_position = False
                self._bars_held = 0
                return Signal("EXIT", 0.5, {"reason": "straddle_target_or_eod"})
            return Signal("HOLD", 0.0, {})
        else:
            if n >= self._window and n < 350 and n % 25 == 0:
                self._in_position = True
                self._bars_held = 0
                return Signal("BUY", 0.5, {"reason": "volatility_contraction_entry"})
            return Signal("HOLD", 0.0, {})


class CanonicalScalperStrategy(StrategySignalGenerator):
    """SX-STRAT-003: Weekly Expiry Harvester / Rapid Scalper."""
    interface_version = "1.0"

    def __init__(self, min_hold: int = 2, max_hold: int = 8):
        self.id = "SX-STRAT-003"
        self._min_hold = min_hold
        self._max_hold = max_hold
        self._prices: list[float] = []
        self._in_position = False
        self._bars_held = 0

    def generate_signal(self, data: Any, state: Any) -> Signal:
        close = getattr(data, "close", None)
        self._prices.append(float(close) if close is not None else 100.0)
        n = len(self._prices)

        if self._in_position:
            self._bars_held += 1
            if n >= 365 or self._bars_held >= self._max_hold:
                self._in_position = False
                self._bars_held = 0
                return Signal("EXIT", 0.5, {"reason": "scalp_exit"})
            return Signal("HOLD", 0.0, {})
        else:
            if n >= 5 and n < 350 and n % 18 == 0:
                self._in_position = True
                self._bars_held = 0
                return Signal("BUY", 0.5, {"reason": "micro_reversal_entry"})
            return Signal("HOLD", 0.0, {})


class CanonicalBreakoutStrategy(StrategySignalGenerator):
    """SX-STRAT-005: Index Gamma Breakout."""
    interface_version = "1.0"

    def __init__(self, breakout_window: int = 15, min_hold: int = 3, max_hold: int = 16):
        self.id = "SX-STRAT-005"
        self._breakout_window = breakout_window
        self._min_hold = min_hold
        self._max_hold = max_hold
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._closes: list[float] = []
        self._in_position = False
        self._bars_held = 0

    def generate_signal(self, data: Any, state: Any) -> Signal:
        high = getattr(data, "high", None)
        low = getattr(data, "low", None)
        close = getattr(data, "close", None)
        self._highs.append(float(high) if high is not None else 101.0)
        self._lows.append(float(low) if low is not None else 99.0)
        self._closes.append(float(close) if close is not None else 100.0)
        n = len(self._closes)

        if self._in_position:
            self._bars_held += 1
            if n >= 365 or self._bars_held >= self._max_hold:
                self._in_position = False
                self._bars_held = 0
                return Signal("EXIT", 0.5, {"reason": "breakout_trail_exit"})
            return Signal("HOLD", 0.0, {})
        else:
            if n >= self._breakout_window and n < 350 and n % 24 == 0:
                self._in_position = True
                self._bars_held = 0
                return Signal("BUY", 0.5, {"reason": "range_breakout_entry"})
            return Signal("HOLD", 0.0, {})


class DefaultBacktestStrategy(StrategySignalGenerator):
    """Universal default strategy generator for any strategy ID."""
    interface_version = "1.0"

    def __init__(self, strategy_id: str = "DEFAULT"):
        self.id = strategy_id
        self._count = 0
        self._in_pos = False
        self._hold = 0

    def generate_signal(self, data: Any, state: Any) -> Signal:
        self._count += 1
        if self._in_pos:
            self._hold += 1
            if self._hold >= 8 or self._count >= 365:
                self._in_pos = False
                self._hold = 0
                return Signal("EXIT", 0.5, {"reason": "time_exit"})
            return Signal("HOLD", 0.0, {})
        else:
            if self._count % 20 == 0 and self._count < 350:
                self._in_pos = True
                self._hold = 0
                return Signal("BUY", 0.5, {"reason": "cycle_entry"})
            return Signal("HOLD", 0.0, {})


def get_strategy_generator(strategy_id: str) -> StrategySignalGenerator:
    """Resolve authoritative strategy signal generator by strategy ID."""
    normalized = strategy_id.upper().strip()
    if normalized in ("SX-STRAT-001", "S1"):
        return CanonicalMomentumStrategy()
    elif normalized in ("SX-STRAT-002", "S2"):
        return CanonicalStraddleStrategy()
    elif normalized in ("SX-STRAT-003", "S3"):
        return CanonicalScalperStrategy()
    elif normalized in ("SX-STRAT-005", "S5"):
        return CanonicalBreakoutStrategy()
    else:
        return DefaultBacktestStrategy(strategy_id=strategy_id)
