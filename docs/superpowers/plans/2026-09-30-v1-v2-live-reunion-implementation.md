# AlgoFortis V1 → V2 Live Reunion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently reunite proven V1 Live/recovery behavior with the current V2 safety spine through one canonical, testable Live path while keeping real broker mutation unreachable and Live `READ_ONLY / DISARMED` throughout Package 1.

**Architecture:** Reuse the existing `ApprovedOrder`, deterministic `client_order_id`, `OrderExecutionLifecycle`/`OrderExecutionState`, `LiveStateMachine`, `BoundBrokerPort`, Phase-6 read-only coordinator/reconciler, S2 gate contracts, and Angel One V2 protection/read-side components. Add only missing focused pieces: permanent donor manifest/guard, additive V9 Live evidence schema, dormant `LiveExecutionCoordinatorV2` behind a production-closed release gate, local account exclusivity, Live eligibility composition, and an Angel One mutation translation seam whose mutation methods remain unavailable in Package 1.

**Tech Stack:** Python 3.13.14, dataclasses/enums/protocols, SQLite additive migrations, pytest, existing AlgoFortis V2 contracts, GitHub Actions dual-Windows qualification.

**Spec:** `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design.md` + `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design-approval.md`

**Normative amendment:** `docs/superpowers/plans/2026-10-01-v1-v2-live-reunion-concurrency-ai-amendment.md` — binding account-domain isolation, deterministic same-account candidate arbitration, and AI provider quota/rate-limit queue rules.

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
- Account capital/exposure authority is scoped by exact `(broker_id, broker_account_ref)`; different broker-account domains never consume each other's capital pool.
- Candidates sharing one broker-account domain must be deterministically arbitrated before atomic reservation; OS/thread arrival order and AI/provider timing may not decide the winner.
- Pending/unfilled orders continue consuming reserved capital/exposure until explicit terminal/reconciliation release.
- AlgoFortis monitoring policy/scheduler, never Laya/provider output, owns AI instrument scope, frequency, trigger, task TTL, provider/model assignment, and concurrency.
- AI provider rate/quota exhaustion uses a bounded deterministic queue; stale queued jobs are not executed later as fresh work, and no silent provider fallback is allowed.

## Review Focus

1. Timeout/restart duplicate submission → one `client_order_id`; `IN_DOUBT` reconciled, never blindly retried.
2. Local persistence mistaken for broker truth → broker query remains authoritative.
3. Second local device/session owner → conflict/uncertainty fails closed; cloud is not trading authority.
4. Protection capability disappears/changes → Live eligibility blocks.
5. Dormant write seam becomes reachable → closed gate + unchanged `BoundBrokerPort` + unavailable Angel mutation methods must prevent it.
6. Same-account simultaneous candidates → deterministic arbiter + correlated exposure + atomic reservation; no stale-balance oversubscription.
7. Different broker accounts → independent capital domains may progress independently; provider/DB implementation details must not logically couple their budgets.
8. AI monitoring/provider pressure → scheduler owns scope; bounded provider queue preserves deterministic order/TTL and cannot self-expand or bypass quota.

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
- `engine/live/account_candidate_arbiter_v2.py`
- `engine/live/live_eligibility_v2.py`
- `engine/ai/monitoring_scheduler_v2.py`
- `engine/ai/provider_queue_v2.py`
- `engine/broker_adapters/angelone_v2/mutation_seam_v2.py`
- focused tests listed below
- `.github/workflows/live-v1-v2-reunion-qualification.yml`
- `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md`

**Modify narrowly**
- `engine/persistence/schema.py`
- `engine/persistence/migrations.py`
- `engine/orders/lifecycle_v2.py`
- `engine/reconciliation/live_reconciler.py`
- `engine/live/execution_capacity_v2.py`
- `engine/live/phase6_readonly_coordinator.py` only if the existing foreign-activity result needs exposure
- `engine/ai/contracts.py`, `engine/ai/orchestrator.py`, `engine/ai/provider_registry.py` only as required to express deterministic scheduling/queue evidence without expanding AI authority
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

### Task 2A: Deterministic Account Candidate Arbiter + Capital-Domain Isolation

**Files:** Create `engine/live/account_candidate_arbiter_v2.py`, `tests_v1/test_live_account_candidate_arbiter_v2.py`; modify `engine/live/execution_capacity_v2.py`, `engine/persistence/live_execution_store_v2.py`, `engine/persistence/live_execution_schema_v9.py`; extend capacity tests.

**Interfaces / authority:**
- immutable `AccountCapitalDomainKey(broker_id: str, broker_account_ref: str)` is the sole shared-capital domain identity.
- capacity evidence/reservations must carry both `broker_id` and `broker_account_ref`.
- `LiveAccountCandidateArbiterV2` may rank/restrict genuine trade candidates for one account domain but cannot mint `ApprovedOrder`, alter RiskGate evidence, or call broker mutation.
- Same-domain deterministic ordering is: (1) hard/pre-eligibility, (2) current portfolio/correlated-exposure interaction, (3) owner-configured strategy priority, (4) deterministic pre-AI edge/quality evidence, (5) deterministic capital-efficiency evidence, (6) signal/event timestamp, (7) stable candidate identity.
- No guessed correlated-exposure or capital thresholds: all limits come from versioned owner/risk policy evidence.
- Different `AccountCapitalDomainKey` values may be processed by separate arbiter instances in parallel. A shared SQLite backend may briefly serialize writes for integrity, but budget calculations/aggregates must remain domain-scoped and independent.
- Pending/unfilled reservations remain active until explicit terminal/reconciliation release.

- [ ] RED: two same-domain concurrent candidates cannot both consume stale full cash; ordering is independent of thread arrival.
- [ ] RED: correlated-exposure policy can block a candidate even when cash is sufficient.
- [ ] RED: pending/unfilled order remains in account exposure/capital calculations.
- [ ] RED: two different `(broker_id, broker_account_ref)` domains reserve independently and never cross-count.
- [ ] RED: same-looking `broker_account_ref` on different `broker_id` values does not collide.
- [ ] RED: stable inputs always produce the same tie-break result; AI response time/content cannot reorder the batch.
- [ ] Harden V9 capacity identity and queries from `broker_account_ref` to `(broker_id, broker_account_ref)` before Package-1 qualification; global `client_order_id` uniqueness remains unchanged.
- [ ] GREEN focused arbiter/capacity/store tests + Task-2 persistence regressions.
- [ ] Commit `feat: isolate broker-account capital domains and arbitrate concurrent candidates`.

### Task 3: Production-Closed Gate + Dormant `LiveExecutionCoordinatorV2`

**Files:** Create `engine/live/mutation_release_gate_v2.py`, `engine/live/execution_coordinator_v2.py`, `tests_v1/test_live_execution_coordinator_v2.py`; extend reunion guard test.

**Interfaces:**
- `LiveMutationBlocked(RuntimeError)`.
- `LiveMutationReleaseGate.authorize(*, order: ApprovedOrder, live_state: LiveState) -> str` Protocol.
- `ClosedLiveMutationReleaseGate.authorize(...)` always raises `LiveMutationBlocked("live mutation release gate is closed")`.
- `_LiveBrokerMutationPort.place(order: ApprovedOrder) -> object` Protocol inside coordinator; production is intended to compose `BoundBrokerPort`, while tests use a test-local fake because `BoundBrokerPort` intentionally blocks all Live mutation in Package 1.
- `LiveExecutionCoordinatorV2.__init__(*, broker_port: _LiveBrokerMutationPort, journal: LiveExecutionStoreV2, release_gate: LiveMutationReleaseGate, state_machine: LiveStateMachine, audit_sink: object, clock: object) -> None`.
- `submit(order: ApprovedOrder) -> object`.

**Sequence:** genuine unexpired `RunMode.LIVE` approval → require `LiveState.ACTIVE` → release-gate authorization → account-domain arbiter/capacity authorization → reserve unique journal record → `OrderExecutionLifecycle` starts `RISK_APPROVED` → persist `SUBMITTING` → persist `SENT_UNACKED` **before** broker call → call `place` → acknowledgement maps to `ACKED` + broker identity; exception after call boundary maps to `IN_DOUBT`; never auto-resubmit.

- [ ] RED: wrong type/mode, expired approval, duplicate ID, non-ACTIVE state, closed-gate port call count zero, test-local fake-gate/fake-port success, ack mapping once, exception→`IN_DOUBT`, second submit rejected, audit failure blocks call.
- [ ] RED: same-account arbitration/capacity denial blocks broker call; different account domain does not consume this account's budget.
- [ ] Run focused RED.
- [ ] Implement closed gate with no env/config/CLI opener.
- [ ] Implement coordinator using existing lifecycle/client ID/store; no approval minting/reconciliation ownership.
- [ ] Guard rejects production open gate/direct broker bypass.
- [ ] GREEN coordinator + Task-2A account-domain tests + Phase-2 RiskGate authority/mode isolation + both static guards.
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

### Task 6A: AI Monitoring Scheduler + Provider Quota/Rate Queue

**Files:** Create `engine/ai/monitoring_scheduler_v2.py`, `engine/ai/provider_queue_v2.py`, `tests_v1/test_ai_monitoring_scheduler_v2.py`, `tests_v1/test_ai_provider_queue_v2.py`; modify `engine/ai/contracts.py`, `engine/ai/orchestrator.py`, `engine/ai/provider_registry.py` only as needed.

**Authority:** current AI stays `RESEARCH` / `SHADOW` and advisory-only. This task adds deterministic scheduling/queue boundaries; it does not grant AI trading, RiskGate, account-capital, Live-state, or broker authority.

**Required contracts:**
- scheduler-created immutable AI task includes stable task identity, exact instrument/scope, reason/trigger, data-window/evidence refs, created-at, `valid_until`, and deterministic priority evidence.
- Laya/provider may consume only that task; it cannot create follow-up scope/schedule changes or mutate task fields.
- provider queue is bounded by versioned provider policy/evidence for concurrency/rate/quota/queue behavior; no guessed production limits are hardcoded.
- quota/rate exhaustion queues a valid task; no direct bypass call is allowed.
- queued task TTL expiry => stale/blocked/cancelled without later execution.
- different providers may operate independent bounded queues only when `PrimeOrchestrator`/owner routing policy explicitly assigns them; no automatic fallback.
- queue ordering uses the same deterministic seven-stage candidate-priority policy only from fields already available before the AI call: hard/pre-eligibility, portfolio/exposure interaction, strategy priority, pre-AI deterministic edge/quality, precomputed capital efficiency, signal/event timestamp, stable task/candidate identity. Missing fields use deterministic neutral/default ordering; AI cannot invent them or use its own output to move itself forward.

- [ ] RED: AI cannot self-schedule, add a symbol, change frequency, extend TTL, or spawn follow-up monitoring outside scheduler authority.
- [ ] RED: provider quota exhaustion queues rather than exceeding configured capacity.
- [ ] RED: same jobs/policy always produce same queue order independent of thread/provider response timing.
- [ ] RED: expired queued task never executes.
- [ ] RED: AI output cannot mint `ApprovedOrder`, reserve account capital, alter Account Arbiter priority, arm Live, or call mutation.
- [ ] RED: no silent provider fallback on quota/failure.
- [ ] GREEN scheduler/queue + existing AI contracts/provider registry/orchestrator/authority boundary regressions.
- [ ] Commit `feat: bound AI monitoring by scheduler and provider quota queue`.

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

**Test harness:** test-local release gate + fake mutation port compose a genuine RiskGate Live `ApprovedOrder`, lifecycle, V9 journal, deterministic account arbiter/capacity domain, reconciliation, exclusivity, eligibility, audit, AI-scheduler/provider-queue authority checks, and `LiveStateMachine`. Production remains closed because there is no production open gate, `BoundBrokerPort` still hard-blocks Live, and Angel place/cancel remain unavailable.

- [ ] E2E tests: ApprovedOrder test path, duplicate replay, pre-call `SENT_UNACKED`, timeout→IN_DOUBT→broker truth, fresh reapproval after NOT_FOUND only, restart no-auto-arm, foreign halt, exclusivity conflict, protection block, audit failure, Emergency Stop vs explicit FLATTEN_ALL.
- [ ] E2E same-account concurrency: BANKNIFTY/NIFTY/SENSEX-style simultaneous candidates share one deterministic arbiter/capital pool, respect correlated exposure and pending reservations, and cannot double-count cash/exposure.
- [ ] E2E different-account concurrency: different `(broker_id, broker_account_ref)` domains remain budget-independent and can progress independently.
- [ ] E2E AI monitoring: scheduler fixes scope/TTL; provider quota queues deterministically; stale jobs do not execute; AI timing/output cannot alter capital arbitration.
- [ ] Negative authority tests: AI/Laya/dashboard/Paper/Backtest cannot reach mutation directly.
- [ ] Run focused Tasks 1–8 including 2A and 6A.
- [ ] Run preservation: Phase-2 RiskGate/hard-limits/intent/kill-switch/mode isolation/order lifecycle; Phase-3 feed; Phase-5 recovery/safety; Phase-6 read-only/transport/protection; S2 device/session/cloud-outage; existing AI authority/provider registry/orchestrator; RiskGate fast-path focused suite.
- [ ] Run `python -m pytest tests_v1 -q`; any executable failure → systematic debugging before fixes.
- [ ] Commit `test: lock V1-to-V2 Live reunion invariants`.

### Task 9: Exact-Head Dual-Windows Qualification + Evidence

**Files:** Create `.github/workflows/live-v1-v2-reunion-qualification.yml`, `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md`.

**Workflow:** `workflow_dispatch`; Python 3.13.14; Windows latest + Windows 2022; same exact SHA. Both run compile, module boundaries, Phase-6 readonly guard, reunion guard, focused reunion/account-domain/AI-queue and preservation suites; primary leg also runs full `tests_v1`. No frontend work unless UI is actually changed.

- [ ] Static workflow test/inspection proves same SHA on both legs and prevents GREEN if a leg never executes.
- [ ] Commit workflow/evidence skeleton without product changes.
- [ ] Dispatch on frozen final Package-1 SHA when runners are available. Zero-step/no-runner = `EXECUTION BLOCKED`, neither RED nor GREEN.
- [ ] Executable failure → systematic debugging, new fix commit, rerun exact head; never rewrite checkpoints/evidence.
- [ ] Record run/job IDs, exact SHA, test counts, artifacts/fingerprints, limitations, account-domain isolation evidence, AI scheduler/provider-queue evidence, and remaining Package-2 gates.
- [ ] Create final verified Package-1 checkpoint only after both Windows legs + required regression execute cleanly. Live stays READ_ONLY/DISARMED.
- [ ] Commit `test: qualify V1-to-V2 Live reunion`.

---

## Package-1 Completion Boundary

Package 1 is complete only when the manifest is final, one canonical authority path is structurally enforced, same-account arbitration/account-domain isolation and AI scheduling/provider-queue authority are verified, focused/full regression evidence is current-head clean, both Windows qualification legs actually execute successfully, and exact-SHA evidence is archived. This does **not** authorize production mutation or a real-money pilot.

## Package-2 Handoff — Separate Future Design/Approval

Package 2 must be separately brainstormed/designed/approved after Package 1 verification. It covers current broker/exchange/regulatory recheck, production network mutation transport, credential custody/static-IP eligibility, permitted broker/sandbox evidence, any reviewed change to the current `BoundBrokerPort` Live hard-block, release defect gates, protection verification, staged minimum-exposure pilot controls, incident rollback criteria, and explicit Owner arming authorization. It must not be silently folded into Package 1.

## Rollback and Commit Discipline

- One task = one independently reviewable commit.
- Failed focused/static checks are fixed/reverted; guards are never weakened just to pass.
- Never force-move `4713b4df...`.
- Historical PASS is never current-head proof.
- Never merge to `main`, permit Live in `BoundBrokerPort`, add a production-open release gate, or enable real-money mutation merely because local tests pass.
