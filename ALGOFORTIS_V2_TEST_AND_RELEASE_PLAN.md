# AlgoFortis V2 — Test & Release Qualification Plan

| Field | Value |
|---|---|
| Document | `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` (5 of 5) |
| Version | v0.1 DRAFT — for Owner review |
| Date | 2026-09-21 |
| Verifies | Requirements (AF2-… IDs), Architecture guarantees, Implementation Plan gates |
| Status | PROPOSED. Numeric thresholds marked *(proposed)* are frozen by **OD-V2-26** / **OD-V2-17** / **OD-V2-18**. |

---

## 1. Purpose

MC §15, §28 Phase I, §29 and §31 say *what* must pass. This document defines *how it is proven*, *what evidence is stored*, *what counts as a blocker*, and *who signs*. A requirement is not "done" until its evidence exists in the evidence bundle (§11).

## 2. Verification strategy

| Layer | What it proves | Where it runs |
|---|---|---|
| Unit | Pure domain logic (risk math, state machines, models) | every commit |
| Contract | Every port/adapter honours its versioned contract (broker conformance kit, data-provider kit, AI-provider kit, notifier kit) | every commit |
| Architecture | Module boundaries, no adapter imports in domain, live adapter unreachable from backtest/paper entrypoints | every commit |
| Invariant / property-based | The critical invariants in §3 under randomized and adversarial inputs | every commit |
| Integration | Module-to-module flows (data → strategy → gate → paper adapter → ledger) | every commit / nightly |
| End-to-end | Full backtest, paper session, recovery scenarios | nightly |
| Regression (golden) | V1 behaviour preserved (§4) | every commit |
| Failure-injection | Behaviour under the faults in §5 | nightly + before gates |
| Security | §7 | per phase + release |
| Performance | §8 | per phase + release |
| Soak / shadow / pilot | §6 | continuous from Phase 5 |

Rules: a failing invariant or golden test blocks merge. Critical modules (Risk, Live, Audit, Auth) need an independent review pass. Tests are part of every slice's "Done when".

---

## 3. Critical invariants register

Each invariant has an automated test that runs in CI from the phase shown, and keeps running afterwards.

| ID | Invariant | Source | From phase |
|---|---|---|---|
| INV-01 | No duplicate live order for the same intent | MC §15.2 | 2 (hardened 5, 6) |
| INV-02 | No stale signal/intent replay after restart or delayed submission | MC §15.2 | 2 (hardened 5) |
| INV-03 | No order can exist without Risk Gate approval (`ApprovedOrder` cannot be constructed elsewhere) | MC §15.2 | 2 |
| INV-04 | No user can access another user's credentials/data (central plane tenant-escape + local profile separation) | MC §15.2 | Track P2 |
| INV-05 | No live action originates from the backtest engine | MC §15.2 | 2 |
| INV-06 | No paper action reaches real broker execution | MC §15.2 | 2 |
| INV-07 | No invalid state transition (engine, order, strategy) | MC §15.2 | 2 |
| INV-08 | An IN_DOUBT order is never blindly retried | **NEW** | 2 |
| INV-09 | Foreign order/position halts new entries and raises an alert | **NEW** | 6 |
| INV-10 | Protective orders/logic survive restart and recover safely | MC §15.2 | 5 |
| INV-11 | A lower config layer can never exceed a higher hard limit | MC §8.4 | 2 |
| INV-12 | No look-ahead in backtesting | MC §15.2 | 4 |
| INV-13 | Same deterministic inputs → identical run fingerprint (also across machines) | MC §15.2 | 4 |
| INV-14 | AI output cannot become an order except through deterministic strategy rules + Risk Gate | MC §11 | 8 |
| INV-15 | The system never auto-arms after restart, crash, update, reconnect or outage | **NEW** | 2 (hardened 5, 6) |
| INV-16 | A trading-critical action is blocked if its audit event cannot be written | **NEW** | 2 |
| INV-17 | Options BUY-only is enforced at the Risk Gate | MC §10 | 2 |
| INV-18 | Secrets never appear in logs, crash dumps, backups, prompts or agent memory | MC §12.2 | 1 |
| INV-19 | Cloud/auth outage never stops or loosens local safety; account operations fail closed | Locked decision | Track P2 / 6 |
| INV-20 | No update, restart or migration is applied while the engine is ACTIVE or holds open positions | **NEW** | Track P3 |
| INV-21 | Two devices cannot both be armed for the same broker account (mechanism per OD-V2-05) | **NEW** | 6 |

**Phase 2 exit set:** INV-01, 02, 03, 05, 06, 07, 08, 11, 15, 16, 17.

---

## 4. Golden regression suite

- **Captured in Phase 0** from frozen V1: representative datasets, strategy runs (including ORB), risk decisions, order-lifecycle traces, report outputs.
- **Contents:** input dataset versions, config snapshots, expected ledgers, expected report JSON, expected run fingerprints.
- **Rules:** a golden change requires an explicit, reviewed "golden update" entry stating why behaviour changed. Silent updates are forbidden.
- **Cross-machine:** runs on at least two environments in CI; deterministic components must match fingerprints exactly, analytic floats within the declared tolerance (OD-V2-12).

---

## 5. Failure-injection catalogue

Each case is automated in paper/simulated mode from Phase 5 and re-run against the real adapter in read-only or sandbox mode in Phase 6 where possible.

| ID | Injected fault | Expected behaviour |
|---|---|---|
| FI-01 | Kill process after order sent, before ack | Restart → RECOVERY; order resolved via broker query; no duplicate; no auto-arm |
| FI-02 | Kill process with open position | RECOVERY; positions and protective exits reconciled and resumed; recovery report produced |
| FI-03 | Feed freezes (stale quotes) | New entries blocked by gate; exits continue; DEGRADED; alert |
| FI-04 | Feed gaps / out-of-order events | Detected, handled per ordering rule, audited |
| FI-05 | Broker disconnect/reconnect with active position | DEGRADED; reconnect; reconciliation before resuming entries |
| FI-06 | Broker rate-limit storm | Backoff; no duplicate submissions; alert |
| FI-07 | Broker session/token expiry mid-session | Refresh or halt entries; no silent failure |
| FI-08 | Order rejection storm | Circuit breaker triggers per policy; audit trail complete |
| FI-09 | Partial fill then disconnect | Lifecycle and reconciliation converge on broker truth |
| FI-10 | Foreign order/position appears in broker account | Halt new entries; alert; no auto-adopt |
| FI-11 | Second device attempts to arm on same broker account | Refused or halted per OD-V2-05 mechanism; alert |
| FI-12 | System clock jump/drift | Arming blocked / DEGRADED; audit records skew |
| FI-13 | Sleep/resume | DEGRADED → RECOVERY; no auto-arm |
| FI-14 | Disk full / audit write failure | Trading-critical actions blocked; alert; read-only safe mode |
| FI-15 | Operational DB corruption | Read-only emergency mode; restore from verified backup; reconciliation before resume |
| FI-16 | Risk config tampered or invalid | Live refuses to start; last known-good restore path |
| FI-17 | Cloud/auth outage during ACTIVE | "AUTH SERVICE OFFLINE — LOCAL SAFETY CONTINUES"; engine and protective logic continue; account ops fail closed |
| FI-18 | Update becomes available during ACTIVE | Deferred to safe window (INV-20) |
| FI-19 | AI provider timeout/outage | NO_TRADE/HOLD; only approved fallback provider; audited |
| FI-20 | Malformed / stale / policy-violating TradeCandidate | Rejected by deterministic validator |
| FI-21 | Prompt-injection payload inside fetched news/web content | Treated as untrusted data; no tool call or policy change results |
| FI-22 | Migration fails midway | Automatic rollback to pre-migration backup; system starts in known-good state |
| FI-23 | Day rollover, session boundary, expiry day | Correct session/expiry rules applied; no stale orders across boundary |
| FI-24 | Network loss on the trading PC | Critical alert delivered on an independent channel where reachable; local protective logic continues |

---

## 6. Shadow, soak and pilot criteria *(proposed — freeze via OD-V2-26 / OD-V2-18)*

**Shadow (AI and pipeline, no orders)**
- Runs continuously from Phase 8; decisions, evidence and later outcomes logged; calibration tracked against outcomes.
- Exit to consideration for paper validation: stable schema validity rate, no invariant violations, reviewed disagreement cases.

**Paper soak (Phase 5 onward)**
- At least **20 consecutive trading sessions** *(proposed)*, including at least one weekly expiry, one monthly expiry, one induced restart-recovery and one induced disconnect.
- **Zero** unreconciled mismatches, **zero** invariant violations, **zero** unexplained duplicate or stale orders, **zero** open P0/P1.
- Paper-vs-backtest drift within the tolerance frozen in OD-V2-17, with every outlier explained.
- Paper evidence report generated automatically at the end.

**Live pilot (Phase 10, stage 2)**
- Limits per OD-V2-18 (minimum lot, one strategy, hard daily-loss cap, Owner monitoring).
- At least **10 live sessions** *(proposed)* with zero P0/P1 incidents, reconciliation clean every session, protective orders verified at the broker, kill-switch drill executed once during the pilot outside market risk (dry run).
- Any P0 → return to the previous stage.

---

## 7. Security verification

| Area | Verification |
|---|---|
| Threat model | Written before Phase 1 exit; reviewed at Phase 6 and Phase 10; includes the local-machine model (AF2-SEC-006) |
| AuthN/AuthZ | Negative tests for every role boundary; device-limit, step-up, revoke and recovery flows; refresh-token reuse detection |
| Tenant isolation | Tenant-escape tests on the central account service |
| Secrets | Secret scan in CI; log/crash-dump/backup redaction tests (INV-18); broker-credential isolation tests |
| App security | Input validation, injection, SSRF, path traversal, upload validation, rate limiting, secure headers |
| Supply chain | Dependency audit, SBOM generation, signed artifacts verified in the installer/updater |
| AI | Prompt-injection suite (FI-21), tool-permission tests, no-bypass red-team (INV-14) |
| Independent review | External or independent-pass security review before Phase 10 |

---

## 8. Performance and disaster-recovery verification

**Performance**
- Latency budgets defined per subsystem (Phase 1) and measured in CI baselines from Phase 4.
- High event-rate feed test, multi-strategy concurrent test, large historical batch test, disk-pressure and network-loss behaviour, no unbounded queues or memory growth.
- Baseline recorded as release evidence; regression thresholds enforced from Phase 9.

**Disaster recovery**
- Restore drill: restore a real backup into a clean profile, verify data and reconciliation. Repeated each release.
- Rollback drill: upgrade → rollback → verify state and audit chain.
- DB-corruption, lost-broker-session, feed-outage and partial-degradation runbooks each exercised at least once.
- RTO and RPO documented and measured against the targets in Requirements §5.

---

## 9. Severity definitions and release-blocker rules

| Severity | Definition | Release effect |
|---|---|---|
| **P0** | Can cause an unintended, duplicate or unauthorised live order; an unprotected position; bypass of the risk gate or kill switch; secret exposure; cross-user data access; corruption or loss of ledger/audit data; violation of any invariant in §3 | Blocks any release and any live stage; immediate rollback/stop |
| **P1** | Material defect in a production-critical path with a workable safe fallback (for example a false-positive reconciliation halt, failed restore on a supported path, misrouted critical alert, wrong risk figure shown) | Blocks release of the affected path until fixed or Owner-accepted in writing |
| **P2** | Non-critical functional defect, degraded non-critical feature, documentation gap | Tracked; does not block |
| **P3** | Cosmetic | Tracked |

**Production-critical paths:** intent → Risk Gate → adapter → order lifecycle → reconciliation → recovery; kill switches; audit writing; device/session gating for arming; secrets handling; update/rollback; critical alerting.

---

## 10. Phase gates (G0–G10) and required evidence

A gate is passed only when the Owner approves the evidence.

| Gate | Evidence required |
|---|---|
| **G0** | Frozen ODs (01, 02, 03, 12); V1 audit report; zero open P0/P1; golden suite green on two environments; V1 contract freeze list |
| **G1** | CI pipeline run showing boundary/architecture tests, lint, type, dependency and secret scans; migration + backup + rollback test log; audit-chain verification; golden green |
| **G2** | Phase 2 invariant set green (§3); proof test that no executable order can be built outside the gate; mode-isolation test; conformance kit results for the paper adapter; state-machine transition-table tests |
| **G3** | Dataset catalog export with versions/checksums/provenance/quality scores for all V1 datasets; resampling reproducibility test; stale-feed test; licensing-gate test |
| **G4** | Two-machine fingerprint match for ORB and golden runs; look-ahead test; promotion evidence bundle sample; experiment lineage sample; trials ledger sample |
| **G5** | Failure-injection results FI-01…FI-09, FI-12…FI-14, FI-23, FI-24 in paper; recovery reports; paper soak started; alert-channel independence test |
| **G6** | Real-adapter conformance kit; read-only reconciliation stability log; FI results against the real adapter (read-only/sandbox); INV-09 and INV-21 green; regulatory review record (OD-V2-09); DISARMED verification |
| **G7** | Portfolio exposure and circuit-breaker tests through the same gate |
| **G8** | No-bypass red-team report; prompt-injection results; provider-outage results; shadow log statistics |
| **G9** | Restore drill and rollback drill logs; runbook exercise records; dashboards/notification tests; DPDP/retention review record |
| **G10** | Full release-qualification checklist (§11); evidence bundle archived; sign-offs (§11); zero open P0; zero open P1 on production-critical paths |
| **GP-S2** (Track P) | Device/session gating tests; INV-04, INV-19; recovery/revoke tests |
| **GP-S3** (Track P) | Installer/updater tests; update-safety test (INV-20); signed-artifact verification; backup/restore/uninstall preservation tests |

---

## 11. Release qualification and sign-off

### 11.1 Qualification checklist (maps to MC §28 Phase I)
| Item | Evidence |
|---|---|
| Full regression PASS | CI run: unit, contract, integration, e2e, golden |
| Security audit PASS | Security review report + closed findings |
| Tenant isolation PASS | Tenant-escape test results (central plane) |
| Recovery/restart PASS | FI-01, FI-02, FI-13 results; recovery reports |
| Long-duration paper soak PASS | Soak report per §6 |
| Broker disconnect/reconnect PASS | FI-05…FI-07 results |
| Reconciliation PASS | Reconciliation logs over soak; INV-09/10 |
| Risk circuit-breaker PASS | FI-08 and portfolio breaker tests |
| Dataset provenance PASS | Catalog export and lineage checks |
| Reproducibility PASS | Two-machine fingerprint results |
| Performance baseline PASS | Baseline report |
| Backup/restore drill PASS | Drill log |
| Documentation complete | Documentation checklist (AF2-DOC-001) |
| Zero open P0; zero open P1 on production-critical paths | Defect register export |

### 11.2 Evidence bundle (archived per release)
Version manifest; SBOM; signed artifact hashes; requirement-to-evidence traceability table; invariant test results; golden results; failure-injection results; soak and pilot reports; security report; DR drill logs; performance baseline; defect register; Owner Decision log snapshot; sign-off record.

### 11.3 Owner sign-offs (MC §31)
Architecture · Safety · Security · Data quality · Backtest/research validation · Paper soak · Live recovery/reconciliation · Risk engine · Tenant isolation · Backup/restore · Monitoring/alerts · Documentation · Release candidate frozen · Evidence bundle archived.

---

## 12. Rollback, hotfix and post-incident

- **Rollback:** every release ships a rollback package; upgrade path always takes a verified backup first; rollback is exercised in drills (§8).
- **Hotfix:** must pass the invariant set and golden suite. No hotfix or update is applied during market hours while the engine is ACTIVE or holding positions unless the Owner declares a P0 and the engine is first brought to a safe state.
- **Post-incident report template**
  ```text
  Incident ID / severity / date-time (UTC + IST)
  Summary and user/position impact
  Timeline (from audit ledger, with correlation IDs)
  Detection: how and how fast
  Root cause and contributing factors
  Which invariant/requirement failed or was missing
  Immediate actions taken; state after (positions, orders, reconciliation)
  Fixes: code, config, process; tests added (INV / FI ids)
  Owner decision required? (OD reference)
  Follow-ups with owners and dates
  ```
