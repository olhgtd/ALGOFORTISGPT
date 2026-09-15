"""Phase 3B-2C strategy-owned pre-entry protective plan foundation.

Separates the pre-entry *plan* (strategy-owned, produced before RiskGate
eligibility) from the runtime *ProtectiveExit instance* (owned by
``engine.protective.runtime.py`` lifecycle).  The engine does NOT dictate one global
STOP/TARGET formula: each strategy owns a ``ProtectivePlanPolicy`` that turns
completed decision-time evidence plus strategy-owned configuration/state into
one concrete STOP_LOSS price and, when the strategy owns a fixed profit exit,
one concrete TARGET price.  A strategy may also provide one immediate-active,
rule-supplied trailing-stop state for the existing runtime.  A legitimate
strategy may otherwise exit by trailing stop,
strategy signal, reversal signal, time exit, or another strategy-owned exit
rule, so a plan may carry NO fixed TARGET (``target_price=None``); target
absence is represented by Python ``None`` — never a magic value.  RiskGate
never calculates these prices; it consumes the resulting plan instances.

Safety rules:

- Plan calculation may use only evidence available at decision time.
- ``Signal.metadata`` is never an authoritative STOP/TARGET source.
- Future execution fill prices / next-bar-open prices / future market data are
  never available at planning time.
- Stale previous-trade runtime protective prices are never reused.
- Terminal ProtectiveExit instances are never revived, rewritten, or deleted.
- A policy that cannot produce valid evidence FAILS CLOSED (raises); it never
  fabricates protection and never invents fallback prices.

Quantity authority is strictly separated:

- ``PreEntryProtectivePlan`` is PRICE / PROVENANCE evidence only and owns NO
  quantity field (preventing a plan policy from becoming a second sizing
  authority).
- RiskManager/RiskGate is the SOLE quantity authority (Q64).
- Runtime ``ProtectiveExit`` materialization requires an explicit authoritative
  quantity argument; no provisional/sentinel/inferred quantity is permitted.
  In the future gate-wired flow that quantity MUST equal the RiskGate APPROVED
  quantity exactly.

The deterministic runtime protective-instance identity is
``sentinelx-protective-instance/v1`` (CanonicalCodec, explicit ordered
fields); its fingerprint is suitable as the ``ProtectiveExit.protective_id``.
Quantity deliberately does NOT participate in that identity: the identity
identifies the entry-cycle protective instance/provenance, while quantity is
authoritative runtime sizing evidence that changes legitimately through
position reduction/reconciliation.  Plan-policy identity and runtime-instance
identity are separate concepts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from engine.core.numeric import as_decimal
from engine.orders import OrderRequest, OrderType, TimeInForce
from engine.portfolio import InstrumentIdentity, PositionKey
from engine.protective.runtime import (
    ProtectiveExit,
    ProtectiveExitBook,
    ProtectiveExitKind,
    ProtectiveExitState,
    TrailingStopState,
)
from engine.reproducibility import CanonicalCodec
from engine.orchestration.signal_intake import SignalIntent


PROTECTIVE_INSTANCE_SCHEMA = "sentinelx-protective-instance/v1"

# Protective exit intents are not signal-ranked; a fixed deterministic
# confidence is authoritative provenance only.
_PROTECTIVE_EXIT_CONFIDENCE = 0.0


def _instrument_fields(value: InstrumentIdentity) -> object:
    """Canonical D4 fields for one full InstrumentIdentity, established order."""
    return (
        value.market,
        value.instrument,
        value.segment,
        value.underlying,
        value.expiry,
        value.strike,
        value.option_type,
    )


def protective_instance_identity(
    *,
    run_identity: str,
    strategy_id: str,
    strategy_version: str,
    identity: InstrumentIdentity,
    timeframe: str,
    originating_timestamp: datetime,
    protective_plan_policy_identity: str,
    kind: ProtectiveExitKind,
) -> str:
    """Deterministic runtime protective-instance identity.

    ``sentinelx-protective-instance/v1`` via CanonicalCodec with explicit
    caller-owned field ordering:

    1. run_identity
    2. strategy_id
    3. strategy_version
    4. full InstrumentIdentity (established 7-field order)
    5. timeframe
    6. originating_timestamp (CanonicalCodec UTC/nanosecond rules)
    7. protective_plan_policy_identity
    8. protective kind (STOP_LOSS, TARGET, or TRAILING_STOP)

    No JSON/SHA legacy identity, no Python ``hash()``, no ``repr()``, no
    delimiter-string canonicalizer, no random UUID, no wall-clock timestamp,
    no insertion/caller order.  Identical evidence replays to the identical
    fingerprint; a later entry cycle on the same PositionKey (later
    ``originating_timestamp``) produces a fresh identity; different protective
    kinds always differ because the kind participates.
    """
    if not isinstance(run_identity, str) or not run_identity.strip():
        raise ValueError("run_identity must be a non-empty string")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError("strategy_id must be a non-empty string")
    if not isinstance(strategy_version, str) or not strategy_version.strip():
        raise ValueError("strategy_version must be a non-empty string")
    if not isinstance(identity, InstrumentIdentity):
        raise TypeError("identity must be an InstrumentIdentity")
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ValueError("timeframe must be a non-empty string")
    if originating_timestamp.tzinfo is None or originating_timestamp.utcoffset() is None:
        raise ValueError("originating_timestamp must be timezone-aware")
    if not isinstance(protective_plan_policy_identity, str) or not protective_plan_policy_identity.strip():
        raise ValueError("protective_plan_policy_identity must be a non-empty string")
    if not isinstance(kind, ProtectiveExitKind):
        raise TypeError("kind must be a ProtectiveExitKind")
    if kind not in (
        ProtectiveExitKind.STOP_LOSS,
        ProtectiveExitKind.TARGET,
        ProtectiveExitKind.TRAILING_STOP,
    ):
        raise ValueError("protective-instance identity supports only protective exit kinds")
    return CanonicalCodec.fingerprint(
        PROTECTIVE_INSTANCE_SCHEMA,
        (
            ("run_identity", run_identity),
            ("strategy_id", strategy_id),
            ("strategy_version", strategy_version),
            ("identity", _instrument_fields(identity)),
            ("timeframe", timeframe),
            ("originating_timestamp", originating_timestamp),
            ("protective_plan_policy_identity", protective_plan_policy_identity),
            ("kind", kind),
        ),
    )


@dataclass(frozen=True)
class TrailingProtectionSpec:
    """Strategy-supplied state for the existing immediate trailing runtime.

    This is deliberately state, not an economic formula.  The current live
    evaluator supports an active long trailing stop and, with an explicitly
    registered runtime policy, a strategy-owned deferred activation. It
    ratchets only through the generic lifecycle after the policy returns a
    validated candidate; no economic formula belongs here.
    """

    initial_stop_price: Decimal | int | float | str
    initial_reference_extreme: Decimal | int | float | str
    activated: bool = True

    def __post_init__(self) -> None:
        stop = as_decimal(self.initial_stop_price, "trailing.initial_stop_price")
        extreme = as_decimal(self.initial_reference_extreme, "trailing.initial_reference_extreme")
        if stop <= 0 or extreme <= 0:
            raise ValueError("trailing prices must be positive")
        if stop >= extreme:
            raise ValueError("trailing initial_stop_price must be below initial_reference_extreme")
        if not isinstance(self.activated, bool):
            raise TypeError("trailing activated must be bool")
        object.__setattr__(self, "initial_stop_price", stop)
        object.__setattr__(self, "initial_reference_extreme", extreme)


@dataclass(frozen=True)
class PreEntryProtectivePlan:
    """Immutable evidence for ONE concrete entry cycle's protective plan.

    Binds the intended PositionKey, the decision-time provenance
    (``originating_timestamp``, ``timeframe``), the producing plan-policy
    identity, a mandatory concrete finite positive STOP price (exact Decimal)
    and, when present, a concrete finite positive TARGET price (exact
    Decimal). It may also carry one ``trailing`` state for
    the existing runtime. ``target_price`` may be ``None``: target absence is represented
    by Python ``None`` — never a magic value, zero, Infinity/NaN, or a
    synthesized price.

    Structural validation is fail-closed.  The object never ``abs()``,
    reorders, swaps, or repairs prices, and never independently invents R:R
    semantics: LONG geometry (``STOP < ENTRY < TARGET``) and target-less R:R
    policy eligibility remain RiskManager/RiskGate authority.  REPRESENTATION
    and ELIGIBILITY are separate contracts: a targetless plan is representable
    while the current RiskPolicy (minimum R:R 1.5) still rejects targetless
    candidates deterministically.
    """

    intended_position_key: PositionKey
    originating_timestamp: datetime
    timeframe: str
    protective_plan_policy_identity: str
    stop_price: Decimal | int | float | str
    target_price: Decimal | int | float | str | None = None
    trailing: TrailingProtectionSpec | None = None
    oco_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.intended_position_key, PositionKey):
            raise TypeError("intended_position_key must be a PositionKey")
        if self.originating_timestamp.tzinfo is None or self.originating_timestamp.utcoffset() is None:
            raise ValueError("originating_timestamp must be timezone-aware")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if not isinstance(self.protective_plan_policy_identity, str) or not self.protective_plan_policy_identity.strip():
            raise ValueError("protective_plan_policy_identity must be a non-empty string")
        stop = as_decimal(self.stop_price, "stop_price")
        if stop <= 0:
            raise ValueError("stop price must be positive")
        object.__setattr__(self, "stop_price", stop)
        if self.target_price is None:
            object.__setattr__(self, "target_price", None)
        else:
            target = as_decimal(self.target_price, "target_price")
            if target <= 0:
                raise ValueError("target price must be positive")
            object.__setattr__(self, "target_price", target)
        if self.trailing is not None and not isinstance(self.trailing, TrailingProtectionSpec):
            raise TypeError("trailing must be a TrailingProtectionSpec or None")
        if not isinstance(self.oco_enabled, bool):
            raise TypeError("oco_enabled must be bool")


class ProtectivePlanPolicy(ABC):
    """Strategy-owned pre-entry protective plan contract.

    Responsibility: completed decision-time evidence + strategy-owned
    configuration/state -> one concrete STOP_LOSS price (mandatory) and,
    when the strategy owns a fixed profit exit, one concrete TARGET price,
    produced BEFORE RiskGate eligibility. A policy may additionally return an
    ``TrailingProtectionSpec`` and choose whether its
    materialized siblings share OCO membership. The trailing specification is
    state for the existing runtime, not a generic formula. Deferred activation
    is available only through an explicitly registered runtime policy. A strategy that exits only by
    trailing stop, strategy/reversal signal, time exit, or another
    strategy-owned exit rule may legitimately return a plan with
    ``target_price=None``: REPRESENTATION does not require a fixed target,
    while current RiskPolicy eligibility (minimum R:R 1.5) may still
    deterministically REJECT targetless candidates.  The engine does NOT
    dictate a global STOP/TARGET formula; concrete production implementations
    (ATR-derived, fixed distance, percentage distance, strategy-specific
    frozen rules) are strategy-owned and are NOT part of this engine-wide
    contract.  Tests use a deterministic test-local stub policy.

    Implementations may consume only evidence available at decision time and
    MUST fail closed (raise) when they cannot produce valid evidence -- never
    fabricate protection, never use ``Signal.metadata`` as an authoritative
    stop/target source, never consume future fill / next-bar-open prices, and
    never revive terminal protective evidence.
    """

    @property
    @abstractmethod
    def policy_identity(self) -> str:
        """Deterministic identity of this strategy-owned plan policy."""

    @abstractmethod
    def plan_for(
        self,
        *,
        intended_position_key: PositionKey,
        originating_timestamp: datetime,
        timeframe: str,
        reference_price: Decimal | int | float | str,
    ) -> PreEntryProtectivePlan:
        """Evaluate one new BUY-entry cycle and return the concrete immutable plan.

        ``reference_price`` is the completed signal-source / decision-time
        reference price already available when the signal becomes eligible
        (never a future fill).  The returned plan carries a concrete STOP
        price and, when the strategy owns a fixed target, a concrete TARGET
        price (``target_price`` may be ``None``), optional supported trailing
        state, and optional OCO composition; no default trading formula exists
        at the engine level.
        """


def _exit_intent(*, key: PositionKey, timeframe: str, originating_timestamp: datetime) -> SignalIntent:
    """Deterministic EXIT intent for a materialized protective instance.

    The symbol is casefolded to match the canonical intake/execution symbol
    convention (``SignalIntake`` stores ``source_event.symbol.casefold()`` and
    the execution engine compares ``bar.symbol.casefold()`` against the order
    symbol), while ``InstrumentIdentity.instrument`` is normalized UPPERCASE.
    Without the casefold a materialized protective order would never match a
    real bar during runtime evaluation.
    """
    return SignalIntent(
        action="EXIT",
        confidence=_PROTECTIVE_EXIT_CONFIDENCE,
        symbol=key.identity.instrument.casefold(),
        timeframe=timeframe,
        originating_timestamp=originating_timestamp,
        strategy_id=key.strategy_id,
        strategy_version=key.strategy_version,
        metadata={},
    )


def _protective_instance(
    plan: PreEntryProtectivePlan,
    *,
    run_identity: str,
    quantity: Decimal,
    kind: ProtectiveExitKind,
    oco_group_id: str | None,
) -> ProtectiveExit:
    """Build one fresh ACTIVE ProtectiveExit from the plan evidence."""
    key = plan.intended_position_key
    protective_id = protective_instance_identity(
        run_identity=run_identity,
        strategy_id=key.strategy_id,
        strategy_version=key.strategy_version,
        identity=key.identity,
        timeframe=plan.timeframe,
        originating_timestamp=plan.originating_timestamp,
        protective_plan_policy_identity=plan.protective_plan_policy_identity,
        kind=kind,
    )
    intent = _exit_intent(key=key, timeframe=plan.timeframe, originating_timestamp=plan.originating_timestamp)
    if kind is ProtectiveExitKind.TARGET:
        order = OrderRequest.from_intent(
            intent, OrderType.LIMIT, quantity, TimeInForce.GTC, limit_price=plan.target_price,
        )
    else:
        stop_price = (
            plan.trailing.initial_stop_price
            if kind is ProtectiveExitKind.TRAILING_STOP
            else plan.stop_price
        )
        order = OrderRequest.from_intent(
            intent, OrderType.STOP, quantity, TimeInForce.GTC, stop_price=stop_price,
        )
    trailing = (
        TrailingStopState(
            current_stop=plan.trailing.initial_stop_price,
            reference_extreme=plan.trailing.initial_reference_extreme,
            activated=plan.trailing.activated,
        )
        if kind is ProtectiveExitKind.TRAILING_STOP
        else None
    )
    return ProtectiveExit(
        protective_id,
        key,
        order,
        kind,
        order.quantity,
        oco_group_id=oco_group_id,
        trailing=trailing,
    )


def materialize_protective_plan(
    plan: PreEntryProtectivePlan,
    *,
    run_identity: str,
    quantity: Decimal | int | float | str,
    book: ProtectiveExitBook,
) -> tuple[ProtectiveExit, ...]:
    """Materialize one plan into fresh ACTIVE runtime ProtectiveExit instance(s)
    registered in ``book``.

    A plan may produce its mandatory STOP_LOSS, optional TARGET, and optional
    immediate-active TRAILING_STOP. A targetless/trailing-less plan produces
    only STOP_LOSS. A trailing plan maps directly to the existing
    ``TrailingStopState`` and never defines activation or ratchet economics.

    ``quantity`` is REQUIRED keyword-only and has NO default: the authoritative
    Q64 quantity supplied by RiskManager/RiskGate.  No provisional, sentinel,
    inferred, Slice-14 configured, or Signal.metadata quantity is permitted.
    The supplied quantity is validated only (numeric, finite, > 0) and then
    used EXACTLY for every produced OrderRequest/ProtectiveExit quantity (the
    STOP quantity, and the TARGET quantity when one is produced, both equal
    the supplied quantity); no second flooring, normalization, rounding,
    clamping, resizing, or account derivation exists here.
    RiskManager/RiskGate remains the sole sizing authority;
    ``reconcile_position`` may reduce protection after legitimate position
    reductions but is not an initial sizing authority.

    Every produced instance binds the exact intended PositionKey, uses the
    concrete plan prices, carries a deterministic
    ``sentinelx-protective-instance/v1`` id (quantity does NOT participate in
    the instance identity), and starts ACTIVE. Exactly-one-ACTIVE safety: if an
    ACTIVE STOP_LOSS, TARGET, or TRAILING_STOP already exists for the intended
    PositionKey, this fails closed (raises) rather than silently adding
    another active plan; it never cancels a legitimate existing active
    protection to make room and never selects a winner by ``protective_id``
    ordering.

    No execution is evaluated, no order is submitted, ``PortfolioAccount`` is
    never mutated, and RiskGate is never invoked here: this helper only
    materializes fresh pre-entry runtime protection evidence.  Existing
    terminal history remains intact and is never revived or rewritten.
    """
    if not isinstance(plan, PreEntryProtectivePlan):
        raise TypeError("plan must be a PreEntryProtectivePlan")
    if not isinstance(book, ProtectiveExitBook):
        raise TypeError("book must be a ProtectiveExitBook")
    quantity_value = as_decimal(quantity, "quantity")
    if quantity_value <= 0:
        raise ValueError("quantity must be positive")
    key = plan.intended_position_key
    if book.authoritative_exits(key, kind=ProtectiveExitKind.STOP_LOSS):
        raise ValueError("active STOP_LOSS already exists for the intended PositionKey")
    if book.authoritative_exits(key, kind=ProtectiveExitKind.TARGET):
        raise ValueError("active TARGET already exists for the intended PositionKey")
    if book.authoritative_exits(key, kind=ProtectiveExitKind.TRAILING_STOP):
        raise ValueError("active TRAILING_STOP already exists for the intended PositionKey")
    oco_group_id = None
    if plan.oco_enabled:
        stop_identity = protective_instance_identity(
            run_identity=run_identity,
            strategy_id=key.strategy_id,
            strategy_version=key.strategy_version,
            identity=key.identity,
            timeframe=plan.timeframe,
            originating_timestamp=plan.originating_timestamp,
            protective_plan_policy_identity=plan.protective_plan_policy_identity,
            kind=ProtectiveExitKind.STOP_LOSS,
        )
        oco_group_id = f"{stop_identity}:oco"
    stop = _protective_instance(
        plan,
        run_identity=run_identity,
        quantity=quantity_value,
        kind=ProtectiveExitKind.STOP_LOSS,
        oco_group_id=oco_group_id,
    )
    book.add(stop)
    materialized = [stop]
    if plan.target_price is not None:
        target = _protective_instance(
            plan,
            run_identity=run_identity,
            quantity=quantity_value,
            kind=ProtectiveExitKind.TARGET,
            oco_group_id=oco_group_id,
        )
        book.add(target)
        materialized.append(target)
    if plan.trailing is not None:
        trailing = _protective_instance(
            plan,
            run_identity=run_identity,
            quantity=quantity_value,
            kind=ProtectiveExitKind.TRAILING_STOP,
            oco_group_id=oco_group_id,
        )
        book.add(trailing)
        materialized.append(trailing)
    return tuple(materialized)
