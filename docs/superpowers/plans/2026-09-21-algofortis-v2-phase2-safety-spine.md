# AlgoFortis V2 Phase 2 Safety Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the single, testable path from an entry intent through the central Risk Gate to a capability-bearing approved order, while proving the Phase 2 safety invariants without enabling real broker mutation.

**Architecture:** Extend the frozen V1 risk/order foundations through additive V2 contracts. `ApprovedOrder` is an opaque capability issued only by the V2 Risk Gate; lifecycle, mode isolation, kill-switch semantics, audit fail-closed behavior, and no-auto-arm are layered around that authority. Real broker mutation remains unreachable because Phase 2 is qualification-only and live stays READ_ONLY/DISARMED.

**Tech Stack:** Python 3.13.14, dataclasses/enums/Decimal, existing AlgoFortis audit/runtime/config foundations, pytest 9.1.1, GitHub Actions dual-Windows verification.

**Spec:** `ALGOFORTIS_V2_REQUIREMENTS.md`, `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`, `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`, `docs/v2/adr/ADR-010-phase2-kill-switch-semantics.md`

## Global Constraints

- Preserve V1 behavior unless a V2 contract explicitly wraps it; no big-bang rewrite.
- Money, price, quantity and risk use Decimal/fixed-point semantics.
- Live remains `READ_ONLY=true`, `DISARMED=true`; zero real broker mutation is introduced in Phase 2.
- `ApprovedOrder` may be created only by the central Risk Gate (INV-03).
- Options scope remains BUY-only at the gate (INV-17).
- Backtest and paper must remain structurally unable to reach live broker mutation (INV-05/06).
- IN_DOUBT is never blindly retried (INV-08).
- No restart/crash/reconnect/update/outage auto-arms live (INV-15).
- Trading-critical actions fail closed if required audit evidence cannot be written (INV-16).
- Standard Emergency Stop = HALT_ENTRIES + CANCEL_PENDING(entries); protective exits remain active; FLATTEN_ALL is separate and explicit.

## Review Focus

1. Capability forgery: callers must not be able to construct a valid `ApprovedOrder` directly.
2. Entry/protective classification: kill-switch and gate logic must not accidentally block/cancel protective exits.
3. Duplicate/stale intent identity: retry/restart paths must not produce a second executable approval.
4. IN_DOUBT resolution: lifecycle must require broker-truth resolution before terminal retry/transition.
5. Audit failure: every state-changing trading-critical action must remain unchanged when its audit write fails.

---

### Task 1: ApprovedOrder capability and Risk Gate authority

**Files:**
- Create: `engine/risk/approval.py`
- Create: `tests_v1/test_v2_phase2_risk_gate_authority.py`
- Modify only if needed: `engine/risk/__init__.py`

**Interfaces:**
- Consumes: existing V1 `RiskGate`, `RiskDecision`, order intent/model types, Phase-1 audit/runtime primitives.
- Produces: `OrderIntent`, `ApprovedOrder`, `RiskGateV2`, `RiskRejection`; only `RiskGateV2.evaluate_entry()` can mint a valid approval capability.

- [ ] Write RED tests proving direct `ApprovedOrder(...)` construction is rejected; an approved BUY entry can be minted only through the gate; rejected risk never yields an approval; approval carries intent ID, risk-rule version and deterministic approval ID; audit failure blocks approval.
- [ ] Run focused test and capture expected RED because `engine.risk.approval` is absent.
- [ ] Implement the minimal additive V2 capability module without rewriting V1 `risk_manager.py`.
- [ ] Run focused test GREEN, then full `tests_v1` regression and architecture/golden checks.
- [ ] Commit implementation only after exact-head verification.

### Task 2: Hard-limit hierarchy and options BUY-only

**Files:**
- Create: `engine/risk/limits.py`
- Create: `tests_v1/test_v2_phase2_hard_limits.py`
- Extend: `engine/risk/approval.py`

**Interfaces:**
- Consumes: `RiskGateV2`, `OrderIntent`.
- Produces: immutable `HardLimitHierarchy` and deterministic limit decision evidence.

- [ ] RED tests for platform > owner > user > strategy > run monotonic limits; lower layers cannot widen higher limits; malformed/missing limits fail closed.
- [ ] RED tests enforce option entry side BUY-only at the gate while protective exit intents remain separately classified.
- [ ] Implement Decimal-safe hierarchy resolution and integrate it into `RiskGateV2`.
- [ ] Verify INV-11 and INV-17 focused GREEN plus full regression.

### Task 3: Duplicate and stale-intent suppression

**Files:**
- Create: `engine/orders/intent_guard.py`
- Create: `tests_v1/test_v2_phase2_intent_guard.py`

**Interfaces:**
- Consumes: approved intent identity and injected Clock.
- Produces: deterministic intent acceptance/rejection with idempotent identity tracking.

- [ ] RED tests for same intent ID duplicate, same client-order identity replay, expired/stale intent, restart-restored consumed identity and deterministic reason codes.
- [ ] Implement fail-closed guard with no broker calls.
- [ ] Verify INV-01/INV-02 focused GREEN plus full regression.

### Task 4: Order lifecycle and IN_DOUBT

**Files:**
- Extend additively: `engine/orders/lifecycle.py` or create `engine/orders/lifecycle_v2.py` if preserving V1 requires isolation.
- Create: `tests_v1/test_v2_phase2_order_lifecycle.py`

**Interfaces:**
- Consumes: `ApprovedOrder`, broker-truth resolution result.
- Produces: versioned lifecycle transition authority including IN_DOUBT.

- [ ] RED tests enumerate legal/illegal transitions; SENT-without-ack enters IN_DOUBT; IN_DOUBT cannot transition through blind retry; only explicit broker-truth resolution can resolve it.
- [ ] Implement state transition table and immutable transition evidence.
- [ ] Verify INV-07/INV-08 focused GREEN plus full regression.

### Task 5: Mode isolation, broker port and paper conformance shell

**Files:**
- Create: `engine/broker_contract/port_v2.py`
- Create: `engine/broker_contract/conformance_v2.py`
- Create: `tests_v1/test_v2_phase2_mode_isolation.py`
- Reuse/extend the existing paper adapter only through the new port.

**Interfaces:**
- Consumes: `ApprovedOrder` and lifecycle contract.
- Produces: broker-neutral port contract and paper conformance test-kit.

- [ ] RED tests prove backtest cannot import/load a live mutation implementation, paper cannot receive real broker credentials/mutation adapter, and paper adapter passes the broker-neutral contract shell.
- [ ] Implement structural mode binding at process/adapter construction time.
- [ ] Verify INV-05/INV-06 focused GREEN plus module-boundary gate/full regression.

### Task 6: Live engine state machine and no-auto-arm latch

**Files:**
- Create: `engine/live/state_machine_v2.py`
- Create: `tests_v1/test_v2_phase2_live_state_machine.py`

**Interfaces:**
- Produces states DISABLED, READY, CONNECTING, ACTIVE, DEGRADED, PAUSED, EMERGENCY_STOP, RECOVERY and explicit transition events.

- [ ] RED tests cover all legal transitions and representative illegal transitions.
- [ ] RED tests prove restart, crash recovery, reconnect and RECOVERY never auto-transition to ACTIVE; explicit arm authority is required and remains disabled in Phase 2 runtime configuration.
- [ ] Implement transition table with audit-before-state semantics.
- [ ] Verify INV-07/INV-15 focused GREEN plus full regression.

### Task 7: Kill-switch contract and audit fail-closed

**Files:**
- Create: `engine/risk/kill_switch.py`
- Create: `tests_v1/test_v2_phase2_kill_switch.py`
- Extend state machine/gate only through narrow interfaces.

**Interfaces:**
- Consumes ADR-010 semantics.
- Produces `HALT_ENTRIES`, `CANCEL_PENDING`, `FLATTEN_ALL` domain commands and `EmergencyStop` orchestration evidence.

- [ ] RED tests prove Emergency Stop halts entries + cancels pending entry orders, preserves protective exits, never implies FLATTEN_ALL, and reconciliation mismatch maps to halt+alert.
- [ ] RED tests inject audit sink failure and prove gate/state/kill-switch mutation is blocked.
- [ ] Implement command semantics and audit-before-mutation guard.
- [ ] Verify INV-16 and LIV-010 behavior plus full regression.

### Task 8: Phase 2 invariant CI and G2 evidence

**Files:**
- Create: `build/tools/check_phase2_safety_spine.py`
- Update: `.github/workflows/v2-phase0-baseline.yml` or successor workflow name to include Phase-2 gates.
- Create: `docs/v2/phase2/G2_EVIDENCE.md`

**Interfaces:**
- Consumes all Phase-2 focused test files and frozen Phase-0/1 golden checks.

- [ ] Add focused CI gate covering INV-01, 02, 03, 05, 06, 07, 08, 11, 15, 16, 17.
- [ ] Keep compile, module-boundary, static foundation, full regression, architecture certification and golden checks on both Windows environments.
- [ ] Run exact-head dual-Windows qualification.
- [ ] Record exact test counts, hashes, workflow run IDs and G2 criterion evidence.
- [ ] Phase 2 is complete only when the evidence commit itself receives a fresh exact-head dual-Windows GREEN run.
