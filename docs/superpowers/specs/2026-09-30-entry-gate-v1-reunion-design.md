# AlgoFortis V1 Entry Gate Reunion — Design

Date: 2026-09-30
Status: DESIGN APPROVED IN CHAT / WRITTEN SPEC PENDING USER REVIEW
Branch: `entry-gate-v1-reunion-20260930`
Base: `owner-admin-authoritative-reunion-20260929`

## 1. Intent

Reunite the proven V1 desktop entry/login experience with the current V2 authority graph without creating a second authentication system.

The application must have one canonical root entry gate shared by Owner and User. The mature V1 entry UX and local password-security behavior are donors; current V2 account/session/device/role authority remains authoritative.

The Normal User dashboard and Owner/Admin dashboard stay separate workspaces behind the same authentication boundary.

## 2. Non-negotiable outcomes

1. A fresh install never opens a dashboard without authoritative session validation.
2. There is one canonical entry gate, not separate Owner and User authentication shells.
3. Owner is a singleton. Existing Owner identity is never recreated because a local database is empty.
4. Owner first bootstrap is available only when an authoritative bootstrap decision explicitly allows it.
5. First-time User activation follows the V1-style password onboarding flow:
   - Owner-issued User ID / account identifier;
   - single-use activation/invitation code when required by the account record;
   - user email binding/confirmation;
   - create password;
   - confirm password;
   - atomic account activation.
6. Returning Owner and User use the same sign-in behavior:
   - User ID or registered email;
   - password;
   - backend resolves identity/role and routes to the correct workspace.
7. WebAuthn/passkey remains available for step-up/high-assurance/recovery where current V2 policy requires it; it is not a second role-routing authority.
8. Owner destructive/security-sensitive actions continue to require fresh step-up authentication.
9. Existing V2 session, device, suspension, entitlement, recovery and role checks remain authoritative.
10. Missing central/roaming authority must fail closed as `UNAVAILABLE`; it must never trigger duplicate Owner setup or fake successful login.
11. Live remains `READ_ONLY / DISARMED`. Entry-gate work must not add broker mutation or alter RiskGateV2 execution authority.

## 3. Canonical root flow

```text
AlgoFortis launch
    |
    v
Runtime authority READY?
    |-- no  -> RuntimeAvailability / UNAVAILABLE
    `-- yes
          |
          v
Existing valid authenticated session?
    |-- yes -> authoritative current-user check -> role/workspace routing
    `-- no
          |
          v
Canonical Secure Entry Gate
    |
    +-- Sign In
    +-- Activate User
    +-- Recovery
    `-- Owner Setup (visible only when authoritative one-time bootstrap allows it)
```

Direct URL/hash requests for User or Owner dashboards must still pass the authenticated `currentUser`/workspace-eligibility boundary. URL state alone grants no access.

## 4. Owner first-run bootstrap

### Preconditions

Owner Setup is allowed only if the backend bootstrap authority returns an explicit `owner_setup_allowed=true` decision. Local SQLite emptiness alone is insufficient evidence.

### UX donor

Reuse the mature V1 `LocalOwnerSetupCard` visual/interaction pattern:

- Owner display name;
- Owner email;
- trusted one-time bootstrap token;
- Create Password;
- Confirm Password;
- password visibility control;
- inline validation/error state;
- submit -> authoritative backend provisioning -> session issuance.

### Authority rules

- backend enforces singleton Owner;
- bootstrap token is one-time and consumed atomically;
- password is never stored or logged in plaintext;
- local password hash behavior may reuse the proven V1 scrypt implementation where compatible with current V2 policy;
- an existing V1 Owner migrating to V2 is claimed/migrated, never recreated;
- fresh second PC must not infer `Owner absent` from an empty local database.

## 5. First-time User activation

### Entry

Owner creates a User through Access Registry. The authoritative account plane issues the User ID/account record and a single-use activation invitation where required.

### User flow

```text
Activate User
   -> User ID / account identifier
   -> Activation code / invitation
   -> Email binding/confirmation
   -> Create Password
   -> Confirm Password
   -> authoritative validation
   -> atomic activation
   -> Sign In
```

### Rules

- activation invitation is single-use;
- expired/revoked/already-used invitation fails closed;
- email must bind to the intended account record and must not silently rebind another identity;
- password mismatch/weak password fails before account activation;
- activation success changes lifecycle only after all authoritative writes succeed;
- failed activation must not leave a half-active account;
- no plaintext password in logs, audit, API responses, support bundles or backups.

The current passkey-first `FirstTimeCustomerFlow` is therefore not the final canonical User activation UX. Its useful UI shell/error states may be reused, but activation behavior must be adapted to the approved password onboarding contract.

## 6. Returning login — shared Owner/User behavior

The canonical returning-login card is shared by Owner and User:

Fields:

- `User ID or Email`;
- `Password`;
- password visibility toggle;
- Sign In;
- Activate User link;
- Recovery link.

Backend behavior:

1. resolve authoritative identity by ID/email;
2. verify password using constant-time comparison and current password policy;
3. verify lifecycle/account status;
4. verify suspension/revocation;
5. verify service entitlement for User workspace;
6. verify device/session policy;
7. issue session;
8. return role/workspace eligibility;
9. UI routes OWNER -> Owner Control Center; USER -> Normal User Dashboard.

Authentication failure remains generic enough to avoid account enumeration. Rate-limit/cooldown behavior is preserved.

## 7. WebAuthn / passkey role

Password login is restored as the normal V1-style interactive login experience requested by the Owner, but WebAuthn remains part of the V2 security architecture for high-assurance operations.

Use WebAuthn/passkey for:

- destructive Owner step-up;
- security-sensitive credential/account changes;
- high-assurance recovery / device enrollment as required;
- optional future passwordless login only when the current account contract explicitly enables it.

WebAuthn must not become a second identity/role authority parallel to the password account plane.

## 8. Cross-PC / reinstall behavior

### Same PC

Existing durable Owner/User account state -> Sign In.

### Fresh second PC

- never show Owner Setup merely because local DB is empty;
- if central/roaming account authority is configured, use the same User ID/email + password login and then run device enrollment/verification as required;
- if central/roaming authority is not configured, show `UNAVAILABLE` rather than creating a new Owner.

### V1 -> V2 migration

Existing Owner identity is migrated/claimed once. User identities are migrated through reviewed account migration rules. No automatic duplicate accounts.

## 9. UI preservation

Preserve the established AlgoFortis Secure Entry visual family:

- AlgoFortis logo/wordmark;
- animated core/chassis where currently used;
- clock/top chrome;
- secure card layout;
- clear inline errors;
- success/failure/verification panels;
- recovery navigation;
- responsive desktop/mobile behavior.

The purpose is reunion, not redesign. Visual changes should be limited to making the approved flows clear and consistent.

Canonical unauthenticated choices:

- **SIGN IN**
- **ACTIVATE USER**
- **RECOVERY**
- **OWNER SETUP** only when the backend explicitly authorizes first bootstrap.

## 10. Backend reuse and boundaries

Reuse current authorities where possible:

- `dashboard/backend/security_store.py` for durable identity/password primitives where policy-compatible;
- existing scrypt + salt + constant-time verification primitives;
- current session service / current-user authorization boundary;
- Owner singleton/bootstrap firewall introduced in the Owner singleton fix;
- current role/lifecycle/entitlement checks;
- current audit/security infrastructure;
- current step-up/WebAuthn authority.

Do not create:

- a second User database;
- a second Owner database;
- parallel session authority;
- parallel role resolver;
- old V1 RiskGate/order authority;
- direct broker calls from the entry UI.

## 11. Expected source changes

Likely touch points (final plan must verify exact paths before implementation):

Frontend:

- `dashboard/web/src/main.tsx`
- `dashboard/web/src/api.ts`
- `dashboard/web/src/contracts.ts`
- `dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx`
- `dashboard/web/src/visual-lab/secure-entry/FirstTimeCustomerFlow.tsx`
- `dashboard/web/src/visual-lab/secure-entry/ReturningUserFlow.tsx`
- `dashboard/web/src/visual-lab/secure-entry/LocalOwnerSetupCard.tsx`
- `dashboard/web/src/visual-lab/secure-entry/LocalLoginCard.tsx`
- secure-entry styles/types as needed.

Backend:

- account/activation/password endpoints under `dashboard/backend/`;
- `dashboard/backend/security_store.py` only where required;
- `dashboard/backend/account_v2/` for canonical Owner/User account/bootstrap contracts;
- `dashboard/runtime/application.py` for composition only, not account logic.

Tests/qualification definitions may be authored now but execution waits for quota reset.

## 12. Test plan for later execution

When execution quota is available, qualification must include at minimum:

1. fresh first install, explicit bootstrap -> one Owner created;
2. second Owner setup attempt rejected;
3. fresh second PC with empty local DB never exposes Owner creation;
4. Owner User issuance -> first-time User activation with ID/invitation/email/password/confirm;
5. duplicate/expired/revoked activation rejected;
6. returning Owner login with ID/email + password;
7. returning User login with ID/email + password;
8. wrong password returns generic failure;
9. cooldown/rate-limit behavior;
10. suspended/revoked user cannot log in;
11. expired entitlement cannot enter User workspace;
12. direct dashboard URL without a valid session returns to Secure Entry;
13. Owner/User role routing cannot be chosen by caller input alone;
14. destructive Owner operations still require fresh WebAuthn step-up;
15. central/roaming authority unavailable -> `UNAVAILABLE`, never Owner recreation;
16. plaintext-password scan / log redaction checks;
17. frontend typecheck/build;
18. Windows latest + Windows 2022 qualification;
19. existing Owner/Admin + AI boundary guards;
20. existing Live `READ_ONLY / DISARMED` firewall and full regression.

## 13. Explicitly out of scope for this reunion

- enabling real-money Live execution;
- changing RiskGateV2/order authority;
- broker mutation paths;
- redesigning Normal User dashboard content;
- redesigning Owner/Admin dashboard content;
- inventing a fake central account service;
- declaring cross-PC login operational until a real central/roaming account adapter is configured and verified.

## 14. Completion definition

Source implementation is complete when:

- the canonical entry gate presents the approved Owner/User flows;
- Owner Setup cannot appear or execute without explicit bootstrap authority;
- first-time User password activation is wired to authoritative account state;
- Owner/User share one returning-login behavior;
- backend role routing determines workspace;
- current V2 account/session/device/security boundaries remain authoritative;
- no duplicate auth authority is introduced;
- qualification tests/workflow definitions are present.

The feature remains **IMPLEMENTED / EXECUTION VERIFICATION PENDING** until the later test/build/Windows qualification run passes at an exact frozen SHA.