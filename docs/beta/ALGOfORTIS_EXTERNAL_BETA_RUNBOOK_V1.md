# AlgoFortis V1 — External Beta Onboarding & Operator Runbook

**PRODUCT:** AlgoFortis  
**RELEASE TARGET:** Local V1 RC1 External Beta  
**AUDIENCE:** Super Owner (`OWNER-001`), Beta Operators, and Invited Quantitative Testers  
**STATUS:** ACTIVE BASELINE  

---

## 1. Pre-Beta Verification Checklist (Operator Prerequisite)

Before distributing any installer or onboarding an external quantitative tester, the Operator/Super Owner must perform the following pre-flight verification:

1. **Verify Binary Integrity:**
   Verify that the SHA-256 digest of `build\installer\AlgoFortis-Setup.exe` strictly matches the authoritative release manifest in `docs/releases/ALGOfORTIS_LOCAL_V1_RC1_SHA256.txt`:
   ```powershell
   Get-FileHash "build\installer\AlgoFortis-Setup.exe" -Algorithm SHA256
   ```
2. **Verify Code Signature:**
   Check Authenticode signature status on `AlgoFortis-Setup.exe`. Once production certificates are applied, verify `Status : Valid`.
3. **Database Health Verification:**
   Ensure local databases pass integrity checks:
   ```powershell
   python -c "import sqlite3; c = sqlite3.connect(r'$env:LOCALAPPDATA\AlgoFortis\databases\security\algofortis_security.sqlite3'); print(c.execute('PRAGMA integrity_check;').fetchall())"
   ```
4. **Distribute Documentation Pack:**
   Provide the tester with:
   - `AlgoFortis-Setup.exe`
   - Release Notes (`docs/releases/ALGOfORTIS_LOCAL_V1_RC1_RELEASE_NOTES.md`)
   - Beta Agreement (`docs/legal/ALGOfORTIS_BETA_AGREEMENT_DRAFT_V1.md`)
   - Risk Disclosure (`docs/legal/ALGOfORTIS_RISK_DISCLAIMER_DRAFT_V1.md`)

---

## 2. User Invitation & Onboarding Lifecycle

AlgoFortis Local V1 uses **manual, Owner-controlled onboarding**. Public self-registration is strictly unavailable.

### Step 1: Owner Creates Invited User Account
The Super Owner issues a secure API request or uses the Owner Administration UI:

```http
POST /api/v1/owner/access/users
Authorization: Bearer <OWNER_SESSION_TOKEN>
Content-Type: application/json

{
  "email": "beta.quant@domain.com",
  "display_name": "Dr. Aris Thorne",
  "role": "USER",
  "service_term_type": "ANNUAL",
  "plan": "STANDARD"
}
```

The response returns:
```json
{
  "success": true,
  "record": {
    "user_id": "usr_94a8f3b2...",
    "account_status": "PENDING"
  },
  "activation_code": "AF-ACT-7B92-K8M4-99P1"
}
```

### Step 2: Deliver Credentials Out-of-Band
- Send the activation code to the user via a secure, out-of-band channel (e.g., encrypted messaging or direct phone confirmation).
- **Expiry:** Activation codes expire strictly after **24 hours**. If expired, the Owner must call `/api/v1/owner/access/users/{user_id}/reissue-activation` to generate a fresh token.

### Step 3: User Installation & First Launch
1. Run `AlgoFortis-Setup.exe`.
2. Follow standard Windows installation steps. Binaries are installed to `C:\Program Files\AlgoFortis`.
3. Launch AlgoFortis via the desktop shortcut or Start Menu.
4. On the welcome screen, enter the assigned email and the 24-hour activation code.

### Step 4: WebAuthn Passkey Registration & Recovery Codes
1. **Passkey Enrollment:** When prompted, register a hardware security key (YubiKey) or Windows Hello (PIN, Fingerprint, Facial Recognition). This becomes the primary credential.
2. **Recovery Codes:** The application displays **8 one-time recovery codes**.
   > [!IMPORTANT]
   > The user **must save these 8 recovery codes offline**. They are required if a hardware passkey is lost or inaccessible.
3. **Device Authorization:** The workstation is registered as Device 1 of 3 allowed slots.

---

## 3. Beta Safety & Trading Boundaries

All beta participants must adhere to the following safety constraints:

| Capability | Status | Operational Rule |
| :--- | :--- | :--- |
| **Historical Backtest** | **AVAILABLE** | Permitted on all bundled parquet historical datasets. |
| **Paper Trading** | **AVAILABLE** | Simulated execution only using virtual capital; zero real market orders. |
| **Live Trading** | **PERMANENTLY DISARMED** | Live execution is disarmed fail-closed (`READ_ONLY=true`, `DISARMED=true`). |
| **Real Broker APIs** | **DISALLOWED** | Do not attempt to wire live broker API keys; broker connection is NONE. |
| **Device Cap** | **MAX 3 DEVICES** | Registration on a 4th device is blocked fail-closed; no silent eviction. |
| **Install Directory** | **IMMUTABLE** | Do not manually edit or inject DLLs into `C:\Program Files\AlgoFortis`. |

---

## 4. Support Intake & Issue Reporting

When beta testers encounter unexpected behavior, they should submit a structured report to `[SUPPORT_EMAIL]`.

### A. Issue Severity Classification

- **P0 — Critical (Blocker):** Security vulnerability, data loss/corruption, application crash on startup, inability to launch.
- **P1 — High:** Major workflow broken (e.g., backtest engine aborts valid strategy, paper session fails to start, passkey authentication failure).
- **P2 — Medium:** Feature defect with an available workaround (e.g., UI display truncation, charting zoom delay).
- **P3 — Low / Cosmetic:** Minor UI styling bug, typographical error, minor performance latency.

### B. Issue Report Template

```markdown
### AlgoFortis Beta Issue Report

**Reporter:** [Name / Tester ID]
**Date & Time:** [YYYY-MM-DD HH:MM IST]
**Severity:** [P0 / P1 / P2 / P3]
**OS Version:** [e.g., Windows 11 Pro 64-bit 23H2]
**Component:** [Installer / Auth / Backtest / Paper / UI / Backup]

#### 1. Summary
[Brief description of the issue]

#### 2. Steps to Reproduce
1. Launch AlgoFortis
2. Navigate to ...
3. Execute ...

#### 3. Expected Result
[What should have occurred]

#### 4. Actual Result
[What actually occurred, including any visible error message]

#### 5. Safe Log Snippet
[Attach snippet from %LOCALAPPDATA%\AlgoFortis\logs\backend.log]
```

### C. Safe vs. Forbidden Log Attachments

> [!WARNING]
> **STRICT SECURITY RULE ON ATTACHMENTS:**
> - **SAFE TO ATTACH:** `%LOCALAPPDATA%\AlgoFortis\logs\backend.log`, `%LOCALAPPDATA%\AlgoFortis\logs\launcher.log`, screenshots of backtest charts, error modal screenshots.
> - **FORBIDDEN TO ATTACH:** Never attach recovery codes, session tokens, JWTs, `.sqlite3` database files containing user hashes, or private strategy source code.

---

## 5. Clean Rollback Procedure

If a beta workstation experiences an unrecoverable failure or needs to revert to a prior release candidate:

1. **Stop Running Processes:**
   Exit the AlgoFortis window. Verify in Windows Task Manager that `AlgoFortis.exe` and any child `python.exe` processes have terminated.
2. **Preserve User Data:**
   User databases reside in `%LOCALAPPDATA%\AlgoFortis`. **Do not delete this folder.** It contains your registered device identity, backtest runs, and paper session records.
3. **Reinstall Known-Good Build:**
   Run the verified known-good `AlgoFortis-Setup.exe` installer. The installer replaces binaries in `Program Files\AlgoFortis` and automatically preserves `%LOCALAPPDATA%\AlgoFortis`.
4. **Relaunch & Verify:**
   Launch AlgoFortis. Existing passkeys and device authorization will recognize the workstation without requiring a new invitation.
