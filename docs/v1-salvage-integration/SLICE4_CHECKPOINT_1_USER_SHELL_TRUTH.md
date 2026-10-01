# Slice 4 — Checkpoint 1: User Shell Truth

Date: 2026-09-29

This checkpoint freezes the first bounded Normal User Dashboard reunion step. It does **not** claim Slice 4 is complete.

## Goal

Preserve the existing V1-quality User Dashboard surfaces while ensuring the shared shell does not depend on visiting Home first to obtain backend-derived truth.

## Implemented

### Direct-route shell hydration

`dashboard/user-dashboard/UserDashboardApp.tsx`

- Direct routes such as `#markets`, `#strategies`, `#testing`, `#trades`, `#portfolio`, and `#account` now request the same command-center authority model used by Home.
- Home retains its existing authority load and reports shell status through `onShellStatus`.
- Non-Home routes no longer remain permanently stuck on the bootstrap `UNKNOWN` shell merely because Home was never opened.
- Failure remains fail-closed: the shell falls back to the explicit UNKNOWN bootstrap state rather than inventing healthy, connected, running, or Paper/Live state.

### Stale market truth mapping

`dashboard/user-dashboard/home/homeData.ts`

- The market-to-Home mapper now preserves an input `STALE` authority state when canonical candles are present.
- Overall market freshness returns `STALE` when any tracked market is stale.
- Invalid or missing values remain fail-closed and are not promoted to available data.

### Regression coverage added

- `dashboard/user-dashboard/UserDashboardApp.test.tsx`
  - direct `#markets` entry hydrates supplied authoritative shell status without requiring a Home visit.
- `dashboard/user-dashboard/home/homeData.test.ts`
  - stale canonical market input remains stale at the Home mapper boundary.

## Safety invariants preserved

This checkpoint does not add or modify broker order placement, cancellation, modification, RiskGate authority, Live arming, or broker mutation behavior.

Permanent invariants remain:

- Live is READ_ONLY / DISARMED.
- UI is a read/client surface, never execution authority.
- Missing authority is UNKNOWN / UNAVAILABLE rather than fabricated healthy state.
- Manual-resume states remain explicit.
- RiskGateV2 remains the executable-order authority.

## Verification status

### Repository evidence

- Integration branch remains a linear descendant of frozen convergence base `7a51807b4dd5a0788ec3bf32a228f771867ddb2f`.
- GitHub compare at the code checkpoint reported the branch ahead with no divergence from that base.

### Automated execution

**NOT EXECUTED in this checkpoint environment.**

Reason:

- the repository is private and the local container has no network route to GitHub;
- the branch currently has no GitHub Actions run and no combined commit statuses;
- existing workflows are configured for PRs targeting `main` or manual workflow dispatch, not ordinary pushes to this integration branch.

Therefore this checkpoint does **not** claim that frontend tests, TypeScript typecheck, build, or the full Python regression suite are green.

## Explicit remaining work after this checkpoint

1. Run focused User Dashboard Vitest/typecheck/build in an authorized runner or local repo checkout.
2. Decide whether the shared market client contract should expose `STALE` end-to-end; the current checkpoint pins stale behavior at the Home mapper boundary only.
3. Continue Slice 4 screen-by-screen truth wiring: Strategies, Testing, Trades, Portfolio, Account, notifications, broker/mode authority, and remaining placeholders.
4. Keep Owner/Admin reunion deferred until the Normal User surface reaches its own clean completion gate.

## Checkpoint meaning

Safe continuation point: yes.

Slice 4 complete: no.

Merge-ready: not claimed until fresh automated verification exists.
