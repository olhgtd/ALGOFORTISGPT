# AlgoFortis V2 — RiskGateV2 Deterministic Fast Path Design

**Status:** DESIGN APPROVED — implementation not started  
**Date:** 2026-09-30  
**Branch:** `riskgate-v2-fast-path-design-20260930`  
**Baseline:** `checkpoint-entry-gate-v1-reunion-preverification-20260930` @ `216c5b1334e6704bd304fa9acc025b97152ef8c2`  
**Safety baseline:** Live remains `READ_ONLY / DISARMED`; AI/Laya remain advisory/research/shadow; `RiskGateV2` remains the sole authority able to mint an `ApprovedOrder` capability.

## 1. Purpose

Reduce candidate-to-risk-decision latency without weakening any existing AlgoFortis trading-safety invariant.

The fast path is not a shortcut around RiskGate. It is a restructuring of where expensive work happens:

- expensive/static risk state is prepared before a candidate arrives;
- the candidate-time path performs only deterministic delta checks against an immutable authoritative snapshot;
- required audit evidence is still written before an `ApprovedOrder` is minted;
- any missing, stale, mismatched, unhealthy, or unauditable authority fails closed;
- no slow fallback is executed inside the hot path.

The design is first implemented and benchmarked only in Paper/Shadow with a mock/warm transport boundary. It does not create a real-broker mutation path and does not arm Live.

## 2. Existing authority preserved

The existing `engine/risk/gate_v2.py` contract remains authoritative:

- `RiskGateV2` is the sole minting authority for `ApprovedOrder`;
- expired intents are rejected;
- entry-policy halts are rejected;
- options SELL entries are rejected under BUY-only policy;
- hard quantity limits are enforced;
- evaluator evidence must match the active limits snapshot;
- invalid/missing evaluator evidence fails closed;
- required audit write failure raises `RiskApprovalError` and blocks the risk action.

This design extends that authority through additive contracts. It does not create a parallel RiskGate or a second approval capability.

## 3. Non-negotiable invariants

1. **No RiskGate bypass.** Laya, Prime, Strategy, Owner/Admin, Paper, Shadow, UI and transport code cannot mint or fabricate `ApprovedOrder`.
2. **INV-16 remains dominant.** A trading-critical action is blocked if its required audit event cannot be written.
3. **Audit failure beats latency.** If the minimal approval/rejection audit append fails, the candidate is BLOCKED and no `ApprovedOrder` is minted, even if this causes the latency SLO to be missed. Speed never overrides audit safety.
4. **No guessed production latency constants.** Production SLO values come only from a versioned `RiskGateLatencyPolicy`; source code contains no guessed/frozen production latency numbers.
5. **No slow fallback in the hot path.** Snapshot stale/missing/mismatched/unhealthy means BLOCK. The candidate path never performs an expensive rebuild, database scan, LLM call, network research, backtest, portfolio rebuild, or synchronous recovery calculation.
6. **Snapshot health is trading safety.** Snapshot-builder stale/crashed/unhealthy state enters the existing operational-state/failure path; it is never a silent performance degradation.
7. **No new monitoring authority.** Snapshot health reuses Phase-5 `HEALTHY / DEGRADED / HALTED / RECOVERY / READY_FOR_RESUME`, `FailureIncident`, existing audit evidence, and existing alert dispatcher/ports.
8. **Price chasing is forbidden.** A candidate whose bounded entry/price/slippage/TTL contract is no longer valid is rejected/expired; the fast path never changes the candidate merely to catch the market.
9. **Replay/duplicate safety remains fail-closed.** Candidate identity, market-data sequence, snapshot identity and order-intent identity must remain consistent and non-replayed.
10. **Live stays disabled.** Initial implementation and performance qualification are Paper/Shadow + mock/warm transport only.

## 4. Approved architecture

```text
Market / Portfolio / Account / Limits / Feed / Strategy Authority
                         |
                         v
              Snapshot Input Collector
                         |
                         v
            Background Risk Snapshot Builder
                         |
             immutable RiskSnapshot
                         |
              atomic current-snapshot ref
                         |
                         v
Laya/Strategy ---> TradeCandidate
                         |
                         v
               RiskGateV2 Fast Path
               - candidate TTL
               - snapshot freshness/id
               - entry-policy state
               - kill/hold state
               - options BUY-only
               - qty ceiling
               - entry zone / max price
               - slippage bound
               - market sequence
               - replay/duplicate guard
                         |
                deterministic decision
                         |
                 required audit append
                         |
            ApprovedOrder OR RiskRejection
                         |
                 warm Paper/Shadow handoff
```

The architecture separates **precomputation** from **authorization**. A precomputed snapshot is evidence, not approval. `RiskGateV2` still authorizes each individual candidate/order intent.

## 5. `RiskGateLatencyPolicy` — versioned, never hardcoded

Latency objectives are policy/evidence, not source constants.

Proposed immutable contract:

```text
RiskGateLatencyPolicy
- policy_id
- version
- status                 # TEST_ONLY / CALIBRATION / APPROVED
- effective_from
- environment_scope      # e.g. paper-shadow qualification profile
- hardware_profile_ref
- runtime_profile_ref
- sample_minimum_ref
- percentile_definition
- stages:
    risk_delta_checks
    riskgate_total_including_required_audit
    candidate_to_transport_handoff
    local_processing_total
- each stage:
    percentile_target
    ceiling_duration
    breach_action
- external_transport_measurement:
    measured_separately = true
- evidence_bundle_ref
- approved_by / approval_ref where governance requires it
```

Rules:

- production code consumes a validated policy object/reference;
- missing/corrupt/unsupported required policy fails closed for qualification-sensitive operation;
- tests may use explicit `TEST_ONLY` values;
- benchmark evidence calibrates policy values;
- no number becomes production-frozen merely because it appeared in a design discussion or benchmark experiment;
- policy revisions are versioned and evidence-linked; changing an SLO never silently mutates historical evidence.

The previously discussed example targets (sub-millisecond delta checks, low-millisecond total gate, tens-of-milliseconds local handoff, and sub-second overall desired interaction) are **calibration starting points only**, not production constants and not hardcoded requirements.

## 6. `RiskSnapshot` contract

The snapshot is immutable, versioned evidence containing only state that can safely be precomputed before a specific candidate arrives.

Proposed fields:

```text
RiskSnapshot
- snapshot_id
- schema_version
- generated_at_utc
- input_fingerprint
- risk_rule_version
- limits_snapshot_id
- account_authority_ref
- strategy_eligibility_ref
- portfolio_state_ref
- entry_policy_ref
- operational_state
- kill_switch_state
- hold_state
- allowed_instrument_scope
- allowed_side_scope
- quantity_ceiling_by_scope
- risk_budget_evidence
- feed_health_ref
- market_sequence_floor / latest_sequence_ref where applicable
- source_versions
- builder_health_generation
```

The snapshot must not contain an implicit permission to trade. It only supplies prevalidated evidence consumed by `RiskGateV2`.

### 6.1 Atomic publication

The builder constructs a complete new snapshot off-path, validates it, then atomically replaces the current snapshot reference. Readers never observe a partially updated snapshot.

No in-place mutation of the active snapshot is permitted.

### 6.2 Snapshot freshness

Freshness rules are versioned policy, not guessed constants.

The fast path checks at minimum:

- snapshot exists;
- snapshot schema supported;
- snapshot builder health generation current;
- snapshot age/freshness satisfies active versioned policy;
- limits/risk-rule identity matches current authority;
- account/strategy/operational references are not invalidated;
- market/feed evidence is compatible with the candidate sequence.

Failure of any required check means BLOCK; no synchronous rebuild occurs.

## 7. Background Snapshot Builder health and failure mode

The builder is a safety-critical evidence producer and therefore uses the existing Phase-5 operational model rather than a new standalone monitor.

### 7.1 Canonical health mapping

- normal current snapshot production -> existing operational state may remain `HEALTHY`;
- transient builder lag/failure while owned state remains trustworthy -> `DEGRADED` according to existing versioned policy;
- stale/unavailable snapshot that prevents safe new-entry authorization -> `HALT_ENTRIES` -> sticky `HALTED` where the existing policy requires it;
- continuity uncertainty -> existing `RECOVERY` path;
- recovery checks can lead to `READY_FOR_RESUME`, and sticky safety halt still requires explicit manual resume before returning to `HEALTHY`.

### 7.2 Failure evidence

Builder stale/crash/error emits/reuses the existing `FailureIncident` model with fields such as:

- failure type;
- severity;
- source = risk snapshot builder;
- affected scope;
- previous/resulting state;
- transition reason;
- halt latch;
- recovery reference when applicable;
- resolution evidence.

Alert delivery reuses the existing Phase-5 dispatcher and alert adapters. No `RiskSnapshotAlertManager`, second incident DB, or private monitoring subsystem is created.

### 7.3 Candidate behavior while unhealthy

A candidate arriving while the snapshot authority is unhealthy, stale, absent or invalid receives a deterministic rejection/block reason. It is never queued waiting for a slow rebuild and never auto-replayed after recovery.

A fresh candidate must be generated/evaluated after authority is restored according to existing intent freshness/replay rules.

## 8. Candidate contract

Laya/Strategy output is a research/trading candidate, never an executable order capability.

The candidate/order-intent boundary must carry sufficient bounded evidence for deterministic checks, including as applicable:

```text
- candidate_id / intent_id
- strategy_version
- instrument identity
- side
- requested quantity
- candidate_created_at
- valid_until / TTL policy ref
- market-data sequence/ref
- observed/reference price evidence
- entry zone or bounded price condition
- maximum acceptable price/slippage policy ref
- originating evidence refs
```

Price/TTL/slippage thresholds themselves follow existing versioned-policy/no-guessed-production-number discipline.

## 9. Fast-path algorithm

Conceptual order:

1. validate candidate/intent type and immutable identity;
2. read current snapshot reference once;
3. verify snapshot health/freshness/version compatibility;
4. verify candidate TTL and non-replay/duplicate state;
5. verify operational state permits new entry;
6. verify feed/market sequence compatibility;
7. enforce options BUY-only and instrument/side scope;
8. enforce quantity ceiling/hard limits;
9. verify bounded entry-price/slippage conditions against authoritative current quote evidence;
10. run only the remaining deterministic candidate-specific risk delta evaluation;
11. construct `RiskDecision` evidence;
12. synchronously append the required minimal audit event;
13. **only after successful audit append**, mint `ApprovedOrder`;
14. hand the opaque capability to the Paper/Shadow warm transport boundary.

At any error or ambiguity, reject/block. There is no retry/rebuild branch inside this sequence.

## 10. Audit path and INV-16

The existing audit-before-approval semantics are preserved.

### 10.1 Minimal deterministic hot-path payload

The required hot-path audit record should contain only bounded deterministic identifiers/evidence necessary to establish the decision, for example:

- candidate/intent id;
- client order id where already deterministically derivable;
- decision/reference;
- risk-rule version;
- limits snapshot id;
- RiskSnapshot id;
- market sequence/ref;
- decision reason(s);
- policy references.

Large human-readable enrichment belongs to downstream read models/reports and must not be required to authorize the order.

### 10.2 Failure rule

**Audit-write failure = BLOCK.**

If the mandatory audit append fails:

- no `ApprovedOrder` is minted;
- no transport handoff occurs;
- the risk action fails closed under INV-16;
- existing operational failure/alert handling records the audit subsystem issue as appropriate;
- latency SLO breach is accepted rather than weakening audit safety.

There is no asynchronous “approve now, audit later” exception for trading-critical approval.

## 11. Warm transport boundary

The performance design may keep non-authorizing transport preparation warm in Paper/Shadow, such as:

- process/thread availability;
- validated static instrument mapping cache;
- serialization template/cache;
- bounded connection/mock-transport readiness;
- preallocated non-secret/non-authorizing structures.

Forbidden before RiskGate approval:

- sending an order;
- constructing/fabricating an executable capability;
- mutating broker/Paper order state as if approved;
- reserving behavior that itself has trading side effects;
- using transport readiness as safety evidence.

The initial implementation uses mock/Paper/Shadow transport only. Real broker submission remains out of scope while Live is `READ_ONLY / DISARMED`.

## 12. Latency instrumentation

Use monotonic high-resolution timing for elapsed durations and authoritative UTC timestamps for evidence correlation.

Canonical stage markers:

```text
T0 candidate_created / received
T1 riskgate_enter
T2 snapshot_loaded
T3 deterministic_checks_complete
T4 audit_append_complete
T5 approved_order_minted OR rejection_finalized
T6 transport_handoff
T7 mock/paper transport acknowledgement
```

Derived metrics include:

- risk delta-check latency;
- audit append latency;
- total RiskGate latency;
- candidate-to-handoff latency;
- mock/Paper transport latency;
- stale-snapshot block count;
- snapshot-health block count;
- latency-policy breach count;
- candidate expiration caused by processing delay;
- audit failure count;
- replay/duplicate rejection count.

Timing instrumentation must not introduce an unbounded hot-path dependency. Evidence buffering/persistence follows existing audit/telemetry safety contracts.

## 13. Benchmark and calibration methodology

Initial qualification is Paper/Shadow only.

Required benchmark dimensions:

- warm steady-state;
- cold-start reported separately, never mixed into warm p99;
- multiple candidate rates;
- approved and rejected paths;
- snapshot publication concurrent with readers;
- stale/mismatch/failure paths;
- audit-store normal and fault-injected conditions;
- Windows 11 first-class target;
- representative supported hardware profiles;
- deterministic fixtures where possible;
- long-enough sample size determined by versioned benchmark policy/evidence requirements.

Performance evidence must report distributions (`p50`, `p95`, `p99`, max/outliers where appropriate), not only averages.

A latency target cannot be promoted to production policy until its evidence bundle identifies hardware/runtime profile, sample methodology, code SHA, policy versions, and observed distribution.

## 14. Policy breach behavior

Latency SLO breach is observability/governance evidence, not permission to skip safety checks.

- If an otherwise safe Paper/Shadow operation exceeds an SLO but completes safely, record the breach.
- Repeated breaches are classified through existing versioned failure/storm policy and operational-state machinery.
- A policy may escalate repeated breaches to `DEGRADED` or `HALT_ENTRIES`/`HALTED` based on evidence-governed thresholds.
- No hardcoded “N breaches in M seconds” is added; use versioned policy.

## 15. Module boundaries

Proposed additive layout (final file names may be refined in the implementation plan without changing authority):

```text
engine/risk/
├── gate_v2.py                    # existing sole approval authority
├── latency_policy_v2.py          # versioned RiskGateLatencyPolicy contract
├── snapshot_contracts_v2.py      # immutable snapshot + health refs
├── snapshot_builder_v2.py        # off-hot-path builder
├── fast_path_v2.py               # deterministic orchestration/helper consumed by RiskGateV2
└── latency_evidence_v2.py        # timing/evidence records
```

Possible integration with existing Phase-5 modules:

```text
engine/paper/operational_state_v2.py
engine/paper/failure_policy_v2.py
engine/persistence/paper_incident_store_v2.py
engine/alerts/dispatcher.py
```

No duplicate operational-state enum, incident repository, audit authority or alert dispatcher is introduced.

## 16. Dependency rules

Allowed:

```text
RiskGateV2
  -> pure risk snapshot/policy contracts
  -> deterministic evaluator/fast-path helper
  -> existing audit sink
  -> read-only entry/operational policy evidence

Snapshot Builder
  -> read-only account/portfolio/limits/feed/strategy authorities
  -> existing operational incident/alert ports for failure signaling
```

Forbidden:

- Laya/AI -> `_mint_approved_order`;
- Snapshot Builder -> broker mutation;
- fast path -> database scan/research/LLM/backtest;
- fast path -> auto-rebuild on stale snapshot;
- transport -> RiskGate approval fabrication;
- latency policy -> disabling a safety invariant;
- latency breach handling -> skipping audit;
- any new component -> independent operational-state/audit/incident/alert authority.

## 17. Concurrency and consistency

The hot path must have predictable synchronization characteristics.

Design preference:

- immutable snapshots;
- single atomic reference swap/publication;
- lock-free or bounded/read-mostly access where the runtime/language implementation safely supports it;
- no global unbounded mutex around candidate authorization;
- duplicate/replay guard with deterministic bounded behavior;
- explicit generation/version checks to detect races between snapshot read and authority invalidation.

If an authority changes in a way that invalidates the loaded snapshot before approval can be proven, fail closed rather than approve against ambiguous state.

## 18. Native-code escalation rule

Python is the first implementation target because current `RiskGateV2` is Python and preserving proven authority is safer than an immediate rewrite.

Rust/C++/native hot-kernel work is permitted only if benchmark evidence shows the Python implementation cannot satisfy the approved `RiskGateLatencyPolicy` on qualified hardware/runtime profiles.

Even then:

- `RiskGateV2` authority semantics remain unchanged;
- native code is a deterministic compute adapter, not a second RiskGate;
- identical safety/contract/golden tests apply;
- audit remains outside any unsafe bypass;
- promotion requires evidence, not intuition.

## 19. Qualification gates

Before calling the fast path verified:

1. existing RiskGate authority tests remain green;
2. INV-16 audit failure test proves no `ApprovedOrder` on audit failure;
3. options BUY-only remains green;
4. intent expiry/replay/duplicate guards remain green;
5. stale/missing/mismatched snapshot tests fail closed;
6. builder crash/stale tests feed existing `FailureIncident` + operational state + alert path;
7. no slow fallback is reachable from candidate hot path;
8. policy values are loaded from versioned `RiskGateLatencyPolicy`, not hardcoded production numbers;
9. Paper/Shadow benchmark produces code-SHA-bound latency distributions;
10. concurrent publication/read tests prove no partial snapshot observation;
11. full regression remains green;
12. Live remains `READ_ONLY / DISARMED` and no real broker mutation path is introduced.

## 20. Out of scope

- enabling or arming Live;
- real-money autonomous execution;
- adding a real broker mutation route;
- weakening/removing synchronous mandatory audit-before-approval;
- Laya/AI becoming execution authority;
- market prediction changes;
- strategy logic changes;
- hardcoding guessed production latency/freshness/slippage/storm thresholds;
- a second incident/monitor/alert system;
- a big-bang RiskGate rewrite.

## 21. Final approved decision

AlgoFortis will use **Precompute -> Immutable Atomic RiskSnapshot -> Deterministic RiskGateV2 Delta Fast Path -> Mandatory Minimal Audit -> ApprovedOrder -> Warm Paper/Shadow Handoff**.

Latency targets are governed by a versioned `RiskGateLatencyPolicy` calibrated from benchmark evidence. Audit-write failure always blocks under INV-16. Snapshot-builder failure is routed through the existing Phase-5 operational state, `FailureIncident`, audit and alert architecture. There is no slow fallback in the hot path, no RiskGate bypass, and Live remains `READ_ONLY / DISARMED`.