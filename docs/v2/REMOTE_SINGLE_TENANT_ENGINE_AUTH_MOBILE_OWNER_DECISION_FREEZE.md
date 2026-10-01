# AlgoFortis V2 — Deployment Portability / Password Fallback Owner Decision Freeze

**Date:** 2026-09-28  
**Status:** FROZEN — FOLLOW-UP CORRECTION / DOCUMENTATION ONLY  
**Scope:** Preserve OD-V2-02 local-first V2.0; redefine OD-V2-27 as deployment portability; retain password fallback; defer remote/mobile/privacy/network go-live items  
**Safety invariant:** Live remains `READ_ONLY / DISARMED`. This record does not authorize broker mutation, Live ARM, workflow changes, runtime changes, or configuration changes.

> **Correction note:** This file path is retained for audit continuity. This follow-up correction supersedes the earlier content committed at `b94a7a5c470da7d63aac8db0d79536e7b7650cf0` where that content amended OD-V2-02 or brought remote hosting/mobile go-live into V2.0 scope.

## 1. Owner decision summary

1. **OD-V2-02 remains AS-IS:** V2.0 is local-first. The trading engine, trading state, broker credentials, trade logs and live positions remain local for V2.0. Remote hosted execution is outside V2.0 scope.
2. **OD-V2-27 is Deployment Portability:** the same engine build is designed to run under two deployment profiles: `LOCAL_PC` now and `REMOTE_HOST` later, without a domain rewrite.
3. Profile changes must be achieved through configuration and adapters/ports, not by changing trading-domain semantics or forking a second engine implementation.
4. V2.0 must expose the engine as a headless-capable process/service with a versioned authenticated API from day one, but the production/default V2.0 bind is local/localhost only unless a later cloud go-live decision changes that.
5. Paths, secrets, storage, clock/time evidence, host lifecycle/power/recovery, and alert delivery must sit behind ports/adapters. Trading-domain code must not depend directly on Windows paths, DPAPI, registry/services, sleep APIs, or other host-specific mechanisms.
6. `AlgoFortisBackup/v1` is the migration vehicle between qualified hosts. A restored target host starts fail-closed in `RECOVERY`, reconciles broker truth, and requires explicit manual resume before new entries.
7. Local and remote engines must never both be eligible for the same broker account at the same time. Any future cutover follows an explicit halt/export/restore/reconcile/manual-resume procedure under OD-V2-05.
8. A target host must re-run the applicable golden suite and failure-injection qualification before that host profile can be considered qualified for trading use.
9. Passkey/WebAuthn remains preferred; password fallback remains allowed with the previously frozen step-up restrictions.
10. Mobile/push, hosted-data OD-V2-25 re-review, hosted/static-IP OD-V2-09 questions, and external testing of an internet-facing engine API are **cloud go-live triggers**, not current V2.0 scope.

## 2. OD-V2-02 — unchanged local-first V2.0

The authoritative OD-V2-02 text remains the 2026-09-21 decision:

> **Local-first for V2.0.** Trading engines, trading state and broker secrets remain local; cloud remains account/device/entitlement authority. Hosted engine remains a future V2.4+ seam, not V2.0 scope.

This follow-up correction explicitly withdraws the prior 2026-09-28 wording that attempted to amend OD-V2-02.

Remote hosting is not a V2.0 release requirement, not a Phase-6 implementation requirement, and not a prerequisite for the V2.0 Live pilot.

## 3. OD-V2-27 — Deployment portability

**Decision:** **FROZEN — one engine build, two deployment profiles, local first.**

### 3.1 Profiles

- `LOCAL_PC`: active V2.0 deployment profile and first qualification target.
- `REMOTE_HOST`: future single-tenant deployment profile to be activated only by a later cloud go-live decision.

The engine codebase is one product. A future move from `LOCAL_PC` to `REMOTE_HOST` must not require a trading-domain rewrite or a second broker/risk/order stack.

### 3.2 Configuration/adapters only at profile boundary

Changing deployment profile may select different:

- filesystem/path adapter;
- secret-store adapter;
- storage adapter;
- clock/time-evidence adapter;
- host lifecycle/health/restart adapter;
- alert/notification adapter;
- bind/network adapter where applicable;
- operating-system integration adapter.

The deployment profile must not change:

- `RiskGateV2` sole executable-order authority;
- order lifecycle semantics;
- fail-closed behavior;
- reconciliation authority;
- BUY-only options invariant;
- restart/reconnect/update no-auto-arm invariant;
- broker-truth authority.

### 3.3 Host-neutral domain boundary

Trading/domain/application logic must not directly assume or import:

- Windows absolute paths or `%LOCALAPPDATA%` resolution;
- DPAPI/CNG/TPM implementation details;
- Windows registry/service APIs;
- Windows sleep/hibernate APIs;
- a specific database/storage engine solely because the host is Windows;
- a cloud KMS/product solely because a future remote host may use it;
- Telegram/email/local-toast implementations directly.

Those belong behind ports/adapters. `LOCAL_PC` may use Windows/DPAPI/CNG implementations at the adapter edge; future `REMOTE_HOST` may supply different adapters.

### 3.4 Headless engine + versioned API from day one

V2.0 should preserve a clean process boundary so the engine can run headless and UI surfaces communicate through a versioned API contract.

Current V2.0 requirements:

- API is authenticated from day one;
- versioned contract family is maintained;
- authorization is scoped to the current authenticated user/device/session rules;
- API cannot mint `ApprovedOrder` or bypass `RiskGateV2`;
- sensitive actions follow S2 assurance/step-up rules;
- default bind/exposure is localhost/local-machine only for V2.0;
- no internet-facing engine endpoint is required by this freeze.

A future cloud go-live may change the bind/network adapter after its own security design and qualification.

## 4. Migration / host cutover contract

The portable migration mechanism is `AlgoFortisBackup/v1` backup + restore, subject to its frozen exclusions (for example non-exportable device private keys and excluded broker secrets).

A future host cutover must conceptually follow:

1. stop/halt new entries on the source under the frozen safety policy;
2. resolve/cancel pending entry activity as permitted by the existing order/kill-switch policy;
3. record final source audit/reconciliation state;
4. create and verify `AlgoFortisBackup/v1` backup;
5. make the old execution host ineligible before the target host can become eligible for that broker account;
6. restore on the target host using the target deployment-profile adapters;
7. re-establish non-exported secrets/device material through the approved target-host ceremony;
8. enter `RECOVERY` on the target;
9. reconcile broker orders/positions/fills against broker truth;
10. re-run the required target-host qualification evidence (golden suite + applicable failure-injection set);
11. require explicit manual resume/arming under the normal policy; never auto-arm because migration succeeded.

Exact CLI/UI ceremony is implementation-plan work and is not invented here.

## 5. OD-V2-05 — local/remote exclusivity and cutover

The existing OD-V2-05 safety authority remains broker-truth reconciliation and fail-closed local protection.

Deployment portability adds this future-host rule:

- `LOCAL_PC` and `REMOTE_HOST` for the same broker account may never both be eligible for new entries simultaneously;
- the cutover must create an explicit ownership/eligibility handoff;
- ambiguous or overlapping activity -> `HALT_ENTRIES` + alert/evidence + broker reconciliation;
- no central/cloud record is sufficient by itself to override broker-truth reconciliation;
- no automatic takeover or auto-arm after target-host startup.

This is a portability/cutover requirement, not authorization to deploy the remote profile in V2.0.

## 6. Target-host requalification

Whenever the engine is moved to a materially different qualified host/profile, the release/qualification process must re-run at minimum:

- applicable golden regression suite / deterministic fingerprints;
- host/restart recovery cases;
- broker reconciliation cases;
- no-auto-arm invariant;
- same-account exclusivity/cutover case;
- applicable failure-injection catalogue for that profile;
- secret-redaction and audit invariants relevant to the selected adapters.

The exact production performance thresholds remain evidence-driven and are not guessed here.

## 7. Password fallback — retained unchanged

Passkey/WebAuthn remains preferred. Password fallback remains permitted.

A password-only session requires successful step-up before:

- Arm Live;
- add/change/remove broker credentials;
- enroll a new registered device;
- revoke a registered device;
- delete the account.

Additional step-up must not become a dependency for an already-authenticated user performing risk-reducing Pause / `HALT_ENTRIES` / permitted cancel-reduce / deliberate Exit or `FLATTEN_ALL` actions.

Password security requirements remain:

- strong modern salted password hashing with versioned parameters;
- no plaintext or reversible password storage;
- isolated rate limiting and progressive cooldown/lockout;
- credential-stuffing defenses;
- privacy-conscious breached-password screening;
- auditable security events;
- **no invented production numeric thresholds**.

`docs/v2/S2_AUTH_ACCESS_AMENDMENT_2026-09-28.md` remains the detailed V2 auth overlay, corrected to preserve local-first deployment.

## 8. Cloud go-live triggers — explicitly NOT current V2.0 scope

The following items activate only when the Owner later approves `REMOTE_HOST` for production/cloud go-live:

### 8.1 Mobile and push

- mobile client scope;
- native versus PWA choice;
- push notification transport and redaction policy;
- authenticated mobile access to a remote engine.

### 8.2 Hosted-data / OD-V2-25 re-review

- hosted trade/position/runtime data inventory;
- cloud-provider processor/service-provider analysis;
- hosted-data notice/consent update;
- dated qualified legal review for the actual hosted architecture.

The base OD-V2-25 remains in its original Phase-9 state for the V2.0 central account plane. Hosted-data re-review is not activated merely by freezing deployment portability.

### 8.3 OD-V2-09 hosted networking/regulatory verification

Future cloud go-live must verify, on a dated basis:

- static-IP requirements, if any;
- broker registration/approval treatment of a hosted engine;
- then-current SEBI/exchange/broker hosted-algo requirements.

No answer is invented now.

### 8.4 Internet-facing API security test

V2.0's localhost-bound authenticated engine API does not trigger an internet-facing API assessment.

Before a future `REMOTE_HOST` API is exposed over the internet, the cloud go-live gate must require an external/independent security assessment appropriate to the final exposed architecture.

## 9. Existing decisions retained

- OD-V2-19 remains FROZEN as already reconciled in the root register.
- OD-V2-24 remains FROZEN for the V2.0 Windows/local host.
- OD-V2-20 safe-update/no-auto-arm behavior remains unchanged for V2.0 local operation; future remote adapters must preserve it when cloud go-live is designed.
- OD-V2-08 broker-resident protection remains unchanged; any future remote-host implications are evaluated at cloud go-live, not added as V2.0 implementation scope here.

## 10. Documentation-only boundary

This correction changes decision documentation only.

It does **not** change:

- runtime code;
- workflows/CI;
- application configuration;
- deployment resources;
- broker mutation capability;
- current Live state.

**Live remains `READ_ONLY / DISARMED`. Implementation planning and coding remain blocked until separate Owner review/approval.**
