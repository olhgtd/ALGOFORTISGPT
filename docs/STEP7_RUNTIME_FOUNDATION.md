# SentinelX V1 — Step 7 runtime foundation

This step introduces a relocatable Windows runtime foundation. It does not build
an installer, connect a broker, or complete roaming identity. Approved production
HTTPS WebAuthn transport is still required before production sign-in can work.

## Runtime entry and paths

`START_SENTINELX.pyw` is the windowless entry point for a future Windows shortcut.
It locates resources relative to itself, starts or reuses the private backend,
waits for readiness, and opens the returned local application URL. There are no
user-entered ports, npm commands, or uvicorn commands in this flow. A compatible
Python runtime with the existing application dependencies and the built frontend
must currently be present; supplying those in a final package is deferred.

`dashboard.runtime.paths.RuntimePaths` is the authoritative runtime layout.
It reuses the existing sensitive SQLite storage validator and the engine's
`SENTINELX_DATA_ROOT` configuration boundary. No engine path code was changed.

| Mode | Mutable root | Rules |
| --- | --- | --- |
| DEVELOPMENT | Installation-relative `.sentinelx-dev-data`, or an explicit development root | Existing manual development composition retained; no auto-seeding in the runtime launcher. |
| TEST | Explicit absolute directory below system temporary storage | Cannot overlap production data; launcher composition remains vacant; fixture runners own separate temporary databases. |
| PRODUCTION | `%LOCALAPPDATA%/SentinelX` | No data-root override, source-tree writes, developer preview, automatic records, or sample fallback. |

The production layout is:

```text
<install>/dashboard/web/dist/         immutable built frontend
<install>/dashboard/, engine/         application Python resources
%LOCALAPPDATA%/SentinelX/
  databases/
    security/sentinelx_security.sqlite3
    governance/sentinelx_governance.sqlite3
    core-audit.sqlite3
  config/
    identity.json                    reserved bootstrap subject, not a user record
    runtime.json                     stable OS-selected loopback port
  logs/backend.log
  cache/
  runtime/
    controller.lock
    backend.lock
    backend.json                     owned instance record and private control secret
  imports/                           imported data and metadata location
  users/                             registered strategy artifacts
```

The application creates private per-user directories without requiring elevation.
Windows ACL validation permits the current user and trusted OS/system administrator
principals; it rejects broad grants and redirected paths. Existing production
directories that fail validation are not silently repaired. Config and runtime
records use same-directory temporary files, flush/fsync, and atomic replacement.
Database WAL files remain beside their databases under the protected root.

No original Administrator/Downloads path is used by this runtime. The former
working-directory assumptions for `users/`, development storage, and historical
feed data are supplied explicitly by the composition. No historical data is
automatically copied into a product installation.

## Lifecycle and discovery

`RuntimeController.start/stop/restart/status` is the packaging-neutral API. The
Python module also exposes these actions for development and future shell use.
There was no existing product process controller to extend: the two development
PowerShell scripts start terminal/Vite processes and do not provide readiness,
safe process identity, durable configuration, or a built-frontend host. They remain
development tools; the new controller does not replace trading or auth services.

An OS file lock serializes controller actions and a separate lifetime lock prevents
duplicate backends. Kernel locks release after a crash. An instance nonce identifies
the actual server even when a Windows Python launcher has a different PID.
The controller records the server PID for diagnostics, but never kills a process
based solely on a persisted PID. Stop uses an authenticated, loopback-only control
request and uvicorn's graceful shutdown. The control secret is neither a bearer
session nor a browser capability; it is never sent in a URL or exposed to frontend
JavaScript. Control requests bypass system HTTP proxies and connect to numeric
loopback. A stale or forged record cannot authorize arbitrary process termination.

Start reports READY after the live server answers the private readiness check and
its security/governance stores and security-status projection are usable. Missing
assets, bad config, denied permissions, an occupied retained port, or unavailable
authority fail closed. Stop can still request graceful shutdown when data authority
has degraded. Startup timeout only targets the child handle created by that start
attempt; a hung/unresponsive backend is never replaced by killing arbitrary PIDs.

The backend binds to `127.0.0.1` and serves the frontend at `http://localhost:<port>`.
The port is initially selected by the OS and retained across restarts. Port
conflicts fail closed instead of silently changing an enrolled origin. Host and
Origin checks reject foreign origins and DNS-rebinding hostnames. No permissive
CORS or public bind is enabled.

The built HTML receives a runtime-mode marker. The frontend uses the existing
relative `/api/v1` clients; there is no second API URL service. A product readiness
boundary provides STARTING, READY, UNAVAILABLE and RECOVERING states. It times out
failed requests, unmounts the workspace on an outage, clears the in-memory bearer,
and reconnects to the retained origin. Relaunching the windowless entry restarts a
stopped/crashed server. The frontend does not launch OS processes from the browser.

## Identity and device authority

Existing `OwnerSetupFlow`, `ReturningUserFlow`, bootstrap-token validation, FIDO2
ceremonies, audit issuance and backend authorization remain authoritative. The
frontend first-run routing implementation is unchanged. The backend status now
reads durable enrollment readiness when that reader exists, so a process restart
does not erase enrolled-state truth. The primary-plus-backup authenticator
requirement remains intact; an incomplete or revoked set is not marked ready.

Local Owner identity is restored from the existing store. For a vacant store, a
stable bootstrap subject is reserved in config without inserting any Owner/user,
credential, session, or bootstrap authorization. Configuration metadata is not
proof of identity. Multiple local Owner records fail closed.

Cross-PC identity is **partially implemented as a provider boundary**. The
`IdentityProvider` protocol and `UnavailableRoamingIdentity` preserve the existing
local store and refuse unverified remote claims. `/api/v1/identity/roaming/verify`
returns 503. No Gmail/OTP/cloud identity service, account synchronization,
credential migration, or successful roaming login is simulated.

Production WebAuthn continues to require the approved `sentinelx.com` and
`sentinelx-recovery.com` HTTPS origins and existing mTLS policy. A local HTTP server
cannot impersonate those origins. Production runtime status truthfully reports
`local_auth_transport=UNAVAILABLE`, and production WebAuthn endpoints return 503
until an approved HTTPS transport/provider is integrated. TEST and DEVELOPMENT
retain the separately validated localhost ceremony profile. A future identity
integration must supply stable global subjects, approved-origin verification,
recovery, authenticated device enrollment/revocation, and authoritative account
and entitlement synchronization. Those capabilities are intentionally deferred.

The existing credential store is the device authority: absent credentials are
untrusted; verified enrollment creates a registered authenticator; terminal
revocation removes its trust while preserving its audit tombstone. A device here
means a WebAuthn authenticator, not an attested physical Windows PC. Installation
config, machine names, email text, or a copied token never establish device trust.
Physical-PC attestation and roaming device enrollment are deferred.

The existing Owner device APIs remain role/step-up protected. An authenticated
`GET /api/v1/security/devices` exposes only the caller's credential records.
Revoking or disabling credentials also invalidates that user's sessions. Because
legacy sessions lack a per-credential binding, revocation conservatively invalidates
all sessions for that user. Device removal is logical revocation, not audit deletion.
Last-seen and revocation timestamps are distinct; unavailable network/device
metadata is no longer replaced by fabricated workstation/IP/location details.
Legacy device session counts explicitly declare USER scope.

Browser bearer tokens remain memory-only. Closing/reopening the application asks
for authentication again; valid persisted server state is not permanent login.
Expired/revoked sessions and inactive identities remain denied by the existing
session service. An observed backend instance change clears browser authority and
remounts entry routing.

## Product UI authority boundaries

Product mode never enables the developer toolbar or agent routes through `dev=1`.
The remaining legacy user strategy-template and passkey-summary surfaces lack
authoritative product projections and are DISABLED / UNAVAILABLE in the product
runtime. They are not relabeled REAL. The account view shows an unavailable state
until its actual profile arrives. Backtest, paper, live-market-paper, shadow,
orders, portfolio, Owner governance, and their backend services are preserved.

Legacy development template views remain honestly marked SAMPLE in legacy
verification. They are not enabled by the product launcher. The legacy development
launchers and static-preview components are not the production entry boundary.

## Verification and limits

`tests/test_step7_runtime.py` exercises relocation to another directory, AppData
resolution, explicit modes, production ACL/seed isolation, atomic config, actual
start/duplicate/stop/restart/crash recovery, stale PID safety, unavailable startup,
durable Owner readiness, device revocation, expired sessions and tenant isolation.
Production storage tests use a temporary AppData surrogate, not real production
data. `verify_step7_runtime.mjs` exercises the actual product server and browser
through loading, an actual backend stop, unavailable state and recovery.

The browser fixture runner now uses temporary databases and artifact paths. The
three later trading evidence verifiers also place their databases under system
temporary storage. Canonical `.sentinelx-dev-data` is not seeded or moved.

Final exact results, changed files and canonical counts are recorded in
`STEP7_FINAL_REPORT.md`. No installer, Step 8, broker integration or real-money
execution is included in this step.
