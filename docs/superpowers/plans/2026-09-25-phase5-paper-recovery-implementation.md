# AlgoFortis Phase 5 Paper Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 5 Paper V2 recovery, reconciliation, failure simulation, host resilience, independent alerts, and deterministic G5 evidence while preserving Live `READ_ONLY/DISARMED` and zero real-broker mutation.

**Architecture:** Extend the existing Paper engine through focused V2 modules rather than rewriting `engine/paper/coordinator.py` or `engine/persistence/sqlite_store.py`. Pure domain code depends on Protocols; SQLite, Windows host services, Telegram, and existing reconciliation remain adapters. Recovery is branching and fail-closed: continuity uncertainty may jump directly to `RECOVERY`; sticky safety conditions use `HALT_ENTRIES` and `HALTED`; successful automated checks end at `READY_FOR_RESUME` and require manual resume.

**Tech Stack:** Python 3.13, pytest, dataclasses/enums/typing.Protocol, SQLite through the existing persistence layer, Windows-specific adapters behind test doubles, GitHub Actions dual-Windows qualification.

**Spec:** `docs/v2/phase5/PHASE5_PAPER_RECOVERY_DESIGN.md`

## Global Constraints

- Live remains `READ_ONLY/DISARMED`; Phase 5 introduces no real-broker mutation path.
- Paper cannot import or call real broker mutation adapters.
- No executable path bypasses RiskGate/ApprovedOrder authority.
- No duplicate logical submission after restart/recovery.
- No stale signal/intent replay after restart, delay, reconnect, rollover, or recovery.
- `IN_DOUBT`/uncertain submissions are reconciled before retry.
- Reconciliation CLEAN is not sufficient for resume; protective integrity and health checks are independent gates.
- Sticky safety halts never auto-clear; `READY_FOR_RESUME` requires explicit manual resume.
- Missing/invalid/corrupt safety policy fails closed.
- No guessed production storm threshold, clock-drift limit, promotion tolerance, drift tolerance, or hardware minimum.
- OD-V2-19: local Windows-visible + Telegram critical alert paths are independent; payloads are redacted; heartbeat remains deferred.
- OD-V2-24: Windows 11 x64 first-class target; single engine instance; sleep/resume forces recovery; watchdog restarts only into recovery; antivirus need not be disabled.
- Existing giant files receive only minimal wiring changes.

## Review Focus

1. **Uncertain submission around crash:** expected behavior is no blind retry, no duplicate, and recovery/reconciliation before any submission permission is restored. Covered in Task 4 and Task 10.
2. **CLEAN reconciliation with broken protection:** expected behavior is `HALT_ENTRIES` → `HALTED`, never resume. Covered in Task 5.
3. **Missing/corrupt storm policy:** expected behavior is no unlimited retry; fail closed with incident/audit evidence. Covered in Task 6.
4. **One alert adapter crashes while another is healthy:** expected behavior is the second channel is still attempted and trading safety remains latched. Covered in Task 8.
5. **Expiry/session rollover with an open option and missing expiry policy:** expected behavior is halt + alert; no invented auto-flatten or silent carry. Covered in Task 5.

---

## File Structure

### Create

- `engine/paper/contracts_v2.py` — Phase-5 immutable domain records and enums.
- `engine/paper/operational_state_v2.py` — branching operational state machine and manual-resume latch.
- `engine/paper/execution_adapter_v2.py` — paper-only approved-order execution boundary.
- `engine/paper/fill_simulator_v2.py` — deterministic conservative fill simulation.
- `engine/paper/failure_policy_v2.py` — versioned storm policy/evaluator.
- `engine/paper/protective_integrity_v2.py` — independent protective-state verdict.
- `engine/paper/recovery_coordinator_v2.py` — restore/reconcile/protective/health/session orchestration.
- `engine/paper/session_v2.py` — thin session authority and failure routing.
- `engine/paper/drift_report_v2.py` — paper-vs-backtest drift records/reporting.
- `engine/paper/evidence_v2.py` — recovery/FI/G5 deterministic evidence.
- `engine/persistence/paper_session_store_v2.py` — Paper session/order/position persistence port adapter.
- `engine/persistence/paper_recovery_store_v2.py` — checkpoints/recovery reports.
- `engine/persistence/paper_incident_store_v2.py` — incidents/alert delivery records.
- `engine/host/__init__.py`, `instance_lock.py`, `clock_health.py`, `power_session.py`, `watchdog_policy.py` — host-safety adapters/policies.
- `engine/alerts/contracts.py`, `dispatcher.py`, `redaction.py`, `adapters/__init__.py`, `adapters/windows_local.py`, `adapters/telegram.py` — independent notifier layer.
- `build/tools/check_phase5_paper_recovery.py` — architecture/static safety gate.
- Focused tests under `tests_v1/test_phase5_*.py` listed per task below.

### Modify minimally

- `engine/persistence/schema.py` — add Phase-5 schema definitions.
- `engine/persistence/migrations.py` — add one forward migration for Phase-5 tables/indexes.
- `engine/persistence/sqlite_store.py` — only small generic execution hooks if required by existing store pattern; no recovery decisions.
- `engine/paper/coordinator.py` and/or `engine/paper/live_runner.py` — only final wiring seam after focused modules are green.
- Existing Phase-4/CI workflow files — add Phase-5 static/focused/deterministic qualification without removing prior gates.

---

### Task 1: P5-01 Contracts + operational state

**Files:**
- Create: `engine/paper/contracts_v2.py`
- Create: `engine/paper/operational_state_v2.py`
- Test: `tests_v1/test_phase5_operational_state.py`

**Interfaces:**
- Produces `OperationalState(Enum)` with `HEALTHY`, `DEGRADED`, `HALTED`, `RECOVERY`, `READY_FOR_RESUME`.
- Produces `IncidentSeverity(Enum)` with `INFO`, `WARNING`, `CRITICAL`, `RECOVERY_REQUIRED`.
- Produces frozen dataclasses `PaperSession`, `PaperOrderRecord`, `PaperPositionRecord`, `RecoveryCheckpoint`, `FailureIncident`, `AlertDeliveryRecord`, `RecoveryReport`, `FailureInjectionResult`.
- `FailureIncident` fields MUST include `previous_state`, `resulting_state`, `transition_reason`, nullable `recovery_id`, nullable `storm_policy_ref`.
- Produces `OperationalStateController(state: OperationalState)` with `degrade(reason)`, `halt_entries(reason)`, `enter_recovery(reason)`, `mark_ready_for_resume(reason)`, `manual_resume()`.

- [ ] **Step 1: Write RED tests for records and direct recovery transition**

```python
from dataclasses import FrozenInstanceError
from engine.paper.contracts_v2 import FailureIncident, IncidentSeverity
from engine.paper.operational_state_v2 import OperationalState, OperationalStateController


def test_crash_can_jump_directly_from_healthy_to_recovery():
    sm = OperationalStateController(OperationalState.HEALTHY)
    sm.enter_recovery("process_crash")
    assert sm.state is OperationalState.RECOVERY


def test_failure_incident_carries_transition_traceability():
    incident = FailureIncident(
        incident_id="inc-1",
        failure_type="PROCESS_CRASH",
        severity=IncidentSeverity.RECOVERY_REQUIRED,
        detected_at="2026-09-25T16:00:00Z",
        source="paper",
        affected_scope="session:s1",
        previous_state=OperationalState.HEALTHY,
        resulting_state=OperationalState.RECOVERY,
        transition_reason="process_crash",
        halt_latched=True,
        recovery_id="rec-1",
        storm_policy_ref=None,
        resolved_at=None,
        resolution_evidence=None,
    )
    assert incident.resulting_state is OperationalState.RECOVERY
    assert incident.recovery_id == "rec-1"
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests_v1/test_phase5_operational_state.py -q`
Expected: FAIL because Phase-5 modules do not exist.

- [ ] **Step 3: Implement minimal immutable contracts and state controller**

State rules to encode exactly:

```python
HEALTHY -> DEGRADED | HALTED | RECOVERY
DEGRADED -> HEALTHY | HALTED | RECOVERY
HALTED -> RECOVERY | READY_FOR_RESUME
RECOVERY -> HALTED | READY_FOR_RESUME
READY_FOR_RESUME -> HEALTHY  # only through manual_resume()
```

`mark_ready_for_resume()` must reject direct use from `HEALTHY`/`DEGRADED`; `manual_resume()` must reject every state except `READY_FOR_RESUME`.

- [ ] **Step 4: Add RED tests for sticky halt/manual resume**

```python
import pytest


def test_halted_never_auto_clears():
    sm = OperationalStateController(OperationalState.HEALTHY)
    sm.halt_entries("clock_bad")
    assert sm.state is OperationalState.HALTED
    with pytest.raises(ValueError):
        sm.manual_resume()


def test_ready_for_resume_requires_explicit_manual_resume():
    sm = OperationalStateController(OperationalState.RECOVERY)
    sm.mark_ready_for_resume("all_checks_green")
    assert sm.state is OperationalState.READY_FOR_RESUME
    sm.manual_resume()
    assert sm.state is OperationalState.HEALTHY
```

- [ ] **Step 5: Run focused GREEN, then full suite**

Run: `python -m pytest tests_v1/test_phase5_operational_state.py -q`
Expected: PASS.

Run: `python -m pytest -q`
Expected: all existing tests PASS; report any unrelated pre-existing failures by name instead of hiding them.

- [ ] **Step 6: Commit**

```bash
git add engine/paper/contracts_v2.py engine/paper/operational_state_v2.py tests_v1/test_phase5_operational_state.py
git commit -m "feat: add phase5 paper contracts and state model"
```

---

### Task 2: P5-02 Paper execution adapter + deterministic fill simulator

**Files:**
- Create: `engine/paper/execution_adapter_v2.py`
- Create: `engine/paper/fill_simulator_v2.py`
- Test: `tests_v1/test_phase5_fill_simulator.py`

**Interfaces:**
- Consumes existing approved-order authority only; adapter must reject unapproved/raw strategy requests.
- Produce `QuoteSnapshot(bid: Decimal, ask: Decimal, observed_at: str, sequence: int)`.
- Produce `FillSimulationPolicy(policy_id, version, slippage_ticks, latency_ms, reject, disconnect, stale_after_ms)`.
- Produce `PaperFillSimulator.simulate(approved_order, quote, policy, now) -> SimulatedExecutionResult`.
- BUY fill base = ask; SELL fill base = bid; slippage applies conservatively outward.

- [ ] **Step 1: RED tests for bid/ask and stale quote**

```python
from decimal import Decimal


def test_buy_uses_ask_side_and_sell_uses_bid_side():
    quote = QuoteSnapshot(bid=Decimal("100"), ask=Decimal("101"), observed_at="t0", sequence=1)
    assert simulator.buy_base_price(quote) == Decimal("101")
    assert simulator.sell_base_price(quote) == Decimal("100")


def test_stale_quote_fails_closed():
    result = simulator.simulate(order, stale_quote, policy, now="t-late")
    assert result.accepted is False
    assert result.reason == "STALE_QUOTE"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests_v1/test_phase5_fill_simulator.py -q`
Expected: FAIL on missing modules/types.

- [ ] **Step 3: Implement minimal simulator**

Implementation rules: Decimal-only price arithmetic; deterministic injected `now`; no random global state; TEST_ONLY policy can force rejection/disconnect; unsupported/missing quote fails closed.

- [ ] **Step 4: Add deterministic replay test**

```python
def test_same_inputs_produce_identical_simulated_execution():
    a = simulator.simulate(order, quote, policy, now=fixed_now)
    b = simulator.simulate(order, quote, policy, now=fixed_now)
    assert a == b
```

- [ ] **Step 5: GREEN + full suite + commit**

Run focused then `python -m pytest -q`.

```bash
git add engine/paper/execution_adapter_v2.py engine/paper/fill_simulator_v2.py tests_v1/test_phase5_fill_simulator.py
git commit -m "feat: add deterministic paper fill simulation"
```

---

### Task 3: P5-03 Persistence + checkpointing

**Files:**
- Create: `engine/persistence/paper_session_store_v2.py`
- Create: `engine/persistence/paper_recovery_store_v2.py`
- Create: `engine/persistence/paper_incident_store_v2.py`
- Modify: `engine/persistence/schema.py`
- Modify: `engine/persistence/migrations.py`
- Modify only if necessary: `engine/persistence/sqlite_store.py`
- Test: `tests_v1/test_phase5_persistence.py`

**Interfaces:**
- `PaperSessionStore.save_session(session)`, `save_order(record)`, `save_position(record)`, `load_owned_state(session_id)`.
- `PaperRecoveryStore.save_checkpoint(checkpoint)`, `latest_checkpoint(session_id)`, `save_recovery_report(report)`.
- `PaperIncidentStore.save_incident(incident)`, `save_alert_delivery(record)`.
- Stored datetimes remain canonical strings matching existing codec policy; money/price remain Decimal-compatible serialized values per existing persistence conventions.

- [ ] **Step 1: RED round-trip test**

```python
def test_checkpoint_round_trip_preserves_fingerprint(tmp_path):
    store = make_store(tmp_path)
    checkpoint = sample_checkpoint()
    store.save_checkpoint(checkpoint)
    loaded = store.latest_checkpoint(checkpoint.session_id)
    assert loaded == checkpoint
    assert fingerprint(loaded) == fingerprint(checkpoint)
```

- [ ] **Step 2: RED corrupt/incomplete checkpoint test**

```python
def test_corrupt_checkpoint_is_not_treated_as_valid_state(tmp_path):
    store = make_store(tmp_path)
    inject_corrupt_checkpoint(store)
    with pytest.raises(CheckpointIntegrityError):
        store.latest_checkpoint("s1")
```

- [ ] **Step 3: Verify RED**

Run: `python -m pytest tests_v1/test_phase5_persistence.py -q`
Expected: FAIL because tables/repositories do not exist.

- [ ] **Step 4: Add one forward migration and focused repositories**

Schema must support PaperSession, PaperOrderRecord, PaperPositionRecord, RecoveryCheckpoint, FailureIncident, AlertDeliveryRecord, RecoveryReport references. Do not add recovery-state decision logic to repository classes.

- [ ] **Step 5: GREEN + migration compatibility + full suite**

Run focused test; run existing migration/persistence tests; run `python -m pytest -q`.

- [ ] **Step 6: Commit**

```bash
git add engine/persistence/schema.py engine/persistence/migrations.py engine/persistence/sqlite_store.py engine/persistence/paper_*_v2.py tests_v1/test_phase5_persistence.py
git commit -m "feat: persist phase5 paper recovery state"
```

---

### Task 4: P5-04 Reconciliation + recovery coordinator

**Files:**
- Create: `engine/paper/recovery_coordinator_v2.py`
- Create only if needed: `engine/reconciliation/paper/contracts_v2.py`
- Create only if needed: `engine/reconciliation/paper/recovery_view_v2.py`
- Test: `tests_v1/test_phase5_recovery.py`

**Interfaces:**
- Define Protocols: `OwnedStateLoader`, `PaperReconcilerPort`, `ProtectiveIntegrityPort`, `FeedHealthPort`, `ClockHealthPort`, `SessionValidityPort`, `AlertPort`.
- `RecoveryCoordinator.recover(trigger, session_id) -> RecoveryReport`.
- Reconciliation verdict vocabulary: `CLEAN`, `MISMATCH`, `UNCERTAIN`, `INCOMPLETE`.

- [ ] **Step 1: RED uncertain-submission test**

```python
def test_uncertain_submission_is_reconciled_before_retry_permission():
    coordinator = coordinator_with(reconciliation="UNCERTAIN")
    report = coordinator.recover("ACK_UNCERTAIN", "s1")
    assert report.final_state is OperationalState.HALTED
    assert retry_port.allowed is False
    assert duplicate_submitter.calls == 0
```

- [ ] **Step 2: RED mismatch/stale replay test**

```python
def test_reconciliation_mismatch_halts_and_never_replays_stale_intent():
    coordinator = coordinator_with(reconciliation="MISMATCH", stale_intent=True)
    report = coordinator.recover("RESTART", "s1")
    assert report.final_state is OperationalState.HALTED
    assert report.unresolved_discrepancies
    assert submitter.calls == 0
```

- [ ] **Step 3: Verify RED**

Run: `python -m pytest tests_v1/test_phase5_recovery.py -q`.

- [ ] **Step 4: Implement coordinator sequencing only**

Order is fixed: restore owned state → reconcile → protective integrity → feed → clock → session/expiry validity → `READY_FOR_RESUME`. Any non-clean/non-valid step stops progression and emits report evidence.

- [ ] **Step 5: GREEN + existing reconciliation regression + full suite**

Run focused; run existing reconciliation/restart tests including `tests_v1/test_area14_live_reconciliation_restart.py`; run full suite.

- [ ] **Step 6: Commit**

```bash
git add engine/paper/recovery_coordinator_v2.py engine/reconciliation/paper tests_v1/test_phase5_recovery.py
git commit -m "feat: add phase5 recovery coordinator"
```

---

### Task 5: P5-05 Protective integrity + session/expiry recovery

**Files:**
- Create: `engine/paper/protective_integrity_v2.py`
- Create: `engine/paper/session_v2.py`
- Test: `tests_v1/test_phase5_protective_integrity.py`

**Interfaces:**
- `ProtectiveIntegrityVerdict(Enum): VALID, INVALID, UNCERTAIN`.
- `ProtectiveIntegrityChecker.check(position, policy_ref, observed_state) -> ProtectiveIntegrityResult`.
- `SessionValidityPort.evaluate(instrument, now, expiry_policy_ref) -> SessionValidityResult`.

- [ ] **Step 1: RED CLEAN-but-protection-broken test**

```python
def test_clean_reconciliation_does_not_resume_when_protection_invalid():
    coordinator = coordinator_with(reconciliation="CLEAN", protective="INVALID")
    report = coordinator.recover("RESTART", "s1")
    assert report.final_state is OperationalState.HALTED
    assert report.protective_integrity_result == "INVALID"
```

- [ ] **Step 2: RED expiry-policy-missing test**

```python
def test_open_option_at_expiry_without_policy_halts_instead_of_inventing_action():
    result = validity.evaluate(expiring_position, now=expiry_time, expiry_policy_ref=None)
    assert result.allowed is False
    assert result.action == "HALT_ENTRIES"
    assert result.auto_flatten is False
```

- [ ] **Step 3: Verify RED, implement minimal integrity/session guards**

No auto-flatten and no silent carry are allowed without explicit versioned policy. Expired contracts cannot accept fresh entries.

- [ ] **Step 4: GREEN + full suite + commit**

```bash
git add engine/paper/protective_integrity_v2.py engine/paper/session_v2.py tests_v1/test_phase5_protective_integrity.py
git commit -m "feat: enforce protective and expiry recovery gates"
```

---

### Task 6: P5-06 Failure policy + storm detection

**Files:**
- Create: `engine/paper/failure_policy_v2.py`
- Test: `tests_v1/test_phase5_failure_policy.py`

**Interfaces:**
- `FailureStormPolicy(policy_id, version, failure_class, observation_window_ms, trigger_count, cooldown_ms, escalation_action, reset_rule)`.
- `StormEvaluator.observe(failure_class, occurred_at_ms) -> StormDecision`.
- `StormDecision`: below-threshold degradation vs threshold-crossed halt.
- No module-level production defaults for count/window.

- [ ] **Step 1: RED TEST_ONLY storm threshold test**

```python
def test_test_only_rejection_policy_halts_exactly_at_threshold():
    policy = FailureStormPolicy(
        policy_id="TEST_ONLY/storm-fi-v1", version="1",
        failure_class="ORDER_REJECTION", observation_window_ms=10_000,
        trigger_count=3, cooldown_ms=30_000,
        escalation_action="HALT_ENTRIES", reset_rule="WINDOW_AND_COOLDOWN",
    )
    evaluator = StormEvaluator(policy)
    assert evaluator.observe("ORDER_REJECTION", 0).halt is False
    assert evaluator.observe("ORDER_REJECTION", 1000).halt is False
    assert evaluator.observe("ORDER_REJECTION", 2000).halt is True
```

- [ ] **Step 2: RED missing-policy fail-closed test**

```python
def test_missing_required_storm_policy_never_allows_unbounded_retry():
    decision = evaluate_without_policy("ORDER_REJECTION")
    assert decision.retry_unbounded is False
    assert decision.resulting_state in {OperationalState.DEGRADED, OperationalState.HALTED}
```

- [ ] **Step 3: Verify RED, implement deterministic sliding-window evaluator**

Use injected integer timestamps; do not use wall clock internally.

- [ ] **Step 4: GREEN + static grep assertion against guessed defaults + full suite**

Add test that production module contains no hardcoded named default policy such as `DEFAULT_REJECTION_STORM`.

- [ ] **Step 5: Commit**

```bash
git add engine/paper/failure_policy_v2.py tests_v1/test_phase5_failure_policy.py
git commit -m "feat: add versioned failure storm policy"
```

---

### Task 7: P5-07 Host resilience

**Files:**
- Create: `engine/host/__init__.py`
- Create: `engine/host/instance_lock.py`
- Create: `engine/host/clock_health.py`
- Create: `engine/host/power_session.py`
- Create: `engine/host/watchdog_policy.py`
- Test: `tests_v1/test_phase5_host_resilience.py`

**Interfaces:**
- `InstanceLock.acquire() -> bool`, `release()`.
- `ClockHealthProvider.check(policy_ref) -> ClockHealthResult` where missing policy is unhealthy/fail-closed.
- `PowerSessionProvider.begin_session()`, `end_session()`, `resume_detected()`.
- `WatchdogPolicy.restart_target() -> OperationalState.RECOVERY` only.

- [ ] **Step 1: RED second-instance and watchdog tests**

```python
def test_second_instance_fails_closed():
    first = fake_lock_backend()
    assert InstanceLock(first).acquire() is True
    assert InstanceLock(first).acquire() is False


def test_watchdog_restart_target_is_recovery_only():
    assert WatchdogPolicy().restart_target() is OperationalState.RECOVERY
```

- [ ] **Step 2: RED sleep/resume and missing clock-policy tests**

```python
def test_resume_discontinuity_requires_recovery():
    provider = FakePowerSession(resume=True)
    assert classify_power_event(provider) is OperationalState.RECOVERY


def test_missing_clock_policy_fails_closed():
    result = FakeClockHealth().check(None)
    assert result.entry_eligible is False
```

- [ ] **Step 3: Verify RED; implement platform-neutral interfaces first**

Windows API calls go behind provider classes; CI tests use fakes and never change runner power plans or clocks.

- [ ] **Step 4: GREEN + full suite + commit**

```bash
git add engine/host tests_v1/test_phase5_host_resilience.py
git commit -m "feat: add phase5 host resilience guards"
```

---

### Task 8: P5-08 Independent alerts

**Files:**
- Create: `engine/alerts/contracts.py`
- Create: `engine/alerts/dispatcher.py`
- Create: `engine/alerts/redaction.py`
- Create: `engine/alerts/adapters/__init__.py`
- Create: `engine/alerts/adapters/windows_local.py`
- Create: `engine/alerts/adapters/telegram.py`
- Test: `tests_v1/test_phase5_alerts.py`

**Interfaces:**
- `AlertEnvelope(alert_id, incident_id, severity, incident_type, session_ref, occurred_at, safety_state, required_action, safe_detail)`.
- `AlertAdapter.deliver(envelope) -> AlertDeliveryRecord` Protocol.
- `AlertDispatcher.dispatch_critical(envelope) -> tuple[AlertDeliveryRecord, ...]` attempts every required adapter even if one raises.
- `redact_alert_payload()` strips credentials/tokens/raw account identifiers/unrestricted trade-log fields.

- [ ] **Step 1: RED independence tests**

```python
def test_windows_failure_does_not_suppress_telegram_attempt():
    dispatcher = AlertDispatcher([FailingWindowsAdapter(), RecordingTelegramAdapter()])
    records = dispatcher.dispatch_critical(sample_alert())
    assert [r.channel for r in records] == ["windows_local", "telegram"]
    assert records[0].delivery_status == "FAILED"
    assert records[1].delivery_status == "DELIVERED"


def test_telegram_failure_does_not_suppress_local_attempt():
    dispatcher = AlertDispatcher([RecordingWindowsAdapter(), FailingTelegramAdapter()])
    records = dispatcher.dispatch_critical(sample_alert())
    assert len(records) == 2
```

- [ ] **Step 2: RED redaction test**

```python
def test_alert_redaction_removes_secrets_and_raw_account_ids():
    safe = redact_alert_payload({"token": "secret", "account_id": "raw", "detail": "clock unhealthy"})
    assert "secret" not in repr(safe)
    assert "raw" not in repr(safe)
    assert safe["detail"] == "clock unhealthy"
```

- [ ] **Step 3: Verify RED; implement dispatcher and fake-safe adapters**

Real Telegram sending remains adapter-specific and must not be required for CI. No alert adapter may import order placement or arm authority.

- [ ] **Step 4: GREEN + full suite + commit**

```bash
git add engine/alerts tests_v1/test_phase5_alerts.py
git commit -m "feat: add independent phase5 alert delivery"
```

---

### Task 9: P5-09 Drift + deterministic evidence

**Files:**
- Create: `engine/paper/drift_report_v2.py`
- Create: `engine/paper/evidence_v2.py`
- Test: `tests_v1/test_phase5_drift_report.py`

**Interfaces:**
- `PaperDriftReporter.compare(backtest_record, paper_record, policy_ref) -> DriftReport`.
- `EvidenceWriter.recovery_fingerprint(report) -> str` exactly 64 lowercase hex.
- `EvidenceWriter.build_g5_manifest(...) -> dict` deterministic key order/content.
- No guessed production drift tolerance; missing promotion/drift policy yields non-promotable/fail-closed evidence state, not an invented threshold.

- [ ] **Step 1: RED deterministic fingerprint test**

```python
def test_same_recovery_report_has_same_64_hex_fingerprint():
    a = EvidenceWriter.recovery_fingerprint(sample_recovery_report())
    b = EvidenceWriter.recovery_fingerprint(sample_recovery_report())
    assert a == b
    assert len(a) == 64
    int(a, 16)
```

- [ ] **Step 2: RED drift-without-policy test**

```python
def test_missing_drift_policy_is_fail_closed_not_guessed():
    report = PaperDriftReporter.compare(backtest, paper, policy_ref=None)
    assert report.promotion_eligible is False
    assert report.reason == "MISSING_DRIFT_POLICY"
```

- [ ] **Step 3: Verify RED; implement canonical serialization/fingerprints**

Use the repository's canonical codec/fingerprint conventions where already available rather than inventing an incompatible encoder.

- [ ] **Step 4: GREEN + deterministic repeated-run check + full suite + commit**

```bash
git add engine/paper/drift_report_v2.py engine/paper/evidence_v2.py tests_v1/test_phase5_drift_report.py
git commit -m "feat: add phase5 drift and evidence reports"
```

---

### Task 10: P5-10 Failure injection, architecture gate, wiring, dual-Windows qualification

**Files:**
- Create: `tests_v1/test_phase5_failure_injection.py`
- Create: `build/tools/check_phase5_paper_recovery.py`
- Modify minimally: `engine/paper/coordinator.py` and/or `engine/paper/live_runner.py`
- Modify: relevant GitHub Actions workflow(s) that currently run Phase-4 dual-Windows qualification.
- Create/update: `docs/v2/phase5/G5_EVIDENCE.md` only after fresh exact-head evidence exists.

**Interfaces:**
- Static checker exits nonzero on forbidden imports/dependencies/default Live weakening/guessed production storm constants.
- Deterministic probe emits exactly:

```text
SESSION_FINGERPRINT=<64hex>
CHECKPOINT_FINGERPRINT=<64hex>
RECOVERY_REPORT=<64hex>
FINAL_STATE=READY_FOR_RESUME
MANUAL_RESUME_REQUIRED=true
DUPLICATE_ORDER_COUNT=0
STALE_REPLAY_COUNT=0
DEFAULT_LIVE_STATE=READ_ONLY/DISARMED
```

- [ ] **Step 1: RED architecture/static tests**

The checker must reject at least these synthetic violations: `engine.paper` importing a real broker mutation adapter, domain importing sqlite, host/alerts importing live arm authority, hardcoded production storm default, default Live state not DISARMED.

Run: `python build/tools/check_phase5_paper_recovery.py`
Expected before implementation: nonzero/missing checker.

- [ ] **Step 2: RED failure-injection tests**

Pin required paper scenarios:

```python
@pytest.mark.parametrize("fi_id", [
    "FI-01", "FI-02", "FI-03", "FI-04", "FI-05", "FI-06", "FI-07", "FI-08", "FI-09",
    "FI-12", "FI-13", "FI-14", "FI-23", "FI-24",
])
def test_required_phase5_failure_injection_case(fi_id):
    result = run_failure_fixture(fi_id)
    assert result.status == "PASS"
    assert result.duplicate_order_count == 0
    assert result.stale_replay_count == 0
```

For FI-24, assert one notifier failure cannot suppress the other independent delivery attempt.

- [ ] **Step 3: Wire focused modules into existing Paper entrypoint with minimal edits**

Only after Tasks 1–9 are green. Preserve existing Paper/Backtest/Live isolation and do not delete legacy safety gates.

- [ ] **Step 4: Run focused Phase-5 suite**

Run:

```bash
python -m pytest tests_v1/test_phase5_operational_state.py tests_v1/test_phase5_fill_simulator.py tests_v1/test_phase5_persistence.py tests_v1/test_phase5_recovery.py tests_v1/test_phase5_protective_integrity.py tests_v1/test_phase5_failure_policy.py tests_v1/test_phase5_host_resilience.py tests_v1/test_phase5_alerts.py tests_v1/test_phase5_drift_report.py tests_v1/test_phase5_failure_injection.py -q
python build/tools/check_phase5_paper_recovery.py
```

Expected: PASS.

- [ ] **Step 5: Run full local regression**

Run: `python -m pytest -q`
Expected: all suites green; any unrelated pre-existing red test must be explicitly reported by name.

- [ ] **Step 6: Extend dual-Windows CI without removing Phase 0–4 gates**

Workflow must run on the same two Windows qualification environments already used for G4, produce Phase-5 deterministic artifacts on both, and compare fingerprints exactly.

- [ ] **Step 7: Verify exact-head CI evidence**

After push, capture exact commit SHA; inspect workflow jobs/logs/artifacts for that SHA. G5 evidence may claim only what the exact-head run proves. Combined status metadata alone is not sufficient if workflow evidence lives in Actions artifacts/logs.

- [ ] **Step 8: Create G5 evidence document only from verified results**

`docs/v2/phase5/G5_EVIDENCE.md` must list exact head SHA, run id, both Windows job ids, focused/full regression results, FI results, deterministic fingerprint comparison, alert independence evidence, host-resilience evidence, and soak-start record. Do not claim soak completion; G5 requires soak started/running.

- [ ] **Step 9: Final verification before completion claim**

Confirm explicitly:

```text
DUPLICATE_ORDER_COUNT=0
STALE_REPLAY_COUNT=0
required FI catalogue GREEN
alert independence GREEN
recovery reports generated
G4 regression still GREEN
Live READ_ONLY/DISARMED
paper soak start recorded
```

- [ ] **Step 10: Commit qualification wiring/evidence separately**

```bash
git add build/tools/check_phase5_paper_recovery.py tests_v1/test_phase5_failure_injection.py engine/paper/coordinator.py engine/paper/live_runner.py .github/workflows docs/v2/phase5/G5_EVIDENCE.md
git commit -m "test: qualify phase5 paper recovery gate"
```

---

## Self-Review Record

### Spec coverage

- Safety invariants: Tasks 1, 4, 5, 7, 8, 10.
- Branching state model/manual resume: Task 1.
- Persistence + FailureIncident traceability fields: Tasks 1 and 3.
- Conservative execution simulation: Task 2.
- Existing reconciliation reuse/recovery sequencing: Task 4.
- Protective integrity + expiry boundaries: Task 5.
- Versioned storm threshold policy/no guessed production numbers: Task 6.
- Host policy OD-V2-24: Task 7.
- Independent alerts OD-V2-19: Task 8.
- Drift/recovery/FI evidence: Tasks 9 and 10.
- G5 FI catalogue, dual-Windows deterministic comparison, full regression, soak-start evidence: Task 10.

### Placeholder scan

No `TBD`, `TODO`, generic “handle errors”, or undefined future task references are permitted in this plan. Optional file creation is limited to adapters/views that are only necessary if existing reconciliation/persistence interfaces cannot be consumed directly; behavior and tests remain specified.

### Type consistency

Canonical names used across tasks: `OperationalState`, `IncidentSeverity`, `FailureIncident`, `RecoveryReport`, `FailureStormPolicy`, `ProtectiveIntegrityVerdict`, `AlertEnvelope`, `AlertDeliveryRecord`, `RecoveryCoordinator`, `READY_FOR_RESUME`, `HALT_ENTRIES`, `HALTED`.

### Review Focus mapping

All five Review Focus items have explicit tests in Tasks 4, 5, 6, 8, and 10.
