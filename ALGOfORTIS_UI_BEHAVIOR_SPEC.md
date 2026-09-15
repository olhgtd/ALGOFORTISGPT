# AlgoFortis — UI Behavior Specification
**Authoritative Frontend Interaction, Validation, Navigation & State Machine Specification**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Routing, Navigation & State Persistence

### 1.1 Master Surface Switching
The application root (`main.tsx`) operates a top-level surface dispatcher driven by URL search parameters and hashes:
- `?surface=website` or `#website` -> Public Marketing & Interactive Docs.
- `?surface=secure-entry` or `#secure-entry` -> Cryptographic Entry Gate.
- `?surface=dashboard-v3` with `&workspace=owner` or `&workspace=user` -> Authenticated Workstation.

### 1.2 State Transition & Guard Matrix
1. **Unauthenticated Access to Dashboard:**
   - If user navigates directly to `?surface=dashboard-v3` without a valid JWT token in `sessionStore`, `AuthorizedDashboard` evaluates `GET /api/v1/users/current`.
   - On error or 401 response, it immediately triggers `onDenied()`, clearing state and transitioning to `surface=secure-entry`.
2. **Role-Based Workspace Guarding:**
   - If a standard `USER` requests `workspace=owner`, `session.workspace_eligibility.owner` evaluates to `false`.
   - The user is automatically redirected to `workspace=user` or denied with a permission boundary notification.
   - An `OWNER` has full eligibility for both `owner` and `user` workspaces and can freely toggle between them via the Workspace Switcher in the top header.
3. **Browser History & Deep Linking:**
   - State synchronizations use `window.history.pushState` and `window.history.replaceState` to maintain clean, shareable URLs without re-triggering full page reloads.
   - Standard browser back/forward buttons fire `popstate` and `hashchange` listeners, keeping UI state perfectly synchronized with history.

### 1.3 Page Refresh & Cold Storage Behavior
- **Theme Persistence:** Dark / Light theme selection is stored in `localStorage.getItem("sentinelx_theme")` and applied to `document.documentElement` as `data-theme="dark"` or `data-theme="light"` prior to DOM paint, preventing white flash.
- **Session Token Persistence:** Session JWT is stored in memory and synchronized to secure storage (`sessionStore.ts`). On reload, `AuthorizedDashboard` re-authenticates with the server to fetch fresh identity and epoch timestamps.
- **Form State on Refresh:** Transient form inputs (e.g. unsubmitted strategy parameters) are held in component React state; refreshing clears unsubmitted drafts to prevent stale parameter execution.

---

## 2. Authentication & Session Expiry Behavior

### 2.1 Idle & Cryptographic Session Expiration
- When any authenticated API request returns HTTP 401 Unauthorized or HTTP 403 Forbidden:
  1. The API client intercepts the error.
  2. `clearSessionToken()` is invoked.
  3. UI dispatches an auth-denied transition to `surface=secure-entry`.
  4. Secure Entry displays an alert badge: `"Your session has expired. Please authenticate with your passkey to resume."`

### 2.2 Server Restart / Desynchronization
- If the backend restarts, generating a new `instance_id` in `/api/v1/runtime/status`:
  1. `RuntimeAvailability` detects the instance mismatch.
  2. It immediately purges client session tokens.
  3. It sets UI state to `RECOVERING` and forces a clean login ceremony.

---

## 3. Form Validation & Control State Rules

### 3.1 Button Enabled / Disabled Matrix
1. **WebAuthn Trigger Buttons:** Disabled during ongoing cryptographic assertion/creation (`loading === true`) to prevent concurrent WebAuthn requests which browser engines explicitly reject.
2. **Backtest Execution Button:**
   - **Disabled** if: No strategy selected, no dataset chosen, date range is inverted (start date >= end date), or backtest engine is currently running.
   - **Enabled** if: Valid strategy + valid dataset + date range >= 1 day + engine idle.
3. **Strategy Promotion Button:** Disabled if strategy quality metrics fail minimum threshold (e.g. Max Drawdown > 25% or Profit Factor < 1.0) unless overridden with Owner override flag.
4. **Token Generation Button:** Disabled if target email/identifier format is invalid or term length is unselected.

### 3.2 Destructive Action Confirmation
All destructive or high-risk actions require explicit two-stage modal confirmation:
- **Emergency Global Execution Hold:** Requires typing the confirmation word `HOLD`.
- **User Account Revocation / Deletion:** Requires typing the user's SX-ID / Email.
- **Hardware Passkey Revocation:** Displays warning that user may be permanently locked out if no backup keys exist.
- **Strategy Demotion / Quarantining:** Requires inputting a mandatory audit reason string.

---

## 4. Tables, Grids & Data Presentation

### 4.1 Sorting, Filtering & Search Behavior
- **Search Inputs:** Debounced at 250ms for responsive text filtering across tables (User directory, Strategies, Orders, Audit events).
- **Column Sorting:** Clicking table header cycles through: `Ascending (▲)` -> `Descending (▼)` -> `Default Unsorted`.
- **Status Filters:** Multi-select pills (e.g., `ALL`, `ACTIVE`, `SUSPENDED`, `EXPIRED`, `PENDING`).

### 4.2 Empty, Loading & Error State Behaviors
- **Loading State:** Shimmering animated skeleton loaders matching exact column widths (no generic center spinner jarring layout shift).
- **Empty State:** High-density descriptive card with icon, clear message (e.g. "No backtest runs found for selected dataset"), and primary action button (e.g. "Run First Backtest").
- **Error State:** In-line error card displaying error details, backend HTTP status code, and "Retry Query" action.

---

## 5. Modals, Drawers & Overlay Ergonomics

### 5.1 Modal Lifecycle Rules
- **Escape Key:** Pressing `Esc` closes non-critical modals. Modals with unsaved changes or active cryptographic ceremonies ignore `Esc` to prevent data loss.
- **Backdrop Click:** Clicking the dimmed backdrop outside the modal card closes view-only modals, but is disabled on multi-step wizards (e.g. `AddStrategyModal`, `FirstTimeCustomerFlow`).
- **Focus Trapping:** Active modal traps keyboard focus (`Tab` / `Shift+Tab`) within modal bounds for accessibility compliance.
- **Body Scroll Lock:** Opening any modal sets `document.body.style.overflow = "hidden"`, preventing background page scrolling.

---

## 6. Live Safety & Execution Invariants

### 6.1 Read-Only & Disarmed Guarding
- UI displays permanent top-right security badges indicating safety lock status:
  - `READ_ONLY: TRUE`
  - `BROKER MUTATION: ZERO`
  - `MODE: PAPER / SIMULATED`
- All manual or automated order dispatch buttons route exclusively to the local simulated matching engine. Any attempt to send live broker mutations is blocked by UI client guards and server-side safety locks.
