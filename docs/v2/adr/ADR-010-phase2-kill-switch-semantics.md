# ADR-010 — Phase 2 Kill-Switch Semantics

- **Status:** Accepted / FROZEN
- **Date:** 2026-09-21
- **Owner decision:** OD-V2-07
- **Scope:** AlgoFortis V2.0 Safety Spine

## Context

Phase 2 requires kill-switch behavior to be unambiguous before the Safety Spine can be implemented. A single overloaded “stop” action would create unsafe ambiguity between preventing new risk, cancelling pending entries, and closing existing positions.

## Decision

AlgoFortis V2.0 defines three distinct actions:

1. `HALT_ENTRIES` — blocks creation/submission of new entry orders while allowing protective exits and reconciliation to continue.
2. `CANCEL_PENDING` — cancels unfilled **entry** orders. It does not cancel protective exits.
3. `FLATTEN_ALL` — closes open positions. It is a separate destructive action and must never be implied by a normal emergency stop or reconciliation mismatch.

The standard **Emergency Stop** semantics are:

- activate `HALT_ENTRIES`;
- request `CANCEL_PENDING` for unfilled entry orders;
- keep protective exits active;
- keep reconciliation/read-only safety processing active;
- do **not** invoke `FLATTEN_ALL` automatically.

A reconciliation mismatch triggers **halt + alert + recovery/reconciliation**, not automatic flattening.

`FLATTEN_ALL` remains an explicitly confirmed, separately audited action. Phase 2 only defines and tests the contract; it does not enable real broker mutation while live execution is DISARMED.

## Safety constraints

- Live remains `READ_ONLY=true` and `DISARMED=true` during Phase 2.
- No restart, reconnect, crash recovery, update, or outage may auto-arm the live engine.
- Protective exits are never treated as entry orders by the kill switch.
- Any trading-critical kill-switch state transition must fail closed if required audit evidence cannot be written.
- Mode isolation must prevent backtest or paper processes from loading a real live-mutation adapter.

## Consequences

This decision gives Phase 2 one deterministic contract for `AF2-LIV-010` and supports the Phase 2 invariant set, especially INV-07, INV-15, and INV-16. Broker-specific cancel/flatten mechanics remain deferred to the broker-contract/live-adapter phases; Phase 2 proves the domain semantics without authorizing live-money execution.