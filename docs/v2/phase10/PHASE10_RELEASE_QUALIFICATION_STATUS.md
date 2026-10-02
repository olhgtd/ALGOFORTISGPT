# Phase 10 — Release Qualification Status

- **Date:** 2026-10-02
- **Scope:** Track-P S3/P4 technical implementation feeding Phase 10
- **Current gate:** **G10: BLOCKED**
- **Safety state:** Live remains **READ_ONLY / DISARMED**. This work grants no broker mutation or ARM authority.

## What this branch implements

The existing V1/Track-P foundations are upgraded rather than replaced:

1. UpdateService now requires signature verification for both the update manifest and installer payload, then resolves application through the existing versioned UpdateSafeWindowPolicy seam. Missing verification or policy evidence fails closed. ACTIVE state, unsafe open-position state, or policy-reference mismatch blocks application. Updates never auto-arm Live.
2. EntitlementLeaseManager now requires a signed lease plus S2 EntitlementTimeEvidence. There is no wall-clock-only validity fallback. Missing or contradictory monotonic/server-time evidence fails closed as ENTITLEMENT_TIME_UNCERTAIN, while protective safety and user-data export remain available.
3. Operational telemetry is deny-by-default. A frozen TelemetryPrivacyPolicy must explicitly opt in and authorize the operational data class before a heartbeat can be built. Support bundles remain explicit sanitized exports.
4. Existing AlgoFortisBackup/v1 backup/restore and LocalAppData preservation are retained and included in S3 qualification evidence.
5. Release packaging is hardened so a signed release requires valid Authenticode signatures for both the staged AlgoFortis.exe and final installer. Signature failure is fatal in release mode; unsigned packages are explicitly development/qualification-only. Person-specific build paths were removed.

## What this branch does not claim

This branch is **technical S3/P4 preparation**, not a G10 release approval and not a real-money Live authorization.

The following controlling blockers remain open or external:

- **OD-V2-18 — Live pilot policy:** OPEN. Capital/lot/session/stop/monitoring policy must be frozen by the Owner before any real-money pilot can be considered.
- **OD-V2-26 — Release-qualification thresholds:** OPEN. Soak length, drift tolerance, performance baselines and severity thresholds require Owner freeze.
- **OD-V2-23 external release identity:** exact legal publisher identity and canonical production domain remain PENDING_EXTERNAL in the controlling decision register. Production WebAuthn re-enrollment/device re-binding must follow domain finalization.
- **Production code-signing material:** certificate/private-key custody and timestamp authority are external release inputs. Test-only signatures used by CI are not production release signatures.
- **External legal/security evidence:** any still-required qualified legal review and independent security/release evidence remain external gates; software tests do not substitute for them.
- **Release Candidate freeze and Owner sign-off:** cannot occur until the above gates and the complete Test & Release Plan evidence set are satisfied.

## Qualification semantics

CI for this work may report **S3 technical qualification PASS** when deterministic tests and cross-Windows evidence agree. It must not emit G10=PASS.

A production G10 decision requires all canonical Phase-10 entry/exit gates, external release identity/signing evidence, closed P0/P1 production-critical findings, frozen OD-V2-18/26, archived evidence bundle, and explicit Owner sign-off.

## Preserved invariants

- RiskGateV2 remains the sole ApprovedOrder authority.
- Account/update/entitlement/telemetry components cannot place, modify, cancel or arm orders.
- Missing authority/evidence fails closed.
- Update/restart never auto-arms.
- Live remains **READ_ONLY / DISARMED** until a separately authorized future release changes that state.
