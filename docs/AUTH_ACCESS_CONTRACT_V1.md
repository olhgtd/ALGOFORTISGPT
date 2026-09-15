# SentinelX V1 — Authoritative Authentication, Access & Service Entitlement Contract

> **Document Status**: `FROZEN — SENTINELX V1 AUTH / ACCESS BEHAVIORAL CONTRACT`  
> **Scope**: SentinelX V1 Production Authentication, Access Registry, Service Entitlements, Credential Lifecycle, Device Quotas, Recovery Workflows & Governance Authority  
> **Precedence Level**: Mandatory System Contract (Overrides generic AI assumptions; governs all subsequent backend/database/API implementations)

---

## 1. Executive Summary & Core Principles

This document constitutes the authoritative specification for identity, authentication, access control, credential lifecycles, service entitlements, recovery procedures, and governance authority in SentinelX V1.

### 1.1 Fundamental Security Invariants
1. **Zero-Knowledge User Secrets**: The SentinelX platform, database, and Owner must never store, view, log, or transmit plaintext passwords, passkey private keys, or recovery code values.
2. **Three Independent State Axes**: The system strictly separates (1) **Activation Credential State** (`DRAFT`, `INVITED`, `REDEEMED`, `EXPIRED`, `REVOKED`), (2) **Account Access State** (`PENDING`, `ACTIVE`, `SUSPENDED`, `REVOKED`), and (3) **Service Entitlement State** (`NOT_STARTED`, `ACTIVE`, `EXPIRED`).
3. **Immutable Account Identification**: A user's permanent SentinelX ID (`SX-U-XXXX-XXXX`) is assigned at account creation, is non-secret and searchable, and **never changes** across reissuances, renewals, credential resets, or recovery flows.
4. **Single-Use 24-Hour Activation**: Activation codes (`SX-ACT-XXXX-XXXX-XXXX`) are strictly single-use, valid for exactly 24 hours from issuance, and immediately consumed upon successful account initialization.
5. **Fail-Closed Governance**: Reissuing an activation credential or renewing a service entitlement can never silently bypass an account suspension or restore a permanently revoked account.
6. **Protective Supervision Invariant**: Service entitlement expiration disables new trading activity but **never** abruptly dismantles live risk/protective controls for existing market exposure.
7. **Independent Suspension Clock**: Account suspension is an administrative access block and does **not** pause, freeze, or extend the user's service entitlement clock.
8. **Non-Destructive Historical Revocation**: Account revocation terminates user access independently without rewriting historical activation facts (`REDEEMED`, `EXPIRED`) or falsely forcing a natural service expiry (`EXPIRED`).
9. **Authoritative Calendar-Month UTC Wall-Clock Semantics**: Month-based service terms use exact calendar-month arithmetic with month-end day clamping and preserved time-of-day under server-authoritative UTC wall-clock time.

---

## 2. Core Identity & Credential Model

SentinelX V1 defines three distinct identifier/credential types, each distinguished by a strict, unambiguous prefix.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               SENTINELX V1 IDENTITY MODEL                              │
├──────────────────────────┬───────────────────────────┬─────────────────────────────────┤
│ Identifier / Credential  │ Canonical Format          │ Lifecycle & Storage Semantics   │
├──────────────────────────┼───────────────────────────┼─────────────────────────────────┤
│ SentinelX ID             │ SX-U-XXXX-XXXX            │ Permanent, non-secret,          │
│                          │                           │ searchable. Stored in plaintext.│
├──────────────────────────┼───────────────────────────┼─────────────────────────────────┤
│ Activation Code          │ SX-ACT-XXXX-XXXX-XXXX     │ One-time, 24h fixed expiry.     │
│                          │                           │ Hashed at rest in production.   │
├──────────────────────────┼───────────────────────────┼─────────────────────────────────┤
│ Recovery Code            │ SX-RCV-XXXX-XXXX-XXXX     │ One-time emergency secret (8x). │
│                          │                           │ Salted hash at rest. User-only. │
└──────────────────────────┴───────────────────────────┴─────────────────────────────────┘
```

### 2.1 SentinelX ID (`SX-U-XXXX-XXXX`)
- **Nature**: Permanent account reference and lookup identifier.
- **Prefix**: `SX-U-` followed by two 4-character alphanumeric blocks (Base32/Crockford: `2-9`, `A-Z` excluding ambiguous `0`, `O`, `1`, `I`).
- **Mutability**: Immutable. Never modified, replaced, or regenerated.
- **Authentication Value**: None. A SentinelX ID alone **never** authenticates a request or unlocks sessions.

### 2.2 Activation Code (`SX-ACT-XXXX-XXXX-XXXX`)
- **Nature**: Single-use onboarding credential issued by the Owner to an invited user.
- **Prefix**: `SX-ACT-` followed by three 4-character alphanumeric blocks.
- **Expiration**: Fixed 24-hour validity window from issuance.
- **Storage**: In production, stored exclusively as a cryptographically salted one-way hash/verifier. Plaintext exists only in transit during owner invitation delivery.
- **Redemption**: Consumed atomically during first-time password/passkey enrollment. Becomes permanently unusable once redeemed or expired.

### 2.3 Recovery Codes (`SX-RCV-XXXX-XXXX-XXXX`)
- **Nature**: Set of 8 emergency single-use backup tokens generated for the user upon enrollment.
- **Prefix**: `SX-RCV-` followed by three 4-character blocks.
- **Storage**: Salted cryptographic hash at rest.
- **Visibility**: Plaintext displayed **only once** to the user at generation. The Owner and database administrators have **zero visibility** into plaintext recovery codes.

### 2.4 Normal User Authentication
- **Primary Method**: High-entropy Password or FIDO2/WebAuthn Passkey.
- **Ceremony**: Client submits login assertion (`SentinelX ID` / bound email + password / passkey signature). Server verifies against hashed verifier/public key.
- **Session Output**: Cryptographically signed, secure, HTTP-only session token.

---

## 3. Consolidation of Accepted Owner Decisions (OD-AUTH-01 through OD-AUTH-24)

| Decision ID | Title | Summary & Mandatory Specification |
|---|---|---|
| **OD-AUTH-01** | **Activation Expiry Window** | Activation code validity is fixed at exactly **24 hours**. An expired code can never revive. The Owner must manually reissue a new activation credential if the window lapses. |
| **OD-AUTH-02** | **Failed Attempt Rate Limiting** | Authentication endpoints enforce a strict **5 failed attempts threshold**, triggering progressive cooldown timers and audit logging. |
| **OD-AUTH-03** | **Multi-Path Recovery Hierarchy** | Account recovery is not solely dependent on the Owner. It supports self-service via recovery codes and verified communication channels, with Owner-assisted recovery as the ultimate fallback. |
| **OD-AUTH-04** | **Distinct Credential Formats** | Credential types must use unambiguous, distinct prefixes: `SX-U-` (Permanent ID), `SX-ACT-` (Activation Code), and `SX-RCV-` (Recovery Code). |
| **OD-AUTH-05** | **Session Invalidation on Credential Reset** | Account recovery or password reset following credential loss immediately terminates all active user sessions across all devices. A normal authenticated password change preserves the current active session while revoking all other concurrent sessions. |
| **OD-AUTH-06** | **Single Super Owner Authority (V1)** | SentinelX V1 operates under a single Super Owner authority model. No multi-owner hierarchy or quorum is implemented in V1. All administrative actions must record the executing actor (`OWNER-001`). |
| **OD-AUTH-07** | **Active Device Quota (Max 3)** | Users may register a maximum of **3 active registered devices**. Silent auto-revocation of older devices is prohibited; users or the Owner must explicitly revoke an active device to free quota. |
| **OD-AUTH-08** | **High-Assurance Recovery Device Purge** | Successful execution of high-assurance account recovery revokes all active trusted devices and active sessions. Historical device records are preserved for audit purposes and do not consume active device quota. |
| **OD-AUTH-09** | **Step-Up Guard on Recovery Code Regeneration** | Generating a new set of recovery codes requires step-up authentication (re-entering password/passkey), except when performed inside the 10-minute Recovery Assurance Window. |
| **OD-AUTH-10** | **Progressive Cooldown Escalation** | Rate-limit violations trigger progressive lockout delays: Breach 1 = 15 minutes; Breach 2 = 1 hour; Breach 3 = 24 hours. Repeated abuse blocks the specific self-service endpoint without destroying the underlying account. |
| **OD-AUTH-11** | **Manual Owner-Only Activation Reissue** | In V1, reissuing an expired or revoked activation code is strictly an Owner manual action. Users cannot self-service activation reissuance. All prior issuances remain immutable historical audit records. |
| **OD-AUTH-12** | **Passkey Portability & Fallback Resilience** | Passkeys must not be assumed to be universally portable across platforms. Passkey-only enrollments must always establish backup recovery codes or secondary verification channels. |
| **OD-AUTH-13** | **Recovery Verification Hierarchy** | The recovery hierarchy is: (1) Verified Primary Email, (2) Verified Secondary Phone (optional), (3) Independent Emergency Recovery Codes, (4) Owner-Assisted Recovery as the final manual fallback. |
| **OD-AUTH-14** | **Independent Lockout Isolation** | Lockout counters are tracked independently for Password, Activation, Recovery Code, and OTP endpoints, alongside a global abuse limiter. Exhausting attempts on one flow does not disable independent recovery mechanisms. |
| **OD-AUTH-15** | **Recovery Code Exhaustion Warnings** | Remaining recovery code counts are tracked: 2 remaining triggers a warning, 1 remaining triggers a strong warning, 0 remaining triggers a persistent critical prompt to regenerate. Depletion does not lock the active account. |
| **OD-AUTH-16** | **10-Minute Recovery Assurance Window** | Successful high-assurance recovery initiates a bounded **10-minute Recovery Assurance Window** allowing password updates, recovery code generation, and current device registration without repeated re-authentication challenges. |
| **OD-AUTH-17** | **Single Owner Risk Acceptance** | The single Super Owner model in V1 is an explicitly accepted operational single point of authority (SPOA). If the Owner is unavailable, assisted recovery and manual reissuance are delayed until Owner availability. |
| **OD-AUTH-18** | **Owner Recovery Metadata Visibility** | The Owner may view high-level recovery health status (`HEALTHY` [3-8 codes], `LOW` [1-2 codes], `NONE` [0 codes]) and last-regenerated timestamps, but **never** plaintext code values. |
| **OD-AUTH-19** | **Owner-Controlled Service Term** | The Owner assigns a service duration at creation (1 Month, 3 Months, 6 Months, 12 Months, Lifetime, or Custom duration in days/months). Duration begins at **successful first activation**, not invitation creation. Lifetime entitlements remain subject to Owner suspension/revocation. |
| **OD-AUTH-20** | **Automatic Service Expiry Lifecycle** | Service Entitlement is tracked via `ServiceEntitlementStatus` (`NOT_STARTED`, `ACTIVE`, `EXPIRED`). Expiry does not delete the user, revoke the account, or change the SentinelX ID; the user receives an access-expired state. |
| **OD-AUTH-21** | **Service Renewal & Extension** | The Owner may extend an `ACTIVE` entitlement from its current expiry, or renew an `EXPIRED` entitlement from the renewal date. Renewal retains the permanent SentinelX ID and account, does not require re-activation, and does not issue a new activation code. |
| **OD-AUTH-22** | **Service Expiry Safe Enforcement** | Service expiry fails closed for new activity (new backtests, paper sessions, live sessions, strategy executions). If live exposure exists, protective supervision (stops, risk enforcement, position reduction) remains active in a reduce-only/protection-only state. |
| **OD-AUTH-23** | **Suspension Does Not Pause Service Term** | Account suspension does not pause, freeze, or extend the user's service entitlement clock. Restoring a suspended account does not grant replacement time or auto-renew an entitlement that expired while suspended. |
| **OD-AUTH-24** | **Exact Service-Term Time Semantics** | Month-based terms (1, 3, 6, 12 Months) use exact calendar-month arithmetic anchored at `service_started_at` preserving time-of-day, clamping to month-end when the target day does not exist (e.g. 31 Jan + 1m -> 28 Feb non-leap; 31 Jan + 3m -> 30 Apr). Custom day terms use exact 24-hour periods. Server-authoritative UTC wall-clock determines expiry (`authoritative_utc_now >= service_expires_at` -> `EXPIRED`). Lifetime has no time expiry (`service_expires_at = null`). |

---

## 4. The Three Independent State Axes & Effective Access Rule

SentinelX V1 models user access across three strictly decoupled state axes. These must never be collapsed into a single generic status field.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              THREE INDEPENDENT STATE AXES                              │
├─────────────────────────┬──────────────────────────┬───────────────────────────────────┤
│ 1. ActivationStatus     │ 2. AccountAccessStatus   │ 3. ServiceEntitlementStatus       │
├─────────────────────────┼──────────────────────────┼───────────────────────────────────┤
│ DRAFT                   │ PENDING                  │ NOT_STARTED                       │
│ INVITED                 │ ACTIVE                   │ ACTIVE                            │
│ REDEEMED                │ SUSPENDED                │ EXPIRED                           │
│ EXPIRED                 │ REVOKED                  │                                   │
│ REVOKED                 │                          │                                   │
└─────────────────────────┴──────────────────────────┴───────────────────────────────────┘
```

### 4.1 State Definitions
1. **ActivationStatus** (Onboarding Credential Lifecycle):
   - `DRAFT`: Unissued access record; no activation code generated.
   - `INVITED`: Active single-use 24-hour activation code issued to user.
   - `REDEEMED`: Activation code successfully consumed during initial enrollment.
   - `EXPIRED`: 24-hour activation window elapsed without redemption.
   - `REVOKED`: Activation invitation explicitly invalidated by the Owner.

2. **AccountAccessStatus** (Identity & Governance Lifecycle):
   - `PENDING`: User identity created; awaiting initial onboarding activation.
   - `ACTIVE`: User identity verified and authorized for platform access.
   - `SUSPENDED`: Administrative hold; login and trading sessions blocked.
   - `REVOKED`: Permanent administrative termination; all access permanently killed.

3. **ServiceEntitlementStatus** (Subscription / Term Validity):
   - `NOT_STARTED`: Account has not completed initial activation; clock has not started.
   - `ACTIVE`: Current server UTC wall-clock time is strictly prior to `service_expires_at` (or Lifetime).
   - `EXPIRED`: Current server UTC wall-clock time has reached or passed `service_expires_at`; new operations blocked.

---

### 4.2 Comprehensive Three-Axis State Transition Matrix

| Initial State (`Account` · `Activation` · `Service`) | Trigger Event | Resulting `Account` | Resulting `Activation` | Resulting `Service` | Invariant Constraints & Operational Semantics |
|---|---|---|---|---|---|
| *None* | Owner Creates Access Record | `PENDING` | `INVITED` | `NOT_STARTED` | Permanent `SX-U-` ID created; 24h `SX-ACT-` code generated; service term configured (clock paused). |
| *None* | Owner Creates Draft Record | `PENDING` | `DRAFT` | `NOT_STARTED` | Permanent `SX-U-` ID created; no activation code issued. Can be deleted by Owner. |
| `PENDING` · `DRAFT` · `NOT_STARTED` | Owner Issues Activation | `PENDING` | `INVITED` | `NOT_STARTED` | 24h activation code generated; issuance recorded. |
| `PENDING` · `INVITED` · `NOT_STARTED` | 24h Activation Window Lapses | `PENDING` | `EXPIRED` | `NOT_STARTED` | Activation code expires. Account remains `PENDING`. Service clock remains `NOT_STARTED`. |
| `PENDING` · `EXPIRED` · `NOT_STARTED` | Owner Reissues Activation | `PENDING` | `INVITED` | `NOT_STARTED` | Prior code marked `EXPIRED` in history; new 24h code issued. Service term preserved. |
| `PENDING` · `INVITED` · `NOT_STARTED` | Owner Revokes Invitation | `PENDING` | `REVOKED` | `NOT_STARTED` | Invitation code invalidated. Account remains `PENDING` (allows future reissue). |
| `PENDING` · `INVITED` · `NOT_STARTED` | User Completes First Activation | `ACTIVE` | `REDEEMED` | `ACTIVE` | Activation code consumed; user sets credentials; **service clock begins at this timestamp**. |
| `ACTIVE` · `REDEEMED` · `ACTIVE` | Service Term Elapses (`utc_now >= expires_at`) | `ACTIVE` | `REDEEMED` | `EXPIRED` | User login permitted; new trading/workspaces blocked; live risk supervision enters protect-only. |
| `ACTIVE` · `REDEEMED` · `ACTIVE` | Owner Extends Active Service | `ACTIVE` | `REDEEMED` | `ACTIVE` | Calendar term added to **current expiry date** (no lost authorized time). |
| `ACTIVE` · `REDEEMED` · `EXPIRED` | Owner Renews Expired Service | `ACTIVE` | `REDEEMED` | `ACTIVE` | New term begins at **renewal timestamp**. Same ID and credentials retained; no re-activation. |
| `ACTIVE` · `REDEEMED` · `ACTIVE` | Owner Suspends Account | `SUSPENDED` | `REDEEMED` | `ACTIVE` | All sessions killed immediately; login blocked. **Service clock continues running (OD-AUTH-23)**. |
| `SUSPENDED` · `REDEEMED` · `ACTIVE` | Service Term Elapses While Suspended | `SUSPENDED` | `REDEEMED` | `EXPIRED` | Clock expires naturally while under suspension. Account remains `SUSPENDED`. |
| `SUSPENDED` · `REDEEMED` · `ACTIVE` | Owner Restores Account | `ACTIVE` | `REDEEMED` | `ACTIVE` | User can log in immediately. Original `service_expires_at` is preserved. |
| `SUSPENDED` · `REDEEMED` · `EXPIRED` | Owner Restores Account | `ACTIVE` | `REDEEMED` | `EXPIRED` | Account restored to `ACTIVE`, but user is blocked by service expiry until Owner extends/renews. |
| `ACTIVE` · `REDEEMED` · `ACTIVE` | Owner Revokes Account | `REVOKED` | `REDEEMED` | `ACTIVE` | Account revoked; login killed. **Activation remains REDEEMED; service remains ACTIVE until natural expiry**. |
| `ACTIVE` · `REDEEMED` · `EXPIRED` | Owner Revokes Account | `REVOKED` | `REDEEMED` | `EXPIRED` | Account revoked; login killed. Activation remains `REDEEMED`; service remains `EXPIRED`. |
| `PENDING` · `INVITED` · `NOT_STARTED` | Owner Revokes Account | `REVOKED` | `REVOKED` | `NOT_STARTED` | Outstanding invitation code invalidated (`REVOKED`); account permanently revoked. |
| `PENDING` · `DRAFT` · `NOT_STARTED` | Owner Revokes Account | `REVOKED` | `DRAFT` | `NOT_STARTED` | Draft unissued record marked revoked. |

---

### 4.3 Effective Access Rule (Derived Decision)

Protected SentinelX access is permitted only when **all** of the following conditions are simultaneously met:
1. `AccountAccessStatus === "ACTIVE"`
2. `ServiceEntitlementStatus === "ACTIVE"`
3. User presents valid, uncompromised credentials (password / passkey / active session) passing all rate-limit and authentication gates.

#### Effective Access Truth Table

```
┌─────────────────────────┬──────────────────────────┬─────────────────────────────┬────────────────────────────────────────────────────────┐
│ AccountAccessStatus     │ ServiceEntitlementStatus │ Effective Access Decision   │ Explanation & System Behavior                          │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ ACTIVE                  │ ACTIVE                   │ ✓ PERMITTED                 │ Full authenticated access to SentinelX workspace.      │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ ACTIVE                  │ EXPIRED                  │ ✗ BLOCKED (SERVICE EXPIRED) │ Login allowed; new operations blocked; protect-only.   │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ ACTIVE                  │ NOT_STARTED              │ ✗ BLOCKED (NOT ACTIVATED)   │ Account pending initial onboarding ceremony.           │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ SUSPENDED               │ ACTIVE                   │ ✗ BLOCKED (SUSPENDED)       │ Administrative hold; service clock running.            │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ SUSPENDED               │ EXPIRED                  │ ✗ BLOCKED (SUSPENDED+EXPIRE)│ Administrative hold; service term has also elapsed.   │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ SUSPENDED               │ NOT_STARTED              │ ✗ BLOCKED (SUSPENDED)       │ Administrative hold on unactivated account.            │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ REVOKED                 │ ACTIVE                   │ ✗ BLOCKED (REVOKED)         │ Permanent security termination; all access killed.     │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ REVOKED                 │ EXPIRED                  │ ✗ BLOCKED (REVOKED)         │ Permanent security termination; all access killed.     │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ REVOKED                 │ NOT_STARTED              │ ✗ BLOCKED (REVOKED)         │ Permanent security termination before activation.      │
├─────────────────────────┼──────────────────────────┼─────────────────────────────┼────────────────────────────────────────────────────────┤
│ PENDING                 │ NOT_STARTED              │ ✗ BLOCKED (ONBOARDING)      │ Requires initial 24h activation code redemption.       │
└─────────────────────────┴──────────────────────────┴─────────────────────────────┴────────────────────────────────────────────────────────┘
```

> **Dynamic Evaluation Invariant**: Effective access is **always dynamically evaluated** at runtime from independent authoritative fields (`AccountAccessStatus`, `ServiceEntitlementStatus`, and credentials). The system **never** creates or stores a mutable composite "effective status" column in the database.

---

## 5. Service Term & Exact Time Semantics (OD-AUTH-19, OD-AUTH-20, OD-AUTH-21, OD-AUTH-24)

### 5.1 Calendar-Month Arithmetic & Time Authority Semantics
1. **Authoritative Persisted UTC Timestamps**:
   - `service_started_at`, `service_expires_at`, `activation.issued_at`, `activation.expires_at`, and audit event timestamps are persisted exclusively as authoritative UTC wall-clock timestamps (`YYYY-MM-DDTHH:MM:SSZ`).
2. **Server-Authoritative UTC Wall-Clock Evaluation**:
   - Production service and activation expiration evaluations use a trusted backend/server-controlled UTC wall-clock (`authoritative_utc_now`):
     - `authoritative_utc_now < service_expires_at` → `ServiceEntitlementStatus = ACTIVE`
     - `authoritative_utc_now >= service_expires_at` → `ServiceEntitlementStatus = EXPIRED`
   - Client and browser clocks are strictly non-authoritative.
3. **Internal Monotonic Clock Boundaries**:
   - Monotonic clocks (e.g. `time.monotonic()` / `CLOCK_MONOTONIC`) represent elapsed duration and **must not** be used as persisted calendar timestamp authorities.
   - Monotonic clocks MAY be used internally by backend services for elapsed-duration controls (e.g. HTTP request timeouts, rate-limit cooldown elapsed durations, 10-minute Recovery Assurance Window timers).
4. **Calendar-Month Arithmetic**: Month-based service terms (1, 3, 6, 12 Months) use true **calendar-month arithmetic**, not fixed 30/90/180/365-day approximations.
5. **Anchor Point**: Calculation begins from `service_started_at` (set to the exact UTC timestamp of successful first activation or expired-service renewal).
6. **Time-of-Day Preservation**: The original time-of-day (hours, minutes, seconds) is strictly preserved in the expiration timestamp.
7. **Month-End Day Clamping**: If the target month has fewer days than the anchor day, the expiration date is clamped to the **last valid calendar day of that target month**.
   - *Example 1*: 31 January 2027 18:00:00 UTC + 1 Month → **28 February 2027 18:00:00 UTC** (non-leap year).
   - *Example 2*: 31 January 2028 18:00:00 UTC + 1 Month → **29 February 2028 18:00:00 UTC** (leap year).
   - *Example 3*: 31 January 2027 18:00:00 UTC + 3 Months → **30 April 2027 18:00:00 UTC**.
   - *Example 4*: 31 August 2026 12:00:00 UTC + 1 Month → **30 September 2026 12:00:00 UTC**.
8. **Day-Based Custom Terms**: Custom terms specified in days use exact 24-hour periods (`days * 86,400 seconds`).
9. **Lifetime Semantics**: `service_term_type: LIFETIME`, `service_expires_at: null` with no automated time expiry. Lifetime accounts remain fully subject to Owner administrative suspension and revocation.

---

### 5.2 Service Term Computation Scenarios

```text
Scenario A: Initial Enrollment & Activation Delay
  - Account Created:        1 September 2026 10:00:00 UTC
  - User Activates:         5 September 2026 14:30:15 UTC
  - Assigned Term:          3 Months
  - service_started_at:     5 September 2026 14:30:15 UTC
  - service_expires_at:     5 December 2026 14:30:15 UTC
  (The 4 days between creation and activation are not deducted from the term.)

Scenario B: Extension of Active Entitlement
  - Current Expiry:         5 December 2026 14:30:15 UTC
  - Owner Action:           Extends +3 Months on 20 November 2026
  - New service_expires_at: 5 March 2027 14:30:15 UTC
  (Added duration is appended to the existing expiry date without losing paid/authorized time.)

Scenario C: Renewal of Expired Entitlement
  - Previous Expiry:        5 December 2026 14:30:15 UTC
  - Entitlement Status:     EXPIRED (as of 5 Dec)
  - Owner Action:           Renews for 3 Months on 10 December 2026 09:00:00 UTC
  - New service_started_at: 10 December 2026 09:00:00 UTC
  - New service_expires_at: 10 March 2027 09:00:00 UTC
  (Term begins at renewal date. User logs in with existing password/passkeys; no new activation code.)

Scenario D: Month-End Clamping Calculation
  - User Activates:         31 January 2027 18:00:00 UTC
  - Assigned Term:          1 Month
  - service_expires_at:     28 February 2027 18:00:00 UTC (Clamped to Feb end; 2027 is non-leap)

Scenario E: Suspension During Active Term (OD-AUTH-23)
  - Term:                   1 September 2026 -> 1 December 2026
  - Owner Suspends Account: 10 October 2026
  - Owner Restores Account: 25 October 2026
  - Restored service_expires_at: 1 December 2026 (Unchanged)
  (Suspension does not pause or extend the service entitlement clock.)

Scenario F: Expiration While Under Suspension (OD-AUTH-23)
  - Term:                   1 September 2026 -> 1 December 2026
  - Owner Suspends Account: 10 November 2026
  - Date Lapses:            1 December 2026 (ServiceEntitlementStatus becomes EXPIRED)
  - Owner Restores Account: 15 December 2026
  - Resulting State:        AccountAccessStatus = ACTIVE, ServiceEntitlementStatus = EXPIRED
  (Restoring account does NOT auto-renew service; Owner must separately extend/renew.)

Scenario G: Conversion to Lifetime
  - Current Status:         ACTIVE (or EXPIRED)
  - Owner Action:           Converts to Lifetime on 15 December 2026
  - service_term_type:      LIFETIME
  - service_expires_at:     null
  (Lifetime does not prevent administrative Owner suspension or revocation.)
```

### 5.3 Service Expiry Safe Enforcement (OD-AUTH-22)
When `ServiceEntitlementStatus === "EXPIRED"`:
- **Blocked Operations**: Creating new backtests, launching new paper trading sessions, initiating new live trading sessions, deploying new strategies, and submitting manual risk-increasing order requests.
- **Protected Safety Operations**: If active market positions exist at the time of expiry, the trading engine enters a **Protection-Only / Reduce-Only** safe state. Existing protective stop-losses, trailing stops, risk monitors, and emergency position closure mechanisms remain fully operational.

---

## 6. Activation Issuance History Schema

Every activation issuance attempt is preserved as an immutable historical record.

```json
{
  "activationHistory": [
    {
      "id": "iss-1725120000000-1",
      "code": "SX-ACT-3N9D-88KX-99PL",
      "codeHash": "<salted-one-way-hash-in-production>",
      "issuedAt": "2026-07-01 08:00:00 UTC",
      "expiresAt": "2026-07-02 08:00:00 UTC",
      "status": "EXPIRED",
      "redeemedAt": null,
      "revokedAt": null,
      "actor": "OWNER-001",
      "notes": "Initial 24h activation window lapsed without redemption"
    },
    {
      "id": "iss-1725123600000-2",
      "code": "SX-ACT-MTEU-534T-YZUZ",
      "codeHash": "<salted-one-way-hash-in-production>",
      "issuedAt": "2026-08-31 18:25:00 UTC",
      "expiresAt": "2026-09-01 18:25:00 UTC",
      "status": "INVITED",
      "redeemedAt": null,
      "revokedAt": null,
      "actor": "OWNER-001",
      "notes": "Reissued 24h activation code following identity confirmation"
    }
  ]
}
```

---

## 7. Device Quota & Session Architecture

### 7.1 Device Quotas (Max 3 Active Registered Devices)
- **Quota Limit**: Maximum **3 active registered devices** per user account.
- **Registration**: Occurs when a user successfully authenticates on a new device and enrolls a WebAuthn passkey or receives a trusted device token.
- **No Silent Ejection**: Silent auto-eviction of older devices is prohibited. When a 4th device attempts registration, the user or Owner must explicitly revoke an existing registered device.
- **Historical Device Records**: Revoked devices are marked `REVOKED` with a timestamp and retained for audit history; they do not consume active device quota.

### 7.2 Session vs Device Distinction
- **Session**: A short-lived authentication state represented by a signed session token. Automatically expires after inactivity or absolute timeout.
- **Device**: A durable cryptographic binding (WebAuthn credential ID or device key) representing trusted hardware.
- **Revocation Rules**:
  - **User Logout**: Terminates the current session only.
  - **Normal Password Change**: Terminates all concurrent sessions except the current session; preserves registered trusted devices.
  - **Account Recovery / Reset**: Terminates **all** sessions across **all** devices and invalidates **all** registered trusted devices immediately.

---

## 8. Account Recovery Architecture

SentinelX V1 implements four tiered recovery mechanisms to guarantee availability while preventing account takeover.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    SENTINELX V1 RECOVERY FLOW HIERARCHY                   │
├───────────────────────────────────┬───────────────────────────────────────┤
│ Tier 1: Verified Email OTP        │ Primary verified self-service channel.│
├───────────────────────────────────┼───────────────────────────────────────┤
│ Tier 2: Verified Phone OTP        │ Optional secondary verified channel.  │
├───────────────────────────────────┼───────────────────────────────────────┤
│ Tier 3: Emergency Recovery Codes  │ 8 single-use codes (SX-RCV-...).      │
│                                   │ Independent emergency self-service.   │
├───────────────────────────────────┼───────────────────────────────────────┤
│ Tier 4: Owner-Assisted Recovery   │ Final manual fallback when all        │
│                                   │ self-service paths are lost.          │
└───────────────────────────────────┴───────────────────────────────────────┘
```

### 8.1 Recovery Channel Specification (OD-AUTH-13)
- **Primary Channel**: Verified Email Address.
- **Secondary Channel (Optional)**: Verified Phone Number (used where configured; recovery does **not** unconditionally require both email and phone simultaneously).
- **Independent Emergency Channel**: Set of 8 single-use Recovery Codes (`SX-RCV-XXXX-XXXX-XXXX`).
- **Final Fallback**: Owner-Assisted Recovery ceremony executed out-of-band by the Super Owner.

### 8.2 Authentication vs Account Recovery Distinction
- **Normal Passkey / Password Authentication**: Standard login verifying user identity. Does not revoke other active devices or sessions.
- **High-Assurance Account Recovery Ceremony**: Executed when primary credentials are lost. Triggers full session purge and device revocation in accordance with **OD-AUTH-08**.

### 8.3 The 10-Minute Recovery Assurance Window (OD-AUTH-16)
Upon completing high-assurance recovery:
- The system opens a bounded **10-minute Recovery Assurance Window**.
- **Permitted Scope**: Setting a new password, enrolling the current device passkey, and generating a fresh set of 8 recovery codes without repeated step-up challenges.
- **Boundary**: Does **not** grant elevated administrative or trading authority.

### 8.4 Recovery Code Replenishment & Readiness Tracking (OD-AUTH-15, OD-AUTH-18)
- Generating a new recovery code set invalidates all prior recovery codes.
- **Owner Visibility**: Displays readiness indicators (`HEALTHY`: 3–8 codes, `LOW`: 1–2 codes, `NONE`: 0 codes) and last-regenerated timestamp, but **never** plaintext code values.

---

## 9. Rate Limiting & Progressive Abuse Mitigation

SentinelX V1 enforces deterministic, flow-isolated rate limits to prevent brute-force attacks while protecting account availability from denial-of-service attempts.

### 9.1 Flow-Isolated Rate Limit Table

| Target Endpoint / Flow | Failed Attempt Policy | Escalation Cooldown Steps | Isolation Invariant |
|---|---|---|---|
| **Password Login** | 5 failed attempts | 15 minutes → 1 hour → 24 hours | Locks password verification only. Recovery codes and passkey login remain accessible. |
| **Activation Code** | 5 failed attempts | 15 minutes → 1 hour → 24 hours | Locks activation endpoint only. Other users and Owner operations unaffected. |
| **Recovery Code** | *[Technical Parameter — to be frozen during backend security design]* | 15 minutes → 1 hour → 24 hours | Locks recovery code submission only. Normal login channels unaffected. |
| **Email / Phone OTP** | *[Technical Parameter — to be frozen during backend security design]* | 15 minutes → 1 hour → 24 hours | Throttles verification & delivery to prevent flooding. |
| **Global Abuse Limiter** | *[Technical Parameter — to be frozen during backend security design]* | Progressive IP/client throttling | Throttles abusive client without modifying user account access states. |

### 9.2 Abuse Isolation Guarantee
- An unauthenticated attacker attempting brute force against a user's password or recovery code can **never** trigger account suspension (`accountStatus: "SUSPENDED"`).
- Endpoint cooldowns fail closed locally, leaving other high-assurance channels functional.

---

## 10. Owner Authority Matrix (Capabilities & Boundaries)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              OWNER GOVERNANCE BOUNDARIES                               │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│ PERMITTED OWNER POWERS                    │ STRICT SYSTEM RESTRICTIONS                 │
├───────────────────────────────────────────┼────────────────────────────────────────────┤
│ ✓ Create user access & assign service term│ ✗ CANNOT view user plaintext passwords     │
│ ✓ Issue initial 24h activation code       │ ✗ CANNOT view recovery code values         │
│ ✓ Reissue activation code for PENDING     │ ✗ CANNOT view or export passkey secrets    │
│ ✓ Extend active service entitlement       │ ✗ CANNOT bypass trading engine risk limits │
│ ✓ Renew expired service entitlement       │ ✗ CANNOT reissue code on REVOKED account   │
│ ✓ Convert entitlement to Lifetime         │ ✗ CANNOT reissue code on SUSPENDED account │
│ ✓ Temporarily suspend user account access │ ✗ CANNOT reactivate consumed tokens        │
│ ✓ Restore suspended user account access   │ ✗ CANNOT alter immutable audit history     │
│ ✓ Permanently revoke user account access  │ ✗ CANNOT silently impersonate user trades  │
│ ✓ Terminate active user sessions/devices  │ ✗ CANNOT disable live protective stops     │
│ ✓ Authorize assisted recovery fallback    │                                            │
│ ✓ View recovery health (HEALTHY/LOW/NONE) │                                            │
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

---

## 11. Prototype vs Production Implementation Boundary

```
┌───────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────────┐
│ Subsystem / Component     │ Current Prototype (Visual-Lab V3)    │ Production Authority (Backend V1)        │
├───────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────────┤
│ ID Generation             │ Client-side pseudo-random generator  │ Cryptographic CSPRNG                     │
│ Credential Storage        │ Browser localStorage                 │ Persistent DB with one-way salted hash   │
│ Expiry Enforcement        │ Date string comparison in React      │ Server UTC wall-clock & cron scheduler   │
│ Service Term Tracking     │ Prototype state fixtures             │ Server-side entitlement service          │
│ Rate Limiting             │ UI simulated feedback banners        │ Server-side sliding-window limiter       │
│ Session Authority         │ React state / mock session cookies   │ Secure signed session authority          │
│ Device Binding            │ Mock registered device lists         │ WebAuthn/passkey attestation & keys      │
│ Recovery Verification     │ Interactive mock recovery drawer     │ Cryptographic OTP & hashed code check    │
│ Audit Evidence            │ UI event history list                │ Append-only immutable Core Audit log     │
│ Notification Delivery     │ Simulated UI alert popups            │ Notification delivery adapter            │
└───────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────────┘
```

---

## 12. Contract Governance & Freeze Criteria

This document represents the frozen, authoritative SentinelX V1 Authentication, Access & Service Entitlement behavioral specification.

### 12.1 Freeze Verification Checklist
- [x] Permanent SentinelX ID format: `SX-U-XXXX-XXXX`
- [x] Single-use Activation Code format: `SX-ACT-XXXX-XXXX-XXXX` (Fixed 24-hour expiration)
- [x] Recovery Code format: `SX-RCV-XXXX-XXXX-XXXX` (8 initial codes, user-only visibility)
- [x] Three independent state axes: `ActivationStatus`, `AccountAccessStatus`, `ServiceEntitlementStatus`
- [x] Dynamic effective access derivation rule (never stored as composite mutable state)
- [x] Service term definitions and activation-anchored duration rules (OD-AUTH-19, OD-AUTH-20, OD-AUTH-21, OD-AUTH-22)
- [x] Suspension clock independence (OD-AUTH-23: suspension does not pause or extend service term)
- [x] Calendar-month arithmetic, month-end day clamping, and server-authoritative UTC wall-clock rules (OD-AUTH-24)
- [x] Non-destructive historical revocation semantics (preserves `REDEEMED`/`EXPIRED` facts; preserves service term)
- [x] Reissuance blocked on `REVOKED` and `SUSPENDED` accounts
- [x] Maximum 3 active registered devices per user with explicit revocation required
- [x] 10-minute Recovery Assurance Window upon high-assurance recovery completion
- [x] Flow-isolated progressive rate limits without invented technical constants
- [x] Implementation-neutral production architecture requirements
- [x] Full consolidation of Owner Decisions `OD-AUTH-01` through `OD-AUTH-24`

---

*This document is **FROZEN** as the authoritative SentinelX V1 Authentication, Access & Service Entitlement behavioral contract.*
