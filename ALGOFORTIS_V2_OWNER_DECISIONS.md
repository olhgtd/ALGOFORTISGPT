# AlgoFortis V2 — Owner Decision Register

| Field | Value |
|---|---|
| Document | `ALGOFORTIS_V2_OWNER_DECISIONS.md` (4 of 5) |
| Version | v1.2 — Phase-9 OD-V2-25 reconciliation on top of local-first portability/auth corrections |
| Date | 2026-10-01 |
| Purpose | Freeze gates for the V2 build. Every OD here blocks a named phase in `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`. |
| Status legend | **OPEN** (needs Owner decision) · **FROZEN** (decided, recorded in §4) · **DEFERRED** (explicitly postponed) |

Recommendations below are proposals unless the corresponding OD is marked **FROZEN**. Frozen decisions are binding build constraints and may only change through a new dated decision-log entry.

---

## 1. Process

1. The Owner reviews an OD, picks an option (or writes a different one) and records it in §4 with the date.
2. Once FROZEN, coding agents treat it as a hard constraint (Implementation Plan §6). Changing it requires a new dated entry, never a silent edit.
3. A phase cannot start while any OD in its blocking row (§5) is OPEN.
4. On 2026-09-21 the Owner delegated implementation execution to the assistant and authorized work to start from the required starting point. The four Phase 0 blocking decisions were therefore frozen to the documented recommended choices in §3 and recorded in §4.
5. On 2026-09-21 the Owner authorized completion of Phase 1. OD-V2-14 was therefore frozen to the documented V2.0 internal-registry recommendation and formalized by `docs/v2/adr/ADR-009-v2-plugin-scope.md`; external third-party plugin loading remains deferred.
6. On 2026-09-21 the Owner authorized Phase 1 merge and immediate Phase 2 execution. OD-V2-07 was therefore frozen to the documented safe kill-switch recommendation and formalized by `docs/v2/adr/ADR-010-phase2-kill-switch-semantics.md`.
7. On 2026-09-23 the Owner authorized Phase 3 execution. OD-V2-04, OD-V2-10 and OD-V2-13 were frozen to the documented safe/recommended data choices and formalized by `docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md`.
8. On 2026-09-24 the Owner authorized immediate next-phase execution after the verified Phase 3 merge. OD-V2-11 and OD-V2-17 were frozen to fail-closed research/promotion governance, and the ORB protective-policy blocker was frozen as an explicit versioned-policy requirement with no invented economic defaults. These are formalized by `docs/v2/adr/ADR-012-phase4-research-promotion-and-orb-policy.md`.
9. On 2026-09-25 the Owner froze the two Phase-5 entry blockers through the dated Phase-5 decision addendum: OD-V2-24 host resilience in `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md` and OD-V2-19 alert-channel independence in `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`. This root register was reconciled on 2026-09-26 so later readers no longer need to rely on an OPEN-status exception note.
10. On 2026-09-26 the Owner approved the G5 Owner gate and explicitly selected Option A for all Phase-6 blocking safety decisions: OD-V2-05, OD-V2-06, OD-V2-08 and OD-V2-09. The Phase-6 choices are formalized in `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` and `docs/v2/phase6/PHASE6_OWNER_DECISION_FREEZE.md`. This approval does not authorize Live mutation; Live remains READ_ONLY / DISARMED.
11. On 2026-09-26 the Owner approved carrying V1 Track-P platform decisions into V2 and froze OD-V2-20, OD-V2-21, OD-V2-22 and OD-V2-23 with three hardening refinements: versioned update safe windows, clock-tamper-resistant offline entitlement time evidence, and explicit production-domain WebAuthn re-enrollment/device re-binding. These are formalized by `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
12. On 2026-09-28 the Owner corrected the in-progress architecture freeze: **OD-V2-02 remains unchanged/local-first for V2.0**; new OD-V2-27 freezes deployment portability rather than remote hosting; password fallback with mandatory step-up is retained; remote hosting/mobile/push/hosted-data re-review/hosted static-IP questions/internet-facing API external security testing are deferred cloud go-live triggers. The earlier contrary wording in commit `b94a7a5c470da7d63aac8db0d79536e7b7650cf0` is superseded by the follow-up correction documents.
13. On 2026-10-01 this root register was reconciled with the controlling dated 2026-09-27 Phase-9 privacy freeze. OD-V2-25 is **FROZEN for engineering architecture**, not certified as legal compliance; a dated qualified legal review remains mandatory before G9 exit. Live remains `READ_ONLY / DISARMED`.

---

## 2. Frozen inputs carried into V2

These come from earlier decision sheets plus dated corrections. If a historical statement conflicts with a later dated FROZEN correction, the later correction governs.

| Area | Frozen input |
|---|---|
| Brand | AlgoFortis; tagline "Trading Research & Risk OS"; logo/icon frozen. Rename scope is visible surfaces only (exe, installer, shortcuts, splash, title bar, UI name, publisher/version metadata), not internal DB/schema IDs. |
| V1 safety contract | `READ_ONLY = true`, `DISARMED = true`, zero broker mutation, no real broker connection, until explicitly changed by a future release. |
| Anywhere-login | Central account authority + local app per PC; WebAuthn/passkey preferred for interactive auth; password fallback allowed under the 2026-09-28 S2/Auth amendment; separate TPM/CNG-backed device-binding key (DPAPI fallback); rotating refresh token with reuse detection; max 3 devices, no silent eviction; server-side revoke; high-assurance recovery revokes old trust. A password-only session cannot Arm Live, change broker credentials, enroll/revoke a device or delete the account without step-up; risk-reducing Pause/Halt/Exit does not require extra step-up for an otherwise authorized authenticated user. |
| Sync scope | Server: account, devices, security/session state, entitlement, non-sensitive settings. Local only for V2.0: broker secrets, strategy configs, trade logs, live positions. Broker credentials re-entered per device. |
| Outage rule | Cloud auth outage never stops the local engine or loosens local safety; new login/enrollment/recovery/entitlement changes fail closed; UI shows "AUTH SERVICE OFFLINE — LOCAL SAFETY CONTINUES". |
| Cloud stack | AWS ap-south-1 central-account stack as locked; this is not a hosted trading-engine decision. Not allowed in V2.0 under OD-V2-02: server-side broker credentials, cloud strategy/trade-state sync, cloud live-order execution. |
| Deployment portability | **OD-V2-27:** one engine build supports deployment profiles `LOCAL_PC` (V2.0/current) and `REMOTE_HOST` (future). Profile differences must be config/adapters/ports, not a trading-domain rewrite. Headless engine + authenticated versioned API is preserved from day one with localhost/local-machine bind default for V2.0. Paths, secrets, storage, clock, host lifecycle and alerts stay behind ports/adapters. |
| Backup/uninstall | Uninstall keeps `%LOCALAPPDATA%\AlgoFortis\` by default; device identity survives uninstall; backup manifest `AlgoFortisBackup/v1`; no export/cloning of device private keys; broker secrets never backed up. `AlgoFortisBackup/v1` is also the frozen migration vehicle for a future qualified host cutover. |
| Release behaviour | Normal Setup.exe, no terminal, bundled runtime, source-independent, Program Files + LocalAppData separation. |
| Auth contract | `AUTH_ACCESS_CONTRACT_V1` remains historical V1 authority and is carried into V2 subject to `docs/v2/S2_AUTH_ACCESS_AMENDMENT_2026-09-28.md`. |
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

**OD-V2-02 — Deployment model** · Blocks Phase 0
- *Question:* Is V2.0 local-first (one engine per install, cloud = account authority only) or a hosted multi-tenant engine?
- *Decision:* **Local-first for V2.0.** Trading engines, trading state and broker secrets remain local; cloud remains account/device/entitlement authority. Hosted engine remains a future V2.4+ seam, not V2.0 scope.
- *Correction note:* The attempted 2026-09-28 amendment in commit `b94a7a5c470da7d63aac8db0d79536e7b7650cf0` is withdrawn/superseded. This 2026-09-21 decision remains AS-IS.
- *Status:* **FROZEN**

**OD-V2-27 — Deployment portability** · Track-P architecture seam
- *Decision:* **One AlgoFortis engine build must support two deployment profiles without a trading-domain rewrite: `LOCAL_PC` is the V2.0/current profile; `REMOTE_HOST` is a future single-tenant profile. Switching profiles must be configuration/adapters/ports only. The engine must be headless-capable with an authenticated, versioned API from day one; V2.0 binds locally/localhost by default. Paths, secrets, storage, clock/time evidence, host lifecycle/recovery and alerts are behind ports/adapters; domain code must not depend directly on Windows/DPAPI/path/power assumptions. Host migration uses `AlgoFortisBackup/v1`; the target starts `RECOVERY`, reconciles broker truth and requires manual resume. Local and future remote engines may never both be eligible for the same broker account; cutover must explicitly hand off eligibility. A materially different target host/profile must re-run the applicable golden suite and failure-injection qualification.**
- *Cloud-go-live boundary:* Remote provisioning, public API exposure, mobile/push, hosted-data OD-V2-25 re-review, hosted/static-IP OD-V2-09 questions, cloud secret/KMS selection and internet-facing API external security testing are deferred until a later Owner cloud go-live decision.
- *Authority:* `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md` (corrected content; historical filename retained for audit continuity).
- *Status:* **FROZEN**

**OD-V2-03 — Tier assignment and "V2.0 complete"** · Blocks Phase 0
- *Question:* Accept the T0/T1/T2 assignments in the Requirements file?
- *Decision:* **Accepted. V2.0 complete means all T0 + all T1, except only explicitly documented Owner-approved exceptions. T2 is seam/design-only and is not required for V2.0.**
- *Status:* **FROZEN**

**OD-V2-04 — Crypto (BTCUSD) scope** · Blocks Phase 3
- *Options:* (A) in V2.0; (B) V2.3 behind the same instrument abstraction.
- *Decision:* **B — BTCUSD is deferred to V2.3 behind the common instrument/calendar abstractions. Phase 3 must remain free of assumptions that would force a rewrite for a future 24×7 market.**
- *Status:* **FROZEN**

### Trading safety

**OD-V2-05 — Multi-device live exclusivity** · Blocks Phase 6
- *Decision:* **A — local hard backstop is mandatory. Local safety does not depend on cloud availability; broker-truth reconciliation detects activity inconsistent with the current local engine and fails closed by halting new entries and reconciling. A future cloud armed-device record may exist only as advisory defense-in-depth and never as trading authority.**
- *Portability clarification:* A future `LOCAL_PC` -> `REMOTE_HOST` cutover for the same broker account must never leave both execution hosts eligible simultaneously. Overlap/ambiguity triggers `HALT_ENTRIES` + audit/alert + broker reconciliation; no auto-takeover or auto-arm.
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` plus corrected OD-V2-27 portability freeze.
- *Status:* **FROZEN**

**OD-V2-06 — Foreign order / position policy** · Blocks Phase 6
- *Decision:* **A — foreign broker orders/positions halt new entries and raise an auditable alert. They are never ignored and never auto-adopted. Adoption, if supported, requires explicit audited human action.**
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`.
- *Status:* **FROZEN**

**OD-V2-07 — Kill-switch semantics** · Blocks Phase 2
- *Define three distinct actions:* `HALT_ENTRIES` (block new entries), `CANCEL_PENDING` (cancel unfilled entry orders), `FLATTEN_ALL` (close positions).
- *Decision:* **Emergency Stop = `HALT_ENTRIES` + `CANCEL_PENDING` for unfilled entry orders; protective exits remain active. `FLATTEN_ALL` is a separate, explicitly confirmed and audited action. Reconciliation mismatch triggers halt-and-alert/recovery, never automatic flattening.**
- *Status:* **FROZEN**

**OD-V2-08 — Broker-resident protective orders** · Blocks Phase 6
- *Decision:* **A — broker-resident protection is mandatory wherever the selected broker/API supports the required protective semantics. Local-only protection is not an equivalent substitute when broker protection exists. If required protection is unsupported or unknown, the affected Live mutation path remains DISARMED until a separate degraded policy is designed, qualified and Owner-approved.**
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`.
- *Status:* **FROZEN**

**OD-V2-09 — Regulatory and broker path** · Blocks Phase 6
- *Decision:* **A — a dated review of the selected broker's current compliance/API documentation and applicable current exchange/regulatory requirements is mandatory before G6 exit. Historical assumptions are insufficient. Phase-6 contracts/read-only/mock/sandbox work may proceed while Live mutation remains DISARMED.**
- *Cloud-go-live trigger:* Hosted/static-IP/broker-registration questions specific to a future `REMOTE_HOST` are not current V2.0 scope; they require a fresh dated OD-V2-09 verification if/when cloud go-live is approved.
- *Authority:* `docs/v2/adr/ADR-015-phase6-live-safety-policy.md`.
- *Status:* **FROZEN**

**OD-V2-24 — Host environment policy** · Blocks Phase 5
- *Decision:* **Windows 11 x64 is the first-class V2.0 qualification target; one trading-engine instance is permitted per local profile/machine context; active Paper/future Live sessions request temporary sleep/hibernate prevention without permanently changing OS power plans; sleep/resume uncertainty forces recovery before new entries; watchdog restart is RECOVERY-only and never auto-arms; clock health is injectable/versioned and fails closed when its required policy is missing/invalid/exceeded; exact production clock-drift and minimum-hardware thresholds are evidence-driven rather than guessed; antivirus/security protections are not required to be disabled; recovery takes precedence over retry/new entries and host events are audited.**
- *Authority:* `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md` and `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`.
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
- *Decision:* **Critical Phase-5 alerts must be attempted independently through a local on-screen/Windows-visible path and Telegram; email is optional. One channel failure cannot suppress the other. Payloads are minimal/redacted and exclude credentials, tokens, raw account identifiers and unrestricted trade logs. Alert delivery failure is auditable. Paper safety does not depend on Telegram availability. A remote dead-PC/engine-silent heartbeat is deferred to OD-V2-22 telemetry/privacy governance. This decision does not authorize cloud trading, broker mutation or remote arming.**
- *Authority:* `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md` and `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md`.
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

**OD-V2-20 — Auto-update and release channel** · Blocks Track P1
- *Decision:* **A — signed artifacts/manifests with integrity verification, staged rollout and tested rollback. Update/restart/migration is allowed only when a resolved versioned `UpdateSafeWindowPolicy` permits it, never while ACTIVE or while open positions make the transition unsafe. Safe-window production timing is not hard-coded. Missing/invalid/stale/inapplicable safe-window policy defers the update. Update/restart never auto-arms Live.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
- *Status:* **FROZEN**

**OD-V2-21 — Licence / entitlement** · Blocks Track P1
- *Decision:* **A — preserve the signed V1 7-day offline entitlement lease. Validation must combine signed server-issued time evidence, last successful server check-in, and monotonic elapsed-time evidence where available; wall clock alone cannot extend the lease. Contradictory/backward/lost time evidence fails closed for entitlement-dependent new operations. Licence/cloud failure must not disable protective exits, reconciliation, local position monitoring, or read-only safety access.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
- *Status:* **FROZEN**

**OD-V2-22 — Telemetry and privacy** · Blocks Track P1
- *Decision:* **A — telemetry remains opt-in, purpose-limited, minimized and scrubbed. Strategy content, broker credentials/tokens, unrestricted trade logs, balances and unnecessary trading data are excluded. Support bundles sanitize first. Purpose/retention are versioned and production retention numbers are not guessed. Telemetry availability never becomes a trading-safety dependency.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
- *Status:* **FROZEN**

**OD-V2-23 — Publisher, version scheme, canonical domain** · Blocks Track P1
- *Decision:* **A — preserve SemVer 2.0.0, independently versioned HTTP/API contracts (`/api/v1/`) and explicit migrations. Exact legal publisher and canonical production domain remain `PENDING_EXTERNAL` until finalized before S3/release. Dev/staging WebAuthn credentials are never silently promoted to production; production-domain finalization requires fresh production WebAuthn enrollment plus explicit device-key possession re-proof/re-binding. Missing/corrupt device key requires fresh enrollment.**
- *Authority:* `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`.
- *Status:* **FROZEN**

**OD-V2-25 — Data-protection (DPDP) and retention** · Blocks Phase 9
- *Question:* Owner's obligations for identity data held in the central plane: consent, retention, deletion, breach handling.
- *Decision:* **FROZEN for Phase-9 engineering architecture: minimum-data, privacy-first, versioned and fail-closed governance. Production legal basis, response timelines, retention durations, breach timelines and transfer obligations are never guessed in code.**
- *Authority:* `docs/v2/phase9/PHASE9_DPDP_DECISION_FREEZE.md` (dated 2026-09-27).
- *Legal gate:* A dated review by a qualified legal adviser remains mandatory before G9 exit. This engineering freeze is **not** a legal-compliance certification.
- *Cloud-go-live trigger:* A separate hosted-data re-review is required only if/when `REMOTE_HOST` is later approved for production and trade/position/runtime data is actually hosted. That future review is not active V2.0 scope merely because OD-V2-27 preserves portability.
- *Safety:* Live remains `READ_ONLY / DISARMED`; this privacy decision grants no broker/trading authority.
- *Status:* **FROZEN**

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
| OD-V2-02 | V2.0 is local-first; cloud is account authority only. Hosted execution deferred. | 2026-09-21 | Preserves existing local-first trust boundary; **remains AS-IS after 2026-09-28 correction**. |
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
| OD-V2-24 | Windows 11 x64 first-class; single instance; temporary session sleep prevention; resume/watchdog recovery-only; versioned clock policy; no guessed production drift/hardware threshold. | 2026-09-25 | `docs/v2/adr/ADR-013-phase5-host-resilience-policy.md`; `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md` |
| OD-V2-19 | Critical alerts independently attempt local Windows-visible + Telegram delivery; redacted payloads; notifier failure cannot weaken Paper safety; heartbeat deferred to OD-V2-22. | 2026-09-25 | `docs/v2/adr/ADR-014-phase5-alert-channel-independence.md`; `docs/v2/phase5/PHASE5_OWNER_DECISION_FREEZE.md` |
| OD-V2-05 | Local hard backstop is mandatory for Live exclusivity; cloud may only be advisory defense-in-depth. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-06 | Foreign broker activity halts new entries + alerts; explicit audited human adoption only; never ignore or auto-adopt. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-08 | Broker-resident protection mandatory where supported; unsupported required protection keeps affected Live mutation DISARMED pending separate policy approval. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-09 | Dated current broker/exchange/regulatory verification is mandatory before G6 exit; historical assumptions are insufficient. | 2026-09-26 | `docs/v2/adr/ADR-015-phase6-live-safety-policy.md` |
| OD-V2-20 | Signed updates/rollback preserved; versioned safe-window policy required; no hard-coded production update timing; never auto-arm. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-21 | V1 signed 7-day offline lease preserved; signed server/check-in + monotonic time evidence hardens against wall-clock tamper; protective safety unaffected. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-22 | Opt-in/minimized/scrubbed telemetry; sanitize-first support bundles; versioned purpose/retention; telemetry never safety authority. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-23 | SemVer/API/migrations preserved; publisher/domain pending external finalization; production domain requires fresh WebAuthn + device re-proof/re-bind. | 2026-09-26 | `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md` |
| OD-V2-25 | Minimum-data, privacy-first, versioned, fail-closed Phase-9 engineering governance; dated qualified legal review remains mandatory before G9 exit. | 2026-09-27 | `docs/v2/phase9/PHASE9_DPDP_DECISION_FREEZE.md`; not a legal-compliance certification; Live remains `READ_ONLY / DISARMED`. |
| CORRECTION | Prior 2026-09-28 remote-hosting amendment to OD-V2-02 is withdrawn; OD-V2-02 remains local-first for V2.0. | 2026-09-28 | Follow-up correction to commit `b94a7a5c470da7d63aac8db0d79536e7b7650cf0`. |
| OD-V2-27 | Deployment portability: same engine build, `LOCAL_PC` now / `REMOTE_HOST` future; config/adapters only; headless authenticated local API; host-neutral ports; backup/restore migration; recovery/manual resume; target-host requalification. | 2026-09-28 | Corrected portability freeze + roadmap/Phase-6 amendment. |
| OD-V2-05 PORTABILITY CLARIFICATION | Future local/remote cutover may never leave both hosts eligible for the same broker account; overlap -> HALT + reconcile; explicit handoff/manual resume. | 2026-09-28 | Corrected OD-V2-27 portability freeze. |
| AUTH/S2 AMENDMENT | Passkey preferred; password fallback allowed; sensitive risk-increasing actions require step-up from password-only session; risk-reducing Pause/Halt/Exit does not. | 2026-09-28 | `docs/v2/S2_AUTH_ACCESS_AMENDMENT_2026-09-28.md` |
| CLOUD GO-LIVE TRIGGERS | Mobile/push, hosted-data OD-V2-25 re-review, hosted/static-IP OD-V2-09 verification, remote secret/KMS selection and external testing of an internet-facing engine API activate only after a later Owner cloud go-live decision. | 2026-09-28 | Corrected portability roadmap + Phase-9 trigger doc. |

---

## 5. Blocking matrix

| Gate | ODs that must be FROZEN before it starts |
|---|---|
| Phase 0 | 01, 02, 03, 12 — **FROZEN 2026-09-21; OD-02 remains AS-IS** |
| Phase 1 | 14 — **FROZEN 2026-09-21** |
| Phase 2 | 07 — **FROZEN 2026-09-21** |
| Phase 3 | 04, 10, 13 — **FROZEN 2026-09-23** |
| Phase 4 | 11, 17, ORB protective-policy governance — **FROZEN 2026-09-24** |
| Phase 5 | 19, 24 — **FROZEN 2026-09-25** |
| Phase 6 | 05, 06, 08, 09 — **FROZEN 2026-09-26**; portability keeps host-specific dependencies behind adapters but does not add remote hosting to V2.0 |
| Phase 8 | 15, 16 |
| Phase 9 | 25 — **FROZEN 2026-09-27 for engineering architecture**; dated qualified legal review remains mandatory before G9 exit; hosted-data re-review is a future cloud go-live trigger |
| Phase 10 | 18, 26 |
| Track P1 | 20, 21, 22, 23 — **FROZEN 2026-09-26** |
| Track P — deployment portability foundation | 27 — **FROZEN 2026-09-28**; `LOCAL_PC` current, `REMOTE_HOST` future/deferred |

### Future cloud go-live (not a V2.0 gate)

If the Owner later activates `REMOTE_HOST` for production, the cloud go-live decision must separately trigger remote provisioning/secret/network design, mobile/push if desired, hosted-data OD-V2-25 re-review, hosted/static-IP/broker-registration OD-V2-09 verification, and external/independent security testing of any internet-facing engine API.
