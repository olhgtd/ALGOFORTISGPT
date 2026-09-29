# V1 Salvage Integration

This directory tracks the **implementation-side reunion** of the manually-built AlgoFortis V1 product work with the current V2 convergence tree.

## Branch

`v1-salvage-integration-20260929`

Base authority:

- source convergence branch: `v2-convergence-v1-salvage-20260928`
- frozen base SHA: `7a51807b4dd5a0788ec3bf32a228f771867ddb2f`
- manual-V1 knowledge/reference branch: `v1-manual-salvage-reference-20260929`

## Rule

> V2 is the skeleton and authority. Manual V1 is the product-feature and regression-knowledge donor.

No V1 salvage is allowed to create a parallel RiskGate, Paper engine, broker-mutation path, recovery engine, idempotency/order authority, or identity authority.

## Completed/active slices

### Slice 1 — Security & Platform Salvage

Files:

- `SLICE1_SECURITY_PLATFORM.md`
- `SLICE1_VERIFICATION.md`
- `../superpowers/plans/2026-09-29-v1-salvage-integration-slice1.md`

Changes:

- strict manifest-closed `AlgoFortisBackup/v1` restore;
- `included_categories` ↔ checksum-map consistency validation;
- regression tests for those backup boundaries;
- guard preserving `RiskGateV2` as the only engine caller of the private ApprovedOrder minter;
- restart-from-ACTIVE guard requiring RECOVERY and no auto-arm.

### Slice 2 — Recovery, Persistence & Idempotency Compatibility

Files:

- `SLICE2_RECOVERY_IDEMPOTENCY.md`
- `SLICE2_VERIFICATION.md`
- `../superpowers/plans/2026-09-29-v1-salvage-integration-slice2.md`

Result:

- current V2 Phase-5 recovery/persistence and Phase-2 IntentGuard are retained as canonical;
- no old V1 recovery/idempotency runtime was transplanted;
- added a regression guard proving a conflicting duplicate recovery checkpoint ID cannot overwrite existing evidence;
- existing V2 tests already cover manual resume, corrupt/missing checkpoint state, duplicate intent/client-order replay and restart replay.

## Existing V1 capabilities already present in the convergence tree

Several high-value manual-V1 foundations were already carried in the current tree and are **preserved/tested rather than duplicated**:

- refresh-token rotation and reuse-family revocation;
- max-device / no-silent-eviction policy;
- high-assurance recovery foundations;
- local data-sovereignty rules;
- DPAPI/device identity foundations;
- backup secret exclusion and path-traversal protections;
- WebView2/local desktop architecture foundations;
- V2 live state machine with restart/crash recovery to RECOVERY;
- Phase-5 Paper recovery/persistence authorities;
- Phase-2 IntentGuard replay protection;
- `RiskGateV2` central approval capability.

## Next slices

1. broker/data read-side salvage;
2. normal User dashboard reunion;
3. Owner/Admin dashboard reunion;
4. installer/update/platform polish;
5. combined qualification.

Laya remains a separate workstream and is not part of this branch until the product/safety reunion reaches its appropriate integration point.

## Verification truth

Slice-specific targeted logic/inspection is recorded in the verification files. A full repository regression has not yet been proven on this branch; merge readiness must remain unclaimed until fresh full-suite/build/Windows evidence exists.
