# AlgoFortis — Consolidated Project State Summary

**Purpose:** Durable repository-level context restore for future development, review, debugging, and handoff.  
**Snapshot date:** 2026-09-26  
**Functional source head scanned:** `79274f3e3c373caca8065fcc340ef356fc2ff9bd` on `v2-phase5-paper-recovery`  
**Repository:** `olhgtd/ALGOFORTISGPT`  
**Current product name:** **AlgoFortis** — older `SentinelX` names remain in legacy files, tests, launchers, environment variables, and historical documentation.  
**Current safety baseline:** Live remains **READ_ONLY / DISARMED**; no Phase-5 work authorizes real-broker mutation or Live arming.

This document is intentionally detailed. It is a map of what exists, what is authoritative, what has been verified, what is still legacy, and what remains pending. It should be read before starting a new phase or changing a safety-critical boundary.

## Authority / precedence when sources disagree

1. **Current code + tests + exact-head CI evidence** are the strongest description of what is actually implemented.
2. **Canonical V2 control documents** govern intended architecture and build order:
   - `ALGOFORTIS_V2_REQUIREMENTS.md`
   - `ALGOFORTIS_V2_ARCHITECTURE.md`
   - `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`
   - `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`
   - `ALGOFORTIS_V2_OWNER_DECISIONS.md`, plus later authoritative phase-specific decision addenda / ADRs.
3. **Frozen ADRs and phase-specific decision records** override older recommendations when a decision has been explicitly frozen.
4. **Phase designs, implementation plans, evidence reports, and qualification records** explain how a canonical requirement was implemented and verified.
5. **Legacy V1 / SentinelX documents and old README content** are historical/reference material unless a current V2 requirement or ADR explicitly carries the behavior forward.

Important current inconsistency: the root `ALGOFORTIS_V2_OWNER_DECISIONS.md` snapshot is older than the final Phase-5 decision freeze. It still shows OD-V2-19 and OD-V2-24 as OPEN. For Phase 5, `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`, ADR-013, and ADR-014 are the authoritative later amendments until the consolidated root decision register is regenerated.

---

# 1. High-level overview

## 1.1 What AlgoFortis is

- AlgoFortis is a **local-first trading research, risk, backtest, paper-execution, recovery, and future broker-execution platform**.
- Its current focus is not merely “generate a buy/sell signal.” The project is designed to make the whole path from data to decision to execution **deterministic, auditable, fail-closed, recoverable, and testable**.
- The V2 architecture deliberately separates:
  - market/historical data;
  - strategy logic;
  - order intent;
  - risk approval;
  - execution mode;
  - persistence;
  - reconciliation/recovery;
  - protective state;
  - audit/evidence;
  - alerts/host safety;
  - future broker integration.
- Backtest, Paper, and Live are intended to share contracts and safety semantics while remaining **mode-isolated**. Mode is fixed at process/session boundaries; Paper must never silently become Live.
- The platform is **Windows-first and local-first** for V2.0. Cloud/account infrastructure is a parallel control-plane track, not the execution engine.

## 1.2 What problem it is solving

AlgoFortis addresses several failure modes common in trading software:

- **Strategy bypass of risk:** strategies are not allowed to create executable broker orders directly. The Risk Gate is the authority that mints an approved executable capability.
- **Backtest/Paper/Live drift:** contracts and evidence are structured so differences can be measured rather than hidden.
- **Look-ahead / non-deterministic research:** Phase 4 added deterministic research/backtest rules, trials accounting, WFO/OOS/robustness controls, evidence bundles, and cross-machine fingerprints.
- **Unsafe restart behavior:** Phase 5 adds operational states, persistent Paper state, reconciliation, recovery ordering, protective-integrity checks, stale/duplicate suppression, host health, and manual-resume semantics.
- **Silent execution ambiguity:** explicit state machines and fail-closed defaults are preferred over implicit retries or auto-resume.
- **Broker/API instability:** broker-facing behavior is expected to live behind contracts/adapters, with one adapter proven thoroughly before expanding.
- **Uncontrolled promotion:** research output is not automatically promotable. The built-in V2 default is fail-closed / `NON_PROMOTABLE` until a separately versioned numeric promotion policy exists.
- **Credential/privacy risk:** V2.0 is local-first; broker secrets and live trading state are not intended to move to the cloud account service.
- **Operational failure:** sleep/resume, crash, stale feed, clock health, reconciliation mismatch, alert delivery, and recovery are first-class safety concerns, not afterthoughts.

## 1.3 Architectural principles that should remain true

- Contracts before implementations.
- One executable-order authority: **Risk Gate**.
- Uncertainty fails closed.
- Recovery and reconciliation outrank retry and new-entry throughput.
- Deterministic core behavior; time/randomness/IDs should be injectable where relevant.
- Local engine owns trading state; cloud is account/device/entitlement authority only in V2.0.
- Evidence is a product output: audit chain, qualification manifests, deterministic fingerprints, recovery reports, drift reports.
- Explicit state machines are preferred to hidden booleans.
- Restart/reconnect must never auto-arm Live.
- A strategy, AI model, dashboard, alert adapter, or broker adapter does not get to override hard safety/risk policy.

## 1.4 Current maturity at this snapshot

- Phases **0–3 are merged** into the canonical progression.
- Phase **4 is technically complete / evidence-ready**, with PR #6 still open and unmerged.
- Phase **5 implementation and technical qualification are complete**, with PR #8 still open/draft/unmerged; G5 technical evidence is ready, Paper soak has **started**, and explicit Owner gate closure remains pending.
- Phase **6 has not started implementation**. Its preflight/design is blocked by owner decisions and the parallel Track-P/S2 device/session work.
- Live is still **READ_ONLY / DISARMED**.
- A separate Laya research/intelligence shell exists on PR #7, but it is not merged and is not equivalent to completing canonical Phase 8.

---

# 2. Architecture map

## 2.1 Top-level directories

### `.github/`

- GitHub automation and CI configuration.
- `.github/workflows/v2-phase0-baseline.yml` is a **historically named workflow**. The filename says Phase 0, but the workflow has evolved and currently runs Phase 1–5 qualification, full regression, certification, golden checks, and G4/G5 cross-Windows fingerprint comparisons.

### `assets/`

- Static product assets, especially branding resources under `assets/branding/`.
- Branding is AlgoFortis; older SentinelX assets/names may still exist for compatibility/history.

### `build/`

- Build, packaging, certification, static-policy, deterministic-probe, installer/launcher, and release support tools.
- `build/tools/` contains the phase static checkers and deterministic probes that turn architecture rules into CI-enforced boundaries.

### `config/`

- Versioned runtime/deployment/configuration inputs.
- Contains deployment configuration, execution/logging/Paper/risk config, and strategy config roots.
- Production numeric thresholds that have not been evidence-frozen must not be casually invented here merely to make a test pass.

### `dashboard/`

- UI/backend product surfaces.
- Includes backend, owner dashboard, user dashboard, shared/runtime/web areas and sample/demo data used by product/UI flows.
- Dashboards are control/visibility surfaces; they must not become an alternate execution authority that bypasses Risk Gate or Live state policy.

### `data/`

- Local data/runtime storage roots such as incoming files, import reports, Parquet storage, quarantine, and state.
- It is not a licence to ingest arbitrary exchange data: Phase-3 licensing/acquisition policy still applies.

### `docs/`

- Architecture, security, release, legal, beta, UI handoff, V2 ADRs, phase designs, implementation plans, and evidence.
- Key subtrees include `docs/v2/`, `docs/superpowers/`, `docs/legal/`, `docs/releases/`, `docs/beta/`, and UI/product handoff material.
- This `PROJECT_STATE_SUMMARY.md` is the consolidated context map; it does not replace canonical requirements/ADRs.

### `engine/`

- Main runtime/domain implementation.
- Contains modular domains for strategy, risk, orders, execution, Paper, Live state, data, persistence, reconciliation, protective logic, audit, alerts, host safety, reporting, research/backtest, portfolio, options, and supporting infrastructure.

### `strategies/`

- Concrete strategy implementations separated from generic strategy SDK/runtime code.
- Current reference strategy package is `strategies/orb/`, used to shape and verify the Phase-4 SDK rather than designing an abstract SDK in isolation.

### `tests_v1/`

- Main regression and qualification test suite.
- The name is historical; it now contains both legacy/V1 coverage and extensive V2 phase-focused contract, invariant, static-policy, deterministic, persistence, recovery, and failure-injection tests.

## 2.2 Important root control files

- `ALGOFORTIS_V2_REQUIREMENTS.md` — requirement inventory / tiering.
- `ALGOFORTIS_V2_ARCHITECTURE.md` — architecture rules, boundaries, modes, ports/adapters, safety principles.
- `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md` — canonical Phase 0–10 build order plus parallel Platform/Account Track P.
- `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` — gates, invariants, failure injection, release qualification.
- `ALGOFORTIS_V2_OWNER_DECISIONS.md` — consolidated decision register, but currently older than Phase-5 addenda for OD-V2-19/24.
- `README.md` — still contains legacy SentinelX-era presentation and should not be treated as the source of truth for current V2 status/branding.
- `START_ALGOFORTIS.pyw` — current branded launcher entry.
- Legacy `START_SENTINELX.pyw` and related names remain for historical/backward-compatibility reasons; they are not the current product name.
- Locked requirements files define reproducible Python/runtime/test dependencies.

## 2.3 Major `engine/` domains at a glance

- `engine/core/` — configuration, runtime primitives, adapter registry, observability, numeric policy support.
- `engine/data/` — V2 dataset/catalog/store/instrument/data-quality/live-feed foundations.
- `engine/market/` — market calendar/data/profile support.
- `engine/strategy/` — strategy SDK contracts, state, lifecycle, promotion and protective-policy binding.
- `engine/risk/` — Risk Gate, hard limits, kill-switch semantics, legacy risk manager.
- `engine/orders/` — order/intent contracts, validity, intent guard, order lifecycle.
- `engine/options/` — options catalog/policy/selector/live-catalog support.
- `engine/backtest/` — deterministic backtest/replay/fill/evidence logic.
- `engine/research/` — experiment/trial/search/WFO/OOS/robustness/overfitting research tooling.
- `engine/execution/` — execution interfaces and legacy/general Paper execution components.
- `engine/paper/` — Paper orchestration plus Phase-5 V2 Paper safety/recovery modules.
- `engine/persistence/` — migrations/schema plus Phase-5 Paper session/incident/recovery stores/codecs.
- `engine/reconciliation/` — reconciliation domain, with Paper-specific reconciliation separated under `paper/`.
- `engine/protective/` — protective-plan/runtime/policy logic; Phase-5 Paper adds a separate integrity verifier in `engine/paper/`.
- `engine/live/` — Live state machine / current live-domain foundations. Live mutation remains disabled.
- `engine/broker_contract/` — broker-neutral adapter contract/conformance boundary.
- `engine/broker_adapters/` — concrete/mock/legacy broker adapters. Phase-5 Paper V2 must not import this domain.
- `engine/host/` — Phase-5 process lock, clock health, session power and watchdog policy.
- `engine/alerts/` — Phase-5 critical alert contracts/redaction/dispatcher/adapters.
- `engine/audit/` — audit event models, chaining, logs and sinks.
- `engine/reporting/` — report models/serialization/writing/Paper summaries.
- `engine/reproducibility/` — canonical codec, dependency/data/source identity and replay support.
- `engine/portfolio/` — current accounting/model/virtual-account foundations; canonical Phase 7 expands portfolio/risk V2.
- `engine/orchestration/` — legacy/high-level coordination and entry pipelines.
- `engine/safety/` — older/cross-cutting safety components; presence of files such as `phase8_safety.py` does **not** mean canonical Phase 8 is complete.
- `engine/trades/` — trade model and ledger.
- `engine/costs/` — cost models/calculation/projections.

---

# 3. Phase-wise status

## Phase 0 — Decision Freeze & V1 Freeze Audit — **COMPLETE / MERGED**

- Gate: G0.
- Purpose: establish canonical build order, freeze V1 safety baseline, numeric/deployment foundations, and prove existing behavior before V2 changes.
- Key frozen decisions include:
  - OD-V2-01 — revised Phase 0–10 build order is canonical.
  - OD-V2-02 — V2.0 is local-first.
  - OD-V2-03 — tier/completion definition.
  - OD-V2-12 — Decimal/fixed-point for money/price/quantity/risk; floats only in analytics with declared tolerance.
- Historical PR #2 merged.
- Phase-0 deterministic golden behavior remains in later CI as a regression anchor.

## Phase 1 — Engineering Foundation — **COMPLETE / MERGED**

- Gate: G1.
- Foundation areas include runtime primitives, configuration snapshots, audit chain, observability, migrations, module boundaries, and internal adapter registry.
- OD-V2-14 frozen: V2.0 uses an **internal adapter registry only**; third-party signed/sandboxed plugin loading is deferred.
- Historical PR #3 merged.
- Static checker: `build/tools/check_phase1_foundation.py`.

## Phase 2 — Safety Spine — **COMPLETE / MERGED**

- Gate: G2.
- Establishes broker-neutral order/risk authority, hard limits, intent validity, order lifecycle, mode isolation, Live state machine and kill-switch semantics.
- OD-V2-07 frozen:
  - `HALT_ENTRIES` blocks new entries.
  - `CANCEL_PENDING` cancels unfilled entry orders.
  - `FLATTEN_ALL` is separate, explicit, confirmed and audited.
  - Emergency Stop does not silently flatten everything; protective exits remain active.
  - Reconciliation mismatch means halt/alert/recovery, not automatic flatten.
- Historical PR #4 merged.
- Static checker: `build/tools/check_phase2_safety_spine.py`.

## Phase 3 — Data V2 — **COMPLETE / MERGED**

- Gate: G3.
- Data catalog/store, instrument master, as-of rules, deterministic resampling, data quality, licensing/source governance, and live-feed health foundations implemented.
- OD-V2-04: BTCUSD/crypto deferred to V2.3 behind shared abstractions.
- OD-V2-10: licensed historical option-chain data is authoritative for promotion-eligible research; synthetic is labeled fallback and not promotion evidence by default.
- OD-V2-13: immutable Parquet/Arrow historical files + in-process PyArrow Dataset + operational SQLite catalog.
- Strict programmatic NSE-acquisition prohibition/dormant-adapter gate remains part of the design.
- Historical PR #5 merged.
- Static checker: `build/tools/check_phase3_data_v2.py`.

## Phase 4 — Strategy SDK, Research & Backtest V2 — **TECHNICALLY COMPLETE / G4 EVIDENCE READY / PR OPEN**

- Gate: G4 technical evidence is green.
- PR #6: `V2 Phase 4: Strategy SDK, Research & Backtest V2`.
- Current PR #6 state at this snapshot: open, mergeable, **not merged**; head `20310e359eeeb13ee2b4e443717cf654466f68c4`.
- Verified exact-head run #121 / `36097336715`: Windows-latest + Windows-2022, Python 3.13.14, full regression/certification/golden/G4 fingerprint green.
- Major delivered areas:
  - V2 strategy contracts/manifest/state/lifecycle.
  - ORB reference port.
  - experiment registry and append-only trial ledger.
  - explicit search budgets and parameter stability.
  - WFO/OOS/robustness/stress evidence.
  - deflated performance / probability-of-backtest-overfitting evidence.
  - deterministic Backtest V2 and no-lookahead protection.
  - options-aware simulation and batch/local evidence.
  - fail-closed promotion governance/evidence bundle.
- OD-V2-11 frozen: trial budgets + WFO/OOS + versioned overfitting controls.
- OD-V2-17 frozen: built-in default is `research-only/v1`, `NON_PROMOTABLE`; no guessed production promotion numbers.
- ADR-012 freezes Phase-4 research/promotion and ORB protective-policy rules.
- ORB execution simulation requires a versioned `protective_policy_ref`; missing policy fails closed. Test-only protective policies are not promotion evidence.
- **Important:** technical completion is not the same as merge state. PR #6 is still unmerged.

## Phase 5 — Paper V2, Reconciliation & Recovery — **IMPLEMENTED + TECHNICALLY QUALIFIED / OWNER GATE PENDING**

- Gate: G5 technical evidence ready.
- PR #8: `Phase 5: Paper V2 recovery foundations`.
- Current PR #8 state at snapshot: open, draft, mergeable, unmerged; head branch `v2-phase5-paper-recovery`.
- Final functional/docs head before this summary: `79274f3e3c373caca8065fcc340ef356fc2ff9bd`.
- Final exact-head run #204 / `36226897730`: SUCCESS.
- Run #204 verifies both Windows-latest and Windows-2022 with Python 3.13.14, Phase 1–5 focused/static gates, full regression, certification, golden, G4 compare and G5 compare.
- G5 evidence: `docs/v2/phase5/G5_EVIDENCE.md`.
- Paper soak start: `docs/v2/phase5/PAPER_SOAK_START.md`.
- Paper soak status at snapshot:
  - `STARTED / RUNNING`.
  - qualifying sessions completed at start: `0`.
  - long soak pass: **NOT YET EVALUATED**.
- Major delivered areas:
  - Paper operational contracts/states.
  - deterministic conservative Paper fill simulation.
  - Paper-only approved-order execution adapter.
  - V8 additive Paper persistence/checkpoints/incidents/recovery reports.
  - reconciliation/recovery ordering and manual-resume semantics.
  - protective integrity and day/session/expiry boundaries.
  - versioned failure/storm policy.
  - Windows host resilience seams.
  - independent local + Telegram critical alert paths.
  - Paper-vs-backtest drift/evidence reporting.
  - deterministic failure-injection catalogue.
  - Phase-5 runtime wrapper around the legacy Paper runner.
- OD-V2-19 and OD-V2-24 are frozen for Phase 5 by later records:
  - `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md` — OD-V2-24.
  - `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md` — OD-V2-19.
  - `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md` — authoritative Phase-5 amendment.
- The root owner-decision register still shows these as OPEN because it has not yet been consolidated/regenerated.
- **Governance state:** technical exit evidence is ready, but canonical phase Definition of Done still requires explicit Owner gate approval.

## Phase 6 — Live Execution V2 (still DISARMED) — **NOT STARTED / PREFLIGHT BLOCKED**

- Gate: G6.
- Goal: implement and prove one real broker adapter and read-only broker truth integration **without enabling mutation**.
- Canonical scope includes real adapter contract implementation, read-only reconciliation, foreign-order detection, multi-device exclusivity, broker-resident protective orders, broker/exchange rule config, credential handling, token/rate-limit/connectivity handling and dated compliance/broker review.
- Entry requires:
  - G5;
  - Track-P S2 device/session gating ready;
  - OD-V2-05 frozen;
  - OD-V2-06 frozen;
  - OD-V2-08 frozen;
  - OD-V2-09 frozen.
- Current blockers:
  - **OD-V2-05 OPEN** — multi-device live exclusivity.
  - **OD-V2-06 OPEN** — foreign order/position policy.
  - **OD-V2-08 OPEN** — broker-resident protective order requirement/degraded policy.
  - **OD-V2-09 OPEN** — current regulatory/broker compliance path.
  - S2 account/device/session gating is not yet delivered by Track P.
- Phase 6 implementation must keep Live mutation unreachable while DISARMED.

## Phase 7 — Portfolio & Risk V2 — **PENDING**

- Gate: G7.
- Intended scope: multi-strategy capital reservation/release, per-strategy/per-user budgets, portfolio circuit breaker, concentration limits, attribution and event-day risk policy.
- Existing `engine/portfolio/` provides foundations, but canonical Phase-7 completion has not been performed.
- Phase 7 should enforce aggregate exposure through the same safety/risk authority rather than creating a second order path.

## Phase 8 — AI / Agents V2 — **PENDING CANONICAL PHASE**

- Gate: G8.
- Intended V2.0 scope: research + shadow AI, provider abstraction, permissioned tool gateway, TradeCandidate validation, budgets/quotas, prompt-injection controls, audit/replay. AI must not directly place orders.
- OD-V2-15 and OD-V2-16 remain open in the root decision register.
- A file named `engine/safety/phase8_safety.py` and older AI-related safety support do not constitute canonical Phase-8 completion.
- Separate PR #7 (`laya-integration`) is an unmerged research/intelligence shell, not canonical G8 completion:
  - base: Phase-4 branch;
  - head: `65127819df42cf8376de2c4ec13faccd56d9037a`;
  - draft/open/unmerged;
  - actual Laya model/weights/runtime not connected;
  - default disabled/fail-closed;
  - opportunity output `CANDIDATE_ONLY`;
  - strategy hunting `RESEARCH_ONLY`;
  - no broker/live/order/network import path.

## Phase 9 — Product & Operations — **PENDING**

- Gate: G9.
- Intended areas: owner/user operational dashboards, full notifications, runbooks, backup/restore drill evidence, incident templates, compliance/disclosure/consent operationalization, staging and product operations.
- Data-protection/retention decision work such as OD-V2-25 belongs to this later operational/compliance area.

## Phase 10 — Release Qualification & Live Pilot — **PENDING**

- Gate: G10.
- Release Candidate freeze, complete evidence bundle, zero production-critical P0/P1, rollback/restore qualification, and explicit Owner sign-off are required.
- Any future live pilot is separate from Phase 6 code existence. Phase 6 remains DISARMED; Phase 10 is where staged pilot authorization/qualification is considered.

## Parallel Platform / Account Track P — **PENDING / PARTIALLY DESIGNED**

- P1 — close account/release/privacy decisions.
- P2 — account service + anywhere-login + device registry/binding/session authority; feeds S2.
- P3 — installer/updater/licence/telemetry/backup-restore; feeds S3.
- P4 — release packaging/code-signing/release-channel operations.
- Open blockers in root decision register include:
  - OD-V2-20 — update/release channel.
  - OD-V2-21 — licence/entitlement.
  - OD-V2-22 — telemetry/privacy.
  - OD-V2-23 — publisher/version/domain.
- S2 is specifically relevant before Phase-6 exit because Live device/session exclusivity cannot rely only on UI convention.

---

# 4. Module-by-module breakdown

## 4.1 `engine/paper/`

### Responsibility

- Paper-mode orchestration and execution behavior.
- Phase-5 V2 extends Paper with deterministic execution simulation, explicit operational states, recovery coordination, protective integrity, session boundaries, drift/evidence and failure injection.
- Paper is deliberately used as the closest safe rehearsal of Live semantics while remaining structurally unable to mutate a real broker.

### Key files

- `contracts_v2.py` — Phase-5 Paper contracts and canonical operational-state vocabulary.
- `operational_state_v2.py` — pure state-transition authority. States: `HEALTHY`, `DEGRADED`, `HALTED`, `RECOVERY`, `READY_FOR_RESUME`. Resume after sticky recovery requires explicit manual authority.
- `fill_simulator_v2.py` — deterministic conservative bid/ask Paper fills, latency/slippage/rejection/disconnect behavior, fail-closed quote validation.
- `execution_adapter_v2.py` — Paper execution boundary; consumes an approved PAPER capability rather than raw strategy output.
- `recovery_coordinator_v2.py` — recovery sequencing: restore -> reconcile -> protective integrity -> health/session gates.
- `protective_integrity_v2.py` — verifies protective-state integrity independently from reconciliation cleanliness.
- `session_v2.py` — day/session/expiry boundary handling and stale-state invalidation.
- `failure_policy_v2.py` — injected/versioned storm/failure policy with cooldown/reset semantics; no guessed production threshold.
- `drift_report_v2.py` — deterministic explanatory Paper-vs-backtest drift report; not a promotion authority.
- `evidence_v2.py` — deterministic G5/recovery evidence and fingerprints.
- `failure_injection_v2.py` — deterministic Phase-5 failure-scenario catalogue.
- `phase5_runtime_v2.py` — safety wrapper around the existing Paper runner. Enforces second-instance/clock/recovery/manual-resume/cleanup boundaries without rewriting the large legacy runner.
- `option_bridge.py` — existing options bridge behavior.
- `protective_policy_registry.py` — existing protective policy registry.
- `runner.py` — smaller runner/composition area used by the existing Paper system.
- `coordinator.py`, `live_runner.py`, `configuration.py`, `promotion_tracking.py` — large legacy/existing Paper implementation files retained for compatibility/current workflows.

### Dependencies / boundaries

**May communicate with:**
- strategy/order contracts;
- RiskGate-approved order capabilities;
- Paper persistence;
- Paper reconciliation;
- protective state;
- market/live-feed abstractions appropriate to Paper;
- audit/metrics/evidence;
- host/alert seams through the Phase-5 wrapper.

**Must not become dependent on:**
- `engine.live` as an execution authority;
- `engine.broker_adapters` for Paper mutation;
- direct network libraries or Telegram SDK from Paper domain;
- direct raw `sqlite3` persistence from Phase-5 Paper modules;
- hidden auto-arm/auto-resume behavior.

`build/tools/check_phase5_paper_recovery.py` statically enforces these Phase-5 boundaries.

## 4.2 `engine/reconciliation/`

### Responsibility

- Compare expected/persisted owned state with observed execution truth and determine whether the system is safe to proceed.
- Reconciliation is a safety authority for continuity, not an order-submission shortcut.

### Key files / areas

- `engine/reconciliation/paper/engine.py` — dedicated Paper reconciliation implementation.
- Paper reconciliation is intentionally separated from broker contract/adapters and from recovery retry machinery.
- `engine/broker_adapters/mock_recovery.py` is a separate deterministic mock/recovery utility; it is not the Paper reconciliation engine.

### Dependencies / boundaries

**Talks to:** persisted state, observed/simulated execution state, recovery coordinator, audit/evidence.

**Does not own:** strategy decisions, risk bypass, arbitrary retry, Live arming, or automatic flatten.

Core precedence is: reconciliation/recovery first; retry/new entries only after fresh clean truth. A reconnect by itself is not permission to resume.

## 4.3 `engine/persistence/`

### Responsibility

- Local durable schema/migrations and Phase-5 Paper session/recovery persistence.
- Converts in-memory safety state into restart-recoverable evidence without letting missing owned state silently disappear.

### Key files

- `migrations.py` — migration entry/coordination.
- `migrations_base_v7.py` — prior schema baseline.
- `phase5_schema_v8.py` — additive Phase-5 schema extension.
- `paper_codec_v2.py` — encode/decode Phase-5 Paper records deterministically.
- `paper_session_store_v2.py` — Paper session/checkpoint/state persistence.
- `paper_incident_store_v2.py` — incident/alert-related persistence.
- `paper_recovery_store_v2.py` — recovery report/state persistence.
- `schema.py` — schema facade/current schema linkage.

### Dependencies / boundaries

- Used by Paper/recovery/reconciliation/evidence layers.
- Persistence should be accessed through store/contracts rather than scattering raw SQL into Paper runtime modules.
- Missing referenced owned order/position/checkpoint truth is a **fail-closed recovery condition**, not something to skip and continue.
- Schema evolution should remain additive/tested with rollback/migration coverage; migration changes are not casual refactors.

## 4.4 `engine/risk/`

### Responsibility

- Central execution approval and hard-risk enforcement.
- This is the critical boundary between a strategy/request and an executable approved order capability.

### Key files

- `gate_v2.py` — V2 Risk Gate; single approval authority for executable order capability.
- `limits.py` — hard limit policy/validation.
- `kill_switch.py` — kill-switch actions and authority semantics.
- `risk_manager.py` — larger legacy/current risk-manager implementation retained alongside V2 safety spine.

### Dependencies / boundaries

**Inputs:** validated order intent, mode/session context, limits/risk state, relevant portfolio/account state.

**Outputs:** approval/rejection and capability that downstream mode-specific execution can consume.

**Must not be bypassed by:**
- strategies;
- dashboard/UI;
- Paper adapter;
- broker adapter;
- AI/research agent;
- recovery retry logic.

Risk is designed to remain broker-neutral. Broker-specific API quirks belong behind adapters/contracts, not inside core risk authority.

## 4.5 `engine/orders/`

### Responsibility

- Defines order/intent contracts, freshness/validity, lifecycle and intent guarding.

### Key files

- `contracts_v2.py` — V2 intent/order contracts.
- `intent_guard.py` — validates freshness/identity/intent constraints before progression.
- `lifecycle_v2.py` — V2 order lifecycle authority.
- `lifecycle.py` / `model.py` / `validity.py` — legacy/current supporting order models and validity behavior.

### Dependencies / boundaries

- Strategy creates intent, not executable broker mutation.
- Risk Gate consumes valid intent and may mint execution capability.
- Execution/Paper/broker adapter consumes approved output according to fixed mode.
- Lifecycle identity is central to duplicate suppression and stale replay protection.

## 4.6 `engine/strategy/` and `strategies/orb/`

### Responsibility

- `engine/strategy/` is generic V2 SDK/lifecycle/promotion infrastructure.
- `strategies/orb/` is the concrete ORB reference strategy used to prove the SDK and deterministic research/backtest path.

### Key `engine/strategy/` files

- `contracts_v2.py` — strategy contracts/manifest-facing types.
- `state_v2.py` — deterministic strategy state.
- `lifecycle_v2.py` — strategy lifecycle.
- `promotion_v2.py` — fail-closed promotion policy/evidence logic.
- `protective_policy_v2.py` — explicit versioned protective-policy binding.
- `base.py` / `exceptions.py` — base/compatibility infrastructure.

### Key ORB files

- `strategies/orb/manifest_v2.py` — ORB V2 manifest.
- `strategies/orb/orb_v2.py` — V2 ORB implementation.
- `strategies/orb/orb_strategy.py` — small compatibility/reference strategy entry.

### Dependencies / boundaries

- Strategy may consume normalized/as-of-safe market data and versioned configuration.
- Strategy emits a strategy decision/order intent; it does not get broker mutation authority.
- ORB protective economics must come from explicit versioned policy. V2 code must not invent stop/target/trailing economics because a missing value is inconvenient.
- Test-only policy fixtures remain test-only and cannot be silently treated as promotion evidence.

## 4.7 `engine/alerts/`

### Responsibility

- Phase-5 independent critical-alert fan-out with minimal/redacted payloads.
- Alert delivery is observational/notification behavior, not execution authority.

### Key files

- `contracts.py` — shared critical alert envelope/contracts.
- `dispatcher.py` — independent adapter fan-out and delivery-result collection.
- `redaction.py` — removes sensitive credential/token/account/trade-log material.
- `adapters/windows_local.py` — local Windows-visible path.
- `adapters/telegram.py` — external Telegram path/seam.

### Dependencies / boundaries

- One channel failure must not suppress another channel attempt.
- Alert failure is auditable/observable but **must not loosen safety**.
- Alerts may not import/own broker or Live authority.
- Telegram availability is not required for Paper safety to remain correct.
- No remote arm/order command path is authorized by Phase 5.
- Email is a possible future third adapter but was not required for G5.

## 4.8 `engine/host/`

### Responsibility

- Host-level safety surrounding Paper/future Live sessions on Windows.

### Key files

- `instance_lock.py` — single-instance/session ownership guard.
- `clock_health.py` — injectable/versioned clock-health policy and preflight.
- `power_session.py` — temporary active-session sleep-prevention abstraction; does not permanently rewrite Windows power plan.
- `watchdog_policy.py` — crash/watchdog restart semantics; recovery-only, never auto-arm.

### Dependencies / boundaries

- Host domain must stay independent of broker/live mutation logic.
- Sleep/resume during active session invalidates continuity and forces recovery.
- Clock threshold is injected/versioned; no guessed production drift constant is embedded.
- Tests/CI use injectable seams rather than changing real runner clock/power settings.

## 4.9 `engine/data/`

### Responsibility

- V2 data catalog, historical store, instrument identity/as-of mapping, quality, resampling, licensing/source policy and live-feed normalization/health.

### Important behavior

- Immutable/versioned historical evidence is preferred.
- Promotion-eligible options research requires an allowed authoritative data source per OD-V2-10.
- Synthetic data is explicitly labeled and not default promotion evidence.
- No look-ahead/as-of violations may be hidden by convenience lookups.
- Data acquisition licensing restrictions are architecture constraints, not optional warnings.

## 4.10 `engine/market/`

### Responsibility

- Market calendar/session/profile and supporting market-data abstractions.

### Key files

- `calendar.py` — trading calendar/session behavior.
- `data.py` — market-data structures/support.
- `profile.py` — market/instrument profile behavior.

### Boundary

- Calendar/session truth feeds strategy/data/session/recovery logic but should not itself decide execution authority.

## 4.11 `engine/options/`

### Responsibility

- Options instrument catalog, live catalog view, policy and contract selection.

### Key files

- `catalog.py` — option catalog abstraction.
- `live_catalog.py` — live catalog support.
- `policy.py` — selector policy.
- `selector.py` — options selection logic.

### Boundary

- Option Selector can choose a contract according to policy, but the selected contract still passes through order intent + Risk Gate + mode-specific execution. Selection does not grant execution permission.

## 4.12 `engine/backtest/` and `engine/research/`

### Responsibility

- Phase-4 reproducible research and deterministic backtest evidence.

### Backtest responsibilities

- deterministic replay/fill/accounting behavior;
- no-lookahead enforcement;
- options-aware simulation;
- local batch execution/evidence;
- stable fingerprints and report inputs.

### Research responsibilities

- experiment/trial registry;
- append-only trial ledger;
- explicit search budget;
- parameter stability;
- WFO/OOS;
- robustness/stress;
- multiple-testing/overfitting evidence;
- fail-closed promotion evidence creation.

### Boundary

- Research/backtest can produce evidence/candidates; it cannot silently enable Paper or Live execution.
- Promotion profiles are separate, immutable/versioned policy; missing policy means reject/non-promotable.

## 4.13 `engine/reproducibility/`

### Responsibility

- Canonical serialization/identity, dependency/data/source identity and replay support required for deterministic evidence.

### Key files

- `codec.py` — canonical codec/serialization identity.
- `dependencies.py` — dependency provenance.
- `market_data.py` — market-data provenance/fingerprints.
- `source.py` — source identity.
- `replay.py` — replay support.
- `model.py` — reproducibility models.

### Boundary

- Reproducibility should describe inputs/results; it should not become an execution side channel.

## 4.14 `engine/execution/`

### Responsibility

- General/legacy execution interfaces, quote/slippage/fill and Paper execution components predating the focused Phase-5 V2 Paper boundary.

### Key files

- `adapter.py` — execution adapter interface.
- `engine.py` — execution engine behavior.
- `model.py` — execution models.
- `paper_broker.py`, `paper_fill.py` — existing Paper execution implementation.
- `quote.py`, `slippage.py` — quote/slippage primitives.

### Boundary

- Treat this area as existing infrastructure; new Phase-5 safety semantics were intentionally placed in focused `engine/paper/*_v2.py` modules rather than rewriting all legacy execution behavior.

## 4.15 `engine/live/`

### Responsibility

- Live-domain state/safety foundations. Phase 2 established a broker-neutral Live state machine; Phase 6 will add the first fully qualified real adapter path.

### Important current behavior

- Default Live is not armed.
- ACTIVE requires explicit transition authority plus runtime enablement.
- Restart/crash restores into `RECOVERY`, not ACTIVE.
- Audit failure can block state transitions.
- Live mutation remains unreachable under the current READ_ONLY/DISARMED baseline.

### Boundary

- Do not use existence of legacy broker/live files as evidence that canonical Phase-6 Live qualification is complete.

## 4.16 `engine/broker_contract/` and `engine/broker_adapters/`

### Responsibility

- `broker_contract/` defines broker-neutral interfaces/conformance expectations.
- `broker_adapters/` contains concrete/mock/legacy adapter implementations.

### Boundary

- Phase 6 should prove **one** real adapter against the contract kit before expanding.
- Paper V2 cannot import/use broker adapters for mutation.
- Broker-specific quirks should not leak into strategy or core risk logic.
- Real-account Phase-6 work starts read-only while Live remains DISARMED.

## 4.17 `engine/protective/`

### Responsibility

- Protective plan/runtime/policy behavior for stops/targets/OCO/protective management.

### Key files

- `plan.py` — protective plan structures/logic.
- `runtime.py` — protective runtime.
- `runtime_policy.py` — protective runtime policy.
- `live.py` — large existing/legacy Live-protective implementation.

### Boundary

- Protective exits have higher safety priority than new entries.
- Phase 5 adds `engine/paper/protective_integrity_v2.py` specifically to prove that CLEAN reconciliation cannot hide missing/invalid protective state.
- Phase 6 OD-V2-08 will determine/lock broker-resident protective behavior for real Live qualification.

## 4.18 `engine/audit/`

### Responsibility

- Tamper-evident/auditable event trail.

### Key files

- `model.py` — audit event models.
- `chain.py` — chaining/integrity.
- `log.py` — audit-log behavior.
- `sinks.py` — audit destinations/sinks.

### Boundary

- Audit is cross-cutting and safety-critical. A critical action must not proceed as if audited when audit persistence/integrity has failed.

## 4.19 `engine/reporting/`

### Responsibility

- Structured report models, serialization, writing and Paper summary output.

### Key files

- `model.py` — report models.
- `serializer.py` — versioned serialization.
- `writer.py` — report output.
- `paper_summaries.py` — Paper reporting summaries.

### Boundary

- Reports are evidence/visibility outputs; they do not grant promotion or execution authority by themselves.

## 4.20 `engine/core/`

### Responsibility

- Foundation primitives shared across domains.

### Key files

- `adapter_registry.py` — internal adapter registry under OD-V2-14.
- `configuration.py` — configuration loading/snapshot foundations.
- `numeric.py` — numeric-policy support.
- `observability.py` — metrics/observability primitives.
- `runtime.py` — runtime primitives.

### Boundary

- Keep `core` generic. Broker-, strategy-, and UI-specific business logic should not be pushed into foundational primitives just for convenience.

## 4.21 `engine/portfolio/`

### Responsibility

- Existing accounting, portfolio models and virtual account support.

### Key files

- `accounting.py` — accounting behavior.
- `model.py` — portfolio models.
- `virtual_account.py` — larger virtual-account implementation.

### Status/boundary

- This is a foundation, not proof of canonical Phase 7 completion.
- Phase 7 must add portfolio-level reservation/budgets/circuit breakers/concentration controls through the existing risk authority.

## 4.22 `engine/orchestration/`

### Responsibility

- Existing high-level signal/strategy/entry/deployment orchestration.

### Key files

- `signal_intake.py` — signal intake.
- `strategy_coordinator.py` — strategy coordination.
- `entry_pipeline.py` — very large existing entry pipeline.
- `deployment_executor.py` — deployment execution support.
- `user_feed_manager.py` — user feed management.

### Boundary

- This is legacy/high-level coordination. It must not become an alternate V2 order/risk authority.
- New safety-sensitive V2 work should prefer small contract-driven modules instead of continuing to enlarge `entry_pipeline.py`.

## 4.23 `engine/safety/`

### Responsibility

- Existing/cross-cutting safety helpers and historical phase-specific safety implementations.

### Key files

- `safety.py` — existing safety logic.
- `alerts.py` — older safety alert logic, separate from Phase-5 `engine/alerts/`.
- `strategy_halt.py` — strategy halt support.
- `phase8_safety.py` — historical/pre-existing Phase8-named safety file.

### Boundary

- Do not infer roadmap completion from filenames. Canonical phase status is determined by current plan, ODs, tests, evidence and gate qualification.

## 4.24 `engine/trades/` and `engine/costs/`

### Trades

- `trades/model.py` — trade models.
- `trades/ledger.py` — trade ledger.
- Used for durable trade/evidence/accounting views, not as an execution authorization layer.

### Costs

- `costs/model.py` — cost structures.
- `costs/calculator.py` — transaction/cost calculation.
- `costs/projection.py` — cost projection.
- Cost/slippage assumptions must be versioned/evidenced when used for promotion decisions.

---

# 5. Data flow — end to end

## 5.1 Research / Backtest flow

1. Historical dataset is identified through the Data V2 catalog/store with source/licence/provenance.
2. Data quality/as-of/instrument rules validate the dataset before strategy evaluation.
3. Deterministic replay feeds the Strategy SDK/reference strategy.
4. Strategy produces state/decision/order intent; strategy does not produce broker authority.
5. Order/intent validity and Risk Gate rules are applied according to the simulation contract.
6. Backtest execution/fill/options/cost logic produces deterministic lifecycle events.
7. Trade/accounting/reporting/reproducibility layers produce result/evidence artifacts.
8. Research layer records experiment/trial/search-budget/WFO/OOS/robustness/overfitting evidence.
9. Promotion layer evaluates only against an explicit versioned profile.
10. Missing/incomplete promotion policy -> `NON_PROMOTABLE`; no automatic transition to Paper/Live.

## 5.2 Normal Paper flow

1. Live/normalized market data enters the Paper-safe pipeline.
2. Strategy evaluates data and emits a strategy decision / order intent.
3. Option Selector chooses an eligible option contract where the strategy requires one.
4. Intent freshness/identity/validity is checked.
5. **Risk Gate** evaluates the request and, only if allowed, mints a PAPER-approved executable capability.
6. `PaperExecutionAdapter` consumes the approved PAPER capability.
7. `PaperFillSimulator` applies conservative deterministic fill/slippage/latency/rejection/disconnect semantics.
8. Order/fill/position/session state is persisted through Phase-5 stores/codecs.
9. Reconciliation checks expected owned truth versus current Paper execution truth.
10. Protective integrity independently verifies the protective state.
11. Audit, metrics, reporting, recovery evidence and alert evidence are recorded.
12. Drift reporting can compare Paper behavior with Backtest evidence, but cannot self-promote a strategy.

## 5.3 Paper restart/crash/sleep/disconnect recovery flow

1. Failure/discontinuity detected.
2. New entries are blocked; operational state moves toward `DEGRADED`, `HALTED`, or `RECOVERY` as appropriate.
3. Persistent checkpoint/session/order/position truth is loaded.
4. Known owned state is restored.
5. Reconciliation compares restored expected truth with observed/simulated execution truth.
6. Protective integrity is checked separately.
7. Host/clock/session/expiry health gates are evaluated.
8. If truth is clean and safety checks pass, system may reach `READY_FOR_RESUME`.
9. `READY_FOR_RESUME` is **not automatic resume**. Explicit manual resume authority is required to return to normal Paper entry eligibility.
10. If reconciliation is non-clean, state is uncertain, protective state is invalid, clock policy is unhealthy, or audit/state is corrupt: entries stay halted and alert/recovery evidence is produced.
11. Reconnect alone never grants retry/resume permission.
12. Recovery takes precedence over retry or new intent processing.

## 5.4 Duplicate/stale protection flow

- Logical intent/submission identity is deterministic.
- Already-known intent is not resubmitted merely because an acknowledgement is uncertain.
- Stale signal/intent is discarded according to freshness/session rules.
- Uncertain prior submission is reconciled first.
- Mismatch blocks retry.
- Disconnect invalidates assumptions about prior CLEAN state.
- Day/session/expiry rollover re-evaluates eligibility; prior-session stale intent must not replay.

## 5.5 Audit / observability side flow

Across strategy, risk, Paper, recovery, host and alert operations:

- significant state transitions and safety decisions produce audit/observability evidence;
- alert delivery results are observable/auditable independently from trading safety;
- reporting/evidence is downstream of authority rather than a replacement for it;
- audit failure on critical paths must fail closed rather than pretending the action is recorded.

## 5.6 Current Live flow vs future Phase-6 flow

### Current

- Live state machine and safety foundations exist.
- Live defaults remain READ_ONLY/DISARMED.
- No Phase-5 code authorizes mutation.
- Existing broker/live files do not equal G6 qualification.

### Planned Phase 6

1. Real broker adapter implements the broker contract kit.
2. Credentials remain local and protected per security policy.
3. First integration is read-only broker/account/order/position truth.
4. Foreign order/position policy and multi-device exclusivity are frozen and enforced.
5. Read-only reconciliation is proven over multiple sessions.
6. Token refresh/rate-limit/disconnect/reconnect behavior is chaos-tested.
7. Broker-resident protective behavior is frozen/verified.
8. Regulatory/broker compliance outcome is recorded.
9. Live mutation is **still unreachable while DISARMED**, even after adapter conformance exists.

---

# 6. Testing strategy

## 6.1 Test suite layout

`tests_v1/` is a combined legacy + V2 suite rather than a clean per-phase directory tree. The flat naming makes phase prefixes important.

### Legacy / product-area regression examples

- `test_api_hardening.py`
- `test_architectural_foundations.py`
- `test_area1_auth_security_recovery.py`
- `test_area2_backup_restore_dr.py`
- `test_area3_installer_update_lifecycle.py`
- `test_area4_ui_integration_readiness.py`
- `test_area5_complete_product_workflows.py`
- `test_area6_performance_stability_sanity.py`
- `test_area7_broker_adapters.py`
- `test_area8_credential_vault.py`
- `test_area9_historical_providers.py`
- `test_area10_live_feeds_isolation.py`
- `test_area11_user_lifecycle_gates.py`
- `test_area12_broker_execution_adapters.py`
- `test_area13_multi_broker_deployments.py`
- `test_area14_live_reconciliation_restart.py`
- `test_area15_security_remediations.py`
- database/migration/security/regression tests.

### Phase-1 focused families

- runtime primitives;
- module boundaries;
- configuration snapshots;
- audit chain;
- observability;
- migrations;
- adapter registry.

### Phase-2 focused families

- Risk Gate authority;
- hard limits;
- intent guard;
- V2 order lifecycle;
- mode isolation;
- Live state machine;
- kill switch;
- CI/static guard behavior.

### Phase-3 focused families

- dataset catalog;
- historical store;
- instrument master/as-of behavior;
- data quality;
- deterministic resampling;
- licensing/source policy;
- live-feed health;
- CI/static guard behavior.

### Phase-4 focused families

- strategy SDK/contracts/state;
- ORB reference port;
- experiment tracking / durable trial ledger;
- search budget / stability;
- WFO/OOS;
- robustness/stress;
- overfitting controls;
- Backtest V2;
- no-lookahead;
- options simulation;
- promotion / protective policy;
- lifecycle / batch / evidence bundle;
- deterministic probe / CI guard.

### Phase-5 focused files

- `test_phase5_contracts.py`
- `test_phase5_operational_state.py`
- `test_phase5_fill_simulator.py`
- `test_phase5_persistence.py`
- `test_phase5_recovery.py`
- `test_phase5_protective_integrity.py`
- `test_phase5_failure_policy.py`
- `test_phase5_host_resilience.py`
- `test_phase5_alerts.py`
- `test_phase5_drift_report.py`
- `test_phase5_failure_injection.py`
- `test_phase5_runtime_wiring.py`
- `test_phase5_architecture_guard.py`
- `test_phase5_qualification_guard.py`

## 6.2 Static policy checks

Current major static checkers in `build/tools/`:

- `check_module_boundaries.py`
- `check_phase1_foundation.py`
- `check_phase2_safety_spine.py`
- `check_phase3_data_v2.py`
- `check_phase4_research_backtest.py`
- `check_phase5_paper_recovery.py`

These are not style-only lint. They encode architectural rules so an unsafe import/default/deletion can fail CI before runtime tests.

### Phase-5 static checker specifically protects

- required Phase-5 authority/test files are present;
- Paper V2 does not import `engine.broker_adapters` or `engine.live`;
- Paper V2 does not directly pull in raw `sqlite3`, `requests`, `httpx`, Telegram SDK, or Win32 APIs as hidden dependencies;
- host and alert domains do not import broker/live mutation authority;
- guessed production storm threshold constants are rejected;
- guessed production clock-drift constants are rejected;
- embedded module-level default production policy profiles are rejected where policy must be injected/versioned;
- permanent Windows power-plan mutation is rejected;
- Live default `arm_enabled=True` is rejected;
- Live default ACTIVE initial state is rejected;
- canonical Paper operational state vocabulary is pinned;
- Phase-5 runtime wrapper and focused test are pinned so they cannot be silently deleted/bypassed.

## 6.3 Deterministic probes

- `build/tools/phase4_probe.py` produces a deterministic G4 fingerprint/evidence marker set.
- `build/tools/phase5_probe.py` produces deterministic G5 recovery/safety markers.
- Cross-Windows jobs compare outputs byte/semantically as required rather than assuming two green local runs are equivalent.

G5 cross-Windows comparison explicitly requires markers including:

- final state `READY_FOR_RESUME`;
- manual resume required;
- duplicate order count = 0;
- stale replay count = 0;
- default Live state = READ_ONLY/DISARMED.

## 6.4 Current CI qualification pipeline

Workflow file: `.github/workflows/v2-phase0-baseline.yml`.

Despite the old filename, current run name is **V2 Phase 5 Paper Recovery Qualification** and it performs:

1. exact-head checkout;
2. Python 3.13.14 setup;
3. locked runtime/dashboard/test dependency installation;
4. environment recording;
5. V2 module-boundary policy;
6. compile gate;
7. Phase-1 static + focused validation;
8. Phase-2 static + focused validation;
9. Phase-3 static + focused validation;
10. Phase-4 static + focused validation;
11. Phase-4 deterministic fingerprint upload;
12. Phase-5 static + focused validation;
13. Phase-5 deterministic fingerprint upload;
14. full `tests_v1` regression;
15. existing regression certification;
16. Phase-0 frozen deterministic golden probe;
17. G4 cross-Windows fingerprint comparison;
18. G5 cross-Windows fingerprint comparison.

Matrix/runner evidence at the final Phase-5 snapshot:

- Windows latest;
- Windows 2022;
- Python 3.13.14;
- exact final head run #204 / `36226897730`: SUCCESS.

## 6.5 TDD / RED -> GREEN evidence pattern

Phase 5 was implemented slice-by-slice with explicit failing tests before authority implementation. Important examples recorded in G5 evidence:

- persistence hardening: RED `d4e623195084166d14cb065e79b299bc7be467d9` -> GREEN `690e16902c6cf39ca6a35c469ec048993e30d775`;
- alerts: RED `4894b05c9eadf817bb6e7038d150823754dd4af5` -> GREEN `72bdbb4ab65775c2d84d1a36cdd750cbb5a89d0e`;
- drift/evidence: RED `73a6af5b2ddd34f55f90581a9810c102d73cef46` -> GREEN `9559e3d68ce19d262a28335d21d105f6decac33e`;
- FI catalogue: RED run #194 at `c7c5c6dfc330664d02ebc2a7aa4bf289c731ed02` before implementation;
- runtime wiring: RED `3214b0d028e7012c69781d6fc74c64bb5c0df798` -> GREEN `b78318a0fc3015be499dd0d711f22c66f075e93e`;
- runtime static pin: RED `174b3ddf297be6150ac9a2d1b1c2fbee2fd2a2bc` -> GREEN `866fd2438807ceed23c69e76fd538ce1437906d9`.

## 6.6 Failure injection scope and limitation

Phase-5 deterministic catalogue covers:

- FI-01 through FI-09;
- FI-12 through FI-14;
- FI-23;
- FI-24.

It verifies safety semantics such as duplicate suppression, stale replay suppression, recovery state, protective integrity, clock/sleep policy seams, alert attempts and fail-closed outcomes.

It does **not** claim CI physically:

- crashes a production PC;
- changes the real Windows clock;
- disconnects actual networking hardware;
- fills a real disk;
- contacts or mutates a real broker account.

Those deterministic fixtures prove the software response contracts. Real operational soak/drills remain separate evidence.

---

# 7. Known constraints / deliberately-avoided files and patterns

## 7.1 Live safety baseline is non-negotiable at this snapshot

- Live = `READ_ONLY / DISARMED`.
- No real broker mutation is authorized by Phase 5.
- Restart/crash/reconnect must not auto-arm.
- Phase 6 itself is designed to remain DISARMED while proving adapter/read-only reconciliation.
- A successful test or available adapter is not Owner authorization for live mutation.

## 7.2 One executable-order path

- Strategy -> intent -> Risk Gate -> approved capability -> mode-specific execution.
- No dashboard, AI, Paper module, broker adapter, recovery loop, or legacy orchestration path may mint its own equivalent execution authority.

## 7.3 Fixed mode / isolation

- BACKTEST, PAPER, LIVE are intentionally isolated.
- Paper must not import or silently fall through to real broker mutation.
- A mode mismatch should fail rather than “helpfully” route somewhere else.

## 7.4 Recovery before retry

- Reconciliation/recovery precedes retry/new entries.
- Reconnect does not imply CLEAN.
- Uncertain acknowledgement -> reconcile first.
- Mismatch -> halt, not blind retry.
- Stale intents do not replay after restart/session rollover.

## 7.5 No automatic safety clearing

- Sticky halt/recovery conditions are not self-cleared merely because one dependency came back.
- Phase-5 recovery can reach `READY_FOR_RESUME`, but explicit manual resume is still required.

## 7.6 Kill-switch constraint

- Emergency Stop semantics are frozen by OD-V2-07.
- `FLATTEN_ALL` remains a separate, explicit, confirmed, audited action.
- Reconciliation mismatch does not automatically flatten positions.

## 7.7 No invented production numbers

Do not create guessed production defaults simply to make a component executable:

- strategy promotion thresholds;
- Paper/backtest drift tolerances;
- failure-storm threshold/window/cooldown policy;
- host clock drift threshold;
- minimum hardware figures;
- Live rollout/pilot numbers;
- ORB stop/target/trailing economics.

Where numbers are not frozen, use injected/versioned policy and fail closed.

## 7.8 Numeric correctness

- Money, price, quantity and risk use Decimal/fixed-point policy.
- Float use is analytics-only with declared tolerance.
- Rounding/tick rules are explicit/versioned per instrument where required.

## 7.9 Data/licensing constraints

- Historical options evidence must respect source licensing.
- Synthetic options data is clearly labeled and excluded from promotion evidence unless a later explicit decision allows it.
- Strict NSE programmatic-acquisition prohibition/dormant-adapter policy remains in force.

## 7.10 Cloud/local boundary

- V2.0 execution is local-first.
- Broker credentials, live positions/trading state, and live order execution are not cloud-account responsibilities.
- Cloud/account outage must not loosen local safety; it also must not silently create new authentication/entitlement authority.

## 7.11 Large legacy files — avoid casual extension/rewrite

These files are not “forbidden forever,” but they are high-risk, legacy-heavy or already too large. New focused V2 behavior should prefer small modules/contracts/wrappers unless a separate design explicitly justifies refactoring them.

- `engine/paper/coordinator.py` — approximately 214 KB; very large legacy Paper coordinator. Phase 5 deliberately did not pour new recovery logic into it.
- `engine/paper/live_runner.py` — approximately 83 KB; large legacy Paper runner. Phase 5 wrapped rather than rewriting it.
- `engine/paper/configuration.py` — approximately 32 KB; existing Paper configuration logic.
- `engine/paper/promotion_tracking.py` — approximately 39 KB; existing promotion-tracking implementation.
- `engine/orchestration/entry_pipeline.py` — approximately 97 KB; large existing orchestration/entry pipeline; do not create a second V2 authority inside it.
- `engine/risk/risk_manager.py` — approximately 59 KB; legacy/current risk manager; new V2 authorization rules belong in focused Risk Gate/contracts rather than ad-hoc additions.
- `engine/protective/live.py` — approximately 42 KB; existing Live protective implementation; future Phase-6 changes require explicit design/OD alignment.
- `engine/portfolio/virtual_account.py` — approximately 38 KB; existing virtual-account foundation; canonical Phase-7 additions should be designed, not appended blindly.

## 7.12 Legacy naming and documents

- Current product is AlgoFortis.
- `README.md` still presents SentinelX-era naming and startup instructions.
- Legacy launchers/environment variables/test fixture names may still say SentinelX.
- Rename cleanup must not silently alter internal DB/schema IDs or compatibility contracts unless explicitly planned.

## 7.13 Deterministic fault tests are not real-world soak

- Passing FI fixtures is necessary but does not replace real Paper-session soak, restart drills, expiry exposure, network/disconnect observation or later real-broker read-only qualification.

## 7.14 No silent strategy/AI promotion

- Phase-4 built-in promotion is fail-closed/non-promotable without explicit versioned profile.
- Laya PR #7 is research/intelligence-only and disabled by default; it is not allowed to become an execution side path.
- Canonical Phase-8 AI is planned as research/shadow first.

## 7.15 Merge/governance discipline

- Technical green != merged.
- Merged != later Live authorization.
- Gate evidence != Owner gate approval where the plan requires Owner approval.
- PR #6, #7 and #8 remain unmerged at this snapshot.

---

# 8. Open / pending items

## 8.1 Phase-5 governance / soak

- Explicit Owner G5 gate approval is still required for canonical Phase-5 closure under the plan Definition of Done.
- Paper soak has started but has not completed.
- At campaign start: 0 qualifying sessions completed.
- The release plan proposes a longer target of at least 20 consecutive trading sessions including relevant weekly/monthly expiry exposure and induced restart/recovery/disconnect cases, with zero unresolved safety mismatch/invariant violation/unexplained duplicate/stale replay/P0/P1 failures.
- That longer-run target is **not claimed passed** in current evidence.
- Real session evidence still needs to accumulate: session boundaries, recovery incidents, drift, alert delivery, host/resource observations, expiry behavior.

## 8.2 Branch / PR sequencing

### PR #6 — Phase 4

- Technical G4 green.
- Open, mergeable, unmerged.
- Must not be described as merged Phase 4 until actually merged.

### PR #8 — Phase 5

- Technical G5 green on its branch.
- Open, draft, mergeable, unmerged.
- Because the work is stacked/evolved from prior V2 branches, merge/retarget sequencing must be reviewed carefully rather than assuming PR metadata alone describes dependency order.

### PR #7 — Laya shell

- Open/draft/unmerged.
- Based on Phase-4 branch.
- Actual Laya model/runtime not connected.
- After upstream branch changes/merges, it requires retarget/requalification before merge consideration.

## 8.3 Owner decision register consolidation

- Root `ALGOFORTIS_V2_OWNER_DECISIONS.md` should eventually be regenerated/updated so OD-V2-19 and OD-V2-24 no longer appear OPEN after Phase-5 ADR/addendum freeze.
- Until then, Phase-5 addendum + ADR-013/ADR-014 are the later authoritative records.

## 8.4 Phase-6 design blockers

Before implementation of canonical Live Execution V2:

- OD-V2-05 must be frozen — multi-device live exclusivity.
  - Current recommendation: local hard backstop is mandatory; optional cloud advisory can exist later but must not be the only safety mechanism.
- OD-V2-06 must be frozen — foreign order/position policy.
  - Current recommendation: halt new entries + alert; explicit user adoption only; never auto-adopt.
- OD-V2-08 must be frozen — broker-resident protective orders / degraded policy where unsupported.
- OD-V2-09 must be frozen — dated regulatory and chosen-broker compliance path.
- Track-P S2 device/session gating must be ready.
- One real broker should be selected/proven extremely well before a second adapter.
- Initial real broker integration should prove read-only account/order/position reconciliation before mutation is even considered.
- Live remains DISARMED through G6 qualification.

## 8.5 Track-P/account platform blockers

- OD-V2-20 — update/release channel policy.
- OD-V2-21 — licence/entitlement/offline-grace behavior.
- OD-V2-22 — telemetry/privacy.
- OD-V2-23 — publisher/version/canonical domain.
- P2 account/device/session service is required to produce S2 for later Live device/session control.
- Optional “engine silent/dead PC” remote heartbeat remains tied to telemetry/privacy policy and was deliberately not made a Phase-5 G5 requirement.

## 8.6 Numeric policies intentionally still open/evidence-driven

- First production promotion profile numbers.
- Backtest-to-Paper and Paper-to-live-eligible drift tolerances.
- Production clock drift threshold.
- Hardware minimums derived from measured resource evidence.
- Live pilot/ramp numbers under later release decisions.

None should be copied from legacy values or guessed without a dated versioned decision/profile.

## 8.7 Phase 7 pending work

- capital reservation/release;
- per-strategy/user budgets;
- portfolio concentration limits;
- portfolio circuit breaker;
- attribution;
- event-day risk policy;
- aggregate exposure enforcement through the existing Risk Gate.

## 8.8 Phase 8 pending work

- freeze OD-V2-15/16;
- provider registry/adapters under a data-sharing allowlist;
- tool gateway with permission allowlists;
- research / risk-challenger agents;
- deterministic `TradeCandidate` validation;
- prompt-injection defenses;
- cost/budget quotas;
- shadow evaluation/audit/replay;
- explicit proof no AI output can reach an order except through deterministic strategy/risk gates.
- Laya actual model/runtime integration remains separate/unmerged and must stay research-only unless future canonical design changes.

## 8.9 Phase 9 pending work

- full operational dashboards;
- full notification set;
- runbooks;
- backup/restore and rollback drills;
- incident templates;
- staging operations;
- compliance/disclosure/consent operationalization;
- data-protection/retention policy decisions.

## 8.10 Phase 10 pending work

- complete G0–G10 release qualification;
- Release Candidate freeze;
- archive full evidence bundle;
- zero open production-critical P0/P1;
- restore and rollback drills;
- Paper soak pass, not merely started;
- LEM confirmation;
- explicit Owner sign-off before any staged Live pilot.

## 8.11 Documentation / technical-debt cleanup

- Update root README from SentinelX-era product naming to current AlgoFortis when a dedicated documentation/branding cleanup is authorized.
- Consolidate root Owner Decision register with later phase amendments.
- Continue distinguishing legacy support files from current V2 authoritative modules; do not delete legacy compatibility code merely for cleanliness without regression/migration evidence.
- Consider future refactoring of oversized legacy files only as separately designed work; do not mix it into safety-critical phase delivery.

---

# Final state markers for fast context restore

- **Product:** AlgoFortis — local-first Trading Research & Risk OS / trading platform.
- **Current branch at source scan:** `v2-phase5-paper-recovery`.
- **Source scan head:** `79274f3e3c373caca8065fcc340ef356fc2ff9bd`.
- **Phase 0–3:** merged.
- **Phase 4:** technically G4 green; PR #6 open/unmerged.
- **Phase 5:** implementation + technical G5 qualification green; PR #8 open/draft/unmerged; Owner gate approval pending.
- **Paper soak:** STARTED/RUNNING; 0 qualifying sessions completed at start; long soak not yet evaluated.
- **Phase 6:** not started; OD-V2-05/06/08/09 + S2 are blockers.
- **Live:** READ_ONLY / DISARMED.
- **Real-broker mutation:** not authorized by current V2 state.
- **Risk authority:** `engine/risk/gate_v2.py` is the V2 executable-order approval boundary.
- **Phase-5 runtime safety wrapper:** `engine/paper/phase5_runtime_v2.py`.
- **Phase-5 evidence:** `docs/v2/phase5/G5_EVIDENCE.md`.
- **Phase-5 soak record:** `docs/v2/phase5/PAPER_SOAK_START.md`.
- **Phase-5 decision addendum:** `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`.
- **Laya:** separate unmerged research-only shell on PR #7; actual model/runtime not connected.
- **Current CI:** dual-Windows exact-head qualification with Phase 1–5 static/focused tests, full regression/certification, frozen golden, G4 and G5 deterministic cross-Windows compares.
