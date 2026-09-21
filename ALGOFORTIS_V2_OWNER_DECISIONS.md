# AlgoFortis V2 — Owner Decision Register

| Field | Value |
|---|---|
| Document | `ALGOFORTIS_V2_OWNER_DECISIONS.md` (4 of 5) |
| Version | v0.4 — Phase 2 kill-switch semantics lock recorded |
| Date | 2026-09-21 |
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

---

## 2. Frozen inputs carried into V2

These come from earlier decision sheets. **Confirm each still holds before Phase 0 closes; update if anything has drifted.**

| Area | Frozen input |
|---|---|
| Brand | AlgoFortis; tagline "Trading Research & Risk OS"; logo/icon frozen. Rename scope is visible surfaces only (exe, installer, shortcuts, splash, title bar, UI name, publisher/version metadata), not internal DB/schema IDs. |
| V1 safety contract | `READ_ONLY = true`, `DISARMED = true`, zero broker mutation, no real broker connection, until explicitly changed by a future release. |
| Anywhere-login | Central account authority + local app per PC; WebAuthn for interactive auth; separate TPM/CNG-backed device-binding key (DPAPI fallback); 15-min access token; rotating refresh token with reuse detection; max 3 devices, no silent eviction; step-up on new device; server-side revoke; high-assurance recovery revokes all sessions, refresh families and device keys. |
| Sync scope | Server: account, devices, security/session state, entitlement, non-sensitive settings. Local only: broker secrets, strategy configs, trade logs, live positions. Broker credentials re-entered per device. |
| Outage rule | Cloud auth outage never stops the local engine or loosens local safety; new login/enrollment/recovery/entitlement changes fail closed; UI shows "AUTH SERVICE OFFLINE — LOCAL SAFETY CONTINUES". |
| Cloud stack | AWS ap-south-1; ECS/Fargate behind ALB; RDS PostgreSQL private; ACM, Route 53, Secrets Manager, KMS, CloudWatch, CloudTrail; no App Runner. Monthly budget ₹6,000 with alert tiers; no auto-shutdown; 1-task start. Not allowed in V1: server-side broker credentials, cloud strategy/trade-state sync, cloud live-order execution. |
| Backup/uninstall | Uninstall keeps `%LOCALAPPDATA%\AlgoFortis\` by default; device identity survives uninstall; backup manifest `AlgoFortisBackup/v1`; no export/cloning of device private keys; broker secrets never backed up. |
| Release behaviour | Normal Setup.exe, no terminal, bundled runtime, source-independent, Program Files + LocalAppData separation. |
| Auth contract | `AUTH_ACCESS_CONTRACT_V1` (Owner/User authority) preserved. |
| Repo structure | `paper/` and `broker_contract/` reconciliation split; `risk/` independent top-level domain; `strategies/orb/` separate from `engine/strategy/`. |
| Data acquisition | Strict NSE programmatic-acquisition prohibition; dormant-adapter gate. |
| Paper trading | Live-market paper trading mandatory; ExecutionAdapter pattern; Option Selector is a completion blocker. |
| Research rules | Backtest reproducibility rules, report schema, versioned JSON envelope, walk-forward and Monte Carlo (circular-block percentile) decisions already locked in earlier slices. |
| ORB | `OptionEntryBridge` MARKET path approved for ORB V1. **Still open:** stop formula, target/R:R, trailing/OCO semantics, config schema (needed before the ORB port in Phase 4). |

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
- *Status:* **FROZEN**

**OD-V2-03 — Tier assignment and "V2.0 complete"** · Blocks Phase 0
- *Question:* Accept the T0/T1/T2 assignments in the Requirements file?
- *Decision:* **Accepted. V2.0 complete means all T0 + all T1, except only explicitly documented Owner-approved exceptions. T2 is seam/design-only and is not required for V2.0.**
- *Status:* **FROZEN**

**OD-V2-04 — Crypto (BTCUSD) scope** · Blocks Phase 3
- *Options:* (A) in V2.0; (B) V2.3 behind the same instrument abstraction.
- *Recommendation:* **B**. It needs a 24×7 calendar, its own adapter, fee and margin model, and different regulatory handling. Keep the calendar and instrument abstractions free of "index-options-only" assumptions so B costs no rewrite.
- *Status:* OPEN

### Trading safety

**OD-V2-05 — Multi-device live exclusivity** · Blocks Phase 6
- *Problem:* Up to 3 devices per account can each hold the same broker credentials; two armed engines could trade the same account.
- *Options:* (A) local only: arm ownership recorded locally, broker-truth reconciliation detects foreign activity and halts; (B) cloud-issued live lease; (C) hybrid: A as the hard backstop plus an *advisory* cloud "armed device" record that blocks a second device from arming while the cloud is reachable.
- *Recommendation:* **A as mandatory backstop; C only if explicitly accepted later.** B is not recommended.
- *Status:* OPEN

**OD-V2-06 — Foreign order / position policy** · Blocks Phase 6
- *Question:* What happens when the broker account contains orders or positions AlgoFortis did not create?
- *Options:* halt new entries / ignore / auto-adopt.
- *Recommendation:* Halt new entries for that account, alert, and adopt only by explicit user action. Never auto-adopt.
- *Status:* OPEN

**OD-V2-07 — Kill-switch semantics** · Blocks Phase 2
- *Define three distinct actions:* `HALT_ENTRIES` (block new entries), `CANCEL_PENDING` (cancel unfilled entry orders), `FLATTEN_ALL` (close positions).
- *Decision:* **Emergency Stop = `HALT_ENTRIES` + `CANCEL_PENDING` for unfilled entry orders; protective exits remain active. `FLATTEN_ALL` is a separate, explicitly confirmed and audited action. Reconciliation mismatch triggers halt-and-alert/recovery, never automatic flattening.**
- *Status:* **FROZEN**

**OD-V2-08 — Broker-resident protective orders** · Blocks Phase 6
- *Question:* Must SL/target rest at the broker so a local crash cannot leave a position unprotected?
- *Recommendation:* Required for live wherever the broker supports it. Where unsupported, document the degraded policy and keep live mutation disarmed until the safety policy is explicitly qualified.
- *Status:* OPEN

**OD-V2-09 — Regulatory and broker path** · Blocks Phase 6
- *Question:* Which compliant route governs live algorithmic orders for retail users?
- *To verify (current rules must be checked, not assumed):* SEBI/exchange retail-algo framework applicability and effective dates; broker-side requirements (static IP whitelisting, algo tagging/registration, order-rate thresholds); whether personal use differs from distributing the software to other users.
- *Recommendation:* Do a dated review with the chosen broker's compliance documentation and a qualified adviser before Phase 6 exit. Record the outcome as a design input. This is not legal advice.
- *Status:* OPEN

**OD-V2-24 — Host environment policy** · Blocks Phase 5
- *Question:* Supported Windows versions, sleep/hibernate policy, watchdog behaviour, clock-drift limit for arming, minimum hardware, antivirus guidance.
- *Recommendation:* Sleep prevented during sessions; resume-from-sleep forces RECOVERY; arming blocked beyond a configurable drift limit; watchdog restarts into RECOVERY only.
- *Status:* OPEN

### Data, research and numerics

**OD-V2-10 — Options data source and synthetic policy** · Blocks Phase 3
- *Options:* licensed historical option-chain data / broker-provided history / synthetic pricing from underlying + IV model.
- *Recommendation:* Choose the source by licence terms first, cost second. Any synthetic pricing must be labelled in every backtest report and excluded from promotion evidence unless explicitly accepted.
- *Status:* OPEN

**OD-V2-11 — Multiple-testing / overfitting control** · Blocks Phase 4
- *Options:* (a) trial count + mandatory WFO/OOS thresholds; (b) (a) + deflated performance metric and backtest-overfitting probability estimate; (c) (b) + reality-check style tests.
- *Recommendation:* **(b)**. Record every trial in the ledger; require WFO and OOS; report a deflated metric. Exact formulas go in the ADR.
- *Status:* OPEN

**OD-V2-12 — Numeric policy** · Blocks Phase 0
- *Decision:* **Decimal/fixed-point for money, price, quantity and risk. Floats are allowed only in analytics with declared tolerance. Rounding mode and per-instrument tick-size rules must be explicit and versioned.**
- *Status:* **FROZEN**

**OD-V2-13 — Historical store technology** · Blocks Phase 3
- *Options:* (a) columnar files + embedded query engine + catalog in the operational DB; (b) embedded analytical DB only; (c) local Postgres/time-series server.
- *Recommendation:* **(a)** — no server process to install or babysit on a user's PC.
- *Status:* OPEN

**OD-V2-17 — Promotion criteria defaults** · Blocks Phase 4
- *Parameters to set:* minimum trade count, OOS share, WFO windows and pass rate, Monte Carlo drawdown percentile cap, cost/slippage stress margin, minimum paper duration, paper-vs-backtest drift tolerance.
- *Recommendation:* Keep them configuration, not code. Set initial numbers after the ORB baseline analysis so they reflect real trade frequency rather than guesses.
- *Status:* OPEN

### Platform and extensibility

**OD-V2-14 — Plugin scope for V2.0** · Blocks Phase 1
- *Options:* (a) internal adapter registry only; (b) + signed third-party packages; (c) + sandboxed/process-isolated.
- *Decision:* **(a) — V2.0 uses the internal adapter registry only.** Manifests, declared permissions, capability discovery and compatibility checks are implemented now; signed third-party package loading and sandbox/process isolation are deferred to future V2.x.
- *Status:* **FROZEN**

**OD-V2-19 — Alert channels and independence** · Blocks Phase 5
- *Recommendation:* Critical alerts on at least two independent channels (on-screen + Telegram; email as third). Consider an optional non-sensitive "engine silent" heartbeat to the central service so a dead PC still triggers an alert — this links to OD-V2-22 (telemetry).
- *Status:* OPEN

### AI

**OD-V2-15 — AI scope and provider set for V2.0** · Blocks Phase 8
- *Options:* (a) research + shadow only; (b) also committee/ensemble.
- *Recommendation:* **(a)**. Start with one local and one cloud provider through the abstraction; committee stays T2 behind the same contract.
- *Status:* OPEN

**OD-V2-16 — AI data-sharing rules** · Blocks Phase 8
- *Recommendation:* Never send broker credentials, account identifiers, personal data or raw trade logs to any provider. Per-provider allowlist of data classes; review each cloud provider's retention terms; redaction at the tool gateway.
- *Status:* OPEN

### Account, release and privacy (Track P — the open items from the existing decision sequence)

**OD-V2-20 — Auto-update and release channel** · Blocks Track P1
- *Recommendation:* Signed artifacts; security-critical updates forced but only in a safe window (never while ACTIVE or holding positions); non-critical updates deferrable; staged rollout; tested rollback; never auto-arm afterwards.
- *Status:* OPEN

**OD-V2-21 — Licence / entitlement** · Blocks Track P1
- *Recommendation:* Cached entitlement with a time-boxed offline grace; new activations fail closed. Licence expiry or outage must never disable protective exits, reconciliation or read-only access to positions.
- *Status:* OPEN

**OD-V2-22 — Telemetry and privacy** · Blocks Track P1
- *Recommendation:* Opt-in; scrubbed crash reports; no strategy, trade or credential content; retention limit; documented purpose.
- *Status:* OPEN

**OD-V2-23 — Publisher, version scheme, canonical domain** · Blocks Track P1
- *Recommendation:* Finalize the publisher identity (needed for code signing), a semantic-version scheme aligned with V2.x, and the canonical production domain. Domain purchase is pending.
- *Status:* OPEN

**OD-V2-25 — Data-protection (DPDP) and retention** · Blocks Phase 9
- *Question:* Owner's obligations for identity data held in the central plane: consent, retention, deletion, breach handling.
- *Recommendation:* Confirm current applicability and timelines with a qualified adviser; keep the central data set minimal.
- *Status:* OPEN

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

| OD | Decision | Date | Notes / ADR link |
|---|---|---|---|
| OD-V2-01 | Revised Phase 0–10 plan is canonical; legacy plans map into it. | 2026-09-21 | Phase 0 owner lock; ADR-001 to formalize mapping. |
| OD-V2-02 | V2.0 is local-first; cloud is account authority only. Hosted execution deferred. | 2026-09-21 | Preserves existing local-first trust boundary. |
| OD-V2-03 | V2.0 requires all T0 + T1; T2 remains seam-only unless explicitly excepted. | 2026-09-21 | Exceptions, if any, must be written and Owner-approved. |
| OD-V2-12 | Decimal/fixed-point for money/price/quantity/risk; analytics floats require declared tolerance. | 2026-09-21 | Rounding and tick-size rules must be explicit/versioned; ADR-008 to formalize details. |
| OD-V2-14 | V2.0 uses the internal adapter registry only; external signed packages and sandbox/process isolation are deferred. | 2026-09-21 | `docs/v2/adr/ADR-009-v2-plugin-scope.md` |
| OD-V2-07 | Emergency Stop halts entries and cancels pending entry orders; protective exits stay active; FLATTEN_ALL is separate and explicit. | 2026-09-21 | `docs/v2/adr/ADR-010-phase2-kill-switch-semantics.md` |

---

## 5. Blocking matrix

| Gate | ODs that must be FROZEN before it starts |
|---|---|
| Phase 0 | 01, 02, 03, 12 — **FROZEN 2026-09-21** |
| Phase 1 | 14 — **FROZEN 2026-09-21** |
| Phase 2 | 07 — **FROZEN 2026-09-21** |
| Phase 3 | 04, 10, 13 |
| Phase 4 | 11, 17, ORB protective-policy ODs (§2) |
| Phase 5 | 19, 24 |
| Phase 6 | 05, 06, 08, 09 |
| Phase 8 | 15, 16 |
| Phase 9 | 25 |
| Phase 10 | 18, 26 |
| Track P1 | 20, 21, 22, 23 |