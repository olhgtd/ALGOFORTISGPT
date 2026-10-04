# AlgoFortis — Complete UI User Flow Map
**Authoritative Product Journey & State Transition Specifications**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Authentication & Public Access Flows

### Flow ID: `FLOW-AUTH-001: Cold App Launch & Routing Resolution`
- **Role Restrictions:** Public / Unauthenticated
- **Start:** User launches desktop executable or opens browser to `http://127.0.0.1:8080/`.
- **Step-by-Step Path:**
  1. `main.tsx` inspects URL search parameters (`surface`, `workspace`) and URL hash.
  2. `RuntimeAvailability` executes initial handshake with `GET /api/v1/runtime/status`.
  3. If runtime status is not `READY`, display startup splash / waiting overlay.
  4. Once `READY`, check for existing valid session token in `sessionStore`.
  5. If valid token exists, fire `GET /api/v1/users/current` to verify authorization epoch.
  6. If verified, transition directly to `dashboard-v3` with authorized workspace (`owner` or `user`).
  7. If unauthenticated, default to `surface=secure-entry` (or `surface=website` if `#website` requested).
- **Decision Points:**
  - Runtime ready? -> Yes: evaluate session; No: show `RuntimeAvailability` screen.
  - Session token present and valid? -> Yes: navigate to dashboard; No: navigate to `secure-entry`.
  - Is user Owner or standard User? -> Route to `workspace=owner` or `workspace=user`.
- **Backend Calls:**
  - `GET /api/v1/runtime/status`
  - `GET /api/v1/users/current`
- **Success Result:** User lands seamlessly on their respective active workspace dashboard or the secure login card.
- **Failure Result:** If token is invalid or expired, token is cleared and user is placed on Secure Entry.

---

### Flow ID: `FLOW-AUTH-002: Returning User Passkey / WebAuthn Login`
- **Role Restrictions:** Public / Registered User
- **Start:** User on `surface=secure-entry` with "Returning User" tab selected.
- **Step-by-Step Path:**
  1. User enters identifier (email/SX-ID) or leaves blank to let passkey discover user credential.
  2. User clicks "Authenticate with Passkey" button.
  3. Client calls `POST /api/v1/auth/webauthn/authentication/options` with `{ identifier }`.
  4. Server responds with cryptographic `challenge_id` and `publicKey` credential request options.
  5. Client invokes `navigator.credentials.get({ publicKey })`.
  6. Browser prompts user for hardware security key touch, TouchID, Windows Hello, or PIN.
  7. User completes hardware ceremony; client receives authenticator assertion response.
  8. Client sends assertion to `POST /api/v1/auth/webauthn/authentication/complete`.
  9. Server validates signature against public key, verifies counter, and returns `{ access_token, role, subject, sx_id }`.
  10. Client saves `access_token` into `sessionStore` and redirects to `dashboard-v3` matching user's role.
- **Decision Points:**
  - Did hardware prompt succeed or user cancel? -> If cancelled, display retry message.
  - Server validation pass? -> If yes, store token and redirect; if no, display error and log security event.
- **Backend Calls:**
  - `POST /api/v1/auth/webauthn/authentication/options`
  - `POST /api/v1/auth/webauthn/authentication/complete`
- **Success Result:** Full authentication granted, JWT stored, immediate transition to User/Owner Workspace.
- **Failure Result:** Red error banner with exact failure message (e.g. `CREDENTIAL_UNKNOWN`, `INVALID_SIGNATURE`, `USER_SUSPENDED`).

---

### Flow ID: `FLOW-AUTH-003: First-Time User Token Activation & Key Enrollment`
- **Role Restrictions:** New Customer with Invitation Token
- **Start:** User on `surface=secure-entry` clicks "First-Time Activation".
- **Step-by-Step Path:**
  1. User fills in: `Account Identifier` (e.g., email), `Activation Code` (provided by Owner), `Key Label` (e.g., "MacBook TouchID").
  2. User clicks "Verify Token & Enroll Security Key".
  3. Client calls `POST /api/v1/auth/webauthn/activation/redeem` with `{ identifier, activation_code }`.
  4. Server validates activation token existence, term, and single-use state, then issues `challenge_id` and `publicKey` creation options.
  5. Client calls `navigator.credentials.create({ publicKey })`.
  6. Browser prompts user to register hardware authenticator.
  7. Client captures attestation and calls `POST /api/v1/auth/webauthn/activation/complete`.
  8. Server registers public key, activates user account lifecycle from `PENDING` to `ACTIVE`, and returns registration confirmation.
  9. User is prompted to log in immediately using their newly enrolled passkey.
- **Decision Points:**
  - Token expired or already redeemed? -> Display "Activation Token Invalid or Expired".
  - WebAuthn registration cancelled? -> Allow retry without invalidating token.
- **Backend Calls:**
  - `POST /api/v1/auth/webauthn/activation/redeem`
  - `POST /api/v1/auth/webauthn/activation/complete`
- **Success Result:** Account bound to physical security key; transition to login or automatic dashboard entry.
- **Failure Result:** Inline error detailing token mismatch or hardware registration refusal.

---

### Flow ID: `FLOW-AUTH-004: Primary Owner Appliance Bootstrap Setup`
- **Role Restrictions:** Appliance Administrator (First Run Only)
- **Start:** Fresh appliance installation where no Owner has been registered.
- **Step-by-Step Path:**
  1. User navigates to `surface=secure-entry` and selects "Owner Setup".
  2. User enters `Bootstrap Token` (printed in terminal during appliance initialization).
  3. User enters `Owner Hardware Key Label` (e.g., "Owner YubiKey 5C NFC Primary").
  4. Client calls `POST /api/v1/auth/webauthn/bootstrap-registration/options` with `x-algofortis-bootstrap` header.
  5. Server validates token, locks bootstrap mutex, and returns creation options.
  6. Client triggers `navigator.credentials.create()`.
  7. Client submits attestation to `POST /api/v1/auth/webauthn/bootstrap-registration/complete`.
  8. Server registers Primary Owner, irreversibly consumes the bootstrap token, and grants Owner session token.
- **Decision Points:**
  - Has owner already been bootstrapped? -> Server rejects with HTTP 403 `BOOTSTRAP_ALREADY_COMPLETED`.
- **Backend Calls:**
  - `POST /api/v1/auth/webauthn/bootstrap-registration/options`
  - `POST /api/v1/auth/webauthn/bootstrap-registration/complete`
- **Success Result:** Master Owner account created, redirect to Owner Control Center (`workspace=owner`).
- **Failure Result:** Setup blocked; error banner displayed.

---

### Flow ID: `FLOW-AUTH-005: Account Recovery via Emergency Token`
- **Role Restrictions:** Registered User who lost physical authenticator
- **Start:** User clicks "Help & Emergency Recovery" on login card.
- **Step-by-Step Path:**
  1. User enters `Account Identifier` and `Emergency Recovery Key`.
  2. Client submits to recovery validation endpoint.
  3. Server verifies recovery key integrity and triggers WebAuthn re-enrollment ceremony.
  4. User registers new replacement security key.
  5. Previous compromised/lost security key is revoked.
- **Backend Calls:**
  - `POST /api/v1/auth/recovery/validate`
  - `POST /api/v1/auth/recovery/complete`
- **Success Result:** Account re-bound to new hardware key; recovery key invalidated.

---

### Flow ID: `FLOW-AUTH-006: Session Invalidation & Logout`
- **Role Restrictions:** Any Authenticated User / Owner
- **Start:** User clicks "Logout" or "Lock Session" in top navigation bar.
- **Step-by-Step Path:**
  1. Client sends `POST /api/v1/security/sessions/revoke` to server.
  2. Client executes `clearSessionToken()`, removing credentials from memory and storage.
  3. Client updates URL to `surface=secure-entry`.
  4. User is returned to login card.
- **Success Result:** Clean logout with server-side token revocation and zero cached auth state.

---

## 2. Owner Management & Governance Flows

### Flow ID: `FLOW-OWN-001: Issuing New User Invitation Token`
- **Role Restrictions:** Owner Only
- **Start:** Owner opens `#access-registry` screen.
- **Step-by-Step Path:**
  1. Owner fills out "Issue Access Token" form:
     - Target User Email / SX-ID
     - Display Name
     - Service Term (30 Days, 90 Days, 1 Year, Lifetime, Custom)
     - Allowed Features (Backtest, Paper, Options)
  2. Owner clicks "Generate Invitation Token".
  3. Client sends `POST /api/v1/owner/access/users` with payload.
  4. Server creates pre-activated record and generates cryptographic invitation code.
  5. Client displays `TokenGeneratedModal` containing the raw token and formatted activation URL.
  6. Owner copies token to clipboard to securely transmit to customer.
- **Backend Calls:**
  - `POST /api/v1/owner/access/users`
  - `GET /api/v1/integration/access/records`
- **Success Result:** Token active in pending registry; ready for user redemption.

---

### Flow ID: `FLOW-OWN-002: User Account Suspension & Immediate Session Termination`
- **Role Restrictions:** Owner Only
- **Start:** Owner on `#users` directory table.
- **Step-by-Step Path:**
  1. Owner locates target user and clicks "Suspend Account".
  2. `SuspendUserModal` opens requesting reason for audit record.
  3. Owner enters reason and clicks "Confirm Immediate Suspension".
  4. Client calls `POST /api/v1/owner/access/users/{id}/suspend` and `POST /api/v1/owner/security/users/{id}/sessions/revoke-all`.
  5. Server transitions user status to `SUSPENDED`, revokes all active JWT sessions, and pauses all active paper daemons.
  6. If user is currently active in another browser, their next polling request fails and they are kicked to Secure Entry.
- **Backend Calls:**
  - `POST /api/v1/owner/access/users/{id}/suspend`
  - `POST /api/v1/owner/security/users/{id}/sessions/revoke-all`
- **Success Result:** User access instantly revoked; audit entry created in D16 store.

---

### Flow ID: `FLOW-OWN-003: User Account Restoration`
- **Role Restrictions:** Owner Only
- **Start:** Owner on `#users` locates suspended user.
- **Step-by-Step Path:**
  1. Owner clicks "Restore Access".
  2. Confirmation dialog confirms un-suspension.
  3. Client calls `POST /api/v1/owner/access/users/{id}/restore`.
  4. Server transitions status to `ACTIVE`. User can now log in with existing passkeys.
- **Backend Calls:**
  - `POST /api/v1/owner/access/users/{id}/restore`
- **Success Result:** User restored; status badge turns green.

---

### Flow ID: `FLOW-OWN-004: Strategy Promotion & Risk Allowance Governance`
- **Role Restrictions:** Owner Only
- **Start:** Owner opens `#strategies` screen and checks "Promotion Approval Queue".
- **Step-by-Step Path:**
  1. Owner clicks "Review Promotion" on pending user strategy.
  2. `PromotionReviewModal` shows:
     - Historical backtest Sharpe, Drawdown, Profit Factor
     - Python source code diff and AST risk policy compliance
     - Proposed max lot size and permitted market instruments
  3. Owner chooses "Approve Promotion" or "Reject / Quarantine".
  4. If approving, Owner sets maximum allowable capital allocation.
  5. Client calls `POST /api/v1/owner/strategies/{id}/promote` and `POST /api/v1/owner/strategies/{id}/allowance`.
  6. Server updates strategy governance state to `PAPER_APPROVED` or `LIVE_PROMOTED`.
- **Backend Calls:**
  - `GET /api/v1/owner/promotions/pending`
  - `POST /api/v1/owner/strategies/{id}/promote`
  - `POST /api/v1/owner/strategies/{id}/allowance`
- **Success Result:** Strategy unlocked for user paper trading or live shadow monitoring.

---

### Flow ID: `FLOW-OWN-005: Global Emergency Execution Hold (Safe Mode)`
- **Role Restrictions:** Owner Only
- **Start:** Owner on `#home` or top header clicks "ENGAGE GLOBAL HOLD".
- **Step-by-Step Path:**
  1. `ConfirmExecutionHoldModal` opens with severe warning.
  2. Owner types confirmation word `HOLD` and clicks "Engage Emergency Hold".
  3. Client calls `POST /api/v1/settings/safe-mode` with `{ enabled: true }`.
  4. Server immediately sets global execution hold flag in engine runtime.
  5. All active order execution, paper daemons, and market orders are frozen.
  6. Header banner updates globally to red `[GLOBAL EXECUTION HOLD: ACTIVE]`.
- **Backend Calls:**
  - `POST /api/v1/settings/safe-mode`
- **Success Result:** Zero-mutation safety invariant enforced instantly across all subsystems.

---

## 3. User Trading & Research Flows

### Flow ID: `FLOW-USR-001: Authoring & Registering a New Strategy`
- **Role Restrictions:** Standard User
- **Start:** User on `#strategies` clicks "New Strategy".
- **Step-by-Step Path:**
  1. `AddStrategyModal` opens with 3 tabs:
     - Step 1: Strategy Metadata (Name, Description, Base Asset).
     - Step 2: Risk Envelope (Max Drawdown %, Max Positions, Stop Loss policy).
     - Step 3: Source Code (Paste Python code or select template).
  2. User inputs strategy code and clicks "Validate & Save".
  3. Client calls `POST /api/v1/strategies` with code and protective policy.
  4. Server performs static AST analysis, checks for unauthorized OS imports (e.g. `os.system`, `subprocess`), verifies event handlers (`on_bar`, `on_tick`), and registers strategy in `DRAFT` state.
  5. Strategy card appears in user's Strategy Catalog.
- **Backend Calls:**
  - `POST /api/v1/strategies`
- **Success Result:** Strategy registered; ready for backtesting.
- **Failure Result:** AST syntax or safety policy error displayed with exact line number.

---

### Flow ID: `FLOW-USR-002: Configuring and Executing a Deterministic Backtest`
- **Role Restrictions:** Standard User
- **Start:** User navigates to `#backtesting`.
- **Step-by-Step Path:**
  1. User selects strategy from dropdown.
  2. User selects dataset (e.g. `BTC-USDT-1M-2024`, `SPY-TICK-Q1-2024`).
  3. User sets Date Range, Initial Capital ($100,000), Slippage Model (e.g., 1 bps), and Commission.
  4. User clicks "Execute Backtest".
  5. Client calls `POST /api/v1/backtest/run`.
  6. Server spawns deterministic replay worker; returns `backtest_id`.
  7. Client enters polling / telemetry stream mode (`GET /api/v1/backtest/status/{id}`).
  8. Progress bar animates (0% -> 100%), tick counter increments.
  9. Upon completion, client requests `GET /api/v1/backtest/results/{id}`.
  10. Dashboard renders full analytics: Equity Curve, Monthly Return Heatmap, Drawdown Underwater Chart, Trade Ledger.
- **Backend Calls:**
  - `POST /api/v1/backtest/run`
  - `GET /api/v1/backtest/status/{id}`
  - `GET /api/v1/backtest/results/{id}`
- **Success Result:** Full interactive performance report rendered; trade ledger searchable.

---

### Flow ID: `FLOW-USR-003: Launching Paper Trading Simulation`
- **Role Restrictions:** Standard User (with Owner-approved strategy)
- **Start:** User on `#paper` clicks "Launch Paper Session".
- **Step-by-Step Path:**
  1. User selects approved strategy and allocated virtual capital.
  2. User clicks "Start Simulation".
  3. Client calls `POST /api/v1/paper/sessions`.
  4. Server spawns simulated execution worker bound to live market data feed.
  5. Live orderbook, position table, and streaming PnL update in real time.
  6. User can submit manual limit/stop orders or let the algorithmic strategy trade automatically.
- **Backend Calls:**
  - `POST /api/v1/paper/sessions`
  - `GET /api/v1/user/orders-portfolio?mode=PAPER`
  - `GET /api/v1/market/chart?mode=LIVE`
- **Success Result:** Simulated paper session running; zero broker mutation.

---

### Flow ID: `FLOW-USR-004: Enrolling an Additional Backup Passkey`
- **Role Restrictions:** Standard User
- **Start:** User on `#security` clicks "Enroll Backup Security Key".
- **Step-by-Step Path:**
  1. User enters key label (e.g., "YubiKey 5 NFC Backup").
  2. User clicks "Begin Registration".
  3. Client calls `POST /api/v1/auth/webauthn/registration/options`.
  4. Browser triggers WebAuthn registration ceremony.
  5. User touches physical key.
  6. Client submits attestation to `POST /api/v1/auth/webauthn/registration/complete`.
  7. Server stores credential public key and updates device count.
- **Backend Calls:**
  - `POST /api/v1/auth/webauthn/registration/options`
  - `POST /api/v1/auth/webauthn/registration/complete`
- **Success Result:** Backup passkey successfully bound to user account.

---

## 4. Runtime & Connectivity Recovery Flows

### Flow ID: `FLOW-RNT-001: Backend Process Restart & Instance ID Desynchronization`
- **Role Restrictions:** All Users
- **Start:** Backend server or desktop sidecar restarts (e.g. due to system update or crash).
- **Step-by-Step Path:**
  1. Frontend `RuntimeAvailability` poller (`/api/v1/runtime/status`) detects that `status.instance_id` has changed compared to initial boot.
  2. Client recognizes that in-memory cryptographic state has been reset on server.
  3. To maintain strict fail-closed safety, client immediately executes `clearSessionToken()`.
  4. State changes to `RECOVERING`, displaying "Reconnecting to AlgoFortis".
  5. Poller completes handshake and redirects user to `surface=secure-entry` with message "Backend restarted. Please re-authenticate."
- **Success Result:** Prevents stale session hijacking; guarantees fresh cryptographic handshake.

---

### Flow ID: `FLOW-RNT-002: Network / Socket Disconnection & Reconnection`
- **Role Restrictions:** All Users
- **Start:** Network drops or local port temporarily unreachable.
- **Step-by-Step Path:**
  1. Poller receives fetch failure / timeout (2000ms threshold).
  2. `RuntimeAvailability` transitions to `UNAVAILABLE`.
  3. Red security overlay covers dashboard, preventing any user interaction with stale data.
  4. Poller continues automatic retries every 3000ms.
  5. User can also click "Retry connection" to trigger immediate attempt.
  6. When endpoint responds with `state: "READY"`, overlay automatically unmounts, restoring active dashboard.
- **Success Result:** Seamless recovery without page reload when connection returns.
