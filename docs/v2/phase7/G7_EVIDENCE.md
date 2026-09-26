# AlgoFortis V2 — G7 Portfolio & Risk Evidence

**Status:** NOT QUALIFIED  
**Phase:** Phase 7 — Portfolio & Risk V2  
**Scope:** AF2-RSK-004, AF2-RSK-006  
**Safety state:** Live remains `READ_ONLY / DISARMED`.

## Qualification meaning

G7 proves portfolio budgets/reservations, projected exposure controls, sticky circuit breaking, event/expiry entry policy, exact attribution, and routing through the existing `RiskGateV2` authority. It does **not** authorize real-money trading, broker mutation, Live arming, or a live pilot.

## Implemented evidence surface

- immutable/versioned portfolio budget and exposure policy contracts;
- atomic lock-protected capital reservation/release with duplicate and oversubscription rejection;
- gross current exposure aggregation by strategy and concrete instrument;
- projected total/strategy/instrument exposure checks using Decimal arithmetic;
- sticky daily-loss/drawdown circuit breaker with audit-before-latch and audited manual reset;
- versioned event/expiry windows with `NO_TRADE` and explicit `SIZE_CAP` semantics;
- no silent immutable-intent quantity rewrite;
- `PortfolioAwareRiskEvaluator` returns the existing `RiskEvaluation` contract only;
- `PortfolioAdmissionCoordinator` reserves before delegating to the existing `RiskGateV2` and never constructs `ApprovedOrder`;
- exact strategy-level marked exposure, unrealized P&L and realized P&L attribution with mismatch fail-closed behavior;
- Phase-7 static firewall forbidding broker/Live/AI/network/database reachability and Phase-7 `ApprovedOrder` mint/construction;
- deterministic secret-free G7 probe and dual-Windows comparison workflow.

## Deterministic local probe

Expected markers:

```text
APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY
PORTFOLIO_BUDGETS=VERSIONED_EXPLICIT
CAPITAL_RESERVATION=ATOMIC_FAIL_CLOSED
PORTFOLIO_EXPOSURE=THROUGH_RISK_GATE
CIRCUIT_BREAKER=STICKY_ENTRY_POLICY
EVENT_RISK=SCHEDULED_VERSIONED_NO_SILENT_RESIZE
LIVE_STATE=READ_ONLY/DISARMED
G7_ENABLES_REAL_MONEY_TRADING=NO
```

Local isolated probe fingerprint observed during implementation:

`014f0fddfeadf5e6f96ab93235b45a363f81c3b09f72bf266311cdd90f2c7c72`

This fingerprint is development evidence only. It is not G7 qualification until both required Windows jobs execute against the same repository head and the comparison job confirms byte-identical output.

## Focused development verification observed

TDD was performed task-by-task in isolated local harnesses. Observed GREEN slices include:

- capital reservations: 5 focused tests;
- exposure controls: 7 focused tests;
- circuit breaker: 6 focused tests;
- event/expiry policy: 7 focused tests;
- portfolio evaluator composition: 5 focused tests;
- admission coordinator core: 5 focused tests;
- attribution: 5 focused tests;
- deterministic G7 evidence/qualification guard: 4 focused tests.

The exact complete repository focused-suite count is intentionally **not claimed here** until the repository workflow executes. Task-1 contract/firewall evidence is preserved separately in the implementation history.

## Required hosted qualification

Workflow: `.github/workflows/v2-phase7-portfolio-risk.yml`

Required before G7 may be marked qualified:

1. Windows latest / Python 3.13.14 job executes all steps and passes.
2. Windows 2022 / Python 3.13.14 job executes all steps and passes.
3. Phase-7 static firewall passes on both legs.
4. All Phase-7 focused tests execute and pass on both legs.
5. Existing RiskGate integration proves circuit breaker and exposure rejections travel through `RiskGateV2`.
6. Both legs emit the same G7 probe bytes/fingerprint.
7. Cross-Windows comparison job executes and passes.
8. Required full regression/golden preservation is reviewed before merge/release qualification.
9. Exact head SHA, workflow run ID, job IDs, final focused-test count and comparison outcome are recorded below.

## Hosted-run record

- Implementation head: **PENDING FINAL HEAD PIN**
- Workflow run ID: **PENDING**
- Windows latest job: **PENDING**
- Windows 2022 job: **PENDING**
- Cross-Windows compare: **PENDING**
- Complete repository focused-test count: **PENDING**

If hosted jobs fail before steps execute, that is an external runner/provisioning blocker rather than code GREEN or code RED; G7 remains **NOT QUALIFIED**.

## Final safety statement

**G7 GREEN, if later achieved, does not enable real-money trading. Live remains `READ_ONLY / DISARMED`.** Any broker mutation enablement requires its own separately authorized design, qualification evidence, release gate and Owner approval.
