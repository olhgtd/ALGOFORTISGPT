# AlgoFortis V1 — Privacy Policy (Draft)

> [!NOTE]
> **LEGAL NOTICE & DISCLAIMER:**  
> This document is a draft operational privacy policy prepared for internal product readiness and external beta testing under the provisions of the Digital Personal Data Protection Act, 2023 (DPDP Act, India) and the Information Technology Act, 2000. It does not constitute formal legal counsel and must be finalized by qualified legal counsel prior to commercial launch.

**EFFECTIVE DATE:** `[EFFECTIVE_DATE]` (e.g., October 1, 2026)  
**ENTITY / DATA FIDUCIARY:** `[LEGAL_ENTITY_NAME]`  
**REGISTRATION/CIN:** `[CIN_OR_REGISTRATION_NUMBER]`  
**REGISTERED OFFICE:** `[REGISTERED_ADDRESS]`  
**GRIEVANCE OFFICER / CONTACT:** `[LEGAL_EMAIL]`  

---

## 1. Overview & Local-First Philosophy

`[LEGAL_ENTITY_NAME]` ("Company", "we", "us") respects your privacy. Unlike cloud-hosted platforms that ingest sensitive financial algorithms and credentials into central servers, **AlgoFortis is built on a local-first privacy architecture**.

In AlgoFortis Local V1:
- Your quantitative strategies, backtest databases, simulated paper execution records, and local configuration files reside exclusively on your local workstation.
- We **do not** upload, inspect, synchronize, or store your trading models or strategy source code on Company servers.

---

## 2. Information We Process

### A. Information Provided During Onboarding (Operator-Managed)
Because AlgoFortis uses manual, Owner-controlled onboarding rather than public self-signup, the Super Owner enters the following information to initialize your profile:
- **Identity Data:** Full display name, business email address, optional contact telephone number.
- **Account Metadata:** Assigned user identifier (`SX-ID`), role (`USER`), service entitlement tier, and activation timestamps.

### B. Local Authentication & Device Data (Stored Locally on User's Workstation)
To secure the local application instance, the software generates and validates:
- **Device Cryptographic Fingerprints:** Windows DPAPI / TPM / CNG-backed hardware identity hashes to enforce the 3-device authorization policy.
- **Passkey / WebAuthn Public Keys:** Standard FIDO2 public key credentials stored in the local SQLite database. Private keys remain securely stored inside your hardware security key or Windows Hello authenticator and are never transmitted.
- **Session Tokens:** Cryptographic JWT access tokens and rotated refresh tokens stored in memory and local session stores.
- **Recovery Hashes:** One-time recovery code SHA-256 digests stored locally to permit secure account recovery.

### C. Data We Do NOT Collect
- **Zero Live Broker Secrets:** We do not collect or transmit real broker API keys, API secrets, or access tokens.
- **Zero Strategy Ingestion:** Your `.py` algorithmic trading scripts remain strictly inside your local directory (`%LOCALAPPDATA%\AlgoFortis\artifacts`).
- **Zero Unsolicited Background Telemetry:** AlgoFortis V1 does not execute covert background usage tracking, screen capture, or keylogging.

---

## 3. Purpose of Processing

We process onboarding and authentication data solely for:
1. Verifying your identity during authorized local login ceremonies.
2. Enforcing software license terms and the 3-device hardware registration ceiling.
3. Providing customer support and administrative account recovery.
4. Maintaining immutable local audit trails for governance and compliance.

---

## 4. Data Sharing & Third Parties

1. **Zero Data Monetization:** We never sell, rent, trade, or monetize your personal data or strategy assets.
2. **Third-Party Service Providers:** In Local V1, no external analytics or third-party tracking libraries are bundled into the application.
3. **Legal Compliance:** We will disclose personal data only when required by applicable law, court order, or regulatory direction issued by Indian governmental authorities (e.g., SEBI, CERT-In, Law Enforcement Agencies).

---

## 5. Security & Storage Safeguards

1. **Windows NTFS ACL Isolation:** Application databases are created with restricted file permissions accessible only by your active Windows user account.
2. **Sanitized Backups:** The portable backup export tool (`AlgoFortisBackup/v1`) enforces automatic secret blacklisting to prevent inadvertent disclosure of credentials.
3. **Fail-Closed Operations:** Any detected tampering with authentication parameters or session tokens immediately revokes access.

---

## 6. Your Rights Under the DPDP Act, 2023

As a Data Principal under the Digital Personal Data Protection Act, 2023 (India), you have the right to:
1. **Access:** Confirm processing and receive a summary of personal data held.
2. **Correction & Updating:** Request correction of inaccurate or incomplete personal profile metadata.
3. **Erasure:** Request deletion of your user account record (upon termination of your beta agreement, subject to legal audit retention requirements).
4. **Grievance Redressal:** File grievances regarding personal data processing with our designated Grievance Officer.

---

## 7. Data Retention & Deletion

- **Uninstallation Behavior:** Uninstalling the Software from Windows removes the application binaries from `Program Files\AlgoFortis`. In accordance with product contract, user data and databases in `%LOCALAPPDATA%\AlgoFortis` are preserved to prevent accidental data loss.
- **Manual Deletion:** Users may permanently delete their local data at any time by manually removing the `%LOCALAPPDATA%\AlgoFortis` directory.

---

## 8. Grievance Officer & Contact Details

In compliance with the Information Technology Act, 2000, and the DPDP Act, 2023, the details of the Grievance Officer are:

- **Name:** `[GRIEVANCE_OFFICER_NAME]`
- **Designation:** Data Protection & Grievance Officer
- **Email:** `[LEGAL_EMAIL]`
- **Support Inbox:** `[SUPPORT_EMAIL]`
- **Postal Address:** `[REGISTERED_ADDRESS]`
