# AlgoFortis V2 — Phase 9 Product & Operations Design

**Date:** 2026-09-27  
**Status:** APPROVED DESIGN — implementation not started  
**Owner direction:** Approach A — safety/privacy spine first, dashboards/UI last  
**Entry decision:** `docs/v2/phase9/PHASE9_DPDP_DECISION_FREEZE.md` (OD-V2-25)  
**Safety state:** Live remains `READ_ONLY / DISARMED`

## 1. Purpose and success criteria

Phase 9 makes AlgoFortis operable as a product without creating any new trading authority. The phase adds privacy/data-governance capability, operational observability, notification health, runbooks, backup/restore/rollback drills, incident handling, disclosures/consent flows, and read-only owner/user dashboards.

Success means:

- privacy-sensitive operations are governed by versioned policy and fail closed when policy/evidence is missing;
- existing security, audit, incident and alert authorities are reused rather than duplicated;
- product operations cannot mint `ApprovedOrder`, arm Live, mutate broker state, bypass `RiskGateV2`, weaken kill-switch behavior, or turn cloud/account/AI services into trading authority;
- local trading safety continues during privacy/account/notification service failures;
- G9 software qualification and dated legal/compliance review remain separate evidence gates;
- no claim of legal compliance is inferred merely from green software tests.

## 2. Architectural approach

Phase 9 follows the same established spine-first discipline used earlier in V2. The system is decomposed into small boundaries with explicit contracts:

1. Privacy Policy Spine
2. Versioned Notice + Consent
3. Data Principal Rights Workflow
4. Retention + Deletion
5. Privacy Incident Bridge
6. Observability + Notification Health
7. Runbooks + Backup/Restore/Rollback Drills
8. Owner/User Read Models and Dashboards
9. G9 Evidence + Qualification

A single large ProductOps module is explicitly rejected. UI-first implementation is also rejected because it would force later policy/audit retrofits.

## 3. Privacy Policy Spine

A versioned `PrivacyPolicyRegistry` is the central policy authority for privacy-sensitive product operations. Every centrally handled data class must resolve to an explicit policy before storage, export, processor use, retention action, or privacy workflow execution.

Each policy binds at least:

- stable policy ID and immutable version;
- data class;
- purpose;
- permitted operations;
- storage boundary;
- retention policy reference;
- processor/recipient scope;
- transfer/egress requirements;
- deletion/anonymisation behavior;
- audit requirement;
- effective/review metadata.

Initial centrally permitted classes are limited to account identity, device/security metadata, session/security metadata, entitlement, consent evidence, privacy-request evidence, support/privacy workflow metadata, and explicitly approved non-sensitive settings.

Broker credentials/tokens, device private keys, strategy content/configuration, unrestricted/raw trade logs, live positions, balances and other trading-sensitive content remain outside the central privacy data set under OD-V2-25 unless a later dated Owner Decision changes that boundary.

Unknown data class, missing policy, stale policy, or ambiguous policy applicability fails closed for the privacy-sensitive operation.

## 4. Versioned Notice + Consent

Notice and consent are immutable versioned policies, not mutable text blobs.

A `PrivacyNoticePolicy` / `ConsentPolicy` binds at least:

- stable policy ID;
- immutable semantic version;
- notice/document fingerprint;
- locale/language;
- covered purposes;
- covered data classes;
- effective date;
- withdrawal/re-consent behavior;
- legal/policy review reference.

A `ConsentRecord` records which principal acted against which exact notice/consent policy version and fingerprint, at what time, and what action was taken. Existing records are append-only historical evidence; updating notice wording never rewrites old consent context.

Purpose expansion is never silent. If a new purpose requires new consent or notice under the then-current policy/legal review, a new policy version is required.

No production consent interpretation or lawful-basis assumption is hard-coded. Exact applicability remains a dated legal-review input.

## 5. Data Principal Rights Workflow

Rights handling is a stateful, audited workflow rather than disconnected endpoints.

Conceptual lifecycle:

`RECEIVED -> IDENTITY_CHECK -> ACCEPTED | REJECTED -> IN_PROGRESS -> COMPLETED`

Supported capability set, subject to then-current applicable law/policy:

- access / processing summary;
- correction, completion and updating;
- erasure/deletion;
- grievance redressal and escalation;
- nomination;
- status, reason and completion evidence.

### 5.1 Identity authority reuse

`IDENTITY_CHECK` **must reuse the existing S2 account/device/session authority** and its established authentication, device/session, recovery and audit semantics. Phase 9 must not create a separate identity-verification platform, independent password mechanism, parallel device proof, or disconnected principal registry.

Where a rights request requires stronger identity assurance than the current S2 session provides, Phase 9 asks the S2 authority for the appropriate existing step-up/recovery proof; it does not invent its own verifier.

### 5.2 Response timing

Statutory/policy response periods are versioned compliance policy, not hard-coded constants. Phase 9 builds the workflow capability now; exact production deadlines and legal wording are activated only from the dated G9 legal review.

## 6. Retention, Deletion and Erasure Priority

Retention is per data class and purpose. Production durations are not guessed.

Each `RetentionPolicy` binds:

- policy ID/version;
- retention trigger/start event;
- duration/rule;
- legal-hold condition;
- safety-retention condition where applicable;
- delete vs permitted anonymisation action;
- processor handling;
- backup propagation behavior;
- completion evidence.

Deletion flow is conceptually:

`request/policy trigger -> eligibility check -> primary deletion -> processor/backup propagation -> minimal tombstone -> audit evidence`

Tombstones must be minimal and must not recreate deleted personal payloads.

### 6.1 Explicit priority rule

When an erasure request conflicts with a valid legal hold or a narrowly scoped safety-retention requirement, **legal hold / safety-retention takes priority over immediate erasure** for the affected data only. The system must never silently refuse the request. It must record and return a reasoned, auditable outcome identifying the applicable policy/hold, the scope being retained, and the next review/release condition where available.

Retention of one required class never justifies retaining unrelated data. When the hold/safety-retention condition expires, the normal deletion policy resumes.

Privacy handling must not delete or corrupt local protective/reconciliation/recovery evidence required to keep an active or recovery trading-safety path safe. Privacy governance and trading safety remain separately authorized and audited.

## 7. Privacy Incident Bridge — Reuse Existing Incident/Audit/Alert Authorities

Phase 9 must **not** introduce a privacy-only incident bus, logging system, alert dispatcher, or audit ledger.

Privacy incidents extend the existing Phase-5/6 incident pattern:

`privacy detector/service -> FailureIncident -> typed privacy category -> existing audit path -> existing independent alert dispatcher -> incident lifecycle/evidence`

A typed category such as `PRIVACY_BREACH` may be added along with structured privacy metadata such as:

- affected data-class identifiers;
- affected-scope/count classification;
- detection time;
- containment/remediation state;
- notification-policy reference;
- regulator/user notification evidence references where applicable.

Raw personal data, secrets, unrestricted trade logs, broker credentials or raw account identifiers must not be copied into alert payloads merely to describe the incident.

Existing independent alert-channel semantics remain authoritative. Notification failure is auditable and must not weaken local trading safety.

## 8. OD-V2-16 AI/Cloud Egress + OD-V2-25 Privacy/Transfer Chain

OD-V2-16 and OD-V2-25 are jointly binding.

Cloud/AI egress path is conceptually:

`data classification -> OD-V2-16 allowlist/redaction -> licensing/provenance gate -> OD-V2-25 purpose/processor/transfer policy -> approved provider call`

OD-V2-16 approval alone never authorizes a personal/account-identifying data transfer. Redaction does not automatically make an otherwise restricted transfer lawful. Missing, stale or ambiguous processor/transfer evidence blocks the outbound operation.

Phase 9 does not replace the Phase-8 provider gateway; it adds the privacy/compliance authorization layer where personal/account data or processor/transfer obligations are implicated.

## 9. Observability and Notification Health

Phase 9 reuses existing structured audit/logging conventions rather than adding a new general logging authority.

Operational read models may include:

- unresolved incident counts/status;
- alert-channel delivery health;
- privacy-request backlog/state counts;
- missing/stale privacy policy status;
- backup freshness/evidence state;
- restore/rollback drill status;
- runbook exercise status;
- active policy versions.

Metrics/logs must exclude unnecessary personal data. Privacy/account/notification outages never become prerequisites for protective exits, reconciliation, local position monitoring, or recovery safety.

## 10. Backup, Restore and Rollback — Explicitly Split Boundaries

Phase 9 treats local-engine backup and central privacy-data backup as two separate concerns with separate evidence.

### 10.1 Local engine backup drill

The local-engine drill verifies the existing `AlgoFortisBackup/v1` contract and its already frozen local-first boundaries. It does not widen the central data set.

The drill must verify, as applicable to the existing contract:

- manifest/version integrity;
- expected local files/state coverage;
- exclusion of non-exportable device private keys;
- exclusion/handling rules for broker secrets according to the frozen backup contract;
- isolated restore target;
- restore verification without overwriting the active production/runtime state;
- deterministic evidence of PASS/FAIL.

### 10.2 Central privacy-data backup drill

A separate central-plane drill covers only approved central account/consent/privacy/support classes governed by the privacy registry. It must not ingest local strategy/trading state, broker credentials, local positions, unrestricted trade logs or other local-only data.

The drill must verify:

- approved data-class coverage only;
- encryption/access policy evidence through the existing platform authority;
- retention/expiry policy binding;
- deletion-propagation behavior;
- isolated restore target;
- restore integrity and audit evidence;
- no authority expansion into trading execution.

### 10.3 Rollback drill

Rollback tests configuration/schema/release recovery independently of Live enablement. Rollback must never auto-arm Live or silently overwrite active safety state.

## 11. Runbooks and Drill Evidence

Runbooks are versioned operational contracts, not documentation-only prose.

Required Phase-9 drills include:

- local `AlgoFortisBackup/v1` backup/restore drill;
- central privacy-data backup/restore drill;
- rollback drill;
- alert-channel failure drill;
- privacy-incident drill;
- missing/stale privacy-policy fail-closed drill;
- account/cloud outage operational drill.

Each drill emits at least:

`runbook_version + environment + start/end + step results + evidence fingerprint + PASS/FAIL`

No destructive auto-fix is allowed without explicit authority/policy/human action where required.

## 12. Dashboards — Read Models Last

Dashboards are built only after the underlying spine and operational evidence contracts are stable.

### 12.1 Owner dashboard

May expose read models for:

- system/operational health;
- alert health;
- unresolved incidents;
- privacy-workflow status;
- backup/restore status;
- runbook/drill status;
- active policy versions.

### 12.2 User dashboard

May expose read models for:

- current privacy notice/version;
- consent state;
- privacy-request status;
- grievance status;
- account/device/security state already authorized by S2.

The UI never talks directly to broker mutation or trading-state authorities and never bypasses policy/audit. User actions invoke service contracts; dashboards themselves are not business/trading authority.

## 13. Failure Semantics

Privacy-sensitive operation failures:

- missing/unknown data policy -> block;
- audit evidence failure -> block;
- missing processor/transfer approval -> block;
- stale/ambiguous legal/policy evidence -> block;
- unknown data class -> reject/quarantine according to policy.

This fail-closed privacy behavior does **not** mean shutting down local protective trading safety. Privacy/account/cloud/notification failures must not stop protective exits, reconciliation, local position monitoring or recovery safety.

## 14. Implementation Slices

Planned implementation order:

- **P9-01** ProductOps/privacy contracts + architecture firewall
- **P9-02** Versioned notice + consent evidence
- **P9-03** Data Principal rights workflow using S2 identity authority
- **P9-04** Retention/deletion/legal-hold/backup-propagation policy
- **P9-05** `FailureIncident` privacy extension + existing alert integration
- **P9-06** Observability + notification health read models
- **P9-07** Local and central backup/restore + rollback runbooks/drills
- **P9-08** Owner/user read-model dashboards
- **P9-09** G9 evidence + qualification harness

Each slice uses RED -> implementation -> focused local verification. A combined full regression/qualification run is deferred to the Phase-9 end per Owner direction, while no intermediate slice is represented as formally qualified without evidence.

## 15. G9 Exit Evidence

G9 requires both software/operational evidence and a separate dated legal/compliance review.

Software/operational evidence must prove at least:

- policy, consent, rights and retention paths behave fail closed;
- rights `IDENTITY_CHECK` is delegated to S2 rather than a new authority;
- valid legal-hold/safety-retention priority produces a reasoned/audited non-erasure outcome rather than silent refusal;
- privacy incidents reuse `FailureIncident`, existing audit and existing independent alert dispatch;
- local and central backup drills remain separate and respect their storage/data boundaries;
- restore and rollback drills succeed in isolated targets;
- required runbooks are exercised;
- dashboards remain read-model/service clients without trading authority;
- full regression is preserved;
- Live remains `READ_ONLY / DISARMED`.

The dated G9 legal/compliance review must independently confirm then-current DPDP applicability/effective provisions and any other relevant legal requirements. **Software tests PASS does not establish legal compliance, and legal review does not substitute for software qualification.**

## 16. Non-goals

Phase 9 does not add:

- a new authentication/identity platform;
- a new incident bus;
- a new audit ledger;
- a new general alert dispatcher;
- a new broker mutation path;
- a new `ApprovedOrder` authority;
- direct AI-to-order authority;
- Live enablement/auto-arm;
- guessed production retention periods, statutory SLAs or transfer rules;
- centralized broker secrets, strategy content, unrestricted trade logs, positions or balances;
- a claim that implementation alone proves DPDP compliance.

## 17. Safety Invariants

- `RiskGateV2` remains the sole `ApprovedOrder` mint authority.
- Live remains `READ_ONLY / DISARMED`.
- Phase 9 cannot directly place/modify/cancel broker orders or arm Live.
- Privacy/account/cloud outages cannot loosen trading safety.
- Missing privacy/compliance evidence fails closed for privacy-sensitive operations.
- G9 GREEN, when eventually achieved, does not by itself authorize real-money trading.
