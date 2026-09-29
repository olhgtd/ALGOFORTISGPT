# Slice 2 — Recovery, Persistence & Idempotency Compatibility

## Purpose

Preserve useful manual-V1 restart, replay-protection, persistence-integrity and projection-dedup behavior while keeping the current V2 recovery/persistence authorities canonical.

## Result of the compatibility audit

The current V2 tree already contains stronger or equivalent mechanisms for nearly all V1 behaviors in this slice. Therefore **no legacy V1 recovery engine, idempotency ledger, projection store, or session authority is transplanted**.

## Current V2 authorities retained

### Phase-5 recovery coordinator

`engine/paper/recovery_coordinator_v2.py`

Canonical ordered recovery checks remain:

1. reconciliation;
2. protective-stop integrity;
3. feed health;
4. clock health;
5. session validity.

Uncertainty/critical failure remains fail-closed. A clean recovery reaches `READY_FOR_RESUME` with `manual_resume_required=True`; it does not auto-resume.

### Operational-state machine

`engine/paper/operational_state_v2.py`

Manual resume remains gated by:

- current state = `READY_FOR_RESUME`;
- transition reason = `MANUAL_RESUME`;
- explicit resume authority with `allowed=True`;
- nonblank evidence/reference.

### Recovery checkpoint store

`engine/persistence/paper_recovery_store_v2.py`

Retained behavior:

- append-style checkpoint identity via primary key;
- fingerprint shape validation;
- indexed-field/payload agreement validation;
- corrupt checkpoint rejection through `CheckpointIntegrityError`;
- latest checkpoint selected deterministically by sequence/time/ID.

### Owned-state persistence

Existing Phase-5 persistence tests already pin:

- exact Paper session/order/position roundtrip;
- missing checkpoint-referenced order fails closed;
- missing checkpoint-referenced position fails closed;
- corrupt checkpoint fingerprint fails closed;
- owned-state load passes through checkpoint integrity validation.

### Order/intent replay protection

`engine/orders/intent_guard.py` remains the stronger V2 equivalent of V1 replay/projection-dedup behavior.

Existing `tests_v1/test_v2_phase2_intent_guard.py` already proves:

- first valid ApprovedOrder is consumed once;
- same `intent_id` is rejected on second consumption;
- restored state rejects replayed `client_order_id`;
- exported/restored guard state blocks restart replay;
- stale intent is rejected without consuming identity;
- snapshot identity sets are deterministic.

This is stronger and closer to executable-order authority than adding a second dashboard-only dedup mechanism.

### Legacy V1 idempotency tests retained as regression knowledge

`tests_v1/test_db011_idempotency.py` remains in the tree and covers historical security/idempotency scenarios such as duplicate/retry convergence and activation replay protection. It remains regression knowledge, not a second V2 order authority.

## New Slice-2 guard

Added:

`tests_v1/test_v1_salvage_recovery_idempotency_compatibility.py`

It pins one uncovered compatibility property:

> a second recovery checkpoint using the same checkpoint identity but conflicting payload/sequence must fail with SQLite uniqueness enforcement, and the original checkpoint remains the authoritative stored evidence.

## Explicitly not imported from V1

- old generic idempotency ledger as a new V2 subsystem;
- old dashboard projection store as an execution truth source;
- old restart hydration that could restore ACTIVE state;
- old recovery coordinator;
- old Paper runtime/session authority;
- any automatic resume behavior.

## Permanent rule

Recovery compatibility is judged against current V2 safety semantics. If an old V1 behavior conflicts with V2 RECOVERY / READY_FOR_RESUME / manual-resume rules, **V2 wins**.
