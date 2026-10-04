# ALGOfORTIS LOCAL V1 RC1 RELEASE BASELINE

**PRODUCT:** AlgoFortis  
**RELEASE:** Local V1 RC1  
**STATUS:** RELEASE CANDIDATE PASS  
**FROZEN AT:** 2026-09-15T16:18:00Z  

---

## 1. CERTIFIED AREAS

- **Database Hardening DB-001..DB-011:** Certified referential integrity, foreign keys, write serialization, crash-safe WAL journal mode, atomic transaction boundaries, idempotency, retention enforcement, and native SQLite online backup.
- **API + Service Contract Hardening:** Verified strictly typed FastAPI / Pydantic V2 request & response models, ownership isolation, fail-closed bounded pagination, error shapes, and zero credential leakage.
- **Backtest + Paper Engine / Job Lifecycle:** Certified offline historical backtesting and simulated paper execution; zero live execution capability; strict AST syntax and governance verification for strategy artifacts.
- **Auth / Session / Recovery:** Token family rotation, refresh reuse detection & family invalidation, 7d/30d idle & absolute timeouts, 24h activation code lifecycle, 5-attempt progressive cooldown ladder, dual hardware key requirement for Owner break-glass, max 3 registered devices per user with no silent eviction, and 8 one-time recovery codes with complete active session revocation upon recovery.
- **Backup / DR:** Three-tier separation: `AlgoFortisBackup/v1` portable sanitized archive (secrets forbidden and stripped, `Zip Slip` / path traversal blocked fail-closed), WAL-safe native SQLite operational backup with `PRAGMA integrity_check`, and validated offline disaster recovery rehearsal.
- **Installer / Reinstall / Uninstall:** Windows-style installation with clean path isolation: immutable binaries in `Program Files\AlgoFortis`, mutable user state strictly inside `%LOCALAPPDATA%\AlgoFortis`; device identity and user databases preserved across reinstalls and uninstalls.
- **UI Integration Readiness:** Certified against `docs/ui-handoff/` for all documented screens, routes, and DTO contracts; disarmed live order endpoints fail-closed with 403 `EXECUTION_DISABLED`.
- **End-to-End Product Workflows:** Owner administration, user authentication, strategy governance & projection, paper trading session lifecycle, high-assurance recovery, and clean app restart without stale worker threads or file locks.
- **Stability Sanity:** Verified bounded read latency (<50ms avg), bounded pagination latency, worker thread containment, clean SQLite Windows file-lock release across repeated open/close cycles, and memory allocation containment under bounded batches.

---

## 2. TEST EVIDENCE

- **`tests_v1` Suite:** 146 / 146 PASS (`python -m pytest tests_v1 -q` in 31.06s)
- **Database Hardening Regression:** PASS (DB-001 through DB-011, 65 tests passed)
- **API Hardening Regression:** PASS (18 tests passed)
- **Engine Hardening Regression:** PASS (15 tests passed)
- **Phase 7 ACL Certification:** PASS (`build\tools\certify_phase7_acl.py`)
- **Phase 8 Security Certification:** PASS (`build\tools\certify_phase8_security.py`)
- **WebAuthn Security Certification:** PASS (`build\tools\certify_webauthn_security.py`)
- **Desktop Shell Certification:** PASS (`build\tools\certify_desktop_shell.py`)
- **Phase 9 & 10 Installation Certification:** PASS (`build\tools\certify_phase9_phase10_installation.py`)
- **Full Regression Certification:** PASS (`build\tools\run_regression_certification.py`)

---

## 3. DATABASE INTEGRITY

- `AppData\Local\AlgoFortis\databases\core-audit.sqlite3`: **OK** (`integrity_check=ok`, `foreign_key_check=0`)
- `AppData\Local\AlgoFortis\databases\governance\algofortis_governance.sqlite3`: **OK** (`integrity_check=ok`, `foreign_key_check=0`)
- `AppData\Local\AlgoFortis\databases\security\algofortis_security.sqlite3`: **OK** (`integrity_check=ok`, `foreign_key_check=0`)
- **Total Foreign Key Violations Across All Databases:** **0**

---

## 4. SAFETY BASELINE

```ini
READ_ONLY=true
DISARMED=true
live_global_hold=true
broker mutation=ZERO
real broker connection=NONE
```

- NO real-money trading.
- NO real broker order placement.
- NO live execution enablement.
- NO cloud execution.
- NO broker secret migration to server.
- Live execution endpoints fail-closed with 403 `EXECUTION_DISABLED`.

---

## 5. PRODUCT MODES

- **BACKTEST:** AVAILABLE (Historical & offline simulation only)
- **PAPER:** AVAILABLE (Local simulated broker & paper accounts only)
- **LIVE:** DISARMED (Fail-closed)

---

## 6. DEFERRED WORK CLASSIFICATION

### P0 LOCAL V1 BLOCKERS:
- **NONE** (All local V1 features, tests, and security controls are certified)

### P1 BEFORE EXTERNAL BETA:
- **Windows Code-Signing Certificate:** Windows Authenticode EV certificate for `AlgoFortisSetup.exe` and `AlgoFortis.exe`.
- **Legal Publisher Identity:** Formal entity name, trademark documentation, and copyright metadata.
- **Terms / EULA:** End-User License Agreement and risk disclosures embedded into installer and UI.
- **Beta Onboarding / Operator Runbook:** Step-by-step onboarding guide for external quantitative beta testers.

### P2 SAFE POST-BETA:
- **Public Domain & Landing Website:** Setup and TLS certificate for `algofortis.io`.
- **Opt-In Crash Telemetry:** Local crash dump packaging with fail-closed user opt-in.
- **Multi-Monitor UI Persistence:** Enhanced desktop window dock state and chart layout persistence.

### P3 FUTURE / CLOUD / PUBLIC LAUNCH:
- **Public Self-Signup:** Public registration portal (Local V1 rule: Manual Owner onboarding only).
- **Payment & Subscription Automation:** Stripe / Razorpay recurring subscription billing.
- **Cloud Entitlement Service:** Remote cloud license verification and device sync.
- **Public Auto-Update Delivery:** CloudFront / S3 signed update channel.
- **Real Broker Live Execution:** Real broker API order placement (permanently disabled in V1).
