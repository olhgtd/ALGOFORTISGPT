# Manual V1 Certified Scope

This file records **what the manually-built V1 was actually certified to provide**, rather than treating every old plan or design document as implemented truth.

## Final certification evidence

The final manual V1 certification recorded:

- Python suite: **909 PASS / 0 FAIL**
- Frontend Vitest: **24 PASS / 0 FAIL**
- TypeScript typecheck: **PASS**
- Production frontend build: **PASS**
- Lots → quantity regression: **44 tests PASS**
- Live safety suite: **PASS**
- Live mutation deny routes: **18/18 intact**
- `mutation_allowed = False`
- `broker_mutation_blocked = True`
- `mutation_attempted = 0`
- P0/P1/P2/P3 open: **0 / 0 / 0 / 0**
- Owner dashboard: **COMPLETE, 0 broken flows**
- User dashboard: **COMPLETE, 0 broken flows**

## Certified product/runtime capabilities

### Strategy and research

- strategy upload/paste workflow;
- strategy validation/governance;
- historical backtesting;
- walk-forward/OOS workflow foundations;
- lots → authoritative contract quantity chain;
- strategy state persistence.

### Paper and market simulation

- historical Paper simulation;
- live-market Paper using live quote inputs with simulated execution;
- isolated Paper ledger;
- Paper execution prevented from becoming real broker mutation.

### Live-safe foundation

V1 Live was **execution-intent/readiness only**.

It was not a real-money live execution release.

Certified safety posture:

```ini
READ_ONLY=true
DISARMED=true
live_global_hold=true
broker_mutation=ZERO
real broker connection=NONE
```

### Broker foundation

Read-side/foundation coverage existed for:

- Upstox;
- Zerodha/Kite;
- Dhan;
- Angel One.

Useful capabilities included instrument/catalog resolution, quote normalization, token lifecycle, throttling/backoff/read parity patterns, and reconciliation inputs.

Real place/modify/cancel remained outside the certified V1 scope.

### Recovery and execution-state integrity

Certified/verified areas included:

- idempotency ledger / replay protection;
- broker-order worklist/state model;
- projection deduplication;
- restart/reattach state hydration;
- corrupt-state fail-closed behavior;
- reconciliation foundations;
- order/position projection foundations.

### Security/account foundations

Verified areas included:

- Owner/User RBAC separation;
- local private desktop authentication;
- WebAuthn/FIDO2 foundations and strict origin/RP validation in applicable profiles;
- scrypt password hashing in local-private mode;
- refresh-token rotation and reuse-family revocation;
- max-device/no-silent-eviction controls;
- high-assurance recovery semantics;
- broker credential vault using Windows-protected storage;
- secret redaction and zero observed real-secret leakage in the final scan;
- local data/secrets sovereignty.

### Backup / installation / desktop productization

Certified/implemented foundations included:

- `AlgoFortisBackup/v1`;
- backup SHA-256 validation;
- secret/private-key exclusion;
- Zip Slip/path traversal rejection;
- WAL-safe SQLite operational backup;
- install/reinstall/uninstall lifecycle;
- Program Files vs LocalAppData separation;
- WebView2 native Windows desktop shell;
- Windows installer build path;
- update manifest/checksum foundations;
- telemetry/privacy redaction foundations.

## V1 UI/product surfaces worth preserving

The V1 product had substantial implementation around:

- secure entry / opening flow;
- Owner dashboard;
- User dashboard;
- market/chart surfaces;
- options workspace;
- Live readiness;
- orders and portfolio;
- backtest and Paper screens;
- strategy add/governance workflows;
- access registry;
- users/roles administration;
- reports/audit UX;
- security/system/settings;
- runtime availability handling.

## Explicitly outside the final V1 proof

The final V1 certification **did not prove**:

- production AWS account authority deployment;
- production remote/VPS engine deployment;
- real-money broker mutation;
- complete cloud/mobile product;
- complete native WebSocket streaming for every broker;
- public auto-update distribution/signing infrastructure;
- all future commercial/licensing infrastructure;
- every historical implementation-plan stage exactly as originally written.

## Interpretation rule

The correct interpretation is:

> Manual V1 was a mature, heavily-tested, locally-operating, safety-locked product baseline. It is not evidence that deferred cloud/live/commercial capabilities were already production-complete.
