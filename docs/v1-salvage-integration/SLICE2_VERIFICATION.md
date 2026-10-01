# Slice 2 Verification — Recovery, Persistence & Idempotency Compatibility

## Status

**Implementation status:** COMPATIBILITY GUARD ADDED / FULL-REPO-UNVERIFIED

Slice 2 intentionally introduces no replacement recovery/idempotency runtime. The audit found current V2 authorities already supersede the useful V1 behaviors; one missing regression guard was added for duplicate checkpoint identity.

## Changed in Slice 2

Added:

- `tests_v1/test_v1_salvage_recovery_idempotency_compatibility.py`
- `docs/v1-salvage-integration/SLICE2_RECOVERY_IDEMPOTENCY.md`
- `docs/superpowers/plans/2026-09-29-v1-salvage-integration-slice2.md`

Runtime files modified by Slice 2: **none**.

## Newly pinned property

The new test verifies that:

1. a canonical recovery checkpoint is saved;
2. a second checkpoint with the same `checkpoint_id` but conflicting sequence/fingerprint is attempted;
3. SQLite uniqueness enforcement rejects the conflicting replay;
4. the original checkpoint remains the result returned by `latest_checkpoint()`.

This preserves recovery evidence immutability rather than silently overwriting it.

## Existing stronger V2 evidence reused

### Manual resume / no auto-resume

Existing `tests_v1/test_phase5_operational_state.py` covers READY_FOR_RESUME/manual-resume authority, invalid resume reasons, denied authority and sticky halt/recovery behavior.

### Recovery ordering / fail-closed uncertainty

Existing `tests_v1/test_phase5_recovery.py` covers uncertain reconciliation, mismatch/halt and clean recovery reaching READY_FOR_RESUME with manual resume still required.

### Corrupt/missing persistence state

Existing `tests_v1/test_phase5_persistence.py` covers checkpoint fingerprint integrity, missing referenced orders/positions and exact state roundtrips.

### Duplicate/restart order replay

Existing `tests_v1/test_v2_phase2_intent_guard.py` covers duplicate `intent_id`, duplicate `client_order_id` after restored state, restart replay and deterministic identity snapshots.

### Historical V1 idempotency knowledge

Existing `tests_v1/test_db011_idempotency.py` remains available as V1 regression knowledge for retry/duplicate security-store scenarios.

## Verification limitation

The new test file has been committed but **has not been executed by a repository runner in this session**. GitHub-hosted workflow capacity/status is not assumed. Therefore:

- new focused test: **PENDING RUNNER VERIFICATION**;
- full Python regression: **PENDING**;
- Windows hosted qualification: **PENDING**;
- merge readiness: **NOT CLAIMED**.

## Safety conclusion

Slice 2 did not add or enable:

- broker place/modify/cancel;
- Live arming;
- automatic restart resume;
- a second RiskGate;
- a second Paper engine;
- a second recovery coordinator;
- a second idempotency/order authority.

Current V2 recovery, IntentGuard and RiskGateV2 remain authoritative.
