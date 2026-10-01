# Phase 7 Local Windows Qualification Evidence — 2026-09-28

## Scope

This document records fresh local Windows qualification evidence for the Phase 7 Portfolio & Risk V2 implementation.

Tested branch:

`v2-phase7-portfolio-risk-impl`

Tested code head:

`118a2d79846f5339b60547b799364ab3c6ee2466`

Environment observed during the run:

- Windows PowerShell
- Python 3.13.14 project environment
- short pytest temp root mapped to `T:\`
- repository root used as `PYTHONPATH`

This is local Windows evidence only. It does not replace the required hosted exact-head dual-Windows G7 qualification.

## Fresh observed results

### Architecture guard fix verification

- `tests_v1/test_phase7_architecture_guard.py`: `3 passed`
- the guard continues to reject forbidden `ApprovedOrder` construction/minting; only the diagnostic wording was aligned with the existing regression expectation

### Complete Phase 7 focused suite

- result: `52 passed`

### Deterministic G7 probe

Two consecutive local probe runs were byte-identical.

Observed markers:

```text
APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY
PORTFOLIO_BUDGETS=VERSIONED_EXPLICIT
CAPITAL_RESERVATION=ATOMIC_FAIL_CLOSED
PORTFOLIO_EXPOSURE=THROUGH_RISK_GATE
CIRCUIT_BREAKER=STICKY_ENTRY_POLICY
EVENT_RISK=SCHEDULED_VERSIONED_NO_SILENT_RESIZE
LIVE_STATE=READ_ONLY/DISARMED
G7_ENABLES_REAL_MONEY_TRADING=NO
FINGERPRINT=014f0fddfeadf5e6f96ab93235b45a363f81c3b09f72bf266311cdd90f2c7c72
```

### Full project regression

- result: `468 passed, 1 warning`
- warning observed: Starlette TestClient / AnyIO `BlockingPortal` deprecation warning; not a test failure

### Regression certification

- self-contained architectural tests: `13` passed
- final output: `=== REGRESSION VERIFICATION: ALL PASS ===`

## Safety assertions supported by the run

- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- portfolio exposure/admission remains through the existing RiskGate path
- `LIVE_STATE=READ_ONLY/DISARMED`
- `G7_ENABLES_REAL_MONEY_TRADING=NO`
- no new broker-mutation or Live-arm authority is introduced by Phase 7

## Qualification status

Local Windows qualification for tested code head `118a2d79846f5339b60547b799364ab3c6ee2466` is GREEN.

Formal G7 remains **NOT QUALIFIED** until fresh hosted exact-head qualification executes successfully on both required Windows environments and the deterministic comparison job passes. GitHub-hosted Actions quota is currently exhausted, so that external evidence gate is deferred until quota reset.
