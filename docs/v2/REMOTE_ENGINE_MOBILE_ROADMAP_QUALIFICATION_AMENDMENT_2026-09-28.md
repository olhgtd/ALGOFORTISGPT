# AlgoFortis V2 — Remote Engine / Mobile Roadmap & Qualification Amendment

**Date:** 2026-09-28  
**Status:** OWNER-FROZEN DOCUMENTATION AMENDMENT  
**Amends:** `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md` and `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`  
**Authority:** `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`  
**Safety invariant:** Live remains `READ_ONLY / DISARMED`; this amendment schedules design/qualification only.

## 1. Canonical roadmap insertion

Add the following Track-P item **after S2 account/device/session gating and before any Live pilot authorization**:

### Track P — Remote Engine Hosting + Mobile Client

**Goal:** qualify the user-dedicated remote execution placement and authenticated mobile/web client path without turning the central account service into trading authority.

**Required design deliverables:**

- dedicated single-tenant execution-instance contract (`one user = one isolated engine instance`);
- authenticated, versioned client-to-engine API contract;
- remote engine provisioning/isolation design;
- KMS-backed instance-side broker-secret custody design;
- local-versus-remote broker-account exclusivity design under OD-V2-05;
- restart/crash/update/reconnect -> `RECOVERY` / reconciliation / manual-resume semantics;
- mobile client security boundary and redacted push-notification policy;
- hosted-data privacy/notice update;
- external/independent security assessment scope for the internet-facing engine API.

**Explicit non-goals of this documentation amendment:**

- choosing cloud provider/region;
- choosing instance size/cost;
- choosing native versus PWA;
- enabling Live;
- adding runtime/workflow/configuration;
- choosing current static-IP/broker-registration/regulatory answers without OD-V2-09 dated verification.

## 2. Sync/gate placement

The existing S2 remains the account/device/session prerequisite.

The new sequence is conceptually:

`Track P account decisions -> S2 account/device/session gate -> Remote Engine Hosting + Mobile Client qualification -> Live pilot gate`

This does not require changing the frozen core order-authority path.

Remote hosting/mobile qualification is a **new prerequisite for using those production paths**, not permission to enable Live.

## 3. Phase 6 documentation amendment

Phase 6 — Live Execution V2 (still DISARMED) gains documentation/design scope for:

- remote-engine deployment boundary;
- dedicated-instance isolation;
- remote broker-session lifecycle;
- KMS-backed secret custody on the user's isolated instance;
- local/remote execution exclusivity for the same broker account;
- remote host restart/crash/update recovery behavior;
- authenticated engine API boundary needed by web/mobile clients;
- current broker/static-IP/registration applicability as an OD-V2-09 dated verification item, not an assumption.

### Phase 6 unchanged safety conditions

- Live mutation remains unreachable while DISARMED.
- `RiskGateV2` remains sole executable-order authority.
- central Account Authority has no broker mutation authority.
- options remain BUY-only.
- foreign/ambiguous activity fails closed and triggers reconciliation.
- broker-resident protective orders remain mandatory where supported under OD-V2-08.
- restart/reconnect never auto-arms.

## 4. Phase 9 documentation amendment

Phase 9 — Product & Operations gains hosted-data/product scope for:

- hosted engine privacy notice/consent changes;
- cloud-provider processor/service-provider role assessment under the final legal model;
- hosted trade/position/runtime data inventory and data-flow map;
- retention/deletion/access/correction/erasure/grievance/nomination handling for hosted data as applicable;
- redacted-by-default external notification policy;
- authenticated mobile in-app detail policy;
- OD-V2-25 dated qualified legal re-review evidence.

Phase 9/G9 technical completion must not be described as legal compliance merely because tests are green.

## 5. Security qualification amendment

The Security Verification section of the Test & Release Qualification Plan gains a required row/concept:

### Internet-facing Engine API

Before the Live pilot gate for remote hosting, qualification must include an **external or independent security test** of the internet-facing dedicated-engine API.

Minimum assessment scope includes:

- authentication/session enforcement;
- authorization and user/instance isolation;
- replay/idempotency abuse on sensitive endpoints;
- rate limiting / credential-stuffing / brute-force resistance where applicable;
- injection/input-validation classes applicable to the exposed API;
- SSRF/request-pivoting risk where applicable;
- secret-custody and secret-exposure boundaries;
- logs/error responses/support artifacts for sensitive-data leakage;
- proof that API/client access cannot bypass `RiskGateV2` or directly mint an executable order;
- proof that central account infrastructure cannot mutate broker orders;
- recovery behavior under API/control-plane disruption.

The exact test provider, tooling, engagement format, severity thresholds, and production numerical limits remain to be selected by the later qualification plan. They are not guessed here.

## 6. Failure-injection / resilience additions

Later qualification must include at minimum:

- remote engine process restart with no auto-arm;
- remote instance reboot/replacement -> recovery/reconciliation/manual resume;
- client-to-engine network loss while broker-resident protective orders remain the primary host-independent protection where supported;
- remote and local engine activity detected for the same broker account -> halt new entries + reconcile;
- central account authority unavailable while already-running execution safety remains fail-closed and protective behavior continues according to the qualified execution-plane design;
- notification delivery degradation without weakening trading safety;
- remote secret-store/KMS access failure -> fail closed for operations requiring the unavailable secret, never fallback to plaintext/central DB.

## 7. OD-V2-20 application to remote engine

Signed/versioned update and safe-window rules apply to remote engine instances too:

- no update/restart/migration while ACTIVE or while open exposure makes the transition unsafe;
- missing/invalid safe-window policy defers change;
- update/restart never auto-arms;
- post-update/restart execution state requires recovery/reconciliation/manual resume under the frozen safety model.

No cloud maintenance window or schedule is invented by this amendment.

## 8. OD-V2-24 application to remote engine

Local Windows sleep/hibernate requirements do not apply to a server host that has no desktop sleep lifecycle.

The invariant that **host uncertainty cannot silently resume entries** does apply:

- restart/crash/watchdog/instance replacement -> recovery;
- reconcile before readiness;
- manual resume after safety recovery;
- never auto-arm.

Cloud SLA, availability target, hardware profile, and sizing remain OPEN.

## 9. Mobile client roadmap scope

Mobile is not deferred to V2.5.

The product track must support a secure authenticated mobile client capable of the approved user-side operations, subject to S2 and execution API authorization.

Notification default:

`Action required — AlgoFortis kholo`

Detailed trade/position/order/P&L content is default in authenticated app only. Detailed Telegram/email payloads require explicit opt-in.

Native vs PWA remains OPEN and must not be implied by roadmap wording.

## 10. Exit condition for this amendment

This amendment is documentation-only. It is satisfied when the canonical decision/roadmap/security documentation consistently records the new architecture and open questions without any runtime, workflow, or configuration mutation.

Implementation planning/coding starts only after separate Owner review/approval.
