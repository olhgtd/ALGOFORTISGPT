# AlgoFortis — Master Implementation Plan V1
**Stage-by-Stage Implementation Blueprint & Safety Guardrails**

> **Document Status**: `PLAN ONLY — FROZEN SPECIFICATION — DO NOT EXECUTE`  
> **Brand**: AlgoFortis  
> **Tagline**: Trading Research & Risk OS  
> **Scope**: Safe, staged transition from SentinelX development baseline to certified AlgoFortis V1 product.

---

## Plan Overview & Stage Sequence

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              13-STAGE IMPLEMENTATION SEQUENCE                          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  [ STAGE 1: COMPATIBILITY INVENTORY ]                                                  │
│    └── Map all paths, schemas, identifiers, and configuration bindings                 │
│                                │                                                       │
│  [ STAGE 2: BRAND MIGRATION ]  ▼                                                       │
│    └── UI, titles, icons, shortcuts, visual theme, and paths with backward-compat      │
│                                │                                                       │
│  [ STAGE 3: INTERNAL API BOUNDARY HARDENING ] ▼                                        │
│    └── Strict Engine API schema validation & Client/Engine decoupling                  │
│                                │                                                       │
│  [ STAGE 4: DEVICE & SECURITY PERSISTENCE ] ▼                                          │
│    └── Windows CNG/TPM & DPAPI device identity key store & metadata preservation       │
│                                │                                                       │
│  [ STAGE 5: LOCAL AUTH COMPATIBILITY ] ▼                                               │
│    └── Dual-token model, rotating refresh tokens, and rate-limit flow isolation        │
│                                │                                                       │
│  [ STAGE 6: BACKUP & UNINSTALL ] ▼                                                     │
│    └── Portable backup format (AlgoFortisBackup/v1) & clean uninstall semantics        │
│                                │                                                       │
│  [ STAGE 7: UPDATER FOUNDATIONS ] ▼                                                    │
│    └── Manifest validation, Authenticode verification & rollback engine                │
│                                │                                                       │
│  [ STAGE 8: ENTITLEMENT FOUNDATIONS ] ▼                                                │
│    └── Signed offline lease engine (7-day lease) & expired safety behavior             │
│                                │                                                       │
│  [ STAGE 9: TELEMETRY & PRIVACY ] ▼                                                    │
│    └── Redacted support bundle generator & opt-in crash telemetry                      │
│                                │                                                       │
│  [ STAGE 10: WINDOWS PACKAGING ] ▼                                                     │
│    └── Inno Setup (AlgoFortis-Setup.exe) & C# WebView2 Desktop Shell (AlgoFortis.exe)   │
│                                │                                                       │
│  [ STAGE 11: FULL REGRESSION & CERTIFICATION ] ▼                                       │
│    └── End-to-end installation, lifecycle, ACL, and trading smoke certification        │
│                                │                                                       │
│  [ STAGE 12: FUTURE AWS ACCOUNT AUTHORITY ] ▼                                          │
│    └── Cloud Fargate/RDS deployment specifications (ap-south-1)                        │
│                                │                                                       │
│  [ STAGE 13: FUTURE VPS / REMOTE-ENGINE ADAPTER ]                                      │
│    └── RemoteEngineClient over mTLS and headless service configurations                │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Stage Plans

### Stage 1: Compatibility Inventory & Namespace Mapping
- **Objective**: Audit and catalog all internal schema IDs, table structures, environment variables, and persisted paths to ensure seamless migration without data loss.
- **Affected Components**:
  - `dashboard/runtime/paths.py`
  - `dashboard/backend/sensitive_storage.py`
  - `dashboard/backend/domain.py`
- **Untouched Invariants**:
  - `READ_ONLY = true`, `DISARMED = true`, `live_global_hold = true`
  - Existing SQLite database schema structures (`sentinelx_security.sqlite3`, `sentinelx_governance.sqlite3`, `core-audit.sqlite3`)
- **Required Tests**:
  - Path resolution regression tests verifying fallback and alias resolution.
- **Rollback Point**: Git commit prior to path mapping updates.
- **Acceptance Criteria**: Full inventory matrix completed; all paths resolve correctly in dev, test, and production modes.

---

### Stage 2: Brand Migration (AlgoFortis)
- **Objective**: Apply the AlgoFortis visual identity, typography, icons, titles, and layout styling across the UI, desktop launcher, and backend metadata surfaces.
- **Affected Components**:
  - `dashboard/web/` (React components, branding headers, stylesheets, index.html)
  - `build/tools/SentinelXLauncher.cs` → `AlgoFortisLauncher.cs`
  - `sentinelx.ico` → `algofortis.ico`
  - Window title, splash/loading screens, error panels
- **Untouched Invariants**:
  - Internal database IDs (`SX-U-XXXX-XXXX` maintained internally with `AF-U-` presentation alias)
  - Zero modification to engine calculation or trading strategy logic
- **Required Tests**:
  - Visual smoke tests across all dashboard tabs (Backtest, Paper, Live Readiness, Governance, Security).
  - Mode marker verification in built `index.html`.
- **Rollback Point**: Revert frontend and launcher branding commits.
- **Acceptance Criteria**: Clean AlgoFortis branding rendered across all surfaces with zero console errors or broken styling.

---

### Stage 3: Internal API Boundary Hardening & Client Decoupling
- **Objective**: Harden the boundary between the Desktop UI (Layer A) and Trading Runtime (Layer B) via schema-enforced Engine API interfaces (`/api/v1/`).
- **Affected Components**:
  - `dashboard/backend/api.py`
  - `dashboard/backend/adapters.py`
  - `dashboard/backend/architecture_manifest.py`
- **Untouched Invariants**:
  - Engine execution guarantees: `execution_model: "next_bar_open"`
  - Risk parameters and strategy interface version checks
- **Required Tests**:
  - API contract fuzzing and schema validation tests.
  - Verification that UI does not directly import Python engine modules.
- **Rollback Point**: Restore API router definitions.
- **Acceptance Criteria**: 100% of UI interactions route through versioned API endpoints with strict input/output Pydantic/dataclass schema enforcement.

---

### Stage 4: Device & Security Persistence
- **Objective**: Implement the cryptographic Device Identity Key subsystem with Windows CNG/TPM hardware backing and DPAPI software fallback under `%LOCALAPPDATA%\AlgoFortis\Security\DeviceIdentity\`.
- **Affected Components**:
  - `dashboard/backend/security.py`
  - `dashboard/backend/security_store.py`
  - `dashboard/runtime/paths.py`
- **Untouched Invariants**:
  - WebAuthn ceremony integrity (python-fido2 server verification)
  - Zero-knowledge storage of private keys (private keys never leave the client PC)
- **Required Tests**:
  - TPM/CNG key generation and signature validation tests.
  - DPAPI fallback encryption/decryption tests across simulated user profiles.
  - Reinstallation device metadata recovery tests.
- **Rollback Point**: Revert to previous security store adapter.
- **Acceptance Criteria**: Device Identity Keys generate and sign challenges successfully; reinstall on the same PC re-attests the existing device slot cleanly.

---

### Stage 5: Local Auth Compatibility & Session Dual-Token Model
- **Objective**: Implement the dual-token session architecture (15-min Access Token + 30-day rotating, device-bound Refresh Token) and flow-isolated progressive rate limiting.
- **Affected Components**:
  - `dashboard/backend/security.py`
  - `dashboard/backend/security_store.py`
  - `dashboard/backend/api.py`
- **Untouched Invariants**:
  - Super Owner governance authority (`OWNER-001`)
  - 24-hour single-use activation code lifecycle
- **Required Tests**:
  - Token refresh rotation and reuse detection tests (ensuring family revocation on reuse).
  - Rate limit isolation tests (verifying password lockout does not block recovery codes).
- **Rollback Point**: Restore prior single-token session model.
- **Acceptance Criteria**: Refresh token rotates on every call; replayed tokens trigger instant session purge; rate limit counters escalate progressively.

---

### Stage 6: Portable Backup & Uninstall Architecture
- **Objective**: Implement the `AlgoFortisBackup/v1` manifest-based export/import engine and refine installer uninstallation scripts to preserve user data by default.
- **Affected Components**:
  - `dashboard/backend/services.py`
  - `build/tools/sentinelx_installer.iss` → `algofortis_installer.iss`
- **Untouched Invariants**:
  - Exclusion of broker keys, device private keys, and session tokens from backups
  - NTFS DACL security on restored directories
- **Required Tests**:
  - Backup creation, validation, and restore round-trip tests.
  - Negative tests importing corrupted or secret-bearing archives (must fail closed).
  - Silent uninstall test verifying preservation of `%LOCALAPPDATA%\AlgoFortis`.
- **Rollback Point**: Revert backup service and uninstaller script.
- **Acceptance Criteria**: Backup archives validate against schema; uninstaller cleanly removes binaries while preserving user state.

---

### Stage 7: Auto-Update Foundations
- **Objective**: Build the signed update manifest fetcher, Authenticode installer validator, and safe shutdown/restart sequence in `RuntimeController`.
- **Affected Components**:
  - `dashboard/runtime/controller.py`
  - `dashboard/backend/deployment_service.py`
- **Untouched Invariants**:
  - Update failure must never terminate active local protective stop-loss logic
- **Required Tests**:
  - Manifest signature verification tests.
  - Simulated failed update and automatic rollback tests.
- **Rollback Point**: Revert update controller modifications.
- **Acceptance Criteria**: Updater verifies SHA-256 and Authenticode signature before initiating install; gracefully rolls back on failure.

---

### Stage 8: Entitlement & Offline Lease Engine
- **Objective**: Implement the cryptographically signed, cached entitlement lease engine with 7-day offline validity and graceful degradation during cloud outages.
- **Affected Components**:
  - `dashboard/backend/domain.py`
  - `dashboard/backend/services.py`
  - `dashboard/backend/api.py`
- **Untouched Invariants**:
  - Expired entitlement must NEVER disable protective stops or lock user out of their own data
- **Required Tests**:
  - Lease issuance, signature verification, and clock-rollback resistance tests.
  - Outage simulation tests verifying "AUTH SERVICE OFFLINE — LOCAL SAFETY CONTINUES".
- **Rollback Point**: Revert entitlement lease service.
- **Acceptance Criteria**: Offline app operates cleanly with valid lease; expired lease blocks new runs while maintaining full protective safety.

---

### Stage 9: Telemetry & Sanitize-First Support Bundles
- **Objective**: Build the opt-in operational telemetry pipeline and the redacted support bundle export tool.
- **Affected Components**:
  - `dashboard/backend/audit.py`
  - `dashboard/backend/path_redaction.py`
  - `dashboard/backend/services.py`
- **Untouched Invariants**:
  - ZERO upload of trading strategies, broker keys, balances, or order payloads
- **Required Tests**:
  - Redaction pipeline tests verifying complete removal of tokens, email addresses, and local system paths from support bundles.
- **Rollback Point**: Revert telemetry and support bundle endpoints.
- **Acceptance Criteria**: Generated support bundle contains zero sensitive tokens or proprietary code; telemetry is strictly opt-in and operational.

---

### Stage 10: Windows Native Packaging & Shell Assembly
- **Objective**: Compile the production C# WebView2 host (`AlgoFortis.exe`) and build the Inno Setup x64 installer (`AlgoFortis-Setup.exe`).
- **Affected Components**:
  - `build/tools/AlgoFortisLauncher.cs`
  - `build/tools/compile_launcher.ps1`
  - `build/tools/algofortis_installer.iss`
  - `build/tools/stage_app.ps1`
- **Untouched Invariants**:
  - End-user environment requires zero external Python, Node, Git, or PowerShell dependencies
- **Required Tests**:
  - Clean VM installation test in `C:\Program Files\AlgoFortis`.
  - Desktop shortcut, Start Menu shortcut, and Add/Remove Programs registry tests.
  - Single-instance mutex validation test.
- **Rollback Point**: Revert build scripts to previous release staging.
- **Acceptance Criteria**: Double-clicking `AlgoFortis-Setup.exe` installs cleanly; launching `AlgoFortis.exe` opens the terminal seamlessly.

---

### Stage 11: End-to-End Regression & Security Certification
- **Objective**: Execute comprehensive automated regression test suite validating security, ACLs, process lifecycle, UI reconnection, and trading simulation smoke tests.
- **Affected Components**:
  - `build/tools/certify_phase8_security.py`
  - `build/tools/certify_phase9_phase10_installation.py`
  - `build/tools/run_regression_certification.py`
- **Untouched Invariants**:
  - 100% pass rate on all Phase 7, 8, 9, 10 certification suites
- **Required Tests**:
  - Host/Origin security header enforcement.
  - Loopback control secret protection.
  - In-place backend restart and UI auto-reconnect.
  - Cold application relaunch and duplicate launch prevention.
- **Rollback Point**: Halt release candidate until all certification tests pass.
- **Acceptance Criteria**: All automated certification scripts report `ALL PASS` with zero warnings or security regressions.

---

### Stage 12: Future AWS Central Account Authority (Deployment Plan)
- **Objective**: Prepare Terraform / CloudFormation infrastructure templates for ECS Fargate, private RDS PostgreSQL, ALB, Route 53, and Secrets Manager in `ap-south-1`.
- **Affected Components**:
  - Cloud infrastructure templates (outside local desktop runtime repository)
- **Untouched Invariants**:
  - AWS budget ceiling of ₹6,000/month with tiered alerts (₹3,000, ₹4,500, ₹6,000)
  - Zero live broker order execution on cloud infrastructure
- **Required Tests**:
  - Cloud infrastructure validation in isolated staging AWS account.
- **Rollback Point**: Destroy Terraform staging workspace.
- **Acceptance Criteria**: Cloud account authority endpoints respond to WebAuthn assertions and issue signed entitlement leases.

---

### Stage 13: Future Windows VPS & Remote-Engine Evolution
- **Objective**: Implement the `RemoteEngineClient` adapter and headless service configuration for Windows Server VPS deployments.
- **Affected Components**:
  - `dashboard/runtime/controller.py` (Service wrapper)
  - `dashboard/backend/adapters.py` (`RemoteEngineClient`)
- **Untouched Invariants**:
  - Core trading engine and risk logic remain 100% identical between local and VPS profiles
- **Required Tests**:
  - Headless service startup/shutdown tests on Windows Server 2022.
  - Remote WebSocket streaming and mTLS authentication tests.
- **Rollback Point**: Revert remote adapter modules.
- **Acceptance Criteria**: Desktop UI connects seamlessly to remote engine instance with identical visual responsiveness and complete risk enforcement.

---
*AlgoFortis Master Implementation Plan V1 is complete and ready for future execution.*
