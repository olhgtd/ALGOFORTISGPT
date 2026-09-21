# AlgoFortis V2 Phase 0 — Baseline Audit Implementation Plan

**Goal:** Produce a frozen, auditable V1 baseline that V2 can extend without a rewrite, while preserving READ_ONLY/DISARMED safety.

**Architecture:** Documentation-first freeze and evidence pass over the existing local-first V1. No engine behavior changes in Phase 0. Existing V1 contracts are inventoried and frozen; current-head regression evidence is captured before V2 production changes begin.

**Tech stack:** Python 3.13.14, pytest, Windows desktop runtime, GitHub repository evidence, existing AlgoFortis build/certification scripts.

**Spec:** `ALGOFORTIS_V2_REQUIREMENTS.md`, `ALGOFORTIS_V2_ARCHITECTURE.md`, `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`, `ALGOFORTIS_V2_OWNER_DECISIONS.md`, `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`.

## Global Constraints

- Preserve `READ_ONLY=true` and `DISARMED=true`.
- Do not enable real broker mutation or live-money execution.
- Do not rewrite stable V1 modules for style.
- Internal legacy schema/database identifiers may remain unchanged.
- Every completion claim requires fresh evidence from the current branch.
- Historical RC evidence is reference evidence only; it does not certify current HEAD.
- Phase 0 may change documentation, evidence tooling, and non-mutating verification automation only.

## Review Focus

1. Safety regressions or any new path toward broker mutation.
2. Missing/ambiguous V1 contracts that V2 relies on.
3. Gaps between historical RC evidence and current HEAD.
4. Reproducibility and golden-regression evidence quality.
5. P0/P1 blockers that would invalidate the V2 starting baseline.

---

## Task 1 — Freeze Phase 0 Owner Decisions

**Files:**
- Modify: `ALGOFORTIS_V2_OWNER_DECISIONS.md`

**Inputs:** Existing V2 requirements, architecture, implementation plan, and current V1 local-first/safety decisions.

**Actions:**
1. Freeze OD-V2-01 as revised plan authority (Option A).
2. Freeze OD-V2-02 as local-first V2.0; hosted engine remains deferred.
3. Freeze OD-V2-03 as V2.0 = all T0 + T1; T2 is seam-only unless explicitly excepted.
4. Freeze OD-V2-12 as Decimal/fixed-point for money/price/quantity/risk, analytics floats only with declared tolerance.
5. Add dated decision-log entries.

**Verification:** Re-fetch the file from this branch and verify all four statuses are `FROZEN` and decision-log rows exist.

**Commit:** `docs(v2): freeze Phase 0 owner decisions`

---

## Task 2 — Capture Current-Head Baseline Manifest

**Files:**
- Create: `docs/v2/phase0/CURRENT_HEAD_BASELINE.md`

**Actions:**
1. Record branch/base commit and tree identity.
2. Record runtime lock and supported Python baseline.
3. Record the historical RC evidence separately from current-head evidence.
4. Inventory critical V1 domains: risk, orders, audit, data/feed, backtest/reproducibility, paper, broker adapters, reconciliation, auth/security, installer/update.
5. Record branch-protection/CI status as observed.

**Verification:** Compare the branch to the Phase 0 start commit and ensure only intended Phase 0 documentation/evidence files changed.

**Commit:** `docs(v2): capture Phase 0 current-head baseline`

---

## Task 3 — V1 Contract Freeze Audit

**Files:**
- Create: `docs/v2/phase0/V1_CONTRACT_FREEZE.md`
- Create: `docs/v2/phase0/V1_GAP_REGISTER.md`

**Actions:**
1. Read and map current contracts used by Risk, Orders, Audit, Reproducibility, Strategy, Paper, Broker, Reconciliation, Auth and Runtime.
2. Classify each as `PRESERVE`, `WRAP_FOR_V2`, or `GAP`.
3. Explicitly record known V2 gaps including formal `ApprovedOrder`, `IN_DOUBT`, complete injectable Clock/Seed/Id coverage, architecture CI boundaries, dataset catalog, full Strategy SDK/promotion lifecycle.
4. Record any P0/P1 defect discovered; do not silently fix production behavior during the audit.

**Verification:** Every V2 Phase 1/2 contract dependency has an explicit current-V1 mapping or GAP entry.

**Commit:** `docs(v2): freeze V1 contracts and gap register`

---

## Task 4 — Current-Head Regression Runner

**Files:**
- Create: `.github/workflows/v2-phase0-baseline.yml`
- Create or modify only non-mutating verification tooling if required by the existing test suite.

**Actions:**
1. Run the full `tests_v1` suite on Windows with CPython 3.13 and the locked runtime dependencies.
2. Run existing regression/certification scripts that are portable to a clean runner.
3. Keep all live execution and broker mutation disabled.
4. Capture logs/status as Phase 0 evidence.
5. Do not weaken tests to obtain green status.

**Verification:** Fresh GitHub Actions result from this branch. A failure is recorded as a blocker, not hidden.

**Commit:** `ci(v2): add Phase 0 baseline verification`

---

## Task 5 — Golden Regression Definition and Evidence

**Files:**
- Create: `docs/v2/phase0/GOLDEN_REGRESSION_BASELINE.md`
- Create: `docs/v2/phase0/G0_EVIDENCE.md`

**Actions:**
1. Identify deterministic V1 outputs suitable for golden capture: risk decisions, order-lifecycle traces, representative backtest/report fingerprints and reproducibility outputs.
2. Reference immutable code/config/dataset inputs where they exist; mark missing provenance as a blocker/gap.
3. Run reproducibility evidence on two clean runner jobs/environments where technically supported.
4. Record exact matches/tolerances per OD-V2-12.
5. Summarize P0/P1 status and remaining G0 blockers.

**Verification:** G0 is marked PASS only if every requirement in `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` is evidenced. Otherwise mark `IN PROGRESS` with exact missing evidence.

**Commit:** `docs(v2): record golden baseline and G0 evidence`

---

## Completion Contract

Phase 0 is complete only when:
- OD-V2-01, 02, 03 and 12 are frozen.
- Current HEAD has a fresh whole-repository audit.
- Current-head regression evidence is green or all failures are explicitly resolved and re-run.
- Zero open P0/P1 blockers remain for the V2 baseline.
- V1 contract freeze list exists.
- Golden regression evidence is reproducible on two clean environments for deterministic components.
- `READ_ONLY=true`, `DISARMED=true`, and zero broker mutation remain unchanged.
