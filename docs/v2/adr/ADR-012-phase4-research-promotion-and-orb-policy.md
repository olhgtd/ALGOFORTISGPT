# ADR-012 — Phase 4 Research, Promotion and ORB Protective-Policy Governance

- **Status:** Accepted / frozen
- **Date:** 2026-09-24
- **Owner decisions:** OD-V2-11, OD-V2-17, Phase-4 ORB protective-policy blockers
- **Applies to:** AlgoFortis V2 Phase 4 — Strategy SDK, Research & Backtest V2

## Context

Phase 4 may not start until the multiple-testing policy, promotion defaults and ORB protective-policy governance are frozen. Existing repository evidence does not contain an Owner-approved ORB stop formula, target/R:R, trailing policy or concrete production configuration. Historical candidate values are therefore not authoritative and must not be promoted into V2 defaults.

The project remains `READ_ONLY` / `DISARMED`. Phase 4 creates research, backtest and promotion-evidence machinery only; this ADR does not authorize broker mutation or real-money execution.

## Decision 1 — Multiple-testing / overfitting control (OD-V2-11)

Adopt the recommended **option (b)**:

1. Every research/search attempt is recorded in an append-only trials ledger, including failed, rejected and early-stopped trials.
2. Promotion evidence requires explicit train/validation/test separation plus WFO and OOS evidence.
3. Research reports include a **deflated performance metric** and a **probability-of-backtest-overfitting estimate** using one versioned methodology implemented and tested in Phase 4.
4. Every search has an explicit, versioned maximum trials budget. The budget is part of the experiment fingerprint and may not be silently increased after OOS evidence is viewed.
5. Trial deletion, relabelling or selective omission may not reduce the recorded trial count used by the overfitting controls.
6. Exact mathematical definitions, numeric tolerances and edge-case handling are versioned implementation contracts and must be reproducible across the two CI environments.

Reality-check-style tests beyond this policy remain optional/future work unless a later Owner Decision promotes them into V2.0 scope.

## Decision 2 — Promotion criteria defaults (OD-V2-17)

Promotion thresholds are **configuration, never hard-coded strategy economics**.

1. Promotion criteria are immutable, versioned, fingerprinted profiles.
2. A profile can contain minimum trade count, OOS share, WFO windows/pass rate, Monte Carlo drawdown cap, cost/slippage stress margin, paper duration/trades, and paper-vs-backtest drift tolerance.
3. The V2.0 built-in default is a fail-closed **`research-only/v1`** profile: it may generate evidence, but it is `NON_PROMOTABLE` until an explicit numeric promotion profile is supplied and validated.
4. No numeric production promotion threshold is invented from legacy values. The first numeric profile must be derived from recorded V2 baseline evidence, including the ORB reference run, and committed as a separately versioned policy.
5. Backtest P&L, profit factor, win rate or any single metric can never independently produce promotion eligibility.
6. Backtest-to-paper and paper-to-eligible-for-live profiles are distinct. An `ELIGIBLE_FOR_LIVE` evidence state does not arm or execute anything; live mutation remains unreachable while the platform is DISARMED.
7. Missing, ambiguous or incomplete criteria fail closed to `NON_PROMOTABLE` with deterministic rejection reasons.

Legacy paper milestone values remain legacy evidence only and are not V2 Phase-4 defaults.

## Decision 3 — ORB protective-policy governance

No Owner-approved ORB protective economics are present in the frozen repository evidence, so Phase 4 **must not invent them**.

1. The ORB SDK manifest/config requires an explicit versioned `protective_policy_ref` for any executable backtest or paper simulation that needs protective exits.
2. The referenced policy must bind, at minimum:
   - stop construction/formula and all parameters;
   - target construction / R:R semantics and all parameters;
   - trailing-stop semantics, including activation/update rules;
   - OCO composition and sibling-cancellation semantics;
   - tick-size/rounding behavior;
   - policy/schema version and deterministic fingerprint.
3. Missing or unresolved protective policy is a hard validation error for executable ORB simulation and makes the run ineligible for promotion evidence.
4. The generic RiskGate minimum R:R or any historical candidate ATR/R:R value may not be substituted as an ORB-specific default.
5. The SDK/reference ORB port may be built before concrete ORB economics are chosen because the economics are injected through the required policy reference rather than hard-coded into strategy code.
6. Tests may use clearly labelled `TEST_ONLY` fixture protective policies to prove contracts, determinism and replay. Test fixture values are not production defaults and cannot be promotion evidence.
7. Existing generic protective-order/OCO infrastructure may be reused, but reuse does not silently choose ORB trailing/target behavior.

This freezes the **governance and fail-closed configuration contract**, while leaving concrete ORB economic values to an explicit future owner-approved policy profile backed by research evidence.

## Consequences

- Phase 4 is unblocked without fabricating performance thresholds or ORB economics.
- Strategy code stays separate from research/promotion policy.
- Trials and search budgets become auditable inputs to every promotion decision.
- The first numeric promotion profile can be calibrated from V2 evidence without changing SDK contracts.
- ORB can serve as the reference SDK port using explicit test/research policy fixtures while production promotion remains fail-closed.
- No part of this ADR changes `READ_ONLY`, `DISARMED`, broker permissions, or live execution authority.
