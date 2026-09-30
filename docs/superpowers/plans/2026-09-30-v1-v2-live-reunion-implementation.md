# AlgoFortis V1 → V2 Live Reunion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permanently reunite proven V1 Live/recovery behavior with the current V2 safety spine through one canonical, testable Live path while keeping real broker mutation unreachable and Live `READ_ONLY / DISARMED` throughout Package 1.

**Architecture:** Reuse the existing V2 `ApprovedOrder`, deterministic `client_order_id`, `OrderExecutionLifecycle`/`OrderExecutionState`, `LiveStateMachine`, `BoundBrokerPort`, Phase-6 read-only coordinator/reconciler, and Angel One V2 protection/read-side components. Add only the missing focused pieces: a permanent donor manifest and boundary guard, an additive V9 Live execution/exclusivity evidence schema, a dormant `LiveExecutionCoordinatorV2` behind a production-closed release gate, an account-local exclusivity backstop, Live eligibility composition, and an Angel One mutation **translation seam** whose broker mutation methods remain unavailable in Package 1.

**Tech Stack:** Python 3.13.14, dataclasses/enums/protocols, SQLite additive migrations, pytest, existing AlgoFortis audit/reconciliation/risk/broker contracts, GitHub Actions dual-Windows qualification; dashboard TypeScript/Vitest only if a later reviewed slice explicitly requires UI evidence.

**Spec:** `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design.md` plus approval amendment `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design-approval.md`

## Global Constraints

- Live remains `READ_ONLY / DISARMED` through this entire implementation plan.
- `RiskGateV2` remains the sole executable-order approval authority; no new mint path for `ApprovedOrder`.
- Never move or rewrite historical checkpoint `4713b4dfb1d250ac01cf23dc73e89ddeac7716de`.
- Existing `engine/orders/lifecycle_v2.py` is the sole order-lifecycle state machine; extend it only where broker-truth convergence requires new terminal truth values.
- Existing deterministic `client_order_id` from `engine/orders/contracts_v2.py` is authoritative; do not create a second identity scheme.
- Existing `engine/live/phase6_readonly_coordinator.py` + `LiveBrokerReconciler` remain the foreign-activity/recovery authorities; do not create parallel engines.
- Existing Phase-6 transport runtime remains the sole reconnect/generation authority.
- Existing `BoundBrokerPort` hard Live-mutation block stays unchanged in Package 1; do not add an enable flag or bypass.
- Do not weaken or delete `build/tools/check_phase6_live_readonly.py` during Package 1.
- Do not promote legacy `engine/broker_adapters/angel_adapter.py`; it is reference-only.
- Paper/Backtest cannot bind real-broker mutation adapters or credentials.
- AI/Laya/dashboard/alerts/reporting/persistence cannot call broker mutation directly.
- Restart/reconnect/recovery/clean reconciliation never auto-arm Live.
- Missing/corrupt journal, broker truth, protection evidence, exclusivity evidence, audit, or policy fails closed.
- No real broker credentials, real orders, or real-money mutation are required or authorized by this plan.
- No new production numeric thresholds are invented to make tests pass.

## Review Focus

1. **Duplicate submission after timeout/restart:** one canonical `client_order_id` remains one submission identity; `IN_DOUBT` is reconciled, never blindly retried. Tests: Tasks 2–4.
2. **Persistence mistaken for broker truth:** journal recovery reconstructs local evidence only; broker truth comes from `LiveBrokerReconciler`. Tests: Task 4.
3. **Second local device/process owner:** conflicting or indeterminate Live ownership fails closed without cloud becoming trading authority. Tests: Task 5.
4. **Protection disappears or capability changes:** required broker-resident protection missing/unsupported blocks eligibility and keeps Live DISARMED. Tests: Task 6.
5. **Dormant write seam accidentally becomes reachable:** Package 1 has only a closed production release gate, existing `BoundBrokerPort` Live hard-block remains, and Angel mutation methods remain unavailable. Tests/guards: Tasks 1, 3, 7, 8.

---

## File Structure Locked by This Plan

**Create**
- `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md` — permanent donor classification/source map.
- `build/tools/check_live_reunion_boundary.py` — permanent alternate-authority/import/reachability guard.
- `engine/persistence/live_execution_schema_v9.py` — additive V9 SQL for execution journal + local ownership evidence.
- `engine/persistence/live_execution_store_v2.py` — focused durable Live execution evidence journal.
- `engine/persistence/live_account_exclusivity_store_v2.py` — focused durable local ownership evidence store.
- `engine/live/mutation_release_gate_v2.py` — production-closed release-gate protocol/implementation.
- `engine/live/execution_coordinator_v2.py` — single orchestration seam after RiskGate approval; production composition remains blocked.
- `engine/live/account_exclusivity_v2.py` — local broker-account Live ownership backstop.
- `engine/live/live_eligibility_v2.py` — composition of state/S2/exclusivity/protection/recovery prerequisites.
- `engine/broker_adapters/angelone_v2/mutation_seam_v2.py` — canonical request translation/capability seam; `place/cancel` unavailable in Package 1.
- focused tests named below.
- `.github/workflows/live-v1-v2-reunion-qualification.yml` — exact-head manual qualification.
- `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md` — final evidence record.

**Modify narrowly**
- `engine/persistence/schema.py` — V8 → V9 facade composition only.
- `engine/persistence/migrations.py` — add `LIVE_EXECUTION_V9_MIGRATION` only.
- `engine/orders/lifecycle_v2.py` — add only broker-truth values/transitions required to converge `IN_DOUBT` to observed broker truth.
- `engine/reconciliation/live_reconciler.py` — bridge unresolved journal entries to existing broker-truth reconciliation.
- `engine/live/phase6_readonly_coordinator.py` — expose/use existing foreign-activity result in reunion recovery flow only if needed.
- `engine/broker_adapters/angelone_v2/protection_capability.py` and/or `order_policy.py` only if current models cannot express Task-6 eligibility.

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
- Manifest statuses exactly: `SALVAGED`, `REFERENCE_ONLY`, `REPLACED_BY_V2`, `DEFERRED`.
- Guard exit `0` marker: `LIVE_REUNION_BOUNDARY_PASS`.

- [ ] **Step 1 — RED:** write tests that reject direct broker-mutation imports from strategy/AI/dashboard/alerts/reporting/persistence/Paper, direct `_mint_approved_order`, production reachability of `angel_adapter.py`, a second reconnect/generation authority, auto-arm tokens outside the canonical Live state boundary, and any Package-1 production mutation-gate implementation other than `ClosedLiveMutationReleaseGate`.
- [ ] **Step 2 — Verify RED:** `python -m pytest tests_v1/test_v2_live_reunion_boundary.py -q`; expected FAIL because guard/manifest do not exist.
- [ ] **Step 3 — Implement manifest:** map every known V1 donor behavior to one canonical V2 owner and record evidence/classification/migration/test/safety/commit columns.
- [ ] **Step 4 — Implement guard:** deterministic repo-relative scan with explicit canonical allowlist; keep `check_phase6_live_readonly.py` unchanged.
- [ ] **Step 5 — GREEN:** run focused test, `python build/tools/check_live_reunion_boundary.py`, and `python build/tools/check_phase6_live_readonly.py`; all PASS.
- [ ] **Step 6 — Commit:** `docs: lock V1-to-V2 Live reunion manifest`.

---

### Task 2: Add the Additive V9 Live Execution + Ownership Evidence Schema

**Files:**
- Create: `engine/persistence/live_execution_schema_v9.py`
- Create: `engine/persistence/live_execution_store_v2.py`
- Modify: `engine/persistence/schema.py`
- Modify: `engine/persistence/migrations.py`
- Create: `tests_v1/test_live_execution_store_v2.py`

**Interfaces:**
- `LiveExecutionRecord` immutable fields: `client_order_id: str`, `approved_order_ref: str`, `run_mode: RunMode`, `lifecycle_state: OrderExecutionState`, `broker_order_identity: str | None`, `submission_attempt_id: str`, `created_at_utc: datetime`, `updated_at_utc: datetime`, `is_uncertain: bool`, `adapter_id: str | None`, `policy_ref: str | None`, `audit_ref: str | None`.
- `LiveExecutionStoreV2.reserve(record: LiveExecutionRecord) -> LiveExecutionRecord`.
- `LiveExecutionStoreV2.get(client_order_id: str) -> LiveExecutionRecord | None`.
- `LiveExecutionStoreV2.transition(client_order_id: str, *, lifecycle_state: OrderExecutionState, broker_order_identity: str | None = None, is_uncertain: bool | None = None, audit_ref: str | None = None) -> LiveExecutionRecord`.
- `LiveExecutionStoreV2.list_uncertain() -> tuple[LiveExecutionRecord, ...]`.
- V9 also creates a `live_account_exclusivity_v2` table consumed by Task 5; no Task-5 behavior is implemented here.
- `LIVE_EXECUTION_V9_MIGRATION`: exactly version `8 -> 9`.

- [ ] **Step 1 — RED:** tests for V8→V9 migration/rollback, unique `client_order_id`, persistence across reopen, exact `OrderExecutionState` round-trip including `IN_DOUBT`, no secret/token columns, and duplicate/corrupt writes failing closed.
- [ ] **Step 2 — Verify RED:** `python -m pytest tests_v1/test_live_execution_store_v2.py -q`; expected FAIL because V9/store do not exist.
- [ ] **Step 3 — Implement schema:** additive create/drop SQL, unique `client_order_id`, ownership-evidence table; do not edit V7/V8 schema files.
- [ ] **Step 4 — Update facades:** `SCHEMA_VERSION = 9`; compose V7 + V8 + V9 create SQL; export `LIVE_EXECUTION_V9_MIGRATION`.
- [ ] **Step 5 — Implement focused store:** follow `paper_recovery_store_v2.py` style; journal is local evidence, never broker truth.
- [ ] **Step 6 — GREEN:** focused test + migration regressions + existing Phase-5 recovery-store tests.
- [ ] **Step 7 — Commit:** `feat: add V2 Live execution journal`.

---

### Task 3: Add the Production-Closed Release Gate and Dormant `LiveExecutionCoordinatorV2`

**Files:**
- Create: `engine/live/mutation_release_gate_v2.py`
- Create: `engine/live/execution_coordinator_v2.py`
- Create: `tests_v1/test_live_execution_coordinator_v2.py`
- Extend: `tests_v1/test_v2_live_reunion_boundary.py`

**Interfaces:**
- `LiveMutationBlocked(RuntimeError)`.
- `LiveMutationReleaseGate` Protocol: `authorize(*, order: ApprovedOrder, live_state: LiveState) -> str` where success returns non-empty authorization evidence; denial raises `LiveMutationBlocked`.
- `ClosedLiveMutationReleaseGate.authorize(...) -> str` always raises `LiveMutationBlocked("live mutation release gate is closed")`.
- No production open/allow implementation exists in Package 1. Tests may define a local fake gate in the test module only.
- `_LiveBrokerMutationPort` Protocol inside `execution_coordinator_v2.py`: `place(order: ApprovedOrder) -> object`. Production composition is intended to use `BoundBrokerPort`; tests use a local fake port because current `BoundBrokerPort` intentionally hard-blocks all Live mutation.
- `LiveExecutionCoordinatorV2.submit(order: ApprovedOrder, *, now: datetime) -> object`.

**Coordinator sequence:** validate genuine unexpired `ApprovedOrder` with `RunMode.LIVE`; require canonical `LiveState.ACTIVE`; call release-gate authorization; reserve unique journal record; create `OrderExecutionLifecycle` at `RISK_APPROVED`; transition/persist `SUBMITTING`; transition/persist `SENT_UNACKED` **before** invoking mutation port so a crash at the call boundary fails conservatively; invoke `place`; returned acknowledgement becomes `ACKED` + broker mapping; any exception after call boundary becomes `IN_DOUBT`; no automatic resubmit.

- [ ] **Step 1 — RED:** wrong mode/type, expired approval, duplicate `client_order_id`, non-ACTIVE state, closed-gate call count zero, test-local fake-gate/fake-port success, acknowledgement mapping once, mutation exception → `IN_DOUBT`, second submit of `IN_DOUBT` rejected without port call, and audit failure blocks the mutation boundary.
- [ ] **Step 2 — Verify RED:** `python -m pytest tests_v1/test_live_execution_coordinator_v2.py -q`.
- [ ] **Step 3 — Implement closed gate:** no env/config/CLI switch that opens it.
- [ ] **Step 4 — Implement coordinator:** reuse `OrderExecutionLifecycle`, deterministic `client_order_id`, `LiveExecutionStoreV2`; never mint approval and never own reconciliation.
- [ ] **Step 5 — Extend guard:** production direct-port bypass, production open release-gate implementation, or direct broker adapter call outside canonical seam is RED.
- [ ] **Step 6 — GREEN:** coordinator tests + Phase-2 RiskGate authority/mode isolation + both static guards.
- [ ] **Step 7 — Commit:** `feat: add dormant V2 Live execution coordinator`.

---

### Task 4: Extend the Existing Lifecycle for Broker Truth and Reconcile `IN_DOUBT`

**Files:**
- Modify: `engine/orders/lifecycle_v2.py`
- Modify: `engine/reconciliation/live_reconciler.py`
- Modify only if needed: `engine/live/phase6_readonly_coordinator.py`
- Create: `tests_v1/test_live_reunion_reconciliation_v2.py`

**Interfaces:**
- Extend `BrokerTruth` with `PARTIALLY_FILLED`, `FILLED`, `CANCELLED` in addition to existing `ACKED`, `REJECTED`, `NOT_FOUND`.
- Extend `OrderExecutionLifecycle.resolve_in_doubt(...)` so `IN_DOUBT` can converge directly to those observed broker states; broker order identity is required when broker truth proves an order exists.
- Preserve `retry_not_found(reapproved_order: ApprovedOrder)` rule: same `client_order_id`, fresh RiskGate decision ref, unexpired TTL; reconciliation itself never retries.
- Add `LiveBrokerReconciler.reconcile_uncertain_orders(records: Sequence[LiveExecutionRecord], *, fail_closed: bool = True) -> tuple[OrderReconciliationItem, ...]`.

- [ ] **Step 1 — RED lifecycle tests:** `IN_DOUBT` can resolve from explicit broker truth to ACKED/PARTIALLY_FILLED/FILLED/CANCELLED/REJECTED/NOT_FOUND; no assumed state; `NOT_FOUND` retry still requires fresh approval.
- [ ] **Step 2 — RED reconciliation tests:** broker query failure remains fail-closed; partial/full fill and cancellation converge; restart with open position enters recovery before entries; reconciliation makes zero place/submit calls.
- [ ] **Step 3 — RED foreign-activity regression:** broker-only order/position still causes halt + critical alert/audit; no auto-adopt and no implicit `FLATTEN_ALL`.
- [ ] **Step 4 — Verify RED:** `python -m pytest tests_v1/test_live_reunion_reconciliation_v2.py tests_v1/test_v2_phase2_order_lifecycle.py -q` (use the existing lifecycle test filename if different after repository inspection; do not invent a duplicate test module).
- [ ] **Step 5 — Implement minimal lifecycle/reconciler extension:** reuse existing item types and Phase-6 incident/alert path; persistence remains non-authoritative.
- [ ] **Step 6 — GREEN:** new tests + existing lifecycle tests + `tests_v1/test_area14_live_reconciliation_restart.py` + Phase-5 recovery regressions.
- [ ] **Step 7 — Commit:** `feat: reconcile uncertain Live orders through broker truth`.

---

### Task 5: Add the Local Broker-Account Live Exclusivity Backstop

**Files:**
- Create: `engine/persistence/live_account_exclusivity_store_v2.py`
- Create: `engine/live/account_exclusivity_v2.py`
- Create: `tests_v1/test_live_account_exclusivity_v2.py`

**Interfaces:**
- `LiveAccountOwner` immutable record: `broker_id`, `broker_account_ref`, `device_id`, `session_family_id`, `ownership_nonce`, `acquired_at_utc`.
- `LiveAccountExclusivityStoreV2.load(broker_id: str, broker_account_ref: str) -> LiveAccountOwner | None`.
- `LiveAccountExclusivityStoreV2.save(owner: LiveAccountOwner) -> None`; conflicting durable owner fails.
- `LiveAccountExclusivityStoreV2.clear(broker_id: str, broker_account_ref: str, ownership_nonce: str) -> None`.
- `LiveAccountExclusivityV2.acquire(candidate: LiveAccountOwner) -> LiveAccountOwner`.
- `LiveAccountExclusivityV2.verify(candidate: LiveAccountOwner) -> bool`.
- `LiveAccountExclusivityV2.release(candidate: LiveAccountOwner) -> None`.
- `LiveAccountExclusivityV2.restore_after_restart(...)` clears active/armed ownership and returns an unowned state requiring explicit reacquisition; durable stale evidence is retained/audited as needed but never re-arms.

- [ ] **Step 1 — RED store/service tests:** same owner verification, second-device conflict, session mismatch, corrupt/unknown evidence, restart does not restore armed owner, cloud unavailable does not weaken local safety, foreign activity causes halt rather than takeover, and cross-user/S2 evidence cannot be substituted.
- [ ] **Step 2 — Verify RED:** `python -m pytest tests_v1/test_live_account_exclusivity_v2.py -q`.
- [ ] **Step 3 — Implement focused V9-backed store + service:** no hostname/MAC/IP trust; no cloud lease authority.
- [ ] **Step 4 — GREEN:** focused tests plus `tests_v1/test_s2_device_session_gate.py`, `tests_v1/test_s2_cloud_outage.py`, `tests_v1/test_s2_device_service.py`.
- [ ] **Step 5 — Commit:** `feat: add local Live account exclusivity backstop`.

---

### Task 6: Compose Live Eligibility with Broker-Resident Protection

**Files:**
- Create: `engine/live/live_eligibility_v2.py`
- Reuse/modify narrowly if required: `engine/broker_adapters/angelone_v2/protection_capability.py`
- Reuse/modify narrowly if required: `engine/broker_adapters/angelone_v2/order_policy.py`
- Create: `tests_v1/test_live_eligibility_v2.py`
- Extend: `tests_v1/test_phase6_protection_capability.py`

**Interfaces:**
- `LiveEligibilityStatus`: exactly `ELIGIBLE_FOR_QUALIFICATION`, `BLOCKED`; neither means armed/production-authorized.
- `LiveEligibilityResult`: immutable `status`, `reasons`, `evidence_refs`.
- `LiveEligibilityV2.evaluate(*, live_state: LiveState, s2_gate_result: object, exclusivity_ok: bool, reconciliation_clean: bool, protection_capability: object, broker_policy_ref: str | None, audit_ready: bool) -> LiveEligibilityResult`.

- [ ] **Step 1 — RED:** missing/unsupported required broker protection, missing policy evidence, dirty reconciliation, invalid S2, exclusivity conflict, non-ready safety state, or audit unavailable => `BLOCKED`; all software prerequisites => only `ELIGIBLE_FOR_QUALIFICATION`, never ACTIVE/armed.
- [ ] **Step 2 — Verify RED:** focused eligibility + protection tests.
- [ ] **Step 3 — Implement pure composition:** reuse existing protection capability/policy models; invent no degraded policy.
- [ ] **Step 4 — GREEN:** eligibility tests + `test_phase6_protection_capability.py` + Phase-6 policy/state-machine + S2 gate regressions.
- [ ] **Step 5 — Commit:** `feat: enforce Live protection eligibility`.

---

### Task 7: Add the Angel One V2 Mutation Translation Seam — Mutation Still Unavailable

**Files:**
- Create: `engine/broker_adapters/angelone_v2/mutation_seam_v2.py`
- Create: `tests_v1/test_angelone_v2_mutation_seam.py`
- Extend: `build/tools/check_live_reunion_boundary.py`

**Interfaces:**
- `AngelOneMutationRequestV2` immutable canonical translated request containing only non-secret order fields and versioned policy references required for a later transport.
- `AngelOneV2MutationUnavailable(RuntimeError)`.
- `AngelOneV2MutationSeam` exposes a `BrokerPortDescriptor` with `RunMode.LIVE`, `BrokerMutationKind.REAL_BROKER`, `BrokerCredentialScope.REAL_BROKER` and `build_place_request(order: ApprovedOrder) -> AngelOneMutationRequestV2`.
- To satisfy/prepare the `BrokerPortAdapterV2` shape, `place(...)` and `cancel(...)` exist but **always raise** `AngelOneV2MutationUnavailable` in Package 1. There is no network client, HTTP call, credential loader, or injected real/test transport in this module.
- Read-side methods delegate only to already-approved read-only components where composition requires them.

- [ ] **Step 1 — RED:** descriptor correctness, canonical ApprovedOrder translation, no legacy adapter import, no HTTP/network dependency, no credential material in request/repr/logs, required protection/policy references, and `place/cancel` always unavailable.
- [ ] **Step 2 — Verify RED:** `python -m pytest tests_v1/test_angelone_v2_mutation_seam.py -q`.
- [ ] **Step 3 — Implement translation seam:** no production or test network mutation path.
- [ ] **Step 4 — Extend guard:** any Package-1 default network mutation/client/credential composition in `angelone_v2` makes qualification RED.
- [ ] **Step 5 — GREEN:** seam tests + Phase-6 Angel/read-only/protection tests + both static guards.
- [ ] **Step 6 — Commit:** `feat: add disarmed Angel One V2 mutation seam`.

---

### Task 8: End-to-End Reunion Invariants and Regression Preservation

**Files:**
- Create: `tests_v1/test_v2_live_reunion_end_to_end.py`
- Update: `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md` implementation-commit/test columns.

**Interfaces:**
- Test-only harness composes a RiskGate-produced Live `ApprovedOrder`, `OrderExecutionLifecycle`, V9 journal, test-local release-gate protocol implementation, test-local fake mutation port, reconciliation, exclusivity, eligibility, audit, and `LiveStateMachine`.
- Production code remains closed because no production release-gate implementation exists, current `BoundBrokerPort` still blocks Live mutation, and Angel One `place/cancel` remain unavailable.

- [ ] **Step 1 — Add end-to-end tests:** canonical ApprovedOrder test path, duplicate replay, pre-call persisted `SENT_UNACKED`, timeout→`IN_DOUBT`→broker-truth recovery, fresh approval after NOT_FOUND only, restart no-auto-arm, foreign activity halt, exclusivity conflict, required-protection failure, audit failure, and Emergency Stop preserving distinct `FLATTEN_ALL` semantics.
- [ ] **Step 2 — Add negative authority tests:** AI/Laya/dashboard/Paper/Backtest cannot reach coordinator/broker mutation directly.
- [ ] **Step 3 — Run focused Task-1…8 suite.**
- [ ] **Step 4 — Run preservation regressions:** Phase-2 RiskGate authority/hard-limits/intent/kill-switch/mode isolation/order lifecycle; Phase-3 live feed; Phase-5 recovery/safety; Phase-6 read-only/transport/protection; S2 device/session/cloud-outage; RiskGate fast-path focused suite.
- [ ] **Step 5 — Run full regression:** `python -m pytest tests_v1 -q`. Any failure triggers systematic debugging before code changes.
- [ ] **Step 6 — Commit:** `test: lock V1-to-V2 Live reunion invariants`.

---

### Task 9: Exact-Head Dual-Windows Qualification and Evidence

**Files:**
- Create: `.github/workflows/live-v1-v2-reunion-qualification.yml`
- Create: `docs/qualification/LIVE_V1_V2_REUNION_2026-09-30.md`

**Workflow:** `workflow_dispatch` only; Python 3.13.14; Windows latest + Windows 2022; exact SHA recorded. Both legs run compile, module-boundary checks, `check_phase6_live_readonly.py`, `check_live_reunion_boundary.py`, focused reunion tests, and preservation suites. Primary Windows leg also runs full `tests_v1`. If UI is untouched, do not add frontend work.

- [ ] **Step 1 — Static workflow test/inspection:** both Windows jobs checkout the same requested exact SHA; evidence/compare cannot claim GREEN if either job never executes.
- [ ] **Step 2 — Commit workflow/evidence skeleton** without product-code changes.
- [ ] **Step 3 — Dispatch against the frozen final Package-1 SHA when hosted runners are available.** Zero-step/no-runner startup failure = `EXECUTION BLOCKED`, neither code RED nor code GREEN.
- [ ] **Step 4 — Executable failure rule:** use systematic debugging, fix on a new commit, rerun exact-head qualification; never rewrite prior checkpoint/evidence commits.
- [ ] **Step 5 — Record evidence:** run/job IDs, exact SHA, test counts, artifacts/fingerprints, limitations, and remaining Package-2 gates.
- [ ] **Step 6 — Final verified checkpoint:** create only after both Windows legs and required regression evidence execute cleanly. Live remains `READ_ONLY / DISARMED`.
- [ ] **Step 7 — Commit:** `test: qualify V1-to-V2 Live reunion`.

---

## Package-1 Completion Boundary

Package 1 is complete only when the permanent manifest is final, one canonical authority path is structurally enforced, focused + full regression evidence is current-head clean, both Windows qualification legs actually execute successfully, and final evidence records the exact SHA. Package-1 completion does **not** authorize production mutation or a real-money pilot.

## Package-2 Handoff — Separate Future Design/Approval

Package 2 must be separately brainstormed/designed/approved after Package 1 verification. It covers: current broker/exchange/regulatory recheck; production network mutation transport; credential custody/static-IP eligibility; permitted sandbox/read-only/controlled broker evidence; any reviewed change required to the current `BoundBrokerPort` Live hard-block; release defect gates; broker-resident protection verification; staged minimum-exposure pilot controls; incident rollback criteria; and explicit Owner arming authorization. Package 2 must not be silently folded into this plan.

## Rollback and Commit Discipline

- One task = one independently reviewable commit; task-local docs may ride with that task.
- If focused/static checks fail, revert/fix the task; never weaken a guard to make it pass.
- Never force-move historical checkpoint `4713b4df...`.
- Never use stale historical PASS evidence as current-head proof.
- Never merge to `main`, open Live mutation, modify `BoundBrokerPort` to permit Live, or create a production enable switch merely because local tests pass.
