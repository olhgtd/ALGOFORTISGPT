# AlgoFortis Owner Full Control Plane — Design

Date: 2026-10-05
Status: WRITTEN DESIGN FOR OWNER REVIEW — implementation not started
Base: `main@da9e8f289be675b243f02cca07af0a328837e387`

## 1. Intent

Make the Owner Dashboard the primary operational control center for AlgoFortis so the Owner can perform normal administration, research operations, paper operations, data operations, AI control, security operations, settings, diagnostics, and product operations without repeatedly dropping into backend files, environment variables, or terminal commands.

The dashboard must centralize control without duplicating engine authority or weakening fail-closed safety. The UI remains a client/control surface; domain authority stays in existing backend services, RiskGate, security policy, persistence, and audit systems.

## 2. Non-negotiable safety boundaries

These invariants remain unchanged:

1. Real-money Live remains `READ_ONLY / DISARMED`.
2. The Owner Dashboard must not gain broker order placement, modification, cancellation, or Live ARM authority.
3. RiskGate remains the sole risk decision/order approval authority; the UI cannot bypass it.
4. Kill-switch/emergency safety controls may move toward a truthful Owner control surface, but the UI may never provide a weaker path to disable safety than the canonical runtime policy permits. No kill-switch-disable control is introduced by this design.
5. Destructive Owner mutations require Owner authorization and, where classified as destructive, fresh WebAuthn step-up.
6. Every privileged mutation is auditable with actor, action, target, result, time, and evidence/reference where available.
7. Missing/stale authority must fail closed and must never be rendered as healthy, safe, ready, zero, PASS, or armed.
8. User, Backtest, Paper, Shadow, and Live authorities remain isolated.
9. No secret, private key, bearer token, raw `.env` file, or arbitrary shell execution surface is exposed in the dashboard.
10. Existing security, audit, boundary, CI, and safety guards are preserved or strengthened; none may be weakened to make UI integration easier.

## 3. Current-state finding

The current Owner Dashboard already provides real backend-backed control for important governance areas, including user/access lifecycle, strategy governance, connection/dataset allowance, AI control, session/device revocation, and safe settings proposal/confirmation.

However, several operational areas are oversight-heavy or read-only even though backend services already expose safe actions. This is the main source of Owner dependence on terminal/backend workflows.

A previous audit also identified hardcoded/legacy UI text such as `Killswitch Status: ARMED & READY`. That text must not be treated as runtime truth. The canonical current User Dashboard uses the newer seven-surface app (`Home`, `Markets`, `Strategies`, `Testing & Validation`, `Trades`, `Portfolio`, `Account`); legacy/dead screens must be explicitly separated from reachable production UI during implementation.

## 4. Architecture choice

Use a **central Owner Control Plane adapter** over existing backend authorities.

The Owner Dashboard does not call engine internals directly. Instead:

`Owner UI -> typed Owner API client -> authenticated Owner backend routes -> existing domain/service authority -> audit/persistence`

Rules:

- Reuse existing routes where correct.
- Add narrow Owner-facing routes only where a real backend capability exists but no safe Owner contract exists.
- Do not move domain logic into React components.
- Do not duplicate RiskGate, strategy readiness, paper execution, deployment, historical data, or security logic in UI code.
- Prefer read models for status and explicit command endpoints for mutations.
- All Owner screens must display authority state (`AVAILABLE`, `STALE`, `UNKNOWN`, `UNAVAILABLE`) where relevant.

## 5. Owner navigation / control domains

The Owner Dashboard remains one application but evolves from governance-heavy oversight into a full safe operational control center.

### 5.1 Overview / Control Center

Purpose: one-screen operational summary and emergency awareness.

Must show authoritative status for:

- backend/database/audit health
- User/access health
- strategies/readiness
- data providers/datasets
- Backtest jobs
- Walk-Forward/OOS jobs
- Paper sessions
- deployments
- AI control plane
- security/session/device authority
- backup/restore/rollback status
- Safe Mode/global hold
- Live state (`READ_ONLY / DISARMED`)
- kill-switch/emergency safety truth if a canonical status authority exists

The Overview may link to controls but must not invent independent state.

### 5.2 Users & Access

Keep and consolidate existing real controls:

- create user access
- activation code lifecycle
- reissue/revoke invite
- suspend/restore/revoke account
- extend/modify service entitlement
- inspect account/service status
- view/revoke sessions
- view/revoke devices/authenticators where policy permits
- inspect user-linked strategies/connections/deployments/paper sessions

All destructive account/security changes remain step-up/audited.

### 5.3 Strategies

Owner controls should include:

- inspect registered strategies and versions
- inspect source hash/version metadata/readiness
- strategy allowance/HOLD
- suspend/restore
- visibility/governance controls
- archive/disable where canonical service supports it
- assignment to users where supported
- promotion governance
- inspect promotion requests and evidence
- inspect Backtest/Paper/Live-Paper/Live readiness independently

No Owner action may fabricate readiness or bypass validation. Live readiness remains informational/governed and Live execution remains disarmed.

### 5.4 Backtests

Upgrade current Owner Backtests oversight into an operational control surface using canonical backtest endpoints/services.

Owner capabilities:

- create/run a backtest
- choose strategy/version, dataset, instrument, timeframe, date range, initial capital, and safe policy inputs supported by backend contract
- list runs
- inspect run details
- inspect trades/results/evidence
- cancel cancellable runs
- link results to strategy/readiness evidence where existing authority does so

The Owner UI must not implement its own backtest engine or calculations.

### 5.5 Walk-Forward / OOS

Add Owner control for canonical validation jobs:

- create job
- list jobs
- inspect status/progress/windows/results
- cancel job
- inspect resulting evidence/reports

Promotion remains fail-closed; missing or failed OOS evidence must never become promotable.

### 5.6 Paper Trading

Upgrade Paper Sessions from oversight to safe operation.

Owner capabilities:

- create Paper session
- start session
- stop session
- inspect session detail
- inspect positions
- inspect orders/fills/events
- apply/release Owner Paper HOLD using canonical Owner route
- inspect feed/data-source state
- inspect failure/recovery state

No Paper control may route to a real broker.

### 5.7 Deployments

Centralize safe deployment management for non-real-money operational modes:

- list deployments
- create deployment where canonical backend permits
- inspect runtime/recovery state
- pause
- resume
- stop
- inspect strategy, connection, instrument, mode, risk reference, and block reason

Allowed operational modes must follow existing backend policy. No Owner UI path may transform a Paper/Shadow deployment into armed Live execution.

### 5.8 Portfolio & Orders

Preserve read-only real-broker safety while improving operational inspection.

Owner capabilities:

- inspect aggregated Backtest/Paper/Shadow/LIVE-readiness projections
- inspect Paper order details and execution evidence
- inspect exposure, positions, orders, events, limitations, and reconciliation
- navigate to the owning User/strategy/session/deployment

Explicitly prohibited:

- place real broker order
- modify real broker order
- cancel real broker order
- bypass RiskGate
- arm Live

### 5.9 Connections & Data

Expand current governance surface into full data operations using existing historical-data authority.

Owner controls:

- inspect connections and capabilities
- allow/HOLD connection/capability
- configure supported historical providers through safe credential-reference handling
- enable/disable provider
- manual historical sync
- scheduled sync configuration
- list/inspect sync jobs
- gap detection/repair
- dataset approval/retirement/replacement where supported
- market-data readiness/freshness status
- dataset hashes/date ranges/row counts/readiness

Secrets must be stored/resolved through canonical secure handling. The UI must never echo raw provider secrets after submission.

### 5.10 Risk & Safety Center

Create a truthful safety surface; remove or quarantine any hardcoded safety claims.

Display only backend-authoritative values for:

- Safe Mode
- global execution hold
- RiskGate availability/status projection
- configured risk limits that are safe to expose
- data freshness/risk readiness
- Live state
- broker mutation state
- emergency/kill-switch state if a canonical runtime authority exists

Control policy:

- **Engage safety / increase restriction:** may be exposed when backed by canonical route and audited.
- **Release a non-Live operational hold:** allowed only where a canonical backend contract already permits it and must use the strongest existing authorization/step-up policy.
- **Disable/bypass the canonical kill switch or arm Live:** not part of this design.
- A missing kill-switch backend authority must render `NOT CONNECTED / UNAVAILABLE`, never `ARMED & READY`.

If engine kill-switch code exists without a dashboard-safe backend status contract, implementation may add a narrow **status/engage-only** adapter that preserves engine authority. Do not call engine internals directly from React, and do not introduce a kill-switch-disable route.

### 5.11 Settings

Keep corrected Settings lifecycle:

`READ -> PROPOSE -> fresh step-up -> CONFIRM/APPLY -> re-read`

Initial supported keys remain constrained by backend allowlist. Protected Live/RiskGate keys remain forbidden unless a future separately approved design explicitly changes policy.

Safe Mode should be presented in the Risk & Safety Center, even if its canonical endpoint remains under settings.

### 5.12 Security Authority

Centralize:

- current security authority state
- Owner authenticators/WebAuthn readiness
- sessions
- devices/authenticators
- revocation actions
- security incidents
- recovery posture/evidence
- step-up freshness/result visibility where safe

No private credential material is displayed.

### 5.13 AI Control Center

Preserve and consolidate existing AI Owner controls:

- providers
- models
- agent bindings
- policies
- jobs
- cancel job
- availability/error state

AI remains decision intelligence only and cannot gain broker/RiskGate/Live mutation authority.

### 5.14 Product Operations / System Operations

Convert read-only Product Operations into a useful safe operations surface where backend authority already exists.

Desired controls/status:

- system health
- database/persistence health
- audit health
- backup status
- restore status
- rollback status
- run approved backup operation if canonical backend supports it
- run approved restore/rollback drill only behind explicit confirmation/step-up and only if existing product-ops service supports a safe command
- diagnostics/evidence export where supported
- privacy/product-op queues and policy status

Do not expose arbitrary filesystem paths, shell commands, service-manager control, or unrestricted process execution.

## 6. Environment and local-machine configuration

The goal is to minimize terminal dependence, not to turn the dashboard into an unrestricted OS administration console.

### May be centralized safely

- runtime profile display
- data-root display (redacted/safe representation)
- provider/connection configuration through secure references
- diagnostics
- supported product settings
- backup/restore operations through bounded backend services

### Must remain outside generic UI editing

- arbitrary `ALGOFORTIS_*` environment variables
- raw `.env` editing
- raw bearer/access tokens
- arbitrary file editing
- arbitrary PowerShell/cmd execution
- unrestricted Windows service/process manipulation

If a specific local setting repeatedly requires terminal use, it should receive a dedicated typed backend setting/command contract rather than a generic terminal box.

## 7. Hardcoded/mock/legacy data policy

Implementation must inventory all reachable Owner/User screens and classify every displayed operational fact as one of:

- `BACKEND_AUTHORITY`
- `DERIVED_FROM_BACKEND`
- `STATIC_COPY`
- `DEV_PREVIEW_SAMPLE`
- `LEGACY_DEAD_SURFACE`

Rules:

1. Operational status/limits/readiness may not use unlabeled sample data.
2. Production/canonical routes may not silently fall back to sample authority.
3. Any preview/sample mode must be visually explicit.
4. Legacy/dead files may remain temporarily only if unreachable and covered by a guard; otherwise remove or migrate them.
5. Hardcoded risk/kill-switch claims must be removed or replaced with authoritative projection.

## 8. Authorization and step-up model

Every Owner command is classified before implementation:

### Read-only
Owner session required. No mutation.

### Normal governed mutation
Owner role + mutable session + audit.

### Destructive/high-impact mutation
Owner role + mutable session + fresh WebAuthn step-up + audit.

Examples expected to require step-up include account revoke/suspend, device/session revoke as existing policy dictates, settings apply, release of permitted non-Live holds, destructive dataset operations, restore/rollback operations, and other actions already classified by `owner_admin/step_up.py`.

The step-up policy must reference the real backend route, and automated contract tests must verify every classified route exists.

## 9. Audit contract

Every Owner mutation should emit or map to canonical audit evidence including:

- actor Owner ID
- action family/type
- target type/id
- request correlation/idempotency reference when applicable
- timestamp
- success/rejected/failure outcome
- reason/block code
- evidence reference

UI success text is never considered proof by itself; after mutation the UI must re-read backend authority.

## 10. Error and state handling

All operational screens use fail-closed state rendering:

- `LOADING` — no inferred value
- `AVAILABLE` — render authoritative data
- `STALE` — clearly label stale; do not treat as current
- `UNKNOWN` — no success/ready inference
- `UNAVAILABLE` — disable dependent mutations and show reason/recovery path

Mutation behavior:

- show pending state
- show backend rejection reason safely
- never optimistically fabricate authoritative success
- refresh authoritative state after success
- preserve idempotency where service supports it

## 11. UI structure

Recommended Owner navigation after implementation:

### CONTROL
- Overview
- Users & Access
- Strategies
- Connections & Data

### RESEARCH & OPERATIONS
- Backtests
- Walk-Forward / OOS
- Paper Trading
- Deployments
- Portfolio & Orders
- Reports & Audit

### SAFETY & INTELLIGENCE
- Risk & Safety
- AI Control Center

### SYSTEM
- Product Operations
- System Health
- Security Authority
- Security Incidents
- Settings

Mobile Owner navigation continues to use the compact bottom bar plus `More` drawer; all controls remain available without changing authority semantics.

## 12. Backend contract strategy

Implementation order for each control:

1. Identify canonical existing backend service/route.
2. If route exists and is safe, wire typed client + UI.
3. If service exists but Owner route is missing, add the narrowest Owner API adapter.
4. If only engine-internal code exists, do **not** expose it directly; first define a backend authority adapter with tests and fail-closed behavior.
5. If no safe canonical authority exists, render the feature as unavailable and document the gap instead of inventing behavior.

## 13. Testing and verification requirements

Implementation is not complete until all of the following are green:

- targeted backend tests for every new/changed Owner command
- Owner route/auth/step-up tests
- Owner/User wiring contract tests
- frontend unit/component tests for all new controls
- production frontend build
- full `tests_v1` regression on Windows/Python 3.13.14
- existing AI boundary guards
- Owner/Admin boundary guard
- S2 account gate
- portfolio/risk guard
- Live architecture/read-only guards
- no forbidden imports/calls from Owner UI into engine broker/live mutation paths
- route inventory proof: every Owner UI API path maps to a real backend route
- authority proof: no reachable canonical screen uses unlabeled sample/mock operational truth
- Live proof remains `READ_ONLY / DISARMED`

Browser smoke testing should cover Owner navigation and representative success/rejection states for each control domain.

## 14. Rollout strategy

Implement as vertical slices so each slice is independently testable and does not create a second authority:

1. Truth cleanup + control inventory
2. Backtest + Walk-Forward controls
3. Paper controls + Owner HOLD
4. Deployments
5. Connections/Historical Data operations
6. Risk & Safety truthful projection
7. Product/System operations
8. Cross-surface polish, browser smoke, full regression

This sequence is a design-level rollout order, not the implementation task plan. The implementation plan will be written only after Owner review/approval of this spec.

## 15. Explicitly out of scope

- enabling real-money Live trading
- Live ARM control
- real broker order placement/modification/cancellation
- kill-switch disable/bypass control
- weakening RiskGate
- generic terminal/shell in the dashboard
- raw secret/token display
- generic `.env` editor
- arbitrary filesystem editor
- bypassing WebAuthn step-up
- replacing canonical backend/engine authority with frontend state
- unrelated redesign of User Dashboard business flows

## 16. Acceptance criteria

The design is successfully implemented when:

1. The Owner can perform normal administration, research, paper, data, AI, security, settings, diagnostics, and supported product operations from the Owner Dashboard.
2. Existing backend operations that currently require external/manual invocation are reachable through typed, authenticated Owner UI controls where safe.
3. Any operation that cannot safely be exposed is visibly identified as unavailable rather than faked.
4. No canonical reachable screen displays hardcoded risk/kill-switch readiness as operational truth.
5. All privileged mutations are authorized, correctly step-up classified, audited, and re-read after completion.
6. The Owner Dashboard does not gain direct engine or broker mutation authority.
7. User/Owner, Backtest/Paper/Shadow/Live isolation remains intact.
8. Live remains `READ_ONLY / DISARMED` and broker mutation remains zero.
9. Full Windows regression, frontend tests/build, wiring contracts, and safety/boundary guards pass.
10. Day-to-day Owner operation no longer requires routine terminal/backend-file access except for intentionally excluded machine/secret administration.
