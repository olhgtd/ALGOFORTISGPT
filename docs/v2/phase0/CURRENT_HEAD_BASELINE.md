# AlgoFortis V2 — Phase 0 Current-Head Baseline

**Status:** IN PROGRESS — audit evidence, not a G0 PASS declaration  
**Date:** 2026-09-21  
**Phase 0 start commit:** `96223c0757004e29b89fe5a00a4aa606957403d2`  
**Working branch:** `v2-phase0-baseline-audit`  
**Safety posture:** `READ_ONLY=true`, `DISARMED=true`; no live broker mutation is authorized by this baseline.

## 1. Purpose

This file separates three things that must not be conflated:

1. **Historical V1 RC evidence** — what was certified on 2026-09-15.
2. **Current source inspection** — what the current repository code contains.
3. **Fresh current-head execution evidence** — tests/CI that must run from this branch before G0 can pass.

Historical PASS evidence is never treated as a fresh PASS for current HEAD.

## 2. Historical V1 RC reference

`docs/releases/ALGOfORTIS_LOCAL_V1_RC1_BASELINE.md` records:

- Local V1 RC1 status `RELEASE CANDIDATE PASS`, frozen 2026-09-15T16:18:00Z.
- `python -m pytest tests_v1 -q`: 146/146 PASS at that frozen baseline.
- Database, API, engine, auth/security, backup/DR, installer and desktop certification scripts recorded PASS.
- Safety baseline: `READ_ONLY=true`, `DISARMED=true`, `live_global_hold=true`, broker mutation ZERO, real broker connection NONE.
- BACKTEST and PAPER available; LIVE fail-closed/disarmed.

This is reference evidence only until the current branch is freshly re-run.

## 3. Current repository/runtime identity

- Runtime lock explicitly targets **CPython 3.13.14**.
- Locked runtime dependencies are recorded in `requirements-runtime.lock.txt` / `.json`.
- Dashboard dependencies are isolated in `requirements-dashboard.in`.
- Existing regression harness: `build/tools/run_regression_certification.py`.
- Primary current V1 test area: `tests_v1/`.
- Branch protection on `v2-phase0-baseline-audit` is currently disabled and there are no required status checks on that branch.
- No workflow run was observed for the Phase 0 start commit when the audit began; fresh verification automation is therefore a Phase 0 evidence task.

## 4. Critical V1 source baseline

| Domain | Current V1 evidence | Phase 0 classification |
|---|---|---|
| Risk | `engine/risk/risk_manager.py`: deterministic pre-order RiskGate, Decimal normalization, fail-closed missing/invalid evidence, daily-loss/trade/open-position/portfolio controls, LONG/BUY-to-open activation | **PRESERVE / WRAP** |
| Order request | `engine/orders/model.py`: `OrderRequest` is explicitly validated and non-executable; concrete open/close instructions preserve provenance | **PRESERVE / WRAP** |
| Order lifecycle | `engine/orders/lifecycle.py`: explicit immutable transition table with CREATED, VALIDATED, QUEUED, CANCELLED, REJECTED, EXPIRED, FILLED | **PRESERVE / EXTEND** |
| Audit | `engine/audit/model.py`: versioned audit envelope/taxonomy, deterministic event identity support and fail-closed integrity concepts | **PRESERVE / WRAP** |
| Strategy | `engine/strategy/base.py`: broker/data-source-agnostic strategy interface v1.0, Signal contract and state schema | **PRESERVE / EXTEND** |
| Live readiness | `dashboard/backend/live_readiness_service.py`: explicit READ_ONLY/SHADOW boundary, `mutation_allowed=False`, `require_live_mutation()` raises, real broker mutation stated ZERO | **PRESERVE AS HARD SAFETY BASELINE** |
| Reproducibility | `engine/reproducibility/` and canonical codec/fingerprint usage are present across risk/order/audit code | **PRESERVE / AUDIT COVERAGE** |
| Broker/read layer | Existing broker adapters and read-only/live-read modules exist; current V2 must capability-gate any mutating adapter paths | **AUDIT / WRAP** |
| Reconciliation/restart | Existing reconciliation and restart tests/modules exist | **PRESERVE / EXTEND** |
| Auth/security | Existing V1 architectural/security tests cover device identity, token families, recovery and isolation | **PRESERVE** |

## 5. Confirmed V2 structural gaps at audit start

These are gaps relative to the V2 contracts, not claims that V1 is defective:

1. **Formal `ApprovedOrder` capability is absent** from current source search. V2 requires an executable capability that only RiskGate can mint.
2. **Formal `IN_DOUBT` lifecycle state is absent** from current source search. Current lifecycle uses the V1 pre-execution vocabulary and must be extended without breaking historical semantics.
3. **Strategy SDK V2 lifecycle/manifest/promotion evidence is not yet represented by the current v1.0 StrategySignalGenerator contract.**
4. **Complete Clock/SeedSource/IdGenerator injection across domain code is not yet proven.** Existing centralized/canonical helpers are useful foundations but coverage needs an architecture audit.
5. **Module-boundary CI enforcement is not currently a required branch check.**
6. **Current-head golden regression and two-clean-environment reproducibility evidence have not yet been produced in Phase 0.**
7. **Dataset catalog with immutable version/checksum/provenance/licence evidence for every V1 research dataset remains to be proven.**

## 6. Phase 0 severity posture

- **P0 discovered so far:** none declared from source inspection alone.
- **P1 discovered so far:** none declared from source inspection alone.
- **Unverified areas:** current-head test execution, full contract map, data provenance/golden evidence.

No `zero P0/P1` G0 claim is valid until the whole audit and fresh regression run finish.

## 7. Next evidence

1. Produce `V1_CONTRACT_FREEZE.md` and `V1_GAP_REGISTER.md` from code-level mapping.
2. Add a non-mutating Phase 0 CI workflow on the isolated branch.
3. Run fresh `tests_v1` and portable certification checks on clean Windows runners using Python 3.13.
4. Build golden/reproducibility evidence and only then evaluate G0.
