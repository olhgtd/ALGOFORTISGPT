# AlgoFortis V1 Entry Gate Reunion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reunite the proven V1 Owner/User password entry behavior with the current V2 account, session, device, role, audit and step-up authorities behind one canonical AlgoFortis entry gate.

**Architecture:** Keep the existing root `SecureEntryApp` and V2 workspace authorization boundary. Add atomic User password activation and a role-neutral password authentication service on the existing `SQLiteSecurityStore`, expose them through a focused `account_v2` router, and adapt the existing V1-derived secure-entry cards rather than creating a second auth shell. Owner bootstrap remains singleton-authorized; roaming/central identity remains fail-closed until a real adapter is configured.

**Tech Stack:** Python 3.13, FastAPI, SQLite, `hashlib.scrypt`, React 19/TypeScript, Vitest, pytest, Windows GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-30-entry-gate-v1-reunion-design.md`

## Global Constraints

- One canonical entry gate for Owner and User.
- Owner is a singleton; local DB emptiness never proves global Owner absence.
- Owner first bootstrap requires explicit authoritative `owner_setup_allowed=true`.
- User activation uses Owner-issued identifier/invitation, email confirmation, password, confirm password, and one atomic activation transaction.
- Returning Owner/User share `User ID or Email + Password`; backend role decides workspace.
- Password login is normal authentication only; it MUST NOT satisfy fresh WebAuthn step-up for destructive Owner actions.
- Passwords are never stored/logged/audited/returned in plaintext.
- Existing scrypt parameters remain `N=16384, r=8, p=1, dklen=64` with a random 16-byte salt unless a separately approved security migration changes them.
- Existing V2 lifecycle, suspension, entitlement, device/session, audit and role authorities remain authoritative.
- Missing central/roaming authority returns `UNAVAILABLE`; no fake cross-PC success and no duplicate Owner creation.
- RiskGateV2 remains the sole executable-order authority; Live remains `READ_ONLY / DISARMED`.
- No new User/Owner database, session authority, role resolver, RiskGate or broker mutation path.
- **Execution constraint for this branch:** author tests before production changes, but do not run pytest/Vitest/typecheck/build/Windows CI until the user's execution quota is reset. Every unexecuted verification step remains explicitly `PENDING`; no GREEN claim is allowed before execution.

## Review Focus

1. **Legacy Owner activation status `ACTIVATED`:** normalize/migrate to canonical `REDEEMED`; an old Owner row must not crash `persisted_identity()` or session issue.
2. **Password login step-up leakage:** password-authenticated Owner sessions must have `step_up_satisfied=False`; destructive Owner routes still demand a fresh WebAuthn step-up.
3. **Atomic first User activation:** wrong email, mismatched password, expired/revoked/replayed invitation, or DB failure must leave the User `PENDING/INVITED` with no password/service start partial write.
4. **Identity ambiguity/enumeration:** ID/email lookup must resolve exactly one authoritative row; bad identifier and bad password return the same generic authentication failure and share cooldown/rate-limit behavior.
5. **Workspace access after authentication:** suspended/revoked Users and inactive/expired entitlements must not enter the User workspace; caller-supplied role/workspace values never override backend identity.

---

### Task 1: Canonical password account primitives

**Files:**
- Modify: `dashboard/backend/security_store.py`
- Test: `tests_v1/test_entry_gate_password_accounts.py`

**Interfaces:**
- Consumes: existing `hash_password()`, `verify_password()`, `_validate_activation()`, `compute_service_expiry()`, `find_user_by_identifier()` and transactional store.
- Produces:
  - `SQLiteSecurityStore.activate_user_password(*, identifier: str, activation_code: str, email: str, password: str, now: datetime | None = None) -> UserIdentity`
  - `SQLiteSecurityStore.verify_identity_password(*, identifier: str, password: str, now: datetime | None = None) -> UserIdentity | None`
  - canonical Owner rows persist `activation_status='REDEEMED'`; legacy Owner `ACTIVATED` rows are migrated to `REDEEMED` during store bootstrap.

- [ ] **Step 1: Author password-account tests first**
  - `test_user_activation_password_is_atomic_and_starts_service()` asserts invitation -> ACTIVE/REDEEMED, password hash+salt stored, plaintext absent, service start/expiry set from existing term.
  - `test_user_activation_rejects_wrong_email_without_partial_state()` asserts pre-bound email must match normalized submitted email and invitation/password state remains unchanged.
  - `test_user_activation_rejects_expired_revoked_or_replayed_invitation()` asserts generic activation failure and no partial write.
  - `test_verify_identity_password_accepts_user_id_or_email_for_owner_and_user()` asserts role-neutral resolution.
  - `test_verify_identity_password_rejects_bad_password_suspended_or_revoked_account()` asserts `None` for all rejected cases.
  - `test_legacy_owner_activated_status_migrates_to_redeemed()` pins migration compatibility.

- [ ] **Step 2: Implement atomic User password activation**
  - Add `activate_user_password(...)` to `SQLiteSecurityStore`.
  - Inside one `BEGIN IMMEDIATE` transaction: resolve one User by canonical ID, validate invitation with `_validate_activation`, require normalized submitted email to equal authoritative `bound_email`, hash password, compute service expiry, redeem issuance, set `account_status='ACTIVE'`, `activation_status='REDEEMED'`, `service_status='ACTIVE'`, service start/expiry, password hash/salt/update timestamp.
  - Any validation/write error rolls back all state.

- [ ] **Step 3: Implement role-neutral password verification**
  - Add `verify_identity_password(...)` using `find_user_by_identifier`, constant-time `verify_password`, canonical lifecycle/account/activation checks, and `persisted_identity`.
  - Do not enforce User service entitlement inside the password verifier; workspace eligibility remains a separate authoritative decision.

- [ ] **Step 4: Normalize Owner activation semantics**
  - Change new Owner password initialization to persist `REDEEMED`, not non-enum `ACTIVATED`.
  - Add bootstrap migration `UPDATE users SET activation_status='REDEEMED' WHERE role='OWNER' AND activation_status='ACTIVATED'` before identities are reconstructed.

- [ ] **Step 5: Verification — DEFERRED UNTIL QUOTA RESET**
  - Run: `python -m pytest tests_v1/test_entry_gate_password_accounts.py -q`
  - Expected later: PASS; until run, status is `PENDING`.

- [ ] **Step 6: Commit**
  - Commit message: `feat: add canonical password account primitives`

---

### Task 2: Shared password activation/login HTTP authority

**Files:**
- Create: `dashboard/backend/account_v2/password_router.py`
- Modify: `dashboard/backend/account_v2/__init__.py`
- Modify: `dashboard/runtime/application.py`
- Modify: `dashboard/backend/api.py` only for legacy local endpoint hardening/compatibility, not for new account logic.
- Test: `tests_v1/test_entry_gate_password_routes.py`

**Interfaces:**
- Consumes: Task 1 `activate_user_password()` and `verify_identity_password()`, `app.state.sessions`, existing `AuthPolicyManager`, existing core/security audit authority.
- Produces:
  - `attach_password_account_routes(app: FastAPI) -> None`
  - `POST /api/v1/auth/password/activate`
  - `POST /api/v1/auth/password/login`
  - stable session response `{access_token, expires_at_utc, subject, role, sx_id, workspace_eligibility}`.

- [ ] **Step 1: Author route tests first**
  - Activation requires `identifier`, `activation_code`, `email`, `password`, `confirm_password`; mismatch returns 422 without mutation.
  - Successful activation returns no password/hash/salt and requires subsequent sign-in.
  - Owner and User login use the same endpoint and backend role.
  - Wrong identifier and wrong password both return generic `INVALID_ID_OR_PASSWORD`.
  - Rate-limit/cooldown keys cover client IP plus normalized identifier.
  - Suspended/revoked account cannot receive a session.
  - Authenticated User with inactive workspace entitlement receives `ACCOUNT_ACCESS_UNAVAILABLE` and no workspace session.
  - Password login session has `step_up_satisfied=False`.

- [ ] **Step 2: Implement focused account router**
  - Add request models locally in `password_router.py`: `PasswordActivationRequest` and `PasswordLoginRequest`.
  - Reuse existing rate limiter and mandatory audit facilities; audit event details must never include password or activation code.
  - Login: verify identity, check `identity.is_workspace_eligible('owner'|'user')` for its actual role, issue normal session with `step_up_satisfied=False`, return backend-derived role/eligibility.
  - Activation: call Task 1 atomic store method, record success/failure with redacted/generic audit semantics, return `{activated: true, authentication_required: true}` only.

- [ ] **Step 3: Attach router in runtime composition**
  - Call `attach_password_account_routes(app)` in `dashboard/runtime/application.py` alongside other additive authority routers.
  - Router must use existing `app.state.security_store`, `app.state.sessions`, `app.state.auth_policy`, and existing audit state; no new stores/services.

- [ ] **Step 4: Harden legacy local auth compatibility**
  - Keep `/api/v1/auth/local/setup` and `/api/v1/auth/local/login` for existing packaged clients/tests, but password-created sessions must no longer set `step_up_satisfied=True`.
  - Legacy owner-only login may delegate to canonical verifier where safe; it must not become a second role authority.

- [ ] **Step 5: Verification — DEFERRED UNTIL QUOTA RESET**
  - Run: `python -m pytest tests_v1/test_entry_gate_password_routes.py tests_v1/test_local_desktop_auth.py -q`
  - Expected later: PASS; until run, status is `PENDING`.

- [ ] **Step 6: Commit**
  - Commit message: `feat: add shared password account routes`

---

### Task 3: Frontend account API contracts

**Files:**
- Modify: `dashboard/web/src/api.ts`
- Modify: `dashboard/web/src/contracts.ts`
- Test: `dashboard/web/src/__tests__/entryGateAccountApi.test.ts`

**Interfaces:**
- Consumes: Task 2 password endpoints.
- Produces:
  - `api.passwordActivate(data)`
  - `api.passwordLogin(data)`
  - typed `PasswordSessionResponse` and activation response.

- [ ] **Step 1: Author API-client tests first**
  - Assert activation posts only identifier/code/email/password/confirm-password to `/auth/password/activate`.
  - Assert login posts only identifier/password to `/auth/password/login`.
  - Assert response typing exposes role/workspace eligibility but no secret/hash fields.

- [ ] **Step 2: Add typed API methods**
  - Add request/response interfaces in `contracts.ts`.
  - Add `passwordActivate` and `passwordLogin` in `api.ts`; successful login stores token only in the existing session store at the UI caller, not inside the generic request helper.

- [ ] **Step 3: Verification — DEFERRED UNTIL QUOTA RESET**
  - Run the focused Vitest file through the existing frontend test command/config.
  - Expected later: PASS; until run, status is `PENDING`.

- [ ] **Step 4: Commit**
  - Commit message: `feat: add entry gate account api contracts`

---

### Task 4: V1-style first-time User password activation UI

**Files:**
- Modify: `dashboard/web/src/visual-lab/secure-entry/FirstTimeCustomerFlow.tsx`
- Modify: `dashboard/web/src/visual-lab/secure-entry/secure-entry.css` only if required for existing card controls.
- Test: `dashboard/web/src/visual-lab/secure-entry/__tests__/FirstTimeCustomerFlow.test.tsx`

**Interfaces:**
- Consumes: Task 3 `api.passwordActivate()`.
- Produces: canonical first-time User flow `User ID -> Activation Code -> Email -> Password -> Confirm Password -> Sign In`.

- [ ] **Step 1: Author component behavior tests first**
  - Required fields render: User ID, activation code, email, create password, confirm password.
  - Password mismatch blocks request client-side.
  - Success clears password/code state and shows `SIGN IN` transition.
  - API error renders inline without exposing secret values.
  - No passkey enrollment is required for ordinary first-time password activation.

- [ ] **Step 2: Adapt the existing V1-derived card rather than redesigning**
  - Preserve current AlgoFortis secure-entry visual family and existing error/success card patterns.
  - Replace canonical passkey-first activation behavior with `api.passwordActivate()`.
  - Keep WebAuthn enrollment code available only through explicit later security/device flows, not this normal onboarding path.

- [ ] **Step 3: Verification — DEFERRED UNTIL QUOTA RESET**
  - Run focused Vitest later; expected PASS.

- [ ] **Step 4: Commit**
  - Commit message: `feat: restore v1 style user activation flow`

---

### Task 5: One shared returning Owner/User login card

**Files:**
- Modify: `dashboard/web/src/visual-lab/secure-entry/ReturningUserFlow.tsx`
- Modify: `dashboard/web/src/visual-lab/secure-entry/LocalLoginCard.tsx` only to delegate/mark compatibility; it is not canonical after this task.
- Test: `dashboard/web/src/visual-lab/secure-entry/__tests__/ReturningUserFlow.test.tsx`

**Interfaces:**
- Consumes: Task 3 `api.passwordLogin()` and existing `setSessionToken()`.
- Produces: shared `User ID or Email + Password` interactive login whose returned backend role determines workspace.

- [ ] **Step 1: Author shared-login tests first**
  - User ID/email + password fields enabled.
  - Successful OWNER response stores token and calls `onEnterWorkspace('OWNER')`.
  - Successful USER response stores token and calls `onEnterWorkspace('USER')`.
  - UI never accepts a caller-selected role/workspace as authentication evidence.
  - Generic invalid credentials and cooldown errors render correctly.
  - Activate User and Recovery links remain available.
  - WebAuthn/passkey is not required for normal login; optional/high-assurance UI must not auto-route roles.

- [ ] **Step 2: Implement shared password login UI**
  - Remove the current `Password authentication is disabled` canonical behavior.
  - Submit `api.passwordLogin({identifier, password})`, set existing session token, then route solely from response `role`.
  - Clear password after success/failure where appropriate.

- [ ] **Step 3: Retire Owner-only canonical login path**
  - `LocalLoginCard` may remain for compatibility/tests but `SecureEntryApp` will no longer select it as the normal returning-auth UI.

- [ ] **Step 4: Verification — DEFERRED UNTIL QUOTA RESET**
  - Run focused Vitest later; expected PASS.

- [ ] **Step 5: Commit**
  - Commit message: `feat: unify owner and user password login`

---

### Task 6: Canonical Secure Entry routing and Owner singleton behavior

**Files:**
- Modify: `dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx`
- Modify: `dashboard/web/src/main.tsx` only if session-continuity behavior needs correction.
- Test: `dashboard/web/src/visual-lab/secure-entry/__tests__/SecureEntryApp.test.tsx`
- Test: `tests_v1/test_owner_singleton_bootstrap_policy.py` (extend only; keep existing source-level protection).

**Interfaces:**
- Consumes: existing `/identity/bootstrap-status`, Task 4 activation card, Task 5 shared login card.
- Produces: unauthenticated choices `SIGN IN`, `ACTIVATE USER`, `RECOVERY`, plus Owner Setup only when explicitly authorized.

- [ ] **Step 1: Author routing tests first**
  - `LOCAL_LOGIN` bootstrap recommendation renders shared `RETURNING_USER`, not Owner-only card.
  - Fresh second PC + roaming unavailable renders `UNAVAILABLE`, never Owner Setup.
  - Explicit `owner_setup_allowed=true` is the only state that renders Owner setup.
  - User can reach Activate User from normal Sign In without exposing Owner Setup.
  - direct dashboard URL still passes through `AuthorizedDashboard/currentUser` and returns to Secure Entry when unauthorized.

- [ ] **Step 2: Simplify canonical flow selection**
  - Map existing-owner/local-login and roaming returning states to `RETURNING_USER`.
  - Keep `LOCAL_OWNER_SETUP` only for explicit first bootstrap.
  - Keep `ACCESS_GATE` as Activate User; Recovery unchanged.
  - Remove normal-user navigation hooks that can surface Owner Setup.

- [ ] **Step 3: Preserve root workspace authorization**
  - `main.tsx` continues to call `api.currentUser()` before rendering either workspace; URL/hash/query never grants access.
  - Do not alter User/Owner dashboard content in this task.

- [ ] **Step 4: Verification — DEFERRED UNTIL QUOTA RESET**
  - Run focused frontend and owner-singleton tests later; expected PASS.

- [ ] **Step 5: Commit**
  - Commit message: `feat: make secure entry the canonical account gate`

---

### Task 7: Security regression guards and manual qualification definition

**Files:**
- Create: `tests_v1/test_entry_gate_security_boundaries.py`
- Modify: `.github/workflows/owner-admin-authoritative.yml`
- Modify: `build/tools/check_owner_admin_boundary.py` only if entry-gate source needs explicit forbidden-call coverage.

**Interfaces:**
- Consumes: Tasks 1-6.
- Produces: permanent regression evidence definitions; workflow remains manual-only (`workflow_dispatch`).

- [ ] **Step 1: Author negative security tests**
  - plaintext password never appears in persisted rows beyond hash/salt columns, API payloads, audit records or expected UI responses;
  - password login session has no fresh Owner step-up;
  - Owner Setup mutation remains blocked without explicit bootstrap authority;
  - role/workspace cannot be supplied by login request to elevate privileges;
  - entry UI/backend contain no broker `place/modify/cancel`, `_mint_approved_order`, Live-arm or RiskGate bypass path.

- [ ] **Step 2: Extend manual qualification workflow without triggering it**
  - Add new password-account/route/security tests and focused secure-entry Vitest files.
  - Keep trigger exactly `workflow_dispatch`; do not add push/pull_request/schedule.
  - Preserve Windows latest + Windows 2022 checks, S2, Owner/Admin+AI guard, Live READ_ONLY firewall, full regression, typecheck and build.

- [ ] **Step 3: Verification — DEFERRED UNTIL QUOTA RESET**
  - Do not dispatch workflow now.
  - Later exact sequence: focused Python -> security boundaries -> S2 -> Live firewall -> full `tests_v1` -> frontend focused/all -> typecheck -> build -> dual Windows exact-SHA evidence.

- [ ] **Step 4: Commit**
  - Commit message: `test: define entry gate reunion qualification`

---

### Task 8: Source audit, migration note and preverification checkpoint

**Files:**
- Create: `docs/v2/ENTRY_GATE_V1_REUNION_STATUS.md`
- Modify: `docs/v2/OWNER_SINGLETON_ANYWHERE_LOGIN.md` if needed to reference the shared password gate and central-account limitation.

**Interfaces:**
- Consumes: Tasks 1-7.
- Produces: exact source-scope status and frozen SHA for later qualification.

- [ ] **Step 1: Source-scope audit**
  - Compare against the branch base and confirm no Normal User dashboard content, Owner/Admin business screens, trading engine authority or broker mutation paths changed outside entry/account scope.
  - Record central/roaming account adapter as separate pending integration if it is still not real/configured; do not claim cross-PC login operational.

- [ ] **Step 2: Record implementation status**
  - Document exact flows implemented, legacy compatibility endpoints retained, step-up behavior, migration of legacy Owner activation status, and all deferred verification commands.
  - Status wording: `SOURCE IMPLEMENTED / EXECUTION VERIFICATION PENDING` until tests/build/Windows evidence pass.

- [ ] **Step 3: Freeze a new checkpoint branch**
  - Create `checkpoint-entry-gate-v1-reunion-preverification-20260930` at the exact final source SHA.
  - Do not move prior checkpoints.

- [ ] **Step 4: Final verification later**
  - After quota reset, dispatch manual qualification at the checkpoint SHA, fix only evidence-backed failures, rerun, then create a separate verified checkpoint.

- [ ] **Step 5: Commit**
  - Commit message: `docs: freeze entry gate reunion source scope`
