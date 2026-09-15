"""Phase 8 Slice 1 — live-safety controller and auto-halt bridges (ADR §128).

AUTHORITY MODEL (§128 — nothing here is a second authority)
-----------------------------------------------------------
* The GLOBAL kill-switch authority remains the existing durable
  ``LivePaperCoordinator.activate_kill_switch`` / ``SafetyManager`` stack.
  This controller never owns global state: it CONSUMES authoritative
  outcomes and ESCALATES through an injected activator callable.
* The RUNTIME per-strategy gating authority remains
  ``LiveStrategyCoordinator._halted_owners``.  This module contributes the
  DURABLE mirror of that latch plus the OD-1/OD-3 escalation arithmetic.
* RiskGate remains the sole daily-loss calculation authority; the
  ``observe_daily_loss_breach`` bridge consumes the already-authoritative
  gate outcome without recomputation.
* Reconciliation evidence remains the reconciliation authority; the
  ``observe_reconciliation_failed`` bridge consumes the first authoritative
  ``ReconciliationHealth.FAILED`` with no grace counter (OD-4).

FROZEN BEHAVIOUR (§128.1/§128.3–§128.7)
---------------------------------------
* Isolated strategy exception ⇒ halt THAT strategy only + increment the one
  canonical per-session error count; count reaching the threshold ⇒ global
  kill switch.  The first isolated exception never halts everything.
* Max daily loss ⇒ immediate global kill switch.
* Reconciliation FAILED ⇒ immediate global kill switch (no grace).
* Manual resume requires explicit operator identity, is gated on ALL
  applicable prerequisites being clean at the affected scope, never
  auto-clears, and global/per-strategy latches are independent in both
  directions.

NO DEFAULTS (§128.3/§128.16): the strategy-error kill threshold is a REQUIRED
constructor argument with no default value — no numeric policy is invented
anywhere in this module.  Callers must supply the configured value or not
enable Phase-8 escalation at all.

DETERMINISM: all decisions derive from explicit inputs; no wall clock, no
randomness, no sleeps, no network.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Iterable, Mapping

logger = logging.getLogger(__name__)

__all__ = [
    "HALT_CONTRACT_VERSION",
    "GlobalResumeDecision",
    "HeartbeatEvaluation",
    "Phase8GlobalCause",
    "Phase8SafetyController",
    "StrategyEscalationOutcome",
    "parse_halted_owners",
    "serialize_halted_owners",
]


HALT_CONTRACT_VERSION = "sentinelx-halt-state/v1"

DAILY_LOSS_REASON_TOKEN = "max_daily_loss_exceeded"
RECONCILIATION_FAILED_REASON_TOKEN = "reconciliation_failed"
STRATEGY_ERROR_THRESHOLD_REASON_TOKEN = "strategy_error_threshold_reached"
STALE_MARKET_DATA_REASON_TOKEN = "stale_market_data"
PROTECTIVE_AMBIGUITY_REASON_TOKEN = "protective_invariant_ambiguous"
PHASE8_AUTO_HALT_SOURCE = "phase8_auto_halt"


# ======================================================================
# Canonical durable owner serialization (§128.9)
# ======================================================================


def serialize_halted_owners(owners: Iterable[tuple[str, str]]) -> str:
    """Canonical deterministic JSON for halted strategy owners (§128.9).

    Produces a sorted array of ``{"strategy_id": ..., "strategy_version": ...}``
    records under fixed compact separators.  Ambiguous colon-concatenated
    identity strings are never produced.
    """
    normalized = _validate_owner_tuples(owners)
    records = [
        {"strategy_id": sid, "strategy_version": sver}
        for sid, sver in sorted(normalized)
    ]
    return json.dumps(records, sort_keys=True, separators=(",", ":"))


def parse_halted_owners(raw: str) -> tuple[tuple[str, str], ...]:
    """Strictly parse persisted halted-owner JSON; ValueError when invalid.

    Accepts ONLY the exact canonical shape: a JSON array of objects each with
    exactly the keys ``strategy_id`` and ``strategy_version`` (non-empty
    strings), already in canonical order without duplicates.  Any deviation is
    corruption and must fail closed upstream.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("halted-owner payload must be a non-empty string")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"halted-owner payload is not valid JSON: {exc}") from exc
    if not isinstance(decoded, list):
        raise ValueError("halted-owner payload must be a JSON array")
    parsed: list[tuple[str, str]] = []
    for entry in decoded:
        if not isinstance(entry, dict) or set(entry.keys()) != {"strategy_id", "strategy_version"}:
            raise ValueError("halted-owner record has unexpected keys")
        sid = entry["strategy_id"]
        sver = entry["strategy_version"]
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(sver, str) or not sver.strip():
            raise ValueError("strategy_version must be a non-empty string")
        parsed.append((sid, sver))
    expected = serialize_halted_owners(parsed)
    if expected != raw:
        raise ValueError("halted-owner payload is not in canonical form")
    return tuple(parsed)


def _validate_owner_tuples(owners: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    validated: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for owner in owners:
        if isinstance(owner, str) or len(owner) != 2:
            raise ValueError("owner must be a (strategy_id, strategy_version) pair")
        sid, sver = owner
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError("strategy_id must be a non-empty string")
        if not isinstance(sver, str) or not sver.strip():
            raise ValueError("strategy_version must be a non-empty string")
        key = (sid, sver)
        if key in seen:
            continue
        seen.add(key)
        validated.append(key)
    return validated


# ======================================================================
# Controller
# ======================================================================


class Phase8GlobalCause(str, Enum):
    """Independently observable global safety causes tracked by the gate."""

    DISCONNECT = "DISCONNECT"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    PROTECTIVE_AMBIGUITY = "PROTECTIVE_AMBIGUITY"


@dataclass(frozen=True)
class StrategyEscalationOutcome:
    """Immutable result of one isolated-strategy-exception observation."""

    owner_newly_halted: bool
    session_error_count: int
    threshold: int
    global_kill_switch_triggered: bool


@dataclass(frozen=True)
class GlobalResumeDecision:
    """Immutable decision for an explicit operator global-resume request."""

    approved: bool
    operator_id: str
    failed_prerequisites: tuple[str, ...]


@dataclass(frozen=True)
class HeartbeatEvaluation:
    """Immutable deterministic heartbeat/staleness evaluation (§128.11)."""

    configured_timeout_seconds: float | None
    age_seconds: float | None
    stale: bool
    stale_transition: bool
    fresh_transition: bool
    global_kill_switch_triggered: bool


@dataclass(frozen=True)
class ProtectiveSafetyOutcome:
    """Immutable result of one protective-invariant failure (§128.12/OD-8).

    Scoped halt requires a clearly attributable owner AND provable broader
    integrity/accounting safety; anything ambiguous fails closed globally.
    """

    scoped_to_strategy: bool
    strategy_id: str | None
    strategy_version: str | None
    newly_halted: bool
    global_kill_switch_triggered: bool


class Phase8SafetyController:
    """OD-1/OD-3 escalation arithmetic over EXISTING safety authorities.

    The controller owns only: the canonical per-session error count, the
    in-memory registry of currently-unsafe global causes feeding the unified
    manual-review gate, and escalation routing through injected callables.
    It persists nothing itself and holds no second kill switch.
    """

    def __init__(
        self,
        *,
        strategy_error_kill_threshold: int,
        activate_global_kill_switch: Callable[[str], object],
        halt_strategy: Callable[[str, str], bool] | None = None,
        persist_halted_owners: Callable[[tuple[tuple[str, str], ...]], None] | None = None,
        resume_strategy_runtime: Callable[[str, str], bool] | None = None,
        global_kill_switch_active_probe: Callable[[], bool] | None = None,
        heartbeat_timeout_seconds: float | int | None = None,
        initial_session_error_count: int = 0,
        controller_id: str = "phase8_safety",
    ) -> None:
        if isinstance(strategy_error_kill_threshold, bool) or not isinstance(
            strategy_error_kill_threshold, int
        ):
            raise TypeError("strategy_error_kill_threshold must be a positive int")
        if strategy_error_kill_threshold < 1:
            raise ValueError("strategy_error_kill_threshold must be >= 1")
        if not callable(activate_global_kill_switch):
            raise TypeError("activate_global_kill_switch must be callable")
        self.strategy_error_kill_threshold = strategy_error_kill_threshold
        self._activate_global = activate_global_kill_switch
        self._halt_strategy = halt_strategy
        self._persist_halted_owners = persist_halted_owners
        self._resume_strategy_runtime = resume_strategy_runtime
        self._global_kill_switch_active_probe = global_kill_switch_active_probe
        # §128.11 (OD-7): reuse the EXISTING heartbeat_timeout_seconds config
        # authority.  None (unset/null) ⇒ stale-data escalation DISABLED and
        # the existing connection/fresh-market-evidence authority stands.
        # No numeric default is invented here — ever.
        if heartbeat_timeout_seconds is not None:
            if isinstance(heartbeat_timeout_seconds, bool) or not isinstance(
                heartbeat_timeout_seconds, (int, float)
            ):
                raise TypeError("heartbeat_timeout_seconds must be a positive number or None")
            if not heartbeat_timeout_seconds > 0:
                raise ValueError("heartbeat_timeout_seconds must be > 0 when configured")
        self._heartbeat_timeout_seconds: float | None = (
            float(heartbeat_timeout_seconds) if heartbeat_timeout_seconds is not None else None
        )
        self._stale_latched = False
        self.controller_id = controller_id
        if isinstance(initial_session_error_count, bool) or not isinstance(
            initial_session_error_count, int
        ) or initial_session_error_count < 0:
            raise ValueError("initial_session_error_count must be a non-negative int")
        self._session_error_count = initial_session_error_count
        # Canonical per-session halted-owner mirror (runtime authority stays
        # in LiveStrategyCoordinator; this is the durability + arithmetic view).
        self._halted_owners: set[tuple[str, str]] = set()
        self._unsafe_causes: dict[Phase8GlobalCause, str | None] = {}
        self._global_escalated_causes: set[str] = set()
        # §128.14: human-review requirements recorded through THIS latch
        # owner (never through alert evidence itself).  Scopes are canonical
        # tuples: ("GLOBAL",) or ("STRATEGY", strategy_id, strategy_version).
        self._pending_human_reviews: set[tuple[str, ...]] = set()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def session_error_count(self) -> int:
        return self._session_error_count

    @property
    def halted_owners(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._halted_owners))

    @property
    def unsafe_causes(self) -> tuple[Phase8GlobalCause, ...]:
        return tuple(sorted(self._unsafe_causes, key=lambda cause: cause.value))

    def is_unsafe(self, cause: Phase8GlobalCause) -> bool:
        return cause in self._unsafe_causes

    # ------------------------------------------------------------------
    # OD-1A / max daily loss — consume existing authoritative outcome
    # ------------------------------------------------------------------

    def observe_daily_loss_breach(self) -> bool:
        """Escalate to GLOBAL kill switch on the authoritative daily-loss outcome."""
        return self._escalate_global(DAILY_LOSS_REASON_TOKEN)

    # ------------------------------------------------------------------
    # OD-4 / reconciliation failure — first FAILED escalates immediately
    # ------------------------------------------------------------------

    def observe_reconciliation_failed(self) -> bool:
        """First authoritative FAILED ⇒ mark unsafe + immediate global halt."""
        self.mark_cause_unsafe(Phase8GlobalCause.RECONCILIATION_FAILED)
        return self._escalate_global(RECONCILIATION_FAILED_REASON_TOKEN)

    def observe_reconciliation_resolved(self) -> None:
        """Reconciliation health recovered: establishes eligibility ONLY."""
        self.mark_cause_healthy(Phase8GlobalCause.RECONCILIATION_FAILED)

    # ------------------------------------------------------------------
    # OD-2 — disconnect/reconnect evidence and mandatory human review
    # ------------------------------------------------------------------

    def observe_feed_disconnect(self) -> bool:
        """Latch a disconnect globally and require human review before resume.

        The existing coordinator remains the only global kill-switch owner.
        A reconnect is handled separately and can establish transport health,
        but it cannot remove this review requirement or clear the kill switch.
        """
        self.mark_cause_unsafe(Phase8GlobalCause.DISCONNECT)
        self.record_human_review_requirement(("GLOBAL",))
        return self._escalate_global("feed_disconnected")

    def observe_feed_reconnected(self) -> None:
        """Record recovered transport only; review and global halt stay latched."""
        self.mark_cause_healthy(Phase8GlobalCause.DISCONNECT)

    # ------------------------------------------------------------------
    # §128.12 / OD-8 — protective-invariant failure scope model
    # ------------------------------------------------------------------

    def observe_protective_failure(
        self,
        *,
        strategy_id: str | None,
        strategy_version: str | None,
        integrity_proven_safe: bool,
    ) -> ProtectiveSafetyOutcome:
        """Route one protective invariant failure to its frozen scope.

        Scoped halt (§128.12): the owner is clearly attributable AND broader
        accounting/integrity safety is proven ⇒ halt that strategy only, emit
        a scoped human-review requirement, and require explicit operator
        resume for it.  The per-session ERROR count is NOT incremented —
        protective failures are not isolated StrategyHaltError exceptions.

        Ambiguous or integrity-threatening ⇒ GLOBAL fail closed / kill switch
        plus a GLOBAL human-review requirement.
        """
        attributable = (
            isinstance(strategy_id, str)
            and bool(strategy_id.strip())
            and isinstance(strategy_version, str)
            and bool(strategy_version.strip())
        )
        if attributable and integrity_proven_safe:
            owner = (strategy_id, strategy_version)  # type: ignore[arg-type]
            newly_halted = True
            if self._halt_strategy is not None:
                newly_halted = bool(self._halt_strategy(*owner))
            self._merge_and_persist(owner if newly_halted else None)
            self.record_human_review_requirement(("STRATEGY", *owner))
            logger.warning(
                "phase8 protective failure scoped to (%s, %s); human review "
                "required; error count NOT incremented",
                *owner,
            )
            return ProtectiveSafetyOutcome(
                scoped_to_strategy=True,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                newly_halted=newly_halted,
                global_kill_switch_triggered=False,
            )

        # Ambiguous / integrity-uncertain ⇒ global fail closed.
        self.mark_cause_unsafe(
            Phase8GlobalCause.PROTECTIVE_AMBIGUITY,
            detail="ownership ambiguous or integrity unproven",
        )
        triggered = self._escalate_global(PROTECTIVE_AMBIGUITY_REASON_TOKEN)
        self.record_human_review_requirement(("GLOBAL",))
        return ProtectiveSafetyOutcome(
            scoped_to_strategy=False,
            strategy_id=None,
            strategy_version=None,
            newly_halted=False,
            global_kill_switch_triggered=triggered,
        )

    # ------------------------------------------------------------------
    # §128.11 / OD-7 — deterministic heartbeat / stale-data safety
    # ------------------------------------------------------------------

    @property
    def heartbeat_timeout_seconds(self) -> float | None:
        return self._heartbeat_timeout_seconds

    def observe_market_data_timestamp(
        self,
        *,
        latest_market_timestamp: datetime | None,
        reference_timestamp: datetime,
    ) -> HeartbeatEvaluation:
        """Deterministic staleness evaluation against canonical timestamps.

        Both timestamps are caller-supplied canonical market-time values; no
        wall clock is consulted.  With ``heartbeat_timeout_seconds`` unset
        (None), NO stale-data escalation ever occurs — the existing
        connection/fresh-market-evidence authority remains solely in force.
        Strictly greater than the timeout is stale; the exact boundary is
        NOT.  A fresh-again transition establishes RESUME ELIGIBILITY ONLY —
        it never clears a latch and never auto-resumes.
        """
        if latest_market_timestamp is not None:
            if (
                not isinstance(latest_market_timestamp, datetime)
                or latest_market_timestamp.tzinfo is None
            ):
                raise ValueError("latest_market_timestamp must be a tz-aware datetime")
        if (
            not isinstance(reference_timestamp, datetime)
            or reference_timestamp.tzinfo is None
        ):
            raise ValueError("reference_timestamp must be a tz-aware datetime")

        timeout = self._heartbeat_timeout_seconds
        if timeout is None or latest_market_timestamp is None:
            return HeartbeatEvaluation(
                configured_timeout_seconds=timeout,
                age_seconds=None,
                stale=self._stale_latched,
                stale_transition=False,
                fresh_transition=False,
                global_kill_switch_triggered=False,
            )

        age = (reference_timestamp - latest_market_timestamp).total_seconds()
        if age > timeout:
            first_stale = not self._stale_latched
            self._stale_latched = True
            triggered = False
            if first_stale:
                self.mark_cause_unsafe(
                    Phase8GlobalCause.STALE_MARKET_DATA,
                    detail=f"age_seconds={age}",
                )
                triggered = self._escalate_global(STALE_MARKET_DATA_REASON_TOKEN)
                logger.critical(
                    "phase8 stale-market-data safety trigger: age=%ss > timeout=%ss "
                    "— submissions blocked globally; manual review required",
                    age,
                    timeout,
                )
            return HeartbeatEvaluation(
                configured_timeout_seconds=timeout,
                age_seconds=age,
                stale=True,
                stale_transition=first_stale,
                fresh_transition=False,
                global_kill_switch_triggered=triggered,
            )

        fresh_transition = self._stale_latched
        if fresh_transition:
            self._stale_latched = False
            # Eligibility ONLY: the global kill switch stays latched until
            # explicit operator resume through the unified gate (§128.2/§128.7).
            self.mark_cause_healthy(Phase8GlobalCause.STALE_MARKET_DATA)
            logger.warning(
                "phase8 market data fresh again (age=%ss <= timeout=%ss): resume "
                "eligibility established only; latches unchanged",
                age,
                timeout,
            )
        return HeartbeatEvaluation(
            configured_timeout_seconds=timeout,
            age_seconds=age,
            stale=False,
            stale_transition=False,
            fresh_transition=fresh_transition,
            global_kill_switch_triggered=False,
        )

    # ------------------------------------------------------------------
    # Cause registry (unified global manual-review gate, §128.7)
    # ------------------------------------------------------------------

    def mark_cause_unsafe(self, cause: Phase8GlobalCause, *, detail: str | None = None) -> None:
        if not isinstance(cause, Phase8GlobalCause):
            raise TypeError("cause must be a Phase8GlobalCause")
        self._unsafe_causes[cause] = detail

    def mark_cause_healthy(self, cause: Phase8GlobalCause) -> None:
        if not isinstance(cause, Phase8GlobalCause):
            raise TypeError("cause must be a Phase8GlobalCause")
        self._unsafe_causes.pop(cause, None)

    # ------------------------------------------------------------------
    # §128.14 — human-review requirements recorded via the latch owner
    # ------------------------------------------------------------------

    @property
    def pending_human_reviews(self) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted(self._pending_human_reviews))

    def record_human_review_requirement(self, scope: tuple[str, ...]) -> None:
        """Record one pending human-review requirement at the given scope."""
        if (
            not isinstance(scope, tuple)
            or not scope
            or any(not isinstance(part, str) or not part.strip() for part in scope)
        ):
            raise ValueError("scope must be a non-empty tuple of non-empty strings")
        self._pending_human_reviews.add(tuple(scope))

    def resolve_human_review_requirement(
        self,
        scope: tuple[str, ...],
        *,
        operator_id: str,
    ) -> bool:
        """Explicitly resolve one pending human-review requirement.

        Operator identity is mandatory.  Resolving a review establishes
        eligibility only and never clears any halt latch.
        """
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ValueError("operator_id is required to resolve a human review")
        normalized = tuple(scope)
        if normalized not in self._pending_human_reviews:
            return False
        self._pending_human_reviews.discard(normalized)
        return True

    def request_global_resume(
        self,
        *,
        operator_id: str,
        extra_failed_prerequisites: tuple[str, ...] = (),
    ) -> GlobalResumeDecision:
        """Explicit operator global resume through the unified gate.

        Approved ONLY when every registered Phase-8 cause is healthy AND the
        caller-supplied external prerequisite probe reports no failures.
        Approval establishes ELIGIBILITY; the actual resume execution remains
        owned by the canonical coordinator resume path.
        """
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ValueError("operator_id is required for global resume")
        failed: list[str] = [f"unsafe_cause:{cause.value}" for cause in self.unsafe_causes]
        # §128.14: any pending human-review requirement blocks global resume.
        failed.extend(
            f"pending_human_review:{':'.join(scope)}" for scope in self.pending_human_reviews
        )
        failed.extend(extra_failed_prerequisites)
        return GlobalResumeDecision(
            approved=not failed,
            operator_id=operator_id,
            failed_prerequisites=tuple(failed),
        )

    # ------------------------------------------------------------------
    # OD-1C / OD-3 — isolated strategy exceptions + shared threshold
    # ------------------------------------------------------------------

    def observe_strategy_exception(
        self, strategy_id: str, strategy_version: str
    ) -> StrategyEscalationOutcome:
        """Isolated exception ⇒ halt that strategy only; escalate at threshold."""
        owner = (strategy_id, strategy_version)
        newly_halted = True
        if self._halt_strategy is not None:
            newly_halted = bool(self._halt_strategy(strategy_id, strategy_version))
        count_before = self._session_error_count
        self._session_error_count = count_before + 1
        global_triggered = False
        if self._session_error_count >= self.strategy_error_kill_threshold:
            global_triggered = self._escalate_global(STRATEGY_ERROR_THRESHOLD_REASON_TOKEN)
        if newly_halted or owner not in self._halted_owners:
            self._merge_and_persist(owner)
        else:
            self._merge_and_persist(None)
        return StrategyEscalationOutcome(
            owner_newly_halted=newly_halted,
            session_error_count=self._session_error_count,
            threshold=self.strategy_error_kill_threshold,
            global_kill_switch_triggered=global_triggered,
        )

    # ------------------------------------------------------------------
    # OD-6 — explicit per-strategy manual resume
    # ------------------------------------------------------------------

    def request_strategy_resume(
        self,
        strategy_id: str,
        strategy_version: str,
        *,
        operator_id: str,
        extra_failed_prerequisites: tuple[str, ...] = (),
    ) -> GlobalResumeDecision:
        """Explicit operator resume for ONE strategy at the affected scope.

        Requires explicit operator identity and clean prerequisites at the
        affected scope: NO unsafe global Phase-8 cause may be active.  On
        approval the affected owner's latch is cleared and durably persisted;
        the global kill switch and every other owner's latch remain untouched.
        """
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ValueError("operator_id is required for strategy resume")
        owner = (strategy_id, strategy_version)
        failed: list[str] = [f"unsafe_cause:{cause.value}" for cause in self.unsafe_causes]
        # §128.6: a per-strategy resume is illegal while any GLOBAL safety
        # condition is active — unaffected strategies may continue on their
        # own, but a halted strategy stays halted until the global condition
        # is resolved AND explicit operator resume is granted.
        if self._global_condition_active():
            failed.append("global_safety_condition_active")
        # §128.14: pending human reviews block the affected scope (or all
        # scopes when a GLOBAL review is pending).
        for scope in self.pending_human_reviews:
            if scope == ("GLOBAL",) or scope == ("STRATEGY", strategy_id, strategy_version):
                failed.append(f"pending_human_review:{':'.join(scope)}")
        failed.extend(extra_failed_prerequisites)
        if owner not in self._halted_owners:
            return GlobalResumeDecision(
                approved=False,
                operator_id=operator_id,
                failed_prerequisites=("strategy_not_halted",),
            )
        if failed:
            return GlobalResumeDecision(
                approved=False,
                operator_id=operator_id,
                failed_prerequisites=tuple(failed),
            )
        remaining = {o for o in self._halted_owners if o != owner}
        previous = tuple(sorted(self._halted_owners))
        # PHASE 8 P2 — ATOMIC RESUME ORDERING (frozen):
        #
        #   validate gates (above)
        #   → STEP 1: durable persistence of the approved resume set
        #   → STEP 2: runtime publication through the EXISTING narrow
        #     coordinator API (LiveStrategyCoordinator.clear_strategy_halt)
        #   → STEP 3: controller eligibility mirror LAST
        #
        # No success is reported before all three steps succeed.  Because the
        # runtime latch only clears after the durable commit, a strategy can
        # never become runtime-active while durable resume persistence failed;
        # and because this sequence is synchronous within the frozen
        # single-threaded runtime model, no interleaving window exists in which
        # an unsafe entry could be admitted mid-resume.
        if self._persist_halted_owners is not None:
            # STEP 1 (§128.10): a failed authoritative write raises; the
            # controller mirror and the runtime latch both remain halted.
            self._persist_halted_owners(tuple(sorted(remaining)))
        # STEP 2: publish to the RUNTIME authority.  Publication failure
        # (False or exception) is compensated: the durable authority is rolled
        # back to the exact pre-request halted set so durable == mirror ==
        # runtime == HALTED, and the decision reports BLOCKED — never a false
        # success.  Restart after a crash in this window reconciles from the
        # durable authority (§128.8 recovery contract).
        runtime_cleared = True
        if self._resume_strategy_runtime is not None:
            try:
                runtime_cleared = bool(
                    self._resume_strategy_runtime(strategy_id, strategy_version)
                )
            except Exception as pub_exc:
                self._compensate_failed_strategy_resume_publication(
                    previous, strategy_id, strategy_version, cause=pub_exc,
                )
                return GlobalResumeDecision(
                    approved=False,
                    operator_id=operator_id,
                    failed_prerequisites=("runtime_publication_failed",),
                )
            if not runtime_cleared:
                self._compensate_failed_strategy_resume_publication(
                    previous, strategy_id, strategy_version, cause=None,
                )
                return GlobalResumeDecision(
                    approved=False,
                    operator_id=operator_id,
                    failed_prerequisites=("runtime_publication_failed",),
                )
        # STEP 3 (LAST): the controller eligibility view may only move after
        # BOTH the durable authority AND the runtime gating authority have
        # confirmed the removal.  On every failure path above the owner remains
        # visible as halted in all three authorities.
        self._halted_owners = remaining
        logger.warning(
            "phase8 strategy resume: operator=%s resumed (%s, %s); "
            "runtime_cleared=%s; global latches untouched",
            operator_id,
            strategy_id,
            strategy_version,
            runtime_cleared,
        )
        return GlobalResumeDecision(approved=True, operator_id=operator_id, failed_prerequisites=())

    def _compensate_failed_strategy_resume_publication(
        self,
        previous: tuple[tuple[str, str], ...],
        strategy_id: str,
        strategy_version: str,
        *,
        cause: BaseException | None,
    ) -> None:
        """Roll the durable authority back to the exact pre-request set.

        Runtime publication failed AFTER the durable commit, so without
        compensation the durable state would say ``resumed`` while the runtime
        authority still gates the owner.  Compensation restores
        durable == mirror == runtime (all HALTED): a fully fail-closed,
        deterministically retryable state with no false success reported.
        The controller mirror is deliberately untouched here — it never moved,
        because step 3 runs only after successful publication.  A rollback
        write failure propagates per the §128.10 terminal contract; the
        runtime latch remains halted regardless, and restart reconciles from
        the last durable authority deterministically.
        """
        logger.critical(
            "phase8 strategy resume runtime-publication FAILED for (%s, %s); "
            "durable halted-set rolled back to pre-request value; owner "
            "remains HALTED everywhere; global latches untouched; cause=%r",
            strategy_id,
            strategy_version,
            cause,
        )
        if self._persist_halted_owners is not None:
            self._persist_halted_owners(previous)

    # ------------------------------------------------------------------
    # Durability mirror hydration (restart contract, §128.8)
    # ------------------------------------------------------------------

    def hydrate_halted_owners(
        self, owners: Iterable[tuple[str, str]]
    ) -> None:
        """Hydrate the durable mirror BEFORE strategy eligibility (restart)."""
        validated = _validate_owner_tuples(owners)
        self._halted_owners.update(validated)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _global_condition_active(self) -> bool:
        """True while a GLOBAL safety condition is active (probe-first)."""
        if self._global_kill_switch_active_probe is not None:
            return bool(self._global_kill_switch_active_probe())
        return bool(self._global_escalated_causes)

    def notify_global_resume_completed(self) -> None:
        """Record that the canonical global resume path actually executed.

        The coordinator's ``resume_from_kill_switch`` remains the resume
        authority; when it succeeds, the runtime wiring calls this so the
        controller's fallback view (used when no live kill-switch probe is
        wired) stops treating prior escalations as still-active conditions.
        """
        self._global_escalated_causes.clear()

    def _merge_and_persist(self, new_owner: tuple[str, str] | None) -> None:
        if new_owner is not None:
            self._halted_owners.add(new_owner)
        if self._persist_halted_owners is not None:
            # §128.10: authoritative write failures propagate (fail closed);
            # the in-memory latch remains and the last durable set is intact,
            # so restart can never silently lose a halt.
            self._persist_halted_owners(self.halted_owners)

    def _escalate_global(self, reason_token: str) -> bool:
        """Route ONE global escalation through the injected canonical activator."""
        already = reason_token in self._global_escalated_causes
        self._global_escalated_causes.add(reason_token)
        self._activate_global(reason_token)
        logger.critical(
            "phase8 GLOBAL kill-switch escalation requested: reason=%s repeat=%s",
            reason_token,
            already,
        )
        return True
