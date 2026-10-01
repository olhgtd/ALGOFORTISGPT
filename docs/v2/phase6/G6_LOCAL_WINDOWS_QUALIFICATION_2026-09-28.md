# Phase 6 Local Windows Qualification Evidence — 2026-09-28

## Scope

This document records fresh local Windows qualification evidence for the Phase 6 multi-broker read-only transport implementation.

Tested branch:

`v2-phase6-multibroker-transport-impl`

Tested code head:

`8b27ac257bc9e33fd42292bdb9293b4bf540f718`

Environment observed during the run:

- Windows PowerShell
- Python `3.13.14`
- short pytest temp root mapped to `T:\`
- `PYTHONPATH` set to the repository root
- test-only insecure ACL flags enabled for the qualification environment

This is local Windows evidence only. It does not replace the required hosted exact-head dual-Windows G6 qualification.

## Fresh observed results

### Structural and static gates

- compile: PASS
- module boundaries: PASS
- Phase 6 static mutation firewall: PASS
- static firewall output: `PHASE6_LIVE_READONLY_STATIC_PASS: multi-broker mutation capability absent and read-only boundary locked`

### Phase 6 focused suite

- discovered Phase 6 test files: `33`
- result: `176 passed, 1 skipped`

### Cross-phase regressions

- Data V2 live-feed regression: `7 passed`
- RiskGate authority regression: `7 passed`
- Phase 5 safety regression: `126 passed`
- S2 device/session dependency regression: `65 passed`

### Deterministic G6 probe

Two consecutive local probe runs were byte-identical.

Observed markers:

```text
SCHEMA=algofortis-g6-readonly-evidence/v2
BROKER_BOUNDARY=V2_ISOLATED_READ_ONLY
BROKER_SCOPE=ANGELONE,ZERODHA,DHAN,UPSTOX
CROSS_BROKER_FAILOVER=DISABLED
FEED_HEALTH_HANDOFF=DATA_V2_FEED_MONITOR
FOREIGN_ACTIVITY_INCIDENT_MODEL=PHASE5_SHARED
G6_ENABLES_REAL_MONEY_TRADING=NO
LIVE_STATE=READ_ONLY/DISARMED
MARKET_DATA_TRANSPORT=SHARED_RUNTIME_THIN_DRIVERS
QUEUE_OVERFLOW=FAIL_CLOSED
REAL_BROKER_MUTATION_CAPABILITY=ABSENT
RECONCILIATION_AUTHORITY=LIVE_RECONCILER
RISK_GATE_FEED_BLOCK=DAT_005_008_EXISTING_PATH
SEQUENCE_KEY=CONNECTION_GENERATION+INSTRUMENT_TOKEN
SOURCE_SEQUENCE=EXPLICIT_SEMANTICS_NO_FABRICATION
STALE_GENERATION=REJECTED
TRANSPORT_HEALTH=LOWER_LEVEL_ONLY
FINGERPRINT=71acbc5355797fb011d68240e4ce943750b5a07e9567143be024bc9a3f9bf089
```

### Full project regression

- result: `783 passed, 1 skipped, 1 warning`
- warning observed: Starlette TestClient / AnyIO `BlockingPortal` deprecation warning; not a test failure

### Regression certification

- self-contained architectural tests: `13` passed
- final output: `=== REGRESSION VERIFICATION: ALL PASS ===`

## Safety assertions supported by the run

- `LIVE_STATE=READ_ONLY/DISARMED`
- `REAL_BROKER_MUTATION_CAPABILITY=ABSENT`
- `G6_ENABLES_REAL_MONEY_TRADING=NO`
- `CROSS_BROKER_FAILOVER=DISABLED`
- transport health remains lower-level evidence and reaches the trading safety boundary through the existing Data V2 / RiskGate path

## Qualification status

Local Windows qualification for tested code head `8b27ac257bc9e33fd42292bdb9293b4bf540f718` is GREEN.

Formal G6 remains **NOT QUALIFIED** until fresh hosted exact-head qualification executes successfully on both required Windows environments and the deterministic comparison job passes. GitHub-hosted Actions quota is currently exhausted, so that external evidence gate is deferred until quota reset.
