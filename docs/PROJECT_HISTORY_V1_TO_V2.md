# AlgoFortis — Complete Project History: V1 to V2

**Purpose:** Durable A-to-Z historical record of how the project evolved from the AlgoFortis/V1 baseline into AlgoFortis V2, including what was actually verified, what was only planned, what was deliberately deferred, what V2 preserved, what V2 hardened, and what remains future work.
**Snapshot date:** 2026-09-26  
**Repository:** `olhgtd/ALGOFORTISGPT`  
**Current branch while this record was written:** `v2-phase5-paper-recovery`  
**Current safety invariant:** Live is `READ_ONLY / DISARMED`; this history does not authorize broker mutation or Live arming.

---

# 0. How to read this history

The project contains several generations of documents and code. To avoid confusing a design decision with an implemented feature, this file uses the following status language consistently:

- **PLANNED** — described in an implementation plan, but not by itself proof that production code was delivered.
- **FROZEN DECISION** — an architecture/Owner decision was accepted and became a build constraint; it does not automatically mean the feature was deployed.
- **IMPLEMENTED** — code exists for the capability.
- **VERIFIED** — tests/evidence exist for the capability at a named checkpoint.
- **CERTIFIED BASELINE** — a broad regression/certification checkpoint passed and is suitable as a reference baseline.
- **MERGED** — integrated into the target branch.
- **DEFERRED** — deliberately postponed.
- **NOT ALLOWED** — intentionally prohibited by architecture/safety policy.
- **OPEN / PENDING** — still requires design, Owner decision, implementation, verification, merge, soak, or some combination of those.

When old V1 plans conflict with later V2 requirements, later frozen V2 decisions and exact-head code/tests/evidence take precedence.

---

# 1. Project identity: AlgoFortis to AlgoFortis

## 1.1 AlgoFortis origin

The repository began as **AlgoFortis**, a Windows-focused algorithmic trading platform with a local backend, modular engine, owner/user dashboard, Paper trading, risk controls, broker abstractions, audit/reconciliation, local runtime data, and a strong fail-closed posture.

Legacy repository material still reflects that identity:

- `README.md` still presents “AlgoFortis — Algorithmic Trading Platform”.
- Legacy launcher/path names such as `START_ALGOFORTIS.pyw`, `%LOCALAPPDATA%\AlgoFortis`, AlgoFortis database names, environment variables and older tests remain in the tree.
- These names are historical/backward-compatibility artifacts; they are not the current product identity.

## 1.2 AlgoFortis identity

The V1 architecture froze the product identity as:

- **Product:** AlgoFortis
- **Tagline:** Trading Research & Risk OS
- **Primary V1 deployment:** local Windows desktop
- **Design goal:** institutional-style separation between UI/account concerns and trading/risk/runtime concerns while keeping the trading engine local and fail-closed.

The migration policy deliberately avoided a destructive mass rename. Existing internal IDs/schema/history could remain compatible while visible surfaces, launcher/installer/publisher metadata and future product identity moved to AlgoFortis.

## 1.3 Naming rule for current development

For current work:

- **AlgoFortis** is the current project/product name.
- **AlgoFortis** refers to legacy history, old paths, older launcher/runtime identifiers, old documentation or compatibility contracts.
- A file retaining “AlgoFortis” in its name should not be assumed obsolete without checking dependencies/tests.

---

# 2. V1 architectural vision

The frozen V1 master architecture described a four-layer model. Some parts were already present locally, while other parts were future product/platform targets. The important point is that the V1 architecture established the boundaries and safety philosophy that V2 later hardened.

## 2.1 Layer A — Desktop client and user experience

V1 defined a Windows desktop/client layer responsible for:

- owner and user visual workspaces;
- authentication/session UX;
- market/backtest/Paper visibility;
- strategy and governance screens;
- system/security controls;
- a stable Engine API boundary instead of UI code directly importing execution internals.

The repository contains substantial dashboard/UI implementation around this model, including:

- root surface routing;
- secure-entry flows;
- owner/user workspaces;
- runtime availability checks;
- charts;
- backtest screens;
- strategy workflow surfaces;
- access/security administration;
- options workspace;
- order/portfolio/readiness components.

## 2.2 Layer B — Local trading runtime

The V1 runtime concept kept trading logic on the local machine. Major responsibilities included:

- market data processing;
- strategy execution;
- deterministic backtest;
- Paper trading;
- risk and protective logic;
- order/execution state;
- reconciliation and audit;
- portfolio/accounting foundations;
- local broker credentials and local trading data.

This local-first execution model became one of the strongest carry-forward V2 constraints.

## 2.3 Layer C — Central account authority

V1 architecture also defined a central account authority for identity/device/entitlement concerns, with concepts such as:

- WebAuthn/passkeys for interactive user authentication;
- a separate device-identity key;
- maximum authorized-device rules;
- rotating session/refresh-token families;
- recovery workflows;
- signed offline entitlement leases;
- central identity/device records without centralizing broker secrets or trading state.

Important historical distinction: these were architecture and product-platform decisions. The V1 implementation plan explicitly left some cloud deployment work as future work. Therefore “FINAL ADR” for an AWS/account design does **not** mean the whole cloud stack was deployed and production-qualified in V1.

## 2.4 Layer D — Local storage and secrets

V1 established strong local-data and secret boundaries:

- trading strategies remain local;
- broker credentials remain local;
- local trading positions/orders/logs are not cloud-synced;
- private device keys stay on the device;
- device trust is not derived from weak hardware/network fingerprints;
- local storage/security ACLs are part of the safety posture.

---

# 3. V1 frozen architectural decisions

The V1 decision register froze a broad set of product/security/deployment choices. These decisions are historically important because many became direct inputs into V2.

## 3.1 Product and deployment decisions

V1 froze:

- AlgoFortis branding and product identity.
- Four-layer architectural decoupling.
- Local Windows desktop as the primary V1 deployment profile.
- Windows VPS compatibility as an architectural target.
- Remote-engine architecture as **DEFERRED** rather than a V1 requirement.
- Semantic versioning/API versioning/migration namespaces.
- A Windows installer/WebView2 shell architecture.

## 3.2 Authentication and device decisions

V1 froze:

- WebAuthn and device identity as separate concepts.
- TPM/CNG preferred for device keys with DPAPI fallback.
- a device quota model without silent eviction;
- short-lived access token + rotating refresh-token family semantics;
- refresh reuse detection/revocation;
- same-PC reinstall identity preservation;
- high-assurance recovery revoking old trust/session state;
- isolated rate-limit flows with progressive cooldown;
- single-use activation-code lifecycle.

## 3.3 Data sovereignty and cloud boundaries

V1 froze that:

- strategies, broker keys, live positions, orders and execution ledgers stay local;
- cloud/account authority cannot become a trading authority;
- cloud outage must never loosen local safety;
- local protective/risk controls continue even if account/cloud services are unavailable.

## 3.4 Backup/update/entitlement/privacy decisions

The V1 architecture froze designs for:

- `AlgoFortisBackup/v1` with secret exclusion;
- clean uninstall preserving user state by default;
- signed update manifests/Authenticode/checksum verification and rollback;
- signed offline entitlement leases;
- privacy-preserving telemetry;
- sanitize-first support bundles.

Again, a frozen design is not automatically proof of deployed production infrastructure. Actual V1 verification is captured separately below.

## 3.5 V1 safety lock

One of the most important decisions, ADR-27, froze the Live execution lock. The certified V1 baseline preserved:

- `READ_ONLY = true`
- `DISARMED = true`
- `live_global_hold = true`
- broker mutation = zero
- real broker connection = none

That invariant is still intentionally preserved in V2 development.

## 3.6 V1 explicitly deferred capabilities

V1 architecture explicitly deferred or excluded from V1 release scope:

- multi-region AWS;
- multi-owner administrative quorum;
- enterprise SSO;
- mobile applications;
- cloud synchronization of proprietary strategies or broker secrets;
- full real-money Live execution;
- some remote-engine behavior;
- push-style roaming-device session termination.

## 3.7 V1 explicitly forbidden patterns

V1 prohibited:

- cloud storage of broker credentials;
- cloud execution of live orders through central auth;
- plaintext password/refresh-token storage;
- device trust based only on MAC/hostname/IP;
- silent device eviction;
- cloud outage failing open;
- cloud synchronization of private device keys;
- secrets in URL query strings;
- bypassing high-assurance admin authentication;
- weakening private local ACL/security controls.

These prohibitions strongly influenced V2’s local-first architecture.

---

# 4. V1 implementation plan — what it planned, not what it automatically proved

`ALGOfORTIS_IMPLEMENTATION_PLAN_V1.md` is explicitly marked **PLAN ONLY — FROZEN SPECIFICATION — DO NOT EXECUTE**. It described a 13-stage journey from the AlgoFortis baseline to a productized AlgoFortis V1. Future readers must not read all 13 stages as automatically completed.

## Stage 1 — Compatibility inventory

Planned mapping of:

- paths;
- schema IDs;
- environment variables;
- persisted state;
- legacy AlgoFortis compatibility.

Goal: migrate branding/product structure without losing audit/history/state compatibility.

## Stage 2 — Brand migration

Planned transition of visible identity to AlgoFortis while avoiding unnecessary changes to internal identifiers or trading behavior.

## Stage 3 — Internal API boundary hardening

Planned stronger separation between UI/client and trading runtime using versioned `/api/v1/` contracts.

## Stage 4 — Device/security persistence

Planned device identity with CNG/TPM preference and DPAPI fallback, plus secure reinstall behavior.

## Stage 5 — Local auth/session compatibility

Planned dual-token/rotation/reuse-detection/rate-limit behavior.

## Stage 6 — Backup and uninstall

Planned portable backup contract and user-data-preserving uninstall semantics.

## Stage 7 — Updater foundations

Planned signed update verification and rollback behavior.

## Stage 8 — Entitlement foundations

Planned signed offline entitlement leasing with safety-preserving expiry behavior.

## Stage 9 — Telemetry and privacy

Planned opt-in/minimal telemetry and redacted support bundles.

## Stage 10 — Windows packaging

Planned native AlgoFortis shell/installer and bundled runtime.

## Stage 11 — Full regression and security certification

Planned end-to-end certification across security, runtime lifecycle, install/upgrade and trading simulation.

## Stage 12 — Future AWS central account authority

This stage was explicitly a **future deployment plan**, not evidence that AWS production infrastructure was completed in V1.

## Stage 13 — Future VPS / remote-engine adapter

This stage was explicitly future evolution. Remote execution was not required for the certified local V1 baseline.

---

# 5. What V1 was actually verified to have achieved

The strongest V1 implementation truth is `CLEAN_CHECKPOINT.md`, not the aspirational 13-stage plan.

## 5.1 Final clean product source checkpoint

The clean checkpoint, dated 2026-09-14, records a certified source baseline after product cleanup/remediation.

Recorded verification:

- **3761 pytest tests passed**;
- **0 failed**;
- **0 errors**;
- frontend TypeScript/Vite production build passed;
- recovery-authority verification passed;
- leaf symlink/junction hardening passed;
- P0 findings: none;
- P1 findings: none;
- P2 findings: none;
- pre-next-stage blockers: none.

This makes V1 a real, heavily tested engineering baseline rather than just a design document.

## 5.2 V1 certified safety baseline

The clean checkpoint explicitly preserved:

- Live read-only;
- Live disarmed;
- global live hold;
- zero broker mutation;
- no real broker connection;
- fail-closed behavior through the disabled Live execution boundary.

## 5.3 V1 broad test domains

The historical `tests_v1/` suite shows that V1 work covered a wide product/runtime/security surface. Major area suites include:

1. authentication, security and recovery;
2. backup/restore/disaster-recovery behavior;
3. installer/update lifecycle;
4. UI integration readiness;
5. complete product workflows;
6. performance/stability sanity;
7. broker-adapter behavior;
8. credential vault/security storage;
9. historical data providers;
10. live-feed isolation;
11. user lifecycle gates;
12. broker execution adapters;
13. multi-broker/deployment abstractions;
14. live reconciliation/restart semantics;
15. security remediations.

Additional V1-era verification includes:

- API hardening;
- architectural foundations;
- engine hardening;
- local desktop authentication;
- database integrity/hardening;
- retention;
- backup;
- referential integrity;
- idempotency;
- strategy projection/database behavior.

## 5.4 V1 product/UI implementation present in the repository

The component inventory records implemented UI/runtime surfaces such as:

- root app/surface router;
- runtime availability fail-closed wrapper;
- authenticated dashboard guard;
- owner/user dashboard shells;
- professional market chart;
- Live readiness display;
- order/portfolio runtime views;
- returning-user WebAuthn flow;
- first-time activation flow;
- owner bootstrap flow;
- user backtesting screen;
- strategy-add workflow;
- options workspace;
- owner access registry;
- owner security/system settings;
- owner strategy governance.

This is important historical context: V2 did not start from an empty engine. It started from an already large local product with UI, trading domains, security, data, Paper/broker abstractions, persistence and thousands of regression tests.

## 5.5 What the V1 certified checkpoint does not prove

The V1 clean checkpoint should **not** be interpreted as proof that all product-roadmap aspirations were operational in production. In particular it does not, by itself, prove:

- production AWS account authority was deployed;
- production remote-engine/VPS networking was complete;
- full real-money Live trading was enabled;
- all future updater/licensing/commercial infrastructure was released;
- all V1 plan stages were separately completed exactly as written.

The correct interpretation is: V1 provided a clean, locally operating, heavily tested and safety-locked platform baseline from which V2 could be built incrementally.

---

# 6. Why V2 was created instead of continuing V1 indefinitely

V1 had become broad and capable, but the next generation required stronger guarantees around reproducibility, explicit domain authority and eventual Live safety. V2 was therefore designed as an incremental hardening/re-architecture path, not a rewrite.

Key reasons:

- make module boundaries mechanically enforceable;
- create one explicit executable-order authority;
- formalize order identity/lifecycle and in-doubt behavior;
- make Backtest/Paper/Live semantics comparable;
- make research reproducible and resistant to hidden overfitting;
- version data provenance and licensing;
- isolate Paper structurally from real broker mutation;
- formalize restart/recovery and reconciliation;
- eliminate silent retry/auto-resume ambiguity;
- introduce deterministic fingerprints and evidence bundles;
- add failure-injection qualification;
- separate core trading phases from account/platform work;
- keep AI advisory/shadow rather than giving it execution authority;
- delay Live mutation until explicit technical, device/session, compliance and Owner gates are satisfied.

The V2 implementation plan explicitly states: **no big-bang rewrite**. Working V1 components are wrapped behind contracts and migrated/hardened.

---

# 7. V1 to V2 transition map

## 7.1 Local-first engine

**V1:** Local desktop engine with local trading data/secrets and cloud separated from execution.  
**V2:** Preserved and made canonical through OD-V2-02. Cloud remains account/device/entitlement authority; engine/trading state/broker secrets stay local.

## 7.2 Live safety lock

**V1:** READ_ONLY/DISARMED/global hold/zero mutation.  
**V2:** Preserved as a standing invariant through Phases 0–5 and remains required during Phase 6 implementation.

## 7.3 UI / engine boundary

**V1:** Versioned API separation was an architectural goal and significant backend/frontend structure existed.  
**V2:** Strengthened through bounded modules, ports/adapters, architecture checks and capability boundaries.

## 7.4 Risk authority

**V1:** Large risk/protective/execution functionality already existed.  
**V2:** Introduced an explicit single executable-order authority: `RiskGate` creates the approved capability. Strategy/Paper/broker layers cannot bypass it.

## 7.5 Orders and retry ambiguity

**V1:** Order lifecycle/reconciliation foundations existed.  
**V2:** Formalized deterministic logical identity, stale suppression, duplicate prevention, in-doubt semantics, reconciliation-before-retry and kill-switch actions.

## 7.6 Backtesting

**V1:** Mature backtesting and historical-provider functionality existed.  
**V2:** Added strict deterministic fingerprints, no-lookahead invariants, options-aware execution realism, versioned evidence, experiment lineage and cross-machine reproducibility.

## 7.7 Research quality

**V1:** Walk-forward/Monte Carlo and research rules existed in earlier decisions/slices.  
**V2:** Added explicit trial accounting, search budgets, OOS/WFO promotion requirements, parameter stability, stress/robustness evidence, deflated performance and backtest-overfitting estimation.

## 7.8 Data

**V1:** Historical/live provider infrastructure existed.  
**V2:** Added immutable dataset versions, provenance/checksum, licensing gates, data-quality scorecards, instrument master/as-of rules, deterministic resampling and standardized live-feed health semantics.

## 7.9 Paper trading

**V1:** Paper execution was already a substantial domain.  
**V2:** Made Paper use the same approved contracts, created Paper-only execution capability, deterministic conservative fill simulation, durable V2 state/checkpoints, reconciliation/recovery, host safety, alerts, drift reporting and FI qualification.

## 7.10 Persistence

**V1:** Large SQLite persistence/database infrastructure existed.  
**V2:** Preserved legacy schema/history and added focused additive V8 stores/codecs rather than stuffing Phase-5 policy into the large legacy SQLite store.

## 7.11 Recovery

**V1:** Restart/reconciliation recovery foundations and tests existed.  
**V2:** Formalized operational states, sticky halts, `RECOVERY`, `READY_FOR_RESUME`, explicit manual resume, protective-integrity checks and restore→reconcile→protective→health/session ordering.

## 7.12 Host resilience

**V1:** Local Windows runtime/ACL/process foundations existed.  
**V2:** Added frozen first-class host policy for single instance, sleep/resume, clock health and watchdog restart-to-recovery semantics.

## 7.13 Alerts

**V1:** Existing safety/notification functionality existed.  
**V2:** Added an explicitly independent critical-alert domain with local Windows-visible + Telegram attempts, redaction and failure isolation.

## 7.14 AI

**V1:** AI/agent concepts were not allowed to become a broker authority.  
**V2:** Canonical AI remains a later research/shadow phase. The current Laya shell is isolated, disabled/fail-closed by default and candidate/research-only.

## 7.15 Cloud/account platform

**V1:** Rich account/auth/device/AWS architecture decisions existed, while some deployment work remained future.  
**V2:** Split account/platform into a parallel Track P so trading-core progress and account/distribution progress have explicit sync points instead of being mixed into one phase chain.

---

# 8. V2 canonical build structure

V2 uses one canonical Trading Core sequence plus a parallel Platform/Account track.

## Trading Core

- Phase 0 — Decision Freeze & V1 Freeze Audit — G0
- Phase 1 — Engineering Foundation — G1
- Phase 2 — Safety Spine — G2
- Phase 3 — Data V2 — G3
- Phase 4 — Strategy SDK, Research & Backtest V2 — G4
- Phase 5 — Paper V2, Reconciliation & Recovery — G5
- Phase 6 — Live Execution V2, still DISARMED — G6
- Phase 7 — Portfolio & Risk V2 — G7
- Phase 8 — AI/Agents research + shadow — G8
- Phase 9 — Product & Operations — G9
- Phase 10 — Release Qualification & controlled Live pilot — G10

## Parallel Platform/Account Track

- P1 — decision completion for release/licence/privacy/publisher topics;
- P2 — account service + anywhere-login/device/session control;
- P3 — installer/updater/licence/telemetry/backup;
- P4 — release packaging/code-signing/release operations.

Important sync points:

- S1 after Safety Spine: arm capability can exist as code but remains disabled.
- S2 before Phase-6 exit: device/session gating must exist for any eventual arm action.
- S3 before release qualification: installer/update/licence/backup/release platform must be ready.

---

# 9. V2 Phase 0 — Decision Freeze & V1 Freeze Audit

## Purpose

Phase 0 explicitly started by treating V1 as a valuable safety baseline rather than discarding it.

## What Phase 0 established

- canonical Phase 0–10 build order;
- local-first V2 deployment model;
- V2 tier/completion rule;
- numeric policy: Decimal/fixed-point for money/price/quantity/risk, floats only in analytics with declared tolerance;
- V1 freeze/audit as the baseline for later work;
- golden regression behavior that later phases must preserve.

## Key frozen ODs

- OD-V2-01 — revised Phase 0–10 plan is canonical.
- OD-V2-02 — V2.0 is local-first.
- OD-V2-03 — V2.0 complete means required T0/T1 scope except explicit Owner-approved exceptions.
- OD-V2-12 — numeric policy.

## Status

Phase 0 is complete/merged in the canonical progression.

---

# 10. V2 Phase 1 — Engineering Foundation

Phase 1 put architecture enforcement underneath later trading features.

Delivered foundations include:

- runtime primitives;
- injected/configurable runtime dependencies;
- configuration snapshots;
- audit-chain foundations;
- observability/correlation support;
- migration framework;
- module-boundary enforcement;
- internal adapter registry;
- CI/static architecture gates.

OD-V2-14 froze V2.0 to an **internal adapter registry only**; external third-party package loading/sandboxing is deferred.

Status: complete/merged.

---

# 11. V2 Phase 2 — Safety Spine

Phase 2 created the single safe path toward an executable order without enabling real Live execution.

Delivered areas include:

- `RiskGate` as executable-approval authority;
- approved-order capability type;
- hard-limit hierarchy;
- intent freshness/identity guarding;
- formal order lifecycle;
- mode isolation;
- Live state-machine foundations;
- kill-switch semantics;
- broker-neutral contract/conformance boundary;
- tests proving Paper/Backtest cannot load a real Live mutation path through mode confusion.

OD-V2-07 froze three distinct safety actions:

- `HALT_ENTRIES`;
- `CANCEL_PENDING`;
- `FLATTEN_ALL` as a separate explicitly confirmed/audited action.

Reconciliation mismatch does not silently flatten.

Status: complete/merged.

---

# 12. V2 Phase 3 — Data V2

Phase 3 moved research/live data from “available data” toward “versioned evidence-quality data”.

Delivered areas include:

- dataset catalog;
- immutable version/checksum/provenance;
- historical store separation;
- instrument master;
- as-of rules;
- exchange/session/calendar handling;
- quality checks and quarantine;
- deterministic resampling;
- live-feed contract and health/staleness behavior;
- licensing/source policy gates.

Key decisions:

- OD-V2-04 — BTCUSD/crypto deferred to V2.3 behind shared abstractions.
- OD-V2-10 — licensed historical option-chain data is authoritative for promotion-eligible options research; synthetic data is labeled fallback and not normal promotion evidence.
- OD-V2-13 — immutable Parquet/Arrow + PyArrow Dataset + SQLite operational catalog.

Status: complete/merged.

---

# 13. V2 Phase 4 — Strategy SDK, Research & Backtest V2

Phase 4 converted research from a loose collection of strategy/backtest capabilities into an evidence-driven lifecycle.

## Delivered

- Strategy SDK V2 contracts/manifests/state/lifecycle.
- ORB reference strategy port.
- explicit protective-policy reference requirement rather than inventing stop/target economics.
- experiment registry.
- append-only trials ledger.
- grid/random search with explicit budgets.
- parameter-stability analysis.
- WFO/OOS validation.
- robustness/stress evidence.
- deflated performance / probability-of-backtest-overfitting evidence.
- deterministic Backtest V2.
- no-lookahead tests.
- options-aware simulation.
- batch/local research orchestration.
- versioned evidence bundle and deterministic cross-machine G4 fingerprint.
- fail-closed promotion lifecycle.

## Promotion philosophy

OD-V2-17 froze the built-in V2 profile to `research-only/v1` / `NON_PROMOTABLE` until explicit evidence-backed numeric criteria exist. No production threshold may be guessed from old numbers merely to make promotion pass.

## Verification / integration state

PR #6 is technically green and open/unmerged at this snapshot. Technical completion and merge state are intentionally recorded separately.

---

# 14. Laya side integration — separate from canonical Phase 8

PR #7 adds a model-neutral Laya intelligence shell stacked on Phase 4.

Implemented shell capabilities include:

- deterministic model-neutral request/result identities;
- disabled-by-default configuration;
- local model registry/provenance seam;
- role routing;
- market-intelligence freshness validation;
- candidate-only CE/PE opportunity objects;
- research-only strategy hunting;
- bounded fast-task service;
- static guards blocking direct broker/Live/order/network authority;
- deterministic dual-Windows qualification probe.

Important limits:

- actual Laya model/weights/runtime are not connected in this milestone;
- Laya is not execution authority;
- candidate output does not bypass strategy rules or RiskGate;
- this PR is draft/open/unmerged;
- this work does **not** mean canonical Phase 8 AI/Agents is complete.

---

# 15. V2 Phase 5 — Paper V2, Reconciliation & Recovery

Phase 5 hardened Paper mode into a recovery-qualified operational system rather than merely a simulated broker.

## 15.1 Frozen Phase-5 decisions

### OD-V2-24 / ADR-013 — Host resilience

Frozen policy includes:

- Windows 11 x64 as first-class V2.0 qualification target;
- one engine instance per local context;
- temporary active-session sleep prevention only, without permanent power-plan rewriting;
- sleep/resume discontinuity forces recovery;
- watchdog restarts into recovery only and never arms;
- clock-health policy is injectable/versioned;
- no guessed production drift threshold;
- no guessed minimum hardware requirement;
- antivirus/security protection does not need to be disabled;
- recovery precedence over retry/new entries;
- host events audited.

### OD-V2-19 / ADR-014 — Critical alert independence

Frozen policy includes:

- local Windows-visible + Telegram as two independent required attempts for critical Phase-5 alerts;
- email optional;
- one channel failing cannot suppress the other;
- redacted payloads;
- alert failure itself is auditable;
- Paper safety does not depend on Telegram;
- dead-PC central heartbeat deferred until telemetry/privacy OD-V2-22;
- no notifier can arm or place orders.

The dated Phase-5 decision-freeze addendum overrides the older root register where OD-V2-19/24 may still appear OPEN.

## 15.2 Operational state model

Phase 5 defines:

- `HEALTHY`
- `DEGRADED`
- `HALTED`
- `RECOVERY`
- `READY_FOR_RESUME`

Key semantics:

- `HALT_ENTRIES` is an action.
- `HALTED` is a sticky resulting safety state.
- state uncertainty can jump directly to `RECOVERY`.
- a CLEAN reconciliation is not enough to resume.
- protective integrity/feed/clock/session/expiry checks remain separate gates.
- recovery success ends at `READY_FOR_RESUME`.
- explicit manual resume is required before normal entry permission returns.

## 15.3 P5-01 — Contracts + operational state

Implemented:

- Paper session/order/position contracts;
- checkpoint/incident/recovery/alert evidence contracts;
- state transitions;
- sticky halt semantics;
- manual-resume boundary;
- architecture guard.

## 15.4 P5-02 — Deterministic Paper execution/fill simulation

Implemented:

- Paper-only approved-order adapter;
- conservative bid/ask execution semantics;
- deterministic slippage/latency/rejection/disconnect simulation;
- stale/future quote validation;
- no real-broker mutation path.

## 15.5 P5-03 — Persistence + checkpointing

Implemented:

- additive V8 schema;
- deterministic Paper codec;
- session/order/position store;
- recovery checkpoint/report store;
- incident/alert evidence store;
- strict restoration checks.

Important hardening discovered during strict re-audit:

- referenced orders/positions missing from owned-state restoration originally could be silently skipped;
- regression tests were added first;
- restoration was changed to fail closed;
- missing owned truth is no longer silently accepted.

## 15.6 P5-04 — Reconciliation + recovery coordinator

Implemented recovery ordering:

- restore;
- reconcile;
- protective integrity;
- feed health;
- clock health;
- session/expiry checks;
- `READY_FOR_RESUME` only when all required checks pass.

Recovery does not own order-submit/retry capability.

## 15.7 P5-05 — Protective integrity + session/expiry

Implemented:

- protective integrity independent of reconciliation;
- fail-closed missing/mismatched protection;
- explicit session/expiry handling;
- expired contracts blocked from fresh entry;
- no invented automatic flatten or silent carry when policy is missing.

## 15.8 P5-06 — Failure/storm policy

Implemented:

- versioned failure/storm policy;
- explicit observation window/trigger/cooldown/reset semantics;
- TEST_ONLY fixtures for test thresholds;
- no guessed production constants;
- missing/corrupt required policy cannot grant unlimited retry.

## 15.9 P5-07 — Host resilience

Implemented:

- second-instance fail-closed behavior;
- clock-health policy seam;
- power/session seam;
- sleep/resume recovery semantics;
- watchdog recovery-only behavior.

## 15.10 P5-08 — Independent alerts

Implemented:

- versioned alert contract;
- redaction;
- dispatcher;
- Windows-local adapter;
- Telegram adapter;
- independent attempts;
- exception/failure isolation;
- no safety/arm/order authority.

## 15.11 P5-09 — Drift + evidence

Implemented:

- Paper-vs-Backtest drift explanation;
- deterministic recovery/G5 evidence fingerprints;
- fail-closed missing drift policy;
- no self-promotion authority.

## 15.12 P5-10 — Failure injection, qualification and runtime wiring

Implemented deterministic safety fixtures for:

- FI-01, FI-02, FI-03, FI-04, FI-05, FI-06, FI-07, FI-08, FI-09, FI-12, FI-13, FI-14, FI-23 and FI-24.

Assertions cover areas such as:

- zero duplicate submission;
- zero stale replay;
- reconciliation before resume;
- protective integrity;
- manual resume;
- expiry/session invalidation;
- independent alert attempts;
- no Live arm permission.

`engine/paper/phase5_runtime_v2.py` wraps the large legacy Paper runner instead of rewriting it. The wrapper enforces host ownership, clock preflight, active-session power boundary, resume→recovery, manual resume and cleanup without exposing `arm`, `place_order` or `submit_order` capability.

## 15.13 G5 technical evidence

The Phase-5 evidence record shows:

- Phase1–5 static/focused gates pass on Windows latest and Windows Server 2022 runners;
- full regression passes;
- regression certification passes;
- Phase-0 golden behavior remains green;
- G4 deterministic cross-Windows comparison passes;
- G5 deterministic cross-Windows comparison passes;
- final recovery state is `READY_FOR_RESUME`;
- manual resume is required;
- duplicate-order marker is zero;
- stale-replay marker is zero;
- default Live state is READ_ONLY/DISARMED.

The final docs-head CI run #205 on commit `1434a65be97eda853ade92b216cd5f16301b40e7` also completed successfully before this history update.

## 15.14 Paper soak

Phase-5 soak campaign began on 2026-09-26:

- mode: Paper only;
- state: STARTED/RUNNING;
- completed qualifying sessions at campaign start: 0;
- long soak: not yet claimed complete.

The later release-plan target proposes at least 20 consecutive qualifying trading sessions including relevant expiry exposure and induced recovery/disconnect cases. That future long-run target is not the same thing as G5 technical qualification.

## 15.15 Current Phase-5 governance state

- technical G5 evidence: ready;
- Owner gate approval: separate governance step;
- PR #8: open/draft/unmerged;
- Live: READ_ONLY/DISARMED.

---

# 16. Testing evolution: V1 to V2

## V1 test philosophy

V1 accumulated a very large product regression suite spanning security, UI, backend, brokers, data, database and runtime workflows. The clean checkpoint’s 3761-pass result is the historical V1 certification anchor.

## V2 test philosophy

V2 retains regression coverage but adds stronger proof layers:

- phase-specific static architecture guards;
- dependency-boundary enforcement;
- deterministic probes/fingerprints;
- exact-head CI evidence;
- two Windows runner environments;
- RED→GREEN TDD for new slices;
- golden-baseline preservation;
- failure-injection catalogues;
- cross-Windows fingerprint comparison;
- explicit gate evidence G0–G10.

The historically named `.github/workflows/v2-phase0-baseline.yml` has evolved into the current Phase1–5 qualification pipeline; its filename should not be mistaken for its current scope.

---

# 17. Files deliberately not used as dumping grounds for V2

V2 intentionally avoids growing several very large legacy files unless necessary:

- `engine/paper/coordinator.py`
- `engine/paper/live_runner.py`
- `engine/persistence/sqlite_store.py`
- `engine/orchestration/entry_pipeline.py`
- `engine/risk/risk_manager.py`
- `engine/protective/live.py`

Instead, new V2 behavior is normally introduced through small contract-driven modules and minimal wiring. This is a direct consequence of the “no big-bang rewrite, no new monolith” rule.

---

# 18. Current PR/history integration state

At this snapshot:

## PR #6 — Phase 4

- open;
- mergeable;
- unmerged;
- head `20310e359eeeb13ee2b4e443717cf654466f68c4`;
- exact-head dual-Windows G4 evidence green.

## PR #7 — Laya shell

- open;
- draft;
- unmerged;
- stacked on Phase 4;
- head `65127819df42cf8376de2c4ec13faccd56d9037a`;
- model runtime not connected;
- fail-closed/candidate-only/research-only.

## PR #8 — Phase 5

- open;
- draft;
- unmerged;
- current docs snapshot head before this master history was added: `1434a65be97eda853ade92b216cd5f16301b40e7`;
- technical G5 qualification is green;
- Paper soak is running;
- merge is not implied by green CI.

---

# 19. What remains after technical Phase 5

## Phase-5 closure work

Still distinct from code completion:

- continue Paper soak evidence accumulation;
- review G5 evidence;
- explicit Owner gate closure if required by the canonical Definition of Done;
- decide/execute PR integration sequence separately;
- update consolidated Owner Decision register so it no longer misleadingly shows Phase-5-frozen OD-V2-19/24 as OPEN.

## Phase 6 — Live Execution V2, still DISARMED

Before Phase 6 can progress to its exit gate:

- OD-V2-05 multi-device Live exclusivity must be frozen;
- OD-V2-06 foreign broker order/position policy must be frozen;
- OD-V2-08 broker-resident protective order policy must be frozen;
- OD-V2-09 regulatory/broker compliance path must be reviewed/frozen;
- Track-P S2 device/session gating must be available;
- Phase-6 design/spec and implementation plan must be approved;
- first real broker adapter must pass the broker contract/conformance kit;
- real account interaction remains read-only during qualification;
- foreign activity detection/reconciliation must be tested;
- disconnect/rate-limit/token-refresh/recovery behavior must be qualified;
- Live mutation remains unreachable while DISARMED.

## Phase 7 — Portfolio & Risk V2

Pending:

- capital reservation/release;
- per-strategy/per-user budgets;
- concentration/exposure controls;
- portfolio circuit breaker;
- attribution/event-risk policy;
- aggregate exposure enforced through the same RiskGate authority.

## Phase 8 — AI / Agents research + shadow

Pending canonical scope:

- freeze OD-V2-15 AI scope/provider set;
- freeze OD-V2-16 provider data-sharing rules;
- provider registry/adapters;
- permissioned tool gateway;
- Prime/Research/Risk-challenger agent roles;
- deterministic `TradeCandidate` validation;
- shadow-mode evaluation;
- cost/quotas;
- prompt-injection defenses;
- replay/audit;
- proof there is no direct AI→order path.

## Phase 9 — Product & Operations

Pending:

- full operational runbooks;
- incident templates;
- release/operator UX;
- backup/restore and rollback drill evidence;
- compliance/risk disclosure/consent surfaces;
- open data-protection/retention governance including OD-V2-25 where applicable.

## Phase 10 — Release qualification and controlled pilot

Pending:

- all prior gates;
- S3 platform packaging/release readiness;
- completed qualification/soak evidence;
- zero critical open production issues;
- archived evidence bundle;
- explicit Owner sign-off;
- only then a controlled Live pilot under the finally frozen Live safety/compliance policy.

## Parallel Platform/Account Track

Still pending in canonical V2 work:

- OD-V2-20 update/release policy;
- OD-V2-21 licence/entitlement policy;
- OD-V2-22 telemetry/privacy policy;
- OD-V2-23 publisher/version/domain decisions;
- account service/device-session implementation to satisfy S2;
- installer/updater/licence/backup/telemetry completion for S3;
- final code-signing/release packaging.

---

# 20. Permanent continuity rules from V1 through V2

These principles represent the continuous safety identity of the project:

- local engine owns trading state;
- broker secrets remain local;
- cloud/account service is not an order engine;
- uncertainty fails closed;
- RiskGate is the V2 executable-order authority;
- strategy/AI/UI/alerts cannot bypass hard risk authority;
- Paper cannot reach real broker mutation;
- reconnect/restart does not auto-arm;
- recovery and reconciliation precede retry/new entries;
- missing/corrupt safety policy/state fails closed;
- no guessed production numeric threshold just to make a gate pass;
- technical test success, merge state, Owner approval and long-soak completion are separate states;
- real Live mutation is not enabled at the current snapshot.

---

# 21. Historical bottom line

The project did **not** jump directly from a prototype to V2.

It evolved through three broad eras:

1. **AlgoFortis engineering era:** a large Windows-local trading platform accumulated dashboard, security, risk, Paper, broker, database, reconciliation and product workflow capabilities.
2. **AlgoFortis V1 product/safety freeze:** architecture/branding/security/product decisions were formalized, a clean source baseline was certified with 3761 passing tests and Live remained deliberately locked.
3. **AlgoFortis V2 incremental hardening:** the V1 foundation was preserved while contracts, data provenance, deterministic research, single risk authority, Paper isolation, recovery, host safety, alert independence, failure injection and cross-Windows evidence were added phase by phase.

At this snapshot, the technical build has reached the end of **Phase 5**. The remaining journey is not “start over”; it is to carry this verified foundation through Phase 6 Live-safe adapter work, Phase 7 portfolio risk, Phase 8 advisory AI, Phase 9 operations and Phase 10 controlled release qualification—while preserving the V1/V2 fail-closed safety lineage throughout.
