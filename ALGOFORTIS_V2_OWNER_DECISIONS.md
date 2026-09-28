# AlgoFortis V2 — Owner Decision Register

| Field | Value |
|---|---|
| Document | `ALGOFORTIS_V2_OWNER_DECISIONS.md` (4 of 5) |
| Version | v1.0 — remote single-tenant engine / mobile / auth amendment frozen |
| Date | 2026-09-28 |
| Purpose | Freeze gates for the V2 build. Every OD here blocks a named phase in `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`. |
| Status legend | **OPEN** (needs Owner decision) · **FROZEN** (decided, recorded in §4) · **RE-REVIEW REQUIRED** (previous scope changed; dated qualified review still required) · **DEFERRED** (explicitly postponed) |

Recommendations below are proposals unless the corresponding OD is marked **FROZEN**. Frozen decisions are binding build constraints and may only change through a new dated decision-log entry.

---

## 1. Process

1. The Owner reviews an OD, picks an option (or writes a different one) and records it in §4 with the date.
2. Once FROZEN, coding agents treat it as a hard constraint (Implementation Plan §6). Changing it requires a new dated entry, never a silent edit.
3. A phase cannot start while any OD in its blocking row (§5) is OPEN or RE-REVIEW REQUIRED where the changed scope makes that review applicable.
4. On 2026-09-21 the Owner delegated implementation execution to the assistant and authorized work to start from the required starting point. The four Phase 0 blocking decisions were therefore frozen to the documented recommended choices in §3 and recorded in §4.
5. On 2026-09-21 the Owner authorized completion of Phase 1. OD-V2-14 was therefore frozen to the documented V2.0 internal-registry recommendation and formalized by `docs/v2/adr/ADR-009-v2-plugin-scope.md`; external third-party plugin loading remains deferred.
6. On 2026-09-21 the Owner authorized Phase 1 merge and immediate Phase 2 execution. OD-V2-07 was therefore frozen to the documented safe kill-switch recommendation and formalized by `docs/v2/adr/ADR-010-phase2-kill-switch-semantics.md`.
7. On 2026-09-23 the Owner authorized Phase 3 execution. OD-V2-04, OD-V2-10 and OD-V2-13 were frozen to the documented safe/recommended data choices and formalized by `docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md`.
8. On 2026-09-24 the Owner authorized immediate next-phase execution after the verified Phase 3 merge. OD-V2-11 and OD-V2-17 were frozen to fail-closed research/promotion governance, and the ORB protective-policy blocker was frozen as an explicit versioned-policy requirement with no invented economic defaults. These are formalized by `docs/v2/adr/ADR-012-phase4-research-promotion-and-orb-policy.md`.
9. On 2026-09-25 the Owner froze the two Phase-5 entry blockers through the dated Phase-5 decision addendum: OD-V2-24 host resilience in `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md` and OD-V2-19 alert-channel independence in `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`. This root register was reconciled on 2026-09-26 so later readers no longer need to rely on an OPEN-status exception note.
10. On 2026-09-26 the Owner approved the G5 Owner gate and explicitly selected Option A for all Phase-6 blocking safety decisions: OD-V2-05, OD-V2-06, OD-V2-08 and OD-V2-09. The Phase-6 choices are formalized in `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` and `docs/v2/phase6/PHASE6_OWNER_DECISION_FREEZE.md`. This approval does not authorize Live mutation; Live remains READ_ONLY / DISARMED.
11. On 2026-09-26 the Owner approved carrying V1 Track-P platform decisions into V2 and froze OD-V2-20, OD-V2-21, OD-V2-22 and OD-V2-23 with three hardening refinements: versioned update safe windows, clock-tamper-resistant offline entitlement time evidence, and explicit production-domain WebAuthn re-enrollment/device re-binding. These are formalized by `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
12. On 2026-09-28 the Owner amended OD-V2-02 to permit a user-dedicated remote single-tenant execution instance, froze new OD-V2-27, brought mobile into scope, allowed password fallback under mandatory step-up restrictions, and triggered an OD-V2-25 hosted-data re-review. These changes are formalized by `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md` plus its S2/Auth, Phase-6, Phase-9 and roadmap/qualification amendments. This documentation freeze does not authorize implementation or Live mutation.

---

## 2. Frozen inputs carried into V2

These come from earlier decision sheets plus dated amendments. If a historical statement conflicts with a later dated FROZEN amendment, the later dated amendment governs.

| Area | Frozen input |
|---|---|
| Brand | AlgoFortis; tagline "Trading Research & Risk OS"; logo/icon frozen. Rename scope is visible surfaces only (exe, installer, shortcuts, splash, title bar, UI name, publisher/version metadata), not internal DB/schema IDs. |
| V1 safety contract | `READ_ONLY = true`, `DISARMED = true`, zero broker mutation until explicitly changed by a future Owner-approved release gate. The 2026-09-28 remote-hosting decision does not change this. |
| Anywhere-login | Central Account Authority + registered client devices; WebAuthn/passkey preferred and password fallback allowed under the 2026-09-28 S2/Auth amendment; separate device-binding key; rotating session families/reuse detection; max 3 devices/no silent eviction; server-side revoke; high-assurance recovery revokes prior trust. Password-only assurance cannot Arm Live, change broker credentials, enroll/revoke a device, or delete the account without step-up. Risk-reducing Pause/Halt/Exit does not require an extra step-up for an otherwise authorized authenticated user. |
| Execution placement | Engine may run on the supported local execution host or on the user's dedicated remote single-tenant engine instance. Shared multi-tenant trading engine is prohibited. `RiskGateV2` remains sole executable-order authority. |
| Data / secret custody | Central account plane remains identity/device/session/entitlement authority and has no trading authority. Broker credentials never go to the central account DB. On a remote engine they stay in that user's isolated instance-side encrypted store with KMS-backed key custody. Trade/position/runtime data may be hosted on the dedicated instance and therefore triggers OD-V2-25 re-review. |
| Outage / recovery rule | Account/control-plane outage, host restart, reconnect, or update never loosens safety or auto-arms. Execution uncertainty fails closed, reconciles broker truth, and follows the manual resume latch after `RECOVERY`/safety halt. |
| Central account stack | Existing central-account stack decisions remain separate from remote-engine hosting. The 2026-09-28 decision does **not** choose the remote-engine cloud provider, region, instance sizing, or per-instance cost. |
| Backup/uninstall | Existing local backup/uninstall safety rules remain. Remote-engine backup/restore and hosted-data handling require the later hosted-engine/privacy design; broker secrets must not be exposed through backups. |
| Release behaviour | Existing signed/versioned release rules remain; OD-V2-20 safe-window restrictions also apply to remote engines. Restart/update never auto-arms. |
| Auth contract | `docs/AUTH_ACCESS_CONTRACT_V1.md` remains historical V1 authority and is carried into V2 subject to `docs/v2/S2_AUTH_ACCESS_AMENDMENT_2026-09-28.md`. |
| Repo structure | `paper/` and `broker_contract/` reconciliation split; `risk/` independent top-level domain; `strategies/orb/` separate from `engine/strategy/`. |
| Data acquisition | Strict NSE programmatic-acquisition prohibition; dormant-adapter gate. |
| Paper trading | Live-market paper trading mandatory; ExecutionAdapter pattern; Option Selector is a completion blocker. |
| Research rules | Backtest reproducibility rules, report schema, versioned JSON envelope, walk-forward and Monte Carlo (circular-block percentile) decisions already locked in earlier slices. |
| ORB | `OptionEntryBridge` MARKET path approved for ORB V1. **Phase 4 policy frozen:** V2 code may not invent stop/target/trailing economics. Executable ORB simulation requires an explicit versioned `protective_policy_ref` binding stop, target/R:R, trailing/OCO, tick/rounding and policy version. Missing policy fails closed; test fixtures are `TEST_ONLY` and never promotion evidence. See ADR-012. |

---

## 3. Owner decisions

### Scope and structure

**OD-V2-01 — Build-order authority** · Blocks Phase 0
- *Question:* Which phase structure governs the build: MC A–I, the existing V2 plan (P0–P10), or the revised plan?
- *Options:* (A) adopt the revised plan and map old P0–P10 into it; (B) keep P0–P10 and fold in MC corrections; (C) keep MC A–I unchanged.
- *Decision:* **A — adopt the revised Phase 0–10 plan as the canonical build order and map legacy plans into it.**
- *Status:* **FROZEN**

**OD-V2-02 — Deployment model** · Blocks Phase 0 · **AMENDED 2026-09-28**
- *Previous decision (2026-09-21):* local-first V2.0, hosted engine deferred.
- *Amended decision:* **AlgoFortis may use either a supported local execution engine or the user's dedicated remote single-tenant engine instance. One user = one isolated engine instance for the remote path. A shared multi-tenant trading engine is prohibited. Desktop/web/mobile clients may communicate with the owning engine through authenticated API contracts. Central Account Authority remains identity/device/session/entitlement authority only and has no trading authority. Broker credentials never enter the central account database.**
- *Open details:* remote-engine provider, region, instance sizing, per-instance cost, production networking/static-IP design remain OPEN.
- *Authority:* `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`.
- *Status:* **FROZEN (as amended 2026-09-28)**

**OD-V2-27 — Remote single-tenant engine hosting** · New Track-P / pre-Live-pilot architecture gate
- *Decision:* **Remote single-tenant engine hosting is an approved V2 architecture path. One user = one isolated engine instance; no shared multi-tenant trading engine. `RiskGateV2` remains sole executable-order authority; central account service has no trading authority; broker credentials are stored only in the user's execution instance encrypted secret store with KMS-backed key custody; restart/reconnect/update never auto-arms; fail-closed and options BUY-only remain unchanged. Mobile/web/desktop are authenticated clients, not order authorities.**
- *Open details:* provider, region, sizing, cost, native-vs-PWA, static-IP/broker-registration/current regulatory specifics.
- *Authority:* `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`.
- *Status:* **FROZEN**

**OD-V2-03 — Tier assignment and "V2.0 complete"** · Blocks Phase 0
- *Question:* Accept the T0/T1/T2 assignments in the Requirements file?
- *Decision:* **Accepted. V2.0 complete means all T0 + all T1, except only explicitly documented Owner-approved exceptions. T2 is seam/design-only and is not required for V2.0.**
- *Status:* **FROZEN**

**OD-V2-04 — Crypto (BTCUSD) scope** · Blocks Phase 3
- *Options:* (A) in V2.0; (B) V2.3 behind the same instrument abstraction.
- *Decision:* **B — BTCUSD is deferred to V2.3 behind the same instrument/calendar abstractions. Phase 3 must remain free of assumptions that would force a rewrite for a future 24×7 market.**
- *Status:* **FROZEN**

### Trading safety

**OD-V2-05 — Multi-device / multi-engine live exclusivity** · Blocks Phase 6 · **AMENDED 2026-09-28**
- *Decision:* **Exactly one execution engine may be eligible to create new entries for a broker account at a time across local and remote placements. Broker-truth reconciliation remains the hard safety backstop. If a local and remote engine show conflicting/ambiguous activity for the same account, new entries HALT and the account is reconciled. A central armed-device/engine record may be defense-in-depth/coordination evidence but never trading authority or a substitute for broker-truth reconciliation.**
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` plus `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`.
- *Status:* **FROZEN (as amended 2026-09-28)**

**OD-V2-06 — Foreign order / position policy** · Blocks Phase 6
- *Decision:* **A — foreign broker orders/positions halt new entries and raise an auditable alert. They are never ignored and never auto-adopted. Adoption, if supported, requires explicit audited human action.**
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`.
- *Status:* **FROZEN**

**OD-V2-07 — Kill-switch semantics** · Blocks Phase 2
- *Define three distinct actions:* `HALT_ENTRIES` (block new entries), `CANCEL_PENDING` (cancel unfilled entry orders), `FLATTEN_ALL` (close positions).
- *Decision:* **Emergency Stop = `HALT_ENTRIES` + `CANCEL_PENDING` for unfilled entry orders; protective exits remain active. `FLATTEN_ALL` is a separate, explicitly confirmed and audited action. Reconciliation mismatch triggers halt-and-alert/recovery, never automatic flattening.**
- *Status:* **FROZEN**

**OD-V2-08 — Broker-resident protective orders** · Blocks Phase 6
- *Decision:* **A — broker-resident protection is mandatory wherever the selected broker/API supports the required protective semantics. Local/host-only protection is not an equivalent substitute when broker protection exists. This requirement is more critical for remote hosting because host/network failure must not leave a position dependent only on the engine process. If required protection is unsupported or unknown, the affected Live mutation path remains DISARMED until a separate degraded policy is designed, qualified and Owner-approved.**
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` plus `docs/v2/phase6/REMOTE_ENGINE_DEPLOYMENT_SECRET_CUSTODY_AMENDMENT_2026-09-28.md`.
- *Status:* **FROZEN**

**OD-V2-09 — Regulatory and broker path** · Blocks Phase 6
- *Decision:* **A — a dated review of the selected broker's current compliance/API documentation and applicable current exchange/regulatory requirements is mandatory before G6 exit. Historical assumptions are insufficient. Phase-6 contracts/read-only/mock/sandbox work may proceed while Live mutation remains DISARMED. Remote-host static-IP/broker-registration/current SEBI-exchange questions remain part of this dated verification; this register does not guess their answer.**
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`.
- *Status:* **FROZEN**

**OD-V2-24 — Host environment policy** · Blocks Phase 5 · **REMOTE-HOST CLARIFICATION 2026-09-28**
- *Decision:* **Windows 11 x64 remains the first-class local V2.0 qualification target; local active Paper/future Live sessions request temporary sleep/hibernate prevention without permanently changing OS power plans; local sleep/resume uncertainty forces recovery before new entries; watchdog restart is RECOVERY-only and never auto-arms; clock health is injectable/versioned and fails closed when required policy is missing/invalid/exceeded. For a remote server host, desktop sleep-prevention is not applicable, but restart/crash/update/host uncertainty still forces `RECOVERY`, broker-truth reconciliation and manual resume before new entries; it never auto-arms. Exact remote host/provider/SLA/sizing values are not guessed.**
- *Authority:* `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md`, `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`, and the 2026-09-28 remote-engine freeze.
- *Status:* **FROZEN**

### Data, research and numerics

**OD-V2-10 — Options data source and synthetic policy** · Blocks Phase 3
- *Options:* licensed historical option-chain data / broker-provided history / synthetic pricing from underlying + IV model.
- *Decision:* **Licensed historical option-chain data is the authoritative path for promotion-eligible research. Broker-provided history is permitted only when its terms explicitly allow the intended use/retention. Synthetic pricing is development/exploration fallback only, must be labelled `SYNTHETIC` with model/version provenance, and is excluded from promotion evidence unless a later dated Owner Decision explicitly accepts it.**
- *Status:* **FROZEN**

**OD-V2-11 — Multiple-testing / overfitting control** · Blocks Phase 4
- *Options:* (a) trial count + mandatory WFO/OOS thresholds; (b) (a) + deflated performance metric and backtest-overfitting probability estimate; (c) (b) + reality-check style tests.
- *Decision:* **(b) — every trial is append-only ledgered; WFO/OOS is mandatory for promotion evidence; reports include a versioned deflated performance metric and probability-of-backtest-overfitting estimate; every search also carries an explicit versioned maximum trials budget that cannot be silently increased after OOS evidence is viewed. Exact formulas/tolerances are versioned and tested under ADR-012.**
- *Status:* **FROZEN**

**OD-V2-12 — Numeric policy** · Blocks Phase 0
- *Decision:* **Decimal/fixed-point for money, price, quantity and risk. Floats are allowed only in analytics with declared tolerance. Rounding mode and per-instrument tick-size rules must be explicit and versioned.**
- *Status:* **FROZEN**

**OD-V2-13 — Historical store technology** · Blocks Phase 3
- *Options:* (a) columnar files + embedded query engine + catalog in the operational DB; (b) embedded analytical DB only; (c) local Postgres/time-series server.
- *Decision:* **(a) — immutable Parquet/Arrow columnar files, queried in-process through PyArrow Dataset, with dataset catalog metadata in the existing operational SQLite store. No local database server is introduced for V2.0.**
- *Status:* **FROZEN**

**OD-V2-17 — Promotion criteria defaults** · Blocks Phase 4
- *Parameters to set:* minimum trade count, OOS share, WFO windows and pass rate, Monte Carlo drawdown percentile cap, cost/slippage stress margin, minimum paper duration, paper-vs-backtest drift tolerance.
- *Decision:* **All criteria are immutable/versioned configuration, not strategy code. The built-in V2.0 default is `research-only/v1`, which is fail-closed and `NON_PROMOTABLE` until an explicit numeric promotion profile is supplied. No numeric production thresholds are copied from legacy values or guessed; the first numeric profile must be derived from recorded V2 baseline evidence. Backtest-to-paper and paper-to-eligible-for-live profiles are distinct, and missing/incomplete criteria always reject promotion.**
- *Status:* **FROZEN**

### Platform and extensibility

**OD-V2-14 — Plugin scope for V2.0** · Blocks Phase 1
- *Options:* (a) internal adapter registry only; (b) + signed third-party packages; (c) + sandboxed/process-isolated.
- *Decision:* **(a) — V2.0 uses the internal adapter registry only.** Manifests, declared permissions, capability discovery and compatibility checks are implemented now; signed third-party package loading and sandbox/process isolation are deferred to future V2.x.
- *Status:* **FROZEN**

**OD-V2-19 — Alert channels and independence** · Blocks Phase 5
- *Decision:* **Critical Phase-5 alerts must be attempted independently through an authenticated/in-product visible path and an approved independent external channel; existing Telegram support remains permitted and email optional. One channel failure cannot suppress the other. Payloads are minimal/redacted by default and exclude credentials, tokens, raw account identifiers and unrestricted trade logs. Detailed external-channel trade content requires explicit opt-in under the 2026-09-28 mobile/privacy amendment. Alert delivery failure is auditable. Trading safety does not depend on notification-channel availability.**
- *Authority:* `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`, `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`, and the 2026-09-28 remote/mobile freeze.
- *Status:* **FROZEN**

### AI

**OD-V2-15 — AI scope and provider set for V2.0** · Blocks Phase 8
- *Options:* (a) research + shadow only; (b) also committee/ensemble.
- *Recommendation:* **(a)**. Start with one local and one cloud provider through the abstraction; committee stays T2 behind the same contract.
- *Status:* OPEN

**OD-V2-16 — AI data-sharing rules** · Blocks Phase 8
- *Recommendation:* Never send broker credentials, account identifiers, personal data or raw trade logs to any provider. Per-provider allowlist of data classes; review each cloud provider's retention terms; redaction at the tool gateway.
- *Status:* OPEN

### Account, release and privacy (Track P)

**OD-V2-20 — Auto-update and release channel** · Blocks Track P1 · **REMOTE-HOST CLARIFICATION 2026-09-28**
- *Decision:* **A — signed artifacts/manifests with integrity verification, staged rollout and tested rollback. Update/restart/migration is allowed only when a resolved versioned `UpdateSafeWindowPolicy` permits it, never while ACTIVE or while open positions make the transition unsafe. The same safe-window rule applies to local and remote engines. Safe-window production timing is not hard-coded. Missing/invalid/stale/inapplicable safe-window policy defers the update. Update/restart never auto-arms; post-update/restart recovery follows reconciliation/manual-resume rules.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` plus the 2026-09-28 roadmap amendment.
- *Status:* **FROZEN**

**OD-V2-21 — Licence / entitlement** · Blocks Track P1
- *Decision:* **A — preserve the signed V1 7-day offline entitlement lease. Validation must combine signed server-issued time evidence, last successful server check-in, and monotonic elapsed-time evidence where available; wall clock alone cannot extend the lease. Contradictory/backward/lost time evidence fails closed for entitlement-dependent new operations. Licence/cloud failure must not disable protective exits, reconciliation, position monitoring, or read-only safety access.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
- *Status:* **FROZEN**

**OD-V2-22 — Telemetry and privacy** · Blocks Track P1
- *Decision:* **A — telemetry remains opt-in, purpose-limited, minimized and scrubbed. Strategy content, broker credentials/tokens, unrestricted trade logs, balances and unnecessary trading data are excluded from telemetry. Support bundles sanitize first. Purpose/retention are versioned and production retention numbers are not guessed. Telemetry availability never becomes a trading-safety dependency. Hosted engine operational data required for engine operation is not reclassified as telemetry merely because it resides on a dedicated remote instance; hosted-data privacy is separately governed by OD-V2-25 re-review.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` and `docs/v2/phase9/HOSTED_DATA_PRIVACY_AMENDMENT_2026-09-28.md`.
- *Status:* **FROZEN**

**OD-V2-23 — Publisher, version scheme, canonical domain** · Blocks Track P1
- *Decision:* **A — preserve SemVer 2.0.0, independently versioned HTTP/API contracts (`/api/v1/`) and explicit migrations. Exact legal publisher and canonical production domain remain `PENDING_EXTERNAL` until finalized before S3/release. Dev/staging WebAuthn credentials are never silently promoted to production; production-domain finalization requires fresh production WebAuthn enrollment plus explicit device-key possession re-proof/re-binding. Missing/corrupt device key requires fresh enrollment.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
- *Status:* **FROZEN**

**OD-V2-25 — Data-protection (DPDP) and retention** · Blocks Phase 9 · **HOSTED-DATA RE-REVIEW 2026-09-28**
- *Question:* Owner obligations for identity plus hosted engine trade/position/runtime data: notice/consent, minimization, processor/service-provider treatment, retention/deletion, user rights, grievance/nomination, security/breach handling.
- *Required next decision evidence:* selected provider/region/data flow plus a **dated qualified legal review** of then-current applicable requirements; update notice/consent and hosted-data policy accordingly.
- *Hard rule:* green technical/security tests must never be represented as proof of legal compliance.
- *Authority:* `docs/v2/phase9/HOSTED_DATA_PRIVACY_AMENDMENT_2026-09-28.md`.
- *Status:* **RE-REVIEW REQUIRED / OPEN**

### Rollout

**OD-V2-18 — Live pilot policy** · Blocks Phase 10
- *Parameters:* capital cap, lot size, one-strategy limit, hard daily-loss cap, minimum number of sessions, stop conditions, who monitors.
- *Status:* OPEN
- *Safety note:* V2 implementation and qualification may proceed through research, backtest, paper, shadow, read-only broker integration and dry-run evidence while live mutation remains DISARMED. No automatic live-money enablement is authorized by this register.

**OD-V2-26 — Release-qualification thresholds** · Blocks Phase 10
- *Question:* Freeze soak length, drift tolerances, performance baselines and severity definitions.
- *Recommendation:* Start from the proposals in Test & Release Plan §6 and §9 and adjust after Phase 5 data.
- *Status:* OPEN

---

## 4. Decision log

| OD | Decision | Date | Notes / authority |
|---|---|---|---|
| OD-V2-01 | Revised Phase 0–10 plan is canonical; legacy plans map into it. | 2026-09-21 | Phase 0 owner lock; ADR-001 to formalize mapping. |
| OD-V2-02 | V2.0 originally frozen local-first; cloud account authority only; hosted execution deferred. | 2026-09-21 | Historical decision; amended 2026-09-28 below. |
| OD-V2-03 | V2.0 requires all T0 + T1; T2 remains seam-only unless explicitly excepted. | 2026-09-21 | Exceptions, if any, must be written and Owner-approved. |
| OD-V2-12 | Decimal/fixed-point for money/price/quantity/risk; analytics floats require declared tolerance. | 2026-09-21 | Rounding and tick-size rules must be explicit/versioned; ADR-008 to formalize details. |
| OD-V2-14 | V2.0 uses the internal adapter registry only; external signed packages and sandbox/process isolation are deferred. | 2026-09-21 | `docs/v2/adr/ADR-009-v2-plugin-scope.md` |
| OD-V2-07 | Emergency Stop halts entries and cancels pending entry orders; protective exits stay active; FLATTEN_ALL is separate and explicit. | 2026-09-21 | `docs/v2/adr/ADR-010-phase2-kill-switch-semantics.md` |
| OD-V2-04 | BTCUSD deferred to V2.3 behind the common instrument/calendar abstractions. | 2026-09-23 | `docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md` |
| OD-V2-10 | Licensed option-chain data is authoritative for promotion evidence; synthetic data is labelled fallback only. | 2026-09-23 | `docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md` |
| OD-V2-13 | Parquet/Arrow + in-process PyArrow Dataset + operational SQLite catalog; no local server. | 2026-09-23 | `docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md` |
| OD-V2-11 | Append-only trials ledger + mandatory WFO/OOS + deflated performance metric + PBO estimate + explicit trials budget. | 2026-09-24 | `docs/v2/adr/ADR-012-phase4-research-promotion-and-orb-policy.md` |
| OD-V2-17 | Promotion criteria are versioned config; built-in `research-only/v1` is fail-closed/non-promotable until evidence-backed numeric profile exists. | 2026-09-24 | `docs/v2/adr/ADR-012-phase4-research-promotion-and-orb-policy.md` |
| ORB-P4 | No hardcoded ORB protective economics; explicit versioned protective-policy reference required; missing policy fails closed. | 2026-09-24 | `docs/v2/adr/ADR-012-phase4-research-promotion-and-orb-policy.md` |
| OD-V2-24 | Windows 11 x64 first-class local host; temporary session sleep prevention; resume/watchdog recovery-only; versioned clock policy; no guessed production drift/hardware threshold. | 2026-09-25 | `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md`; `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md` |
| OD-V2-19 | Critical alerts independently attempted; redacted payloads; notifier failure cannot weaken safety. | 2026-09-25 | `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`; `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md` |
| OD-V2-05 | Local hard backstop frozen for Live exclusivity; broker-truth reconciliation is safety authority. | 2026-09-26 | Historical wording; amended across local/remote placements 2026-09-28. |
| OD-V2-06 | Foreign broker activity halts new entries + alerts; explicit audited human adoption only; never ignore or auto-adopt. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-08 | Broker-resident protection mandatory where supported; unsupported required protection keeps affected Live mutation DISARMED pending separate policy approval. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-09 | Dated current broker/exchange/regulatory verification is mandatory before G6 exit; historical assumptions are insufficient. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-20 | Signed updates/rollback preserved; versioned safe-window policy required; no hard-coded production update timing; never auto-arm. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-21 | V1 signed 7-day offline lease preserved; signed server/check-in + monotonic time evidence hardens against wall-clock tamper; protective safety unaffected. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-22 | Opt-in/minimized/scrubbed telemetry; sanitize-first support bundles; versioned purpose/retention; telemetry never safety authority. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-23 | SemVer/API/migrations preserved; publisher/domain pending external finalization; production domain requires fresh WebAuthn + device re-proof/re-bind. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-02 AMENDMENT | Local-first-only restriction replaced by local-or-dedicated-remote single-tenant execution placement; shared multi-tenant trading engine prohibited. | 2026-09-28 | `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md` |
| OD-V2-27 | Remote single-tenant engine hosting approved as V2 architecture path; central account has no trading authority; instance-side KMS-backed secret custody; no auto-arm. | 2026-09-28 | `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md` |
| OD-V2-05 AMENDMENT | Exactly one eligible execution engine per broker account across local/remote; conflict -> HALT + reconcile. | 2026-09-28 | Remote-engine freeze + Phase-6 secret-custody amendment. |
| OD-V2-20 CLARIFICATION | Safe-window update policy applies to remote engine too; restart/update -> recovery/manual resume; never auto-arm. | 2026-09-28 | Roadmap/qualification amendment. |
| OD-V2-24 CLARIFICATION | Cloud host has no desktop sleep requirement; restart/crash/update uncertainty still -> RECOVERY + reconcile + manual resume. | 2026-09-28 | Remote-engine freeze. |
| AUTH/S2 AMENDMENT | Passkey preferred; password fallback allowed; sensitive risk-increasing actions require step-up from password-only session; risk-reducing Pause/Halt/Exit does not. | 2026-09-28 | `docs/v2/S2_AUTH_ACCESS_AMENDMENT_2026-09-28.md` |
| MOBILE SCOPE | Mobile is in scope now; redacted push by default; authenticated-app detail; detailed Telegram/email only explicit opt-in; native vs PWA open. | 2026-09-28 | Remote-engine freeze + S2/Auth amendment. |
| OD-V2-25 RE-REVIEW | Hosted trade/position/runtime data triggers new privacy/processor analysis, notice/consent update and dated qualified legal review; tests green != legal compliance. | 2026-09-28 | `docs/v2/phase9/HOSTED_DATA_PRIVACY_AMENDMENT_2026-09-28.md` |

---

## 5. Blocking matrix

| Gate | ODs that must be FROZEN / reviewed before it starts or exits |
|---|---|
| Phase 0 | 01, 02, 03, 12 — **FROZEN; OD-02 amended 2026-09-28** |
| Phase 1 | 14 — **FROZEN 2026-09-21** |
| Phase 2 | 07 — **FROZEN 2026-09-21** |
| Phase 3 | 04, 10, 13 — **FROZEN 2026-09-23** |
| Phase 4 | 11, 17, ORB protective-policy governance — **FROZEN 2026-09-24** |
| Phase 5 | 19, 24 — **FROZEN 2026-09-25; OD-24 remote-host clarification 2026-09-28** |
| Phase 6 | 05, 06, 08, 09 — **FROZEN; OD-05 remote/local amendment 2026-09-28**; remote-engine deployment/secret-custody design added while Live stays DISARMED |
| Phase 8 | 15, 16 |
| Phase 9 | 25 — **RE-REVIEW REQUIRED / OPEN for hosted-data model** |
| Phase 10 | 18, 26; remote/mobile production path additionally requires Track-P remote-engine/mobile qualification and applicable OD-25 dated review |
| Track P1 | 20, 21, 22, 23 — **FROZEN 2026-09-26; OD-20 remote-host clarification 2026-09-28** |
| Track P — post-S2 remote/mobile | 27 — **FROZEN 2026-09-28**; provider/region/sizing/cost and mobile technology remain OPEN design selections, not OD-27 reversals |
