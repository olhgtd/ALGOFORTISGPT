# Slice 4 — Normal User Dashboard Completion Qualification

**Date:** 2026-09-29  
**Working branch:** `v1-salvage-integration-20260929`  
**Frozen comparison base:** `checkpoint-v1-salvage-slice4-shell-20260929` (`0bd7d924595ac99c93f0956cfe2c75ae9f44ed63`)  
**Implementation head before this qualification record:** `b6c238039737279a029aae366f71281f75e4592f`

## Scope

This qualification covers only the canonical Normal User workspace:

1. Home
2. Markets
3. Strategies
4. Testing & Validation
5. Trades
6. Portfolio
7. Account

Owner/Admin, Laya, broker execution authority, RiskGate authority, and architecture rewrites are outside this slice.

## Preserved invariants

- Live presentation remains `READ_ONLY / DISARMED`.
- A connected broker does not arm Live execution.
- `RECOVERY`, `HALTED`, `HALT_ENTRIES`, and `READY_FOR_RESUME` require manual resume/clearance semantics.
- Missing authority remains `UNKNOWN`, `UNAVAILABLE`, or `STALE`; it is never converted to healthy/ready/PASS.
- Canonical user routes do not import legacy sample user-data modules.
- Canonical user routes do not own direct broker mutation or executable-order APIs.
- Paper and Live portfolio/trade projections remain separate.
- Option-chain data remains explicitly unavailable when no authoritative option-chain authority is attached; generated/sample strikes and prices are not shown.

## Wiring completed

### Shared shell and Attention Center

`dashboard/user-dashboard/data/userShellData.ts` is the shared read-only shell authority adapter. It derives display-only shell truth from existing backend authorities:

- persistence/runtime health
- NIFTY/BANKNIFTY canonical market reads
- per-user broker connections
- per-user deployments
- user live-readiness/risk projection

`UserDashboardApp` owns this shared shell state for every route and passes the same shell/risk authority into Home. Home no longer performs a competing shell/risk read.

Derived Attention Center notices are evidence-based only: manual-resume states, broker-health attention, engine unavailable/stale, market stale/unavailable, suspended connection evidence, risk state, and Live read-only state.

Historical stopped/completed/cancelled/archived deployments are not used to infer the current trading mode.

### Market truth

A user-specific thin read-only adapter, `dashboard/user-dashboard/data/userMarketAuthority.ts`, reads the existing canonical `/api/v1/market/chart` endpoint and preserves `STALE` without introducing a second market engine or sample fallback.

Home, shared shell status, Markets overview, and the Markets chart use the same canonical market authority family. Canonical stale candles may remain visible for context only with an explicit `STALE` label; they are not promoted to fresh truth.

The shared professional chart quote helper accepts stale canonical candles without changing their authority state.

### Home command center

Home now consumes existing authoritative Strategies and Testing loaders rather than fixed placeholders. It reports counts/states only and does not invent promotion/success conclusions.

The same shared shell/risk authority used by the global chrome is injected into Home, so Home does not own a parallel operational truth.

### Strategies / Testing / Account authority trust

`dashboard/user-dashboard/data/userSurfaceData.ts` preserves all four user authority states:

- `AVAILABLE`
- `STALE`
- `UNKNOWN`
- `UNAVAILABLE`

Only `BACKEND + FRESH` evidence is exposed as current strategy/testing/account row data. Stale or unknown strategy rows, test/report rows, account identity, entitlement values, and broker connection records are withheld rather than rendered as fresh.

The UI forwards the actual state into shared authority badges/messages. `STALE` and `UNKNOWN` receive distinct presentation states.

### Static safety boundary

`tests_v1/test_v1_salvage_user_dashboard_boundaries.py` locks:

- exact seven-route Normal User navigation
- no imports from legacy sample-data modules in canonical user files
- no direct broker/order mutation references in canonical user files
- Live `READ_ONLY / DISARMED` wording
- fail-closed option-chain wording
- shared shell authority usage across routes
- no duplicate Home shell authority
- STALE/UNKNOWN propagation through user surfaces and Home summaries

## Test coverage added or expanded

Focused TypeScript/Vitest regression coverage now includes:

- conflicting active deployment modes -> `UNKNOWN`
- halted/recovery/manual-resume precedence
- stopped historical deployments do not define current mode
- broker connection/health mapping
- evidence-derived notifications
- direct-route shell hydration
- Home receives the same shared shell and risk authority
- STALE canonical market data survives market adapter/model/chart quote
- no fabricated market quote on unavailable authority
- Home strategy/testing summaries use authoritative loaders
- stale/unknown strategy/testing/account evidence is not exposed as fresh row data
- stale account identity and stale broker account references are withheld
- option-chain sample generation remains absent from the finished Markets surface

`dashboard/web/vitest.config.ts` also includes the shared `professionalChartTruth.test.ts` file so the market-truth helper is no longer excluded from the user-dashboard Vitest gate.

## Diff-scope audit

Comparison from `checkpoint-v1-salvage-slice4-shell-20260929` to implementation head `b6c238039737279a029aae366f71281f75e4592f` showed changes limited to:

- `dashboard/user-dashboard/**`
- `dashboard/shared/components/professionalChartTruth.ts` and its test
- `dashboard/web/vitest.config.ts`
- Normal User completion plan/qualification docs
- Normal User static boundary test

No Owner/Admin, Laya, backend API, engine execution, broker adapter, or RiskGate implementation file was changed by this completion pass.

## Executed verification evidence

A temporary draft verification PR (`#21`, `Verify normal-user dashboard wiring`) was opened only to trigger repository CI. It was not intended for merge.

At implementation head `b6c238039737279a029aae366f71281f75e4592f`, both repository qualification workflows were triggered:

- `V2 Phase 5 Paper Recovery Qualification` — run `36542112274`
- `V2 Phase 6 Multi-Broker Read-Only Qualification` — run `36542112303`

Both workflows reported `failure`, but their Windows jobs failed before any step started:

- regression/G6 job `steps` were empty/null
- downstream deterministic comparison jobs were skipped
- no test, typecheck, build, or Python verification command produced execution output

This is recorded as **runner/infrastructure execution unavailable**, not as a code-test failure and not as a GREEN result.

## Qualification status

### Source / architecture review

**IMPLEMENTED / REVIEWED** for the Normal User wiring scope described above.

### Executable verification

**PENDING — CI RUNNER INFRASTRUCTURE BLOCKED.**

The following commands still require a functioning authorized runner before this checkpoint can be called execution-GREEN:

```text
npm --prefix dashboard/web run test:user-dashboard
npm --prefix dashboard/web run typecheck
npm --prefix dashboard/web run build
python -m pytest tests_v1/test_v1_salvage_user_dashboard_boundaries.py -q
```

A broader repository regression should then be executed according to the existing Windows qualification workflow.

## Merge / promotion status

This qualification record does **not** authorize merge, Live arming, broker mutation, strategy promotion, or executable-order authority. Until executable verification produces fresh GREEN evidence, treat the checkpoint as source-complete but execution-verification-pending.
