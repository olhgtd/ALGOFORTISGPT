# Owner/Admin + AI Authoritative Reunion Design

Date: 2026-09-29  
Branch: `owner-admin-authoritative-reunion-20260929`  
Base checkpoint: `f7e05888d67562bccffd7e9734a03431fa2a0c67`

## Purpose

Preserve the mature manually-built V1 Owner/Admin UX while replacing prototype/sample/localStorage authority with current AlgoFortis V2 backend authority. The Normal User Dashboard checkpoint remains frozen. This design also brings the AI/agent control plane into the Owner/Admin scope as a real production-authority subsystem rather than the current sample-only visual prototype.

The Owner surface and AI subsystem remain governance/research clients. Neither may become a second trading, RiskGate, broker-mutation, Paper, recovery-resume, or order authority.

## Selected architecture

**Option A: preserve V1 Owner UX + current V2 authority + fresh authoritative AI control plane.**

- Keep useful Owner/Admin screens and workflows.
- Replace canonical sample/prototype/localStorage truth with explicit backend contracts/read models.
- Reuse the existing S2 account/device/session security design rather than inventing another authentication system.
- Reuse the existing audit/evidence/FailureIncident pattern rather than creating an Admin-only log system.
- Build AI authority fresh behind backend contracts; the old `Agents.tsx` is UI/reference material only because it currently uses `sampleData` and explicitly has no authoritative agent backend.
- Preserve ADR-017: Prime owns orchestration/provider routing; Laya is Market Intelligence only.
- Missing evidence remains `UNAVAILABLE`, `UNKNOWN`, or `STALE`; never inferred zero/healthy/safe.
- Live remains `READ_ONLY / DISARMED`.
- Broker connected does not imply Live armed.
- RiskGateV2 remains the sole executable-order authority.

## Mandatory implementation order

The order is fixed:

1. **Permanent Admin + AI boundary guard**
2. **Step-up authentication for destructive/security-sensitive Owner actions**
3. **Existing audit ledger / FailureIncident reuse**
4. **Clear visual `AVAILABLE / STALE / UNKNOWN / UNAVAILABLE` truth**
5. **Owner/Admin authoritative wiring**
6. **Authoritative AI Control Center**
7. **Qualification record + frozen checkpoint**

No later stage may weaken an earlier stage.

---

## 1. Permanent Admin + AI boundary guard

Create an executable static safety check following repository check conventions, expected name:

`check_owner_admin_boundary.py`

It must be runnable locally and in CI/qualification.

### The guard must fail if canonical Owner/Admin or AI production code introduces

- broker `place_order`, `modify_order`, `cancel_order` authority;
- direct Live broker-mutation endpoints;
- `_mint_approved_order()` usage from Owner/Admin/AI;
- legacy `engine.broker_adapters` mutation authority;
- a second/legacy RiskGate approval path;
- direct Live arm or recovery-resume authority;
- canonical `sampleData`, prototype localStorage, fixture authority, or silent fake-success helpers;
- Laya-owned agent routing/provider selection (`LayaRouter` or equivalent);
- AI output converted directly into executable broker commands;
- AI-owned account/security/billing mutation;
- AI-owned database/trading-state mutation outside explicitly approved evidence/job stores.

### Pinned invariants

- Owner/Admin = governance/oversight.
- AI = advisory/research/shadow.
- Prime = orchestration/router.
- Laya = Market Intelligence only.
- Research Agent = research/data specialist.
- Risk Challenger = critique/challenge specialist, not RiskGate.
- RiskGateV2 is the sole executable-order authority.
- Live = `READ_ONLY / DISARMED`.
- Paper and Live remain isolated.
- Sample/demo material may exist only behind explicit preview/dev-only boundaries.

---

## 2. Step-up authentication for destructive Owner actions

Reuse S2 WebAuthn/account/device/session semantics. Do not create a new Admin password/confirmation authority.

Step-up is required for trust-changing/risk-increasing Owner operations, including at minimum:

- suspend/revoke account/access;
- restore/re-enable when policy classifies it as risk-increasing;
- activation revoke/reissue when trust changes;
- entitlement extend/renew/lifetime conversion;
- session revoke/revoke-all;
- device revoke/revoke-all;
- security posture changes;
- strategy suspension/restoration/administrative allowance changes affecting deployability;
- connection/capability administrative allowance changes;
- AI provider credential/binding changes where they change trust or external data access;
- enabling/disabling an AI agent or job class when policy marks it security-sensitive;
- future operations classified by backend policy as trust-changing/risk-increasing.

Backend authority decides whether proof is required and whether it is fresh. Missing/stale/expired proof fails closed with zero mutation. UI/localStorage confirmation never satisfies step-up.

---

## 3. Existing audit ledger / FailureIncident reuse

No separate hidden Admin or AI logging database.

Security-relevant Owner operations and AI governance actions flow through the existing audit/evidence model. Rejected trust transitions, policy breaches, security failures, provider failures requiring incident treatment, and equivalent conditions reuse/extend the existing FailureIncident pattern where applicable.

Audit/evidence should preserve, where safe:

- actor/Owner identity;
- target user/account/strategy/connection/agent/provider/job id;
- action family;
- request/evaluation time;
- authoritative result (`APPLIED`, `REJECTED`, `FAILED`, etc.);
- policy/reason code;
- step-up required/result without proof secrets;
- correlation/request/job id;
- safe before/after high-level state;
- immutable evidence/audit reference.

No password, activation secret, recovery secret, API secret, model-provider secret, broker credential, or step-up proof material may be logged. Audit-required mutations fail closed if required evidence cannot be persisted.

---

## 4. Visual authority truth

Owner/Admin and AI Control Center use the same authority states:

- `AVAILABLE`
- `STALE`
- `UNKNOWN`
- `UNAVAILABLE`

Rules:

- `UNAVAILABLE` must be visibly different from valid `0`, healthy, safe, PASS, or empty.
- `STALE` stays stale; it is never promoted to available.
- `UNKNOWN` is never guessed.
- `0` is shown only when an `AVAILABLE` source explicitly returns an empty set/count.
- Missing user/strategy/risk/incident/agent/provider/job authority never renders as `0` or healthy.
- Owner Overview and AI cards use shared visible warning/error/disabled states.

---

## 5. Owner/Admin authoritative wiring

### Owner Overview

Preserve UX; remove canonical sample fallbacks. Show authoritative Users/Access, strategy governance, connections/data, system/persistence health, security posture, AI status and attention items. Hard-coded claims such as `AUTHORITATIVE RUNTIME · RELEASE CANDIDATE` must be derived from evidence or replaced with neutral product identity.

### Users Oversight + User Inspection

Preserve the V1 inspection flow and its conceptual tabs:

`Profile | Strategies | Backtests | Paper | Portfolio | Orders | Connections | Reports | Sessions | Security State`

Every tab reads current authority. Missing per-user authority = unavailable/unknown, never sample rows. Administrative mutations remain separate, step-up gated and audited.

### Access Registry

Backend authority owns access creation, activation/reissue/revoke, account suspend/restore/revoke, entitlement lifecycle and service-term changes. Prototype-generated identifiers/codes remain preview-only.

### Strategy Governance

Use current registry/readiness/promotion contracts. Owner may add restrictions/holds, but cannot override failed system readiness, deterministic validation or RiskGateV2. Promotion success is shown only after authoritative persisted confirmation/re-read.

### Connections / Datasets / Plugins

Use authoritative connection, capability, historical-data and dataset status. Remove simulated verification/gap repair/sample fallback from canonical production mode. Missing backend capability means unavailable, not simulated success.

### Backtest + Paper

Use current deterministic V2 backtest/research authority and current Paper engine only. No duplicate V1 engine/ledger.

### Portfolio + Orders

Preserve canonical runtime view where already authoritative. Owner view is oversight/read-side; no direct place/modify/cancel broker authority.

### Reports + Audit

Use current report/evidence and immutable audit authorities. Remove simulated report success from production mode.

### Security + System + Settings

Preserve current backend sessions/devices/security/persistence/settings wiring. Retain `PROPOSE -> CONFIRM -> APPLY -> VERIFY`. Destructive operations are step-up gated and audited.

---

## 6. Authoritative AI Control Center

The current visual Agent screen is not production authority. Production AI is built fresh behind explicit backend contracts while reusing useful V1/visual interaction ideas.

### 6.1 Agent roles

```text
Prime Agent / Agent Orchestrator
    ├── Laya — Market Intelligence only
    ├── Research Agent — research/data specialist
    └── Risk Challenger — independent risk critique
```

Prime owns task routing, orchestration and provider/model routing. Laya never dispatches agents or chooses models for other agents.

### 6.2 Backend authority to build

The AI control plane should expose explicit durable/readable contracts for:

- agent registry and immutable role/type;
- agent status/health and authority freshness;
- provider registry;
- model registry/model availability;
- per-agent provider/model binding;
- deterministic fallback policy owned by Prime/orchestration;
- research/shadow job queue and lifecycle;
- run/job history;
- structured outputs/artifacts;
- provenance/evidence refs;
- failures/incidents;
- Owner administrative holds/enablement policy where allowed;
- configuration versioning and audit linkage.

Secrets/API keys are stored only through approved secret-provider abstractions, never Git or rendered in UI.

### 6.3 Laya

Implement according to ADR-017. Laya may consume approved authoritative market/options context and produce structured market observations, regime/context, hypotheses, `TradeCandidate`/`NO-TRADE` research outputs and evidence. It cannot route agents, select providers globally, mutate brokers, arm Live, bypass validation or become RiskGate.

The existing `laya-native-workspace` and frozen Laya source/model decisions may be integrated later through an adapter; model availability must be reported truthfully (`AVAILABLE/STALE/UNKNOWN/UNAVAILABLE`). Synthetic training data is pipeline/pretraining/shadow material only and is never labeled real NSE evidence.

### 6.4 Prime

Prime coordinates AI tasks and specialist delegation, owns provider/model selection via the registry, records routing decisions/evidence, and fails closed when required agents/providers/data are unavailable. Prime output remains advisory/research; it cannot produce broker mutations.

### 6.5 Research Agent

Research/data specialist for strategy research, evidence gathering, experiment/research artifacts and supporting analysis. It must use approved data/read ports and preserve provenance; it cannot silently promote strategies or trade.

### 6.6 Risk Challenger

Produces independent critique/challenge of candidate assumptions and risk. It is not RiskGateV2 and cannot approve executable orders. Its output is evidence/advice only.

### 6.7 Owner AI UI

Owner Control Center should show, from backend authority only:

- Prime/Laya/Research/Risk Challenger cards;
- status + health + current authoritative task;
- provider/model binding;
- provider/model health;
- current and recent research/shadow jobs;
- run history/detail;
- artifact/evidence refs;
- failures/incidents;
- four-state authority badges;
- clearly protected safety boundaries.

Pause/resume/start/stop controls are exposed only for backend-supported research/shadow jobs and follow policy/step-up/audit requirements. No UI-only sample toggle becomes production control.

### 6.8 AI acceptance guards

Tests must prove:

- no `LayaRouter`/Laya-owned provider routing;
- no AI broker/order mutation imports/calls;
- no AI Live arm/recovery-resume authority;
- no RiskGateV2 bypass;
- unavailable/stale providers or market data fail closed;
- provider/model routing belongs to Prime/orchestrator;
- job/output provenance is retained;
- sample Agent data is not canonical production truth.

---

## Shared Owner authority layer

Create/consolidate a thin presentation/read-model layer for Owner shell/system/security/recovery/broker-data/audit/AI attention state. It does not become a trading or AI execution authority.

## Data/provenance rules

Canonical production screens consume backend/source-tagged results. `SAMPLE_FALLBACK`, fixture storage, prototype localStorage and simulation helpers are preview/dev-only. Secrets remain sealed/redacted. Current V2 contracts win on conflicts with V1.

## Qualification

Tests are written during implementation, but until an executable runner successfully performs them the status remains:

`IMPLEMENTED / EXECUTION VERIFICATION PENDING`

Required families include:

- Admin+AI static boundary guard;
- step-up positive/negative/expired tests;
- audit/incident linkage + no-secret tests;
- four-state visual truth/no-fake-zero tests;
- sample/prototype isolation tests;
- Owner surface authority tests;
- Prime/Laya/Research/Risk Challenger role-boundary tests;
- provider/model registry and routing tests;
- AI provenance/fail-closed tests;
- frozen User-side regressions;
- TypeScript tests/typecheck/build;
- relevant Python regression;
- existing Live READ_ONLY/DISARMED, RiskGateV2, Paper/recovery and broker read-only safety checks.

## Completion criteria

Implementation-complete requires all seven ordered stages implemented, canonical Owner/Admin/AI production paths free of sample authority, step-up/audit/four-state truth enforced, AI roles/backend authority present, User checkpoint unchanged, and a frozen exact-SHA checkpoint/qualification record.

`100% VERIFIED COMPLETE` additionally requires fresh executable test/typecheck/build/qualification evidence with no unexplained failures.

## Out of scope

- enabling real-money Live broker execution;
- giving AI autonomous broker/order authority;
- making Laya the router/orchestrator;
- rewriting the mature Owner UX merely for aesthetics;
- treating synthetic data as real market evidence;
- unrelated cloud/commercial expansion.