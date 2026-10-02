# Phase 10 — Release Qualification & S3 Completion Implementation Plan

**Date:** 2026-10-02  
**Base:** `main@063cf728be2af47b5541fce58f809ec192cd1229`  
**Branch:** `phase10/release-qualification-20261002`  
**Authority:** `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`, `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`, OD-V2-18/20/21/22/23/26, ADR-016.

## Safety / scope lock

- `RiskGateV2` remains the sole `ApprovedOrder` authority.
- Live remains `READ_ONLY / DISARMED`.
- Phase 10 engineering qualification does **not** enable broker mutation or real-money execution.
- OD-V2-18 Live pilot policy remains OPEN; no real-money pilot is executed.
- Exact legal publisher and canonical production domain remain `PENDING_EXTERNAL`; production release/signing must fail closed until finalized.
- Legal/compliance review remains an external gate; software tests do not certify legal compliance.

## Goal

Complete Track-P S3 engineering requirements and add a deterministic G10 release-qualification system that can freeze a technically qualified research/backtest/paper/staging RC while truthfully reporting external-release blockers.

## Task 1 — V2 update safety + signed-manifest enforcement

**Modify**
- `dashboard/backend/update_service.py`

**Create tests**
- `tests_v1/test_phase10_update_s3.py`

**Required behavior**
- reuse `UpdateSafeWindowPolicy` / `evaluate_update_safe_window` from S2 policy seams;
- update application is deferred if policy is missing/invalid/inapplicable;
- ACTIVE engine state and unsafe open-position state block update;
- update can never auto-arm Live;
- manifest carries signing key id + detached signature metadata;
- production-shaped verification requires an explicit signature verifier; missing verifier fails closed;
- SHA-256 payload verification remains mandatory;
- channel mismatch and malformed digest fail closed.

**TDD**
1. RED tests for missing policy, ACTIVE state, signature verifier absence, invalid signature, channel mismatch.
2. GREEN minimal integration.
3. Existing Area-3 and architectural-foundation update tests remain green after migration.

## Task 2 — V2 entitlement + telemetry policy integration

**Modify**
- `dashboard/backend/entitlement_service.py`
- `dashboard/backend/telemetry_service.py`

**Create tests**
- `tests_v1/test_phase10_entitlement_telemetry_s3.py`

**Required behavior**
- entitlement validation requires `EntitlementTimeEvidence` and `evaluate_entitlement_time`;
- wall-clock-only validation path is removed from production-shaped API;
- uncertainty yields `ENTITLEMENT_TIME_UNCERTAIN` for entitlement-dependent new operations;
- expiry/outage never disables protective safety/read-only safety access;
- device mismatch still fails closed;
- telemetry requires `TelemetryPrivacyPolicy`;
- no opt-in => no telemetry envelope;
- forbidden data classes remain rejected by the shared policy seam;
- support bundle sanitization remains explicit-user-export only.

## Task 3 — Packaging / publisher-domain fail-closed boundary

**Modify**
- `build/tools/algofortis_installer.iss`
- `build/tools/build_installer.ps1` if needed

**Create**
- `build/tools/check_phase10_packaging.py`
- `tests_v1/test_phase10_packaging_guard.py`

**Required behavior**
- production package cannot silently use guessed publisher/domain;
- release metadata is explicit input;
- `PENDING_EXTERNAL` blocks production-release packaging;
- qualification/staging packaging remains explicitly labelled non-production;
- Program Files / LocalAppData separation and uninstall preservation remain unchanged;
- no installer/update action auto-arms Live.

## Task 4 — GP-S3 qualification authority

**Create**
- `dashboard/backend/release_v2/__init__.py`
- `dashboard/backend/release_v2/s3.py`
- `tests_v1/test_phase10_s3_qualification.py`

**Evidence dimensions**
- installer lifecycle coverage;
- update-safe-window coverage;
- manifest/signature enforcement;
- entitlement time-evidence enforcement;
- telemetry opt-in/privacy boundary;
- `AlgoFortisBackup/v1` backup/restore;
- uninstall data preservation;
- production identity external status.

**Output states**
- `GP_S3_ENGINEERING_PASS`
- `GP_S3_EXTERNAL_RELEASE_BLOCKED`
- fail closed on any missing mandatory engineering evidence.

## Task 5 — G10 release-candidate qualification model

**Create**
- `dashboard/backend/release_v2/contracts.py`
- `dashboard/backend/release_v2/qualification.py`
- `tests_v1/test_phase10_release_qualification.py`

**Required behavior**
- deterministic checklist matching Test & Release Plan §11.1;
- defect register requires zero open P0 and zero open P1 on production-critical paths;
- evidence bundle manifest contains version/SBOM reference/artifact hashes/traceability/invariants/golden/FI/soak/security/DR/performance/defect/OD snapshot/sign-off refs;
- RC can be frozen only when mandatory engineering checks pass;
- external publisher/domain/legal/live-pilot blockers remain separately visible and cannot be converted to PASS by code;
- final technical status may be `TECHNICALLY_QUALIFIED_EXTERNAL_RELEASE_BLOCKED`;
- Live remains `READ_ONLY/DISARMED`.

## Task 6 — Static guard, deterministic probe and evidence docs

**Create**
- `build/tools/check_phase10_release.py`
- `build/tools/phase10_release_probe.py`
- `tests_v1/test_phase10_architecture_guard.py`
- `tests_v1/test_phase10_evidence.py`
- `docs/v2/phase10/G10_EVIDENCE.md`
- `docs/v2/phase10/G10_EXTERNAL_RELEASE_STATUS.md`

**Guard rules**
- no Phase-10 module may mint/import private ApprovedOrder construction authority;
- no Phase-10 module may enable Live mutation;
- no hard-coded production publisher/domain;
- no bypass of S2/Portfolio/RiskGateV2;
- no software-only claim of legal compliance.

## Task 7 — G10 CI qualification

**Create**
- `.github/workflows/v2-phase10-release.yml`

**Jobs**
1. focused Windows latest;
2. focused Windows 2022;
3. full repository preservation Windows latest;
4. exact cross-Windows deterministic evidence compare.

**Full preservation includes**
- compileall;
- all static/safety guards Phase 1–10 + S2 + AI/Laya;
- full `tests_v1`;
- regression certification;
- deterministic probes;
- root/dashboard npm audits;
- dashboard tests/typecheck/build.

## Task 8 — Final branch qualification and integration

- exact-head Phase 10 workflow must pass;
- Phase 5/6/7/8/9, Live reunion and AI/Laya workflows must also pass on the same final head;
- review PR diff for authority changes;
- merge only the exact qualified head;
- post-merge verify `main` SHA and signature.

## Completion semantics

**Engineering Phase 10 complete** means:
- S3 engineering contract is implemented and qualified;
- G10 technical RC qualification evidence is reproducible;
- zero tested P0/P1 blockers remain;
- release packaging truthfully blocks on external publisher/domain/legal gates;
- Live remains `READ_ONLY/DISARMED`.

It does **not** mean:
- legal compliance certified;
- production code-signing identity finalized;
- production domain finalized;
- real-money Live pilot executed or authorized.
