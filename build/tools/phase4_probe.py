"""Deterministic cross-run ORB reference and Backtest V2 probe."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from engine.backtest.v2.contracts import Bar, ExecutionModel, OrderIntent
from engine.backtest.v2.execution import simulate
from strategies.orb.orb_v2 import ORBReferenceStrategyV2, ORBSignalSnapshot


def run() -> tuple[str, str]:
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    signal = ORBReferenceStrategyV2().generate_signal(ORBSignalSnapshot(
        "NIFTY", now, Decimal("22011"), Decimal("22010"), Decimal("21990")))
    bars = (Bar(now, Decimal("22000"), Decimal("22012"), Decimal("21999"), Decimal("22011"), Decimal("100")),
            Bar(now + timedelta(minutes=5), Decimal("22015"), Decimal("22020"), Decimal("22010"), Decimal("22018"), Decimal("100")))
    result = simulate(bars, (OrderIntent(0, "BUY", Decimal("1")),),
                      ExecutionModel("research-execution@v1", latency_bars=1,
                                     spread=Decimal("0.2"), slippage=Decimal("0.1")))
    return signal.fingerprint, result.fingerprint


if __name__ == "__main__":
    signal, run_fingerprint = run()
    print("ORB_SIGNAL=" + signal)
    print("BACKTEST_RUN=" + run_fingerprint)
