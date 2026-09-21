# AlgoFortis V2 — Phase 0 V1 Audit Report

**Audit status:** COMPLETE FOR G0 BASELINE  
**Date:** 2026-09-21  
**Audited branch:** `v2-phase0-baseline-audit`  
**Verified source head:** `b173d2454eeab52ffd61ed4f86afae360d768b39`  
**Verification run:** GitHub Actions run `35547332775` — SUCCESS

## 1. Audit objective

Establish whether current V1 is a safe, reproducible baseline that V2 can extend without a rewrite. Phase 0 intentionally does not change production engine behavior.

## 2. Scope reviewed

The audit inspected and mapped the current authorities for:

- numeric/fixed-point handling;
- RiskGate and risk policies;
- signal intake and non-executable order requests;
- order lifecycle;
- audit/event evidence;
- reproducibility/source/dependency/market-data identities;
- strategy interface;
- protective logic;
- paper execution boundaries;
- broker adapters and reconciliation/restart foundations;
- data feeds and historical-data inventory;
- auth/device/session/security foundations;
- live-readiness mutation boundary;
- build/release/certification tooling.

The resulting contract map is in `V1_CONTRACT_FREEZE.md`; V1→V2 gaps are in `V1_GAP_REGISTER.md`; data findings are in `DATA_PROVENANCE_AUDIT.md`.

## 3. Fresh current-head verification

A hardened pull-request workflow checked out the exact PR head and ran on two independent clean Windows environments with exact CPython 3.13.14.

### Environment A

- Windows Server 2025 Datacenter, build 26100.
- Exact source head: `b173d2454eeab52ffd61ed4f86afae360d768b39`.
- `python -m pytest tests_v1 -q`: **209 passed**, 1 non-failing deprecation warning.
- Existing architectural regression certification: **13/13 passed**, `ALL PASS`.
- Deterministic golden probe: PASS.

### Environment B

- Windows Server 2022 Datacenter, build 20348.
- Exact source head: `b173d2454eeab52ffd61ed4f86afae360d768b39`.
- `python -m pytest tests_v1 -q`: **209 passed**, 1 non-failing deprecation warning.
- Existing architectural regression certification: **13/13 passed**, `ALL PASS`.
- Deterministic golden probe: PASS.

### Cross-environment deterministic evidence

Both environments emitted exactly the same fingerprints:

- Market-data fingerprint: `7620420d3bbe9c3dc805947f86d31e64ec6214f43441edc2844ded1f112e0c35`
- Runtime-config fingerprint: `6e9168409c73254f8d38ff92025929ed6ebfa104d5150696fdc75ac03efef616`

This satisfies the Phase 0 requirement to prove deterministic baseline evidence on two clean environments for the captured deterministic components.

## 4. Safety findings

### Preserved hard baseline

Current source inspection confirms the live-readiness authority remains READ_ONLY/SHADOW: mutation is not allowed and the live-mutation guard fails closed. No Phase 0 production code changed this behavior.

### Production diff boundary

The Phase 0 branch changes only:

- V2/Phase 0 documentation and ADRs;
- the non-mutating verification workflow;
- a test-only dependency closure (`requirements-test.in`);
- Owner Decision documentation.

No production engine/business-logic source file was modified during Phase 0.

## 5. V1→V2 gaps confirmed

These are planned V2 structural extensions, not current V1 release defects:

1. Formal RiskGate-only `ApprovedOrder` capability is absent.
2. Formal order `IN_DOUBT` state/no-blind-retry contract is absent.
3. Complete Clock/SeedSource/IdGenerator injection coverage is not yet proven.
4. Module-boundary CI enforcement is not yet a protected repository merge gate.
5. Full immutable V2 dataset catalog with version/provenance/lineage/licence/quality metadata is absent.
6. Full V2 Strategy SDK manifest/lifecycle/promotion evidence layer is absent.
7. AI V2 contracts/tool gateway/shadow evaluation are future Phase 8 work.

## 6. Data/provenance ruling

V1 already has strong exact-file SHA-256 validation, local historical inventory hashes, coverage/gap metadata and canonical market-data fingerprints. The private source repository does not contain the user's production historical-data corpus, so this audit does not invent or certify multi-year NIFTY/BANKNIFTY dataset coverage from GitHub.

The missing universal dataset version/provenance/licence catalog is recorded as V2 gap G-006 for Phase 3 and is not a P0/P1 defect in the frozen V1 baseline.

## 7. Defect severity result

- **Open P0:** 0 observed.
- **Open P1:** 0 observed.
- **P2/non-blocking maintenance:** Starlette/AnyIO test-client deprecation warning; GitHub-hosted Actions report Node-runtime deprecation notices for upstream checkout/setup actions. Neither caused a failed V1 test or changed engine safety behavior in this audit.

A future verification failure or newly discovered safety bypass reopens the gate immediately; this report is not permission to weaken invariants.

## 8. G0 audit conclusion

The current V1 source and fresh verification evidence support using V1 as the frozen starting baseline for V2. Known V2 gaps have explicit destinations and do not require a big-bang rewrite.

`READ_ONLY=true`, `DISARMED=true` and zero authorized live broker mutation remain mandatory throughout the non-live V2 build and qualification work.
