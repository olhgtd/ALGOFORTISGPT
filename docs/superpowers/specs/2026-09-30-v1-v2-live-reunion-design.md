# AlgoFortis V1 → V2 Live Reunion Design

**Date:** 2026-09-30  
**Status:** DESIGN — Owner review required before implementation planning  
**Target implementation branch:** `live-v1-v2-reunion-20260930`  
**Design commit branch:** `riskgate-v2-fast-path-implementation-20260930`  
**Base head before this design:** `e30df7ed4b87e8063b6445a69779bb4b1adb94ea`  
**Live safety state during this work:** `READ_ONLY / DISARMED`

## 1. Purpose

Permanently align reusable, previously verified V1 Live/recovery behavior with the current V2 architecture so future work does not repeatedly re-audit the V1 donor material. This is a reunion, not a rewrite and not a second Live stack.

Canonical authority chain:

`Strategy/AI advisory → Trade Intent → RiskGateV2 → ApprovedOrder → Live execution boundary → BrokerPortV2 → broker adapter → broker truth → LiveBrokerReconciler → protection/portfolio/audit`

No V1 module, dashboard, AI component, persistence component, alert component, or strategy may become an alternate broker-mutation authority.

## 2. Success criteria

1. A permanent V1→V2 Live salvage registry exists in the repo.
2. Every reusable V1 Live capability has exactly one V2 owner.
3. `REFERENCE_ONLY` V1 components cannot become runtime authority.
4. `RiskGateV2` remains the sole executable-order approval authority.
5. Live execution accepts only a genuine `ApprovedOrder` from the canonical RiskGate path.
6. Paper and Backtest remain unable to reach real-broker mutation.
7. Idempotency, broker-order mapping, stale/duplicate suppression, `IN_DOUBT` recovery, reconciliation, restart recovery, foreign activity, local Live exclusivity, protective-order policy, and kill-switch semantics live behind V2 contracts.
8. Restart/reconnect/recovery never auto-arms Live.
9. Reunion development and qualification keep real broker mutation unreachable and Live `READ_ONLY / DISARMED`.
10. A later separately reviewed release gate can enable a controlled pilot without redesigning the authority graph.

## 3. Binding constraints

- Product name is AlgoFortis; SentinelX is legacy/history only.
- V2 architecture is authoritative; V1 contributes behavior, tests, and selected bounded helpers only.
- No big-bang legacy merge.
- No duplicate RiskGate, Live coordinator, reconnect authority, broker lifecycle authority, or recovery authority.
- Cloud/account services never become trading authority and never hold broker secrets.
- Broker credentials/trading state/orders/execution ledgers remain local.
- AI/Laya is advisory and cannot call broker mutation directly.
- Options current scope remains BUY-only through RiskGate enforcement.
- Foreign broker activity fails closed.
- Reconnect, clean reconciliation, restart, watchdog restart, state restoration, or successful alerts never imply arm permission.
- Missing/corrupt safety state, policy, broker truth, or required protection fails closed.
- Do not invent production thresholds merely to satisfy tests.

## 4. Architecture decision

### Selected: V1 behavior salvage behind V2 contracts

Rejected:

- Direct V1 file merge: risks legacy monoliths and duplicate authorities.
- Fresh Live rewrite: wastes verified behavior and regression knowledge.

Selected method:

- preserve V2 authority boundaries;
- turn V1 behavior into V2-owned contracts/services/tests;
- copy implementation only when bounded, compatible, and non-authoritative;
- otherwise re-express behavior with minimal V2-compatible code;
- salvage tests/evidence before implementation when ambiguous.

## 5. Canonical authority graph

```text
Market/Data V2
      ↓
Strategy / AI-Laya advisory
      ↓
Trade Intent
      ↓
RiskGateV2
      ↓
ApprovedOrder
      ↓
LiveExecutionCoordinatorV2
      ↓
Idempotency + Order Lifecycle
      ↓
BoundBrokerPort / BrokerPortV2
      ↓
RealBrokerAdapterV2
      ↓
Broker
      ↓
Broker truth: orders / fills / positions / funds
      ↓
LiveBrokerReconciler
      ↓
Protection + Portfolio + Audit + Alerts
```

Sole authorities:

| Concern | Sole V2 authority |
|---|---|
| Executable-order approval | `RiskGateV2` |
| Run-mode/broker mutation boundary | `BrokerPortV2` / `BoundBrokerPort` |
| Live state transitions / arm latch | V2 Live state machine |
| Broker truth after uncertainty/restart | `LiveBrokerReconciler` |
| Market-data reconnect/generation | existing Phase-6 transport runtime |
| Kill-switch semantics | existing V2 risk kill-switch |
| Trading-critical audit | V2 audit path |

## 6. Permanent salvage registry

Implementation must create `docs/v2/live/V1_V2_LIVE_REUNION_MANIFEST.md`.

Each donor item receives exactly one status:

- `SALVAGED`
- `REFERENCE_ONLY`
- `REPLACED_BY_V2`
- `DEFERRED`

Each row records V1 capability/module, verified historical behavior, classification, canonical V2 owner, migration method (`wrap`, `port`, `test-only`, `retire`), required regression tests, safety notes, and final implementation commit.

This manifest becomes the default future reference. Re-audit the donor only when a capability is absent from the manifest or new evidence contradicts it.

## 7. Initial V1 → V2 mapping

| V1 behavior / donor area | Classification | Canonical V2 destination |
|---|---|---|
| Idempotency ledger / replay protection | SALVAGE behavior | Live lifecycle/idempotency service |
| Broker order records / lifecycle worklist | SALVAGE behavior | V2 order lifecycle + broker mapping |
| Stale/duplicate suppression | SALVAGE behavior | RiskGate/intake + lifecycle |
| Live workspace persistence | SALVAGE selectively | V2 persistence/read model, never recovery authority |
| Restart/recovery scenarios | SALVAGE behavior/tests | `LiveBrokerReconciler` + Live state machine |
| Open-position/protection restoration | SALVAGE behavior/tests | reconciler + protective subsystem |
| Projection dedup by client order ID | SALVAGE behavior/tests | V2 portfolio/order projection |
| Legacy broker read-side knowledge | SALVAGE tests/edge cases | Phase-6 broker/transport contracts |
| Legacy direct mutation adapters | REFERENCE_ONLY | never promote directly |
| Legacy monolithic paper/live coordinator | REFERENCE_ONLY | V2 focused modules |
| Legacy entry pipeline | REFERENCE_ONLY | V2 intent → RiskGate flow |
| Legacy risk manager authority | REFERENCE_ONLY | `RiskGateV2` |
| Legacy protective live monolith | REFERENCE_ONLY unless bounded helper proven safe | V2 protective contracts/services |
| Legacy UI Live readiness/workspace | SALVAGE presentation behavior | dashboard clients of V2 read models only |

Implementation must refine this table to exact file/function mappings before changing runtime behavior.

## 8. Live execution coordinator boundary

A focused `LiveExecutionCoordinatorV2` (final name follows repo conventions) is the only orchestration seam between `ApprovedOrder` and `BrokerPortV2` mutation.

Responsibilities:

1. Require `RunMode.LIVE` and genuine `ApprovedOrder`.
2. Check Live eligibility; reunion itself keeps release/arm gate disabled.
3. Derive/use stable client order identity.
4. Check persistent idempotency before submission.
5. Update lifecycle before/after broker calls.
6. Handle send/no-ack as `IN_DOUBT`.
7. Never blindly retry `IN_DOUBT`; reconciliation resolves it.
8. Persist broker-order mapping on acknowledgement.
9. Feed fills/status into canonical lifecycle/projection/audit.
10. Never own RiskGate policy or mint `ApprovedOrder`.

Keep the coordinator small. Reconciliation, protection, persistence, and broker-specific translation remain separate.

## 9. Idempotency and lifecycle

Required properties:

- stable client order ID per canonical intent/order identity;
- duplicate submission blocked before broker mutation;
- stale intent blocked;
- persisted broker-order-ID mapping;
- formal lifecycle including `IN_DOUBT`;
- partial fill/fill/rejection/cancellation/expiry/divergence explicit;
- restart loads durable evidence but never treats persistence as broker truth;
- unresolved ambiguity routes to reconciliation;
- no blind retry after timeout/unknown acknowledgement.

## 10. Reconciliation and recovery

`LiveBrokerReconciler` remains broker-truth authority on startup, reconnect, and uncertainty.

Flow:

1. Live remains in non-entry recovery/degraded/paused state.
2. Restore local durable state.
3. Query broker funds/orders/positions and uncertain orders as required.
4. Reconcile in-flight and `IN_DOUBT` records.
5. Detect broker-only/foreign orders and positions.
6. Restore/verify protection.
7. Verify feed, clock, session/expiry, and risk prerequisites.
8. Produce recovery evidence.
9. Any uncertainty/mismatch remains fail-closed.
10. Clean recovery reaches ready-for-manual-resume only; never auto-arm.

Persistence provides remembered state, not broker truth.

## 11. Foreign activity policy

Binding behavior:

- unattributable broker order/position → halt new entries for that account;
- incident + alert + audit evidence;
- never ignore;
- never auto-adopt;
- manual adoption, if supported later, is separate and audited;
- foreign activity never implies automatic `FLATTEN_ALL`.

Use reconciliation + existing incident/alert vocabulary; no second foreign-activity engine.

## 12. Multi-device Live exclusivity

Use the Owner-frozen local hard backstop:

- at most one local armed execution owner for a broker account;
- local durable ownership evidence fails closed on conflict/uncertainty;
- broker-truth reconciliation detects competing/foreign activity and halts entries;
- cloud may later provide advisory visibility but never trading authority;
- cloud outage cannot weaken local safety;
- restart never silently restores armed ownership.

Process single-instance locking may be reused but alone is not sufficient broker-account exclusivity.

## 13. Broker-resident protection

- Where selected broker supports required protection, it must rest at broker before Live eligibility.
- If required protection is unsupported, that path stays `DISARMED` unless a separately approved degraded policy exists.
- Local protection may supplement but not replace required broker-resident protection.
- Reconnect/recovery verifies protection against broker truth.
- Capabilities/policy are adapter/versioned-policy concerns, not global hard-coded assumptions.

## 14. Broker adapters

### Read side

Keep existing Phase-6 broker-neutral transport/read-only architecture and its shared reconnect/generation authority.

### Mutation side

Do not directly promote the legacy Angel adapter.

The first mutation-capable adapter must:

- implement the V2 broker contract;
- accept only canonical V2 orders/capabilities;
- expose capability discovery;
- handle current token/session/reconnect/rate-limit semantics;
- keep broker-specific translation at the edge;
- return sufficient acknowledgement for lifecycle/reconciliation;
- implement broker-resident protection where supported;
- consume current versioned broker/exchange policy;
- never mint RiskGate approval or arm Live.

Multi-broker market data does not imply multi-broker mutation. Prove one broker mutation path completely before expanding.

## 15. Kill switch

Existing semantics remain authoritative:

- `HALT_ENTRIES`
- `CANCEL_PENDING`
- `FLATTEN_ALL` as separate explicit action

Standard Emergency Stop remains `HALT_ENTRIES + CANCEL_PENDING`; protective exits and reconciliation continue. Reconciliation mismatch, foreign activity, reconnect uncertainty, or audit failure must not silently invoke `FLATTEN_ALL`.

## 16. Audit and persistence

Every trading-critical mutation decision must record enough evidence to identify intent/order identity, RiskGate approval, client order ID, idempotency result, broker path, lifecycle state before/after, broker acknowledgement, reconciliation result, Live state/safety overlays, and policy versions.

If mandatory audit persistence fails, trading-critical mutation fails closed under existing policy.

## 17. Static architecture guards

Add/extend permanent guards that fail if:

1. reference-only V1 runtime authority is imported into canonical Live mutation without explicit allowlist;
2. strategy, AI, dashboard, alerting, reporting, persistence, or Paper directly imports broker mutation authority;
3. anything outside RiskGate bypasses executable approval capability;
4. Paper/Backtest binds real mutation adapters or credentials;
5. a second reconnect/generation authority appears;
6. persistence becomes recovery-decision authority;
7. restart/reconnect code auto-arms;
8. a legacy direct mutation adapter becomes production-reachable.

## 18. Test design

Implementation follows TDD. Convert V1 regression knowledge into V2 tests before porting behavior where practical.

Focused invariants must cover:

- genuine `ApprovedOrder` required;
- forged/wrong-mode/expired capability rejected;
- duplicate canonical intent cannot cause duplicate mutation;
- stale intent rejected;
- send/no-ack → `IN_DOUBT`;
- `IN_DOUBT` queried/reconciled, never blindly retried;
- broker acknowledgement mapping persisted once;
- partial fill + disconnect converges to broker truth;
- restart with open position reconciles before entries;
- restart/reconnect never auto-arms;
- foreign activity halts + alerts, no auto-adopt;
- second-device/local-owner conflict fails closed;
- missing required broker protection keeps path ineligible/disarmed;
- Emergency Stop semantics preserved;
- `FLATTEN_ALL` remains explicit;
- audit failure blocks mutation;
- Paper/Backtest cannot reach real mutation;
- AI/Laya/dashboard cannot bypass RiskGate.

Regression preservation includes relevant Phase 2/3/5/6, S2, RiskGate fast-path, and final full `tests_v1` on exact head.

Dual-Windows qualification must execute on Windows latest + Windows 2022 when hosted runners are available. A no-runner/zero-step startup failure is neither code GREEN nor code RED.

## 19. Expected implementation slices

1. Reunion manifest + authority guard baseline.
2. V1 behavior regression fixtures/tests.
3. V2 idempotency/lifecycle alignment.
4. Live execution coordinator contract, still mutation-disabled.
5. Reconciliation/foreign-activity reunion.
6. Local Live exclusivity backstop.
7. Broker-resident protection capability/policy seam.
8. First mutation-adapter seam behind permanent DISARMED release gate.
9. Audit/read-model/dashboard alignment.
10. Focused + full qualification and final evidence.

No slice enables real-money mutation merely because unit tests pass.

## 20. Release-gate separation

### A. Reunion implemented

V1 salvage behavior aligned behind V2 contracts; Live remains `READ_ONLY / DISARMED`.

### B. Live write path technically qualified

Mutation path exists and passes software/sandbox/read-only/failure-injection qualification, but production arming remains blocked.

### C. Controlled real-money pilot authorized

Requires separate final release decision, current broker/exchange/regulatory evidence, production environment/credentials, required protection, defect gates, qualification evidence, and explicit Owner authorization.

No implementation commit automatically advances A→B or B→C.

## 21. Two remaining top-level Live packages

### Package 1 — Live Write-Path Reunion

V1 salvage, V2 lifecycle/idempotency, coordinator, broker mutation seam, reconciliation/foreign activity, local exclusivity, protection policy, audit, and permanent guards.

### Package 2 — Live Qualification + Controlled Pilot

Final exact-head qualification, failure injection, permitted real-broker read/sandbox evidence, current rule review, protection verification, release evidence, staged pilot controls, and explicit Owner arming authorization.

These are project-management packages; Package 1 is intentionally split into small implementation slices.

## 22. Explicit non-goals

This reunion does not:

- enable real-money trading immediately;
- create automatic cross-broker execution failover;
- make all market-data brokers mutation-capable;
- restore V1 monoliths as authority;
- move secrets/execution authority to cloud;
- let AI/Laya order directly;
- redesign RiskGate authority;
- weaken READ_ONLY/DISARMED;
- invent degraded protection policy;
- replace Phase-6 reconnect authority;
- treat historical PASS evidence as current-head qualification.

## 23. Definition of done

Reunion implementation is complete only when:

- permanent manifest is complete and source-linked;
- every selected donor item is classified;
- one canonical authority path is structurally enforced;
- focused invariants pass;
- relevant regressions pass;
- full repository regression passes on final exact head;
- static guards pass;
- dual-Windows qualification executes successfully when runners are available;
- no open P0/P1 on reunited production-critical path;
- Live remains `READ_ONLY / DISARMED` unless a later pilot authorization changes that state;
- final evidence records exact SHA, results, limitations, and remaining Package-2 gates.

## 24. Review checklist

- [x] V2 RiskGate sole authority
- [x] V1 behavior reuse without V1 authority resurrection
- [x] Paper/Backtest/Live isolation
- [x] Live READ_ONLY/DISARMED during reunion
- [x] no auto-arm after restart/reconnect
- [x] foreign activity fail-closed
- [x] local Live exclusivity hard backstop
- [x] broker-resident protection requirement
- [x] distinct kill-switch semantics
- [x] AI/Laya advisory-only role
- [x] permanent manifest avoids routine donor re-audits
- [x] exact-head verification before completion claims
