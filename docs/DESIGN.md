---
version: 1.0.0
name: SentinelX-Control-Center-Design-System
description: "A high-density, desktop-class dark visual language engineered for fail-closed algorithmic trading, risk governance, and security operations. Built on ultra-deep navy canvas (#05080e), four-step surface elevations (#090e17 through #172033), hairline border grids (#182232, #24334a), and crisp slate typography (#f0f4f8, #94a3b8) with JetBrains Mono for telemetry, prices, and cryptographic fingerprints. Strict fail-closed trust badges (FRESH / STALE / UNKNOWN) communicate data authority. No decorative AI-purple gradients, no fake green statuses, and no clipped viewport geometry."
---

# SentinelX Design System & Visual Authority (`DESIGN.md`)

SentinelX is an institutional-grade, fail-closed algorithmic trading platform and security control center. The interface communicates uncompromising precision, technical authority, and operational clarity.

---

## 1. Visual Theme & Atmosphere

- **Core Aesthetic**: Institutional dark desktop terminal (Linear precision + TradingView data density + Bloomberg clarity).
- **Dominant Tone**: Ultra-deep slate/navy canvas with subtle cool undertones. No pure pitch-black `#000000` voids, no AI-purple gradient slop, no distracting decorative mesh animations.
- **Fail-Closed Semantics**: State is only represented from authoritative backend evidence. Missing data is `UNKNOWN`, expired data is `STALE`, verified authoritative data is `FRESH`. Never fake green statuses.
- **Density Philosophy**: High data density without visual claustrophobia. Clear 1px hairline delimiters, explicit cell paddings, crisp tabular alignment for numbers.

---

## 2. Color Palette & Roles

### Canvas & Surface Ladder
| Token | Hex / Value | Role |
|---|---|---|
| `canvas` | `#05080e` | Deepest root canvas, behind all panels and sidebar |
| `surface-1` | `#090e17` | Sidebar background, primary panel surface, table body |
| `surface-2` | `#101725` | Elevated metric cards, table headers, hover states, sub-bars |
| `surface-3` | `#172033` | Active tab pills, input fields, popovers, dropdown containers |
| `surface-4` | `#1f2c42` | Highlighted rows, active focus backdrops, elevated overlays |
| `hairline` | `#182232` | 1px standard border for cards, table rows, structural dividers |
| `hairline-strong` | `#24334a` | Elevated borders, active tab outlines, hover borders |
| `hairline-accent` | `#3b4f6e` | Focus rings, key structural emphasis |

### Typography / Ink
| Token | Hex / Value | Role |
|---|---|---|
| `ink-primary` | `#f0f4f8` | Primary headlines, metric values, active navigation items |
| `ink-secondary` | `#94a3b8` | Subheadings, table cell text, card descriptions, labels |
| `ink-muted` | `#50627a` | Table headers, timestamp metadata, inactive icons, helper text |
| `ink-dim` | `#334155` | Disabled labels, placeholder text, inactive border markers |
| `ink-mono` | `#cbd5e1` | Monospace numbers, order IDs, timestamps, hex fingerprints |

### Semantic & Trust Accents
| Token | Base Hex | Dark BG | Text Tint | Role |
|---|---|---|---|---|
| `semantic-emerald` | `#10b981` | `rgba(16, 185, 129, 0.12)` | `#34d399` | Bullish candles, FRESH trust badge, Live status, Configured |
| `semantic-ruby` | `#ef4444` | `rgba(239, 68, 68, 0.12)` | `#f87171` | Bearish candles, UNKNOWN trust badge, Step-up required, Stop loss, Forbidden |
| `semantic-amber` | `#f59e0b` | `rgba(245, 158, 11, 0.14)` | `#fbbf24` | STALE trust badge, Safe Mode active, Needs Rotation, Trailing stop |
| `semantic-sky` | `#0284c7` | `rgba(2, 132, 199, 0.14)` | `#38bdf8` | Primary command actions, Frozen historical view, Focus ring, Target overlay |

---

## 3. Typography Scale & Hierarchy

### Font Families
- **Primary UI Sans**: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
- **Telemetry & Numbers**: `JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`

### Scale Hierarchy
| Role | Size | Weight | Line Height | Tracking | Font |
|---|---|---|---|---|---|
| Display / Top Bar Title | 20px | 700 (Bold) | 1.2 | -0.5px | Sans |
| Section Headline / Card Title | 15px | 600 (SemiBold) | 1.3 | -0.3px | Sans |
| Large Metric Value | 26px | 700 (Bold) | 1.1 | -0.5px | Sans / Mono |
| Body / Table Data | 13px | 400–500 | 1.45 | -0.1px | Sans |
| Small / Meta / Table Header | 11px | 600 (SemiBold) | 1.3 | +0.2px | Sans |
| Eyebrow / Category Tag | 10px | 700 (Bold) | 1.0 | +0.8px (Caps) | Sans |
| Monospace Telemetry / Code | 12px | 500 (Medium) | 1.4 | 0 | Mono |
| Micro / Timestamp | 10px | 500 (Medium) | 1.2 | 0 | Mono |

---

## 4. Geometry & Elevation System

- **Border Radius**:
  - Micro / Badge: `4px`
  - Control / Button / Input: `6px`
  - Panel / Card / Table Container: `8px`
  - Modal / Security Gate Box: `12px`
  - *No oversized full-pill buttons in desktop panels.*
- **Shadows**:
  - Whisper Lift: `0 4px 12px rgba(0, 0, 0, 0.45)`
  - Elevated Popover: `0 12px 32px rgba(0, 0, 0, 0.65)`
  - Inner Hairline Edge: `inset 0 1px 0 rgba(255, 255, 255, 0.05)`

---

## 5. Layout Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TOP STATUS BAR: Brand • Workspace • Engine Status • Safe Mode • UTC Clock   │
├──────────────┬──────────────────────────────────────────────────────────────┤
│ SIDEBAR      │ MAIN CONTENT AREA (Grid / Canvas / Blotter)                 │
│              │                                                              │
│ • Overview   │  ┌────────────────────────────────────────────────────────┐  │
│ • Strategies │  │ METRIC SUMMARY CARDS (Dense 4-col responsive grid)     │  │
│ • Backtest   │  ├────────────────────────────────────────────────────────┤  │
│ • Paper      │  │ WORKSPACE / CANDLESTICK CHART / GOVERNANCE PIPELINE     │  │
│ • Live       │  │ (Canvas rendered, crosshair, timeframe selector)       │  │
│ • Portfolio  │  ├────────────────────────────────────────────────────────┤  │
│ • Trades     │  │ HIGH-DENSITY AUDIT / ORDER BLOTTER / EXECUTION TABLE    │  │
│ • Market     │  │ (Mono numbers, status pills, strict column alignment)   │  │
│ • Audit      │  └────────────────────────────────────────────────────────┘  │
│ • Settings   │                                                              │
│ • Security   │                                                              │
├──────────────┴──────────────────────────────────────────────────────────────┤
│ FOOTER / STATUS TAPE: Trust Evidence • Fingerprint • Authority • Build Ver │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Sidebar**: Fixed width `230px`, dark linear surface `#090e17`, clean vertical navigation with left accent bar for active route.
- **Top Command Bar**: Height `52px`, fixed at top of content, displays real-time UTC timestamp, safe-mode status pill, engine state, and active route identity.
- **Main Viewport**: High-performance scrolling container with `padding: 20px 24px`, max-width `1920px`.

---

## 6. Component Guidelines

### Trust Badges
- **`FRESH`**: Emerald background (`rgba(16,185,129,0.14)`), emerald text (`#34d399`), 1px border (`rgba(16,185,129,0.3)`).
- **`STALE`**: Amber background (`rgba(245,158,11,0.14)`), amber text (`#fbbf24`), 1px border (`rgba(245,158,11,0.3)`).
- **`UNKNOWN`**: Ruby background (`rgba(239,68,68,0.14)`), ruby text (`#f87171`), 1px border (`rgba(239,68,68,0.3)`).

### Interactive Charts
- High-DPI canvas rendering.
- Dark canvas background (`#08101a`), subtle grid lines (`#142030`), crosshair readout for price and time.
- Bullish candles in emerald `#10b981`, Bearish candles in ruby `#ef4444`.
- Overlay lines (STOP, TARGET, TRAILING) with distinct dashed signatures and crisp inline labels.
- Mode tags: `LIVE MARKET`, `FROZEN HISTORICAL VIEW`, `BACKTEST ANALYSIS`.

### High-Density Data Tables
- Header: `#101725` background, uppercase 10px tracking `+0.05em`, color `#50627a`.
- Row: Alternating hover `#121b2a`, 1px hairline borders `#182232`.
- Numbers and timestamps right-aligned and rendered in monospace font.

### Unauthenticated Security Perimeter (Login)
- Centered vault card (`max-width: 480px`) with institutional border highlight and security status indicators.
- WebAuthn Hardware Security Key as primary primary action.
- Trusted-Host Bootstrap Authorization input with clear disclosures.
- Prominent fail-closed security status matrix.

### Dev Preview Inspector (Non-Authoritative)
- Distinctive warning banner at the top of the interface: `DEV PREVIEW — NON-AUTHORITATIVE • LOCAL VISUAL INSPECTION ONLY`.
- Allows developer navigation across all 11 panels to inspect layouts and responsive behavior without faking backend credentials or security authority.

---

## 7. Anti-Patterns & Hard Rules

- ❌ **No fake green statuses**: If backend data is disconnected or missing, show `UNKNOWN` or `UNAVAILABLE`.
- ❌ **No AI-purple gradients or floating decorative spheres**.
- ❌ **No clipped text or broken layout overflow**.
- ❌ **No placeholder div fake screenshots**.
- ❌ **No huge empty unused regions on desktop viewports**.
