# Phase 7 Portfolio & Risk V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement AF2-RSK-004 and AF2-RSK-006 with deterministic portfolio budgets/reservations, exposure controls, sticky circuit breaking, event/expiry risk policy, and exact attribution while preserving RiskGateV2 as the only ApprovedOrder authority.

**Architecture:** Add pure focused modules under `engine/portfolio/v2/` and risk composition under `engine/risk/`. Existing `engine/portfolio/model.py` remains the account/position truth model and `engine/risk/gate_v2.py` remains the executable-order mint authority. All production limits are versioned injected policy; missing evidence fails closed.

**Tech Stack:** Python 3.13.14, stdlib dataclasses/Decimal/threading, pytest, existing AlgoFortis V2 contracts and RiskGateV2.

**Spec:** `docs/superpowers/specs/2026-09-27-phase7-portfolio-risk-design.md`

## Global Constraints

- `RiskGateV2` remains the only authority that can mint `ApprovedOrder`.
- No Phase-7 broker/Live/AI/vendor/network/database dependency.
- No `_mint_approved_order` import/call and no direct `ApprovedOrder(...)` construction.
- Decimal/fixed-point only for money, quantity, exposure, P&L and thresholds.
- No guessed production numeric defaults; production policy is explicit/versioned.
- Missing/corrupt portfolio-risk evidence fails closed for new entries.
- Event `SIZE_CAP` never silently rewrites an immutable intent quantity.
- RSK-005 correlated exposure/dynamic scaling/rebalancing remains deferred T2.
- Live remains `READ_ONLY / DISARMED`.

## Review Focus

1. Concurrent/duplicate capital reservations must never oversubscribe user/strategy budgets.
2. Missing context or missing strategy/exposure policy must reject, not fall back permissively.
3. Circuit breaker must remain latched until explicit audited manual reset; restart/reconnect/time cannot auto-clear it.
4. Overlapping event windows must choose the most restrictive deterministic rule; exits are not turned into blocked entries.
5. Attribution must reject incomplete realized-P&L evidence instead of silently assigning residual P&L.

---

### Task 0 — Baseline and design lock

**Files:**
- Read: `ALGOFORTIS_V2_REQUIREMENTS.md`
- Read: `ALGOFORTIS_V2_TEST_AND_RELEASE_PLAN.md`
- Read: `engine/risk/gate_v2.py`
- Read: `engine/portfolio/model.py`
- Spec: `docs/superpowers/specs/2026-09-27-phase7-portfolio-risk-design.md`

- [ ] Confirm scope is AF2-RSK-004 + AF2-RSK-006 only; RSK-005 stays deferred.
- [ ] Confirm G7 requires portfolio exposure and circuit-breaker proof through the same RiskGate.
- [ ] Confirm no new Owner Decision blocks Phase 7 when production numeric values remain explicit policy rather than guessed defaults.
- [ ] Confirm Phase 7 can branch from merged Phase-4 `main` and does not depend on G6 qualification.

### Task 1 — Pure contracts and Phase-7 static firewall

**Files:**
- Create: `engine/portfolio/v2/__init__.py`
- Create: `engine/portfolio/v2/contracts.py`
- Create: `build/tools/check_phase7_portfolio_risk.py`
- Test: `tests_v1/test_phase7_contracts.py`
- Test: `tests_v1/test_phase7_architecture_guard.py`

**Interfaces:**
- Produces immutable `PortfolioBudgetPolicy`, `CapitalReservation`, `ReservationSnapshot`, `PortfolioRiskContext`, `PortfolioExposurePolicy`, `PortfolioExposureSnapshot`, `RealizedPnlRecord`, and attribution value types.

- [ ] RED: invalid hierarchy `strategy > user` or `user > owner` is rejected.
- [ ] RED: money/quantity fields reject float/non-finite/non-positive values where applicable.
- [ ] RED: static negative fixtures importing broker/Live/AI, `_mint_approved_order`, or directly constructing `ApprovedOrder` fail.
- [ ] Implement minimal immutable Decimal contracts.
- [ ] Implement AST static firewall and required-file presence gate.
- [ ] Run focused tests and firewall.
- [ ] Commit: `feat: add Phase 7 portfolio risk contracts and firewall`.

### Task 2 — Atomic capital reservation/release

**Files:**
- Create: `engine/portfolio/v2/reservations.py`
- Test: `tests_v1/test_phase7_reservations.py`

**Interfaces:**
- `CapitalReservationBook(policy: PortfolioBudgetPolicy)`
- `reserve(*, reservation_id: str, user_id: str, strategy_id: str, amount: Decimal, created_at: datetime) -> ReservationDecision`
- `release(reservation_id: str, *, released_at: datetime) -> ReservationDecision`
- `snapshot() -> ReservationSnapshot`

- [ ] RED: duplicate active reservation ID fails closed and does not double-count.
- [ ] RED: unknown strategy, wrong user, strategy budget breach, and aggregate user budget breach reject.
- [ ] RED: release unknown/already-released ID does not create available capital or negative reservation totals.
- [ ] RED: two competing reserves cannot both push totals over the same cap.
- [ ] Implement lock-protected deterministic book using caller-supplied IDs/time only.
- [ ] Run tests.
- [ ] Commit: `feat: add atomic portfolio capital reservations`.

### Task 3 — Exposure aggregation and projected concentration

**Files:**
- Create: `engine/portfolio/v2/exposure.py`
- Test: `tests_v1/test_phase7_exposure.py`

**Interfaces:**
- `build_exposure_snapshot(account: AccountSnapshot) -> PortfolioExposureSnapshot`
- `evaluate_projected_exposure(snapshot, intent, context, policy) -> PortfolioExposureDecision`

- [ ] RED: current exposure aggregates marked value by total/strategy/concrete instrument without cross-strategy netting.
- [ ] RED: missing strategy cap fails closed.
- [ ] RED: projected total, strategy, or instrument exposure cap breach rejects with stable reason.
- [ ] RED: missing/invalid reference price or multiplier fails closed.
- [ ] Implement Decimal-only projected exposure.
- [ ] Run tests.
- [ ] Commit: `feat: add Phase 7 projected exposure controls`.

### Task 4 — Sticky audited portfolio circuit breaker

**Files:**
- Create: `engine/portfolio/v2/circuit_breaker.py`
- Test: `tests_v1/test_phase7_circuit_breaker.py`

**Interfaces:**
- `PortfolioCircuitBreakerPolicy`
- `PortfolioRiskMetrics`
- `PortfolioResetAuthority`
- `PortfolioCircuitBreaker.observe(metrics) -> CircuitDecision`
- `PortfolioCircuitBreaker.manual_reset(authority, metrics) -> CircuitDecision`
- property `entries_allowed: bool`

- [ ] RED: daily-loss or drawdown threshold breach latches entries off.
- [ ] RED: audit failure blocks transition and fails closed.
- [ ] RED: healthy subsequent metrics do not auto-reset latch.
- [ ] RED: manual reset without explicit allowed authority or while metrics still breach is rejected.
- [ ] RED: successful manual reset requires audit-before-state-change.
- [ ] Implement without broker/live dependency.
- [ ] Run tests.
- [ ] Commit: `feat: add sticky portfolio circuit breaker`.

### Task 5 — Event-day and expiry risk policy

**Files:**
- Create: `engine/risk/event_day_policy_v2.py`
- Test: `tests_v1/test_phase7_event_day_policy.py`

**Interfaces:**
- `EventRiskAction = NO_TRADE | SIZE_CAP`
- `EventRiskWindow`
- `EventRiskPolicy`
- `evaluate_event_risk(policy, *, at, baseline_qty, requested_qty) -> EventRiskDecision`

- [ ] RED: missing policy fails closed for entry evaluation.
- [ ] RED: active NO_TRADE blocks.
- [ ] RED: SIZE_CAP computes max explicit qty but never returns/constructs a rewritten OrderIntent.
- [ ] RED: requested qty at/below explicit cap passes; above cap rejects.
- [ ] RED: overlapping windows choose NO_TRADE over SIZE_CAP, otherwise lowest size fraction.
- [ ] RED: explicitly versioned policy with no active window passes without hidden event dates.
- [ ] Implement pure timezone-aware policy.
- [ ] Run tests.
- [ ] Commit: `feat: add versioned event and expiry risk policy`.

### Task 6 — Portfolio-aware RiskEvaluator composition

**Files:**
- Create: `engine/risk/portfolio_v2.py`
- Test: `tests_v1/test_phase7_portfolio_evaluator.py`

**Interfaces:**
- `PortfolioContextProvider.context_for(intent: OrderIntent) -> PortfolioRiskContext`
- `PortfolioAwareRiskEvaluator(base_evaluator, context_provider, reservation_book, exposure_policy, event_policy)`
- `.evaluate(intent: OrderIntent) -> RiskEvaluation`

- [ ] RED: base rejection is preserved without portfolio override.
- [ ] RED: missing context/reservation or insufficient reservation rejects.
- [ ] RED: exposure breach rejects using existing `RiskEvaluation` with same limits snapshot authority.
- [ ] RED: event policy breach rejects; allowed explicit reduced-size intent can continue.
- [ ] RED: successful portfolio checks preserve base approved qty; evaluator never constructs ApprovedOrder.
- [ ] Implement wrapper only; no gate minting.
- [ ] Run tests.
- [ ] Commit: `feat: compose portfolio evidence into RiskGate evaluator`.

### Task 7 — Reservation-aware central-gate admission

**Files:**
- Create: `engine/risk/portfolio_admission_v2.py`
- Test: `tests_v1/test_phase7_riskgate_integration.py`

**Interfaces:**
- `PortfolioAdmissionCoordinator(risk_gate, context_provider, reservation_book)`
- `evaluate_entry(intent: OrderIntent) -> ApprovedOrder | RiskRejection | PortfolioAdmissionRejection`
- `release_terminal(intent_id: str, *, released_at: datetime) -> bool`

- [ ] RED: required capital is reserved before the existing central gate evaluates entry.
- [ ] RED: gate rejection/exception releases reservation.
- [ ] RED: only a real `RiskGateV2` result may return ApprovedOrder; coordinator has no constructor/mint path.
- [ ] RED: successful central gate approval retains reservation until explicit terminal release.
- [ ] RED: duplicate active intent/reservation does not gain a second admission.
- [ ] RED integration: circuit breaker `entries_allowed=False` causes existing RiskGate to return `entries_halted` and no ApprovedOrder.
- [ ] RED integration: portfolio exposure breach reaches RiskGate as a normal risk rejection.
- [ ] Implement composition; never mutate intent qty.
- [ ] Run tests + static guard.
- [ ] Commit: `feat: route portfolio controls through central RiskGate`.

### Task 8 — P&L and exposure attribution

**Files:**
- Create: `engine/portfolio/v2/attribution.py`
- Test: `tests_v1/test_phase7_attribution.py`

**Interfaces:**
- `build_attribution(account: AccountSnapshot, realized_records: tuple[RealizedPnlRecord, ...]) -> PortfolioAttributionReport`

- [ ] RED: marked exposure/unrealized P&L group exactly by strategy.
- [ ] RED: realized records aggregate by strategy.
- [ ] RED: realized-record total mismatch vs `AccountSnapshot.realized_pnl` fails closed.
- [ ] RED: report totals reconcile exactly to account snapshot.
- [ ] Implement Decimal-only attribution.
- [ ] Run tests.
- [ ] Commit: `feat: add exact portfolio attribution`.

### Task 9 — Deterministic G7 evidence and qualification workflow

**Files:**
- Create: `engine/portfolio/v2/evidence.py`
- Create: `build/tools/phase7_probe.py`
- Create: `tests_v1/test_phase7_evidence.py`
- Create: `tests_v1/test_phase7_qualification_guard.py`
- Create: `.github/workflows/v2-phase7-portfolio-risk.yml`
- Modify: `build/tools/check_phase7_portfolio_risk.py`

**Interfaces:**
- Deterministic markers/fingerprint and dual-Windows G7 compare.

- [ ] RED: evidence requires all locked Phase-7 authority/safety markers.
- [ ] RED: qualification guard fails if focused tests/static guard/probe/compare disappear.
- [ ] Add dual Windows latest/2022 Python 3.13.14 legs and exact fingerprint compare.
- [ ] Run all Phase-7 focused tests + static guard + local probe.
- [ ] Do not claim G7 GREEN until hosted jobs actually execute and compare passes.
- [ ] Commit: `ci: add deterministic G7 portfolio risk qualification`.

### Task 10 — G7 evidence record

**Files:**
- Create: `docs/v2/phase7/G7_EVIDENCE.md`

- [ ] Record exact implementation head, focused test count, static result and probe fingerprint.
- [ ] Record hosted workflow IDs/status; if jobs fail before steps, status remains NOT QUALIFIED.
- [ ] Record that G7 does not authorize real-money trading and Live remains READ_ONLY/DISARMED.
- [ ] Require full regression/golden preservation and actual dual-Windows G7 comparison for qualification.

## Self-review result

- AF2-RSK-004 coverage: Tasks 1–4, 6–8.
- AF2-RSK-006 coverage: Task 5 + Task 6.
- G7 “same gate” requirement: Task 7 directly composes with existing RiskGateV2.
- ApprovedOrder authority: static guard + Task 7 forbid Phase-7 minting.
- No silent quantity rewriting: Task 5/6/7.
- T2 exclusions: correlated exposure, dynamic risk reduction and rebalancing are not implemented.
- No invented numeric policy: all budgets/exposure/circuit/event values are explicit versioned inputs.
