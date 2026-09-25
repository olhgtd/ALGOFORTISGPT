# Phase 5 P5-01 Implementation Evidence

**Slice:** P5-01 — Contracts + operational state  
**Branch:** `v2-phase5-paper-recovery`  
**Safety:** Live remains `READ_ONLY/DISARMED`; no real-broker mutation path.

## Execution rulings

- **CI trigger ruling:** the inherited verification workflow currently auto-runs only for pull requests targeting `main`. PR #8 is canonically stacked on `v2-phase4-strategy-research-backtest`, so for RED/GREEN evidence it may be temporarily retargeted to `main`, then restored immediately after evidence is captured. This is a CI-only workaround and never merge authorization.
- **Isolation ruling:** connector-based implementation has no local filesystem checkout/worktree. The dedicated `v2-phase5-paper-recovery` branch is the isolated mutation boundary; `main` and the Phase-4 branch remain untouched by Phase-5 commits.

## TDD ledger

### Task 1 — Phase-5 paper contracts

- RED test commit: `487c422fa4e81f0e916f8a848f4c94588fc0a600`
- Production implementation: not present at RED checkpoint.
- Expected RED reason: `ModuleNotFoundError` / import failure for `engine.paper.contracts_v2`.

Further exact-head run IDs and GREEN evidence are appended by later P5-01 commits.
