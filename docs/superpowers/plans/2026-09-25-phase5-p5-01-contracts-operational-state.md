# Phase 5 P5-01 Contracts + Operational State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Phase-5 paper-domain contracts and canonical operational-state machine, including the sticky manual-resume latch, with deterministic validation and no broker/live mutation path.

**Architecture:** Add two focused modules under `engine/paper/`: `contracts_v2.py` for immutable domain records/enums and `operational_state_v2.py` for state-transition authority. Keep persistence, reconciliation, alerts, Windows APIs, Telegram, and broker adapters out of these modules. Tests live in `tests_v1/` and use only pure in-memory values.

**Tech Stack:** Python 3.13, stdlib `dataclasses`, `enum`, `datetime`, `decimal`; pytest; existing AlgoFortis canonical validation conventions.

**Spec:** `docs/v2/phase5/PHASE5_PAPER_RECOVERY_DESIGN.md`

## Global Constraints

- Live remains `READ_ONLY/DISARMED`; P5-01 introduces no real-broker mutation or arming path.
- `HALT_ENTRIES` is an action; `HALTED` is a sticky operational state.
- Canonical states are exactly `HEALTHY`, `DEGRADED`, `HALTED`, `RECOVERY`, `READY_FOR_RESUME`.
- State-continuity uncertainty may jump directly to `RECOVERY`.
- `HALTED` cannot clear automatically; `READY_FOR_RESUME` requires an explicit manual-resume authority before returning to `HEALTHY`.
- `FailureIncident` explicitly carries `previous_state`, `resulting_state`, `transition_reason`, `recovery_id`, and `storm_policy_ref` in addition to its core incident fields.
- Missing/invalid safety values fail closed through validation errors; no guessed production storm/clock thresholds are introduced.
- Pure Phase-5 paper domain modules must not import SQLite, Telegram, Windows APIs, or real broker adapters.
- Decimal/fixed-point policy remains binding for money, price, quantity, and risk-like numeric values.

## Review Focus

1. Invalid/blank identifiers or timezone-naive timestamps must be rejected rather than normalized silently — pinned in Task 1 validation tests.
2. `FailureIncident` must reject a `resulting_state` that contradicts the supplied transition target type/value — pinned in Task 1 enum/type tests and Task 2 transition recording tests.
3. A crash/restart-style continuity failure must be able to transition `HEALTHY -> RECOVERY` directly without passing through `DEGRADED` or `HALTED` — pinned in Task 2.
4. A sticky `HALTED` state must never return to `HEALTHY` without first reaching `READY_FOR_RESUME` and consuming explicit manual-resume authority — pinned in Task 2.
5. A denied/blank manual-resume authority reference must fail closed and leave state unchanged — pinned in Task 2.

---

### Task 1: Phase-5 paper contracts

**Files:**
- Create: `engine/paper/contracts_v2.py`
- Create: `tests_v1/test_phase5_contracts.py`

**Interfaces:**
- Consumes: stdlib-only validation primitives; existing project import style.
- Produces:
  - `PaperMode.PAPER`
  - `PaperOperationalState` enum with `HEALTHY`, `DEGRADED`, `HALTED`, `RECOVERY`, `READY_FOR_RESUME`
  - `FailureSeverity` enum with `INFO`, `WARNING`, `CRITICAL`, `RECOVERY_REQUIRED`
  - `PaperSession`
  - `PaperOrderRecord`
  - `PaperPositionRecord`
  - `RecoveryCheckpoint`
  - `FailureIncident`
  - `AlertDeliveryRecord`
  - `RecoveryReport`
  - `FailureInjectionResult`

- [ ] **Step 1: Write the failing contract tests**

Create `tests_v1/test_phase5_contracts.py` with tests that import the symbols above and assert at minimum:

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.paper.contracts_v2 import (
    AlertDeliveryRecord,
    FailureIncident,
    FailureSeverity,
    PaperMode,
    PaperOperationalState,
    PaperOrderRecord,
    PaperPositionRecord,
    PaperSession,
    RecoveryCheckpoint,
)

UTC_NOW = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)


def test_phase5_state_vocabulary_is_closed():
    assert tuple(state.value for state in PaperOperationalState) == (
        "HEALTHY",
        "DEGRADED",
        "HALTED",
        "RECOVERY",
        "READY_FOR_RESUME",
    )


def test_failure_incident_carries_traceability_fields():
    incident = FailureIncident(
        incident_id="incident-1",
        failure_type="PROCESS_CRASH",
        severity=FailureSeverity.RECOVERY_REQUIRED,
        detected_at=UTC_NOW,
        source="paper-session",
        affected_scope="session-1",
        previous_state=PaperOperationalState.HEALTHY,
        resulting_state=PaperOperationalState.RECOVERY,
        transition_reason="PROCESS_CRASH",
        halt_latched=True,
        recovery_id="recovery-1",
        storm_policy_ref=None,
        resolved_at=None,
        resolution_evidence=None,
    )
    assert incident.previous_state is PaperOperationalState.HEALTHY
    assert incident.resulting_state is PaperOperationalState.RECOVERY
    assert incident.recovery_id == "recovery-1"
    assert incident.storm_policy_ref is None


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        PaperSession(
            session_id="session-1",
            mode=PaperMode.PAPER,
            started_at=datetime(2026, 1, 5, 9, 30),
            trading_date="2026-01-05",
            session_state=PaperOperationalState.HEALTHY,
            config_snapshot_ref="config@v1",
            strategy_versions=("orb@v2",),
            risk_policy_version="risk@v2",
            instrument_master_version="im@v1",
            failure_policy_version="failure@v1",
        )


def test_blank_ids_are_rejected():
    with pytest.raises(ValueError, match="session_id"):
        PaperSession(
            session_id=" ",
            mode=PaperMode.PAPER,
            started_at=UTC_NOW,
            trading_date="2026-01-05",
            session_state=PaperOperationalState.HEALTHY,
            config_snapshot_ref="config@v1",
            strategy_versions=("orb@v2",),
            risk_policy_version="risk@v2",
            instrument_master_version="im@v1",
            failure_policy_version="failure@v1",
        )


def test_order_quantity_and_fill_are_decimal_and_bounded():
    with pytest.raises(ValueError, match="cumulative_fill"):
        PaperOrderRecord(
            logical_intent_id="intent-1",
            approved_order_id="approved-1",
            instrument="NIFTY26JAN25000CE",
            side="BUY",
            quantity=Decimal("50"),
            lifecycle_state="FILLED",
            cumulative_fill=Decimal("51"),
            submitted_at=UTC_NOW,
            last_observed_at=UTC_NOW,
            last_observation_sequence=1,
            terminal_reason=None,
        )


def test_position_requires_positive_quantity_and_protective_policy():
    with pytest.raises(ValueError, match="quantity"):
        PaperPositionRecord(
            position_id="position-1",
            instrument="NIFTY26JAN25000CE",
            quantity=Decimal("0"),
            average_price=Decimal("100.00"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            protective_policy_ref="orb-protective@test-v1",
            protective_state="VALID",
            expiry_metadata="2026-01-29",
            session_metadata="2026-01-05",
        )


def test_checkpoint_sequence_must_be_non_negative():
    with pytest.raises(ValueError, match="last_event_sequence"):
        RecoveryCheckpoint(
            checkpoint_id="checkpoint-1",
            session_id="session-1",
            persisted_at=UTC_NOW,
            last_event_sequence=-1,
            open_order_refs=(),
            open_position_refs=(),
            recovery_required=True,
            reason="PROCESS_CRASH",
            fingerprint="a" * 64,
        )


def test_alert_record_has_independent_channel_status():
    record = AlertDeliveryRecord(
        alert_id="alert-1",
        incident_id="incident-1",
        channel="telegram",
        attempt=1,
        delivery_status="FAILED",
        failure_reason="network",
        attempted_at=UTC_NOW,
        completed_at=UTC_NOW,
    )
    assert record.channel == "telegram"
    assert record.delivery_status == "FAILED"
```

Also add direct construction smoke tests for `RecoveryReport` and `FailureInjectionResult` so every public record is instantiated at least once.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
pytest tests_v1/test_phase5_contracts.py -q
```

Expected: collection/import failure because `engine.paper.contracts_v2` does not exist yet.

- [ ] **Step 3: Implement the minimal immutable contracts**

Create `engine/paper/contracts_v2.py` using `@dataclass(frozen=True, slots=True)` records and closed enums. Implement small private validators:

```python
def _require_text(value: str, field: str) -> str: ...
def _require_aware(dt: datetime, field: str) -> datetime: ...
def _require_decimal(value: Decimal, field: str) -> Decimal: ...
def _require_non_negative_int(value: int, field: str) -> int: ...
```

Required behavior:
- reject blank identifiers/required refs;
- reject timezone-naive timestamps;
- require actual `Decimal` for quantity/price/P&L fields;
- require positive order/position quantities;
- require `0 <= cumulative_fill <= quantity`;
- require non-negative observation/event sequences;
- require enum instances for mode/state/severity fields;
- permit nullable `recovery_id`, `storm_policy_ref`, resolution fields, terminal reason, and alert failure reason where the spec allows them;
- never import persistence, broker, alerts, host, or live modules.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
pytest tests_v1/test_phase5_contracts.py -q
```

Expected: all tests in the file PASS.

- [ ] **Step 5: Run relevant regression tests**

Run:

```bash
pytest tests_v1/test_architectural_foundations.py tests_v1/test_area12_broker_execution_adapters.py tests_v1/test_area14_live_reconciliation_restart.py -q
```

Expected: PASS with no new failure.

- [ ] **Step 6: Commit Task 1**

```bash
git add engine/paper/contracts_v2.py tests_v1/test_phase5_contracts.py
git commit -m "feat: add Phase 5 paper domain contracts"
```

---

### Task 2: Canonical operational state machine + manual-resume latch

**Files:**
- Create: `engine/paper/operational_state_v2.py`
- Create: `tests_v1/test_phase5_operational_state.py`

**Interfaces:**
- Consumes: `PaperOperationalState` from `engine.paper.contracts_v2`.
- Produces:
  - `PaperTransitionReason`
  - `PaperStateTransitionError`
  - `ManualResumeAuthority` Protocol
  - `PaperOperationalStateMachine.state`
  - `PaperOperationalStateMachine.halt_entries(reason=...)`
  - `PaperOperationalStateMachine.degrade(reason=...)`
  - `PaperOperationalStateMachine.require_recovery(reason=...)`
  - `PaperOperationalStateMachine.mark_ready_for_resume(reason=...)`
  - `PaperOperationalStateMachine.resume(authority=..., reason=...)`

- [ ] **Step 1: Write failing state-machine tests**

Create `tests_v1/test_phase5_operational_state.py` with tests equivalent to:

```python
from dataclasses import dataclass

import pytest

from engine.paper.contracts_v2 import PaperOperationalState
from engine.paper.operational_state_v2 import (
    PaperOperationalStateMachine,
    PaperStateTransitionError,
    PaperTransitionReason,
)


@dataclass(frozen=True)
class _Authority:
    allowed: bool
    reference: str


def test_continuity_failure_can_jump_healthy_directly_to_recovery():
    machine = PaperOperationalStateMachine()
    assert machine.require_recovery(reason=PaperTransitionReason.PROCESS_CRASH) is PaperOperationalState.RECOVERY


def test_halt_entries_is_action_that_produces_sticky_halted_state():
    machine = PaperOperationalStateMachine()
    assert machine.halt_entries(reason=PaperTransitionReason.RECONCILIATION_MISMATCH) is PaperOperationalState.HALTED
    with pytest.raises(PaperStateTransitionError, match="manual resume"):
        machine.resume(authority=_Authority(True, "owner-1"), reason=PaperTransitionReason.MANUAL_RESUME)
    assert machine.state is PaperOperationalState.HALTED


def test_recovery_must_be_marked_ready_before_manual_resume():
    machine = PaperOperationalStateMachine()
    machine.require_recovery(reason=PaperTransitionReason.RESTART_WITH_OPEN_STATE)
    machine.mark_ready_for_resume(reason=PaperTransitionReason.RECOVERY_CHECKS_CLEAN)
    assert machine.state is PaperOperationalState.READY_FOR_RESUME
    assert machine.resume(
        authority=_Authority(True, "owner-resume-1"),
        reason=PaperTransitionReason.MANUAL_RESUME,
    ) is PaperOperationalState.HEALTHY


def test_denied_resume_authority_fails_closed_and_keeps_ready_state():
    machine = PaperOperationalStateMachine(initial_state=PaperOperationalState.READY_FOR_RESUME)
    with pytest.raises(PaperStateTransitionError, match="denied"):
        machine.resume(
            authority=_Authority(False, "owner-resume-denied"),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )
    assert machine.state is PaperOperationalState.READY_FOR_RESUME


def test_blank_resume_authority_reference_is_rejected():
    machine = PaperOperationalStateMachine(initial_state=PaperOperationalState.READY_FOR_RESUME)
    with pytest.raises(PaperStateTransitionError, match="reference"):
        machine.resume(
            authority=_Authority(True, " "),
            reason=PaperTransitionReason.MANUAL_RESUME,
        )
    assert machine.state is PaperOperationalState.READY_FOR_RESUME


def test_transient_degradation_can_clear_only_when_no_sticky_halt_was_entered():
    machine = PaperOperationalStateMachine()
    machine.degrade(reason=PaperTransitionReason.TRANSIENT_FEED_LATENCY)
    assert machine.clear_degradation(reason=PaperTransitionReason.DEGRADATION_CLEARED) is PaperOperationalState.HEALTHY


def test_halted_can_escalate_to_recovery_without_auto_clear():
    machine = PaperOperationalStateMachine()
    machine.halt_entries(reason=PaperTransitionReason.CLOCK_UNHEALTHY)
    assert machine.require_recovery(reason=PaperTransitionReason.STATE_CONTINUITY_UNCERTAIN) is PaperOperationalState.RECOVERY
```

- [ ] **Step 2: Run focused state tests and verify RED**

Run:

```bash
pytest tests_v1/test_phase5_operational_state.py -q
```

Expected: import failure because `engine.paper.operational_state_v2` does not exist.

- [ ] **Step 3: Implement the minimal state authority**

Create `engine/paper/operational_state_v2.py` with a closed `PaperTransitionReason` enum containing at least:

```text
PROCESS_CRASH
RESTART_WITH_OPEN_STATE
SLEEP_RESUME_DISCONTINUITY
UNCERTAIN_ACKNOWLEDGEMENT
PARTIAL_STATE_UNCERTAINTY
STATE_CONTINUITY_UNCERTAIN
TRANSIENT_FEED_LATENCY
DEGRADATION_CLEARED
RECONCILIATION_MISMATCH
PROTECTIVE_INTEGRITY_FAILURE
CLOCK_UNHEALTHY
STALE_FEED
STORM_THRESHOLD_CROSSED
RECOVERY_CHECKS_CLEAN
MANUAL_RESUME
```

Implement only the approved transitions:

```text
HEALTHY -> DEGRADED
HEALTHY -> HALTED
HEALTHY -> RECOVERY
DEGRADED -> HEALTHY        # only clear_degradation
DEGRADED -> HALTED
DEGRADED -> RECOVERY
HALTED -> RECOVERY
HALTED -> READY_FOR_RESUME # automated checks prove safe-to-resume
RECOVERY -> HALTED         # checks fail / mismatch remains
RECOVERY -> READY_FOR_RESUME
READY_FOR_RESUME -> HALTED # a new safety failure arrives before resume
READY_FOR_RESUME -> RECOVERY
READY_FOR_RESUME -> HEALTHY # resume() only with explicit allowed authority
```

Public methods enforce action semantics rather than exposing a generic unrestricted transition API. `resume()` must require `MANUAL_RESUME`, `allowed is True`, and a non-blank authority reference. State mutates only after all validation succeeds.

- [ ] **Step 4: Run focused state tests and verify GREEN**

Run:

```bash
pytest tests_v1/test_phase5_operational_state.py -q
```

Expected: PASS.

- [ ] **Step 5: Run P5-01 focused suite together**

Run:

```bash
pytest tests_v1/test_phase5_contracts.py tests_v1/test_phase5_operational_state.py -q
```

Expected: PASS.

- [ ] **Step 6: Run full repository regression**

Run:

```bash
pytest tests_v1 -q
```

Expected: existing suite plus P5-01 tests PASS; any pre-existing skipped tests remain skipped.

- [ ] **Step 7: Commit Task 2**

```bash
git add engine/paper/operational_state_v2.py tests_v1/test_phase5_operational_state.py
git commit -m "feat: add Phase 5 paper operational state machine"
```

---

### Task 3: P5-01 boundary guard and exact-slice verification

**Files:**
- Create: `build/tools/check_phase5_paper_recovery.py`
- Create: `tests_v1/test_phase5_architecture_guard.py`

**Interfaces:**
- Consumes: source paths from Tasks 1–2.
- Produces: deterministic static checker executable with `python -m build.tools.check_phase5_paper_recovery`.

- [ ] **Step 1: Write failing architecture-guard tests**

Create tests that require the checker to:
- pin `engine/paper/contracts_v2.py`, `engine/paper/operational_state_v2.py`, and the three P5-01 tests;
- reject imports in P5-01 production modules rooted at `engine.broker_adapters`, `engine.live`, `sqlite3`, `requests`, `httpx`, `telegram`, `win32api`, or `win32con`;
- reject literal production storm-threshold configuration names/constants in these P5-01 files;
- assert `PaperOperationalState` has exactly the five approved values.

- [ ] **Step 2: Run guard test and verify RED**

Run:

```bash
pytest tests_v1/test_phase5_architecture_guard.py -q
```

Expected: import/module failure because `build.tools.check_phase5_paper_recovery` does not exist.

- [ ] **Step 3: Implement minimal static checker**

Use `ast` to parse only the P5-01 production modules at this slice. Exit non-zero / raise a clear exception for forbidden imports, missing required files, or state-vocabulary drift. Keep the checker extensible for later P5 slices without prematurely pinning files that do not exist yet.

- [ ] **Step 4: Run guard + focused suite GREEN**

Run:

```bash
python -m build.tools.check_phase5_paper_recovery
pytest tests_v1/test_phase5_contracts.py tests_v1/test_phase5_operational_state.py tests_v1/test_phase5_architecture_guard.py -q
```

Expected: checker prints PASS and tests PASS.

- [ ] **Step 5: Run full regression**

Run:

```bash
pytest tests_v1 -q
```

Expected: PASS with only known/intentional skips.

- [ ] **Step 6: Commit Task 3**

```bash
git add build/tools/check_phase5_paper_recovery.py tests_v1/test_phase5_architecture_guard.py
git commit -m "ci: guard Phase 5 paper recovery boundaries"
```

## P5-01 Completion Contract

P5-01 is complete only when:

- all public P5-01 contracts exist and validate fail-closed;
- `FailureIncident` includes all approved traceability fields;
- branching operational transitions match the approved design;
- `HALT_ENTRIES` action produces sticky `HALTED` state;
- continuity uncertainty can directly enter `RECOVERY`;
- `READY_FOR_RESUME -> HEALTHY` requires explicit manual authority;
- no P5-01 module imports broker/live/persistence/network/Windows concrete integrations;
- focused tests and full `tests_v1` pass on the exact head;
- Phase-5 static checker passes;
- Live remains `READ_ONLY/DISARMED`.
