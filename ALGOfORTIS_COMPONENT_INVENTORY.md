# AlgoFortis — Complete Component Inventory
**Authoritative Catalog of Existing React Components, Props, States & Reusability Audit**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Top-Level Shell & Router Components

### Component: `App` (`dashboard/web/src/main.tsx`)
- **Used On:** Root Application Entrypoint.
- **Purpose:** Top-level URL dispatcher and surface coordinator (`website`, `secure-entry`, `dashboard-v3`).
- **Props / Inputs:** None (Root component).
- **States:** `surface` (`website` | `secure-entry` | `dashboard-v3`), `activeWorkspace` (`user` | `owner`), `authorizationEpoch`.
- **Backend Dependency:** `GET /api/v1/runtime/status`, `GET /api/v1/users/current`.
- **Role Dependency:** Public / Owner / User.
- **Reusable in New UI?** `YES` (Architecture & routing logic must be preserved; visual presentation may be upgraded).

---

### Component: `AuthorizedDashboard` (`dashboard/web/src/main.tsx`)
- **Used On:** Wrapper for authenticated views in `main.tsx`.
- **Purpose:** Asynchronous session resolution and workspace capability guard.
- **Props / Inputs:** `requestedWorkspace: Workspace`, `authorizationEpoch: number`, `onDenied: () => void`, `onExit: () => void`.
- **States:** `session: AuthoritativeSession | null`, `resolved: boolean`.
- **Backend Dependency:** `api.currentUser()`.
- **Role Dependency:** Enforces `session.workspace_eligibility`.
- **Reusable in New UI?** `YES` (Essential security invariant guard).

---

### Component: `RuntimeAvailability` (`dashboard/web/src/RuntimeAvailability.tsx`)
- **Used On:** Global Root Wrapper around `App`.
- **Purpose:** Fail-closed network and runtime daemon connectivity barrier with auto-recovery.
- **Props / Inputs:** `children: React.ReactNode`.
- **States:** `state: "STARTING" | "READY" | "UNAVAILABLE" | "RECOVERING"`, `retry: number`.
- **Backend Dependency:** Polling `GET /api/v1/runtime/status` every 3000ms.
- **Role Dependency:** Global.
- **Reusable in New UI?** `YES` (Critical system resilience component).

---

### Component: `DashboardV3App` (`dashboard/web/src/DashboardV3App.tsx`)
- **Used On:** Master Workspace Dispatcher.
- **Purpose:** Theme management and workspace switching between `OwnerDashboardApp` and `UserDashboardApp`.
- **Props / Inputs:** `initialWorkspace?: Workspace`, `initialTheme?: ThemeMode`, `forceMode?: "desktop" | "mobile"`, `onExit?: () => void`.
- **States:** `ws: Workspace`, `theme: ThemeMode`.
- **Backend Dependency:** None (Propagates downstream).
- **Role Dependency:** Dispatches to Owner or User shell.
- **Reusable in New UI?** `YES`.

---

## 2. Shared & Presentation Components

### Component: `ProfessionalChart` (`dashboard/shared/components/ProfessionalChart.tsx`)
- **Used On:** User Dashboard Home, Backtest Screen, Paper Trading Screen.
- **Purpose:** High-performance OHLCV financial candlestick chart with volume pane, crosshair, and order overlays.
- **Props / Inputs:** `instrument: string`, `timeframe: string`, `mode: MarketChartMode`, `orders?: any[]`, `positions?: any[]`.
- **States:** `chartState: MarketChartState`, `candles: MarketCandle[]`, `hoveredCandle: MarketCandle | null`.
- **Backend Dependency:** `queryMarketChart()`, `queryMarketTimeframes()`.
- **Role Dependency:** Shared (Owner & User).
- **Reusable in New UI?** `PARTIAL` (Can be enhanced with TradingView Lightweight Charts or modernized Canvas engine).

---

### Component: `LiveReadinessRuntime` (`dashboard/shared/components/LiveReadinessRuntime.tsx`)
- **Used On:** Market Connections, System Health screens.
- **Purpose:** Display real-time connectivity status, broker adapter readiness, and market data feed health.
- **Props / Inputs:** `owner?: boolean`.
- **States:** `readiness: LiveReadiness | null`, `loading: boolean`, `error: string | null`.
- **Backend Dependency:** `GET /api/v1/{owner|user}/live-readiness`.
- **Role Dependency:** Shared.
- **Reusable in New UI?** `YES`.

---

### Component: `OrdersPortfolioRuntime` (`dashboard/shared/components/OrdersPortfolioRuntime.tsx`)
- **Used On:** User Portfolio & Orders, Owner Portfolio Oversight.
- **Purpose:** Render real-time positions table, working orders, and account balances with live PnL calculations.
- **Props / Inputs:** `owner: boolean`, `mode: OrdersPortfolioMode`.
- **States:** `snapshot: OrdersPortfolioSnapshot | null`, `activeFilter: string`, `selectedOrder: any | null`.
- **Backend Dependency:** `queryOrdersPortfolio(owner, mode)`.
- **Role Dependency:** Shared.
- **Reusable in New UI?** `YES`.

---

## 3. Secure Entry & Authentication Components

### Component: `SecureEntryApp` (`dashboard/web/src/visual-lab/secure-entry/SecureEntryApp.tsx`)
- **Used On:** Surface `secure-entry`.
- **Purpose:** Master authentication card containing canvas logo and mode selection tabs.
- **Props / Inputs:** `onEnterWorkspace: (auth: boolean, ws: Workspace) => void`, `onBackToWebsite: () => void`, `onOpenDashboard: () => void`.
- **States:** `flow: "returning" | "first-time" | "owner-setup" | "help-recovery"`.
- **Backend Dependency:** WebAuthn auth and registration APIs.
- **Role Dependency:** Public / Authenticating.
- **Reusable in New UI?** `YES`.

---

### Component: `ReturningUserFlow` (`dashboard/web/src/visual-lab/secure-entry/ReturningUserFlow.tsx`)
- **Used On:** Secure Entry Card.
- **Purpose:** WebAuthn passkey assertion prompt and hardware touch ceremony execution.
- **Props / Inputs:** `onSuccess: (token: string, role: string) => void`, `onSwitchFlow: (flow: string) => void`.
- **States:** `identifier: string`, `authenticating: boolean`, `error: string | null`.
- **Backend Dependency:** `POST /api/v1/auth/webauthn/authentication/options` and `/complete`.
- **Role Dependency:** Public.
- **Reusable in New UI?** `YES`.

---

### Component: `FirstTimeCustomerFlow` (`dashboard/web/src/visual-lab/secure-entry/FirstTimeCustomerFlow.tsx`)
- **Used On:** Secure Entry Card.
- **Purpose:** Invitation token redemption and initial WebAuthn security key attestation.
- **Props / Inputs:** `onSuccess: () => void`, `onBack: () => void`.
- **States:** `identifier: string`, `activationCode: string`, `keyLabel: string`, `loading: boolean`.
- **Backend Dependency:** `POST /api/v1/auth/webauthn/activation/redeem` and `/complete`.
- **Role Dependency:** Public.
- **Reusable in New UI?** `YES`.

---

### Component: `OwnerSetupFlow` (`dashboard/web/src/visual-lab/secure-entry/OwnerSetupFlow.tsx`)
- **Used On:** Secure Entry Card (First Run).
- **Purpose:** Appliance bootstrap authority verification and Primary Owner key enrollment.
- **Props / Inputs:** `onSuccess: () => void`, `onBack: () => void`.
- **States:** `bootstrapToken: string`, `label: string`, `submitting: boolean`.
- **Backend Dependency:** `POST /api/v1/auth/webauthn/bootstrap-registration/options` and `/complete`.
- **Role Dependency:** Appliance Administrator.
- **Reusable in New UI?** `YES`.

---

### Component: `SentinelXCore` / `AlgoFortisCore` (`dashboard/web/src/visual-lab/secure-entry/SentinelXCore.tsx`)
- **Used On:** Secure Entry Header, Hero Background.
- **Purpose:** 2D Canvas dynamic cryptographic shield animation with security particle pulse.
- **Props / Inputs:** `width?: number`, `height?: number`, `glowColor?: string`.
- **States:** Internal `requestAnimationFrame` loop.
- **Backend Dependency:** None.
- **Role Dependency:** Public.
- **Reusable in New UI?** `YES` (Can be upgraded with WebGL / Three.js).

---

## 4. User Dashboard Components

### Component: `BacktestingScreen` (`dashboard/user-dashboard/screens/BacktestingScreen.tsx`)
- **Used On:** `#backtesting`.
- **Purpose:** Complete backtest configuration form, execution telemetry, and analytics visualization.
- **Props / Inputs:** Theme, active user identity.
- **States:** `selectedStrategy: string`, `selectedDataset: string`, `dateRange: [string, string]`, `running: boolean`, `progress: number`, `results: BacktestResult | null`.
- **Backend Dependency:** `POST /api/v1/backtest/run`, `GET /api/v1/backtest/results/{id}`.
- **Role Dependency:** User / Owner in user mode.
- **Reusable in New UI?** `YES`.

---

### Component: `AddStrategyModal` (`dashboard/user-dashboard/components/AddStrategyModal.tsx`)
- **Used On:** User Strategy Catalog (`#strategies`).
- **Purpose:** Multi-step wizard to create or upload a new Python algorithmic trading strategy.
- **Props / Inputs:** `isOpen: boolean`, `onClose: () => void`, `onStrategyCreated: (strat: any) => void`.
- **States:** `step: 1 | 2 | 3`, `name: string`, `asset: string`, `sourceCode: string`, `riskPolicy: string`, `validating: boolean`.
- **Backend Dependency:** `POST /api/v1/strategies`.
- **Role Dependency:** User.
- **Reusable in New UI?** `YES`.

---

### Component: `OptionsWorkspace` (`dashboard/user-dashboard/components/OptionsWorkspace.tsx`)
- **Used On:** Options Analytics Screen.
- **Purpose:** Greeks calculations, multi-leg payoff diagram, and volatility smile modeling.
- **Props / Inputs:** `underlyingSymbol: string`.
- **States:** `selectedExpiry: string`, `selectedLegs: OptionLeg[]`, `volShock: number`.
- **Backend Dependency:** `GET /api/v1/market/chart`.
- **Role Dependency:** User.
- **Reusable in New UI?** `YES`.

---

## 5. Owner Dashboard Components

### Component: `AccessRegistryScreen` (`dashboard/owner-dashboard/screens/AccessRegistryScreen.tsx`)
- **Used On:** `#access-registry`.
- **Purpose:** Invitation token generator, pending invitation ledger, and redemption tracker.
- **Props / Inputs:** Owner identity, theme.
- **States:** `tokens: AccessRecord[]`, `isGenerating: boolean`, `generatedTokenModal: boolean`.
- **Backend Dependency:** `GET /api/v1/integration/access/records`, `POST /api/v1/owner/access/users`.
- **Role Dependency:** Owner Only.
- **Reusable in New UI?** `YES`.

---

### Component: `AdminSecuritySystemSettingsScreen` (`dashboard/owner-dashboard/screens/AdminSecuritySystemSettingsScreen.tsx`)
- **Used On:** `#security`, `#system`.
- **Purpose:** Manage active sessions, hardware credentials, mTLS parameters, and system health.
- **Props / Inputs:** Owner identity.
- **States:** `sessions: SessionRow[]`, `devices: DeviceRow[]`, `systemHealth: HealthPayload`.
- **Backend Dependency:** `GET /api/v1/owner/security/sessions`, `GET /api/v1/owner/security/devices`.
- **Role Dependency:** Owner Only.
- **Reusable in New UI?** `YES`.

---

### Component: `AdminStrategiesScreen` (`dashboard/owner-dashboard/screens/AdminStrategiesScreen.tsx`)
- **Used On:** `#strategies`.
- **Purpose:** Strategy lifecycle governance, promotion approval, execution holds, and risk allowances.
- **Props / Inputs:** Owner identity.
- **States:** `strategies: StrategyRow[]`, `pendingPromotions: PromotionRequest[]`, `selectedReview: any | null`.
- **Backend Dependency:** `GET /api/v1/owner/strategies`, `POST /api/v1/owner/strategies/{id}/promote`.
- **Role Dependency:** Owner Only.
- **Reusable in New UI?** `YES`.
