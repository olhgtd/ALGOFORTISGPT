# Manual V1 Security Recheck

This document captures security controls from the manually-built V1 that are valuable enough to preserve or re-implement under current V2 authority.

## High-value controls to preserve

### Local credential protection

- Broker API credentials were protected with Windows DPAPI (`CryptProtectData`) in the V1 credential-vault design.
- SQLite stored opaque credential references rather than plaintext broker secrets.
- Credential representations were masked.
- API projections exposed presence/status rather than raw secret values.
- Final secret scan evidence recorded `0` real plaintext secret leaks and `0` frontend secret leaks.

**Current use:** preserve the principle and tests. Current AlgoFortis must continue to keep broker secrets local and outside logs, backups, central account storage and UI projections.

### Local password authentication

The final LOCAL_PRIVATE desktop flow used:

- `hashlib.scrypt`;
- 16-byte cryptographically-random salt;
- `N=16384`, `r=8`, `p=1`, `dklen=64`;
- `hmac.compare_digest` for verification;
- no plaintext password persistence/log/audit/API exposure;
- one-time bootstrap token consumed atomically.

**Current use:** treat this as a proven local implementation reference, not an automatic replacement for the current V2/anywhere-login account contract. Reassess parameters and step-up rules against the current security specification before production reuse.

### Session/token controls

Useful V1 controls:

- short-lived access-token model;
- rotating refresh-token families;
- refresh-token reuse → family invalidation;
- 7-day idle / 30-day absolute expiry foundation;
- server/local authority checks according to deployment profile;
- generic authentication failure responses to reduce account enumeration.

**Current use:** preserve behavior through current account/session contracts and regression tests.

### Device and recovery controls

Useful V1 controls:

- max 3 registered devices;
- no silent device eviction;
- 24-hour single-use activation lifecycle;
- 8 single-use recovery codes in the local security policy;
- high-assurance recovery revokes active sessions/trusted device state;
- same-PC reinstall identity continuity;
- distinct hardware/passkey policies for high-assurance Owner recovery.

**Current use:** preserve semantics but route authority through the current V2 account/device architecture.

### WebAuthn/FIDO2

Preserved V1 strengths:

- RP/origin validation;
- production profiles reject invalid HTTP/origin/domain combinations;
- passkey/hardware-key foundations;
- WebAuthn code remained in the source even when LOCAL_PRIVATE used local password auth.

**Current use:** adapt to current interactive-auth and device-binding contracts. Do not infer that LOCAL_PRIVATE password mode itself provides roaming/central identity.

### Authorization

- Owner/User separation via RBAC and middleware;
- no unauthenticated mutation route was accepted in final certification evidence;
- single Super Owner invariant in local-private V1;
- live broker mutation denied on 18/18 mapped routes.

**Current use:** preserve negative tests and least privilege. Current V2 role/capability contracts remain authoritative.

### Backup/restore security

V1 hardening worth preserving:

- explicit exclusion of activation material, credentials, private keys, TPM/device/WebAuthn private material from portable backups;
- archive traversal (`..`, absolute path, drive-letter/colon) rejection;
- duplicate archive member rejection;
- undeclared-category rejection;
- SHA-256 manifest validation;
- SQLite WAL-safe operational backup plus integrity check.

**Current use:** high-priority salvage. `AlgoFortisBackup/v1` should be extended only through compatible, reviewed changes.

### Local filesystem / deployment security

Useful V1 design:

- immutable application binaries in `Program Files\AlgoFortis`;
- mutable runtime/user state under `%LOCALAPPDATA%\AlgoFortis`;
- private Windows ACL handling;
- symlink/junction/path hardening checks;
- data/secrets remain local by default.

## Security controls that must NOT be copied blindly

1. **LOCAL_PRIVATE local password authority** must not overwrite current anywhere-login/device/session architecture.
2. **Old V1 RiskGate/order/execution code** must not become a parallel execution authority.
3. **Old broker mutation code paths** must remain non-authoritative and disabled unless separately qualified under V2.
4. **Old DB files** are migration/test evidence only, never current runtime authority.
5. **Old rate-limit wiring** must be rechecked at actual HTTP/service boundaries; historical audits found earlier periods where rate-limit components existed but were not yet wired everywhere.
6. **Unsigned development installers** are evidence of packaging flow, not production supply-chain trust.

## Fresh revalidation checklist before adopting a V1 security component

For every security-related salvage item:

- [ ] identify exact old source path and current destination contract;
- [ ] verify no raw secret/test credential is copied;
- [ ] add/port negative AuthZ tests first;
- [ ] verify fail-closed behavior on missing/corrupt state;
- [ ] verify logs/audit/support bundles redact secrets;
- [ ] verify backup excludes secret/private-key material;
- [ ] verify current role/device/session authority is not bypassed;
- [ ] verify Paper cannot reach real broker mutation;
- [ ] verify Live remains READ_ONLY/DISARMED;
- [ ] run current V2 regression/security gates before merge consideration.

## Security bottom line

The manually-built V1 contains substantial reusable security engineering. Preserve the controls and tests, but integrate them through current V2 authority boundaries rather than restoring old authority graphs wholesale.
