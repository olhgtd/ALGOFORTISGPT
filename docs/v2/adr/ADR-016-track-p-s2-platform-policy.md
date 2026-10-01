# ADR-016 — Track P / S2 Platform Policy

- **Date:** 2026-09-26
- **Status:** ACCEPTED / OWNER-FROZEN
- **Decisions:** OD-V2-20, OD-V2-21, OD-V2-22, OD-V2-23
- **Scope:** Track P1 decisions feeding P2 account service and GP-S2 device/session qualification
- **Safety invariant:** Live remains `READ_ONLY / DISARMED`; this ADR grants no broker-mutation or arming authority.

## Context

Track P2 provides the central account/device/session authority required by sync point S2. V1 already froze and implemented much of the underlying security model: signed updates/rollback, a 7-day offline entitlement lease, privacy-preserving telemetry, SemVer/API versioning, WebAuthn interactive authentication, separate device identity keys, strict device quota, rotating session families, and high-assurance recovery.

The Owner approved carrying those V1 decisions forward rather than redesigning them, with three V2 hardening refinements:

1. update safe windows are versioned policy, never hard-coded production timing;
2. offline entitlement validity cannot depend on wall-clock time alone;
3. production-domain finalization requires an explicit WebAuthn re-enrollment/device re-binding migration.

## OD-V2-20 — Auto-update and release channel

**Decision: Option A — carry forward signed updates and rollback, with a versioned safe-window policy.**

1. Release artifacts and update manifests MUST be signed and integrity-checked.
2. Security-critical updates MAY be mandatory, but application/restart/migration MUST occur only when the resolved safe-window policy permits it.
3. Non-critical updates MAY be deferred.
4. Rollout SHOULD support staging/canary behavior and a tested rollback path.
5. Update/restart/migration MUST NOT occur while the trading engine is ACTIVE or while open positions make the transition unsafe.
6. Update/restart MUST NEVER auto-arm Live.
7. Safe-window timing MUST NOT be embedded as production constants in application code.
8. The update policy MUST reference a versioned `UpdateSafeWindowPolicy` (or equivalent) containing at minimum a policy identifier/version, allowed engine states, open-position rule, session-calendar reference, and applicability metadata.
9. Missing, invalid, stale, or inapplicable safe-window policy MUST fail closed by deferring the update; code MUST NOT invent a production timing window.

## OD-V2-21 — Licence / entitlement

**Decision: Option A — preserve the V1 signed 7-day offline entitlement model and harden it against clock tamper.**

1. Offline entitlement remains a signed, time-boxed lease with V1's 7-day validity policy.
2. New activation/renewal operations fail closed when required authority cannot be verified.
3. Licence/entitlement expiry or cloud outage MUST NOT disable protective exits, reconciliation, local position monitoring, or read-only access needed for safety.
4. Offline validity MUST NOT be derived from wall-clock time alone.
5. Validation MUST combine signed server-issued time evidence, the last successful server check-in, and monotonic elapsed time for the current boot/session where available.
6. Wall-clock movement MAY be used as supporting/tamper evidence but MUST NOT by itself extend the lease.
7. A suspicious backward clock jump, contradictory time evidence, lost/invalid monotonic anchor, or other uncertainty MUST produce an explicit fail-closed entitlement state such as `ENTITLEMENT_TIME_UNCERTAIN` for entitlement-dependent new operations.
8. The full entitlement implementation remains Track P3/S3 scope; S2 must preserve and test the contract/seam needed to prevent later wall-clock-only implementations.

## OD-V2-22 — Telemetry and privacy

**Decision: Option A — preserve opt-in, minimize data, sanitize first.**

1. Telemetry is opt-in unless a later dated policy explicitly changes the product model.
2. Permitted operational telemetry is limited to the minimum needed for reliability/security, such as app version, update state, coarse health, and scrubbed crash signatures.
3. Strategies, prompts containing proprietary strategy logic, broker credentials/tokens, unrestricted trade logs, balances, and other unnecessary trading content MUST NOT be transmitted as telemetry.
4. Support bundles MUST sanitize/redact sensitive content before export.
5. Retention and purpose MUST be documented and versioned; production retention numbers MUST NOT be guessed merely to complete a build gate.
6. Telemetry availability MUST NOT become a trading-safety dependency.

## OD-V2-23 — Publisher, version scheme, and canonical production domain

**Decision: Option A — preserve SemVer/API versioning; publisher/domain remain externally pending until release preparation.**

1. Product releases use SemVer 2.0.0.
2. HTTP/API contracts remain independently versioned (current family `/api/v1/`) and migrations remain explicitly versioned.
3. Exact legal publisher identity remains `PENDING_EXTERNAL` until the legal/signing identity is finalized.
4. Exact canonical production domain remains `PENDING_EXTERNAL` until it is purchased/finalized.
5. S2 development and qualification MAY use explicitly non-production development/staging RP-ID/origin configuration; such credentials MUST NOT be silently promoted to production.
6. Before S3/release packaging, the production publisher identity and canonical production domain MUST be frozen.
7. Because WebAuthn credentials are RP-ID/origin scoped, production-domain finalization MUST trigger an explicit migration: fresh production WebAuthn registration is required; development/staging WebAuthn credentials are not migrated as production credentials.
8. The separate TPM/CNG or DPAPI device identity key is not automatically invalidated by RP-ID change. If the key is still present and valid, the client MUST re-prove possession and the central authority MUST explicitly re-bind/re-enroll that device identity under the production authority.
9. Missing/corrupt local device key fails closed and requires fresh device enrollment.

## S2 carry-forward invariants from V1

S2 must preserve, not weaken:

- WebAuthn interactive user authentication and separate device identity key;
- preferred TPM/CNG non-exportable device key with DPAPI-protected fallback;
- strict maximum of three registered devices with no silent eviction;
- 15-minute access-token model and rotating single-use refresh-token families;
- refresh-token reuse detection revoking the affected family;
- server-side device/session revocation;
- high-assurance recovery revoking all sessions and registered devices;
- same-PC reinstall identity preservation: the local device identity survives normal uninstall/reinstall, is rediscovered, and possession is re-proved against the server's registered public key; missing/corrupt key fails closed to fresh enrollment;
- flow-isolated rate limiting/cooldowns for login, device-proof/enrollment verification, recovery, and other sensitive account flows;
- cloud/auth outage never loosens or stops local protective safety.

## `AUTHORITY_UNAVAILABLE` and `LOCAL_SAFETY_ONLY`

These names describe different layers and MUST NOT be implemented as competing independent meanings:

- `AUTHORITY_UNAVAILABLE` is a **DeviceSessionGate evaluation result/reason** indicating the central account authority cannot currently be reached or verified.
- The local runtime maps that result to the **operating mode `LOCAL_SAFETY_ONLY`**.
- In `LOCAL_SAFETY_ONLY`, already-running local protective logic, risk monitoring, reconciliation, and position monitoring continue; new login, enrollment, recovery, entitlement changes, security-sensitive account mutations, and any fresh future ARM eligibility fail closed.
- Authority recovery does not auto-arm and does not by itself restore trading-entry permission; normal revalidation/recovery rules still apply.

## GP-S2 consequences

GP-S2 may be considered technically ready only when evidence covers at minimum:

- durable server-authoritative account/device/session state;
- WebAuthn RP-ID/origin validation;
- device-key possession proof;
- strict device quota/no silent eviction;
- same-PC reinstall rediscovery and re-proof, plus missing/corrupt-key fail-closed behavior;
- refresh rotation and reuse-detection family revocation;
- explicit device revoke and all-device revoke;
- high-assurance recovery;
- isolated brute-force/rate-limit tests for login, device-proof/enrollment, recovery, and other sensitive flows;
- cross-user/tenant isolation (`INV-04`);
- cloud/auth outage behavior (`INV-19`) including `AUTHORITY_UNAVAILABLE` → `LOCAL_SAFETY_ONLY` mapping;
- proof that auth/account components cannot place, cancel, modify, or arm orders;
- audit failure on security-critical account mutation fails closed;
- production RP-ID migration/re-enrollment contract;
- entitlement clock-tamper contract;
- no hard-coded production update safe-window values.

## Scope boundaries

This ADR does **not** implement or authorize:

- a real broker adapter;
- Live ARM/mutation;
- the full updater client/service;
- the full entitlement service;
- the full telemetry backend;
- production code signing;
- production-domain activation.

Those remain in their respective later Track-P/Phase scopes.
