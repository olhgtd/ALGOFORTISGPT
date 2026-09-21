# ADR-008 — Numeric Policy

**Status:** Accepted  
**Date:** 2026-09-21  
**Owner decision:** OD-V2-12

## Context

Trading correctness and cross-machine reproducibility are unsafe if money, price, quantity or risk calculations silently depend on binary floating-point behavior. Existing V1 risk/order code already uses `Decimal` and `engine.core.numeric` normalization extensively, so V2 should preserve and formalize that direction rather than rewrite it.

## Decision

1. Money, price, quantity and risk calculations use `Decimal`/fixed-point semantics.
2. Binary floats are permitted only for analytics where the comparison tolerance is explicitly declared and tested.
3. Rounding mode, tick-size and quantity-step rules are explicit, instrument-aware and versioned.
4. No implicit `float -> Decimal` conversion may become an economic authority.
5. Deterministic/golden fingerprints compare economic fixed-point fields exactly. Analytics float outputs use their documented tolerance.

## Consequences

- Existing `engine.core.numeric` and Decimal-based V1 behavior is preserved.
- V2 contracts such as OrderIntent, RiskDecision, ApprovedOrder projections and accounting values must follow this policy.
- Cross-machine reproducibility tests can demand exact matches for fixed-point economic state.
- Any exception requires a documented tolerance and a test proving why the value is analytical rather than economic authority.

## Traceability

- `ALGOFORTIS_V2_REQUIREMENTS.md`: AF2-ARC-006.
- `ALGOFORTIS_V2_ARCHITECTURE.md`: deterministic core / numeric policy.
- `ALGOFORTIS_V2_OWNER_DECISIONS.md`: OD-V2-12.
