# AlgoFortis — Authentication & Security UI Requirements
**Authoritative Authentication, Passkey, Device & Recovery Architecture Specification**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Classification Overview
Authentication in AlgoFortis is built on FIDO2/WebAuthn hardware-bound public-key cryptography. To ensure complete clarity for the external frontend engineering team, all authentication requirements are strictly classified into:
- **`[IMPLEMENTED TODAY]`**: Fully functional in current production client & backend.
- **`[FROZEN FOR FUTURE IMPLEMENTATION]`**: Architecturally approved and locked in Master Contracts, scheduled for subsequent releases.
- **`[NOT CURRENTLY IMPLEMENTED]`**: Explicitly out of scope or intentionally omitted for security invariants.

---

## 2. Authentication Requirements by Category

### 2.1 WebAuthn / FIDO2 Passkey Ceremonies
- **`[IMPLEMENTED TODAY]` Hardware-Bound WebAuthn Authentication:**
  - Standard `navigator.credentials.get()` ceremony using ES256 (-7) and RS256 (-257) algorithms.
  - Server challenge issuance with 60-second TTL.
  - User verification support (`preferred` / `required`).
  - Supports YubiKey, Nitrokey, Apple TouchID, Apple FaceID, Windows Hello, Android Biometrics.
- **`[IMPLEMENTED TODAY]` Discoverable Passkeys (Resident Keys):**
  - Identifier-less login allowing users to authenticate without entering an email/username when using supported platform authenticators.
- **`[IMPLEMENTED TODAY]` Cross-Platform Security Keys:**
  - Dedicated UI guidance and prompts for external USB-A / USB-C / NFC hardware tokens.
- **`[FROZEN FOR FUTURE IMPLEMENTATION]` Multi-Passkey Conditional UI (WebAuthn Autofill):**
  - Seamless inline browser autofill dropdown for passkey discovery on username input focus (`autocomplete="webauthn"`).

---

### 2.2 Account Activation & First-Time Onboarding
- **`[IMPLEMENTED TODAY]` Cryptographic Token Redemption:**
  - Single-use alphanumeric/UUID invitation token entry.
  - Client-side token format validation before submission.
  - Transition from `PENDING_ACTIVATION` to `ACTIVE` lifecycle state upon successful key attestation.
- **`[IMPLEMENTED TODAY]` Mandatory Initial Key Enrollment:**
  - Customer cannot complete onboarding without enrolling at least one physical/platform authenticator.
  - Friendly label assignment during registration (e.g. "Work YubiKey 5C").
- **`[NOT CURRENTLY IMPLEMENTED]` Plaintext Password Creation:**
  - Passwords are fundamentally forbidden in AlgoFortis architecture. Zero password inputs or password reset flows exist.

---

### 2.3 Appliance Bootstrap & Owner Authority
- **`[IMPLEMENTED TODAY]` Terminal Bootstrap Key Ceremony:**
  - One-time appliance initialization using CLI/console bootstrap secret header `x-algofortis-bootstrap`.
  - Irreversible consumption of bootstrap token upon Primary Owner credential registration.
  - Immediate promotion to `Role.OWNER` with full governance privileges.
- **`[FROZEN FOR FUTURE IMPLEMENTATION]` M-of-N Multi-Owner Governance:**
  - Quorum-based administrative actions requiring multiple hardware signatures for high-impact system mutations.

---

### 2.4 Device & Session Management
- **`[IMPLEMENTED TODAY]` Enrolled Hardware Device Registry:**
  - User settings screen lists all enrolled credentials (ID hash, friendly label, registration date, last used timestamp).
  - Ability to enroll secondary / backup hardware keys.
  - Ability to delete backup keys (minimum 1 active key invariant enforced by UI and backend).
- **`[IMPLEMENTED TODAY]` Active Session Monitoring & Revocation:**
  - User and Owner screens show active JWT sessions with IP, User Agent, login time, and idle duration.
  - One-click remote session termination.
  - Bulk "Revoke All Other Sessions" action.
- **`[IMPLEMENTED TODAY]` Owner Global Device & Session Governance:**
  - Owner can view, inspect, and revoke any user's active sessions or registered hardware devices.
- **`[FROZEN FOR FUTURE IMPLEMENTATION]` Max-Device Enforcement Alerts:**
  - Configurable policy limiting users to 3 concurrent active devices; UI prompt when limit reached with option to replace an existing device.

---

### 2.5 Security Health, Lockouts & Recovery
- **`[IMPLEMENTED TODAY]` Rate-Limiting & Lockout Feedback:**
  - Exponential backoff timers and UI countdown banners when failed authentication attempts exceed safety thresholds (5 consecutive failures = 60s cooldown).
- **`[IMPLEMENTED TODAY]` Emergency Master Recovery Key:**
  - Cryptographic emergency recovery voucher input to re-bind authenticator if hardware is lost.
- **`[IMPLEMENTED TODAY]` Owner-Assisted Recovery Flow:**
  - Owner can reissue activation invitation to an existing user whose authenticators were lost or compromised.
- **`[FROZEN FOR FUTURE IMPLEMENTATION]` Recovery Assurance Window:**
  - 48-hour security delay and email/SMS broadcast notice before recovery key execution takes final effect, allowing the legitimate account owner to cancel fraudulent recovery attempts.
- **`[NOT CURRENTLY IMPLEMENTED]` SMS / Email OTP Fallback:**
  - SMS and Email OTP are intentionally excluded due to SIM-swapping and unencrypted transit vulnerabilities.

---

## 3. UI Implementation Checklist for External Frontend Team

```
[x] WebAuthn Passkey Login UI & Prompts (ReturningUserFlow.tsx)
[x] First-Time Token Redemption UI (FirstTimeCustomerFlow.tsx)
[x] Owner First-Run Setup UI (OwnerSetupFlow.tsx)
[x] Emergency Recovery Key UI (HelpRecoveryFlow.tsx)
[x] Real-Time Device Registry & Key Revocation UI
[x] Active Session Table & Remote Termination UI
[x] Fail-Closed Session Expiry & Auto-Redirect
[ ] WebAuthn Conditional UI (Autofill integration) [FROZEN]
[ ] Multi-Owner Quorum Approvals UI [FROZEN]
[ ] Recovery Assurance Delay Notification [FROZEN]
```
