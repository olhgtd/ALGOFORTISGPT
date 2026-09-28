# AlgoFortis V2 — Remote Single-Tenant Engine / Password Fallback / Mobile Owner Decision Freeze

**Date:** 2026-09-28  
**Status:** FROZEN — DOCUMENTATION / DECISION RECORD ONLY  
**Scope:** OD-V2-02 amendment; new OD-V2-27; S2/Auth amendment; mobile scope; OD-V2-25 re-review trigger; roadmap/qualification impacts  
**Safety invariant:** Live remains `READ_ONLY / DISARMED`. This record does not authorize broker mutation, Live ARM, workflow changes, runtime changes, or configuration changes.

## 1. Owner decision summary

The Owner freezes the following architectural direction:

1. AlgoFortis may run a trading engine either on the supported local execution host or on the user's own **dedicated remote single-tenant engine instance**.
2. A remote hosted engine is never a shared multi-tenant trading engine: **one user = one isolated engine instance**.
3. Desktop, web, and mobile clients may communicate with the user's dedicated engine through an authenticated, versioned API.
4. The central Account Authority remains identity/device/session/entitlement authority only. It has **no trading authority** and cannot mint `ApprovedOrder`, arm Live, or place/cancel/modify broker orders.
5. `RiskGateV2` remains the sole authority that can approve an executable order.
6. Broker credentials are never stored in the central account database. On a remote engine they are held only in that user's isolated instance-side encrypted secret store, with KMS-backed key custody. Raw credentials are never returned to normal UI/API responses.
7. Restart, crash, reconnect, host replacement, migration, or update never auto-arms. Uncertain/restarted execution enters recovery/reconciliation and requires the already-frozen manual-resume latch where applicable.
8. Fail-closed remains the default.
9. Options remain BUY-only under `INV-17`.
10. Passkey/WebAuthn is preferred interactive authentication; password fallback is allowed under the assurance restrictions in §4.
11. Mobile client is now in scope. Native versus PWA remains OPEN.
12. Hosted trade/position data changes the privacy/data-processing model and forces an OD-V2-25 re-review before hosted production release.

## 2. OD-V2-02 amendment — deployment model

The previous V2.0 local-first-only wording is superseded by this dated amendment.

**Frozen decision:** AlgoFortis supports an execution-plane abstraction with two permitted placements:

- supported local engine; or
- user-dedicated remote single-tenant engine.

This is **not** authorization for a shared multi-tenant trading engine. The central account service remains separate from the execution plane and has no order authority.

The following are intentionally **not frozen here**:

- cloud provider;
- cloud region;
- instance size;
- per-instance cost;
- production networking/static-IP design;
- broker registration treatment of a hosted engine.

Those require later evidence and, where relevant, the dated OD-V2-09 regulatory/broker verification.

## 3. OD-V2-27 — Remote single-tenant engine hosting

**Decision:** **FROZEN — Remote single-tenant engine hosting is an approved V2 architecture path.**

### 3.1 Isolation and authority

- One user maps to one isolated engine instance when remote hosting is used.
- Shared multi-user trading-engine process/state is prohibited.
- Instance isolation must cover runtime state, broker sessions, secret storage, trading state, audit state, and execution authority boundaries.
- Central account infrastructure may authenticate/authorize the client and issue account/session evidence, but it cannot approve or execute trades.
- The client cannot bypass the engine's deterministic trading path.

### 3.2 Order path remains unchanged

The executable path remains conceptually:

`Strategy / allowed deterministic source -> intent/candidate validation -> RiskGateV2 -> ApprovedOrder -> BrokerPort`

No mobile/web/desktop client, central service, AI/Laya component, hosting control plane, or notification service may mint an executable approval or bypass `RiskGateV2`.

### 3.3 Secret custody

- Broker credentials/tokens are prohibited from the central account database.
- On a remote engine, credentials live only in the user's isolated instance-side encrypted secret store.
- Encryption keys are KMS-backed; exact provider/product is not selected by this record.
- Secret access is auditable and must follow least privilege.
- Backups/support bundles/logs must not expose broker credentials or tokens.

### 3.4 Recovery / arming

- Remote host restart/crash/replacement/update -> `RECOVERY` or equivalent fail-closed recovery state.
- Broker/session reconnect alone does not restore trading-entry permission.
- Recovery requires reconciliation and the frozen manual-resume latch before new entries when the system has entered a safety halt/recovery state.
- No restart/reconnect/update may auto-arm Live.

## 4. Password fallback amendment

Passkey/WebAuthn remains preferred. Password login is allowed as fallback, but a password-only session is lower assurance for risk-increasing/sensitive mutations.

### 4.1 Step-up mandatory from password-only session

A password-only session cannot perform the following without successful step-up authentication under the S2 security policy:

- Arm Live;
- change/add/remove broker credentials;
- enroll a new device;
- revoke a registered device;
- delete the account.

Step-up is also required for any later action explicitly classified by a dated policy as equivalent or higher risk.

### 4.2 Risk-reducing actions do not depend on step-up

The following safety actions must remain available without requiring step-up merely because the current session is password-only:

- Pause / `HALT_ENTRIES`;
- emergency halt;
- cancel/reduce actions permitted by the frozen safety policy;
- exit a position / `FLATTEN_ALL` or equivalent deliberate risk-reducing exit action.

Authentication/authorization sufficient to prevent an unauthenticated attacker is still required; this rule means an additional step-up ceremony must not become a dependency for reducing market risk during an outage or urgent condition.

### 4.3 Password security requirements

The S2/Auth specification must require, without inventing production numbers:

- modern strong password hashing with unique salts and versioned parameters;
- no plaintext or reversibly stored passwords;
- flow-isolated rate limiting and progressive lockout/cooldown;
- credential-stuffing defenses;
- breached-password screening/checking using a privacy-conscious mechanism appropriate to the final architecture;
- auditability of security-relevant fallback use and abuse events;
- production parameters chosen from dated security evidence/review, not guessed to make a gate green.

Historical V1 numeric lockout values are historical contract evidence; they are not silently promoted into new V2 production constants by this amendment.

## 5. Mobile client scope

Mobile is now in scope before the Live pilot gate.

- Mobile communicates with the dedicated engine through authenticated API contracts; trading authority does not move onto the phone.
- Native versus PWA is OPEN.
- Push notification payload is **redacted by default**, e.g. `Action required — AlgoFortis kholo`.
- Detailed trade/position/order/P&L content is shown by default only after opening an authenticated AlgoFortis client/session.
- Telegram/email/external-channel detailed content is allowed only after explicit user opt-in under the privacy/notification policy.
- Secrets, tokens, raw broker credentials, and unrestricted account identifiers are never notification payload content.

## 6. Impact on existing frozen decisions

### OD-V2-05 — exclusivity

The frozen exclusivity principle now applies across **all eligible execution placements**. If a local engine and a remote engine show activity for the same broker account, they may not both be eligible to create new entries. Conflicting/ambiguous activity triggers halt of new entries plus broker-truth reconciliation. No central service decision can substitute for reconciliation or become trading authority.

### OD-V2-08 — broker-resident protection

Broker-resident protective orders become even more critical for remote hosting. If the remote host is unreachable or crashes, a position must not depend solely on a process running on that host where the broker/API supports the required resident protective semantics. Unsupported/unknown required protection keeps the affected Live mutation path DISARMED under the existing policy.

### OD-V2-20 — updates

The versioned safe-window update policy applies to remote engine instances too. No update/restart/migration while the engine is ACTIVE or open exposure makes the transition unsafe. Update/restart never auto-arms and recovery/manual-resume semantics still apply.

### OD-V2-24 — host resilience

The Windows sleep/hibernate-specific controls remain applicable to the local Windows host. A cloud host does not inherit the desktop sleep-prevention requirement, but remote restart/crash/update uncertainty still forces `RECOVERY`, reconciliation, and manual resume before new entries. Exact cloud host resilience/SLA/sizing values remain OPEN.

## 7. OD-V2-25 — hosted-data re-review

OD-V2-25 remains an explicit **RE-REVIEW REQUIRED / OPEN legal-product gate** for the hosted model.

Because trade/position/runtime data may now be stored/processed on the user's hosted engine instance:

- the selected cloud provider becomes a data processor/service provider for hosted data as applicable to the final legal model;
- privacy notice and consent flows must be re-reviewed and updated for hosted processing;
- retention/deletion/access/correction/erasure/grievance/nomination and breach-response treatment must be reconciled with the hosted architecture;
- a **dated qualified legal review** of applicable current requirements is mandatory before production hosted-data release / Live pilot authorization;
- technical tests, security tests, or green CI **must never be represented as proof of legal compliance**.

No legal conclusion, provider, retention number, or jurisdiction-specific production implementation detail is invented by this record.

## 8. Roadmap and qualification impact

The canonical roadmap receives a new Track-P item after S2 and before the Live pilot gate:

**Remote Engine Hosting + Mobile Client**

Required design/qualification scope includes:

- single-tenant execution-instance provisioning/isolation contract;
- authenticated client-to-engine API;
- remote secret-custody design;
- local-vs-remote broker-account exclusivity handling;
- remote recovery/manual-resume behavior;
- mobile authenticated-client contract and redacted push behavior;
- hosted-data privacy/notice update;
- external/independent security testing of the internet-facing engine API before the Live pilot gate.

Phase 6 documentation must include remote-engine deployment and secret-custody design while Live remains DISARMED.

Phase 9 privacy/product documentation must include the hosted-data model and OD-V2-25 re-review.

## 9. Explicitly OPEN — do not infer

This freeze intentionally does **not** choose or invent:

- cloud provider;
- cloud region;
- instance sizing;
- per-instance cost;
- native mobile versus PWA;
- static-IP requirement;
- broker registration treatment;
- current SEBI/exchange/broker hosted-algo requirements;
- production password numeric thresholds;
- production security rate-limit/lockout numbers;
- production cloud performance or availability targets.

OD-V2-09 remains the dated authority for verifying current broker/exchange/regulatory requirements before the relevant gate.

## 10. Documentation-only boundary

This freeze changes documentation and decision authority only.

It does **not** change:

- runtime code;
- workflows;
- CI configuration;
- application configuration;
- broker adapter mutation capability;
- current Live state.

**Live remains `READ_ONLY / DISARMED`. Implementation planning and coding require a separate Owner approval after review of this documentation freeze.**
