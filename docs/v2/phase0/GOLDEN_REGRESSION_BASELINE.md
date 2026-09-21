# AlgoFortis V2 — Phase 0 Golden Regression Baseline

**Status:** FROZEN + EXECUTION EVIDENCE PASS  
**Date:** 2026-09-21  
**Verified source head:** `b173d2454eeab52ffd61ed4f86afae360d768b39`  
**Verification run:** GitHub Actions `35547332775` — SUCCESS

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

Representative cases include approved and fail-closed rejected decisions in the current regression suite.

**Expected comparison:** exact fixed-point values, reason codes and canonical identities.

### GOL-04 — Order lifecycle trace

Authority: `engine/orders/lifecycle.py`.

Representative V1 trace freezes the current meanings of CREATED → VALIDATED → QUEUED → terminal states plus cause-reference/event identities.

**Expected comparison:** exact state/cause identities. V2 may add a versioned lifecycle for submission/ack/IN_DOUBT, but it must not silently reinterpret this V1 trace.

### GOL-05 — Audit envelope/event identity

Authority: `engine/audit/model.py` plus durable audit sink/log behavior.

Representative events cover signal/intent, risk decision, order lifecycle, fill/accounting, protective lifecycle, safety/restart/fail-closed evidence through the frozen test suite.

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

## Cross-environment execution evidence

The hardened Phase 0 workflow checked out the exact PR head and ran on two different clean Windows images with exact CPython 3.13.14.

### Environment A

- Windows Server 2025 Datacenter, build 26100.
- Exact head: `b173d2454eeab52ffd61ed4f86afae360d768b39`.
- `tests_v1`: **209 passed**, 1 non-failing deprecation warning.
- Architectural certification: **13/13 passed**, `ALL PASS`.
- Golden probe: PASS.

### Environment B

- Windows Server 2022 Datacenter, build 20348.
- Exact head: `b173d2454eeab52ffd61ed4f86afae360d768b39`.
- `tests_v1`: **209 passed**, 1 non-failing deprecation warning.
- Architectural certification: **13/13 passed**, `ALL PASS`.
- Golden probe: PASS.

### Exact fingerprint comparison

| Deterministic artifact | Environment A | Environment B | Result |
|---|---|---|---|
| Market-data snapshot | `7620420d3bbe9c3dc805947f86d31e64ec6214f43441edc2844ded1f112e0c35` | `7620420d3bbe9c3dc805947f86d31e64ec6214f43441edc2844ded1f112e0c35` | **EXACT MATCH** |
| Runtime configuration | `6e9168409c73254f8d38ff92025929ed6ebfa104d5150696fdc75ac03efef616` | `6e9168409c73254f8d38ff92025929ed6ebfa104d5150696fdc75ac03efef616` | **EXACT MATCH** |

This is the frozen Phase 0 deterministic evidence for the captured components. Later V2 phases expand the golden set rather than replacing this evidence silently.

## Cross-environment evidence rule going forward

- Deterministic golden cases run on at least two clean environments using the locked runtime/dependency closure.
- Fixed-point/canonical fingerprints match exactly.
- Analytics float outputs may differ only within the explicit tolerance governed by ADR-008.
- Environment-specific paths/timestamps are excluded from a deterministic fingerprint unless the contract explicitly defines them as identity.

## Golden change control

Any intentional changed golden output requires:

1. linked requirement/ADR;
2. explanation of changed behavior and compatibility impact;
3. RED→GREEN test evidence for production-code behavior changes;
4. before/after golden identities;
5. explicit confirmation that READ_ONLY/DISARMED and risk/audit invariants are not weakened.
