# AlgoFortis V2 Phase 4 — Strategy SDK, Research & Backtest V2 Implementation Plan

> **Execution rule:** implement task-by-task with strict RED → GREEN → fresh regression verification. Preserve all Phase-0/1/2/3 behavior and frozen golden fingerprints.

**Goal:** Build a deterministic Strategy SDK, research/experiment system and realistic Backtest V2 that can generate auditable promotion evidence while remaining research/paper-only and `READ_ONLY` / `DISARMED`.

**Canonical scope:** STR-001/002/003; RSH-001…005; BKT-001…005; ORB ported as the reference strategy.

**Frozen inputs:** OD-V2-11 and OD-V2-17 plus ORB protective-policy governance in `docs/v2/adr/ADR-012-phase4-research-promotion-and-orb-policy.md`.

## Global constraints

- No broker mutation, no live execution enablement, no auto-arm, no live adapter loading.
- Preserve Phase-2 RiskGate authority and Phase-3 feed/data licensing behavior.
- Backtest P&L or any single metric can never independently promote a strategy.
- Every experiment/search attempt must be ledgered; OOS/WFO evidence cannot be silently re-used as training input.
- Research randomness is injected/versioned and deterministic when a seed is supplied.
- Money/price/quantity/risk remain Decimal/fixed-point per OD-V2-12. Analytics floats require declared tolerance.
- ORB economics are never invented. Executable ORB simulation requires an explicit versioned protective-policy reference; test fixtures must be labelled `TEST_ONLY` and cannot become promotion evidence.
- Built-in promotion profile is `research-only/v1` and fail-closed `NON_PROMOTABLE` until an explicit evidence-backed numeric profile exists.

---

## P4-01 — Strategy SDK v2 contracts and deterministic state

**Requirements:** STR-001, STR-003; foundations for STR-002.

**Create:**
- `engine/strategy/contracts_v2.py`
- `engine/strategy/state_v2.py`
- `tests_v1/test_v2_phase4_strategy_sdk.py`

**Contracts:**
- immutable `StrategyManifestV2` with strategy/version/interface, parameter schema, required datasets/data kinds, timeframes, supported instruments, dependency lock and optional protective-policy requirement;
- deterministic manifest fingerprint via `CanonicalCodec`;
- typed/frozen parameter definitions with bounds/enums and fail-closed validation;
- deterministic strategy-state envelope with schema version, strategy/version, state payload fingerprint, serialization and restore validation;
- lifecycle hook protocol that consumes supplied inputs only—no direct clock/network/broker dependency.

**RED tests:** deterministic fingerprint independent of mapping insertion order; invalid/ambiguous manifest rejected; dependency lock/version bound; parameter values validated; state round-trip stable; wrong strategy/version/schema or tampered state rejected; executable policy requirement cannot be bypassed.

**Done when:** focused tests GREEN; full suite, architecture certification and golden probes GREEN on dual Windows.

---

## P4-02 — ORB reference port to Strategy SDK v2

**Requirements:** STR-001/003; reference-port deliverable.

**Create/extend:**
- `strategies/orb/orb_v2.py`
- `strategies/orb/manifest_v2.py`
- `tests_v1/test_v2_phase4_orb_reference.py`

**Rules:**
- preserve `strategies/orb/` boundary; no broker imports;
- manifest declares 5m/current required data seam and instrument support without assuming future asset classes;
- signal logic is deterministic and testable from supplied data/state;
- executable simulation requires `protective_policy_ref`; no ATR/R:R/trailing production default is embedded;
- test-only protective fixture is clearly non-promotion evidence.

**RED tests:** HOLD/BUY/SELL behavior from frozen signal inputs; deterministic state; missing protective policy blocks executable-simulation preparation; no strategy path emits an executable order.

---

## P4-03 — Experiment registry and append-only trials ledger

**Requirements:** RSH-001, RSH-005.

**Create:**
- `engine/research/experiments.py`
- `engine/research/trials.py`
- `tests_v1/test_v2_phase4_experiment_tracking.py`

**Evidence identity:** experiment ID/fingerprint binds code/strategy version, dataset versions, config snapshot, seed, environment fingerprint, parent lineage, tags/notes and trial budget.

**Rules:** every attempted trial is append-only, including failed/rejected/early-stopped attempts; duplicate/conflicting trial IDs fail closed; trial count cannot decrease or be rewritten.

---

## P4-04 — Budgeted grid/random search and parameter stability

**Requirements:** RSH-002 T1.

**Create:**
- `engine/research/search.py`
- `engine/research/stability.py`
- `tests_v1/test_v2_phase4_search_budget.py`

**Rules:** deterministic grid ordering; seeded random search; explicit max-trials budget; early stopping produces ledger evidence; OOS observations cannot increase/reopen the search budget; parameter-stability report is deterministic.

Bayesian optimization/parallel optimizer is T2 and excluded.

---

## P4-05 — Validation split authority and robustness/stress evidence

**Requirements:** RSH-003, RSH-004.

**Create/extend:**
- `engine/research/validation_v2.py`
- reuse Phase-0/V1 `engine.backtest.validation` and `walk_forward` calculations where their contracts are already deterministic;
- `tests_v1/test_v2_phase4_research_validation.py`

**Rules:** train/validation/test ownership is explicit; WFO/OOS mandatory for promotion evidence; bootstrap/Monte Carlo/sensitivity/regime/cost/slippage/delay/missing/bad-feed stress evidence is versioned; no look-ahead or split contamination; backtest P&L-only evidence rejects promotion.

---

## P4-06 — Deflated performance and backtest-overfitting evidence

**Requirements:** RSH-005; OD-V2-11.

**Create:**
- `engine/research/overfitting.py`
- `tests_v1/test_v2_phase4_overfitting.py`

**Rules:** versioned DSR/deflated-performance methodology plus PBO estimate; exact formulas/tolerances documented in module and evidence schema; trial count comes from the append-only ledger; insufficient/degenerate samples fail closed rather than manufacture confidence.

---

## P4-07 — Strategy lifecycle and promotion evidence authority

**Requirements:** STR-002, RSH-004; OD-V2-17.

**Create:**
- `engine/strategy/lifecycle_v2.py`
- `engine/strategy/promotion_v2.py`
- `tests_v1/test_v2_phase4_promotion.py`

**Lifecycle:** Draft → Research → Backtest → Validation → Paper → Eligible-for-Live evidence state.

**Rules:** immutable/versioned promotion profile; built-in `research-only/v1` is `NON_PROMOTABLE`; missing criteria or evidence yields deterministic rejection reasons; rollback/deactivation supported; no automatic transition arms or executes anything; eligible-for-live is evidence only while DISARMED.

---

## P4-08 — Backtest V2 execution realism, determinism, replay and no-lookahead

**Requirements:** BKT-001/002/003.

**Create:**
- `engine/backtest/v2/contracts.py`
- `engine/backtest/v2/execution.py`
- `engine/backtest/v2/replay.py`
- `tests_v1/test_v2_phase4_backtest_v2.py`
- `tests_v1/test_v2_phase4_no_lookahead.py`

**Models:** latency, spread, slippage, fees/taxes/brokerage, partial fill, rejection, liquidity cap, gap-through-stop and open/close edge behavior as explicit versioned inputs.

**Determinism:** same strategy/config/dataset/seed/execution-model → same event ordering, result fingerprint and replay ledger on both CI machines.

**No-lookahead:** future bars/events cannot be accessed by strategy/execution callbacks; invariant fails closed.

---

## P4-09 — Options-aware simulation and batch orchestration

**Requirements:** BKT-004 T1, BKT-005.

**Create:**
- `engine/backtest/v2/options.py`
- `engine/backtest/v2/batch.py`
- `tests_v1/test_v2_phase4_options_sim.py`
- `tests_v1/test_v2_phase4_batch.py`

**Options:** as-of lot size/expiry rules from Phase 3, explicit theta/IV/gamma/spread model inputs; no synthetic option data may qualify as promotion evidence under OD-V2-10.

**Batch:** local resource limits, deterministic job IDs, cancel/resume/retry/priority/worker-health state. Distributed workers remain T2 seam only.

---

## P4-10 — CI qualification and G4 evidence

**Create:**
- `build/tools/check_phase4_research_backtest.py`
- `tests_v1/test_v2_phase4_ci_guard.py`
- update `.github/workflows/v2-phase0-baseline.yml`
- qualification output: `docs/v2/phase4/G4_EVIDENCE.md`

**Static guard:** required Phase-4 authorities/tests exist; strategy/research/backtest V2 remains broker-neutral; no network/live-adapter imports; `research-only/v1`, trials-ledger and no-lookahead markers locked; ORB has no hardcoded production protective economics.

**Focused CI:** all Phase-4 tests on Windows latest and Windows 2022 / Python 3.13.14, followed by full `tests_v1`, architecture certification and frozen golden probes.

**G4 exit evidence:**
- reference ORB test/backtest fixture produces identical run fingerprint on both CI machines;
- automatic promotion evidence bundle generated, with built-in profile remaining non-promotable unless explicit criteria supplied;
- look-ahead invariant green;
- all prior Phase-0/1/2/3 gates and golden fingerprints remain green;
- evidence commit itself receives a fresh exact-head dual-Windows GREEN run before merge.
