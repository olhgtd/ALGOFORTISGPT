# AlgoFortis — Responsive & Multi-Device Requirements
**Functional Prioritization & Form Factor Specifications for External UI Engineering**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Multi-Device Objective & Form Factor Targets
AlgoFortis must provide an institutional, reliable trading research experience across 5 core form factors:
1. **Desktop Workstation** (>= 1440px width): Multi-monitor high-density quant layout.
2. **Laptop Display** (1024px – 1439px width): Compact single-screen layout with collapsible panels.
3. **Tablet Landscape** (900px – 1023px width): Touch-optimized dual-pane workspace.
4. **Tablet Portrait** (600px – 899px width): Single-column stacked cards with bottom navigation sheet.
5. **Mobile Handheld** (< 600px width): High-priority monitoring, panic actions, and passkey authentication.

---

## 2. Functional Priority Hierarchy by Form Factor

| Screen / Feature Domain | Desktop & Laptop | Tablet Landscape | Tablet Portrait & Mobile | High-Priority Must-Remain-Visible Data |
|---|---|---|---|---|
| **Secure Entry (`AUTH-001`)** | Full Centered Card with Canvas Shield | Centered Card | Full-Width Bottom Sheet / Clean Card | Authenticator touch prompt, Error reason, Invariant lock status. |
| **Trader Home (`USR-001`)** | Multi-Column (Chart + KPIs + Orders + Quick Trade) | 2-Column Split (Chart + KPIs on top, Orders below) | Single Column (KPI Carousel -> Mini Chart -> Position List) | Total Equity, Today PnL, Active Strategy Count, Live Safety Badge. |
| **Backtesting Lab (`USR-003`)** | Side-by-Side Config + Full Multi-Chart Report | Collapsible Config Accordion + Full Report | Form Stepper -> Full-Screen Report with Tabbed Charts | Net Profit, Max DD, Sharpe Ratio, Progress %, Stop Run button. |
| **Paper Trading (`USR-004`)** | Chart + Orderbook + Open Positions Grid | Chart + Position Table | Mini Chart + Position Cards with Panic Flatten Button | Live Bid/Ask, Position PnL, Emergency Flatten Button. |
| **Owner Control Center (`OWN-001`)** | Full System Health Grid + 24h Audit Stream | Health Cards Grid + Collapsed Audit Stream | Stacked Health Cards + Critical Alert Pills | Database Status, Schema Version, Global Hold Switch. |
| **Owner User Registry (`OWN-003`)** | Full 8-Column Table with Action Dropdowns | Horizontal Scrollable Table with Sticky User Column | Card List per User with Expandable Action Drawer | User Email, Status Badge, Expiry Date, Suspend Button. |
| **Audit Trail (`OWN-009`)** | Full Cryptographic Event Table with Hash Inspection | Filterable Table with Hash Popover | Event Stream List with Tap-to-Inspect Drawer | Timestamp, Actor ID, Event Type, Status. |

---

## 3. Responsive Navigation & Shell Transformation Rules

### 3.1 Navigation Bar & Sidebar Behavior
- **Desktop (>= 1024px):** Persistent left sidebar navigation (240px) with icons and full labels, plus top status bar with system clocks and safety badges.
- **Tablet (600px – 1023px):** Left sidebar automatically collapses to icon-only rail (64px). Tapping icon opens slide-out sub-navigation if sub-menus exist.
- **Mobile (< 600px):**
  - Left sidebar transforms into a **Bottom Navigation Bar** displaying 4 critical items: `Home`, `Paper/Trade`, `Strategies`, `More`.
  - "More" opens a full-height slide-over drawer containing secondary routes (Audit, Connections, Settings, Passkeys).

### 3.2 Tables to Responsive Card Transformations
Large multi-column data tables (Orders, Users, Trades, Access Tokens) must adapt gracefully:
- **Desktop/Laptop:** Native high-density tabular grid with sortable column headers.
- **Tablet:** Table with fixed left column (e.g. Symbol or User Identifier) and horizontally swipeable remaining metric columns.
- **Mobile Handheld:** Tables transform into **Compact Summary Cards**. Each card shows:
  - Header: Primary Identifier + Status Badge (e.g. `BTC/USDT` | `[FILLED]`).
  - Body: 2x2 grid of key values (e.g., `Qty: 0.5`, `Price: $58,750`, `PnL: +$420`, `Time: 14:32:01`).
  - Footer / Tap Action: Tapping the card opens a detail bottom sheet displaying microsecond timestamps and raw DTO JSON.

---

## 4. Touch Targets & Mobile Ergonomics
1. **Touch Target Sizing:** All interactive buttons, tabs, table action triggers, and icon buttons must maintain a minimum touch target area of **44px × 44px** on touch-enabled viewports.
2. **Emergency Action Ergonomics:** The "Panic Flatten" and "Engage Global Hold" buttons must be positioned within the thumb-accessible bottom reach zone on mobile viewports with a 2-step confirmation sheet to prevent accidental triggers.
3. **WebAuthn UX on Mobile:** On iOS and Android browsers, WebAuthn triggers native platform sheet biometrics (FaceID/Fingerprint). The UI must provide a clean "Touch to authenticate" trigger that respects platform OS prompts without duplicate loading overlays.

---

## 5. Chart & Financial Visualization Responsiveness
- **Desktop / Laptop:** Interactive Canvas/SVG chart with crosshair cursor, volume pane, and drawing tools.
- **Tablet:** Pinch-to-zoom and two-finger pan enabled on chart canvas; timeframe selector rendered as horizontal scroll pill bar.
- **Mobile:** Fixed aspect ratio (16:9 or 4:3) with simplified crosshair on single tap; indicator overlays collapsed into a bottom configure sheet.

---

## 6. Runtime Availability & Safety Banner Visibility
- The `RuntimeAvailability` barrier (`STARTING`, `RECONNECTING`, `UNAVAILABLE`) and the top-level safety lock badge (`READ_ONLY: TRUE`, `DISARMED: TRUE`) must remain **100% visible and un-clipped across all screen sizes and orientations**.
