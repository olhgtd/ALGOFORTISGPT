# S2 Account, Device & Session Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox items so progress can be audited.

**Goal:** Deliver the Track-P/P2 `GP-S2` account/device/session gate by preserving proven V1 auth/device/session behavior, adding explicit V2 contracts, durable server-authoritative state seams, fail-closed cloud-outage behavior, and deterministic qualification evidence without granting cloud/account code any broker-mutation or Live-ARM authority.

**Architecture:** Keep the existing V1 security primitives (`dashboard/backend/security.py`, `device_identity.py`, `session_manager.py`, `auth_policy.py`, `security_store.py`) as the proven substrate. Add a focused `dashboard/backend/account_v2/` package that composes/wraps those primitives behind typed V2 contracts instead of rewriting them or growing the legacy monoliths. S2 produces identity/device/session prerequisite evidence only. `AUTHORITY_UNAVAILABLE` is a gate result; runtime maps it to `LOCAL_SAFETY_ONLY`. Trading state, broker secrets, `RiskGate`, Paper/Live execution, and ARM authority remain outside the account plane.

**Tech Stack:** Python 3.13, dataclasses/enums/protocols, existing `python-fido2`, existing SQLite security store, Windows CNG/TPM + DPAPI device identity, pytest, GitHub Actions dual-Windows qualification.

**Spec:** `docs/superpowers/specs/2026-09-26-s2-account-device-session-gating-design.md`

## Global Constraints

- Live remains `READ_ONLY / DISARMED` for the entire plan.
- S2 MUST NOT place, cancel, modify, or arm any order.
- `dashboard/backend/account_v2/` MUST NOT import concrete broker adapters, execution mutation APIs, `engine.live` arming APIs, or order-placement capabilities.
- Reuse existing V1 WebAuthn/device/session/recovery behavior; do not build a second independent auth stack.
- Keep `dashboard/backend/api.py` and `dashboard/backend/security_store.py` changes minimal; prefer focused adapters/modules.
- Do not hard-code new production security thresholds. TEST_ONLY policy values are permitted in tests.
- OD-V2-20 update safe windows are versioned policy, never production constants.
- OD-V2-21 offline entitlement is 7 days but wall-clock-only validation is forbidden; S2 implements the contract/seam, not the full entitlement service.
- OD-V2-22 telemetry remains opt-in/minimized/scrubbed; S2 does not implement a telemetry backend.
- OD-V2-23 publisher/domain remain `PENDING_EXTERNAL`; dev/staging WebAuthn credentials are never silently promoted to production.
- Same-PC reinstall continuity requires cryptographic device-key re-proof; hostname/MAC/disk IDs are never trust anchors.
- Every security-critical mutation that requires audit must fail closed if required audit persistence fails.
- Cross-user/tenant isolation (`INV-04`) and cloud-outage safety (`INV-19`) are explicit GP-S2 blockers.
- No PR merge is part of this plan unless the Owner separately authorizes it.

## Review Focus

Review every slice for: accidental cloud trading authority, duplicated V1 auth logic, silent fail-open paths, weak caller-supplied ownership checks, refresh-token replay handling, same-PC reinstall semantics, RP-ID/origin scope, rate-limit isolation, audit-failure behavior, and any hidden wall-clock-only entitlement or hard-coded update-window assumption.

---

## Task 0 — Reconcile Track-P Owner Decisions in the root register

**Files:**
- Modify: `ALGOFORTIS_V2_OWNER_DECISIONS.md`
- Verify against: `docs/v2/adr/ADR-016-track-p-s2-platform-policy.md`

- [ ] Update the register version/process note to record the 2026-09-26 Owner freeze of OD-V2-20/21/22/23.
- [ ] Replace OD-V2-20 OPEN recommendation with the frozen Option A decision: signed artifacts/rollback + versioned `UpdateSafeWindowPolicy`, missing policy defers updates, never auto-arm.
- [ ] Replace OD-V2-21 OPEN recommendation with the frozen 7-day signed offline lease plus server-time/check-in/monotonic-time hardening; uncertainty fails closed for entitlement-dependent new operations while protective safety continues.
- [ ] Replace OD-V2-22 OPEN recommendation with the frozen opt-in/minimized/scrubbed telemetry policy and no guessed retention constants.
- [ ] Replace OD-V2-23 OPEN recommendation with frozen SemVer/API versioning; publisher/domain `PENDING_EXTERNAL`; fresh production WebAuthn enrollment + explicit device re-proof/re-binding before S3/release.
- [ ] Add dated decision-log rows for 20–23 pointing to ADR-016.
- [ ] Change blocking matrix Track P1 row to `20, 21, 22, 23 — FROZEN 2026-09-26`.
- [ ] Re-fetch the file and verify no OD20–23 `OPEN` status remains.
- [ ] Commit: `docs: reconcile Track P S2 owner decisions`.

---

## Task 1 — Add S2 typed contracts and architecture boundary guard

**Files:**
- Create: `dashboard/backend/account_v2/__init__.py`
- Create: `dashboard/backend/account_v2/contracts.py`
- Create: `tests_v1/test_s2_contracts.py`
- Create: `tests_v1/test_s2_architecture_guard.py`
- Create: `build/tools/check_s2_account_gate.py`

**Interfaces:**

`contracts.py` must define immutable typed contracts for:
- `DeviceSessionGateStatus`: `VALID`, `REVOKED`, `SESSION_EXPIRED`, `DEVICE_UNTRUSTED`, `RECOVERY_REQUIRED`, `AUTHORITY_UNAVAILABLE`.
- `AccountRuntimeMode`: `NORMAL`, `LOCAL_SAFETY_ONLY`.
- `DeviceSessionGateResult`: `schema_version`, `user_id`, `device_id`, optional `session_family_id`, `status`, `reasons`, optional `authority_evidence_ref`, `evaluated_at`, optional `audit_ref`.
- `UpdateSafeWindowPolicyRef` seam with explicit policy id/version and no production time defaults.
- `EntitlementTimeEvidence` seam carrying signed-server/check-in/monotonic evidence fields without implementing full entitlement decisions.
- `ProductionIdentityPolicy` seam carrying RP-ID/origin environment identity and explicit production-migration status.

**TDD:**
- [ ] RED: write tests proving exact enum set, immutability, `VALID` has no arm/trade field, and `LOCAL_SAFETY_ONLY` is a runtime mode rather than gate status.
- [ ] RED: architecture test scans `dashboard/backend/account_v2/**/*.py` and rejects imports/references to concrete broker adapters, broker mutation methods, `ApprovedOrder`, Live arming/mutation APIs, `place_order`, `submit_order`, `cancel_order`, `modify_order`, or `arm(`.
- [ ] Run: `python -m pytest tests_v1/test_s2_contracts.py tests_v1/test_s2_architecture_guard.py -q` and capture expected RED because package/modules do not exist.
- [ ] GREEN: add minimum contracts/package/static checker to satisfy tests.
- [ ] Run focused GREEN.
- [ ] Run existing V1 auth regressions: `python -m pytest tests_v1/test_area1_auth_security_recovery.py tests_v1/test_local_desktop_auth.py -q`.
- [ ] Commit: `feat: add S2 account gate contracts and boundary guard`.

---

## Task 2 — Add account-authority repository port and durable V1-store adapter

**Files:**
- Create: `dashboard/backend/account_v2/repository.py`
- Create: `dashboard/backend/account_v2/v1_store_adapter.py`
- Modify only if unavoidable: `dashboard/backend/security_store.py`
- Create: `tests_v1/test_s2_repository.py`

**Interfaces:**

`AccountAuthorityRepository` Protocol must expose only account-plane operations needed by S2, scoped by authoritative `user_id`:
- account/user lookup;
- enabled WebAuthn credential lookup by user/RP;
- registered-device lookup/list/register/revoke;
- session-family lookup/create/rotate-state/revoke;
- all-session/all-device revoke for recovery;
- challenge/recovery/audit references required by higher services.

`V1SecurityStoreAdapter` must wrap existing durable `SQLiteSecurityStore`; it must not expose broker/trading tables or caller-controlled cross-user query escape hatches.

**TDD:**
- [ ] RED: tests require persistence across adapter/store reopen for representative device/session/revocation state.
- [ ] RED: user A cannot read/revoke/mutate user B device/session records (`INV-04`).
- [ ] RED: caller-supplied foreign user/device IDs fail closed rather than broad-querying the store.
- [ ] Inspect existing `SQLiteSecurityStore` public methods before extending it; add focused methods only if the V1 store lacks a required durable primitive.
- [ ] GREEN: implement the narrow repository adapter; do not copy/rebuild the entire store.
- [ ] Run: `python -m pytest tests_v1/test_s2_repository.py -q`.
- [ ] Run V1 database/auth regression subset.
- [ ] Commit: `feat: add durable S2 account authority repository`.

---

## Task 3 — Wrap existing WebAuthn authority and lock RP-ID/origin migration semantics

**Files:**
- Create: `dashboard/backend/account_v2/webauthn_authority.py`
- Reuse: `dashboard/backend/security.py::WebAuthnRelyingParty`
- Reuse: `dashboard/backend/security.py::WebAuthnCeremonyService`
- Create: `tests_v1/test_s2_webauthn_authority.py`

**Behavior:**
- Delegate actual FIDO2 ceremonies to the existing `WebAuthnCeremonyService`.
- Keep explicit normal/development RP configuration.
- Reject origin/RP mismatch, production loopback, non-HTTPS production origin, and unconfigured RP.
- Expose an explicit production migration decision: dev/staging credential cannot satisfy a production RP; fresh production WebAuthn enrollment is required.
- S2 wrapper never adds a password fallback.

**TDD:**
- [ ] RED: dev localhost profile valid only with explicit development flag/port.
- [ ] RED: production origin mismatch and HTTP production origin rejected.
- [ ] RED: credential/RP from dev/staging cannot be silently accepted as production-migrated.
- [ ] GREEN: minimal wrapper/policy around the existing service.
- [ ] Run focused + existing WebAuthn/security tests.
- [ ] Commit: `feat: harden S2 WebAuthn authority boundary`.

---

## Task 4 — Device registry, possession proof, quota, and same-PC reinstall continuity

**Files:**
- Create: `dashboard/backend/account_v2/device_service.py`
- Reuse: `dashboard/backend/device_identity.py`
- Create: `tests_v1/test_s2_device_service.py`

**Interfaces:**
- `DeviceRegistryService.enroll(...)`
- `DeviceRegistryService.verify_possession(...)`
- `DeviceRegistryService.reprove_existing_device(...)`
- `DeviceRegistryService.revoke(...)`
- `DeviceRegistryService.list_for_user(...)`

**Rules:**
- Max three active registered devices, no silent eviction.
- Enrollment stores public key/fingerprint only; private key never leaves local provider.
- Same-PC reinstall: rediscovered key signs fresh challenge; matching registered public key restores same logical device and consumes no new quota slot.
- Missing/corrupt/mismatched key or failed signature → `DEVICE_UNTRUSTED` / fresh enrollment, never metadata-only continuity.
- Hostname/MAC/disk ID cannot prove identity.

**TDD:**
- [ ] RED: fourth device rejected with existing three unchanged.
- [ ] RED: successful re-proof retains same device id and quota count.
- [ ] RED: missing/corrupt key or fingerprint mismatch fails closed.
- [ ] RED: cross-user device proof cannot be replayed as another user's device (`INV-04`).
- [ ] GREEN: compose existing `DeviceIdentityManager`/provider behavior with repository records and server challenges.
- [ ] Run focused + V1 device identity/auth tests.
- [ ] Commit: `feat: add S2 device registry and reinstall reproof`.

---

## Task 5 — Durable device-bound session-family rotation and replay revocation

**Files:**
- Create: `dashboard/backend/account_v2/session_service.py`
- Reuse semantics from: `dashboard/backend/session_manager.py`
- Create: `tests_v1/test_s2_session_service.py`

**Rules:**
- Preserve V1 concepts: 15-minute access token; 30-day absolute refresh-family lifetime; 7-day idle inactivity policy unless a later dated OD changes it.
- Refresh token is single-use and rotating.
- Persist hashes/state through the account repository; plaintext refresh tokens are never stored server-side.
- Reuse of a consumed refresh token immediately revokes affected family and denies replacement tokens.
- Session is bound to user + registered non-revoked device.
- Revoked device/session cannot evaluate `VALID`.
- Time source is injected/testable; do not introduce hidden production timing beyond the existing frozen V1 policy.

**TDD:**
- [ ] RED: normal rotation consumes old token and persists new active hash.
- [ ] RED: replaying consumed token revokes the family.
- [ ] RED: reopening durable store preserves revocation/replay history.
- [ ] RED: revoked/foreign device cannot rotate.
- [ ] GREEN: implement persistent service, using V1 semantics instead of changing the legacy in-memory manager.
- [ ] Run focused + V1 session tests.
- [ ] Commit: `feat: add durable S2 session family service`.

---

## Task 6 — High-assurance recovery and flow-isolated rate limiting

**Files:**
- Create: `dashboard/backend/account_v2/rate_limit.py`
- Create: `dashboard/backend/account_v2/recovery_service.py`
- Reuse semantics from: `dashboard/backend/auth_policy.py`
- Create: `tests_v1/test_s2_rate_limit.py`
- Create: `tests_v1/test_s2_recovery.py`

**Interfaces:**
- Versioned `RateLimitPolicy` with per-flow profiles and no new guessed production thresholds.
- Flow IDs at minimum: interactive login/WebAuthn, device proof/enrollment, refresh misuse, recovery, expensive/high-risk account operation.
- Recovery service revokes all active session families and all registered device trust after successful high-assurance proof.

**TDD:**
- [ ] RED: exhausting login limiter does not consume/reject recovery flow unless recovery's own policy is exceeded.
- [ ] RED: process/repository reopen preserves authoritative rate-limit state where the policy requires server-side persistence.
- [ ] RED: high-assurance recovery revokes every session/device for target user only.
- [ ] RED: user A recovery cannot revoke user B (`INV-04`).
- [ ] RED: required audit failure prevents security-critical recovery mutation from being reported successful.
- [ ] GREEN: implement policy/service with TEST_ONLY values in tests, no guessed production constants.
- [ ] Run focused + V1 recovery/rate-limit tests.
- [ ] Commit: `feat: add S2 recovery and isolated rate limiting`.

---

## Task 7 — DeviceSessionGate and cloud-outage `LOCAL_SAFETY_ONLY` mapping

**Files:**
- Create: `dashboard/backend/account_v2/gate.py`
- Create: `dashboard/backend/account_v2/safety_mode.py`
- Create: `tests_v1/test_s2_device_session_gate.py`
- Create: `tests_v1/test_s2_cloud_outage.py`

**Interfaces:**
- `DeviceSessionGate.evaluate(user_id, device_id, session_family_id, now) -> DeviceSessionGateResult`
- `AccountSafetyModeMapper.map(result) -> AccountRuntimeMode`

**Rules:**
- `VALID` only when account, credential context, registered device, possession/session/revocation state all satisfy the account prerequisite.
- Central authority timeout/unreachable/unverifiable → result `AUTHORITY_UNAVAILABLE`.
- Mapper immediately converts `AUTHORITY_UNAVAILABLE` to runtime mode `LOCAL_SAFETY_ONLY`.
- `LOCAL_SAFETY_ONLY` allows existing local protective/risk/reconciliation/position-monitoring behavior but blocks new login/enrollment/recovery/entitlement mutation and fresh future ARM eligibility.
- Returning to `VALID` never auto-arms and does not itself restore trading-entry permission.

**TDD:**
- [ ] RED: exact status/reason mapping for revoked/session-expired/device-untrusted/recovery-required/authority-unavailable.
- [ ] RED: authority timeout maps to `LOCAL_SAFETY_ONLY` (`INV-19`).
- [ ] RED: gate result has no method/field that can arm/place/cancel/modify.
- [ ] GREEN: implement pure deterministic gate/mode mapper.
- [ ] Run focused tests.
- [ ] Commit: `feat: add S2 device session gate and outage mode`.

---

## Task 8 — Add OD20/21/22/23 policy seams without pulling P3/S3 scope forward

**Files:**
- Create: `dashboard/backend/account_v2/policy_seams.py`
- Create: `tests_v1/test_s2_policy_seams.py`

**Required seams:**
- `UpdateSafeWindowPolicy`: policy id/version, allowed engine states, open-position rule, session-calendar ref, applicability. No hard-coded production market window. Missing/invalid policy decision = defer update.
- `EntitlementTimeEvidence`: signed server-issued time, last successful server check-in, signed lease expiry, monotonic anchor/elapsed evidence, boot/session identity where applicable. Wall-clock evidence cannot extend lease. Contradictory/backward/lost-anchor evidence yields `ENTITLEMENT_TIME_UNCERTAIN` for entitlement-dependent new operations.
- `TelemetryPrivacyPolicy`: opt-in/minimized/scrubbed boundary; no strategy/broker secret/raw trading data classes.
- `ProductionIdentityMigration`: production domain/publisher may be `PENDING_EXTERNAL`; dev/staging credentials never promote; production domain finalization requires fresh production WebAuthn + device key re-proof/re-bind.

**TDD:**
- [ ] RED: no default production update hours/times exist.
- [ ] RED: wall-clock rollback cannot extend entitlement lease.
- [ ] RED: missing monotonic/check-in evidence fails closed for entitlement-dependent new operation, while `protective_safety_allowed=True` remains explicit.
- [ ] RED: telemetry policy rejects forbidden data classes.
- [ ] RED: production migration rejects dev credential promotion and requires re-enrollment/rebind flags.
- [ ] GREEN: implement seams only; do not build updater/entitlement/telemetry backend.
- [ ] Run focused tests.
- [ ] Commit: `feat: add S2 platform policy seams`.

---

## Task 9 — S2 security audit/fail-closed mutation wrapper and INV-04 qualification

**Files:**
- Create: `dashboard/backend/account_v2/audit.py`
- Create: `dashboard/backend/account_v2/authority_service.py`
- Create: `tests_v1/test_s2_audit_fail_closed.py`
- Create: `tests_v1/test_s2_inv04_isolation.py`

**Behavior:**
- Security-critical account mutations execute through a service boundary that writes required audit evidence.
- If required audit persistence fails, mutation must not be reported/committed as successful; use transaction/rollback or pre-commit audit strategy appropriate to repository capabilities.
- Every public service method derives ownership scope from the authenticated principal/server record, not a free caller-supplied target id alone.

**TDD:**
- [ ] RED: audit sink failure during device enroll/revoke/recovery/session-family revoke produces fail-closed outcome.
- [ ] RED: user A cannot list/read/revoke/mutate user B devices/session/recovery state.
- [ ] RED: no broad helper accepts arbitrary user id without caller/authority ownership check.
- [ ] GREEN: implement narrow authority facade and transaction/audit behavior.
- [ ] Run focused tests.
- [ ] Commit: `feat: enforce S2 audit and tenant isolation`.

---

## Task 10 — Deterministic GP-S2 evidence probe and static qualification checker

**Files:**
- Create: `dashboard/backend/account_v2/evidence.py`
- Create: `build/tools/s2_deterministic_probe.py`
- Extend: `build/tools/check_s2_account_gate.py`
- Create: `tests_v1/test_s2_evidence.py`
- Create: `tests_v1/test_s2_qualification_guard.py`

**Probe output must be deterministic and machine-comparable, containing at minimum:**
- `S2_SCHEMA_VERSION`
- `ACCOUNT_AUTHORITY_FINGERPRINT=<64hex>`
- `DEVICE_REPROOF_FINGERPRINT=<64hex>`
- `SESSION_REPLAY_RESULT=FAMILY_REVOKED`
- `CROSS_USER_ESCAPE_COUNT=0`
- `OUTAGE_GATE_STATUS=AUTHORITY_UNAVAILABLE`
- `OUTAGE_RUNTIME_MODE=LOCAL_SAFETY_ONLY`
- `DEVICE_LIMIT=3`
- `PRODUCTION_DOMAIN=PENDING_EXTERNAL`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `BROKER_MUTATION_CAPABILITY=ABSENT`

**TDD:**
- [ ] RED: qualification guard fails if any required S2 module/test/probe marker is missing.
- [ ] RED: two identical deterministic fixtures produce byte-identical evidence fingerprints.
- [ ] GREEN: implement canonical JSON/fingerprint generation using stable ordering and explicit inputs.
- [ ] Run focused S2 suite.
- [ ] Commit: `feat: add GP-S2 deterministic evidence`.

---

## Task 11 — Wire S2 qualification into dual-Windows CI without weakening Phase 0–5 gates

**Files:**
- Modify: `.github/workflows/v2-phase0-baseline.yml`
- Create: `tests_v1/test_s2_ci_guard.py`

**CI changes:**
- Add S2 static checker on both Windows environments.
- Add focused S2 pytest set.
- Run deterministic S2 probe on both Windows environments and upload/compare the exact fingerprint/markers.
- Preserve existing Phase0 golden, Phase1–5 static/focused/full-regression/certification/G4/G5 checks unchanged.
- Cross-Windows GP-S2 compare fails on any marker/fingerprint mismatch.

**TDD:**
- [ ] RED: CI-guard test requires S2 static/focused/probe/cross-Windows steps and both Windows jobs.
- [ ] GREEN: minimally extend workflow.
- [ ] Run focused CI-guard locally where possible.
- [ ] Push exact head and inspect GitHub Actions. If GitHub runner provisioning again shows `runner_id=0` / `steps=[]`, record infrastructure failure honestly; do not call S2 green until an executable run completes.
- [ ] Commit: `ci: add GP-S2 dual-Windows qualification`.

---

## Task 12 — Full GP-S2 qualification, evidence document, and handoff

**Files:**
- Create after fresh executable evidence only: `docs/v2/s2/GP_S2_EVIDENCE.md`
- Update: `docs/PROJECT_CURRENT_STATE_AND_REMAINING_WORK.md`
- Do not edit detailed history unless a material historical state changes.

**Required evidence:**
- [ ] Existing V1 auth/security/recovery regressions green.
- [ ] Full S2 focused suite green.
- [ ] Static architecture checker green.
- [ ] `INV-04` cross-user isolation green.
- [ ] `INV-19` cloud-outage mapping green.
- [ ] Same-PC reinstall/re-proof green; missing/corrupt key fail-closed.
- [ ] Strict three-device/no-silent-eviction green.
- [ ] Refresh replay → family revoke green and durable across reopen.
- [ ] High-assurance recovery revokes all target sessions/devices only.
- [ ] Flow-isolated brute-force/rate-limit tests green.
- [ ] Audit-failure security mutations fail closed.
- [ ] RP-ID/origin and production migration tests green.
- [ ] Entitlement clock-tamper contract green.
- [ ] No hard-coded production update safe-window values.
- [ ] No broker/order/ARM capability in S2 package.
- [ ] Dual-Windows GP-S2 deterministic output matches.
- [ ] Full `tests_v1` regression/certification remains green.
- [ ] Live remains `READ_ONLY / DISARMED`.

Only after all executable evidence above exists:
- [ ] Write `GP_S2_EVIDENCE.md` with exact head SHA, run ID/job IDs, focused/full/static results, fingerprints, invariant results, known limitations, and explicit statement that S2 grants no Live mutation authority.
- [ ] Update current-state master: Track P1 decisions frozen, S2 status `GATE-READY` only if evidence supports it; Phase 6 remains DISARMED.
- [ ] Request code review using `superpowers:requesting-code-review`.
- [ ] Run `superpowers:verification-before-completion` before any completion claim.
- [ ] Commit: `docs: record GP-S2 qualification evidence`.

---

## Implementation Order / Checkpoints

Execute strictly in this order:

1. Task 0 governance reconciliation.
2. Tasks 1–3: contracts/repository/WebAuthn boundary.
3. Tasks 4–6: device/session/recovery/rate-limit authority.
4. Tasks 7–9: gate/outage/policy seams/audit/isolation.
5. Tasks 10–11: deterministic evidence + CI.
6. Task 12: final qualification/evidence only after executable green proof.

At every task, preserve the previous task's GREEN state and run the smallest relevant existing V1 regression subset before moving on. No Phase-6 broker mutation work begins merely because S2 coding has started; Phase 6 consumes S2 only after GP-S2 evidence is actually gate-ready.