# AlgoFortis V2 Phase 7 — Portfolio & Risk V2 Design

**Date:** 2026-09-27  
**Status:** IMPLEMENTATION-READY  
**Scope:** AF2-RSK-004, AF2-RSK-006; G7  
**Base:** merged Phase-4 `main`  

## Goal

Add deterministic multi-strategy portfolio budgets, capital reservation/release, exposure/concentration controls, sticky portfolio circuit breaking, event/expiry risk windows, and P&L/exposure attribution without creating a second execution authority.

## Standing safety invariants

1. `RiskGateV2` remains the only authority allowed to mint `ApprovedOrder`.
2. Phase-7 code MUST NOT import broker adapters, Live execution code, AI/agent code, or vendor APIs.
3. Phase-7 code MUST NOT import or call `_mint_approved_order` and MUST NOT construct `ApprovedOrder` directly.
4. Portfolio/circuit/event policy may reject entry or constrain an explicit entry quantity, but may not silently rewrite a submitted intent.
5. Exit/protective actions are never blocked by an entry-only portfolio policy.
6. All money, quantity, exposure, P&L and risk thresholds use `Decimal`/fixed-point semantics.
7. Production thresholds are injected immutable/versioned policy. No guessed production defaults are embedded in source.
8. Missing/corrupt/unavailable portfolio-risk evidence fails closed for new entries.
9. Live remains `READ_ONLY / DISARMED`; Phase 7 does not change broker mutation authority.
10. RSK-005 correlated exposure, dynamic drawdown scaling and rebalancing remain T2 seams and are not implemented in V2.0 Phase 7.

## Architecture

### 1. Pure portfolio domain

New focused package: `engine/portfolio/v2/`.

It owns:
- immutable budget/reservation contracts;
- capital reservation/release book;
- current/projected exposure calculations;
- portfolio circuit-breaker state/evidence;
- strategy-level P&L and exposure attribution;
- deterministic G7 evidence.

It does not own:
- broker state;
- live arming;
- order submission;
- strategy signal generation;
- `ApprovedOrder` construction.

Existing `engine/portfolio/model.py` remains the authoritative concrete account/position snapshot model. Phase 7 consumes `AccountSnapshot`, `PositionSnapshot`, `PositionKey`, and `InstrumentIdentity`; it does not rewrite V1/V2 accounting.

### 2. Budget hierarchy and reservations

`PortfolioBudgetPolicy` is immutable and versioned:
- `owner_capital_limit`
- `user_id`
- `user_budget`
- per-strategy budget map

Validation locks the hard hierarchy:

`strategy_budget <= user_budget <= owner_capital_limit`

No strategy missing from the profile receives an implicit budget.

`CapitalReservationBook` provides atomic in-process reserve/release semantics for concurrent strategies. Reservation IDs are caller-supplied deterministic identities; the book does not invent IDs or time.

Reservation rules:
- amount must be positive `Decimal`;
- duplicate active reservation ID fails closed;
- unknown strategy fails closed;
- strategy reservation total may not exceed strategy budget;
- aggregate active reservations may not exceed user budget;
- release of an unknown/already released reservation does not create capital;
- snapshots are immutable evidence.

Durable persistence is outside this domain object; orchestration/persistence adapters may store its evidence through existing versioned persistence boundaries. Phase 7 does not add a second database authority.

### 3. Exposure and concentration

`PortfolioExposureSnapshot` is derived from authoritative `AccountSnapshot` and groups marked exposure by:
- total account;
- strategy;
- concrete instrument identity.

`PortfolioExposurePolicy` is immutable/versioned and supplies explicit caps:
- total marked/projected exposure cap;
- per-strategy cap map;
- per-instrument cap.

`PortfolioRiskContext` supplies authoritative pre-trade evidence not present in `OrderIntent`:
- account snapshot;
- reference price;
- contract multiplier;
- normal/baseline strategy quantity;
- required capital;
- active reservation reference;
- evaluation timestamp.

A `PortfolioContextProvider` port resolves this context for an intent. It must sit behind a port; portfolio/risk domain code does not query brokers or databases directly.

Projected entry exposure is calculated as:

`reference_price * requested_qty * contract_multiplier`

using Decimal arithmetic.

Missing context, invalid price/multiplier, missing strategy cap, or any cap breach rejects new entry.

### 4. Circuit breaker

`PortfolioCircuitBreakerPolicy` is immutable/versioned; numeric limits are required inputs, not source defaults. Initial V2 scope covers:
- maximum daily loss;
- maximum drawdown.

`PortfolioCircuitBreaker` is a sticky local entry policy compatible with `RiskGateV2.EntryPolicy` via the `entries_allowed` boolean property.

Rules:
- threshold breach audits before latching;
- audit failure blocks state mutation and fails closed;
- once latched, entries remain blocked across subsequent healthy observations;
- no automatic reset on time, reconnect, restart, or improving metrics;
- manual reset requires explicit reset authority, clean current metrics, and successful audit-before-state-change;
- circuit breaker never submits/cancels/modifies orders.

### 5. Event-day / expiry policy

New module: `engine/risk/event_day_policy_v2.py`.

`EventRiskPolicy` is immutable/versioned and contains explicit timezone-aware windows. Each window has:
- stable window ID;
- category/label (for example policy announcement, budget, election, result, expiry; the engine treats labels as opaque policy metadata);
- start/end timestamps;
- action `NO_TRADE` or `SIZE_CAP`;
- for `SIZE_CAP`, an explicit Decimal fraction `(0, 1]`.

No event dates or production fractions are built into source.

For `SIZE_CAP`, Phase 7 never silently changes `OrderIntent.qty`. The policy calculates the maximum explicit quantity as:

`baseline_qty * size_fraction`

If submitted quantity exceeds that cap, RiskGate evaluation rejects the intent. The caller must create a new explicit smaller intent if desired. This preserves immutable intent/audit semantics.

Overlapping windows use the most restrictive deterministic outcome:
- any `NO_TRADE` window blocks;
- otherwise the lowest size fraction wins.

An explicitly versioned policy with zero active windows is valid. Missing policy/evaluation context fails closed for entry.

### 6. Portfolio-aware evaluator through the existing RiskGate

New module: `engine/risk/portfolio_v2.py`.

`PortfolioAwareRiskEvaluator` wraps an existing `RiskEvaluator` and returns the existing `RiskEvaluation` contract.

Evaluation order:
1. evaluate base risk rules;
2. if base result is rejected/reduced, preserve that result;
3. fetch authoritative `PortfolioRiskContext`;
4. prove an active capital reservation exists and matches the strategy/required-capital evidence;
5. evaluate projected exposure/concentration;
6. evaluate event/expiry policy;
7. if all portfolio checks pass, preserve base approval quantity; otherwise return a normal `RiskEvaluation.rejected(...)` with a versioned portfolio reason.

The wrapper cannot mint orders. `RiskGateV2.evaluate_entry()` remains the only code that may mint `ApprovedOrder` after all evidence and audit checks.

### 7. Admission coordinator and reservation lifecycle

`PortfolioAdmissionCoordinator` is an orchestration helper around an existing `RiskGateV2` plus `CapitalReservationBook` and `PortfolioContextProvider`.

It may:
- reserve required capital before calling the central gate;
- delegate the immutable intent to `RiskGateV2`;
- release the reservation immediately if the gate rejects or throws;
- retain the reservation if the central gate returns an `ApprovedOrder` minted by RiskGate;
- release the retained reservation when the caller reports the intent/order lifecycle terminal.

It may not:
- construct or clone `ApprovedOrder`;
- change intent quantity;
- call a broker;
- arm Live.

A duplicate active reservation/intent is rejected rather than admitted twice.

### 8. Attribution

`PortfolioAttributionReport` groups by strategy:
- marked exposure;
- unrealized P&L;
- realized P&L supplied by explicit realized-attribution records;
- open position count.

The report must reconcile supplied realized attribution records to `AccountSnapshot.realized_pnl`. Mismatch fails closed as incomplete attribution rather than silently assigning residual P&L.

No cross-strategy netting is used to hide gross concentration.

### 9. Static architecture firewall

Create `build/tools/check_phase7_portfolio_risk.py`.

It must statically reject Phase-7 code that:
- imports `engine.broker_adapters`, `engine.live`, or `engine.ai`;
- imports `_mint_approved_order`;
- calls `ApprovedOrder(...)` or `_mint_approved_order(...)`;
- embeds guessed production budget/exposure/circuit/event threshold constants;
- directly calls network/database/vendor APIs from the new pure domain modules.

It must require the Phase-7 authorities, focused tests, probe, evidence docs and qualification workflow.

### 10. G7 evidence

Create deterministic `phase7_probe.py` evidence with markers including:
- `APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY`
- `PORTFOLIO_BUDGETS=VERSIONED_EXPLICIT`
- `CAPITAL_RESERVATION=ATOMIC_FAIL_CLOSED`
- `PORTFOLIO_EXPOSURE=THROUGH_RISK_GATE`
- `CIRCUIT_BREAKER=STICKY_ENTRY_POLICY`
- `EVENT_RISK=SCHEDULED_VERSIONED_NO_SILENT_RESIZE`
- `LIVE_STATE=READ_ONLY/DISARMED`

Dedicated dual-Windows G7 workflow runs:
- Phase-7 static guard;
- Phase-7 focused tests;
- RiskGate integration test proving portfolio/circuit rejection occurs through the existing gate;
- deterministic fingerprint comparison.

G7 is not claimed GREEN unless actual jobs execute and evidence passes. Hosted runner provisioning failure is recorded as an external blocker, not treated as a test failure or success.

## G7 exit interpretation

G7 requires evidence that:
- multi-strategy budgets/reservations cannot oversubscribe configured capital;
- projected portfolio/strategy/instrument exposure rejects through the existing RiskGate;
- circuit-breaker latch blocks entry through the existing RiskGate;
- event/expiry windows deterministically block/limit explicit quantities;
- attribution reconciles exactly;
- static guard proves Phase-7 code cannot mint an executable order or reach broker/Live mutation;
- deterministic dual-Windows G7 evidence matches.

**G7 does not authorize real-money trading and does not change Live from `READ_ONLY / DISARMED`.**
