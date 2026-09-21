# AlgoFortis V2 — Phase 0 Gap Register

**Status:** IN PROGRESS  
**Date:** 2026-09-21  
**Important:** A V2 gap is not automatically a V1 defect. Severity is assigned only when current behavior violates an already-binding safety/product contract.

| Gap ID | V2 target | Current V1 observation | Classification | Planned phase |
|---|---|---|---|---|
| G-001 | `ApprovedOrder` capability mintable only by RiskGate | Source search found no formal `ApprovedOrder`; current `OrderRequest` is explicitly non-executable | V2 structural gap; not V1 defect | Phase 2 |
| G-002 | Formal submission/ack/`IN_DOUBT` lifecycle | Current order lifecycle has CREATED, VALIDATED, QUEUED, CANCELLED, REJECTED, EXPIRED, FILLED; source search found no `IN_DOUBT` | V2 structural gap; not V1 defect | Phase 2 |
| G-003 | Fixed process run-mode capability isolation | V1 has strong paper/live separation and current live-readiness fail-closed boundary, but formal V2 adapter capability proof is not yet established | Audit / hardening gap | Phase 2 |
| G-004 | Clock/SeedSource/IdGenerator injected across domain | Canonical/deterministic helpers exist, but full direct-wall-clock/random/ID audit is not yet complete | Evidence/architecture gap | Phase 1 |
| G-005 | CI-enforced module boundaries | Phase 0 branch currently has no required status checks; architecture boundary enforcement is not a protected merge gate | Engineering-foundation gap | Phase 1 |
| G-006 | Immutable dataset catalog with version/checksum/provenance/lineage/licence | Existing data/import/feed foundations exist; universal V2 dataset-catalog evidence has not been proven | Data V2 gap | Phase 3 |
| G-007 | V2 Strategy SDK manifest + lifecycle + promotion evidence | Current `StrategySignalGenerator` interface v1.0 is intentionally smaller | V2 extension gap | Phase 4 |
| G-008 | Formal golden regression bundle from current HEAD | Historical RC baseline exists; current-head golden bundle/two-clean-environment evidence not yet captured | G0 evidence gap | Phase 0 |
| G-009 | Current-head full regression evidence | Historical 146/146 PASS is dated 2026-09-15; current branch has not yet produced a fresh full-suite PASS | G0 evidence gap | Phase 0 |
| G-010 | V2 audit envelope hash-chain/version additions as required by requirements | Mature V1 audit taxonomy/evidence exists; exact V2 envelope compatibility and fail-closed critical-write contract need mapping/tests | V2 extension/audit gap | Phase 1/2 |
| G-011 | Dataset-independent cross-machine deterministic fingerprint comparison | Existing canonical fingerprints/reproducibility modules exist; Phase 0 must select and capture golden deterministic outputs | G0 evidence gap | Phase 0 |
| G-012 | AI tool gateway / TradeCandidate / shadow evaluation | Not expected in V1 | Planned V2 feature; no V1 defect | Phase 8 |

## Severity review

### P0

None declared from source inspection so far. A P0 will be opened immediately if fresh verification finds a path that can create unintended/unauthorized broker mutation, bypass risk, expose secrets, corrupt audit evidence, or violate another critical invariant.

### P1

None declared from source inspection so far. Fresh current-head verification may change this status.

### Evidence blockers to G0

- G-008 current-head golden bundle.
- G-009 current-head full regression execution.
- G-011 two-clean-environment deterministic comparison.
- Complete whole-repository contract/data provenance audit still in progress.

## Rules

- Do not close a gap by weakening a requirement or test.
- Do not silently mutate a frozen V1 schema/contract to make a V2 name fit.
- Every implemented gap gets requirement IDs, tests, evidence and an explicit commit/PR trace.
- Live mutation remains DISARMED throughout Phase 0 and all non-live qualification work.
