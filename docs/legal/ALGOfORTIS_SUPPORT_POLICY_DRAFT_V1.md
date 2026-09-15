# AlgoFortis V1 — Customer Support & Service Policy (Draft)

> [!NOTE]
> **OPERATIONAL NOTICE & DISCLAIMER:**  
> This policy outlines support tiers, channels, response expectations, and escalation paths for the AlgoFortis Local V1 Release Candidate and External Beta Program.

**EFFECTIVE DATE:** `[EFFECTIVE_DATE]`  
**COMPANY:** `[LEGAL_ENTITY_NAME]`  
**SUPPORT INTAKE:** `[SUPPORT_EMAIL]`  
**OPERATING TIMEZONE:** Indian Standard Time (IST, UTC+05:30)  

---

## 1. Scope of Support Services

### A. Supported Issues (In-Scope)
AlgoFortis technical support covers:
1. **Workstation Installation & Lifecycle:** Installation failures, shortcut setup, Inno Setup errors, and uninstallation issues on supported Windows 10/11 platforms.
2. **Authentication & Identity:** WebAuthn passkey enrollment, hardware security key configuration, Windows Hello integration, session token rotation, and 3-device authorization troubleshooting.
3. **Core Engine Functionality:** Backtest engine calculation errors, historical parquet dataset ingestion issues, paper trading session lifecycle management, and strategy AST syntax validation.
4. **Data Integrity & Backup:** SQLite database integrity errors, WAL checkpoint anomalies, and portable archive (`AlgoFortisBackup/v1`) restore assistance.
5. **Account Recovery:** Facilitation of Owner-assisted break-glass account recovery when user one-time recovery codes are exhausted.

### B. Excluded Issues (Out-of-Scope)
Support services do **not** cover:
1. **Financial & Trading Advice:** We provide zero advice regarding strategy profitability, entry/exit timing, risk-reward parameters, or market direction.
2. **Custom Strategy Authoring:** Writing, debugging, or optimizing proprietary trading algorithms on behalf of users.
3. **Third-Party Broker Configuration:** Troubleshooting live broker APIs or third-party order gateways (which are disarmed in V1).
4. **General IT & Hardware Maintenance:** Resolving operating system corruption, malware infections, or network firewall issues unrelated to AlgoFortis.

---

## 2. Support Channels & Hours

- **Primary Support Channel:** Direct email to `[SUPPORT_EMAIL]`.
- **Operating Hours:** Monday through Friday, 09:30 AM to 06:30 PM IST (excluding Indian national holidays).
- **Beta Response Targets:**
  - **Critical (P0):** Acknowledgment within 4 business hours; active mitigation plan within 24 hours.
  - **High (P1):** Acknowledgment within 8 business hours; investigation update within 48 hours.
  - **Medium/Low (P2/P3):** Acknowledged within 2 business days; prioritized for upcoming maintenance batches.

---

## 3. Support Submission Guidelines

To ensure rapid diagnosis, all support requests submitted by users should follow the format documented in the **External Beta Runbook**:
1. Clear description of the observed defect versus expected behavior.
2. Step-by-step reproduction sequence.
3. Relevant application logs from `%LOCALAPPDATA%\AlgoFortis\logs\backend.log` (ensuring no secrets or private keys are attached).
4. Operating system version and hardware specifications (e.g., Windows 11 Pro 64-bit).

---

## 4. Escalation to Super Owner

Issues involving account lockout, device reallocation beyond the 3-device limit, or database corruption are automatically escalated to the Super Owner (`OWNER-001`) for manual administrative resolution.
