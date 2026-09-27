# AlgoFortis V2 Phase 6 — Multi-Broker Live Connectivity and Read-Only Safety Design

**Date:** 2026-09-27  
**Status:** WRITTEN SPEC — OWNER REVIEW REQUIRED; IMPLEMENTATION PLAN AND CODING BLOCKED  
**Phase:** Phase 6 — Live Execution V2 (still `READ_ONLY / DISARMED`)  
**Scope:** Broker-neutral market-data transport plus broker-neutral read-only account/execution boundaries for multiple brokers  
**Initial market-data brokers:** Angel One, Zerodha, Dhan, Upstox  
**Extension target:** a fifth broker must be addable without changing core transport/runtime/feed-health architecture  
**Supersedes:** `docs/superpowers/specs/2026-09-27-phase6-live-readonly-angelone-design.md` as the primary Phase-6 architecture. The earlier document remains historical evidence for the Angel One-only design and its read-only safety invariants; this document broadens Phase 6 to a multi-broker architecture.

## 1. Purpose

Phase 6 is revised from a single-broker Angel One boundary into a broker-neutral multi-broker live-connectivity architecture while preserving all previously frozen safety properties.

The repository already contains three useful broker-neutral seams:

- `engine/broker_contract/port_v2.py` for broker/account/execution contracts;
- `engine/data/feeds/live_feed.py` for a broker-agnostic live-feed protocol;
- `engine/data/feeds/broker_live_feeds.py` for broker-specific raw-payload normalization.

The remaining architectural gap is a production-shaped, broker-neutral transport/runtime layer that owns WebSocket lifecycle, reconnect, heartbeat, subscriptions, bounded buffering, connection-generation fencing, and transport-health evidence without gaining execution authority.

The selected architecture is:

> **one shared broker-neutral market-data transport runtime + thin broker-specific transport drivers + one centralized Data-V2 health bridge.**

Broker differences stay at the edge. Connection safety, health semantics, lifecycle, and Data-V2 integration stay in the core.

## 2. Binding safety invariants

The revised scope does not weaken any existing Phase-5/Phase-6 safety boundary.

The following remain binding:

- Live remains `READ_ONLY / DISARMED` throughout G6 qualification.
- G6 GREEN must not mean real-money trading is enabled.
- `RiskGateV2` remains the sole future `ApprovedOrder` authority.
- No market-data transport, broker driver, normalizer, feed-health monitor, UI, AI, account/cloud component, alert path, or recovery path may mint an `ApprovedOrder`.
- reconnect, heartbeat recovery, session refresh, resubscription, restart, or healthy feed recovery must never auto-arm Live.
- broker account/execution authority and market-data transport authority remain separate.
- missing, stale, contradictory, or unverifiable required broker policy fails closed.
- no automatic cross-broker execution failover is introduced.
- no automatic cross-broker market-data failover is introduced in this phase.
- protective-exit safety remains a separate path and must not be disabled merely because new entries are blocked by feed uncertainty.

## 3. Top-level architecture

```text
                            AlgoFortis
                                |
                  +-------------+-------------+
                  |                           |
           EXECUTION / ACCOUNT            MARKET DATA
                  |                           |
            BrokerPortV2               Data-V2 canonical
                  |                    health/event seam
        read-only broker truth                 ^
                  |                           |
       reconciliation / risk             FeedMonitor
                  |                           ^
                  |                    MarketEventBridge
                  |                           ^
                  |                     LiveQuoteEvent
                  |                           ^
                  |                 provider normalizers
                  |                           ^
                  |                    ProviderEnvelope
                  |                           ^
                  |             MarketDataTransportRuntime
                  |                           ^
                  |          +--------+-------+--------+--------+
                  |          |        |       |        |        |
                  |       Angel    Zerodha   Dhan   Upstox   Broker-5
                  |       driver    driver  driver   driver    driver
                  |          |        |       |        |        |
                  |         WSS      WSS     WSS      WSS      WSS
```

The market-data side is not an order-routing side channel. `BrokerPortV2` remains the execution/account boundary. The new transport runtime is a sibling architecture under Data V2, not a replacement for `BrokerPortV2`.

## 4. Broker-neutral transport contracts

The design introduces a broker-neutral market-data transport contract below the existing normalizers.

Conceptual contract family:

```python
class BrokerTransportDriver(Protocol):
    broker_id: BrokerId
    capabilities: TransportCapabilities

    def authorize(...) -> AuthorizedEndpoint: ...
    def connect(...) -> TransportConnection: ...
    def encode_subscribe(...) -> TransportMessage: ...
    def encode_unsubscribe(...) -> TransportMessage: ...
    def decode_frame(...) -> ProviderEnvelope: ...
    def classify_frame(...) -> FrameKind: ...
    def extract_source_sequence(...) -> SourceSequence | None: ...
```

The driver owns only provider-specific behavior:

- authentication/authorization handshake details;
- WebSocket endpoint/session binding;
- provider frame decoding;
- provider heartbeat interpretation;
- provider subscription encoding/ack interpretation;
- provider-native sequence extraction and semantics;
- provider capability declaration.

The driver does **not** own:

- retry/backoff policy execution;
- generic reconnect state machine;
- queue/backpressure policy;
- connection-generation fencing;
- generic subscription replay;
- Data-V2 entry-policy authority;
- Paper/Live operational-state authority;
- RiskGate authority;
- broker order mutation.

## 5. Shared `MarketDataTransportRuntime`

A single shared runtime owns the lifecycle for all supported brokers.

Responsibilities:

- connect / disconnect lifecycle;
- bounded reconnect/backoff;
- transport watchdog;
- heartbeat deadline handling;
- connection-generation allocation and fencing;
- desired-vs-active subscription tracking;
- deterministic resubscription after reconnect;
- bounded receive queues / backpressure;
- stale-generation callback rejection;
- transport-health snapshots/events;
- redacted/auditable lifecycle evidence.

A successful reconnect means only that market-data transport may begin health recovery. It does not restore trading authority and does not auto-resume entries.

### 5.1 Connection-generation fencing

Every accepted live connection has a monotonically advancing `connection_generation` within the runtime instance.

If generation 41 is dead and generation 42 is current, any delayed callback from generation 41 is rejected before normalization/health observation.

```text
old callback generation=41
current generation=42
          |
          +--> DISCARD / AUDIT
```

No old connection may become a valid data source after a reconnect.

## 6. Provider envelope and canonical event bridge

Raw socket bytes do not enter strategies, RiskGate, or Paper/Live operational logic.

The transport driver first produces a provider-neutral envelope:

```text
ProviderEnvelope
  broker_id
  connection_id
  connection_generation
  instrument_token
  receive_timestamp
  exchange_timestamp
  source_sequence
  frame_kind
  decoded_payload
```

Then the existing broker-specific normalizer converts provider payload into the normalized quote/event representation, and one centralized bridge produces Data-V2 canonical observations.

```text
raw frame
   |
BrokerTransportDriver
   |
ProviderEnvelope
   |
existing broker normalizer
   |
LiveQuoteEvent / normalized quote
   |
MarketEventBridge
   |
LiveMarketEvent + monitor metadata
   |
FeedMonitor
```

No broker-specific FeedMonitor implementation is permitted.

## 7. REFINEMENT 1 — transport feed-health naming/state-machine separation

### 7.1 Two different state machines are intentional

Phase-6 transport feed-health is a **separate lower-level state machine** from the existing Phase-5 Paper/Live operational state machine.

Transport lifecycle/health states may use:

```text
STOPPED
CONNECTING
AUTHORIZING
CONNECTED
SUBSCRIBING
HEALTHY
DEGRADED
RECONNECTING
FAILED_CLOSED
```

The existing Phase-5 canonical operational states remain:

```text
HEALTHY
DEGRADED
HALTED
RECOVERY
READY_FOR_RESUME
```

The shared names `HEALTHY` and `DEGRADED` do **not** mean the state machines are the same machine.

**Binding rule:**

> **Transport feed-health is a separate, lower-level state machine. Its output feeds the Paper/Live operational state machine through the existing Data-V2 fail-closed feed-health/staleness signal. It does not replace, duplicate, or directly mutate the Phase-5 operational state machine.**

### 7.2 Exact handoff point

The single architectural handoff point is **Data-V2 `FeedMonitor` / existing feed-health entry-policy seam**.

```text
Broker WebSocket
      |
      v
MarketDataTransportRuntime
      |
      |  TransportHealthSnapshot
      |  STOPPED / CONNECTING / AUTHORIZING / CONNECTED /
      |  SUBSCRIBING / HEALTHY / DEGRADED /
      |  RECONNECTING / FAILED_CLOSED
      v
+-------------------------------------------------------+
| Data-V2 transport-health bridge / FeedMonitor         |
|                                                       |
| converts transport uncertainty + event freshness +    |
| sequence integrity + clock skew into EXISTING         |
| FeedHealthReason / entries_allowed semantics          |
+-------------------------------------------------------+
      |                         |
      |                         +--> RiskGateV2 existing EntryPolicy path
      |                               (new entries allowed/blocked)
      v
existing Paper/Live operational-health input
      |
      v
Phase-5 operational state machine
HEALTHY / DEGRADED / HALTED / RECOVERY / READY_FOR_RESUME
```

The transport runtime must never call the Paper/Live operational state machine directly.

The transport runtime must never call RiskGate directly.

The transport runtime publishes lower-level health evidence; Data V2 converts that evidence into the same feed-health semantics already consumed by existing safety authorities.

### 7.3 Transport-to-Data-V2 mapping semantics

The mapping is fail-closed but does not create a new operational authority.

Examples:

- `RECONNECTING` -> existing reconnect/feed-unavailable reason -> entries blocked;
- `SUBSCRIBING` before required subscriptions are confirmed -> feed not ready -> entries blocked;
- `DEGRADED` -> Data-V2 feed-health reason(s) such as stale/uncertain/gap depending on the observed cause -> entries blocked for the affected required feed context;
- `FAILED_CLOSED` -> Data-V2 feed-health unavailable/stale fail-closed condition -> entries blocked;
- transport `HEALTHY` alone does **not** imply Paper/Live operational `HEALTHY` or entry permission; freshness, sequence, clock, market state, reconciliation, risk, and all other existing gates must still pass.

This prevents the lower-level transport state machine from becoming a second operational state authority.

## 8. REFINEMENT 2 — per-instrument sequence-gap and staleness tracking

A single WebSocket commonly multiplexes multiple instruments. A connection-level sequence/staleness tracker can therefore report a false healthy condition if one instrument goes silent while another continues producing traffic.

### 8.1 Binding gap-detection key

> **Gap-detection key = `(connection_generation, instrument_token)` tuple. It must never be only `connection_generation`.**

This tuple scopes sequence history to the exact live stream generation and instrument identity.

Example:

```text
connection_generation = 42

NIFTY token   sequence: 100, 101, 103  -> gap for (42, NIFTY_TOKEN)
BANKNIFTY      sequence: 501, 502, 503  -> healthy for (42, BANKNIFTY_TOKEN)
```

BANKNIFTY traffic must not mask NIFTY's missing provider sequence.

### 8.2 `SourceSequence` semantics

Provider sequence semantics are explicit rather than assumed:

```python
SourceSequence:
    value: int | None
    semantics:
        STRICT_CONTIGUOUS
        MONOTONIC_ONLY
        UNAVAILABLE
    scope:
        CONNECTION
        STREAM
        INSTRUMENT
        NONE
    provider_field: str | None
```

Rules:

- `STRICT_CONTIGUOUS`: `n, n+1` continuity is required for the relevant key; a jump creates `SEQUENCE_GAP`.
- `MONOTONIC_ONLY`: regression/duplicate/out-of-order may be detected, but numeric gaps are not inferred.
- `UNAVAILABLE`: AlgoFortis must not fabricate a provider sequence. Health falls back to freshness, heartbeat, exchange/receive timestamps, and other supported signals.

### 8.3 Internal ingress ordering is separate

AlgoFortis may maintain an internal deterministic `ingress_sequence`, but:

```text
ingress_sequence != provider/source sequence
```

The internal counter must never be used as evidence that broker packets were contiguous.

The canonical Data-V2 model must therefore separate:

```text
ingress_sequence   # AlgoFortis internal ordering
source_sequence    # provider-origin sequence + semantics
```

The current ambiguous single `LiveMarketEvent.sequence` must be treated as a compatibility field during migration and must not remain the long-term source of provider gap truth.

### 8.4 Required `FeedMonitor.observe()` target contract

The revised design requires the monitor call to carry enough identity to enforce per-instrument/per-generation tracking explicitly.

Target design contract:

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

Equivalent typed envelope forms are acceptable only if they preserve these exact fields and semantics at the `FeedMonitor` boundary; implementation must not hide the key behind a global connection-only counter.

The monitor behavior must maintain state keyed by:

```text
(connection_generation, instrument_token)
```

At minimum, keyed state includes:

- last provider/source sequence where available;
- last accepted receive timestamp;
- last accepted exchange timestamp as needed for skew evidence;
- sequence-integrity latch(es) for that key.

### 8.5 Per-instrument staleness

The same multiplexing problem applies to freshness.

A single global `_last_event` cannot be authoritative for a multi-instrument feed because traffic from instrument B can hide staleness of required instrument A.

Therefore the revised monitor design must evaluate freshness per active/required instrument token. A required instrument that stops producing valid observations becomes stale even while the WebSocket and other instruments remain active.

Aggregation into `entries_allowed` remains an existing Data-V2 policy decision: if any required feed input for a candidate/decision context is stale or integrity-failed, the existing feed-health policy blocks that new entry.

## 9. REFINEMENT 3 — explicit linkage to the existing RiskGate stale-feed block

DAT-005/008 already establish the authority rule that stale/unsafe market data blocks new entries at RiskGate.

The new Phase-6 transport-health architecture must **not** introduce a second blocking authority.

**Binding rule:**

> **`FAILED_CLOSED` or `DEGRADED` transport health feeds the existing Data-V2 `FeedMonitor` fail-closed signal and thereby triggers the existing RiskGate stale-feed/entry-policy block through the same DAT-005/008 path. No new second authority path is created. The transport layer only supplies better-quality upstream evidence to the existing gate.**

Exact authority path:

```text
transport lifecycle / provider evidence
            |
            v
Data-V2 FeedMonitor
  reasons / entries_allowed
            |
            v
existing EntryPolicy seam
            |
            v
RiskGateV2
            |
            +--> new entry BLOCKED when feed unsafe
            |
            +--> protective-exit path remains governed separately
```

Prohibited parallel paths include:

```text
TransportRuntime -> direct RiskGate mutation
TransportRuntime -> direct Paper/Live HALT authority
BrokerDriver     -> direct RiskGate mutation
Normalizer       -> direct Paper/Live state mutation
```

Transport health is evidence, not authority.

## 10. FeedMonitor authority and recovery semantics

`FeedMonitor` remains the canonical Data-V2 market-feed health / entry-policy seam.

It owns the normalized safety view of:

- no data;
- per-instrument staleness;
- supported provider sequence gap/out-of-order evidence;
- clock skew;
- market closed/halted state;
- reconnect/resubscribe uncertainty;
- lower-level transport degradation/fail-closed evidence.

A transport recovery to `HEALTHY` does not automatically clear every Data-V2 integrity latch. Persistent sequence/integrity faults require the existing explicit recovery semantics defined by Data V2 / operational recovery policy.

Similarly, Paper/Live operational `READY_FOR_RESUME` is not generated by the transport runtime. It remains an operational-state result after all existing recovery conditions are satisfied.

## 11. Subscription model

AlgoFortis maintains a broker-neutral desired subscription set.

Conceptual request:

```text
SubscriptionRequest
  instruments
  data_mode
```

The shared runtime owns:

- desired subscriptions;
- active/acknowledged subscriptions;
- subscription generation;
- resubscription after reconnect;
- fail-closed state until required subscriptions are confirmed.

The provider driver only translates between the broker-neutral request and broker-specific subscription frames/acknowledgements.

Partial or ambiguous subscription acknowledgement must not be interpreted as a healthy complete subscription set.

## 12. Heartbeat model

Heartbeat semantics are capabilities, not assumptions.

Supported modes may include:

```text
PROTOCOL_PING_PONG
PROVIDER_HEARTBEAT_FRAME
DATA_ACTIVITY
NONE
```

The runtime tracks distinct clocks where applicable:

- `last_frame_at`;
- `last_data_at`;
- `last_protocol_heartbeat_at`.

Receiving a market tick is not automatically equivalent to receiving a provider/protocol heartbeat unless the provider contract explicitly defines it that way.

## 13. Backpressure and bounded buffering

The shared runtime must use bounded buffering.

An unbounded receive queue is not permitted in the production-shaped transport path.

Queue overflow, decoder saturation, or sustained processing lag must be explicit health evidence. The system must not silently drop frames while continuing to advertise a healthy feed.

Conceptually:

```text
incoming frames
      |
 bounded queue
      |
 normalization

capacity exceeded
      |
QUEUE_OVERFLOW evidence
      |
transport DEGRADED / FAILED_CLOSED
      |
Data-V2 FeedMonitor fail-closed path
      |
existing RiskGate entry block
```

## 14. Broker-specific drivers

Initial Phase-6 market-data support targets:

- Angel One;
- Zerodha;
- Dhan;
- Upstox.

Each implements the same `BrokerTransportDriver` contract.

The existing raw-payload normalizers are reused above the transport driver unless a small contract adaptation is required.

### 14.1 Upstox scaffold migration

Existing Upstox-specific WebSocket fields/drop/watchdog scaffolding are treated as provider-specific precursor code, not as the final architecture.

Provider-specific connection details move behind `UpstoxTransportDriver`; generic reconnect/watchdog/backpressure/subscription replay move into the shared runtime.

No special second runtime architecture is retained for Upstox.

## 15. Broker-5 extensibility test

The fifth broker is intentionally not guessed in this design.

The architecture passes the extensibility criterion only if adding Broker-5 requires primarily:

- one new transport driver;
- one normalizer or normalization adaptation if required;
- capability/policy declaration;
- conformance fixtures/tests;
- registry entry.

Adding Broker-5 must not require core changes to:

- `MarketDataTransportRuntime` lifecycle architecture;
- `FeedMonitor` authority model;
- RiskGate authority path;
- Paper/Live operational-state authority;
- `BrokerPortV2`;
- strategy code.

## 16. Broker policy and capability data

Broker limits and protocol properties are versioned policy/capability inputs, not guessed source constants.

Examples:

- maximum subscriptions/socket;
- subscription batch limits;
- connection/socket limits;
- heartbeat deadlines;
- auth/session lifetime semantics;
- reconnect bounds;
- provider sequence semantics/scope;
- supported quote/depth/OI modes.

If a required production policy/capability is missing or unverifiable, the relevant path fails closed.

## 17. Authentication and secret boundary

Transport drivers may consume injected authenticated session/token providers but must not persist or expose credentials in market-data events.

Credentials/tokens/account identifiers must not appear in:

- normalized quote events;
- `LiveMarketEvent`;
- transport-health snapshots;
- audit payloads;
- replay artifacts;
- exception/log text intended for general diagnostics.

Authentication success grants only the transport/read capability appropriate to the configured boundary. It never grants Live arm or order mutation authority.

Auth expiry/refresh failure invalidates the connection and enters controlled fail-closed recovery; it does not silently simulate success.

## 18. Read-only execution/account boundary remains separate

The earlier Angel One V2 work remains relevant as the first read-only broker-truth implementation, but it is no longer the sole Phase-6 architecture.

`BrokerPortV2` remains the broker-neutral account/execution contract family.

Market-data transport support for multiple brokers does not automatically mean that every broker receives a real execution implementation in the same change. Read-only account/reconciliation adapters may be implemented per broker behind `BrokerPortV2` without merging their authority with market-data transport.

No market-data reconnect or health recovery may invoke order placement/modification/cancellation.

## 19. No automatic broker failover

Multi-broker support means multiple brokers implement the same contracts. It does not mean AlgoFortis automatically routes between accounts/providers.

If an Angel One feed drops, Phase 6 does not automatically place an order through Zerodha, and it does not silently replace the market-data source with Zerodha.

Any future smart routing/failover feature requires a separate design covering account identity, position reconciliation, risk, data provenance, quantity/margin semantics, idempotency, and explicit Owner authorization.

## 20. Failure semantics

Examples of fail-closed transport/data outcomes:

- stale required instrument -> Data-V2 stale reason -> existing RiskGate entry block;
- strict source-sequence gap for one instrument -> instrument-specific integrity failure -> existing RiskGate entry block for affected decision context;
- reconnect in progress -> feed not ready -> existing RiskGate entry block;
- resubscription not fully acknowledged -> feed not ready -> existing RiskGate entry block;
- stale connection generation callback -> reject before canonical observation;
- heartbeat timeout -> transport degradation -> Data-V2 fail-closed signal;
- queue overflow -> transport degradation/fail-closed -> Data-V2 fail-closed signal;
- malformed frame/unknown required instrument mapping -> fail closed for affected input;
- unavailable provider sequence -> no fabricated gap evidence; use supported freshness/heartbeat/clock signals.

None of these outcomes independently authorizes broker mutation or changes RiskGate's role.

## 21. Conformance requirements for eventual implementation

This section defines required design verification targets only; it is **not** an implementation plan.

Every broker driver must eventually prove the same deterministic contract behavior using fake/sanitized transports and fixtures for at least:

- connect / clean close / unexpected disconnect;
- reconnect and bounded exhaustion;
- subscribe / unsubscribe / resubscribe;
- partial subscription acknowledgement;
- heartbeat success/timeout;
- per-instrument staleness;
- strict per-instrument sequence gap;
- monotonic-only regression/out-of-order;
- sequence unavailable without fabrication;
- malformed frame;
- unknown instrument mapping;
- old-generation callback rejection;
- duplicate/out-of-order provider frame handling;
- auth expiry;
- queue overflow;
- policy missing/stale/unverifiable failure.

A broker is not Phase-6 supported merely because its socket connected once.

## 22. G6 qualification direction

G6 is revised from an Angel-only qualification into a multi-broker connectivity/read-only safety qualification.

Future G6 evidence must prove, at the exact reviewed head:

- one broker-neutral shared runtime architecture;
- common driver conformance across the selected initial brokers;
- explicit source-sequence semantics;
- `(connection_generation, instrument_token)` keyed gap tracking;
- per-instrument freshness tracking for required instruments;
- transport-state to Data-V2 handoff at the single `FeedMonitor` seam;
- `DEGRADED` / `FAILED_CLOSED` flow through the existing DAT-005/008 RiskGate stale-feed block;
- no second operational-state authority;
- no second RiskGate/blocking authority;
- stale-generation rejection;
- bounded queues and fail-closed overflow;
- no automatic cross-broker execution failover;
- Live remains `READ_ONLY / DISARMED`;
- real broker mutation remains structurally unreachable during G6.

Hosted qualification failure before test provisioning remains infrastructure/unqualified evidence, not code GREEN and not code RED.

## 23. Explicit non-goals

This written spec does not authorize or design:

- real-money order activation;
- automatic Live arming;
- cross-broker smart order routing;
- automatic position migration;
- broker-selection AI;
- automatic broker failover for execution;
- silent cross-provider market-data substitution;
- a replacement for the Phase-5 Paper/Live operational state machine;
- a replacement for RiskGateV2;
- a second stale-feed blocking authority;
- a broker-specific FeedMonitor;
- implementation-plan execution.

## 24. Frozen Phase-6 architectural decisions for spec review

The written spec asks the Owner to approve the following exact decisions:

1. `BrokerPortV2` remains the broker-neutral execution/account authority boundary.
2. Market-data transport is a separate broker-neutral sibling boundary under Data V2.
3. One shared `MarketDataTransportRuntime` owns lifecycle/reconnect/watchdog/backpressure/generation/subscription replay.
4. Angel One, Zerodha, Dhan, and Upstox use thin provider drivers behind the common transport contract.
5. Broker-5 remains an extension slot; core architecture must not depend on choosing that vendor now.
6. Provider-specific sequence semantics are explicit; provider sequence is never fabricated from internal ingress order.
7. **Gap-detection key is `(connection_generation, instrument_token)`.**
8. Required-instrument staleness is evaluated per instrument, not from one global last-event timestamp.
9. Transport feed-health is a separate lower-level state machine.
10. **The exact handoff from transport health to safety authority is Data-V2 `FeedMonitor`; transport health does not replace/duplicate the Phase-5 operational state machine.**
11. **`DEGRADED` / `FAILED_CLOSED` transport conditions trigger the existing DAT-005/008 RiskGate stale-feed/EntryPolicy block through `FeedMonitor`; no new second authority path exists.**
12. Transport/runtime/driver code cannot arm Live, mint `ApprovedOrder`, or mutate broker orders.
13. No automatic cross-broker execution or feed failover is introduced by this scope.
14. G6 qualification is broadened to multi-broker transport/read-only safety evidence while Live remains `READ_ONLY / DISARMED`.

## 25. Process gate after this commit

This document is the written design spec only.

**No implementation plan and no code changes may start until the Owner reviews and explicitly approves this written spec.**

After written-spec approval, the next allowed step is to create a separate implementation plan with task ordering, TDD/verification gates, migration sequencing, and exact G6 evidence changes. Implementation begins only after that plan is reviewed under the normal project process.
