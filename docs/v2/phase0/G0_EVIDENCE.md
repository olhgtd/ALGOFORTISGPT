# AlgoFortis V2 — G0 Evidence Ledger

**Gate:** G0 — Decision Freeze & V1 Freeze Audit  
**Status:** IN PROGRESS  
**Date:** 2026-09-21  
**Rule:** This file never marks G0 PASS from historical evidence alone.

## Required evidence

| G0 requirement | Status | Evidence / blocker |
|---|---|---|
| OD-V2-01 frozen | PASS | `ALGOFORTIS_V2_OWNER_DECISIONS.md` — revised Phase 0–10 plan canonical |
| OD-V2-02 frozen | PASS | local-first V2.0; cloud account authority only |
| OD-V2-03 frozen | PASS | V2.0 = T0 + T1; T2 seam-only unless explicitly excepted |
| OD-V2-12 frozen | PASS | Decimal/fixed-point money/price/qty/risk; analytics floats require tolerance |
| V1 current-head baseline captured | PASS | `docs/v2/phase0/CURRENT_HEAD_BASELINE.md` |
| V1 contract freeze list | PASS (initial map) | `docs/v2/phase0/V1_CONTRACT_FREEZE.md`; whole-repo audit continues |
| V1→V2 gap register | PASS (initial map) | `docs/v2/phase0/V1_GAP_REGISTER.md` |
| Fresh current-head full regression | BLOCKED / NOT YET RUN | Phase-0 GitHub Actions workflow committed; no successful run evidence recorded yet |
| Zero open P0/P1 | NOT YET PROVABLE | Source inspection has not declared a P0/P1, but fresh full regression and whole-repo audit must finish first |
| Golden regression bundle | NOT YET COMPLETE | Historical RC evidence exists; current-head golden outputs still need capture |
| Two-clean-environment reproducibility | NOT YET COMPLETE | Two independent Windows/Python 3.13 runner jobs are defined; execution evidence pending |
| Data provenance/coverage verified | NOT YET COMPLETE | Dataset-by-dataset catalog/provenance audit pending |

## Historical reference only

The V1 RC baseline dated 2026-09-15 records `146/146 PASS` for `tests_v1` and a fail-closed `READ_ONLY=true`, `DISARMED=true`, zero broker mutation posture. This is useful prior evidence but is not substituted for current-head verification.

## Safety invariant during Phase 0

- No real broker order placement.
- No arming or live mutation enablement.
- No test is weakened to obtain green status.
- A failed verification becomes an explicit blocker and is investigated before G0 can pass.

## Current working trace

- Base/main with V2 baseline docs: `96223c0757004e29b89fe5a00a4aa606957403d2`.
- Isolated branch: `v2-phase0-baseline-audit`.
- Draft PR: #2, intentionally not merge-ready until G0 evidence is complete.
