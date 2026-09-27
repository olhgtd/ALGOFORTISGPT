# Phase 6 Multi-Broker Transport Implementation Plan

> **For implementer:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Broaden the existing Phase-6 Angel One read-only implementation into a broker-neutral multi-broker market-data transport architecture for Angel One, Zerodha, Dhan, and Upstox while preserving every existing read-only/live-safety invariant. Live remains `READ_ONLY / DISARMED`; no real broker mutation is added.

**Architecture:** Preserve the existing Angel One read-only account/execution boundary and Phase-6 reconciliation/incident/safety work. Add a new sibling market-data transport spine under Data V2: one shared `MarketDataTransportRuntime`, thin broker-specific drivers, one centralized provider-envelope/market-event bridge, and the existing Data-V2 `FeedMonitor` / RiskGate EntryPolicy authority path. Provider sequence semantics are explicit and per-instrument. The transport layer supplies evidence; it never becomes a second RiskGate or Paper/Live operational-state authority.

**Tech Stack:** Python 3.13.14, dataclasses/enums/Protocols, existing AlgoFortis `Clock`/Data-V2/RiskGate primitives, pytest, source-level static guards, deterministic fake/injected transport clients and sanitized fixtures, GitHub Actions dual-Windows evidence workflow. No live credentials or real-money broker mutation are required for implementation or qualification tests.

---

## Baseline and branch rules

- Approved written spec: `docs/superpowers/specs/2026-09-27-phase6-multi-broker-transport-design.md`.
- Approved design commit: `d481b48ab838dc6b4eb9a0a84f564daacef2f4ca`.
- Existing Angel-only implementation branch: `v2-phase6-live-readonly-impl`.
- Exact existing implementation head at plan authoring: `9efad00f7fcc4e25b7115b70f881ec3505f4cd93`.
- The existing Angel-only implementation is valuable tested/read-only work and must be preserved, not rewritten from scratch.
- Implementation must use a new branch, recommended: `v2-phase6-multibroker-transport-impl`, created from exact old implementation head `9efad00f7fcc4e25b7115b70f881ec3505f4cd93`.
- Do not mutate `v2-phase6-live-readonly-impl` or `v2-phase6-live-readonly-design` during implementation.
- Carry the approved multi-broker spec and this plan onto the new implementation branch as documentation-only commits before runtime edits.
- Existing Angel One read-only account/reconciliation/safety modules remain the baseline unless a task below explicitly requires a narrow additive compatibility change.
- Hosted GitHub Actions availability is currently unreliable/quota-constrained. Pre-step runner failure is neither code GREEN nor code RED. G6 remains **NOT QUALIFIED** until the exact reviewed head gets real hosted qualification evidence.
- Every implementation task follows RED -> minimal GREEN -> focused regression -> commit.
- Do not combine unrelated tasks into one commit.

---

## Task 0 — Create the safe implementation branch and preserve the old Phase-6 baseline

**Files:**
- Add/carry: `docs/superpowers/specs/2026-09-27-phase6-multi-broker-transport-design.md`
- Add/carry: `docs/superpowers/plans/2026-09-27-phase6-multi-broker-transport-implementation.md`
- No runtime file changes in this task.

**Step 1: Create the implementation branch**

Create `v2-phase6-multibroker-transport-impl` from exact head:

```text
9efad00f7fcc4e25b7115b70f881ec3505f4cd93
```

**Step 2: Carry only the approved spec and plan**

Add the approved spec and this plan without changing runtime/workflow/test code.

**Step 3: Verify baseline diff**

Expected: branch differs from the old implementation head only by the approved documentation files.

**Step 4: Re-run the existing Phase-6 focused baseline before transport edits**

```powershell
python -m pytest tests_v1/test_phase6_*.py -q
python build/tools/check_phase6_live_readonly.py
python build/tools/phase6_probe.py
```

Record exact output. If the current environment cannot run it, record the limitation and do not call the baseline GREEN.

**Step 5: Commit**

```text
docs: carry approved phase6 multi-broker design and plan
```

---

## Task 1 — Add broker-neutral transport contracts and extend the static authority firewall

**Files:**
- Create: `engine/data/transports/__init__.py`
- Create: `engine/data/transports/contracts.py`
- Create: `engine/data/transports/sequence.py`
- Create: `engine/data/transports/policy.py`
- Create: `tests_v1/test_phase6_transport_contracts.py`
- Create: `tests_v1/test_phase6_transport_policy.py`
- Modify: `build/tools/check_phase6_live_readonly.py`
- Modify: `tests_v1/test_phase6_architecture_guard.py`

**Step 1: Write failing contract tests**

Require immutable/validated contracts for at least:

- `BrokerTransportDriver` protocol;
- `TransportCapabilities`;
- `TransportConnection` / connection identity;
- `ProviderEnvelope`;
- `TransportHealthState` with `STOPPED`, `CONNECTING`, `AUTHORIZING`, `CONNECTED`, `SUBSCRIBING`, `HEALTHY`, `DEGRADED`, `RECONNECTING`, `FAILED_CLOSED`;
- `HeartbeatMode`;
- `SubscriptionRequest`;
- `SourceSequence`, sequence semantics, and sequence scope;
- versioned `BrokerTransportPolicy`.

Tests must fail when policy identity/version is missing or required policy fields are invalid.

**Step 2: Write failing architecture-guard fixtures**

The static guard must reject a synthetic transport/driver file that:

- imports or constructs `ApprovedOrder`;
- imports broker mutation/order-submission code;
- exposes callable production mutation entrypoints such as `place`, `submit`, `modify`, `cancel`, GTT mutation, or equivalent;
- sets or reaches Live auto-arm authority;
- directly mutates RiskGate or the Phase-5 operational state machine.

A `READ_ONLY=True` or `DISARMED=True` flag must not make unsafe code pass.

**Step 3: Run RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_contracts.py tests_v1/test_phase6_transport_policy.py tests_v1/test_phase6_architecture_guard.py -q
```

Expected: new tests fail for missing transport contracts/guard rules.

**Step 4: Implement minimal contracts and guard rules**

Keep `engine/broker_contract/port_v2.py` unchanged. The market-data transport contract is a sibling Data-V2 boundary, not an extension of execution authority.

**Step 5: Run GREEN + static guard**

```powershell
python -m pytest tests_v1/test_phase6_transport_contracts.py tests_v1/test_phase6_transport_policy.py tests_v1/test_phase6_architecture_guard.py -q
python build/tools/check_phase6_live_readonly.py
```

**Step 6: Commit**

```text
feat: add phase6 broker-neutral transport contracts
```

---

## Task 2 — Implement the shared transport runtime, generation fencing, and bounded backpressure

**Files:**
- Create: `engine/data/transports/runtime.py`
- Create: `tests_v1/test_phase6_transport_runtime.py`
- Create: `tests_v1/test_phase6_transport_backpressure.py`
- Modify only if required: `engine/data/transports/contracts.py`

**Step 1: Write failing lifecycle tests**

Cover:

- deterministic initial `STOPPED` state;
- connect lifecycle through `CONNECTING` / `AUTHORIZING` / `CONNECTED`;
- generation increment on accepted replacement connection;
- delayed callback from an old generation is rejected before normalization;
- unexpected disconnect enters `RECONNECTING`;
- bounded reconnect attempts/backoff are policy-driven;
- retry exhaustion ends in `FAILED_CLOSED`;
- reconnect success does not arm Live or restore entry permission by itself.

Use injected fake wire/client factories and injected clock/sleeper where needed. Do not open real broker sockets.

**Step 2: Write failing bounded-queue tests**

Require a bounded receive queue/ring buffer. Overflow must:

- produce explicit health/audit evidence;
- move transport to `DEGRADED` or `FAILED_CLOSED` per versioned policy;
- never silently drop data and continue `HEALTHY`.

**Step 3: Run RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_runtime.py tests_v1/test_phase6_transport_backpressure.py -q
```

**Step 4: Implement minimal shared runtime**

The runtime owns lifecycle/reconnect/generation/backpressure. Broker drivers must not reimplement the generic reconnect state machine.

**Step 5: Run GREEN**

```powershell
python -m pytest tests_v1/test_phase6_transport_runtime.py tests_v1/test_phase6_transport_backpressure.py -q
python build/tools/check_phase6_live_readonly.py
```

**Step 6: Commit**

```text
feat: add shared phase6 market-data transport runtime
```

---

## Task 3 — Add broker-neutral subscription replay and heartbeat semantics

**Files:**
- Create if separation is cleaner: `engine/data/transports/subscriptions.py`
- Modify: `engine/data/transports/runtime.py`
- Modify: `engine/data/transports/contracts.py`
- Inspect/reuse where compatible, do not blindly rewrite: `engine/data/feeds/subscription.py`
- Create: `tests_v1/test_phase6_transport_subscriptions.py`
- Create: `tests_v1/test_phase6_transport_heartbeat.py`

**Step 1: Write failing subscription tests**

Require:

- desired subscription set is broker-neutral;
- active/acknowledged subscription set is generation-scoped;
- partial/ambiguous acknowledgement cannot become `HEALTHY`;
- reconnect replays desired subscriptions exactly once for the new generation;
- unsubscribe removes the desired subscription deterministically;
- stale-generation acknowledgements are ignored.

**Step 2: Write failing heartbeat tests**

Require explicit modes:

- `PROTOCOL_PING_PONG`;
- `PROVIDER_HEARTBEAT_FRAME`;
- `DATA_ACTIVITY`;
- `NONE`.

Track separately where applicable:

- `last_frame_at`;
- `last_data_at`;
- `last_protocol_heartbeat_at`.

A market-data tick must not automatically count as protocol heartbeat unless the broker capability explicitly says `DATA_ACTIVITY`.

**Step 3: RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_subscriptions.py tests_v1/test_phase6_transport_heartbeat.py -q
```

**Step 4: Implement minimal shared behavior**

No broker-specific reconnect/heartbeat state machine may be added here.

**Step 5: GREEN**

```powershell
python -m pytest tests_v1/test_phase6_transport_subscriptions.py tests_v1/test_phase6_transport_heartbeat.py -q
```

**Step 6: Commit**

```text
feat: add shared subscription and heartbeat lifecycle
```

---

## Task 4 — Migrate Data-V2 events and FeedMonitor to explicit source sequence + per-instrument tracking

**Files:**
- Modify: `engine/data/live_feed.py`
- Modify: `engine/data/feed_monitor.py`
- Create: `engine/data/transports/bridge.py`
- Create: `tests_v1/test_phase6_market_event_bridge.py`
- Create: `tests_v1/test_phase6_feed_monitor_multi_instrument.py`
- Modify relevant existing Data-V2 tests, including current live-feed tests, only as needed for compatibility.

**Step 1: Write failing event-migration tests**

Require canonical separation of:

```text
ingress_sequence   # AlgoFortis internal deterministic ordering
source_sequence    # provider-origin sequence + semantics
```

The existing single `LiveMarketEvent.sequence` may remain temporarily as an explicitly deprecated compatibility field, but it must not remain authoritative provider-gap evidence.

**Step 2: Write failing per-instrument sequence tests**

The monitor key is exactly:

```text
(connection_generation, instrument_token)
```

Required cases:

- NIFTY strict sequence `100,101,103` latches a NIFTY gap;
- simultaneous BANKNIFTY `501,502,503` remains independently healthy;
- BANKNIFTY traffic cannot clear/mask NIFTY gap;
- a new connection generation starts a new generation-scoped sequence history;
- old-generation observations are rejected upstream and cannot update current monitor state;
- `MONOTONIC_ONLY` catches regression/out-of-order but does not infer numeric missing packets;
- `UNAVAILABLE` never fabricates provider continuity from `ingress_sequence`.

**Step 3: Write failing per-instrument staleness tests**

A required instrument that stops receiving valid observations becomes stale even when another instrument continues producing traffic.

**Step 4: Keep clock-skew behavior**

Existing exchange-vs-receive timestamp skew checks must remain fail-closed per required instrument context.

**Step 5: RED**

```powershell
python -m pytest tests_v1/test_phase6_market_event_bridge.py tests_v1/test_phase6_feed_monitor_multi_instrument.py -q
```

**Step 6: Implement minimal migration**

Target monitor seam must carry equivalent information to:

```python
def observe(
    self,
    event: LiveMarketEvent,
    *,
    connection_generation: int,
    instrument_token: str,
    source_sequence: SourceSequence | None,
) -> None:
    ...
```

An equivalent typed envelope is acceptable only if the tuple key and source-sequence semantics remain explicit.

**Step 7: GREEN + Data-V2 regression**

```powershell
python -m pytest tests_v1/test_phase6_market_event_bridge.py tests_v1/test_phase6_feed_monitor_multi_instrument.py -q
python -m pytest tests_v1 -k "live_feed or feed_monitor" -q
```

**Step 8: Commit**

```text
feat: make data-v2 feed health per instrument and source-sequence aware
```

---

## Task 5 — Prove the existing DAT-005/008 RiskGate handoff; do not add a second authority

**Files:**
- Create: `tests_v1/test_phase6_feed_riskgate_handoff.py`
- Modify only if compatibility requires: existing Data-V2/RiskGate tests
- Do not add a new RiskGate authority module.

**Step 1: Write failing integration tests**

Prove the exact existing authority path:

```text
TransportHealthSnapshot / market-event integrity
        -> Data-V2 FeedMonitor
        -> existing entries_allowed / EntryPolicy seam
        -> RiskGateV2
        -> new entry blocked
```

Required cases:

- transport `DEGRADED` maps through Data-V2 and blocks new-entry eligibility;
- transport `FAILED_CLOSED` maps through the same path and blocks new-entry eligibility;
- transport `HEALTHY` alone does not grant entry if staleness/gap/clock/market/risk/reconciliation reasons remain;
- protective-exit eligibility remains separate and must not be disabled merely because feed uncertainty blocks new entries;
- transport runtime/driver contains no direct RiskGate state mutation;
- transport runtime/driver contains no direct Phase-5 operational state mutation.

**Step 2: RED**

```powershell
python -m pytest tests_v1/test_phase6_feed_riskgate_handoff.py -q
```

**Step 3: Implement only the minimum bridge/mapping needed**

No new blocking authority is permitted.

**Step 4: GREEN + authority regression**

```powershell
python -m pytest tests_v1/test_phase6_feed_riskgate_handoff.py -q
python -m pytest tests_v1 -k "risk_gate and authority" -q
python build/tools/check_phase6_live_readonly.py
```

**Step 5: Commit**

```text
test: bind phase6 transport health to existing riskgate feed policy
```

---

## Task 6 — Preserve existing broker normalizers and add transport-envelope bridge compatibility

**Files:**
- Modify: `engine/data/feeds/live_feed.py`
- Modify: `engine/data/feeds/broker_live_feeds.py`
- Modify if required: `engine/data/transports/bridge.py`
- Create: `tests_v1/test_phase6_broker_normalizer_bridge.py`
- Re-run existing live-feed isolation tests.

**Step 1: Write RED tests**

For Angel One, Zerodha, Dhan, Upstox sanitized payloads prove:

- provider payload normalization remains broker-specific;
- connection generation/instrument token/source sequence metadata survives the transport-to-Data-V2 bridge;
- normalizers do not open sockets;
- normalizers do not own reconnect/heartbeat policy;
- normalizers do not gain RiskGate, operational-state, or broker-mutation authority.

**Step 2: RED**

```powershell
python -m pytest tests_v1/test_phase6_broker_normalizer_bridge.py -q
```

**Step 3: Minimal GREEN changes**

Do not rewrite working payload parsers solely for style.

**Step 4: GREEN + existing feed isolation regression**

```powershell
python -m pytest tests_v1/test_phase6_broker_normalizer_bridge.py -q
python -m pytest tests_v1 -k "live_feeds_isolation or broker_live_feed" -q
```

**Step 5: Commit**

```text
feat: bridge existing broker normalizers into shared transport metadata
```

---

## Task 7 — Add Angel One market-data transport driver without disturbing the existing read-only account adapter

**Files:**
- Create: `engine/data/transports/brokers/__init__.py`
- Create: `engine/data/transports/brokers/angelone.py`
- Create: `tests_v1/test_phase6_transport_angelone.py`
- Inspect/reuse narrow session evidence from `engine/broker_adapters/angelone_v2/session.py`; do not merge market-data transport into the account/execution adapter.

**Step 1: Write RED driver tests using injected fake wire/session**

Verify:

- driver declares `ANGELONE` identity/capabilities;
- auth/session evidence is injected, not hard-coded;
- subscribe/unsubscribe messages are provider-specific translations of broker-neutral requests;
- raw frames decode into `ProviderEnvelope`/normalizer inputs;
- heartbeat semantics are explicitly declared;
- native sequence is extracted only if sanitized provider fixtures prove a reliable provider field;
- otherwise sequence capability is `UNAVAILABLE` and no local counter is presented as broker sequence;
- no order mutation surface exists.

**Step 2: RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_angelone.py -q
```

**Step 3: Implement minimal driver**

Keep `engine/broker_adapters/angelone_v2/*` read-only account/reconciliation responsibilities intact.

**Step 4: GREEN + old Angel Phase-6 regression**

```powershell
python -m pytest tests_v1/test_phase6_transport_angelone.py tests_v1/test_phase6_angelone_read_only_adapter.py tests_v1/test_phase6_angelone_session.py -q
python build/tools/check_phase6_live_readonly.py
```

**Step 5: Commit**

```text
feat: add angelone market-data transport driver
```

---

## Task 8 — Add Zerodha and Dhan transport drivers behind the same contracts

**Files:**
- Create: `engine/data/transports/brokers/zerodha.py`
- Create: `engine/data/transports/brokers/dhan.py`
- Create: `tests_v1/test_phase6_transport_zerodha.py`
- Create: `tests_v1/test_phase6_transport_dhan.py`

**Step 1: RED tests for both providers**

Each driver must prove the same common contract:

- injected authorization/session material only;
- provider-specific handshake/subscription/frame translation;
- explicit heartbeat capability;
- explicit sequence semantics from sanitized fixture evidence, otherwise `UNAVAILABLE`;
- no guessed production subscription/rate limits;
- no reconnect algorithm inside the driver;
- no execution/broker-mutation authority.

**Step 2: RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_zerodha.py tests_v1/test_phase6_transport_dhan.py -q
```

**Step 3: Implement thin drivers**

Any production limits must come from versioned `BrokerTransportPolicy`, never unversioned source constants.

**Step 4: GREEN**

```powershell
python -m pytest tests_v1/test_phase6_transport_zerodha.py tests_v1/test_phase6_transport_dhan.py -q
python build/tools/check_phase6_live_readonly.py
```

**Step 5: Commit**

```text
feat: add zerodha and dhan market-data transport drivers
```

---

## Task 9 — Migrate the existing Upstox V3 scaffold into the shared runtime/driver model

**Files:**
- Create: `engine/data/transports/brokers/upstox.py`
- Modify narrowly: `engine/data/feeds/upstox/auth.py`
- Modify narrowly: `engine/data/feeds/upstox/feed.py`
- Modify `engine/data/feeds/upstox/normalizer.py` / dispatcher only if required by the new boundary
- Create: `tests_v1/test_phase6_transport_upstox.py`
- Re-run all existing Upstox feed tests.

**Step 1: Write RED migration tests**

Prove:

- Upstox-specific authorization/URL/frame decode remains provider-specific;
- generic reconnect/watchdog/generation/subscription replay now belongs to `MarketDataTransportRuntime`;
- no second Upstox reconnect state machine remains authoritative;
- existing binary-frame normalization remains deterministic;
- stale-generation frames are rejected centrally;
- provider sequence semantics are explicit;
- no execution authority appears.

**Step 2: RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_upstox.py -q
```

**Step 3: Refactor minimally**

Move only generic lifecycle responsibilities out of the Upstox scaffold. Preserve provider-specific auth/decode behavior.

**Step 4: GREEN + Upstox regressions**

```powershell
python -m pytest tests_v1/test_phase6_transport_upstox.py -q
python -m pytest tests_v1 -k "upstox" -q
python build/tools/check_phase6_live_readonly.py
```

**Step 5: Commit**

```text
refactor: move upstox live lifecycle onto shared transport runtime
```

---

## Task 10 — Add a dedicated market-data transport registry and fifth-broker extension proof

**Files:**
- Create: `engine/data/transports/registry.py`
- Create: `tests_v1/test_phase6_transport_registry.py`
- Create: `tests_v1/test_phase6_transport_extension.py`

**Step 1: RED registry tests**

Register exactly the initial supported transport drivers:

- Angel One;
- Zerodha;
- Dhan;
- Upstox.

Do not guess/select a fifth production vendor.

**Step 2: RED extension proof**

Use a synthetic `TestBrokerTransportDriver` to prove a fifth broker can be registered without modifying:

- `MarketDataTransportRuntime`;
- `FeedMonitor`;
- `MarketEventBridge` core behavior;
- `RiskGateV2`;
- `BrokerPortV2`.

The market-data registry must stay separate from the execution/account adapter registry.

**Step 3: RED**

```powershell
python -m pytest tests_v1/test_phase6_transport_registry.py tests_v1/test_phase6_transport_extension.py -q
```

**Step 4: Implement minimal registry**

No automatic cross-broker fallback/routing logic.

**Step 5: GREEN**

```powershell
python -m pytest tests_v1/test_phase6_transport_registry.py tests_v1/test_phase6_transport_extension.py -q
```

**Step 6: Commit**

```text
feat: add isolated market-data transport registry
```

---

## Task 11 — Build one common deterministic conformance and chaos suite for all four drivers

**Files:**
- Create: `tests_v1/test_phase6_transport_conformance.py`
- Create helper only if repository test style supports it: `tests_v1/helpers/phase6_transport_fakes.py`
- Reuse existing sanitized provider fixtures where available.

**Step 1: Parameterize the same suite across all four drivers**

Required scenarios:

1. connect;
2. clean close;
3. unexpected disconnect;
4. bounded reconnect;
5. reconnect exhaustion;
6. subscribe;
7. unsubscribe;
8. resubscribe after reconnect;
9. heartbeat success;
10. heartbeat timeout;
11. per-instrument staleness;
12. clock skew;
13. strict sequence gap;
14. monotonic regression/out-of-order;
15. sequence unavailable without fabrication;
16. malformed frame;
17. unknown instrument;
18. old-generation callback;
19. duplicate frame;
20. authentication expiry;
21. bounded queue overflow;
22. partial subscription acknowledgement;
23. no auto-arm on recovery;
24. no broker mutation authority.

**Step 2: Run RED for any driver not yet conforming**

```powershell
python -m pytest tests_v1/test_phase6_transport_conformance.py -q
```

**Step 3: Make only provider-edge fixes needed for conformance**

Do not fork the common runtime to special-case a provider unless the behavior is represented through declared capabilities/policy.

**Step 4: GREEN**

```powershell
python -m pytest tests_v1/test_phase6_transport_conformance.py -q
python build/tools/check_phase6_live_readonly.py
```

**Step 5: Commit**

```text
test: add common multi-broker transport conformance suite
```

---

## Task 12 — Broaden Phase-6 evidence, probe, static guard, and qualification markers

**Files:**
- Modify: `build/tools/check_phase6_live_readonly.py`
- Modify: `engine/live/phase6_evidence.py`
- Modify: `build/tools/phase6_probe.py`
- Modify: `tests_v1/test_phase6_architecture_guard.py`
- Modify: `tests_v1/test_phase6_evidence.py`
- Modify: `tests_v1/test_phase6_qualification_guard.py`
- Update only after executable evidence exists: `docs/v2/phase6/G6_EVIDENCE.md`

**Step 1: Write RED evidence tests**

The deterministic probe must retain old read-only/reconciliation markers and add at least:

```text
BROKER_SCOPE=ANGELONE,ZERODHA,DHAN,UPSTOX
MARKET_DATA_TRANSPORT=SHARED_RUNTIME_THIN_DRIVERS
TRANSPORT_HEALTH=LOWER_LEVEL_ONLY
FEED_HEALTH_HANDOFF=DATA_V2_FEED_MONITOR
RISK_GATE_FEED_BLOCK=DAT_005_008_EXISTING_PATH
SEQUENCE_KEY=CONNECTION_GENERATION+INSTRUMENT_TOKEN
SOURCE_SEQUENCE=EXPLICIT_SEMANTICS_NO_FABRICATION
QUEUE_OVERFLOW=FAIL_CLOSED
STALE_GENERATION=REJECTED
CROSS_BROKER_FAILOVER=DISABLED
LIVE_STATE=READ_ONLY/DISARMED
REAL_BROKER_MUTATION_CAPABILITY=ABSENT
```

Retain relevant existing markers for:

- `RECONCILIATION_AUTHORITY=LIVE_RECONCILER`;
- shared Phase-5 incident/alert model;
- no auto-arm;
- versioned broker/rate/rule policy;
- foreign activity halt/alert/manual-only behavior.

**Step 2: RED**

```powershell
python -m pytest tests_v1/test_phase6_evidence.py tests_v1/test_phase6_qualification_guard.py tests_v1/test_phase6_architecture_guard.py -q
```

**Step 3: Broaden guard/probe minimally**

The static firewall must scan the new transport/driver package as part of the G6 production-shaped read-only boundary.

**Step 4: GREEN + deterministic probe repeat**

```powershell
python -m pytest tests_v1/test_phase6_evidence.py tests_v1/test_phase6_qualification_guard.py tests_v1/test_phase6_architecture_guard.py -q
python build/tools/check_phase6_live_readonly.py
python build/tools/phase6_probe.py
python build/tools/phase6_probe.py
```

The two local probe outputs/fingerprints must be identical under the same deterministic fixture/environment.

**Step 5: Commit**

```text
feat: broaden g6 evidence to multi-broker transport safety
```

---

## Task 13 — Broaden the canonical G6 workflow without creating a duplicate qualification path

**Files:**
- Modify: `.github/workflows/v2-phase6-readonly.yml`
- Do not create a second competing G6 workflow unless review explicitly requires migration to a new filename.

**Step 1: Update workflow scope/name**

Keep one canonical G6 qualification workflow and broaden its focused suite to include:

- existing Angel read-only account/session/reconciliation/foreign-activity tests;
- all new Phase-6 transport contract/runtime/bridge/driver/conformance tests;
- Data-V2 live-feed/FeedMonitor regressions;
- RiskGate authority/handoff regression;
- S2 dependency checks required by the stack;
- static mutation firewall;
- deterministic G6 probe.

**Step 2: Preserve dual-Windows evidence**

Run the deterministic G6 path on:

- `windows-latest`;
- `windows-2022`;

and compare normalized artifacts/fingerprints in the existing comparison pattern.

**Step 3: Add workflow-structure tests if repository pattern supports them**

Qualification guard must fail if a required broker/conformance/static/probe step is silently removed.

**Step 4: Local syntax/guard verification**

Run all repository-supported workflow/qualification guard tests locally. Do not claim hosted G6 from local execution.

**Step 5: Commit**

```text
ci: broaden g6 qualification for multi-broker transport
```

---

## Task 14 — Final local verification, manual code review, and G6 evidence update

**Files:**
- Update: `docs/v2/phase6/G6_EVIDENCE.md` only with evidence actually observed.
- No feature code should be added in this task unless a discovered defect is handled through the normal RED/fix/GREEN cycle.

**Step 1: Run the complete focused Phase-6 suite**

```powershell
python -m pytest tests_v1/test_phase6_*.py -q
```

**Step 2: Run static firewall + probe**

```powershell
python build/tools/check_phase6_live_readonly.py
python build/tools/phase6_probe.py
```

**Step 3: Run relevant cross-phase regressions**

At minimum include the current canonical tests covering:

- Data-V2 live feed / FeedMonitor;
- RiskGate authority;
- Phase-5 operational safety/recovery seams touched by integration;
- S2 device/session dependency;
- existing Phase-6 reconciliation and incident behavior.

Use the actual repository filenames present at execution time rather than guessing renamed tests.

**Step 4: Run broader/full regression when the project gate requires it**

Per owner sequencing, the large combined project regression may be run with the later Phase-9 combined verification. That does not waive the focused Phase-6 verification in this task.

**Step 5: Manual architecture review**

Verify by diff and source inspection:

- `BrokerPortV2` remains execution/account authority;
- `MarketDataTransportRuntime` has no mutation/arm/RiskGate authority;
- no broker driver imports or creates `ApprovedOrder`;
- no broker driver owns a divergent generic reconnect loop;
- gap/staleness is per `(connection_generation, instrument_token)`;
- internal ingress sequence is not represented as provider continuity;
- transport health reaches RiskGate only through Data-V2 `FeedMonitor`/EntryPolicy;
- no automatic cross-broker execution/feed failover exists;
- existing Angel read-only account/reconciliation protections remain intact;
- Live remains `READ_ONLY / DISARMED`.

Use the `superpowers:requesting-code-review` process. If no review subagent is available, perform and disclose a manual requirements-vs-diff review.

**Step 6: Hosted qualification**

Trigger the canonical G6 workflow only when GitHub Actions can actually provision runners.

Qualification requires fresh exact-head evidence from both Windows jobs and the compare job. If jobs fail before steps execute, record:

```text
G6 NOT QUALIFIED — HOSTED EXECUTION EVIDENCE UNAVAILABLE
```

Do not represent infrastructure failure as code GREEN or code RED.

**Step 7: Evidence document**

Update `G6_EVIDENCE.md` with:

- exact commit SHA;
- exact test commands/counts;
- static firewall result;
- deterministic probe fingerprint;
- broker-driver conformance result;
- dual-Windows run/job/artifact IDs when actually available;
- explicit `LIVE_STATE=READ_ONLY/DISARMED`;
- explicit `G6_ENABLES_REAL_MONEY_TRADING=NO`.

**Step 8: Final verification before completion claim**

Use `superpowers:verification-before-completion`. No Phase-6 completion/qualification claim may be made from stale or partial evidence.

**Step 9: Commit evidence only after the evidence exists**

```text
docs: record multi-broker g6 qualification evidence
```

---

## G6 implementation exit checklist

Implementation may be called code-complete only when all of the following are supported by fresh evidence:

- one broker-neutral transport contract;
- one shared runtime owns lifecycle/reconnect/watchdog/backpressure/generation/subscription replay;
- Angel One, Zerodha, Dhan, and Upstox use the common driver contract;
- a synthetic fifth broker can plug in without core changes;
- provider-native sequence semantics are explicit and never fabricated;
- gap detection key is `(connection_generation, instrument_token)`;
- required-instrument staleness is per instrument;
- transport-health and Phase-5 operational state machines remain separate;
- the only safety handoff is through Data-V2 `FeedMonitor` / existing EntryPolicy;
- `DEGRADED` / `FAILED_CLOSED` feed the existing DAT-005/008 RiskGate stale-feed block;
- old connection generations cannot inject current data;
- bounded-queue overflow fails closed rather than silently dropping while healthy;
- missing/invalid provider policy fails closed;
- no automatic cross-broker execution or market-data failover;
- existing Angel read-only reconciliation/incident/account safety remains intact;
- static mutation firewall passes;
- focused Phase-6 tests pass;
- relevant Data-V2/RiskGate/Phase-5/S2 regressions pass;
- Live remains `READ_ONLY / DISARMED`.

Formal **G6 QUALIFIED** additionally requires successful hosted exact-head dual-Windows deterministic evidence. Code-complete/local-green alone is not G6 qualification and never enables real-money trading.
