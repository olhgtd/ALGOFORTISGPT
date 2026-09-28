# AlgoFortis V2 — S2 / AUTH_ACCESS_CONTRACT_V1 Amendment

**Date:** 2026-09-28  
**Status:** OWNER-FROZEN DOCUMENTATION AMENDMENT  
**Amends:**
- `docs/superpowers/specs/2026-09-26-s2-account-device-session-gating-design.md`
- `docs/AUTH_ACCESS_CONTRACT_V1.md` for V2 interpretation/carry-forward
- `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`

**Safety invariant:** Live remains `READ_ONLY / DISARMED`. Identity/authentication state cannot mint `ApprovedOrder`, arm Live, or call broker mutation.

## 1. Precedence and historical-contract rule

`AUTH_ACCESS_CONTRACT_V1.md` remains an immutable historical record of the V1 behavioral contract. This dated amendment is the authoritative V2 overlay where its requirements differ from or extend V1 wording.

The S2 design remains authoritative except where this amendment explicitly supersedes local-only execution placement or WebAuthn-only assumptions.

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

## 6. S2 execution-plane amendment

The original S2 design uses `local Windows plane` language because the then-frozen deployment model was local-first. For V2 after OD-V2-02/27 amendment, interpret this as two distinct responsibilities:

### 6.1 Client/device plane

A desktop, web, or mobile client may hold only the client/device authentication material required for its role, such as device-bound keys/tokens under the S2 contract.

The client does not own RiskGate/order authority merely because it is authenticated.

### 6.2 Execution-instance plane

The trading engine may run:

- on the supported local execution host; or
- on that user's isolated remote single-tenant engine instance.

The execution instance owns the execution-side state required by its approved design, including broker runtime state and secret custody. A remote execution instance is not the central account service.

### 6.3 Central Account Authority

The central Account Authority remains authoritative for account identity, registered devices, sessions, revocation/recovery, entitlement/account security state and permitted non-sensitive account preferences.

It remains prohibited from:

- minting `ApprovedOrder`;
- arming Live;
- placing/canceling/modifying broker orders;
- storing broker credentials in the central account database;
- becoming a shared trading engine.

## 7. Remote secret custody

When the engine is remote:

- broker credentials/tokens exist only in that user's isolated engine instance-side secret store;
- credential material is encrypted at rest with KMS-backed key custody;
- exact provider/KMS product remains OPEN;
- raw secret values are not returned to normal mobile/web/desktop UI;
- central account database contains no broker credential plaintext/ciphertext copy intended for trading use;
- secret access and rotation are auditable;
- logs, telemetry, crash data, support bundles and backups obey secret-redaction rules.

## 8. Client-to-engine authentication

Mobile/web/desktop clients may access the dedicated engine through an authenticated, versioned API.

The design must provide:

- authenticated session/device binding appropriate to S2;
- authorization scoped to the owning user/engine instance;
- replay resistance for security-sensitive requests;
- rate limiting/abuse controls;
- audit correlation between client request and engine action;
- no unauthenticated public trading endpoint;
- fail-closed behavior on unverifiable identity/session evidence.

Exact API gateway/vendor/network topology is not frozen here.

## 9. Mobile notification/privacy rule

Mobile is now in scope.

Default push payload is minimal/redacted, for example:

`Action required — AlgoFortis kholo`

Detailed trade/position/order/P&L information is shown by default only inside an authenticated AlgoFortis client.

Telegram/email or other external channel may receive detailed content only after explicit opt-in under the notification/privacy policy.

No notification may contain credentials, tokens, raw broker secrets, or unrestricted raw account identifiers.

Native versus PWA remains OPEN.

## 10. Recovery and arming semantics

Execution-host restart, crash, reconnect, replacement, migration, or update cannot auto-arm Live.

A safety halt or `RECOVERY` state requires:

1. broker-truth reconciliation;
2. resolution of mismatches/unknown activity;
3. transition to the appropriate ready-for-resume state; and
4. explicit manual resume where required by `INV-15` and the frozen recovery policy.

A clean login, successful password fallback, successful step-up, cloud-account recovery, broker reconnect, or API reconnect is never sufficient by itself to resume/arm trading.

## 11. S2 qualification additions

GP-S2 / later security qualification must add evidence for:

### Password fallback
- valid password fallback authenticates only to its documented assurance level;
- password-only session cannot Arm Live;
- password-only session cannot mutate broker credentials;
- password-only session cannot enroll/revoke devices;
- password-only session cannot delete account;
- successful step-up enables only the action classes authorized by policy;
- Pause/Halt/Exit remain available without extra step-up to an otherwise authorized authenticated user;
- password hashes/secrets do not appear in logs/support artifacts;
- rate-limit/lockout flows are isolated;
- breached-password and credential-stuffing controls have qualified production design before release;
- no guessed production threshold is embedded merely to pass qualification.

### Remote execution API
- cross-user/cross-instance API access denied;
- authenticated client cannot bypass `RiskGateV2`;
- authenticated client cannot construct an executable approval directly;
- replayed sensitive request rejected/idempotently handled as required by the endpoint contract;
- unauthorized request cannot mutate engine/trading state;
- rate-limit/abuse controls verified;
- broker credential centralization absent;
- remote instance secret isolation verified;
- external/independent security test of the internet-facing engine API is required before the Live pilot gate.

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

- cloud provider or region;
- instance size/cost;
- native versus PWA;
- static-IP policy;
- current broker/SEBI/exchange production requirements;
- production password/rate-limit numeric constants.

These remain open or governed by their existing dated verification gates.
