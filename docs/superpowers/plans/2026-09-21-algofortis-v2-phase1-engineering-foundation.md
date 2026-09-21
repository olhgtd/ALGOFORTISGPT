# AlgoFortis V2 Phase 1 — Engineering Foundation Implementation Plan

**Goal:** Build the additive V2 engineering foundation on the frozen V1 baseline without rewriting working V1 components or weakening READ_ONLY/DISARMED safety.

**Architecture:** Add versioned cross-cutting contracts and infrastructure behind stable module boundaries. V1 code is wrapped or adapted where needed; production behavior changes require RED→GREEN tests. Deterministic core services receive time, randomness and identifiers by injection. CI remains exact-head and preserves the Phase 0 golden baseline.

**Tech stack:** Python 3.13.14, pytest 9.1.1, GitHub Actions on Windows Server 2025/2022, existing AlgoFortis runtime/dashboard dependency closures.

**Specification authority:** `ALGOFORTIS_V2_REQUIREMENTS.md`, `ALGOFORTIS_V2_ARCHITECTURE.md`, `ALGOFORTIS_V2_IMPLEMENTATION_PLAN.md`, `ALGOFORTIS_V2_OWNER_DECISIONS.md`, Phase 0 freeze evidence, ADR-001 and ADR-008.

## Global constraints

- Live execution remains `READ_ONLY=true` and `DISARMED=true`; Phase 1 adds no broker mutation path.
- Preserve V1 contracts and Phase 0 deterministic fingerprints unless an explicit versioned contract change is approved.
- No test weakening or deletion to obtain green status.
- Domain logic must not gain adapter/UI/transport dependencies.
- Security- or audit-critical uncertainty fails closed.
- New cross-cutting contracts are versioned/additive; no big-bang rewrite.
- OD-V2-14 must be frozen before registry implementation; V2.0 scope is the recommended internal registry only.

## Review focus

Determinism, module boundaries, migration rollback, audit integrity, secret safety, correlation/version provenance, and proof that no Phase 1 change can arm or mutate a live broker.

---

## Task P1-01 — Injectable Clock / SeedSource / IdGenerator

**Files:**
- Add `tests_v1/test_v2_phase1_runtime_primitives.py`
- Add `engine/core/runtime.py`

**RED:**
1. Add contract tests before implementation.
2. Run the exact-head PR CI and record the expected import/contract failure.

**Minimal implementation:**
1. Add typed `Clock`, `SeedSource`, and `IdGenerator` protocols matching Architecture §4.1.
2. Add production system implementations plus deterministic test/replay implementations.
3. Require UTC-aware wall-clock values, monotonic time, stable scoped seeds, and deterministic scoped IDs for replay.
4. Validate malformed scopes/seed inputs fail closed.

**GREEN:**
1. `python -m pytest tests_v1/test_v2_phase1_runtime_primitives.py -q`
2. `python -m pytest tests_v1 -q`
3. `python build/tools/run_regression_certification.py`
4. Phase 0 golden fingerprint probe remains unchanged on both clean Windows runners.

**Commit:** `feat(v2): add injectable runtime primitives`

---

## Task P1-02 — Module-boundary enforcement

**Files:** architecture checker/config plus focused tests and CI integration.

**RED:** Add fixtures proving forbidden Domain→Adapter/UI/Transport imports and live-adapter imports from BACKTEST/PAPER are rejected.

**Implementation:** Add the smallest repository-aware boundary checker needed for AF2-OPS-002; avoid introducing a second dependency graph authority.

**GREEN:** Boundary checks fail on deliberate violations and pass on the current repository; existing suite/golden checks remain green.

---

## Task P1-03 — Immutable config snapshot service

**RED:** Tests for layered resolution, immutable snapshot identity, secret exclusion, deterministic fingerprint and invalid-config failure.

**Implementation:** Add config port/service that resolves explicit layers to immutable versioned snapshots and binds existing reproducibility configuration identity.

**GREEN:** Snapshot replay is exact across two CI environments and V1 configuration fingerprints remain stable.

---

## Task P1-04 — Hash-chained audit ledger foundation

**RED:** Tests for sequence monotonicity, `prev_hash` linkage, tamper detection, required version provenance and critical write failure.

**Implementation:** Extend/wrap the existing audit envelope and durable sink rather than replacing V1 audit code.

**GREEN:** Tampering is detected; critical audit failure is fail-closed; legacy audit tests remain green.

---

## Task P1-05 — Structured logging + correlation IDs

**RED:** Tests for correlation propagation, redaction and forbidden secret material.

**Implementation:** Add structured event/log context compatible with existing telemetry redaction; no credential/account secret values in logs.

**GREEN:** Correlated records are deterministic where required and secret fixtures are absent from emitted text.

---

## Task P1-06 — Migration runner with pre-backup + rollback

**RED:** Tests prove migration refusal without backup, successful migration, deterministic schema versioning, failed migration rollback and restart safety.

**Implementation:** Minimal local migration framework using existing backup contracts where possible.

**GREEN:** A migration backs up, applies and rolls back under injected failure in CI.

---

## Task P1-07 — Internal adapter registry

**Entry gate:** OD-V2-14 FROZEN to V2.0 internal-registry-only scope.

**RED:** Tests for duplicate IDs, incompatible versions, undeclared permissions/capabilities and external package loading attempts.

**Implementation:** Internal manifests, compatibility/capability checks and explicit registration only. No third-party package loading or sandbox system in V2.0.

**GREEN:** Registry conformance tests pass and prohibited dynamic/external registration fails closed.

---

## Task P1-08 — CI foundation hardening

Add architecture checks, compile/lint/type checks where supported by the locked repo, dependency/secret scanning and migration validation without weakening the exact-head two-environment regression/golden workflow.

Every added check must have a repository-local reproducible command and actionable failure output.

---

## Task P1-09 — G1 evidence and gate review

Create `docs/v2/phase1/G1_EVIDENCE.md` only from fresh evidence.

G1 passes only when:
- CI blocks module-boundary violations;
- migration backup/apply/rollback test is green;
- required audit events carry versions and chain evidence;
- runtime determinism/config snapshot tests are green;
- Phase 0 golden suite remains green across both clean environments;
- no open Phase 1 P0/P1 finding exists;
- live mutation remains unreachable while DISARMED.
