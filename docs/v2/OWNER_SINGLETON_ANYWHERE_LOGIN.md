# AlgoFortis V2 — Owner Singleton and Anywhere-Login Rule

Date: 2026-09-30

## Invariant

AlgoFortis has one authoritative Owner identity. Installing the desktop application on another PC does not create another Owner and must never interpret an empty local database as proof that the global Owner is absent.

## Entry behavior

- Existing durable Owner on this installation -> the same canonical **Sign In** gate used by User accounts.
- Returning User -> the same canonical **Sign In** gate.
- Shared Sign In accepts AlgoFortis User ID / `OWNER-001` / registered email plus password; backend identity resolves the role/workspace.
- Fresh installation + configured central account authority -> returning/anywhere-login flow.
- Fresh installation + central account authority unavailable -> fail closed / authority unavailable.
- Owner setup is allowed only when a trusted authority explicitly confirms an initial bootstrap. It is never enabled merely because the local database is empty.

Owner provisioning uses the V1-derived first-run card (display name, email, one-time bootstrap token, password, confirm password), but its effective mutation/session path is delegated to the canonical password account authority.

## Owner identity normalization

The singleton Owner's canonical public identifier is `OWNER-001`.

Current account migration normalizes historical Owner rows so that:

- legacy `activation_status='ACTIVATED'` becomes current `REDEEMED`;
- a missing/blank Owner `sx_id` becomes `OWNER-001`;
- User records are not modified by this Owner-only migration.

New Owner bootstrap performs the same normalization before its first returned password session so ID login does not require an application restart.

## V1 -> V2 migration

The V1 Owner is not recreated for V2. The migration path is a one-time claim/migration of the existing Owner identity into the server-authoritative account plane while preserving the Owner role and account identity. New PCs then authenticate against that existing account and enroll/bind the new device under the account/device policy.

Until the central roaming identity/account service is actually configured, cross-PC login remains unavailable and the application must say so. It must not fall back to creating a second Owner.

## Current implementation boundary

The desktop runtime exposes `/api/v1/identity/bootstrap-status` and blocks duplicate Owner setup when global Owner presence is not authoritative.

The local entry-gate reunion now provides the shared Owner/User password UX and canonical local account endpoints. This does **not** mean central anywhere-login exists: the current `UnavailableRoamingIdentity` remains fail-closed. Connecting the central account authority is a separate integration step and must be verified before claiming anywhere-login is operational.

## Step-up separation

Normal password login creates an ordinary authenticated session and does not count as fresh WebAuthn step-up. Destructive/security-sensitive Owner actions continue to require the action-bound WebAuthn step-up authority.

## Safety

This identity work does not arm Live trading, mutate broker orders, change RiskGateV2 authority, or alter the existing Owner/Admin trading-safety boundaries.
