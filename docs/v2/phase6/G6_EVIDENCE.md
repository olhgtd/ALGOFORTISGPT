# AlgoFortis V2 — G6 Multi-Broker Read-Only Evidence

**Status:** NOT QUALIFIED  
**Evidence date:** 2026-09-27  
**Phase:** Phase 6 — Multi-Broker Live Connectivity V2 (READ_ONLY / DISARMED)  
**Implementation branch:** `v2-phase6-multibroker-transport-impl`

## Binding interpretation

`G6 GREEN` does **not** enable real-money trading. Live remains `READ_ONLY / DISARMED` unless a later separately designed, reviewed, qualified, and explicitly authorized release gate changes that state.

This record contains no credentials, access tokens, account identifiers, or broker-mutation authorization.

## Revised scope

Phase 6 is no longer an Angel-One-only boundary. The reviewed architecture supports a common read-only market-data transport spine for:

- Angel One;
- Zerodha;
- Dhan;
- Upstox;
- a fifth broker extension slot that must satisfy the same conformance contract before being declared supported.

Execution/account authority remains separate under `BrokerPortV2`. Market-data transport cannot mint `ApprovedOrder`, arm Live, mutate broker state, or automatically fail over execution between brokers.

## Implemented evidence surfaces

The implementation branch contains:

- existing isolated Angel One V2 read-only account/broker boundary preserved;
- broker-neutral transport contracts under `engine/data/transports/`;
- explicit source-sequence semantics (`STRICT_CONTIGUOUS`, `MONOTONIC_ONLY`, `UNAVAILABLE`) with no fabricated provider continuity;
- shared `MarketDataTransportRuntime` owning connect/disconnect/reconnect, bounded backoff, subscription replay, generation fencing, heartbeat evidence, and bounded receive buffering;
- thin provider drivers for Angel One, Zerodha, Dhan, and Upstox;
- provider registry/extension seam that does not require core-runtime changes for the next broker;
- Data-V2 bridge using `(connection_generation, instrument_token)` as the per-instrument continuity key;
- transport `DEGRADED` / `FAILED_CLOSED` feeding the existing Data-V2 `FeedMonitor -> EntryPolicy -> RiskGateV2` DAT-005/008 block rather than creating a second authority path;
- `HEALTHY` transport state unable to override stale/gap/clock-skew/market/risk/reconciliation blocks;
- queue overflow and stale-generation rejection fail-closed behavior;
- common deterministic four-broker conformance tests;
- legacy Upstox V3 listener/normalization facade migrated so transport generation/reconnect/subscription lifecycle delegates to the shared runtime instead of maintaining a second lifecycle authority;
- Phase-5 `FailureIncident`/alert vocabulary preserved for broker-truth and foreign-activity incidents;
- structural mutation firewall `build/tools/check_phase6_live_readonly.py`;
- deterministic G6 v2 evidence/probe;
- dual-Windows G6 workflow with exact evidence comparison.

## Deterministic G6 v2 markers

The qualification probe requires the following architecture/safety facts:

- `BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY`
- `BROKER_SCOPE=ANGELONE,ZERODHA,DHAN,UPSTOX`
- `CROSS_BROKER_FAILOVER=DISABLED`
- `FEED_HEALTH_HANDOFF=DATA_V2_FEED_MONITOR`
- `FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED`
- `G6_ENABLES_REAL_MONEY_TRADING=NO`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `MARKET_DATA_TRANSPORT=SHARED_RUNTIME_THIN_DRIVERS`
- `QUEUE_OVERFLOW=FAIL_CLOSED`
- `REAL_BROKER_MUTATION_CAPABILITY=ABSENT`
- `RECONCILIATION_AUTHORITY=LIVE_RECONCILER`
- `RISK_GATE_FEED_BLOCK=DAT_005_008_EXISTING_PATH`
- `SEQUENCE_KEY=CONNECTION_GENERATION+INSTRUMENT_TOKEN`
- `SOURCE_SEQUENCE=EXPLICIT_SEMANTICS_NO_FABRICATION`
- `STALE_GENERATION=REJECTED`
- `TRANSPORT_HEALTH=LOWER_LEVEL_ONLY`

## Verification already available

Earlier focused development provided isolated RED/GREEN evidence for the Data-V2 sequence/generation bridge and transport-health-to-existing-RiskGate handoff. That evidence does **not** prove the current full branch, four-broker conformance suite, full repository regression, or hosted G6 qualification.

The broadened conformance/workflow/static changes in the current branch must be executed afresh before any PASS claim.

## Evidence still required before G6 can be QUALIFIED

G6 remains `NOT QUALIFIED` until all of the following are evidenced on the exact reviewed head:

1. Hosted/approved `windows-latest` and `windows-2022` jobs actually provision and execute the canonical focused/static qualification.
2. Both Windows legs produce byte-identical G6 v2 evidence and the compare job passes.
3. The common four-broker conformance suite passes on that exact head.
4. The single-Upstox-lifecycle-authority guard passes, proving the legacy Upstox facade cannot restore a second reconnect/generation authority.
5. Full repository regression/golden and stacked G4/G5/GP-S2 preservation gates execute successfully according to the project qualification plan.
6. S2 dependency is qualified as required by the canonical phase plan.
7. Any real broker evidence used for qualification is observation-only/read-only, redacted, authorized, and does not perform broker mutation.
8. Disconnect/reconnect, auth-expiry, heartbeat/staleness, sequence-capability, queue-overflow, and stale-generation evidence is archived without real-money mutation.
9. Foreign-activity evidence is shown flowing through `LiveBrokerReconciler` into the shared incident/alert path.
10. Exact workflow/run IDs, artifact fingerprints, dated external-rule review where applicable, and unresolved limitations are archived.

## Explicit blockers at this evidence snapshot

- The broadened current-head multi-broker test suite has not yet been proven by a completed hosted dual-Windows G6 run.
- No completed cross-Windows G6 v2 compare is recorded for the current branch head.
- Full repository regression is not inferred from focused development evidence.
- No broker mutation test or real-money order is required or authorized for G6 read-only qualification.

**Result: G6 = NOT QUALIFIED. Live = READ_ONLY / DISARMED.**
