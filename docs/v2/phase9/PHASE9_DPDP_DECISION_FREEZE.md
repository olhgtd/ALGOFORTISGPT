# AlgoFortis V2 — Phase 9 DPDP / Data-Protection Decision Freeze

**Date:** 2026-09-27  
**Decision:** OD-V2-25  
**Status:** **FROZEN — ARCHITECTURE-READY, NOT A LEGAL-COMPLIANCE CERTIFICATION**  
**Phase blocked/unblocked:** Phase 9 Product & Operations

## 1. Legal-status boundary

This decision is an engineering/governance freeze, not legal advice and not a claim that AlgoFortis is presently or finally compliant with the Digital Personal Data Protection Act, 2023 or Digital Personal Data Protection Rules, 2025.

The published DPDP commencement notifications use a staged rollout. As of 2026-09-27, several operational provisions relevant to ordinary Data Fiduciary duties and Data Principal rights are scheduled to commence later. Therefore:

- Phase 9 may build the required privacy/data-governance capabilities now;
- production behavior must be driven by versioned policy and current effective law, not hard-coded assumptions;
- a **dated DPDP applicability/compliance review by a qualified legal adviser is mandatory before G9 exit**;
- that review must confirm the then-current status of Data Fiduciary obligations, any Significant Data Fiduciary designation/applicability, Consent Manager requirements, breach-notification duties/timelines, Data Principal rights procedures, retention requirements, processor obligations, and transfer restrictions;
- any legal requirement that is missing, stale, ambiguous or unresolved for a production path fails closed for that privacy-sensitive operation.

## 2. Architecture direction

AlgoFortis V2.0 adopts **minimum-data, privacy-first, fail-closed** governance.

The central plane stores only data required for account, device, security/session, entitlement, support/privacy workflow and explicitly approved non-sensitive settings. Broker credentials/tokens, device private keys, strategy content/configuration, unrestricted/raw trade logs, live positions, balances and other trading-sensitive content remain outside the central privacy data set unless a later dated Owner Decision explicitly changes that boundary after legal/security review.

Collection, processing, sharing and retention are purpose-bound and versioned. New data classes are deny-by-default until their purpose, lawful basis/consent path where applicable, retention rule, access scope, processors/recipients and deletion behavior are explicitly registered.

## 3. Notice, consent and evidence

Where consent is the applicable processing basis, AlgoFortis must support:

- versioned privacy notices and consent text;
- timestamped evidence of notice/version shown and consent action;
- withdrawal/revocation flow where applicable;
- no dark-pattern or silent consent expansion;
- purpose changes requiring a new policy/notice decision rather than silent reuse;
- auditable evidence without logging secrets or unnecessary personal data.

No production legal basis or consent interpretation may be guessed in code. The exact applicability is a dated legal-review input.

## 4. Data Principal rights capability

Phase 9 must include an auditable rights-request workflow capable of supporting, subject to then-current applicable law:

- access / processing-summary requests, including sharing-recipient information where required;
- correction, completion and updating;
- erasure/deletion subject to lawful retention requirements;
- grievance redressal and escalation tracking;
- nomination of another individual for exercise of rights upon death/incapacity where applicable;
- request identity/authority verification without collecting unnecessary additional data;
- status, timestamps, decision reason and completion evidence for each request.

These capabilities are architecture requirements even where a particular statutory provision has a later commencement date. Activation/SLA/legal wording is controlled by versioned policy after dated legal review.

## 5. Retention, deletion and backups

Retention is per data class and purpose. Production durations are **not guessed**.

Each retained class must have:

- policy ID/version;
- purpose;
- retention trigger/start event;
- retention duration or legal-hold condition;
- deletion/anonymisation action;
- processor/backup handling;
- audit evidence.

Account deletion does not silently erase data that must lawfully be retained, and lawful retention does not justify retaining unrelated data. Backups must have bounded lifecycle and documented deletion propagation. Tombstones/audit records must be minimal and must not recreate deleted payloads.

Published DPDP rules/timelines are engineering inputs, but the exact production retention numbers are re-verified against law effective at G9 exit.

## 6. Breach / incident handling

Phase 9 must provide a privacy incident workflow that can record detection, affected data classes, scope, containment, remediation, affected-user communications, regulator/Board communications where applicable, timestamps and evidence.

The system must support the then-current statutory notification sequence/timelines, but those timelines are versioned compliance policy rather than hard-coded product constants. A dated legal review before G9 exit confirms the exact applicable notification duties and deadlines.

## 7. OD-V2-16 AI/cloud link and transfer boundary

OD-V2-25 and OD-V2-16 are jointly binding.

OD-V2-16 remains the first technical gate for AI/provider egress: provider data classification, strict allowlists, redaction and licensing/provenance checks apply before any cloud AI call.

In addition, before any personal/account-identifying data could leave the local/central boundary for a cloud provider or processor, Phase 9 must require positive evidence that the transfer/processing is permitted under the then-current DPDP transfer framework and any other applicable higher-protection law, contractual/processor requirements and approved purpose/retention policy.

Redaction does not automatically make an otherwise restricted transfer lawful, and OD-V2-16 does not override DPDP or other applicable transfer restrictions. Missing/stale/ambiguous transfer-policy evidence blocks the outbound operation.

## 8. Significant Data Fiduciary / role classification

AlgoFortis does not self-declare that it is or is not a Significant Data Fiduciary. The architecture keeps seams for additional DPO/audit/DPIA/governance obligations if classification or notification requires them. A dated review before G9 exit must confirm current role/classification obligations.

## 9. Children / age-sensitive processing

This decision does not authorize collection of child personal data or create a child-user product flow. If future product eligibility includes users for whom child-specific DPDP obligations apply, that processing requires a separate dated design/legal review before enablement. Data minimization means age/date-of-birth is not collected merely to speculate about future use unless a defined eligibility/compliance purpose requires it.

## 10. Fail-closed invariants

- Unknown personal-data class -> reject/quarantine, not silently store/share.
- Missing purpose/retention policy -> reject privacy-sensitive write/export.
- Missing processor/transfer approval for cloud egress -> block egress.
- Privacy/audit evidence failure -> block the privacy-sensitive operation rather than fabricate success.
- Deletion request cannot delete protective trading safety state needed locally for an active/recovery safety path; privacy handling and trading safety remain separately governed and audited.
- Live remains `READ_ONLY / DISARMED`; this privacy decision grants no trading authority.

## 11. G9 legal-review gate

Before Phase 9 can exit G9, record a dated review of:

1. DPDP Act/Rules provisions actually in force on that date;
2. Data Fiduciary / possible Significant Data Fiduciary obligations;
3. Data Principal rights procedures and response periods;
4. breach notification recipients/timelines;
5. retention/deletion/log requirements;
6. Consent Manager/consent requirements where applicable;
7. processor/cloud contracts and current cross-border/transfer restrictions;
8. OD-V2-16 AI-provider redaction/egress policy against those rules;
9. any other Indian law imposing a higher protection or transfer restriction.

G9 may not claim legal compliance merely because software tests are green.

## 12. Controlling authority

This dated freeze is the controlling OD-V2-25 Phase-9 entry decision on `v2-phase9-product-ops-design`. If an older copy of `ALGOFORTIS_V2_OWNER_DECISIONS.md` on the stacked base still shows OD-V2-25 as OPEN, this record supersedes that OPEN label until the consolidated Owner Decision Register is synchronized without losing later branch-specific decisions.
