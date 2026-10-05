# AlgoFortis Owner Full Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the canonical Owner Dashboard into the primary safe operational control center for administration, research, Paper, deployment, data, AI, security, settings, diagnostics, and supported product operations while preserving `LIVE READ_ONLY / DISARMED`, RiskGate authority, fail-closed behavior, WebAuthn step-up, and audit guarantees.

**Architecture:** Keep the Owner UI as a typed client over existing backend authorities. Reuse real backend routes first; add only narrow Owner-facing adapters where a service exists but no safe Owner route exists. Never duplicate engine logic in React, never add direct broker/Live mutation authority, and never render missing/stale authority as success.

**Tech Stack:** Python 3.13.14, FastAPI/Pydantic, SQLite-backed existing authorities, React/TypeScript/Vite/Vitest, pytest, GitHub Actions Windows verification.

**Spec:** `docs/superpowers/specs/2026-10-05-owner-full-control-plane-design.md`

## Global Constraints

- Real-money Live remains `READ_ONLY / DISARMED`.
- No Owner broker order placement, modification, cancellation, or Live ARM authority.
- RiskGate remains the sole risk decision/order approval authority.
- No kill-switch-disable control is introduced.
- No raw secrets, private keys, bearer tokens, `.env` editing, arbitrary filesystem editing, or generic terminal/shell surface in the dashboard.
- Missing/stale authority fails closed and cannot be displayed as healthy, ready, safe, PASS, zero, or armed.
- Existing Owner/Admin, AI, S2 account, portfolio/risk, Live-read-only, and architecture guards remain enabled and may only be strengthened.
- Destructive/high-impact Owner mutations require the existing authorization model and fresh WebAuthn step-up where classified.
- Every mutation must re-read backend authority before the UI claims success.
- Existing User/Owner, Backtest/Paper/Shadow/Live isolation remains intact.
- Canonical production Owner UI remains `dashboard/owner-dashboard/OwnerDashboardApp.tsx` plus `dashboard/owner-dashboard/authoritative/**`; legacy/sample-heavy screens are donors only.

## Review Focus

1. **Cross-user Owner scope:** Owner oversight/control must not accidentally use a self-only User route when an installation-wide Owner route exists; tests must prove the intended scope without impersonating a User.
2. **Stale/unavailable authority:** every operational screen must disable dependent mutations and show `STALE`, `UNKNOWN`, or `UNAVAILABLE` instead of inferring success.
3. **Step-up route/resource binding:** every newly classified destructive route must exist, match the exact frontend path, bind the correct resource, and reject missing/reused grants.
4. **Secret handling:** provider/connection credentials must never be returned to or re-rendered by Owner UI after submission; tests must assert redaction/non-echo.
5. **Live/broker reachability:** no new Owner client or backend route may call broker mutation, Live ARM, or bypass RiskGate; static guards and route tests must prove this after every slice.

---

## File Structure / Responsibilities

### Existing canonical files to modify

- `dashboard/owner-dashboard/OwnerDashboardApp.tsx` — navigation and canonical screen routing only.
- `dashboard/owner-dashboard/authoritative/api.ts` — shared authenticated Owner fetch + step-up primitive; keep governance/AI functions that already belong here.
- `dashboard/owner-dashboard/authoritative/mutations.ts` — existing governance/security/settings mutations.
- `dashboard/owner-dashboard/authoritative/screens.tsx` — retain current governance/security/settings screens; move new large operational surfaces into focused files instead of enlarging this file further.
- `dashboard/backend/api.py` — only narrow route wiring where existing service authority already exists.
- `dashboard/backend/owner_admin/step_up.py` — exact destructive-route classification only.
- `dashboard/backend/owner_admin/router.py` — Owner authority summary/step-up/audit control-plane composition; no engine domain logic.
- `tests_v1/test_owner_user_wiring_contract.py` — extend route-to-UI wiring checks.
- `tests_v1/test_owner_admin_step_up_policy.py` — exact new step-up route expectations.

### New focused Owner client modules

- `dashboard/owner-dashboard/authoritative/researchOps.ts` — Backtest + Walk-Forward typed reads/commands.
- `dashboard/owner-dashboard/authoritative/paperOps.ts` — Paper session typed reads/commands and Owner HOLD/release-HOLD.
- `dashboard/owner-dashboard/authoritative/deploymentOps.ts` — deployment reads/commands for allowed non-real-money modes.
- `dashboard/owner-dashboard/authoritative/dataOps.ts` — historical providers/sync/gaps/dataset operations.
- `dashboard/owner-dashboard/authoritative/safetyOps.ts` — Safe Mode/global hold/risk/kill-switch truth projection and safety-increasing commands only.
- `dashboard/owner-dashboard/authoritative/systemOps.ts` — product/system/backup/restore/rollback supported operations.

### New focused Owner screen modules

- `dashboard/owner-dashboard/authoritative/ResearchOperations.tsx`
- `dashboard/owner-dashboard/authoritative/PaperOperations.tsx`
- `dashboard/owner-dashboard/authoritative/DeploymentOperations.tsx`
- `dashboard/owner-dashboard/authoritative/DataOperations.tsx`
- `dashboard/owner-dashboard/authoritative/RiskSafetyScreen.tsx`
- `dashboard/owner-dashboard/authoritative/SystemOperations.tsx`

### New backend support only where required

- `dashboard/backend/owner_safety_adapter.py` — bounded read/command adapter over canonical safety sources; no direct broker/Live mutation and no disable-kill-switch command.
- Add narrow functions to existing product-ops service/router seams rather than creating a second product-ops authority.

### New tests

- `tests_v1/test_owner_full_control_contract.py` — canonical Owner API-path inventory, authority/state contract, forbidden Live/broker reachability.
- `tests_v1/test_owner_research_operations.py`
- `tests_v1/test_owner_paper_operations.py`
- `tests_v1/test_owner_deployment_operations.py`
- `tests_v1/test_owner_data_operations.py`
- `tests_v1/test_owner_safety_operations.py`
- `tests_v1/test_owner_system_operations.py`
- Matching Vitest files beside each new `dashboard/owner-dashboard/authoritative/*.tsx` module.

---

### Task 1: Lock the canonical Owner control inventory and remove false operational truth

**Files:**
- Create: `tests_v1/test_owner_full_control_contract.py`
- Modify: `tests_v1/test_owner_user_wiring_contract.py`
- Modify: `dashboard/owner-dashboard/authoritative/api.ts`
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Test/Create: `dashboard/owner-dashboard/authoritative/OwnerControlTruth.test.ts`
- Modify only if reachable: legacy file containing any hardcoded `Killswitch Status: ARMED & READY` claim; otherwise leave it unreachable and pin that fact in the guard test.

**Interfaces:**
- Consumes: current FastAPI route table and canonical Owner navigation.
- Produces: a test-owned inventory of every canonical Owner API path and an explicit distinction between reachable canonical screens and legacy/dead donor screens.

- [ ] **Step 1: Write failing backend contract tests**

Add tests that assert:
- every static Owner UI path resolves to a real FastAPI route/method;
- canonical Owner read functions use installation-wide Owner routes when those exist (`/api/v1/owner/backtests`, `/api/v1/owner/paper/sessions`, `/api/v1/owner/orders-portfolio`);
- no canonical Owner API path contains broker-order mutation or Live ARM endpoints;
- every route in `owner_admin.step_up.ROUTES` maps to a real backend route.

- [ ] **Step 2: Run the contract tests and capture the RED failures**

Run: `python -m pytest tests_v1/test_owner_full_control_contract.py tests_v1/test_owner_user_wiring_contract.py tests_v1/test_owner_admin_step_up_policy.py -q -p no:cacheprovider`

Expected: FAIL only on current Owner wiring/truth gaps identified by the new tests.

- [ ] **Step 3: Write failing frontend truth tests**

Assert that canonical navigation imports only authoritative screen modules, no canonical operational status is sourced from sample fixtures, and hardcoded kill-switch readiness is absent from reachable canonical surfaces.

Run: `cd dashboard/web; npx vitest run ../owner-dashboard/authoritative/OwnerControlTruth.test.ts`

Expected: RED on any current canonical wiring mismatch.

- [ ] **Step 4: Make the minimum wiring/truth corrections**

Update `queryOwnerBacktests()` and `queryOwnerPaperSessions()` to use the existing Owner-wide read routes. Do not add new behavior beyond the failing inventory tests. If the hardcoded kill-switch claim is only in unreachable legacy code, keep it unreachable and label it `LEGACY_DEAD_SURFACE` in the test inventory instead of editing unrelated donor UI.

- [ ] **Step 5: Re-run backend + frontend tests**

Expected: PASS.

- [ ] **Step 6: Run Owner boundary guard**

Run: `python build/tools/check_owner_admin_boundary.py`

Expected: PASS.

- [ ] **Step 7: Commit**

Commit message: `test: lock Owner control-plane truth and route inventory`

---

### Task 2: Complete existing governance controls before adding new operations

**Files:**
- Modify: `dashboard/owner-dashboard/authoritative/screens.tsx`
- Modify: `dashboard/owner-dashboard/authoritative/api.ts`
- Modify: `dashboard/owner-dashboard/authoritative/mutations.ts`
- Modify: `dashboard/backend/owner_admin/step_up.py` only if an already-existing destructive route is not classified.
- Test: `tests_v1/test_owner_full_control_contract.py`
- Test/Create: `dashboard/owner-dashboard/authoritative/GovernanceControls.test.tsx`

**Interfaces:**
- Consumes: existing Owner account/strategy/connection/dataset/security routes.
- Produces: complete UI access to existing safe governance actions without adding domain logic.

- [ ] **Step 1: Add failing tests for missing existing governance actions**

Cover: service-term variants already supported by `ownerAccountAction`, strategy visibility/promote controls, strategy assignment listing/assign/revoke where existing backend routes support them, connection capability allowance, dataset HOLD/APPROVE/REJECT plus retire/replace only when backend already supports those routes.

- [ ] **Step 2: Verify RED**

Run focused pytest + Vitest tests.

- [ ] **Step 3: Add typed client functions and screen controls**

Reuse existing route semantics. No new route is allowed in this task unless the service and backend route already exist but the typed client wrapper is missing.

- [ ] **Step 4: Verify destructive controls request step-up and refresh authority after success**

Tests must assert `ownerMutationWithStepUp()` for classified operations and re-read after completion.

- [ ] **Step 5: Run focused tests + Owner boundary guard**

Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: complete Owner governance controls`

---

### Task 3: Backtest and Walk-Forward / OOS operations

**Files:**
- Create: `dashboard/owner-dashboard/authoritative/researchOps.ts`
- Create: `dashboard/owner-dashboard/authoritative/ResearchOperations.tsx`
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Modify: `dashboard/backend/api.py` only for missing narrow Owner-scoped admin commands; reuse existing `/api/v1/backtests*`, `/api/v1/owner/backtests`, `/api/v1/walkforward/jobs*` first.
- Modify: `dashboard/backend/owner_admin/step_up.py` only for cross-user cancel/admin commands introduced here.
- Create: `tests_v1/test_owner_research_operations.py`
- Create: `dashboard/owner-dashboard/authoritative/ResearchOperations.test.tsx`

**Interfaces:**
- Produces frontend functions:
  - `listOwnerBacktests(): Promise<...>`
  - `runOwnerBacktest(input: OwnerBacktestRequest): Promise<...>`
  - `cancelOwnerBacktest(runId: string): Promise<...>`
  - `listOwnerWalkForwardJobs(): Promise<...>`
  - `createOwnerWalkForwardJob(input: OwnerWalkForwardRequest): Promise<...>`
  - `cancelOwnerWalkForwardJob(jobId: string): Promise<...>`
- Owner-created research runs are Owner-owned; cross-user administrative cancellation must use an explicit Owner contract, not User impersonation.

- [ ] **Step 1: Write backend RED tests**

Assert Owner can list installation-wide runs, create an Owner-owned Backtest/Walk-Forward job, inspect evidence, and administratively cancel only through a real audited Owner authority. Assert non-Owner calls are rejected and cancellation cannot change Live state.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests_v1/test_owner_research_operations.py -q -p no:cacheprovider`

- [ ] **Step 3: Implement minimal backend Owner adapters only where route gaps exist**

Use existing Backtest/Walk-Forward services; do not duplicate execution or validation logic.

- [ ] **Step 4: Write frontend RED tests**

Assert create forms, run list, cancel action, loading/unavailable states, backend rejection display, and authoritative refresh.

- [ ] **Step 5: Implement `researchOps.ts` + `ResearchOperations.tsx` and navigation**

Split Backtests and Walk-Forward/OOS into one research operations surface with separate panels/tabs.

- [ ] **Step 6: Verify focused backend/frontend tests**

Expected: PASS.

- [ ] **Step 7: Run promotion/fail-closed tests and guards**

Run existing WFO/OOS/promotion tests plus Owner/Admin, AI, portfolio/risk, and Live guards.

- [ ] **Step 8: Commit**

Commit message: `feat: add Owner research operations`

---

### Task 4: Paper session operations and Owner HOLD/release-HOLD

**Files:**
- Create: `dashboard/owner-dashboard/authoritative/paperOps.ts`
- Create: `dashboard/owner-dashboard/authoritative/PaperOperations.tsx`
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Modify: `dashboard/backend/api.py`
- Modify: `dashboard/backend/owner_admin/step_up.py`
- Create: `tests_v1/test_owner_paper_operations.py`
- Create: `dashboard/owner-dashboard/authoritative/PaperOperations.test.tsx`

**Interfaces:**
- Produces:
  - `listOwnerPaperSessions()` using `/api/v1/owner/paper/sessions`
  - Owner-owned create/start/stop wrappers using canonical Paper service routes
  - `engageOwnerPaperHold(sessionId, reason)`
  - `releaseOwnerPaperHold(sessionId, reason)` through a distinct high-assurance Owner route
  - reads for positions/orders/events/feed state.

- [ ] **Step 1: Write RED tests for Owner Paper control**

Prove create/start/stop works only through Simulated Paper authority; Owner can inspect all sessions; HOLD can be engaged; release-HOLD requires fresh step-up; no Paper command reaches a real broker.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Harden HOLD API semantics**

Keep the existing Owner HOLD capability for increasing restriction. Add a distinct release-HOLD command if needed so backend policy can enforce fresh step-up specifically for reducing restriction. Do not add a kill-switch-disable path.

- [ ] **Step 4: Add exact step-up classification and policy tests**

Add the real release-HOLD route to `ROUTES` with resource binding. Assert missing/reused/wrong-resource grants fail.

- [ ] **Step 5: Write frontend RED tests and implement Paper UI**

Include create/start/stop/detail/positions/orders/events, HOLD state, release confirmation, unavailable state, and post-mutation refresh.

- [ ] **Step 6: Run Paper/Owner/full safety focused tests**

Expected: PASS.

- [ ] **Step 7: Commit**

Commit message: `feat: add Owner Paper operations and protected hold release`

---

### Task 5: Deployment operations for safe non-real-money modes

**Files:**
- Create: `dashboard/owner-dashboard/authoritative/deploymentOps.ts`
- Create: `dashboard/owner-dashboard/authoritative/DeploymentOperations.tsx`
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Modify: `dashboard/backend/api.py` only for narrow Owner oversight/control routes over existing `DeploymentService`.
- Modify: `dashboard/backend/owner_admin/step_up.py` for cross-user administrative stop if classified high-impact.
- Create: `tests_v1/test_owner_deployment_operations.py`
- Create: `dashboard/owner-dashboard/authoritative/DeploymentOperations.test.tsx`

**Interfaces:**
- Backend service authority: existing `DeploymentService.list_deployments(user_id: str | None, ...)` and existing pause/resume/stop/recovery methods.
- Owner UI may create only modes already permitted by backend policy; it must not convert or arm Live.

- [ ] **Step 1: Write RED backend tests**

Assert Owner-wide listing uses `user_id=None`; create/pause/resume/stop/recovery are audited and bounded; `LIVE` arming or broker mutation remains rejected.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Add minimal Owner deployment routes if missing**

Route handlers call `DeploymentService`; no deployment logic belongs in `api.py`.

- [ ] **Step 4: Write RED frontend tests**

Assert mode labels, blocked reasons, create/pause/resume/stop controls, recovery status, and unavailable handling.

- [ ] **Step 5: Implement client + screen + navigation**

- [ ] **Step 6: Run focused tests and Live architecture guard**

Expected: PASS with `READ_ONLY / DISARMED` unchanged.

- [ ] **Step 7: Commit**

Commit message: `feat: add safe Owner deployment operations`

---

### Task 6: Historical providers, sync, gap repair, and dataset operations

**Files:**
- Create: `dashboard/owner-dashboard/authoritative/dataOps.ts`
- Create: `dashboard/owner-dashboard/authoritative/DataOperations.tsx`
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Modify: `dashboard/owner-dashboard/authoritative/mutations.ts` for dataset retire/replace wrappers.
- Modify: `dashboard/backend/owner_admin/step_up.py` only where existing high-impact routes need exact classification.
- Create: `tests_v1/test_owner_data_operations.py`
- Create: `dashboard/owner-dashboard/authoritative/DataOperations.test.tsx`

**Interfaces:**
- Reuse existing `/api/v1/owner/historical/providers*`, `/sync/manual`, `/sync/schedule`, `/sync/jobs*`, `/gaps/repair`, and dataset approval/retire/replace routes.

- [ ] **Step 1: Write RED tests for provider/sync/dataset controls**

Assert configure/toggle, manual sync, schedule read/write, job list/detail, gap repair, approval, retire/replace, and failure states.

- [ ] **Step 2: Add secret non-echo tests**

Provider credential/API-key submission responses and Owner reads must not expose raw secret values.

- [ ] **Step 3: Verify RED**

- [ ] **Step 4: Implement typed client + Owner Data Operations UI**

Keep credentials write-only or opaque-reference-based. Show provider state, dataset hash/date range/readiness, sync progress, and gap status.

- [ ] **Step 5: Run focused tests + data/Owner boundary guards**

Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: centralize Owner data operations`

---

### Task 7: Truthful Risk & Safety Center

**Files:**
- Create: `dashboard/backend/owner_safety_adapter.py`
- Modify: `dashboard/backend/api.py` or `dashboard/backend/owner_admin/router.py` only to attach/read this adapter through a narrow Owner API.
- Create: `dashboard/owner-dashboard/authoritative/safetyOps.ts`
- Create: `dashboard/owner-dashboard/authoritative/RiskSafetyScreen.tsx`
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Modify: `dashboard/backend/owner_admin/step_up.py` only for safety-release operations that already have a canonical safe release contract.
- Create: `tests_v1/test_owner_safety_operations.py`
- Create: `dashboard/owner-dashboard/authoritative/RiskSafetyScreen.test.tsx`

**Interfaces:**
- Read model returns explicit authority states for Safe Mode, global hold, RiskGate/risk snapshot availability, Live state, broker mutation state, and kill-switch state.
- Kill-switch state values must distinguish at least `ACTIVE`, `CLEAR`, `UNAVAILABLE/NOT_CONNECTED`; no default may imply readiness.
- Commands may increase restriction (Safe Mode/global hold/kill-switch engage) only when a canonical backend authority exists.
- No kill-switch-disable command is produced.

- [ ] **Step 1: Write RED safety truth tests**

Assert missing source => `UNAVAILABLE/NOT_CONNECTED`, never `ARMED & READY`; Live remains `READ_ONLY/DISARMED`; broker mutation remains absent; risk-limit values are shown only if backend-authoritative.

- [ ] **Step 2: Write RED command-boundary tests**

Assert safety-increasing commands are Owner-only/audited. Any safety release route must require fresh step-up. Assert no route/client symbol offers `disableKillSwitch`, Live ARM, place/modify/cancel real order.

- [ ] **Step 3: Implement the bounded safety adapter**

Adapter reads canonical app/runtime authorities already attached to the backend. If a canonical kill-switch bridge is not available, report `UNAVAILABLE`; do not directly instantiate or bypass engine authority merely to make the UI green.

- [ ] **Step 4: Implement Risk & Safety UI**

Use authority badges and explicit unavailable states. Safe Mode/global hold controls must re-read state after success.

- [ ] **Step 5: Run Phase-2 safety spine, RiskGate, Owner/Admin, and Live guards**

Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: add truthful Owner risk and safety center`

---

### Task 8: Product/System operations without exposing an OS console

**Files:**
- Create: `dashboard/owner-dashboard/authoritative/systemOps.ts`
- Create: `dashboard/owner-dashboard/authoritative/SystemOperations.tsx`
- Modify: `dashboard/owner-dashboard/authoritative/ProductOperationsScreen.tsx`
- Modify: `dashboard/owner-dashboard/data/productOps.ts` or replace its fetches with canonical `ownerFetch` wrappers without changing its DTO meaning.
- Modify: existing `dashboard/backend/product_ops_v2/**` files only where a tested safe command already belongs in that service.
- Modify: `dashboard/backend/api.py` only for narrow command wiring.
- Modify: `dashboard/backend/owner_admin/step_up.py` for destructive restore/rollback commands.
- Create: `tests_v1/test_owner_system_operations.py`
- Create: `dashboard/owner-dashboard/authoritative/SystemOperations.test.tsx`

**Interfaces:**
- Read: health, persistence, audit, backup, restore, rollback, runbook/evidence, privacy/product-op queues.
- Commands: only bounded backup/restore/rollback drills actually supported by product-ops services.
- Explicitly no arbitrary path input, shell command, PowerShell/cmd, service-manager, or generic process control.

- [ ] **Step 1: Write RED backend tests**

Assert Owner-only operation, explicit confirmation/idempotency where supported, step-up on restore/rollback, audit evidence, path redaction, and failure without authoritative product-ops service.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Add minimal safe command seams to product-ops service/router**

If a requested operation does not have a safe canonical product-ops implementation, leave it `UNAVAILABLE` and document the gap instead of adding shell/file execution.

- [ ] **Step 4: Write RED frontend tests and implement System Operations UI**

Display current operation state/evidence and explicit confirmation for supported commands.

- [ ] **Step 5: Run Phase-9 product-ops tests + Owner boundary guards**

Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: add safe Owner system operations`

---

### Task 9: Navigation, cross-surface links, authority-state consistency, and mobile parity

**Files:**
- Modify: `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- Modify: new focused screen modules from Tasks 3–8.
- Modify: `dashboard/owner-dashboard/owner-dashboard.css` only for required layout/state styles.
- Create/Modify: Owner Dashboard navigation/smoke Vitest tests.

**Interfaces:**
- Final navigation:
  - CONTROL: Overview, Users & Access, Strategies, Connections & Data
  - RESEARCH & OPERATIONS: Backtests/Walk-Forward, Paper Trading, Deployments, Portfolio & Orders, Reports & Audit
  - SAFETY & INTELLIGENCE: Risk & Safety, AI Control Center
  - SYSTEM: Product Operations, System Health, Security Authority, Security Incidents, Settings

- [ ] **Step 1: Write navigation/mobile RED tests**

Assert all canonical controls are reachable on desktop and through the mobile `More` drawer, and no duplicate authority screen is mounted.

- [ ] **Step 2: Add cross-links**

From User/strategy/session/deployment rows, navigate to related Owner surfaces by stable IDs without changing backend authority.

- [ ] **Step 3: Normalize authority-state UX**

All new surfaces use the same semantics for `LOADING`, `AVAILABLE`, `STALE`, `UNKNOWN`, and `UNAVAILABLE`; dependent actions are disabled unless authority is adequate.

- [ ] **Step 4: Run complete frontend test suite + typecheck + build**

Run:
- `cd dashboard/web`
- `npm ci`
- `npx vitest run`
- `npx tsc --noEmit`
- `npm run build`

Expected: all PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: complete Owner control-center navigation and authority UX`

---

### Task 10: Full Windows qualification, browser smoke, and merge gate

**Files:**
- Create: `docs/qualification/OWNER_FULL_CONTROL_PLANE_2026-10-05.md`
- No product-code changes are allowed during this task unless a failing test identifies a defect inside the approved scope; any such fix must get its own RED/GREEN cycle and commit.

**Interfaces:**
- Produces the merge evidence packet; no new runtime authority.

- [ ] **Step 1: Record clean baseline/branch diff and forbidden-path scan**

Confirm no unintended edits under `engine/live/**`, `engine/risk/**`, `engine/orders/**`, `engine/execution/**`, or `engine/broker_adapters/**` unless a separately approved safety-adapter change was explicitly required by Task 7. Any such engine change is a stop/review point, not an automatic continuation.

- [ ] **Step 2: Run full Python suite on Windows / Python 3.13.14**

Run: `python -m pytest tests_v1 -q -p no:cacheprovider`

Expected: 0 failures and no regression from the pre-implementation baseline.

- [ ] **Step 3: Run required guards**

Run at minimum:
- `python build/tools/check_ai_decision_intelligence_boundary.py`
- `python build/tools/check_ai_import_allowlist.py`
- `python build/tools/check_phase8_ai_shadow.py`
- `python build/tools/check_owner_admin_boundary.py`
- `python build/tools/check_phase7_portfolio_risk.py`
- `python build/tools/check_s2_account_gate.py`
- `python build/tools/check_phase2_safety_spine.py`
- existing Live read-only/architecture guards used by the current repository qualification workflow.

Expected: all PASS.

- [ ] **Step 4: Run complete frontend suite/typecheck/build**

Expected: all PASS.

- [ ] **Step 5: Run browser smoke against the actual current app**

Cover desktop and mobile Owner navigation plus representative states:
- authority available
- authority unavailable
- normal mutation success
- backend rejection
- step-up required/success/rejection
- Backtest create/cancel
- Walk-Forward create/cancel
- Paper create/start/stop/HOLD/release-HOLD
- Deployment pause/resume/stop
- provider/sync operation
- Risk & Safety status
- supported Product/System operation
- confirm `LIVE READ_ONLY / DISARMED` everywhere.

- [ ] **Step 6: Generate route/control proof**

Report every canonical Owner UI API path and its backend route/method, all destructive step-up mappings, and all unavailable/not-connected capabilities. Confirm no reachable canonical screen uses unlabeled sample/mock operational truth.

- [ ] **Step 7: Write qualification report**

`docs/qualification/OWNER_FULL_CONTROL_PLANE_2026-10-05.md` must include baseline commit, final commit, test counts, guard results, frontend results, browser smoke evidence, files changed, remaining unavailable controls, and explicit `LIVE READ_ONLY / DISARMED` proof.

- [ ] **Step 8: Whole-branch review before merge**

Review specifically for authority duplication, User impersonation, secret leakage, missing step-up, missing audit, stale-state optimism, direct engine/broker imports, and accidental Live enablement.

- [ ] **Step 9: Merge only after Owner-approved verification**

Do not merge a partially green slice or hide an unavailable capability. The final branch is mergeable only when every implemented slice is green and the qualification report matches the actual branch state.

---

## Self-Review Result

- **Spec coverage:** Users/Access, Strategies, Backtests, Walk-Forward/OOS, Paper, Deployments, Portfolio/Orders, Connections/Data, Risk/Safety, Settings, Security, AI, Product/System operations, legacy/mock truth policy, audit, step-up, error states, mobile parity, and verification are all mapped to tasks.
- **No authority duplication:** every task reuses an existing service first; any new backend code is a narrow adapter/route only.
- **Type consistency:** new client modules are domain-focused and share existing `ownerFetch` / `ownerMutationWithStepUp`; no competing fetch/step-up mechanism is introduced.
- **Review Focus coverage:** cross-user scope (Tasks 1,3–5), stale/unavailable (Tasks 1,9), step-up binding (Tasks 2,4,7,8), secret non-echo (Task 6), Live/broker reachability (Tasks 1,3–8,10).
- **Proportion:** the plan specifies boundaries, interfaces, test names, and verification gates without embedding implementation bodies.
