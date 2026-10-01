# V1 Salvage Integration Slice 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve useful manual-V1 restart, idempotency, checkpoint, and projection-dedup behavior using the current V2 persistence/recovery authorities, without creating duplicate ledgers or recovery engines.

**Architecture:** Treat Phase-5 recovery/persistence and Phase-2 intent consumption as authoritative. Add only missing regression guards. Existing stronger V2 behavior is referenced rather than rewritten.

**Tech Stack:** Python, pytest, SQLite, existing V2 Paper/Recovery/IntentGuard modules.

**Spec:** `docs/v1-salvage-reference/ADOPTION_MATRIX.md` on `v1-manual-salvage-reference-20260929`.

## Global Constraints

- No duplicate idempotency ledger, Paper engine, recovery coordinator, or order authority.
- Restart/reconnect never auto-arms.
- `READY_FOR_RESUME` still requires explicit manual resume authority.
- Corrupt/missing recovery state fails closed.
- `RiskGateV2` remains sole executable-order authority.
- Live remains READ_ONLY/DISARMED.

## Review Focus

- Duplicate checkpoint identity must never silently overwrite earlier evidence.
- Restart replay of consumed intent/client-order identity must stay rejected.
- Corrupt checkpoint fingerprint must fail closed.
- Missing checkpoint-referenced order/position must fail closed.
- Clean recovery may reach READY_FOR_RESUME but never auto-resume.

---

### Task 1: Map V1 behaviors to current V2 authorities

**Files:**
- Create: `docs/v1-salvage-integration/SLICE2_RECOVERY_IDEMPOTENCY.md`

- [ ] Record current recovery, persistence, intent-guard, and V1 legacy-test authorities.
- [ ] Mark superseded V1 behavior versus missing guard coverage.

### Task 2: Pin duplicate-checkpoint immutability

**Files:**
- Create: `tests_v1/test_v1_salvage_recovery_idempotency_compatibility.py`

- [ ] Save a canonical checkpoint.
- [ ] Attempt to save a second checkpoint with the same checkpoint ID but changed payload.
- [ ] Assert SQLite uniqueness failure and verify the original checkpoint remains authoritative.

### Task 3: Reuse existing stronger V2 replay/dedup evidence

**Files:**
- No runtime changes expected.

- [ ] Reference `tests_v1/test_v2_phase2_intent_guard.py` for same-intent replay rejection and restored-state client-order replay rejection.
- [ ] Reference Phase-5 persistence/recovery tests for corrupt/missing-state fail-closed behavior and manual-resume gating.
- [ ] Do not duplicate those implementations/tests unless a real coverage gap is found.

### Task 4: Verification report

**Files:**
- Create: `docs/v1-salvage-integration/SLICE2_VERIFICATION.md`

- [ ] Record exact changed files.
- [ ] Record existing current V2 evidence reused by the slice.
- [ ] Record runner/test limitations truthfully.
- [ ] Keep merge readiness unclaimed until full regression runs.
