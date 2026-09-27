# AlgoFortis V2 S2 — Local Windows Qualification Evidence

**Date:** 2026-09-28  
**Tested branch:** `v2-s2-account-device-session`  
**Tested commit:** `6c076c4dbdddee528c42318938bf11590b9fdef1`  
**Environment:** local Windows PowerShell, Python 3.13.14  
**Status:** LOCAL WINDOWS QUALIFICATION GREEN — NOT YET DUAL-WINDOWS / HOSTED-CI QUALIFIED

## 1. Exact-head verification

The local qualification was executed from exact branch `v2-s2-account-device-session` at commit `6c076c4dbdddee528c42318938bf11590b9fdef1`.

A short `T:\` pytest base temp was used only to avoid the host Windows path-length limitation observed with long content-addressed historical-store paths. This is an environment workaround, not a product-code change.

## 2. Qualification results

- Compile gate: PASS
- Module boundaries: PASS
- Phase 1 static: PASS
- Phase 2 static: PASS
- Phase 3 static: PASS
- Phase 4 static: PASS
- Phase 4 focused tests: **67 passed**
- Phase 4 deterministic probe: PASS
- Phase 5 static: PASS
- Phase 5 focused tests: **126 passed**
- Phase 5 deterministic probe: PASS
- S2 account authority static boundary: PASS
- S2 focused tests: **65 passed**
- S2 deterministic probe: PASS
- V1 auth/security regression subset: **20 passed**
- Full `tests_v1` regression: **607 passed, 0 failed**
- Existing regression certification: **13 tests PASS / ALL PASS**

The repeated `starlette.testclient` / AnyIO `BlockingPortal` deprecation warning is non-failing dependency noise and did not affect qualification results.

## 3. Deterministic S2 evidence

Observed deterministic S2 markers:

- `S2_SCHEMA_VERSION=s2-account-gate/v1`
- `ACCOUNT_AUTHORITY_FINGERPRINT=2dab2565f6fabbcc9e0624bf838ef2a7b3416f0957e0b96073330e0688a3f4aa`
- `DEVICE_REPROOF_FINGERPRINT=94db9d127da635df093d4e37b740cf749593148f8255b3e1b000743261da1a24`
- `DEVICE_CHALLENGE_POLICY=SERVER_ISSUED_SCOPED_EXPIRING_SINGLE_USE`
- `DEVICE_CHALLENGE_REPLAY_RESULT=REJECTED`
- `SESSION_REPLAY_RESULT=FAMILY_REVOKED`
- `CROSS_USER_ESCAPE_COUNT=0`
- `OUTAGE_GATE_STATUS=AUTHORITY_UNAVAILABLE`
- `OUTAGE_RUNTIME_MODE=LOCAL_SAFETY_ONLY`
- `RATE_LIMIT_FLOWS=LOGIN,DEVICE_PROOF,REFRESH_MISUSE,RECOVERY`
- `DEVICE_LIMIT=3`
- `PRODUCTION_DOMAIN=PENDING_EXTERNAL`
- `LIVE_STATE=READ_ONLY/DISARMED`
- `BROKER_MUTATION_CAPABILITY=ABSENT`
- `GP_S2_FINGERPRINT=7821925569b36b90257dab713f38daff6ced6334ca113851e1baa9aa427536a4`

## 4. Preserved safety invariants

- Live remains `READ_ONLY / DISARMED`.
- S2 has no broker-mutation capability.
- S2 cannot ARM Live.
- Authority outage maps to `LOCAL_SAFETY_ONLY`.
- Refresh replay revokes the session family.
- Cross-user escape count is zero in deterministic qualification.
- Device challenge flow is server-issued, scoped, expiring, single-use, and replay-rejecting.

## 5. Remaining formal gate

This local run provides fresh executable evidence on a real Windows PC for the exact tested S2 commit.

It does **not** by itself satisfy the plan's dual-Windows / cross-Windows GP-S2 comparison requirement. At the time of recording, the exact tested commit has no executable hosted workflow run or combined commit status available from GitHub, so the branch must not be represented as hosted-CI-qualified or final GP-S2 `GATE-READY` solely from this local run.

Required before final S2 gate closure under the current plan:

1. executable qualification on the required second Windows environment / hosted Windows job;
2. cross-Windows GP-S2 deterministic marker/fingerprint comparison;
3. then record final `GP_S2_EVIDENCE.md` and perform the final review/qualification gate.

No merge authorization is implied by this evidence record.
