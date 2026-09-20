# AlgoFortis V2 — Requirements

| Field | Value |
|---|---|
| Document | `ALGOFORTIS_V2_REQUIREMENTS.md` (1 of 5) |
| Version | v0.1 DRAFT — for Owner review |
| Date | 2026-09-21 |
| Source | `AlgoFortis_V2_Master_Checklist-5.md` (referred to as **MC** below) |
| Status | PROPOSED. Nothing here is frozen until the matching Owner Decision (see `ALGOFORTIS_V2_OWNER_DECISIONS.md`) is closed. |
| Companion files | `ALGOFORTIS_V2_ARCHITECTURE.md`, `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`, `ALGOFORTIS_V2_OWNER_DECISIONS.md`, `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` |

---

## 1. Purpose

MC is a strong **completeness checklist** (810 checkbox items, 31 sections). It is not yet a **requirements baseline**: items have no IDs, no priority, no acceptance criteria, and some conflict with decisions already locked for AlgoFortis. This document converts MC into a baseline that can be built, tested and audited.

What this file adds over MC:
1. Stable requirement IDs (`AF2-<DOMAIN>-NNN`) tied back to MC sections.
2. A tier for every requirement (T0 / T1 / T2) so a solo developer can sequence work.
3. Requirements MC is missing, tagged **[NEW]** (see Appendix A for the reasoning).
4. Fixes for places where MC conflicts with locked decisions.

## 2. Scope and context

**In scope for V2**
- Local-first desktop platform (one install per PC) with a **central account authority on AWS** (identity, devices, entitlement).
- Trading engines (Data, Research, Backtest, Paper, Live) on the local machine.
- Indian index options (NIFTY / BANKNIFTY), **options BUY-only** for current scope.
- Strategy SDK, research/experiment engine, risk engine, portfolio layer, AI/agent layer (advisory), audit, observability, release/update, DR.

**Standing constraints (already locked; V2 must not weaken them)**
- Live execution stays `READ_ONLY = true` and `DISARMED = true` with zero broker mutation until V2 release qualification and explicit Owner sign-off.
- Trading engine, strategies, broker credentials, trade logs and live positions stay **local**. Cloud never executes orders and never holds broker secrets.
- Cloud/auth outage never stops or loosens local safety; cloud-dependent account operations fail closed.
- Anywhere-login model: WebAuthn interactive auth, separate device-binding key, max 3 devices, step-up on new device, recovery revokes everything.
- Fail-closed is the default for uncertainty, corruption, invalid state and reconciliation mismatch.

**Out of scope for V2.0** (designed-for through contracts, not built): see Section 6.

## 3. Tiers and IDs

| Tier | Meaning | Rule |
|---|---|---|
| **T0** | Safety spine. Must be proven before any live order can ever exist. | Blocks the Live-Eligible Milestone. |
| **T1** | V2.0 release scope. | Required for "V2 complete". |
| **T2** | V2.x. Architecture must leave a clean seam (contract/adapter), code is deferred. | Not required for V2.0. |

ID format: `AF2-<DOMAIN>-NNN`. `(MC §x)` = master checklist section. **[NEW]** = not in MC. **[OD-xx]** = depends on an open Owner Decision.

Each requirement is verified by the evidence named in `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` (invariant IDs `INV-nn`, gate IDs `Gn`).

---

## 4. Requirements by domain

### 4.1 ARC — Platform architecture (MC §0, §1, §26)
- **AF2-ARC-001 [T0]** Bounded modules: Data, Research, Strategy, Backtest, Paper, Live, Risk, Broker, Portfolio, AI, Audit, Auth, Notifications, Reporting. Modules interact only through versioned contracts; no cross-module database access.
- **AF2-ARC-002 [T0]** Domain logic has no dependency on transport, UI, database or vendor code. Every external system (broker, market data, storage, AI provider, notifier, auth provider, secrets, clock) sits behind a port.
- **AF2-ARC-003 [T0] [NEW]** All time, randomness and ID generation come from injectable providers (`Clock`, `SeedSource`, `IdGenerator`). No direct `now()` in domain code.
- **AF2-ARC-004 [T0]** Persisted schemas and APIs are versioned; migrations are deterministic, backed up before running, and fail closed.
- **AF2-ARC-005 [T0]** Hard-limit hierarchy: platform hard maximum > Owner > user > strategy > run. A lower layer can never exceed a higher one. (MC §8.4, §1.3)
- **AF2-ARC-006 [T0] [NEW]** Numeric policy: money, price, quantity and risk math use decimal/fixed-point types; floating point is allowed only in analytics with a documented tolerance. **[OD-V2-12]**
- **AF2-ARC-007 [T1]** Module health contract, capability discovery, version-compatibility matrix.
- **AF2-ARC-008 [T1]** Internal adapter registry with manifest (id, version, capabilities, declared permissions, compatibility range) for broker, data, AI provider, notifier, report/export, fee/slippage model, execution model, risk rule, indicator, strategy. Enable / disable / rollback supported.
- **AF2-ARC-009 [T1]** Layered configuration (system → environment → user → strategy → run), schema-validated, versioned, immutable per-run snapshot, secrets never in config, safe default profiles.
- **AF2-ARC-010 [T1]** V2.x compatibility and deprecation policy written before feature expansion begins.
- **AF2-ARC-011 [T2]** Third-party plugin sandboxing / process isolation and external plugin distribution. **[OD-V2-14]**
- **AF2-ARC-012 [T2]** Config diff viewer; config-pack import/export.

### 4.2 DAT — Data platform (MC §2)
- **AF2-DAT-001 [T1]** Historical data catalog: dataset IDs, immutable versions, provenance, checksum/fingerprint, lineage.
- **AF2-DAT-002 [T1]** Instrument/symbol master, exchange calendar, holiday and session rules, timezone normalization.
- **AF2-DAT-003 [T1]** Quality pipeline: gap, duplicate and outlier detection; bad-bar quarantine; quality scorecard; coverage report.
- **AF2-DAT-004 [T1]** Deterministic, reproducible 1m → higher-timeframe resampling.
- **AF2-DAT-005 [T0]** Live feed contract: unified quote/event schema, exchange vs receive timestamps, heartbeat, sequence-gap and out-of-order handling, stale-quote and clock-skew detection, market-status state machine, halt handling. Stale data blocks new entries in the risk gate.
- **AF2-DAT-006 [T1]** Reconnect + resubscribe; failover-capable data adapter architecture.
- **AF2-DAT-007 [T1]** Operational DB separated from historical store; migration framework; automated backup and **verified** restore; retention policies.
- **AF2-DAT-008 [T0] [NEW]** Data licensing gate: every data adapter declares its licence/terms and permitted use. Programmatic acquisition from sources where it is prohibited stays blocked (existing NSE prohibition and dormant-adapter gate remain in force).
- **AF2-DAT-009 [T2]** Cold archive, point-in-time recovery, dataset archival policy, corporate-action framework for non-index instruments.

### 4.3 STR — Strategy framework (MC §3)
- **AF2-STR-001 [T1]** Strategy SDK: stable interface, manifest (parameter schema, required data, timeframes, supported instruments), deterministic lifecycle hooks, state serialization, restart recovery, versioning, dependency lock, unit-test template. The existing ORB strategy is the reference port used to prove the SDK.
- **AF2-STR-002 [T0]** Lifecycle Draft → Research → Backtest → Validation → Paper → Eligible-for-Live. Configurable promotion criteria, stored evidence, stored rejection reasons, rollback to previous version, deactivation kill switch, maximum deployment scope, ownership/permissions.
- **AF2-STR-003 [T1]** Rule-based and multi-timeframe strategies; options-BUY templates for current scope.
- **AF2-STR-004 [T2]** Multi-instrument, portfolio, event-driven, ML-assisted and agent-researched strategy types.

### 4.4 RSH — Research and experimentation (MC §4)
- **AF2-RSH-001 [T1]** Experiment tracking: unique ID; code, dataset, config, seed and environment fingerprint; results/artifacts; parent/child lineage; side-by-side compare; tags/notes.
- **AF2-RSH-002 [T1]** Grid and random search with budget controls, early stopping, parameter-stability reports. Bayesian adapter and parallel search are T2.
- **AF2-RSH-003 [T0]** Research safety: train/validation/test separation; WFO and OOS enforceable by promotion policy; bootstrap and Monte Carlo robustness; sensitivity; regime split; cost, slippage, delay, missing-data and bad-feed stress tests.
- **AF2-RSH-004 [T0]** No live promotion on backtest P&L alone.
- **AF2-RSH-005 [T1] [NEW]** Multiple-testing control: every experiment increments a per-strategy trials ledger; promotion evidence must state trial count and apply the agreed deflation/penalty method. **[OD-V2-11]**

### 4.5 BKT — Backtest engine (MC §5)
- **AF2-BKT-001 [T1]** Execution realism: bar/tick modes, latency, slippage, spread, fees/taxes/brokerage, partial fills, rejections, liquidity limits, gap-through-stop, open/close edge cases.
- **AF2-BKT-002 [T0]** Determinism: same inputs → same result; formal event ordering; standard seed handling; full run fingerprint; replay from event log; rebuild results from ledger; cross-machine reproducibility test.
- **AF2-BKT-003 [T0]** No look-ahead (enforced by invariant tests).
- **AF2-BKT-004 [T1]** Batch and parallel runs with resource limits, cancellation, resume/retry, priority, worker health. Distributed-worker abstraction only (implementation T2).
- **AF2-BKT-005 [T1] [NEW]** Options-aware simulation: theta decay, IV change, expiry-day gamma and spread widening, lot-size and expiry rules applied **as of the trade date**.

### 4.6 PPR — Paper trading (MC §6)
- **AF2-PPR-001 [T0]** Paper uses the same strategy, risk and order contracts as live; the paper broker is an adapter, not special-case logic.
- **AF2-PPR-002 [T0]** Structural guarantee that paper can never reach a real broker mutation path (separate adapter, separate credentials, mode fixed at process start).
- **AF2-PPR-003 [T1]** Live market data + simulated execution; configurable fill models; latency, rejection, disconnect, partial-fill and broker-error simulation.
- **AF2-PPR-004 [T1]** Restart/recovery, day-rollover and session-boundary tests.
- **AF2-PPR-005 [T1]** Paper-vs-backtest drift report; paper evidence report required before live eligibility.

### 4.7 LIV — Live trading and broker layer (MC §7)
- **AF2-LIV-001 [T0]** Broker-neutral order, position and balance/margin contracts; adapter capability discovery; rate-limit, reconnect and session/token-refresh handling; maintenance mode.
- **AF2-LIV-002 [T0]** Idempotent client order IDs; broker order-ID mapping; duplicate-order and stale-intent suppression; rejection, partial-fill and cancel/replace handling.
- **AF2-LIV-003 [T0] [NEW]** Formal order-lifecycle state machine including an in-doubt state (sent, no acknowledgement). In-doubt orders are resolved by querying the broker; **never blindly retried**.
- **AF2-LIV-004 [T0]** Live engine state machine (DISABLED, READY, CONNECTING, ACTIVE, DEGRADED, PAUSED, EMERGENCY_STOP, RECOVERY); transitions audited; unsafe transitions blocked. The manual-resume latch is preserved; **the engine never auto-arms after a restart or crash.**
- **AF2-LIV-005 [T0]** Reconciliation loop with mismatch escalation. Restart recovery: restore state, fetch broker truth, reconcile positions, pending orders and fills missed during outage, never replay stale entry signals, never duplicate submitted intents, resume protective exits, produce a recovery report.
- **AF2-LIV-006 [T0] [NEW]** Foreign order/position policy: orders or positions not created by AlgoFortis (for example placed from the broker's mobile app) are detected by reconciliation. Default: halt new entries for that account and alert; adoption only by explicit user action. **[OD-V2-06]**
- **AF2-LIV-007 [T0] [NEW]** Multi-device exclusivity: at most one device may be armed for live trading per broker account. Local safety must not depend on cloud availability. **[OD-V2-05]**
- **AF2-LIV-008 [T0] [NEW]** Protective orders rest at the broker where the broker supports it, so a local crash, power cut or network loss does not leave a position unprotected; otherwise a documented degraded policy applies. **[OD-V2-08]**
- **AF2-LIV-009 [T1] [NEW]** Exchange/broker rule handling as versioned configuration: product types, broker auto-square-off windows, freeze quantity and order slicing, price bands, tick size, margin/funds pre-check.
- **AF2-LIV-010 [T0] [NEW]** Kill-switch semantics defined and tested at position, strategy, user and platform level: `HALT_ENTRIES`, `CANCEL_PENDING`, `FLATTEN_ALL` are distinct actions. **[OD-V2-07]**

### 4.8 RSK — Risk and portfolio (MC §8, §9)
- **AF2-RSK-001 [T0]** One central pre-trade risk gate: per-trade risk, quantity/notional, strategy/instrument/portfolio exposure, daily trades, daily loss, drawdown, consecutive losses, session/time, volatility, spread/slippage, stale-data, market-state and duplicate-intent guards.
- **AF2-RSK-002 [T0]** In-trade risk: mandatory SL where required, TP, trailing, OCO linkage, kill switches, connectivity-loss policy, broker-mismatch policy.
- **AF2-RSK-003 [T0]** Governance: overrides explicit and audited; AI and strategies cannot change hard limits; user limits ≤ Owner/system maxima; risk-rule version stored per trade. **The risk gate is the only component able to produce an executable order** (structural, see Architecture §5).
- **AF2-RSK-004 [T1]** Portfolio: multi-strategy aggregation, capital reservation/release, per-strategy and per-user budget, portfolio circuit breaker, concentration limits, P&L and exposure attribution.
- **AF2-RSK-005 [T2]** Correlated-exposure controls, dynamic risk reduction under drawdown, rebalancing framework.
- **AF2-RSK-006 [T1] [NEW]** Event-day risk policy: configurable no-trade / reduced-size windows for scheduled events (policy announcements, budget, elections, results) and for expiry.

### 4.9 OPT — Options and instrument scope (MC §10)
- **AF2-OPT-001 [T1]** Option instrument master; expiry handling; strike-selection abstraction; CE/PE rules; weekly/monthly expiry; symbol normalization; lot-size versioning; exchange-rule changes configurable.
- **AF2-OPT-002 [T0]** Options BUY-only policy enforced at system level (risk gate), not only in strategy code.
- **AF2-OPT-003 [T1]** Premium-based risk calculations; liquidity/spread filters; expiry-day safety rules.
- **AF2-OPT-004 [T1] [NEW]** Historical option-chain source with IV/Greeks, or a synthetic-pricing fallback that is **explicitly labelled** in every backtest report. **[OD-V2-10]**
- **AF2-OPT-005 [T1] [NEW]** Crypto (BTCUSD) scope decision: if in V2.0 it needs a 24×7 calendar, its own adapter and its own fee/margin model; if not, it is V2.3 behind the same instrument abstraction. **[OD-V2-04]**
- **AF2-OPT-006 [T2]** Multi-leg support as an additional module without changing the single-leg core.

### 4.10 AIA — AI and agents (MC §11)
- **AF2-AIA-001 [T0]** AI is advisory by default; acts only through permissioned tools; no direct DB or broker access; cannot bypass risk, execution or kill switch.
- **AF2-AIA-002 [T1]** Provider abstraction: registry, manifests, per-agent routing by config, local + cloud models, health/latency/quota tracking, approved fallback that preserves schema/audit/safety, budgets, secrets only in the secrets system. **[OD-V2-15, OD-V2-16]**
- **AF2-AIA-003 [T1]** AI trade-candidate contract (Architecture §11): structured, TTL-bound, provenance-carrying, deterministically validated; output is a candidate or NO-TRADE, never a broker command.
- **AF2-AIA-004 [T1]** Continuous market intelligence is research-only; hypotheses enter the normal strategy lifecycle; retrieved/web content is untrusted and prompt-injection-defended.
- **AF2-AIA-005 [T1]** Agent safety: capability permissions, read/write separation, tool/path/command allowlists, full action logging, agent-written code needs tests, agents cannot self-promote to live, rollback/cancel controls.
- **AF2-AIA-006 [T1]** Agent memory: per-user boundaries, approved long-term facts only, provenance, correction/deletion, no secrets.
- **AF2-AIA-007 [T1]** Shadow mode: AI decisions logged and compared with outcomes without placing orders. Paper validation mandatory before any AI-assisted live eligibility.
- **AF2-AIA-008 [T2]** Multi-agent committee (3–5+ agents) with independent assessments, challenger role, disagreement → NO-TRADE, correlated-model awareness, calibration tracking, full decision replay.
- **AF2-AIA-009 [T2]** Full agent-role catalogue (MC §11.2). Start with Prime, Risk-challenger and Research agents; add the rest incrementally.
- **AF2-AIA-010 [T1] [NEW]** Build-time agent governance (coding agents used to develop AlgoFortis): slice-scoped prompts, no self-selected build order, path/command allowlists, verification gate per slice, Owner approval at phase exits. (Implementation Plan §6)

### 4.11 SEC — Security (MC §12)
- **AF2-SEC-001 [T0]** Authentication, sessions, Owner/Admin/User roles, least privilege, token rotation and device/session revocation follow `AUTH_ACCESS_CONTRACT_V1` and the anywhere-login decisions. V2 must not weaken them.
- **AF2-SEC-002 [T0]** Broker credentials encrypted at rest (OS-protected), never centralized, excluded from logs, crash dumps and backups; rotation workflow; secrets-provider abstraction.
- **AF2-SEC-003 [T1]** Application security: input validation, output encoding, CSRF/XSS/SQLi/SSRF, upload validation, path traversal, rate limiting, abuse detection, secure headers.
- **AF2-SEC-004 [T1]** Supply chain: dependency scanning, SBOM, **signed release artifacts** (required once auto-update exists).
- **AF2-SEC-005 [T1]** Verification: threat model, static analysis, secret scan, AuthZ negative tests, tenant-escape tests (central service), broker-credential isolation tests, incident playbook.
- **AF2-SEC-006 [T1] [NEW]** Local-machine threat model: tampering with local DB, config or risk limits; malware on the host. Integrity check of risk configuration at load; tamper-evident local audit.

### 4.12 ACC — Account, release and platform track (locked + pending decisions)
- **AF2-ACC-001 [T0]** Anywhere-login as locked: server-authoritative account/device, WebAuthn for interactive auth, separate TPM/CNG-backed device-binding key (DPAPI fallback), 15-min access token, rotating refresh token with reuse detection, 3-device hard limit, no silent eviction, high-assurance recovery revokes everything.
- **AF2-ACC-002 [T1]** Central account stack as locked (AWS ap-south-1, ECS/Fargate, ALB, RDS PostgreSQL private, Secrets Manager, KMS, CloudWatch/CloudTrail) with the agreed cost guardrails. Cloud never executes orders or holds broker secrets.
- **AF2-ACC-003 [T1]** Backup/restore/uninstall preservation as locked (`AlgoFortisBackup/v1` manifest; device identity survives uninstall; broker credentials re-entered after restore).
- **AF2-ACC-004 [T1]** Auto-update and release channel: signed updates, forced vs optional, rollback, security-critical update behaviour. **[OD-V2-20 — open]**
- **AF2-ACC-005 [T1]** License/entitlement including offline-grace behaviour that fails closed for new activations. **[OD-V2-21 — open]**
- **AF2-ACC-006 [T1]** Telemetry and privacy policy (opt-in, no secrets, minimal). **[OD-V2-22 — open]**
- **AF2-ACC-007 [T1]** Publisher, version and canonical domain finalized; installer per locked release behaviour (normal Setup.exe, bundled runtime, Program Files / LocalAppData split).
- **AF2-ACC-008 [T0] [NEW]** Update safety: no update, restart or migration is applied while the live engine is ACTIVE or holds open positions; updates apply in a defined safe window and never auto-arm afterwards.

### 4.13 HOST — Local host resilience [NEW domain]
The engine runs on a user's Windows PC. MC assumes a server-grade host.
- **AF2-HOST-001 [T0]** One live-engine instance per machine/profile (instance lock).
- **AF2-HOST-002 [T0]** Sleep/hibernate prevented during paper/live sessions; resume-from-sleep is treated as a DEGRADED → RECOVERY trigger.
- **AF2-HOST-003 [T0]** System clock checked against a time source; arming is blocked when drift exceeds the configured limit.
- **AF2-HOST-004 [T1]** Supervisor/watchdog restarts a crashed engine into RECOVERY (never into ARMED).
- **AF2-HOST-005 [T1]** Disk-space, memory and log-rotation guards; diagnostics for antivirus/firewall interference and Windows-update reboots. **[OD-V2-24]**
- **AF2-HOST-006 [T1]** Network-identity diagnostics (for example a changed public/static IP when the broker requires whitelisting). **[OD-V2-09]**

### 4.14 AUD — Audit (MC §13)
- **AF2-AUD-001 [T0]** Immutable audit envelope: actor, user/account, UTC timestamp + monotonic sequence, correlation/run ID, before/after state where safe, reason/source, and versions (strategy, risk rule, broker adapter, dataset, model/agent).
- **AF2-AUD-002 [T0]** Every important action and state transition emits an audit event. **[NEW]** For trading-critical actions, failure to write audit evidence blocks the action (fail-closed).
- **AF2-AUD-003 [T1]** Hash-chained tamper evidence, retention policy, searchable timeline, evidence export, incident reconstruction from the trail.

### 4.15 OBS — Observability (MC §14)
- **AF2-OBS-001 [T1]** Structured logs with correlation IDs, per-engine separation, secret redaction, retention.
- **AF2-OBS-002 [T1]** Metrics: API latency, error rates, queue depth, worker health, feed latency/staleness, broker latency, reconciliation mismatches, order and risk rejection rates, strategy health, DB health, CPU/RAM/disk.
- **AF2-OBS-003 [T1]** Alerts: feed/broker disconnect, circuit breaker, reconciliation mismatch, storage threshold, worker crash, repeated strategy failure, error spike, security indicators, backup failure.
- **AF2-OBS-004 [T0] [NEW]** Critical alerts use at least two independent channels (for example on-screen + Telegram) so a network or app fault on the trading PC cannot silence them. **[OD-V2-19]**

### 4.16 TST / PRF / API / OPS / DOC (MC §15–§17, §20–§23)
- **AF2-TST-001 [T0]** Critical invariants (MC §15.2 plus additions) are automated and run on every change. See Test & Release Plan §3.
- **AF2-TST-002 [T1]** Test pyramid: unit, contract, integration, end-to-end, property-based, regression, performance, recovery, failure-injection, security.
- **AF2-TST-003 [T1]** Golden regression suite captured from V1 before any V2 change (Phase 0).
- **AF2-PRF-001 [T1]** Latency budgets per subsystem; profiling before optimizing; bounded queues, backpressure, no unbounded memory growth.
- **AF2-PRF-002 [T2]** Performance-regression benchmarks in CI; horizontal worker scaling.
- **AF2-API-001 [T1]** Versioned HTTP/WebSocket contracts, schema generation, request/response validation, idempotency keys for writes, pagination conventions, error taxonomy, deprecation policy, backward-compatibility tests, internal vs public separation, API audit trail.
- **AF2-OPS-001 [T1]** Environments (local dev, CI, staging, production) with parity strategy; reproducible builds; dependency locks; versioned artifacts; rollback package; upgrade prechecks (DB, config, strategy, plugin); backup before upgrade; tested rollback.
- **AF2-OPS-002 [T1]** CI gates: tests, lint, type check, security and dependency scan, migration validation, build reproducibility, release notes, changelog, code-owner review for critical modules.
- **AF2-OPS-003 [T1]** Feature-flag system with per-feature kill switch and canary rollout; tenant-specific rollout is T2.
- **AF2-DOC-001 [T1]** Documentation set per MC §23 (architecture, module boundaries, data flow, SDK guide, adapter guides, risk engine, recovery runbook, security model, agent permissions, deployment, backup/restore, incident response, user/owner guides, API reference, versioning policy).

### 4.17 UXP / NTF — Product and notifications (MC §18, §19)
- **AF2-UXP-001 [T0]** BACKTEST / PAPER / LIVE are unmistakable; live mode visually distinct; broker connection status always visible in live; risk-stop reason shown; destructive actions confirmed; no "guaranteed profit" language.
- **AF2-UXP-002 [T1]** Owner dashboard (health, users, strategies, risk alerts, broker/feed status, audit search, incident timeline, feature flags, global emergency stop with safeguards) and user dashboard (strategy library, backtest, experiments, paper, live, risk controls, broker setup, positions/orders, analytics, preferences). Navigation rail follows the pending design-token-level spec.
- **AF2-NTF-001 [T1]** In-app, email and Telegram adapters; priority levels; dedupe/throttle; preferences; delivery tracking; notification audit record. WhatsApp/SMS is T2.

### 4.18 CMP — Compliance and business readiness (MC §24)
Exact obligations must be confirmed with qualified advisers at launch; this file only defines the engineering hooks.
- **AF2-CMP-001 [T1]** Product scope documented; backtest/paper/live separated in product language; consent and risk-disclosure flows; terms and privacy-policy support.
- **AF2-CMP-002 [T0] [NEW]** SEBI/exchange retail-algo framework review before any live use: broker route, static-IP requirement, algo tagging/registration, order-rate thresholds. Current applicability must be verified at the time. **[OD-V2-09]**
- **AF2-CMP-003 [T1] [NEW]** Data-protection review for the central account service (India's DPDP Act: consent, retention, deletion, breach handling). **[OD-V2-25]**
- **AF2-CMP-004 [T1]** Broker API terms review process; data retention/deletion policy; audit/evidence export for support; user activity logs.
- **AF2-CMP-005 [T2]** Billing-provider abstraction and plan framework if SaaS pricing is launched.

### 4.19 DRB — Disaster recovery (MC §25)
- **AF2-DRB-001 [T1]** Backup schedule and encryption; restore drills; documented RTO and RPO; recovery plans for DB corruption, lost broker session, feed outage, partial degradation; emergency read-only mode; incident command checklist; post-incident report template.

---

## 5. Non-functional targets (PROPOSED — freeze via Owner Decisions)

| Area | Proposed target |
|---|---|
| Ledger durability | No acknowledged order/fill event lost on crash (RPO = 0 for the local ledger). |
| Engine recovery | Restart → RECOVERY → READY only after reconciliation PASS; automatic recovery attempt completes within a configurable bound (starting point: 5 min). |
| Reconciliation cadence | Every ≤ 60 s while ACTIVE (configurable). |
| Critical alert latency | ≤ 30 s to first channel. |
| Stale-quote threshold | Configurable per instrument; default set in config profile, not code. |
| Clock drift limit for arming | Configurable; default set in config profile. |
| Central auth service (beta) | Best-effort availability; correctness and fail-closed behaviour matter more than uptime. |

## 6. Deferred / do-not-build-yet (MC §27, extended)
- Many brokers before one adapter contract is proven.
- Many asset classes before the instrument abstraction is proven (crypto per **OD-V2-04**).
- AI agents with unrestricted live-order authority (never).
- Social/copy-trading; marketplace/community features.
- Advanced ML before research reproducibility and OOS validation are solid.
- Cloud/distributed workers before local deterministic execution is stable.
- Microsecond optimization before profiling proves the need.
- Rewrites of stable V1 modules for style alone.
- Third-party plugin sandbox and external plugin distribution (AF2-ARC-011).
- Multi-region, enterprise SSO, org/team hierarchy, push session kill, mobile app (already deferred in the anywhere-login decisions).

---

# Appendix A — Review of the Master Checklist

## A1. Verdict
Structure, safety philosophy and coverage are strong. The master rule (extend through contracts, never bypass) and the honest "V3 unnecessary, not impossible" framing are correct. Main problems: (1) it assumes a hosted multi-tenant SaaS while the locked design is local-first with a cloud account authority; (2) it omits several risks that only appear when the engine runs on a retail PC against an Indian broker; (3) the build order defers foundations that everything else depends on; (4) 810 unprioritized items are not buildable by one developer without tiering.

## A2. Conflicts with locked decisions and internal inconsistencies
| # | Finding | Fix in this baseline |
|---|---|---|
| 1 | "Tenant isolation", per-tenant config and billing imply a hosted engine. Locked design: engine is local; only account/device/entitlement is central. | "Tenant" is defined only for the central account plane. Tenant-escape tests apply there (SEC-005). Hosted engine = V2.4+ (OD-V2-02). |
| 2 | §12.1 says "MFA-ready" and generic sessions. Locked design is WebAuthn + device-binding key + 3-device limit + step-up. | SEC-001 / ACC-001 defer to the locked design. |
| 3 | No mention of auto-update, licence/entitlement, telemetry, installer, publisher/domain — all still open. | ACC-004…007 added as open ODs. |
| 4 | §28 build order puts Security, CI/CD and Observability last (Phase H). | Moved to foundation (Plan Phase 1). |
| 5 | §28 puts Live (Phase E) before Risk/Portfolio (Phase F). The risk gate must exist before any adapter can submit. | Risk gate and order lifecycle move into Phase 2 "Safety Spine". |
| 6 | Long paper soak appears only at release qualification (Phase I). | Soak starts as soon as paper is stable (Plan Phase 5) and runs continuously. |
| 7 | Existing V2 documents use phases P0–P10 (35 sections); MC uses A–I. Two build orders will cause agent-loop drift. | OD-V2-01 picks one authority; Plan includes a mapping. |
| 8 | "Cross-machine reproducibility" conflicts with floating-point variance unless a numeric policy exists. | ARC-006, OD-V2-12. |
| 9 | P0/P1 severities are used as gates but never defined. | Defined in Test & Release Plan §9. |
| 10 | Scope overlap: §0, §1, §26 restate each other; kill switches appear in §3.3, §8.2, §18.1. | Consolidated under single requirement IDs. |

## A3. Missing from MC (added above, tagged [NEW])
1. Order **in-doubt** state and no-blind-retry rule (LIV-003).
2. **Foreign/manual orders** placed outside the platform (LIV-006).
3. **Multi-device** conflict: 3 active devices may share one broker account (LIV-007).
4. **Broker-resident protective orders** for crash/power/network loss (LIV-008).
5. **Kill-switch semantics**: halt vs cancel vs flatten (LIV-010).
6. **Never auto-arm after restart/crash/update** (LIV-004, ACC-008).
7. **Local host resilience**: sleep, clock drift, instance lock, watchdog (HOST-001…006).
8. **Options data reality**: historical strike-level prices, IV/Greeks, synthetic fallback labelling (OPT-004, BKT-005).
9. **Data licensing / ToS gate** for every data adapter (DAT-008).
10. **Indian market specifics**: freeze quantity, product types, auto-square-off, price bands, event-day policy (LIV-009, RSK-006).
11. **Regulatory hooks**: SEBI retail-algo framework, static-IP/broker requirements, DPDP (CMP-002, CMP-003).
12. **Multiple-testing control** for parameter search and AI-generated hypotheses (RSH-005).
13. **Numeric policy** and injectable clock/seed/ID (ARC-003, ARC-006).
14. **Audit-write failure = fail-closed** for trading-critical actions (AUD-002).
15. **Independent alert channels** (OBS-004).
16. **Local tamper/threat model** (SEC-006).
17. **Crypto (BTCUSD) scope** decision and 24×7 session model (OPT-005).
18. **Build-agent governance** for coding-agent workflows (AIA-010).
19. **Requirement IDs, tiers, acceptance evidence, severity definitions** (this document, Test & Release Plan).

## A4. Scope and sizing concerns
- 810 unprioritized checkboxes ≈ a multi-year programme for one developer. Tiering (T0/T1/T2) plus the Live-Eligible Milestone (Plan §8) is the mitigation.
- Third-party plugin sandboxing, a 15-role agent catalogue, committee ensembles, Bayesian search and distributed workers are individually large; each is moved to T2 or reduced to a seam.
- AI committee value is unproven; MC already requires shadow mode — this baseline makes shadow mode the V2.0 ceiling for AI-assisted decisions.

## A5. Wording fixes
- "Zero open P1 blockers for production-critical paths" → needs the severity definitions in Test & Release Plan §9.
- "V2 Non-Negotiable Design Rules" and "Completion Gate" should reference requirement IDs, not repeat prose.
- Section 30 roadmap (V2.1–V2.5) is a good expectation-setter; keep it, but tie each item to a deferred requirement ID.

---

# Appendix B — Traceability (MC section → domain)

| MC § | Domain | MC § | Domain |
|---|---|---|---|
| 0, 1, 26 | ARC | 15 | TST |
| 2 | DAT | 16 | PRF |
| 3 | STR | 17 | API |
| 4 | RSH | 18 | UXP |
| 5 | BKT | 19 | NTF |
| 6 | PPR | 20, 21, 22 | OPS |
| 7 | LIV | 23 | DOC |
| 8, 9 | RSK | 24 | CMP |
| 10 | OPT | 25 | DRB |
| 11 | AIA | 27 | Section 6 above |
| 12 | SEC | 28 | Implementation Plan |
| 13 | AUD | 29, 31 | Test & Release Plan |
| 14 | OBS | 30 | Implementation Plan §9 |
