# AlgoFortis V2 Phase 6 — Remote Engine Deployment & Secret-Custody Amendment

**Date:** 2026-09-28  
**Status:** OWNER-FROZEN DESIGN AMENDMENT — NO IMPLEMENTATION AUTHORIZATION  
**Phase:** Phase 6 — Live Execution V2 (still `READ_ONLY / DISARMED`)  
**Authority:** OD-V2-02 amendment + OD-V2-27 in `docs/v2/REMOTE_SINGLE_TENANT_ENGINE_AUTH_MOBILE_OWNER_DECISION_FREEZE.md`

## 1. Purpose

Phase 6 must now design/qualify the broker/execution boundary for a user-dedicated remote single-tenant engine in addition to the supported local execution placement.

This document changes Phase-6 documentation only. It does not add a deployment, broker mutation path, workflow, secret, cloud resource, or production configuration.

## 2. Deployment boundary

Permitted execution placements:

1. supported local execution host; or
2. user's isolated remote engine instance.

Remote-hosted execution is **single tenant**:

- one user = one isolated engine instance;
- no shared multi-user trading-engine state/process;
- central Account Authority remains separate;
- authenticated mobile/web/desktop clients call the owning user's engine API;
- no client or central service becomes order authority.

## 3. Secret custody

For the remote engine path:

- broker credentials/tokens are stored only in that user's isolated engine-side encrypted secret store;
- encryption keys use KMS-backed custody;
- exact provider/KMS product remains OPEN;
- credentials are never copied to the central account database for trading use;
- raw credentials are never exposed back through normal UI/API responses;
- instance role/identity must use least privilege to retrieve/decrypt only that user's engine secrets;
- secret access/rotation/failure is auditable;
- logs, crash artifacts, support bundles, telemetry, and backups must preserve existing secret-redaction invariants;
- KMS/secret-store uncertainty fails closed for any operation needing the unavailable credential.

## 4. OD-V2-05 exclusivity amendment

The exclusivity invariant applies across local and remote engine placements for the same broker account.

If broker truth or execution evidence indicates both a local engine and a remote engine are attempting/claiming eligible activity on the same account:

1. halt new entries;
2. raise auditable alert/evidence;
3. reconcile against broker truth;
4. do not auto-adopt ambiguous/foreign activity;
5. require the qualified manual recovery/resume path before entries can resume.

A cloud account record may support coordination/visibility but cannot be the sole safety authority and cannot place/cancel/modify broker orders.

## 5. OD-V2-08 hosted implication

Broker-resident protective orders are more important under remote hosting because host or network failure can make the engine temporarily unreachable.

Where the broker/API supports the required resident protection, the Live path must not substitute host-only protection as equivalent.

If required broker-resident protection is unsupported/unknown, the affected Live path remains DISARMED until a separate degraded policy is documented, qualified, and Owner-approved.

## 6. Recovery semantics

The following never auto-arm or auto-resume a safety-halted engine:

- instance restart;
- process crash/watchdog restart;
- host replacement;
- update/migration restart;
- broker reconnect;
- client reconnect;
- central account service recovery.

Execution uncertainty enters `RECOVERY` (or the corresponding frozen fail-closed state), reconciles broker truth, reaches the qualified ready-for-resume state, and then requires manual resume where `INV-15`/recovery policy requires it.

## 7. Authenticated engine API boundary

The remote engine API must be designed so that:

- unauthenticated requests cannot access engine/trading state;
- authenticated clients are scoped to their owning user/instance;
- sensitive actions are authorized and audited;
- replay/idempotency protections apply where relevant;
- password-only session assurance restrictions from the S2/Auth amendment are enforced for sensitive risk-increasing mutations;
- risk-reducing Pause/Halt/Exit actions do not depend on an extra step-up ceremony for an otherwise authorized authenticated user;
- no API call bypasses `RiskGateV2` or directly constructs `ApprovedOrder`;
- central Account Authority has no broker mutation endpoint/authority.

## 8. Mobile/web client boundary

Mobile/web/desktop are clients, not trading engines.

They may request authorized operations from the user's dedicated engine, but:

- trading logic/order authority stays in the execution instance;
- Live ARM remains gated and currently unavailable while Live is DISARMED;
- push payloads are redacted by default;
- detailed trading data is authenticated-app content by default.

Native vs PWA remains OPEN.

## 9. OD-V2-09 remains dated/open verification work

This amendment does not decide:

- whether a static IP is currently required;
- how a selected broker registers/approves a hosted engine;
- current SEBI/exchange/broker requirements;
- provider/region/network topology.

Those questions remain subject to the dated OD-V2-09 verification before the relevant production gate.

## 10. Phase-6 qualification addition

Before the hosted execution path can be considered for Live pilot, evidence must include:

- single-tenant instance isolation;
- cross-user/cross-instance denial;
- central account service cannot mutate broker state;
- broker credentials absent from central DB;
- instance secret-store/KMS fail-closed behavior;
- local-vs-remote same-account exclusivity halt/reconcile behavior;
- remote restart/reconnect/update never auto-arms;
- broker-resident protection behavior;
- external/independent security test of the internet-facing engine API.

Exact production numeric thresholds, cloud provider, instance size, and external test vendor remain OPEN.

## 11. Standing constraints

- Live remains `READ_ONLY / DISARMED`.
- `RiskGateV2` remains sole executable-order authority.
- Options remain BUY-only.
- Fail closed on uncertainty.
- No runtime/code/config/workflow change is authorized by this document.
