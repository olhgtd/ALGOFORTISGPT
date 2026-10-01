# AlgoFortis V1 Entry Gate Reunion — Implementation Status

Date: 2026-09-30
Branch: `entry-gate-v1-reunion-20260930`
Status: **SOURCE IMPLEMENTED / EXECUTION VERIFICATION PENDING**

## What is implemented

### One canonical root gate

AlgoFortis continues to use the existing root `SecureEntryApp` and `AuthorizedDashboard` boundary. Direct dashboard URLs/hashes still require an authoritative `currentUser()` read and workspace eligibility before rendering a dashboard.

Canonical unauthenticated behavior is now:

- **Sign In** — shared Owner/User password login;
- **Activate User** — Owner-issued identifier/invitation + email + password onboarding;
- **Recovery** — existing recovery surface;
- **Owner Setup** — rendered only when authoritative one-time bootstrap state explicitly allows it.

An existing local Owner no longer receives a separate Owner-only login card. `LOCAL_LOGIN` and `RETURNING_USER` bootstrap decisions both resolve to the shared returning-login surface.

### Owner first bootstrap

The proven V1 `LocalOwnerSetupCard` UX remains the Owner first-run donor:

- display name;
- email;
- one-time trusted bootstrap token;
- password;
- confirm password.

The legacy `/api/v1/auth/local/setup` transport is bridged to the canonical password-account authority for package compatibility. The canonical backend also exposes `/api/v1/auth/password/owner-bootstrap`.

Owner bootstrap:

- requires the existing singleton/bootstrap decision when the product runtime supplies it;
- rejects re-provisioning after Owner initialization;
- consumes the existing one-time bootstrap authority;
- normalizes the canonical Owner identity to `OWNER-001` + `REDEEMED` before issuing the first password session;
- issues a normal password session with `step_up_satisfied=false`.

### User first activation

`FirstTimeCustomerFlow` now implements the approved V1-style password onboarding:

1. Owner-issued AlgoFortis User ID;
2. one-time activation code;
3. authoritative email match/binding confirmation;
4. create password;
5. confirm password;
6. atomic backend activation;
7. Sign In.

The normal activation path no longer requires passkey enrollment. WebAuthn remains available for high-assurance policy uses rather than acting as a second normal-login role authority.

Backend `PasswordAccountAuthority.activate_user_password()` performs all effective activation writes inside the existing security-store transaction. Validation or write failure rolls back without leaving a half-active account.

Successful activation changes the User from `PENDING/INVITED/NOT_STARTED` to `ACTIVE/REDEEMED/ACTIVE`, starts the service entitlement, stores only scrypt hash+salt, and redeems the invitation once.

### Shared returning Owner/User login

`ReturningUserFlow` now uses:

- User ID or registered email;
- password;
- one shared backend login endpoint.

The client does not send a role or workspace selection. `PasswordAccountAuthority.verify_identity_password()` resolves the persisted identity, and the backend response supplies the authoritative role/workspace eligibility.

- `OWNER` -> Owner Control Center;
- `USER` -> Normal User Dashboard, only when current service/lifecycle authority permits it.

Wrong identifier and wrong password are designed to return the same generic authentication failure. Existing login cooldown/rate-limit authority is reused.

### Password security and step-up separation

The reunion reuses the existing V1-proven password primitives already present in the current security store:

- `hashlib.scrypt`;
- `N=16384, r=8, p=1, dklen=64`;
- random 16-byte salt;
- `hmac.compare_digest` verification;
- no plaintext password persistence.

Normal password authentication **does not** count as fresh destructive-action WebAuthn step-up. Password-created sessions persist `step_up_satisfied=false`.

Owner/Admin destructive mutations continue to require the separate action-bound `OwnerStepUpAuthority` WebAuthn grant and immutable audit/FailureIncident path.

### Legacy compatibility

Legacy packaged desktop calls to:

- `/api/v1/auth/local/login`;
- `/api/v1/auth/local/setup`;

are intercepted and delegated to the canonical password account authority. This preserves the V1 package behavior without retaining a second password-session authority.

### Permanent boundaries

`build/tools/check_owner_admin_boundary.py` now governs the canonical entry-gate frontend and password account backend in addition to Owner/Admin + AI.

The governed entry surface must not acquire:

- broker adapters/execution/live modules;
- `place_order` / `submit_order` / `modify_order` / `cancel_order`;
- `_mint_approved_order`;
- sample/localStorage identity authority.

RiskGateV2 remains the sole executable-order authority. This work adds no broker mutation and does not arm Live.

## Source files added/changed

Primary backend additions:

- `dashboard/backend/account_v2/password_accounts.py`
- `dashboard/backend/account_v2/password_router.py`

Primary frontend reunion:

- `dashboard/web/src/visual-lab/secure-entry/FirstTimeCustomerFlow.tsx`
- `dashboard/web/src/visual-lab/secure-entry/ReturningUserFlow.tsx`
- `dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx`
- `dashboard/web/src/api.ts`
- `dashboard/web/src/contracts.ts`

Qualification definitions:

- `tests_v1/test_entry_gate_password_accounts.py`
- `tests_v1/test_entry_gate_password_routes.py`
- `tests_v1/test_entry_gate_security_boundaries.py`
- `dashboard/web/src/__tests__/entryGateAccountApi.test.ts`
- `dashboard/web/src/visual-lab/secure-entry/__tests__/FirstTimeCustomerFlow.test.tsx`
- `dashboard/web/src/visual-lab/secure-entry/__tests__/ReturningUserFlow.test.tsx`
- `dashboard/web/src/visual-lab/secure-entry/__tests__/SecureEntryApp.test.tsx`

The existing manual-only qualification workflow has been extended to include the entry-gate tests and boundary guard.

## Implementation-plan deviation

The approved plan originally named `dashboard/backend/security_store.py` as the direct home for the new password methods. During execution, that file was confirmed to be a very large shared persistence monolith and the available repository write interface replaces whole files.

To reduce accidental regression risk, the implementation instead placed the new account behavior in focused `dashboard/backend/account_v2/password_accounts.py`, while reusing the existing security store transaction/hash/query primitives directly. No second DB or persistence authority was created. This preserves the plan's behavior and authority model with a safer edit boundary.

## Cross-PC / anywhere-login truth

Duplicate Owner creation is blocked independently of this reunion. A fresh second PC with an empty local DB is not proof that the Owner is absent.

The current real roaming identity implementation is still `UnavailableRoamingIdentity`. Therefore:

- same-installation local password login is source-wired;
- a fresh second PC cannot create Owner #2;
- **actual cross-PC password login is not yet operational** because no real central account adapter is connected;
- when central/roaming authority is absent, the product must remain `UNAVAILABLE`, not fabricate login success.

Connecting and verifying the real central account/roaming adapter remains a separate integration step.

## Verification status

Per owner instruction, no pytest, Vitest, TypeScript typecheck, production build, or Windows GitHub Actions qualification has been executed for this reunion yet.

The manual workflow remains `workflow_dispatch` only.

When quota is available, run the exact frozen checkpoint through:

1. Python compile;
2. permanent Owner/Admin + AI + Entry Gate boundary guard;
3. S2 account boundary guard;
4. Live READ_ONLY mutation firewall;
5. focused Owner/Admin + AI + Owner singleton + Entry Gate tests;
6. S2 regression;
7. full `tests_v1` regression;
8. User + Owner + Entry Gate Vitest;
9. TypeScript typecheck;
10. production build;
11. Windows latest + Windows 2022 cross-check.

Until those commands actually run and pass, this work must be described only as:

**SOURCE IMPLEMENTED / EXECUTION VERIFICATION PENDING**

## Frozen safety state

- Live: `READ_ONLY / DISARMED`
- Broker mutation from entry/auth: absent
- RiskGateV2: unchanged / sole executable-order authority
- Owner destructive action step-up: preserved
- Normal User dashboard implementation: not redesigned by this reunion
- Owner/Admin dashboard implementation: not redesigned by this reunion
