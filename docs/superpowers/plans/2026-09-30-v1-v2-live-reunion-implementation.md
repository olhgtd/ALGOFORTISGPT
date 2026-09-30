# AlgoFortis V1 → V2 Live Reunion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently reunite proven V1 Live/recovery behavior with the current V2 safety spine through one canonical, testable Live path while keeping real broker mutation unreachable and Live `READ_ONLY / DISARMED` throughout Package 1.

**Architecture:** Reuse the existing `ApprovedOrder`, deterministic `client_order_id`, `OrderExecutionLifecycle`/`OrderExecutionState`, `LiveStateMachine`, `BoundBrokerPort`, Phase-6 read-only coordinator/reconciler, S2 gate contracts, and Angel One V2 protection/read-side components. Add only missing focused pieces: permanent donor manifest/guard, additive V9 Live evidence schema, dormant `LiveExecutionCoordinatorV2` behind a production-closed release gate, local account exclusivity, Live eligibility composition, and an Angel One mutation translation seam whose mutation methods remain unavailable in Package 1.

**Tech Stack:** Python 3.13.14, dataclasses/enums/protocols, SQLite additive migrations, pytest, existing AlgoFortis V2 contracts, GitHub Actions dual-Windows qualification.

**Spec:** `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design.md` + `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design-approval.md`

## Global Constraints

- Live remains `READ_ONLY / DISARMED` for this entire plan.
- `RiskGateV2` remains the sole executable-order approval authority.
- Historical checkpoint `4713b4dfb1d250ac01cf23dc73e89ddeac7716de` is immutable.
- `engine/orders/lifecycle_v2.py` remains the sole order lifecycle; only broker-truth convergence extensions are allowed.
- `engine/orders/contracts_v2.py` remains the sole deterministic `client_order_id` source.
- `LiveBrokerReconciler` + `engine/live/phase6_readonly_coordinator.py` remain reconciliation/foreign-activity authorities.
- Existing Phase-6 transport runtime remains sole reconnect/generation authority.
- Existing `BoundBrokerPort` Live hard-block stays unchanged in Package 1.
- `build/tools/check_phase6_live_readonly.py` stays enabled and must remain GREEN.
- Legacy `engine/broker_adapters/angel_adapter.py` is reference-only.
- Paper/Backtest, AI/Laya, dashboard, alerts, reporting, and persistence never gain direct broker mutation authority.
- Restart/reconnect/recovery never auto-arm.
- Missing/corrupt safety, journal, broker truth, protection, exclusivity, audit, or policy evidence fails closed.
- No real broker credentials/orders/mutation and no invented production thresholds.

## Review Focus

1. Timeout/restart duplicate submission → one `client_order_id`; `IN_DOUBT` reconciled, never blindly retried.
2. Local persistence mistaken for broker truth → broker query remains authoritative.
3. Second local device/session owner → conflict/uncertainty fails closed; cloud is not trading authority.
4. Protection capability disappears/changes → Live eligibility blocks.
5. Dormant write seam becomes reachable → closed gate + unchanged `BoundBrokerPort` + unavailable Angel mutation methods must prevent it.

---

## Locked File Structure

**Create**
- `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md`
- `build/tools/check_live_reunion_boundary.py`
- `engine/persistence/live_execution_schema_v9.py`
- `engine/persistence/live_execution_store_v2.py`
- `engine/persistence/live_account_exclusivity_store_v2.py`
- `engine/live/mutation_release_gate_v2.py`
- `engine/live/execution_coordinator_v2.py`
- `engine/live/account_exclusivity_v2.py`
- `engine/live/live_eligibility_v2.py`
- `engine/broker_adapters/angelone_v2/mutation_seam_v2.py`
- focused tests listed below
- `.github/workflows/live-v1-v2-reunion-qualification.yml`
- `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md`

**Modify narrowly**
- `engine/persistence/schema.py`
- `engine/persistence/migrations.py`
- `engine/orders/lifecycle_v2.py`
- `engine/reconciliation/live_reconciler.py`
- `engine/live/phase6_readonly_coordinator.py` only if the existing foreign-activity result needs exposure
- `engine/broker_adapters/angelone_v2/protection_capability.py` / `order_policy.py` only if current models cannot express Task 6

**Do not grow/promote**
- `engine/persistence/sqlite_store.py`
- legacy paper/live coordinator, entry pipeline, risk-manager, protective monoliths
- legacy direct Angel mutation adapter

---

### Task 1: Permanent Manifest + Boundary Guard

**Files:** Create `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md`, `build/tools/check_live_reunion_boundary.py`, `tests_v1/test_v2_live_reunion_boundary.py`.

**Interfaces:** manifest statuses exactly `SALVAGED`, `REFERENCE_ONLY`, `REPLACED_BY_V2`, `DEFERRED`; guard success marker `LIVE_REUNION_BOUNDARY_PASS`.

- [ ] RED tests reject direct mutation imports from strategy/AI/dashboard/alerts/reporting/persistence/Paper, direct `_mint_approved_order`, production reachability of `angel_adapter.py`, second reconnect authority, restart auto-arm code, and any Package-1 production release-gate implementation other than `ClosedLiveMutationReleaseGate`.
- [ ] Run `python -m pytest tests_v1/test_v2_live_reunion_boundary.py -q`; expect FAIL because files do not exist.
- [ ] Create manifest with donor path/behavior, historical evidence, classification, canonical V2 owner, migration method, regression tests, safety note, implementation commit.
- [ ] Implement deterministic repo-relative guard with explicit canonical allowlist; do not weaken Phase-6 guard.
- [ ] GREEN: focused test + `python build/tools/check_live_reunion_boundary.py` + `python build/tools/check_phase6_live_readonly.py`.
- [ ] Commit `docs: lock V1-to-V2 Live reunion manifest`.

### Task 2: Additive V9 Live Execution + Ownership Evidence

**Files:** Create `engine/persistence/live_execution_schema_v9.py`, `engine/persistence/live_execution_store_v2.py`, `tests_v1/test_live_execution_store_v2.py`; modify `schema.py`, `migrations.py`.

**Interfaces:**
- `LiveExecutionStoreV2.__init__(database_path: Path | str) -> None` following `PaperRecoveryStore` style.
- immutable `LiveExecutionRecord(client_order_id: str, approved_order_ref: str, run_mode: RunMode, lifecycle_state: OrderExecutionState, broker_order_identity: str | None, submission_attempt_id: str, created_at_utc: datetime, updated_at_utc: datetime, is_uncertain: bool, adapter_id: str | None, policy_ref: str | None, audit_ref: str | None)`.
- `reserve(record)`, `get(client_order_id)`, `transition(... lifecycle_state: OrderExecutionState ...)`, `list_uncertain()`.
- V9 creates execution-journal and `live_account_exclusivity_v2` ownership-evidence tables.
- `LIVE_EXECUTION_V9_MIGRATION` is exactly `8 -> 9`.

- [ ] RED: migration/rollback, unique `client_order_id`, persistence across reopen, exact `OrderExecutionState` round-trip including `IN_DOUBT`, no secret/token columns, corrupt/duplicate fail-closed.
- [ ] Run focused RED.
- [ ] Add V9 create/drop SQL without editing V7/V8 files; update facade to `SCHEMA_VERSION = 9`; export migration.
- [ ] Implement focused store; journal is evidence, never broker truth.
- [ ] GREEN focused + migration + Phase-5 recovery-store regressions.
- [ ] Commit `feat: add V2 Live execution journal`.

### Task 3: Production-Closed Gate + Dormant `LiveExecutionCoordinatorV2`

**Files:** Create `engine/live/mutation_release_gate_v2.py`, `engine/live/execution_coordinator_v2.py`, `tests_v1/test_live_execution_coordinator_v2.py`; extend reunion guard test.

**Interfaces:**
- `LiveMutationBlocked(RuntimeError)`.
- `LiveMutationReleaseGate.authorize(*, order: ApprovedOrder, live_state: LiveState) -> str` Protocol.
- `ClosedLiveMutationReleaseGate.authorize(...)` always raises `LiveMutationBlocked("live mutation release gate is closed")`.
- `_LiveBrokerMutationPort.place(order: ApprovedOrder) -> object` Protocol inside coordinator; production is intended to compose `BoundBrokerPort`, while tests use a test-local fake because `BoundBrokerPort` intentionally blocks all Live mutation in Package 1.
- `LiveExecutionCoordinatorV2.__init__(*, broker_port: _LiveBrokerMutationPort, journal: LiveExecutionStoreV2, release_gate: LiveMutationReleaseGate, state_machine: LiveStateMachine, audit_sink: object, clock: object) -> None`.
- `submit(order: ApprovedOrder) -> object`.

**Sequence:** genuine unexpired `RunMode.LIVE` approval → require `LiveState.ACTIVE` → release-gate authorization → reserve unique journal record → `OrderExecutionLifecycle` starts `RISK_APPROVED` → persist `SUBMITTING` → persist `SENT_UNACKED` **before** broker call → call `place` → acknowledgement maps to `ACKED` + broker identity; exception after call boundary maps to `IN_DOUBT`; never auto-resubmit.

- [ ] RED: wrong type/mode, expired approval, duplicate ID, non-ACTIVE state, closed-gate port call count zero, test-local fake-gate/fake-port success, ack mapping once, exception→`IN_DOUBT`, second submit rejected, audit failure blocks call.
- [ ] Run focused RED.
- [ ] Implement closed gate with no env/config/CLI opener.
- [ ] Implement coordinator using existing lifecycle/client ID/store; no approval minting/reconciliation ownership.
- [ ] Guard rejects production open gate/direct broker bypass.
- [ ] GREEN coordinator + Phase-2 RiskGate authority/mode isolation + both static guards.
- [ ] Commit `feat: add dormant V2 Live execution coordinator`.

### Task 4: Broker-Truth Lifecycle Convergence + `IN_DOUBT` Reconciliation

**Files:** Modify `engine/orders/lifecycle_v2.py`, `engine/reconciliation/live_reconciler.py`; extend `tests_v1/test_v2_phase2_order_lifecycle.py`; create `tests_v1/test_live_reunion_reconciliation_v2.py`; modify Phase-6 coordinator only if needed.

**Interfaces:**
- extend `BrokerTruth` with `PARTIALLY_FILLED`, `FILLED`, `CANCELLED` in addition to existing `ACKED`, `REJECTED`, `NOT_FOUND`.
- `OrderExecutionLifecycle.resolve_in_doubt(...)` maps explicit broker truth to those states; broker identity required whenever truth proves an order exists.
- preserve `retry_not_found(reapproved_order)` requirement: same client ID, fresh RiskGate decision ref, unexpired TTL.
- `LiveBrokerReconciler.reconcile_uncertain_orders(records: Sequence[LiveExecutionRecord], *, fail_closed: bool = True) -> tuple[OrderReconciliationItem, ...]`.

- [ ] RED lifecycle tests for all explicit truth outcomes and no assumed state; NOT_FOUND retry still requires fresh approval.
- [ ] RED reconciliation: broker-query failure fail-closed, partial/full fill/cancel convergence, restart with position recovers before entries, zero place/submit calls.
- [ ] RED foreign activity: existing halt + critical alert/audit, no auto-adopt, no implicit `FLATTEN_ALL`.
- [ ] Run `python -m pytest tests_v1/test_v2_phase2_order_lifecycle.py tests_v1/test_live_reunion_reconciliation_v2.py -q` and verify RED.
- [ ] Implement minimal lifecycle/reconciler extension; persistence remains non-authoritative.
- [ ] GREEN above + `tests_v1/test_area14_live_reconciliation_restart.py` + Phase-5 recovery regressions.
- [ ] Commit `feat: reconcile uncertain Live orders through broker truth`.

### Task 5: Local Broker-Account Live Exclusivity

**Files:** Create `engine/persistence/live_account_exclusivity_store_v2.py`, `engine/live/account_exclusivity_v2.py`, `tests_v1/test_live_account_exclusivity_v2.py`.

**Interfaces:**
- immutable `LiveAccountOwner(broker_id: str, broker_account_ref: str, device_id: str, session_family_id: str, ownership_nonce: str, acquired_at_utc: datetime)`.
- store: `__init__(database_path: Path | str)`, `load(broker_id, broker_account_ref)`, `save(owner)`, `clear(broker_id, broker_account_ref, ownership_nonce)`.
- service: `acquire(candidate)`, `verify(candidate)`, `release(candidate)`, `restore_after_restart(...)`; restart never restores armed ownership from disk alone.

- [ ] RED: same-owner verify, second-device conflict, session mismatch, corrupt/unknown evidence, restart no restored owner, cloud unavailable local safety, foreign activity halt-not-takeover, cross-user/S2 substitution rejected.
- [ ] Run focused RED.
- [ ] Implement V9-backed focused store/service; no hostname/MAC/IP trust, no cloud lease authority.
- [ ] GREEN focused + `tests_v1/test_s2_device_session_gate.py` + `tests_v1/test_s2_cloud_outage.py` + `tests_v1/test_s2_device_service.py`.
- [ ] Commit `feat: add local Live account exclusivity backstop`.

### Task 6: Live Eligibility + Broker-Resident Protection

**Files:** Create `engine/live/live_eligibility_v2.py`, `tests_v1/test_live_eligibility_v2.py`; extend `tests_v1/test_phase6_protection_capability.py`; modify protection/policy source only if required.

**Interfaces:**
- import exact S2 `DeviceSessionGateResult` / `DeviceSessionGateStatus` from `dashboard/backend/account_v2/contracts.py`.
- consume exact `ProtectionCapabilityDecision` / `ProtectionCapabilityStatus` from `engine/broker_adapters/angelone_v2/protection_capability.py`.
- `LiveEligibilityStatus`: `ELIGIBLE_FOR_QUALIFICATION`, `BLOCKED` only.
- immutable `LiveEligibilityResult(status, reasons: tuple[str, ...], evidence_refs: tuple[str, ...])`.
- `LiveEligibilityV2.evaluate(*, live_state: LiveState, s2_gate_result: DeviceSessionGateResult, exclusivity_ok: bool, reconciliation_clean: bool, protection_decision: ProtectionCapabilityDecision, broker_policy_ref: str | None, audit_ready: bool) -> LiveEligibilityResult`.
- Package-1 software eligibility requires `LiveState.READY`, S2 `VALID`, exclusivity true, clean reconciliation, `VERIFIED_SUPPORTED` protection with `disarmed_required=True`, current non-empty broker policy ref, audit ready. Result is qualification eligibility only, never arm permission.

- [ ] RED: each missing/invalid prerequisite => BLOCKED; complete prerequisites => only ELIGIBLE_FOR_QUALIFICATION; never ACTIVE/armed.
- [ ] Run focused RED.
- [ ] Implement pure composition; no degraded policy invented.
- [ ] GREEN eligibility + protection + Phase-6 policy/state-machine + S2 gate regressions.
- [ ] Commit `feat: enforce Live protection eligibility`.

### Task 7: Angel One V2 Mutation Translation Seam — Mutation Unavailable

**Files:** Create `engine/broker_adapters/angelone_v2/mutation_seam_v2.py`, `tests_v1/test_angelone_v2_mutation_seam.py`; extend reunion guard.

**Interfaces:**
- immutable `AngelOneMutationRequestV2` contains only non-secret canonical order fields + versioned policy/protection refs.
- `AngelOneV2MutationUnavailable(RuntimeError)`.
- `AngelOneV2MutationSeam` exposes `BrokerPortDescriptor(RunMode.LIVE, REAL_BROKER, REAL_BROKER)` and `build_place_request(order: ApprovedOrder) -> AngelOneMutationRequestV2`.
- `place(...)` and `cancel(...)` always raise `AngelOneV2MutationUnavailable` in Package 1.
- no HTTP client, credential loader, network transport, or injected mutation transport exists here.

- [ ] RED: descriptor, canonical translation, no legacy import/network dependency/secrets, protection/policy refs, place/cancel always unavailable.
- [ ] Run focused RED.
- [ ] Implement translation seam only.
- [ ] Guard rejects any Package-1 default network mutation/client/credential composition.
- [ ] GREEN seam + Phase-6 Angel/read-only/protection + both guards.
- [ ] Commit `feat: add disarmed Angel One V2 mutation seam`.

### Task 8: End-to-End Reunion Invariants + Regression Preservation

**Files:** Create `tests_v1/test_v2_live_reunion_end_to_end.py`; update manifest implementation/test columns.

**Test harness:** test-local release gate + fake mutation port compose a genuine RiskGate Live `ApprovedOrder`, lifecycle, V9 journal, reconciliation, exclusivity, eligibility, audit, and `LiveStateMachine`. Production remains closed because there is no production open gate, `BoundBrokerPort` still hard-blocks Live, and Angel place/cancel remain unavailable.

- [ ] E2E tests: ApprovedOrder test path, duplicate replay, pre-call `SENT_UNACKED`, timeout→IN_DOUBT→broker truth, fresh reapproval after NOT_FOUND only, restart no-auto-arm, foreign halt, exclusivity conflict, protection block, audit failure, Emergency Stop vs explicit FLATTEN_ALL.
- [ ] Negative authority tests: AI/Laya/dashboard/Paper/Backtest cannot reach mutation directly.
- [ ] Run focused Tasks 1–8.
- [ ] Run preservation: Phase-2 RiskGate/hard-limits/intent/kill-switch/mode isolation/order lifecycle; Phase-3 feed; Phase-5 recovery/safety; Phase-6 read-only/transport/protection; S2 device/session/cloud-outage; RiskGate fast-path focused suite.
- [ ] Run `python -m pytest tests_v1 -q`; any executable failure → systematic debugging before fixes.
- [ ] Commit `test: lock V1-to-V2 Live reunion invariants`.

### Task 9: Exact-Head Dual-Windows Qualification + Evidence

**Files:** Create `.github/workflows/live-v1-v2-reunion-qualification.yml`, `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md`.

**Workflow:** `workflow_dispatch`; Python 3.13.14; Windows latest + Windows 2022; same exact SHA. Both run compile, module boundaries, Phase-6 readonly guard, reunion guard, focused reunion and preservation suites; primary leg also runs full `tests_v1`. No frontend work unless UI is actually changed.

- [ ] Static workflow test/inspection proves same SHA on both legs and prevents GREEN if a leg never executes.
- [ ] Commit workflow/evidence skeleton without product changes.
- [ ] Dispatch on frozen final Package-1 SHA when runners are available. Zero-step/no-runner = `EXECUTION BLOCKED`, neither RED nor GREEN.
- [ ] Executable failure → systematic debugging, new fix commit, rerun exact head; never rewrite checkpoints/evidence.
- [ ] Record run/job IDs, exact SHA, test counts, artifacts/fingerprints, limitations, remaining Package-2 gates.
- [ ] Create final verified Package-1 checkpoint only after both Windows legs + required regression execute cleanly. Live stays READ_ONLY/DISARMED.
- [ ] Commit `test: qualify V1-to-V2 Live reunion`.

---

## Package-1 Completion Boundary

Package 1 is complete only when the manifest is final, one canonical authority path is structurally enforced, focused/full regression evidence is current-head clean, both Windows qualification legs actually execute successfully, and exact-SHA evidence is archived. This does **not** authorize production mutation or a real-money pilot.

## Package-2 Handoff — Separate Future Design/Approval

Package 2 must be separately brainstormed/designed/approved after Package 1 verification. It covers current broker/exchange/regulatory recheck, production network mutation transport, credential custody/static-IP eligibility, permitted broker/sandbox evidence, any reviewed change to the current `BoundBrokerPort` Live hard-block, release defect gates, protection verification, staged minimum-exposure pilot controls, incident rollback criteria, and explicit Owner arming authorization. It must not be silently folded into Package 1.

## Rollback and Commit Discipline

- One task = one independently reviewable commit.
- Failed focused/static checks are fixed/reverted; guards are never weakened just to pass.
- Never force-move `4713b4df...`.
- Historical PASS is never current-head proof.
- Never merge to `main`, permit Live in `BoundBrokerPort`, add a production-open release gate, or enable real-money mutation merely because local tests pass.
