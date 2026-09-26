# AlgoFortis — Project State Summary / START HERE

**Purpose:** Thin navigation/index file for restoring project context without duplicating mutable phase, PR, Owner Decision, or module-detail state.  
**Snapshot date:** 2026-09-26  
**Repository:** `olhgtd/ALGOFORTISGPT`  
**Current product:** **AlgoFortis**  
**Standing safety baseline:** Live remains **READ_ONLY / DISARMED**.

> **Maintenance rule:** this file is an index, not the authoritative current-state ledger. Do **not** copy detailed phase status, PR heads, CI run numbers, Owner Decision tables, module maps, or remaining-work lists into this file. Mutable project state belongs in `docs/PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md`.

---

# Read in this order

## 1. `docs/PROJECT_HISTORY_V1_TO_V2.md`

Use this for **how the project got here**:

- SentinelX → AlgoFortis history;
- V1 architecture and frozen decisions;
- V1 plan versus actually verified work;
- V1 certified checkpoint and regression evidence;
- V1 deferred/forbidden scope;
- why V2 exists;
- V1→V2 transition map;
- chronological Phase 0–5 development history;
- Laya side-integration history;
- future Phase 6–10 and Platform/Account Track roadmap.

**Ownership:** chronology/history. Historical facts should not be rewritten merely because current branch state changes.

## 2. `docs/PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md`

Use this for **what exists now and what to do next**. This is the detailed human-readable current-state authority for:

- exact phase/gate state;
- PR/branch/head/CI state;
- module map and dependency boundaries;
- frozen/open Owner Decisions;
- safety constraints;
- current blockers;
- ordered remaining work;
- merge/soak/governance distinctions.

**Ownership:** mutable current snapshot. When phase/PR/OD/CI status changes, update this file instead of duplicating the change here.

---

# Canonical supporting sources

The two master files above are context-restoration maps. Underlying code, tests, exact-head evidence, frozen ADRs and canonical specifications remain the final technical authority.

## V1

- `ALGOfORTIS_MASTER_ARCHITECTURE_V1.md`
- `ALGOfORTIS_IMPLEMENTATION_PLAN_V1.md`
- `ALGOfORTIS_DECISION_REGISTER_V1.md`
- `ALGOfORTIS_COMPONENT_INVENTORY.md`
- `CLEAN_CHECKPOINT.md`

## V2

- `ALGOFORTIS_V2_REQUIREMENTS.md`
- `ALGOFORTIS_V2_ARCHITECTURE.md`
- `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`
- `ALGOFORTIS_V2_OWNER_DECISIONS.md`
- `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`
- `docs/v2/adr/`
- phase-specific designs, implementation plans and evidence under `docs/v2/` and `docs/superpowers/plans/`.

---

# Non-negotiable continuity rules

These are intentionally repeated here because they are cross-version safety invariants rather than mutable progress details:

- Current product name is **AlgoFortis**; SentinelX names are legacy/compatibility/history.
- V2 is incremental hardening of V1, not a big-bang rewrite.
- Backtest, Paper and Live remain mode-isolated.
- RiskGate is the V2 executable-order authority.
- Strategy, AI, UI, alerts and reporting cannot bypass risk/execution authority.
- Paper cannot reach real broker mutation.
- Recovery/reconciliation precede retry and new-entry permission.
- Sticky safety recovery does not auto-resume.
- Missing/corrupt safety policy or state fails closed.
- Technical qualification, merge, Owner approval and soak completion are separate states.
- No PR should be merged merely because a historical CI run is green.
- **Live remains READ_ONLY / DISARMED at this snapshot.**

---

# Context-restoration rule for future agents/engineers

1. Read this index.
2. Read `PROJECT_HISTORY_V1_TO_V2.md` for chronology.
3. Read `PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md` for mutable current truth.
4. Read the canonical V2 specifications and Owner Decision register.
5. Read the ADR/design/evidence files for the specific phase being changed.
6. Check the live branch/PR/exact-head CI before relying on any snapshot document.

**Do not maintain a second copy of current-state detail in this file.**