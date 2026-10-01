# AlgoFortis User Dashboard Shell + Home Command Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to execute this plan. Follow TDD and verify before completion.

**Goal:** Replace the old normal-user dashboard shell/Home with the approved AlgoFortis user shell and truthful Home / Command Center, while preserving the existing User/Owner runtime boundary and keeping Live `READ_ONLY / DISARMED`.

**Architecture:** Keep `DashboardV3App` as the outer User/Owner dispatcher. Refactor only the normal-user surface into a small shell + read-only Home view model + focused presentational components. Authoritative backend queries feed Home where available; missing authority renders explicit unavailable/stale/empty states rather than sample values or invented zeros. Full Markets/Strategies/Testing/Trades/Portfolio/Account redesigns are separate follow-up slices.

**Tech Stack:** React 19, TypeScript 7, Vite 8, Vitest 4, jsdom, existing AlgoFortis integration client and V3 shared utilities.

**Spec:** `docs/superpowers/specs/2026-09-28-user-dashboard-shell-home-design.md`

## Global Constraints

- Entry Gate is out of scope and remains unchanged.
- Owner/Admin workspace is out of scope and remains unchanged.
- Final normal-user nav is exactly: `Home`, `Markets`, `Strategies`, `Testing & Validation`, `Trades`, `Portfolio`, `Account`.
- Live is always presented as `READ_ONLY / DISARMED`; broker connectivity never implies Live is armed.
- Recovery/safety halt never auto-resumes. `RECOVERY` and `READY_FOR_RESUME` require manual resume.
- RiskGateV2 remains the sole executable-order authority; this slice adds no order authority.
- Options remain BUY-only. Do not expose the existing sample SELL/short-option fixtures in the new Home.
- Laya is research/shadow-only; no Confirm/Auto/order authority and no chain-of-thought.
- No fabricated P&L, broker state, market value, PASS state, win rate, or health state.
- Missing/stale authority is shown explicitly as `UNAVAILABLE`, `STALE`, `UNKNOWN`, loading, or empty.
- Paper/session capital rows remain distinct. Do not present separate broker/session balances as one freely routable spendable pool.
- Use existing `/algofortis_logo.png`; do not introduce another branding system in this slice.
- Keep old screens/files for compatibility until their individual redesign slices; do not delete unrelated legacy surfaces.
- User-only visual changes must be scoped so Owner visuals are not unintentionally restyled.

## Review Focus

1. Backend unavailable on startup must never become fake `₹0`, green health, or a fake PASS.
2. Broker/connection state `CONNECTED` must still render Live as `READ_ONLY / DISARMED`.
3. `RECOVERY` / `READY_FOR_RESUME` must stay manual-resume states and never derive `RUNNING` automatically.
4. Multiple account/capital pools must stay visibly distinct; no cross-broker spendable-funds implication.
5. Critical risk/recovery state must be immediate and readable even with motion/reduced-motion settings.

---

## Task 1 — Add a user-dashboard test harness and lock the final navigation contract

**Files:**
- Modify: `dashboard/web/package.json`
- Create: `dashboard/web/vitest.config.ts`
- Create: `dashboard/user-dashboard/navigation.ts`
- Create: `dashboard/user-dashboard/navigation.test.ts`

**Interfaces**
- Consumes: existing `IconName` from `dashboard/shared/icons/V3Icons.tsx`.
- Produces: `UserScreenId`, `UserNavItem`, `USER_NAV_ITEMS`, and a single canonical list used by desktop/mobile/palette navigation.

- [ ] **Step 1: Write the failing navigation test.**

Assert the exact ordered labels and IDs:

```ts
[
  ["home", "Home"],
  ["markets", "Markets"],
  ["strategies", "Strategies"],
  ["testing", "Testing & Validation"],
  ["trades", "Trades"],
  ["portfolio", "Portfolio"],
  ["account", "Account"],
]
```

Also assert that normal-user navigation does **not** contain `connections`, `trading`, `backtest`, `paper`, `orders`, `reports`, `security`, `help`, `agents`, `control`, or `users`.

- [ ] **Step 2: Run the focused test and confirm RED.**

```powershell
cd dashboard/web
npm run test:user-dashboard -- ../user-dashboard/navigation.test.ts
```

Expected: fail because the test script/config/navigation module do not yet exist.

- [ ] **Step 3: Add the Vitest script/config and canonical navigation module.**

`package.json` adds only a test script; dependencies already include Vitest/jsdom.

```json
"test:user-dashboard": "vitest run -c vitest.config.ts"
```

`vitest.config.ts` must reuse the React aliases from `vite.config.ts`, use `jsdom`, and include user-dashboard tests without changing production Vite behavior.

- [ ] **Step 4: Run the focused test and confirm GREEN.**

```powershell
npm run test:user-dashboard -- ../user-dashboard/navigation.test.ts
```

- [ ] **Step 5: Commit.**

```powershell
git add dashboard/web/package.json dashboard/web/vitest.config.ts dashboard/user-dashboard/navigation.ts dashboard/user-dashboard/navigation.test.ts
git commit -m "test: lock final user dashboard navigation"
```

---

## Task 2 — Add the pure operational/safety presentation model

**Files:**
- Create: `dashboard/user-dashboard/shellState.ts`
- Create: `dashboard/user-dashboard/shellState.test.ts`

**Interfaces**
- Consumes: read-only strings/states from backend projections; no mutation APIs.
- Produces: normalized presentation state for mode, automation, broker, engine, data freshness, Live lock, notifications, and manual-resume requirement.

Suggested core types:

```ts
export type TradingMode = "BACKTEST" | "PAPER" | "LIVE";
export type AutomationState =
  | "RUNNING" | "PAUSED" | "STOPPED"
  | "HALT_ENTRIES" | "RECOVERY" | "READY_FOR_RESUME";
export type AuthorityState = "AVAILABLE" | "STALE" | "UNAVAILABLE" | "UNKNOWN";
```

- [ ] **Step 1: Write failing tests for the frozen safety rules.**

Minimum cases:
- `LIVE` always produces the exact label `READ_ONLY / DISARMED`.
- Broker state `CONNECTED` cannot change that Live label.
- `RECOVERY` => `manualResumeRequired === true` and never presents running automation.
- `READY_FOR_RESUME` => `manualResumeRequired === true`.
- unavailable broker/engine/data remains unavailable/unknown rather than healthy.
- critical notification count remains visible and is not downgraded.

- [ ] **Step 2: Run RED.**

```powershell
cd dashboard/web
npm run test:user-dashboard -- ../user-dashboard/shellState.test.ts
```

- [ ] **Step 3: Implement the smallest pure derivation model.**

Do not put network calls, React state, timers, or trading mutations in this module.

- [ ] **Step 4: Run GREEN.**

```powershell
npm run test:user-dashboard -- ../user-dashboard/shellState.test.ts
```

- [ ] **Step 5: Commit.**

```powershell
git add dashboard/user-dashboard/shellState.ts dashboard/user-dashboard/shellState.test.ts
git commit -m "feat: add user shell safety state model"
```

---

## Task 3 — Build the reusable user shell, top bar, navigation rail, and notification center

**Files:**
- Create: `dashboard/user-dashboard/components/UserDashboardShell.tsx`
- Create: `dashboard/user-dashboard/components/UserTopBar.tsx`
- Create: `dashboard/user-dashboard/components/UserNavRail.tsx`
- Create: `dashboard/user-dashboard/components/NotificationCenter.tsx`
- Create: `dashboard/user-dashboard/components/PendingUserSurface.tsx`
- Create: `dashboard/user-dashboard/components/UserDashboardShell.test.tsx`
- Modify: `dashboard/user-dashboard/UserDashboardApp.tsx`
- Modify: `dashboard/user-dashboard/user-dashboard.css`

**Interfaces**
- Consumes: `USER_NAV_ITEMS`, normalized `UserShellStatus`, theme toggle, navigation callback, notification summary, existing `GlobalRealTimeClock` and `CommandPalette`.
- Produces: one reusable desktop/mobile-ready normal-user shell around the current selected screen.

- [ ] **Step 1: Write the failing shell DOM tests.**

Use React `createRoot` + jsdom; do not add a new testing library.

Test that:
- all seven final nav items render in order;
- old normal-user nav labels are absent;
- top bar shows AlgoFortis branding, mode, broker state, engine/host state, notifications, theme/profile affordances, and clock;
- `LIVE` visibly includes `READ_ONLY / DISARMED` even if broker is connected;
- bell opens a notification layer;
- no Owner/Admin/Agents controls appear;
- root carries deterministic `data-mode` and `data-operational-state` attributes for CSS/safety styling.

- [ ] **Step 2: Run RED.**

```powershell
cd dashboard/web
npm run test:user-dashboard -- ../user-dashboard/components/UserDashboardShell.test.tsx
```

- [ ] **Step 3: Implement the shell components and refactor `UserDashboardApp`.**

Rules:
- keep `DashboardV3App` untouched;
- root user class becomes e.g. `v3-root af-user-workspace` so styling can be scoped;
- use `/algofortis_logo.png` from existing public assets;
- `Ctrl+K` remains, but the command palette contains the final seven pages + appearance only; remove global option-strike-policy commands from this shell;
- notification layer uses authoritative entries when present; otherwise explicit empty/unavailable copy, never sample alerts;
- final-page routes that are not redesigned yet render `PendingUserSurface` rather than silently exposing the old mismatched page as “finished”;
- preserve old screen modules in the repository for later page-specific migration.

- [ ] **Step 4: Run GREEN plus typecheck.**

```powershell
npm run test:user-dashboard -- ../user-dashboard/components/UserDashboardShell.test.tsx
npm run typecheck
```

- [ ] **Step 5: Commit.**

```powershell
git add dashboard/user-dashboard/components dashboard/user-dashboard/UserDashboardApp.tsx dashboard/user-dashboard/user-dashboard.css
git commit -m "feat: build final user dashboard shell"
```

---

## Task 4 — Build a truthful read-only Home data loader and view model

**Files:**
- Create: `dashboard/user-dashboard/home/homeModel.ts`
- Create: `dashboard/user-dashboard/home/homeData.ts`
- Create: `dashboard/user-dashboard/home/homeModel.test.ts`
- Create: `dashboard/user-dashboard/home/homeData.test.ts`

**Interfaces**
- Consumes existing read-only authorities:
  - `queryCurrentUserProfile()`
  - `queryPersistenceHealth()`
  - `queryOrdersPortfolio(false, "PAPER")`
  - `queryMarketChart(...)` for NIFTY/BANKNIFTY only when canonical market data is available
- Produces a `HomeCommandCenterModel` containing truth state plus nullable values; UI does not read `sampleData` directly.

- [ ] **Step 1: Write failing model tests.**

Cases:
- unavailable portfolio authority yields `null` values and `UNAVAILABLE`, not numeric zero;
- missing market data yields no hard-coded NIFTY/BANKNIFTY price;
- broker/connection state cannot change the Live lock;
- multiple account rows remain separate;
- unknown risk/testing state is not rendered as SAFE/PASS;
- empty positions is distinct from unavailable positions.

- [ ] **Step 2: Run RED.**

```powershell
cd dashboard/web
npm run test:user-dashboard -- ../user-dashboard/home/homeModel.test.ts ../user-dashboard/home/homeData.test.ts
```

- [ ] **Step 3: Implement the view model and read-only loader.**

Important data rules:
- do **not** use `PORTFOLIO`, `UNDERLYINGS`, `ACTIVITY`, `generateCandles`, sample strategy templates, sample security sessions, or force-demo fixtures for an authoritative Home;
- market snapshots call `queryMarketChart` and preserve its fail-closed states;
- `queryOrdersPortfolio` currently exposes persisted paper/session account evidence. Label it as paper/session evidence unless the backend explicitly identifies a broker account; do not relabel it as broker capital;
- only show an aggregate value when a canonical aggregate is actually supplied/derivable without implying cross-broker routability;
- keep source/trust/as-of fields in the model so UI can display stale/unavailable truthfully.

- [ ] **Step 4: Run GREEN.**

```powershell
npm run test:user-dashboard -- ../user-dashboard/home/homeModel.test.ts ../user-dashboard/home/homeData.test.ts
```

- [ ] **Step 5: Commit.**

```powershell
git add dashboard/user-dashboard/home/homeModel.ts dashboard/user-dashboard/home/homeData.ts dashboard/user-dashboard/home/*.test.ts
git commit -m "feat: add truthful home command center model"
```

---

## Task 5 — Build the Home / Command Center from small read-only components

**Files:**
- Create: `dashboard/user-dashboard/home/HomeCommandCenter.tsx`
- Create: `dashboard/user-dashboard/home/HomeCommandCenter.test.tsx`
- Create: `dashboard/user-dashboard/home/components/OperationalStateStrip.tsx`
- Create: `dashboard/user-dashboard/home/components/MarketSnapshotCard.tsx`
- Create: `dashboard/user-dashboard/home/components/CapitalSummary.tsx`
- Create: `dashboard/user-dashboard/home/components/PositionsSummary.tsx`
- Create: `dashboard/user-dashboard/home/components/StrategyStatusSummary.tsx`
- Create: `dashboard/user-dashboard/home/components/RiskSummary.tsx`
- Create: `dashboard/user-dashboard/home/components/TestingProgressSummary.tsx`
- Create: `dashboard/user-dashboard/home/components/RecentActivitySummary.tsx`
- Modify: `dashboard/user-dashboard/screens/UserHome.tsx`

**Interfaces**
- Consumes only `HomeCommandCenterModel` + navigation callbacks.
- Produces the approved Home layout; no broker/order mutation interface.

- [ ] **Step 1: Write failing render tests.**

Required assertions:
- unavailable capital renders `UNAVAILABLE`, not `₹0`;
- no PASS text appears unless a real model field says a test passed;
- no `Confirm`, `Auto`, order-submit, or direct broker-execution control is present;
- Live mode renders `READ_ONLY / DISARMED` prominently;
- no positions/strategies are presented as empty only when authority confirms an empty collection; otherwise unavailable is explicit;
- `RECOVERY`, `READY_FOR_RESUME`, and `HALT_ENTRIES` are visually represented directly;
- Laya execution actions are absent.

- [ ] **Step 2: Run RED.**

```powershell
cd dashboard/web
npm run test:user-dashboard -- ../user-dashboard/home/HomeCommandCenter.test.tsx
```

- [ ] **Step 3: Implement the approved Home composition.**

Order:
1. Operational command strip.
2. Compact NIFTY/BANKNIFTY snapshot only; no full chart/options ladder on Home.
3. Capital/P&L summary with separate account/pool rows.
4. Compact positions summary.
5. Strategy lifecycle/status summary.
6. Risk state summary.
7. Testing progress summary: Backtest / WFO / OOS / Robustness / Validation.
8. Notifications/recent activity summary.

`UserHome.tsx` becomes a thin loader/wrapper around `HomeCommandCenter` and removes direct sample-data, `ProfessionalChart`, and `OptionsWorkspace` use. Full chart and option-chain experiences stay for the later Markets slice.

- [ ] **Step 4: Run GREEN plus typecheck.**

```powershell
npm run test:user-dashboard -- ../user-dashboard/home/HomeCommandCenter.test.tsx
npm run typecheck
```

- [ ] **Step 5: Commit.**

```powershell
git add dashboard/user-dashboard/home dashboard/user-dashboard/screens/UserHome.tsx
git commit -m "feat: build home command center"
```

---

## Task 6 — Apply premium AlgoFortis styling, responsive behavior, and motion safety

**Files:**
- Modify: `dashboard/user-dashboard/user-dashboard.css`
- Modify tests only if needed to expose deterministic class/data hooks.

**Interfaces**
- Consumes the shell/Home class names and data attributes.
- Produces user-scoped styling only; no domain behavior.

- [ ] **Step 1: Add/extend tests for deterministic safety hooks before CSS work.**

Ensure DOM exposes:
- `data-mode="paper|live|backtest"`
- `data-operational-state="recovery|ready-for-resume|halt-entries|..."`
- stable notification/risk region labels.

- [ ] **Step 2: Run tests before styling and confirm any new hook test is RED.**

```powershell
cd dashboard/web
npm run test:user-dashboard
```

- [ ] **Step 3: Implement scoped premium styling under `.af-user-workspace`.**

Visual rules:
- deep near-black / graphite surfaces;
- restrained gold primary brand accent and platinum secondary accent;
- green/red only for semantic trading state;
- UI stack begins with `Manrope`; numeric stack begins with `IBM Plex Mono`, with safe system fallbacks and no bundled font files;
- thin borders, controlled shadows, no neon/glass overload;
- Paper and Live must be unmistakable;
- `RECOVERY`, `READY_FOR_RESUME`, `HALT_ENTRIES`, critical notifications render immediately; do not wait for decorative animation;
- use short transform/opacity transitions only where they clarify state;
- add `@media (prefers-reduced-motion: reduce)` to disable nonessential motion;
- preserve usable desktop rail and a compact mobile-ready navigation structure.

Do not make broad shared `shared.css` changes unless a missing primitive cannot be safely scoped to user-only CSS.

- [ ] **Step 4: Run complete user-dashboard tests, typecheck, and build.**

```powershell
npm run test:user-dashboard
npm run typecheck
npm run build
```

- [ ] **Step 5: Commit.**

```powershell
git add dashboard/user-dashboard/user-dashboard.css dashboard/user-dashboard/**/*.test.ts dashboard/user-dashboard/**/*.test.tsx
git commit -m "style: apply premium algofortis user dashboard system"
```

---

## Task 7 — Full verification and anti-regression review

**Files:**
- Modify only files required to fix verification failures.

- [ ] **Step 1: Run the complete focused frontend qualification.**

```powershell
cd dashboard/web
npm run test:user-dashboard
npm run typecheck
npm run build
```

Expected: all green.

- [ ] **Step 2: Run repository whitespace/diff checks.**

```powershell
git diff --check
git status --short
```

- [ ] **Step 3: Static anti-regression checks.**

From repository root:

```powershell
rg 'sampleData|UNDERLYINGS|ACTIVITY|generateCandles|ProfessionalChart|OptionsWorkspace' dashboard/user-dashboard/screens/UserHome.tsx dashboard/user-dashboard/home
rg 'READ_ONLY / DISARMED' dashboard/user-dashboard dashboard/shared
rg 'connections|Strategy Execution|Backtesting|Paper Trading|Orders|Reports|Help & Docs|Agents' dashboard/user-dashboard/navigation.ts
```

Interpretation:
- first command should find no production Home dependence on sample/full-market fixtures;
- second must prove the Live-lock wording remains present;
- third must not find old navigation entries in the canonical final nav.

- [ ] **Step 4: Review untouched boundaries.**

Verify the slice did not redesign/enable:
- Entry Gate,
- Owner/Admin workspace,
- Live execution,
- Laya execution,
- arbitrary strategy-code import,
- cloud/remote-host go-live.

- [ ] **Step 5: Review the five Review Focus scenarios manually against tests/diff.**

Any ambiguity is a blocker; do not call the slice complete until resolved.

- [ ] **Step 6: Commit only verification fixes if any.**

```powershell
git add <only-fixed-files>
git commit -m "fix: close user dashboard qualification gaps"
```

---

## Slice Definition of Done

This first dashboard slice is done only when:

- the normal-user shell shows exactly the approved seven-page navigation;
- Owner/Admin/Agents/research internals are absent from normal-user navigation;
- Home is a premium Command Center rather than a full Markets screen;
- no production Home value is fabricated from sample fixtures;
- unavailable/stale/empty states are truthfully differentiated;
- Live is visibly `READ_ONLY / DISARMED` regardless of broker connectivity;
- recovery/manual-resume semantics are visible and never auto-promoted to running;
- separate account/capital pools are not presented as one freely routable pool;
- critical state remains immediate under normal and reduced-motion settings;
- `npm run test:user-dashboard`, `npm run typecheck`, and `npm run build` all pass;
- Entry Gate and Owner/Admin remain untouched.

## Follow-up Work — Separate Plans After This Slice Is Approved Visually

Do **not** expand this implementation plan into the entire product. After Shell + Home is implemented and visually approved, create separate design/implementation cycles for:

1. Markets
2. Strategies
3. Testing & Validation
4. Trades
5. Portfolio
6. Account
7. Owner/Admin workspace
8. Entry Gate final V1 reuse/merge
