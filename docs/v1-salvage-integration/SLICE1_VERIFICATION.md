# Slice 1 Verification — V1 Security & Platform Salvage

## Status

**Implementation status:** PARTIAL-COMPLETE / FULL-REPO-UNVERIFIED

This slice has landed its first concrete hardening + authority guards on the isolated integration branch. The full repository test suite has **not** been executed for this branch because no GitHub workflow run/status is currently attached to the head and the hosted-runner quota is unavailable. Nothing in this report upgrades that missing evidence to PASS.

## Base / branch isolation

- Source convergence base SHA: `7a51807b4dd5a0788ec3bf32a228f771867ddb2f`
- Integration branch: `v1-salvage-integration-20260929`
- Manual-V1 reference branch: `v1-manual-salvage-reference-20260929`
- Source convergence branch was restored to the exact frozen base after branch creation.

## Implemented in Slice 1

### 1. Portable backup manifest hardening

Modified:

- `dashboard/backend/backup_service.py`

Added fail-closed checks:

- `checksums` must be an object with string member names;
- `included_categories` must be a list of strings;
- duplicate `included_categories` entries are rejected;
- `included_categories` must match the checksum-map keys exactly;
- every ZIP payload member other than `manifest.json` must be declared by the checksum map;
- allowed-but-undeclared JSON payloads are rejected rather than silently ignored.

Existing protections remain in place:

- secret/private-key stripping;
- path traversal / rooted path / drive-letter rejection;
- duplicate ZIP member rejection;
- disallowed category rejection;
- schema-version rejection;
- SHA-256 content verification;
- operational SQLite backup integrity checking.

### 2. Backup regression tests

Added:

- `tests_v1/test_v1_salvage_backup_manifest_boundary.py`

Covers:

- allowed-but-undeclared payload rejection;
- `included_categories` / checksum-map mismatch rejection.

### 3. Trading-authority anti-regression guard

Added:

- `tests_v1/test_v1_salvage_authority_boundaries.py`

Guards:

- engine references to `_mint_approved_order(` are restricted to the private contract definition and `engine/risk/gate_v2.py`;
- restart from `ACTIVE` restores to `RECOVERY`;
- restart recovery is not active/armed;
- direct RECOVERY → ACTIVE jump is rejected.

This is specifically intended to stop future V1 salvage from resurrecting a parallel approval path or restoring an active state after restart.

## Existing V1-derived controls found already present

No duplicate implementation was added for controls already represented in the convergence tree, including:

- `SessionManager` refresh-token rotation and reuse-family revocation;
- 15-minute access token and 7-day idle / 30-day absolute refresh limits;
- device quota/recovery foundations in `AuthPolicyManager`;
- local data-sovereignty rules;
- DPAPI/device identity foundation;
- existing `AlgoFortisBackup/v1` secret exclusion and traversal protections;
- V2 `LiveStateMachine` restart/crash recovery to `RECOVERY` with arming disabled;
- `RiskGateV2` private ApprovedOrder minting seam.

Historical/current test evidence already exists in files such as:

- `tests_v1/test_architectural_foundations.py`
- `tests_v1/test_area2_backup_restore_dr.py`
- `tests_v1/test_v2_phase2_live_state_machine.py`

## Verification actually performed in this work session

### Isolated RED → GREEN: undeclared allowed member

The pre-hardening restore logic was exercised against an archive containing:

- declared/checksummed `strategies.json`;
- allowed but undeclared `reports.json`.

Observed before fix:

- test condition failed because restore **did not raise**.

Observed with the new manifest-closed guard:

- `BackupSecurityError` raised as required;
- isolated targeted test: **1 passed**.

### Isolated RED → GREEN: included-category mismatch

Pre-hardening behavior accepted a manifest where:

- `included_categories = ["reports.json"]`;
- checksum map + payload contained only `strategies.json`.

New behavior rejects it with:

- `Invalid archive manifest: included_categories mismatch checksums`.

### Isolated backup behavior sanity checks

The hardened restore logic was exercised for five conditions:

1. valid roundtrip + secret stripping — PASS;
2. tampered payload checksum rejection — PASS;
3. undeclared allowed payload rejection — PASS;
4. included-category/checksum mismatch rejection — PASS;
5. path traversal rejection — PASS.

These are isolated logic checks, **not a substitute for the full repository pytest suite**.

## GitHub CI/status evidence

At the inspected Slice-1 head:

- pull-request-triggered workflow runs attached to the commit: **none**;
- combined commit statuses: **none**.

Therefore:

- full Python regression: **PENDING**;
- frontend tests/typecheck/build: **NOT REQUIRED by current code diff, but branch-wide qualification still pending**;
- hosted Windows gates: **PENDING**;
- merge readiness: **NOT CLAIMED**.

## Safety impact

No change in this slice intentionally enables:

- real broker place/modify/cancel;
- Live arming;
- a second RiskGate;
- a second Paper execution engine;
- Laya/AI execution authority;
- cloud-held broker credentials.

Required posture remains:

```ini
READ_ONLY=true
DISARMED=true
live_global_hold=true
real broker mutation=DISABLED
```

## Next Slice

Proceed to **Slice 2 — persistence/recovery/idempotency compatibility**, using the same method:

1. locate current V2 authority;
2. port V1-derived regression cases first;
3. implement only missing behavior;
4. preserve RECOVERY/manual-resume and fail-closed semantics;
5. defer merge consideration until full regression evidence is available.
