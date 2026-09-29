# AlgoFortis V2 — Owner Singleton and Anywhere-Login Rule

Date: 2026-09-30

## Invariant

AlgoFortis has one authoritative Owner identity. Installing the desktop application on another PC does not create another Owner and must never interpret an empty local database as proof that the global Owner is absent.

## Entry behavior

- Existing durable Owner on this installation -> existing Owner login.
- Fresh installation + configured central account authority -> returning/anywhere-login flow.
- Fresh installation + central account authority unavailable -> fail closed / authority unavailable.
- Owner setup is allowed only when a trusted authority explicitly confirms an initial bootstrap. It is never enabled merely because the local database is empty.

All Owner-provisioning mutation paths, including local password setup and bootstrap WebAuthn registration, are guarded by the same decision.

## V1 -> V2 migration

The V1 Owner is not recreated for V2. The migration path is a one-time claim/migration of the existing Owner identity into the server-authoritative account plane while preserving the Owner role and account identity. New PCs then authenticate against that existing account and enroll/bind the new device under the account/device policy.

Until the central roaming identity/account service is actually configured, cross-PC login remains unavailable and the application must say so. It must not fall back to creating a second Owner.

## Current implementation boundary

The desktop runtime now exposes `/api/v1/identity/bootstrap-status` and blocks duplicate Owner setup when global Owner presence is not authoritative. The current `UnavailableRoamingIdentity` remains fail-closed; connecting the central account authority is a separate integration step and must be verified before claiming anywhere-login is operational.

## Safety

This identity work does not arm Live trading, mutate broker orders, change RiskGate authority, or alter the existing Owner/Admin trading-safety boundaries.
