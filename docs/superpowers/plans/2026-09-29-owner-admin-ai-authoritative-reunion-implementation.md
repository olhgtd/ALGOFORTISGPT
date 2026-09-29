# Owner/Admin + AI Authoritative Reunion Implementation Plan

> **Execution:** implement in this branch using the approved design, test-first where executable, and preserve all current safety invariants.

**Goal:** Replace canonical Owner/Admin sample/prototype authority with explicit backend authority, add fresh step-up + auditable mutation boundaries, add four-state authority truth, and build a real Owner AI Control Center for Prime/Laya/Research/Risk Challenger without granting AI or Admin any broker/order/Live-arm authority.

**Branch:** `owner-admin-authoritative-reunion-20260929`

**Spec:** `docs/superpowers/specs/2026-09-29-owner-admin-authoritative-reunion-design.md`

**Frozen AI ADR:** `docs/v2/adr/ADR-017-laya-market-intelligence-role.md`

## Global constraints

- Normal User Dashboard checkpoint stays frozen.
- Live stays `READ_ONLY / DISARMED`.
- Broker connection never implies Live armed.
- RiskGateV2 remains the sole executable-order authority.
- Owner/Admin is governance/oversight only.
- AI is advisory/research/shadow only.
- Prime owns orchestration and provider/model routing.
- Laya is Market Intelligence only; no `LayaRouter` or Laya-owned provider routing.
- No direct broker `place_order`, `modify_order`, `cancel_order`, Live ARM, recovery-resume, or legacy RiskGate authority from Owner/Admin/AI code.
- Missing authority is `UNKNOWN`, `STALE`, or `UNAVAILABLE`, never guessed zero/healthy/safe/PASS.
- Canonical production Owner/AI paths cannot use `sampleData`, prototype localStorage, or fake-success helpers as authority.
- Explicit preview/dev fixtures may remain isolated and visibly labeled.
- Existing S2/WebAuthn/session security and Core Audit are reused; no parallel auth or hidden Admin audit store.
- Audit-required mutations fail closed if authoritative audit intent cannot be persisted.
- Secrets, passwords, recovery material, provider keys, broker credentials, and step-up proofs are never logged or rendered.
- No main-branch merge is part of implementation unless separately authorized.

---

## Task 1 — Permanent Owner/Admin + AI boundary guard

**Create:**
- `build/tools/check_owner_admin_boundary.py`
- `tests_v1/test_owner_admin_boundary_guard.py`

**Guard scope:** canonical Owner/Admin production files plus `engine/ai/**/*.py` and backend AI-control files.

**Fail on:**
- concrete broker-adapter imports;
- obvious broker mutation capability tokens;
- `_mint_approved_order` / second approval authority;
- Live arming or direct recovery-resume authority;
- canonical `sampleData`/localStorage imports in Owner production entrypoints;
- `LayaRouter` or Laya provider-selection/routing methods;
- AI order/broker mutation authority.

**TDD:**
- RED: test requires the guard and demonstrates forbidden fixture text is rejected.
- GREEN: implement minimum static checker with explicit preview/dev allowlist.
- Run focused test + checker.

**Commit:** `test: enforce owner admin AI authority boundary`

---

## Task 2 — Four-state Owner authority contracts and UI truth

**Create:**
- `dashboard/backend/owner_admin/__init__.py`
- `dashboard/backend/owner_admin/contracts.py`
- `tests_v1/test_owner_admin_contracts.py`
- `dashboard/owner-dashboard/authority.ts`
- `dashboard/owner-dashboard/authority.test.ts`

**Modify:**
- `dashboard/web/vitest.config.ts`
- `dashboard/shared/services/integrationClient.ts`

**Contracts:**
- `AuthorityState = AVAILABLE | STALE | UNKNOWN | UNAVAILABLE`
- immutable/source-tagged authority envelope with `as_of`, optional reason/evidence ref, and payload.
- no trading/arming/order fields.

**UI mapping:**
- backend + fresh -> AVAILABLE;
- backend + stale -> STALE;
- explicit unknown -> UNKNOWN;
- missing/unreachable -> UNAVAILABLE;
- `0` is only valid under AVAILABLE authority.

**TDD:** prove exact status set, immutability/no trading fields, and no-fake-zero display mapping.

**Commit:** `feat: add owner authority truth contracts`

---

## Task 3 — Fresh Owner step-up and audited mutation gateway

**Create:**
- `dashboard/backend/owner_admin/step_up.py`
- `dashboard/backend/owner_admin/mutation_gateway.py`
- `tests_v1/test_owner_admin_step_up.py`
- `tests_v1/test_owner_admin_audit_gateway.py`

**Reuse:**
- `dashboard/backend/security.py` WebAuthn/session authority.
- `dashboard/backend/account_v2/` S2 semantics.
- `dashboard/backend/core_audit.py` / `MandatoryCoreSecurityAudit` and Phase9 mutation protocol.

**Design:**
- Destructive/trust-changing Owner actions require a fresh, server-authoritative step-up grant even when the base login session is otherwise normal.
- A step-up grant is bound to Owner user/session, has an explicit short expiry, cannot be manufactured in localStorage/UI state, and is consumed/validated by backend policy.
- WebAuthn completion is the high-assurance proof source where WebAuthn is configured; approved local-private auth may only use an explicitly policy-approved fresh re-auth flow rather than a UI confirmation.
- The mutation gateway validates Owner role + fresh step-up first, then persists authoritative audit intent, then executes the supplied business mutation.
- Missing/stale/expired/mismatched proof -> reject with zero mutation.
- Required audit failure -> reject with zero mutation.

**Modify after focused tests:**
- `dashboard/backend/api.py` to add step-up issue/complete routes and route destructive Owner operations through the dependency/gateway.
- `dashboard/shared/services/integrationClient.ts` to carry step-up grants for protected mutations.

**Protected families:** account suspend/restore/revoke, activation revoke/reissue, entitlement changes, session/device revoke, security posture, strategy deployability/allowance changes, AI provider/binding/policy changes.

**Commit:** `feat: require audited owner step up for sensitive mutations`

---

## Task 4 — Authoritative Owner read model and no-fake-zero overview

**Create:**
- `dashboard/backend/owner_admin/read_model.py`
- `tests_v1/test_owner_admin_read_model.py`

**Modify:**
- `dashboard/backend/api.py`
- `dashboard/shared/services/integrationClient.ts`
- `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- `dashboard/owner-dashboard/screens/AdminHome.tsx`

**Backend endpoint:** add an Owner control-center summary/read model that composes existing security/access/strategy/connection/persistence/audit authorities without becoming a new domain authority.

**Rules:**
- unavailable adapter/store => UNAVAILABLE/UNKNOWN, never numeric zero;
- authoritative empty set => AVAILABLE with zero permitted;
- hard-coded `AUTHORITATIVE RUNTIME · RELEASE CANDIDATE` is removed/replaced by neutral AlgoFortis identity plus truth-aware authority state.

**TDD:** unavailable sources cannot render/return positive zero/healthy claims; available empty sources can return zero.

**Commit:** `feat: wire authoritative owner overview truth`

---

## Task 5 — Reunite Owner/Admin surfaces with backend authority

**Modify:**
- `dashboard/owner-dashboard/screens/AdminScreens.tsx`
- `dashboard/owner-dashboard/screens/AccessRegistryScreen.tsx`
- related canonical Owner screens/services discovered during implementation.

**Rules:**
- Remove canonical production reliance on `sampleData`, prototype generators and localStorage truth.
- Keep explicit demo/preview-only fixture behavior isolated and labeled.
- User inspection tabs use authoritative reads or visibly UNAVAILABLE/UNKNOWN states.
- Access Registry creation/lifecycle uses backend results only.
- Strategy governance uses current registry/readiness/promotion authority only.
- Connections/datasets missing backend capability means unavailable, never simulated success.
- Backtest/Paper remain current engines; no duplicate V1 engine.
- Portfolio/Orders stay read-side; no Owner place/modify/cancel.
- Reports/Audit show persisted evidence only.
- Security/System/Settings preserve backend authority and `PROPOSE -> CONFIRM -> APPLY -> VERIFY`.

**Tests:** add targeted Owner frontend tests plus Python endpoint/read-model tests; preserve existing `tests_v1/test_area4_ui_integration_readiness.py` behavior unless the stronger truth contract intentionally supersedes an old fake-zero expectation.

**Commit:** `feat: reunite owner surfaces with backend authority`

---

## Task 6 — Authoritative AI research/shadow control plane

**Create engine domain:**
- `engine/ai/__init__.py`
- `engine/ai/contracts.py`
- `engine/ai/provider_registry.py`
- `engine/ai/orchestrator.py`
- `engine/ai/laya.py`
- `engine/ai/research_agent.py`
- `engine/ai/risk_challenger.py`
- `engine/ai/evidence.py`

**Create backend/UI adapter:**
- `dashboard/backend/ai_control.py`
- `dashboard/owner-dashboard/screens/AgentControlCenter.tsx`

**Tests:**
- `tests_v1/test_ai_agent_contracts.py`
- `tests_v1/test_ai_architecture_guard.py`
- `tests_v1/test_ai_orchestrator.py`
- `tests_v1/test_ai_control_api.py`
- `dashboard/owner-dashboard/screens/AgentControlCenter.test.tsx`

**Contracts:**
- Agent roles: PRIME, LAYA_MARKET_INTELLIGENCE, RESEARCH, RISK_CHALLENGER.
- Provider/model registry stores metadata/health/binding policy only; secrets stay behind approved secret-provider seams.
- Prime chooses specialist and provider/model via deterministic routing policy and records routing evidence.
- Laya exposes market-intelligence analysis input/output only; no dispatch/provider-selection methods.
- Research Agent outputs research artifacts/evidence.
- Risk Challenger outputs independent critique; it is explicitly not RiskGateV2.
- Jobs run only in RESEARCH/SHADOW scope in this implementation.
- No AI contract contains broker/order mutation or Live-arm authority.
- Provider/data unavailable/stale fails closed to no-job/no-candidate or explicit unavailable result.
- Job/output provenance/evidence refs are retained.

**Backend API:** Owner can read registry/health/jobs/evidence and can govern research/shadow job state only where backend policy permits. Protected/system responsibilities remain view-only. Security-sensitive provider/binding/governance changes use Task-3 step-up/audit boundary.

**Frontend:** replace Owner route use of sample `AgentsScreen` with canonical `AgentControlCenter` backed only by authoritative API; no local sample pause/resume state.

**Commit:** `feat: add authoritative AI research control plane`

---

## Task 7 — CI qualification, regression and frozen checkpoint

**Create/modify:**
- `.github/workflows/owner-admin-authoritative.yml`
- `docs/qualification/OWNER_ADMIN_AI_REUNION_2026-09-29.md`

**CI:**
- Python compile for changed backend/engine/check/test paths.
- `python build/tools/check_owner_admin_boundary.py`.
- focused Owner/Admin/AI pytest families.
- existing S2 boundary/audit tests.
- existing Live READ_ONLY/DISARMED / broker read-only safety qualification available in the repository.
- frontend install/typecheck/Vitest/build.
- frozen Normal User regression tests.

**Verification rule:** source inspection is not GREEN. `100% VERIFIED COMPLETE` requires a fresh executable workflow/test/build result at the final exact SHA with no unexplained failures.

**Checkpoint:** after fresh GREEN, record exact SHA in qualification doc and create a frozen checkpoint branch/ref without merging to main.

**Commit:** `ci: qualify owner admin AI authoritative reunion`

---

## Completion definition

Implementation is complete only when:

1. permanent boundary guard is executable;
2. protected Owner mutations require fresh backend step-up and authoritative audit;
3. canonical Owner/AI UI uses four-state authority truth and cannot infer zero/healthy from missing authority;
4. canonical Owner production paths are free of sample/prototype authority;
5. Owner surfaces are wired to current backend authorities;
6. Prime/Laya/Research/Risk Challenger control plane exists with ADR-017 boundaries and research/shadow-only behavior;
7. Normal User behavior remains frozen;
8. Live remains READ_ONLY/DISARMED and no new broker mutation path exists;
9. final qualification records exact executed evidence and final SHA;
10. final checkpoint is frozen only after verification.