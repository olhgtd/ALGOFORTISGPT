# Manual V1 Path & Capability Map

This map records high-value V1 source locations/components already identified in the manual build/audit evidence. Exact final-manual-V1 bytes may still require Drive retrieval if the file was never pushed to Git.

## Desktop/runtime/product shell

| V1 path/component | What it did | Current destination/use |
|---|---|---|
| `START_ALGOFORTIS.pyw` | desktop launch entry | current desktop launcher/runtime lifecycle |
| `build/tools/AlgoFortisLauncher.cs` | native window/WebView2 launcher | current Windows shell; adapt, do not blindly overwrite |
| `dashboard/runtime/controller.py` | local runtime start/stop/control | current runtime host/control boundary |
| `dashboard/runtime/application.py` | app/runtime assembly | current host/application composition |
| `dashboard/runtime/paths.py` | Program Files/LocalAppData path rules | preserve deployment/path invariants |
| `dashboard/runtime/deployment_profiles.py` | DESKTOP_LOCAL / WINDOWS_VPS / REMOTE_ENGINE profiles | architecture reference for current deployment profiles |

## Identity / security

| V1 path/component | What it did | Current destination/use |
|---|---|---|
| `dashboard/backend/security_store.py` | users/security persistence | schema/migration/test reference; current auth authority wins |
| `dashboard/backend/security.py` | security service logic | adapt selected controls |
| `dashboard/backend/session_manager.py` | access/refresh token family handling | current session contracts |
| `dashboard/backend/auth_policy.py` | login limits, activation/device/recovery policy | current auth/device/recovery policy |
| `dashboard/backend/device_identity.py` | local cryptographic device identity | current device-binding abstraction/reference |
| `dashboard/backend/data_sovereignty.py` | local-only trading/secrets rules | permanent data-boundary invariant |
| credential vault under `%LOCALAPPDATA%\AlgoFortis\Security\Vault` | DPAPI-protected broker credentials | current local secret provider; never centralize secrets |
| `dashboard/web/src/visual-lab/secure-entry/LocalLoginCard.tsx` | local login UX | salvage premium UX only; current auth service underneath |
| `dashboard/web/src/visual-lab/secure-entry/LocalOwnerSetupCard.tsx` | first-run Owner setup UX | salvage UX/flow patterns |
| `dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx` | secure entry routing | current secure opening surface |

## API/UI boundary

| V1 path/component | What it did | Current destination/use |
|---|---|---|
| `dashboard/backend/api.py` | versioned local API and RBAC routes | current backend API boundary; salvage tests/semantics selectively |
| `dashboard/backend/engine_client.py` | UI↔engine separation | preserve principle; current ports/read-model clients authoritative |
| `dashboard/web/src/api.ts` | frontend API client | current user/owner client boundary |
| `dashboard/web/src/contracts.ts` | frontend/backend DTO contracts | map useful DTO semantics into current contracts |

## Backup / release / platform

| V1 path/component | What it did | Current destination/use |
|---|---|---|
| `dashboard/backend/backup_service.py` | `AlgoFortisBackup/v1`, restore validation, secret exclusion | high-priority salvage; preserve contract and security tests |
| `dashboard/backend/update_service.py` | update manifest/payload verification foundation | current release/update track |
| `dashboard/backend/entitlement_service.py` | offline entitlement foundation | current Platform/Account track reference |
| `dashboard/backend/telemetry_service.py` | privacy/redaction telemetry foundation | current opt-in telemetry track |
| `build/tools/build_installer.ps1` | Windows installer build | current installer pipeline reference |
| `build/tools/stage_app.ps1` | staging product payload | current reproducible packaging flow |

## Paper / Live-safe / state

| V1 path/component | What it did | Current destination/use |
|---|---|---|
| `dashboard/backend/live_workspace_service.py` | strategy state save/load/hydrate/autosave | current persistence/recovery adapter |
| `dashboard/backend/orders_portfolio_service.py` | order/position projection and dedup | current canonical read models/projections |
| `idempotency_ledger.py` | replay protection / operation identity | V2 idempotency/reconciliation behavior and tests |
| `broker_order_records.py` | broker-order worklist/lifecycle records | current broker/reconciliation state model |
| historical Paper/live-market-Paper services | simulated execution | current V2 Paper authority only; do not duplicate engine |

## Broker/data capability families

The final V1 certification identified useful read-side foundations for:

- Upstox catalog/quote/WebSocket/token handling;
- Zerodha/Kite catalog/quote/token handling;
- Dhan catalog/quote/token handling;
- Angel One catalog/quote/token handling;
- HTTP 429/backoff normalization;
- quote normalization/read parity;
- reconciliation inputs.

Current use: salvage patterns/tests into current data gateway/broker adapters. Do not import old mutation authority.

## Product UI capability families

High-value visual/workflow source areas include:

- Owner dashboard application/screens;
- User dashboard application/screens;
- market/chart workspace;
- options workspace;
- Live readiness surface;
- orders/portfolio projections;
- backtest/Paper screens;
- strategy add/governance;
- access registry/users;
- reports/audit;
- security/system/settings.

Current use: preserve UX and complete workflows, but make every screen a client of current V2 services/read models. UI must never become trading truth or execution authority.

## Test families worth locating first when salvaging

Historical test names/evidence referenced:

- `tests_v1/test_paper_unification_lots_only.py`
- `tests_v1/test_live_paper_and_position_sizing.py`
- `tests_v1/test_p1_signal_contract.py`
- `tests_v1/test_p1_token_key.py`
- `tests_v1/test_g01_projection.py`
- `tests_v1/test_g02_idempotency_ledger.py`
- `tests_v1/test_p3_g15_open_ledger.py`
- `tests_v1/test_p3_g16_executable_spec.py`
- `tests_v1/test_p3_g17_projection_dedup.py`
- `tests_v1/test_p3_g18_state_persistence.py`
- `tests_v1/test_p1_g03_broker_catalogs.py`
- `tests_v1/test_p1_g04_quote_normalization.py`
- `tests_v1/test_p1_g05_token_lifecycle.py`
- `tests_v1/test_p1_g10_read_throttle.py`
- `tests_v1/test_p1_g12_live_resume.py`
- `tests_v1/test_p1_g13_read_parity.py`
- `tests_v1/test_p1_g07_reconciler_bridge.py`
- `tests_v1/test_p1_g08_unknown_state.py`
- `tests_v1/test_area14_live_reconciliation_restart.py`
- `tests_v1/test_p2_security.py`
- `tests_v1/test_local_desktop_auth.py`
- `tests_v1/test_p1_root_failclosed.py`
- `tests_v1/test_p1_promote_auth.py`
- `tests_v1/test_p1_owner_governance.py`
- `tests_v1/test_owner_user_management.py`
- `tests_v1/test_api_hardening.py`
- `tests_v1/test_area4_ui_integration_readiness.py`

Where these tests still exist in current Git, use them as first-line historical behavioral evidence. Where absent, retrieve/reconstruct only the needed test from the manual V1 source package.

## Selection rule

For an exact V1 path:

1. check current branch/history first;
2. compare behavior against current V2 contract;
3. port the regression test before runtime code where practical;
4. retrieve Drive source only when the current tree does not contain the required final-manual-V1 implementation;
5. never transplant an old authority merely because the file exists.
