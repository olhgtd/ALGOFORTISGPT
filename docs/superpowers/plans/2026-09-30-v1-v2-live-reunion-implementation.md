# AlgoFortis V1 → V2 Live Reunion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently reunite proven V1 Live/recovery behavior with the current V2 safety spine through one canonical, testable Live path while keeping real broker mutation unreachable and Live `READ_ONLY / DISARMED` throughout Package 1.

**Architecture:** Reuse the existing V2 `ApprovedOrder`, deterministic `client_order_id`, `OrderExecutionLifecycle`, `LiveStateMachine`, `BoundBrokerPort`, Phase-6 read-only coordinator/reconciler, and Angel One V2 protection/read-side components. Add only the missing focused pieces: a permanent donor manifest and boundary guard, an additive V9 Live execution journal, a dormant `LiveExecutionCoordinatorV2` behind a production-closed release gate, an account-local exclusivity backstop, Live eligibility composition, and a mutation-adapter seam that has no production enable path in Package 1.

**Tech Stack:** Python 3.13.14, dataclasses/enums/protocols, SQLite additive migrations, pytest, existing AlgoFortis audit/reconciliation/risk/broker contracts, GitHub Actions dual-Windows qualification; dashboard TypeScript/Vitest only if a later reviewed slice requires UI evidence.

**Spec:** `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design.md` plus approval amendment `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design-approval.md`

## Global Constraints

- Live remains `READ_ONLY / DISARMED` through this entire implementation plan.
- `RiskGateV2` remains the sole executable-order approval authority; no new mint path for `ApprovedOrder`.
- Never move or rewrite historical checkpoint `4713b4dfb1d250ac01cf23dc73e89ddeac7716de`.
- Existing `engine/orders/lifecycle_v2.py` is the sole order-lifecycle state machine; do not create a second lifecycle.
- Existing deterministic `client_order_id` from `engine/orders/contracts_v2.py` is authoritative; do not create a second identity scheme.
- Existing `engine/live/phase6_readonly_coordinator.py` + `LiveBrokerReconciler` remain the foreign-activity/recovery authorities; do not create parallel engines.
- Existing Phase-6 transport runtime remains the sole reconnect/generation authority.
- Do not weaken or delete `build/tools/check_phase6_live_readonly.py` during Package 1.
- Do not promote legacy `engine/broker_adapters/angel_adapter.py`; it is reference-only.
- Paper/Backtest cannot bind real-broker mutation adapters or credentials.
- AI/Laya/dashboard/alerts/reporting/persistence cannot call broker mutation directly.
- Restart/reconnect/recovery/clean reconciliation never auto-arm Live.
- Missing/corrupt journal, broker truth, protection evidence, exclusivity evidence, audit, or policy fails closed.
- No real broker credentials, real orders, or real-money mutation are required or authorized by this plan.
- No new production numeric thresholds are invented to make tests pass.

## Review Focus

1. **Duplicate submission after timeout/restart:** one canonical `client_order_id` must remain one submission identity; `IN_DOUBT` is reconciled, never blindly retried. Test in Tasks 2–4.
2. **Persistence mistaken for broker truth:** journal recovery may reconstruct local evidence but must query `LiveBrokerReconciler` before entries/resubmission. Test in Task 4.
3. **Second local device/process owner:** any conflicting or indeterminate Live ownership must fail closed without cloud becoming authority. Test in Task 5.
4. **Protection disappears or adapter capability changes:** required broker-resident protection missing/unsupported must make the path ineligible and keep it DISARMED. Test in Task 6.
5. **Dormant mutation seam accidentally becomes reachable:** production code must have only a closed release-gate implementation in Package 1 and the existing Phase-6 mutation firewall must remain green. Test/static guard in Tasks 1, 3, 7 and 8.

---

## File Structure Locked by This Plan

**Create**
- `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md` — permanent donor classification/source map.
- `build/tools/check_live_reunion_boundary.py` — permanent alternate-authority/import/reachability guard.
- `engine/persistence/live_execution_schema_v9.py` — additive V9 SQL only.
- `engine/persistence/live_execution_store_v2.py` — focused durable Live execution evidence journal.
- `engine/live/mutation_release_gate_v2.py` — production-closed mutation authorization protocol/implementation.
- `engine/live/execution_coordinator_v2.py` — single orchestration seam from `ApprovedOrder` to `BoundBrokerPort`.
- `engine/live/account_exclusivity_v2.py` — local broker-account Live ownership backstop.
- `engine/live/live_eligibility_v2.py` — composition of state/S2/exclusivity/protection/recovery prerequisites.
- `engine/broker_adapters/angelone_v2/mutation_seam_v2.py` — dormant V2 mutation contract/translation seam; no production HTTP mutation in Package 1.
- focused tests named in tasks below.
- `.github/workflows/live-v1-v2-reunion-qualification.yml` — exact-head manual qualification.
- `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md` — final evidence record.

**Modify narrowly**
- `engine/persistence/schema.py` — V8 → V9 facade composition only.
- `engine/persistence/migrations.py` — add `LIVE_EXECUTION_V9_MIGRATION` only.
- `engine/reconciliation/live_reconciler.py` — bridge unresolved journal entries to existing broker-truth reconciliation, without making persistence authoritative.
- `engine/live/phase6_readonly_coordinator.py` — expose/use existing foreign-activity result in reunion recovery flow only if needed.
- `engine/broker_adapters/angelone_v2/protection_capability.py` and/or `order_policy.py` only if an existing capability cannot express eligibility required by Task 6.

**Do not grow**
- `engine/persistence/sqlite_store.py`
- legacy paper/live coordinator monoliths
- legacy entry pipeline/risk manager/protective monoliths
- legacy direct Angel mutation adapter

---

### Task 1: Lock the Permanent Reunion Manifest and Boundary Guard

**Files:**
- Create: `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md`
- Create: `build/tools/check_live_reunion_boundary.py`
- Create: `tests_v1/test_v2_live_reunion_boundary.py`

**Interfaces:**
- Produces manifest statuses exactly: `SALVAGED`, `REFERENCE_ONLY`, `REPLACED_BY_V2`, `DEFERRED`.
- Produces CLI guard exit `0` with marker `LIVE_REUNION_BOUNDARY_PASS` only when all forbidden authority paths are absent.

- [ ] **Step 1: Write RED architecture tests** asserting the guard rejects fixture/source patterns for direct broker mutation imports from strategy/AI/dashboard/alerts/reporting/persistence/Paper, direct `_mint_approved_order`, production reachability of `angel_adapter.py`, second reconnect authority, and restart auto-arm tokens outside the canonical Live state boundary.
- [ ] **Step 2: Run RED:** `python -m pytest tests_v1/test_v2_live_reunion_boundary.py -q`; expected FAIL because the guard/manifest do not exist.
- [ ] **Step 3: Create the manifest** with exact known donor mappings from the approved spec and columns: donor capability/path, historical evidence, classification, V2 owner, migration method, regression tests, safety note, implementation commit.
- [ ] **Step 4: Implement the static guard** using repo-relative deterministic scanning; explicitly allow canonical V2 files and reject legacy/direct authority patterns. Keep `check_phase6_live_readonly.py` unchanged.
- [ ] **Step 5: Run GREEN:** focused test + `python build/tools/check_live_reunion_boundary.py` + `python build/tools/check_phase6_live_readonly.py`; all must pass.
- [ ] **Step 6: Commit:** `docs: lock V1-to-V2 Live reunion manifest`.

---

### Task 2: Add the Additive V9 Live Execution Journal

**Files:**
- Create: `engine/persistence/live_execution_schema_v9.py`
- Create: `engine/persistence/live_execution_store_v2.py`
- Modify: `engine/persistence/schema.py`
- Modify: `engine/persistence/migrations.py`
- Create: `tests_v1/test_live_execution_store_v2.py`

**Interfaces:**
- `LiveExecutionRecord` immutable fields: `client_order_id`, `approved_order_ref`, `run_mode`, `lifecycle_state`, optional `broker_order_identity`, `submission_attempt_id`, `created_at_utc`, `updated_at_utc`, `is_uncertain`, optional `adapter_id`, optional `policy_ref`, optional `audit_ref`.
- `LiveExecutionStoreV2.reserve(record: LiveExecutionRecord) -> LiveExecutionRecord`
- `LiveExecutionStoreV2.get(client_order_id: str) -> LiveExecutionRecord | None`
- `LiveExecutionStoreV2.transition(client_order_id: str, *, lifecycle_state: OrderState, broker_order_identity: str | None = None, is_uncertain: bool | None = None, audit_ref: str | None = None) -> LiveExecutionRecord`
- `LiveExecutionStoreV2.list_uncertain() -> tuple[LiveExecutionRecord, ...]`
- `LIVE_EXECUTION_V9_MIGRATION`: version `8 -> 9`.

- [ ] **Step 1: Write RED tests** for V8→V9 migration/rollback, unique `client_order_id`, persistence across reopen, legal lifecycle values, `IN_DOUBT` persistence, no secret/token columns, and corrupt/duplicate writes failing closed.
- [ ] **Step 2: Run RED:** `python -m pytest tests_v1/test_live_execution_store_v2.py -q`; expected FAIL because V9/store do not exist.
- [ ] **Step 3: Add `live_execution_schema_v9.py`** with additive create/drop SQL and a unique index on `client_order_id`; do not modify legacy V7 or Phase-5 V8 files.
- [ ] **Step 4: Update schema/migration facades** to `SCHEMA_VERSION = 9`, compose V7 + V8 + V9 create SQL, and export `LIVE_EXECUTION_V9_MIGRATION`.
- [ ] **Step 5: Implement focused store** using injected SQLite connection/path pattern consistent with `paper_recovery_store_v2.py`; persistence is evidence only, never broker truth.
- [ ] **Step 6: Run GREEN:** focused test, migration regression, and existing Phase-5 recovery-store tests.
- [ ] **Step 7: Commit:** `feat: add V2 Live execution journal`.

---

### Task 3: Add a Production-Closed Mutation Gate and Dormant `LiveExecutionCoordinatorV2`

**Files:**
- Create: `engine/live/mutation_release_gate_v2.py`
- Create: `engine/live/execution_coordinator_v2.py`
- Create: `tests_v1/test_live_execution_coordinator_v2.py`
- Extend: `tests_v1/test_v2_live_reunion_boundary.py`

**Interfaces:**
- `LiveMutationBlocked(RuntimeError)`.
- `LiveMutationReleaseGate` Protocol: `authorize(*, order: ApprovedOrder, live_state: LiveState) -> str`; success returns a non-empty authorization evidence ref, denial raises `LiveMutationBlocked`.
- `ClosedLiveMutationReleaseGate.authorize(...) -> str` always raises `LiveMutationBlocked("live mutation release gate is closed")`.
- No production `Open*`/`Allow*` implementation exists in Package 1. Tests may define a local fake protocol implementation inside the test file only.
- `LiveExecutionCoordinatorV2.submit(order: ApprovedOrder, *, now: datetime) -> object`.

**Coordinator responsibilities:** genuine `ApprovedOrder` + `RunMode.LIVE`; state must be ACTIVE only after the canonical state machine has reached it; persistent duplicate reservation before broker call; lifecycle `CREATED -> SUBMITTING`; release gate check immediately before mutation; broker acknowledgement persisted once; exception/unknown acknowledgement after attempted send becomes `IN_DOUBT`; no blind retry; mandatory audit-before/after behavior follows existing audit policy.

- [ ] **Step 1: Write RED tests** for wrong mode/forged input rejection, duplicate `client_order_id`, production closed-gate no-call guarantee (`adapter.place` call count zero), test-local permitted fake path, acknowledgement persistence, send/no-ack → `IN_DOUBT`, and second submit of `IN_DOUBT` rejected without broker call.
- [ ] **Step 2: Run RED:** `python -m pytest tests_v1/test_live_execution_coordinator_v2.py -q`.
- [ ] **Step 3: Implement closed release gate** with no environment variable/config/CLI switch that can open it.
- [ ] **Step 4: Implement minimal coordinator** reusing `OrderExecutionLifecycle`, existing deterministic `client_order_id`, `LiveExecutionStoreV2`, and `BoundBrokerPort`; do not mint approvals and do not own reconciliation.
- [ ] **Step 5: Extend static guard** to reject any production implementation of the release-gate protocol that returns authorization and any direct bypass around the coordinator.
- [ ] **Step 6: Run GREEN:** coordinator tests + Phase-2 RiskGate authority/mode isolation + both static guards.
- [ ] **Step 7: Commit:** `feat: add dormant V2 Live execution coordinator`.

---

### Task 4: Bridge `IN_DOUBT` and Restart Recovery to Existing Broker Truth

**Files:**
- Modify: `engine/reconciliation/live_reconciler.py`
- Modify only if needed: `engine/live/phase6_readonly_coordinator.py`
- Create: `tests_v1/test_live_reunion_reconciliation_v2.py`

**Interfaces:**
- Add focused method `LiveBrokerReconciler.reconcile_uncertain_orders(records: Sequence[LiveExecutionRecord], *, fail_closed: bool = True) -> tuple[OrderReconciliationItem, ...]`.
- It queries broker truth by stored broker identity/client identity as supported by the existing adapter and never calls submit/place.
- The coordinator/recovery caller updates the journal only from reconciliation results; the journal does not decide broker truth.

- [ ] **Step 1: Write RED tests** for `IN_DOUBT` resolved as filled/cancelled/rejected/open, broker query failure remaining fail-closed, partial-fill + disconnect convergence, restart with open position entering recovery before entries, and absolutely no retry/place call during reconciliation.
- [ ] **Step 2: Add foreign-activity regression** proving existing broker-only order/position handling still halts new entries + critical alert/audit and never auto-adopts or auto-flattens.
- [ ] **Step 3: Run RED:** `python -m pytest tests_v1/test_live_reunion_reconciliation_v2.py -q`.
- [ ] **Step 4: Implement minimal reconciler bridge** reusing existing `LiveBrokerReconciler` item types and Phase-6 coordinator incident/alert path; no second foreign-activity service.
- [ ] **Step 5: Run GREEN:** new tests + `tests_v1/test_area14_live_reconciliation_restart.py` + Phase-5 recovery regressions.
- [ ] **Step 6: Commit:** `feat: reconcile uncertain Live orders through broker truth`.

---

### Task 5: Add Local Broker-Account Live Exclusivity Backstop

**Files:**
- Create: `engine/live/account_exclusivity_v2.py`
- Create: `tests_v1/test_live_account_exclusivity_v2.py`

**Interfaces:**
- `LiveAccountOwner` immutable record: `broker_id`, `broker_account_ref`, `device_id`, `session_family_id`, `ownership_nonce`, `acquired_at_utc`.
- `LiveAccountExclusivityV2.acquire(candidate: LiveAccountOwner) -> LiveAccountOwner`
- `LiveAccountExclusivityV2.verify(candidate: LiveAccountOwner) -> bool`
- `LiveAccountExclusivityV2.release(candidate: LiveAccountOwner) -> None`
- `LiveAccountExclusivityV2.restore_after_restart(...)` must return/enter an unowned state requiring fresh explicit acquisition; never restore armed ownership from disk alone.

**Rules:** local durable hard backstop; conflict/unknown/corrupt evidence fails closed; cloud may supply advisory evidence but is never required to preserve safety; valid S2 device/session prerequisite is consumed as evidence but does not arm Live.

- [ ] **Step 1: Write RED tests** for same owner idempotent verification, second device conflict, second session conflict where policy requires, corrupt/unknown ownership, restart clearing armed ownership, cloud unavailable with local safety intact, and foreign broker activity causing ownership/entry halt rather than takeover.
- [ ] **Step 2: Run RED:** `python -m pytest tests_v1/test_live_account_exclusivity_v2.py -q`.
- [ ] **Step 3: Implement local backstop** with an injected focused persistence seam; do not use hostname/MAC/IP as trust and do not create cloud lease authority.
- [ ] **Step 4: Run GREEN** plus S2 regressions: `tests_v1/test_s2_device_session_gate.py`, `tests_v1/test_s2_cloud_outage.py`, and `tests_v1/test_s2_device_service.py`.
- [ ] **Step 5: Commit:** `feat: add local Live account exclusivity backstop`.

---

### Task 6: Compose Live Eligibility with Broker-Resident Protection

**Files:**
- Create: `engine/live/live_eligibility_v2.py`
- Reuse/modify narrowly if required: `engine/broker_adapters/angelone_v2/protection_capability.py`
- Reuse/modify narrowly if required: `engine/broker_adapters/angelone_v2/order_policy.py`
- Create: `tests_v1/test_live_eligibility_v2.py`
- Extend: `tests_v1/test_phase6_protection_capability.py`

**Interfaces:**
- `LiveEligibilityStatus`: `ELIGIBLE_FOR_QUALIFICATION`, `BLOCKED` (never means armed or production-authorized).
- `LiveEligibilityResult`: immutable `status`, `reasons`, `evidence_refs`.
- `LiveEligibilityV2.evaluate(*, live_state, s2_gate_result, exclusivity_ok, reconciliation_clean, protection_capability, broker_policy_ref, audit_ready) -> LiveEligibilityResult`.

- [ ] **Step 1: Write RED tests** proving missing/unsupported required broker protection => `BLOCKED`; missing current policy/evidence => `BLOCKED`; dirty reconciliation, invalid S2, exclusivity conflict, non-ready Live state, or audit unavailable => `BLOCKED`; all software prerequisites produce only `ELIGIBLE_FOR_QUALIFICATION`, never ACTIVE/armed.
- [ ] **Step 2: Run RED:** focused eligibility + protection tests.
- [ ] **Step 3: Implement pure eligibility composition** using existing protection capability/policy models; no degraded policy is invented.
- [ ] **Step 4: Run GREEN** plus `test_phase6_protection_capability.py`, Phase-6 policy tests, state-machine tests, and S2 gate tests.
- [ ] **Step 5: Commit:** `feat: enforce Live protection eligibility`.

---

### Task 7: Add the First Angel One V2 Mutation Seam — Still DISARMED

**Files:**
- Create: `engine/broker_adapters/angelone_v2/mutation_seam_v2.py`
- Create: `tests_v1/test_angelone_v2_mutation_seam.py`
- Extend: `build/tools/check_live_reunion_boundary.py`

**Interfaces:**
- Implement `BrokerPortAdapterV2` shape for a mutation-capable descriptor with `RunMode.LIVE`, `BrokerMutationKind.REAL_BROKER`, `BrokerCredentialScope.REAL_BROKER`.
- The seam translates canonical V2 order/protection requests into a broker-neutral request object and exposes capabilities/read methods needed by `BoundBrokerPort`.
- Package 1 must not contain production HTTP `place/cancel/modify` transport. Its mutation methods raise a typed `AngelOneV2MutationUnavailable` unless an explicitly injected **test/sandbox transport object** is supplied by tests; no default real network transport or credentials are created.

- [ ] **Step 1: Write RED tests** for descriptor correctness, canonical-order-only input, no legacy adapter import, no default HTTP/network mutation, no credentials in repr/logs, injected test transport translation, capability/version-policy handoff, and broker-resident protection request shape where supported.
- [ ] **Step 2: Run RED:** `python -m pytest tests_v1/test_angelone_v2_mutation_seam.py -q`.
- [ ] **Step 3: Implement dormant seam** without importing/promoting `engine/broker_adapters/angel_adapter.py` and without a production network client.
- [ ] **Step 4: Extend guard** so a later accidental default network mutation implementation makes Package-1 qualification RED until separately designed/approved.
- [ ] **Step 5: Run GREEN:** seam tests + Phase-6 Angel/read-only/protection tests + both static guards.
- [ ] **Step 6: Commit:** `feat: add disarmed Angel One V2 mutation seam`.

---

### Task 8: End-to-End Reunion Invariants and Regression Preservation

**Files:**
- Create: `tests_v1/test_v2_live_reunion_end_to_end.py`
- Update manifest implementation-commit/test columns as each task lands.

**Interfaces:**
- One deterministic test harness composes RiskGate-produced Live `ApprovedOrder`, lifecycle, V9 journal, closed/test-local release gate, bound fake broker port, reconciliation, exclusivity, eligibility, audit, and Live state machine.

- [ ] **Step 1: Add end-to-end tests** for canonical ApprovedOrder flow under a test-local fake gate, duplicate replay, timeout→`IN_DOUBT`→broker-truth recovery, restart no-auto-arm, foreign activity halt, exclusivity conflict, required-protection failure, audit failure, and Emergency Stop preserving distinct `FLATTEN_ALL` semantics.
- [ ] **Step 2: Add negative authority tests** proving AI/Laya/dashboard/Paper/Backtest cannot reach the coordinator/broker mutation seam directly.
- [ ] **Step 3: Run focused suite** covering Tasks 1–8.
- [ ] **Step 4: Run preservation regressions:** Phase-2 RiskGate authority/hard-limits/intent/kill-switch/mode isolation; Phase-3 live feed; Phase-5 recovery/safety; Phase-6 read-only/transport/protection; S2 device/session/cloud-outage; RiskGate fast-path focused suite.
- [ ] **Step 5: Run full regression:** `python -m pytest tests_v1 -q`. Any failure triggers systematic debugging before code changes.
- [ ] **Step 6: Commit:** `test: lock V1-to-V2 Live reunion invariants`.

---

### Task 9: Exact-Head Dual-Windows Qualification and Evidence

**Files:**
- Create: `.github/workflows/live-v1-v2-reunion-qualification.yml`
- Create: `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md`

**Workflow:** `workflow_dispatch` only; Python 3.13.14; Windows latest + Windows 2022; record exact SHA. Jobs run compile, module boundaries, `check_phase6_live_readonly.py`, `check_live_reunion_boundary.py`, focused reunion tests, Phase-2/3/5/6/S2/RiskGate preservation suites, and full `tests_v1` on the primary Windows leg. If UI was not touched, do not add unnecessary frontend work here.

- [ ] **Step 1: Add workflow/evidence test or static inspection** proving both Windows legs use the same exact checked-out SHA and the compare/evidence stage cannot report GREEN if either leg never executes.
- [ ] **Step 2: Commit qualification workflow** without changing product code.
- [ ] **Step 3: Dispatch against the frozen final Package-1 SHA when hosted runners are available.** A zero-step/no-runner startup failure is `EXECUTION BLOCKED`, neither code RED nor code GREEN.
- [ ] **Step 4: If any executable check fails, use systematic debugging, fix on a new commit, and rerun exact-head qualification. Never rewrite prior evidence/checkpoint commits.
- [ ] **Step 5: Record actual run IDs, job IDs, test counts, artifacts/fingerprints, exact SHA, limitations, and remaining Package-2 gates in the qualification doc.
- [ ] **Step 6: Only after both Windows legs and required regression evidence are clean, create a new final verified Package-1 checkpoint. Live remains `READ_ONLY / DISARMED`.
- [ ] **Step 7: Commit:** `test: qualify V1-to-V2 Live reunion`.

---

## Package-1 Completion Boundary

Package 1 is complete only when the manifest is final, the canonical authority path is structurally enforced, focused + full regression evidence is current-head clean, both Windows qualification legs actually execute successfully, and the final evidence bundle records the exact SHA. Completion of Package 1 does **not** authorize production mutation or a real-money pilot.

## Package-2 Handoff — Separate Future Design/Approval

After Package 1 is verified, Package 2 must be separately designed and approved before any real-money action. It will cover current broker/exchange/regulatory recheck, production network mutation transport, credential custody/static-IP eligibility, permitted sandbox/read-only/controlled broker evidence, release defect gates, protection verification, staged minimum-exposure pilot controls, incident rollback criteria, and explicit Owner arming authorization. Package 2 must not be silently folded into this plan.

## Rollback and Commit Discipline

- One task = one independently reviewable commit (documentation updates may ride with the task they document).
- If a task fails its focused/static checks, revert only that task; do not weaken a guard to make it pass.
- Never force-move historical checkpoint `4713b4df...`.
- Never use stale historical PASS evidence as current-head proof.
- Never merge to `main`, open Live mutation, or create a production enable switch merely because local tests pass.
