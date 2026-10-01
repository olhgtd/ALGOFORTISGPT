# Normal User Dashboard Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the canonical Normal User Dashboard wiring so Home, Markets, Strategies, Testing & Validation, Trades, Portfolio and Account surface only authoritative backend truth, preserve stale/unknown states, and share one truthful shell/attention model.

**Architecture:** Keep the existing V1-quality user UI and existing V2 read services. Add a small user-shell authority adapter that derives display state only from backend evidence, complete STALE propagation through market reads, wire Home summaries to the same existing user loaders, and add static/runtime regression guards that prevent sample fixtures or execution authority from re-entering the canonical user surface.

**Tech Stack:** React, TypeScript, Vitest, existing `dashboard/shared/services/integrationClient.ts`, V2 backend read APIs.

**Spec:** `docs/v1-salvage-integration/SLICE4_CHECKPOINT_1_USER_SHELL_TRUTH.md`

## Global Constraints

- Canonical navigation remains Home, Markets, Strategies, Testing & Validation, Trades, Portfolio, Account.
- Missing authority renders UNKNOWN / UNAVAILABLE / STALE; never fabricated healthy, PASS, P&L, positions, connections, prices, alerts or readiness.
- Live remains READ_ONLY / DISARMED; broker connected does not imply Live armed.
- UI never owns order execution, RiskGate approval, broker mutation, recovery resume or promotion authority.
- Paper and Live capital/trade projections remain isolated.
- Sample/static user data may remain as legacy files but must not be imported by the canonical user app/routes.
- Owner/Admin and Laya are out of scope for this plan.

## Review Focus

1. Multiple active deployments with conflicting modes must yield UNKNOWN mode, not a guessed mode.
2. RECOVERY/HALTED/READY_FOR_RESUME must require manual resume and outrank ordinary RUNNING/PAUSED presentation.
3. Canonical STALE market candles must remain visible as STALE, not be promoted to AVAILABLE or dropped to fake NO_DATA.
4. Backend-unavailable notifications must be derived from failed authority reads and never from sample fixtures.
5. Direct route entry (`#markets`, `#trades`, etc.) must receive the same shell truth as Home without requiring a Home visit.

---

### Task 1: Shared user shell authority and Attention Center

**Files:**
- Create: `dashboard/user-dashboard/data/userShellData.ts`
- Create: `dashboard/user-dashboard/data/userShellData.test.ts`
- Modify: `dashboard/user-dashboard/UserDashboardApp.tsx`
- Modify: `dashboard/user-dashboard/UserDashboardApp.test.tsx`
- Modify: `dashboard/user-dashboard/shellState.ts`
- Modify: `dashboard/user-dashboard/shellState.test.ts`

**Interfaces:**
- Consumes: `queryPersistenceHealth`, `queryMarketChart`, `listUserConnections`, `listUserDeployments`, `liveReadinessRequest`.
- Produces: `loadUserShellAuthority()` returning `{ status, notifications, risk }`.

- [ ] Write failing tests for conflicting deployment modes, HALTED/manual-resume semantics, broker state mapping, derived notifications and direct-route shell hydration.
- [ ] Implement pure derivation helpers and `loadUserShellAuthority()` with fail-closed fallbacks.
- [ ] Make `UserDashboardApp` use the shared loader for all routes and pass its authoritative notifications to `UserDashboardShell`.
- [ ] Keep Home from becoming a competing shell authority.

### Task 2: STALE market truth end-to-end

**Files:**
- Modify: `dashboard/shared/services/integrationClient.ts`
- Modify: `dashboard/shared/components/professionalChartTruth.ts`
- Modify: `dashboard/user-dashboard/markets/marketsModel.ts`
- Modify: `dashboard/user-dashboard/markets/MarketsChart.tsx`
- Modify: `dashboard/user-dashboard/markets/UserMarkets.tsx`
- Modify: market/home tests.

**Interfaces:**
- Produces: `MarketChartState` that includes `STALE` and preserves canonical stale candles.

- [ ] Write failing tests proving STALE candles survive service -> model -> chart quote.
- [ ] Add `STALE` to the typed client contract and parser.
- [ ] Render stale candles with stale authority labeling while retaining read-only semantics.

### Task 3: Complete Home command-center wiring

**Files:**
- Modify: `dashboard/user-dashboard/home/homeData.ts`
- Modify: `dashboard/user-dashboard/home/homeModel.ts`
- Modify: `dashboard/user-dashboard/home/components/StrategyStatusSummary.tsx`
- Modify: `dashboard/user-dashboard/home/components/TestingProgressSummary.tsx`
- Modify: `dashboard/user-dashboard/home/components/RiskSummary.tsx`
- Modify: Home tests.

**Interfaces:**
- Consumes: existing `loadStrategiesSurface`, `loadTestingSurface`, shared shell/risk authority.
- Produces: Home strategy/testing/risk summaries backed by the same authorities as their full screens.

- [ ] Write failing tests showing Home no longer hard-codes Strategies/Testing as UNAVAILABLE when backend-authoritative data exists.
- [ ] Map counts/states only; do not invent success/promotion verdicts.
- [ ] Use exact backend risk state when available; otherwise UNKNOWN.

### Task 4: Canonical surface anti-sample / anti-execution guard

**Files:**
- Create: `tests_v1/test_v1_salvage_user_dashboard_boundaries.py`
- Modify: `dashboard/user-dashboard/screens/UserFinishedSurfaces.test.tsx` only if required.

**Interfaces:**
- Produces: static regression boundary for canonical user routes.

- [ ] Pin seven-route navigation.
- [ ] Reject imports from legacy sample-data modules (`userStrategies`, `liveOrders`, `optionsChain`, `userAgents`, `userSecurity`) in canonical app/screens/home/markets files.
- [ ] Reject direct broker mutation/order execution APIs from canonical user app/routes.
- [ ] Pin READ_ONLY / DISARMED Live copy and fail-closed authority language.

### Task 5: Finish checkpoint and qualification record

**Files:**
- Create: `docs/v1-salvage-integration/SLICE4_NORMAL_USER_DASHBOARD_COMPLETION.md`

- [ ] Audit branch diff against the frozen Slice-4 checkpoint.
- [ ] Attempt focused Vitest/typecheck/build/full regression in any available authorized runner.
- [ ] Record executed evidence exactly; if no runner is available, explicitly mark execution verification pending rather than claiming GREEN.
- [ ] Freeze a dedicated checkpoint branch at the final exact SHA.
