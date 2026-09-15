# AlgoFortis V1 — Beta Release Gate Checklist

**RELEASE CANDIDATE:** Local V1 RC1  
**TARGET MILESTONE:** External Beta Launch  
**STATUS:** PREPARATION IN PROGRESS  

---

## Gate 1: Product Certification & Invariants

- [x] **RC Baseline Verified:** Source files, staging files, and test results match `docs/releases/ALGOfORTIS_LOCAL_V1_RC1_BASELINE.md`.
- [x] **Source Tests Passing:** All 146 tests in `tests_v1` passing (`python -m pytest tests_v1 -q`).
- [x] **Full Regression Certification:** Architectural and regression suite certified passing (`python build/tools/run_regression_certification.py`).
- [x] **Database Integrity Clean:** `PRAGMA integrity_check` returns `ok` and `foreign_key_check` returns 0 violations on all local databases.
- [x] **Safety Baseline Strictly Enforced:**
  - `READ_ONLY=true`
  - `DISARMED=true`
  - `live_global_hold=true`
  - `broker mutation=ZERO`
  - `real broker connection=NONE`
- [x] **Live Trading Endpoints Disabled:** Live order routes return HTTP 403 `EXECUTION_DISABLED`.

---

## Gate 2: Packaging & Binary Signing

- [x] **Installer Present:** `build\installer\AlgoFortis-Setup.exe` built and verified.
- [x] **Executable Present:** `build\stage\AlgoFortis.exe` compiled and staged.
- [x] **Hashes Recorded:** Authoritative SHA-256 manifest recorded in `docs/releases/ALGOfORTIS_LOCAL_V1_RC1_SHA256.txt`.
- [ ] **Windows Code-Signing Certificate Acquired:** [OWNER ACTION REQUIRED] EV / Authenticode certificate ready for use.
- [ ] **Executable Signed:** `AlgoFortis.exe` signed with SHA-256 and RFC 3161 timestamp.
- [ ] **Installer Signed:** `AlgoFortis-Setup.exe` signed with SHA-256 and RFC 3161 timestamp.
- [ ] **Post-Sign Hashes Updated:** Final distribution SHA-256 hashes published in release notes.

---

## Gate 3: Legal & Governance Documentation

- [ ] **Publisher & Legal Entity Confirmed:** [OWNER ACTION REQUIRED] Official corporate entity name and registered address confirmed.
- [x] **Terms of Use Reviewed:** Draft completed in `docs/legal/ALGOfORTIS_TERMS_OF_USE_DRAFT_V1.md`.
- [x] **Privacy Policy Reviewed:** Draft completed in `docs/legal/ALGOfORTIS_PRIVACY_POLICY_DRAFT_V1.md`.
- [x] **Risk Disclaimer Reviewed:** SEBI-compliant F&O and backtest risk disclosures drafted in `docs/legal/ALGOfORTIS_RISK_DISCLAIMER_DRAFT_V1.md`.
- [x] **Beta Agreement Reviewed:** Pre-release confidentiality and feedback terms drafted in `docs/legal/ALGOfORTIS_BETA_AGREEMENT_DRAFT_V1.md`.
- [x] **Refund & Cancellation Policy:** Draft completed in `docs/legal/ALGOfORTIS_REFUND_CANCELLATION_DRAFT_V1.md`.
- [x] **Support & SLA Policy:** Draft completed in `docs/legal/ALGOfORTIS_SUPPORT_POLICY_DRAFT_V1.md`.

---

## Gate 4: Operational Readiness

- [ ] **Support Inbox Operational:** [OWNER ACTION REQUIRED] Dedicated beta support email address (`[SUPPORT_EMAIL]`) configured and monitored.
- [x] **Owner Authentication Secured:** Master Owner (`OWNER-001`) passkeys configured with dual hardware key break-glass capability.
- [x] **Onboarding Procedure Tested:** Manual user creation and 24-hour activation code reissue validated end-to-end.
- [x] **Recovery Procedure Tested:** 8 one-time recovery codes and session revocation verified.
- [x] **Issue Intake Process Ready:** Structured P0–P3 bug report template documented in `docs/beta/ALGOfORTIS_EXTERNAL_BETA_RUNBOOK_V1.md`.

---

## Gate 5: Beta Tester Cohort Provisioning

- [ ] **Candidate Beta Quant Selection:** Cohort of initial quantitative testers identified and invited.
- [ ] **Out-of-Band Activation Sent:** 24-hour activation code securely delivered to each approved tester.
- [ ] **Passkey Enrolled:** Tester successfully completes FIDO2 / Windows Hello passkey ceremony.
- [ ] **Recovery Codes Safely Stored:** Tester acknowledges offline storage of 8 recovery codes.
- [ ] **Device Cap Enforced:** Tester workstation registered within the 3-device ceiling.
- [ ] **Confirmation of Safe Mode:** Tester confirms application runs in Backtest / Paper mode only.
