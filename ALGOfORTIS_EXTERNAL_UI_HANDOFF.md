# AlgoFortis — External UI Team Handoff Specification
**Master Architecture, Requirements, Boundary Constraints & Deliverables for Frontend Redesign**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Executive Summary & Product Mission
**AlgoFortis** is an institutional **Trading Research & Risk Operating System**. It provides quantitative traders and asset managers with deterministic historical tick-replay backtesting, paper execution simulation, multi-leg options volatility analytics, hardware-bound (FIDO2/WebAuthn) cryptographic security, and immutable regulatory audit logging.

This specification enables external UI/UX designers and frontend engineers to design and implement a modern, responsive, high-performance web and mobile interface **without reading or modifying internal Python engine code or trading mathematics**.

---

## 2. Core Brand & Product Identity
- **Product Name:** `AlgoFortis`
- **Official Tagline:** `Trading Research & Risk OS`
- **Visual Tone:** Institutional, high-density, quantitative, security-first, dark obsidian glassmorphic aesthetic with electric blue and emerald financial accents.
- **Master Invariant Badges:**
  - `READ_ONLY: TRUE`
  - `DISARMED: TRUE`
  - `BROKER MUTATION: ZERO`

---

## 3. User Roles & Workspace Architecture
The application is strictly partitioned into two authenticated workspaces and one public surface:
1. **Public Marketing & Documentation (`surface=website`)**: Unauthenticated showcase of architecture, risk engine, and interactive docs.
2. **Secure Entry Gate (`surface=secure-entry`)**: Central FIDO2/WebAuthn hardware key authentication portal.
3. **Owner Workspace (`workspace=owner`)**: Administrative control center for user onboarding, token issuance, strategy promotion governance, system persistence monitoring, and emergency freeze controls.
4. **User Workspace (`workspace=user`)**: Quantitative workstation for strategy development, deterministic backtesting, paper simulation, options analytics, and personal passkey management.

---

## 4. Complete Application Sitemap

```
AlgoFortis Root (main.tsx)
│
├── 1. Public Marketing (surface=website)
│   ├── Cinematic Hero & Capability Matrix
│   ├── Architecture & Backtest Replay Showcase
│   ├── Risk OS Interactive Policy Matrix
│   └── Interactive Documentation Modal (DocsModal)
│
├── 2. Secure Entry Gate (surface=secure-entry)
│   ├── Returning User Flow (Passkey WebAuthn)
│   ├── First-Time Customer Flow (Token Redemption)
│   ├── Primary Owner Setup Flow (Bootstrap Key Ceremony)
│   └── Emergency Recovery Flow (Voucher Key)
│
├── 3. Owner Workspace (surface=dashboard-v3&workspace=owner)
│   ├── #home / #overview — Owner Control Center & System Health
│   ├── #access-registry — Token Issuance & Customer Onboarding
│   ├── #users — User Accounts & Service Lifecycle Directory
│   ├── #security / #system — Enrolled Hardware Devices & Active Sessions
│   ├── #strategies — Strategy Governance & Promotion Authority
│   ├── #backtests / #paper — Supervised Engine Runs Oversight
│   ├── #portfolio-oversight / #orders — Institutional Read Projection
│   ├── #plugins — Data Adapters & Gateway Connectors
│   └── #audit / #reports — Immutable D16 Compliance Trail
│
├── 4. User Workspace (surface=dashboard-v3&workspace=user)
│   ├── #home / #portfolio — Trader Overview & Equity Curve
│   ├── #strategies — Strategy Catalog & Add Strategy Modal
│   ├── #backtesting / #backtest — Deterministic Historical Laboratory
│   ├── #paper / #trading — Live Paper Trading Simulation Center
│   ├── #orders — Searchable Execution History
│   ├── #connections — Assigned Feeds & Connection Health
│   ├── #agents — Quantitative Copilot & AST Linting
│   ├── #options — Options Chain, Greeks & Multi-Leg Payoffs
│   └── #security / #settings — Personal Passkeys & Device Registry
│
└── 5. Global Runtime Layer (RuntimeAvailability.tsx)
    ├── State: STARTING (App Launch Splash)
    ├── State: RECOVERING (Auto-Reconnect Poller)
    └── State: UNAVAILABLE (Fail-Closed Offline Security Overlay)
```

---

## 5. Absolute Boundaries: What the UI Team MUST NOT Implement
To preserve strict security, regulatory, and live safety invariants, external frontend teams must adhere to the following **absolute prohibitions**:

1. **DO NOT implement trading business logic or order matching in JavaScript.** All matching is executed by the backend deterministic replay / simulated matching engine.
2. **DO NOT connect to or query the SQLite database directly.** All reads and writes must pass through the authoritative REST API (`/api/v1/*`).
3. **DO NOT store broker API secrets, private keys, or API tokens in client storage.**
4. **DO NOT bypass the API authentication layer or mock authentication tokens in production builds.**
5. **DO NOT create plaintext password fields or password reset workflows.** WebAuthn hardware passkeys are the sole authentication authority.
6. **DO NOT modify the Live Safety Invariants:**
   - `READ_ONLY` must remain `true`.
   - `DISARMED` must remain `true`.
   - `broker mutation` must remain `ZERO`.
7. **DO NOT import Python backend modules or C# launcher code directly into frontend bundles.**

---

## 6. Multi-Device & Responsive Targets
The redesigned UI must be fully functional, touch-optimized, and aesthetically stunning across 5 form factors:
1. **Desktop Workstation (>= 1440px):** Multi-pane high-density layout with persistent sidebar and advanced charts.
2. **Laptop Display (1024px – 1439px):** Single-screen view with collapsible panels.
3. **Tablet Landscape (900px – 1023px):** Dual-pane touch layout with icon-rail navigation.
4. **Tablet Portrait (600px – 899px):** Single-column stacked cards with bottom navigation sheet.
5. **Mobile Handheld (< 600px):** Thumb-accessible bottom navigation bar, swipeable KPI cards, full-screen chart bottom sheets, and biometric passkey authentication.

---

## 7. Deliverables Expected from External Frontend Team
The external UI team will deliver:
1. **Responsive Component Library:** Fully typed TypeScript/React components using semantic HTML and clean, modular CSS/SCSS (or Vanilla CSS tokens).
2. **Page & Screen Implementations:** All 18+ cataloged screens matching the contracts in `ALGOfORTIS_UI_SCREEN_CATALOG.md` and `ALGOfORTIS_UI_STATE_MATRIX.md`.
3. **Design System Tokens:** Central CSS custom properties defining colors, typography, spacing, shadows, and radii matching `ALGOfORTIS_CURRENT_DESIGN_SYSTEM.md`.
4. **Interactive Charting Suite:** Responsive OHLCV candlestick chart, equity curve chart, and drawdown underwater graph.
5. **WebAuthn Ceremonies Integration:** Full integration with browser `navigator.credentials.get()` and `create()` matching `ALGOfORTIS_AUTH_UI_REQUIREMENTS.md`.
6. **Automated UI Test Suite:** Unit and component tests verifying state machine transitions, form validations, and role boundaries.

---

## 8. Acceptance Criteria
- [ ] 100% of routes and screens cataloged in `ALGOfORTIS_UI_SCREEN_CATALOG.md` are accessible and functional.
- [ ] Zero compile-time or runtime errors in browser console.
- [ ] Passes all 14 visual states in `ALGOfORTIS_UI_STATE_MATRIX.md` (Normal, Loading, Empty, Error, Offline, etc.).
- [ ] Strict role separation enforced: Standard User cannot access `#access-registry`, `#audit`, or Owner settings.
- [ ] FIDO2/WebAuthn passkey ceremonies succeed seamlessly on desktop browsers (YubiKey/TouchID/Windows Hello) and mobile (iOS FaceID/Android Biometrics).
- [ ] `RuntimeAvailability` fail-closed overlay intercepts all network interruptions within 2000ms.
- [ ] Zero live broker mutations sent; safety badges permanently visible.
