# AlgoFortis — Architecture Decision Register V1 (ADR)
**Authoritative Record of Architectural Decisions & Constraints**

> **Document Status**: `FROZEN — OWNER DECISION REGISTER V1`  
> **Brand**: AlgoFortis  
> **Valid Status Codes**: `FINAL` | `DEFERRED` | `NOT_ALLOWED` | `PENDING_EXTERNAL`

---

## Decision Index

| ID | Title | Status | Implementation Phase |
|---|---|---|---|
| **ADR-01** | Product Brand, Tagline & Visual Identity | `FINAL` | Phase 1 (Brand Migration) |
| **ADR-02** | Four-Layer Architectural Decoupling & Engine API Boundary | `FINAL` | Phase 2 (Boundary Hardening) |
| **ADR-03** | Primary Deployment Profile: Desktop Local (V1) | `FINAL` | Phase 1 (Local Runtime) |
| **ADR-04** | Windows VPS Deployment Profile Compatibility | `FINAL` | Phase 8 (VPS Ready) |
| **ADR-05** | Remote Engine Architecture & Client Adapters | `DEFERRED` | Phase 10 (Remote Engine V2) |
| **ADR-06** | Anywhere Login & Strict 3-Device Quota | `FINAL` | Phase 4 (Central Auth) |
| **ADR-07** | Separation of WebAuthn and Device Identity Keys | `FINAL` | Phase 3 (Device Security) |
| **ADR-08** | Windows CNG/TPM & DPAPI Device Key Storage Hierarchy | `FINAL` | Phase 3 (Device Security) |
| **ADR-09** | Dual-Token Model & Rotating Refresh Token Family | `FINAL` | Phase 4 (Central Auth) |
| **ADR-10** | Same-PC Reinstallation Device Identity Metadata Preservation | `FINAL` | Phase 3 (Device Security) |
| **ADR-11** | High-Assurance Recovery Device Purge & Assurance Window | `FINAL` | Phase 4 (Central Auth) |
| **ADR-12** | Flow-Isolated Rate Limiting & Progressive Cooldown Escalation | `FINAL` | Phase 4 (Central Auth) |
| **ADR-13** | 24-Hour Single-Use Activation Lifecycle | `FINAL` | Phase 4 (Central Auth) |
| **ADR-14** | Data Sovereignty & Strict Cloud Sync Boundaries | `FINAL` | Phase 2 (Storage Authority) |
| **ADR-15** | Local Trading Safety & Degraded Operation During Cloud Outages | `FINAL` | Phase 2 (Local Safety Authority) |
| **ADR-16** | Central Cloud Infrastructure Topology (AWS Mumbai ap-south-1) | `FINAL` | Phase 7 (Cloud Infrastructure) |
| **ADR-17** | AWS Cost Governance & Monthly Budget Ceiling (₹6,000) | `FINAL` | Phase 7 (Cloud Infrastructure) |
| **ADR-18** | Portable Backup Schema (`AlgoFortisBackup/v1`) & Secret Exclusion | `FINAL` | Phase 5 (Backup / Restore) |
| **ADR-19** | Default Clean Uninstall Semantics (Preserve User Data) | `FINAL` | Phase 6 (Windows Packaging) |
| **ADR-20** | Authenticode-Signed Auto-Update Architecture | `FINAL` | Phase 6 (Update Infrastructure) |
| **ADR-21** | Signed Offline Entitlement Leases (7-Day Offline Validity) | `FINAL` | Phase 4 (Entitlement Engine) |
| **ADR-22** | Privacy-Preserving Telemetry & Sanitize-First Support Bundles | `FINAL` | Phase 5 (Telemetry Authority) |
| **ADR-23** | Technical Identity, SemVer Versioning & Migration Namespaces | `FINAL` | Phase 1 (Foundation) |
| **ADR-24** | Legal Publisher Identity Specification | `PENDING_EXTERNAL` | Phase 6 (Installer Signing) |
| **ADR-25** | Central Production Domain & Subdomain Hierarchy | `PENDING_EXTERNAL` | Phase 7 (Cloud Infrastructure) |
| **ADR-26** | Windows Installer Packaging & WebView2 Desktop Shell | `FINAL` | Phase 6 (Windows Packaging) |
| **ADR-27** | Absolute Lock on Live Trading Execution Safety (DISARMED) | `FINAL` | Phase 1-10 (Continuous Invariant) |
| **ADR-28** | Multi-Region AWS Active-Active Infrastructure | `DEFERRED` | V2 Architecture Phase |
| **ADR-29** | Multi-Owner Administrative Quorum Governance | `DEFERRED` | V2 Architecture Phase |
| **ADR-30** | Enterprise Single Sign-On (SAML / OIDC) | `DEFERRED` | V2 Architecture Phase |
| **ADR-31** | Mobile Client Application Ecosystem | `DEFERRED` | V2 Architecture Phase |
| **ADR-32** | Central Cloud Storage of Broker Secrets or Strategy Logic | `NOT_ALLOWED` | Never / Prohibited |
| **ADR-33** | Permanent Bearer Tokens or Indefinite Sliding Sessions | `NOT_ALLOWED` | Never / Prohibited |
| **ADR-34** | Device Trust Derived Solely from MAC/Hostname Fingerprints | `NOT_ALLOWED` | Never / Prohibited |
| **ADR-35** | Cloud Outage Failing Open or Disarming Local Safety Controls | `NOT_ALLOWED` | Never / Prohibited |
| **ADR-36** | Central Auth Service Controlling or Mutating Live Orders | `NOT_ALLOWED` | Never / Prohibited |

---

## Detailed Architecture Decisions

### ADR-01: Product Brand, Tagline & Visual Identity
- **Status**: `FINAL`
- **Rationale**: Establishes a distinct, institutional brand identity ("AlgoFortis — Trading Research & Risk OS") replacing the legacy development naming while maintaining code stability through explicit migration boundaries.
- **Dependencies**: None.
- **Supersedes**: Legacy AlgoFortis branding.
- **Implementation Phase**: Phase 1.

### ADR-02: Four-Layer Architectural Decoupling & Engine API Boundary
- **Status**: `FINAL`
- **Rationale**: Decouples the Desktop Client (Layer A) from Trading Runtime (Layer B) via schema-enforced Engine API interfaces (`/api/v1/`). Enables local execution now and remote execution later without rewriting UI or engine components.
- **Dependencies**: ADR-01.
- **Supersedes**: Monolithic in-process desktop imports.
- **Implementation Phase**: Phase 2.

### ADR-03: Primary Deployment Profile: Desktop Local (V1)
- **Status**: `FINAL`
- **Rationale**: Primary target for V1. Runs both UI and engine on local Windows hardware, guaranteeing complete data sovereignty and zero reliance on cloud availability for trading execution.
- **Dependencies**: ADR-02.
- **Supersedes**: None.
- **Implementation Phase**: Phase 1.

### ADR-04: Windows VPS Deployment Profile Compatibility
- **Status**: `FINAL`
- **Rationale**: Ensures the exact same engine and runtime codebase can run on Windows Server VPS headless without requiring core engine refactoring.
- **Dependencies**: ADR-02, ADR-08.
- **Supersedes**: None.
- **Implementation Phase**: Phase 8.

### ADR-05: Remote Engine Architecture & Client Adapters
- **Status**: `DEFERRED`
- **Rationale**: Splitting the UI to communicate across the internet to a remote engine over mTLS is deferred to V2 to prioritize a rock-solid local desktop launch.
- **Dependencies**: ADR-02, ADR-04.
- **Supersedes**: None.
- **Implementation Phase**: Phase 10 (Deferred).

### ADR-06: Anywhere Login & Strict 3-Device Quota
- **Status**: `FINAL`
- **Rationale**: Allows users to log in across up to 3 authorized Windows PCs. Prohibits silent auto-eviction of older devices to prevent unexpected authorization loss.
- **Dependencies**: ADR-07, ADR-08, ADR-16.
- **Supersedes**: OD-AUTH-07.
- **Implementation Phase**: Phase 4.

### ADR-07: Separation of WebAuthn and Device Identity Keys
- **Status**: `FINAL`
- **Rationale**: WebAuthn passkeys prove *user identity* during interactive login. Device Identity Keys provide *machine proof* and cryptographic session binding for background requests. Reusing WebAuthn credentials for background signing is architecturally flawed and prohibited.
- **Dependencies**: None.
- **Supersedes**: Generic authenticator binding models.
- **Implementation Phase**: Phase 3.

### ADR-08: Windows CNG/TPM & DPAPI Device Key Storage Hierarchy
- **Status**: `FINAL`
- **Rationale**: Preferred security uses hardware TPM 2.0 via Windows CNG (non-exportable keys). Software fallback utilizes Windows DPAPI bound to the local user account. The private key never leaves the client PC.
- **Dependencies**: ADR-07.
- **Supersedes**: Plaintext or reversible local key storage.
- **Implementation Phase**: Phase 3.

### ADR-09: Dual-Token Model & Rotating Refresh Token Family
- **Status**: `FINAL`
- **Rationale**: Short-lived 15-minute access tokens minimize exposure. Rotating 30-day refresh tokens (with 7-day idle limit) bound to the Device Identity Key provide secure session persistence. Presenting a reused refresh token immediately revokes the session family.
- **Dependencies**: ADR-07, ADR-08.
- **Supersedes**: Static opaque bearer tokens.
- **Implementation Phase**: Phase 4.

### ADR-10: Same-PC Reinstallation Device Identity Metadata Preservation
- **Status**: `FINAL`
- **Rationale**: Normal uninstallation preserves `%LOCALAPPDATA%\AlgoFortis\Security\DeviceIdentity\`. Reinstalling on the same PC allows cryptographic re-authentication without consuming an additional device quota slot.
- **Dependencies**: ADR-08.
- **Supersedes**: Reinstall requiring manual Owner device reset.
- **Implementation Phase**: Phase 3.

### ADR-11: High-Assurance Recovery Device Purge & Assurance Window
- **Status**: `FINAL`
- **Rationale**: Completing high-assurance recovery assumes potential credential theft; therefore, all existing devices, sessions, and refresh tokens are immediately revoked. A 10-minute assurance window allows setting up fresh credentials on the current PC.
- **Dependencies**: ADR-06, ADR-09.
- **Supersedes**: OD-AUTH-08, OD-AUTH-16.
- **Implementation Phase**: Phase 4.

### ADR-12: Flow-Isolated Rate Limiting & Progressive Cooldown Escalation
- **Status**: `FINAL`
- **Rationale**: Progressive cooldowns (15m → 1h → 24h) are tracked independently for login, activation, recovery, and step-up flows. An attack on one endpoint cannot deny access to independent recovery mechanisms.
- **Dependencies**: None.
- **Supersedes**: OD-AUTH-02, OD-AUTH-10, OD-AUTH-14.
- **Implementation Phase**: Phase 4.

### ADR-13: 24-Hour Single-Use Activation Lifecycle
- **Status**: `FINAL`
- **Rationale**: Activation codes (`AF-ACT-XXXX-XXXX-XXXX`) expire strictly after 24 hours. Expired codes cannot auto-revive; manual Owner reissuance is required.
- **Dependencies**: None.
- **Supersedes**: OD-AUTH-01, OD-AUTH-11.
- **Implementation Phase**: Phase 4.

### ADR-14: Data Sovereignty & Strict Cloud Sync Boundaries
- **Status**: `FINAL`
- **Rationale**: Trading strategies, broker API keys, live positions, orders, and execution ledgers remain exclusively on the local machine. The central cloud only stores identity, device public keys, and entitlement leases.
- **Dependencies**: ADR-02.
- **Supersedes**: None.
- **Implementation Phase**: Phase 2.

### ADR-15: Local Trading Safety & Degraded Operation During Cloud Outages
- **Status**: `FINAL`
- **Rationale**: Outages of central authentication or cloud infrastructure must never disrupt local protective stop-loss, risk monitoring, or order management. The system transitions to Local Degraded Mode with full safety enforcement.
- **Dependencies**: ADR-02, ADR-14.
- **Supersedes**: None.
- **Implementation Phase**: Phase 2.

### ADR-16: Central Cloud Infrastructure Topology (AWS Mumbai ap-south-1)
- **Status**: `FINAL`
- **Rationale**: Production central services run on AWS ECS Fargate, ALB, private RDS PostgreSQL, Secrets Manager, and Route 53 in region `ap-south-1` for optimal regional latency and security compliance.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Phase 7.

### ADR-17: AWS Cost Governance & Monthly Budget Ceiling (₹6,000)
- **Status**: `FINAL`
- **Rationale**: Hard financial ceiling of ₹6,000/month with tiered AWS Budget notifications (₹3,000, ₹4,500, ₹6,000). Budget alerts provide operational visibility and are explicitly not automated system kill-switches.
- **Dependencies**: ADR-16.
- **Supersedes**: None.
- **Implementation Phase**: Phase 7.

### ADR-18: Portable Backup Schema (`AlgoFortisBackup/v1`) & Secret Exclusion
- **Status**: `FINAL`
- **Rationale**: Portable backups contain non-secret settings, strategy configurations, and backtest results. Broker secrets, device private keys, and session tokens are strictly excluded to prevent credential theft.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Phase 5.

### ADR-19: Default Clean Uninstall Semantics (Preserve User Data)
- **Status**: `FINAL`
- **Rationale**: Standard uninstaller removes application binaries in `Program Files` but preserves `%LOCALAPPDATA%\AlgoFortis` to prevent unintentional loss of user research data and device credentials.
- **Dependencies**: ADR-10.
- **Supersedes**: None.
- **Implementation Phase**: Phase 6.

### ADR-20: Authenticode-Signed Auto-Update Architecture
- **Status**: `FINAL`
- **Rationale**: Updates are delivered via signed manifests and Authenticode-signed executables verified by SHA-256 digests. Failed updates trigger automated rollback to the previous working installation.
- **Dependencies**: ADR-26.
- **Supersedes**: None.
- **Implementation Phase**: Phase 6.

### ADR-21: Signed Offline Entitlement Leases (7-Day Offline Validity)
- **Status**: `FINAL`
- **Rationale**: Clients receive an Ed25519-signed lease granting offline functionality for up to 7 days. An expired lease blocks new operations while preserving full access to existing data and protective risk management.
- **Dependencies**: ADR-15.
- **Supersedes**: OD-AUTH-20, OD-AUTH-22.
- **Implementation Phase**: Phase 4.

### ADR-22: Privacy-Preserving Telemetry & Sanitize-First Support Bundles
- **Status**: `FINAL`
- **Rationale**: Operational telemetry is strictly limited to app versions, crash signatures, and update status. Proprietary strategies, balances, and broker keys are never transmitted. Support bundles sanitize sensitive information prior to export.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Phase 5.

### ADR-23: Technical Identity, SemVer Versioning & Migration Namespaces
- **Status**: `FINAL`
- **Rationale**: Adopts SemVer 2.0.0 for product releases, independent API versioning (`/api/v1/`), and automated backward-compatible migration from legacy `%LOCALAPPDATA%\AlgoFortis` data roots.
- **Dependencies**: ADR-01.
- **Supersedes**: None.
- **Implementation Phase**: Phase 1.

### ADR-24: Legal Publisher Identity Specification
- **Status**: `PENDING_EXTERNAL`
- **Rationale**: Exact legal entity and publisher certificate details are pending formal corporate entity finalization. The build pipeline uses configurable placeholder identifiers until finalized.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Phase 6.

### ADR-25: Central Production Domain & Subdomain Hierarchy
- **Status**: `PENDING_EXTERNAL`
- **Rationale**: Exact root domain purchase is pending Owner domain registration. The architecture establishes the standard subdomain structure (`auth.`, `api.`, `updates.`, `status.`) driven by deployment configuration.
- **Dependencies**: None.
- **Supersedes**: Hardcoded `algofortis.com` references.
- **Implementation Phase**: Phase 7.

### ADR-26: Windows Installer Packaging & WebView2 Desktop Shell
- **Status**: `FINAL`
- **Rationale**: Bundles an embedded Python runtime, compiled UI assets, and a native C# WebView2 host into an enterprise Inno Setup package (`AlgoFortis-Setup.exe`) requiring zero user-installed prerequisites.
- **Dependencies**: ADR-01, ADR-02.
- **Supersedes**: Legacy multi-window dev scripts.
- **Implementation Phase**: Phase 6.

### ADR-27: Absolute Lock on Live Trading Execution Safety (DISARMED)
- **Status**: `FINAL`
- **Rationale**: Mandatory institutional safety lock: `READ_ONLY = true`, `DISARMED = true`, `live_global_hold = true`, `broker mutation = ZERO`, `real broker connection = NONE` across all development and packaging phases.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Phase 1-10 (Continuous Invariant).

### ADR-28: Multi-Region AWS Active-Active Infrastructure
- **Status**: `DEFERRED`
- **Rationale**: Multi-region active-active deployment adds high cost and architectural complexity unnecessary for V1 single-region operations.
- **Dependencies**: ADR-16.
- **Supersedes**: None.
- **Implementation Phase**: V2 Architecture Phase.

### ADR-29: Multi-Owner Administrative Quorum Governance
- **Status**: `DEFERRED`
- **Rationale**: Single Super Owner (`OWNER-001`) authority model is sufficient and authoritative for V1. Quorum schemes are deferred to enterprise multi-tenant releases.
- **Dependencies**: ADR-06.
- **Supersedes**: None.
- **Implementation Phase**: V2 Architecture Phase.

### ADR-30: Enterprise Single Sign-On (SAML / OIDC)
- **Status**: `DEFERRED`
- **Rationale**: Corporate identity federation is deferred to enterprise V2 milestones.
- **Dependencies**: ADR-06.
- **Supersedes**: None.
- **Implementation Phase**: V2 Architecture Phase.

### ADR-31: Mobile Client Application Ecosystem
- **Status**: `DEFERRED`
- **Rationale**: Mobile companions (iOS/Android) are out of scope for V1 desktop institutional focus.
- **Dependencies**: ADR-05.
- **Supersedes**: None.
- **Implementation Phase**: V2 Architecture Phase.

### ADR-32: Central Cloud Storage of Broker Secrets or Strategy Logic
- **Status**: `NOT_ALLOWED`
- **Rationale**: Uploading broker API secrets or proprietary strategy code to central cloud databases violates core data sovereignty invariants and creates catastrophic exposure risks.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Permanently Prohibited.

### ADR-33: Permanent Bearer Tokens or Indefinite Sliding Sessions
- **Status**: `NOT_ALLOWED`
- **Rationale**: Permanent authorization tokens or unexpiring sliding sessions create indefinite exposure if a device is lost or compromised.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Permanently Prohibited.

### ADR-34: Device Trust Derived Solely from MAC/Hostname Fingerprints
- **Status**: `NOT_ALLOWED`
- **Rationale**: Hardware MAC addresses, hostnames, and OS details are easily spoofed or altered and cannot replace cryptographic asymmetric key pair proof.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Permanently Prohibited.

### ADR-35: Cloud Outage Failing Open or Disarming Local Safety Controls
- **Status**: `NOT_ALLOWED`
- **Rationale**: Any failure mode that disables protective risk controls or allows uncontrolled execution during network loss violates core fail-closed safety invariants.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Permanently Prohibited.

### ADR-36: Central Auth Service Controlling or Mutating Live Orders
- **Status**: `NOT_ALLOWED`
- **Rationale**: Central authentication servers possess zero trading context or risk state and must never execute or modify broker orders directly.
- **Dependencies**: None.
- **Supersedes**: None.
- **Implementation Phase**: Permanently Prohibited.

---
*AlgoFortis Architecture Decision Register V1 is hereby FROZEN.*
