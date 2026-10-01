# Phase 9 Product & Operations Implementation Plan

**Goal:** Implement the approved Phase 9 Product & Operations safety/privacy spine without creating any new trading authority, while preserving S2 identity authority, Phase-5/6 incident/alert authority, `AlgoFortisBackup/v1`, and Live `READ_ONLY / DISARMED`.

**Architecture:** Phase 9 is a central/product-operations layer under `dashboard/backend/product_ops_v2/`, with narrow, immutable contracts and deny-by-default policy resolution. It reuses `dashboard/backend/account_v2/` for identity/session authority, `engine/paper/contracts_v2.py` + `engine/alerts/` for incidents/alerts, and `dashboard/backend/backup_service.py` for the existing local portable-backup contract. Dashboards consume read models only and do not become business or trading authority.

**Tech stack:** Python 3.13, dataclasses/Protocol-based domain contracts, existing audit/alert/account seams, pytest, React 19 + TypeScript 7 + Vite 8 for dashboards, repository-hosted GitHub Actions for final G9 qualification when Actions capacity is available.

**Design authority:**
- `docs/superpowers/specs/2026-09-27-phase9-product-operations-design.md`
- `docs/v2/phase9/PHASE9_DPDP_DECISION_FREEZE.md`

**Branching rule:** Implement on a new branch `v2-phase9-product-ops-impl` created from the approved design branch head. Keep design PR #19 docs-only. Do not mutate or merge Phase-6/7/8 branches as part of Phase 9.

**Qualification rule:** Per Owner direction, each slice gets focused RED -> GREEN development verification. The large combined full regression and hosted G9 qualification are deferred until Phase 9 end. Until exact-head qualification actually executes and passes, G9 remains **NOT QUALIFIED**. GitHub Actions pre-step failures or exhausted hosted minutes are infrastructure evidence, not code GREEN or RED.

**Safety invariants for every task:**
- `RiskGateV2` remains the sole `ApprovedOrder` mint authority.
- Phase 9 never imports broker mutation, Live ARM, order placement, kill-switch authority, or direct AI execution authority.
- Live remains `READ_ONLY / DISARMED`.
- Privacy/account/cloud/notification failures cannot weaken protective exits, reconciliation, local monitoring, or recovery safety.
- Missing/stale/ambiguous privacy policy evidence fails closed for the privacy-sensitive operation.
- No task may introduce a second auth platform, incident bus, audit ledger, general alert dispatcher, or guessed production legal/retention/SLA constants.

---

## Task 0 — Implementation Branch, Decision Register Sync, and Baseline Guard

**Purpose:** Start Phase 9 from the approved docs-only head and make the frozen OD-V2-25 visible in the consolidated register without changing runtime behavior.

**Files:**
- Modify: `ALGOFORTIS_V2_OWNER_DECISIONS.md`
- Create: `docs/v2/phase9/PHASE9_IMPLEMENTATION_BASELINE.md`
- No runtime code.

**Steps:**
1. Create `v2-phase9-product-ops-impl` from the exact approved design head.
2. Write a failing documentation/guard test in `tests_v1/test_phase9_owner_decision_guard.py` that requires:
   - OD-V2-25 status = FROZEN;
   - Phase-9 blocking matrix row = FROZEN 2026-09-27;
   - legal-review-before-G9-exit language present;
   - Live remains READ_ONLY/DISARMED.
3. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_owner_decision_guard.py -q
   ```
   Expected RED before the consolidated register is synchronized.
4. Update only the OD-V2-25 entry, decision log, version/date header, and Phase-9 blocking row. Preserve every later/parallel branch decision already present on the selected base; do not silently overwrite unrelated ODs.
5. Record exact base SHA and docs authorities in `PHASE9_IMPLEMENTATION_BASELINE.md`.
6. Re-run the focused test; expected GREEN.
7. Commit: `docs: synchronize Phase 9 owner decision gate`.

**Review focus:** No runtime/workflow changes; no loss of earlier frozen decisions.

---

## P9-01 — ProductOps Privacy Contracts, Policy Registry, and Architecture Firewall

**Purpose:** Establish one narrow policy spine before any consent, rights, retention, incident, or dashboard behavior exists.

**Create:**
- `dashboard/backend/product_ops_v2/__init__.py`
- `dashboard/backend/product_ops_v2/contracts.py`
- `dashboard/backend/product_ops_v2/privacy_policy.py`
- `dashboard/backend/product_ops_v2/repository.py`
- `build/tools/check_phase9_product_ops.py`
- `tests_v1/test_phase9_product_ops_contracts.py`
- `tests_v1/test_phase9_privacy_policy.py`
- `tests_v1/test_phase9_architecture_guard.py`

**Contracts to implement:**
- `PrivacyDataClass` with only approved central classes plus `UNKNOWN`.
- `PrivacyOperation`: STORE, READ, EXPORT, PROCESSOR_USE, RETAIN, DELETE, BACKUP, RESTORE.
- immutable `PrivacyPolicy` containing policy ID/version, data class, purpose, allowed operations, storage boundary, retention-policy ref, processor/recipient scope, transfer-policy ref, audit requirement, effective/review metadata.
- `PrivacyPolicyDecision` / rejection reason vocabulary.
- narrow `ProductOpsRepository(Protocol)` for consent/right/retention/incident-metadata/read-model evidence. Do not tie domain logic directly to SQLite/Postgres/network calls in this slice.

**TDD:**
1. Tests first for unknown class, missing policy, stale policy, ambiguous version, unlisted operation, unapproved recipient/processor, and missing transfer evidence.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_product_ops_contracts.py tests_v1/test_phase9_privacy_policy.py tests_v1/test_phase9_architecture_guard.py -q
   ```
   Expected RED because Phase-9 modules do not exist.
3. Implement minimal immutable contracts and `PrivacyPolicyRegistry.resolve(...)`.
4. Static checker must reject Phase-9 backend imports/references to:
   - broker adapters / broker mutation entry points;
   - Live ARM/auto-arm authority;
   - `ApprovedOrder(` or private RiskGate mint internals;
   - direct AI-to-order authority;
   - direct arbitrary network clients from pure policy modules;
   - hard-coded production retention/SLA/legal constants.
5. Explicit narrow exceptions later allowed only for S2 gate, Phase-5/6 incident/alert contracts, and existing backup service in the named integration modules.
6. Re-run focused tests and static checker:
   ```powershell
   python build/tools/check_phase9_product_ops.py
   ```
   Expected marker: `PHASE9_PRODUCT_OPS_STATIC_PASS`.
7. Commit: `feat: add Phase 9 product operations policy spine`.

**Critical regression:** Prove no privacy-sensitive side effect can occur before positive policy resolution.

---

## P9-02 — Immutable Versioned Notice and Consent Evidence

**Purpose:** Make notice/consent history reproducible and prevent silent purpose expansion.

**Create:**
- `dashboard/backend/product_ops_v2/consent.py`
- `tests_v1/test_phase9_consent_policy.py`

**Modify:**
- `dashboard/backend/product_ops_v2/contracts.py`
- `dashboard/backend/product_ops_v2/repository.py`

**Implement:**
- immutable `PrivacyNoticePolicy` and `ConsentPolicy` with stable policy ID, semantic version, content/document fingerprint, locale, purposes, data classes, effective date, withdrawal/re-consent policy, legal/policy-review reference.
- `ConsentAction`: ACKNOWLEDGE / GRANT / WITHDRAW only where applicable.
- append-only `ConsentRecord` binding user/principal ref to exact policy version + fingerprint + timestamp + action.
- audit-before-persist boundary; if required audit evidence cannot be written, the consent mutation does not report success.
- new purpose cannot inherit old consent silently.

**TDD:**
1. RED tests for:
   - same policy ID + same version + different fingerprint rejected;
   - rewriting historical consent rejected;
   - purpose expansion without new version rejected;
   - consent record missing exact notice fingerprint rejected;
   - audit failure blocks persistence;
   - withdrawal does not delete historical evidence.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_consent_policy.py -q
   ```
3. Implement minimal code, then GREEN.
4. Re-run P9-01 static guard as regression.
5. Commit: `feat: add immutable notice and consent evidence`.

---

## P9-03 — Data Principal Rights Workflow Reusing S2 Identity Authority

**Purpose:** Provide one audited rights workflow while making S2 the only identity/session authority.

**Existing authority to reuse:**
- `dashboard/backend/account_v2/contracts.py`
- `dashboard/backend/account_v2/gate.py` — `DeviceSessionGate.evaluate(...) -> DeviceSessionGateResult`
- `dashboard/backend/account_v2/evidence.py` for S2 evidence concepts.
- `dashboard/backend/account_v2/audit.py` for required security/audit semantics where applicable.

**Create:**
- `dashboard/backend/product_ops_v2/identity.py`
- `dashboard/backend/product_ops_v2/rights.py`
- `tests_v1/test_phase9_rights_identity.py`
- `tests_v1/test_phase9_rights_workflow.py`

**Modify:**
- `dashboard/backend/product_ops_v2/contracts.py`
- `dashboard/backend/product_ops_v2/repository.py`

**Implement:**
- rights types: ACCESS, CORRECTION_UPDATE, ERASURE, GRIEVANCE, NOMINATION.
- workflow states: RECEIVED, IDENTITY_CHECK, ACCEPTED, REJECTED, IN_PROGRESS, COMPLETED.
- `S2IdentityAuthorizer` wraps/injects the existing `DeviceSessionGate`; it does not implement passwords, WebAuthn, challenge generation, device proof, or its own user registry.
- request target `user_id` derives from the authenticated principal / S2-scoped result, never arbitrary caller input.
- where higher assurance is required, accept only injected S2-issued/verified step-up evidence; Phase 9 does not define a new credential format.
- response deadlines remain versioned policy data, never hard-coded statutory constants.

**TDD:**
1. RED tests for:
   - invalid/revoked/expired/authority-unavailable S2 result -> no rights mutation;
   - cross-user target request rejected;
   - caller cannot override principal user ID;
   - strong-verification-required path rejects missing/unverified S2 evidence;
   - state transition skipping is rejected;
   - audit failure blocks state-changing operation.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_rights_identity.py tests_v1/test_phase9_rights_workflow.py tests_v1/test_v2_s2_*.py -q
   ```
   If glob expansion differs on PowerShell, run the Phase-9 files plus the repository's existing focused S2 test filenames explicitly.
3. Implement minimal workflow and S2 adapter; GREEN.
4. Static guard must detect any Phase-9-defined password/WebAuthn/private-device-proof implementation.
5. Commit: `feat: add S2-scoped privacy rights workflow`.

**Critical regression:** No rights workflow can become a parallel auth platform.

---

## P9-04 — Retention, Deletion, Legal Hold, Safety Retention, and Backup Propagation Policy

**Purpose:** Make erasure deterministic and fail closed without deleting data under a valid hold or trading-safety retention requirement.

**Create:**
- `dashboard/backend/product_ops_v2/retention.py`
- `tests_v1/test_phase9_retention.py`
- `tests_v1/test_phase9_erasure_priority.py`

**Modify:**
- `dashboard/backend/product_ops_v2/contracts.py`
- `dashboard/backend/product_ops_v2/repository.py`

**Implement:**
- immutable `RetentionPolicy` with policy/version, trigger, duration/rule reference, legal-hold semantics, safety-retention semantics, delete/anonymise action, processor handling, backup propagation, evidence requirements.
- no default production duration.
- `ErasureDecision` that explicitly distinguishes DELETE_ALLOWED, RETAIN_LEGAL_HOLD, RETAIN_SAFETY, REJECT_POLICY_UNRESOLVED.
- legal hold / narrowly scoped safety retention wins over immediate erasure **only for affected classes**.
- unrelated eligible classes continue deletion.
- held request returns reason/policy ref/scope/review-release condition where available; silent refusal forbidden.
- minimal tombstone contains identifiers/fingerprints necessary for audit but cannot reconstruct deleted personal payload.

**TDD:**
1. RED tests for:
   - no retention policy -> no delete;
   - valid legal hold preserves affected class;
   - safety-retention preserves only required class;
   - unrelated class still deletes;
   - expired hold resumes deletion eligibility;
   - tombstone cannot contain original payload;
   - processor/backup deletion propagation failure is surfaced and audited, not reported as complete.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_retention.py tests_v1/test_phase9_erasure_priority.py -q
   ```
3. Implement and GREEN.
4. Commit: `feat: add fail-closed retention and erasure policy`.

**Critical regression:** Erasure must never corrupt active/recovery protective or reconciliation evidence needed for local trading safety.

---

## P9-05 — Privacy Incident Bridge via Existing FailureIncident + AlertDispatcher

**Purpose:** Add privacy incidents without creating a second incident or notification system.

**Existing seams to reuse:**
- `engine/paper/contracts_v2.py` — `FailureIncident`, `FailureSeverity`.
- `engine/alerts/contracts.py` — `AlertEnvelope`, severity/channel contracts.
- `engine/alerts/dispatcher.py` — independent channel dispatch + delivery evidence.
- `engine/persistence/paper_incident_store_v2.py` — append-only incident/evidence behavior where a compatible store is injected.

**Create:**
- `dashboard/backend/product_ops_v2/privacy_incidents.py`
- `tests_v1/test_phase9_privacy_incidents.py`

**Modify only if required by a proven contract gap:**
- `engine/paper/contracts_v2.py` may receive a backwards-compatible typed privacy failure vocabulary extension; do not replace `FailureIncident`.
- `engine/alerts/contracts.py` only if an additional non-sensitive title/category field is required; avoid schema churn if `failure_type` is sufficient.

**Implement:**
- `PrivacyIncidentBridge` creates/reuses `FailureIncident` with a typed failure value such as `PRIVACY_BREACH` and sanitized outcome/reason text.
- Phase-9-specific structured metadata is stored as a sanitized link/evidence record keyed by `incident_id`; raw PII is not copied into `FailureIncident` or `AlertEnvelope`.
- alerts are dispatched through existing `AlertDispatcher`; no second channel registry/dispatcher.
- alert body redaction rejects credentials, tokens, raw account identifiers, unrestricted trade logs, and personal payload.
- delivery failure is auditable but never weakens local trading safety.

**TDD:**
1. RED tests for:
   - bridge emits an existing `FailureIncident`, not a parallel incident class;
   - existing dispatcher receives independent channel attempts;
   - forbidden PII/secret fields cannot enter alert payload;
   - duplicate incident ID uses existing append-only/idempotency semantics;
   - audit/store failure does not fabricate successful incident evidence.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_privacy_incidents.py tests_v1/test_phase5_alert*.py -q
   ```
   Use the exact existing Phase-5 alert test filenames if wildcard behavior differs.
3. Implement and GREEN.
4. Re-run static architecture guard.
5. Commit: `feat: bridge privacy incidents into existing alert authority`.

**Critical regression:** No new privacy-only incident bus, alert dispatcher, or audit ledger.

---

## P9-06 — Operational Observability and Notification-Health Read Models

**Purpose:** Surface operational health without granting mutation authority or leaking personal data.

**Create:**
- `dashboard/backend/product_ops_v2/observability.py`
- `dashboard/backend/product_ops_v2/read_models.py`
- `tests_v1/test_phase9_observability.py`
- `tests_v1/test_phase9_read_models.py`

**Implement immutable read models for:**
- unresolved incident counts/status;
- alert-channel delivery health;
- privacy-request state counts;
- missing/stale policy status;
- backup freshness/evidence status;
- restore/rollback drill status;
- runbook exercise status;
- active privacy policy versions.

**Rules:**
- aggregate/minimized fields only; unnecessary PII excluded.
- repositories/services are injected; read models do not import broker/live/risk authorities.
- notification health can be degraded without changing trading safety state.

**TDD:**
1. RED tests for aggregation, redaction, stale-policy visibility, channel-failure visibility, and no mutation methods.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_observability.py tests_v1/test_phase9_read_models.py -q
   ```
3. Implement and GREEN.
4. Commit: `feat: add product operations health read models`.

---

## P9-07 — Separate Local and Central Backup/Restore + Rollback Runbooks and Drills

**Purpose:** Verify two different backup boundaries without mixing local trading/user archives with central privacy/account data.

**Existing local contract:**
- `dashboard/backend/backup_service.py`
  - `BACKUP_SCHEMA_VERSION = "AlgoFortisBackup/v1"`
  - `AlgoFortisBackupService`
  - forbidden secret filtering;
  - manifest/checksum/path-traversal validation;
  - fail-closed zero-partial-import behavior.
- `SQLiteOperationalBackupService` remains distinct from the portable `AlgoFortisBackup/v1` archive.

**Create:**
- `dashboard/backend/product_ops_v2/drills.py`
- `dashboard/backend/product_ops_v2/central_backup.py`
- `docs/v2/phase9/runbooks/RUNBOOK_LOCAL_BACKUP_RESTORE.md`
- `docs/v2/phase9/runbooks/RUNBOOK_CENTRAL_PRIVACY_BACKUP_RESTORE.md`
- `docs/v2/phase9/runbooks/RUNBOOK_ROLLBACK.md`
- `tests_v1/test_phase9_local_backup_drill.py`
- `tests_v1/test_phase9_central_backup_drill.py`
- `tests_v1/test_phase9_rollback_drill.py`

**Do not rewrite:** `AlgoFortisBackupService` unless a test demonstrates a security defect. Phase 9 wraps/verifies the existing contract.

**Local drill requirements:**
- create a representative `AlgoFortisBackup/v1` archive;
- verify manifest/schema/checksums and secret exclusion;
- restore into an isolated test target/data object only;
- prove no active runtime state is overwritten;
- emit deterministic `DrillResult` with runbook version, environment, timestamps, step results, evidence fingerprint, PASS/FAIL.

**Central privacy backup requirements:**
- define a separate `CentralPrivacyBackupPort(Protocol)` / evidence contract, not `AlgoFortisBackup/v1`.
- allow only PrivacyPolicyRegistry-approved central classes (account/consent/privacy/support scope).
- explicitly reject broker credentials, private keys, strategy content, local positions, balances, unrestricted/raw trade logs, and local trading state.
- require retention/expiry + encryption/access evidence references from the platform boundary; do not invent cloud-vendor constants in domain code.
- isolated restore target only; no trading authority.
- if no production central-backup adapter exists yet, deterministic development tests use a fake/in-memory adapter, while G9 remains blocked on real environment drill evidence. Never promote a fake adapter as production proof.

**Rollback requirements:**
- versioned configuration/schema/release rollback evidence;
- isolated target;
- never auto-arm Live;
- never silently overwrite active safety state.

**TDD:**
1. RED tests including cross-boundary contamination: central backup containing local/broker/private-key/trade data must reject.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_local_backup_drill.py tests_v1/test_phase9_central_backup_drill.py tests_v1/test_phase9_rollback_drill.py -q
   ```
3. Implement minimal drill harness + runbooks; GREEN.
4. Regression for existing backup service:
   ```powershell
   python -m pytest tests_v1 -k "backup" -q
   ```
5. Commit: `feat: add separated backup restore and rollback drills`.

**Critical regression:** Central privacy backup must never become a route for centralizing broker secrets or local trading state.

---

## P9-08 — Owner/User ProductOps Dashboards as Read-Model Clients Only

**Purpose:** Add UI last, after service/read-model contracts are stable.

**Existing UI structure to extend:**
- `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- `dashboard/owner-dashboard/data/`
- `dashboard/owner-dashboard/screens/`
- `dashboard/user-dashboard/UserDashboardApp.tsx`
- `dashboard/user-dashboard/data/`
- `dashboard/user-dashboard/screens/`
- web integration under `dashboard/web/src/`.

**Backend create/modify:**
- Create: `dashboard/backend/product_ops_v2/service.py`
- Modify only narrow route wiring in `dashboard/backend/api.py` or its existing route registration seam; do not put domain logic into the large API file.
- Add tests: `tests_v1/test_phase9_product_ops_service.py`, `tests_v1/test_phase9_dashboard_authority.py`.

**Frontend create:**
- `dashboard/owner-dashboard/data/productOps.ts`
- `dashboard/owner-dashboard/screens/ProductOperationsScreen.tsx`
- `dashboard/user-dashboard/data/privacy.ts`
- `dashboard/user-dashboard/screens/PrivacyAndRequestsScreen.tsx`

**Frontend modify:**
- `dashboard/owner-dashboard/data/index.ts`
- `dashboard/owner-dashboard/OwnerDashboardApp.tsx`
- `dashboard/user-dashboard/data/index.ts`
- `dashboard/user-dashboard/UserDashboardApp.tsx`
- `dashboard/web/src/api.ts` / `dashboard/web/src/contracts.ts` only if the existing runtime integration requires typed API additions.

**Owner view:** operational health, alert health, unresolved incident status, privacy workflow counts, backup/restore/rollback status, runbook status, active policy versions.

**User view:** current notice/version, consent state, privacy-request/grievance status, and S2-authorized account/device/security state.

**Authority rules:**
- UI never accesses DB directly.
- UI never imports/requests broker place/modify/cancel, Live ARM, RiskGate mint, or AI execution operations.
- mutations such as consent/rights requests go only through audited ProductOps services and S2 identity scope; dashboards themselves remain presentation/read-model clients.

**Backend TDD:**
1. RED tests prove owner/user scoping, no cross-user reads, and absence of trading authority.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_product_ops_service.py tests_v1/test_phase9_dashboard_authority.py -q
   ```

**Frontend verification:**
1. Add UI after backend contracts are GREEN.
2. Run from repo root:
   ```powershell
   npm run typecheck
   npm run build
   ```
   Expected: TypeScript and Vite build succeed.
3. Visual check in the existing dashboard dev runtime:
   - Owner Product Operations screen renders health/policy/drill states without raw PII.
   - User Privacy & Requests screen renders exact notice version/fingerprint reference and request statuses.
   - degraded/missing-policy state is visibly fail-closed, not shown as success.
   - no Live enable/ARM/order-control UI is introduced by these screens.
4. Capture visual verification evidence/screenshot path in the Phase-9 evidence ledger during implementation; do not claim visual PASS if the browser/dev runtime was not actually exercised.
5. Commit: `feat: add read-only Phase 9 product operations dashboards`.

---

## P9-09 — G9 Evidence, Deterministic Probe, Combined Regression, and Hosted Qualification

**Purpose:** Qualify the full Phase 9 stack only after all slices exist.

**Create:**
- `dashboard/backend/product_ops_v2/evidence.py`
- `build/tools/phase9_product_ops_probe.py`
- `tests_v1/test_phase9_evidence.py`
- `tests_v1/test_phase9_qualification_guard.py`
- `.github/workflows/v2-phase9-product-ops.yml`
- `docs/v2/phase9/G9_EVIDENCE.md`
- `docs/v2/phase9/G9_LEGAL_REVIEW_STATUS.md`

**Required deterministic G9 markers:**
- `PRODUCT_OPS_AUTHORITY=PRIVACY_OPERATIONS_ONLY`
- `IDENTITY_AUTHORITY=S2_DEVICE_SESSION_GATE`
- `INCIDENT_AUTHORITY=FAILURE_INCIDENT_EXISTING_PATH`
- `ALERT_AUTHORITY=EXISTING_ALERT_DISPATCHER`
- `NOTICE_CONSENT=VERSIONED_IMMUTABLE`
- `ERASURE_PRIORITY=LEGAL_HOLD_OR_SAFETY_RETENTION_SCOPED`
- `LOCAL_BACKUP_CONTRACT=AlgoFortisBackup/v1`
- `CENTRAL_PRIVACY_BACKUP=SEPARATE_ALLOWLISTED_BOUNDARY`
- `DASHBOARDS=READ_MODEL_CLIENTS_ONLY`
- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `G9_ENABLES_REAL_MONEY_TRADING=NO`
- `SOFTWARE_TESTS_PROVE_LEGAL_COMPLIANCE=NO`

**Qualification guard must require:**
- OD-V2-25 FROZEN;
- software evidence complete;
- local + central backup drill evidence kept distinct;
- restore + rollback drill evidence;
- incident/alert reuse proof;
- dashboard authority/static checks;
- legal-review status recorded separately and cannot be synthesized from pytest results.

**Focused pre-full RED/GREEN:**
1. Write evidence/qualification tests first; expected RED until probe/workflow/docs exist.
2. Run:
   ```powershell
   python -m pytest tests_v1/test_phase9_evidence.py tests_v1/test_phase9_qualification_guard.py -q
   python build/tools/check_phase9_product_ops.py
   python build/tools/phase9_product_ops_probe.py
   ```
3. Probe must be deterministic and secret/PII-free.

**Combined local regression at Phase-9 end (Owner-requested big check):**
```powershell
python build/tools/check_phase9_product_ops.py
python -m pytest tests_v1 -q
python build/tools/phase9_product_ops_probe.py
npm run typecheck
npm run build
```
Also execute the existing required Phase-5/6/7/8 static/probe gates that are present on the eventual qualification stack; do not skip a gate merely because its hosted run was previously blocked.

**Hosted G9 workflow:**
- Windows latest + Windows 2022 / pinned Python consistent with existing V2 qualification policy.
- run static Phase-9 firewall;
- run Phase-9 focused tests;
- run full regression/golden preservation required by the current stack;
- build/typecheck UI;
- emit deterministic G9 evidence artifacts A/B;
- cross-Windows compare requires exact normalized evidence equality.

**Actions-capacity rule:** If GitHub-hosted jobs again return pre-step `steps=null` because hosted capacity/minutes are unavailable, record **G9 NOT QUALIFIED**. Do not alter product code merely to make an unprovisioned runner appear green. Rerun after capacity resets or through an explicitly approved equivalent qualification environment.

**Legal gate:**
- `G9_LEGAL_REVIEW_STATUS.md` records dated qualified-adviser review separately.
- Never write `COMPLIANT` based only on software tests.
- If legal review is pending, software can be development-GREEN while G9 exit remains blocked.

**Final review checklist:**
1. Missing/unknown/stale privacy policy cannot permit side effects.
2. S2 mismatch/cross-user rights request cannot pass.
3. Valid legal hold/safety retention cannot be erased; unrelated eligible data still deletes.
4. Privacy incident path cannot leak PII/secrets or introduce a parallel incident/alert/audit system.
5. Central backup cannot contain local trading/broker/private-key data.
6. Dashboards cannot reach broker/Live/RiskGate execution authority.
7. Existing Phase-5/6 safety behavior remains intact.
8. G8/G9 hosted qualification status is reported exactly as observed, never inferred.

**Commit sequence:**
- `test: define G9 evidence qualification contract`
- `feat: add deterministic Phase 9 qualification evidence`
- `ci: add dual-Windows G9 qualification workflow`
- `docs: record G9 evidence status`

---

## End-of-Phase Review and Merge Rules

Before calling Phase 9 complete:

1. Run verification-before-completion against the exact implementation head.
2. Review the full diff from the approved design head to implementation head.
3. Perform code review focusing on the five critical regressions listed above and all safety invariants.
4. Keep implementation PR draft/unmerged while any required exact-head G9 software evidence or dated G9 legal-review evidence is missing.
5. Phase 9/G9 never authorizes real-money trading. Live remains `READ_ONLY / DISARMED`.
6. Do not use successful local focused tests as a substitute for hosted qualification when the gate explicitly requires hosted/external evidence.

## Execution Method After Plan Approval

**Recommended available method:** execute inline in this chat, task-by-task, using TDD. For each P9 slice: write tests first, demonstrate RED where execution is available, implement the minimum change, run focused GREEN/static checks, review the diff, then commit. Keep the user updated with `changed / verified / left` checkpoints.

**Alternative:** leave this plan committed and start implementation later without changing the approved design/spec.

Implementation must not start until the Owner explicitly approves this written plan and selects execution.