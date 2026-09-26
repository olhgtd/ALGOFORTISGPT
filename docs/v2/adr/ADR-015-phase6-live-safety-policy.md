# ADR-015 — Phase 6 Live Safety Policy

- **Date:** 2026-09-26
- **Status:** ACCEPTED / OWNER-FROZEN
- **Decisions:** OD-V2-05, OD-V2-06, OD-V2-08, OD-V2-09
- **Phase:** AlgoFortis V2 Phase 6 — Live Execution V2 (still DISARMED)

## Context

Phase 6 introduces the first real-broker adapter and real-account truth/reconciliation while preserving the standing V2 rule that Live mutation remains unreachable during qualification. Four Owner Decisions block the phase: multi-device exclusivity, foreign broker activity, broker-resident protection, and the regulatory/broker review path.

The Owner explicitly selected the conservative **Option A** for all four decisions on 2026-09-26.

## OD-V2-05 — Multi-device Live exclusivity

**Decision: Option A — local hard backstop is mandatory.**

1. Local safety MUST NOT depend on cloud availability.
2. The engine MUST maintain a local account/device ownership/exclusivity boundary for any future armed Live state.
3. Broker-truth reconciliation MUST detect activity inconsistent with the current local engine's known intents/orders/positions.
4. A second/foreign activity condition MUST fail closed: halt new entries, enter reconciliation/recovery as appropriate, and alert.
5. A future cloud `armed_device` record MAY be added only as advisory defense-in-depth. It MUST NOT replace the local hard backstop or become trading authority.
6. Cloud outage MUST NOT loosen exclusivity or create permission to arm.

## OD-V2-06 — Foreign order / position policy

**Decision: Option A — halt + alert + explicit manual adoption only.**

1. Broker orders/positions not attributable to AlgoFortis MUST be treated as foreign activity.
2. Foreign activity MUST halt new entries for the affected account/context and generate an auditable alert.
3. Foreign activity MUST NOT be ignored.
4. Foreign activity MUST NOT be auto-adopted.
5. Any adoption requires an explicit, audited human action under a separately defined adoption workflow.
6. Reconciliation remains authoritative for classifying broker truth; detection itself does not submit/cancel/modify orders.

## OD-V2-08 — Broker-resident protective orders

**Decision: Option A — broker-resident protection is mandatory wherever the broker supports it.**

1. For future Live mutation, protective stop/target behavior MUST rest at the broker wherever the selected broker/API supports the required semantics.
2. Local-only protection is not accepted as an equivalent safety substitute for a broker capability that exists.
3. If the broker/API cannot provide the protection required by the frozen strategy/risk policy, AlgoFortis MUST remain DISARMED for that affected path until a separate degraded policy is explicitly designed, reviewed, qualified, and Owner-approved.
4. Missing/unknown broker protective capability fails closed.
5. Recovery/reconciliation MUST verify broker-resident protection before any later entry permission can be considered.

## OD-V2-09 — Regulatory and broker path

**Decision: Option A — dated current verification is mandatory before G6 exit.**

1. Phase-6 implementation MAY proceed in contracts, read-only, mock, sandbox, and DISARMED qualification modes.
2. G6 MUST NOT close until a dated review of the selected broker's current compliance/API documentation and applicable current exchange/regulatory requirements has been completed and recorded as design/evidence input.
3. Historical assumptions MUST NOT be treated as current truth.
4. The review must distinguish personal/private use from any distributed/user-facing product path where the rules differ.
5. The recorded review is an engineering/compliance input, not a substitute for qualified legal/compliance advice where such advice is required.
6. Live mutation remains DISARMED until all later release/pilot gates and explicit Owner authorization are satisfied.

## Phase-6 entry and exit consequences

- G5 Owner gate is separately recorded in `docs/v2/phase5/G5_OWNER_APPROVAL.md`.
- S2 device/session gating remains a required dependency before Phase-6 exit.
- OD-V2-05, OD-V2-06, OD-V2-08 and OD-V2-09 are now FROZEN.
- The first real broker adapter is qualified **DISARMED**.
- Read-only broker balances/orders/positions/reconciliation may be implemented and tested.
- No decision in this ADR authorizes real-money order mutation.

## Required verification themes

Phase 6 must eventually prove, at minimum:

- real-adapter contract conformance;
- stable read-only broker reconciliation;
- deterministic foreign-activity detection and fail-closed response;
- multi-device/exclusivity invariant coverage;
- broker protective-capability detection and protection verification;
- disconnect/reconnect/rate-limit/token-refresh handling;
- dated OD-V2-09 compliance/broker review evidence;
- Live mutation still unreachable while DISARMED.

## Safety invariants preserved

- RiskGate remains the only executable-order approval authority.
- Strategy, AI, UI, notifier, watchdog, cloud account authority, and reconciliation do not gain direct broker-mutation authority.
- Cloud cannot become trading authority.
- Restart/reconnect never auto-arms.
- Uncertainty fails closed.
- Live remains `READ_ONLY / DISARMED` throughout Phase-6 qualification unless a later explicitly authorized release gate changes that standing state.
