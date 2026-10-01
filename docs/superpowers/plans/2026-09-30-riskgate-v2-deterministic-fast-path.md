# RiskGateV2 Deterministic Fast Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an evidence-calibrated, deterministic low-latency RiskGateV2 path for Paper/Shadow that keeps RiskGateV2 as the sole ApprovedOrder authority, preserves INV-16 audit-before-approval semantics, and reuses existing Phase-5 operational failure/alert machinery.

**Architecture:** Keep `engine/risk/gate_v2.py` as the only approval/mint authority. Add versioned latency-policy and immutable risk-snapshot contracts, publish snapshots off the hot path, implement a `RiskEvaluator`-compatible deterministic fast evaluator, and add bounded timing/evidence hooks around the existing RiskGateV2 approval path. Snapshot-builder failures feed the existing Phase-5 `PaperOperationalStateMachine`, `FailureIncident`, `PaperIncidentStore`, and `AlertDispatcher`; no parallel safety authority is introduced.

**Tech Stack:** Python 3.13, frozen dataclasses/Enums/Protocols, `Decimal`, monotonic `time.perf_counter_ns`, existing AlgoFortis V2 RiskGate/Order/Paper/Phase-5 contracts, pytest, GitHub Actions Windows qualification.

**Spec:** `docs/superpowers/specs/2026-09-30-riskgate-v2-deterministic-fast-path-design.md`

## Global Constraints

- Live remains `READ_ONLY / DISARMED`; this plan creates no real-broker mutation path and no Live arming path.
- `RiskGateV2` remains the sole authority that can mint `ApprovedOrder`.
- INV-16 is absolute: required audit-write failure blocks the candidate and no `ApprovedOrder` is minted, even if the latency SLO is missed.
- Production latency values are supplied only through versioned `RiskGateLatencyPolicy`; no discussed example duration becomes a production constant in source.
- Snapshot stale/missing/mismatched/unhealthy means deterministic BLOCK; there is no slow rebuild/database/LLM/network/backtest fallback inside the candidate hot path.
- Snapshot-builder failures reuse existing Phase-5 `HEALTHY / DEGRADED / HALTED / RECOVERY / READY_FOR_RESUME`, `FailureIncident`, incident persistence, and alert dispatcher/ports.
- Options entries remain BUY-only at RiskGate.
- Laya/AI remain advisory/research/shadow; neither can mint `ApprovedOrder` or call a broker.
- Price/TTL/slippage/freshness limits are versioned policy/evidence, never guessed production constants.
- Initial implementation/benchmark scope is Paper/Shadow + mock/warm transport only.
- Current execution constraint remains: author tests/workflows now if implementing before quota reset, but do not claim GREEN or trigger CI/build/test execution until the user explicitly says test capacity is available.

## Review Focus

- Snapshot publication races with candidate evaluation: reader must see either the complete old snapshot or complete new snapshot, never partial/mixed state; Task 2 pins this.
- Builder crash/staleness after a previously healthy snapshot: new candidates must block and existing Phase-5 incident/state/alert path must fire; Task 4 pins this.
- Audit append stalls/fails after all risk checks pass: no `ApprovedOrder` or transport handoff may occur; Task 6 pins this.
- Quote/market sequence advances between candidate creation and evaluation: bounded price/sequence evidence must reject stale or out-of-zone candidate rather than chase; Task 5 pins this.
- Latency-policy mismatch/missing policy or benchmark evidence from a different runtime/hardware profile: qualification must fail closed rather than silently adopt numbers; Tasks 1 and 8 pin this.

---

### Task 1: Versioned `RiskGateLatencyPolicy`

**Files:**
- Create: `engine/risk/latency_policy_v2.py`
- Test: `tests_v1/test_riskgate_latency_policy_v2.py`

**Interfaces:**
- Produces `LatencyPolicyStatus(str, Enum)` with `TEST_ONLY`, `CALIBRATION`, `APPROVED`.
- Produces `LatencyStagePolicy(stage_name: str, percentile_target: str, ceiling_ns: int, breach_action: str)`.
- Produces `RiskGateLatencyPolicy(policy_id: str, version: str, status: LatencyPolicyStatus, environment_scope: str, hardware_profile_ref: str, runtime_profile_ref: str, sample_minimum_ref: str, stages: tuple[LatencyStagePolicy, ...], evidence_bundle_ref: str | None, approval_ref: str | None)`.
- Produces `RiskGateLatencyPolicy.reference -> str` and `RiskGateLatencyPolicy.stage(name: str) -> LatencyStagePolicy`.
- No default production `ceiling_ns` values exist anywhere in the module.

- [ ] **Step 1: Write policy-validation tests**

Pin: empty IDs rejected; duplicate stage names rejected; non-positive ceilings rejected; `APPROVED` requires `evidence_bundle_ref` and `approval_ref`; `TEST_ONLY` requires `policy_id` prefix `TEST_ONLY/`; no module-level numeric production thresholds.

- [ ] **Step 2: Run the focused test when execution capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_latency_policy_v2.py -q`
Expected: initial RED before implementation; final PASS after Step 3.

- [ ] **Step 3: Implement the immutable policy contracts**

Keep validation pure/std-lib only. Do not import broker, Paper execution, SQLite, AI, or UI code.

- [ ] **Step 4: Re-run focused test when capacity is available**

Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat(risk): add versioned latency policy contract"`

### Task 2: Immutable `RiskSnapshot` and atomic publication boundary

**Files:**
- Create: `engine/risk/snapshot_contracts_v2.py`
- Create: `engine/risk/snapshot_publication_v2.py`
- Test: `tests_v1/test_riskgate_snapshot_contracts_v2.py`
- Test: `tests_v1/test_riskgate_snapshot_publication_v2.py`

**Interfaces:**
- Produces frozen `RiskSnapshot` containing the spec fields: snapshot/schema IDs, generated time, input fingerprint, risk/limits versions, account/strategy/portfolio refs, operational/kill/hold state, allowed scopes, quantity ceilings, risk budget/feed refs, market sequence ref, source versions, and builder-health generation.
- Produces `RiskSnapshotPublication.publish(snapshot: RiskSnapshot) -> None` and `current() -> RiskSnapshot | None`.
- Publication performs complete-object replacement only; no active snapshot field mutation API exists.

- [ ] **Step 1: Write contract tests**

Pin timezone-aware generation time, immutable/frozen behavior, non-empty/versioned references, non-negative market generation/sequence values, and deterministic fingerprint validation.

- [ ] **Step 2: Write publication-concurrency tests**

One publisher alternates two complete snapshots while readers repeatedly call `current()`; every observed object must equal one whole published snapshot identity, never a mixed object.

- [ ] **Step 3: Run focused tests when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_snapshot_contracts_v2.py tests_v1/test_riskgate_snapshot_publication_v2.py -q`

- [ ] **Step 4: Implement contracts/publication**

Use immutable objects and one reference-swap publication seam. Any synchronization must be bounded/read-mostly; do not introduce an unbounded global candidate lock.

- [ ] **Step 5: Re-run focused tests when capacity is available**

Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat(risk): add immutable risk snapshot publication"`

### Task 3: Off-hot-path snapshot builder

**Files:**
- Create: `engine/risk/snapshot_builder_v2.py`
- Test: `tests_v1/test_riskgate_snapshot_builder_v2.py`

**Interfaces:**
- Produces `RiskSnapshotInputs` frozen input bundle.
- Produces `SnapshotInputProvider(Protocol).collect() -> RiskSnapshotInputs`.
- Produces `RiskSnapshotBuilder.build(inputs: RiskSnapshotInputs, *, generated_at: datetime) -> RiskSnapshot`.
- Produces `RiskSnapshotBuilder.refresh(*, generated_at: datetime) -> RiskSnapshot` which collects, builds, validates, then publishes only the completed snapshot.
- Consumes Task 2 `RiskSnapshotPublication`.

- [ ] **Step 1: Write builder tests**

Pin deterministic same-input snapshot identity, input-version changes causing new identity, failed collection/build leaving the previously published snapshot untouched, and unsupported/missing authority refs raising a fail-closed builder error.

- [ ] **Step 2: Run focused test when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_snapshot_builder_v2.py -q`

- [ ] **Step 3: Implement builder**

No broker mutation, LLM, filesystem scan, or candidate-specific price decision belongs in the builder. Build off-path; publish only after full validation.

- [ ] **Step 4: Re-run focused test when capacity is available**

Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat(risk): add off-path risk snapshot builder"`

### Task 4: Snapshot health -> existing Phase-5 incident/state/alert path

**Files:**
- Create: `engine/risk/snapshot_health_v2.py`
- Modify: `engine/paper/operational_state_v2.py` — add explicit snapshot-health transition reasons only; do not add states.
- Test: `tests_v1/test_riskgate_snapshot_health_v2.py`
- Reuse unchanged unless a minimal interface extension is required: `engine/persistence/paper_incident_store_v2.py`, `engine/alerts/dispatcher.py`, `engine/alerts/contracts.py`.

**Interfaces:**
- Produces `SnapshotHealthEvent` with failure class, severity, occurred time, scope, health generation, and safe reason.
- Produces `RiskSnapshotHealthCoordinator.handle(event: SnapshotHealthEvent) -> PaperOperationalState`.
- Constructor consumes existing `PaperOperationalStateMachine`, `PaperIncidentStore`, `AlertDispatcher`, ID generator/clock, session scope, and optional existing `StormEvaluator`.
- Adds `PaperTransitionReason.RISK_SNAPSHOT_BUILDER_UNHEALTHY`, `RISK_SNAPSHOT_STALE`, and `RISK_SNAPSHOT_CONTINUITY_UNCERTAIN` only if each maps to an actual tested transition.

- [ ] **Step 1: Write health-routing tests**

Pin transient builder lag -> `DEGRADED` under supplied versioned policy; stale/unavailable snapshot that prevents new entry -> `HALTED`; continuity uncertainty -> `RECOVERY`; no auto-clear of sticky HALTED; incident stored using existing `FailureIncident`; CRITICAL/RECOVERY_REQUIRED alert uses existing dispatcher.

- [ ] **Step 2: Pin alert failure independence**

One alert adapter may fail without suppressing the other; trading state remains safe regardless of alert delivery result.

- [ ] **Step 3: Run focused test when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_snapshot_health_v2.py -q`

- [ ] **Step 4: Implement coordinator and minimal transition reasons**

Do not create a new operational-state enum, incident DB, alert dispatcher, or retry authority.

- [ ] **Step 5: Re-run focused test when capacity is available**

Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat(risk): route snapshot failures through Phase 5 safety state"`

### Task 5: Deterministic candidate-specific fast evaluator

**Files:**
- Create: `engine/risk/fast_path_v2.py`
- Modify: `engine/risk/gate_v2.py` — additive evidence fields only; preserve sole mint authority.
- Test: `tests_v1/test_riskgate_fast_path_v2.py`
- Regression: existing `tests_v1/test_v2_phase2_risk_gate_authority.py`, `test_v2_phase2_hard_limits.py`, `test_v2_phase2_intent_guard.py`, `test_v2_phase3_live_feed.py`.

**Interfaces:**
- Produces `CurrentQuoteEvidence(instrument_ref, observed_at, market_sequence, bid, ask, source_ref)`.
- Produces `CurrentQuoteProvider(Protocol).current(instrument_ref) -> CurrentQuoteEvidence`.
- Produces `ReplayGuard(Protocol).claim(intent_id: str, snapshot_id: str, market_sequence: int) -> bool` with bounded deterministic semantics.
- Produces `FastPathRiskEvaluator`, implementing existing `RiskEvaluator.evaluate(intent: OrderIntent) -> RiskEvaluation`.
- Extends `RiskEvaluation` additively with optional `risk_snapshot_id`, `market_sequence_ref`, and `latency_policy_ref`; legacy evaluators remain valid.
- Candidate bounded price/slippage evidence is read from the existing immutable `OrderIntent` fields/provenance under a versioned contract; do not let AI-provided provenance override RiskGate policy.

- [ ] **Step 1: Write happy-path fast-evaluator test**

Given current healthy snapshot, matching rules/limits, BUY option intent, valid TTL, claimed replay key, compatible quote sequence and price bound, evaluator returns APPROVED with exact snapshot/sequence refs and requested quantity.

- [ ] **Step 2: Write fail-closed matrix**

Pin: no snapshot, stale snapshot per injected policy, builder generation mismatch, limits/risk version mismatch, operational state not entry-safe, kill/hold active, option SELL, qty ceiling breach, duplicate/replay claim false, quote sequence behind candidate evidence, price outside bounded zone/max-slippage, expired intent -> REJECT/BLOCK with deterministic reason and no slow fallback callback.

- [ ] **Step 3: Run focused tests when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_fast_path_v2.py -q`

- [ ] **Step 4: Implement evaluator and minimal additive `RiskEvaluation` evidence**

Do not call `_mint_approved_order` from `fast_path_v2.py`; only `RiskGateV2` may mint.

- [ ] **Step 5: Re-run focused + Phase-2/3 regressions when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_fast_path_v2.py tests_v1/test_v2_phase2_risk_gate_authority.py tests_v1/test_v2_phase2_hard_limits.py tests_v1/test_v2_phase2_intent_guard.py tests_v1/test_v2_phase3_live_feed.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat(risk): add deterministic snapshot fast evaluator"`

### Task 6: INV-16-safe gate timing and minimal audit evidence

**Files:**
- Create: `engine/risk/latency_evidence_v2.py`
- Modify: `engine/risk/gate_v2.py`
- Test: `tests_v1/test_riskgate_latency_evidence_v2.py`
- Extend: `tests_v1/test_v2_phase2_risk_gate_authority.py`

**Interfaces:**
- Produces `RiskLatencyStage(str, Enum)` for canonical T1..T6 local stages from the spec.
- Produces frozen `RiskGateLatencyRecord` containing intent ID, snapshot/policy refs, monotonic stage timestamps, decision kind, audit result, and optional rejection reason.
- Produces `RiskLatencySink(Protocol).record(record: RiskGateLatencyRecord) -> None`.
- `RiskGateV2.__init__` gains optional injected `monotonic_ns: Callable[[], int]` and optional `latency_sink: RiskLatencySink`; defaults must preserve existing behavior and must not define production SLO numbers.

- [ ] **Step 1: Write stage-order and duration tests**

Injected monotonic clock yields deterministic timestamps; record validates monotonic stage order and derives durations without wall-clock arithmetic.

- [ ] **Step 2: Extend audit-approval tests**

Pin exact sequence: checks/evaluator complete -> mandatory audit append succeeds -> `ApprovedOrder` mint. On audit exception, `RiskApprovalError` is raised, no `ApprovedOrder` exists, and no downstream handoff callback is possible. This explicitly proves INV-16 under fast-path instrumentation.

- [ ] **Step 3: Pin minimal audit payload evidence**

Fast-path approval audit contains intent/client order IDs, decision ref, risk/limits versions, RiskSnapshot ID, market sequence ref, and policy refs; it excludes large human-readable enrichment and secrets.

- [ ] **Step 4: Run focused tests when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_latency_evidence_v2.py tests_v1/test_v2_phase2_risk_gate_authority.py -q`

- [ ] **Step 5: Implement additive timing/evidence hooks**

Latency recording must never authorize an order. If latency evidence sink is optional/non-authorizing and fails, handle according to the spec's telemetry contract without weakening mandatory risk audit; mandatory risk audit failure remains BLOCK.

- [ ] **Step 6: Re-run focused tests when capacity is available**

Expected: PASS.

- [ ] **Step 7: Commit**

`git commit -m "feat(risk): instrument INV-16-safe RiskGate latency evidence"`

### Task 7: Warm Paper/Shadow handoff boundary

**Files:**
- Create: `engine/paper/warm_handoff_v2.py`
- Test: `tests_v1/test_riskgate_warm_paper_handoff_v2.py`
- Reuse: `engine/paper/execution_adapter_v2.py`

**Interfaces:**
- Produces `WarmPaperHandoff.prepare_static(...) -> WarmPaperContext` for non-authorizing static mapping/cache only.
- Produces `WarmPaperHandoff.handoff(approved_order: ApprovedOrder, context: WarmPaperContext, ...) -> SimulatedExecutionResult`.
- Handoff rejects any value that is not a real RiskGate-minted PAPER `ApprovedOrder` and delegates actual simulation to existing `PaperExecutionAdapterV2`.

- [ ] **Step 1: Write authorization-boundary tests**

Pin no pre-RiskGate send/submit side effect, no fabricated ApprovedOrder accepted, LIVE mode rejected, expired capability rejected according to existing policy, and one ApprovedOrder maps to one bounded handoff identity.

- [ ] **Step 2: Run focused test when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_warm_paper_handoff_v2.py -q`

- [ ] **Step 3: Implement warm handoff**

Warm only non-authorizing process/static mapping/serialization state. Do not add a broker SDK or network submission code.

- [ ] **Step 4: Re-run focused test when capacity is available**

Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat(paper): add RiskGate-authorized warm handoff"`

### Task 8: Benchmark/calibration evidence without production hardcodes

**Files:**
- Create: `build/tools/benchmark_riskgate_fast_path.py`
- Create: `engine/risk/latency_benchmark_v2.py`
- Test: `tests_v1/test_riskgate_latency_benchmark_v2.py`

**Interfaces:**
- Produces `LatencyDistribution(sample_count, p50_ns, p95_ns, p99_ns, max_ns)`.
- Produces `RiskGateBenchmarkEvidence(code_sha, policy_ref, hardware_profile_ref, runtime_profile_ref, warm: bool, approved_distribution, rejected_distribution, candidate_to_handoff_distribution, audit_distribution, breach_counts, sample_method_ref)`.
- Benchmark CLI requires an explicit policy fixture/reference; it contains no built-in production threshold.

- [ ] **Step 1: Write percentile/evidence tests**

Pin deterministic percentile calculation, warm/cold evidence separation, policy/runtime/hardware mismatch rejection, and inability to mark evidence as production-approved without an `APPROVED` policy/evidence link.

- [ ] **Step 2: Write benchmark harness dry test**

Use fake monotonic durations and mock Paper transport only; assert emitted JSON/evidence includes code SHA, policy ref, hardware/runtime refs, sample count, distributions and breach counts.

- [ ] **Step 3: Run focused test when capacity is available**

Run: `python -m pytest tests_v1/test_riskgate_latency_benchmark_v2.py -q`

- [ ] **Step 4: Implement calculator + CLI harness**

CLI may accept TEST_ONLY calibration numbers from an explicit fixture/config argument, never source defaults.

- [ ] **Step 5: Re-run focused test when capacity is available**

Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat(risk): add evidence-driven fast-path benchmark harness"`

### Task 9: Permanent architecture guard and manual Windows qualification

**Files:**
- Create: `build/tools/check_riskgate_fast_path_boundary.py`
- Test: `tests_v1/test_riskgate_fast_path_boundary.py`
- Create: `.github/workflows/riskgate-fast-path-qualification.yml`

**Interfaces:**
- Boundary checker scans `engine/risk/*fast_path*`, snapshot/latency modules, and warm handoff code.
- Rejects imports/tokens for real broker adapters, Live mutation/arm paths, AI-owned order minting, `_mint_approved_order` outside `engine/risk/gate_v2.py` / canonical order-contract module, hardcoded production SLO policy construction, and duplicate operational-state/audit/incident/alert authorities.
- Workflow is `workflow_dispatch` only.

- [ ] **Step 1: Write boundary-guard tests**

Pin rejection of broker import, direct order mint, Live arm/mutation token, AI/Laya approval authority, guessed production latency policy literal, and parallel incident/alert subsystem patterns.

- [ ] **Step 2: Implement guard**

Current canonical tree must return no failures.

- [ ] **Step 3: Add manual Windows workflow**

Windows latest: compile new modules; run fast-path boundary guard; existing Live READ_ONLY guard; Phase-2/3 RiskGate tests; Phase-5 operational/alert tests; new focused tests; full `tests_v1` optionally; run benchmark harness with an explicitly checked-in `TEST_ONLY` fixture/reference or workflow input; record exact SHA and upload evidence artifact.

Windows 2022: focused safety cross-check only. Do not include any real broker credentials or mutation call.

- [ ] **Step 4: Execute only when user says test capacity is available**

Expected: all guards/tests green, benchmark produces evidence; benchmark numbers are observations, not automatic production SLO approval.

- [ ] **Step 5: Commit**

`git commit -m "ci: qualify RiskGateV2 deterministic fast path"`

### Task 10: Qualification report and preverification/final checkpoint discipline

**Files:**
- Create: `docs/qualification/RISKGATE_FAST_PATH_2026-09-30.md`

**Interfaces:**
- Report records exact implementation SHA, policy refs/status, test/guard status, benchmark evidence refs, observed distributions, audit-failure evidence, snapshot-failure state/incident/alert evidence, and explicit Live `READ_ONLY / DISARMED` status.

- [ ] **Step 1: Before executable verification, mark status**

`IMPLEMENTED / EXECUTION VERIFICATION PENDING` and create a historical preverification checkpoint branch at the exact source SHA. Never call it GREEN.

- [ ] **Step 2: When capacity is available, run Task 9 qualification on that exact checkpoint**

If failures occur, branch/commit repairs; do not move the historical preverification checkpoint.

- [ ] **Step 3: Re-run until clean and record exact verified SHA**

No performance claim is accepted without matching code SHA, policy ref, runtime/hardware profile and evidence bundle.

- [ ] **Step 4: Create a new final verified checkpoint**

Keep Live `READ_ONLY / DISARMED`; no merge to `main` without separate authorization.

- [ ] **Step 5: Commit report updates**

`git commit -m "docs: record RiskGate fast-path qualification evidence"`

## Final Qualification Commands (when execution capacity is available)

```powershell
python build/tools/check_riskgate_fast_path_boundary.py
python build/tools/check_phase6_live_readonly.py
python -m pytest tests_v1/test_riskgate_latency_policy_v2.py -q
python -m pytest tests_v1/test_riskgate_snapshot_contracts_v2.py tests_v1/test_riskgate_snapshot_publication_v2.py -q
python -m pytest tests_v1/test_riskgate_snapshot_builder_v2.py tests_v1/test_riskgate_snapshot_health_v2.py -q
python -m pytest tests_v1/test_riskgate_fast_path_v2.py tests_v1/test_riskgate_latency_evidence_v2.py -q
python -m pytest tests_v1/test_riskgate_warm_paper_handoff_v2.py tests_v1/test_riskgate_latency_benchmark_v2.py -q
python -m pytest tests_v1/test_v2_phase2_risk_gate_authority.py tests_v1/test_v2_phase2_hard_limits.py tests_v1/test_v2_phase2_intent_guard.py tests_v1/test_v2_phase2_mode_isolation.py tests_v1/test_v2_phase3_live_feed.py -q
python -m pytest tests_v1 -q
```

The benchmark command is intentionally not given a baked-in duration target. It must receive an explicit TEST_ONLY/CALIBRATION policy fixture/reference during qualification.
