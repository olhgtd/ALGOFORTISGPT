# AlgoFortis — Project State Summary / START HERE

**Purpose:** Entry point for restoring full project context from V1 through the current V2 state.  
**Snapshot date:** 2026-09-26  
**Repository:** `olhgtd/ALGOFORTISGPT`  
**Current product:** **AlgoFortis**  
**Current safety baseline:** Live remains **READ_ONLY / DISARMED**.

This file is intentionally short. The previous V2-heavy consolidated summary has been superseded by two detailed master documents so future development can recover **both V1 and V2 context**, not only the latest V2 phase.

---

# Read these two master files

## 1. `docs/PROJECT_HISTORY_V1_TO_V2.md`

Use this when you need to understand **how the project got here**.

It contains:

- SentinelX origin and transition to AlgoFortis;
- V1 four-layer architecture;
- V1 frozen decisions;
- the V1 13-stage implementation plan, clearly separated into planned vs actually verified work;
- V1 certified clean checkpoint and regression evidence;
- V1 test/product/security/runtime coverage;
- V1 deferred and forbidden items;
- why V2 was created;
- a V1→V2 transition matrix explaining what was preserved, hardened, isolated or deferred;
- V2 Phase 0 through Phase 5 chronological implementation history;
- Phase-4/Phase-5 technical evidence context;
- separate Laya integration history;
- future Phase 6–10 and Platform/Account Track P roadmap;
- permanent safety/continuity rules carried from V1 into V2.

## 2. `docs/PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md`

Use this when you need to know **what exists now and what to do next**.

It contains:

- exact current V1/V2 status distinctions;
- current PR #6 / #7 / #8 states;
- top-level repository map;
- module-by-module responsibilities, key files, dependencies and prohibited dependencies;
- current data/control flows;
- testing/TDD/CI/static-gate strategy;
- Phase 0–10 exact status;
- frozen and open Owner Decisions;
- known architectural constraints and deliberately avoided large legacy files;
- ordered remaining-work backlog from Phase-5 soak/governance through Phase 10;
- Track-P/S2/S3 dependencies;
- current Live safety invariants.

---

# Supporting canonical documents

The two master files are context-restoration maps. They do not replace the underlying authoritative specifications/evidence.

Important V1 sources:

- `ALGOfORTIS_MASTER_ARCHITECTURE_V1.md`
- `ALGOfORTIS_IMPLEMENTATION_PLAN_V1.md`
- `ALGOfORTIS_DECISION_REGISTER_V1.md`
- `ALGOfORTIS_COMPONENT_INVENTORY.md`
- `CLEAN_CHECKPOINT.md`

Important V2 sources:

- `ALGOFORTIS_V2_REQUIREMENTS.md`
- `ALGOFORTIS_V2_ARCHITECTURE.md`
- `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`
- `ALGOFORTIS_V2_OWNER_DECISIONS.md`
- `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`
- `docs/v2/adr/`
- `docs/v2/phase5/G5_EVIDENCE.md`
- `docs/v2/phase5/PAPER_SOAK_START.md`
- `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`
- `docs/superpowers/plans/` for slice-level approved implementation plans.

---

# Current snapshot in one page

## V1

- V1 is a real certified historical baseline, not merely a proposal.
- Clean checkpoint recorded 3761 pytest passes, frontend production build pass, no P0/P1/P2 findings at that checkpoint.
- V1 Live remained READ_ONLY/DISARMED with zero broker mutation and no real broker connection.
- V1 also contained future architecture/plans that were not necessarily deployed; the master history distinguishes these carefully.

## V2

- Phase 0 — complete/merged.
- Phase 1 — complete/merged.
- Phase 2 — complete/merged.
- Phase 3 — complete/merged.
- Phase 4 — technically G4-green; PR #6 open/unmerged.
- Phase 5 — technically G5-ready; PR #8 open/draft/unmerged; Paper soak STARTED/RUNNING; long soak not complete.
- Phase 6 — pending/preflight; blocking Owner Decisions and S2 device/session work remain.
- Phase 7 — pending.
- Phase 8 — pending canonical phase; Laya shell is separate draft side work.
- Phase 9 — pending.
- Phase 10 — pending.

## Open Phase-6 blockers

- OD-V2-05 — multi-device Live exclusivity.
- OD-V2-06 — foreign broker activity policy.
- OD-V2-08 — broker-resident protective orders.
- OD-V2-09 — current regulatory/broker path.
- Track-P S2 — device/session gating.

## Phase-5 decision precedence note

If the root Owner Decision register still shows OD-V2-19 or OD-V2-24 as OPEN, use the later dated Phase-5 authority:

- `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`
- `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md`
- `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`

Those Phase-5 decisions are frozen.

---

# Non-negotiable continuity rules

- Current product name is AlgoFortis; SentinelX names are legacy/compatibility/history.
- V2 is an incremental hardening of V1, not a big-bang rewrite.
- Backtest, Paper and Live remain mode-isolated.
- RiskGate is the V2 executable-order authority.
- Strategy, AI, UI, alerts and reporting cannot bypass risk/execution authority.
- Paper cannot reach real broker mutation.
- Recovery/reconciliation precede retry and new-entry permission.
- Sticky safety recovery does not auto-resume.
- Missing/corrupt policy/state fails closed.
- Technical qualification, merge, Owner approval and long-soak completion are separate states.
- No PR should be merged merely because a prior CI run is green.
- **Live remains READ_ONLY / DISARMED at this snapshot.**

---

# Recommended context-restoration order

For any future engineer/agent joining with no prior context:

1. Read this file.
2. Read `PROJECT_HISTORY_V1_TO_V2.md` completely.
3. Read `PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md` completely.
4. Read the canonical V2 requirements/architecture/implementation/Owner Decision/test plans.
5. Read the ADR/design/evidence files for the specific phase being changed.
6. Check the current branch/PR/exact-head CI before assuming any status in a snapshot document is still current.

This three-file documentation set is the project’s human-readable context recovery layer. The underlying code, tests, frozen ADRs and exact-head evidence remain the final technical authority.
