# AlgoFortis Canonical Dashboard Action Control Plane — Design

**Date:** 2026-10-05  
**Repository:** `olhgtd/ALGOFORTISGPT`  
**Baseline before this spec:** `853e04e8ec1fc71fd7ee77eada89c736521ede92`  
**Status:** Approved conversational design captured as implementation specification  

## 1. Purpose

The finished AlgoFortis dashboards must be operational control surfaces, not read-only demonstrations of capabilities that already exist elsewhere in the repository.

The canonical User dashboard must allow an eligible User to perform the legitimate research and paper-trading actions the backend already supports: submit strategies, run backtests, run walk-forward/OOS jobs, create/start/stop paper sessions, and create/control non-Live deployments. The canonical Owner dashboard must expose the Owner governance controls that already exist in backend authority but are currently unreachable from the canonical routes, including account lifecycle and connection allowance controls.

A capability is considered **ACTIVE** only when all of the following are true:

1. The canonical dashboard route exposes the action.
2. The action calls the canonical backend endpoint/client.
3. The backend performs the real governed operation rather than a local fixture or simulated UI-only mutation.
4. The UI shows authoritative success, rejection, or unavailable state.
5. Regression tests prove the wiring and safety boundary.
6. Critical browser flows are exercised through Chromium against the canonical application shell.

The design must not revive the legacy monolithic `UserScreens.tsx` as the canonical UI and must not weaken Live execution safeguards.

---

## 2. Non-negotiable safety invariants

The following constraints remain unchanged throughout this work:

- Live remains **READ_ONLY / DISARMED**.
- No User or Owner dashboard control may expose broker order placement, modification, cancellation, or Live arming.
- No UI mutation may bypass RiskGate, strategy readiness, service entitlement, dataset governance, session ownership, or backend authorization.
- Missing authority must render `UNAVAILABLE`, `UNKNOWN`, or the backend failure reason; it must never be replaced with a healthy/sample value.
- Hardcoded financial risk numbers are forbidden on canonical production surfaces unless explicitly labelled as non-authoritative demonstration data. This design chooses not to show such demo values on canonical surfaces.
- Kill-switch state must never be shown as ready/armed unless a canonical kill-switch authority is attached and reports that state.
- User market-data import remains Owner-only. Users consume approved datasets; they do not mutate the canonical shared data store.
- Owner destructive actions continue to require the existing WebAuthn step-up mechanism where the backend classifies them as destructive.
- Historical/provider credentials remain write-only in the UI and are never rendered back.
- Existing V1/V2 safety, audit, NON_PROMOTABLE, fail-closed, and broker-mutation-absent guarantees must continue to pass.

---

## 3. Canonical navigation remains stable

### User navigation

The seven canonical User routes remain:

- Home
- Markets
- Strategies
- Testing & Validation
- Trades
- Portfolio
- Account

No new top-level route is required for this project. Action controls are added to the screen that already owns the corresponding domain.

### Owner navigation

The current Owner navigation remains stable. Missing controls are merged into the already-routed canonical screens instead of introducing parallel Owner screens.

---

## 4. User Control Plane design

### 4.1 Strategies — submission, promotion, and deployment authority

The canonical Strategies screen becomes the User's strategy lifecycle control surface.

It must support:

- viewing the authoritative strategy registry;
- submitting a new strategy source through `POST /api/v1/strategies`;
- optionally supplying the existing `protective_policy_identity` field when supported by the backend contract;
- showing validation or submission rejection from the backend without inventing success;
- requesting strategy promotion through the existing promotion request client/endpoint;
- showing current stage/readiness/allowance evidence;
- creating a User deployment through `/api/v1/user/deployments`;
- pausing, resuming, and stopping User deployments through the existing deployment mutation clients;
- refreshing the strategy/deployment evidence after a successful mutation.

Deployment UI must not permit a real `LIVE` execution mode. The allowed mutation choices are limited to modes already safe under the current product boundary, such as `PAPER` / `LIVE_PAPER` where the backend accepts them. If backend authority rejects a mode, the UI surfaces the rejection rather than translating it into success.

No direct broker mutation path may be imported into the Strategies screen.

### 4.2 Testing & Validation — actionable Backtest and Walk-Forward/OOS

The canonical `Testing & Validation` screen becomes both the read model and the run-control surface for research jobs.

It must support **Run Backtest** with canonical inputs including:

- strategy ID/version where available;
- dataset ID;
- instrument;
- timeframe;
- initial capital;
- backend-supported policy values;
- date range or equivalent existing backend field.

It must call the existing canonical `POST /api/v1/backtests` path via the shared client. It must expose active-run status and the existing cancel operation when the backend reports a cancellable state.

It must support **Run Walk-Forward / OOS** with canonical inputs including:

- strategy ID/version;
- dataset ID;
- instrument;
- timeframe;
- IS days;
- OOS days;
- max windows;
- initial capital;
- backend-supported policy values.

It must call the existing canonical `POST /api/v1/walkforward/jobs` client and expose cancellation only when the backend supports it.

After creation/cancellation, the screen refreshes authoritative runs/jobs/reports. It must not fabricate progress. Progress is derived only from backend job evidence.

### 4.3 Trades — actionable Paper sessions

The canonical Trades screen becomes the User's Paper runtime control surface while keeping Live observation read-only.

For **PAPER**, it must support:

- create paper session;
- start paper session;
- stop paper session;
- select or display the strategy, instrument, timeframe, initial capital, dataset/date source inputs supported by the backend;
- list authoritative paper sessions;
- display paper orders, positions, and events;
- show backend rejection/hold/suspension reasons.

These operations use the existing `createPaperSession`, `startPaperSession`, and `stopPaperSession` shared clients and the existing paper backend service. The UI must make clear that this path uses the simulated/paper execution authority and does not route real broker orders.

For **LIVE**, the screen remains observation-only and prominently retains `READ_ONLY / DISARMED`. It may show authoritative readiness/orders/positions evidence if available, but it may not expose Live arm or order mutation controls.

### 4.4 Markets — truthful data only

Markets remains read-only for normal Users.

Users may:

- view canonical market candles;
- view authority/freshness states;
- select supported instruments/timeframes;
- see option-chain authority as unavailable when not attached.

Users may **not** import, overwrite, sync, repair, or approve canonical market data.

The existing Owner-only `/api/v1/market/data/import` policy remains Owner-only.

### 4.5 Account — connections and Live readiness evidence

Account remains the canonical User identity/connectivity/readiness surface.

It displays:

- account/service entitlement;
- broker connection metadata;
- connection health and capabilities;
- Live readiness/reconciliation evidence where available;
- explicit `CONNECTION ≠ ARMED LIVE` messaging.

The User may use only existing safe connection-management actions if already explicitly allowed by backend User authority. This project must not infer new broker credential mutation authority merely because connection records can be read.

### 4.6 Home and Portfolio

Home continues to summarize authoritative shell state and must refresh after mutations performed elsewhere.

Portfolio remains evidence-oriented unless an existing safe mutation already belongs there. No new order-entry authority is introduced.

---

## 5. Owner Control Plane wiring fixes

### 5.1 Users & Access — merge lifecycle controls into the reachable canonical screen

The canonical `UsersAccessScreen` currently combines inspection and access-registry functionality but does not expose all account lifecycle actions available in the unreachable `OwnerUsersScreen`.

The canonical screen must expose, for each eligible account:

- Suspend;
- Restore;
- Revoke;
- activation reissue;
- activation revoke;
- extend service;
- renew service;
- lifetime conversion;
- user inspection.

The implementation should reuse the existing `ownerAccountAction(...)` clients and existing Owner mutation endpoints rather than duplicating backend logic.

After this integration, the unreachable duplicate Owner user-governance UI should be removed or reduced to a non-canonical compatibility wrapper so that there is one authoritative Owner user-management surface.

### 5.2 Connections & Data — merge broker allowance controls into the reachable screen

The canonical Owner route currently renders `DataOperations`, while connection/capability allowance controls exist in a separate component that the router does not use.

`DataOperations` must become the single canonical `Connections & Data` control surface and include:

- connection allowance `ALLOWED` / `HOLD` / `REVOKED`;
- capability-level allowance control;
- historical provider create/update/enable/disable;
- manual historical sync;
- scheduled sync configuration;
- gap repair;
- dataset approval/hold/reject where backend supports it;
- dataset retire;
- dataset replacement.

All connection/dataset destructive governance continues through Owner step-up clients.

### 5.3 Settings authorization correction

`POST /api/v1/settings/propose` currently uses generic mutable-session authorization while the canonical UI is Owner-only and final confirmation is Owner-controlled.

The proposal endpoint must require Owner mutation authority as well, using the same Owner-role/active-account boundary as other Owner settings changes. A non-Owner must not be able to stage a settings proposal.

The existing lifecycle remains:

`PROPOSE → VALIDATE → DRY RUN → DIFF → CONFIRM → ATOMIC APPLY → VERIFY → AUDIT`

The canonical Owner Settings screen must continue to re-read effective settings after confirmation and show backend confirmation/rejection.

---

## 6. Safety authority design

### 6.1 Safe Mode and Global Hold

The existing Owner Risk & Safety screen remains the canonical safety surface.

- Safe Mode engage remains a real backend mutation.
- Global Hold engage/release remains a real backend mutation.
- Release operations that the backend classifies as destructive continue to require step-up.
- No new Safe Mode clear/bypass action is invented unless the backend already has an explicit, tested recovery contract. If no such authority exists, the dashboard says so.

### 6.2 Canonical kill-switch bridge

Current truth is `NOT_CONNECTED` because `OwnerSafetyAdapter` intentionally does not import the engine kill-switch authority.

This project introduces a **bounded safety bridge**, not a general engine-control bridge.

The bridge requirements are:

1. A narrow backend interface exposes kill-switch status from the canonical Paper/Live-Paper coordinator authority.
2. Owner may **engage** the kill switch through a dedicated Owner safety endpoint.
3. Engaging is idempotent and audit-recorded.
4. The bridge cannot place/modify/cancel orders, arm Live, mutate broker credentials, or call arbitrary engine functions.
5. Dashboard state is derived only from the bridge response.
6. If the coordinator authority is absent, the response remains `NOT_CONNECTED` / `UNAVAILABLE` and the Engage button is disabled.
7. No casual dashboard "disable kill switch" action is added. Reset/recovery, if required later, must be a separately designed step-up recovery flow.

The initial bridge scope targets Paper / Live-Paper safety behavior only. It does not make real-money Live executable.

### 6.3 RiskGate numeric authority

The Owner Risk & Safety page currently reports RiskGate availability but does not expose authoritative numeric policy limits.

A read-only risk-policy projection should expose the values the active canonical RiskGate/policy authority can prove, for example:

- policy/version identity;
- daily loss limit;
- portfolio/exposure limit;
- drawdown threshold;
- per-order or position limit if the active authority owns such a value;
- slippage/cost policy only if that value is owned by the canonical risk/cost authority;
- authority timestamp/source.

The dashboard must render only fields actually returned by authority. Unsupported values display `UNAVAILABLE`; no defaults are invented in the UI.

This projection is read-only and must not provide a path for the dashboard to rewrite core RiskGate policy unless a separately governed settings contract already exists.

---

## 7. Legacy/sample cleanup and truth firewall

The repository still contains legacy/sample User data modules and `UserScreens.tsx` with hardcoded safety/risk presentation.

The canonical application already forbids importing these modules, but the cleanup must make future regression less likely.

Required actions:

- Remove hardcoded `ARMED & READY` and hardcoded production-looking risk metrics from legacy source, or remove the obsolete screen when no compatibility consumer requires it.
- Retire/remove unused sample modules from active barrels where safe.
- Ensure canonical `UserDashboardApp` and canonical screens cannot import legacy sample modules.
- Update stale documentation that describes obsolete User routes/actions or obsolete endpoint paths as current behavior.
- Keep historical documents only when clearly marked historical; do not silently rewrite factual project history.

Permanent static tests must reject canonical imports of sample modules and reject known misleading hardcoded safety strings on canonical production surfaces.

---

## 8. Shared client architecture

The implementation should prefer `dashboard/shared/services/integrationClient.ts` as the User-side typed integration boundary and the existing Owner authoritative client modules for Owner actions.

Do not duplicate fetch logic inside multiple screens when a shared client already exists.

Where existing shared clients have inconsistent return shapes (`ok` vs `success`, direct payload vs `IntegrationResult`), screen adapters may normalize locally first. A broader client rewrite is out of scope unless required to make the canonical actions reliable.

All new mutation UI must:

- disable duplicate submission while pending;
- surface HTTP/backend error detail in bounded user-safe form;
- refresh authoritative state on success;
- never fall back to sample success;
- preserve session/role checks enforced by the backend.

---

## 9. Error and authority-state UX

Every action-capable panel uses four observable classes of state:

- `AVAILABLE`: authoritative backend state is current enough for the action.
- `UNAVAILABLE`: required backend authority/service is not attached or unreachable; action disabled.
- `REJECTED/BLOCKED`: backend intentionally rejected the request; exact bounded reason shown.
- `PENDING/RUNNING`: backend accepted asynchronous work; UI shows authoritative job/run state and allows cancel only when permitted.

`UNKNOWN` and `STALE` must not be promoted to safe/healthy/ready.

A failed mutation must leave the previous authoritative read model visible with an error message; it must not optimistically fake the resulting state.

---

## 10. Testing strategy

### 10.1 Backend tests

Add or extend tests for:

- User can create a backtest when eligible and invalid/suspended/held cases fail closed.
- User can create and cancel Walk-Forward/OOS jobs according to backend rules.
- User can create/start/stop Paper sessions, with RiskGate/policy rejection preserved.
- User deployment create/pause/resume/stop remains limited to allowed execution modes.
- Non-Owner cannot stage a settings proposal.
- Owner account lifecycle endpoints remain step-up/role protected.
- Owner connection/capability allowance endpoints remain step-up/role protected.
- Kill-switch bridge returns `NOT_CONNECTED` when authority absent and engages the canonical coordinator when present.
- Kill-switch bridge has no Live arm/broker mutation capability.
- Risk-policy projection returns only authoritative fields and fails closed when authority is absent.

### 10.2 Frontend unit/component tests

Tests must prove canonical routed screens expose the controls:

- Strategies: submit/promotion/deployment lifecycle.
- Testing & Validation: run/cancel Backtest and WFO.
- Trades: create/start/stop Paper.
- Users & Access: suspend/restore/revoke/service actions.
- Connections & Data: connection/capability allowance plus data controls.
- Risk & Safety: truthful kill-switch and risk-policy rendering.

Tests must also prove:

- no Live arm or broker-order mutation API string is imported/exposed;
- no sample-data fallback is treated as authoritative success;
- canonical User app does not import retired legacy/sample modules;
- `READ_ONLY / DISARMED` remains visible in Live contexts.

### 10.3 Browser verification

A canonical Chromium smoke/qualification must exercise real routed UI controls with a deterministic backend test authority or local test runtime.

Minimum browser flows:

1. User → Strategies → submit strategy or deterministic test submission → observe backend response.
2. User → Testing & Validation → run Backtest → observe created run → cancel if cancellable.
3. User → Testing & Validation → run WFO → observe created job.
4. User → Trades → create Paper session → start → observe runtime evidence → stop.
5. User → Strategies → create allowed deployment → pause/resume/stop.
6. Owner → Users & Access → lifecycle action reaches correct API and rejection/step-up path is handled.
7. Owner → Connections & Data → connection allowance action reaches correct API.
8. Owner → Risk & Safety → disconnected kill-switch never renders ready; attached test authority can engage it.

The browser verifier must not mock a success for a path whose backend contract is missing. Mocking is acceptable only when the mock explicitly represents the canonical backend contract and the separate backend tests prove that contract.

---

## 11. Implementation slices

### Slice A — User action control plane

Deliver:

- strategy submission/promotion/deployment controls;
- Backtest create/cancel controls;
- Walk-Forward/OOS create/cancel controls;
- Paper session create/start/stop controls;
- refresh/error/pending UX;
- User component and backend contract tests;
- canonical browser smoke for these User flows.

Acceptance gate: a normal eligible User can perform the complete research → validate → paper workflow from the canonical seven-screen dashboard without using legacy screens.

### Slice B — Owner reachability and authorization

Deliver:

- lifecycle controls merged into `UsersAccessScreen`;
- connection/capability allowance merged into `DataOperations`;
- settings proposal made Owner-only;
- duplicate unreachable Owner control components retired or reduced to wrappers;
- Owner unit/backend/browser verification.

Acceptance gate: every existing Owner governance mutation named above is reachable from the canonical Owner router and remains step-up/role protected.

### Slice C — Safety truth bridge

Deliver:

- bounded kill-switch status/engage bridge;
- Owner Risk & Safety wiring;
- read-only RiskGate numeric policy projection;
- fail-closed tests proving absent authority stays unavailable;
- no broker mutation or Live arming reachability.

Acceptance gate: dashboard safety status matches canonical runtime authority, and no hardcoded/fabricated safety state remains.

### Slice D — Cleanup and full qualification

Deliver:

- legacy misleading User safety UI removed/retired;
- unused sample barrels/modules cleaned where safe;
- stale current-behavior documentation corrected;
- full Python regression;
- frontend unit suite;
- typecheck;
- production build;
- static Live/broker/AI/safety boundary checks;
- Chromium desktop/mobile control-plane qualification.

Acceptance gate: no known current dashboard capability is merely decorative when an approved backend authority exists for it, and all Live safety invariants remain green.

---

## 12. Explicitly out of scope

This project does **not**:

- arm real Live trading;
- add real broker order placement/modification/cancellation;
- let AI directly submit orders;
- give normal Users canonical market-data import/overwrite authority;
- expose arbitrary terminal/process/file-system control through the dashboard;
- redesign the seven-route User navigation;
- replace the engine, RiskGate, paper broker, backtest engine, or WFO engine;
- rewrite the entire shared integration client merely for style consistency;
- add a general-purpose engine RPC/control bus.

---

## 13. Completion definition

The project is complete only when all four statements are true:

1. **User:** an eligible User can submit a strategy, run Backtest, run WFO/OOS, run a Paper session, and control allowed deployments entirely from canonical routed screens.
2. **Owner:** account lifecycle, service entitlement, connection/capability governance, datasets/providers, settings, AI, sessions/devices, audit, and safety controls that have approved backend authority are reachable from canonical Owner routes.
3. **Truth:** no canonical screen fabricates risk/safety/readiness values; kill switch and RiskGate values come from backend authority or show unavailable.
4. **Safety:** Live remains `READ_ONLY / DISARMED`, broker mutation stays absent, and all existing fail-closed regression gates continue to pass.
