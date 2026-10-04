# AlgoFortis — Current Design System Inventory
**Authoritative Visual Tokens, Layouts, Components & Typography Specification**
**Product Brand:** AlgoFortis | **Tagline:** Trading Research & Risk OS
**Safety Lock:** `READ_ONLY: true` | `DISARMED: true` | `live_global_hold: true` | `broker mutation: ZERO` | `real broker connection: NONE`

---

## 1. Typography & Type Scale

| Property / Token | Value / Font Family | Classification | Usage in Codebase |
|---|---|---|---|
| **Primary Sans Font** | `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` | `CURRENT` | Global UI text, headings, cards, navigation. |
| **Monospace / Numerical Font** | `'JetBrains Mono', 'Fira Code', 'Roboto Mono', Menlo, monospace` | `CURRENT` | Numbers, prices, PnL metrics, timestamps, SHA256 hashes, AST code. |
| **Hero Display Heading** | `font-size: 2.75rem (44px)`, `font-weight: 800`, `line-height: 1.15` | `CURRENT` | Public landing page hero, master title cards. |
| **H1 Screen Title** | `font-size: 1.75rem (28px)`, `font-weight: 700`, `line-height: 1.25` | `CURRENT` | Main screen titles across Owner and User dashboards. |
| **H2 Section Header** | `font-size: 1.25rem (20px)`, `font-weight: 600`, `line-height: 1.3` | `CURRENT` | Sub-section headers, card category titles. |
| **H3 Card Header** | `font-size: 1.05rem (16.8px)`, `font-weight: 600`, `line-height: 1.4` | `CURRENT` | Table headers, modal titles, KPI card labels. |
| **Body Regular** | `font-size: 0.875rem (14px)`, `font-weight: 400`, `line-height: 1.5` | `CURRENT` | Standard body copy, form labels, table cell content. |
| **Body Small / Captions** | `font-size: 0.75rem (12px)`, `font-weight: 500`, `line-height: 1.4` | `CURRENT` | Metadata timestamps, badge labels, footnote notes. |
| **Micro / Subtext** | `font-size: 0.6875rem (11px)`, `font-weight: 600`, `letter-spacing: 0.05em` | `CURRENT` | Status indicator pills, uppercase category chips. |

---

## 2. Color Palette & Semantic Tokens

### 2.1 Dark Mode Palette (Default Core Theme)

| Semantic Role | Token / Variable | Hex / HSL Value | Classification |
|---|---|---|---|
| **Canvas Background** | `--bg-canvas` | `#0b0f17` (Deep Obsidian Void) | `CURRENT` |
| **Surface / Card Background** | `--bg-surface` | `#111827` (Dark Navy Gray) | `CURRENT` |
| **Elevated Surface (Modals/Menus)** | `--bg-elevated` | `#1f2937` (Charcoal Slate) | `CURRENT` |
| **Card Border** | `--border-subtle` | `rgba(255, 255, 255, 0.08)` | `CURRENT` |
| **Interactive Border Focus** | `--border-focus` | `#3b82f6` (Vibrant Blue) | `CURRENT` |
| **Primary Accent (AlgoFortis Blue)** | `--color-primary` | `#2563eb` / `#3b82f6` | `CURRENT` |
| **Primary Hover** | `--color-primary-hover` | `#1d4ed8` | `CURRENT` |
| **Text High Emphasis** | `--text-primary` | `#f9fafb` (Pure White Slate) | `CURRENT` |
| **Text Medium Emphasis** | `--text-secondary` | `#9ca3af` (Muted Cool Gray) | `CURRENT` |
| **Text Low Emphasis / Disabled** | `--text-tertiary` | `#6b7280` (Deep Muted Gray) | `CURRENT` |

### 2.2 Financial & Status Palette

| Status / Domain | Token / Variable | Hex Value | Semantic Meaning in Product | Classification |
|---|---|---|---|---|
| **Success / Long / Profit** | `--color-success` | `#10b981` (Emerald 500) | Positive PnL, Active service, Passed backtest, Healthy subsystem | `CURRENT` |
| **Danger / Short / Loss** | `--color-danger` | `#ef4444` (Rose 500) | Negative PnL, Suspended user, Drawdown breach, Revoked key | `CURRENT` |
| **Warning / Caution** | `--color-warning` | `#f59e0b` (Amber 500) | Expiring service, Degraded adapter, Quarantined strategy | `CURRENT` |
| **Informational / Neutral** | `--color-info` | `#06b6d4` (Cyan 500) | Paper trading simulation mode, Telemetry streaming | `CURRENT` |
| **Safety Hold / Emergency** | `--color-emergency` | `#dc2626` (Red Alert) | `GLOBAL EXECUTION HOLD`, `DISARMED: TRUE` | `CURRENT` |

---

## 3. Spacing, Radii, Shadows & Borders

| Token Name | Value | Classification | Usage |
|---|---|---|---|
| **`space-1` (4px)** | `0.25rem` | `CURRENT` | Micro-padding, badge icon gap. |
| **`space-2` (8px)** | `0.5rem` | `CURRENT` | Input internal padding, card element gap. |
| **`space-3` (12px)** | `0.75rem` | `CURRENT` | Table cell vertical padding, sidebar item gap. |
| **`space-4` (16px)** | `1.0rem` | `CURRENT` | Standard card padding, grid gutter. |
| **`space-6` (24px)** | `1.5rem` | `CURRENT` | Screen content padding, section margin. |
| **`space-8` (32px)** | `2.0rem` | `CURRENT` | Modal body padding, hero spacing. |
| **`radius-sm`** | `4px` | `CURRENT` | Badges, tags, micro-buttons. |
| **`radius-md`** | `8px` | `CURRENT` | Form inputs, standard buttons, dropdown menus. |
| **`radius-lg`** | `12px` | `CURRENT` | Cards, table containers, popover drawers. |
| **`radius-xl`** | `16px` | `CURRENT` | Modals, Secure Entry login card, Hero container. |
| **`shadow-card`** | `0 4px 6px -1px rgba(0, 0, 0, 0.3)` | `CURRENT` | Standard dashboard cards. |
| **`shadow-modal`** | `0 20px 25px -5px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255,255,255,0.1)` | `CURRENT` | Elevated modals and WebAuthn dialogs. |

---

## 4. Layout Dimensions & Structure

| Layout Dimension | Current Value | Classification | Notes |
|---|---|---|---|
| **Max Content Width** | `1440px` (or `100% fluid` on wide displays) | `CURRENT` | Centered layout container. |
| **Sidebar Width (Expanded)** | `240px` | `CURRENT` | Desktop sidebar showing icons + labels. |
| **Sidebar Width (Collapsed)** | `64px` | `CURRENT` | Icon-only collapsed rail mode. |
| **Top Header Height** | `60px` | `CURRENT` | Fixed top navigation bar. |
| **Modal Max Width (Standard)** | `560px` | `CURRENT` | Confirmation and input dialogs. |
| **Modal Max Width (Wide/Table)** | `900px` | `CURRENT` | `PromotionReviewModal`, `DocsModal`. |
| **Drawer Width** | `420px` | `CURRENT` | Strategy parameter and user inspector drawers. |

---

## 5. UI Consistency & Outlier Audit

- **Consistent System Elements:** Dark mode color tokens, WebAuthn flow glassmorphism card, monospace data formatting, table action buttons, and status badge color conventions.
- **`LOCAL OVERRIDE` Elements:** Certain interactive canvas elements in `CinematicHero.tsx` and `AlgoFortisCore.tsx` render direct WebGL/Canvas styles independent of CSS classes.
- **`INCONSISTENT` Areas:** Font family fallbacks occasionally list `system-ui` vs `-apple-system` in legacy CSS blocks. Redesign team should consolidate all font rules to standard root CSS custom properties.
