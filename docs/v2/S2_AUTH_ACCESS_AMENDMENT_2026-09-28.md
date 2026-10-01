# AlgoFortis V2 — S2 / AUTH_ACCESS_CONTRACT_V1 Amendment

**Date:** 2026-09-28  
**Status:** OWNER-FROZEN DOCUMENTATION AMENDMENT — CORRECTED  
**Amends:**
- `docs/superpowers/specs/2026-09-26-s2-account-device-session-gating-design.md`
- `docs/AUTH_ACCESS_CONTRACT_V1.md` for V2 interpretation/carry-forward
- `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`

**Safety invariant:** Live remains `READ_ONLY / DISARMED`. Identity/authentication state cannot mint `ApprovedOrder`, arm Live, or call broker mutation.

> **Correction note:** Earlier 2026-09-28 text that treated remote execution/mobile as current V2 scope is superseded. OD-V2-02 remains local-first for V2.0. This amendment keeps the password-fallback/step-up decision and adds only deployment-portability seams needed to avoid a future engine rewrite.

## 1. Precedence and historical-contract rule

`AUTH_ACCESS_CONTRACT_V1.md` remains an immutable historical record of the V1 behavioral contract. This dated amendment is the authoritative V2 overlay where its authentication requirements differ from or extend V1 wording.

The S2 design remains authoritative. Its local-first execution placement remains in force for V2.0 under OD-V2-02.

This amendment does not silently rewrite historical V1 numeric policies. Existing V1 values remain evidence of V1 behavior, not automatically selected V2 production values.

## 2. Authentication methods

### Preferred

FIDO2/WebAuthn passkey remains the preferred interactive authentication method.

### Allowed fallback

Password authentication is permitted as a fallback path.

Password fallback does not create trading authority and does not automatically satisfy high-assurance/step-up requirements.

## 3. Session assurance requirement

S2 must distinguish at least conceptually between:

- an authenticated session whose current assurance is password-only; and
- a session with a current successful step-up/high-assurance proof sufficient for a protected sensitive action.

Exact token field names, assurance labels, step-up lifetime, and implementation technology are implementation-plan decisions and are not invented by this documentation freeze.

A central account/session assertion remains only an authentication prerequisite. It cannot by itself make Live eligible, ARMED, reconciled, RiskGate-approved, or broker-mutating.

## 4. Step-up policy

A password-only session MUST NOT perform the following without successful step-up authentication:

1. Arm Live.
2. Add, replace, rotate, reveal-equivalent, or remove broker credential material.
3. Enroll a new registered device.
4. Revoke a registered device.
5. Delete the user account.

A later dated policy may add equivalent/higher-risk actions, but cannot silently remove these minimum protections.

### 4.1 Risk-reducing exception

Additional step-up MUST NOT be required merely to perform a risk-reducing emergency/safety action that the already-authenticated user is otherwise authorized to perform, including:

- Pause / `HALT_ENTRIES`;
- emergency halt;
- `CANCEL_PENDING` where permitted by the frozen safety policy;
- exit a position;
- `FLATTEN_ALL` after its required deliberate confirmation.

This exception does not mean anonymous access is allowed. It means a fresh step-up ceremony must not become a dependency for reducing market risk during an urgent condition or authentication-factor outage.

## 5. Password security requirements

The V2 password fallback path MUST use:

- strong modern password hashing suitable for password storage;
- a unique salt per credential and versioned hashing parameters;
- no plaintext or reversibly encrypted password storage;
- flow-isolated rate limiting;
- progressive lockout/cooldown behavior;
- credential-stuffing defenses;
- breached-password screening/checking through a privacy-conscious mechanism appropriate to the final production design;
- audit evidence for material fallback-authentication abuse/security events;
- secure reset/recovery integration consistent with high-assurance recovery semantics.

### 5.1 No invented production numbers

This amendment deliberately freezes **requirements, not guessed production constants**.

Exact production values such as:

- password length/complexity policy;
- hash work/memory parameters;
- failed-attempt thresholds;
- cooldown durations;
- breach-check provider/query policy;
- step-up validity duration;

must be selected through dated security evidence/review and versioned policy before production release.

Historical V1 values such as the V1 failed-attempt/cooldown settings remain historical V1 contract values. They MUST NOT be copied into V2 merely because they already exist.

TEST_ONLY profiles may use explicit test values and must never be presented as production policy.

## 6. V2.0 local-first execution boundary

OD-V2-02 remains unchanged: V2.0 trading execution is local-first.

### 6.1 Local client/device plane

The local AlgoFortis client holds the approved user/device authentication material required by S2, including the separate device-binding key under the frozen policy.

The client does not own RiskGate/order authority merely because it is authenticated.

### 6.2 Local execution plane

For V2.0, the trading engine and trading state remain local. Broker credentials remain local under the existing local secret-custody design.

The central Account Authority remains authoritative for account identity, registered devices, sessions, revocation/recovery, entitlement/account security state and permitted non-sensitive account preferences.

It remains prohibited from:

- minting `ApprovedOrder`;
- arming Live;
- placing/canceling/modifying broker orders;
- storing broker credentials for trading use;
- becoming a shared trading engine.

## 7. Deployment-portability seam under OD-V2-27

S2 must not force future remote hosting to require a trading-domain rewrite.

The engine architecture therefore preserves two conceptual deployment profiles:

- `LOCAL_PC` — V2.0/current profile;
- `REMOTE_HOST` — future single-tenant profile, not currently activated.

Profile-specific concerns belong behind ports/adapters, including:

- paths/filesystem;
- secret storage;
- persistence/storage;
- clock/time evidence;
- host lifecycle/health/restart integration;
- alert delivery;
- bind/network exposure.

Trading-domain code must not directly depend on Windows path/DPAPI/registry/sleep APIs. Windows/CNG/DPAPI behavior remains valid at the `LOCAL_PC` adapter edge.

Future `REMOTE_HOST` secret/network implementations are cloud go-live design work; no KMS/provider/network product is selected by this amendment.

## 8. Headless engine API — local by default

V2.0 should preserve a headless-capable engine/process boundary with a versioned API used by approved local UI/client surfaces.

Required properties from day one:

- authenticated API;
- versioned contract;
- authorization tied to S2 account/device/session rules;
- no direct `ApprovedOrder` construction;
- no RiskGate bypass;
- sensitive actions enforce the password-only step-up policy;
- localhost/local-machine bind by default for V2.0;
- fail closed on unverifiable auth/session evidence.

An internet-facing API is **not** required by V2.0 and is not qualified by this amendment.

## 9. Recovery and arming semantics

Execution-host restart, crash, reconnect, replacement, migration, or update cannot auto-arm Live.

For the current local profile, existing recovery rules remain authoritative.

For any future host migration under OD-V2-27, the restored target host must:

1. start in `RECOVERY` or equivalent fail-closed state;
2. reconcile broker truth;
3. resolve ambiguity before readiness;
4. require explicit manual resume/arming under the normal policy.

A clean login, successful password fallback, successful step-up, account recovery, broker reconnect, or API reconnect is never sufficient by itself to resume/arm trading.

## 10. Current S2 qualification additions

### Password fallback

Qualification must prove:

- valid password fallback authenticates only to its documented assurance level;
- password-only session cannot Arm Live;
- password-only session cannot mutate broker credentials;
- password-only session cannot enroll/revoke devices;
- password-only session cannot delete account;
- successful step-up enables only action classes authorized by policy;
- Pause/Halt/Exit remain available without extra step-up to an otherwise authorized authenticated user;
- password hashes/secrets do not appear in logs/support artifacts;
- rate-limit/lockout flows are isolated;
- breached-password and credential-stuffing controls have a qualified production design before release;
- no guessed production threshold is embedded merely to pass qualification.

### Local authenticated engine API

Qualification for V2.0 must prove:

- API authentication is enforced;
- default production bind is localhost/local-machine only;
- unauthorized local requests cannot mutate protected engine state;
- an authenticated API caller cannot bypass `RiskGateV2` or directly construct an executable approval;
- password-only assurance restrictions apply to protected sensitive actions;
- risk-reducing actions remain available under the frozen exception;
- API/versioning seam does not add broker mutation authority to the central account service.

## 11. Future cloud go-live triggers — not current S2 scope

Only when the Owner later activates `REMOTE_HOST` for cloud production do the following become mandatory:

- remote client/engine internet exposure design;
- mobile client / push-notification design;
- cross-instance remote isolation qualification;
- remote secret-store/KMS selection and qualification;
- internet-facing API external/independent security test;
- hosted/static-IP/broker-registration OD-V2-09 dated verification;
- hosted-data privacy/OD-V2-25 re-review.

These are not V2.0 S2 exit requirements merely because the portability seam exists.

## 12. Unchanged S2 invariants

The amendment does not weaken:

- separate user authentication and device identity/binding;
- device quota/no silent eviction;
- server-side session/device revocation;
- refresh-family reuse detection;
- high-assurance recovery revoking old trust;
- account/tenant isolation;
- audit fail-closed behavior for security-critical mutation;
- RiskGate/order-authority separation;
- fail-closed defaults;
- `INV-15` no auto-arm after restart/reconnect/update/outage;
- `INV-17` options BUY-only;
- Live `READ_ONLY / DISARMED` state.

## 13. Explicitly not selected here

This amendment does not select:

- cloud provider/region;
- remote instance size/cost;
- cloud KMS/secret product;
- native versus PWA;
- static-IP policy;
- current hosted broker/SEBI/exchange requirements;
- production password/rate-limit numeric constants.

These remain future/open or governed by their dated verification gates.
