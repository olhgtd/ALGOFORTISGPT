# AlgoFortis V2 — V1 Contract Freeze Map

**Status:** Phase 0 audit artifact  
**Date:** 2026-09-21  
**Rule:** V2 wraps or extends these contracts. Stable V1 semantics are not rewritten for style.

## Classification

- **PRESERVE** — keep behavior/schema identity unless an explicit ADR authorizes change.
- **WRAP** — keep existing implementation and expose it behind a V2 contract/capability boundary.
- **EXTEND** — add V2 states/fields/contracts without silently changing historical meaning.
- **AUDIT** — retain but prove coverage/invariants before depending on it.

## Frozen contract map

| Area | V1 authority / paths | V2 treatment | Frozen meaning |
|---|---|---|---|
| Numeric | `engine/core/numeric.py`, Decimal use throughout risk/order/accounting | PRESERVE | Money/price/qty/risk conversions must not silently route through binary float. OD-V2-12 governs V2 extensions. |
| Risk | `engine/risk/risk_manager.py` | PRESERVE + WRAP | Existing deterministic RiskGate, fail-closed rejection semantics, policy identities, quantity/risk controls remain authoritative foundations. V2 adds the capability boundary rather than replacing risk math. |
| Signal intent / order request | `engine/orchestration/signal_intake.py`, `engine/orders/model.py` | PRESERVE + WRAP | `OrderRequest` remains a validated non-executable request with source provenance. It is not silently redefined as executable. |
| Concrete entry/exit instructions | `engine/orders/model.py` | PRESERVE + WRAP | Existing provenance-preserving instructions remain semantic/execution projections. They do not become V2 risk approval capabilities by renaming. |
| Order lifecycle | `engine/orders/lifecycle.py` | PRESERVE + EXTEND | Existing CREATED/VALIDATED/QUEUED/CANCELLED/REJECTED/EXPIRED/FILLED meanings are frozen. V2 submission/ack/IN_DOUBT semantics require an explicit additive/superseding contract and migration tests. |
| Audit/event journal | `engine/audit/model.py`, `engine/audit/log.py`, `engine/audit/sinks.py` | PRESERVE + WRAP | Existing versioned envelope, taxonomy, canonical identities, redaction and durable evidence semantics remain evidence authorities. V2 envelope additions require versioned compatibility. |
| Reproducibility | `engine/reproducibility/` | PRESERVE + AUDIT | Canonical codec/fingerprint conventions stay authoritative for deterministic evidence. V2 run manifests must compose with, not bypass, these identities. |
| Strategy core | `engine/strategy/base.py` | PRESERVE + EXTEND | Interface v1.0 and Signal semantics remain valid V1 contracts. V2 SDK manifests/lifecycle/promotion evidence are additive layers with compatibility rules. |
| Protective logic | `engine/protective/` | PRESERVE | Existing protective-plan/runtime authorities and provenance are not duplicated by V2 risk/order code. |
| Paper execution | existing paper engine/adapters and `tests_v1` workflows | PRESERVE + WRAP | Paper remains simulated execution and must never acquire a path to real broker mutation. V2 broker contract conformance wraps existing behavior. |
| Broker adapters | `engine/broker_adapters/` | AUDIT + WRAP | Adapter capabilities, dedupe/error classification and read/write methods stay behind a V2 `BrokerPort`; mutation capability must be mode/capability gated. |
| Live readiness | `dashboard/backend/live_readiness_service.py`, `dashboard/backend/live_broker_read.py` | PRESERVE HARD SAFETY | Current READ_ONLY/SHADOW boundary and zero-mutation posture are frozen throughout Phase 0–qualification. `require_live_mutation()` must remain fail-closed. |
| Reconciliation / restart | `engine/reconciliation/`, restart/recovery code and tests | PRESERVE + EXTEND | Broker truth, stale/duplicate suppression and recovery evidence remain foundations. V2 adds formal IN_DOUBT/foreign-order/device rules without weakening reconciliation. |
| Auth/access | `AUTH_ACCESS_CONTRACT_V1`, auth/session/device modules and tests | PRESERVE | Owner/User authority, device/session/recovery controls remain binding. V2 account plane cannot weaken local safety. |
| Data feeds | `engine/data/feeds/`, provider modules and isolation tests | PRESERVE + EXTEND | Normalization, staleness/out-of-order/reconnect behavior remain foundations. V2 adds immutable dataset catalog/provenance/licensing contracts separately. |
| Safety / kill state | `engine/safety/` and safety/restart tests | PRESERVE + EXTEND | Existing fail-closed safety state remains authoritative until OD-V2-07 defines additive V2 kill-switch semantics. |
| Installer/update/backup | `build/`, release/backup modules and `tests_v1` installation/DR tests | PRESERVE + EXTEND | Program Files/LocalAppData separation, backup secret exclusion and safe recovery remain frozen; V2 updater/licence additions cannot weaken them. |

## V2 Phase 1/2 interface rules derived from the freeze

1. V2 `ApprovedOrder` must be a **new capability**, not a rename of `OrderRequest` or `ConcreteOpenInstruction`.
2. Only the V2 RiskGate approval path may mint that capability.
3. Broker mutation interfaces must accept the capability type and matching fixed run mode; paper/backtest must not load live mutation authority.
4. V2 `IN_DOUBT` must be introduced with explicit migration/compatibility rules; existing lifecycle state meanings remain unchanged.
5. Audit writes for trading-critical V2 actions must compose with the existing audit authority and fail closed.
6. V2 Clock/Seed/Id injection must not break existing canonical fingerprints without a reviewed golden update.
7. Legacy `sentinelx-*` schema identity strings may remain internal historical identifiers; visible-product renaming is not a reason for schema rewrites.

## Freeze change control

A change to a frozen V1 meaning requires:

1. a named V2 requirement and ADR;
2. compatibility/migration impact;
3. RED→GREEN tests for changed behavior;
4. golden-regression review;
5. explicit evidence that READ_ONLY/DISARMED safety is not weakened.
