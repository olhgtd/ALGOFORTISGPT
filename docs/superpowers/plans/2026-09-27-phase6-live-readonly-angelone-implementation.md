# Phase 6 Isolated Angel One Live V2 Read-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and qualify an isolated Angel One Live V2 read-only broker boundary that supplies real broker truth to the existing Live reconciler while keeping real-broker mutation structurally unreachable and Live `READ_ONLY / DISARMED`.

**Architecture:** Add a focused `engine/broker_adapters/angelone_v2/` observation-only package rather than patching the legacy mutation-capable Angel adapter. Broker truth flows into the existing `engine/reconciliation/live_reconciler.py`, whose verdict feeds a Phase-6 read-only coordinator that reuses the Phase-5 `FailureIncident` and alert dispatcher. A source-level static guard makes mutation-unreachability structural rather than flag-based.

**Tech Stack:** Python 3.13, dataclasses/enums/protocols, existing broker normalization/contracts, existing `LiveBrokerReconciler`, Phase-5 incident/alert contracts, pytest, GitHub Actions dual-Windows deterministic qualification.

**Spec:** `docs/superpowers/specs/2026-09-27-phase6-live-readonly-angelone-design.md`

## Global Constraints

- Live remains `READ_ONLY / DISARMED` for the complete G6 implementation and qualification.
- **G6 GREEN does not mean real-money trading is enabled.**
- Do not modify or promote `engine/broker_adapters/angel_adapter.py` into the Phase-6 authority path.
- The V2 adapter supplies broker truth only; `engine/reconciliation/live_reconciler.py` owns reconciliation verdicts.
- Reuse Phase-5 `FailureIncident`, `FailureSeverity`, `AlertEnvelope`, and `AlertDispatcher`; do not create a second incident/alert framework.
- No Phase-6 production module may expose or reach real `place` / `submit` / `modify` / `cancel` / GTT mutation calls.
- No runtime/env/config flag may bypass the structural mutation firewall.
- RiskGate remains the only future executable-order approval authority; Phase-6 read-only code must not construct or transport `ApprovedOrder` to a real mutation path.
- Restart/reconnect/token refresh/session recovery never auto-arms.
- Foreign broker activity halts new-entry eligibility + alerts; never ignore, auto-adopt, cancel, or modify it.
- Broker-resident protection is capability/evidence-only during G6; G6 must not create/modify protective broker orders.
- Broker/exchange/rate/order-type values are versioned policy/evidence, not guessed production constants.
- Current OD-V2-09 evidence input is `docs/v2/phase6/G6_BROKER_RULE_REVIEW_2026-09-27.md`; re-check authoritative sources before G6 exit.
- Missing/stale/contradictory/unverifiable required evidence fails closed.
- Hosted-runner pre-step provisioning failures are neither code GREEN nor code RED; do not claim G6 qualified without executed test output.

## Review Focus

1. **Broad legacy protocol accidentally reintroduces mutation:** read-only compatibility code must not inherit/implement mutation just to satisfy `BrokerAdapter` shape; test the production object has no callable mutation methods.
2. **Broker query failure misclassified as clean state:** unavailable/partial orders, positions, or funds must produce uncertainty/fail-closed evidence rather than an empty broker truth set being treated as matched.
3. **Foreign activity alert storms or silent dedup loss:** repeated identical foreign observations must produce stable/idempotent incident evidence and bounded alert behavior while remaining unresolved.
4. **Session/rate recovery accidentally creates permission:** auth refresh, 429 cooldown expiry, reconnect, or restart must never transition Live to ACTIVE or restore entry eligibility by themselves.
5. **Policy drift hidden in code:** static-IP, order-type, rate, OPS/tagging, or protection values must be injected/versioned and missing/stale policy must fail closed.

---

### Task 0 — Bind the approved design and dated OD-V2-09 evidence

**Files:**
- Verify: `docs/superpowers/specs/2026-09-27-phase6-live-readonly-angelone-design.md`
- Verify: `docs/v2/phase6/G6_BROKER_RULE_REVIEW_2026-09-27.md`
- Verify: `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`
- Verify: `docs/v2/phase6/PHASE6_OWNER_DECISION_FREEZE.md`

**Interfaces:**
- Consumes: Owner-approved Option B and frozen OD-V2-05/06/08/09.
- Produces: immutable design inputs for every later slice.

- [ ] Re-read the four documents and verify they all preserve `READ_ONLY / DISARMED`, no auto-arm, foreign activity halt+alert/manual-only, and dated-current rule review.
- [ ] Verify the spec contains the exact binding sentence that the V2 adapter provides broker truth and `live_reconciler.py` provides the reconciliation verdict.
- [ ] Verify the spec says G6 GREEN does not enable real-money trading.
- [ ] Commit any documentation correction separately before code begins.

### Task 1 — Add read-only contracts and structural Phase-6 mutation firewall

**Files:**
- Create: `engine/broker_adapters/angelone_v2/__init__.py`
- Create: `engine/broker_adapters/angelone_v2/contracts.py`
- Create: `build/tools/check_phase6_live_readonly.py`
- Create: `tests_v1/test_phase6_readonly_contracts.py`
- Create: `tests_v1/test_phase6_architecture_guard.py`

**Interfaces:**
- Produces: `AngelOneBrokerProfile`, `AngelOneCredentialRef`, `AngelOneReadOnlyCapability`, `BrokerRuleEvidenceRef`, `AngelOneReadOnlyHealth`, and a static `verify(root: Path) -> tuple[str, ...]` guard.
- Consumes later: Tasks 2–11 import these types; no mutation contract is defined.

- [ ] Write RED tests proving immutable contracts validate explicit non-empty profile/policy references and expose no arm/trade/mutation authority.
- [ ] Write RED architecture tests using safe and intentionally unsafe synthetic fixture trees. Unsafe fixtures must fail even when they declare `DISARMED=True`.
- [ ] Static guard must reject Phase-6 production imports/references to legacy `AngelOneBrokerAdapter`, `ApprovedOrder`, execution mutation modules, `arm_enabled=True`, and callable broker mutation names (`place`, `submit`, `modify`, `cancel`, GTT mutation variants).
- [ ] Run: `python -m pytest tests_v1/test_phase6_readonly_contracts.py tests_v1/test_phase6_architecture_guard.py -q`; verify expected RED before implementation.
- [ ] Implement the minimum contracts and static checker.
- [ ] Run focused tests + `python build/tools/check_phase6_live_readonly.py`; require GREEN.
- [ ] Commit: `feat: add Phase 6 read-only contracts and mutation firewall`.

### Task 2 — Add versioned broker-rate and broker-rule policy seams

**Files:**
- Create: `engine/broker_adapters/angelone_v2/rate_policy.py`
- Create: `engine/broker_adapters/angelone_v2/compliance_gate.py`
- Create: `tests_v1/test_phase6_rate_policy.py`
- Create: `tests_v1/test_phase6_compliance_gate.py`

**Interfaces:**
- Produces: `BrokerRatePolicy`, `BrokerRateClass`, `BrokerRateDecision`, `BrokerComplianceEvidence`, `BrokerEligibilityStatus`, `BrokerComplianceGate.evaluate(...)`.
- Consumes: explicit versioned policy/evidence only; no production defaults.

- [ ] RED: missing rate policy cannot authorize retry/unbounded traffic.
- [ ] RED: per-class rules are explicit/versioned; TEST_ONLY numeric values are allowed only under a test-only profile.
- [ ] RED: missing/stale/unverified static-IP/rule-review evidence evaluates `NOT_ELIGIBLE`/`UNVERIFIED`.
- [ ] RED: eligibility result has no arm/order field and cannot become Live authority.
- [ ] Implement minimal pure policy/evaluator modules; do not embed current 9 req/s or 10 OPS as source defaults.
- [ ] Run focused GREEN and static guard.
- [ ] Commit: `feat: add versioned Phase 6 broker policy seams`.

### Task 3 — Add explicit Angel One session/auth lifecycle with no fake fallback

**Files:**
- Create: `engine/broker_adapters/angelone_v2/session.py`
- Create: `tests_v1/test_phase6_angelone_session.py`

**Interfaces:**
- Produces: `AngelOneSessionState`, `AngelOneSessionEvidence`, `AngelOneSessionAuthority.authenticate()`, `refresh()`, `invalidate()`, `health()`.
- Consumes: credential reference + broker profile + injected transport + injected clock.

- [ ] RED: missing credentials/transport/profile fail closed; `None` transport never returns mock success.
- [ ] RED: auth/token values are never rendered in repr/evidence/error text.
- [ ] RED: token expiry, daily-boundary invalidation, refresh failure and reconnect uncertainty remain non-arming.
- [ ] RED: session success yields observation/session evidence only.
- [ ] Implement the minimum lifecycle wrapper around injected HTTP transport; no module-level network client.
- [ ] Run focused tests + architecture guard.
- [ ] Commit: `feat: add fail-closed Angel One V2 session authority`.

### Task 4 — Build the isolated Angel One read-only adapter

**Files:**
- Create: `engine/broker_adapters/angelone_v2/read_only_adapter.py`
- Create: `tests_v1/test_phase6_angelone_read_only_adapter.py`
- Reuse: `engine/broker_adapters/contracts.py`
- Reuse: `engine/broker_adapters/normalization.py`

**Interfaces:**
- Produces an observation-only adapter/facade with `capabilities()`, `profile()`, `orders()`, `trades()`, `positions()`, `funds()`, `health()` plus only the narrow compatibility query aliases required by `LiveBrokerReconciler`.
- Consumes: Task-3 session authority and Task-2 rate policy.

- [ ] RED: production object has no callable `place`, `submit`, `modify`, `cancel`, or GTT mutation methods.
- [ ] RED: current endpoint profile is injected; legacy `apiconnect.angelbroking.com` is not silently defaulted.
- [ ] RED: missing/invalid/partial broker responses fail typed-unavailable rather than returning fake success/empty-clean state.
- [ ] RED: normalized orders/positions/funds use existing canonical broker snapshot contracts deterministically.
- [ ] RED: 429/auth/network errors classify through typed read-only failures and rate/session evidence.
- [ ] Implement only read queries needed by reconciliation/qualification.
- [ ] Run focused tests + static guard.
- [ ] Commit: `feat: add isolated Angel One V2 read-only adapter`.

### Task 5 — Add read-only conformance without widening the production adapter

**Files:**
- Create: `engine/broker_contract/read_only_conformance_v2.py`
- Create: `tests_v1/test_phase6_read_only_conformance.py`
- Reuse: `engine/broker_contract/port_v2.py`

**Interfaces:**
- Produces: `assert_read_only_broker_conformance(adapter: object, *, expected_broker: str) -> None`.
- Consumes: Task-4 observation-only surface.

- [ ] RED: adapter missing orders/positions/funds/health fails conformance.
- [ ] RED: any callable mutation method fails conformance.
- [ ] RED: adding mutation merely to satisfy the older broad `BrokerPortAdapterV2` is explicitly rejected.
- [ ] Implement the narrow read-only conformance kit; do not change Phase-2 broad contract to weaken existing tests.
- [ ] Run focused GREEN + existing broker-contract regressions.
- [ ] Commit: `feat: add read-only real-broker conformance kit`.

### Task 6 — Make `LiveBrokerReconciler` consume V2 broker truth and classify foreign activity deterministically

**Files:**
- Modify narrowly: `engine/reconciliation/live_reconciler.py`
- Create: `tests_v1/test_phase6_live_reconciliation.py`

**Interfaces:**
- Consumes: Task-4 read-only adapter compatibility surface.
- Produces: existing `LiveReconciliationReport` plus deterministic foreign/uncertainty classifications; no broker mutation.

- [ ] RED: broker-only order is classified as foreign/orphan broker truth, not silently accepted.
- [ ] RED: broker-only position is classified as foreign broker truth.
- [ ] RED: query failure/partial truth produces explicit errors/uncertainty and `is_clean == False`; an exception must not be converted into an empty clean broker state.
- [ ] RED: same broker/local fixture produces identical verdict independent of adapter implementation detail.
- [ ] RED: reconciler never calls a mutation method even if a malicious fixture offers one.
- [ ] Make the smallest broker-neutral additive change needed; preserve the reconciler as verdict authority.
- [ ] Run Phase-6 reconciliation tests + existing Live reconciler regressions.
- [ ] Commit: `feat: harden Live reconciler for Phase 6 broker truth`.

### Task 7 — Reuse Phase-5 incidents/alerts for foreign activity and uncertainty

**Files:**
- Create: `engine/live/phase6_readonly_coordinator.py`
- Modify only if required for generic reuse: `engine/paper/contracts_v2.py`
- Reuse: `engine/alerts/contracts.py`
- Reuse: `engine/alerts/dispatcher.py`
- Create: `tests_v1/test_phase6_foreign_activity_incidents.py`

**Interfaces:**
- Produces: `Phase6ReadonlyCoordinator.observe_and_reconcile(...) -> Phase6ObservationResult`.
- Consumes: `LiveReconciliationReport`, existing `FailureIncident`, existing `AlertDispatcher`, existing Live state authority via a narrow fail-closed port.

- [ ] RED: foreign order creates shared `FailureIncident` with critical/recovery-required severity, latches halt/new-entry denial, and dispatches through existing dispatcher.
- [ ] RED: foreign position behaves the same.
- [ ] RED: broker-truth uncertainty creates fail-closed incident rather than clean success.
- [ ] RED: repeated identical unresolved observation is idempotent/bounded and does not create uncontrolled duplicate alerts.
- [ ] RED: coordinator never auto-adopts, cancels, modifies, submits, or arms.
- [ ] Implement coordinator using existing incident/alert vocabulary. If a generic extraction of `FailureIncident` is required, preserve backward-compatible Phase-5 imports/tests.
- [ ] Run focused + Phase-5 alert/incident regressions + static guard.
- [ ] Commit: `feat: reuse incident pipeline for Phase 6 foreign activity`.

### Task 8 — Add order-type/rule policy validation with Market fail-closed

**Files:**
- Create: `engine/broker_adapters/angelone_v2/order_policy.py`
- Create: `tests_v1/test_phase6_order_policy.py`

**Interfaces:**
- Produces: `BrokerOrderPolicyEvidence` and `validate_order_shape_for_policy(...) -> BrokerOrderPolicyDecision`.
- Consumes: versioned broker/exchange rule evidence only.

- [ ] RED: current test policy rejects `MARKET` deterministically.
- [ ] RED: validator never silently converts Market to Limit.
- [ ] RED: missing/unknown product/order-type/tagging policy fails closed.
- [ ] RED: production module contains no hard-coded permanent 9 req/s, 10 OPS, or exchange square-off constants.
- [ ] Implement pure policy validation. It is evidence/qualification logic only; no broker mutation exists.
- [ ] Run focused GREEN + static guard.
- [ ] Commit: `feat: add Phase 6 order rule policy validation`.

### Task 9 — Add broker-resident protective-capability observation

**Files:**
- Create: `engine/broker_adapters/angelone_v2/protection_capability.py`
- Create: `tests_v1/test_phase6_protection_capability.py`

**Interfaces:**
- Produces: `ProtectionCapabilityEvidence`, `ProtectionCapabilityStatus`, `evaluate_required_protection(...)`.
- Consumes: frozen strategy/risk protection requirement references + broker capability observations.

- [ ] RED: missing/unknown required capability returns unsupported/unverified and keeps future mutation path DISARMED.
- [ ] RED: capability observation cannot place/modify protective orders.
- [ ] RED: existing broker protection may be observed where available but is not adopted as AlgoFortis-owned without reconciliation evidence.
- [ ] Implement observation/evaluation only.
- [ ] Run focused GREEN + static guard.
- [ ] Commit: `feat: add broker protection capability evidence`.

### Task 10 — Add reconnect/auth/rate-limit chaos tests with zero auto-arm

**Files:**
- Create: `tests_v1/test_phase6_connectivity_chaos.py`
- Modify minimally if needed: `engine/live/phase6_readonly_coordinator.py`
- Reuse: `engine/live/state_machine_v2.py`

**Interfaces:**
- Consumes Tasks 2–7.
- Produces deterministic failure/recovery evidence only.

- [ ] Test network disconnect during observation -> broker truth unavailable + incident/halt evidence.
- [ ] Test reconnect -> observation may resume but Live remains non-ACTIVE and entry eligibility is not automatically restored.
- [ ] Test token expiry/refresh failure -> fail closed.
- [ ] Test repeated 429/rate-limit events -> versioned policy decision; no unbounded retry.
- [ ] Test restart from any prior state -> existing `restore_after_restart` remains RECOVERY/non-arming.
- [ ] Test missing storm/rate policy -> halt/fail closed.
- [ ] Run focused GREEN + existing live-state and Phase-5 storm regressions.
- [ ] Commit: `test: qualify Phase 6 connectivity fail-closed behavior`.

### Task 11 — Add deterministic G6 evidence and CI qualification guard

**Files:**
- Create: `engine/live/phase6_evidence.py`
- Create: `build/tools/phase6_probe.py`
- Create: `tests_v1/test_phase6_evidence.py`
- Create: `tests_v1/test_phase6_qualification_guard.py`
- Modify: `.github/workflows/v2-phase0-baseline.yml`
- Modify: `build/tools/check_phase6_live_readonly.py`

**Interfaces:**
- Produces deterministic G6 evidence markers/fingerprint and dual-Windows comparison job.

- [ ] RED: evidence requires all spec markers including `BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY`, `RECONCILIATION_AUTHORITY=LIVE_RECONCILER`, `FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED`, `LIVE_STATE=READ_ONLY/DISARMED`, and `REAL_BROKER_MUTATION_CAPABILITY=ABSENT`.
- [ ] RED: qualification guard fails if focused tests, static guard, probe, or comparison job disappear.
- [ ] Implement side-effect-free evidence generation; never include tokens/account identifiers/secrets.
- [ ] Wire both Windows legs to run Phase-6 static/focused tests and emit `g6.txt`; comparison requires byte-identical output and valid fingerprint.
- [ ] Preserve G4/G5/GP-S2 checks required by the current stacked dependency chain.
- [ ] Run local/focused checks where executable; do not claim Windows qualification until actual Windows jobs execute.
- [ ] Commit: `ci: add G6 read-only qualification evidence`.

### Task 12 — Real-account read-only qualification evidence

**Files:**
- Create: `docs/v2/phase6/G6_EVIDENCE.md`
- Create: `docs/v2/phase6/G6_READ_ONLY_SESSION_TEMPLATE.md`
- Update after actual runs: `docs/v2/phase6/G6_BROKER_RULE_REVIEW_<DATE>.md`

**Interfaces:**
- Consumes: actual read-only Angel One session evidence plus Tasks 1–11.
- Produces: auditable G6 evidence; never secrets.

- [ ] Re-check current Angel One, NSE, and SEBI authoritative sources immediately before evidence run; record dated identifiers and changes.
- [ ] Use credentials through the approved secret boundary; never commit credentials/tokens/account identifiers.
- [ ] Establish observation-only session and capture redacted health/config-policy refs.
- [ ] Observe orders/positions/funds across the required qualification sessions; the exact `N` must come from a frozen qualification policy, not be invented in code.
- [ ] Exercise disconnect/reconnect/token-expiry/rate-limit test cases without order mutation.
- [ ] Prove foreign-activity fixture/controlled evidence feeds `LiveBrokerReconciler` -> shared incident/alert path.
- [ ] Prove static guard and read-only conformance show zero mutation capability.
- [ ] Run full regression/golden + Phase-6 focused/static + dual-Windows G6 compare.
- [ ] Archive exact head SHA, workflow/run IDs, artifact fingerprints, review date, and all unresolved limitations.
- [ ] Keep G6 `NOT QUALIFIED` if runner jobs do not execute or required real-Windows/read-only evidence is absent.
- [ ] Record explicitly: **G6 GREEN does not enable real-money trading. Live remains READ_ONLY / DISARMED.**

## Self-review result

- Spec coverage: every approved Option-B element is owned by Tasks 1–12.
- Reconciliation ownership: Task 6 explicitly reuses `LiveBrokerReconciler`; no third reconciler.
- Incident ownership: Task 7 explicitly reuses Phase-5 `FailureIncident` + alert dispatcher.
- Structural mutation firewall: Tasks 1 and 11 require static negative-fixture proof, independent of runtime flags.
- Policy drift: Tasks 2, 8, 9, 12 keep external values versioned/evidence-driven.
- G6 semantics: Tasks 10–12 prove reconnect/recovery never auto-arms and G6 does not authorize trading.
- Current CI limitation: plan forbids completion claims when hosted runners fail before executing steps.
