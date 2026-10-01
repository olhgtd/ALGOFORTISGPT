# AlgoFortis V2 Canonical Document Status

**Status:** CURRENT GOVERNANCE MAP  
**Date:** 2026-10-02  
**Purpose:** Remove ambiguity between historical/baseline document headers and later frozen Owner Decisions, ADRs, phase freezes, and qualification evidence.

## Controlling precedence

When two documents appear to conflict, use this order:

1. `ALGOFORTIS_V2_OWNER_DECISIONS.md` frozen Owner Decisions and dated corrections.
2. Accepted/frozen ADRs and dated phase decision-freeze documents referenced by those Owner Decisions.
3. Owner-approved dated design specifications under `docs/superpowers/specs/`.
4. `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md` for the Phase 0-10 build order after OD-V2-01 was frozen.
5. Phase qualification evidence for what a specific exact commit actually proved.
6. Older root architecture/requirements/test-plan headers and historical V1/V2 baseline documents as background only where later authorities supersede them.

A stale `DRAFT` or `PROPOSED` header in an older baseline document does **not** reopen a later frozen Owner Decision.

## Current plan status

OD-V2-01 is frozen in `ALGOFORTIS_V2_OWNER_DECISIONS.md`. Therefore the revised Phase 0-10 implementation plan is the canonical build order even though the implementation-plan file still carries an older baseline header saying it becomes canonical when OD-V2-01 is frozen.

The root `ALGOFORTIS_V2_ARCHITECTURE.md`, `ALGOFORTIS_V2_REQUIREMENTS.md`, and `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` began as v0.1 baseline documents. Their older status headers are historical metadata; later frozen ODs/ADRs and dated correction documents control where they differ.

## AI / Laya status

The original G8 evidence and `engine/ai/v2/evidence.py` preserve the exact historical Phase-8 qualification markers that were valid for that older exact head. Do not rewrite those historical fingerprints merely to make their wording look current.

For current research/backtest/paper AI/Laya architecture, the controlling authorities are:

- `docs/v2/phase8/PHASE8_DECISION_FREEZE.md` as amended 2026-10-01;
- `docs/superpowers/specs/2026-10-01-ai-laya-decision-intelligence-architecture.md`;
- the later exact-head AI/Laya qualification evidence.

Current design permits optional `0..N` AI providers and optional Laya as a first-class Market Intelligence Engine in research/backtest/paper workflows. Historical G8 strings such as `PROVIDER_SCOPE=ONE_LOCAL_ONE_CLOUD` remain historical evidence, not the current architecture policy.

## Safety authorities that remain unchanged

- `RiskGateV2` is the sole `ApprovedOrder` authority.
- Portfolio/accounting authority remains in the existing portfolio layer.
- S2 `DeviceSessionGate` remains identity/session authority.
- Existing Owner/Admin authority owns global configuration.
- Live remains `READ_ONLY/DISARMED` in the current qualified product.
- AI/Laya does not directly mint executable orders.
- No real-money broker mutation is enabled by the AI/Laya redesign or this governance map.

## Historical product naming

The current product name is **AlgoFortis**. `SentinelX` may remain in explicitly historical V1 artifacts, compatibility seams, old evidence identifiers, or legacy filenames where renaming would destroy provenance or compatibility. New current-product documentation and user-facing instructions should use AlgoFortis.
