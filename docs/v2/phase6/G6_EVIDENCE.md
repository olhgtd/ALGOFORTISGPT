# AlgoFortis V2 — G6 Multi-Broker Read-Only Evidence

**Status:** NOT QUALIFIED  
**Evidence date:** 2026-09-27  
**Phase:** Phase 6 — Multi-Broker Live Connectivity V2 (READ_ONLY / DISARMED)  
**Implementation branch:** `v2-phase6-multibroker-transport-impl`  
**Implementation PR:** `#20` (OPEN / DRAFT / stacked on `v2-phase6-live-readonly-impl`)  
**Current implementation head before this evidence-only commit:** `994344faf303438a579bd89f1fa8f6356852e87a`

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
- explicit four-broker auth-expiry regression proving `AUTH_EXPIRED` invalidates the active wire and requires an explicit reconnect/re-auth path before a new generation becomes healthy;
- legacy Upstox V3 listener/normalization facade migrated so transport generation/reconnect/subscription lifecycle delegates to the shared runtime instead of maintaining a second lifecycle authority;
- Phase-5 `FailureIncident`/alert vocabulary preserved for broker-truth and foreign-activity incidents;
- structural mutation firewall `build/tools/check_phase6_live_readonly.py`;
- deterministic G6 v2 evidence/probe;
- dual-Windows G6 workflow with exact evidence comparison.

The bullets above describe implementation surfaces present in source. They are **not** a current-head PASS claim until the required executable verification runs complete.

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

## Hosted qualification attempts observed

### Run 36321847283 — target head `636a8b1ff39977b03f51bc4c3a00cbb13064f4d1`

Workflow: `V2 Phase 6 Multi-Broker Read-Only Qualification`  
Run number: `2`  
Conclusion: `failure`

Jobs observed:

- `108627075856` — `G6 Windows 2022 / Python 3.13.14` — `failure` — `steps=null`;
- `108627075954` — `G6 Windows latest / Python 3.13.14` — `failure` — `steps=null`;
- `108627081675` — `G6 cross-Windows deterministic fingerprint comparison` — `skipped`.

Interpretation:

- both Windows jobs failed **before any job steps were exposed/executed**;
- therefore this run is **not code RED evidence** and **not code GREEN evidence**;
- no test/static/probe result can be inferred from this run;
- the compare job produced no deterministic cross-Windows qualification evidence.

### Current head `994344faf303438a579bd89f1fa8f6356852e87a`

This head adds the explicit common auth-expiry conformance regression after the hosted attempt above.

Observed verification state at evidence update:

- PR #20 head points to `994344faf303438a579bd89f1fa8f6356852e87a`;
- no pull-request workflow run was returned for this exact head;
- combined commit-status API returned `statuses: []`;
- therefore the previous run on `636a8b1...` is stale relative to the current implementation head and cannot qualify it.

## Earlier focused development evidence

Earlier focused development produced isolated RED/GREEN evidence for the Data-V2 sequence/generation bridge and transport-health-to-existing-RiskGate handoff. That evidence does **not** prove the current full branch, four-broker conformance suite, full repository regression, or hosted G6 qualification.

The broadened conformance/workflow/static changes in the current branch still require fresh execution before any full PASS claim.

## Manual requirements-vs-source review at current head

Source/diff inspection confirms the intended architecture is represented as follows, without treating inspection as executable verification:

- `BrokerPortV2` remains outside the market-data transport package and was not replaced by the multi-broker transport work;
- `MarketDataTransportRuntime` imports transport contracts/policy only and exposes no Live-arm or broker-order mutation surface;
- transport drivers remain provider-edge translation/auth/connection seams and the shared runtime owns generic reconnect/subscription/generation behavior;
- static firewall scope includes `engine/data/transports/**` and rejects RiskGate/Phase-5-state direct imports plus mutation entrypoints/imports;
- the canonical G6 workflow includes both Windows legs, the common four-broker conformance suite, Data-V2/RiskGate handoff regressions, mutation firewall, deterministic probe, and a compare job;
- no automatic cross-broker execution failover is introduced by the reviewed diff;
- Live remains `READ_ONLY / DISARMED` in workflow and evidence markers.

This is a manual architecture review only. It does not substitute for pytest/static/probe execution.

## Evidence still required before G6 can be QUALIFIED

G6 remains `NOT QUALIFIED` until all of the following are evidenced on the exact reviewed head:

1. Hosted/approved `windows-latest` and `windows-2022` jobs actually provision and execute the canonical focused/static qualification.
2. Both Windows legs produce byte-identical G6 v2 evidence and the compare job passes.
3. The common four-broker conformance suite passes on that exact head, including explicit auth-expiry handling.
4. The single-Upstox-lifecycle-authority guard passes, proving the legacy Upstox facade cannot restore a second reconnect/generation authority.
5. Full repository regression/golden and stacked G4/G5/GP-S2 preservation gates execute successfully according to the project qualification plan.
6. S2 dependency is qualified as required by the canonical phase plan.
7. Any real broker evidence used for qualification is observation-only/read-only, redacted, authorized, and does not perform broker mutation.
8. Disconnect/reconnect, auth-expiry, heartbeat/staleness, sequence-capability, queue-overflow, and stale-generation evidence is archived without real-money mutation.
9. Foreign-activity evidence is shown flowing through `LiveBrokerReconciler` into the shared incident/alert path.
10. Exact workflow/run IDs, artifact fingerprints, dated external-rule review where applicable, and unresolved limitations are archived.

## Explicit blockers at this evidence snapshot

- current implementation head has no completed executable G6 qualification run;
- the last hosted attempt failed pre-step on both Windows legs and is stale relative to the current implementation head;
- no completed cross-Windows G6 v2 compare is recorded for the current implementation head;
- current-head focused conformance/static/probe execution has not been observed through the available hosted runner evidence;
- full repository regression is not inferred from earlier focused development evidence;
- no broker mutation test or real-money order is required or authorized for G6 read-only qualification.

**Result: G6 = NOT QUALIFIED. Live = READ_ONLY / DISARMED.**
