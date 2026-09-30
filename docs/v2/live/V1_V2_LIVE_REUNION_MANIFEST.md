# AlgoFortis V1 -> V2 Live Reunion Manifest

**Status:** Package-1 implementation manifest  
**Authority:** `docs/superpowers/specs/2026-09-30-v1-v2-live-reunion-design.md`  
**Safety state:** Live remains `READ_ONLY / DISARMED`.

This registry is the permanent donor map for Live/recovery reunion work. A legacy component listed as `REFERENCE_ONLY` is evidence, not runtime authority. V2 contracts remain authoritative.

| V1 capability / donor | Historical behavior reused | Classification | Sole V2 owner | Migration | Required regression / safety note | Implementation commit |
|---|---|---|---|---|---|---|
| `engine/portfolio/virtual_account.py::reserve_premium` | worst-case premium commitment before submission; idempotent duplicate; insufficient cash reject | SALVAGED | V2 Live execution-capacity reservation composed before broker mutation | port behavior, not virtual-account authority | simultaneous NIFTY/BANKNIFTY/SENSEX entries must consume one shared account budget atomically; no stale-balance oversubscription | PENDING |
| `engine/risk/risk_manager.py::PendingRiskCommitment` | gate-approved but not-yet-filled entry counts against pending risk | SALVAGED | V2 execution-capacity/risk reservation | port contract semantics | pending approvals participate in account exposure until terminal release | PENDING |
| legacy idempotency/replay behavior | one canonical intent cannot create duplicate broker mutation | SALVAGED | `OrderExecutionLifecycle` + V9 Live execution journal | wrap/port tests | duplicate `client_order_id` blocked before broker call | PENDING |
| legacy broker-order records / worklist | local order-to-broker identity mapping and uncertain work | SALVAGED | V9 Live execution journal | port | persistence is evidence, never broker truth | PENDING |
| legacy stale/duplicate suppression | stale candidate and replay rejection | REPLACED_BY_V2 | `RiskGateV2` + fast-path replay guard + lifecycle | retain V2 | do not reintroduce legacy gate | existing V2 |
| legacy Live workspace persistence | restart remembers local execution evidence | SALVAGED | focused V2 persistence/read model | selective port | restart never restores armed authority | PENDING |
| legacy restart/recovery scenarios | restore local state then reconcile against broker | SALVAGED | `LiveBrokerReconciler` + V2 Live state machine | port tests | recovery reaches manual-ready only; never auto-arm | PENDING |
| legacy open-position/protection restoration | detect positions and verify protection after restart | SALVAGED | reconciler + V2 protection capability/policy | port tests | missing required protection stays DISARMED | PENDING |
| legacy projection dedup | same client order cannot double-project fills/orders | SALVAGED | V2 lifecycle/projection | port tests | client-order identity remains canonical | PENDING |
| legacy broker read-side edge cases | broker truth/status normalization knowledge | SALVAGED | Phase-6 broker-neutral read-only contracts | test-only/port bounded helpers | no mutation authority transferred | existing/PENDING |
| `engine/broker_adapters/angel_adapter.py` and other direct legacy mutation adapters | broker-specific historical behavior only | REFERENCE_ONLY | none at runtime; V2 Angel One mutation seam later | retire from canonical path | direct production import is permanently guarded | N/A |
| legacy monolithic paper/live coordinator | orchestration evidence only | REFERENCE_ONLY | focused V2 coordinator/services | retire authority | cannot become alternate Live authority | N/A |
| legacy entry pipeline | historical intent flow only | REFERENCE_ONLY | V2 intent -> `RiskGateV2` | retire authority | cannot mint `ApprovedOrder` | N/A |
| legacy risk-manager executable authority | historical risk behavior only | REFERENCE_ONLY | `RiskGateV2` | test-only salvage | RiskGateV2 remains sole executable approval authority | N/A |
| legacy protective Live monolith | historical protection behavior | REFERENCE_ONLY | V2 protection contracts/services | bounded helpers only if separately proven | no hidden cancel/modify authority | N/A |
| legacy UI Live readiness/workspace | presentation behavior | SALVAGED | dashboard read models consuming V2 evidence | presentation-only | dashboard cannot call broker mutation | PENDING |
| automatic cross-broker execution failover | not part of reunion | DEFERRED | future separately approved package | none | no fallback mutation path in Package 1 | N/A |
| production mutation transport / real-money pilot | intentionally outside Package 1 | DEFERRED | Package 2 release design | separate approval | current package cannot open mutation gate | N/A |

## Binding rules

- `RiskGateV2` is the sole executable-order approval authority.
- Shared account capital/risk reservations may only further restrict an approved order; they never mint approval.
- Independent instruments retain separate intent/order/lifecycle identities.
- Shared account budget/exposure reservation must be atomic across simultaneous instruments before broker mutation.
- Broker truth resolves uncertainty; local persistence never does.
- Foreign activity fails closed and never auto-adopts or auto-flattens.
- Restart, reconnect, clean reconciliation, and alert success never auto-arm Live.
- Paper/Backtest/AI/Laya/dashboard/reporting/persistence cannot directly reach real-broker mutation.
