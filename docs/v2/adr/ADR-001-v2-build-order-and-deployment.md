# ADR-001 — V2 Build Order and Deployment Authority

**Status:** Accepted  
**Date:** 2026-09-21  
**Owner decisions:** OD-V2-01, OD-V2-02, OD-V2-03

## Context

AlgoFortis had multiple planning vocabularies: the master checklist A–I structure, earlier P0–P10 material, and the revised Phase 0–10 implementation plan. Running more than one build order creates ambiguous dependencies and agent drift. The existing product trust boundary is also local-first: trading engines/state/secrets stay local while cloud services are limited to account/device/entitlement authority.

## Decision

1. `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md` Phase 0–10 is the canonical trading-core build order.
2. Earlier plans/checklists remain source/traceability material and are mapped into the canonical phases; they do not independently choose implementation order.
3. V2.0 is local-first. Hosted trading execution is not a V2.0 deployment model and remains a future seam.
4. V2.0 completion means all T0 + T1 requirements, except only explicitly documented Owner-approved exceptions. T2 is architecture/seam scope only.
5. Live mutation remains READ_ONLY/DISARMED through qualification; this ADR does not authorize real-money execution.

## Consequences

- Coding work is issued as bounded slices from one phase map.
- Existing V1 modules are wrapped/migrated, not rewritten for style.
- Cloud outages cannot loosen local safety.
- Broker credentials/trade state remain local.
- G0 must finish before Phase 1 begins.

## Traceability

- `ALGOFORTIS_V2_OWNER_DECISIONS.md`: OD-V2-01/02/03.
- `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`: canonical Phase 0–10 map.
- `ALGOFORTIS_V2_REQUIREMENTS.md`: T0/T1/T2 definitions.
