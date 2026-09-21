# AlgoFortis V2 — Phase 0 Golden Regression Baseline

**Status:** DEFINITION FROZEN; EXECUTION EVIDENCE PENDING  
**Date:** 2026-09-21

## Purpose

Freeze what V2 must preserve before production behavior changes begin. A golden update is an explicit reviewed event; expected outputs are never silently rewritten to match new code.

## Existing deterministic authorities selected for golden capture

### GOL-01 — Reproducibility manifest

Authority: `engine/reproducibility/model.py::ReproducibilityManifest.manifest_fingerprint`.

Inputs include source identity, market-data snapshot, runtime configuration, runtime identity, dependency closure and execution/cost/validation/randomness policy identities.

**Expected comparison:** exact fingerprint equality.

### GOL-02 — Market-data snapshot

Authority: `engine/reproducibility/market_data.py::MarketDataSnapshot.fingerprint` and child stream fingerprints.

Economic bar fields are normalized through Decimal before canonical fingerprinting.

**Expected comparison:** exact fingerprint equality.

### GOL-03 — Risk policy/decision evidence

Authority: `engine/risk/risk_manager.py` and its existing deterministic/canonical policy/result evidence.

Representative cases must include approved and fail-closed rejected decisions, including missing/invalid risk evidence.

**Expected comparison:** exact fixed-point values, reason codes and canonical identities.

### GOL-04 — Order lifecycle trace

Authority: `engine/orders/lifecycle.py`.

Representative V1 trace freezes the current meanings of CREATED → VALIDATED → QUEUED → terminal states plus cause-reference/event identities.

**Expected comparison:** exact state/cause identities. V2 may add a versioned lifecycle for submission/ack/IN_DOUBT, but it must not silently reinterpret this V1 trace.

### GOL-05 — Audit envelope/event identity

Authority: `engine/audit/model.py` plus durable audit sink/log behavior.

Representative events: signal/intent, risk decision, order lifecycle, fill/accounting, protective lifecycle, safety/restart/fail-closed evidence.

**Expected comparison:** exact schema/event-family/event-type and canonical deterministic IDs where the event class is deterministic. Observation UUIDs are compared by schema/semantics, not literal random UUID value.

### GOL-06 — Strategy interface compatibility

Authority: `engine/strategy/base.py` interface version `1.0`, Signal action vocabulary and state schema behavior.

**Expected comparison:** existing V1 strategies continue to satisfy the frozen v1 interface after V2 SDK wrapping.

### GOL-07 — Live fail-closed boundary

Authority: `dashboard/backend/live_readiness_service.py`.

Required golden safety assertions:

- `execution_boundary("LIVE")` reports `arming_state=READ_ONLY`.
- `mutation_allowed` is `False`.
- `require_live_mutation()` raises `LiveExecutionDisabled`.
- No Phase 0/V2 foundation change introduces automatic arming or broker mutation.

**Expected comparison:** exact safety behavior; any weakening is P0.

## Cross-environment evidence rule

- Run deterministic golden cases on at least two clean Windows runners using Python 3.13 and the locked dependency closure.
- Fixed-point/canonical fingerprints must match exactly.
- Analytics float outputs may differ only within the explicit tolerance governed by ADR-008.
- Environment-specific paths/timestamps are excluded from a deterministic fingerprint unless the contract explicitly defines them as identity.

## Current evidence status

- Historical V1 RC test evidence exists but is not the current golden execution.
- Phase 0 CI now defines two independent clean Windows/Python 3.13 runner jobs.
- Current-head full regression and golden fingerprint capture are not marked PASS until fresh run evidence exists.

## Golden change control

Any intentional changed golden output requires:

1. linked requirement/ADR;
2. explanation of changed behavior and compatibility impact;
3. RED→GREEN test evidence for production-code behavior changes;
4. before/after golden identities;
5. explicit confirmation that READ_ONLY/DISARMED and risk/audit invariants are not weakened.
