# Owner/Admin Authoritative Reunion Design

Date: 2026-09-29
Branch: `owner-admin-authoritative-reunion-20260929`
Base checkpoint: `f7e05888d67562bccffd7e9734a03431fa2a0c67`

## Purpose

Preserve the mature manually-built V1 Owner/Admin UX and workflows while replacing prototype/sample/localStorage authority with current AlgoFortis V2 backend authority. The Owner surface remains a governance/oversight client. It must never become a second trading, RiskGate, broker-mutation, Paper, recovery-resume, or promotion authority.

The Normal User Dashboard checkpoint is frozen and out of scope except for shared read-only primitives that are explicitly reusable without changing user behavior.

## Selected approach

**Option A: V1 Owner UX + V2 authoritative backend reunion.**

- Keep useful Owner/Admin screens and interaction patterns.
- Replace production-path sample/prototype state with explicit backend read models/services.
- Preserve fail-closed behavior: missing evidence is `UNAVAILABLE`, `UNKNOWN`, or `STALE`, never zero/healthy/safe by inference.
- Keep Live `READ_ONLY / DISARMED`.
- Broker connected does not imply Live armed.
- RiskGateV2 remains the sole executable-order authority.

## Mandatory implementation order

The following order is fixed and must be completed before broader Owner/Admin surface wiring:

1. **Permanent Admin boundary guard**
2. **Step-up authentication for destructive/security-sensitive Owner actions**
3. **Existing audit ledger / FailureIncident reuse for security-relevant Owner actions**
4. **Clear visual truth for `UNAVAILABLE / STALE / UNKNOWN / AVAILABLE`**
5. **Owner/Admin authoritative wiring by surface**
6. **Qualification record and frozen checkpoint**

No later stage may weaken an earlier stage.

---

## 1. Permanent Admin boundary guard

Create an executable static safety check, expected path:

`checks/check_owner_admin_boundary.py`

The exact path may follow existing repository check conventions, but the check must be runnable in CI and locally.

### The guard must fail if canonical Owner/Admin production code introduces any direct or indirect obvious reference to:

- broker `place_order`, `modify_order`, `cancel_order` paths;
- direct Live broker mutation endpoints;
- `_mint_approved_order()`;
- legacy `engine.broker_adapters` mutation authority;
- a second/legacy RiskGate approval path;
- direct recovery resume/arming authority;
- sample/prototype/localStorage modules as canonical production truth;
- silent fake-success mutation helpers.

### The guard must pin these invariants

- Owner/Admin UI is governance/oversight only.
- Live remains `READ_ONLY / DISARMED`.
- Broker connection does not arm Live.
- RiskGateV2 remains the sole executable-order authority.
- Paper and Live remain isolated.
- Sample/demo modules may exist only behind explicit preview/dev-only paths and must not be imported by canonical production Owner routes.

This is not documentation-only. It must be an executable regression boundary.

---

## 2. Step-up authentication for destructive Owner actions

Destructive or security-sensitive Owner actions affect another user's access or system trust and therefore require fresh step-up authentication.

### Step-up-required action families

At minimum:

- suspend account;
- restore/re-enable account where policy classifies it as risk-increasing;
- revoke account/access;
- revoke activation/access token;
- reissue activation where it changes trust/access state;
- entitlement extend/renew/lifetime conversion where it changes service authority;
- session revoke / revoke-all sessions;
- device revoke / revoke-all devices;
- security posture changes;
- strategy suspension/restoration/administrative allowance changes when they alter deployability;
- connection/capability administrative allowance changes;
- any future Owner action classified by policy as risk-increasing or trust-changing.

### Step-up behavior

- The UI may request the action, but the backend is the authority deciding whether step-up is required and whether the proof is fresh/valid.
- No localStorage-only or UI-only confirmation may satisfy step-up.
- A stale/expired/missing step-up proof fails closed with no mutation.
- The Owner receives a clear reason and may retry after completing step-up.
- Step-up state must not silently persist beyond the server-defined freshness window.
- Existing S2 account/device/session gating semantics are reused rather than inventing a new authentication system.

---

## 3. Existing audit ledger / FailureIncident reuse

Do not create a separate hidden Admin-only logging subsystem.

Security-relevant and destructive Owner actions must flow through the existing audit/evidence model. Where an action represents a failure, policy breach, rejected trust transition, or security incident, reuse/extend the existing `FailureIncident` pattern rather than creating a parallel incident table.

### Audit requirements

Each relevant action must preserve, where available and policy-safe:

- actor / Owner identity;
- target user/account/strategy/connection identifier;
- action family;
- request time;
- authoritative result (`APPLIED`, `REJECTED`, `FAILED`, etc.);
- reason / policy code;
- step-up requirement and verification result without logging secret proof material;
- correlation/request id;
- before/after high-level state where safe and necessary;
- immutable audit linkage/evidence reference.

### Failures

- Audit write failure must never be converted into fake action success.
- If policy requires audit persistence before mutation, mutation fails closed when audit persistence cannot be guaranteed.
- No plaintext credentials, passwords, activation secrets, recovery secrets, or step-up proof material may be logged.

---

## 4. Visual authority truth

Owner/Admin screens must use the same four-state authority model:

- `AVAILABLE`
- `STALE`
- `UNKNOWN`
- `UNAVAILABLE`

### UI rules

- `UNAVAILABLE` must be visually unmistakable from `0`, empty-but-valid, healthy, or safe.
- `STALE` must remain visible as stale and must not be promoted to available.
- `UNKNOWN` must never be converted to a guessed status.
- An authoritative empty dataset may render `0` only when the source itself is `AVAILABLE` and explicitly returned an empty valid set.
- Missing authority must not render `0 users`, `0 risks`, `0 incidents`, `healthy`, `safe`, `PASS`, or equivalent positive inference.
- Owner Overview summary cards must show warning/error/disabled presentation for unavailable authority rather than neutral empty values.
- Shared badges/messages should be reusable across Owner screens so state meaning stays consistent.

---

## 5. Owner/Admin surfaces to reunite

### 5.1 Owner Overview

Preserve the current overview UX, but remove canonical `sampleData`/prototype fallbacks.

Authoritative summaries:

- Users/Access Registry
- Strategy governance
- Connections/data providers
- System/persistence health
- Security posture
- attention items

Hard-coded claims such as `AUTHORITATIVE RUNTIME · RELEASE CANDIDATE` must be derived from actual authority or replaced with neutral product identity text.

### 5.2 Users Oversight + User Inspection

Preserve the mature inspection workflow, including the existing conceptual tabs:

- Profile
- Strategies
- Backtests
- Paper
- Portfolio
- Orders
- Connections
- Reports
- Sessions
- Security State

Each tab must read from current backend authority. Missing per-user authority renders unavailable/unknown, never sample rows.

Owner inspection remains read-only except for separately authorized administrative actions subject to step-up and audit requirements.

### 5.3 Access Registry

Use backend authority for:

- create access;
- activation/reissue/revoke;
- account suspend/restore/revoke;
- entitlement lifecycle;
- service term changes.

Prototype-generated identifiers/codes may remain only in explicit preview/dev fixtures and cannot become production truth.

### 5.4 Strategy Governance

Preserve the Owner strategy UX but use current registry/readiness/promotion APIs.

Owner administrative allowance may further restrict a strategy but cannot override a failed system/readiness gate.

Promotion success may be shown only after authoritative persisted confirmation/re-read as required by current contracts.

No Owner action bypasses RiskGateV2 or creates executable orders.

### 5.5 Connections / Datasets / Plugins

Use authoritative connection, capability, historical-data, and dataset status.

Remove simulated verification, simulated gap repair, and sample fallback from canonical production mode.

Missing backend action endpoint means the action is unavailable, not simulated.

Legacy broker mutation adapters are not imported into Owner UI.

### 5.6 Backtest + Paper Oversight

Backtest uses current deterministic V2 backtest/research authority.

Paper uses current Paper engine only.

No duplicate V1 Paper engine or local prototype ledger may become runtime authority.

Administrative holds are allowed only through current backend governance contracts.

### 5.7 Portfolio & Orders

Preserve the existing canonical runtime view where already authoritative.

Preview/sample version remains explicitly preview-only.

Owner view is oversight/read-side and cannot place/modify/cancel real broker orders.

### 5.8 Reports & Audit

Use current backend report and immutable audit authorities.

Simulated report-generation success is removed from production mode.

Report generation, if supported, must be backend-authoritative and may show success only after persisted evidence is available.

### 5.9 Security + System + Settings

Preserve current strong backend wiring for sessions, devices, security state, system/persistence health, and server settings.

Retain the safe setting transition:

`PROPOSE -> CONFIRM -> APPLY -> VERIFY`

Security/session/device destructive actions are step-up gated and audited.

---

## Shared Owner authority layer

Introduce or consolidate a thin read-only Owner authority layer analogous to the finished user-side pattern.

It may expose:

- owner shell/system status;
- security posture;
- recovery/manual-resume status;
- broker/data health;
- audit/report health;
- attention-center notifications;
- per-surface authority state.

This layer is a presentation/read-model adapter only. It does not become trading authority.

---

## Data and provenance rules

- Production Owner screens consume backend/source-tagged results.
- `SAMPLE_FALLBACK`, fixture storage, prototype localStorage, and simulation helpers are not authoritative production sources.
- Explicit preview/dev-only modes may retain fixtures, visually labeled `SAMPLE`/`PREVIEW`, isolated from canonical production routes.
- Secrets remain sealed and never rendered.
- Secret references may be shown only in redacted/opaque form.

---

## Compatibility and preservation

Preserve valuable V1 Owner UX and workflows rather than rewriting them.

Do not transplant:

- legacy RiskGate authority;
- old broker mutation paths;
- duplicate Paper engine;
- old local-only identity authority as current roaming identity;
- fake/sample success paths;
- duplicate stores;
- generated build artifacts/caches.

Current V2 contracts win on conflicts.

---

## Testing and qualification

Implementation must add tests while work proceeds, but until an executable runner successfully performs the commands, status remains:

`IMPLEMENTED / EXECUTION VERIFICATION PENDING`

Never claim GREEN from source inspection alone.

### Required verification families

- `check_owner_admin_boundary.py` static guard;
- Owner authority-state tests (`AVAILABLE/STALE/UNKNOWN/UNAVAILABLE`);
- step-up-required destructive-action tests;
- step-up expiry/missing/rejected tests;
- audit/FailureIncident linkage tests;
- no-secret-in-audit tests;
- Owner overview no-fake-zero tests;
- sample/prototype isolation tests;
- user-side regression tests to prove frozen user behavior remains intact;
- TypeScript typecheck;
- frontend unit tests;
- production build;
- relevant Python regression suite;
- existing Live READ_ONLY/DISARMED and RiskGate authority checks;
- existing Paper/recovery and broker read-only qualification where available.

When hosted quota/runner availability returns, execute the combined qualification rather than treating deferred execution as success.

---

## Completion criteria

Owner/Admin reunion is implementation-complete only when:

1. Boundary guard exists and covers canonical Owner routes.
2. Canonical production Owner screens no longer rely on sample/prototype/localStorage truth.
3. Destructive/security-sensitive actions require backend-authoritative step-up.
4. Relevant actions write to the existing audit/evidence model and FailureIncident where applicable.
5. All Owner surfaces preserve four-state authority truth without fake zero/healthy inference.
6. User-side frozen behavior remains unchanged.
7. Live remains `READ_ONLY / DISARMED` and no Owner UI direct broker mutation authority exists.
8. Qualification record documents exact executed evidence and pending items.
9. A dedicated frozen Owner/Admin checkpoint branch is created at the exact final SHA.

Full `100% VERIFIED COMPLETE` status additionally requires fresh executable test/typecheck/build/qualification evidence with zero unexplained failures.

## Out of scope

- Real-money Live broker execution enablement.
- Laya/AI authority changes.
- New Owner visual redesign unrelated to authority/wiring.
- Cloud/commercial account platform expansion beyond existing contracts.
- Rewriting the mature V1 Owner UX from scratch.
