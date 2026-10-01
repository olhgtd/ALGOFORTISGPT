# V1 Salvage Integration Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reintroduce the highest-value V1 security/platform behaviors into the current AlgoFortis convergence tree without creating any parallel trading, Paper, broker-mutation, or identity authority.

**Architecture:** Current V2 contracts remain authoritative. Manual V1 is used as a behavioral/evidence donor. Slice 1 adds regression guards first, then only the minimum compatibility/adaptation needed for the current tree. No wholesale folder copy and no old runtime authority resurrection.

**Tech Stack:** Python/pytest, TypeScript/Vitest where needed, existing AlgoFortis backend/runtime modules, GitHub Actions when available.

**Spec:** `V1_SALVAGE_REFERENCE_README.md` and `docs/v1-salvage-reference/ADOPTION_MATRIX.md` on branch `v1-manual-salvage-reference-20260929`.

## Global Constraints

- Live remains `READ_ONLY=true`, `DISARMED=true`, and real broker mutation remains disabled.
- `RiskGateV2` remains the sole executable-order authority.
- No duplicate Paper engine, RiskGate, broker-mutation authority, or identity authority.
- No SAMPLE/fake-success state may become production truth.
- Broker secrets remain local and must not be centralized or logged.
- Existing V2 recovery/manual-resume semantics remain authoritative.
- Prefer V1 regression behavior/tests over transplanting V1 implementations.

## Review Focus

- Secret exposure through logs/API/repr/backup must remain impossible.
- Refresh-token reuse must fail closed and revoke the relevant family.
- Recovery must never silently re-arm or create executable authority.
- Backup restore must reject traversal/duplicate/undeclared entries.
- Old V1 modules must not become a second RiskGate/Paper/broker-mutation path.

---

### Task 1: Freeze slice boundaries and branch provenance

**Files:**
- Create: `docs/v1-salvage-integration/SLICE1_SECURITY_PLATFORM.md`

- [ ] Record base commit, V1 reference branch, safety invariants, included capability families, and explicit exclusions.
- [ ] Commit documentation before runtime changes.

### Task 2: Port V1 security invariants as regression guards

**Files:**
- Create or extend focused tests under `tests_v1/` using current module paths.

**Behaviors:**
- plaintext broker/user secrets never persist or leak via string/API projection;
- Owner/User authorization remains fail-closed;
- token/session reuse handling remains fail-closed where current session authority exposes it;
- recovery cannot arm Live or bypass current authority.

- [ ] Write failing/current-state tests first.
- [ ] Run targeted tests and capture RED or already-covered evidence.
- [ ] Add minimum implementation only where a required behavior is missing.
- [ ] Re-run targeted tests.

### Task 3: Port V1 backup/restore security invariants

**Files:**
- Create or extend focused backup tests under `tests_v1/`.

**Behaviors:**
- private keys, broker credentials, activation secrets, and device private material excluded;
- restore rejects `..`, rooted paths, drive-letter paths, duplicate members, undeclared categories;
- manifest/checksum failure is fail-closed.

- [ ] Write/port regression tests first.
- [ ] Verify RED or existing current coverage.
- [ ] Add only missing compatible implementation.
- [ ] Verify targeted tests.

### Task 4: Recovery/idempotency compatibility guards

**Files:**
- Create or extend tests around current recovery/idempotency/projection modules.

**Behaviors:**
- duplicate operation/order projection suppressed;
- corrupt persisted state fails closed;
- restart/reconnect never auto-arms;
- current RECOVERY/READY_FOR_RESUME/manual-resume semantics win over V1 behavior.

- [ ] Write tests first.
- [ ] Verify current behavior.
- [ ] Adapt only missing behavior.
- [ ] Verify targeted tests.

### Task 5: Static authority-boundary guard

**Files:**
- Create: `tests_v1/test_v1_salvage_authority_boundaries.py`

**Assertions:**
- salvaged modules do not introduce a second executable-order authority;
- no V1 salvage module directly enables broker place/modify/cancel;
- no duplicate Paper execution authority is introduced;
- Live safety defaults remain fail-closed.

- [ ] Write the guard.
- [ ] Run it against the branch.
- [ ] Fix only actual boundary violations.

### Task 6: Verification and slice report

**Files:**
- Create: `docs/v1-salvage-integration/SLICE1_VERIFICATION.md`

- [ ] Run all targeted Slice-1 tests.
- [ ] Run the widest available Python regression command in the environment.
- [ ] Run relevant frontend tests/typecheck/build if Slice-1 touched frontend code.
- [ ] Record exact commands/results and any unavailable runner limitation.
- [ ] Record what was adopted, what was already present, and what remains for Slice 2.
