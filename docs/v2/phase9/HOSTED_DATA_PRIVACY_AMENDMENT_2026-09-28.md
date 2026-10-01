# AlgoFortis V2 Phase 9 — Cloud Go-Live Privacy Trigger

**Date:** 2026-09-28  
**Status:** DEFERRED TRIGGER / DOCUMENTATION CORRECTION  
**Phase:** Phase 9 — Product & Operations  
**Decision impact:** OD-V2-25 hosted-data re-review is **not activated for V2.0 local-first scope**  
**Safety invariant:** This document does not authorize Live trading; Live remains `READ_ONLY / DISARMED`.

> **Correction note:** The earlier version of this file incorrectly treated hosted trade/position/runtime data as current V2 scope. That is superseded. OD-V2-02 remains local-first for V2.0, so hosted-data privacy re-review is a future cloud go-live trigger.

## 1. V2.0 privacy scope remains local-first

For V2.0:

- trading engine remains local;
- broker credentials remain local;
- trade logs/live positions/trading runtime state remain local under the existing architecture;
- the central account plane remains limited to its already-approved account/device/session/entitlement/security data and permitted non-sensitive settings.

Therefore the prior hosted-engine expansion does not change the current V2.0 Phase-9 data model.

## 2. OD-V2-25 base status

OD-V2-25 returns to its original V2.0 question:

> Owner obligations for identity data held in the central plane: consent, retention, deletion, breach handling.

Its existing Phase-9 status remains OPEN until resolved through the normal Product & Operations/legal-review path.

This correction does **not** mark OD-V2-25 as currently re-reviewed for hosted trade/position/runtime data.

## 3. Future hosted-data re-review trigger

A new hosted-data OD-V2-25 re-review is triggered only when the Owner later approves `REMOTE_HOST` for production/cloud go-live.

At that time the actual selected hosted architecture must be reviewed for:

- hosted trade/position/order/runtime/audit data classes;
- selected provider/region/data flow;
- processor/service-provider/subprocessor treatment under the then-current applicable legal model;
- notice/consent updates;
- retention/deletion/access/correction/erasure/grievance/nomination handling as applicable;
- incident/breach responsibilities;
- backup/restore and hosted-data deletion behavior;
- dated qualified legal review using the actual production architecture.

No provider, region, retention number, legal conclusion, or deadline is selected now.

## 4. No false compliance claim

The standing rule remains:

- technical tests can provide engineering evidence;
- green CI/security tests do not prove legal compliance;
- a future hosted-data legal conclusion requires the dated qualified review applicable to the actual go-live architecture.

This rule is retained as a future cloud go-live requirement, not a statement that V2.0 currently hosts trading data.

## 5. Mobile / push — future cloud go-live trigger

Mobile/push is not added to current V2.0 Phase-9 scope by OD-V2-27.

When a future cloud go-live is approved, product/privacy design must then decide and qualify:

- whether the mobile client is native or PWA;
- mobile authentication/session model against the remote engine;
- push transport/provider;
- default redacted push payload behavior;
- detailed in-app trading information only after authenticated access;
- external-channel detailed data only under explicit opt-in if that policy is retained/frozen for the final design.

Until that trigger, current OD-V2-19 alert behavior remains the V2.0 authority.

## 6. Cloud provider / remote secret custody — future trigger

This file does not select a cloud provider, KMS, remote secret store, region, residency model, or per-instance cost.

Those belong to future `REMOTE_HOST` cloud go-live design and must preserve:

- no broker credential centralization in the central account DB;
- secret redaction from logs/support artifacts/backups as governed by the final remote design;
- least-privilege secret access;
- fail-closed behavior on secret-store uncertainty.

## 7. OD-V2-09 hosted questions — future trigger

Hosted static-IP/broker-registration/current SEBI-exchange-broker questions are not current V2.0 Phase-9 scope.

They become a dated OD-V2-09 cloud go-live verification only when the Owner moves `REMOTE_HOST` toward production.

No answer is invented by this document.

## 8. Internet-facing API security test — future trigger

V2.0's headless engine API is authenticated and localhost/local-machine bound by default under the corrected portability design.

An external/independent security assessment specifically for an internet-facing engine API is therefore not a current Phase-9/V2.0 requirement.

Before future cloud go-live exposes the engine API over the internet, that assessment becomes mandatory against the actual final network/auth/API architecture.

## 9. Phase-9 current scope correction

Current V2.0 Phase 9 keeps its existing Product & Operations obligations only.

This file adds no current requirement for:

- hosted trade-state processing;
- cloud processor contracts for trading data;
- mobile/push;
- remote-host data-residency design;
- public engine API;
- remote hosted consent UI.

Those are deferred cloud go-live triggers.

## 10. Documentation-only boundary

No runtime, database, workflow, cloud resource, configuration, consent UI, retention job, notification transport, or production policy is changed by this file.

Implementation planning/coding requires separate Owner approval after review.
