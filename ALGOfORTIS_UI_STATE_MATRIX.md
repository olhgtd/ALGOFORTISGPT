# AlgoFortis — UI State Matrix
**Authoritative Comprehensive State & Surface Behavior Matrix**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Global State Classification
The AlgoFortis frontend system defines 14 exhaustive visual and interactive states across all product screens:

1. **`NORMAL`**: Standard nominal operating state with live, fresh authoritative data.
2. **`LOADING`**: Asynchronous fetching / computation in progress; skeleton loaders or pulses rendered.
3. **`EMPTY`**: Query succeeded but returned 0 records; contextual call-to-action rendered.
4. **`SUCCESS`**: Action or mutation completed; confirmation feedback rendered.
5. **`WARNING`**: Non-critical issue (e.g. expiring service term, high drawdown threshold).
6. **`ERROR`**: Action or query failed; error description and status code surfaced.
7. **`OFFLINE`**: Network connectivity lost; UI prevents stale data mutations.
8. **`RECONNECTING`**: Connection dropped; active automated retry polling in progress.
9. **`AUTH_EXPIRED`**: JWT session expired / rejected by server (HTTP 401).
10. **`PERMISSION_DENIED`**: User lacks required RBAC role or license capability (HTTP 403).
11. **`RUNTIME_UNAVAILABLE`**: Local Python backend process down / uncommunicative.
12. **`DEGRADED_MODE`**: Partial system health; some subsystems operating on local cache.
13. **`NO_DATA`**: Selected instrument / timeframe has no candles or records.
14. **`PARTIAL_DATA`**: Partial date range or missing intermediate ticks during replay.

---

## 2. Screen-by-Screen State Matrix

### 2.1 Public & Authentication Surfaces

| Screen | State | Trigger | Visible Message / Indicator | Available Actions | Disabled Actions | Recovery Path |
|---|---|---|---|---|---|---|
| **Public Landing (`PUB-001`)** | `NORMAL` | Initial load | Interactive Hero, live capability pills | Navigate sections, open docs, launch console | None | N/A |
| **Public Landing (`PUB-001`)** | `LOADING` | Canvas initializing | Shimmering particle container | Read static text, click nav links | Canvas interactivity | Wait ~200ms |
| **Public Landing (`PUB-001`)** | `ERROR` | WebGL context lost | Fallback dark gradient background | Launch console, view docs | 3D visual FX | Reload page |
| **Secure Entry (`AUTH-001`)** | `NORMAL` | Unauthenticated route | AlgoFortis Shield, WebAuthn trigger card | Enter identifier, click authenticate | None | N/A |
| **Secure Entry (`AUTH-001`)** | `LOADING` | WebAuthn prompt active | Pulsing shield, "Waiting for security key..." | Cancel ceremony | Input fields, mode tabs | Complete hardware touch or cancel |
| **Secure Entry (`AUTH-001`)** | `ERROR` | Invalid signature / cancel | Red alert banner: "Passkey authentication failed" | Retry authentication, try recovery key | Submit button (temporarily) | Click "Retry" |
| **Secure Entry (`AUTH-001`)** | `AUTH_EXPIRED` | 401 token rejection | "Session expired. Re-authenticate to continue." | Authenticate with passkey | None | Re-authenticate |
| **Secure Entry (`AUTH-001`)** | `PERMISSION_DENIED` | Account suspended | "Account is suspended. Contact system Owner." | Contact Owner / Support | Login submit | Contact Owner to restore account |

---

### 2.2 Owner Workspace Surfaces

| Screen | State | Trigger | Visible Message / Indicator | Available Actions | Disabled Actions | Recovery Path |
|---|---|---|---|---|---|---|
| **Owner Control Center (`OWN-001`)** | `NORMAL` | Authoritative fetch | Green health pills, live system metrics | Toggle Safe Mode, inspect telemetry | None | N/A |
| **Owner Control Center (`OWN-001`)** | `LOADING` | System health polling | Shimmering metric cards & skeleton rows | Navigate sidebar | Action toggles | Wait for polling fetch |
| **Owner Control Center (`OWN-001`)** | `DEGRADED_MODE` | 1 subsystem offline | Amber banner: "Market data adapter offline" | Review logs, toggle holds | Live streaming feeds | Check adapter connection |
| **Owner Control Center (`OWN-001`)** | `WARNING` | High memory / disk use | Yellow metric badge: "Audit store disk > 85%" | Export audit log, purge logs | None | Export/archive audit store |
| **Access Registry (`OWN-002`)** | `NORMAL` | Active tokens loaded | Tabular view of issued & pending tokens | Issue token, reissue, revoke | None | N/A |
| **Access Registry (`OWN-002`)** | `EMPTY` | 0 invitations issued | "No active invitation tokens found" | Click "Issue First Token" | Table bulk actions | Generate new invitation |
| **Access Registry (`OWN-002`)** | `SUCCESS` | Token generated | Modal showing raw token + one-click copy | Copy token, close modal | Modal background click | Copy token and close |
| **User Directory (`OWN-003`)** | `NORMAL` | Users fetched | Full user table with status pills | Search, filter, suspend, extend term | None | N/A |
| **User Directory (`OWN-003`)** | `LOADING` | Table pagination | Skeleton rows with animated pulse | Search input | Row edit buttons | Automatic on fetch complete |
| **User Directory (`OWN-003`)** | `ERROR` | API 500 error | "Failed to load user registry (HTTP 500)" | Click "Retry Load" | User mutation buttons | Click retry button |
| **Security & Devices (`OWN-004`)** | `NORMAL` | Devices/sessions loaded | Active session list, enrolled WebAuthn keys | Revoke session, revoke device | None | N/A |
| **Security & Devices (`OWN-004`)** | `WARNING` | Unrecognized IP login | Orange flag: "Session from new subnet detected" | Terminate suspicious session | None | Revoke session if unauthorized |
| **Strategy Governance (`OWN-005`)** | `NORMAL` | Strategies cataloged | Full strategy matrix with quality scores | Promote, quarantine, set hold | None | N/A |
| **Strategy Governance (`OWN-005`)** | `EMPTY` | No pending promotions | "No strategies currently awaiting Owner review" | Inspect historic catalog | "Approve" button | Wait for user submission |
| **Strategy Governance (`OWN-005`)** | `WARNING` | High drawdown strategy | Red tag: "Drawdown exceeds conservative policy" | Quarantine strategy, view AST | Promote without override | Adjust risk bounds or reject |
| **Audit Trail (`OWN-009`)** | `NORMAL` | D16 events streaming | Chronological event table with SHA256 hashes | Filter, search, export audit package | None | N/A |
| **Audit Trail (`OWN-009`)** | `LOADING` | Querying historical DB | Loading shimmer on event ledger | Date filter | Export button | Fetch completes |

---

### 2.3 User Workspace Surfaces

| Screen | State | Trigger | Visible Message / Indicator | Available Actions | Disabled Actions | Recovery Path |
|---|---|---|---|---|---|---|
| **Trader Overview (`USR-001`)** | `NORMAL` | Portfolio data loaded | Interactive equity curve, active paper stats | Switch timeframes, view orders | None | N/A |
| **Trader Overview (`USR-001`)** | `EMPTY` | Fresh account (no trades) | "No trading history recorded yet. Run backtest." | Click "Launch Backtesting Lab" | Chart timeframe zooms | Execute first backtest |
| **Trader Overview (`USR-001`)** | `WARNING` | Service term < 7 days | Top banner: "Subscription expires in 5 days" | Contact Owner for extension | None | Owner extends service term |
| **Backtesting Lab (`USR-003`)** | `NORMAL` | Idle configuration | Dataset picker, strategy selector, parameters | Select inputs, click "Run Backtest" | "Stop Run" (while idle) | N/A |
| **Backtesting Lab (`USR-003`)** | `LOADING` | Replay execution | Real-time progress bar (0-100%), tick counter | Click "Stop Run / Abort" | "Run Backtest", form inputs | Wait for run or abort |
| **Backtesting Lab (`USR-003`)** | `SUCCESS` | Replay completed | Analytics charts, Sharpe ratio, trade ledger | Export PDF/CSV, inspect trades | None | Review results |
| **Backtesting Lab (`USR-003`)** | `NO_DATA` | Dataset empty for range | "No market bars found in selected date interval" | Change date range or dataset | "Run Backtest" | Select valid date range |
| **Backtesting Lab (`USR-003`)** | `PARTIAL_DATA` | Dataset contains gaps | Warning pill: "14 missing bar intervals filled" | Inspect gap report, run backtest | None | Informational notice |
| **Paper Trading (`USR-004`)** | `NORMAL` | Simulation active | Live orderbook, real-time streaming PnL | Submit simulated order, flatten all | Live broker orders | N/A |
| **Paper Trading (`USR-004`)** | `WARNING` | Max Drawdown reached | "Strategy risk limit hit: Paper daemon paused" | Inspect order log, reset daemon | Automated order entry | Review strategy risk rules |
| **Paper Trading (`USR-004`)** | `ERROR` | Market feed dropped | "Simulated feed disconnected. Reconnecting..." | Emergency Flatten | Normal order placement | System auto-reconnects |
| **User Security (`USR-009`)** | `NORMAL` | Passkeys loaded | List of enrolled security keys | Enroll new key, rename key | Delete sole primary key | N/A |
| **User Security (`USR-009`)** | `WARNING` | Single key enrolled | Badge: "No backup key enrolled. Add backup." | Enroll backup passkey | Delete current passkey | Enroll secondary hardware key |

---

### 2.4 Global Runtime Availability Layer

| Screen | State | Trigger | Visible Message / Indicator | Available Actions | Disabled Actions | Recovery Path |
|---|---|---|---|---|---|---|
| **All Screens (`RNT-001`)** | `STARTING` | App boot / init | "AlgoFortis is starting. Waiting for runtime..." | None (overlay active) | All background screens | Wait ~2-3 seconds for READY |
| **All Screens (`RNT-001`)** | `RECONNECTING` | Transient drop | "Reconnecting to AlgoFortis..." | None (overlay active) | All background screens | Auto-retries every 3000ms |
| **All Screens (`RNT-001`)** | `RUNTIME_UNAVAILABLE` | Process termination | "AlgoFortis is unavailable. Reopen app or retry." | Click "Retry connection" | All background screens | Restart backend / click retry |
