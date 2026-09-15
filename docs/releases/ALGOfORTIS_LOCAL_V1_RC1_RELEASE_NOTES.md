# AlgoFortis Local V1 Release Candidate 1 (RC1) — Release Notes

**VERSION:** Local V1 RC1  
**RELEASE TARGET:** External Beta Program  
**TARGET OS:** Microsoft Windows 10 / 11 (64-bit)  
**BUILD DATE:** September 2026  

---

## What is AlgoFortis RC1?

AlgoFortis is an institutional-grade, local-first quantitative modeling, backtesting, and paper execution workstation engineered for professional quantitative traders and researchers. Built for privacy, deterministic speed, and zero cloud dependency, AlgoFortis keeps your proprietary algorithms, datasets, and trade ledgers entirely on your local workstation.

---

## Available Features

### 1. High-Performance Backtesting Engine
- **Deterministic Historical Simulation:** Backtest Python-based quantitative trading strategies against granular historical market datasets stored in high-performance Parquet format.
- **Institutional Analytics:** Comprehensive calculation of annualized returns, Sharpe ratio, Sortino ratio, maximum drawdown, equity curve timeseries, and trade execution ledgers.
- **Strict AST Syntax Validation:** Ensures quantitative strategy code adheres to execution safety limits and deterministic boundaries before running.

### 2. Simulated Paper Trading Engine
- **Real-Time Simulation:** Run active paper trading sessions with live tick ingestion or historical replay feeds.
- **Virtual Account Ledger:** Complete tracking of simulated cash balances, margin utilization, open positions, unrealized PnL, realized PnL, and order states.
- **Zero Real Capital at Risk:** Simulated orders are matched entirely within the local engine.

### 3. Institutional Security & Authentication
- **Passkey / WebAuthn Primary Login:** Modern, phishing-resistant authentication using Windows Hello (PIN, fingerprint, facial recognition) or hardware security keys (FIDO2 / YubiKey).
- **Hardware Device Identity Binding:** Cryptographically binds user sessions to authorized workstations (maximum 3 registered hardware devices per user).
- **Active Session Management:** Cryptographic session rotation, idle and absolute session expiry, and instant all-device session termination.
- **High-Assurance Recovery:** 8 one-time offline recovery codes to regain access if a hardware key is lost, with automatic revocation of all active sessions to protect account integrity.
- **Progressive Rate Limiting:** Fail-closed progressive cooldown ladder on failed authentication attempts.

### 4. Portable User Backup & Disaster Recovery
- **Sanitized Portable Archives (`AlgoFortisBackup/v1`):** Export strategies, backtest results, and analytical configurations with automated secret-stripping.
- **Operational SQLite Backups:** Native, WAL-safe database snapshots verified with SQLite integrity checks.
- **Hardened Extraction:** Full path-traversal and file-tamper protection during backup restoration.

### 5. Native Windows Integration
- **Clean Architecture Separation:** Application binaries install to `C:\Program Files\AlgoFortis`, while all mutable databases, logs, and artifacts reside strictly inside `%LOCALAPPDATA%\AlgoFortis`.
- **Integrated Desktop Shell:** High-performance native C# launcher hosting a modern, reactive interface powered by Microsoft Edge WebView2.
- **Safe Reinstall & Uninstall:** Workstation updates and uninstalls cleanly preserve user strategy files and backtest history without data loss.

---

## Safety & Operational Invariants

> [!IMPORTANT]
> **LIVE TRADING IS PERMANENTLY DISABLED IN V1:**
> - `READ_ONLY = true`
> - `DISARMED = true`
> - `LIVE_GLOBAL_HOLD = true`
> - `REAL BROKER CONNECTION = NONE`
> 
> AlgoFortis Local V1 contains **zero capability to connect to live brokerage execution gateways or place real-money orders**. All live order endpoints return HTTP 403 `EXECUTION_DISABLED`.

---

## Known Limitations & Architecture Notes

- **Desktop-Only:** Requires Microsoft Windows 10 (version 1809+) or Windows 11 64-bit with Microsoft Edge WebView2 Runtime.
- **Manual Onboarding:** Accounts are provisioned exclusively via Super Owner invitation. There is no automated public registration.
- **Single-Tenant Local Execution:** Multi-user accounts operate sequentially on assigned workstations; distributed multi-node clustering is not part of Local V1.

---

## Deferred Features (Roadmap)

The following capabilities are intentionally deferred from Local V1 and scheduled for subsequent post-beta / commercial phases:
- Automated payment gateway billing and recurring subscriptions.
- Cloud-hosted strategy synchronization and remote fleet management.
- Public over-the-air auto-update distribution service.
- Live broker execution gateways (subject to regulatory licensing and institutional infrastructure).

---

## Support & Feedback

Beta participants may report issues, suggest improvements, or request technical support by emailing `[SUPPORT_EMAIL]` in accordance with the External Beta Runbook.
