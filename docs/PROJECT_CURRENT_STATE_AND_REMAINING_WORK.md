# AlgoFortis — Current State and Remaining Work Master

**Purpose:** Authoritative operational context restore for the current repository: what exists now, what each major module owns, what has been verified, what is merged vs unmerged, which Owner Decisions are frozen/open, what constraints must not be weakened, and the ordered work that remains from the current V2 state through release qualification.  
**Snapshot date:** 2026-09-26  
**Repository:** `olhgtd/ALGOFORTISGPT`  
**Working branch:** `v2-phase5-paper-recovery`  
**Functional Phase-5 source head:** `79274f3e3c373caca8065fcc340ef356fc2ff9bd`  
**Verified docs-head before these two master files:** `1434a65be97eda853ade92b216cd5f16301b40e7` — CI run #205 completed successfully.  
**Important:** master-document commits after `1434a65...` are documentation-only unless separately stated.  
**Current product:** AlgoFortis  
**Current Live state:** `READ_ONLY / DISARMED` — zero authorization for real broker mutation.

For chronological history and the V1→V2 transition, read `docs/PROJECT_HISTORY_V1_TO_V2.md` first.

---

# 0. Status language and authority

Do not collapse the following states into one word such as “done”:

- **Designed** — architecture/spec exists.
- **Owner-frozen** — required Owner Decision/ADR is frozen.
- **Implemented** — code exists.
- **Verified** — focused/static/regression evidence exists.
- **Gate-ready** — technical exit evidence satisfies the named technical gate.
- **Merged** — integrated into the target branch.
- **Owner-approved** — explicit governance approval has been given where required.
- **Soak-running** — long-run operational evidence is accumulating.
- **Soak-passed** — the defined long-run soak criteria have actually completed successfully.

A technically green PR can still be unmerged. A gate-ready phase can still have Owner/governance work. A soak can be started without being passed.

## Authority precedence

When records disagree, use this order:

1. exact current code + tests + exact-head CI evidence;
2. frozen V2 Owner Decisions/ADRs and dated phase amendments;
3. canonical V2 requirements/architecture/implementation/test plans;
4. phase designs/implementation plans/evidence reports;
5. V1 frozen architecture and certified checkpoint for historical/carry-forward behavior;
6. old README/AlgoFortis-era presentation as historical reference only.

Phase-5 decision reconciliation is complete: root `ALGOFORTIS_V2_OWNER_DECISIONS.md` now records OD-V2-19 and OD-V2-24 as **FROZEN**, consistent with `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`, ADR-013 and ADR-014. Future changes to either decision require a new dated decision-log entry rather than an exception note.

---

# 1. One-screen current status

## V1

- Historical product/runtime baseline: **certified**.
- Clean checkpoint: 3761 pytest passed, frontend build passed, P0/P1/P2 findings none at that checkpoint.
- Live at V1 baseline: `READ_ONLY=true`, `DISARMED=true`, `live_global_hold=true`, zero broker mutation, no real broker connection.
- V1 architecture/account/cloud plans include future/deferred items and must not all be treated as deployed.

## V2 Trading Core

- Phase 0: complete/merged.
- Phase 1: complete/merged.
- Phase 2: complete/merged.
- Phase 3: complete/merged.
- Phase 4: technically G4-green, PR #6 open/unmerged.
- Phase 5: technically G5-ready, PR #8 open/draft/unmerged; Paper soak running, Owner gate distinct.
- Phase 6: preflight only; implementation not authorized until blockers frozen/ready.
- Phase 7: pending.
- Phase 8: pending canonical implementation; Laya side shell exists separately on draft PR #7.
- Phase 9: pending.
- Phase 10: pending.

## Platform/Account Track P

- architectural/frozen V1 inputs exist;
- V2 Track P still has open decisions and implementation work;
- S2 device/session gate matters before Phase-6 exit;
- S3 installer/updater/licence/backup/release packaging matters before Phase 10.

---

# 2. Current PR and branch state

## PR #6 — Phase 4

**Title:** V2 Phase 4: Strategy SDK, Research & Backtest V2  
**State:** open, mergeable, not draft, unmerged  
**Head:** `v2-phase4-strategy-research-backtest`  
**Exact head:** `20310e359eeeb13ee2b4e443717cf654466f68c4`  
**Evidence:** run #121 / `36097336715` — Windows latest and Windows 2022 green; Phase0–4 gates, full regression, certification, golden and G4 cross-Windows deterministic comparison pass.  
**Safety:** research/backtest only; Live remains DISARMED; built-in promotion remains fail-closed/NON_PROMOTABLE.

## PR #7 — Laya integration

**Title:** Laya integration: model-agnostic fast intelligence shell  
**State:** open, draft, unmerged  
**Base:** Phase-4 branch  
**Head:** `laya-integration`  
**Exact head:** `65127819df42cf8376de2c4ec13faccd56d9037a`  
**Evidence:** run #138 / `36146416264` success including dual-Windows Laya fingerprint compare.  
**Limits:** actual Laya model/runtime not connected; default disabled/fail-closed; CANDIDATE_ONLY; research-only; no direct broker/Live/order authority.

## PR #8 — Phase 5

**Title:** Phase 5: Paper V2 recovery foundations  
**State:** open, draft, unmerged  
**Branch:** `v2-phase5-paper-recovery`  
**Functional technical source head:** `79274f3e3c373caca8065fcc340ef356fc2ff9bd` before later docs-only commits.  
**Technical qualification:** final exact functional head run #204 / `36226897730` success; dual-Windows full regression/certification plus G4/G5 comparisons green.  
**Docs-head check:** `1434a65be97eda853ade92b216cd5f16301b40e7`, run #205 success.  
**Governance:** technical G5 evidence ready; Paper soak running; PR remains draft/open/unmerged; Owner gate/merge remain separate decisions.

## Merge rule

No PR is to be merged automatically because CI is green. Merge requires explicit Owner instruction plus whatever fresh retarget/diff/exact-head verification is appropriate at that time.

---

# 3. Top-level repository map

## `.github/`

Purpose:

- GitHub Actions/CI.
- Current V2 qualification workflow lives in `.github/workflows/v2-phase0-baseline.yml`.

Important naming note:

- the workflow filename is historical;
- its current responsibility extends far beyond Phase 0 and includes Phase1–5 checks, full regression, deterministic probes and cross-Windows comparisons.

## `assets/`

Purpose:

- product branding/static assets.
- current product identity is AlgoFortis even where legacy AlgoFortis artifacts remain.

## `build/`

Purpose:

- build/certification/release tooling;
- static architecture/policy checkers;
- deterministic qualification probes;
- installer/launcher/release support.

`build/tools/` is safety-critical because it converts architectural rules into CI failures rather than relying only on documentation.

## `config/`

Purpose:

- layered/versioned runtime, execution, Paper, risk and strategy configuration.

Constraint:

- do not add guessed production thresholds just because code/tests need a value; production economic/safety thresholds require frozen evidence-backed policy.

## `dashboard/`

Purpose:

- owner/user dashboards;
- backend/API surfaces;
- shared UI/runtime components;
- secure entry/auth UX;
- system visibility and product workflows.

Constraint:

- UI is not an execution authority;
- dashboard actions must ultimately respect domain/risk contracts.

## `data/`

Purpose:

- local data/state roots such as incoming files, import reports, Parquet, quarantine and state.

Constraint:

- source/licensing/provenance rules from Data V2 still apply.

## `docs/`

Purpose:

- architecture/ADRs;
- phase designs/plans/evidence;
- security/legal/release/beta/product handoff;
- master project context.

Master context entry:

- `PROJECT_STATE_SUMMARY.md`
- `PROJECT_HISTORY_V1_TO_V2.md`
- `PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md`

## `engine/`

Purpose:

- main domain/runtime implementation.

Key domains are mapped in detail below.

## `strategies/`

Purpose:

- concrete strategies separated from generic Strategy SDK.

Current reference:

- `strategies/orb/`.

## `tests_v1/`

Purpose:

- historical V1 regression plus V2 phase-specific qualification tests.

Naming note:

- directory name is historical; it is the active broad suite for both generations.

---

# 4. Module-by-module current map

# 4.1 `engine/core/`

## Responsibility

Shared runtime foundation:

- configuration;
- runtime primitives;
- adapter/capability registry;
- observability;
- numeric helpers/policies.

## Key files

- `adapter_registry.py` — internal adapter registration/capability compatibility.
- `configuration.py` — configuration/snapshot foundations.
- `numeric.py` — numeric support.
- `observability.py` — runtime/log/observability structures.
- `runtime.py` — core runtime primitives.

## Talks to

- most domain layers through shared contracts/primitives.

## Must not become

- a dumping ground for strategy/risk/broker policy.

## Status

- Phase-1 foundation complete/merged.

---

# 4.2 `engine/data/`

## Responsibility

Data V2 domain:

- dataset catalog/versioning;
- historical storage abstractions;
- provenance/licensing;
- instrument master;
- data quality;
- deterministic resampling;
- live-feed contracts/health.

## Talks to

- market/research/backtest/strategy/live feed consumers.

## Must not

- allow unlicensed/prohibited acquisition paths;
- hide provenance;
- permit stale/invalid live data to silently continue entry eligibility.

## Status

- Phase 3 complete/merged.

---

# 4.3 `engine/market/`

## Responsibility

Supporting market domain:

- calendars;
- market data models/helpers;
- market/session profiles.

## Key files

- `calendar.py`
- `data.py`
- `profile.py`

## Talks to

- data, strategy, options, backtest, Paper/live feed consumers.

## Status

- established supporting domain carried through V1/V2.

---

# 4.4 `engine/strategy/`

## Responsibility

Generic Strategy SDK V2:

- manifest/contracts;
- deterministic state;
- lifecycle;
- promotion evidence;
- protective-policy association.

## Key files

- `contracts_v2.py`
- `state_v2.py`
- `lifecycle_v2.py`
- `promotion_v2.py`
- `protective_policy_v2.py`
- legacy/supporting `base.py`, `exceptions.py`.

## Talks to

- data/market inputs;
- research/backtest;
- order-intent/risk boundary;
- reporting/evidence.

## Must not talk directly to

- concrete broker mutation adapters;
- Live arm authority.

## Status

- Phase-4 implementation verified on PR #6; not merged to main at snapshot.

---

# 4.5 `strategies/orb/`

## Responsibility

Concrete ORB reference strategy proving that the Strategy SDK works for a real strategy instead of an abstract-only design.

## Key files

- `manifest_v2.py`
- `orb_v2.py`
- `orb_strategy.py`

## Important V2 rule

V2 does not invent missing ORB protective economics. Executable simulation requires an explicit versioned protective policy reference. Missing policy fails closed.

## Status

- Phase-4 reference implementation verified; PR #6 open/unmerged.

---

# 4.6 `engine/research/`

## Responsibility

Research/experiment governance:

- experiment registry;
- append-only trials ledger;
- search budgets;
- parameter stability;
- WFO/OOS;
- robustness/stress;
- overfitting/deflated performance evidence.

## Talks to

- datasets;
- strategies;
- Backtest V2;
- promotion/evidence/reporting.

## Must not

- convert research P&L directly into Live eligibility;
- silently expand trial budget after seeing OOS evidence.

## Status

- Phase-4 verified; PR #6 open/unmerged.

---

# 4.7 `engine/backtest/`

## Responsibility

Deterministic historical execution/replay/evidence.

## Current V2 behavior

- deterministic ordering;
- explicit realism/cost/slippage;
- no-lookahead tests;
- options-aware simulation;
- reproducible fingerprints;
- replay/evidence.

## Talks to

- data/research/strategy/orders/risk models/costs/reporting/reproducibility.

## Must not

- self-authorize promotion;
- use future data.

## Status

- Phase-4 verified; PR #6 open/unmerged.

---

# 4.8 `engine/risk/`

## Responsibility

Central safety/risk authority.

## Key files

- `gate_v2.py` — V2 RiskGate and executable approval capability.
- `kill_switch.py` — HALT_ENTRIES/CANCEL_PENDING/FLATTEN_ALL semantics.
- `limits.py` — hard limits.
- `risk_manager.py` — large legacy risk manager.

## Talks to

- validated order intent/context;
- Paper/live execution adapters through approved capability;
- portfolio layer later.

## Must not allow

- strategy bypass;
- AI bypass;
- dashboard bypass;
- a lower policy layer exceeding a higher hard limit.

## Status

- Phase-2 Safety Spine complete/merged; later modules rely on it.

## Legacy constraint

Do not casually add new V2 authority into the large `risk_manager.py`; prefer `gate_v2.py`/focused modules.

---

# 4.9 `engine/orders/`

## Responsibility

Order/intention contracts, identity, validity and lifecycle.

## Key files

- `contracts_v2.py`
- `intent_guard.py`
- `lifecycle.py`
- `lifecycle_v2.py`
- `model.py`
- `validity.py`

## Talks to

- strategy intent;
- risk gate;
- execution adapters;
- persistence/audit/reconciliation.

## Safety rules

- deterministic logical intent ID;
- stale intent rejected;
- duplicate intent suppressed;
- uncertain prior submission reconciled before any retry;
- in-doubt is not “retry blindly”.

## Status

- Phase-2 foundations complete/merged.

---

# 4.10 `engine/options/`

## Responsibility

Option catalog, selection and contract/expiry policy.

## Key files

- `catalog.py`
- `live_catalog.py`
- `policy.py`
- `selector.py`

## Talks to

- market/data;
- strategy/Paper/backtest;
- instrument master.

## Safety rules

- expired option cannot receive a fresh entry;
- selection uses explicit eligibility data;
- no invented expiry flatten/carry rule if policy missing.

## Status

- significant foundation exists and is used by V2 research/Paper flows.

---

# 4.11 `engine/execution/`

## Responsibility

General/legacy execution abstractions and Paper execution infrastructure.

## Key files

- `adapter.py`
- `engine.py`
- `model.py`
- `paper_broker.py`
- `paper_fill.py`
- `quote.py`
- `slippage.py`

## Relationship to Phase 5

Phase-5 V2 Paper safety uses focused Paper V2 modules rather than giving generic/legacy execution code new real-broker authority.

## Status

- mature V1 foundation plus V2 wrappers/boundaries.

---

# 4.12 `engine/paper/`

## Responsibility

Paper-mode runtime plus Phase-5 operational safety.

## Large legacy files

- `coordinator.py` — very large legacy coordinator.
- `live_runner.py` — very large legacy Paper runtime.

These are deliberately not the preferred home for new V2 concerns.

## Phase-5 key files

- `contracts_v2.py`
- `execution_adapter_v2.py`
- `fill_simulator_v2.py`
- `operational_state_v2.py`
- `failure_policy_v2.py`
- `protective_integrity_v2.py`
- `recovery_coordinator_v2.py`
- `session_v2.py`
- `drift_report_v2.py`
- `evidence_v2.py`
- `failure_injection_v2.py`
- `phase5_runtime_v2.py`

## Talks to

- approved RiskGate Paper capability;
- reconciliation;
- persistence;
- host safety;
- alert port;
- data/feed/session policy;
- audit/evidence.

## Must not talk to

- real broker mutation adapters;
- Live arm capability.

## Current operational states

- HEALTHY
- DEGRADED
- HALTED
- RECOVERY
- READY_FOR_RESUME

## Current safety semantics

- HALT_ENTRIES → sticky HALTED when safety latch applies;
- uncertain continuity → RECOVERY;
- CLEAN reconciliation does not auto-resume;
- recovery all-clean → READY_FOR_RESUME;
- explicit manual resume required;
- no stale replay/duplicate resubmit.

## Status

- Phase-5 technical implementation verified; PR #8 open/draft/unmerged.

---

# 4.13 `engine/reconciliation/`

## Responsibility

Truth comparison and mismatch classification.

## Structure

- Paper-specific reconciliation remains under `engine/reconciliation/paper/`.
- `live_reconciler.py` provides existing Live-oriented reconciliation foundation.

## Talks to

- persisted/expected owned state;
- current execution truth;
- recovery coordinator.

## Must not

- retry/submit an order simply because it detected a mismatch;
- declare “safe to resume” beyond its reconciliation responsibility.

## Important rule

Reconciliation CLEAN is necessary but not sufficient. Protective/feed/clock/session/expiry gates remain independent.

## Status

- mature V1 foundation, Phase-5 recovery-integrated and verified.

---

# 4.14 `engine/persistence/`

## Responsibility

Durable state/evidence storage.

## Key files

- `migrations.py`
- `migrations_base_v7.py`
- `phase5_schema_v8.py`
- `paper_codec_v2.py`
- `paper_session_store_v2.py`
- `paper_recovery_store_v2.py`
- `paper_incident_store_v2.py`
- `schema.py`
- `strategy_state.py`
- large legacy `sqlite_store.py`.

## Phase-5 persisted areas

- Paper session;
- orders;
- positions;
- checkpoints;
- incidents;
- alert delivery evidence;
- recovery reports.

## Talks to

- Paper runtime/recovery/evidence.

## Must not

- decide recovery policy;
- silently skip missing owned truth.

## Important strict hardening

`load_owned_state()` now fails closed when a checkpoint references an order/position that cannot be restored. This was found in a strict P5-03 re-audit and closed with RED→GREEN tests.

## Status

- additive V8 Phase-5 persistence verified; legacy store preserved.

---

# 4.15 `engine/protective/`

## Responsibility

Protective plan/runtime/policy foundations.

## Key files

- `plan.py`
- `runtime.py`
- `runtime_policy.py`
- large `live.py`.

## Talks to

- risk/order/position state;
- runtime and future Live adapter behavior.

## Phase-5 relationship

`engine/paper/protective_integrity_v2.py` independently verifies Paper protective state; reconciliation cannot bypass it.

## Constraint

Do not turn large `live.py` into a catch-all for unrelated V2 safety features.

---

# 4.16 `engine/live/`

## Responsibility

Live state-machine and current Live-domain safety foundations.

## Current state

- READ_ONLY;
- DISARMED;
- no Phase-5 component may change this.

## Future Phase-6 role

- first real broker adapter remains DISARMED during qualification;
- read-only reconciliation;
- device/session exclusivity;
- foreign-activity policy;
- broker-resident protection;
- compliance/broker constraints;
- disconnect/token/rate-limit behavior.

## Must not

- auto-arm after restart/reconnect;
- become reachable from Paper mode.

---

# 4.17 `engine/broker_contract/`

## Responsibility

Broker-neutral contract/conformance boundary.

## Talks to

- Paper adapter and future real broker adapters through the same contract discipline.

## Future Phase-6 role

The first real adapter must pass the contract kit before any later Live eligibility discussion.

---

# 4.18 `engine/broker_adapters/`

## Responsibility

Concrete/mock/legacy broker implementations.

## Current rule

Phase-5 Paper V2 cannot import real broker mutation adapters.

## Future rule

Phase 6 should prove one adapter extremely well before expanding to a second.

---

# 4.19 `engine/host/`

## Responsibility

Phase-5 local host/session safety.

## Key files

- `instance_lock.py`
- `clock_health.py`
- `power_session.py`
- `watchdog_policy.py`

## Frozen behavior

- one instance;
- temporary active-session sleep prevention;
- sleep/resume uncertainty → recovery;
- watchdog restart → recovery only;
- injectable/versioned clock policy;
- no guessed production clock/hardware threshold;
- no requirement to disable antivirus/security.

## Must not

- arm Live;
- permanently rewrite user power plans as a hidden side effect.

## Status

- P5-07 verified.

---

# 4.20 `engine/alerts/`

## Responsibility

Phase-5 critical operational notifications.

## Key files

- `contracts.py`
- `dispatcher.py`
- `redaction.py`
- `adapters/windows_local.py`
- `adapters/telegram.py`

## Talks to

- recovery/incident/evidence through an alert port.

## Must not

- place orders;
- arm Live;
- mutate RiskGate/reconciliation outcome;
- expose secrets/raw identifiers/unrestricted trade logs.

## Frozen behavior

- local + Telegram attempts independent;
- one failure cannot suppress another;
- email optional;
- alert failure auditable;
- safety continues independently of Telegram.

## Status

- P5-08 verified.

---

# 4.21 `engine/audit/`

## Responsibility

Audit events, chain integrity, log/evidence sinks.

## Talks to

- all safety-critical domains.

## Rule

Safety-critical transitions/decisions/recovery incidents must remain reviewable and version-associated.

## Status

- V1 foundation strengthened in Phase 1; later phases depend on it.

---

# 4.22 `engine/reporting/`

## Responsibility

Report contracts, serialization and writing.

## Key files

- `model.py`
- `paper_summaries.py`
- `serializer.py`
- `writer.py`

## Must not

- change trading permission or safety state.

---

# 4.23 `engine/reproducibility/`

## Responsibility

Canonical identities/fingerprints/replay inputs.

## Key files

- `codec.py`
- `dependencies.py`
- `market_data.py`
- `model.py`
- `replay.py`
- `source.py`

## Talks to

- data/research/backtest/evidence/certification.

## Status

- central to Phase-4 cross-machine determinism and later evidence.

---

# 4.24 `engine/portfolio/`

## Responsibility

Existing accounting/model/virtual-account foundation.

## Key files

- `accounting.py`
- `model.py`
- `virtual_account.py`

## Current status

Foundation exists; canonical Phase 7 is **not complete**.

## Phase-7 pending additions

- reservation/release;
- per-strategy/per-user budgets;
- aggregate/concentration controls;
- circuit breakers;
- attribution/event-risk policy;
- RiskGate integration.

---

# 4.25 `engine/orchestration/`

## Responsibility

Existing high-level signal/strategy/entry/deployment coordination.

## Key files

- `signal_intake.py`
- `strategy_coordinator.py`
- very large `entry_pipeline.py`
- `deployment_executor.py`
- `user_feed_manager.py`

## Constraint

This domain must not become an alternate V2 order/risk authority. Prefer small focused V2 modules rather than continuing to grow `entry_pipeline.py`.

---

# 4.26 `engine/safety/`

## Responsibility

Historical/cross-cutting safety helpers.

## Key files

- `safety.py`
- `alerts.py`
- `strategy_halt.py`
- `phase8_safety.py`

## Warning

A filename such as `phase8_safety.py` does not prove canonical roadmap Phase 8 is complete. Phase status comes from current requirements/ODs/gates/evidence.

---

# 4.27 `engine/trades/`

## Responsibility

Trade models and ledger.

## Key files

- `model.py`
- `ledger.py`

## Rule

Ledger/report/accounting views do not authorize execution.

---

# 4.28 `engine/costs/`

## Responsibility

Cost models/calculation/projections.

## Key files

- `model.py`
- `calculator.py`
- `projection.py`

## Rule

When used in promotion evidence, cost/slippage assumptions must be versioned and auditable.

---

# 4.29 `engine/ai/laya/` — side integration

## Responsibility

Current model-agnostic Laya research/intelligence shell.

## Current status

- separate draft PR #7;
- actual model runtime/weights not connected;
- disabled/fail-closed default;
- candidate-only opportunity output;
- research-only strategy hunting;
- direct broker/Live/order/network authority statically blocked.

## Must not be confused with

- completed canonical Phase 8.

---

# 5. Current end-to-end data/control flows

## 5.1 Historical research flow

1. Data V2 identifies immutable dataset/version/provenance.
2. Data quality and instrument/as-of/session rules validate inputs.
3. Deterministic replay feeds Strategy SDK/reference strategy.
4. Strategy generates decision/intent, not broker authority.
5. Risk/order semantics are represented consistently in simulation.
6. Backtest execution models fills/slippage/cost/options behavior.
7. Research records experiment/trial/search/WFO/OOS/robustness/overfitting evidence.
8. Reproducibility/reporting generate fingerprint/evidence bundle.
9. Promotion checks an explicit versioned policy.
10. Missing/incomplete profile → NON_PROMOTABLE.

## 5.2 Normal Paper flow

1. normalized/live market data enters Paper-safe pipeline;
2. strategy evaluates;
3. Option Selector resolves eligible contract when needed;
4. intent identity/freshness/validity checked;
5. RiskGate approves/rejects;
6. only RiskGate-minted PAPER approved capability reaches Paper execution adapter;
7. deterministic simulator models conservative fill/slippage/latency/reject/disconnect;
8. order/position/session state persisted;
9. reconciliation compares owned truth with execution truth;
10. protective integrity independently validates protection;
11. audit/evidence/alerts/reporting recorded;
12. drift report may compare Paper vs Backtest but cannot promote by itself.

## 5.3 Paper failure/recovery flow

1. discontinuity/failure detected;
2. entries blocked;
3. state becomes DEGRADED/HALTED/RECOVERY according to failure semantics;
4. persisted checkpoint/session/orders/positions restored;
5. reconciliation runs;
6. non-clean/uncertain reconciliation halts progress;
7. protective integrity runs;
8. feed health runs;
9. clock health runs;
10. session/expiry policy runs;
11. all required gates passing → READY_FOR_RESUME;
12. explicit manual resume → HEALTHY;
13. no known intent resubmit, no stale replay;
14. alerts attempted independently;
15. recovery report/evidence persisted.

## 5.4 Future Phase-6 Live qualification flow

Target only; still DISARMED:

1. same Strategy/RiskGate/order identity contracts;
2. real broker adapter behind broker contract;
3. read-only broker truth retrieval/reconciliation;
4. foreign activity detection;
5. device/session exclusivity;
6. broker-resident protective behavior where supported;
7. regulatory/broker constraints represented as versioned policy;
8. disconnect/rate-limit/token-refresh/recovery tested;
9. real mutation remains unreachable while Phase-6 qualification is DISARMED.

---

# 6. Testing and CI strategy

## 6.1 Historical V1 regression

V1 clean checkpoint anchor:

- 3761 passed;
- 0 failed;
- 0 errors;
- frontend production build pass;
- no P0/P1/P2 findings at checkpoint.

V1 area suites span auth/recovery, backup, installer/update, UI workflows, broker/data/credential/reconciliation/security and DB hardening.

## 6.2 V2 TDD pattern

For new slices:

1. write focused RED test;
2. confirm the expected failure;
3. add minimal implementation;
4. focused GREEN;
5. architecture/static checks;
6. full regression;
7. deterministic/golden checks;
8. exact-head dual-Windows evidence where required.

## 6.3 Static architecture gates

Current guards enforce rules such as:

- Paper V2 cannot import real broker mutation adapters;
- alert adapters cannot acquire arm/order authority;
- persistence cannot decide recovery semantics;
- host/watchdog cannot arm Live;
- required Phase-5 modules/tests cannot silently disappear;
- default Live safety cannot weaken;
- production failure policy cannot default to unbounded retries;
- module dependency direction remains constrained.

## 6.4 Current CI pipeline

`.github/workflows/v2-phase0-baseline.yml` currently covers:

- setup/compile/module-boundary checks;
- Phase-1 static/focused validation;
- Phase-2 Safety Spine checks;
- Phase-3 Data V2 checks;
- Phase-4 Strategy/Research/Backtest checks + deterministic probe;
- Phase-5 Paper/Recovery checks + deterministic probe;
- full `tests_v1` regression;
- regression certification;
- frozen Phase-0 golden probe;
- Windows latest runner;
- Windows 2022 runner;
- G4 cross-Windows deterministic comparison;
- G5 cross-Windows deterministic comparison.

## 6.5 Phase-5 FI scope

Deterministic safety fixtures cover:

- FI-01
- FI-02
- FI-03
- FI-04
- FI-05
- FI-06
- FI-07
- FI-08
- FI-09
- FI-12
- FI-13
- FI-14
- FI-23
- FI-24

They prove software response contracts and adapter-level fault semantics. They do not claim CI physically crashes a production PC, rewrites a real system clock, fills a real disk or contacts a real broker.

---

# 7. Phase-wise exact state

## Phase 0 — COMPLETE / MERGED

Decision/V1 freeze, canonical build order, numeric/deployment baseline and golden regression anchor.

## Phase 1 — COMPLETE / MERGED

Engineering foundation: runtime/config/audit/observability/migrations/internal registry/module boundaries.

## Phase 2 — COMPLETE / MERGED

Safety Spine: RiskGate, ApprovedOrder, hard limits, lifecycle, mode isolation, kill-switch and Live state foundation.

## Phase 3 — COMPLETE / MERGED

Data V2: immutable datasets/provenance/quality/resampling/instrument/live-feed/licensing.

## Phase 4 — TECHNICALLY COMPLETE / G4 GREEN / PR #6 OPEN

Implementation verified, not merged at snapshot.

## Phase 5 — TECHNICALLY COMPLETE / G5 EVIDENCE READY / PR #8 OPEN-DRAFT

P5-01 through P5-10 implemented and verified. Soak running. Owner gate and merge remain separate.

## Phase 6 — PENDING / PREFLIGHT

No production code should enable real mutation. Blocking ODs/S2/design/planning still required.

## Phase 7 — PENDING

Portfolio-level risk expansion not complete.

## Phase 8 — PENDING CANONICAL PHASE

Laya shell is separate side work; canonical AI permissions/providers/shadow system still pending.

## Phase 9 — PENDING

Product/operations/runbooks/drills/compliance UX pending.

## Phase 10 — PENDING

Release qualification and controlled pilot pending.

---

# 8. Owner Decision state

# 8.1 Frozen / binding V2 decisions relevant to completed work

- OD-V2-01 — canonical revised Phase0–10 build order.
- OD-V2-02 — V2.0 local-first.
- OD-V2-03 — T0/T1 completion rule.
- OD-V2-04 — crypto/BTCUSD deferred to V2.3.
- OD-V2-07 — kill-switch semantics.
- OD-V2-10 — options data source/synthetic policy.
- OD-V2-11 — multiple-testing/overfitting governance.
- OD-V2-12 — Decimal/fixed-point numeric policy.
- OD-V2-13 — Parquet/Arrow + PyArrow Dataset + SQLite catalog.
- OD-V2-14 — internal registry only for V2.0.
- OD-V2-17 — fail-closed promotion criteria/default NON_PROMOTABLE.
- OD-V2-19 — Phase-5 alert independence, frozen in the root register and ADR-014.
- OD-V2-24 — Phase-5 host policy, frozen in the root register and ADR-013.

# 8.2 Open decisions blocking Phase 6

## OD-V2-05 — multi-device Live exclusivity

Needs binding policy for preventing simultaneous armed engines on the same broker account. Local safety cannot depend solely on cloud availability.

## OD-V2-06 — foreign broker order/position policy

Needs binding behavior when broker truth contains activity not created by AlgoFortis. Existing recommendation is fail-closed/halt entries + alert + explicit user adoption, never auto-adopt.

## OD-V2-08 — broker-resident protective orders

Needs binding policy for broker-hosted stop/target protection and degraded handling where the broker cannot support the required protection.

## OD-V2-09 — regulatory/broker path

Requires a dated current review of the chosen broker/exchange/regulatory requirements before Phase-6 exit. Do not assume historical rules remain current.

# 8.3 Open AI decisions

- OD-V2-15 — V2.0 AI scope/provider set.
- OD-V2-16 — AI provider data-sharing/redaction rules.

# 8.4 Open Platform/Account decisions

- OD-V2-20 — auto-update/release channel.
- OD-V2-21 — licence/entitlement.
- OD-V2-22 — telemetry/privacy.
- OD-V2-23 — publisher/version/domain.

# 8.5 Later governance

- OD-V2-25 and related current data-protection/retention obligations belong to later product/operations governance where applicable and must be resolved against current law/policy at that time.

---

# 9. Known constraints and deliberately avoided architecture mistakes

## 9.1 Live stays DISARMED

No completed Phase 0–5 work grants permission for real-money order placement.

## 9.2 No new monolith

Avoid pushing new V2 concerns into:

- `engine/paper/coordinator.py`
- `engine/paper/live_runner.py`
- `engine/persistence/sqlite_store.py`
- `engine/orchestration/entry_pipeline.py`
- `engine/risk/risk_manager.py`
- `engine/protective/live.py`

Prefer focused modules, explicit protocols and minimal wiring.

## 9.3 No alternate execution authority

Forbidden conceptual paths include:

- Strategy → broker direct.
- AI → broker/order direct.
- Dashboard → broker direct.
- Alert adapter → arm/order.
- Watchdog → arm.
- Persistence → recovery policy decision.
- Reporting → state mutation.
- Paper → real broker adapter.

## 9.4 No automatic trust restoration

- reconnect is not resume;
- CLEAN reconciliation is not resume;
- successful alert delivery is not resume;
- watchdog restart is not resume;
- successful state restore is not resume;
- sticky halt/recovery requires all gates and manual resume when applicable.

## 9.5 No invented production numbers

Do not freeze guessed values for:

- promotion thresholds;
- storm thresholds;
- clock drift;
- drift tolerance;
- minimum hardware;
- strategy protective economics;
- Live risk/compliance constraints.

Use measured/frozen versioned policy.

## 9.6 Legacy names are not automatic cleanup targets

Old AlgoFortis names may be referenced by:

- compatibility paths;
- database identifiers;
- migrations;
- tests;
- launchers;
- old evidence.

Do not perform a broad rename without dependency/evidence review.

---

# 10. Ordered remaining-work backlog

This section is the practical “what next?” list. Do not skip earlier gates simply because later code looks interesting.

# 10.1 Finish Phase-5 governance/evidence lifecycle

1. Continue Paper soak campaign and accumulate real qualifying session evidence.
2. Record session start/end and clean/unclean shutdown evidence.
3. Record reconciliation/recovery incidents.
4. Record protective-integrity/feed/clock/session/expiry evidence.
5. Record duplicate/stale replay counters.
6. Record critical alert delivery attempts.
7. Record Paper-vs-Backtest drift.
8. Evaluate the longer soak only after its defined target is actually met; do not label it passed early.
9. Review G5 technical evidence for explicit Owner closure where required.
10. Treat PR #8 merge as a separate explicit decision.

# 10.2 Resolve branch/PR integration sequencing

1. PR #6 Phase 4 remains unmerged.
2. PR #7 Laya is stacked on Phase 4 and remains draft.
3. PR #8 Phase 5 currently targets main and contains substantial stacked Phase-4/5 work.
4. Before any merge/retarget, inspect exact diff against intended base.
5. Require fresh exact-head CI after meaningful retarget/integration changes.
6. Never infer merge permission from green historical runs.

# 10.3 Phase-6 decision freeze

Before product code for Phase 6:

1. freeze OD-V2-05;
2. freeze OD-V2-06;
3. freeze OD-V2-08;
4. perform/freeze the current OD-V2-09 regulatory/broker path;
5. confirm S2 device/session dependency plan;
6. write Phase-6 architecture/design spec;
7. review/approve it;
8. write Phase-6 implementation plan;
9. review/approve it;
10. then implement in small TDD slices.

# 10.4 Phase-6 technical target — still DISARMED

Planned work includes:

- first real broker adapter against the contract kit;
- read-only balances/positions/orders truth;
- stable reconciliation;
- foreign activity detection;
- multi-device exclusivity backstop;
- broker-resident protection policy;
- rate limits/reconnect/token refresh;
- broker/exchange rule config;
- compliance outcome documentation;
- disconnect/reconnect chaos evidence;
- no mutation route while DISARMED.

# 10.5 Platform Track P / S2

To make later Live governance safe:

1. freeze OD-V2-20 update/release behavior;
2. freeze OD-V2-21 entitlement behavior;
3. freeze OD-V2-22 telemetry/privacy;
4. freeze OD-V2-23 publisher/version/domain;
5. implement account/device/session authority under local-safety constraints;
6. provide device/session gate for S2;
7. never centralize broker credentials/trading state.

# 10.6 Phase 7 — Portfolio & Risk V2

Implement and verify:

- capital reservation/release;
- per-strategy/per-user budgets;
- aggregate exposure;
- concentration controls;
- portfolio circuit breakers;
- attribution;
- event-day risk policy;
- integration through existing RiskGate, not around it.

# 10.7 Phase 8 — AI/Agents research + shadow

Before implementation:

- freeze OD-V2-15;
- freeze OD-V2-16.

Then build/verify:

- provider registry/adapters;
- permissioned tool gateway;
- Prime/Research/Risk-challenger roles;
- market-intelligence scheduler;
- deterministic TradeCandidate contract/validator;
- budgets/quotas;
- prompt-injection defense;
- audit/replay;
- provider outage → safe degradation/NO_TRADE;
- proof that AI has no direct execution path.

Laya work may become one provider/intelligence component later, but it does not bypass this canonical phase.

# 10.8 Phase 9 — Product & Operations

Pending:

- production operator/user workflows;
- complete alert/runbook set;
- incident templates;
- backup/restore drill evidence;
- rollback drill evidence;
- release/operator diagnostics;
- consent/disclosure/privacy/compliance UX;
- relevant data-protection/retention decisions.

# 10.9 Platform Track P / S3

Before final release qualification:

- installer packaging;
- signed updater + rollback;
- entitlement implementation;
- privacy-governed telemetry;
- backup/restore product flow;
- code signing/publisher metadata;
- release channels/operations.

# 10.10 Phase 10 — Release Qualification & controlled Live pilot

Required before G10:

- all required prior gates green;
- S3 ready;
- long-run soak evidence complete according to frozen criteria;
- FI/drill evidence archived;
- zero open P0 and no unresolved production-critical P1;
- security/recovery/rollback evidence;
- evidence bundle frozen;
- explicit Owner sign-off;
- controlled pilot only under the final frozen Live/compliance policy.

---

# 11. Documentation maintenance still required

Future documentation work should:

- keep `ALGOFORTIS_V2_OWNER_DECISIONS.md` synchronized with any future dated Owner Decision amendments/ADRs;
- update stale AlgoFortis README presentation without breaking compatibility references;
- update these master docs after meaningful phase/merge/gate changes;
- keep technical qualification, merge, Owner approval and soak status separate;
- preserve historical evidence rather than deleting old proof when cleaning names/structure.

---

# 12. Current “do not forget” invariants

For any future engineer/agent reading only this file:

- Current product name: **AlgoFortis**.
- V1 was a large certified platform baseline, not a throwaway prototype.
- V2 is an incremental hardening architecture, not a rewrite.
- Backtest, Paper and Live must remain mode-isolated.
- RiskGate is the V2 executable-order authority.
- Strategy/AI/UI/alerts do not get execution authority.
- Paper cannot reach real broker mutation.
- Recovery/reconciliation precede retry/new entries.
- Safety halts do not silently clear.
- READY_FOR_RESUME still requires explicit manual resume when the recovery latch applies.
- Missing/corrupt policy/state fails closed.
- Phase-4 and Phase-5 technical work is green but remains unmerged at this snapshot.
- Paper soak is running, not passed.
- Canonical Phase 6 has not been implemented/authorized.
- Live remains `READ_ONLY / DISARMED`.

---

# 13. Current bottom line

The repository currently contains two major generations of value:

- **V1:** a certified local Windows trading/product/security foundation with thousands of passing regression tests and a deliberate zero-mutation Live lock.
- **V2 through Phase 5:** stronger bounded contracts, deterministic evidence, Data V2, explicit RiskGate authority, research governance, Strategy SDK, Backtest V2, structurally isolated Paper execution, durable recovery state, reconciliation, protective integrity, host safety, independent alerts, FI qualification and dual-Windows deterministic CI.

The next safe engineering move is **not** to enable Live. It is to close the remaining Phase-5 governance/soak lifecycle, freeze Phase-6 blockers and S2 dependencies, design Phase 6, then build the first real-broker path while keeping mutation DISARMED through qualification.
