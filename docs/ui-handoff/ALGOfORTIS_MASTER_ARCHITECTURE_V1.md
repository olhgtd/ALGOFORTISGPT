# AlgoFortis — Master Architecture Contract V1
**Authoritative & Frozen Architecture Specification**

> **Document Status**: `FROZEN — OWNER MASTER ARCHITECTURE CONTRACT V1`  
> **Brand**: AlgoFortis  
> **Tagline**: Trading Research & Risk OS  
> **Precedence Level**: Supreme Architecture Authority (Governs all subsequent design, security, packaging, backend, and frontend phases)  
> **Target Platform**: Windows 10/11 x64 (Primary V1 Desktop Local; VPS and Remote Engine Ready)

---

## 1. Executive Architecture

AlgoFortis is an institutional-grade desktop trading research, simulation, and risk operating system. It provides an isolated, deterministic, and fail-closed environment for developing, evaluating, stress-testing, and executing rule-based algorithmic trading strategies.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              ALGOFORTIS FOUR-LAYER TOPOLOGY                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ LAYER A: DESKTOP CLIENT ] (Windows App / WebView2 / React UI)                       │
│    ├── Visual Workspace, Charts & Governance Dashboards                                │
│    ├── Local Host Security & Session Management                                        │
│    └── Versioned Engine Client Adapter (LocalEngineClient / RemoteEngineClient)        │
│                                │                                                       │
│                                ▼                                                       │
│  [ LAYER B: TRADING RUNTIME ] (Python Engine / Deterministic Backtest / Paper)        │
│    ├── Core Backtesting Engine & Walk-Forward Optimizer                                │
│    ├── Paper Trading Engine & Replay Market Feed                                       │
│    ├── Strategy Signal Generation & Strategy Quality Authority                         │
│    ├── Risk Engine, Protective Stop/Target Supervision & Capital Allocation            │
│    └── Order Ledger, SQLite Persistence & Local Safety Authority                       │
│                                │                                                       │
│                                ▼                                                       │
│  [ LAYER C: CENTRAL ACCOUNT AUTHORITY ] (AWS Cloud / Cloud Identity)                  │
│    ├── Global User Identity (SX-U- / AF-U-) & WebAuthn RP Authority                   │
│    ├── Device Registry (Max 3 Devices) & Asymmetric Device Key Binding                 │
│    ├── High-Assurance Account Recovery Authority & Rate Limiting Enforcement           │
│    └── Signed Offline Entitlement Leases (7-day validity)                              │
│                                │                                                       │
│                                ▼                                                       │
│  [ LAYER D: STORAGE & SECRET PROVIDERS ]                                               │
│    ├── LocalDataStore (%LOCALAPPDATA%\AlgoFortis\databases\)                           │
│    ├── LocalSecretStore (Windows CNG / TPM & DPAPI-Protected Secrets)                  │
│    └── CloudAccountStore (Private AWS RDS PostgreSQL + KMS)                            │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Architectural Decoupling Invariant
The Desktop Client (Layer A) **must never directly import or execute internal trading-engine Python classes**. All interaction between UI and Trading Runtime is strictly mediated by a versioned, schema-enforced Engine API boundary (`/api/v1/`). In V1, this communication occurs via a local high-performance loopback IPC/HTTP interface (`LocalEngineClient`). In future releases, this identical contract enables remote execution (`RemoteEngineClient`) without altering UI components or trading business logic.

---

## 2. Brand Identity

```
┌───────────────────────────┬────────────────────────────────────────────────────────────┐
│ Brand Element             │ Authoritative Specification                                │
├───────────────────────────┼────────────────────────────────────────────────────────────┤
│ Product Name              │ AlgoFortis                                                 │
│ Tagline                   │ Trading Research & Risk OS                                 │
│ Logo                      │ Owner-Approved AlgoFortis Shield/Geometric Monogram        │
│ Color Palette             │ Deep Space (#090E17), Cyan Accent (#38BDF8), Slate (#94A3B8│
│ Target Binary             │ AlgoFortis.exe (C# / .NET WebView2 Native Wrapper)         │
│ Target Installer          │ AlgoFortis-Setup.exe (Inno Setup x64 Authenticode-signed)  │
│ Install Directory         │ C:\Program Files\AlgoFortis                                │
│ User Data Directory       │ %LOCALAPPDATA%\AlgoFortis                                  │
│ Shortcut Labels           │ AlgoFortis (Desktop, Start Menu Programs Group)            │
└───────────────────────────┴────────────────────────────────────────────────────────────┘
```

### 2.1 Internal Identity Stability & Migration Boundary
To prevent data corruption, cryptographic breakage, or migration risk:
1. **Database Schemas & Internal IDs**: Historical schema IDs, table structures, column definitions, and cryptographic hash salts remain stable.
2. **Permanent User Identifiers**: Accounts retain canonical immutable IDs (`SX-U-XXXX-XXXX` internally, aliasable as `AF-U-XXXX-XXXX` for user presentation).
3. **Configuration & Data Migration**: The runtime automatically discovers legacy `%LOCALAPPDATA%\SentinelX` data roots and migrates them safely to `%LOCALAPPDATA%\AlgoFortis` without loss of audit evidence or security credentials.

---

## 3. Deployment Profiles

AlgoFortis architecture natively supports three distinct deployment profiles using modular runtime adapters:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                DEPLOYMENT PROFILE MATRIX                               │
├──────────────────────┬────────────────────────┬───────────────────┬────────────────────┤
│ Dimension            │ PROFILE 1:             │ PROFILE 2:        │ PROFILE 3:         │
│                      │ DESKTOP_LOCAL (V1 NOW) │ WINDOWS_VPS (SOON)│ REMOTE_ENGINE (V2) │
├──────────────────────┼────────────────────────┼───────────────────┼────────────────────┤
│ UI Location          │ Local Windows PC       │ Local / RDP       │ Local Windows PC   │
│ Engine Location      │ Local Windows PC       │ Windows VPS       │ Remote VPS / Cloud │
│ UI-Engine Transport  │ Localhost Loopback     │ Localhost / IPC   │ HTTPS / mTLS / WSS │
│ Engine Client        │ LocalEngineClient      │ LocalEngineClient │ RemoteEngineClient │
│ Broker Credentials   │ Local DPAPI / CNG      │ VPS DPAPI / CNG   │ Remote VPS Vault   │
│ Trading Data         │ Local Parquet / SQLite │ VPS Parquet/SQLite│ Remote Database    │
│ Cloud Dependency     │ Zero for Trading       │ Zero for Trading  │ Zero for Trading   │
│ Hardware Security    │ Client TPM / DPAPI     │ VPS DPAPI / TPM   │ Remote HSM / DPAPI │
└──────────────────────┴────────────────────────┴───────────────────┴────────────────────┘
```

### 3.1 Profile 1: DESKTOP_LOCAL (Primary V1)
- UI and Trading Runtime run on the same physical Windows PC.
- Complete offline capability: all market data, backtest results, strategies, and broker keys reside locally.
- Cloud connectivity is used exclusively for account authentication, device registration, and entitlement lease renewal.

### 3.2 Profile 2: WINDOWS_VPS (Near-Term Evolution)
- Same unified AlgoFortis package deployed on a dedicated Windows Server VPS.
- Zero trading engine rewrite: operates via identical `RuntimeController` and `RuntimePaths` models configured for server environment (headless execution, Windows service integration, DPAPI key storage, firewall isolation).

### 3.3 Profile 3: REMOTE_ENGINE (Future Architecture)
- Desktop UI runs on user PC; Trading Runtime runs on high-availability VPS/Server.
- UI communicates with runtime through `RemoteEngineClient` over mutually authenticated TLS (mTLS) with token-bound authorization.
- Engine core logic, risk validation, and execution rules remain 100% identical.

---

## 4. Local vs Cloud Boundaries & Data Authority

AlgoFortis enforces a strict, unidirectional security boundary between central cloud authority and local trading sovereignty.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOVEREIGNTY & SYNC BOUNDARY                             │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│ SERVER-AUTHORITATIVE (Cloud May Sync)     │ LOCAL-ONLY / NEVER CLOUD-SYNCED            │
├───────────────────────────────────────────┼────────────────────────────────────────────┤
│ ✓ Account Identity & Global Subject ID    │ ✗ Broker API Keys & API Secrets            │
│ ✓ WebAuthn Public Credentials             │ ✗ Trading Strategies & Proprietary Code    │
│ ✓ Device Registry (device_id, public key) │ ✗ Trade Execution History & Order Ledgers  │
│ ✓ Device Trust & Revocation State         │ ✗ Live Positions, Margin & Account Balance │
│ ✓ Recovery Health & Tier States           │ ✗ Device Private Keys (TPM / DPAPI blobs)  │
│ ✓ Signed Entitlement Leases               │ ✗ Local Historical Parquet & Replay DBs    │
│ ✓ Non-sensitive Account Preferences       │ ✗ Raw Debug & Local Trace Logs             │
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

> **CORE SOVEREIGNTY RULE**:  
> Trading intelligence, strategy IP, financial balances, and broker secrets **NEVER leave the local machine**. Even encrypted blobs of broker credentials will not be stored in the central cloud.

---

## 5. Authentication Architecture

AlgoFortis uses an institutional, phishing-resistant authentication hierarchy anchored by FIDO2/WebAuthn passkeys.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         ALGOFORTIS AUTHENTICATION HIERARCHY                            │
├───────────────────────────────────┬────────────────────────────────────────────────────┤
│ Primary Method                    │ FIDO2 / WebAuthn Hardware Passkeys & Platform Keys │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ Tier 1 Fallback                   │ Verified Primary Email OTP                         │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ Tier 2 Fallback                   │ Verified Secondary Phone OTP (Optional)            │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ Tier 3 Emergency                  │ 8 Pre-Generated Single-Use Recovery Codes          │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ Tier 4 Fallback                   │ Owner-Assisted Out-of-Band Manual Recovery         │
└───────────────────────────────────┴────────────────────────────────────────────────────┘
```

### 5.1 Single Super Owner Governance (V1)
- All administrative operations (invitation, suspension, renewal, manual revocation) are attributed to the single authoritative Super Owner actor (`OWNER-001`).
- Multi-owner quorum and enterprise role hierarchies are explicitly **DEFERRED to V2**.

### 5.2 Activation Lifecycle & 24-Hour Expiration (OD-AUTH-01, OD-AUTH-11)
- User onboarding uses single-use activation codes (`SX-ACT-XXXX-XXXX-XXXX` / `AF-ACT-XXXX-XXXX-XXXX`).
- Fixed **24-hour expiration window** from issuance timestamp.
- Expired codes cannot auto-revive. Reissuance is an explicit, manual action by `OWNER-001`.

---

## 6. WebAuthn vs Device Identity Key System

AlgoFortis establishes a fundamental, permanent architectural separation between **User Authentication** and **Device Proof**:

```
┌───────────────────────────────────────┬────────────────────────────────────────────────┐
│ 1. WebAuthn Credential                │ 2. Device Identity Key                         │
├───────────────────────────────────────┼────────────────────────────────────────────────┤
│ Purpose: User Authentication          │ Purpose: Ongoing Machine & Session Binding     │
│ Answers: "Who is the user?"           │ Answers: "Is this the authorized device?"      │
│ Trigger: Interactive user login       │ Trigger: Background API signing, token refresh │
│ Storage: Browser / OS Authenticator   │ Storage: Windows CNG / TPM (DPAPI fallback)    │
│ Server Stores: Credential Public Key  │ Server Stores: Device Public Key + Fingerprint │
└───────────────────────────────────────┴────────────────────────────────────────────────┘
```

> **CRITICAL RULE**: WebAuthn credentials **MUST NEVER** be repurposed for automated, background API request signing. Background machine proof is exclusively provided by the Device Identity Key.

### 6.1 Device Identity Key Hardware Hierarchy
1. **Primary**: Windows Cryptography Next Generation (CNG) backed by hardware TPM 2.0 (non-exportable asymmetric ECC NIST P-256 / RSA-2048 key).
2. **Fallback**: Software-generated asymmetric key pair with the private key encrypted using Windows Data Protection API (`CryptProtectData` / `DPAPI`) bound to the current local Windows user account.
3. **Server Registration**: Server stores `device_id`, public key, SHA-256 public key fingerprint, enrollment timestamp, and last-seen telemetry. The server **never receives the private key**.

### 6.2 Active Device Quota & Registration Limits (OD-AUTH-07)
- Maximum **3 active registered devices** per user account.
- **Strict No-Auto-Eviction Invariant**: Attempting to enroll a 4th device fails closed with an actionable prompt requiring explicit revocation of an existing registered device.

---

## 7. Session Model & Token Lifecycle

AlgoFortis utilizes a high-security dual-token architecture bound cryptographically to the registered Device Identity Key:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SESSION TOKEN LIFECYCLE                                   │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ Token Type               │ Validity / Lifetime      │ Storage & Binding Rules          │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ Access Token             │ 15 Minutes               │ In-memory only (Never disk)      │
│ Refresh Token            │ 30 Days Absolute Max     │ DPAPI-encrypted on disk          │
│ Inactivity Timeout       │ 7 Days Continuous Idle   │ Requires re-authentication       │
│ Device Binding           │ Bound to Device Key ID   │ Signature verified on refresh    │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

### 7.1 Refresh Token Rotation & Reuse Detection
1. **Single-Use Rotation**: Every successful refresh token exchange invalidates the old refresh token and issues a new cryptographically random token.
2. **Reuse Detection**: If an already-consumed refresh token is presented, the Central Account Authority treats it as an active compromise, immediately revoking the **entire device session family**.
3. **Absolute Bounded Lifetime**: Sessions expire unconditionally after 30 days regardless of activity. Sliding sessions cannot extend indefinitely.

---

## 8. Reinstall & Same-PC Device Identity Preservation

AlgoFortis ensures clean reinstallation workflows while preventing device cloning or unauthorized spoofing:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      DEVICE IDENTITY DIRECTORY SPECIFICATION                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Location: %LOCALAPPDATA%\AlgoFortis\Security\DeviceIdentity\                           │
│                                                                                        │
│ Files:                                                                                 │
│   ├── device_metadata.json   (device_id, provider_type, key_name, fp, enrolled_at)     │
│   └── device_key.blob        (DPAPI-encrypted private key for fallback provider only)  │
│                                                                                        │
│ Windows Security Descriptor:                                                           │
│   ├── Restrictive DACL: SYSTEM (FullControl) + Current User SID (FullControl)          │
│   └── Inheritance disabled, Reparse points/Junctions strictly rejected                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.1 Reinstallation Rules
1. **Normal Application Uninstall**: Removes `C:\Program Files\AlgoFortis`, but **preserves** `%LOCALAPPDATA%\AlgoFortis\Security\DeviceIdentity\`.
2. **Seamless Reinstallation**: An installer running on the same PC re-reads the preserved device metadata and resolves the TPM/CNG key or DPAPI blob. If cryptographic challenge-response succeeds, the PC reuses its existing registered device slot without consuming quota.
3. **Fail-Closed on Tampering**: If the key reference or blob is missing, corrupted, or cannot be decrypted, the client fails closed and initiates a fresh device enrollment.
4. **Hardware Substitution Prohibition**: MAC addresses, CPU serials, or NetBIOS hostnames are **strictly forbidden** as surrogates for cryptographic device keys.

---

## 9. High-Assurance Recovery Architecture

Execution of a high-assurance account recovery ceremony (via Email OTP, Phone OTP, Recovery Codes, or Owner Assistance) indicates potential loss or compromise of primary authentication credentials.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        HIGH-ASSURANCE RECOVERY IMPACT MATRIX                           │
├────────────────────────────────────────┬───────────────────────────────────────────────┤
│ Security Entity                        │ Post-Recovery State                           │
├────────────────────────────────────────┼───────────────────────────────────────────────┤
│ Active WebAuthn Credentials            │ Revoked (Must re-enroll new authenticator)    │
│ Active User Sessions (All PCs)         │ Terminated Immediately                        │
│ Active Refresh Tokens (All PCs)        │ Revoked & Purged                              │
│ Registered Devices (All PCs)           │ Marked REVOKED (Untrusted)                    │
│ Active Device Identity Keys            │ Invalidated on Central Authority              │
│ Recovery Codes                         │ Exhausted & Invalidated (New set generated)   │
│ 10-Minute Recovery Assurance Window    │ Activated for Current Session (OD-AUTH-16)    │
└────────────────────────────────────────┴───────────────────────────────────────────────┘
```

### 9.1 The 10-Minute Recovery Assurance Window (OD-AUTH-16)
Upon successful high-assurance recovery, a bounded 10-minute administrative window allows the user to configure new WebAuthn passkeys, establish a new device identity key, and generate a new set of 8 emergency recovery codes without repeated step-up authentication challenges.

---

## 10. Rate Limiting & Flow Isolation

Rate limits are strictly partitioned across independent authentication and recovery endpoints to mitigate denial-of-service and brute-force threats:

```
┌────────────────────────────┬──────────────────┬────────────────────────────────────────┐
│ Target Flow / Endpoint     │ Failure Limit    │ Progressive Lockout Escalation         │
├────────────────────────────┼──────────────────┼────────────────────────────────────────┤
│ Passkey / Login Endpoint   │ 5 Failures       │ 15 Minutes → 1 Hour → 24 Hours         │
│ Activation Redemption      │ 5 Failures       │ 15 Minutes → 1 Hour → 24 Hours         │
│ Step-Up / OTP Verification │ 3 Failures       │ 15 Minutes → 1 Hour → 24 Hours         │
│ Emergency Recovery Codes   │ 3 Failures       │ 15 Minutes → 1 Hour → 24 Hours         │
│ Global IP / Client Limiter │ Sliding Window   │ Progressive IP Throttling / HTTP 429   │
└────────────────────────────┴──────────────────┴────────────────────────────────────────┘
```

> **ISOLATION GUARANTEE**: Lockout on one endpoint (e.g. repeated failed password attempts) **never locks out independent recovery mechanisms** and **never causes account suspension**.

---

## 11. Local Trading Safety During Cloud Outage

Central auth, licensing, or network outages must never compromise the deterministic safety of locally running trading algorithms:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         OUTAGE DEGRADED MODE STATE MACHINE                             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ NORMAL CLOUD STATE ]                                                                │
│    ├── Live Central Account Authority Connected                                        │
│    ├── Active Entitlement Lease Validated                                              │
│    └── Full Workspace & Mutation Permitted                                             │
│                                │                                                       │
│                                ▼ (Cloud Outage / Network Loss)                         │
│                                                                                        │
│  [ LOCAL DEGRADED MODE: "AUTH SERVICE OFFLINE — LOCAL SAFETY CONTINUES" ]              │
│    ├── CONTINUES UNINTERRUPTED:                                                        │
│    │     ├── Active Position Monitoring & Risk Calculation                             │
│    │     ├── Protective Stop-Loss & Target Management                                  │
│    │     ├── Automated Position Liquidation on Risk Breaches                           │
│    │     └── Local Backtest & Paper Replay Engine                                      │
│    │                                                                                   │
│    └── BLOCKED UNTIL CLOUD RESTORATION:                                                │
│          ├── New User Login & Initial Activation                                       │
│          ├── New Device Enrollment & Key Registration                                  │
│          ├── Account Recovery & Password Changes                                       │
│          └── Service Entitlement Upgrades/Modifications                                │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

> **FAIL-CLOSED INVARIANT**:  
> A cloud outage **must never fail open**, must never bypass local risk rules, and must never arm live execution unexpectedly.

---

## 12. Central Cloud Stack Architecture (AWS Production Target)

The central authority runs exclusively in **AWS Region ap-south-1 (Mumbai)** adhering to a zero-trust, cost-governed infrastructure topology:

```
                                  [ Route 53 ]
                                       │
                                       ▼
                       [ Application Load Balancer ]
                         (ACM Managed TLS 1.3 / HTTPS)
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
                    ▼                                     ▼
        [ ECS Fargate: Auth API ]             [ ECS Fargate: Updates ]
          (Private Subnet VPC)                  (Private Subnet VPC)
                    │                                     │
                    ├──────────────────┬──────────────────┤
                    │                  │                  │
                    ▼                  ▼                  ▼
          [ AWS Secrets Manager] [ CloudWatch Logs ] [ KMS Encryption ]
                    │
                    ▼
          [ Amazon RDS PostgreSQL ]
            (Private DB Subnet, Multi-AZ Ready, Encrypted at Rest)
```

### 12.1 Core Infrastructure Components
1. **Compute**: Amazon ECS on AWS Fargate (Task Desired Count: 1 for Beta; auto-scaling capped).
2. **Ingress**: AWS Application Load Balancer with TLS termination via AWS Certificate Manager.
3. **Database**: Amazon RDS PostgreSQL (db.t4g.micro/small, private subnets only, TLS required, KMS at-rest encryption, automated daily snapshots).
4. **Secrets & IAM**: AWS Secrets Manager with strictly scoped IAM task execution roles.
5. **DNS & Edge**: Amazon Route 53 with health checks.
6. **Auditing**: AWS CloudTrail for control plane auditing; CloudWatch Logs with 30-day default retention.

---

## 13. AWS Cost Control & Financial Governance

```
┌───────────────────────────────────┬────────────────────────────────────────────────────┐
│ Metric / Component                │ Governance Constraint                              │
├───────────────────────────────────┼────────────────────────────────────────────────────┤
│ Monthly Budget Ceiling            │ ₹6,000 INR Total Monthly Spend                     │
│ Warning Alert 1 (Actual)          │ ₹3,000 INR (50% Budget Threshold)                  │
│ Warning Alert 2 (Forecast)        │ ₹4,500 INR (75% Budget Forecast Threshold)         │
│ Critical Alert (Actual/Forecast)  │ ₹6,000 INR (100% Budget Threshold)                │
│ Initial Task Capacity             │ 1 ECS Fargate Task (256 CPU / 512 MB RAM)          │
│ Uncontrolled Auto-Scaling         │ Disabled during Beta Phase                         │
│ CloudWatch Log Retention          │ 30 Days (Non-audit logs)                           │
└───────────────────────────────────┴────────────────────────────────────────────────────┘
```

> **BUDGET ALERT RULE**: AWS Budget alerts serve operational notifications only and **must not act as automated kill-switches** that dismantle authentication infrastructure unexpectedly.

---

## 14. Backup & Disaster Recovery Specification

AlgoFortis establishes a strict schema for exportable user data archives:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          PORTABLE BACKUP MANIFEST SCHEMA                               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Format Identifier: AlgoFortisBackup/v1                                                 │
│                                                                                        │
│ ALLOWED IN BACKUP:                                                                     │
│   ├── Non-Secret User Preferences & Workspace Layouts                                  │
│   ├── Custom Strategy YAML Configurations & Python Modules                             │
│   ├── Historical Backtest Run Artifacts & Performance Summaries                        │
│   └── User-Generated Reports & Replay Datasets                                         │
│                                                                                        │
│ STRICTLY PROHIBITED IN BACKUP:                                                         │
│   ├── Broker API Keys & Secrets                                                        │
│   ├── WebAuthn Private Credentials & Passkey Attestations                              │
│   ├── Device Identity Private Keys & DPAPI Blobs                                       │
│   ├── Access Tokens, Refresh Tokens & Active Session IDs                               │
│   └── Unhashed Recovery Codes & Temporary OTPs                                         │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 14.1 Validation Invariant
Importing an archive with an unrecognized schema version or malformed checksum fails closed immediately with zero partial state mutation.

---

## 15. Packaging, Installation & Uninstallation

AlgoFortis installs as a self-contained, enterprise Windows application:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        WINDOWS FILESYSTEM LAYOUT (x64)                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│ 1. Immutable Installation Root: C:\Program Files\AlgoFortis\                          │
│    ├── AlgoFortis.exe               (Native .NET WebView2 Shell)                       │
│    ├── runtime\python\              (Isolated, Packaged Python 3.11+ Runtime)          │
│    ├── dashboard\web\dist\          (Compiled Production UI Assets)                    │
│    ├── engine\, strategies\, data\  (Trading Engine Modules & Datasets)                │
│    └── unins000.exe                 (Authenticode-Signed Uninstaller)                  │
│                                                                                        │
│ 2. Mutable User Data Root: %LOCALAPPDATA%\AlgoFortis\                                  │
│    ├── databases\                   (Security, Governance, Core-Audit SQLite DBs)      │
│    ├── config\                      (runtime.json, identity.json)                      │
│    ├── logs\                        (launcher.log, backend.log, engine logs)           │
│    ├── Security\DeviceIdentity\     (device_metadata.json, device_key.blob)            │
│    └── runtime\                     (backend.lock, controller.lock, backend.json)      │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 15.1 Zero External Prerequisites
The installer (`AlgoFortis-Setup.exe`) packages the embedded Python runtime, compiled frontend, and WebView2 bootstrapper. The end user does **not** require Node.js, npm, pip, Python, PowerShell, or Git installed on their system.

### 15.2 Uninstall Semantics
1. **Default Clean Uninstall**: Uninstalls all files in `C:\Program Files\AlgoFortis`, but **preserves** `%LOCALAPPDATA%\AlgoFortis` to allow future updates/reinstalls without device re-enrollment.
2. **Explicit Data Purge (Optional)**: A separate, explicitly confirmed option allows users to purge all local databases and device keys with appropriate safety warnings.

---

## 16. Auto-Update & Release Management

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              AUTO-UPDATE ARCHITECTURE                                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Update Manifest: https://updates.<domain>/v1/manifest.json                             │
│                                                                                        │
│ Update Flow:                                                                           │
│   1. Manifest Retrieval & HTTPS Certificate Verification                               │
│   2. SHA-256 Checksum & Authenticode Signature Verification of Installer               │
│   3. Graceful Engine & Backend Shutdown (via RuntimeController)                        │
│   4. Silent Execution of Update Installer                                              │
│   5. Post-Update Integrity Check & Automatic Backend Relaunch                          │
│   6. Automatic Rollback to Previous Version on Initialization Failure                  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 16.1 Release Channels
- **STABLE** (Default): Production-certified builds with zero breaking changes.
- **BETA**: Opt-in pre-release channel for early feature validation.

---

## 17. Licensing & Entitlement Lease Model

AlgoFortis utilizes a cryptographically signed, cached entitlement lease allowing resilient offline operation:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                             ENTITLEMENT LEASE SCHEMA                                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ Lease Structure:                                                                       │
│   ├── user_id: SX-U-XXXX-XXXX / AF-U-XXXX-XXXX                                         │
│   ├── device_id: Cryptographic Device UUID                                             │
│   ├── tier: RESEARCH_BASIC | PRO_TRADER | INSTITUTIONAL                                │
│   ├── issued_at_utc: ISO-8601 Timestamp                                                │
│   ├── expires_at_utc: ISO-8601 Timestamp (7-day offline validity)                      │
│   ├── server_signature: Ed25519 / RSA-PSS Digital Signature                            │
│   └── anti_rollback_nonce: Monotonic System Nonce                                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 17.1 Expired Entitlement Safety Invariant (OD-AUTH-22)
When an entitlement lease expires:
- **Blocked**: Creating new backtests, launching new paper sessions, initiating live runs.
- **Always Permitted**: Inspecting existing logs, managing open protective stops, exporting proprietary strategies, and reviewing historical audit journals.

---

## 18. Telemetry, Privacy & Support Bundles

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              PRIVACY & TELEMETRY CHARTER                               │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ DEFAULT: MINIMAL OPERATIONAL TELEMETRY ONLY                                            │
│                                                                                        │
│ PERMITTED OPERATIONAL METRICS:                                                         │
│   ├── App Version & OS Build                                                           │
│   ├── Update Success / Failure Telemetry                                               │
│   ├── Coarse Crash Fingerprints & Unhandled Exceptions                                 │
│   └── Backend Initialization Health Category                                           │
│                                                                                        │
│ ABSOLUTE PROHIBITION (NEVER TRANSMITTED):                                              │
│   ├── Trading Strategy Logic, Source Code, or Formulas                                 │
│   ├── Account Balances, Positions, Margins, or P&L Values                              │
│   ├── Order Payloads, Executions, or Broker Logs                                       │
│   └── Broker API Secrets, Passwords, or Private Cryptographic Keys                     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 18.1 Support Bundle Generator
User-initiated support requests use the built-in Support Bundle generator, which sanitizes all file paths, strips sensitive authentication tokens, redacts personal email addresses, and provides a preview before transmission.

---

## 19. Technical Identity, Versioning & Domain Structure

### 19.1 Versioning Scheme
- **Application**: Semantic Versioning (`SemVer 2.0.0`, e.g., `1.0.0`, `1.0.0-beta.1`).
- **Engine API**: Independent URI path versioning (starting at `/api/v1/`).
- **Database Schema**: Sequential integer migration versions (`schema_version = 1, 2, 3...`).
- **Backup Manifest**: Versioned contract (`AlgoFortisBackup/v1`).

### 19.2 Legal Publisher & Domain Architecture
- **Legal Publisher**: `CONFIGURABLE_PENDING_LEGAL_ENTITY` (Configured in build pipelines).
- **Domain Structure**: Production domains use standard subdomains (`auth.<domain>`, `api.<domain>`, `updates.<domain>`, `status.<domain>`). Exact domain name is passed via deployment configuration.

---

## 20. Windows Desktop Shell Architecture

The AlgoFortis Windows launcher is implemented in C# utilizing Microsoft Edge WebView2:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        ALGOFORTIS RUNTIME PROCESS HIERARCHY                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ AlgoFortis.exe ] (C# .NET Form + WebView2 Embedded Browser)                         │
│    ├── Single-Instance Mutex: "Global\AlgoFortis_Desktop_App_Instance_Mutex"          │
│    ├── Spawns/Supervises Background Backend Controller                                 │
│    └── WebView2 Sandbox Root: %LOCALAPPDATA%\AlgoFortis_WebView2                       │
│                                │                                                       │
│                                ▼ (Spawns via hidden window)                            │
│  [ python.exe ] (Packaged Python Backend via RuntimeController)                        │
│    ├── Binds strictly to 127.0.0.1 on OS-allocated retained port                       │
│    ├── Validates Host/Origin headers to prevent DNS rebinding                          │
│    ├── Authenticated loopback-only control channel with private control secret         │
│    └── Serves compiled frontend at http://localhost:<port>/                            │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 21. VPS & Remote-Engine Evolution Path

The architecture guarantees seamless evolution across deployment models:

1. **VPS Deployment (Profile 2)**:
   - Run `python.exe -m dashboard.runtime.controller start --mode PRODUCTION` as a Windows Service or Startup task.
   - Connect via local RDP or loopback proxy. Zero engine modifications needed.
2. **Remote Engine Deployment (Profile 3)**:
   - Implement `RemoteEngineClient` implementing the existing `EngineClient` abstract base class.
   - Stream real-time ticks, bars, order updates, and logs via authenticated WebSockets over mTLS.
   - Desktop UI connects transparently to the remote engine endpoint with identical visual rendering.

---

## 22. Explicitly Deferred Features (V2 Scope)

The following features are formally deferred and **must not be implemented in V1**:
- Multi-region AWS deployments.
- Multi-owner governance or administrative quorum schemes.
- Enterprise Single Sign-On (SAML / OIDC).
- Mobile trading applications.
- Cloud synchronization of proprietary strategies or broker secrets.
- Full live execution (real-money order placement).
- Push-based instant session termination across roaming devices.

---

## 23. Explicitly Forbidden Implementations

The following patterns are **permanently forbidden**:
1. Storing broker credentials in any central or cloud database.
2. Storing or transmitting plaintext refresh tokens or passwords.
3. Establishing device trust based on MAC address, hostname, or IP address.
4. Silent automatic eviction of registered devices.
5. Allowing cloud outages to fail open or disarm local safety controls.
6. Permitting central authentication services to place live broker orders.
7. Cloud-syncing private device keys or DPAPI blobs.
8. Passing secrets or authentication tokens in URL query strings.
9. Bypassing WebAuthn passkey requirements for production administrative actions.
10. Weakening existing NTFS ACL enforcement or security store permissions.

---

## 24. Current Live Execution Safety Lock

Until an explicit, separate Owner-approved live execution phase:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          LIVE EXECUTION SAFETY LOCK INVARIANTS                         │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ READ_ONLY             = true                                                           │
│ DISARMED              = true                                                           │
│ live_global_hold      = true                                                           │
│ broker mutation       = ZERO                                                           │
│ real broker connection= NONE                                                           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 25. Migration Constraints (SentinelX -> AlgoFortis)

1. **Data Migration**: Existing `%LOCALAPPDATA%\SentinelX` directories will be safely discovered and migrated to `%LOCALAPPDATA%\AlgoFortis` during first run of AlgoFortis V1.
2. **Backward Compatible IDs**: User identifiers (`SX-U-`) and database schemas are preserved to ensure zero audit history loss.
3. **Registry & Shortcuts**: Inno Setup installer cleanly replaces previous SentinelX shortcuts and Start Menu entries with AlgoFortis.

---
*AlgoFortis Master Architecture Contract V1 is hereby FROZEN and AUTHORITATIVE.*
