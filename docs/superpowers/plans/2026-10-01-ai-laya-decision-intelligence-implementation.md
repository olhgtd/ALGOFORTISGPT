# AI, Laya & Decision Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Owner-approved AlgoFortis AI/Laya decision-intelligence architecture for research, backtest and paper workflows while preserving deterministic Strategy independence and all existing safety authorities.

**Architecture:** Extend the existing Phase-8 AI provider/orchestration/scheduler/queue seams, existing Phase-7 Portfolio reservation/admission stack, S2 DeviceSessionGate authority, and the authoritative Owner/Admin AI Control Center. Do not create parallel risk, accounting, identity, scheduler, or admin authorities. `RiskGateV2` remains the sole ApprovedOrder authority and current Live remains `READ_ONLY / DISARMED`.

**Tech Stack:** Python 3.13, pytest, FastAPI backend, React/TypeScript/Vite/Vitest dashboard, existing AlgoFortis audit/registry/portfolio/risk contracts.

**Spec:** `docs/superpowers/specs/2026-10-01-ai-laya-decision-intelligence-architecture.md`

## Global Constraints

- Deterministic Strategy must remain operational with Laya OFF and with zero AI providers.
- AI/Laya providers are optional `0..N`; provider failure degrades intelligence only.
- Laya/AI may review StrategyCandidates and may generate independent research/backtest/paper `IntelligenceCandidate` objects.
- `RiskGateV2` remains the sole `ApprovedOrder` authority; no second risk/order authority may be introduced.
- Existing `engine/portfolio/` and Phase-7 reservation/admission code remain the source of truth for capital/reservations/exposure.
- Same broker/account capital reservation is atomic; distinct broker/account pools are separate while aggregate exposure remains centrally governed.
- Monitoring scope/cadence comes only from versioned Owner-controlled policy; AI/provider output cannot self-widen or self-reschedule.
- Provider rate limits, queue capacity, TTL, retries and budgets remain controlled by scheduler/provider policy.
- Third-party/cloud data egress, including after-hours Strategy Hunting, must pass OD-V2-16/Data V2 provenance/licensing authorization.
- Intelligence entitlements sit on top of existing S2 identity/device/session authority; no parallel auth system.
- Global configuration is Owner/Admin-only and extends the existing authoritative AI Control Center; user-facing AI/Laya UX remains deferred.
- Current Live remains `READ_ONLY / DISARMED`; this plan does not enable real-money broker mutation or Live arming.

## Review Focus

- Zero-provider/Laya-OFF mode must keep deterministic Strategy and core Paper/Backtest paths healthy.
- Concurrent candidates targeting the same account must never double-reserve capital; separate broker/accounts must not falsely block each other.
- Correlated/same-model council passes must not be counted as independent confirmations.
- Expired/rate-limited AI monitoring tasks must never execute later as fresh market intelligence.
- S2-invalid/unavailable sessions must not acquire AI/Laya entitlements or Owner configuration authority.

---

### Task 1: Synchronize the AI decision freeze and root authority guards

**Files:**
- Modify: `ALGOFORTIS_V2_OWNER_DECISIONS.md`
- Modify: `docs/v2/phase8/PHASE8_DECISION_FREEZE.md`
- Create: `build/tools/check_ai_decision_intelligence_boundary.py`
- Create: `tests_v1/test_ai_decision_intelligence_boundary.py`

**Interfaces:**
- Consumes: locked architecture spec and amended Phase-8 freeze.
- Produces: canonical OD-V2-15/16 FROZEN root status plus a static authority guard preventing duplicate risk/accounting/auth/admin authorities and Live-enabling imports.

- [ ] **Step 1: Write failing tests** asserting root OD-V2-15/16 are FROZEN, Live remains DISARMED, and the boundary checker rejects a fixture that mints/bypasses ApprovedOrder or introduces an AI-specific accounting/auth authority.
- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest tests_v1/test_ai_decision_intelligence_boundary.py -q`
Expected: FAIL because root register/checker are not synchronized yet.

- [ ] **Step 3: Implement the minimal root decision sync and static checker**. Checker must explicitly recognize `RiskGateV2`, existing `engine/portfolio/`, S2 `DeviceSessionGate`, and authoritative `dashboard/owner-dashboard/` as reused authorities.
- [ ] **Step 4: Run GREEN verification**

Run: `python -m pytest tests_v1/test_ai_decision_intelligence_boundary.py -q && python build/tools/check_ai_decision_intelligence_boundary.py`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "docs: freeze AI decision intelligence authority"`

---

### Task 2: Extend candidate and council contracts for 0..N intelligence

**Files:**
- Modify: `engine/ai/contracts.py`
- Modify: `engine/ai/v2/contracts.py`
- Modify: `engine/ai/v2/candidates.py`
- Modify: `engine/ai/laya.py`
- Create: `engine/ai/v2/review_council.py`
- Create: `tests_v1/test_ai_decision_intelligence_candidates.py`
- Create: `tests_v1/test_ai_review_council.py`

**Interfaces:**
- Produces: `IntelligenceCandidate`, review dispositions, lineage/correlation evidence, and dynamic council aggregation that works with zero, one, or many participants.
- Consumes later: Candidate Pool/orchestration and Owner read models.

- [ ] **Step 1: Write failing tests** for zero participants, one provider, Laya-only, multiple providers, candidate TTL/schema, and `correlated_model_flag` behavior.
- [ ] **Step 2: Run RED tests**

Run: `python -m pytest tests_v1/test_ai_decision_intelligence_candidates.py tests_v1/test_ai_review_council.py -q`
Expected: FAIL for missing contracts/council.

- [ ] **Step 3: Implement minimal immutable contracts and council aggregation**. Blind majority must not create execution authority; repeated same provider/model roles must set correlation evidence.
- [ ] **Step 4: Run GREEN tests**

Run: `python -m pytest tests_v1/test_ai_decision_intelligence_candidates.py tests_v1/test_ai_review_council.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: add AI intelligence candidates and review council"`

---

### Task 3: Upgrade versioned MarketWatchPolicy, scope requests, and provider queue

**Files:**
- Modify: `engine/ai/monitoring_scheduler_v2.py`
- Modify: `engine/ai/provider_queue_v2.py`
- Modify: `engine/ai/provider_registry.py`
- Create: `engine/ai/scope_expansion_v2.py`
- Modify: `tests_v1/test_ai_monitoring_provider_queue_v2.py`
- Create: `tests_v1/test_ai_market_watch_policy_v2.py`

**Interfaces:**
- Produces: versioned Owner policy with sessions/timeframes/task classes, scheduled/event/owner triggers, immutable scope-expansion requests, provider priority/TTL/backoff/quota behavior.
- Consumes later: orchestration, Owner Dashboard API.

- [ ] **Step 1: Write failing tests** for policy versioning, out-of-scope instruments, no self-reschedule, expired tasks, priority ordering, queue capacity, alternate-provider routing only when policy allows, and immutable `ScopeExpansionRequest`.
- [ ] **Step 2: Run RED tests**

Run: `python -m pytest tests_v1/test_ai_monitoring_provider_queue_v2.py tests_v1/test_ai_market_watch_policy_v2.py -q`
Expected: FAIL on new policy/request behavior.

- [ ] **Step 3: Extend existing scheduler/queue rather than creating a second scheduler**. Preserve current API compatibility where existing tests rely on it.
- [ ] **Step 4: Run GREEN tests**

Run: `python -m pytest tests_v1/test_ai_monitoring_provider_queue_v2.py tests_v1/test_ai_market_watch_policy_v2.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: extend AI market watch policy and provider queue"`

---

### Task 4: Add strategy review, independent candidate orchestration, and Strategy Hunting data gate

**Files:**
- Modify: `engine/ai/v2/orchestrator.py`
- Modify: `engine/ai/orchestrator.py`
- Modify: `engine/ai/v2/data_policy.py`
- Modify: `engine/ai/v2/provider_gateway.py`
- Create: `engine/ai/v2/strategy_hunting.py`
- Create: `tests_v1/test_ai_strategy_review_orchestration.py`
- Create: `tests_v1/test_ai_strategy_hunting.py`

**Interfaces:**
- Consumes: Task 2 candidate/council contracts and Task 3 scheduler/queue.
- Produces: strategy review evidence, independent IntelligenceCandidate creation, and after-hours hunting jobs that must pass OD-V2-16/Data V2 egress authorization before third-party provider calls.

- [ ] **Step 1: Write failing tests** for Strategy-only fallback, Laya-only, one-AI sequential proposer/critic correlation, multi-AI review, independent candidate generation, and licensed/unlicensed Strategy Hunting egress.
- [ ] **Step 2: Run RED tests**

Run: `python -m pytest tests_v1/test_ai_strategy_review_orchestration.py tests_v1/test_ai_strategy_hunting.py -q`
Expected: FAIL for missing orchestration/hunting behavior.

- [ ] **Step 3: Implement orchestration using existing provider gateway/data-policy seams**. Local provider calls remain subject to dataset usage policy; third-party/cloud egress fails closed without provenance/licensing evidence.
- [ ] **Step 4: Run GREEN tests**

Run: `python -m pytest tests_v1/test_ai_strategy_review_orchestration.py tests_v1/test_ai_strategy_hunting.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: add AI strategy review and strategy hunting"`

---

### Task 5: Reuse Portfolio authority for candidate arbitration and multi-broker atomic reservations

**Files:**
- Modify: `engine/portfolio/accounting.py`
- Modify: `engine/portfolio/model.py`
- Modify: `engine/portfolio/virtual_account.py` only if required by existing reservation semantics
- Modify: `engine/risk/portfolio_admission_v2.py`
- Create: `engine/portfolio/candidate_arbitration_v2.py`
- Create: `tests_v1/test_ai_candidate_portfolio_arbitration.py`
- Extend: `tests_v1/test_phase7_portfolio_admission_v2.py` (or the existing Phase-7 admission test file actually present in the branch)

**Interfaces:**
- Consumes: StrategyCandidate/IntelligenceCandidate metadata.
- Produces: existing-portfolio-backed reservation/admission result keyed by `Broker + Account`, plus cross-account aggregate exposure evidence handed to existing `RiskGateV2` admission.

- [ ] **Step 1: Write failing tests** for simultaneous same-account candidates, atomic reserve/release, reservation TTL, distinct broker/account parallelism, aggregate exposure limits, and no AI-specific accounting ledger.
- [ ] **Step 2: Run RED tests**

Run: `python -m pytest tests_v1/test_ai_candidate_portfolio_arbitration.py -q`
Expected: FAIL for missing arbitration/multi-account behavior.

- [ ] **Step 3: Implement a thin arbitration extension over existing Portfolio/Phase-7 reservation authority**. Do not mint ApprovedOrder here; route surviving admission through existing `RiskGateV2` path.
- [ ] **Step 4: Run GREEN tests plus Phase-7 preservation**

Run: `python -m pytest tests_v1/test_ai_candidate_portfolio_arbitration.py tests_v1/test_phase7* -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: arbitrate AI candidates through portfolio authority"`

---

### Task 6: Add S2-backed intelligence entitlements

**Files:**
- Modify: `dashboard/backend/account_v2/contracts.py`
- Modify: `dashboard/backend/account_v2/repository.py` if entitlement persistence belongs there
- Create: `dashboard/backend/account_v2/intelligence_entitlements.py`
- Modify: `dashboard/backend/owner_admin/user_inspection.py`
- Create: `tests_v1/test_ai_intelligence_entitlements.py`

**Interfaces:**
- Consumes: existing `DeviceSessionGateResult` / S2 authenticated principal.
- Produces: fail-closed capability checks for `ACCESS_LAYA_ANALYSIS`, `ACCESS_AI_REVIEW`, `ACCESS_INTELLIGENCE_CANDIDATES`, `ACCESS_STRATEGY_HUNTING`, `ACCESS_ADVANCED_RESEARCH`.

- [ ] **Step 1: Write failing tests** for valid S2 principal, invalid/revoked session, authority unavailable, normal-user self-grant rejection, and Owner inspection of entitlements.
- [ ] **Step 2: Run RED tests**

Run: `python -m pytest tests_v1/test_ai_intelligence_entitlements.py -q`
Expected: FAIL for missing entitlement layer.

- [ ] **Step 3: Implement entitlement authorization strictly above S2**. Do not create a second identity/session token/gate.
- [ ] **Step 4: Run GREEN tests plus S2 preservation**

Run: `python -m pytest tests_v1/test_ai_intelligence_entitlements.py tests_v1/test_s2_* -q`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -am "feat: add S2-backed AI capability entitlements"`

---

### Task 7: Extend the authoritative Owner AI Control Center

**Files:**
- Modify: `dashboard/backend/owner_admin/contracts.py`
- Modify: `dashboard/backend/owner_admin/repository.py`
- Modify: `dashboard/backend/owner_admin/router.py`
- Modify: `dashboard/owner-dashboard/authoritative/api.ts`
- Modify: `dashboard/owner-dashboard/authoritative/AIControlCenter.tsx`
- Modify/Create: corresponding Owner AI Control Center Vitest files under `dashboard/owner-dashboard/authoritative/`
- Modify: `build/tools/check_owner_admin_boundary.py` only if required to recognize new authoritative files without weakening the boundary.

**Interfaces:**
- Consumes: Tasks 2–6 read/configuration contracts.
- Produces: Owner-only dashboard controls/read models for Laya/provider enablement, capabilities, MarketWatchPolicy, queue/budget state, Strategy Hunting, scope requests, candidate/portfolio intelligence status, and per-user entitlements.

- [ ] **Step 1: Write failing backend/frontend tests** proving controls are Owner-only, step-up requirements remain where existing Owner policy requires them, and no normal user/global config route is exposed.
- [ ] **Step 2: Run RED tests**

Run backend: `python -m pytest tests_v1/test_owner_admin* tests_v1/test_ai_intelligence_entitlements.py -q`
Run frontend: `npm test -- --run` from dashboard workspace using the existing repo command.
Expected: new assertions FAIL.

- [ ] **Step 3: Extend existing AI Control Center and owner-admin backend**. Preserve credential secrecy and existing authoritative UI namespace.
- [ ] **Step 4: Run GREEN backend/frontend tests, TypeScript check and Vite build**

Expected: all PASS; no new Owner UI surface created.

- [ ] **Step 5: Commit**

`git commit -am "feat: add Owner decision intelligence controls"`

---

### Task 8: Add qualification guard, full regression evidence, and exact-head workflow coverage

**Files:**
- Create: `build/tools/ai_decision_intelligence_probe.py`
- Create: `docs/qualification/AI_LAYA_DECISION_INTELLIGENCE_2026-10-01.md`
- Modify/Create: GitHub Actions workflow used for this feature branch qualification under `.github/workflows/`
- Modify: `docs/superpowers/specs/2026-10-01-ai-laya-decision-intelligence-architecture.md` only for verified implementation references, not design changes.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: deterministic invariant markers and evidence for zero/one/many AI, Laya OFF, correlated-model evidence, multi-broker reservation separation, OD-V2-16 gate, S2 entitlements, Owner-only controls, existing RiskGateV2 authority, and Live DISARMED preservation.

- [ ] **Step 1: Write/extend qualification tests and probe expectations** before adding success markers.
- [ ] **Step 2: Run feature-focused verification and full Python regression**

Expected: feature tests PASS; full suite preserves or improves the Phase-9 baseline.

- [ ] **Step 3: Run static authority guards, npm audits, frontend Vitest, typecheck and production build**

Expected: PASS and 0 npm audit vulnerabilities where the existing qualification currently requires zero.

- [ ] **Step 4: Add exact-head workflow/evidence markers** including:
  - `AI_INTELLIGENCE_STRATEGY_INDEPENDENCE=PASS`
  - `AI_INTELLIGENCE_ZERO_TO_N=PASS`
  - `AI_INTELLIGENCE_RISKGATE_AUTHORITY=PASS`
  - `AI_INTELLIGENCE_MULTI_BROKER_RESERVATION=PASS`
  - `AI_INTELLIGENCE_OD16_EGRESS=PASS`
  - `AI_INTELLIGENCE_S2_ENTITLEMENTS=PASS`
  - `AI_INTELLIGENCE_OWNER_DASHBOARD=PASS`
  - `LIVE_STATE=READ_ONLY/DISARMED`

- [ ] **Step 5: Re-run exact-head hosted qualification and archive evidence**

Expected: all required jobs succeed on the same exact head before merge consideration.

- [ ] **Step 6: Commit**

`git commit -am "test: qualify AI Laya decision intelligence architecture"`

---

## Plan Self-Review

- Spec coverage: all locked authority, provider, candidate, scheduler, queue, strategy-hunting, OD-V2-16, portfolio, multi-broker, S2 entitlement, Owner Dashboard and invariant requirements map to Tasks 1–8.
- Interface consistency: Tasks 2/3 produce contracts consumed by Task 4; Task 4 candidate outputs are admitted by Task 5; Task 6 entitlement output is consumed by Task 7; Task 8 verifies all prior outputs.
- Existing-authority reuse is explicit in every task that could otherwise create a duplicate system.
- Entry Gate remains out of scope.
- User-side AI/Laya UX remains deferred exactly as locked in the spec.
- Real-money Live mutation remains out of scope and DISARMED.
