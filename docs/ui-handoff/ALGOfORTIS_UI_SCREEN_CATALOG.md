# AlgoFortis — Complete UI Screen Catalog
**Authoritative UI Inventory for External Frontend, Web, Tablet & Mobile Redesign**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## Document Overview
This document catalogs every user-facing screen, route, sub-view, modal, and drawer in the current AlgoFortis platform. External frontend engineers and UI/UX designers must use this catalog as the exact functional specification of what the product does today across all surfaces: Public Marketing, Secure Entry / Authentication, Owner Workspace, User Workspace, and Runtime Availability.

---

## Surface 1: Public Website & Documentation (`surface=website`)

### Screen ID: `PUB-001`
- **Screen Name:** AlgoFortis Public Landing & Documentation Portal
- **Route:** `/?surface=website` or `/#website`
- **Role:** `PUBLIC / UNAUTHENTICATED`
- **Purpose:** Brand landing page showcasing platform architecture, institutional risk controls, deterministic backtesting, paper execution, security guarantees, and interactive technical documentation.
- **Entry Conditions:** Direct browser navigation to root URL without active session or explicit click on "Public Docs / Website" from login gate.
- **Layout Shell:**
  - Sticky Top Navigation Bar (`logo`, `Nav Links: Platform, Architecture, Risk OS, Performance, Docs`, `CTA: Launch Trading OS`)
  - Hero Section (`CinematicHero` with interactive particle background, animated headline, live capability status pills, dual CTAs)
  - Interactive Showcase Sections 1–10 (`WebsiteSections`)
  - Footer with product invariants and copyright
- **Main Sections:**
  1. *Cinematic Hero*: "Institutional Trading Research & Risk Operating System", Real-Time Engine Health Pill, "Launch Console" & "Explore Architecture" buttons.
  2. *Core Tenets / Pillars*: 4 cards (Deterministic Replay, Zero Silent Failures, Hardware-Bound Security, Local-First Privacy).
  3. *Backtest Engine Architecture*: Visual comparison between standard vector backtesters vs. AlgoFortis tick-level orderbook queue replay.
  4. *Risk Operating System (Risk OS)*: Interactive policy matrix (Drawdown circuit breakers, order throttles, margin limits, auto-flatten rules).
  5. *Paper Trading Engine*: Zero-mutation simulated matching engine specifications.
  6. *Security & FIDO2 Architecture*: Hardware security token ceremony overview.
  7. *Technical Specification Matrix*: Detailed tabular benchmark metrics (latency, memory footprint, throughput).
  8. *Interactive Documentation Modal*: Comprehensive tabbed documentation overlay.
- **Visible Data:**
  - Product Version & Build Number
  - Platform Invariant Indicators: `READ_ONLY: ACTIVE`, `BROKER MUTATION: DISARMED`
  - Engine Benchmark Metrics (e.g. `Tick Replay: 1.2M ticks/sec`, `Latency: < 45μs`)
  - Architectural Schema Diagrams
- **User Actions:**
  - Click "Launch Trading OS" / "Launch Console" -> Transition to Secure Entry Gate (`surface=secure-entry`).
  - Click "Explore Architecture" -> Smooth scroll to Architecture Section.
  - Click "View Documentation" -> Open `DocsModal` overlay.
  - Switch Documentation Tabs in `DocsModal` (Overview, Quickstart, Architecture, Risk Rules, API & SDK).
- **Modals / Dialogs:**
  - `DocsModal`: High-density technical documentation reader with code snippets, table of contents, and close button.
- **Backend Dependencies & API Endpoints:** None (Purely static client presentation on public surface; optional heartbeat check).
- **Permissions:** Unrestricted public access.
- **Loading State:** Minimalist dark skeleton during particle canvas initialization.
- **Empty State:** N/A.
- **Error State:** Fallback static gradient if WebGL/Canvas context initialization fails.
- **Offline / Reconnect State:** Static content remains 100% readable offline.
- **Auth-Expired State:** N/A.
- **Success State:** Instant fluid navigation and smooth scrolling.
- **Notes & Quirks:** Particle canvas pauses when window is backgrounded to preserve CPU/GPU cycles.

---

## Surface 2: Secure Entry & Authentication (`surface=secure-entry`)

### Screen ID: `AUTH-001`
- **Screen Name:** Secure Entry Gate & Mode Dispatcher
- **Route:** `/?surface=secure-entry` or `/#secure-entry`
- **Role:** `PUBLIC / AUTHENTICATING`
- **Purpose:** Central cryptographic authentication gate providing 4 primary entry ceremonies: Returning User (Passkey), First-Time Customer (Token Activation), Owner Bootstrap Setup, and Emergency Recovery.
- **Entry Conditions:** Default application entrypoint when no authenticated session exists, or when user clicks "Exit / Lock Session".
- **Layout Shell:**
  - Centered Glassmorphic Security Card with animated AlgoFortis Shield logo canvas (`SentinelXCore`).
  - Mode Switcher Tabs / Selector buttons.
  - Footer with "Return to Public Website" and platform status indicator.
- **Sub-Flow 1: Returning User (`ReturningUserFlow`)**
  - *Purpose*: Hardware WebAuthn / Passkey assertion login.
  - *Fields*: User Identifier (optional username/email or autofilled from localStorage credential cache).
  - *Controls*: "Authenticate with Passkey" button, "Use Security Key / Biometrics" trigger, "Lost Access / Emergency Recovery" link.
  - *APIs*: `POST /api/v1/auth/webauthn/authentication/options`, `POST /api/v1/auth/webauthn/authentication/complete`.
- **Sub-Flow 2: First-Time Customer (`FirstTimeCustomerFlow`)**
  - *Purpose*: Redeem single-use cryptographic invitation token and bind user hardware authenticator.
  - *Fields*: User Identifier (SX-ID/Email), Activation Code / Token (alphanumeric/UUID format), Security Key Label (e.g., "Workplace MacBook TouchID").
  - *Controls*: "Verify Token", "Register Hardware Key", "Complete Activation".
  - *APIs*: `POST /api/v1/auth/webauthn/activation/redeem`, `POST /api/v1/auth/webauthn/activation/complete`.
- **Sub-Flow 3: Owner Setup Flow (`OwnerSetupFlow`)**
  - *Purpose*: Initial appliance deployment bootstrap to register the Primary Platform Owner.
  - *Fields*: Bootstrap Provisioning Token (from server startup console), Hardware Key Friendly Name, Secondary Recovery Contact (optional).
  - *Controls*: "Verify Bootstrap Authority", "Register Owner Hardware Key", "Generate Master Emergency Recovery Kit".
  - *APIs*: `POST /api/v1/auth/webauthn/bootstrap-registration/options`, `POST /api/v1/auth/webauthn/bootstrap-registration/complete`.
- **Sub-Flow 4: Help & Recovery Flow (`HelpRecoveryFlow`)**
  - *Purpose*: Account access recovery via pre-issued cryptographic recovery mnemonic/token.
  - *Fields*: Account Identifier, Master Recovery Key / Emergency Voucher.
  - *Controls*: "Validate Recovery Token", "Reset Authenticator", "Contact System Owner".
  - *APIs*: `POST /api/v1/auth/recovery/validate`, `POST /api/v1/auth/recovery/complete`.
- **Visible Data:**
  - Active RP ID / Origin Domain indicator
  - Cryptographic Ceremony Status ("Waiting for hardware touch...", "Verifying challenge signature...", "Access Granted")
  - Invariant Status Banner: `LIVE SAFETY LOCKED`
- **Backend Dependencies & APIs:**
  - `GET /api/v1/runtime/status`
  - `POST /api/v1/auth/webauthn/authentication/options`
  - `POST /api/v1/auth/webauthn/authentication/complete`
  - `POST /api/v1/auth/webauthn/activation/redeem`
  - `POST /api/v1/auth/webauthn/activation/complete`
  - `POST /api/v1/auth/webauthn/bootstrap-registration/options`
  - `POST /api/v1/auth/webauthn/bootstrap-registration/complete`
- **Permissions:** Public / Non-authenticated.
- **Loading State:** Circular cryptographic pulse on the AlgoFortis Shield during WebAuthn prompt.
- **Empty State:** Standard input prompts with clear placeholder text.
- **Error State:** Red inline alert banner with exact RFC error code, countdown lockout timer if rate-limited.
- **Offline / Reconnect State:** Handled by outer `RuntimeAvailability` boundary.
- **Auth-Expired State:** Automatically resets to Returning User mode with notification "Session expired. Re-authenticate to continue."
- **Success State:** Sets authoritative JWT session token in `sessionStore`, clears transient input, redirects to appropriate workspace (`surface=dashboard-v3&workspace=owner` or `workspace=user`).

---

## Surface 3: Owner Workspace (`surface=dashboard-v3&workspace=owner`)

### Screen ID: `OWN-001`
- **Screen Name:** Owner Master Control Center & System Health
- **Route:** `/#home` or `/#overview` or `/#control`
- **Role:** `OWNER`
- **Purpose:** Executive overview of entire platform runtime state, database persistence health, active user sessions, safety hold status, and engine throughput.
- **Entry Conditions:** Authenticated user with `role === "OWNER"`.
- **Layout Shell:**
  - Owner Top Header (AlgoFortis Master Brand, Environment Indicator, Theme Switcher, Role Badge `[OWNER]`, Global Emergency Hold Status, Workspace Switcher, Logout).
  - Owner Sidebar Navigation (9 items: Control Center, Access Registry, User Accounts, Security & Devices, Strategy Governance, Backtest & Paper Oversight, Portfolio & Orders Oversight, Plugin System, Audit Trail).
- **Main Sections:**
  1. *System Health & Persistence Card*: Database status (SQLite WAL), journal mode, schema version, audit integrity checksum, adapter latency.
  2. *Live Execution Policy Card*: Global safety hold toggle status (`READ_ONLY`, `DISARMED`, `broker mutation: ZERO`).
  3. *Active Subsystem Grid*: Real-time status pills for Backtest Engine, Paper Engine, Market Data Feed, Audit Store, Auth Authority.
  4. *Quick Stat Cards*: Total Managed Users, Active Hardware Passkeys, Approved Strategies, Total 24h Audit Events.
  5. *Recent High-Priority Audit Stream*: Live log of security and administrative actions.
- **Visible Data:**
  - Persistence Health DTO (database status, schema version, audit count)
  - Subsystem status map (`BACKEND`, `LOCAL_CACHE`, `SAMPLE_FALLBACK`)
  - Active global safety parameters
- **User Actions:**
  - Toggle Emergency Safe Mode / Global Execution Hold (requires confirmation dialog).
  - Refresh System Health metrics.
  - Click any quick stat card to navigate to respective detail screen.
- **Modals / Dialogs:**
  - `ConfirmExecutionHoldModal`: High-risk confirmation dialog before changing system execution flags.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/integration/system/health`
  - `GET /api/v1/security/status`
  - `GET /api/v1/audit/events`
  - `POST /api/v1/settings/safe-mode`
- **Permissions:** Strict Owner only (`session.role === "OWNER"`).
- **Loading State:** Shimmering table rows and skeleton metric cards.
- **Empty State:** Informational message "No recent audit events in current epoch."
- **Error State:** Amber banner "Backend authority unreachable; displaying local system projection."

---

### Screen ID: `OWN-002`
- **Screen Name:** Access Registry & Token Issuance
- **Route:** `/#access-registry`
- **Role:** `OWNER`
- **Purpose:** Issue, monitor, reissue, and revoke user invitation tokens and manage customer onboarding lifecycle.
- **Entry Conditions:** Authenticated Owner.
- **Main Sections:**
  1. *Issue New Access Token Panel*: Form to generate single-use cryptographic invitation tokens with customizable term limits (30-day, 90-day, 1-year, Lifetime).
  2. *Active Invitations Table*: List of pending, unredeemed activation tokens with expiry countdowns.
  3. *Token Lifecycle Actions*: Reissue token, revoke token, extend expiration.
- **Visible Data:**
  - Token Identifier (masked)
  - Target User Email / SX-ID
  - Allowed Workspaces (`USER` only)
  - Service Term & Expiration Date
  - Creation Timestamp & Issuing Owner ID
  - Redemption State (`PENDING`, `REDEEMED`, `EXPIRED`, `REVOKED`)
- **User Actions:**
  - Submit "Generate Invitation Token" form.
  - Copy generated token / activation link to clipboard.
  - Click "Reissue" on expired/lost token.
  - Click "Revoke" on pending token.
- **Modals / Dialogs:**
  - `TokenGeneratedModal`: Shows the newly generated activation token once, with one-click copy and warning that token is not stored in plaintext.
  - `RevokeConfirmationModal`: Destructive action confirmation.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/integration/access/records`
  - `POST /api/v1/owner/access/users`
  - `POST /api/v1/owner/access/users/{id}/reissue-activation`
  - `POST /api/v1/owner/access/users/{id}/revoke-activation`
- **Permissions:** Strict Owner only.

---

### Screen ID: `OWN-003`
- **Screen Name:** User Accounts & Service Lifecycle Management
- **Route:** `/#users`
- **Role:** `OWNER`
- **Purpose:** Comprehensive user directory for managing account status, service terms, suspension, restoration, and role governance.
- **Main Sections:**
  1. *User Directory Table*: Filterable list of all registered users with search, role filter, and status filter.
  2. *User Detail Drawer / Modal*: Shows individual user details, registered passkeys, service expiry, and account history.
  3. *Service Term Management*: Extend, renew, convert to lifetime, or suspend user access.
- **Visible Data:**
  - User SX-ID, Display Name, Email/Identifier
  - Account Status (`ACTIVE`, `SUSPENDED`, `REVOKED`, `PENDING_ACTIVATION`)
  - Service Status (`ACTIVE`, `EXPIRED`, `GRACE_PERIOD`)
  - Service Term Type (`MONTHLY`, `ANNUAL`, `LIFETIME`, `CUSTOM`)
  - Service Started At & Expires At (UTC)
  - Registered Hardware Devices Count
- **User Actions:**
  - Search/Filter users by name, status, or date.
  - Suspend user account (immediate session invalidation).
  - Restore suspended account.
  - Extend / Renew service term.
  - Convert account to Lifetime License.
  - Permanently Revoke user access.
- **Modals / Dialogs:**
  - `EditServiceTermModal`: Date picker and duration selector for term extension.
  - `SuspendUserModal`: Requires entry of reason for audit log.
  - `RevokeUserModal`: High-risk double-confirmation modal.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/owner/access/users`
  - `POST /api/v1/owner/access/users/{id}/suspend`
  - `POST /api/v1/owner/access/users/{id}/restore`
  - `POST /api/v1/owner/access/users/{id}/extend-service`
  - `POST /api/v1/owner/access/users/{id}/renew-service`
  - `POST /api/v1/owner/access/users/{id}/convert-lifetime`
  - `POST /api/v1/owner/access/users/{id}/revoke`
- **Permissions:** Strict Owner only. Owner cannot modify own role to non-owner or delete the primary owner key without bootstrap key ceremony.

---

### Screen ID: `OWN-004`
- **Screen Name:** Security, Hardware Devices & Active Sessions
- **Route:** `/#security` or `/#system` or `/#settings`
- **Role:** `OWNER`
- **Purpose:** Global security oversight, hardware passkey registry, session revocation, TLS/mTLS parameters, and anomaly monitoring.
- **Main Sections:**
  1. *Active Sessions Table*: Real-time list of all active user and owner sessions with IP, User Agent, login timestamp, and idle timeout.
  2. *Enrolled Hardware Devices Matrix*: List of all FIDO2/WebAuthn credentials bound to user accounts.
  3. *Global Security Policy Settings*: Session idle timeout, maximum concurrent devices per user, WebAuthn user verification requirement (`required` vs `preferred`).
- **Visible Data:**
  - Session Reference ID, User ID, Client IP, Device Fingerprint, Created At, Last Active
  - Credential ID, Device Label, Hardware Type (YubiKey, TouchID, Windows Hello), Registered At, Last Used At
  - Global Security Policy Configuration parameters
- **User Actions:**
  - Terminate individual session.
  - Terminate all sessions for a specific user.
  - Terminate all user sessions globally (Emergency Session Purge).
  - Revoke registered hardware passkey.
  - Update global security policies.
- **Modals / Dialogs:**
  - `RevokeDeviceModal`: Confirmation before revoking a user's passkey.
  - `PurgeSessionsModal`: Confirmation for bulk session termination.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/owner/security/sessions`
  - `POST /api/v1/owner/security/sessions/{ref}/revoke`
  - `POST /api/v1/owner/security/users/{id}/sessions/revoke-all`
  - `GET /api/v1/owner/security/devices`
  - `POST /api/v1/owner/security/devices/{id}/revoke`
  - `POST /api/v1/settings/propose`
  - `POST /api/v1/settings/confirm`
- **Permissions:** Strict Owner only.

---

### Screen ID: `OWN-005`
- **Screen Name:** Strategy Governance & Promotion Authority
- **Route:** `/#strategies`
- **Role:** `OWNER`
- **Purpose:** Central registry for inspecting, vetting, approving, promoting, quarantining, and setting risk allowances for trading strategies across all users.
- **Main Sections:**
  1. *Strategy Catalog Table*: All registered strategies across all tenants with version, author, status, and compliance score.
  2. *Promotion Approval Queue*: Pending requests from users to promote strategies from Backtest to Paper or Paper to Live.
  3. *Strategy Risk Allowance Configuration*: Max lot size, allowed instruments, max open positions, execution hold.
- **Visible Data:**
  - Strategy ID, Name, Author SX-ID, Version Hash
  - Governance State (`DRAFT`, `BACKTEST_ONLY`, `PAPER_APPROVED`, `LIVE_PROMOTED`, `QUARANTINED`, `SUSPENDED`)
  - Quality Score & Quality Metrics (Sharpe, Max Drawdown, Win Rate, Profit Factor)
  - Execution Hold Status (`ACTIVE` / `DISABLED`)
  - Allowed Market Instruments & Connection Bindings
- **User Actions:**
  - Approve / Reject Strategy Promotion request.
  - Set Execution Hold on individual strategy.
  - Quarantine suspicious or failing strategy.
  - Inspect strategy source code / AST summary (read-only).
  - Modify strategy risk allowance parameters.
- **Modals / Dialogs:**
  - `PromotionReviewModal`: Side-by-side backtest verification metrics and code hash review before approving promotion.
  - `QuarantineStrategyModal`: Justification input before quarantining.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/owner/strategies`
  - `GET /api/v1/owner/promotions/pending`
  - `POST /api/v1/owner/strategies/{id}/promote`
  - `POST /api/v1/owner/strategies/{id}/allowance`
  - `POST /api/v1/owner/strategies/{id}/suspend`
  - `POST /api/v1/owner/strategies/{id}/restore`
  - `POST /api/v1/owner/strategies/{id}/execution-hold`
- **Permissions:** Strict Owner only. Owner cannot invent algorithmic trades directly; Owner governs permissions and limits.

---

### Screen ID: `OWN-006`
- **Screen Name:** Backtest & Paper Trading Oversight
- **Route:** `/#backtests` or `/#paper`
- **Role:** `OWNER`
- **Purpose:** System-wide visibility into running and historic backtests and active paper trading instances across all users.
- **Main Sections:**
  1. *Active Engine Runs*: Real-time CPU, RAM, and tick-replay rates across all running sessions.
  2. *Historic Backtest Registry*: Searchable ledger of completed backtests with benchmark performance.
  3. *Active Paper Trading Daemons*: Supervised simulated broker instances.
- **Visible Data:**
  - Session ID, Strategy Name, Owner/User ID, Dataset ID, Date Range, Progress %, Elapsed Time
  - Paper Trading Simulated PnL, Order Count, Fill Rate, Slippage Model
- **User Actions:**
  - Inspect backtest report and trade log.
  - Terminate runaway backtest process.
  - Stop paper trading daemon.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/owner/orders-portfolio?mode=BACKTEST`
  - `GET /api/v1/owner/orders-portfolio?mode=PAPER`
  - `POST /api/v1/paper/sessions/{id}/stop`
- **Permissions:** Strict Owner only.

---

### Screen ID: `OWN-007`
- **Screen Name:** Portfolio & Orders Oversight (Institutional Read Projection)
- **Route:** `/#portfolio-oversight` or `/#orders`
- **Role:** `OWNER`
- **Purpose:** Global consolidated view of all positions, simulated orders, and risk exposures across all managed accounts.
- **Main Sections:**
  1. *Consolidated Exposure Card*: Aggregate margin utilization, gross exposure, net exposure.
  2. *Global Orders Ledger*: Filterable live and historic order log (symbol, side, quantity, price, state, user).
  3. *Global Positions Table*: Aggregate open positions by instrument.
- **Visible Data:**
  - Mode Indicator (`PAPER` / `BACKTEST` / `SHADOW`)
  - Order Evidence DTOs (ID, Client Order ID, Instrument, Side, Qty, Status, Timestamp)
  - Position Evidence DTOs (Instrument, Net Qty, Avg Price, Unrealized PnL, Realized PnL)
- **User Actions:**
  - Filter by User, Strategy, Instrument, or Order Status.
  - Click Order Row to inspect raw execution evidence.
  - Export orders ledger as CSV / JSON audit package.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/owner/orders-portfolio?mode={PAPER|BACKTEST|SHADOW}`
  - `GET /api/v1/paper/sessions/{id}/orders/{orderId}`
- **Permissions:** Strict Owner only.

---

### Screen ID: `OWN-008`
- **Screen Name:** Plugin System & Data Adapters
- **Role:** `OWNER`
- **Route:** `/#plugins`
- **Purpose:** Manage market data connectors, broker adapters, execution plugins, and dataset storage providers.
- **Main Sections:**
  1. *Installed Plugins List*: Status of built-in and external plugins (Market Data, Broker, Analytics).
  2. *Connection Endpoints Configuration*: Hostnames, ports, and health status for external market gateways.
  3. *Dataset Approval Registry*: Manage imported tick/candle datasets available to users.
- **Visible Data:**
  - Plugin Name, Version, Type (`DATA_FEED`, `BROKER_ADAPTER`, `RISK_FILTER`), Status (`ACTIVE`, `INACTIVE`, `ERROR`)
  - Connected Gateway Health, Latency (ms), Reconnect Count
  - Dataset Registry (Name, Symbol, Timeframe, Date Range, Size, SHA256 Checksum, Approval Status)
- **User Actions:**
  - Enable / Disable Plugin.
  - Approve Dataset for User Backtesting.
  - Test Gateway Connectivity.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/owner/connections`
  - `POST /api/v1/owner/connections/{id}/allowance`
  - `GET /api/v1/owner/datasets`
  - `POST /api/v1/owner/datasets/{id}/approval`
- **Permissions:** Strict Owner only.

---

### Screen ID: `OWN-009`
- **Screen Name:** Regulatory Audit Trail & Compliance Reports
- **Route:** `/#audit` or `/#reports`
- **Role:** `OWNER`
- **Purpose:** Immutable D16 compliance event viewer and cryptographic audit log exporter.
- **Main Sections:**
  1. *Audit Event Log Stream*: Chronological, append-only ledger of all security, auth, governance, and risk events.
  2. *Filter & Search Bar*: Filter by Actor, Event Type, Target Entity, Date Range, Severity.
  3. *Compliance Report Generator*: Export signed audit packages for regulatory audit.
- **Visible Data:**
  - Audit Event ID, Timestamp (UTC ISO 8601), Actor ID, Action Type, Target Resource, IP Address, Integrity Checksum, Metadata JSON
- **User Actions:**
  - Search audit log.
  - Click event to inspect full cryptographic event payload.
  - Click "Export Compliance Package" -> Downloads verifiable JSON/CSV bundle.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/integration/audit/events`
  - `GET /api/v1/audit/events`
- **Permissions:** Strict Owner only.

---

## Surface 4: User Workspace (`surface=dashboard-v3&workspace=user`)

### Screen ID: `USR-001`
- **Screen Name:** Trader Overview & Portfolio Dashboard
- **Route:** `/#home` or `/#portfolio`
- **Role:** `USER` (also accessible to `OWNER` in user workspace view)
- **Purpose:** Primary trading research dashboard showing portfolio performance, active strategy status, live paper sessions, and quick market charts.
- **Entry Conditions:** Authenticated User with active service term.
- **Layout Shell:**
  - User Top Header (AlgoFortis Logo, Market Time Clock, Mode Indicator `[PAPER TRADING]`, Service Expiry Pill, Theme Toggle, Workspace Switcher if eligible, Logout).
  - User Sidebar Navigation (8 items: Home / Overview, Strategies, Backtesting, Paper Trading, Portfolio & Orders, Market Data / Connections, Agent Intelligence, Reports / History).
- **Main Sections:**
  1. *Portfolio Equity Curve*: Interactive interactive SVG/Canvas chart showing equity balance over time.
  2. *Key Performance Indicators (KPI Cards)*: Net Liquidating Value, Today's Simulated PnL, Win Rate %, Profit Factor, Max Drawdown %.
  3. *Active Paper Strategies Table*: Summary of currently running automated trading strategies.
  4. *Quick Order Widget*: Manual simulated order placement (Paper Mode only, subject to risk limits).
  5. *Recent Trade Log*: Stream of recent simulated fills and cancellations.
- **Visible Data:**
  - Total Equity, Available Margin, Used Margin
  - Unrealized & Realized PnL
  - Active Strategy Metrics
  - Real-time Market Clock (UTC & Local)
- **User Actions:**
  - Switch chart timeframe (1D, 1W, 1M, 1Y, ALL).
  - Pause / Resume individual paper strategy.
  - Click strategy to view detailed telemetry.
  - Trigger Manual Simulated Order (Limit, Market, Stop) in Paper Mode.
- **Modals / Dialogs:**
  - `PaperOrderConfirmModal`: Summary of simulated order fees, slippage estimate, and risk margin impact.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/users/current`
  - `GET /api/v1/portfolio`
  - `GET /api/v1/user/orders-portfolio?mode=PAPER`
  - `GET /api/v1/market/chart`
- **Permissions:** Standard User.

---

### Screen ID: `USR-002`
- **Screen Name:** Strategy Catalog & Lifecycle Manager
- **Route:** `/#strategies`
- **Role:** `USER`
- **Purpose:** Author, configure, inspect, test, and manage algorithmic trading strategies.
- **Main Sections:**
  1. *Strategy Cards Grid / Table*: List of personal strategies with status (`DRAFT`, `BACKTESTED`, `PAPER_RUNNING`, `PROMOTED`).
  2. *Strategy Details Drawer*: Parameter editor, risk bounds, historical quality scorecard.
  3. *Add / Import Strategy Action Bar*: Create new script or upload Python strategy file.
- **Visible Data:**
  - Strategy Name, Identifier, Version Tag, Created Date
  - Risk Parameters (Max Position Size, Stop Loss %, Take Profit %, Trailing Stop)
  - Quality Metrics (Sharpe Ratio, Sortino Ratio, Calmar Ratio, Expectancy)
  - Governance State & Owner Promotion Status
- **User Actions:**
  - Click "New Strategy" -> Open `AddStrategyModal`.
  - Edit Strategy Parameters (Integer/Float inputs, dropdowns).
  - Request Promotion from Backtest to Paper / Live.
  - Archive / Delete strategy.
  - Launch Instant Backtest from strategy card.
- **Modals / Dialogs:**
  - `AddStrategyModal`: Multi-step modal (Name, Base Asset, Algorithm Template, Initial Risk Rules, Source Code Upload).
  - `RequestPromotionModal`: Submits formal promotion request to Owner review queue.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/strategies`
  - `POST /api/v1/strategies`
  - `POST /api/v1/strategies/{id}/archive`
  - `POST /api/v1/strategies/{id}/request-promotion`
  - `GET /api/v1/strategies/{id}/quality`
- **Permissions:** Standard User.

---

### Screen ID: `USR-003`
- **Screen Name:** Deterministic Backtesting Laboratory
- **Route:** `/#backtesting` or `/#backtest`
- **Role:** `USER`
- **Purpose:** Full-featured institutional backtesting laboratory featuring tick-level historical replay, parameter sweeps, and performance breakdown.
- **Main Sections:**
  1. *Backtest Configuration Panel*: Strategy selector, Dataset picker, Date Range, Initial Capital, Fee/Commission model, Slippage model.
  2. *Execution Progress & Telemetry*: Real-time progress bar, simulated clock, tick throughput counter during active run.
  3. *Performance Analytics Suite*: Equity curve chart, Drawdown underwater chart, Monthly returns heatmap, Trade distribution histogram.
  4. *Trade Ledger Table*: Every simulated fill with entry timestamp, exit timestamp, duration, slippage, PnL, and MFE/MAE metrics.
  5. *Log & Telemetry Console*: Live Python runtime logs emitted during replay.
- **Visible Data:**
  - Replay Progress %, Processed Bars / Ticks count
  - CAGR %, Total Net Profit, Max Drawdown %, Sharpe Ratio, Profit Factor
  - Win/Loss Ratio, Total Trades, Average Trade Duration
  - Detailed Trade Ledger (50+ data points per execution)
- **User Actions:**
  - Select Dataset & Strategy from dropdowns.
  - Set Custom Date Range (Datepicker).
  - Configure Capital ($1,000 to $10,000,000) and Fees.
  - Click "Run Backtest" -> Executes deterministic replay.
  - Click "Cancel / Stop Run" -> Aborts active backtest.
  - Filter and Sort Trade Ledger.
  - Export Backtest Report as PDF / CSV / JSON.
- **Modals / Dialogs:**
  - `ExportReportModal`: Select export format and metrics to include.
  - `CompareBacktestModal`: Side-by-side comparison of two backtest runs.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/strategies`
  - `GET /api/v1/market/timeframes`
  - `POST /api/v1/backtest/run`
  - `GET /api/v1/backtest/status/{id}`
  - `GET /api/v1/backtest/results/{id}`
- **Permissions:** Standard User.

---

### Screen ID: `USR-004`
- **Screen Name:** Paper Trading & Real-Time Simulation Center
- **Route:** `/#paper` or `/#trading`
- **Role:** `USER`
- **Purpose:** Live forward-testing workstation running automated strategies against live market feeds with zero financial capital risk.
- **Main Sections:**
  1. *Active Simulation Daemons*: Cards showing running strategies, active since, allocated capital, and current drawdown.
  2. *Live Orderbook & Chart*: Real-time candlestick chart with order and fill overlays.
  3. *Open Paper Positions*: Live table with streaming mark-to-market PnL.
  4. *Working Simulated Orders*: Active limit, stop, and trailing orders awaiting simulated trigger.
  5. *Live Execution Log*: Microsecond-stamped event stream.
- **Visible Data:**
  - Live Bid/Ask/Last Price
  - Position Quantity, Entry Price, Current Price, Unrealized PnL ($ and %)
  - Order Status (`PENDING`, `SUBMITTED`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`)
- **User Actions:**
  - Start / Stop Paper Trading Session.
  - Cancel Working Order.
  - Panic Flatten / Close All Positions (instant market simulated liquidation).
  - Adjust Strategy Risk Envelope on the fly.
- **Modals / Dialogs:**
  - `EmergencyFlattenModal`: High-priority modal to close all active simulated positions.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/user/orders-portfolio?mode=PAPER`
  - `GET /api/v1/market/chart?mode=LIVE`
  - `POST /api/v1/paper/orders`
  - `DELETE /api/v1/paper/orders/{id}`
  - `POST /api/v1/paper/flatten`
- **Permissions:** Standard User.

---

### Screen ID: `USR-005`
- **Screen Name:** User Orders & Execution History
- **Route:** `/#orders`
- **Role:** `USER`
- **Purpose:** Comprehensive searchable record of all orders and fills generated across Backtest, Paper, and Shadow modes.
- **Main Sections:**
  1. *Mode Switcher Tabs*: `PAPER`, `BACKTEST`, `SHADOW`.
  2. *Orders Filter Bar*: Instrument, Side, Status, Date.
  3. *Orders Data Table*: Paginated list of order executions.
  4. *Order Detail Inspector*: Microsecond timestamp breakdown, slippage analysis, fill breakdown.
- **Visible Data:**
  - Order ID, Client Ref, Strategy, Symbol, Side (BUY/SELL), Type (LIMIT/MARKET/STOP), Quantity, Limit Price, Executed Price, Status, Timestamp
- **User Actions:**
  - Search & filter orders.
  - Click row to view detailed execution timeline.
  - Export order history to CSV.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/user/orders-portfolio?mode={mode}`
  - `GET /api/v1/paper/sessions/{id}/orders/{orderId}`
- **Permissions:** Standard User.

---

### Screen ID: `USR-006`
- **Screen Name:** Market Connections & Data Providers
- **Route:** `/#connections`
- **Role:** `USER`
- **Purpose:** View assigned market data feeds, connection health, subscription tiers, and instrument symbology.
- **Main Sections:**
  1. *Connection Health Status*: Connection latency, ping times, packet loss.
  2. *Assigned Instruments List*: Symbols enabled by Owner for user trading and backtesting.
  3. *Historical Data Catalog*: Available pre-loaded historical tick and bar archives.
- **Visible Data:**
  - Provider Name (e.g. Interactive Brokers, Binance, Alpaca, Simulated Feed)
  - Connection State (`CONNECTED`, `DEGRADED`, `DISCONNECTED`)
  - Permitted Symbols & Timeframes
- **User Actions:**
  - Test connection ping.
  - Search available instrument symbology.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/user/live-readiness`
  - `GET /api/v1/market/timeframes`
- **Permissions:** Standard User (Read-only; configuration governed by Owner).

---

### Screen ID: `USR-007`
- **Screen Name:** Agent Intelligence & AI Strategy Copilot
- **Route:** `/#agents`
- **Role:** `USER`
- **Purpose:** Interactive quantitative research assistant for strategy syntax validation, risk parameter optimization, and backtest analysis.
- **Main Sections:**
  1. *Research Chat Interface*: Interactive dialogue for exploring quantitative ideas and risk rules.
  2. *Strategy Code Inspector*: Integrated code viewer with syntax highlighting and risk linting warnings.
  3. *Parameter Optimization Suggestions*: Algorithmic suggestions for parameter ranges based on walk-forward analysis.
- **Visible Data:**
  - Strategy Code Snippets
  - AST Validation Errors / Warnings
  - Metric Explanations
- **User Actions:**
  - Query assistant regarding strategy metrics.
  - Apply suggested risk parameter constraints.
- **Permissions:** Standard User.

---

### Screen ID: `USR-008`
- **Screen Name:** Options Workspace & Volatility Analytics
- **Route:** `/#options` or accessible via Options Component
- **Role:** `USER`
- **Purpose:** Dedicated options chain analysis, Greeks modeling, and multi-leg option strategy constructor.
- **Main Sections:**
  1. *Underlying Ticker Selector & Spot Price Banner*.
  2. *Interactive Options Chain*: Calls on left, Puts on right, Strike column in center with Delta, Gamma, Theta, Vega, IV.
  3. *Payoff Diagram / Risk Profile*: Multi-leg PnL curve at expiration and current date.
  4. *Strategy Constructor*: Build Spreads, Straddles, Iron Condors, Covered Calls.
- **Visible Data:**
  - Strike Prices, Expiration Dates, Implied Volatility (IV)
  - Greeks (Delta, Gamma, Theta, Vega, Rho)
  - Max Profit, Max Loss, Breakeven Points
- **User Actions:**
  - Select Expiration Date from tabs.
  - Click Bid/Ask to add option leg to strategy builder.
  - Adjust strike price sliders and volatility shock parameters.
  - Send option strategy to Backtest or Paper Trading.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/market/chart`
- **Permissions:** Standard User.

---

### Screen ID: `USR-009`
- **Screen Name:** User Security, Passkeys & Account Settings
- **Route:** `/#security` or `/#settings` or `/#account`
- **Role:** `USER`
- **Purpose:** Personal security center for managing enrolled FIDO2 hardware keys, viewing active personal sessions, and reviewing subscription status.
- **Main Sections:**
  1. *Account & Service Status Card*: SX-ID, Registered Email, Service Term Expiry, Time Remaining.
  2. *Enrolled Hardware Passkeys*: List of user's registered WebAuthn security keys with "Enroll New Key" button.
  3. *Active Devices & Sessions*: List of personal active logins with "Log Out Other Sessions".
  4. *Appearance & Interface Preferences*: Theme mode (Dark / Light / High Contrast), Chart color scheme, Sound effects.
- **Visible Data:**
  - User Identifier, Account Status
  - Hardware Key Labels, Enrolled Dates, Key ID hashes
  - Active Session IP, User Agent, Last Active Time
- **User Actions:**
  - Enroll additional WebAuthn hardware security key / TouchID.
  - Rename security key label.
  - Delete / Revoke personal backup key (minimum 1 key required).
  - Terminate other active sessions.
  - Toggle Theme (Dark / Light).
- **Modals / Dialogs:**
  - `EnrollPasskeyModal`: Browser WebAuthn registration ceremony prompt.
  - `ConfirmRevokePasskeyModal`: Warning if removing backup key.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/users/current`
  - `POST /api/v1/auth/webauthn/registration/options`
  - `POST /api/v1/auth/webauthn/registration/complete`
  - `POST /api/v1/security/sessions/revoke`
- **Permissions:** Standard User.

---

## Surface 5: Runtime Availability & System Recovery Layer

### Screen ID: `RNT-001`
- **Screen Name:** Runtime Availability & Connectivity Overlay
- **Route:** Global Root Component (`RuntimeAvailability`)
- **Role:** `ALL (GLOBAL OVERLAY)`
- **Purpose:** Full-screen fail-closed protection barrier that automatically intercepts UI whenever backend runtime state is starting, reconnecting, degraded, or unavailable.
- **States & Visual Surfaces:**
  1. *State: `STARTING`*: "AlgoFortis is starting" — Spinner with message "Waiting for local runtime to become ready."
  2. *State: `RECOVERING`*: "Reconnecting to AlgoFortis" — Pulse indicator with auto-retry in 3 seconds.
  3. *State: `UNAVAILABLE`*: "AlgoFortis is unavailable" — Red alert card with message "The local runtime is unavailable. Reopen AlgoFortis to restart it, or retry the connection." and "Retry connection" button.
- **Visible Data:**
  - Current Runtime Connection State
  - Runtime Instance ID & API Base
- **User Actions:**
  - Click "Retry connection" -> Manually triggers immediate endpoint ping and retry counter increment.
- **Backend Dependencies & APIs:**
  - `GET /api/v1/runtime/status` (polled every 3000ms with 2000ms abort controller timeout).
- **Permissions:** Global.
- **Notes & Quirks:** If backend restarts and produces a new `instance_id`, `RuntimeAvailability` automatically calls `clearSessionToken()` to prevent stale session attacks and forces re-authentication.
