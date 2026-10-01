# AlgoFortis — AI, Laya & Decision Intelligence Architecture

**Date:** 2026-10-01  
**Status:** LOCKED BY OWNER APPROVAL  
**Base:** `main@a2b4d22bfc36a34becb3ef917eaf880ca6ff5fc5`  
**Scope:** Research, backtest and paper decision-intelligence architecture; Owner/Admin configuration; future-compatible mode contracts without enabling real-money broker mutation.  

## 1. Authority and precedence

This document is the controlling architecture decision for the AI/Laya decision-intelligence redesign approved by the Owner on 2026-10-01.

Where this design conflicts with the older Phase-8 statement that AI is permanently limited to passive research/shadow observation, this document supersedes that narrow role **for research/backtest/paper decision intelligence only**. AI and Laya may review deterministic strategy candidates and may generate independent research/paper candidates.

The following older authorities are **not** superseded and remain controlling:

- `RiskGateV2` remains the sole authority able to mint `ApprovedOrder` capabilities.
- Existing portfolio/accounting authority remains the source of truth for capital, reservations and aggregate exposure.
- S2 account/device/session authority remains the identity/session authority.
- OD-V2-16/Data V2 provenance/licensing rules remain mandatory before third-party provider data egress.
- Existing Owner/Admin authority and authoritative Owner Dashboard remain the only system-wide administrative surface.
- Live remains `READ_ONLY / DISARMED` in the current product build.
- This design does not authorize real-money broker mutation, Live arming or an AI-to-broker execution path.

Guiding rule:

> Extend existing authority; do not create a parallel authority where AlgoFortis already has one.

---

## 2. Core objective

AlgoFortis must operate correctly with any of these intelligence configurations:

- Strategy only
- Strategy + Laya
- Strategy + one external/local AI provider
- Strategy + multiple AI providers
- Strategy + Laya + one AI provider
- Strategy + Laya + multiple AI providers
- Laya disabled
- all AI providers disabled
- one or more provider outages

Optional intelligence must never become a hidden dependency of deterministic strategy execution, Backtest, Paper, portfolio accounting or `RiskGateV2`.

---

## 3. Core runtime paths

AlgoFortis has two first-class candidate sources.

### 3.1 Deterministic Strategy Path

`Strategy Engine -> StrategyCandidate`

The Strategy Engine remains independently operational. AI/Laya absence must not prevent deterministic strategy candidates from being produced.

### 3.2 Intelligence Path

`Laya + available AI providers (0..N) -> IntelligenceCandidate`

Laya and connected AI providers may:

- review a StrategyCandidate;
- generate independent research/paper candidates;
- produce market/regime context;
- challenge other AI or strategy reasoning;
- participate in after-hours Strategy Hunting.

They may not mint `ApprovedOrder`, mutate broker state, arm Live, bypass portfolio authority or bypass `RiskGateV2`.

---

## 4. Laya role

Laya is not a generic chatbot and not merely another provider entry.

**Laya = Market Intelligence Engine.**

Its responsibilities may include:

- market regime classification;
- trend state and trend strength;
- momentum state;
- volatility state;
- market structure;
- regime-change detection;
- reversal context;
- unusual-behaviour detection;
- strategy-candidate review;
- strategy conflict detection;
- missed-opportunity detection;
- independent research/paper candidate generation;
- structured market context for other agents.

Laya remains optional. Turning Laya OFF must not stop deterministic strategy execution.

---

## 5. Provider model: `0..N`

The architecture must not require exactly three AI providers or any other fixed count.

Provider/agent availability is discovered through the existing AI provider/model/agent authority. Valid active counts are `0..N`.

Examples:

- one cloud model only;
- one local model only;
- Laya only;
- Laya + one external model;
- several providers/models;
- no AI provider at all.

The same contracts and orchestration must work in every case.

---

## 6. Capability registry

Extend the existing provider/model/agent registry rather than create a second registry.

The registry/read model must expose enough metadata for Owner policy to answer:

- configured provider/model;
- enabled/disabled state;
- health/authority state;
- provider/model lineage;
- market-analysis capability;
- strategy-review capability;
- independent-candidate capability;
- strategy-hunting capability;
- critic/challenger capability;
- quota/rate-limit policy reference;
- budget policy reference;
- current degradation state.

Provider credentials remain backend-controlled; plaintext secrets must not be returned to the browser/UI.

---

## 7. Graceful degradation

Required runtime states include:

- `FULL` — configured Laya/AI intelligence healthy;
- `DEGRADED` — some providers unavailable;
- `LAYA_ONLY` — Laya available, external/local providers unavailable;
- `STRATEGY_ONLY` — Laya and AI providers unavailable/disabled.

Hard rule:

> Optional intelligence failure must never silently break deterministic strategy execution.

The Owner Dashboard must show degraded/unavailable intelligence status explicitly instead of fabricating success.

---

## 8. Strategy candidate review

When Owner policy enables review, a `StrategyCandidate` may be reviewed by Laya and/or available AI providers.

Review dimensions may include:

- why the deterministic strategy fired;
- current regime;
- trend/momentum support;
- volatility state;
- market-structure compatibility;
- sudden regime/change evidence;
- conflicting evidence;
- data freshness;
- historical regime compatibility;
- model/provider disagreement.

Advisory/research dispositions may include:

- `CONFIRM`
- `CAUTION`
- `CHALLENGE`
- `REJECT_FOR_RESEARCH`
- `INSUFFICIENT_DATA`

Owner policy decides whether a given research/paper workflow treats review as optional, preferred or required. AI unavailability itself does not silently stop the Strategy Engine.

---

## 9. AI Review Council

Available intelligence participants may form a dynamic evidence-review council. Fixed participant count is forbidden.

Possible roles include:

- Laya;
- Research agent;
- Strategy critic;
- Risk challenger;
- Validation agent;
- future provider-backed roles.

### 9.1 No blind majority vote

`3 YES vs 1 NO` is not sufficient by itself to approve a candidate.

Council output is evidence, not execution authority.

### 9.2 Correlated-model evidence

Council evidence must carry a `correlated_model_flag` and enough lineage metadata to avoid treating correlated outputs as independent confirmation.

Correlation may arise from:

- same foundation model;
- same upstream provider;
- same retrieved source set;
- same prompt lineage;
- repeated logical roles on the same provider/model.

Required evidence may include:

- participant count;
- independent-source count;
- provider/model lineage;
- `correlated_model_flag`;
- disagreement summary;
- confidence/evidence dispersion.

A single provider used sequentially for proposer/critic roles is useful, but those passes must not be counted as independent provider votes.

---

## 10. IntelligenceCandidate contract

Laya and AI may generate independent `IntelligenceCandidate` objects for research/backtest/paper evaluation.

A candidate must carry at least:

- unique candidate ID;
- source type and source participants;
- provider/model lineage where applicable;
- instrument;
- direction/setup hypothesis;
- research entry zone or structured trigger condition;
- invalidation condition;
- regime/context;
- supporting evidence;
- conflicting evidence;
- input/data fingerprint;
- policy/version references;
- created timestamp;
- expiry/TTL.

An IntelligenceCandidate is not an `ApprovedOrder` and cannot become one without the existing downstream authorities.

---

## 11. Common Candidate Pool

`StrategyCandidate` and `IntelligenceCandidate` enter one controlled Candidate Pool/read workflow.

Candidate source does not grant priority or special execution authority.

Common validation includes, as applicable:

- valid instrument;
- valid session/policy scope;
- fresh market/data inputs;
- candidate TTL;
- source/provider permission;
- schema validity;
- duplicate/conflict detection;
- account/broker context;
- portfolio state;
- entitlement/policy constraints.

Invalid or ambiguous candidates fail closed for that candidate; they do not kill unrelated deterministic strategy processing.

---

## 12. Existing portfolio/accounting authority reuse

Do **not** create an AI-specific accounting ledger or a new parallel portfolio authority.

Extend/reuse existing portfolio components, including the established `engine/portfolio/` authority and Phase-7 reservation-aware admission path.

Existing portfolio/accounting state remains the source of truth for:

- available capital;
- reservations;
- positions;
- projected exposure;
- strategy/user budgets;
- concentration;
- circuit-breaker state;
- attribution.

---

## 13. Atomic capital reservation

Candidates competing for the same broker/account capital pool must not independently observe and spend the same stale available balance.

Reservation requirements:

- atomic reserve;
- atomic release;
- stable reservation ID;
- candidate ID;
- broker/account scope;
- amount/capacity claim;
- expiry;
- audit evidence.

Example:

- pool available = 60 units;
- Candidate A reserves 30;
- remaining becomes 30;
- Candidate B requesting 40 must not use the pre-reservation 60 snapshot.

---

## 14. Multi-broker / multi-account pools

Capital is not one global undifferentiated pool.

Define reservation scope conceptually as:

`CapitalPoolKey = Broker + Account`

Rules:

- candidates on the same broker/account compete for the same reservation pool;
- different broker/accounts maintain separate reservation pools and can genuinely proceed in parallel when otherwise permitted;
- user-level/global portfolio policy may still cap aggregate exposure across those accounts;
- separate account pools must not create separate conflicting sources of aggregate portfolio truth.

---

## 15. Portfolio arbitration

Before `RiskGateV2`, the existing portfolio authority evaluates surviving candidates against current portfolio/account state.

Checks may include:

- available account capital;
- active/provisional reservations;
- existing positions;
- same-direction correlated exposure;
- conflicting directional exposure;
- instrument limits;
- strategy limits;
- user-level limits;
- concentration;
- cross-account aggregate exposure;
- candidate freshness/expiry.

Exact ranking weights remain a separate policy decision. AI confidence alone may not determine approval priority.

---

## 16. Risk/order authority

The downstream authority is explicitly the existing:

# `RiskGateV2`

Do not create a generic new `Risk/Safety Validation` engine or a second order authority.

All candidate sources and portfolio components may contribute context/signals, but only existing `RiskGateV2` may mint `ApprovedOrder` capabilities.

No AI/Laya/scheduler/council/portfolio extension may bypass that boundary.

---

## 17. MarketWatchPolicy and scheduler

Extend the existing `MonitoringPolicyV2` / `MonitoringSchedulerV2` seam into the authoritative versioned Market Watch policy; do not create an unrelated second scheduler.

Monitoring values are policy data, not hard-coded business rules.

A versioned policy may define:

- allowed instruments;
- sessions/windows;
- timeframes/cadence;
- scheduled triggers;
- event triggers;
- provider/model assignments or routing constraints;
- task TTL;
- task classes;
- quota/budget references;
- strategy-review policy;
- independent-candidate scan policy.

Examples such as 1-minute or 5-minute checks are examples only; actual values come from versioned policy.

---

## 18. Monitoring trigger classes

The controlled scheduler may create work from these classes:

1. **Scheduled** — versioned policy cadence/bar events.
2. **Event-triggered** — e.g. StrategyCandidate created, regime change, unusual volatility, data-feed recovery.
3. **Owner-triggered** — explicit one-shot request from the Owner/Admin Dashboard.

AI/provider output may not invent an uncontrolled fourth trigger class.

---

## 19. ScopeExpansionRequest

AI/Laya may recommend wider scope but may not apply it themselves.

Examples requiring an Owner-controlled `ScopeExpansionRequest`:

- new instrument;
- new timeframe;
- higher monitoring frequency;
- new data source;
- new task class;
- expanded provider usage.

Flow:

`AI/Laya suggestion -> ScopeExpansionRequest -> Owner/Admin review -> approve/deny -> new policy version if approved`

No self-widening provider scope is permitted.

---

## 20. Provider queue, rate limits and quotas

Extend/reuse the existing `ProviderJobQueueV2` and provider-budget concepts.

Provider pressure may delay work, but must not create bypass calls or uncontrolled fallback.

The queue/budget layer must account for:

- provider max concurrency;
- queue capacity;
- provider rate limits;
- token/API quotas;
- Owner budget;
- task priority;
- task TTL/expiry;
- retry/backoff policy;
- provider health.

Expired market-intelligence work must be dropped rather than executed later as if it were fresh.

---

## 21. Queue priority

Priority is versioned policy, not provider discretion.

The architecture must support prioritizing urgent candidate review over after-hours/background research. A representative priority ordering is:

1. active candidate review;
2. abnormal market/regime event;
3. normal scheduled monitoring;
4. strategy hunting;
5. low-priority research.

The exact numeric policy is configurable, but Strategy Hunting must not starve higher-priority active-session work.

---

## 22. Provider failure and fallback

Provider failure must not create infinite wait or hidden execution fallback.

Permitted behavior depends on policy and may include:

- bounded retry/backoff;
- route to another explicitly permitted provider if the policy allows it;
- degrade the intelligence task;
- expire/drop the task.

Deterministic Strategy execution remains independent.

Owner Dashboard must expose states such as queued, running, rate-limited, degraded, unavailable and expired.

---

## 23. OD-V2-16 / Data V2 licensing-provenance gate

Any market, instrument, dataset-derived, news-derived or research data leaving the local boundary for a third-party/cloud AI provider must pass the existing provenance/licensing/egress authority.

Strategy Hunting is **not exempt** merely because it runs after market hours.

Required flow:

`Data -> OD-V2-16 / Data V2 provenance+licensing authorization -> allowed projection/redaction -> provider`

Missing, stale, ambiguous or prohibitive evidence blocks the provider call fail closed.

Redaction does not make otherwise non-exportable data exportable.

---

## 24. Strategy Hunting

After the market/session or whenever Owner policy permits, available Laya/AI capacity may be assigned to Strategy Hunting.

Representative workflow:

`historical/session data -> licensing/provenance gate -> hypothesis generation -> critique -> Laya regime analysis -> existing deterministic Backtest/WFO/OOS/robustness stack -> Research Candidate`

AI roles may:

- propose hypotheses;
- challenge assumptions;
- identify regime dependency;
- search for failure cases;
- summarize evidence.

AI cannot self-promote an unvalidated strategy.

---

## 25. One-AI and zero-AI Strategy Hunting

### One provider

One AI provider/model may perform sequential logical roles such as proposer, critic and summarizer. Those passes remain correlated and are not counted as independent votes.

### Zero providers

Existing deterministic research remains available:

- parameter search;
- Backtest;
- WFO/OOS;
- bootstrap/stress/sensitivity;
- robustness/stability checks.

No AI = reduced intelligence capability, not broken AlgoFortis.

---

## 26. Existing S2 authority and user entitlements

Do not create a parallel authentication system for AI/Laya access.

Entitlement flow is:

`S2 authenticated principal/device/session -> entitlement lookup -> allowed capability`

S2 answers **who/which authenticated session/device**. Entitlement policy answers **which intelligence capability that authenticated principal may use**.

Possible entitlement capabilities include:

- `ACCESS_LAYA_ANALYSIS`
- `ACCESS_AI_REVIEW`
- `ACCESS_INTELLIGENCE_CANDIDATES`
- `ACCESS_STRATEGY_HUNTING`
- `ACCESS_ADVANCED_RESEARCH`

A normal user must not self-grant capabilities.

---

## 27. Owner/Admin dashboard authority

All system-wide intelligence configuration belongs inside the existing authoritative Owner/Admin Dashboard and backend authority.

Do not create a second Owner UI or a separate AI-admin application.

The existing `AI Control Center` is the natural surface to extend.

Owner/Admin sections may include:

- provider registry/configuration;
- Laya state;
- provider/model role capabilities;
- MarketWatchPolicy;
- provider queue/budget health;
- Strategy Hunting controls;
- Candidate policy/read models;
- portfolio/intelligence status;
- per-user intelligence entitlements;
- ScopeExpansionRequest approvals;
- audit/evidence views.

Sensitive Owner mutations continue to use existing Owner/Admin authorization and step-up requirements where applicable.

---

## 28. User-side scope deliberately deferred

Backend entitlement architecture must be ready before final normal-user AI/Laya UI is designed.

Not decided in this architecture freeze:

- which Laya outputs normal users see;
- which AI review outputs they see;
- whether independent intelligence candidates are exposed;
- whether Strategy Hunting is owner-only or entitlement-based;
- plan/tier differences;
- amount of configuration exposed to normal users.

Until a later Owner decision, advanced intelligence configuration remains Owner/Admin-only.

---

## 29. Audit and replay

Important AI/Laya decisions must be auditable/replayable enough to answer:

- where did this candidate come from?
- which provider/model/role produced or reviewed it?
- which MarketWatchPolicy version was active?
- what data/input fingerprint was used?
- was the council correlated?
- why was the candidate challenged/rejected?
- why was capital blocked/reserved?
- what did `RiskGateV2` decide?

Evidence should include, as applicable:

- task ID;
- candidate ID;
- provider/model lineage;
- `correlated_model_flag`;
- timestamps;
- instrument;
- broker/account scope where relevant;
- task purpose;
- policy version;
- trigger;
- input fingerprint;
- evidence/disagreement;
- portfolio reservation result;
- `RiskGateV2` result.

---

## 30. Mode architecture

Common contracts should remain usable across:

- `BACKTEST`
- `PAPER`
- `LIVE_READ_ONLY`
- a future live-capable adapter contract

Current implementation remains research/backtest/paper focused and Live remains `READ_ONLY / DISARMED`.

This freeze prepares reusable boundaries; it does **not** enable real-money trading or broker mutation.

---

## 31. Existing code to extend, not replace

The implementation should preferentially extend these existing authorities/seams:

| Requirement | Existing authority/seam |
|---|---|
| AI contracts | `engine/ai/contracts.py` |
| Laya | `engine/ai/laya.py` |
| provider registry | `engine/ai/provider_registry.py` |
| AI orchestration | `engine/ai/orchestrator.py` |
| monitoring policy/scheduler | `engine/ai/monitoring_scheduler_v2.py` |
| provider queue | `engine/ai/provider_queue_v2.py` |
| AI evidence | `engine/ai/evidence.py` |
| Risk/order authority | `engine/risk/gate_v2.py` (`RiskGateV2`) |
| reservation-aware RiskGate wrapper | `engine/risk/portfolio_admission_v2.py` |
| portfolio/accounting | `engine/portfolio/` |
| S2 identity/session | `dashboard/backend/account_v2/` |
| Owner/Admin authority | `dashboard/backend/owner_admin/` |
| Owner AI UI | `dashboard/owner-dashboard/authoritative/AIControlCenter.tsx` |
| strategy validation | existing Backtest/WFO/OOS/robustness stack |

If an implementation task proposes a second authority in one of these categories, it must be rejected unless a later explicit Owner decision changes this spec.

---

## 32. Hard architectural invariants

### Core independence

- **INV-AI-01** Strategy Engine does not depend on AI availability.
- **INV-AI-02** Strategy Engine does not depend on Laya availability.
- **INV-AI-03** Zero AI providers are supported.
- **INV-AI-04** One AI provider is supported.
- **INV-AI-05** Multiple AI providers are supported.
- **INV-AI-06** Provider failure causes graceful degradation rather than core failure.

### Monitoring authority

- **INV-AI-07** AI cannot expand monitoring scope by itself.
- **INV-AI-08** AI cannot change monitoring frequency by itself.
- **INV-AI-09** AI cannot grant itself permissions.
- **INV-AI-19** Monitoring schedules originate from versioned owner policy.

### Candidate authority

- **INV-AI-10** Laya/AI may generate independent research/backtest/paper candidates.
- **INV-AI-11** Strategy and intelligence candidates use common controlled validation.
- **INV-AI-12** Candidate source cannot bypass Portfolio authority or `RiskGateV2`.
- **INV-AI-20** No parallel `ApprovedOrder`/risk authority may be created.

### Capital and portfolio

- **INV-AI-13** Same broker/account capital cannot be double-reserved.
- **INV-AI-14** Reservations are atomic.
- **INV-AI-21** Separate broker/accounts maintain separate reservation pools.
- **INV-AI-22** Cross-account aggregate exposure still uses existing Portfolio authority.
- **INV-AI-23** No parallel AI-specific accounting ledger exists.

### Provider orchestration

- **INV-AI-24** Provider rate limits/quotas are enforced through controlled queue/budget policy.
- **INV-AI-25** Expired market-intelligence tasks do not execute as fresh tasks.
- **INV-AI-26** Strategy Hunting does not starve higher-priority active-session reviews.

### AI evidence

- **INV-AI-27** Council agreement records model/provider correlation.
- **INV-AI-28** Correlated models cannot masquerade as independent confirmations.

### Data licensing

- **INV-AI-29** Third-party AI data transfer requires OD-V2-16/Data V2 licensing-provenance authorization.
- **INV-AI-30** After-hours Strategy Hunting does not bypass data-licensing rules.

### Entitlements

- **INV-AI-15** User AI/Laya capabilities are controlled by Owner/Admin entitlement.
- **INV-AI-16** Normal users cannot modify global intelligence configuration.
- **INV-AI-31** Entitlement authority extends the existing S2 authenticated principal authority.
- **INV-AI-32** No parallel identity/authentication mechanism is created for AI access.

### Research safety

- **INV-AI-17** AI Strategy Hunting cannot self-promote an unvalidated strategy.
- **INV-AI-18** Important intelligence decisions are auditable/replayable.

### Existing safety boundary

- **INV-AI-33** `RiskGateV2` remains the sole `ApprovedOrder` authority.
- **INV-AI-34** Current Live state remains `READ_ONLY / DISARMED`.
- **INV-AI-35** Current implementation does not authorize real-money broker mutation.

---

## 33. Acceptance conditions for implementation

The implementation is not complete until evidence proves, at minimum:

1. Strategy-only operation works with all AI/Laya disabled.
2. Laya-only, one-provider and multi-provider configurations work without separate code paths that change core strategy semantics.
3. Provider outage degrades intelligence but does not break deterministic strategy processing.
4. Laya/AI can emit structured independent research/paper candidates.
5. Strategy candidates can receive evidence review without granting AI execution authority.
6. Correlated-provider/model evidence is recorded.
7. Monitoring scope/cadence comes from versioned policy and cannot be widened by provider output.
8. Provider queue obeys concurrency, TTL and priority policy.
9. Strategy Hunting passes licensing/provenance authorization before third-party egress.
10. Same broker/account candidates cannot double-reserve capital.
11. Separate broker/accounts use separate reservation pools while aggregate exposure still uses existing Portfolio authority.
12. Every executable-order-capability test still proves `RiskGateV2` sole authority.
13. Intelligence entitlements are evaluated only after existing S2 identity/session authority.
14. All advanced global AI/Laya configuration lives under the existing Owner/Admin authority and Owner Dashboard.
15. Existing Phase 1-9 regression/safety guards remain green.
16. Live remains `READ_ONLY / DISARMED` and no broker-mutation path is introduced.

---

## 34. Explicitly unresolved follow-up decisions

These are intentionally not frozen yet and must be separate Owner decisions rather than guessed during coding:

- exact deterministic candidate-arbitration ranking weights;
- exact provider routing/cost preference policy;
- exact normal-user AI/Laya UX and controls;
- which entitlements belong to which future product plan/tier;
- any future real-money Live eligibility/activation design.

Implementation must keep these configurable/deferred instead of hard-coding guesses.

---

## 35. Implementation decomposition

This architecture spans several independently reviewable subsystems. Implementation should therefore be planned and executed as bounded slices, each independently tested and committed:

1. Contract evolution + invariant firewall.
2. Capability registry / 0..N provider degradation.
3. Versioned MarketWatchPolicy + scheduler evolution.
4. Provider queue/budget policy evolution.
5. IntelligenceCandidate + review council/correlation evidence.
6. Candidate pool/common validation.
7. Portfolio reservation/arbitration extension including multi-broker account scopes.
8. Strategy Hunting + OD-V2-16 egress gate.
9. S2-backed intelligence entitlements.
10. Existing Owner/Admin AI Control Center expansion.
11. Full regression, exact-head qualification and evidence bundle.

No slice may enable real-money broker mutation.

---

# Final locked direction

AlgoFortis keeps deterministic Strategy as an independent backbone, upgrades Laya to a first-class optional Market Intelligence Engine, supports `0..N` AI providers, permits evidence-based independent intelligence candidates and strategy review in research/backtest/paper workflows, centralizes monitoring under versioned Owner policy, reuses existing provider queue, Portfolio, S2, Owner/Admin and `RiskGateV2` authorities, and prohibits parallel authorities.

**LOCKED BY OWNER APPROVAL — 2026-10-01.**
