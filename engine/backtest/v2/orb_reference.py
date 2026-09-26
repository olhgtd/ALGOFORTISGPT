"""Policy-bound, options-buy-only ORB research backtest fixture."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.data.instruments import InstrumentTerms
from engine.reproducibility.codec import CanonicalCodec
from engine.strategy.protective_policy_v2 import ProtectivePolicyV2
from strategies.orb.orb_v2 import ORBAction, ORBReferenceStrategyV2, ORBSignalSnapshot
from .contracts import Bar
from .options import OptionModel, price_option_fill


class ORBBacktestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ORBBacktestResult:
    action: str
    entry_price: Decimal
    exit_price: Decimal
    exit_reason: str
    quantity: Decimal
    pnl: Decimal
    fingerprint: str
    promotion_eligible: bool = False


def run_orb_option_backtest(snapshot: ORBSignalSnapshot, *, terms: InstrumentTerms,
                            option_bars: tuple[Bar, ...], policy: ProtectivePolicyV2,
                            option_model: OptionModel) -> ORBBacktestResult:
    if (not isinstance(snapshot, ORBSignalSnapshot) or not isinstance(terms, InstrumentTerms)
            or not isinstance(policy, ProtectivePolicyV2) or not isinstance(option_model, OptionModel)
            or not isinstance(option_bars, tuple) or len(option_bars) < 2
            or any(not isinstance(bar, Bar) for bar in option_bars)
            or any(a.timestamp >= b.timestamp for a, b in zip(option_bars, option_bars[1:]))
            or option_bars[0].timestamp <= snapshot.timestamp):
        raise ORBBacktestError("ordered future option quotes and explicit policy/model required")
    signal = ORBReferenceStrategyV2().generate_signal(snapshot)
    if signal.action is ORBAction.HOLD:
        raise ORBBacktestError("no breakout: no option entry")
    side = "CE" if signal.action is ORBAction.BUY else "PE"
    if terms.segment != "options" or terms.option_type != side or terms.underlying != snapshot.symbol:
        raise ORBBacktestError("as-of option terms must match CE/PE buy signal")
    entry_bar = option_bars[0]
    fill = price_option_fill(terms, entry_bar.timestamp.date(), entry_bar.open, 1, option_model)
    entry = fill.premium
    stop = entry - policy.stop_distance
    target = entry + policy.target_distance
    if stop <= 0:
        raise ORBBacktestError("stop price must remain positive")
    highest = entry
    exit_price = None
    reason = ""
    for bar in option_bars[1:]:
        if bar.timestamp.date() > terms.expiry:
            raise ORBBacktestError("option expired during research simulation")
        # Conservative OHLC ordering: if stop and target both touch in one bar,
        # book the stop. A gap through the stop fills at the worse open.
        if bar.low <= stop:
            exit_price = min(bar.open, stop)
            reason = "STOP"
            break
        if bar.high >= target:
            exit_price = target
            reason = "TARGET"
            break
        highest = max(highest, bar.high)
        stop = max(stop, highest - policy.trailing_distance)
    if exit_price is None:
        exit_price = option_bars[-1].close
        reason = "END_OF_DATA"
    pnl = (exit_price - entry) * fill.quantity
    fingerprint = CanonicalCodec.fingerprint("algofortis-orb-option-backtest/v1", (
        ("signal", signal.fingerprint), ("terms", terms.fingerprint),
        ("policy", policy.fingerprint), ("option_model", (option_model.version,
          option_model.daily_theta, option_model.iv_shift, option_model.gamma_impact, option_model.spread)),
        ("bars", tuple((bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)
                       for bar in option_bars)), ("entry", entry), ("exit", exit_price),
        ("reason", reason), ("quantity", fill.quantity), ("pnl", pnl),
        ("promotion_eligible", False)))
    return ORBBacktestResult("BUY_" + side, entry, exit_price, reason,
                             fill.quantity, pnl, fingerprint)
