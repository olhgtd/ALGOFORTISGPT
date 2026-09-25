# AlgoFortis V2 — Phase 5 Paper V2, Reconciliation & Recovery Design

**Status:** DESIGN APPROVED — implementation not started  
**Date:** 2026-09-25  
**Branch:** `v2-phase5-paper-recovery`  
**Phase:** 5 — Paper V2, Reconciliation & Recovery  
**Exit gate:** G5  
**Blocking owner decisions:** OD-V2-19 and OD-V2-24 — FROZEN  
**Safety baseline:** Live remains `READ_ONLY/DISARMED`; Phase 5 introduces no real-broker mutation path.

## 1. Purpose

Phase 5 hardens the existing AlgoFortis paper-trading stack so paper execution behaves conservatively like live execution semantics, survives failures, reconciles state after uncertainty, produces deterministic recovery evidence, and starts the long-running paper-soak clock required by G5.

This phase follows the V2 no-big-bang-rewrite rule. Existing `engine/paper/`, `engine/reconciliation/paper/`, persistence, risk, audit, option-selection, and broker-contract infrastructure is reused behind explicit contracts. New behavior is added through focused modules and small integration seams rather than expanding already-large coordinator/store files.

## 2. Non-negotiable safety invariants

1. Paper can never reach a real broker mutation path.
2. Live stays `READ_ONLY/DISARMED`; no Phase-5 code may create an arming route.
3. No executable path bypasses the existing RiskGate/ApprovedOrder authority.
4. No duplicate logical submission after restart/recovery.
5. No stale signal or intent replay after restart, disconnect, delayed acknowledgement, rollover, or recovery.
6. `IN_DOUBT`/uncertain submission state is reconciled before any retry; never blindly retried.
7. Recovery and reconciliation take precedence over retries and new entries.
8. Reconciliation CLEAN is necessary but not sufficient for resume; protective integrity and health checks remain independent gates.
9. A sticky safety halt cannot clear automatically. `READY_FOR_RESUME` still requires explicit manual resume.
10. Missing, invalid, corrupt, or unsupported safety policy fails closed.
11. Critical alert-channel failure cannot weaken trading safety.
12. No guessed production numeric storm thresholds, clock-drift thresholds, promotion tolerances, or hardware minima are embedded in code.

## 3. Approved architecture approach

Phase 5 uses **Approach A: harden/extend the existing Paper engine through V2 contracts**.

High-level execution flow:

```text
Live/Replay Market Data
        ↓
Strategy + Option Selector
        ↓
RiskGate
        ↓
Approved Paper Intent
        ↓
PaperExecutionAdapter
        ↓
PaperFillSimulator
        ↓
Order / Position State
        ↓
Persistence + Reconciliation + Recovery Evidence
```

There is no Paper → real-broker mutation edge.

## 4. Operational state model

Canonical operational states:

```text
HEALTHY
DEGRADED
HALTED
RECOVERY
READY_FOR_RESUME
```

Canonical action/state distinction:

- `HALT_ENTRIES` is a safety **action**.
- `HALTED` is the resulting sticky operational **state**.

### 4.1 Branching transitions

The state model is branching, not linear.

State-continuity uncertainty can jump directly to RECOVERY:

```text
HEALTHY → RECOVERY
```

Typical direct-RECOVERY triggers include:

- process crash;
- restart with unresolved/open state;
- sleep/resume discontinuity;
- uncertain submission acknowledgement;
- partial-state uncertainty after disconnect.

Runtime degradation while state remains trustworthy may instead enter DEGRADED:

```text
HEALTHY → DEGRADED
```

Examples include transient feed latency, recoverable connectivity degradation, or a failure count below a versioned storm threshold.

When a sticky safety condition is reached:

```text
DEGRADED/HEALTHY
      ↓
HALT_ENTRIES
      ↓
HALTED
```

If continuity later becomes uncertain:

```text
DEGRADED/HALTED → RECOVERY
```

After automated recovery checks pass:

```text
RECOVERY/HALTED
      ↓
READY_FOR_RESUME
      ↓ explicit manual resume
HEALTHY
```

`HALTED` never silently clears itself.

## 5. Recovery sequence

Generalized failure routing starts from **ANY FAILURE / SAFETY TRIGGER**, not only restart events.

Recovery authority:

```text
Failure detected
   ↓
Classify severity + state uncertainty
   ↓
DEGRADED / HALT_ENTRIES→HALTED / RECOVERY
   ↓
Restore persisted owned state when required
   ↓
Reconcile expected vs observed state
   ↓
Protective-state integrity check
   ↓
Feed health
   ↓
Clock health
   ↓
Session / expiry / instrument validity
   ↓
All required checks GREEN
   ↓
READY_FOR_RESUME
   ↓
Explicit manual resume
   ↓
HEALTHY
```

### 5.1 Reconciliation and protective integrity are decoupled

A CLEAN reconciliation only proves compared state agrees. It does not prove protective exits are valid.

If reconciliation is CLEAN but protective state is missing, invalid, or uncertain:

```text
HALT_ENTRIES
→ HALTED
→ critical alert
→ recovery evidence
```

Normal paper entries remain blocked.

### 5.2 Retry permission

Reconnect alone never restores submission/retry permission after uncertainty. A fresh reconciliation cycle is required. Safety-triggered HALTED state additionally requires manual resume even after all automated checks become green.

Low-level transient retry/backoff that never triggered the safety latch may recover automatically according to its versioned policy.

## 6. Session and expiry boundaries

At day/session rollover:

- stale pending entry intents expire;
- previous-session signals are never replayed;
- open-position state remains explicit;
- expiry/session rules are re-evaluated;
- rollover emits audit evidence.

For an open option position approaching expiry, Phase 5 never invents an auto-flatten or silent-carry rule. A versioned instrument/session/expiry policy must explicitly define the allowed outcome. Missing or invalid policy causes halt + alert. Expired contracts cannot receive fresh entries.

## 7. Persistence model

Persisted state is **owned expectation**, not automatically current truth. Reconciliation determines whether the current observed/simulated state agrees with that expectation.

Core Phase-5 records:

### 7.1 `PaperSession`

- `session_id`
- `mode = PAPER`
- `started_at`
- `trading_date`
- `session_state`
- `config_snapshot_ref`
- `strategy_versions`
- `risk_policy_version`
- `instrument_master_version`
- `failure_policy_version`

### 7.2 `PaperOrderRecord`

- `logical_intent_id`
- `approved_order_id`
- instrument / side / quantity
- lifecycle state
- cumulative fill
- submit/observe timestamps
- last observation sequence
- terminal reason

### 7.3 `PaperPositionRecord`

- `position_id`
- instrument / quantity / average price
- realized / unrealized P&L
- `protective_policy_ref`
- protective state
- expiry/session metadata

### 7.4 `RecoveryCheckpoint`

- `checkpoint_id`
- `session_id`
- `persisted_at`
- `last_event_sequence`
- owned open-order/open-position references
- `recovery_required`
- reason
- checksum/fingerprint

### 7.5 `FailureIncident`

The approved field set explicitly includes the Section-4 traceability fields:

- `incident_id`
- `failure_type`
- `severity`
- `detected_at`
- `source`
- `affected_scope`
- `previous_state`
- `resulting_state`
- `transition_reason`
- `halt_latched`
- `recovery_id` (nullable)
- `storm_policy_ref` (nullable when not applicable)
- `resolved_at`
- `resolution_evidence`

### 7.6 `AlertDeliveryRecord`

- `alert_id`
- `incident_id`
- channel
- attempt
- delivery status
- failure reason
- timestamps

## 8. Failure-storm policy

Storm detection is configuration-driven and versioned.

`FailureStormPolicy` contains:

- `policy_id`
- `version`
- `failure_class`
- `observation_window`
- `trigger_count`
- `cooldown`
- `escalation_action`
- `reset_rule`

Failure classes may include order rejection, rate limit, transport error, feed stale, and repeated strategy/runtime failure.

No production constant such as “N failures in M seconds” is guessed in Phase 5. Tests may use explicit `TEST_ONLY` policies. Missing/corrupt required storm policy must not permit unlimited retries; it fails closed through DEGRADED/HALTED behavior plus audit/alert evidence.

## 9. Incident severity

Canonical severity categories:

- `INFO` — no trading-safety impact.
- `WARNING` — degraded but state remains trustworthy.
- `CRITICAL` — new entries halted.
- `RECOVERY_REQUIRED` — owned state continuity/truth is uncertain and recovery is required.

Typical `RECOVERY_REQUIRED` examples include crash, restart with open state, uncertain acknowledgement, and partial state after disconnect.

## 10. Alert architecture

Per ADR-014 / OD-V2-19, critical alerts use two required independent delivery paths:

1. local on-screen / Windows-visible alert;
2. Telegram remote alert.

Email is an optional third adapter and is not required for G5.

Rules:

- adapters share a versioned alert contract;
- delivery attempts are independent;
- failure of one required channel must not suppress the other;
- paper safety never depends on Telegram availability;
- alert payloads are minimal/redacted and exclude credentials, tokens, raw account identifiers, secrets, and unrestricted trade logs;
- alert-delivery failure is itself audited/observable;
- the future dead-PC/engine-silent heartbeat is deferred until telemetry/privacy OD-V2-22.

## 11. Host resilience

Per ADR-013 / OD-V2-24:

- Windows 11 x64 is the first-class qualification target;
- one trading-engine instance per local profile/machine context;
- active Paper/future Live sessions request sleep/hibernate prevention without permanently modifying OS power-plan settings;
- detected resume discontinuity forces RECOVERY before new entries can resume;
- watchdog restart target is RECOVERY only, never armed/active;
- clock health is injected/versioned and fails closed when missing/invalid/exceeded;
- no production drift threshold is invented before evidence exists;
- hardware minimums are evidence-derived, not guessed;
- antivirus/Windows security need not be disabled;
- host-recovery safety always precedes retry/new-entry behavior.

## 12. Module boundaries and proposed file layout

### 12.1 Paper domain/orchestration

```text
engine/paper/
├── contracts_v2.py
├── execution_adapter_v2.py
├── fill_simulator_v2.py
├── operational_state_v2.py
├── failure_policy_v2.py
├── protective_integrity_v2.py
├── recovery_coordinator_v2.py
├── drift_report_v2.py
├── evidence_v2.py
└── session_v2.py
```

Responsibilities:

- `contracts_v2.py`: pure domain records and enums only; no SQLite, Telegram, Windows API, broker SDK.
- `execution_adapter_v2.py`: paper-only execution boundary after approval.
- `fill_simulator_v2.py`: deterministic bid/ask execution, latency, slippage, rejection/disconnect simulation.
- `operational_state_v2.py`: canonical operational states, transition table, `HALT_ENTRIES` semantics, manual resume latch.
- `failure_policy_v2.py`: storm policy and threshold evaluation; no guessed production constants.
- `protective_integrity_v2.py`: independent `VALID/INVALID/UNCERTAIN` protective-state authority.
- `recovery_coordinator_v2.py`: restore→reconcile→protective→health→validity orchestration; does not own persistence implementation or alert adapter implementation.
- `session_v2.py`: thin Phase-5 session authority and wiring.
- `drift_report_v2.py` / `evidence_v2.py`: immutable/versioned evidence generation.

### 12.2 Reconciliation

Existing authority remains under:

```text
engine/reconciliation/paper/
```

Only minimal V2 contracts/views are added when required. Paper orchestration consumes reconciliation verdicts; it does not implement a competing reconciliation engine.

### 12.3 Persistence

Proposed focused repositories:

```text
engine/persistence/
├── paper_session_store_v2.py
├── paper_recovery_store_v2.py
└── paper_incident_store_v2.py
```

Existing `schema.py`, `migrations.py`, and `sqlite_store.py` receive only the smallest required integration. Persistence reports stored state; recovery domain logic decides what that state means.

### 12.4 Host adapters

```text
engine/host/
├── __init__.py
├── instance_lock.py
├── clock_health.py
├── power_session.py
└── watchdog_policy.py
```

Windows-specific behavior stays behind testable interfaces/fakes.

### 12.5 Alerts

```text
engine/alerts/
├── contracts.py
├── dispatcher.py
├── redaction.py
└── adapters/
    ├── windows_local.py
    └── telegram.py
```

Paper/recovery code depends on an AlertPort/Protocol, not Telegram/Windows concrete implementations.

## 13. Dependency direction

The architecture uses Protocol/interface boundaries so domain tests remain deterministic and external integrations remain adapters.

```text
Paper domain
  ↓ Protocols
Persistence / Host / Alert / Reconciliation ports
  ↓
SQLite / Windows / Telegram / existing reconciliation implementations
```

Forbidden directions include:

- paper domain → real broker mutation adapter;
- pure domain → SQLite implementation;
- recovery coordinator → Telegram/Windows concrete adapter;
- persistence → operational recovery decisions;
- host adapter → Live arm authority.

## 14. Giant-file avoidance

Phase 5 deliberately avoids expanding existing oversized files such as `engine/paper/coordinator.py` and `engine/persistence/sqlite_store.py` with substantial new behavior. They receive only minimal integration seams. Unrelated refactors are out of scope.

## 15. Paper fill behavior

Paper fills are conservative and execution-realistic:

- BUY uses executable ask-side evidence;
- SELL uses executable bid-side evidence;
- configurable slippage and signal-to-execution latency;
- stale quote rejection;
- rejection/disconnect simulation;
- impossible/unsupported fills fail closed instead of being fabricated;
- applicable cost model is included;
- deterministic test fixtures use injected clock/seed providers.

Advanced queue-position/market-impact modeling is outside this Phase-5 scope.

## 16. Recovery report

Every recovery cycle produces an immutable/versioned `RecoveryReport` containing at minimum:

- recovery id / trigger;
- previous state;
- checkpoint fingerprint;
- restored orders/positions;
- reconciliation result;
- protective-integrity result;
- feed health;
- clock health;
- session/expiry validity;
- unresolved discrepancies;
- alerts emitted;
- final state;
- manual-resume requirement.

Safety-triggered recovery keeps `manual_resume_required = true` until explicit resume.

## 17. Paper-vs-backtest drift evidence

The drift report records execution differences including expected vs paper entry time/fill, slippage, rejection, cost, exit timing, P&L delta, missed/extra trades, and session/expiry differences. Outliers require machine-readable explanations.

No production drift tolerance is invented. Tolerance remains versioned policy and is frozen from evidence under the existing promotion-governance decisions.

## 18. Failure-injection evidence

Each FI result stores:

- FI id;
- fixture/policy versions;
- starting state;
- injected event;
- expected state;
- actual state;
- duplicate-order count;
- stale-replay count;
- unresolved mismatch count;
- recovery report reference;
- alert evidence;
- PASS/FAIL.

G5 qualification includes the required paper-mode cases from the canonical Test & Release Plan, including FI-01…FI-09, FI-12…FI-14, FI-23 and FI-24 as applicable.

## 19. G5 evidence bundle

Expected structure:

```text
G5/
├── failure-injection-results/
├── recovery-reports/
├── reconciliation-evidence/
├── alert-channel-independence/
├── host-resilience/
├── session-rollover/
├── expiry-handling/
├── paper-backtest-drift/
├── deterministic-probe/
├── full-regression/
└── soak-start-record/
```

G5 is not considered passed until required failure-injection results are green, recovery reports exist, alert independence is proven, required regressions/golden checks remain green, the paper soak is started/running, and Live remains `READ_ONLY/DISARMED`.

## 20. Implementation slice order

Phase 5 implementation is decomposed into ten bounded slices:

1. **P5-01 Contracts + operational state** — records, enums, transitions, manual resume latch.
2. **P5-02 Fill simulation V2** — paper execution adapter + deterministic fill simulator.
3. **P5-03 Persistence + checkpointing** — session/order/position/checkpoint storage and migration.
4. **P5-04 Reconciliation + recovery coordinator** — existing reconciler integrated with recovery sequencing.
5. **P5-05 Protective integrity + session/expiry recovery** — independent protective gate and boundary handling.
6. **P5-06 Failure policy + storm detection** — versioned storm policy and incident recording.
7. **P5-07 Host resilience** — instance lock, sleep/resume, clock health, watchdog policy.
8. **P5-08 Independent alerts** — alert contract, redaction, Windows + Telegram independent adapters.
9. **P5-09 Drift + G5 evidence** — deterministic evidence/report generation.
10. **P5-10 Failure-injection catalogue + qualification** — required FI suite, dual-Windows qualification, soak-start evidence.

Each slice must preserve Phase 0–4 gates and standing safety invariants.

## 21. Testing strategy

Every implementation slice follows RED → minimal implementation → focused GREEN → static/architecture gates → full regression.

Proposed focused tests:

```text
tests_v1/test_phase5_operational_state.py
tests_v1/test_phase5_fill_simulator.py
tests_v1/test_phase5_persistence.py
tests_v1/test_phase5_recovery.py
tests_v1/test_phase5_protective_integrity.py
tests_v1/test_phase5_failure_policy.py
tests_v1/test_phase5_host_resilience.py
tests_v1/test_phase5_alerts.py
tests_v1/test_phase5_drift_report.py
tests_v1/test_phase5_failure_injection.py
```

Tests must use fakes/injected providers for clock, IDs, seed, Windows power/session behavior, alert delivery, and other side effects wherever practical.

## 22. Static/CI gate

Phase 5 adds a dedicated static checker such as:

```text
build/tools/check_phase5_paper_recovery.py
```

It must enforce at least:

- no real broker mutation imports from Phase-5 paper modules;
- no direct SQLite import in pure domain modules;
- no recovery-state authority in persistence modules;
- no Live arm authority in host/alert modules;
- no hardcoded guessed production storm thresholds;
- required Phase-5 files/tests pinned;
- no Phase-5 change weakens the default Live `READ_ONLY/DISARMED` state.

Final CI qualification extends the existing dual-Windows workflow with Phase-5 focused validation, deterministic recovery probe artifacts, and cross-Windows fingerprint comparison while retaining all prior Phase 0–4 checks.

## 23. Deterministic Phase-5 probe

A fixed synthetic paper-recovery fixture should emit stable ordered output such as:

```text
SESSION_FINGERPRINT=<64hex>
CHECKPOINT_FINGERPRINT=<64hex>
RECOVERY_REPORT=<64hex>
FINAL_STATE=READY_FOR_RESUME
MANUAL_RESUME_REQUIRED=true
DUPLICATE_ORDER_COUNT=0
STALE_REPLAY_COUNT=0
DEFAULT_LIVE_STATE=READ_ONLY/DISARMED
```

Both Windows qualification environments must match exactly for deterministic fields.

## 24. Out of scope / explicitly deferred

- real broker mutation or Live enablement;
- broker-account foreign-order handling and multi-device live exclusivity (Phase 6);
- production numeric storm thresholds before evidence;
- production numeric clock-drift threshold before evidence;
- remote dead-PC heartbeat before telemetry/privacy policy is frozen;
- advanced market-impact/queue-position simulation;
- guessed auto-flatten behavior at expiry;
- unrelated giant-file refactors.

## 25. Design completion criteria

This document records the owner-approved Phase-5 architecture design from Sections 1–5 of the design review. Implementation may proceed only through the documented slice order and must remain evidence-driven, fail-closed, and paper-only.

Before any Phase-5 completion claim, fresh exact-head verification is required, including focused tests, full regression, required failure-injection evidence, dual-Windows qualification, G5 evidence generation, and verification that Live remains `READ_ONLY/DISARMED`.
