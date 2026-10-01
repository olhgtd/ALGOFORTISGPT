# AlgoFortis V2 — S2 Account, Device & Session Gating Design

- **Date:** 2026-09-26
- **Status:** DESIGN APPROVED — WRITTEN SPEC FOR OWNER REVIEW
- **Track:** Platform/Account Track P2 → Sync Point S2 (`GP-S2`)
- **Depends on:** V1 auth/device/session baseline; ADR-016 / OD-V2-20, 21, 22, 23
- **Feeds:** Phase 6 Live Execution V2 qualification
- **Safety invariant:** Live remains `READ_ONLY / DISARMED`; S2 cannot place, cancel, modify, or arm an order.

## 1. Purpose

S2 provides a durable, server-authoritative account/device/session security gate that Phase 6 can consume without making cloud/account infrastructure a trading authority.

The goal is not to rewrite the proven V1 authentication/security system. The goal is to preserve its verified behavior behind explicit V2 contracts, replace demonstration/in-memory authority with durable server-authoritative state, define cloud-outage semantics, and produce `GP-S2` evidence for `INV-04` and `INV-19` plus revoke/recovery qualification.

S2 is complete only when a future Phase-6 consumer can ask, in a deterministic and auditable way, whether the current user/device/session is valid enough to satisfy the account/device prerequisite while remaining unable to derive Live ARM or broker-mutation authority from that answer.

## 2. Design intent and success criteria

### 2.1 Intended outcome

S2 must provide:

1. server-authoritative account, WebAuthn credential, device, session-family, revocation, and recovery state;
2. WebAuthn interactive authentication with strict RP-ID/origin validation;
3. a separate TPM/CNG-backed device identity key with DPAPI-protected fallback;
4. device possession proof and strict three-device quota with no silent eviction;
5. rotating, single-use refresh-token families with reuse detection and fail-closed family revocation;
6. explicit device revoke, all-session revoke, and high-assurance recovery;
7. same-PC reinstall identity preservation with cryptographic re-proof;
8. flow-isolated rate limiting for sensitive internet-facing account operations;
9. fail-closed cloud-outage behavior that preserves local protective safety;
10. a Device/Session Gate result usable by Phase 6 but structurally unable to arm or trade;
11. qualification evidence satisfying `GP-S2`, `INV-04`, and `INV-19`;
12. seams for the approved OD-V2-20/21/22/23 policies without prematurely implementing all Track-P3/S3 product features.

### 2.2 Explicit non-goals

S2 does not implement or authorize:

- a real broker adapter;
- real-money order placement/cancel/modify;
- Live ARM implementation;
- updater implementation;
- full entitlement implementation;
- telemetry backend implementation;
- production code signing;
- production-domain activation;
- broker credential centralization;
- strategy/trade-state cloud synchronization.

## 3. Authority and trust boundaries

### 3.1 Central Account Authority owns

The central account plane is authoritative for:

- user/account identity;
- WebAuthn public credentials and credential status;
- registered device records and public device keys;
- device revocation state;
- session/refresh-token family state;
- session revocation/reuse-detection state;
- recovery state;
- account-security audit/evidence;
- entitlement metadata/seams required by later Track P work;
- non-sensitive account preferences where permitted.

The central account plane does not own:

- broker credentials;
- broker sessions used for trading;
- strategies or proprietary strategy configuration;
- live positions/orders/trade ledgers;
- local RiskGate state;
- Paper/Live execution state;
- local protective-order state;
- order-placement authority.

### 3.2 Local Windows plane owns

The local client owns:

- the TPM/CNG device private key or DPAPI-protected software fallback;
- local session cache/material needed by the client;
- local safety and engine state;
- trading/audit state that remains local by architecture;
- broker credentials and broker runtime state;
- local recovery/safety mode when central authority is unavailable.

### 3.3 Non-negotiable trust rule

A central Account API response can satisfy an identity/device/session prerequisite. It cannot mint an `ApprovedOrder`, cannot set the Live engine ARMED latch, and cannot place/cancel/modify broker orders.

Cloud/account authority is authentication authority only, never trading authority.

## 4. Reuse versus new V2 work

### 4.1 Reuse/preserve from V1

S2 preserves the verified V1 semantics for:

- WebAuthn interactive login;
- separation of WebAuthn user credential and device identity key;
- TPM/CNG preferred device key;
- DPAPI software fallback;
- 15-minute access-token concept;
- rotating refresh token;
- refresh-token reuse detection;
- 30-day absolute / 7-day idle session-family policy already locked by V1 unless a later dated decision changes it;
- strict max-three-device rule;
- no silent device eviction;
- explicit device revoke;
- same-PC identity continuity;
- high-assurance recovery revoking sessions/devices;
- flow-isolated progressive rate limiting;
- account/security role boundaries.

### 4.2 New V2 hardening

S2 adds or formalizes:

- server-authoritative durable repository contracts instead of relying on in-memory/demo authority;
- explicit DeviceSessionGate contract and status/reason model;
- cloud-outage-to-local-mode mapping;
- architecture guard preventing account/auth modules from importing broker mutation/Live ARM authority;
- `GP-S2` deterministic qualification evidence;
- cross-user/tenant isolation evidence;
- explicit same-PC reinstall re-proof workflow;
- explicit production RP-ID/domain migration seam;
- OD-V2-20 versioned update-safe-window seam;
- OD-V2-21 clock-tamper-resistant entitlement-time seam;
- OD-V2-22 privacy/telemetry boundary;
- audit-failure fail-closed semantics for security-critical account mutations.

## 5. Proposed component architecture

### 5.1 Central components

#### `AccountRepository`
Durable account-plane persistence interface. Production implementation is server-side durable storage; tests may use deterministic in-memory/fake repositories.

Owns persistence for users, WebAuthn public credentials, registered devices/public keys, session families, revocation state, recovery state, and account-security audit references.

It must not expose broker/trading tables or local trading state.

#### `WebAuthnService`
Owns interactive registration/authentication ceremonies, challenge lifecycle, RP-ID/origin validation, replay prevention, credential status, and step-up rules.

#### `DeviceRegistry`
Owns registered-device records, device quota, revocation status, key binding metadata, and explicit replacement/re-enrollment transitions.

#### `DeviceProofVerifier`
Verifies a challenge signature against the registered public device key. It never receives the private key.

#### `SessionFamilyService`
Owns short-lived access-token/session-family semantics, rotating refresh tokens, expiry, reuse detection, and family revocation.

#### `RevocationService`
Coordinates explicit session/device revocation and all-device/all-session actions without weakening local protective behavior.

#### `RecoveryService`
Owns high-assurance recovery state transitions. Successful high-assurance recovery revokes all active session families and registered device trust, requiring fresh enrollment.

#### `AccountAuditSink`
Records security-critical account events with actor, user, device/session references, reason and version metadata. Security-critical mutation must fail closed if its required audit record cannot be written.

#### `RateLimitPolicy` / `RateLimitService`
Provides versioned, flow-isolated throttling/cooldown for login, WebAuthn challenge abuse, device proof/enrollment, refresh misuse, recovery, and other high-risk account endpoints.

Production thresholds are versioned policy/configuration. S2 must not invent new production numbers merely to satisfy tests; TEST_ONLY profiles are allowed in tests.

### 5.2 Local components

#### `AuthClient`
Transport/application client for the central account authority. It carries no broker mutation capability.

#### `DeviceIdentityProvider`
Local device-key abstraction preserving V1 semantics:

- preferred Windows TPM/CNG non-exportable P-256 key;
- DPAPI-protected software fallback;
- public-key fingerprint/device metadata;
- challenge signing;
- no private-key export to cloud.

#### `SessionCache`
Stores only the minimum local client session material needed for operation, using OS-protected storage where sensitive.

#### `DeviceSessionGate`
The single S2 evaluation boundary consumed by future application/Phase-6 preflight code.

It evaluates central authority response plus local device/session proof and returns a typed result. It does not arm Live and has no broker/order dependency.

#### `AccountSafetyModeMapper`
Maps account-authority availability/results into a local account-operation mode. In particular, it maps `AUTHORITY_UNAVAILABLE` to `LOCAL_SAFETY_ONLY`.

## 6. DeviceSessionGate contract

Conceptual contract:

```text
DeviceSessionGateResult
- schema_version
- user_id
- device_id
- session_family_id?
- status
- reasons[]
- authority_evidence_ref?
- evaluated_at
- audit_ref?
```

### 6.1 Status set

- `VALID`
- `REVOKED`
- `SESSION_EXPIRED`
- `DEVICE_UNTRUSTED`
- `RECOVERY_REQUIRED`
- `AUTHORITY_UNAVAILABLE`

`LOCAL_SAFETY_ONLY` is deliberately not a competing DeviceSessionGate status. It is a **runtime operating mode** selected by `AccountSafetyModeMapper` when the gate reports `AUTHORITY_UNAVAILABLE` or equivalent central-authority uncertainty.

This removes the earlier ambiguity between a detection result and an operating mode.

### 6.2 Meaning of `VALID`

`VALID` means the account/device/session prerequisite is satisfied at evaluation time.

It explicitly does not mean:

- ARMED;
- Live eligible;
- broker connected;
- reconciliation clean;
- RiskGate approved;
- permission to place/cancel/modify an order.

Future Phase 6 must combine S2 validity with its own independent Live-state, reconciliation, broker, risk, protection, host, and Owner-controlled requirements.

## 7. Enrollment and login flows

### 7.1 Existing-device interactive login

1. Start WebAuthn authentication ceremony.
2. Validate challenge, RP-ID, origin, credential state, and user/account state.
3. Request device possession proof when policy requires binding/refresh of machine trust.
4. Verify signature against the server-registered public device key.
5. Validate device is registered and not revoked.
6. Create/rotate the device-bound session family as applicable.
7. Audit success/failure.
8. Return typed account/session result.

### 7.2 New-device enrollment

1. User completes interactive WebAuthn authentication/step-up.
2. Central authority validates account eligibility and current device count.
3. Local `DeviceIdentityProvider` generates or discovers a local private key.
4. Client sends only public device identity/proof material.
5. Central authority verifies challenge possession proof.
6. Enforce hard maximum of three active registered devices.
7. If quota is full, reject; never silently evict an older device.
8. Register device/public key and audit the action.
9. Create a device-bound session family.

### 7.3 Same-PC reinstall identity preservation

This flow is an explicit S2 requirement carried forward from V1.

1. Normal uninstall/reinstall preserves `%LOCALAPPDATA%\AlgoFortis\Security\DeviceIdentity\` and the underlying TPM/CNG key where the V1 preservation contract applies.
2. On reinstall/relaunch, `DeviceIdentityProvider` attempts to rediscover the existing device identity/key.
3. The central authority returns/recognizes the previously registered public device identity record after interactive user authentication.
4. The server issues a fresh possession challenge.
5. The local client signs with the rediscovered private key.
6. Server verifies the proof against the previously registered public key.
7. Successful proof restores the same logical device identity without consuming a new device quota slot.
8. A new session family may then be established under current policy.
9. If the local key is missing, corrupt, inaccessible, mismatched, or cannot prove possession, the client MUST fail closed and use the normal fresh-device enrollment path. It MUST NOT claim continuity based only on hostname, MAC address, disk ID, or cached metadata.

## 8. Session and refresh-token lifecycle

### 8.1 Normal rotation

1. Valid refresh token is presented over the authenticated transport.
2. Server identifies the session family.
3. Verify family/device/account not revoked and within current lifetime policy.
4. Mark presented refresh token consumed.
5. Issue a new refresh token and short-lived access token.
6. Persist/audit rotation atomically enough that reuse detection remains authoritative.

### 8.2 Refresh-token reuse

If a previously consumed refresh token is presented:

1. classify as reuse/security incident;
2. revoke the affected session family immediately;
3. deny issuance of replacement tokens;
4. invalidate future use of that family;
5. record an auditable security event;
6. require re-authentication/appropriate recovery under policy.

A reused token must never be treated as an ordinary expired token that can silently retry.

## 9. Device/session revocation and recovery

### 9.1 Explicit device revoke

- server marks device revoked;
- active/future account sessions bound to it can no longer renew as allowed by policy;
- future `DeviceSessionGate` returns a fail-closed result;
- local protective trading safety is not forcibly disabled by the account plane;
- any future ARM eligibility requires a valid, non-revoked device/session plus all Phase-6 conditions.

### 9.2 All-session revoke

All active session families for the user are revoked server-side. Existing local protective behavior continues, but fresh sensitive account operations fail until re-authentication.

### 9.3 High-assurance recovery

1. Verify the approved high-assurance recovery proof.
2. Revoke all active session/refresh families.
3. Revoke/purge all registered device trust for the user under the recovery policy.
4. Clear trusted account/device state that must not survive a credential-compromise recovery.
5. Consume single-use recovery proof where applicable.
6. Audit the recovery.
7. Require fresh interactive authentication and fresh device enrollment/re-binding.

Recovery cannot auto-arm Live or authorize broker mutation.

## 10. Flow-isolated rate limiting and brute-force resistance

S2 is internet-facing security authority, so GP-S2 cannot pass without rate-limit qualification.

### 10.1 Independent flows

At minimum, rate limiting must distinguish:

- interactive login/WebAuthn initiation and verification;
- device proof verification;
- new-device enrollment/step-up;
- refresh-token misuse/rotation abuse;
- recovery requests/proof verification;
- expensive/high-risk account operations.

Attacking one flow must not consume the entire recovery path or create a global denial-of-service lockout across unrelated flows.

### 10.2 Policy requirements

- thresholds/cooldowns are versioned policy/configuration;
- test profiles may use TEST_ONLY values;
- production numeric thresholds are not guessed in code;
- lockout/throttle decisions are auditable where appropriate;
- successful verification resets or advances counters according to the frozen policy;
- distributed/server implementation must make counters authoritative enough to prevent trivial bypass by process restart;
- rate limiting is defense-in-depth and does not replace credential/device cryptographic verification.

## 11. Cloud/auth outage semantics

### 11.1 Detection and mapping

When the central authority cannot be reached or its result cannot be verified:

1. `DeviceSessionGate` returns `AUTHORITY_UNAVAILABLE` with an explicit reason.
2. `AccountSafetyModeMapper` immediately maps that result to local operating mode `LOCAL_SAFETY_ONLY`.

Therefore the two terms are not redundant:

- `AUTHORITY_UNAVAILABLE` = evaluation result/reason from the account gate;
- `LOCAL_SAFETY_ONLY` = local runtime operating mode used while authority is unavailable/uncertain.

### 11.2 Behavior in `LOCAL_SAFETY_ONLY`

Continue:

- already-running local protective logic;
- local RiskGate hard safety for existing local operation;
- reconciliation/position monitoring needed to preserve safety;
- local audit/incident evidence where available;
- safe read-only local access required to understand existing positions/state.

Fail closed / block:

- new login;
- new-device enrollment;
- recovery changes;
- entitlement changes requiring authority;
- security-sensitive account mutations;
- fresh future ARM eligibility;
- any action that requires a new central trust assertion.

### 11.3 Authority recovery

When connectivity returns:

- central authority must be revalidated;
- device/session state must be re-evaluated;
- revocation/recovery changes that occurred remotely must be honored;
- returning to `VALID` account state does not auto-arm and does not by itself restore trading-entry permission;
- Phase-6 recovery/reconciliation/host/risk rules remain independent.

This is the S2 proof target for `INV-19`.

## 12. Cross-user / tenant isolation

The central account service must enforce user/account ownership at its repository/application boundary.

Qualification must prove:

- user A cannot list, read, revoke, or mutate user B devices;
- user A cannot use user B session family or recovery state;
- a valid device proof for one user/account cannot be replayed as another user's device proof;
- Owner/Admin authority follows the frozen role model and is not inferred from client input;
- repository queries for security objects are scoped by authoritative account/user ownership, not untrusted caller-supplied IDs alone.

This is the core `INV-04` evidence.

## 13. Audit and failure semantics

Security-critical events include at minimum:

- credential registration/revocation;
- device registration/revocation/re-binding;
- quota rejection;
- device-proof failure;
- session-family creation/revocation;
- refresh reuse detection;
- high-assurance recovery;
- authority outage/recovery transitions where useful;
- rate-limit security events;
- cross-user authorization rejection;
- production-domain re-enrollment migration actions.

If a security-critical mutation requires audit evidence and the required audit write cannot be committed, the mutation fails closed. Read-only validation may return a failure/uncertainty result with local diagnostic evidence, but must not pretend a mutation succeeded.

## 14. OD-V2-20 seam — versioned update safe window

S2 does not implement the updater, but the Track-P authority contract must prevent future code from hard-coding production timing.

A versioned `UpdateSafeWindowPolicy` or equivalent must be capable of carrying:

- `policy_id`;
- `version`;
- allowed engine states;
- open-position rule;
- session-calendar reference;
- applicability/environment metadata;
- effective-version/audit identity.

No production market time, minute count, or schedule is embedded as a universal constant merely to satisfy tests.

If the required policy is missing, invalid, stale, or inapplicable, update/restart/migration is deferred. Never auto-arm after an update/restart.

## 15. OD-V2-21 seam — 7-day offline entitlement with clock-tamper resistance

S2 does not implement the full entitlement service, but the account/session design must preserve a time-evidence contract that makes wall-clock-only offline validation unacceptable.

Conceptual time evidence:

```text
EntitlementTimeEvidence
- lease_id / lease_signature_ref
- issued_server_time
- lease_expiry_server_time
- last_successful_server_check_in
- local_monotonic_anchor
- monotonic_elapsed
- boot/session identity
- wall_clock_observation
- validation_reasons[]
```

Rules:

1. lease is cryptographically signed/verifiable;
2. V1 seven-day offline-grace policy is preserved;
3. wall clock alone cannot extend validity;
4. server check-in + monotonic elapsed time are primary anti-rollback inputs where available;
5. backward wall-clock jump or contradictory evidence is a tamper/uncertainty signal;
6. invalid/lost anchors fail closed for new entitlement-dependent operations rather than creating extra lease time;
7. protective exits/reconciliation/read-only safety access are not disabled because entitlement authority is unavailable or expired.

The implementation plan must define exact persistence/boot semantics without pretending monotonic time survives reboot. The design intentionally treats reboot or lost monotonic continuity as additional evidence requiring conservative reconciliation with signed server/check-in state.

## 16. OD-V2-22 seam — telemetry/privacy

S2's account service may emit only the minimum security/operational evidence needed for operation and audit.

- telemetry remains opt-in under the frozen policy;
- no broker credentials/tokens;
- no proprietary strategy body;
- no unrestricted trade logs or balances;
- support bundles sanitize first;
- retention/purpose are versioned policy;
- production retention numbers are not guessed in S2;
- telemetry failure cannot weaken trading safety.

Account-security audit required for correctness is distinct from optional product telemetry and must not be conflated with opt-in telemetry.

## 17. OD-V2-23 seam — production publisher/domain and WebAuthn migration

SemVer 2.0.0 remains the release-version scheme and `/api/v1/` remains the current independently versioned API family.

Exact publisher identity and canonical production domain remain `PENDING_EXTERNAL` until finalized before S3/release packaging.

### 17.1 Development/staging rule

- development/staging WebAuthn uses explicit non-production RP-ID/origin configuration;
- credentials registered for dev/staging are not production credentials;
- no silent RP-ID rewrite or credential promotion.

### 17.2 Production-domain finalization migration

When the real production domain is finalized:

1. freeze canonical production RP-ID and allowed origins;
2. mark development/staging WebAuthn credentials ineligible for production authentication;
3. require fresh production WebAuthn registration;
4. rediscover the existing separate device identity key if present;
5. require fresh possession proof;
6. explicitly re-bind/re-enroll that device identity to the production authority;
7. issue a new production session family only after both user and device verification succeed;
8. if the device key is missing/corrupt/unverifiable, fail closed and perform full fresh-device enrollment.

The device private key does not become invalid merely because the WebAuthn RP-ID changes; the trust binding must nevertheless be re-established explicitly.

## 18. Persistence model boundaries

S2 requires durable server-authoritative records conceptually equivalent to:

- `AccountRecord`
- `WebAuthnCredentialRecord`
- `RegisteredDeviceRecord`
- `SessionFamilyRecord`
- `RefreshTokenState` / consumed-token evidence
- `RecoveryStateRecord`
- `SecurityIncidentRecord`
- `AccountAuditRecord`
- `PolicyVersionRef`

Detailed SQL/storage schema belongs in the implementation plan and migrations, not this design. The important design rules are:

- foreign keys/ownership prevent cross-user object escape;
- revocation is durable;
- restart does not clear authoritative counters/state;
- token secrets are not stored plaintext when hash/verifier storage suffices;
- private device key is never stored server-side;
- broker/trading state is not added to the account database.

## 19. Dependency rules

### 19.1 Allowed

S2 account/security application code may depend on:

- account-domain contracts;
- cryptographic/WebAuthn ports;
- durable account repository port;
- Clock/monotonic/time-evidence abstractions;
- AuditSink;
- configuration/policy ports;
- HTTP/transport adapters at the outer layer;
- OS key-store/device-key adapters on the local client side.

### 19.2 Forbidden

S2 domain/application modules must not import or call:

- concrete broker adapters;
- `BrokerPort.place/cancel/modify` mutation paths;
- RiskGate private approval constructors;
- Live ARM implementation/state mutation;
- Paper execution adapters;
- strategy execution logic;
- order placement/router mutation paths.

Static architecture checks must enforce these boundaries.

## 20. GP-S2 qualification strategy

`GP-S2` is not passed because files exist. It requires focused evidence plus preserved broader regression.

### 20.1 Required focused tests

#### WebAuthn
- valid registration/authentication;
- replayed challenge rejected;
- wrong RP-ID rejected;
- wrong origin rejected;
- revoked credential rejected;
- development/staging credential cannot silently become production credential.

#### Device identity
- TPM/CNG provider contract where environment permits or deterministic adapter/fake in CI;
- DPAPI fallback contract;
- public-key possession proof;
- private key never transmitted/stored centrally;
- strict three-device quota;
- fourth device rejected;
- no silent eviction;
- explicit device revoke;
- revoked device fails the gate.

#### Same-PC reinstall
- normal reinstall rediscovers same logical device identity/key;
- server challenge re-proof succeeds against existing registered public key;
- successful reinstall does not consume a new device quota slot;
- missing key fails closed to fresh enrollment;
- corrupt/unverifiable key fails closed;
- MAC/hostname/local metadata without private-key proof cannot restore trust.

#### Sessions
- short-lived access-token validation;
- refresh rotation;
- consumed refresh replay → entire family revoked;
- revoked family cannot rotate;
- idle/absolute expiration according to frozen policy;
- explicit single-family revoke;
- all-user-session revoke.

#### Recovery
- high-assurance recovery proof accepted once;
- replay rejected;
- all session families revoked;
- all registered device trust revoked/purged per policy;
- fresh enrollment required afterward.

#### Rate limiting / brute force
- login flow throttles/locks according to TEST_ONLY policy;
- device-proof/enrollment brute-force flow throttles independently;
- recovery brute-force flow throttles independently;
- refresh misuse flow protection does not disable unrelated recovery flow;
- one flow's attack cannot consume all independent security flows;
- rate-limit state survives relevant service/repository restart in durable-integration tests;
- no guessed production numeric thresholds embedded in domain code.

#### Cross-user isolation — `INV-04`
- cross-user device read denied;
- cross-user device revoke denied;
- cross-user session-family access denied;
- cross-user recovery state denied;
- caller-supplied foreign user/device IDs cannot escape authoritative ownership scope.

#### Cloud outage — `INV-19`
- central authority timeout/unreachable → `AUTHORITY_UNAVAILABLE`;
- mapper → `LOCAL_SAFETY_ONLY`;
- local protective safety continues;
- new login/enrollment/recovery/account mutation blocked;
- fresh ARM eligibility blocked;
- reconnect requires revalidation;
- reconnect never auto-arms.

#### Audit
- required security mutation audit succeeds and mutation commits;
- required audit failure prevents security-critical mutation from being reported/committed as successful;
- sensitive secrets/tokens not emitted.

#### OD seams
- hard-coded production update safe-window values rejected by static/config guard;
- missing update policy defers update decision seam;
- entitlement contract rejects wall-clock-only extension;
- backward clock/tamper evidence produces fail-closed uncertainty;
- production-domain migration requires new WebAuthn enrollment + device re-proof/re-bind.

### 20.2 Architecture/static tests

Static guard must prove account/S2 modules cannot import broker mutation, Live ARM, Paper execution, or strategy execution authority.

A contract-level test must prove `DeviceSessionGateResult(status=VALID)` cannot itself create or obtain an executable `ApprovedOrder` or transition Live to ARMED.

### 20.3 Regression expectations

- existing V1 auth/security/recovery regression remains green;
- V2 Phase 0–5 safety/golden regression remains preserved;
- no weakening of Live `READ_ONLY / DISARMED` defaults;
- deterministic/security tests run in both supported Windows CI environments where applicable.

### 20.4 GP-S2 evidence bundle

The S2 gate evidence should eventually record:

- exact source SHA;
- exact workflow run IDs/jobs;
- focused S2 test results;
- `INV-04` result;
- `INV-19` result;
- revoke/recovery results;
- same-PC reinstall/re-proof result;
- rate-limit/brute-force isolation results;
- architecture/static guard result;
- preserved V1 auth regression result;
- preserved V2 golden/full regression result;
- explicit statement that S2 has no broker mutation/ARM authority;
- explicit statement that Live remains `READ_ONLY / DISARMED`.

## 21. Failure behavior summary

| Condition | Gate/result | Local/runtime behavior |
|---|---|---|
| Valid user/device/session | `VALID` | S2 prerequisite satisfied only; no ARM/trade implication |
| Device revoked | `REVOKED` | Account-sensitive actions fail closed; fresh ARM eligibility impossible |
| Session expired/revoked | `SESSION_EXPIRED` / `REVOKED` | Re-auth required; local protective safety not disabled |
| Device key missing/corrupt | `DEVICE_UNTRUSTED` | Fresh enrollment required; no metadata-only trust recovery |
| High-assurance recovery active | `RECOVERY_REQUIRED` | All old trust invalid; fresh enrollment required |
| Central authority unreachable/unverifiable | `AUTHORITY_UNAVAILABLE` | Map to `LOCAL_SAFETY_ONLY`; preserve local safety, block new account trust/ARM eligibility |
| Rate limit exceeded | flow-specific rejection | Only affected flow throttled according to policy; unrelated recovery path preserved |
| Required audit write fails on security mutation | fail closed | Mutation not treated as successful |
| Production RP-ID changes | old dev/staging WebAuthn ineligible | Fresh production WebAuthn + device re-proof/re-bind |

## 22. Implementation constraints

The later implementation plan must follow these constraints:

1. no big-bang rewrite of V1 auth/security modules;
2. wrap/reuse stable V1 behavior behind V2 contracts;
3. extract pure domain logic from transport/storage where needed, but avoid unrelated refactors;
4. use deterministic injectable time/ID providers for new domain logic;
5. TDD RED→GREEN for every slice;
6. test with deterministic fakes for Windows hardware/cloud dependencies where CI cannot use real hardware/services;
7. never weaken production behavior to satisfy CI;
8. no hard-coded guessed production thresholds;
9. migrations additive and rollback-aware;
10. no broker/Live mutation code added as part of S2.

## 23. Suggested implementation decomposition for the future plan

The implementation plan should split S2 into small verified slices roughly along these boundaries:

1. S2 contracts/status/mode mapping + architecture guard;
2. durable account/device/session repository schema and ports;
3. V1 device identity adapter integration + possession proof;
4. WebAuthn server-authority service and RP-ID/origin policy;
5. session-family rotation/reuse/revocation;
6. strict device quota + revoke + same-PC reinstall/re-proof;
7. high-assurance recovery;
8. isolated rate limiting/brute-force policy;
9. cloud-outage `AUTHORITY_UNAVAILABLE` → `LOCAL_SAFETY_ONLY` integration;
10. OD20/21/22/23 policy seams and production-domain migration contract;
11. `INV-04` / `INV-19` integration qualification;
12. dual-Windows/full-regression/GP-S2 evidence.

This is decomposition guidance only. Exact file names and slice ordering are finalized by the implementation plan after this written spec is reviewed.

## 24. Final safety statement

S2 establishes who the account authority trusts; it does not decide whether AlgoFortis may trade.

A valid account/device/session is only one future Phase-6 prerequisite. Broker truth, local exclusivity, reconciliation, host health, protective-order support, regulatory/broker verification, RiskGate approval, Live state, and explicit arming governance remain separate controls.

No S2 state, cloud response, device proof, session token, entitlement lease, recovery success, reconnect, update, or domain migration may directly arm Live or create a broker mutation.

**Live remains `READ_ONLY / DISARMED`.**
