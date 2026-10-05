# Canonical User Action Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the canonical seven-screen AlgoFortis User dashboard genuinely actionable for strategy submission, backtests, walk-forward/OOS, Paper sessions, and safe `LIVE_PAPER` deployments while preserving real-money Live as `READ_ONLY / DISARMED`.

**Architecture:** Keep `UserDashboardApp` and its current seven canonical routes. Reuse the existing governed backend endpoints through `dashboard/shared/services/integrationClient.ts`, add only the missing typed User mutation contract there, and inject action functions into focused canonical screens for deterministic component testing. Do not revive `UserScreens.tsx` or `BacktestingScreen.tsx` as canonical routes; use them only as reference for already-proven client calls and UX expectations.

**Tech Stack:** React 19, TypeScript 7, Vitest/jsdom, FastAPI/Python backend, pytest, Playwright/Chromium verification.

**Spec:** `docs/superpowers/specs/2026-10-05-canonical-dashboard-action-control-plane-design.md`

## Global Constraints

- Live remains **READ_ONLY / DISARMED**.
- Canonical User UI must never expose `/api/v1/live/arm`, broker order placement/modification/cancellation, or a real `LIVE` deployment choice.
- User-created deployments in this plan use **`LIVE_PAPER` only**.
- User market-data import remains Owner-only.
- Mutations must fail closed: no sample/local-success fallback.
- Missing/stale/unknown authority must not be relabelled healthy or ready.
- Existing RiskGate, strategy eligibility, service entitlement, dataset governance, session ownership, audit, and NON_PROMOTABLE safeguards stay authoritative.
- Hardcoded production-looking safety/risk numbers are forbidden from canonical User surfaces.
- Canonical screens must not import legacy sample modules (`userStrategies`, `liveOrders`, `optionsChain`, `userAgents`, `userSecurity`) or the legacy monolithic `UserScreens.tsx`.

## Review Focus

1. **Double-click / duplicate mutation:** pending actions must disable repeat submission; add component tests that trigger once and assert one action call.
2. **Backend rejection after valid-looking input:** preserve the previous read model and show the returned rejection; add tests for rejected backtest, WFO, Paper, strategy, and deployment actions.
3. **Authority refresh failure after successful mutation:** show mutation success/receipt without fabricating refreshed state; add tests where action succeeds but `loadData()` refresh rejects.
4. **Unsafe execution-mode input:** no canonical control may submit `LIVE`; test deployment payload is exactly `LIVE_PAPER` even when existing records include `LIVE` read-only evidence.
5. **Stale/unavailable reads with action controls:** controls requiring authority must disable or fail closed; tests must prove stale/unknown state is not promoted to actionable readiness.

---

## File Structure

**Modify**
- `dashboard/shared/services/integrationClient.ts` — add the missing typed strategy-submission mutation; reuse existing backtest/WFO/Paper/deployment clients.
- `dashboard/user-dashboard/screens/UserTesting.tsx` — canonical Backtest + WFO run/cancel controls and authoritative refresh.
- `dashboard/user-dashboard/screens/UserTrades.tsx` — canonical Paper session create/start/stop controls while Live stays read-only.
- `dashboard/user-dashboard/screens/UserStrategies.tsx` — strategy submission/promotion plus `LIVE_PAPER` deployment lifecycle controls.
- `dashboard/user-dashboard/screens/UserFinishedSurfaces.test.tsx` — preserve current truth-state regression coverage and add canonical action assertions where useful.

**Create**
- `dashboard/user-dashboard/screens/UserTestingActions.test.tsx` — focused Backtest/WFO mutation tests.
- `dashboard/user-dashboard/screens/UserTradesActions.test.tsx` — focused Paper mutation tests.
- `dashboard/user-dashboard/screens/UserStrategiesActions.test.tsx` — focused strategy/promotion/deployment tests.
- `dashboard/web/scripts/user-action-control-smoke.mjs` — routed Chromium verification of canonical User action controls using canonical backend-contract fixtures.

**Backend tests to extend only if contract gaps are discovered**
- `tests_v1/test_area5_complete_product_workflows.py`
- existing backtest/WFO/deployment/paper API tests nearest the changed contract.

No new backend subsystem is planned in Slice A; existing endpoints are the source of truth.

---

### Task 1: Pin the User Mutation Client Boundary

**Files:**
- Modify: `dashboard/shared/services/integrationClient.ts`
- Create: `dashboard/user-dashboard/screens/UserStrategiesActions.test.tsx` (initial client-consumer contract cases; expanded again in Task 4)

**Interfaces:**
- Consumes existing: `executeBacktest(BacktestExecuteRequest)`, `cancelBacktestRun(runId)`, `createWalkForwardJob(WalkForwardCreateRequest)`, `cancelWalkForwardJob(jobId)`, `createPaperSession(PaperSessionCreateRequest)`, `startPaperSession(sessionId)`, `stopPaperSession(sessionId)`, `requestStrategyPromotion(strategyId, opts)`, `createUserDeployment(params)`, `pauseUserDeployment(id)`, `resumeUserDeployment(id)`, `stopUserDeployment(id)`.
- Produces: `submitUserStrategy(source: string, protectivePolicyIdentity?: string | null): Promise<MutationResult<StrategySubmitReceipt>>` using `POST /api/v1/strategies` with `{ source, protective_policy_identity }` and no fallback success.

- [ ] **Step 1: Write the failing mutation contract test**

Add a test that stubs `fetch`, enables backend authority, calls `submitUserStrategy("class X...", "POL-1")`, and asserts one POST to `/api/v1/strategies` with the exact JSON keys `source` and `protective_policy_identity`. Assert a non-2xx response becomes `success: false` and never `isFallback: true`.

- [ ] **Step 2: Run the focused test and verify RED**

Run from `dashboard/web`: `npm run test:user-dashboard -- ../user-dashboard/screens/UserStrategiesActions.test.tsx`
Expected: FAIL because `submitUserStrategy` is not exported.

- [ ] **Step 3: Implement the minimal typed client**

Add `StrategySubmitReceipt` and `submitUserStrategy(...)` to `dashboard/shared/services/integrationClient.ts`, following the existing `MutationResult<T>` and authenticated `fetchWithTimeout` pattern.

- [ ] **Step 4: Run the focused test and existing User dashboard suite**

Run: `npm run test:user-dashboard -- ../user-dashboard/screens/UserStrategiesActions.test.tsx`
Expected: PASS.

Run: `npm run test:user-dashboard`
Expected: all current User dashboard tests PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add canonical user strategy submission client`

---

### Task 2: Make Testing & Validation Actionable

**Files:**
- Modify: `dashboard/user-dashboard/screens/UserTesting.tsx`
- Create: `dashboard/user-dashboard/screens/UserTestingActions.test.tsx`
- Modify: `dashboard/user-dashboard/screens/UserFinishedSurfaces.test.tsx`

**Interfaces:**
- Consumes Task 1 shared client boundary plus existing `loadTestingSurface()`.
- Produces canonical UI actions: `Run Backtest`, `Cancel Backtest`, `Run Walk-Forward`, `Cancel Walk-Forward`; mutation functions are injectable props with defaults bound to the shared clients.

- [ ] **Step 1: Write RED tests for Backtest controls**

Test an AVAILABLE testing surface renders a Backtest form with Strategy ID, Dataset ID, Instrument, Timeframe, Initial Capital, Date Range and `Run Backtest`. Invoke the button and assert `executeBacktest` receives the exact entered payload once, duplicate click is disabled while pending, and success triggers `loadData()` refresh.

Add a rejection case asserting backend error text is visible and existing run rows remain visible.

- [ ] **Step 2: Run focused Backtest tests and verify RED**

Run: `npm run test:user-dashboard -- ../user-dashboard/screens/UserTestingActions.test.tsx`
Expected: FAIL because canonical controls do not exist.

- [ ] **Step 3: Implement Backtest action panel in `UserTesting.tsx`**

Add injected props typed from `executeBacktest`/`cancelBacktestRun`. Render controls only against usable authority; keep stale/unavailable messaging fail-closed. Show mutation receipt/error separately from the read model. Add Cancel only for backend statuses treated as cancellable by the existing contract.

- [ ] **Step 4: GREEN the Backtest tests**

Run the focused test file; expected PASS.

- [ ] **Step 5: Add RED tests for Walk-Forward/OOS**

Assert fields: Strategy ID, Dataset ID, Instrument, Timeframe, IS Days, OOS Days, Max Windows, Initial Capital; assert `createWalkForwardJob` exact payload; assert a RUNNING/PENDING job exposes Cancel and calls `cancelWalkForwardJob(jobId)` once.

Cover stale/unavailable authority: no READY/PASS inference and mutation is disabled/fails closed.

- [ ] **Step 6: Implement Walk-Forward controls and refresh behavior**

Use existing shared client functions; no progress fabrication. Preserve backend job status/progress as the only progress source.

- [ ] **Step 7: Run focused + finished-surface tests**

Run: `npm run test:user-dashboard -- ../user-dashboard/screens/UserTestingActions.test.tsx ../user-dashboard/screens/UserFinishedSurfaces.test.tsx`
Expected: PASS.

- [ ] **Step 8: Commit**

Commit message: `feat: activate canonical user research controls`

---

### Task 3: Make Trades an Actionable Paper Runtime

**Files:**
- Modify: `dashboard/user-dashboard/screens/UserTrades.tsx`
- Create: `dashboard/user-dashboard/screens/UserTradesActions.test.tsx`
- Modify: `dashboard/user-dashboard/screens/UserFinishedSurfaces.test.tsx`

**Interfaces:**
- Consumes existing `createPaperSession`, `startPaperSession`, `stopPaperSession`, `queryPaperSessions` or equivalent existing Paper-session read client, and `loadTradingSurface`.
- Produces canonical Paper actions while `ModeTrades(mode="LIVE")` remains observation-only with `READ_ONLY / DISARMED`.

- [ ] **Step 1: Write RED create-session tests**

Mount `UserTrades` with AVAILABLE Paper authority and injected mutation functions. Assert fields for Strategy ID, Instrument, Timeframe, Initial Capital, data-source mode and optional Dataset/Date Range as supported by `PaperSessionCreateRequest`. Click `Create Paper Session`; assert one exact mutation call and refresh.

- [ ] **Step 2: Verify RED**

Run: `npm run test:user-dashboard -- ../user-dashboard/screens/UserTradesActions.test.tsx`
Expected: FAIL because Paper controls are absent.

- [ ] **Step 3: Implement Paper session control panel**

Add injectable action props with shared-client defaults. Render authoritative sessions and allow Start only for startable states and Stop only for running states. Surface backend hold/suspension/RiskGate rejection without changing the visible read model optimistically.

- [ ] **Step 4: Add and GREEN start/stop/rejection tests**

Assert Start calls `startPaperSession(sessionId)` once, Stop calls `stopPaperSession(sessionId)` once, pending disables duplicate action, and rejected responses remain visible.

- [ ] **Step 5: Add Live safety assertions**

Assert canonical Trades contains `READ_ONLY / DISARMED` and contains no `Arm Live`, `/api/v1/live/arm`, broker-order action, or real Live mutation affordance.

- [ ] **Step 6: Run focused + finished-surface tests**

Run: `npm run test:user-dashboard -- ../user-dashboard/screens/UserTradesActions.test.tsx ../user-dashboard/screens/UserFinishedSurfaces.test.tsx`
Expected: PASS.

- [ ] **Step 7: Commit**

Commit message: `feat: activate canonical paper session controls`

---

### Task 4: Make Strategies an Actionable Lifecycle + LIVE_PAPER Deployment Surface

**Files:**
- Modify: `dashboard/user-dashboard/screens/UserStrategies.tsx`
- Expand: `dashboard/user-dashboard/screens/UserStrategiesActions.test.tsx`
- Modify: `dashboard/user-dashboard/screens/UserFinishedSurfaces.test.tsx`

**Interfaces:**
- Consumes Task 1 `submitUserStrategy`, existing `requestStrategyPromotion`, `createUserDeployment`, `pauseUserDeployment`, `resumeUserDeployment`, `stopUserDeployment`, plus `loadStrategiesSurface`.
- Produces canonical controls for strategy submission, promotion request, deployment creation and deployment lifecycle. `createUserDeployment` payload is hard-pinned to `execution_mode: "LIVE_PAPER"`.

- [ ] **Step 1: Write RED strategy-submission UI tests**

Assert a source editor/textarea, optional protective policy field and `Submit Strategy` action. Assert exact call to `submitUserStrategy`, duplicate prevention, backend rejection rendering, and refresh on success.

- [ ] **Step 2: Implement strategy submission panel and GREEN it**

Use the shared client; do not import `dashboard/web/src/api.ts` and do not reuse legacy sample data.

- [ ] **Step 3: Write RED promotion tests**

For an authoritative strategy row, assert `Request Promotion` calls `requestStrategyPromotion(strategyId, { target_stage: "PAPER_ELIGIBLE", ... })` and renders backend receipt/rejection. No direct stage mutation is allowed.

- [ ] **Step 4: Implement promotion request control and GREEN it**

Refresh the canonical strategy surface only after backend acceptance.

- [ ] **Step 5: Write RED deployment tests**

Assert create form takes Strategy, Connection ID, Instrument, Timeframe and Risk Ref where supported, but **does not render an execution-mode chooser**. Assert payload sent to `createUserDeployment` contains `execution_mode: "LIVE_PAPER"` exactly. Existing read-only `LIVE` records may be displayed but cannot be created/resumed through a Live control.

For existing deployments, assert PAUSED can Resume, active can Pause/Stop, STOPPED has no Resume, and backend rejection is shown without local fake transition.

- [ ] **Step 6: Implement deployment controls and GREEN them**

Reuse existing shared clients. All lifecycle state after action comes from refreshed backend evidence.

- [ ] **Step 7: Run focused + canonical surface suites**

Run: `npm run test:user-dashboard -- ../user-dashboard/screens/UserStrategiesActions.test.tsx ../user-dashboard/screens/UserFinishedSurfaces.test.tsx`
Expected: PASS.

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 8: Commit**

Commit message: `feat: activate strategy and live-paper deployment controls`

---

### Task 5: Backend Contract Regression + Routed Chromium Qualification

**Files:**
- Extend nearest existing Python API tests only where current contracts lack explicit proof.
- Create: `dashboard/web/scripts/user-action-control-smoke.mjs`
- Modify static boundary tests if necessary: `tests_v1/test_v1_salvage_user_dashboard_boundaries.py`

**Interfaces:**
- Consumes completed canonical screens from Tasks 2–4.
- Produces final Slice-A qualification evidence: real endpoint contract tests + routed browser action proof + preserved Live safety boundary.

- [ ] **Step 1: Add missing backend contract tests only**

Pin these behaviors if not already directly tested: eligible User backtest creation/cancel; WFO create/cancel; Paper create/start/stop; deployment create/pause/resume/stop with `LIVE_PAPER`; strategy submission rejection/eligibility. Do not duplicate tests already proving the exact contract.

- [ ] **Step 2: Run focused Python tests**

Run the nearest test modules plus `tests_v1/test_area5_complete_product_workflows.py`.
Expected: PASS.

- [ ] **Step 3: Add static safety boundary assertions**

Assert canonical User files do not import legacy sample modules or `UserScreens.tsx`; do not contain `/api/v1/live/arm`, broker order mutation paths, or hardcoded `ARMED & READY` safety copy; deployment create UI is `LIVE_PAPER` only.

- [ ] **Step 4: Create canonical routed Chromium smoke**

In `user-action-control-smoke.mjs`, launch the actual `DashboardV3App` User path and provide deterministic canonical backend-contract responses. Exercise: Strategies submit; Testing run Backtest; WFO create; Trades Paper create/start/stop; Strategy `LIVE_PAPER` deployment create/pause/resume/stop. Assert outbound requests use the canonical endpoints and exact safe mode payloads. Assert Live still displays `READ_ONLY / DISARMED` and no Live mutation control exists.

- [ ] **Step 5: Run the full frontend qualification**

From `dashboard/web`:
- `npm run test:user-dashboard`
- `npm run typecheck`
- `npm run build`
- run `node scripts/user-action-control-smoke.mjs` under the same Playwright/preview-server convention used by the existing Owner smoke.

Expected: all PASS and smoke prints a stable marker such as `USER_ACTION_CONTROL_SMOKE=PASS`.

- [ ] **Step 6: Run full Python regression and safety qualification**

Run the repository's current full pytest suite and the existing Live READ_ONLY / AI firewall / risk qualification checks used by current `main` CI.
Expected: no regression; Live remains `READ_ONLY/DISARMED`; broker mutation absent.

- [ ] **Step 7: Commit**

Commit message: `test: qualify canonical user action control plane`

---

## Slice-A Done Criteria

Slice A is complete only when all of these are true:

1. Canonical `Strategies` can submit strategy source, request Paper eligibility promotion, create `LIVE_PAPER` deployments, and pause/resume/stop allowed deployments.
2. Canonical `Testing & Validation` can create/cancel Backtests and WFO/OOS jobs and display only authoritative progress/results.
3. Canonical `Trades` can create/start/stop Paper sessions and display Paper runtime evidence.
4. Canonical Live controls remain observation-only with `READ_ONLY / DISARMED`; no real Live arm/order mutation is exposed.
5. No mutation falls back to sample/local success.
6. Focused component tests, full User dashboard tests, typecheck, production build, backend contract tests, full Python regression, safety gates, and routed Chromium smoke are GREEN.
7. Subsequent plans remain separate: Slice B Owner wiring/settings auth; Slice C kill-switch + RiskGate projection; Slice D legacy/docs cleanup and final integrated qualification.
