# AlgoFortis — UI Copy & Text Inventory
**Authoritative User-Facing Strings, Warnings, Errors, Headings & Status Copy**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Classification Methodology
All strings in this inventory are tagged with an authoritative design governance label:
- **`[KEEP EXACT]`**: Required for security invariants, regulatory compliance, or exact brand alignment.
- **`[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]`**: The underlying meaning is mandatory, but UX copywriters/designers may refine tone and phrasing.
- **`[LEGACY / REMOVE IN REDESIGN]`**: Deprecated strings or legacy placeholder text that must be removed.

---

## 2. Master String Inventory

### 2.1 Brand, Taglines & Primary Surface Headings

| Copy String | UI Location | Classification | Usage Context |
|---|---|---|---|
| `"AlgoFortis"` | Global Header, Logo, Tab Title | `[KEEP EXACT]` | Official product brand name. |
| `"Trading Research & Risk OS"` | Header Subtitle, Landing Hero | `[KEEP EXACT]` | Authoritative product tagline. |
| `"Institutional Trading Research & Risk Operating System"` | Public Landing Hero (`CinematicHero.tsx`) | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Main landing page headline. |
| `"Deterministic Replay. Microsecond Precision. Zero Live Broker Mutation."` | Landing Page Subhead | `[KEEP EXACT]` | Core architectural guarantee. |
| `"Secure Entry Gate"` | Auth Card Header (`SecureEntryApp.tsx`) | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Authentication card title. |
| `"Owner Master Control Center"` | Owner Dashboard Home Header | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Owner workspace title. |
| `"Trader Portfolio & Research Console"` | User Dashboard Home Header | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | User workspace title. |
| `"Deterministic Backtesting Laboratory"` | Backtest Screen Title | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Backtesting module header. |

---

### 2.2 Invariant Badges & Live Safety Copy

| Copy String | UI Location | Classification | Usage Context |
|---|---|---|---|
| `"READ_ONLY: TRUE"` | Header Safety Pill | `[KEEP EXACT]` | Permanent read-only safety indicator. |
| `"DISARMED: TRUE"` | Header Safety Pill | `[KEEP EXACT]` | Permanent broker mutation disarmed indicator. |
| `"BROKER MUTATION: ZERO"` | Status Bar | `[KEEP EXACT]` | Invariant execution guarantee. |
| `"GLOBAL EXECUTION HOLD: ENGAGED"` | Emergency Banner | `[KEEP EXACT]` | Alert banner when Safe Mode is triggered by Owner. |
| `"LIVE READINESS: SIMULATED MATCHING ENGINE"` | Paper Trading Header | `[KEEP EXACT]` | Identifies paper daemon matching authority. |

---

### 2.3 Authentication, WebAuthn & Recovery Strings

| Copy String | UI Location | Classification | Usage Context |
|---|---|---|---|
| `"Authenticate with Passkey"` | Login Button (`ReturningUserFlow.tsx`) | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Primary WebAuthn login button. |
| `"Waiting for security key or biometric verification..."` | WebAuthn Modal | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | During hardware touch ceremony. |
| `"Touch your security key or verify biometrics on your device."` | WebAuthn Subtext | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Hardware instruction prompt. |
| `"Passkey authentication failed. Please retry or use emergency recovery."` | Login Error Banner | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Assertion signature mismatch or timeout. |
| `"Redeem Single-Use Activation Token"` | Onboarding Header | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | First-time customer onboarding. |
| `"Activation token is invalid, expired, or has already been redeemed."` | Activation Error | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Token redemption failure. |
| `"Appliance Bootstrap Authority Required"` | Owner Setup Header | `[KEEP EXACT]` | First-run appliance bootstrap title. |
| `"Your session has expired. Please re-authenticate with your passkey."` | Session Expiry Toast | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | HTTP 401 interception notification. |
| `"Account is currently suspended. Please contact the platform Owner."` | Suspension Banner | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | HTTP 403 user suspended notification. |

---

### 2.4 Runtime Availability & Connectivity Messages

| Copy String | UI Location | Classification | Usage Context |
|---|---|---|---|
| `"AlgoFortis is starting"` | `RuntimeAvailability.tsx` | `[KEEP EXACT]` | Displayed while server starts up. |
| `"Waiting for the local runtime to become ready."` | `RuntimeAvailability.tsx` | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Subtext during initialization. |
| `"Reconnecting to AlgoFortis"` | `RuntimeAvailability.tsx` | `[KEEP EXACT]` | Displayed during automatic retry polling. |
| `"AlgoFortis is unavailable"` | `RuntimeAvailability.tsx` | `[KEEP EXACT]` | Alert title when process is unreachable. |
| `"The local runtime is unavailable. Reopen AlgoFortis to restart it, or retry the connection."` | `RuntimeAvailability.tsx` | `[KEEP EXACT]` | Actionable recovery instructions for desktop app. |
| `"Retry connection"` | `RuntimeAvailability.tsx` | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Manual retry button text. |

---

### 2.5 Destructive Action & Confirmation Modals

| Copy String | UI Location | Classification | Usage Context |
|---|---|---|---|
| `"CONFIRM GLOBAL EXECUTION HOLD"` | Safe Mode Modal Header | `[KEEP EXACT]` | Emergency freeze confirmation title. |
| `"WARNING: This action immediately freezes all active trading daemons, order matching queues, and paper execution sessions across all users."` | Safe Mode Modal Body | `[KEEP EXACT]` | High-severity emergency warning. |
| `"Type HOLD to confirm this emergency action:"` | Safe Mode Input Label | `[KEEP EXACT]` | Verification input prompt. |
| `"Confirm Account Suspension"` | Suspend User Modal | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Modal title before suspending user. |
| `"Enter reason for audit record:"` | Suspend / Revoke Input | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Mandatory audit entry justification. |
| `"Revoke Hardware Security Key"` | Revoke Device Modal | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Confirmation title for passkey revocation. |
| `"Are you sure you want to revoke this passkey? If you have no other security keys registered, you will lose access to your account."` | Revoke Device Body | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Lockout risk warning text. |

---

### 2.6 Empty State & Informational Copy

| Copy String | UI Location | Classification | Usage Context |
|---|---|---|---|
| `"No backtest runs found. Select a strategy and dataset above to launch your first deterministic simulation."` | Backtest Screen | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Empty historical backtest ledger. |
| `"No active paper trading sessions. Promote an approved strategy to start simulated execution."` | Paper Trading Screen | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Empty paper daemons list. |
| `"No invitation tokens currently pending redemption."` | Access Registry | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Empty invitations table. |
| `"No audit events recorded in the current filter window."` | Audit Screen | `[FUNCTIONALLY REQUIRED BUT COPY MAY CHANGE]` | Empty audit search results. |

---

### 2.7 Deprecated / Legacy Strings to Remove

| Legacy Copy String | Current Location | Classification | Migration Instruction |
|---|---|---|---|
| `"AlgoFortis Enterprise Control Center"` | Legacy headers / comments | `[LEGACY / REMOVE IN REDESIGN]` | Replace with `"AlgoFortis Trading Research & Risk OS"`. |
| `"Enter password"` | Legacy mock prototypes | `[LEGACY / REMOVE IN REDESIGN]` | Remove completely; product uses WebAuthn exclusively. |
| `"Simulated Sentinel Engine v1"` | Footer comment | `[LEGACY / REMOVE IN REDESIGN]` | Replace with `"AlgoFortis Core Engine v1"`. |
