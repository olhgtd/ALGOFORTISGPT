# AlgoFortis V2 Phase 9 — Hosted Data & Privacy Amendment

**Date:** 2026-09-28  
**Status:** REQUIRED RE-REVIEW / DOCUMENTATION AMENDMENT  
**Phase:** Phase 9 — Product & Operations  
**Decision impact:** OD-V2-25  
**Safety invariant:** This document does not authorize Live trading; Live remains `READ_ONLY / DISARMED`.

## 1. Why OD-V2-25 must be re-reviewed

The previous privacy/data-protection framing primarily assumed a central account plane holding identity/device/session/entitlement data while trading state remained local.

OD-V2-02/27 now allows the user's trading engine to run on a dedicated cloud instance. That can place trade/position/runtime data with a cloud hosting provider and changes the hosted-data processing model.

Therefore OD-V2-25 remains OPEN but is now explicitly marked **RE-REVIEW REQUIRED for remote single-tenant hosting**.

## 2. Hosted data boundary

The future Phase-9 data-flow inventory must distinguish at least:

### Central Account Authority
May hold the approved identity/account/device/session/entitlement/security data and permitted non-sensitive settings.

It has no trading authority and must not become the repository for broker credentials merely because remote hosting exists.

### Dedicated Engine Instance
May hold execution/runtime data required by the approved engine design, including trade/position/order/reconciliation/audit state and the instance-side encrypted broker secret store.

One user = one isolated engine instance.

### Client surfaces
Desktop/web/mobile receive only data required for the authenticated user experience and according to notification/redaction policy.

### External notification channels
Push is redacted by default. Detailed Telegram/email content is explicit opt-in only.

## 3. Cloud provider role

The selected cloud hosting provider must be assessed as a data processor/service provider or equivalent role under the final applicable legal model because hosted engine data may be processed/stored on its infrastructure.

This document does not select:

- a provider;
- region;
- contractual terms;
- data-residency conclusion;
- retention period;
- legal basis/conclusion.

Those require the later provider choice and dated qualified review.

## 4. Notice and consent update

Before production hosted-data use, Phase 9 must update/review user-facing notice/consent materials so they accurately describe:

- dedicated cloud engine hosting;
- categories of hosted data;
- purpose of processing;
- relevant processor/service-provider involvement;
- external notification behavior and opt-in detail sharing;
- retention/deletion handling once legally and operationally frozen;
- user rights/request channels applicable to the final legal model.

Consent/notice version must be recorded/auditable where the final product/legal design requires it.

## 5. User privacy request surface

The product/privacy design must preserve an explicit path for applicable requests concerning:

- access;
- correction;
- erasure/deletion;
- data export where offered/required;
- grievance;
- nomination;
- account deletion;
- explanation of any legally/safety-required retention that prevents immediate deletion.

No production response deadlines or retention durations are guessed in this amendment.

## 6. Qualified legal review gate

A **dated qualified legal review** of the then-current hosted architecture and applicable current legal/regulatory requirements is mandatory before the hosted production / Live pilot path can be approved.

The review must use the actual selected provider, data flow, region, notice/consent design, retention design, security controls, and current applicable law/rules available at that date.

Historical assumptions are insufficient.

## 7. No false compliance claim

AlgoFortis documentation, CI, release evidence, dashboards, or gate reports must not state or imply:

> tests green = legally compliant

Technical security/privacy tests can provide engineering evidence. They do not substitute for the required dated qualified legal review.

Likewise, this documentation amendment is not a legal conclusion.

## 8. Security/privacy engineering inputs for later implementation

Phase 9 design/qualification should include, without selecting production numbers here:

- hosted-data inventory and flow diagram;
- minimization by data class;
- encryption in transit/at rest;
- instance isolation evidence;
- KMS-backed broker-secret custody on the user instance;
- central DB prohibition for broker credentials;
- access/audit controls;
- redaction in logs/support bundles/notifications;
- backup/restore data-class handling;
- deletion/retention mechanics once policy is legally frozen;
- incident/breach runbook inputs;
- provider/subprocessor documentation needed for the qualified review.

## 9. Open items

Remain OPEN and must not be inferred by this spec:

- cloud provider;
- region/data residency choice;
- provider contract/subprocessor list;
- retention periods;
- per-instance cost;
- production legal conclusions;
- current SEBI/exchange/broker hosted-engine requirements (OD-V2-09 dated verification).

## 10. Documentation-only boundary

No runtime, database, workflow, cloud resource, configuration, consent UI, retention job, or production policy is changed by this file.

Implementation planning/coding requires separate Owner approval after review.
