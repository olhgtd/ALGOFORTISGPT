# AlgoFortis User Dashboard Shell + Home Command Center Design

Date: 2026-09-28
Status: DESIGN SPEC — awaiting user review before implementation
Branch: `v2-convergence-v1-salvage-20260928`

## 1. Purpose

Build the inside-the-app AlgoFortis user experience first, while leaving the Entry Gate for later V1 reuse/merge. The first implementation slice is the reusable User Dashboard Shell plus the Home / Command Center. This becomes the visual, interaction, safety, and component benchmark for all remaining user-side pages.

The design must feel like a premium institutional trading terminal: deep graphite/near-black surfaces, restrained gold and platinum, strong information hierarchy, precise motion, no gaming-neon look, no random gradient overload, and no decorative animation that interferes with trading clarity.

## 2. Existing Runtime Baseline to Preserve

The current `DashboardV3App` already separates User and Owner workspaces and delegates the user surface to `UserDashboardApp`. That dispatcher remains the outer runtime boundary.

Current reusable user-side building blocks include:
- `UserDashboardApp`
- `UserHome`
- `ProfessionalChart`
- `OptionsWorkspace`
- command palette / `Ctrl+K`
- `GlobalRealTimeClock`
- theme support
- integration client/profile plumbing
- existing reusable drawers, truth chips, icons, sparklines, status utilities

The new work must reuse sound runtime/service behavior where compatible, but is not visually constrained by the old dashboard.

## 3. Product Scope

This spec covers only the normal user workspace.

In scope:
- reusable dashboard shell
- top system/status bar
- left desktop navigation
- mobile-ready shell structure
- global notification entry point
- profile/theme controls
- Home / Command Center
- shared visual primitives needed by Home
- motion rules used by the shell and Home
- truthful loading/empty/error/recovery states

Out of scope for this slice:
- Entry Gate / login redesign
- Owner/Admin workspace redesign
- full Markets page
- full Strategies page
- full Testing & Validation page
- full Trades page
- full Portfolio page
- full Account page
- cloud/mobile production deployment
- any Live execution enablement

## 4. Final User Navigation

Normal user navigation is:

1. Home
2. Markets
3. Strategies
4. Testing & Validation
5. Trades
6. Portfolio
7. Account

Notifications are a global layer accessed from the top bar, not a normal nav page.

The following remain hidden from normal users:
- strategy hunting internals
- internal research queue
- Laya training/model internals
- agent orchestration
- prompts/providers/memory/tools
- release certification
- system master-risk controls
- dataset/experiment internals
- other-user registry/access administration
- raw audit/incidents
- deployment/master-admin controls

## 5. Dashboard Shell

### 5.1 Desktop layout

The shell has three primary regions:

- fixed top system bar
- fixed/collapsible left navigation rail
- main content canvas

The layout must prioritize dense information without feeling cramped.

### 5.2 Top system bar

The top bar shows only system-level context that matters everywhere:

- compact AlgoFortis brand mark
- current operational mode: Backtest / Paper / Live
- Live state when present: `READ_ONLY / DISARMED`
- selected/default broker summary
- broker connection health
- local engine/host health
- notification bell with unread priority indicator
- theme control
- profile/account entry
- real-time clock

The bar must not imply that broker-connected means Live-enabled.

### 5.3 Left navigation

The left rail uses the final user navigation only. Active state is obvious but restrained. Gold is reserved for focus/identity, not for every selected control.

Navigation transitions should be quick and directional; no full-page flashy animation.

### 5.4 Mobile/responsive shell

Desktop-first implementation. Structure must permit a later mobile bottom-navigation treatment, but full production mobile/push behavior is deferred.

## 6. Visual System

### 6.1 Typography

- Main UI: Manrope
- Trading numerics and dense status values: IBM Plex Mono
- AlgoFortis wordmark/logo keeps its own brand identity and is not used as the general UI font

### 6.2 Color language

Base:
- near-black / deep charcoal canvas
- matte graphite surfaces
- subtle warm-gold accents
- platinum/silver secondary accents

Semantic colors:
- green only for positive/healthy/filled/connected trading semantics
- red only for loss/error/risk-critical semantics
- amber/gold for attention, selected premium actions, identity, and certain warnings

No purple/blue gradient SaaS look. No neon cyberpunk treatment.

### 6.3 Surfaces

- thin low-contrast borders
- soft deep shadows
- small selective use of glass, never full glass-card overload
- moderate radius, not bubble UI
- data tables and operational cards remain crisp and flat enough for scanning

## 7. Motion System

Motion must explain state changes.

Use:
- subtle card elevation on hover
- fast tab/rail transitions
- status-chip morphs for state changes
- number updates with short controlled interpolation where useful
- drawer/notification slides
- contextual progress animation for testing/runtime events
- success transforms, not confetti

Avoid:
- bouncing cards
- looping decorative motion in main trading areas
- large parallax
- dramatic background movement
- anything that hides or delays safety states

Paper vs Live transitions must be unmistakable. Critical risk/recovery states must appear immediately without waiting for decorative animation.

## 8. Home / Command Center Purpose

Home answers four questions immediately:

1. What is the system doing now?
2. What is the market doing now?
3. What is my trading/portfolio state now?
4. What needs my attention now?

It is not a full analytics page and must not duplicate every deeper page.

## 9. Home Information Architecture

### 9.1 Command strip

Top Home strip shows:
- current mode: Backtest / Paper / Live
- automation state: Running / Paused / Stopped / `HALT_ENTRIES` / `RECOVERY` / `READY_FOR_RESUME`
- local engine status
- selected broker status
- data freshness/session status

`RECOVERY` and `READY_FOR_RESUME` must be visually distinct. Clean reconciliation must never visually imply automatic resume.

### 9.2 Market snapshot

Compact NIFTY / BANKNIFTY region:
- current value
- session change
- session status
- data freshness
- market regime summary
- compact chart/sparkline or mini market view

The full professional chart belongs on Markets, not Home.

### 9.3 Portfolio / capital summary

Portfolio summary supports multiple brokers while preserving the rule that each broker account is a separate capital pool.

Show aggregate overview plus clear broker-wise decomposition:
- total equity
- available funds
- used capital/margin
- today P&L
- open P&L
- realized P&L
- drawdown

Never present cross-broker funds as freely routable combined capital.

### 9.4 Positions

Compact active-position list:
- broker
- strategy
- instrument/contract
- lots
- current quantity derived from lots × broker/exchange lot size
- entry/current price
- P&L
- SL/target state
- trade state

Home shows only a compact subset and links to Trades.

### 9.5 Strategies summary

Show:
- active/deployed strategies
- lifecycle state
- paper/live eligibility state
- latest relevant test/validation status
- warning if edits invalidated prior validation

Do not expose internal research or strategy-hunting machinery.

### 9.6 Risk summary

Simple operational states:
- normal
- attention
- restricted
- halted
- recovery

Show user-actionable reasons only. Raw internals belong elsewhere.

Emergency controls remain distinct concepts:
- Pause / `HALT_ENTRIES`
- Cancel Pending
- Flatten / Exit

Risk-reducing actions must not inherit strong-step-up dependencies intended for high-risk actions.

### 9.7 Testing progress

Compact background-job area:
- Backtest
- Walk-Forward
- OOS
- Robustness
- Validation

Show truthful queued/running/completed/failed states. Do not fabricate PASS results.

### 9.8 Notifications / attention

Home can show a compact high-priority feed, but the global bell owns the full notification center.

Priority classes:
- Critical
- Action Required
- Important
- Info

Critical safety/security notifications cannot be disabled.

### 9.9 Recent activity

Compact recent events:
- strategy state changes
- test completion
- broker state changes
- fills/exits
- risk blocks
- recovery events

Detailed order timelines live in Trades.

### 9.10 Laya surface

If Laya appears on Home in V2.0, it is strictly informational/shadow-only.

Allowed:
- regime summary
- market observation
- informational confidence/context

Not allowed:
- Confirm
- Auto
- direct order action
- broker authority
- hidden chain-of-thought

## 10. Trading and Safety Invariants

The UI must preserve these product invariants:

- Live defaults to `READ_ONLY / DISARMED`
- broker connection never auto-enables Live
- only the approved engine path can create executable orders
- `RiskGateV2` remains the sole authority that mints an `ApprovedOrder`
- options scope is BUY-only
- Laya cannot directly execute
- no automatic resume after safety halt/recovery
- no automatic arm
- missing/mismatched lot size fails closed; UI never guesses
- strategy edit resets relevant validation
- emergency risk-reducing actions stay available even when stronger auth or cloud services are unavailable

## 11. Data and Truthfulness

The Home implementation must distinguish:
- authoritative runtime data
- unavailable data
- stale data
- loading data
- empty data
- demo/preview-only data

No fabricated P&L, broker health, pass state, or Live status.

Where an authoritative endpoint is not yet wired, show a named unavailable/empty state rather than fake business data.

## 12. Component Boundaries

Initial component breakdown:

- `UserDashboardApp` — navigation/shell orchestration
- `UserTopBar` — global operational context
- `UserNavRail` — final user nav
- `NotificationCenter` — global notification layer
- `HomeCommandCenter` — Home composition only
- `OperationalStateStrip`
- `MarketSnapshotCard`
- `CapitalSummary`
- `PositionsSummary`
- `StrategyStatusSummary`
- `RiskSummary`
- `TestingProgressSummary`
- `RecentActivitySummary`
- shared status chip / metric / card primitives

Existing reusable components such as `ProfessionalChart`, `OptionsWorkspace`, drawers, icons, and runtime utilities remain available for deeper pages where appropriate.

## 13. Error / Recovery UX

Required explicit states:
- data unavailable
- broker disconnected
- broker stale
- engine unavailable
- stale market feed
- safety halt
- recovery in progress
- ready for manual resume
- testing failed
- no strategies
- no broker configured
- no positions

Errors should state what is known, what is unknown, and the safe next action. Never silently degrade a safety state into a healthy-looking card.

## 14. Testing Requirements

At minimum the implementation plan must cover:

- navigation renders only final normal-user items
- owner/admin surfaces are not exposed through normal user nav
- agents/Laya internals remain hidden
- Live renders as `READ_ONLY / DISARMED` unless later eligibility work explicitly changes it
- broker-connected does not imply Live-armed
- `RECOVERY` does not auto-transition to Running
- `READY_FOR_RESUME` requires explicit manual resume action
- Paper and Live are visually distinguishable
- loading/empty/stale/error states render truthfully
- responsive shell preserves usable navigation
- critical risk state is not hidden by animation
- no fake PASS/P&L/business data introduced by the new Home composition

## 15. Implementation Order

1. lock shared visual tokens and typography
2. refactor `UserDashboardApp` into the final shell structure while preserving runtime routing
3. implement final user navigation
4. implement top system/status bar
5. build reusable shell primitives
6. build `HomeCommandCenter`
7. wire authoritative/available current data sources
8. add truthful empty/unavailable states where integration is not ready
9. add restrained motion and state transitions
10. run UI tests and safety-state regression checks

## 16. Success Criteria

This slice is complete when:

- opening the authorized user workspace lands on a premium, coherent Home Command Center
- the final user navigation is present and old user-nav clutter is removed from normal navigation
- visual language is consistent with AlgoFortis gold/platinum institutional branding
- Home answers current system/market/portfolio/risk/action state without exposing owner/research internals
- all safety-critical states remain truthful and fail-closed
- no Entry Gate rewrite is required for this slice
- remaining pages can be built on the same shell/component system without redesigning the foundation
