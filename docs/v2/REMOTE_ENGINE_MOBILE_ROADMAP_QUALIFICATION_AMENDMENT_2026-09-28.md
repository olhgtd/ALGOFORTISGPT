# AlgoFortis V2 — Deployment Portability Roadmap & Qualification Amendment

**Date:** 2026-09-28  
**Status:** OWNER-FROZEN DOCUMENTATION AMENDMENT — CORRECTED  
**Amends:** `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md` and `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md` by dated overlay only  
**Authority:** corrected OD-V2-27 in `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`  
**Safety invariant:** Live remains `READ_ONLY / DISARMED`; this amendment schedules architecture/qualification seams only.

> **Correction note:** The earlier version of this file incorrectly made remote hosting/mobile qualification a current pre-pilot requirement. That is superseded. V2.0 remains local-first under OD-V2-02.

## 1. Canonical roadmap insertion

Add a bounded Track-P architecture item after S2:

### Track P — Deployment Portability Foundation

**Goal:** make the V2.0 local engine portable enough that a later move to a single-tenant remote host changes configuration/adapters rather than trading-domain code.

**Current V2.0 deliverables:**

- one engine build;
- deployment profile contract with `LOCAL_PC` current and `REMOTE_HOST` future;
- headless-capable engine/process boundary;
- authenticated, versioned engine API from day one;
- V2.0 default API bind limited to localhost/local machine;
- path/filesystem port + local adapter;
- secret-store port + local secure adapter;
- storage/persistence port + local adapter;
- clock/time-evidence port;
- host lifecycle/health/recovery port;
- alert/notifier port;
- no Windows/DPAPI/path/power assumptions in trading-domain code;
- `AlgoFortisBackup/v1` backup/restore as the host-migration contract;
- future cutover contract that preserves OD-V2-05 exclusivity and no-auto-arm.

**Explicit non-goals for V2.0:**

- provisioning a remote engine;
- selecting cloud provider/region/instance size/cost;
- exposing the engine API to the internet;
- mobile client or push implementation;
- hosted-data privacy redesign;
- static-IP/broker-hosting regulatory conclusion;
- remote KMS/secret product selection.

## 2. Sequence and scope

The current sequence remains conceptually:

`Track P account decisions -> S2 account/device/session gate -> Deployment Portability Foundation -> normal V2.0 local qualification / Live pilot gates`

The portability foundation is **not** a remote-hosting go-live gate and does not change OD-V2-02.

A future cloud sequence, activated only by a later Owner decision, is conceptually:

`qualified LOCAL_PC product -> cloud go-live design -> REMOTE_HOST adapters/provisioning -> hosted/privacy/network/security qualification -> target-host requalification -> explicit production approval`

## 3. Phase 6 documentation impact — current V2.0

Phase 6 remains local-first and DISARMED.

Add only portability-aware architecture constraints:

- broker/order/risk domain remains host-neutral;
- path, secret, storage, clock, host lifecycle and alert mechanisms are consumed through ports/adapters;
- local Windows/DPAPI/CNG implementation details remain at the adapter edge;
- headless engine/API seam is authenticated and versioned;
- localhost/local bind is the default V2.0 exposure;
- deployment-profile selection cannot alter `RiskGateV2`, order lifecycle or BUY-only semantics;
- future migration/cutover contract is documented without implementing remote hosting.

### Phase 6 unchanged safety conditions

- Live mutation remains unreachable while DISARMED.
- `RiskGateV2` remains sole executable-order authority.
- central Account Authority has no broker mutation authority.
- options remain BUY-only.
- foreign/ambiguous activity fails closed and triggers reconciliation.
- broker-resident protective orders remain mandatory where supported under OD-V2-08.
- restart/reconnect never auto-arms.

## 4. Host migration / cutover qualification contract

The portability foundation must document a future cutover that uses:

1. source `HALT_ENTRIES` / safe shutdown preparation;
2. pending-order handling under existing kill-switch/order-lifecycle rules;
3. verified final source reconciliation/audit state;
4. verified `AlgoFortisBackup/v1` backup;
5. old host made ineligible before target host eligibility;
6. target restore using the target profile's adapters;
7. re-entry of non-exported secrets/device material where required;
8. target starts `RECOVERY`;
9. broker reconciliation;
10. target-host golden regression and applicable failure-injection re-run;
11. explicit manual resume/arming.

No silent live-state transfer or auto-arm is permitted.

## 5. Target-host qualification rule

A deployment profile/host is not qualified merely because the same binary starts successfully.

Before trading eligibility on a materially different target host/profile, evidence must re-run at minimum:

- deterministic/golden regression fingerprints applicable to the engine;
- restart/recovery cases;
- reconciliation cases;
- `INV-15` no-auto-arm;
- same-account exclusivity/cutover case;
- applicable failure-injection catalogue;
- selected adapter secret/audit/redaction tests;
- any host-specific performance/clock evidence required by the then-current policy.

Exact production thresholds remain evidence-driven and are not invented here.

## 6. OD-V2-05 portability consequence

`LOCAL_PC` and future `REMOTE_HOST` must never be simultaneously eligible for new entries on the same broker account.

If overlap/ambiguity is detected during a future cutover:

- halt new entries;
- preserve protective exits;
- produce auditable evidence;
- reconcile broker truth;
- require the manual recovery/resume path.

A central coordination record may assist but never replaces broker truth or RiskGate/order authority.

## 7. OD-V2-20 / OD-V2-24 portability consequence

### OD-V2-20

The update/no-auto-arm semantics are profile-independent. V2.0 applies them to `LOCAL_PC`; any future `REMOTE_HOST` adapter must preserve the same safe-window/recovery contract when activated.

### OD-V2-24

OD-V2-24 remains frozen for the current Windows `LOCAL_PC` profile, including its sleep/resume/clock/recovery rules.

Future `REMOTE_HOST` host-specific lifecycle rules are a cloud go-live design item. They must preserve the invariant that host uncertainty -> recovery/reconciliation/manual resume, but they are not current V2.0 implementation scope.

## 8. Cloud go-live triggers — deferred

The following do **not** belong to current V2.0 portability implementation/qualification. They activate only when a future Owner decision approves cloud go-live:

### Mobile/push

- mobile client;
- native vs PWA decision;
- push transport;
- redacted push default / authenticated in-app detail policy.

### Hosted-data privacy

- hosted trade/position/runtime data map;
- cloud-provider processor/service-provider analysis;
- OD-V2-25 hosted-data re-review;
- hosted notice/consent/legal-review update.

### OD-V2-09 hosted networking/regulatory verification

- static-IP requirement;
- hosted-engine broker registration/approval;
- then-current SEBI/exchange/broker hosted-algo requirements.

### Internet-facing API security

- network exposure design;
- remote ingress/auth gateway design;
- external/independent security testing of the internet-facing engine API.

V2.0's authenticated localhost/local-machine API does not trigger this external internet-facing assessment.

## 9. Phase 9 correction

No hosted-data/mobile product scope is added to current Phase 9 merely because OD-V2-27 exists.

Phase 9 keeps its existing V2.0 product/privacy obligations, including the original OD-V2-25 central-account-plane review.

Hosted-data/mobile/privacy additions are activated only by a future cloud go-live decision and are documented as deferred triggers in `docs/v2/phase9/HOSTED_DATA_PRIVACY_AMENDMENT_2026-09-28.md`.

## 10. Security qualification correction

Current V2.0 security qualification must cover the authenticated local engine API and prove its localhost/local-machine default exposure and no RiskGate bypass.

An **external/independent security test of an internet-facing engine API is not a current V2.0 requirement** because no internet-facing engine API is authorized by this freeze.

That assessment becomes mandatory before a future cloud go-live exposes `REMOTE_HOST` over the internet.

## 11. Documentation-only boundary

This amendment is documentation-only.

It does not:

- enable remote hosting;
- expose an API publicly;
- add mobile/push;
- change runtime code;
- change workflows/CI;
- change application configuration;
- enable broker mutation;
- change current Live state.

Implementation planning/coding starts only after separate Owner review/approval.
