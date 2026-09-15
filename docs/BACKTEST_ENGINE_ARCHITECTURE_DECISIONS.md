# SentinelX — Backtest Engine Architecture Decisions

**Status:** FROZEN  
**Companion to:** `BACKTEST_ENGINE_FREEZE.md`  
**Purpose:** Resolve architecture conflicts discovered during the freeze-alignment audit before Backtest Engine implementation begins.

---

## 1. Authority, Amendment, and Sequencing

`BACKTEST_ENGINE_FREEZE.md` is the owner-approved direction for the Backtesting Engine.

### Authority and amendment rule

1. `requirements-freeze-125.md` (business/trading requirements) and `architecture-rules.md` (engineering contracts) remain the frozen baselines.
2. Later architecture decisions do NOT casually or implicitly override baseline requirements.
3. An explicit, numbered owner-locked decision in this log (e.g. §59 multiplier-aware Q64 sizing, §64 cost-adjusted capital basis, §73 planned entry references) may refine, correct, bind, or supersede an earlier frozen engineering or business requirement ONLY when the decision explicitly identifies that exact refinement, correction, or supersession.
4. For that exact identified conflict or refinement, the later owner-locked decision becomes authoritative and governs implementation.
5. All historical requirements, baseline texts, and superseded decisions remain preserved for traceability and auditability; historical records are never deleted or rewritten.
6. Unrelated frozen requirements and engineering contracts remain completely unchanged.

### Sequencing

For sequencing decisions related to the Backtesting Engine, this file and `BACKTEST_ENGINE_FREEZE.md` supersede the older roadmap order that required ORB implementation before backtest execution.

This does NOT invalidate unrelated frozen interfaces or contracts from:
- `architecture-rules.md`
- `requirements-freeze-125.md`
- `PROJECT_STRUCTURE.md`
- `CONFIG_SCHEMA.md`
- `CLAUDE.md`

Only the conflicting **implementation sequence** and explicitly numbered owner-locked refinements are superseded.

### Frozen sequence

1. Complete the long-term Backtesting Engine core.
2. Validate it with deterministic dummy/test signal generators and synthetic data.
3. Complete engine accounting, execution, costs, metrics, validation, and reproducibility.
4. Pass the Backtest Engine completion gate.
5. Implement real trading strategies such as ORB later.

Real ORB implementation remains deferred.

The existing `strategies/orb/orb_strategy.py` skeleton may remain untouched.

---

## 2. Current Active Milestone

Do not depend on inconsistent historical phase numbers.

The current active milestone is:

> **Complete SentinelX Backtesting Engine — Long-Term Stable Core**

Older documents may continue to contain different phase labels. Those labels are historical/documentation metadata and must not block the current owner-approved milestone.

`SENTINELX_PROGRESS.md` should be updated in a controlled step to reflect this active milestone after this architecture decision file is accepted.

Do not rewrite historical documents merely to make numbering cosmetically consistent.

---

## 3. Market and Timezone Architecture

The older requirement “IST throughout” must NOT be interpreted as a permanent global engine restriction.

SentinelX must support India and US markets.

### Frozen rule

All internal timestamps must be timezone-aware.

Market/exchange-specific time handling must come from a market profile.

Examples:
- India market profile -> `Asia/Kolkata`
- US market profile -> appropriate exchange timezone/calendar

The central backtest loop must not hard-code IST.

### Display/reporting

Reporting/display timezone may be configurable independently from the exchange timezone where practical.

### Existing `HistoricalDataFeed`

The existing behavior that normalizes timestamps to `Asia/Kolkata` must NOT be silently changed now.

It is considered a known compatibility/migration issue.

When market-profile support reaches the data-feed boundary:
1. inspect all existing tests,
2. define migration behavior,
3. add India and US timezone tests,
4. then change implementation in a controlled step.

---

## 4. Market Profile Boundary

Use a two-layer design:

### Code-level immutable value object

A small, explicit code-level model must define the contract for a market/exchange profile.

It should be capable of representing at least:
- market/exchange identifier
- timezone
- session open
- session close
- holidays/calendar identifier
- tick size
- lot size
- contract multiplier
- supported asset metadata hooks
- cost-profile reference
- expiry/contract metadata hooks where required

The exact field list must remain minimal and requirement-driven.

### External configuration

Actual India/US values should come from configuration where practical.

Business behavior must not be buried in arbitrary config files.

The config layer supplies values; code-level objects define valid structure and behavior.

---

## 5. First Backtest Engine Slice

The first implementation slice must establish only the minimum stable public foundation required by all later engine modules.

### First slice must contain

1. `BacktestRunContext`
2. `MarketEvent` contract
3. `BarEvent` implementation
4. deterministic chronological event-loop contract
5. minimal run result/status contract
6. tests for deterministic event ordering

### First slice must NOT yet contain

- real ORB logic
- real strategy business logic
- portfolio accounting
- full order lifecycle
- cost models
- metrics
- walk-forward
- Monte Carlo
- bootstrap
- parameter sensitivity
- broker integrations
- UI/plotting

Those come in later engine slices after the foundation is accepted.

---

## 6. BacktestRunContext Contract

`BacktestRunContext` must represent the immutable or controlled metadata/configuration for one backtest run.

It should be capable of holding or referencing:
- run id
- engine version
- strategy identifier/version
- market profile
- requested symbols
- requested timeframes
- date/time boundaries
- execution model identifier
- cost model identifier
- reproducibility seed
- configuration snapshot/fingerprint
- data fingerprint(s) where practical

Do not add fields merely because another framework has them.

The context must not contain mutable portfolio/account state.

---

## 7. MarketEvent Contract

The engine must process generic market events rather than hard-coding the central loop to one candle size.

### Current implementation target

`BarEvent`

At minimum it must support:
- symbol
- timestamp
- timeframe
- open
- high
- low
- close
- volume
- data-quality/synthetic marker where available

### Future-ready extension

A future `TickEvent` may be added without redesigning:
- order engine
- portfolio
- metrics
- validation
- reporting

Do not implement a full tick engine now.

---

## 8. Deterministic Event Loop Contract

The event loop is the core sequencing mechanism.

### Frozen requirements

- chronological processing
- deterministic ordering
- explicit multi-symbol ordering rule
- explicit multi-timeframe ordering rule
- no future-data access
- repeatable output from the same input/configuration
- clear start/finalize lifecycle
- strategy signal generation separated from execution
- no silent mutation outside owned engine components

The engine must define what happens when multiple events share the same timestamp.

That tie-breaking rule must be deterministic and covered by tests before dependent modules rely on it.

---

## 9. No-Look-Ahead Rule

No component may use future market data when making a current decision.

The default execution model remains:

> signal from a completed bar -> eligible execution no earlier than the next bar open

Same-bar execution must not occur silently.

Any future alternative execution model must be explicit, named, configurable, and independently tested.

---

## 10. Strategy Boundary

Keep the existing SentinelX `Signal` / `StrategySignalGenerator` separation.

Frozen rule:

`Market data -> StrategySignalGenerator -> Signal`

Then:

`Signal -> engine-side validation/translation -> Order/Execution`

A strategy must not directly:
- mutate cash
- mutate portfolio state
- force fills
- modify trade ledger
- alter metrics

Real strategy logic is deferred.

A deterministic dummy/test strategy is allowed only for engine testing.

---

## 11. Rule 7 — `alert_and_halt()` Decision

The current audit found a contract mismatch:

- frozen architecture declares `alert_and_halt(...) -> NoReturn`
- current implementation logs and returns

### Frozen decision

Do NOT silently weaken the declared contract.

`NoReturn` means normal execution must not continue after the halt path is invoked.

However, this must be fixed as a separate controlled reconciliation task before any new engine component depends on that halt behavior.

Before modifying it:
1. inspect current tests and callers,
2. define exact halt mechanism,
3. add tests proving it does not return normally,
4. confirm no unrelated behavior breaks.

Until then, treat Rule 7 as a known unresolved implementation defect, not as accepted behavior.

---

## 12. Walk-Forward Documentation Mismatch

The audit found that `HistoricalDataFeed` documentation implies walk-forward boundary support while the implementation does not provide it.

### Frozen decision

Do not assume walk-forward support exists in the feed.

Walk-forward testing belongs to the Backtesting Engine validation layer.

It must be implemented explicitly with:
- chronological splits
- train/test boundaries
- leakage prevention
- reproducible validation output

Any misleading docstring should be corrected only during the relevant controlled implementation step.

---

## 13. Configuration Directory

The absence of a current `config/` directory is not itself a blocker.

Do not create empty folders only to match a historical project-tree document.

Create configuration modules/files only when the first concrete configuration contract is implemented.

Market-profile configuration is expected to become one of the first valid reasons to establish this boundary.

---

## 14. Git Status Limitation

The project is currently not a Git repository according to the audit.

This architecture decision does NOT authorize:
- `git init`
- resets
- checkouts
- restores
- automated repository mutations

Change tracking must therefore be handled carefully through:
- small implementation slices
- explicit file-change reports
- full test runs after each slice
- no unrelated edits

Git may be introduced only through a separate owner-approved step.

---

## 15. Public Contract Stability Rule

Before implementing a new major backtest subsystem:

1. define its smallest public contract,
2. verify it does not conflict with existing frozen contracts,
3. implement only that slice,
4. write tests,
5. run focused tests,
6. run the full existing suite,
7. stop on suspicious behavior or unexpected regression.

Do not build multiple large subsystems in one unreviewed change.

Long-term stability is achieved through clean boundaries, not through one giant implementation patch.

---

## 16. Planned Engine Slices

The Backtesting Engine should proceed in controlled slices.

### Slice 1 — Core Run/Event Foundation
- BacktestRunContext
- MarketEvent
- BarEvent
- deterministic event-loop contract
- run result/status
- ordering tests

### Slice 2 — Market Profiles and Time
- market/exchange profile
- timezone/session/calendar boundary
- India profile
- US-ready contract
- timezone tests

### Slice 3 — Signal Intake
- signal validator
- signal-to-order intent boundary
- dummy/test strategy integration
- signal timing tests

### Slice 4 — Orders
- order model
- lifecycle states
- order validation
- queue/pending state
- market/limit/stop/stop-limit representation

### Slice 5 — Execution
- next-bar-open fill model
- market fills
- limit fills
- stop fills
- stop-limit fills
- slippage interface
- execution records
- no-look-ahead tests

### Slice 6 — Portfolio and Accounting
- position
- account
- cash
- equity
- realized P&L
- unrealized P&L
- mark-to-market
- contract multiplier
- lot size
- quantity validation

### Slice 7 — Trade Ledger
- trade lifecycle
- immutable trade records
- entry/exit
- gross/net P&L
- costs
- timestamps/duration

### Slice 8 — Costs
- brokerage/commission
- exchange charges
- statutory/tax charges
- asset-specific profiles
- India/US-ready configuration

### Slice 9 — Multi-Symbol / Multi-Timeframe
- synchronization
- deterministic tie-breaking
- session-aware event availability
- resampling boundary where approved

### Slice 10 — Metrics
- exact frozen SentinelX metric set
- equity/drawdown calculations
- trade statistics
- result summaries

### Slice 11 — Validation
- chronological splits
- walk-forward
- bootstrap
- Monte Carlo
- parameter sensitivity
- batch/multi-run validation
- leakage tests

### Slice 12 — Reproducibility
- deterministic seeds
- snapshots
- config fingerprint
- data fingerprint
- result fingerprint where practical

### Slice 13 — Reporting/Export
- structured backtest result
- trade report
- metrics report
- validation report
- machine-readable export

### Slice 14 — Integration / Regression Hardening
- complete synthetic fixtures
- accounting edge cases
- gaps/missing bars
- multi-symbol
- multi-timeframe
- fees/slippage
- sessions
- determinism
- end-to-end regression suite

### Slice 15 — Final Backtest Engine Audit
- freeze compliance review
- full-suite test run
- unresolved-risk review
- documentation alignment
- owner approval gate

---

## 17. Owner-Approved Slice 5 Execution Decisions

These decisions refine Slice 5 execution behavior. They do not authorize
implementation by themselves. The default no-look-ahead rule remains:

> signal from a completed bar -> eligible execution no earlier than the next bar open

### 17.1 Limit order better-price behavior

For the first eligible **real** bar after order creation:

- BUY LIMIT: if `OPEN <= limit_price`, the fill basis is `OPEN`; otherwise,
  if valid OHLC evidence touches or trades through the limit, the fill basis
  is `limit_price`; otherwise the order remains unfilled.
- SELL LIMIT: if `OPEN >= limit_price`, the fill basis is `OPEN`; otherwise,
  if valid OHLC evidence touches or trades through the limit, the fill basis
  is `limit_price`; otherwise the order remains unfilled.

No same-signal-bar look-ahead fill may be invented.

### 17.2 Stop order gap behavior

- BUY STOP: if an eligible real bar opens at or above the stop, the
  trigger/fill basis is `OPEN`. Otherwise, valid reach/cross evidence uses
  the stop price as the pre-slippage trigger/fill basis.
- SELL STOP: reverse the BUY STOP logic. If an eligible real bar opens at or
  below the stop, the trigger/fill basis is `OPEN`; otherwise valid
  reach/cross evidence uses the stop price as the pre-slippage basis.

Never grant an impossible favorable stop-price fill when price gaps through
the stop.

### 17.3 Stop-limit intrabar ambiguity

Use **D first -> A fallback**:

- **D:** reliable, correctly synchronized lower-timeframe evidence for the
  exact ambiguous parent-bar window may resolve intrabar sequence.
- **A:** if that evidence is unavailable, incomplete, unreliable, or still
  ambiguous, do not invent an OHLC path and do not assume a fill. The order
  remains unfilled and active, subject to its applicable lifetime rules.

Slice 5 must not force a lower-timeframe resolver into the current event/data
architecture if doing so would require new architecture or risk look-ahead.
If the dependency is absent, Slice 5 implements the conservative A fallback
only. The D resolver remains an approved mandatory future capability and must
be added when correctly synchronized lower-timeframe evidence is available.

### 17.4 Slippage

Execution requires a replaceable slippage-model boundary. The initial Slice 5
default is **zero slippage**; no arbitrary universal non-zero assumption may
be hard-coded. The design must allow later approved instrument-appropriate
models, including BPS-based, spread-based, and depth/liquidity-based models,
to be selected through configuration and later UI boundaries without source
edits.

### 17.5 Time in force

There is **no silent universal default**. Every applicable pending order must
explicitly specify its TimeInForce.

- **DAY:** valid only for its applicable trading session; if unfilled at the
  applicable session boundary, session-expiry behavior applies.
- **GTC:** may remain active across sessions until fill, cancellation,
  contract expiry, or another approved termination rule.

TimeInForce controls the lifetime of a pending/unfilled order. It is separate
from position holding policy, which controls whether an already-filled
position is intraday-only or may remain open across sessions. Position holding
policy belongs to later Position/Portfolio-integrated design.

### 17.6 Same-timestamp order priority

Slice 5 must not invent arbitrary capital/order priority and must not use
lexical symbol order, order ID, or existing market-event ordering as implicit
capital-allocation priority. Eligible orders may be evaluated independently
under execution rules where no portfolio-capital conflict must be resolved.
Capital, risk, and strategy allocation priority belongs to the appropriate
Portfolio/Risk layer when that state exists; do not implement it in Slice 5.

### 17.7 End-of-backtest outstanding orders

Outstanding orders use TimeInForce-aware handling:

- DAY orders follow their session-bound expiry rules.
- GTC orders are not silently cancelled or filled merely because the
  historical dataset ends. Preserve/report their unresolved outstanding state
  where applicable.

Dataset exhaustion is not itself a market cancellation event.

### 17.8 Synthetic and gap-filled bars

Synthetic/gap-filled candles are not valid execution evidence. No new trigger
or fill may be created from a synthetic bar. Pending orders wait for eligible
real market evidence, subject to their TimeInForce/lifetime rules. This is a
data-integrity correctness rule, not a user preference.

### 17.9 Stop-Loss, Target, and Trailing Stop placement

`BACKTEST_ENGINE_FREEZE.md` requires Stop-Loss, Target, and Trailing-Stop
capability. They are **DEFERRED FROM SLICE 5, NOT DEFERRED FROM THE BACKTEST
ENGINE**. Implement them after the required Position/Portfolio dependencies
exist. The overall Backtest Engine must not be declared complete until all
three capabilities are implemented and tested.

### 17.10 Lower-timeframe resolver placement

The lower-timeframe ambiguity resolver is an approved mandatory future
capability. Before it is implemented, the system must reliably provide
correctly synchronized lower-timeframe evidence for the exact parent-bar
window without look-ahead. If that dependency is absent during Slice 5, do
not invent a partial resolver: use the conservative no-assumed-fill fallback
and retain the resolver as a mandatory future engine item. The design must
allow it to be added without changing the fundamental execution contract.

### 17.11 Strategy, engine, and future configuration boundaries

The strategy owns trading intent: BUY, SELL, HOLD, and EXIT. The
Backtest/Execution Engine does not invent market-direction decisions; it
simulates actionable strategy intent under deterministic, realistic execution
rules. A filled position must not be arbitrarily exited merely because it has
been held for a duration unless an explicit strategy, configuration, risk, or
holding rule requires that exit.

User-adjustable trading/backtest parameters should be supplied through
configuration and later UI boundaries where appropriate rather than requiring
source edits. Examples include capital, quantity/lots, brokerage/cost
profiles, slippage configuration, TimeInForce, strategy parameters,
instrument/timeframe, risk settings, and position holding/square-off policy.
Correctness invariants such as no-look-ahead and invalid-data rejection must
not become casually disableable preferences. Core engine contracts must not
be hard-coded to NIFTY, BANKNIFTY, options-only, India-only, or
intraday-only behavior.

Future strategy-generation systems, including AI-generated strategies, must
use the same standard strategy/signal boundary as manually supplied
strategies. The Backtest Engine remains an independent evaluator; future AI
strategy generation must not alter execution rules to improve its own
backtest results.

---

## 18. Future-Ready but Deferred Features

Architecture may leave clean extension points for:

- tick feeds/events
- partial fills
- OCO orders
- bracket orders
- richer live execution behavior
- additional broker adapters
- additional indicators
- UI plotting

Do not implement their full complexity now unless a later owner decision explicitly promotes them into current Backtest Engine scope.

---

## 19. Backtest Engine Application of the Project-Wide Reference Routing Rule

`REFERENCE_ROUTING_RULES.md` is the single authoritative project-wide workflow
for reference routing, research, comparison, coverage, and reporting. This
section is its mandatory Backtest Engine application: Backtrader remains
mandatory where relevant, but it must not exclude vectorbt, zipline-reloaded,
or any other capability-mapped reference.

### 19.1 Required workflow

For each relevant Backtest Engine task, follow `REFERENCE_ROUTING_RULES.md`.
Where Backtrader is selected, its targeted study must cover the relevant
source, tests, and samples before significant implementation or final
technical recommendation. Backtrader is a reference baseline, not a ceiling
and not a template to reproduce.

The Backtest Engine-specific application is:

1. Understand the applicable SentinelX requirement, approved owner decision,
   and current failure/question first.
2. Route through the project-wide catalog/process and perform targeted local
   Backtrader research where it is materially relevant; do not read the entire
   repository by default.
3. Record the Backtrader findings before judging SentinelX.
4. Inspect the relevant SentinelX code, tests, configuration, and contracts.
5. Explicitly compare the two and classify each material finding as one of:
   - **A — SentinelX already strong:** retain the existing contract/design.
   - **B — useful missing edge:** identify whether it belongs in current scope
     or is a future capability.
   - **C — SentinelX intentionally differs:** document the rejected Backtrader
     behavior and the SentinelX reason.
   - **D — Backtrader has a better concept:** independently design a
     SentinelX-equivalent boundary; do not transplant an API or hierarchy.
   - **E — future capability:** record it as deferred without silently adding
     it to the active slice.
   - **F — not applicable:** state why the concept does not apply.

The project-wide workflow owns routing, multi-reference coverage, trivial-task
exceptions, classification, availability reporting, and the significant-task
report format. The exact Backtrader files depend on the SentinelX requirement.

### 19.2 SentinelX authority and independence

Use the authority order in `REFERENCE_ROUTING_RULES.md` when comparing or
reconciling a Backtrader concept:

Backtrader source, tests, fixtures, API/class hierarchy, and implementation
patterns must not be copied, closely adapted, or recreated for similarity.
SentinelX must independently implement its own interfaces, data models,
algorithms, tests, and fixtures; GPL source code must never be copied.

### 19.3 Availability and evidence reporting

If Backtrader is unavailable, use the project-wide **REFERENCE UNAVAILABLE**
reporting rule; do not substitute memory for source inspection. Backtest Engine
reports retain the project-wide evidence requirements and specifically include
all Backtrader source, test, and sample paths that were researched.

---

## 20. Conflict Resolution Priority

When a conflict appears, use this priority for Backtest Engine work:

1. explicit current owner decision
2. SentinelX frozen requirements
3. this `BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md`
4. verified public contracts
5. SentinelX configuration/schema contracts
6. reference repositories

This priority applies only where documents genuinely conflict.

Do not use it to ignore unrelated hard requirements.

`SENTINELX_PROGRESS.md` records implementation state only and is not an
authority in this conflict order.

---

## 21. Implementation Start Gate

Coding may begin only after this file is accepted and present in the project.

The first coding task must be:

> Implement Slice 1 — Core Run/Event Foundation only.

If Slice 1 reveals a new architecture conflict, STOP before expanding scope.

---

## 22. Owner-Approved Slice 6 Portfolio and Accounting Decisions

These decisions refine the Slice 6 boundary in Section 16. They preserve the
frozen separation of strategy, signal intake, orders, execution,
portfolio/accounting, costs, and trade ledger. They do not authorize Slice 6
implementation by themselves.

### 22.1 Starting capital

Starting capital must be explicitly supplied/configured by the caller,
backtest configuration, or future UI. The Portfolio/Accounting engine has no
universal hard-coded starting-capital default; example values are user
configuration, not engine constants.

### 22.2 Insufficient capital

If an executed trade requires more capital than is available under the
applicable accounting rules, Portfolio/Accounting rejects its acceptance. It
must not silently create negative cash, invent leverage or margin,
automatically reduce quantity, or fabricate margin. The rejection reason must
be deterministic and auditable. Leverage/margin support requires an explicit
future approved policy.

Slice 6 uses **single-currency accounts**. Each account has one explicit
currency, and the applicable InstrumentSpecification has an explicit currency.
Portfolio accepts accounting only where those currencies match; a mismatch is
deterministically rejected. Slice 6 must not silently convert currencies or
invent FX rates. Multi-currency accounts and FX conversion remain mandatory
future work outside Slice 6.

### 22.3 Execution versus Portfolio/Accounting

Execution answers whether an order could fill from supplied market evidence
and at which execution price. Portfolio/Accounting answers whether the account
can accept and account for that execution under capital, position, and
accounting rules. Execution must not own cash, P&L, capital allocation, or
hidden sizing; Portfolio must not invent market fills. Immutable provenance
must remain traceable from source intent through order, execution, and
accounting.

### 22.4 Position accounting method

The Slice 6 foundation uses **average-cost** position accounting. FIFO, LIFO,
and other tax-lot accounting are not introduced unless separately approved.

### 22.5 Directional intent and option-buying mode

Directional strategy logic remains separate from concrete instrument
selection. The verified frozen `Signal` contract remains unchanged. A future,
nonbreaking deployment/orchestration boundary must instead express directional
intent explicitly as `BULLISH`, `BEARISH`, `EXIT`, or `HOLD`, rather than
overloading concrete execution `SELL` semantics.

In future `OPTION_BUYING` mode, `BULLISH` maps through a separate selector to
BUY of a configured CE contract and `BEARISH` maps to BUY of a configured PE
contract. A bearish directional instruction must not automatically create a
naked short option position. The future boundary must reconcile with the
existing verified Signal actions through an adapter; it does not authorize a
change to strategy/signal production code.

ATM/ITM/OTM choice, strike distance, and expiry-selection policy belong to a
future configuration/UI-controlled instrument-selection layer, not strategy
logic. That selector is not part of Slice 6. This refines, without replacing,
the Strategy Library and Deployment Environments requirement in
`requirements-freeze-125.md`.

### 22.6 EXIT semantics

For the approved foundation, EXIT means **full close** of the applicable
strategy-owned open position. Partial EXIT is not implemented unless approved
later. If no applicable position exists, no closing trade may be fabricated.
EXIT decision logic remains separate from execution and accounting mechanics.

Authorize a position-aware EXIT-resolution boundary with this flow:

`Strategy EXIT intent -> position-aware EXIT resolver -> immutable,
provenance-preserving full-close instruction -> Execution ->
Portfolio/Accounting`.

The resolver identifies only the applicable strategy-owned concrete open
position and produces its concrete closing side and full owned quantity. It
preserves the original strategy/signal/order provenance, never closes another
strategy's position, and never fabricates a market fill. Execution remains
responsible for realistic fill evaluation and Portfolio remains responsible for
accounting the resulting execution. A smallest nonbreaking execution-boundary
extension may accept this concrete close instruction; it does not authorize
partial EXIT.

Stop-Loss, Target, and Trailing Stop remain mandatory later capabilities, not
Slice 6 behavior. Their future trigger logic may create an EXIT/close request;
execution then determines realistic fill behavior and Portfolio performs the
accounting.

### 22.7 Structured instrument identity

Portfolio/Accounting must use structured, collision-safe instrument identity.
For options it must be capable of distinguishing underlying, expiry, strike,
option type (CE/PE), and applicable market/instrument context. Different
option contracts must never collapse merely because they share an underlying.

Reuse compatible canonical identity/value-object concepts where possible. The
existing importer `CanonicalIdentity` is relevant evidence because it already
distinguishes market, instrument, segment, timeframe, underlying, expiry,
strike, and option type; Portfolio must not create a conflicting duplicate
identity system.

### 22.8 Universal instrument-specific sizing

Slice 6 must not assume NSE-only fixed lot sizes. It must support
instrument-specific sizing semantics for future Indian index/options/futures,
equities, Forex, Gold/XAUUSD, and other supported instruments.

Keep separate, where applicable: user/strategy sizing intent, number of lots,
lot/contract size, fractional volume, shares/units, contract multiplier, and
final canonical executable quantity. The applicable specification comes from
authoritative instrument metadata, not a strategy assumption. Live uses
current authoritative broker/exchange/instrument metadata; backtests use
historical date-effective metadata when specifications changed over time.

If metadata is missing, stale, incompatible, or cannot safely resolve the
requested size, reject/fail deterministically with an explicit reason. Do not
guess or silently substitute another size. Live metadata retrieval is not part
of Slice 6; this decision freezes the boundary only.

### 22.9 Multiple strategies on the same contract

Positions preserve strategy ownership and isolation. The system must represent
separate strategy-owned quantities for the same contract while deriving
account-level aggregate exposure. An EXIT from one strategy must not close a
different strategy's position. Same-contract positions must not be blindly
collapsed into an anonymous strategy-less position.

### 22.10 Same-timestamp capital contention

Capital allocation is deterministic and auditable; accidental processing order
or random ordering is never the economic allocation policy. For competing
trades at one timestamp:

1. Use comparable signal/confidence priority only when confidence values are
   valid and comparable across the competing strategies.
2. Otherwise use an explicit strategy priority/rank policy as a deterministic
   control/fallback.
3. If still tied, use an explicit stable deterministic tie-break rule.
4. Accept trades in resolved priority order only while sufficient capital
   remains.
5. Reject remaining unfunded trades with an explicit insufficient-capital or
   allocation reason.
6. Audit every acceptance/rejection and its applied priority reason.

If no safe batch/same-timestamp allocation boundary exists yet, retain this as
mandatory policy for the appropriate orchestration capability rather than
inventing an unsafe Slice 6 queue. This refines the existing prohibition on
implicit lexical, order-ID, or market-event ordering priority.

### 22.11 Mark-to-market

For the initial backtest accounting convention, use the latest eligible,
matching, **real** `BarEvent` CLOSE as the default mark for an open position.
Each position records its valuation timeframe. A mark must come from a real
`BarEvent` for the matching instrument and that same recorded valuation
timeframe; wrong instrument, wrong timeframe, synthetic, or future/look-ahead
evidence is rejected. The architecture must allow a future configurable
mark-price convention. Mark-to-market affects unrealized P&L/equity and never
fabricates a trade fill.

### 22.12 Accounting records

The Slice 6 foundation uses immutable accounting events/results and immutable
account/position snapshots. The trail must support deterministic audit of how
the account changed and preserve provenance through the existing
order/execution/source-intent chain. Opaque mutable in-memory state alone is
insufficient accounting evidence.

### 22.13 Holding and forced exits

Portfolio must not invent a universal forced-exit rule. Holding/exit behavior
comes only from an approved strategy, risk, session, or instrument policy.
Future Stop-Loss, Target, Trailing Stop, time-based exit, expiry handling, and
other close rules must remain explicit capabilities rather than hidden
Portfolio behavior.

### 22.14 Expiry and settlement

Detailed derivative expiry/settlement mechanics are deferred from Slice 6.
Do not invent automatic expiry closure, physical or cash settlement, ITM/OTM
treatment, worthless-expiry behavior, or automatic expiry-day closing rules
until required instrument metadata and an owner-approved settlement policy
exist. This remains mandatory later work whenever derivatives can survive to
expiry and must not be treated as implemented.

### 22.15 Trade ledger and cost scope

Preserve the staged architecture:

- **Slice 6:** Portfolio/Accounting foundation, including its immutable
  accounting evidence and snapshots.
- **Slice 7:** complete Trade Ledger.
- **Slice 8:** costs, brokerage, taxes, and related approved cost accounting.

Do not pull the complete Slice 7 ledger or Slice 8 cost engine into Slice 6.

## 23. Owner-Approved Slice 7 Complete Trade Ledger Decisions

These decisions authorize the Slice 7 contract boundary only. They preserve
the approved separation between Portfolio/Accounting, Trade Ledger, Costs,
Metrics, Reporting, and future live/paper orchestration. They do not
authorize Slice 7 implementation by themselves.

### 23.1 Ledger event key and deterministic replay

Slice 7 uses immutable `LedgerEventKey(run_id, accounting_sequence)`.

- `run_id` must be non-empty.
- `accounting_sequence` must be positive, deterministic, and unique within a
  run.
- The key is assigned at the accounting/orchestration evidence boundary; the
  Trade Ledger must not randomly generate it.
- An exact replay of the same key with the same immutable source evidence is
  idempotent.
- Presenting the same key with different source evidence is a deterministic
  collision/error and must never be silently accepted.

This key supports deterministic trade identity, replay, and duplicate
prevention without changing Portfolio's authority over account state.

### 23.2 Completed-trade definition

One completed trade is one strategy-owned `PositionKey` lifecycle:

`first accepted BUY opening PositionKey -> zero or more accepted BUY additions
-> zero or more accepted SELL reductions -> final accepted SELL reducing owned
quantity to zero -> one immutable completed TradeRecord`.

A fill alone is not automatically a completed trade. Rejected, unfilled, or
accounting-rejected activity must not create a completed trade record.

### 23.3 Average cost and partial reductions

Slice 7 preserves Slice 6 average-cost accounting and must not introduce
FIFO, LIFO, or tax-lot accounting. Multiple accepted BUY additions belong to
the same position lifecycle.

Accepted partial SELL reductions are immutable EXIT/SELL legs within that same
lifecycle. For example, `BUY 3 -> SELL 1 -> SELL 2` produces one completed
TradeRecord with two immutable exit legs. Gross realized P&L comes from the
authoritative Slice 6 accounting deltas; the ledger must not independently
recalculate it.

### 23.4 Ledger ownership, mutability, and retrieval

Slice 7 is an in-memory domain ledger of append-only immutable completed
TradeRecords. Record ordering is deterministic and duplicate prevention/
idempotency uses `LedgerEventKey`. It supports simple account, strategy, and
instrument retrieval/filtering.

Portfolio remains the sole authority for open positions and account state. A
TradeLedger may retain minimal internal lifecycle assembly state needed to
turn accepted accounting evidence into a completed record, but that state must
not become a competing Portfolio source of truth.

No file, database, CSV, or JSON persistence is required in Slice 7.

### 23.5 Preserved accounting and provenance boundaries

Slice 7 preserves the Slice 6 Decimal/monetary-quantum precision policy,
strategy-owned `PositionKey` isolation, single-currency account rule, gross
P&L-only boundary, and immutable provenance chain. Trade ledger logic must not
introduce float accounting or independently round/recalculate authoritative
Portfolio P&L.

### 23.6 Explicit Slice 7 exclusions

Slice 7 excludes brokerage, taxes, costs, net P&L, metrics, reporting/export,
FX conversion, expiry/settlement, broker/live APIs, Option Selector,
Stop-Loss, Target, and Trailing Stop. Costs remain Slice 8.

## 24. Owner-Approved Slice 8 Cost Decisions

These decisions authorize the Slice 8 cost-contract boundary only. They do
not authorize Slice 8 implementation, configuration-schema activation, or
mutation of the verified Slice 6/7 contracts.

### 24.1 Boundary, gross/net P&L, and timing

Slice 8 creates immutable cost assessments that reference verified Slice 7
`TradeRecord`/`TradeLeg` evidence. It must not mutate or reinterpret Slice 6
gross accounting or Slice 7 gross trade records. Gross realized P&L remains
authoritative and unchanged; net realized P&L is derived as
`gross_realized_pnl - total_applicable_cost`.

Costs are assessed from accepted execution-backed `TradeLeg` evidence.
Multiple entries and partial exits are independently assessable economic legs;
a completed-trade assessment aggregates their applicable component results.
Rejected, unfilled, expired, cancelled, invalid, or accounting-rejected
activity has no economic transaction cost in this foundation. Do not invent
cancellation fees.

Slice 8 must not retroactively mutate verified Slice 6 gross Portfolio state.
It produces a separate immutable cost-adjusted assessment/result. Future
orchestration/live accounting may integrate approved costs into cash/equity
reconciliation only through a separately approved boundary.

### 24.2 Generic, configuration-driven component model

The core Cost Engine is broker-, market-, exchange-, and jurisdiction-agnostic.
Rates and formulas must not be permanently hard-coded into production
calculation logic. Configuration must be capable of representing, where
explicitly configured: zero cost, fixed charge, per-unit/per-contract charge,
notional/turnover rate, side applicability, minimum charge, maximum/capped
charge, component-specific deterministic rounding, and dependency on selected
prior cost components.

Do not hard-code jurisdiction-specific names or formulas. Cost-profile or
cost-schedule selection belongs to account, backtest, or deployment
configuration—not strategy logic. Routine broker/rate/schedule changes must
be possible through configuration and later UI without strategy or core
calculation source edits.

### 24.3 Effective-dated schedule selection and availability

Cost schedules are effective-dated. Historical backtests must select the
schedule applicable to the accepted execution timestamp, not blindly apply a
current schedule. Schedules require immutable identity, version, and
provenance sufficient for reproducible historical results.

If a required applicable schedule cannot be resolved, return a deterministic
`COST_UNAVAILABLE`/rejected-unavailable assessment; never silently assume zero
cost. Zero cost is valid only when an applicable configured schedule explicitly
defines it. Ambiguous competing schedule selection is a deterministic
configuration error: do not randomly select, double-charge, or silently
compose schedules. Composition is permitted only when configuration
unambiguously defines distinct applicable components/rules.

### 24.4 Decimal precision, dependencies, currency, and slippage

Cost calculations use `Decimal`, never float. A component may declare explicit
deterministic rounding quantum, approved rounding behavior, and rounding
boundary. Final authoritative monetary outputs remain compatible with the
verified Slice 6 account monetary-precision policy; no hidden INR/USD
assumption is permitted.

Components may use selected prior component amounts only through explicit,
deterministic dependencies. Circular dependencies must reject deterministically.
No India-specific dependency formula may be hard-coded.

Slice 6's single-currency account foundation remains in force. Cost schedule
and assessment currency must match the account/instrument currency; mismatch
rejects deterministically. FX conversion is out of scope. Execution remains
authoritative for accepted fill price; when slippage is represented in that
price, Slice 8 must not subtract slippage again as a transaction fee.

### 24.5 Replay and provenance

Cost assessments are deterministic and immutable. They preserve TradeRecord
identity, TradeLeg/event evidence, account, instrument, execution timestamp,
schedule ID/version/fingerprint, component identity, calculation basis, and
resulting amount. The same immutable trade evidence with the same immutable
schedule must reproduce the same assessment. A collision or changed evidence
under the same deterministic identity must reject.

---

## 25. Owner-Approved Slice 9 Multi-Symbol / Multi-Timeframe Decisions

These decisions authorize the Slice 9 contract and implementation boundary.
They do not implement Slice 9, alter verified Slices 1–8 behavior, or
authorize Slice 10.

### 25.1 Completed-bar-only visibility

SentinelX OHLCV bars retain their approved start-of-interval source timestamp.
For strategy/data visibility, their deterministic availability/completion time
is:

`availability_time = bar_start_timestamp + timeframe_duration`

A strategy may access a bar only when its `availability_time` is less than or
equal to the current decision/event time. Thus a 09:15–09:16 1m bar becomes
visible at 09:16, a 09:15–09:20 5m bar at 09:20, and a 09:15–09:30 15m bar at
09:30. Source start timestamps remain unchanged for provenance. A final OHLCV
bar must never become visible merely because its start-labelled row is loaded.

This completed-bar-only rule applies to every multi-symbol/multi-timeframe
as-of view and is the Slice 9 no-look-ahead visibility boundary.

### 25.2 Explicit configurable subscriptions, triggers, and readiness

A strategy must explicitly declare its required/subscribed data streams, its
evaluation trigger stream(s), and required readiness/minimum-history
conditions. Orchestration evaluates it only when an approved trigger stream
completes and all required context is ready.

All eligible same-timestamp completed evidence becomes visible atomically
before one strategy evaluation. Multiple required-stream updates in the same
batch do not create duplicate evaluation unless an explicit multiple-trigger
policy requires it. Trigger selection is configuration/declaration driven, not
hard-coded in strategy implementation. If required data is unready,
orchestration skips evaluation explicitly; it must not fabricate HOLD.

### 25.3 Same-timestamp capital allocation priority

When multiple entry candidates compete for one limited capital pool at the
same logical timestamp, allocation uses an explicit configurable strategy
allocation priority/rank owned by deployment/orchestration configuration—not
strategy trading logic. The rank is deterministic, unambiguous among
simultaneously competing strategies, and validates/rejects duplicate or
ambiguous priorities before allocation. Lower numeric rank has higher
allocation priority unless an equivalent deterministic representation is used.

Alphabetical symbol order, dictionary/input-file order, strategy execution
order, incidental event ordering, and random choice are prohibited. Confidence
does not automatically determine capital priority; a confidence-based mode is
future work requiring explicit approval and defined cross-strategy
comparability.

### 25.4 Explicit stream/instrument-to-market-profile mapping

Every configured instrument/stream resolves deterministically to an explicit
`MarketProfile`. The mapping is configuration driven and must not infer a
profile from display-symbol text. Multiple timeframes of one instrument may
share its configured profile where appropriate. A required missing mapping
fails/rejects deterministically; no default profile may be silently selected.

This preserves multi-market extensibility without requiring a market-specific
holiday/session database, historical metadata retrieval, or live profile
retrieval in Slice 9.

### 25.5 Reconciled Slice 9 boundaries and exclusions

Stream identity must be instrument-aware and timeframe-aware; timeframe-only
strategy data is insufficient for multi-instrument input. Strategy input stays
restricted to declared subscriptions, and per-stream readiness/freshness is
explicit. No arbitrary staleness-age threshold is approved.

Current execution remains bound to its originating symbol and timeframe.
Lower-timeframe execution from a higher-timeframe signal remains future work.
Slice 6 Portfolio/Accounting, Slice 7 Trade Ledger, and Slice 8 Cost contracts
remain unchanged unless a later implementation demonstrates a genuine
nonbreaking extension is necessary.

Lower-timeframe execution resolution, production resampling, walk-forward,
bootstrap, Monte Carlo, parameter sensitivity, broker/live or paper-trading
orchestration, historical/live metadata retrieval, margin/leverage/short
selling, and unrelated P2 capabilities remain deferred. Strategy data
subscriptions, trigger streams, allocation priority, and stream/instrument-to-
market-profile mapping are configuration driven and later UI-controllable; UI
does not become the source of market-data or accounting truth.

---

## 26. Owner-Approved Slice 10 Metrics Decisions

These decisions define Slice 10 as a pure, deterministic, immutable
calculation boundary. They do not implement Slice 10, alter verified Slices
1–9, or authorize Slice 11.

### 26.1 Authority, evidence, and scope

The metric boundary is:

`authoritative immutable evidence + explicit metric scope + explicit calculation policy → immutable metric summary`

Metrics consume but never own or mutate strategy, portfolio, order, execution,
ledger, cost, market-data, or broker state. Portfolio/Accounting owns account
and equity evidence; TradeLedger owns completed trades; Costs owns immutable
cost evidence; MarketProfile owns session/calendar interpretation; and Slice 9
owns legally available completed market evidence.

Metric scope is explicit, extensible, and filters authoritative evidence
without merging or destroying its ownership/provenance. Initial required scopes
are RUN/ACCOUNT, STRATEGY, INSTRUMENT, and STRATEGY × INSTRUMENT. Unsupported
or invalid scopes reject deterministically. Future dimensions such as
deployment/environment, strategy version, market, asset class, and account
grouping must be addable without rewriting formulas, but are not implemented
by Slice 10.

### 26.2 Authoritative equity and valuation timeline

Slice 10 requires an explicitly ordered immutable account-level valuation/
equity timeline; session-close-only sampling is not its sole authority. Each
observation must preserve its logical timestamp, applicable authoritative
account/cash, realized and unrealized valuation evidence, accumulated costs,
resulting net equity, and source identity/provenance.

Only legally available completed evidence contributes. Future or incomplete
bars are prohibited. Same-timestamp evidence respects Slice 9 atomic
visibility; observations have deterministic ordering; and conflicting,
invalid, or duplicate observations reject. Metrics must not mutate Portfolio
to construct this timeline.

When one instrument updates, another held instrument may use its latest legally
available authoritative completed mark if the valuation policy permits it. The
observation must preserve which mark was used for each instrument; one
instrument's evidence must never be silently substituted for another's.

Equity/valuation-observation cadence is distinct from risk-ratio return-
sampling cadence. Higher-resolution legally available intraday observations
must not be discarded merely because risk ratios use a lower-frequency series.
Max Drawdown uses the authoritative net-equity timeline and must retain that
higher-resolution evidence.

### 26.3 Net-cost view

Slice 6/7 gross accounting and trade evidence, and Slice 8 `CostAssessment`,
remain unchanged. Slice 10 derives a net valuation/equity view from gross
equity less applicable accumulated transaction costs at their economic
execution timing: entry costs from entry, partial-exit costs from that
reduction, and final-exit costs from final close. It must not defer all costs
to trade closure or double-count them.

Default performance summaries are net-of-costs where the required evidence is
available; gross evidence remains preserved separately. A requested net metric
with unavailable or ambiguous required cost evidence uses deterministic
unavailable/rejection semantics and must not assume zero cost. No FX behavior
is introduced.

### 26.4 Returns, annualization, and MarketProfile policy

Return sampling is explicit calculation policy. It must not be inferred from a
strategy, trigger, execution, smallest, largest, or arbitrary input timeframe.
The default foundation is session-level net-equity returns, with annualization
and calendar interpretation from explicit MarketProfile/session evidence—not a
hard-coded 252 assumption. Sharpe's default risk-free rate is zero and
Sortino's default target/minimum acceptable return is zero unless explicitly
configured otherwise. Calmar is CAGR divided by absolute Max Drawdown fraction;
CAGR uses beginning/ending net equity and valid elapsed period under the policy.
Alternative hourly, daily, weekly, or custom return sampling must be addable
without rewriting formulas.

No scope may assume one shared MarketProfile. For a scope containing different
MarketProfiles, eligible scope time for Time Exposure is the scope-aware union
of applicable authoritative MarketProfile eligible-session intervals.
Overlapping intervals count once; SentinelX must not sum session durations,
select an arbitrary primary profile, use a universal 24×7 denominator, or use
the intersection of all markets. Session semantics, including timezone,
holidays, special sessions, boundaries, and DST behavior, remain owned by the
applicable MarketProfile. Missing required profiles or invalid/conflicting
session evidence reject deterministically.

### 26.5 Validity, exposure, holding time, and precision

Every result distinguishes VALID, UNDEFINED, and INSUFFICIENT_DATA, with value,
reason, and provenance as applicable. Corrupt, non-monotonic, or conflicting
evidence rejects deterministically. NaN, Infinity, magic sentinel values, and
fabricated zeros are prohibited.

- Zero trades: Trade Count is valid zero; unavailable trade-derived values are
  UNDEFINED or INSUFFICIENT_DATA.
- No losing trades: Average Loss and Profit Factor are UNDEFINED.
- No winning trades: Average Win is UNDEFINED.
- Zero return volatility: Sharpe is UNDEFINED; zero downside deviation:
  Sortino is UNDEFINED.
- Zero Max Drawdown is valid zero; Recovery Factor and Calmar are UNDEFINED.
- Insufficient elapsed period makes CAGR INSUFFICIENT_DATA; zero or negative
  starting equity makes CAGR UNDEFINED; no equity observations makes equity
  metrics INSUFFICIENT_DATA.

Exposure % is time exposure: eligible trading/session time with at least one
applicable open position divided by total eligible trading/session time for the
scope. MarketProfile determines eligible session interpretation. Overlapping
positions cannot exceed 100%; it is not capital, notional, or margin exposure.
For mixed-profile scopes, the numerator is the duration in the eligible scope
timeline during which at least one applicable position is open *and* that
position's own instrument is within its own eligible MarketProfile interval.
Each instrument remains constrained by its own session even if another market
is open. A 24×7 instrument may expand the scope union but cannot make closed
hours count as exposure for an exchange-traded position. No eligible scope
interval is INSUFFICIENT_DATA; a valid eligible interval with no applicable
open position is valid zero exposure.

Average Holding Time is eligible trading/session duration from a completed
trade's first accepted opening execution to its final accepted closing
execution. Partial exits do not end the interval and scale-ins do not reset it.
Raw execution timestamps/provenance remain available for later calendar-time
reporting; weighted holding analytics are separate future metrics.

Decimal is authoritative wherever practical. Monetary metrics preserve the
existing monetary-quantum policy; non-monetary ratios use deterministic
high-precision calculation rather than binary float truth; percentages remain
canonical fractions; and durations remain canonical duration evidence. No
intermediate display rounding is authoritative—formatting belongs to future
Reporting/UI.

### 26.6 Mandatory set, provenance, and exclusions

The mandatory set remains: Profit Factor, Win Rate, Net Profit, Max Drawdown,
Sharpe, Sortino, Calmar, Expectancy, Recovery Factor, CAGR, Average Win,
Average Loss, Exposure %, Average Holding Time, and Trade Count. Completed
applicable trades determine Trade Count and trade statistics. Max Drawdown is
derived from the net-equity timeline; Net Profit is net-of-cost under §26.3;
and Exposure/Holding Time follow §26.5.

Metric output must preserve immutable scope, source run/evidence identity,
calculation-policy identity/version, gross/net basis where relevant, return
sampling and annualization/session policy, relevant MarketProfile/session
identity, and cost-evidence identity. Future Reporting/UI may format, display,
compare, or visualize metric truth but must not redefine it. The same evidence-
driven calculation contract should be reusable by future Paper/Live work
without weakening deterministic Backtest behavior.

#### Slice 10 provenance hardening erratum

Authoritative metric evidence carries explicit immutable run and account
provenance. `EquityObservation`, `SessionInterval`, and `PositionInterval`
each require `run_id` and `account_id`; authoritative metric calculation has
no implicit all-supplied-evidence assumption and no fallback for missing
provenance. MetricScope filters every consumed evidence type before
calculation: run/account first, then applicable strategy and instrument.
Cost assessments are applicable only through their in-scope authoritative
completed TradeRecord provenance.

A completed TradeRecord used by metrics must have opening and closing
LedgerEventKeys from the same run; cross-run lifecycle evidence is invalid.
Metric evidence identity is a deterministic SHA-256 digest of canonical,
order-independent, in-scope immutable evidence and provenance: complete scope,
complete policy configuration, net/gross basis, selected trades, equity
observations, applicable cost assessments, session intervals, and position
intervals. Counts alone are never authoritative evidence identity.

Slice 10 excludes reporting/export, dashboard/UI, walk-forward, bootstrap,
Monte Carlo, parameter sensitivity, external-index benchmarks, Paper/Live or
broker work, risk/execution/strategy changes, margin/leverage, short selling,
financing/interest, FX, performance instrumentation, and AI decision-making.

### 26.7 Owner-approved final metric decisions

#### 26.7.1 Expectancy

Canonical Expectancy is the total applicable **net realized P&L** of completed
trades divided by the number of applicable completed trades: average net
realized P&L per completed trade. It is monetary, obeys the existing Decimal
and monetary-quantum policy, and uses no intermediate display rounding.

The alternative Win Rate decomposition is a consistency check only:
`(Win Rate × Avg Win) + (Loss Rate × Avg Loss)`, with Average Loss signed
negative. Break-even trades are neither wins nor losses, but they count in
Trade Count and the direct Expectancy denominator. Scale-ins and partial exits
do not manufacture additional completed-trade samples. Zero applicable
completed trades makes Expectancy INSUFFICIENT_DATA; future percentage,
R-multiple, or normalized expectancy measures are separate named metrics.

#### 26.7.2 Recovery Factor

Canonical Recovery Factor is **Net Profit / absolute maximum monetary
drawdown**. Both values must use the same scope, net-of-cost basis,
authoritative net-equity timeline, calculation policy, and evidence universe.
Maximum monetary drawdown is calculated directly from authoritative peak and
subsequent trough equity, never reconstructed from a rounded percentage.

Its evidence preserves peak/trough timestamps and equities, equity-series
identity, and calculation-policy/version identity. Zero monetary drawdown
makes Recovery Factor UNDEFINED; insufficient equity evidence is
INSUFFICIENT_DATA; and negative Net Profit with a valid positive drawdown
produces a valid negative Recovery Factor. It is high-precision Decimal with
no intermediate rounding. Drawdown/recovery/underwater duration and rolling
recovery analytics remain future separate metrics.

#### 26.7.3 Per-trade holding duration in mixed profiles

An individual completed trade's eligible holding duration is the interval from
its first accepted opening execution to its final accepted closing execution,
intersected only with that instrument's own authoritative MarketProfile
eligible-session intervals. The account-level mixed-profile union is never
used for an individual trade. Strategy/account Average Holding Time averages
these applicable completed-trade durations.

### 26.8 Slice 10 readiness

All required Slice 10 metric semantics are now frozen. Slice 10 is ready for
implementation, subject to the approved scope, policy, provenance, validity,
and no-look-ahead boundaries above. This readiness does not mark Slice 10
implemented or complete and does not authorize Slice 11.

---

## 27. Owner-Approved Slice 11 Validation Decisions

These decisions freeze the Slice 11 Validation architecture and contract
boundary. Slice 11 consumes immutable authoritative evidence from prior slices;
it does not become market-data, execution, Portfolio/Accounting, TradeLedger,
Costs, or Metrics authority. These decisions do not implement Slice 11, alter
verified Slices 1–10, or authorize Slice 12.

### 27.1 Validation and parameter-selection modes

Slice 11 supports immutable explicit modes:

- `FIXED_PARAMETERS`;
- `TRAIN_SELECT_THEN_OOS`.

Selection policy is an explicit typed/enum contract, never a free-form string.
`FIXED_PARAMETERS` uses an already-fixed parameter fingerprint, performs no
training-driven selection, and must not attach fabricated selection evidence.

For `TRAIN_SELECT_THEN_OOS`, only training/selection evidence may select a
candidate. The candidate universe, selection policy, selection evidence, and
selected parameter fingerprint are preserved. The selected configuration
freezes before its corresponding OOS window. OOS evidence can never select,
reselect, or retune parameters.

### 27.2 Walk-forward model and authoritative calendar boundaries

Slice 11 supports `ROLLING` and `EXPANDING` walk-forward models. `ROLLING`
remains the mandatory baseline where the frozen historical-depth requirement
applies; `EXPANDING` is an explicit alternative.

Each policy explicitly supplies `training_length`, `test_length`, `step`, and
`embargo`. There are no statistically consequential hidden values.

`training_length`, `test_length`, and `step` use canonical calendar-duration /
calendar-boundary semantics to construct the common validation schedule.
Strategy bar counts and strategy timeframes never define canonical validation
windows. In a multi-instrument validation, outer train/OOS boundaries are
common and calendar-based; each instrument's authoritative `MarketProfile`
determines eligible evidence inside those boundaries.

The frozen 70/30 historical split applies to the canonical available historical
calendar interval, never to a bar count. Boundary construction uses an
explicit, deterministic, versioned boundary/rounding rule and may not depend
on incidental platform or date rounding. Embargo is a separate exclusion gap:

`TRAIN -> EMBARGO -> OOS`

It is not absorbed into the 70% training allocation or 30% OOS allocation.

For `PROMOTION` validation, train and corresponding OOS have zero overlap;
constructed OOS intervals are strictly non-overlapping; selection freezes
before OOS; and incomplete final OOS windows are dropped rather than shortened.
Warm-up evidence is data/indicator readiness only and never training-selection
or OOS outcome evidence. OOS evaluation begins without carried
training/selection positions.

Where the frozen ten-year-depth requirement applies, at least three complete,
eligible rolling OOS windows are required. “Ten years available” requires
canonical calendar coverage plus separately valid applicable MarketProfile/data
eligibility and sufficiency. First-to-last timestamp distance alone is not
proof of usable depth, and material missing/corrupt gaps cannot count silently.
Only complete eligible OOS windows count.

### 27.3 Canonical Primary OOS Evidence Set and sample baseline

`PROMOTION` uses one authoritative Canonical Primary OOS Evidence Set: unique
completed-trade evidence from the frozen selected configuration over the
strictly non-overlapping OOS intervals of the frozen validation run and
universe. It excludes training, selection, warm-up, sensitivity-neighbor,
research-overlap, and post-OOS-retuning outcomes. Duplicate canonical trade
identity is invalid evidence and must not be silently deduplicated.

**Locked OOS timestamp membership.** Canonical OOS intervals use half-open
semantics: `[oos_start, oos_end)`. A completed trade belongs to an OOS window
only when its authoritative `closed_at` timestamp is greater than or equal to
that window's `oos_start` and strictly earlier than its `oos_end`. Entry/open
time never determines OOS membership. Consequently, a trade at the shared
endpoint of adjacent windows belongs to at most one window.

Canonical `PRIMARY_OOS` evidence is fail-closed. Each candidate must bind to a
known frozen `window_id`; satisfy that window's half-open `closed_at` interval;
be eligible for its exact instrument × window pair; use the frozen run's
parameter and selection provenance; and carry the frozen validation-run
identity/configuration provenance. Relabelling non-primary provenance as
`PRIMARY_OOS` is invalid evidence, not a way to enter the canonical set.

Aggregate completed canonical OOS trades are the primary promotion sample
authority. At least 200 trades passes the sample-count baseline. Fewer than
200 produces `INSUFFICIENT_SAMPLE_BASELINE`; it is neither an automatic pass
nor an automatic strategy failure. The only exception is the approved
Bootstrap CI rule below. Break-even completed trades count. Per-window and
per-instrument trade counts remain preserved. No universal hard-coded
per-instrument 200-trade minimum exists.

### 27.4 Bootstrap expectancy confidence interval

Bootstrap answers: “Is OOS per-trade net Expectancy confidently positive?” For
statistically valid single-instrument/dependence-preserving evidence, it uses
chronological Canonical Primary OOS completed-trade net outcomes and a
dependence-aware block bootstrap.

Method, sample count, confidence level, block length, and root seed are
explicit immutable policy inputs; there are no defaults. Its target is mean net
realized P&L per completed OOS trade. For the under-200 exception, the
two-sided CI lower bound must be strictly greater than zero; zero does not
pass. Invalid policy is `INVALID_POLICY`; legitimate inadequate evidence is
`INSUFFICIENT_DATA`. Method, policy, seed, and evidence provenance are retained.

### 27.5 Monte Carlo

Bootstrap and Monte Carlo are distinct. MC-1 is seeded permutation/
sequence-risk analysis. MC-2 is dependence-aware block-resampled
path/drawdown-risk analysis. Monte Carlo never satisfies the under-200
Bootstrap profitability exception.

Percentage/equity drawdown analysis requires explicit starting-equity evidence.
Monte Carlo does not invent leverage, compounding, synthetic prices, random
slippage, or random costs, and must not subtract costs already represented in
net evidence. Any Monte Carlo promotion threshold is a separate explicit
ValidationPolicy gate. Randomized analysis kinds—including Bootstrap, MC-1,
and MC-2—use explicit/versioned, deterministic collision-resistant derived
seed identities; process-dependent `hash()` is forbidden.

### 27.6 Parameter sensitivity and robustness

Sensitivity is mandatory where an applicable parameter domain exists. Explicit
neighborhood forms are `COORDINATE`, `LOCAL_GRID`, and
`EXPLICIT_CANDIDATE_SET`; ranges are never inferred. Numeric and explicitly
declared categorical domains are supported.

Training sensitivity evaluates selection robustness using training/selection
evidence. OOS sensitivity is post-selection robustness evidence only and may
never select or reselect parameters. Primary selected-configuration OOS
performance remains separate; sensitivity-neighbor results/trades never merge
into it or its sample count.

Sensitivity preserves requested, valid, and invalid points; coverage fraction;
evaluated metrics; stability statistics; and provenance. It is diagnostic unless
an explicit policy enables a stability gate. A parameterless strategy is
`NOT_APPLICABLE`. An applicable declared domain that lacks legitimate evidence
is `INSUFFICIENT_DATA`; corrupt/invalid required evidence is `INVALID`; either
prevents overall pass when the analysis is required/applicable. Sensitivity uses
the primary window/embargo construction unless a new validation identity exists.

### 27.7 Hierarchical multi-instrument validation

Validation has three levels: aggregate OOS economic/performance evidence,
mandatory per-instrument evidence, and explicit policy-controlled breadth/
promotion gates. Aggregate pass alone is insufficient for multi-instrument
promotion. Each instrument preserves trade count, metrics, validity, gate
outcomes, applicable Bootstrap/Monte Carlo evidence, reasons, and provenance.
Trade-count-weighted voting is not the default breadth authority.

The instrument universe and universe fingerprint freeze before OOS. No
instrument/window is silently added, removed, or quarantined. Shared parameters
are selected jointly from applicable training-universe evidence and frozen
before OOS. Instrument-specific parameterization is allowed only if the
strategy contract declared it before OOS; no post-OOS per-instrument retuning
is permitted.

For multi-instrument promotion, one immutable common outer walk-forward
calendar schedule applies. Each instrument's MarketProfile determines eligible
evidence within those boundaries, and an explicit instrument × window
eligibility matrix is retained. Research may use independent schedules, but
those results cannot masquerade as canonical promotion evidence.

### 27.8 Gates, statuses, and evidence propagation

Validation gates are fail-closed and non-compensating; no weighted/composite
magic score is permitted. Validation-integrity gates are permanently mandatory.
Promotion addresses applicable sample adequacy, OOS performance, risk/drawdown,
walk-forward consistency, and multi-symbol breadth through explicit versioned
ValidationPolicy thresholds/operators.

All applicable gates and required analyses are evaluated; do not short-circuit
on the first failure. Each required gate/analysis emits a result/status even
when upstream failure prevents numeric computation. Required/applicable status
precedence is:

`INVALID > INSUFFICIENT_DATA > FAIL > PASS`

`NOT_APPLICABLE` is explicit and does not degrade the overall verdict. The
precedence applies to the applicable required dependency graph, not optional
diagnostics. Every gate/result preserves identity, policy/version, scope,
evidence identity, operator, threshold, observed value/status, result, reason,
and provenance.

Invalid evidence propagates only through authoritative dependency/
contamination. If an applicable frozen-universe instrument's primary evidence
is invalid and an aggregate depends on it, that instrument, the dependent
aggregate, and overall promotion validation are invalid. Unaffected evidence
remains diagnostic. A reduced universe requires a new universe fingerprint,
validation identity, and authoritative run. Invalid optional/non-applicable
diagnostics do not contaminate promotion unless promotion depends on them.

### 27.9 Embargo, block length, and OOS overlap

Embargo is explicit `BARS`, `ELAPSED_TIME`, or `SESSION_AWARE_TIME` plus an
explicit value. No inference or conversion occurs. `BARS` is valid only with
one unambiguous instrument/timeframe bar domain; ambiguous multi-timeframe or
multi-instrument use is `INVALID_POLICY`. `SESSION_AWARE_TIME` uses each
applicable MarketProfile/calendar; missing required calendar evidence fails
closed. Mixed scopes use an immutable versioned map with optional scope default
and explicit instrument/stream overrides. The resolved map freezes before OOS,
forms part of validation identity/provenance, and does not create independent
promotion schedules.

Every applicable block analysis has an explicit immutable block length. There
is no auto-selection, heuristic, clamp, shrink, fallback, or silent adjustment.
Bootstrap and MC-2 may differ. Invalid values are `INVALID_POLICY`; legitimate
inadequate evidence is `INSUFFICIENT_DATA`.

`validation_purpose` is immutable: `PROMOTION` or `RESEARCH`. Promotion OOS
overlap is `INVALID_POLICY` and is not repaired/deduplicated. Research overlap
is non-promotional and cannot satisfy promotion sample count, the Bootstrap
exception, or merge/convert into promotion evidence.

### 27.10 Dependence, currencies, Paper/Live, and provenance

Per-instrument statistical analysis uses each instrument's own chronological
canonical evidence. It must not blindly merge independent trade sequences.
Aggregate economic analysis uses authoritative time-aligned net portfolio/
equity evidence. Multi-instrument MC-1 and MC-2 use synchronized economic/time
episodes and blocks that preserve same-time cross-instrument evidence atomically.
Episode construction is explicit, versioned, and provenance-preserved; missing
trustworthy alignment fails closed.

Every aggregate economic scope has explicit immutable base currency and evidence
scope. Same-currency evidence requires no invented conversion. Different
currencies require authoritative point-in-time FX evidence under explicit
versioned conversion policy, at realized-P&L, cost, and applicable valuation
timing. End-of-run conversion, future FX, implicit 1:1, inferred base currency,
and hidden FX routing are prohibited. Missing FX is `INSUFFICIENT_DATA` and
corrupt/conflicting FX is `INVALID`; native instrument evidence remains intact.
Actual FX-engine work remains deferred unless required by a later slice.

Slice 11 is primarily `BACKTEST_PROMOTION`. Future Paper/Live may reuse generic
statuses, provenance, evidence identity, deterministic policy, gate/result
structures, and applicable metric semantics, but must not inherit walk-forward
or OOS semantics. Backtest pass never authorizes Paper/Live, and Paper pass
never authorizes Live.

Validation identity is compound and immutable. It includes applicable purpose;
strategy identity/version; parameter, universe, window-policy, source-data, and
source-evidence fingerprints; validation-policy version; embargo map; base
currency; FX policy; statistical-analysis policy; and seed policy. Canonical
serialization precedes authoritative hashing/fingerprinting. Stable sorting by
window, instrument, and candidate identity is mandatory, so future parallel or
distributed completion order cannot change results.

### 27.10.1 S4 synchronized aggregate economic episodes (owner-approved repair)

For multi-instrument aggregate MC-1 and MC-2 only, synchronization derives
from the authoritative time-aligned portfolio/equity observation timeline, not
from equality of completed-trade `closed_at` timestamps. The immutable episode
key is `(validation_run_id, window_id, authoritative_portfolio_observation_time)`.
Eligible Canonical Primary OOS net outcomes realized in that exact authoritative
observation interval are atomic members of one episode. No nearest-time match,
tolerance, synthetic time bucket, bar-count inference, or master-instrument
substitution is permitted.

Members retain their instrument, canonical trade identity, window, validation
identity, and already-net outcome provenance. One member belongs to exactly one
episode; episodes never cross validation runs or windows; construction and
member ordering are deterministic; missing, duplicate, or ambiguous alignment
fails closed. Aggregate MC-1 permutes episodes, never constituent trades.

For aggregate MC-2, `block_length` is measured strictly in synchronized
`EPISODES`; the immutable aggregate MC-2 policy/provenance must state that
block unit explicitly. There is no conversion from trades, bars, minutes, or
instruments. Per-instrument MC and existing Bootstrap semantics, including the
under-200 Bootstrap exception, remain unchanged. Aggregate Bootstrap is not
authorized by this repair.

### 27.11 Validation evidence and preserved authority

`ValidationRunEvidence` must carry nonempty applicable identities for source
run, configuration, source data, MarketProfile, cost policy, and metric policy.
Optional `BacktestRunContext` fields are not implicit validation provenance.

Slice 11 consumes immutable evidence and preserves Slices 1–10 authority:
Slice 9 market-data visibility/subscriptions, MarketProfile/session ownership,
strategy signal/state, orders, execution, Portfolio/Accounting, TradeLedger,
CostAssessment, Slice 10 MetricSummary/formulas, Decimal/monetary policy,
Rule 7 contracts, and runtime-performance governance remain unchanged.

Reporting/UI, broker integration, Paper/Live orchestration, Slice 12+, runtime
instrumentation, distributed execution, unrelated risk/execution changes, and
production resampling outside these approved validation semantics remain
deferred.

### 27.12 Slice 11 readiness

The final consolidated contradiction/stress audit found no P0/P1
cross-decision conflict and no Slice 1–10 production-contract conflict. All
owner decisions required for Slice 11 implementation are resolved. Slice 11 is
ready for implementation under this section, but is not implemented or complete.

---

## 28. Owner-Locked Slice 12 Reproducibility Architecture (v1)

This section is the single coherent, versioned Slice 12 architecture.  It
refines the Slice 12 scope in §16 and preserves all existing Slice 1–11
economic contracts.  It authorizes architecture and later implementation only;
it does not make reporting/export artifact serialization a Slice 12 concern.

### 28.1 D1 — reproducibility equivalence

Slice 12 guarantees all of the following:

1. logical-run reproducibility;
2. deterministic economic-result reproducibility; and
3. exact seeded randomized-analysis reproducibility.

Byte-identical report/export artifacts are explicitly deferred to the future
versioned reporting/serialization contract.  "Same economic result" binds
authoritative outcome evidence, not merely headline P&L.

An authoritative reproducible result is either a successful authoritative
economic/result outcome or a Category-A deterministic structured failure after
valid Tier-1 manifest establishment.  The failure case is governed exclusively
by §28.8; it does not create a competing failure taxonomy.

### 28.2 D2 — immutable hierarchical manifest and identity DAG

Each logical run has one immutable, versioned `ReproducibilityManifest` run-
start snapshot.  It composes authoritative component identities rather than
duplicating their underlying state, binds every required Tier-1 input and
randomness provenance, and fails closed if mandatory Tier-1 identity is absent.
Changing a Tier-1 input creates a different logical-run identity.

Only identity-critical Tier-1 child identities compose
`manifest_fingerprint`.  Tier-2 operational provenance and Tier-3
non-authoritative fields remain inspectable evidence but are excluded directly
and indirectly from the logical-run fingerprint.

Physical execution/replay attempt IDs, process UUIDs, timestamps used only to
identify an attempt, and equivalent operational identifiers are not Tier-1
identity and must not appear in a Tier-1 child fingerprint.  If introduced,
they are operational provenance only.  The mandatory acyclic direction is:

```text
Tier-1 inputs -> component fingerprints -> manifest_fingerprint
    -> execution/replay attempt -> successful-result or Category-A-failure fingerprint
    -> replay comparison/cache
```

Result fingerprints never feed back into `manifest_fingerprint`.  In
particular, a future logical-run identity must not form a cycle through
`ValidationRunEvidence.source_run_id` or an equivalent field.

### 28.3 D3 — canonical market-data identity

Market-data identity is content-based, never a Parquet/CSV/XLS file-byte
identity.  Each authoritative stream is fingerprinted from its existing
authoritative `InstrumentIdentity`, its exact validated timeframe string, its
normalized completed canonical market evidence, and the explicit
interpretation/normalization policy that gives that evidence economic meaning.
A top-level data snapshot hierarchically composes canonically ordered stream
identities and relevant data-policy identities.  Incidental input order cannot
change identity; a material candle revision must.

Raw vendor/file hashes and importer manifests remain separate audit provenance;
they do not replace canonical market-data identity.  Timeframe identity reuses
the existing exact string without invented aliases: under the current contract
`"5m"` and `"05m"` remain distinct where both are accepted upstream.

### 28.4 D4 — canonical fingerprint encoding and timestamp precision

All Slice 12 fingerprint schemas use SHA-256 over deterministic,
schema-versioned, type-aware, length-delimited canonical encoding.  Field order
is explicitly schema-defined; dictionary insertion order, filesystem order,
worker completion order, Python `hash()`, delimiter-only concatenation,
`repr()`, pickle, object identity, and incidental runtime serialization are
prohibited.  Every schema version is recorded externally and included in its
own hashed canonical input.

Decimals encode finite exact numeric value as canonical fixed-point text:
insignificant trailing zeros are removed, every signed zero is canonical zero,
and scientific notation is not canonical.  Tick-size quantization is forbidden
inside the encoder.  NaN and infinities fail closed.

Enums encode enum type identity and member identity separately.  Mappings use
a closed, explicit schema-defined field set/order and reject unexpected fields.
Unordered sets fail closed unless their owning schema supplies explicit
ordering.  Nested values use either their own versioned canonical schema or an
existing authoritative child fingerprint.  Timeframe/duration representation
is the representation owned by the existing authoritative contract.

Every authoritative timestamp must be timezone-aware, normalized to UTC, and
encoded as ISO-8601 `Z` notation at fixed nine-digit nanosecond precision.
Native Python `datetime` microseconds are exactly zero-padded into that domain;
this aligns representations and does not invent evidence.  Precision finer
than nanoseconds fails closed.  The fingerprint pipeline must extract
sub-microsecond precision directly from its native representation—especially a
`pandas.Timestamp`—and must never first pass it through a microsecond-limited
Python `datetime`, truncate it, or round it.  Timezone/calendar economic
semantics remain separately bound through their authoritative policy identity.

### 28.5 D5 — Tiered source, runtime, and dependency provenance

Tier 1 identity-critical evidence includes source-content identity,
`RuntimeIdentity` (Python implementation and exact authoritative runtime
version, never a machine-specific interpreter path), relevant detected runtime
dependency closure, and timezone/calendar-data identity where it can affect
economic semantics.  Tier 2 operational provenance may include OS, CPU/GPU,
machine identity, locale, and relevant worker/thread counts.  Tier 3
non-economic evidence includes logging, UI, and report-formatting settings.
Only Tier 1 composes the manifest.  Git commit/branch/dirty state is useful
provenance but source reproducibility never depends exclusively on Git.

#### SourceIdentityPolicy/v1

The default Tier-1 Python source roots are `engine/**/*.py` and
`strategies/**/*.py`.  Every ordinary Python source file in those roots is
included independently of import traversal.  Changing those roots or their
boundary needs a new versioned policy.  Each file identity binds canonical
project-relative `/` path plus exact content bytes through the D4 encoder;
absolute paths, unresolved `..`, native separators, duplicate canonical paths,
raw path/content concatenation, and symlinks/reparse points in the source set
fail closed.  Composition is sorted by canonical relative path.  Mutation
during capture prevents certification or requires a clean new capture.

Non-Python runtime resources are included only through an explicit versioned
allowlist when authoritative runtime code loads/parses/consumes them and they
can affect economic semantics.  They are not inferred by broadly hashing
`engine/**/*` or `strategies/**/*`.  An undeclared consumed authoritative
resource fails certification.  Tests, reference repositories, data, caches,
bytecode, logs, reports, UI/report assets, temporary/generated material,
`.git/`, governance/design/progress/reference documents, and root utilities
outside authoritative economic runtime are excluded.  Runtime configuration is
owned by ConfigurationIdentity rather than duplicated into SourceIdentity.

#### DependencyIdentity/v1

Slice 12 requires distinct, versioned identities for (a) declared runtime
dependency specification, (b) approved resolved dependency lock/baseline, and
(c) actually detected authoritative runtime dependency closure.  A
version-controlled declaration and resolver-produced approved lock are required
before certification.  Do not lock a package-manager product name here, and do
not use unrestricted whole-machine `pip freeze`; development, test, reporting,
and UI packages are excluded unless authoritative runtime requires them.

Optional/selectable backends that can change authoritative data/economic
semantics must be explicitly selected by a versioned dependency/runtime policy.
The actual detected runtime closure is what a valid manifest binds.  If that
closure is fully detected yet differs from the approved lock, establish the
manifest with the actual closure and emit separate versioned environment-
conformance/certification status.  If closure detection is incomplete, it is a
Category-B manifest-establishment failure and no manifest fingerprint exists.

### 28.6 D6 — replay and successful-result identity

Mandatory Slice 12 replay is `RUN_REEXECUTION`: deterministic re-execution
from canonical Tier-1 inputs.  Reusing recorded signals, orders, fills, ledger
records, or validation evidence is not a substitute for a full replay.  A
physical replay attempt may have operational provenance only.

Replay states are `REPLAY_MATCH`, `REPLAY_MISMATCH`, and
`REPLAY_UNVERIFIABLE`.  Missing required evidence is never MATCH.  Comparison
is hierarchical and localizes manifest, data, configuration, strategy/source,
economic/result evidence, validation, and randomized analysis differences.
It recurses through successful result children, where applicable: completed
trade/ledger, execution/fill, portfolio/accounting, cost, metrics, validation,
and seeded randomized-analysis evidence.  The same states apply to a
Category-A failure; failure-to-same-failure may match, while failure-to-success
or success-to-failure is a mismatch.

A successful-result fingerprint is versioned, hierarchical, and acyclic.  It
reuses existing authoritative child evidence/fingerprints where available and
binds the applicable outcome families above.  It must distinguish equal final
P&L with different trade/fill/cost/validation evidence.  Manifest-side policy
identities describe input/cause; result-side identities describe outcome/effect.
They remain distinct namespaces.

### 28.7 D7 — cache boundary

Cache is an optimization, not proof of full-run reproducibility.  A verified
cache result may be represented distinctly (for example
`CACHE_HIT_VERIFIED`), never as `REPLAY_MATCH` merely because a key matched.
Replay-verification mode always re-executes.  Logical-result cache keys are
rooted in `manifest_fingerprint` and a versioned cache schema/policy.  Stale,
malformed, partial, or corrupt payload/evidence fails closed and may not be
trusted only because a filename/key appears to match.

### 28.8 D7 — deterministic failure taxonomy

Category A is a deterministic structured failure after valid manifest
establishment.  It may be an authoritative reproducible result only through
stable machine-readable, versioned evidence containing the failure-result
schema, applicable existing failure code/status, relevant canonical evidence,
governing policy identity (reused from manifest rather than recomputed), and
deterministic stage/context identity.  Human messages, tracebacks, memory
addresses, absolute paths, and incidental exception formatting are excluded.
Same code with materially different evidence is not the same failure result.

Category B is manifest-establishment failure: mandatory Tier-1 identity cannot
be established, no valid manifest fingerprint may be invented, and it is not a
completed-manifest reproducible economic result or cacheable result.

Category C is operational/infrastructure failure (for example crash, OOM,
external interruption, filesystem/runtime failure) and remains operational
provenance unless a future explicit deterministic-failure contract promotes a
specific class.  Raw exception equality is never reproducibility proof.  Only
a successful result or Category-A failure is cacheable under a valid
manifest-rooted, versioned cache contract.

### 28.9 Preserved Slice 12 preflight facts and implementation guards

The pandas/Parquet path can preserve nanosecond timestamps; no existing
universal microsecond truncation policy exists.  Native Python `datetime` is
microsecond-limited, so it cannot be the intermediary for pandas nanosecond
evidence.  Existing reusable identities include `InstrumentIdentity`,
`StreamKey`, `BacktestRunContext` fields, `LedgerEventKey`/
`TradeRecord.trade_id`, cost schedule/evidence identities,
`MetricSummary.evidence_id`, `ValidationRunEvidence.validation_identity`, and
the existing deterministic SHA-256-derived local `random.Random` seed
primitives.  Existing execution/slippage is deterministic; Slice 12 must not
invent stochastic fill/slippage behavior.  No physical backtest/replay attempt
ID exists today; a future one is operational only.

The required implementation preflight found no non-Python files below
`engine/` or `strategies/` other than generated bytecode, and no authoritative
runtime code consumes `CONFIG_SCHEMA.md`; therefore the
SourceIdentityPolicy/v1 non-Python allowlist is empty at this checkpoint.
This must be rechecked at certification if runtime resources are added.

The direct non-stdlib authoritative runtime dependency visible in current
source is `pandas`; its `read_parquet` use makes the actual Parquet engine an
authoritative runtime-selectable backend that DependencyIdentity/v1 must
identify explicitly.  `zoneinfo` is standard-library, but its timezone-data
identity is Tier 1 where calendar/timezone semantics affect economics.  There
is currently no dependency declaration or lock metadata in the repository;
Slice 12 must add those governed artifacts before reproducibility
certification.  `CONFIG_SCHEMA.md` is governance/documentation, not runtime
configuration parsing, and is excluded from SourceIdentity.

Existing stable machine-readable candidates for Category-A evidence include
existing `ExecutionOutcome`, `AccountingOutcome`, `OrderLifecycleState`,
`MetricStatus`, `ValidationStatus`, and `RandomizedAnalysisKind` contracts
when an approved Slice 12 failure schema explicitly uses them.  Existing
free-form reasons and raw exceptions are not automatically Category-A codes.

### 28.10 Slice 12 readiness

The D1–D7 architecture is owner-locked and introduces no conflict with the
existing frozen requirements or verified Slice 1–11 contracts.  Slice 12 is
**IMPLEMENTATION_READY**, subject to the mandatory implementation guards in
this section: create the canonical codec and manifest/result/failure contracts,
establish the declared/approved/detected dependency boundaries, explicitly
identify the actual Parquet backend at runtime, and preserve the acyclic DAG.
These are implementation obligations, not unresolved owner decisions.

---

## 29. Owner-Locked Slice 13 Reporting / Export Architecture (v1)

Slice 13 is a reporting/serialization boundary over existing authoritative
Slice 1–12 evidence. It must not recompute P&L, execution, accounting, costs,
metrics, validation, or reproducibility semantics, and must not alter any
upstream economic behavior.

### 29.1 R1 — canonical machine-readable export

Versioned JSON is the sole canonical Slice 13 v1 machine-readable format.
Export reproducibility is deterministic semantic content and authoritative
ordering, not byte-identical JSON bytes. Decimal values use the exact D4
canonical fixed-point string representation; timestamps use D4 UTC ISO-8601
text with exactly nine fractional nanosecond digits and `Z`. Decimal JSON
numbers and numeric epoch timestamps are prohibited. The public JSON schema
may reuse D4 value semantics but must not expose the internal fingerprint codec
as its wire format.

### 29.2 R2 — immutable terminal result envelope

`StructuredBacktestResult` is one immutable, versioned envelope with exactly
one terminal `result_kind`: `SUCCESS`, `CATEGORY_A`, `CATEGORY_B`, or
`CATEGORY_C`. Cross-variant fields are invalid and fail closed. A no-trade
`SUCCESS` is valid where upstream evidence permits it. Embedded or referenced
evidence remains owned by its existing Slice 1–12 authority.

### 29.3 R3 — public-safe provenance

Canonical JSON is public-safe by schema allowlist, never post-hoc scrubbing.
It excludes paths, usernames, host/device identifiers, credentials, keys,
tokens, passwords, private data locations, environment secrets, raw exception
text, traces, and machine-local diagnostics. Allowed public provenance is
limited to approved identities, versions, runtime/environment conformance, and
strategy/validation evidence. Every reference-only field independently passes
this allowlist.

Operational `attempt_id` is included exactly when an upstream non-empty,
public-safe identifier is available; it has no logical/economic meaning.
When seeded randomized analysis applies, the public report includes the exact
root seed textual value, seed-derivation-policy identity, authoritative result
evidence, and the exact derived seed where existing authority exposes it. The
report is never a D6 replay input.

### 29.4 R4/R5 — publication and deferred presentations

Slice 13 v1 constructs one complete in-memory result and publishes one complete
canonical JSON document. Streaming, NDJSON, pagination, chunks, split-file
canonical export, CSV, Markdown, HTML, PDF, and other presentation formats are
deferred. Resource failures are operational export failures only and do not
alter logical identities. Future public presentation derives exclusively from
canonical public-safe JSON unless a separate internal-diagnostic schema is
approved; future CSV is non-authoritative unless a separate lossless contract
is frozen.

Publication is all-or-nothing: stage on the target filesystem, validate, then
atomically rename/replace using the strongest safe supported semantics. No
copy-then-delete fallback is permitted. Partial/truncated output is never
canonical; temporary artifacts are explicitly non-canonical.

### 29.5 R6 — closed schema and strict JSON

The opaque public schema identifier is `sentinelx-report/v1`. It is closed:
any field addition/removal/rename/type/requiredness/semantic change requires a
new schema identifier. Unknown versions or fields, malformed/truncated JSON,
missing required fields, invalid types, forbidden variant fields, or silent
defaults fail closed. Readers and migrations are deferred. A future internal
diagnostic schema must have a distinct identity.

JSON is UTF-8 without BOM, uses explicit schema-defined object ordering, makes
no implicit Unicode normalization, preserves valid authoritative Unicode
scalars, and rejects invalid/unpaired surrogate content rather than replacing
it. It is strict RFC 8259: NaN, Infinity, -Infinity, locale conversion, and
other non-standard numeric literals are prohibited.

Required empty collections encode as `[]`; an inapplicable conditional section
is omitted; `null` appears only where its upstream authority defines a
present-but-absent value. No null, empty object/string, zero, or dummy hash may
stand in for required evidence. Explicit upstream statuses, including `PASS`,
`FAIL`, `INVALID`, `INSUFFICIENT_DATA`, and `NOT_APPLICABLE`, are preserved.

### 29.6 V1-D1 — top-level schema

Top-level fields are exactly `schema_version`, `result_kind`,
`report_generated_at`, `provenance`, and `payload`. `report_generated_at` is a
required operational D4 UTC nanosecond timestamp and is excluded from all
logical/economic identity. `provenance.attempt_id` follows §29.3.

### 29.7 V1-D2/D3 — success and failure payloads

`SUCCESS` is a self-contained public projection. It includes the applicable
manifest/result identities; required strategy, parameter, data, configuration,
validation, runtime/dependency-conformance identities; and authoritative
trade, execution/fill, portfolio/equity, cost, metric, validation, and
applicable randomized-analysis evidence. If an evidence family participates in
result-fingerprint child composition, it is embedded at evidence-defining
granularity rather than represented by its fingerprint alone.

`CATEGORY_A` includes valid manifest and failure-result fingerprints, stable
machine-readable failure schema/code/stage, manifest-owned governing-policy
identity by reference, and failure-result-defining evidence. `CATEGORY_B`
contains no manifest/result/failure-result fingerprint and exposes only minimum
public-safe pre-manifest classification/evidence. `CATEGORY_C` is operational;
it may associate an already-valid manifest for audit but has no successful or
failure-result fingerprint and is not replay-eligible merely because a
manifest exists.

The Slice 12 D6 separation remains mandatory: manifest policy/input identities
and result outcome/evidence identities are separate namespaces; mismatch
localization recurses through result child evidence. Category-A is an
authoritative D1 reproducible-result variant. Category-B is not cacheable under
manifest-rooted caching. Failure governing-policy identity references its
manifest-owned Tier-1 identity and is never independently re-derived.

### 29.8 V1-D4 — randomized analysis

In `SUCCESS`, randomized analysis appears under the success payload; for
`CATEGORY_A` it appears under reproducibility evidence. If not applicable it
is omitted, never null or defaulted. Reporting neither recomputes nor reseeds
analysis.

### 29.9 R7/V1-D7/D8 — path, naming, collision, and idempotency

Filename/path is operational publication metadata, never logical/economic
identity. Unsafe, traversing, inaccessible, non-writable, missing-parent (by
default), invalid-name, locked, permission, disk, or unsafe-publication
destinations fail export without changing result identity. Parent directories
are not silently created unless an explicit caller policy permits it.

Default names are `sentinelx-report-success-<manifest12>-<result12>.json` and
`sentinelx-report-category-a-<manifest12>-<failure12>.json`, where each short
fingerprint is 12 lowercase SHA-256 hex characters and display-only.
Category-B/Category-C names use public-safe `attempt_id`, otherwise a
filesystem-safe `report_generated_at` token; they never fabricate a
fingerprint.

Before replacement, an existing artifact is strict-parsed and schema-validated
and its full identities are compared. Distinct full identities are a collision.
For Success/Category-A, same full identities require authoritative
payload/evidence equivalence excluding only `report_generated_at` and
`provenance.attempt_id`; equivalent content is `ALREADY_PUBLISHED` and is not
rewritten, while inconsistent content fails closed. Category-B and every
Category-C collision fails closed.

### 29.10 V1-D9/D10 — writer validation and concurrency

There is no separate canonical report-content fingerprint/checksum in v1;
manifest/result/failure identities remain authoritative. Before publication,
the writer validates the staged bytes for UTF-8, strict JSON,
`sentinelx-report/v1`, variant exclusivity, required/unknown fields, Decimal
and timestamp encoding, R3 allowlisting, authoritative ordering, and intended
identity/content consistency. This is writer-owned publication validation, not
a general import/migration reader.

Every staging path has an explicit non-canonical marker and a unique
per-export-attempt token; concurrent writers never share it. Stale staging
material is removed only where writer ownership and inactivity are verifiable;
the writer never broadly deletes arbitrary temporary files. A crash before
publish may leave only non-canonical staging material; after atomic rename the
canonical artifact is complete.

### 29.11 Slice 13 readiness

The R1–R7 and V1-D1–V1-D10 decisions introduce no Slice 1–12 contract or
identity-DAG conflict. Slice 13 is implementation-ready under this section.

---

## 30. Owner-Locked Slice 14 Decision 1 — Multi-Instrument Strategy Data Contract

### 30.1 Reconciled strategy-data boundary

The timeframe-keyed strategy-data shape in Architecture Rule 3 remains a
backward-compatible single-instrument convenience only. It may be used when
exactly one authoritative instrument is in scope and the timeframe key is
therefore unambiguous.

For a strategy subscribed to more than one authoritative instrument,
timeframe-only keys are insufficient and must not be used as the authoritative
delivery shape. Slice 14 orchestration must reuse the existing Slice 9
instrument-aware `MarketDataView` and `StreamKey` contracts. `StreamKey`,
composed of `InstrumentIdentity` and timeframe, remains the sole authoritative
market-stream identity; no parallel instrument tuple, duplicate data view, or
second market-data truth may be introduced.

### 30.2 Ambiguity and compatibility

If a multi-instrument strategy requests or receives evidence through a
timeframe-only shape that cannot unambiguously identify its instrument, the
orchestration boundary must reject/fail closed. It must never infer an
instrument from a timeframe, symbol display text, map iteration order, or
other incidental ordering.

This reconciliation does not require a breaking change to existing
single-instrument strategy contracts and does not authorize ORB implementation,
resampling, Risk, Paper, Live, or any Slice 1–13 economic-semantic change.

### 30.3 Reproducibility

Slice 12 D3/D4 market-data identities remain unchanged. The existing
`InstrumentIdentity` plus timeframe identity, completed-bar availability, and
canonical stream/snapshot fingerprinting remain authoritative. No new
fingerprint architecture is required by this reconciliation.

### 30.4 Slice 14 readiness effect

This decision resolves only the Rule 3 / Slice 9 multi-instrument data-shape
contradiction. Slice 14 must still obtain every separate required owner
decision before implementation; it must not infer a signal-to-order policy or
same-timestamp capital-allocation behavior from this decision.

### 30.5 Owner-Locked Decision 2 — Slice 14 signal-to-order policy identity

Slice 14 orchestration may use an explicit, deterministic, configuration-owned
signal-to-order policy to translate an actionable neutral `SignalIntent` into
the existing immutable `OrderRequest` boundary. The policy must declare every
economically relevant translation input, including its permitted action/order
form, Time In Force, and deterministic configured quantity mechanism; the
strategy's opaque `Signal.metadata` must not become load-bearing for any of
those inputs.

The quantity mechanism used solely to prove Slice 14 end-to-end orchestration
is a temporary integration/test-fixture policy and must carry its own explicit
versioned identity: `sentinelx-slice14-integration-quantity-policy/v1`. It is
not a production Risk Management sizing/allocation policy and must not be
silently reused as one. When production Risk Management is introduced, its
sizing/allocation policy must have a separately explicit versioned Tier-1
policy identity and its own manifest/replay binding.

The complete Slice 14 signal-to-order policy, including the temporary quantity
policy identity wherever it affects economic behavior, is Tier-1
authoritative. It must bind into manifest execution semantics and the existing
D6 replay comparison; a changed policy is a changed logical run. This decision
does not change `Signal`, `SignalIntent`, `OrderRequest`, Portfolio, or
execution contracts, and does not introduce Risk Management behavior.

### 30.6 Owner-Locked Decision 3 — unresolved concurrent capital competition

When same-timestamp entry intents compete for shared capital and no approved
deterministic allocation/priority policy is present, Slice 14 orchestration
must fail closed as a post-manifest `CATEGORY_A` deterministic structured
failure with stable machine-readable failure code
`AMBIGUOUS_CONCURRENT_CAPITAL_COMPETITION`. It must not choose by event order,
symbol order, dictionary order, confidence, or any other incidental property.

The Category-A failure has a stable failure stage and governing policy
identity/reference, retains the established manifest association, and uses the
existing D7 Category-A failure-result composition. Its authoritative failure
evidence must identify the specific competing entry intents/signals and their
relevant source/provenance identities in a canonical order. Consequently,
different competing-intent evidence produces a different authoritative
failure-result fingerprint even when the stable failure code is unchanged.
Raw exception text, stack traces, and machine-local diagnostics are excluded
from authoritative failure identity and public reporting evidence.

This is not Category B or Category C: the manifest is already valid and the
competition is deterministically identified during orchestration. It does not
authorize capital allocation, Risk Management, broker behavior, or a change to
existing economic semantics.

### 30.7 Slice 14 decision readiness

Decisions 1–3 reconcile the discovered Slice 14 orchestration boundaries
without reopening any locked Slice 1–13 contract. Slice 14 is ready for its
separately authorized implementation plan, subject to retaining all stated
fail-closed, Tier-1, provenance, and deferred-scope boundaries.

## 31. Owner-Locked Slice 15 P1 Repairs

### 31.1 Full market-event identity

Every event accepted by multi-instrument coordinator or orchestration logic
must bind through the existing `InstrumentIdentity` plus timeframe `StreamKey`.
`BoundBarEvent` is the nonbreaking canonical carrier for that binding. Raw
`BarEvent` compatibility is limited to flows whose declared streams have one
unambiguous full `InstrumentIdentity`; after resolution both paths use the
same `StreamKey` and existing D3/D4 market-data fingerprinting. Symbol plus
timeframe is never an alternative authoritative identity path. Wrong,
ambiguous, cross-market, cross-segment, and derivative-contract identity
evidence fails closed.

### 31.2 Rule 7 orchestration identity

The authoritative Rule 7 audit/fallback identity in backtest orchestration is
`StrategyDataRequirements.strategy_id`. Orchestration invokes the frozen
`safe_generate_signal(..., "backtest")` boundary through an internal adapter;
an optional strategy-object `id` must equal that requirements identity or the
binding fails closed. Existing audited HOLD fallback semantics are unchanged;
this decision creates neither live-halt behavior nor a new D7 taxonomy.

---

## 32. Owner-Approved Reconciliation for Combined P1 Repairs

This owner-approved section reconciles the previously deferred P1-3 and P1-5
boundaries for the separately authorized combined repair.  It does not reopen
the verified Slice 1–15 contracts, authorize Risk, Paper, Live, broker, FX,
or any new economic formula, or change the authoritative gross-accounting
truth.

### 32.1 P1-3 — protective quantity after a position reduction

After an accepted partial reduction, every active protection on that exact
strategy-owned `PositionKey` must be deterministically reconciled downward so
that its protected quantity is never greater than the remaining owned
quantity.  The reconciliation is limited to that exact key: it must never
resize, cancel, aggregate, or otherwise affect protection belonging to another
strategy, strategy version, or instrument identity.

The existing Stop-Loss, Target, Trailing Stop, and OCO semantics remain
unchanged.  In particular, reconciliation must not make protection
retroactively eligible within the same bar and must preserve the existing
conservative no-look-ahead and same-bar ambiguity rules.  A complete close
cancels/removes all protection for its exact `PositionKey` as already required.

A scale-in never automatically increases an existing protection quantity.  An
upward resize remains unapproved and must fail closed or require a later
explicit policy; this decision authorizes only the deterministic downward
reconciliation required to prevent stale protection from exceeding owned
quantity.  This supersedes only the prior statement that automatic resizing
after pyramiding/scaling was unapproved and unimplemented.

### 32.2 P1-5 — cost-adjusted cash/equity orchestration projection

This section activates the separately approved boundary anticipated by §24.1.
Slice 6 `PortfolioAccount` remains the sole authority for gross cash, gross
equity, positions, and realized/unrealized P&L.  Slice 8 `CostAssessment`
remains the sole authority for calculation, provenance, schedule selection,
and identity of recognized transaction costs.  The `TradeLedger` remains
unchanged and gross-only.

The combined repair must introduce a separate authoritative cost-adjusted
orchestration projection derived only from immutable gross accounting evidence
and immutable recognized `CostAssessment` evidence.  It must not mutate,
reinterpret, or replace the Slice 6 gross truth; must not duplicate cost
formulas, schedule selection, cost assessment, execution, or slippage; and
must reuse the established immutable evidence identities.  A schema version
bump is allowed only where genuinely unavoidable for a new public immutable
contract.

Cost timing is exact: recognized entry-leg cost reduces cost-adjusted buying
power at entry; a recognized partial-exit cost reduces it at that partial exit;
and a recognized final-exit cost reduces it at final exit.  Gross cash remains
the unmodified Slice 6 value.  An otherwise valid order may therefore be
rejected when gross cash is sufficient but cost-adjusted buying power is not.
The projection must never fabricate future cost assessments; rejected,
unfilled, expired, invalid, or accounting-rejected activity has no recognized
transaction cost.  Where a net result is exposed, it remains exactly
`gross - recognized cost` under the existing Decimal/monetary policy.

The projection, its governing policy identity where required, and the
underlying existing assessment/gross-evidence identities are authoritative
where they affect economic orchestration.  They bind through the established
manifest/replay architecture without introducing a parallel identity DAG.  The
approval supersedes the previously deferred account-level cost-adjusted
cash/equity integration only for this P1-5 repair.

### 32.3 P1-4 — preserved locked decision

The previously locked P1-4 contract remains unchanged.  This reconciliation
does not alter its boundary, evidence, ordering, lifecycle, or failure
semantics.

### 32.4 Reconciliation result

The P1-3 downward-only protection rule and P1-5 separate cost-adjusted
projection are internally consistent with §24.1, the Slice 6 gross-accounting
authority, Slice 8 assessment authority, the existing `PositionKey` ownership
model, and Slice 12 Tier-1/D6/D7 reproducibility rules.  No additional owner
decision remains for P1-3, P1-4, or P1-5 before the separately authorized
combined repair.

---

## 33. Owner-Approved P1-5 Pre-Closure Per-Leg Cost Evidence

### 33.1 Reconciled authority boundary

The existing completed-trade `CostAssessment` remains authoritative for
aggregate cost evidence of a completed `TradeRecord`.  This section supersedes
only the former limitation that authoritative cost evidence could exist only
after a completed `TradeRecord` was created.  Gross `PortfolioAccount`
accounting and gross `TradeRecord`/`TradeLeg` authority remain unchanged.

### 33.2 `CostLegAssessment/v1`

P1-5 is authorized to introduce the immutable, explicitly versioned
`CostLegAssessment/v1` contract.  It is distinct from a completed-trade
`CostAssessment` and has its own deterministic canonical identity under the
existing codec/fingerprint composition rules; it is not a parallel cost
identity architecture.

A `CostLegAssessment/v1` may be created only from one accepted,
execution-backed economic leg and its one applicable authoritative cost
schedule.  Its canonical evidence must preserve the accepted accounting and
execution/leg provenance, deterministic event identity where available,
account and concrete instrument identity, side, quantity, fill price,
execution timestamp, currency and monetary-precision evidence, schedule ID,
version, and fingerprint, component identity/calculation basis, and resulting
component and total cost amounts.  The existing accepted-fill evidence remains
authoritative for slippage; slippage already represented in that fill price
must not be charged again.

Rejected, unfilled, cancelled, expired, invalid, or accounting-rejected
activity must never produce a `CostLegAssessment/v1`.  The same immutable
accepted-leg evidence and same immutable schedule must reproduce the same
assessment identity and amount.  A collision under that deterministic identity
with different authoritative evidence must reject/fail closed.

### 33.3 Recognition and completed-trade composition

An entry-leg assessment becomes economically recognized at that accepted entry
execution; a partial-exit/reduction assessment becomes recognized at that
accepted reduction execution; and a final-exit assessment becomes recognized
at that accepted final-close execution.  These recognized per-leg assessments
are the authoritative cost evidence consumed by the P1-5 separate
cost-adjusted cash/equity/buying-power projection approved in §32.2.

When the position lifecycle completes, the completed-trade `CostAssessment`
must compose/aggregate the already-authoritative applicable
`CostLegAssessment/v1` evidence.  It must not recalculate the same leg costs
from scratch, create a second truth, or double charge.  The completed-trade
aggregate remains derived aggregate evidence; it does not replace the
pre-closure recognition timing of its constituent leg assessments.

### 33.4 Reproducibility and external schemas

Manifest-side cost-policy identity remains Tier-1 input/cause identity.
`CostLegAssessment/v1` and completed-trade `CostAssessment` are result-side
outcome/effect evidence and participate in the existing cost/result/replay
evidence hierarchy.  Existing legal cost-evidence slots in
`SuccessfulResult`/authoritative-result composition and public reporting must
be reused where sufficient.  `ReproducibilityManifest`, successful-result,
and `sentinelx-report` schema versions are not automatically bumped; only an
affected closed external schema may receive a versioned bump when a genuinely
new externally authoritative structural field cannot be represented legally.

### 33.5 Scope guard and readiness

This decision authorizes no Risk Management, Paper/Live, broker
reconciliation, margin, leverage, FX, unrelated cost model, or gross-accounting
formula change.  It resolves the P1-5 pre-closure evidence contradiction; no
owner-decision blocker remains for the separately authorized P1-3/P1-4/P1-5
implementation.

---

## 34. Owner-Locked P1-4 Authoritative Regime Policy

### 34.1 Taxonomy, status, and `RegimePolicy/v1`

Frozen requirement Q36 requires regime tagging.  For the P1-4 repair,
`RegimePolicy/v1` is the authoritative Tier-1 policy identity.  Its taxonomy
contains exactly `TRENDING`, `SIDEWAYS`, and `VOLATILE`.  `UNCLASSIFIED_WARMUP`
is not a fourth taxonomy member: regime evidence instead has the separate
status `CLASSIFIED` or `UNCLASSIFIED_WARMUP`.  `CLASSIFIED` requires exactly one
taxonomy value; `UNCLASSIFIED_WARMUP` requires that the taxonomy value be
absent.

The policy uses Wilder ADX(14), ATR(14), normalized volatility `ATR(14) /
Close`, and a 100 eligible-real-completed-observation volatility baseline.
The volatile threshold is the explicitly pinned nearest-rank 80th percentile,
not a library-default percentile.  Classification precedence is: `VOLATILE`
when normalized ATR is at least that threshold; otherwise `TRENDING` when ADX
is at least 25; otherwise `SIDEWAYS`.

### 34.2 Readiness and evidence

The classifier is authoritative only after ADX/ATR readiness and the full
100 eligible real completed-bar baseline.  Before that point it emits
`UNCLASSIFIED_WARMUP` with no taxonomy value; any trade remains economically
valid.  The effective regime warm-up is therefore 100 eligible real completed
bars.

Regime evidence is calculated independently for each authoritative
`InstrumentIdentity` plus timeframe stream.  Only legally available completed
real bars contribute; synthetic bars are not fresh observations, and future or
incomplete evidence is prohibited.  The one authoritative regime component
updates after each eligible completed real bar.

### 34.3 Entry-time snapshot and single owner

Each entry uses the latest legally available completed regime immediately
before its actual fill.  It must not use incomplete fill-bar OHLC, future
evidence, or an implicitly assumed signal-bar regime.  The same rule applies
to delayed LIMIT/STOP fills and is part of `RegimePolicy/v1` identity.

Metrics, validation, reproducibility, replay, and reporting consume the
authoritative regime evidence; none may independently recompute it.  Reporting
must reconcile `TRENDING + SIDEWAYS + VOLATILE + UNCLASSIFIED_WARMUP` status
bucket exactly to the applicable overall trade total.  The warm-up bucket is a
reporting/status bucket only.

### 34.4 Manifest, result, report, and replay versioning

`ReproducibilityManifest/v1` is closed.  `ReproducibilityManifest/v2` adds the
Tier-1 `regime_policy_identity` input only.  It must not include regime
evidence, its fingerprint, or post-run outcomes.

`AuthoritativeResultIdentity/v1` is closed.  Its v2 composition adds the
authoritative `regime_evidence_fingerprint` child while preserving the separate
core economic trade/fill evidence family.

`sentinelx-report/v1` is closed.  `sentinelx-report/v2` must expose
authoritative `regime_evidence`, `regime_evidence_fingerprint`, regime status,
the taxonomy value only when classified, and reconciliation/bucket semantics.
There is no in-place extension of v1; unknown or unsupported schema versions
retain existing closed-schema rejection behavior.

Regime evidence participates in authoritative result/replay verification.
When core economic evidence matches but regime evidence differs, the overall
result is `REPLAY_MISMATCH`; hierarchical localization must preserve the core
economic family as matching and the regime family as mismatching.  Missing
required authoritative regime evidence can never produce `REPLAY_MATCH`.

### 34.5 Scope and progress reconciliation

This section authorizes only P1-4 Backtest Engine regime tagging.  It does not
authorize Risk, strategy redesign, Paper/Live, broker APIs, UI, production
resampling, unrelated indicators, or unrelated schema redesign.  The former
progress statement that regime tagging is deferred is superseded as current
authority by this owner lock; it remains unimplemented and cannot be marked
complete until implementation and tests pass.

---

## 35. Owner-Locked P1-01/P1-02 Import Evidence and Instrument Identity

### 35.1 P1-01 — authoritative importer `run_id`

An importer `run_id` is one globally unique authoritative logical import-run
identity. Reuse of an already committed `run_id` is prohibited and must fail
closed deterministically. A reused identifier must not overwrite, replace,
truncate, reinterpret, or otherwise destroy the original report/evidence; the
original report bytes remain preserved.

Report publication must retain the P0-01 safe-path boundary and create a
complete JSON temporary artifact, validate/flush it as required, then publish
only when the destination does not already represent a committed authoritative
run. Atomic replacement is not authorized for `run_id` reuse. A failed second
attempt preserves the original report unchanged.

Per-source labels such as `{run_id}-{index}` are child/source-artifact labels,
not separate authoritative logical run identities. They remain associated with
the one parent `run_id`; this decision does not authorize a repeatable-label or
report-version-addressing scheme.

### 35.2 P1-02 — `InstrumentIdentityCasePolicy/v1`

New authoritative identity evidence uses `InstrumentIdentityCasePolicy/v1`.
At `InstrumentIdentity` construction only, canonicalize case and no other
identity semantics:

| Field | Canonical representation |
| --- | --- |
| `market` | lowercase |
| `segment` | lowercase |
| `instrument` | uppercase |
| `underlying` | uppercase when present |
| `option_type` | uppercase when present; valid option values remain `CE`/`PE` |
| `expiry` | unchanged semantic date |
| `strike` | unchanged semantic numeric value |

No alias mapping, symbol rewrite, internal-character removal, expiry change,
strike rounding, broker-symbol translation, or additional whitespace rewrite
is authorized. Genuine distinctions across every identity field remain
authoritative; this policy only collapses equivalent case representations.

After construction, equality, hashing, dictionary/set keys, `PositionKey`,
`StreamKey`, routing, fingerprints, and downstream comparisons use the stored
canonical identity. Downstream case transforms must not create an alternative
identity rule where canonical `InstrumentIdentity` evidence is already
available.

### 35.3 Historical compatibility and Tier-1 binding

Historic identity/fingerprint evidence remains interpreted under the policy
version that produced it. `InstrumentIdentityCasePolicy/v1` is a new explicit
identity-normalization policy for new runs, not an in-place reinterpretation of
old stored fingerprints.

The existing `MarketDataPolicy.normalization_identity` is the legal Tier-1
normalization-policy binding point. New case-canonicalized market-data runs
must bind `InstrumentIdentityCasePolicy/v1` there (or a composite
normalization identity that explicitly includes it), so a new run cannot be
confused with historical evidence produced under a different identity policy.
No `ReproducibilityManifest`, result, replay, or report schema bump is
authorized solely by this policy binding: the existing versioned
normalization-identity input already composes into market-data and manifest
identity.

### 35.4 Scope and readiness

These decisions supersede the prior P1-01 run-id reuse ambiguity and P1-02
split-case identity behavior. They authorize only the focused importer report
safety and `InstrumentIdentity` canonicalization repair with permanent tests.
They do not authorize unrelated importer versioning, changes to historical
evidence, economic formulas, Risk, Paper/Live, broker integration, or any
later P1 work.

---

## 36. Owner-Locked P1-03/P1-04 Regime Identity and Validation Applicability

### 36.1 P1-03 — full canonical option identity in regime evidence

`RegimeEvidence`, `EntryRegimeSnapshot`, aggregate regime-evidence
fingerprints, and every regime identity derived from a `StreamKey` must encode
the complete stored canonical `InstrumentIdentity`: `market`, `instrument`,
`segment`, `underlying`, `expiry`, `strike`, and `option_type`, plus the
`StreamKey` timeframe.  The existing canonical `InstrumentIdentity` /
`StreamKey` representation and canonical codec are the only legal source;
local recasing, symbol-only keys, `repr()` encodings, and a duplicate identity
codec are prohibited.  Case-only variants remain equivalent under
`InstrumentIdentityCasePolicy/v1`; every genuine option-contract distinction
must change the applicable regime identity.

### 36.2 P1-04 — exact OOS trade to entry-regime snapshot binding

For regime-aware validation, authoritative `OOSTradeEvidence` carries
`opening_entry_event_key: LedgerEventKey` sourced directly from
`TradeRecord.opening_event_key` and `account_id` sourced from the authoritative
trade/account scope.  `EntryRegimeSnapshot` also carries the authoritative
`account_id` from the exact account that accepted the opening economic event.
`ValidationRunEvidence` carries `account_id` as its validation account scope.

An entry-regime snapshot is applicable to a canonical OOS trade only when its
`entry_event_key` equals the trade's `opening_entry_event_key`, its
`account_id` equals both the trade and validation account scope, and every
already-required run/scope identity matches.  Timestamp-only, instrument-only,
strategy-only, and ordering-based matching are prohibited.  Exactly one
applicable snapshot is required for every regime-aware canonical OOS trade;
zero is a deterministic insufficient/unavailable failure and more than one is
duplicate/ambiguous evidence.  A matching `UNCLASSIFIED_WARMUP` snapshot with
no taxonomy value is valid evidence and must never be confused with absence.

Foreign-account or otherwise out-of-scope snapshots cannot satisfy a required
trade, are excluded from scoped validation-result identity, and do not change
that identity merely by being added or removed.

### 36.3 P1-04 — layered validation identity and causality

The pre-canonical validation-run identity binds validation inputs,
policies/configuration, split/provenance, and validation `account_id`; it must
not bind the raw unfiltered regime-snapshot bag.  It is the only identity used
to establish canonical OOS trade provenance.

After canonical OOS trades are built, the engine selects only their exact
applicable snapshots and creates `ScopedValidationResultIdentity/v1` from the
canonical OOS trade evidence, those selected snapshots, and other
authoritative validation-result evidence.  Equal canonical trades plus equal
applicable snapshots yield the same scoped identity; changing applicable
evidence changes it; foreign-only snapshots do not.

The causal direction is fixed:

`validation inputs/policies -> pre-canonical validation-run identity ->`
`canonical OOS trades -> exact account + opening-event applicability ->`
`scoped validation-result identity`.

No post-canonical regime evidence may feed backward into the pre-canonical
identity.

### 36.4 Version and schema boundary

The existing validation identity is not silently reinterpreted.  New
regime-aware evidence must use explicit v2 canonical evidence composition for
`EntryRegimeSnapshot`, `OOSTradeEvidence`, and `ValidationRunEvidence`, each
including the newly required account/entry fields.  The smallest new outcome
identity is `ScopedValidationResultIdentity/v1`.  Historical v1 evidence
remains historical evidence under its producing contract.  This decision does
not bump `ReproducibilityManifest`, `AuthoritativeResultIdentity`, or
`sentinelx-report`; they consume the produced upstream evidence through their
existing legal slots unless a later independently authorized closed-schema
change is required.

---

## 37. Owner-Locked P1-06 State-Store Path and Optimistic-Concurrency Contract

### 37.1 Scope, target identity, and path boundary

P1-06 hardens only the existing engine-managed JSON persistence boundary for
Rule 2 state keyed by `(strategy_id, interface_version)`.  `strategy_id` is
an authoritative path component and must be accepted only through the existing
P0-01 `require_safe_component()` / `path_within_root()` containment boundary;
unsafe text is rejected without sanitization or identity rewriting.  The
existing one-file-per-strategy layout remains authoritative: interface-version
entries share that strategy file.  This decision does not add broker
reconciliation, live/paper restart orchestration, database persistence,
distributed locking, or generic state merge semantics.

### 37.2 Conditional save contract and `EXPECTED_ABSENT`

State writes use optimistic concurrency with an explicit
`expected_prior_fingerprint` precondition.  A caller replacing an existing
`(strategy_id, interface_version)` entry must supply the fingerprint returned
with the authoritative previously loaded state entry.  Creation must supply
the explicit `EXPECTED_ABSENT` token.  Omission never means an unconditional
overwrite.

The state-store API must therefore expose an explicit immutable
state-entry/identity retrieval boundary and a conditional-save boundary.  The
existing value-only Rule 2 APIs must not be silently reinterpreted as allowing
an unconditional write; the smallest implementation-compatible versioned
extension must make the precondition explicit.  Historical JSON state is not
rewritten solely for this contract extension.

### 37.3 Commit algorithm and multi-interface preservation

For one strategy-state target, the engine validates the strategy path,
acquires the P0-02 target-specific OS-backed claim, and re-reads the latest
complete committed whole strategy document under that claim.  It locates the
requested interface-version entry, computes its canonical state-entry
fingerprint, and compares it with the explicit precondition.

An existing entry may be replaced only on an exact fingerprint match.  A new
entry may be created only when `EXPECTED_ABSENT` is supplied and that entry is
absent.  The caller's complete replacement applies only to the requested
interface-version entry in this freshly read document; all other entries are
preserved.  The complete document is then written through the existing temp
write, flush/fsync, and atomic-publication boundary before the claim is
released.

Consequently, competing writers to the same interface version cannot silently
overwrite newer state.  A stale caller must reload and explicitly derive a new
replacement before retrying.  Writers to different interface versions preserve
each other's already-committed entries because each writer re-reads the whole
document while holding the claim.  Last-writer-wins, automatic retry with a
stale replacement, and generic merge are prohibited.

### 37.4 Locking, deterministic failure, and fingerprint authority

The P0-02 OS-backed target claim provides cross-process serialization for the
exact state target; the optimistic token detects stale derivation.  Both are
required.  The lock file is inert identity material, not a stale-claim
authority, and exception/process termination release follows the existing
P0-02 local-filesystem model.

A failed precondition raises a deterministic programmatic
`STALE_STATE_WRITE` failure identity.  Raw exception prose is not authoritative
failure identity.

Each state-entry fingerprint binds the complete authoritative persisted state
for exactly one interface-version entry using `CanonicalCodec` and a dedicated
versioned state-entry schema.  It uses the existing typed canonical encoding,
including canonical timezone-aware timestamp handling; it must not use
`repr()`, noncanonical datetime serialization, or mutable post-fingerprint
data.  This is a local state-entry identity under the existing canonical
fingerprint hierarchy, not a parallel codec or manifest architecture.

### 37.5 Path-test and verification boundary

Path-safety regressions assert the stable exception type/programmatic
rejection contract, not unfrozen human-readable `PathSafetyError` prose.  They
must still prove no escaped state file is created.  P1-06 implementation must
add adversarial path, cross-process stale-write, multi-interface preservation,
crash/exception-release, atomic-read, corrupt-committed-state, and
multi-strategy-isolation coverage.  No P1-06 work is complete until those
tests and the required regressions pass.

---

## 38. Owner-Locked P1-07 Final Result and Report Finalization Ownership

### 38.1 One-way finalization boundary

`BacktestFinalizer/v1` is the one authoritative application boundary that
composes a completed `OrchestrationResult` and already-produced authoritative
analysis/result evidence into `SuccessfulResult` / `AuthoritativeResultIdentity`
and `StructuredBacktestResult` under `sentinelx-report/v2`.  The causal flow is
strictly one way:

`OrchestrationResult + FinalizationEvidenceBundle -> BacktestFinalizer/v1 ->`
`SuccessfulResult -> StructuredBacktestResult -> serializer -> replay comparison`.

`BacktestOrchestrator` remains the sole coordinator of market evidence,
strategy, orders, execution, gross accounting, ledger/trades, accepted-leg and
completed costs, regime runtime evidence, and `OrchestrationResult`.  It must
not calculate metrics, validation, report projections, or replay merely to
produce a report.  `ReportSerializer` remains a serializer/projection boundary
only and never becomes evidence producer.

### 38.2 Immutable finalization evidence

`FinalizationEvidenceBundle` is an immutable typed input contract.  It may
contain only already-authoritative typed evidence required by the existing
result/report contract: applicable `MetricSummary`/metric evidence,
validation result and `ScopedValidationResultIdentity/v1`, report-safe
strategy and parameter/configuration identity, and other already-frozen
analysis/result evidence.  It must not accept arbitrary caller-invented child
fingerprints in place of authoritative typed evidence when that evidence is
available.  Frozen Python value objects are appropriate; mutable shared
containers are not.

`BacktestFinalizer` validates and composes this evidence but never recalculates
fills, slippage, accounting, P&L, trade lifecycle, costs, regime, metrics, or
validation.  MetricsCalculator and ValidationEngine remain their respective
sole computation owners.  No reverse dependency from finalization/reporting to
orchestration or prior economic computation is permitted.

### 38.3 Canonical child identities and applicability

The finalizer must not invent economic child identities ad hoc.  Each family
has one canonical producer derived from its authoritative evidence:

- EXECUTION: authoritative `ExecutionResult` / execution evidence;
- PORTFOLIO_ACCOUNTING: authoritative `AccountingResult` / portfolio evidence;
- TRADE_LEDGER: authoritative ledger/trade evidence;
- COST: existing `CostLegAssessment` / `CostAssessment` and
  `cost_evidence_fingerprint`;
- REGIME: existing `RegimeEvidence` / `EntryRegimeSnapshot` and regime evidence
  fingerprint path;
- METRICS: the authoritative metrics evidence producer;
- VALIDATION: authoritative validation/scoped-validation result evidence when
  applicable.

Existing canonical producers must be reused.  Where authoritative evidence
exists but an applicable family producer does not, implementation may add the
smallest named, versioned **internal** evidence-family producer under the
existing `AuthoritativeResultIdentity` composition rules.  It must not create
a second top-level result hierarchy or change the public report schema.

Validation is included only when frozen applicability requires it.  Required
applicable validation/scoped identity, required regime evidence for a
regime-enabled run, and required cost evidence for a cost-applicable run must
be present, unique, consistent, correctly versioned, and in scope.  Missing,
duplicate, foreign, malformed, or fingerprint-inconsistent required evidence
fails closed and cannot emit SUCCESS.  Explicitly not-applicable validation
uses only established absence/not-applicable semantics; no validation success,
zero-cost fallback, gross fallback, fabricated warm-up status, or legacy
report downgrade is permitted.

### 38.4 Consolidation, replay, determinism, and versions

The prior helper path `successful_result(economic_evidence)` must not remain an
authoritative arbitrary-fingerprint assembly route.  Existing helpers,
including `report_payload_v2`, `success_payload_v2`, and
`success_payload_with_cost_evidence`, either delegate to the finalizer's
canonical producer/sub-producer or remain explicit non-authoritative
legacy/compatibility utilities.  There is one authoritative result assembly
path.

Replay compares the `SuccessfulResult` produced by that same finalization
path; it does not independently rebuild economic evidence.  Identical run and
bundle evidence match; changed regime or cost evidence localizes respectively
to REGIME or COST; changed execution/accounting/trade evidence localizes to
its appropriate family; missing required child evidence never matches.
Collection order is canonical.  The same `OrchestrationResult` and equivalent
authoritative bundle produce the same child identities, result identity,
structured result, and canonical serialized report.

No automatic bump to `ReproducibilityManifest/v2`,
`AuthoritativeResultIdentity/v2`, or `sentinelx-report/v2` is authorized.
`BacktestFinalizer/v1` and `FinalizationEvidenceBundle` are internal/application
composition contracts.  If implementation finds a closed public schema cannot
represent a required already-approved field, it must stop for an owner
decision before a schema change.

---

## 39. Owner-Locked P1-07 Validation Applicability Outcome Identity

### 39.1 `ValidationOutcomeIdentity/v1`

Validation is not required for every finalizable successful backtest.
`ValidationOutcomeIdentity/v1` is the closed, typed VALIDATION-family identity
used by final successful-result composition.  It has exactly one legal variant:

- **APPLICABLE:** `status = APPLICABLE`, the exact authoritative
  `ScopedValidationResultIdentity/v1`, and existing required run/scope
  consistency; no not-applicable reason field is permitted.
- **NOT_APPLICABLE:** `status = NOT_APPLICABLE`, stable
  `reason_code = VALIDATION_NOT_APPLICABLE` unless an already-frozen more
  specific applicability reason exists, authoritative run/result scope
  identity, and authoritative validation-applicability policy identity where
  existing contracts define one.  A scoped validation identity, fabricated
  PASS, result metrics, null, empty identity, or global magic constant is
  prohibited.

The wrapper is a composition/status identity only.  It does not run validation,
calculate validation metrics, or create another validation truth.

### 39.2 Canonical binding and failure boundary

Both variants use `CanonicalCodec`, a versioned schema, and typed canonical
values only; `repr()`, raw exception text, and arbitrary human-readable
diagnostics are excluded.  APPLICABLE binds the exact scoped validation result
identity and authoritative run/scope consistency.  NOT_APPLICABLE binds its
status, stable reason code, authoritative run/result scope identity, and
applicable policy identity, so it cannot be substituted across runs.

The states are distinct and exhaustive only when applicability is authoritatively
known:

- applicable plus valid scoped evidence produces APPLICABLE;
- explicitly not applicable under policy produces NOT_APPLICABLE;
- applicable but missing evidence is finalization failure/unverifiable; and
- unknown or ambiguous applicability fails closed.

Missing evidence must never be reclassified as NOT_APPLICABLE.

### 39.3 Result, report, replay, and version binding

`AuthoritativeResultIdentity/v2` / `SuccessfulResult` composes exactly one
VALIDATION child using `ValidationOutcomeIdentity/v1`, never a caller-invented
validation fingerprint.  `sentinelx-report/v2`'s existing required
`validation_identity` field carries that canonical SHA-256 identity.  The
closed report field accepts a lowercase SHA-256 identity and does not restrict
the concrete producer type; no report, manifest, or top-level-result schema
bump is required.

Replay compares this VALIDATION-family identity: equivalent N/A scope and
policy evidence matches; changed applicable evidence, APPLICABLE versus
NOT_APPLICABLE, changed N/A scope, or missing required applicable evidence
cannot silently match.  BacktestFinalizer determines the outcome only from
authoritative applicability evidence/policy; ValidationEngine remains the sole
owner of applicable validation computation.

---

## 40. Owner-Locked Validation Applicability Decision

### 40.1 `ValidationApplicabilityDecision/v1`

`ValidationApplicabilityDecision/v1` is the one immutable, typed policy result
that determines whether validation is required for a finalizable backtest run.
It has exactly two legal statuses: `REQUIRED` and `NOT_APPLICABLE`.  There is
no `UNKNOWN` success state, no `None`/missing decision meaning not applicable,
no caller boolean, and no inference from absence of validation evidence.  If a
decision cannot be produced or is ambiguous, finalization fails closed.

One dedicated validation-applicability policy producer owns this decision.
It derives it solely from the already-authoritative finalization run scope and
validation policy/configuration inputs: the exact `ReproducibilityManifest`
fingerprint and that manifest's existing `validation_policy_identity` (whose
Tier-1 configuration binding is already part of the manifest).  The
`BacktestFinalizer` does not calculate applicability, and `ValidationEngine`
continues to calculate validation only when that policy has made it applicable.

The versioned canonical identity uses `CanonicalCodec` and binds the schema,
the exact manifest/run-scope identity, the authoritative validation
applicability-policy identity/version, the status, and a stable reason code
only where the frozen policy defines one.  `repr()`, raw exception prose, and
arbitrary human diagnostics are excluded.

### 40.2 Finalization enforcement

`BacktestFinalizer` receives both `ValidationApplicabilityDecision/v1` and
`ValidationOutcomeIdentity/v1` as typed authoritative finalization evidence.
Their run scope must exactly match the `OrchestrationResult` manifest scope.

- With `REQUIRED`, the outcome must be `APPLICABLE` and carry the exact valid
  `ScopedValidationResultIdentity/v1` for that scope.  Missing outcome,
  missing scoped evidence, `NOT_APPLICABLE`, foreign scope, duplicate,
  malformed, or inconsistent evidence fails closed.
- With `NOT_APPLICABLE`, the outcome must be the canonical
  `NOT_APPLICABLE` variant with exact matching run scope, applicability policy
  identity, and stable N/A reason semantics.  An `APPLICABLE` outcome is
  rejected; no permission to run validation despite an N/A decision is
  authorized.

Thus `REQUIRED + valid validation`, `REQUIRED + missing validation`, explicit
`NOT_APPLICABLE`, missing applicability decision, and ambiguous applicability
decision are distinct states.  Missing evidence can never be relabelled as
not applicable.

### 40.3 Result, replay, and version binding

The VALIDATION result-family child composes the outcome identity that is
causally bound to the applicability decision.  Changing `REQUIRED` to
`NOT_APPLICABLE`, or the reverse, changes the VALIDATION-family/result
identity; equivalent run, decision, and applicable validation evidence are
deterministic.  Replay compares the produced identity and never independently
infers applicability.

`ValidationApplicabilityDecision/v1` is a new internal/result-policy identity.
It reuses the manifest's existing validation-policy/configuration identity
slot and the existing outcome/result/report validation-identity path.  It does
not by itself authorize a bump to `ReproducibilityManifest/v2`,
`AuthoritativeResultIdentity/v2`, or `sentinelx-report/v2`; implementation
must stop for an owner decision if a closed schema cannot carry the resulting
outcome identity through those existing legal slots.

---

## 41. Final Owner Lock — Validation Applicability Policy

### 41.1 `ValidationApplicabilityPolicy/v1`

`ValidationApplicabilityPolicy/v1` is the sole explicit, immutable Tier-1
semantic policy that determines validation applicability for a new
applicability-aware run.  It has exactly one required closed-enum field:
`mode`.

The only legal modes are `REQUIRED` and `NOT_APPLICABLE`.  `AUTO`,
`UNKNOWN`, `OPTIONAL`, caller-defined values, a missing mode, and `None` are
prohibited.  For `NOT_APPLICABLE`, the stable frozen authoritative reason code
is `VALIDATION_NOT_APPLICABLE`, unless an already-existing more-specific
frozen reason code applies.  Free-text reasons and dynamic/conditional
applicability rules are not authoritative in v1.

This deliberate v1 policy is explicit rather than inferred.  Richer future
walk-forward, sample-size, strategy, or market conditions require a separately
approved later policy version.

### 41.2 Tier-1 and manifest binding

The actual immutable policy object is part of authoritative Tier-1
application/run configuration.  Its `CanonicalCodec` fingerprint is exactly
the existing `ReproducibilityManifest.validation_policy_identity`; no new
manifest field is authorized.  `repr()`, raw object hashes, and
human-readable serialization are prohibited as policy identity.

The application/run-construction boundary must carry the actual structured
policy object to the finalization pipeline.  Policy semantics must never be
reconstructed from the fingerprint.  Before a decision is produced,
`fingerprint(actual_policy)` must exactly equal
`manifest.validation_policy_identity`; any mismatch fails closed.

`CONFIG_SCHEMA.md` currently has no closed validation-policy representation
that conflicts with this runtime policy contract.  Accordingly, no
configuration-schema, `ReproducibilityManifest/v2`,
`AuthoritativeResultIdentity/v2`, or `sentinelx-report/v2` change is
authorized by this lock.  If a future file-backed configuration boundary needs
to read this policy, its exact closed schema must be owner-approved before it
is added.

### 41.3 Sole producer and decision identity

`ValidationApplicabilityPolicyProducer/v1` is the sole producer of
`ValidationApplicabilityDecision/v1`.  It consumes the actual immutable
policy and authoritative manifest, verifies the binding in §41.2, and maps
`REQUIRED` only to `REQUIRED` and `NOT_APPLICABLE` only to
`NOT_APPLICABLE`.  No other subsystem may reinterpret the policy.

The decision uses `CanonicalCodec` and binds its schema/version, manifest
fingerprint/run scope, `validation_policy_identity`, status, and the stable
reason code only for `NOT_APPLICABLE`.  This decision remains the §40 typed
applicability result; §41 supersedes only §40.1's prior description that a
producer could derive semantics from an opaque manifest identity.

### 41.4 Finalizer and compatibility rules

`BacktestFinalizer` receives the policy-produced
`ValidationApplicabilityDecision/v1` together with
`ValidationOutcomeIdentity/v1`:

- `REQUIRED` permits only a valid, scope-bound `APPLICABLE` outcome.  Missing
  validation, a missing decision, or `NOT_APPLICABLE` fails closed.
- `NOT_APPLICABLE` permits only the canonical scope- and policy-bound
  `NOT_APPLICABLE` outcome.  An `APPLICABLE` outcome fails closed.

No caller boolean, flag, missing object, validation outcome, or report
argument can override the policy.  Legacy runs lacking this explicit policy
retain only their already-frozen legacy version path; new
applicability-aware runs have no implicit default and must provide the policy.

The following alternatives are explicitly rejected: caller boolean;
applicability inference from the policy fingerprint; inference of N/A from
missing validation; finalizer-owned inference; validation-always-required;
and dynamic conditional rules in v1.

---

## 42. Owner-Locked Full-Identity Historical Read Boundary

### 42.1 Additive exact-stream API

`HistoricalDataFeed.fetch_stream(stream: StreamKey)` is the one nonbreaking
exact-stream historical-read boundary.  The frozen legacy
`fetch(instrument, timeframe)` surface remains unchanged and may continue to
serve already-legal legacy single-instrument callers.  It must never be
silently reinterpreted as full-contract lookup.

All new V1/V2/V3 production historical-run paths that have an authoritative
`StreamKey` must use `fetch_stream()`.  An exact-stream read uses the complete
`StreamKey` identity: market, instrument, segment, underlying where
applicable, expiry where applicable, strike where applicable, option type
where applicable, and timeframe.  Symbol-only inference is prohibited.

### 42.2 One canonical storage-path authority

Exact-stream path resolution must reuse the importer canonical identity and
storage resolver, or a single shared resolver extracted from it.  Importer
writes and exact-stream reads therefore resolve the same full identity to the
same canonical dataset.  The reader must not build an independent path rule.

For futures and options, missing or wrong expiry, strike, CE/PE, underlying,
or other required identity evidence fails closed.  Two contracts sharing an
instrument and timeframe but differing in any identity-bearing contract field
must resolve to different canonical datasets.  The reader must never select a
nearest, same-symbol, or legacy fallback contract.

### 42.3 Production, compatibility, and versioning boundary

`fetch_stream()` is the authoritative input for new dataset adapters and
application-run services.  A requested `StreamKey` whose resolved canonical
identity/path does not exactly match fails closed, as do incomplete option
identity, ambiguous legacy lookup in an exact-stream path, and stored-path
mismatch.

This is an additive feed API extension only.  It does not authorize removal
or alteration of `fetch(instrument, timeframe)`, and does not itself require a
`ReproducibilityManifest`, result, report, or other public schema version
bump.  The existing `StreamKey` and `MarketDataSnapshot` identities remain
the single market-data truth.

---

## 43. Owner-Locked Market-Qualified Canonical Storage and Futures Identity

### 43.1 `StorageLayout/v2` is the exact-stream canonical layout

All **new** canonical importer writes and all new exact-stream reads use the
versioned market-qualified `StorageLayout/v2` layout.  `market` is a required
canonical path component and is never inferred from symbol, segment, or an
existing marketless path:

- index/spot: `data/parquet/{market}/{instrument}/{segment}/{timeframe}/data.parquet`
- futures: `data/parquet/{market}/{instrument}/{segment}/{expiry}/{timeframe}/data.parquet`
- options: `data/parquet/{market}/{instrument}/{segment}/{underlying}/{expiry}/{strike}/{option_type}/{timeframe}/data.parquet`

The options form retains `underlying` because it is an already frozen
identity-bearing component of the importer identity.  It is not optional in
an options path, and neither importer nor reader may collapse it into a
symbol-only alias.  Each layout component is the canonical representation
validated by the shared identity and path-safety boundary.

### 43.2 One full-identity authority, including futures

`CanonicalIdentity`, `InstrumentIdentity`, `StreamKey`, the shared canonical
storage resolver, importer routing, and `HistoricalDataFeed.fetch_stream()`
must represent and validate one identical contract identity.  No subsystem
may invent an alternate identity or a separate path rule.

For `segment == "futures"`, `InstrumentIdentity` requires a concrete
`expiry: date`.  Its `strike` and `option_type` must be `None`; the
underlying/instrument treatment must otherwise mirror `CanonicalIdentity`
exactly.  This is the additive reconciliation that lets a futures `StreamKey`
identify the exact contract required by `StorageLayout/v2`.

For `segment == "options"`, market, instrument, segment, underlying, expiry,
strike, option type, and timeframe are all exact identity evidence.  A
different market, expiry, strike, or CE/PE produces a different canonical
dataset.  Missing, malformed, or mismatched option evidence is never
normalized into another contract.

### 43.3 Legacy storage and migration boundary

Existing marketless canonical paths remain **legacy**.  They must not be
deleted, moved, overwritten, guessed, or silently reinterpreted.
`HistoricalDataFeed.fetch(instrument, timeframe)` retains its frozen legacy
behavior and may continue to access that legacy surface where already legal.

`HistoricalDataFeed.fetch_stream(stream)` is an exact `StorageLayout/v2`
operation only.  It never falls back to a marketless path or another contract
sharing the same symbol.  New V1/V2/V3 production historical-run paths must
use this exact-stream method whenever an authoritative `StreamKey` exists.

There is no automatic legacy-to-v2 identity migration.  A migration is legal
only when a trusted import manifest or other authoritative source proves the
complete identity required by `StorageLayout/v2`; otherwise the legacy data
remains untouched.  Migration tooling is separate work and is not authorized
by this decision.

### 43.4 Fail-closed and versioning rules

Exact-stream operations fail closed for missing market, incomplete or wrong
futures/options identity, wrong expiry/strike/CE/PE/underlying, a path that
does not correspond exactly to the requested `StreamKey`, a missing exact
dataset, or any ambiguous identity.  There is no symbol-only, nearest-match,
or legacy fallback in the exact-stream path.

This is an additive storage/identity and feed-boundary versioning decision. It
does not remove or reinterpret legacy `fetch(instrument, timeframe)` and does
not itself require a manifest, result, report, or other public schema bump.

---

## 44. Owner-Locked Step-3A Walk-Forward Execution / Selection Policy

These Step-3A-specific decisions refine the missing walk-forward
execution/orchestration policy layered on top of §27 and the existing Slice 12
D1–D7 foundation. They do not replace, weaken, or redefine that foundation:
D1 reproducibility, D4 canonical ordering/fingerprinting, D6 replay
verification, and D7 structured-failure/category rules remain authoritative.
No parallel validation, manifest, fingerprint, or failure architecture is
authorized by this section.

### 44.1 Per-window selection scope

Candidate selection is independent for every walk-forward window:

```text
training-only historical evidence
    -> candidate evaluation
    -> candidate selection
    -> frozen selected candidate/parameter fingerprint
    -> corresponding isolated OOS execution
```

A candidate selected for one window is not automatically selected for another.
OOS evidence from a current or future window must never affect candidate
generation, eligibility, scoring, ranking, tie-breaking, or selection. The
Step-3A orchestration boundary, not strategy code, owns selection.

### 44.2 Training candidate-selection policy

The selection policy is `MAXIMIZE_TRAINING_METRIC`. Its primary metric is
canonical **net Expectancy** from training-only completed-trade evidence under
the existing SentinelX metric definition.

A candidate with zero completed trades in its applicable training window is
`SELECTION_INELIGIBLE`, because canonical net Expectancy is undefined. A
candidate whose required selection-chain metric is undefined or non-finite
must not be silently compared; its treatment is explicit selection
ineligibility. No NaN, Infinity, implicit numeric sentinel, runtime-specific
ordering, or library-default non-finite comparison may participate in an
authoritative ranking.

Eligible candidates rank deterministically by:

1. highest canonical net Expectancy;
2. lowest canonical Max Drawdown;
3. lexicographically smallest canonical candidate fingerprint.

A zero-trade candidate must never gain an advantage from trivial zero drawdown.

If all candidates are selection-ineligible for a window, selection fails closed
as a post-manifest D7 Category-A deterministic structured failure with stable
code `WALK_FORWARD_NO_VALID_CANDIDATE`. It uses an explicit
candidate-selection failure stage; an existing stage may be reused only if it
exactly denotes candidate selection, otherwise the smallest additive
candidate-selection stage contract is required.

Its canonical evidence binds at minimum the walk-forward-window identity,
training-window identity, candidate-universe identity, ordered ineligible
candidate evidence, applicable training/metric-evidence identity, and
selection-policy identity. Ineligibility reasons are stable machine-readable
codes, never free text, and include as applicable:

- `ZERO_COMPLETED_TRADES`;
- `PRIMARY_METRIC_UNDEFINED`;
- `NON_FINITE_SELECTION_METRIC`;
- `MISSING_REQUIRED_TRAINING_EVIDENCE`.

Before composition, ineligible candidate entries sort lexicographically by
their own canonical candidate fingerprint. Candidate-generation/declaration
order, mappings, sets, worker completion, filesystem order, and library/runtime
order are prohibited. The machine-readable reason remains bound to its
candidate after sorting.

This evidence reuses D4 schema-versioned type-aware canonical encoding and D7
failure-result machinery, producing a `failure_result_fingerprint`. The same
manifest, training evidence, window, candidate universe/ineligibility evidence,
and policy must reproduce the same fingerprint through D6 replay. A materially
different window, candidate set, evidence, policy, or reason must not collapse
into the same authoritative failure identity. This is not an unclassified
generic validation error.

### 44.3 Training/OOS completed-bar visibility

For start-labelled bars, training/OOS market-data visibility and membership use
the authoritative completed-bar **availability time**, not merely the bar-start
timestamp. A bar may be consumed by training/candidate selection only when its
complete authoritative evidence is available before the applicable OOS
boundary under the existing `MarketDataCoordinator` / `MarketProfile`
availability contract. A bar whose completed-bar availability time is at or
after that OOS boundary is unavailable to training and candidate selection.

This decision preserves the existing `ValidationWindow`, embargo,
`validation_identity`, completed-bar/no-look-ahead, and exact historical-run
evidence identities. It defines evidence visibility at those existing
boundaries only.

---

## 45. Owner-Locked Step-3B Multi-Window Walk-Forward Orchestration Policy

These additive Step-3B decisions compose the authoritative Step-3A
`WalkForwardWindowExecutor` across multiple independent `ValidationWindow`
values. They preserve §27 and §44, including the per-window candidate
selection, training/OOS isolation, completed-bar availability, canonical OOS,
D4 canonical codec, D6 replay, and D7 structured-failure authorities. Step 3B
must not duplicate or redefine any of those per-window responsibilities, and
must not introduce a parallel manifest, fingerprint, or failure architecture.

### 45.1 Multi-window parameter-selection identity

`MultiWindowSelectionIdentity/v1` is an additive, versioned authoritative
identity for a multi-window walk-forward run. It binds each window's existing
`ParameterPlan`, `ParameterSelectionEvidence`, selected parameter fingerprint,
and training-evidence identity as a canonical ordered collection.

The canonical window schedule and selection-identity order is:

```text
(oos_start, window_id)
```

The ordered collection must retain the exact identity of its corresponding
`ValidationWindow`; duplicate window identities and any contradictory
per-window selection/provenance are invalid and fail closed. This identity is
an aggregate binding only: it must not flatten, replace, or imply one global
selected-parameter fingerprint. Each window's already-frozen single-window
`ParameterPlan` semantics remain unchanged, and a later window may select a
different candidate/parameter under its own training-only evidence.

### 45.2 Independent windows and partial-success handling

Step 3B invokes the Step-3A executor independently for each canonical window.
No candidate selection, strategy runtime, account/portfolio, position, order,
ledger, protection, cost, metric, OOS-trade, or candidate-eligibility state
from one window may become state for another window.

A deterministic per-window `WALK_FORWARD_NO_VALID_CANDIDATE` or
`INSUFFICIENT_DATA` result does not immediately abort later independent
windows. The aggregate retains that window's existing structured-failure
evidence unchanged, continues the remaining canonical schedule
deterministically, and retains successful windows' canonical OOS evidence for
audit, research, and replay. A failed or incomplete window must never be
relabelled as successful or eligible.

Retaining one or more successful windows does not alone establish promotion
eligibility. The applicable frozen complete-eligible-window requirement remains
authoritative.

### 45.3 Aggregate canonical Primary OOS status and identity

Where the applicable frozen minimum number of complete eligible OOS windows is
not achieved, the aggregate result is
`MULTI_WINDOW_INSUFFICIENT_COMPLETE_WINDOWS`, classified as
`INSUFFICIENT_DATA` / `NON_PROMOTABLE`. This status is distinct from a
corrupt-policy or corrupt-evidence result and does not erase the preserved
per-window D7 structured failures or successful OOS evidence.

The aggregate is invalid and fails closed for duplicate window identities,
overlapping Promotion OOS intervals, corrupt provenance, contradictory
identities, invalid canonical aggregation, or any attempt to admit relabelled
non-OOS evidence. Those conditions must not be converted to insufficient data.

The authoritative multi-window aggregate binds, at minimum:

- the complete canonically ordered window schedule;
- successful per-window result identities;
- failed per-window structured-failure identities;
- the `MultiWindowSelectionIdentity/v1` ordered per-window selection
  identities;
- aggregate `CanonicalPrimaryOOS` evidence, retaining each trade's window and
  per-window parameter-selection provenance; and
- the applicable required and achieved complete-window counts.

The same authoritative schedule, per-window results, selection identities,
failure evidence, and canonical Primary OOS evidence must reproduce the same
aggregate identity through the existing D4/D6 machinery. Materially different
competing evidence must not collapse into one aggregate identity.

### 45.4 Step-3B scope boundary

Step 3B stops at deterministic multi-window composition and aggregate canonical
Primary OOS evidence. It does not run promotion gates, bootstrap, MC-1, MC-2,
sensitivity orchestration, multi-instrument aggregate economic episodes, Risk,
Paper/Live, broker APIs, UI, or ORB logic. Those remain governed by their
existing frozen boundaries and later approved work.

---

## 46. Owner-Locked Step-4A Bootstrap Evidence Policy

These Step-4A decisions are additive and layered on top of the existing D1-D7
foundation. They do not replace, weaken, or redefine D1 reproducibility, D4
canonical encoding/fingerprinting, D6 replay verification, or D7 structured
failure/category semantics. Step 4A creates no parallel fingerprint, replay,
or failure system.

### 46.1 `CIRCULAR_BLOCK_PERCENTILE_V1`

The sole Step-4A Bootstrap method is `CIRCULAR_BLOCK_PERCENTILE_V1`. It runs
once per instrument over that instrument's aggregate chronological
`CanonicalPrimaryOOS` evidence from successful eligible Promotion OOS windows.
It consumes only canonical `PRIMARY_OOS` evidence and excludes training,
selection, warm-up, sensitivity-neighbor, research-overlap, failed-window,
relabelled, and other noncanonical evidence.

Its only statistic is canonical net Expectancy: mean net realized P&L per
completed canonical OOS trade. No additional statistic is part of Step 4A.

Resampling uses circular, contiguous chronological blocks with explicit
`block_length`. `BootstrapPolicy` must explicitly provide method/version,
bootstrap sample count `B`, confidence level `c`, block length, and root seed.
There are no hidden defaults, automatic block-size estimation, IID trade
shuffling, BCa, Studentized, normal-approximation, or alternate
interpolation/quantile methods. Each replicate samples circular contiguous
blocks until it contains exactly the original canonical OOS sample size `N`.

Input must first pass through `CanonicalPrimaryOOS`; its resulting canonical
chronological order is authoritative. Raw caller order must not affect samples,
CI, evidence identity, or result fingerprint.

The derived Bootstrap seed reuses existing deterministic seed derivation and
binds root seed, `BOOTSTRAP` analysis kind, canonical Primary OOS source
identity, validation identity, `BootstrapPolicy` identity, and method identity.
No process-global or implicit runtime RNG state is permitted.

### 46.2 Locked finite-sample empirical percentile rule

For exactly `B` valid finite bootstrap Expectancy estimates, let:

```text
alpha = (1 - c) / 2
lower_index = floor(alpha * B)
upper_index = floor((1 - alpha) * B) - 1
```

After ascending canonical numeric sorting, each index is independently clamped
to `[0, B - 1]`. If the clamped lower index exceeds the clamped upper index,
the CI is undefined and the result is
`BOOTSTRAP_INSUFFICIENT_SAMPLES_FOR_CI`, classified `INSUFFICIENT_DATA`.
Indices must not be swapped, collapsed, interpolated, widened, or repaired by
changing `c` or `B`.

Otherwise, `ci_lower` and `ci_upper` are the estimates at those exact indices.
No generic/library percentile or quantile function is authoritative. This
discrete convention is part of `CIRCULAR_BLOCK_PERCENTILE_V1`; any change
requires a new Bootstrap-method version.

### 46.3 Sample sufficiency, finite values, and D7 failure

The frozen 200-completed-canonical-OOS-trade baseline remains unchanged. Under
200 trades, only a valid `CIRCULAR_BLOCK_PERCENTILE_V1` result with
`ci_lower > 0` qualifies for the Bootstrap exception. `ci_lower == 0` and
`ci_lower < 0` do not qualify, but a valid CI at or below zero is not invalid;
it simply does not satisfy the exception.

Zero canonical OOS trades, original sample size below required block length,
and `BOOTSTRAP_INSUFFICIENT_SAMPLES_FOR_CI` are legitimate
`INSUFFICIENT_DATA` outcomes. They must not be converted into invalid evidence
unless policy or evidence is itself invalid or contradictory.

Every canonical source observation and generated replicate Expectancy must be
finite. A non-finite value must never be sorted, dropped, regenerated,
substituted, or used to reduce `B`. The computation fails closed as the D7
Category-A deterministic structured failure
`BOOTSTRAP_NON_FINITE_EVIDENCE` at `BOOTSTRAP_ANALYSIS`.

For `SOURCE_OBSERVATION_NON_FINITE`, failure evidence binds at minimum the
canonical Primary OOS source identity, offending trade/observation identity,
canonical source index, offending field, and a stable non-finite reason. For
`GENERATED_REPLICATE_NON_FINITE`, it binds source identity, policy and method
identity, derived-seed identity, deterministic replicate index, and stable
reason. Stable reasons include `NON_FINITE_NAN`,
`NON_FINITE_POSITIVE_INFINITY`, and `NON_FINITE_NEGATIVE_INFINITY`; raw
runtime NaN payloads or strings are not authoritative evidence. Existing D4
encoding, D7 failure-result machinery, and D6 replay apply unchanged.

### 46.4 `BootstrapEvidence/v1`

`BootstrapEvidence/v1` is the immutable authoritative Step-4A result evidence.
It binds at minimum canonical Primary OOS source identity, validation identity,
instrument/scope identity, `BootstrapPolicy` identity,
`CIRCULAR_BLOCK_PERCENTILE_V1` identity, root-seed identity, derived seed and
derived-seed identity, `B`, confidence level, block length, completed canonical
OOS trade count, canonical point Expectancy, CI lower/upper bounds,
applicability/status, derived under-200 exception eligibility, and a
deterministic canonical result fingerprint.

`under_200_exception_eligible` is derived authoritative truth, never a caller
field: completed OOS trade count below 200, valid/applicable Bootstrap result,
and `ci_lower > 0`. At 200 or more trades it must not alter the ordinary
baseline. Zero/legitimately short samples are `INSUFFICIENT_DATA`; corrupt or
contradictory canonical evidence, missing identities/seed, invalid policy, or
non-finite evidence are `INVALID` or the required D7 failure above.

### 46.5 Step-4A scope boundary

Step 4A covers only `CanonicalPrimaryOOS` to dependency-preserving circular
block Bootstrap to `BootstrapEvidence/v1`. MC-1, MC-2, sensitivity,
promotion-gate orchestration, synchronized multi-instrument aggregate episodes,
Risk, Paper/Live, brokers, UI, and ORB remain out of scope.

---

## 47. Owner-Locked Step-4B MC-1 Permutation / Sequence-Risk Policy

These Step-4B decisions are additive on top of §27.5, §46, and the existing
D1–D7 foundation. They do not replace or weaken existing Bootstrap, MC-2,
validation, reproducibility, failure, accounting, or metric contracts. D1
reproducibility, D4 canonical encoding/fingerprinting, D6 replay, and D7
structured-failure/category semantics remain authoritative. No parallel
fingerprint, replay, RNG, failure, accounting, or metric system is authorized.

### 47.1 `MC1Policy/v1` and full-permutation method

`MC1Policy/v1` is immutable and binds the method/version, trial count `T`,
root seed, and requested drawdown quantiles. There are no hidden defaults and
no process-global RNG. The sole Step-4B method is
`MC1_FULL_PERMUTATION_ABSOLUTE_DRAWDOWN_V1`.

`T` must be a non-Boolean integer greater than or equal to one. A Boolean is
invalid despite being an `int` subtype. `T < 1` is `INVALID_POLICY` / `INVALID`
with stable reason `MC1_INVALID_TRIAL_COUNT`; it must not initialize RNG,
generate a permutation or empty distribution, compute quantile indices, use a
default, or clamp/repair the supplied value.

For one target instrument, `N` is its count of canonical Primary-OOS completed
trades. `N < 2` is legitimate `INSUFFICIENT_DATA` with stable reason
`MC1_INSUFFICIENT_SOURCE_TRADES`. `N >= 2` is eligible subject to valid policy
and evidence. Source insufficiency is distinct from policy invalidity.

Each of the `T` randomized trials is a full, without-replacement permutation
of all `N` canonical source net-realized-P&L observations: every observation
appears exactly once and each path has length exactly `N`. Repeated generated
permutations across trials are valid; paths must not be deduplicated, `T` need
not be less than or equal to `N!`, and implementation must not switch to exact
enumeration. The original chronological source order is baseline evidence only,
not an automatic randomized trial. If RNG generates that order, it remains a
valid generated trial.

### 47.2 Economic and drawdown authority

Step 4B uses only canonical net realized P&L per completed Primary-OOS trade.
Costs already represented in net evidence must not be subtracted again. All
calculations use the existing authoritative Decimal/internal precision policy;
floats and display rounding are not calculation truth.

The sole Step-4B drawdown is absolute peak-to-trough maximum drawdown. For a
path `p1 ... pN`, `S0 = Decimal(0)`, `Sk` is the cumulative sum through `pk`,
`running_peak(k) = max(S0, S1, ..., Sk)`, and
`drawdown(k) = running_peak(k) - Sk`. Absolute maximum drawdown is the maximum
of those drawdowns across the complete path. The original canonical
chronological order is evaluated by this same definition as separately
preserved baseline point evidence.

Step 4B must not invent starting equity, percentage/equity drawdown, leverage,
compounding, prices, synthetic fills, slippage, random costs, or position
sizing. Percentage/equity drawdown remains outside Step 4B because §27.5
requires explicit starting-equity evidence. The legacy helper's lowest
cumulative-P&L point is not equivalent to peak-to-trough maximum drawdown
unless mathematically identical for the particular path.

### 47.3 `MC1_EMPIRICAL_NEAREST_RANK_V1`

`requested_drawdown_quantiles` are explicit immutable `MC1Policy/v1` inputs.
Every quantile must be an authoritative finite `Decimal` strictly greater than
zero and less than or equal to one. `q <= 0`, `q > 1`, NaN, either infinity,
or an unsupported/non-authoritative numeric representation is `INVALID_POLICY`
/ `INVALID` with stable reason `MC1_INVALID_QUANTILE`. Invalid quantile policy
must not begin randomized analysis.

Quantiles are canonically sorted ascending and exactly-equal Decimal values are
deduplicated before policy fingerprint and output composition; caller insertion
order cannot affect either identity or result.

For exactly `T` finite randomized absolute-max-drawdown values and each
canonical quantile `q`, sort values ascending and select:

```text
index = ceil(q * T) - 1
index = clamp(index, 0, T - 1)
quantile_value = sorted_drawdowns[index]
```

There is no interpolation or generic/library percentile truth. This exact rule
is `MC1_EMPIRICAL_NEAREST_RANK_V1`; changing it requires a new method/version.

### 47.4 Finite evidence and D7 failure

Every canonical source net-realized-P&L observation, generated cumulative P&L,
and generated drawdown must be finite. Non-finite evidence/calculation fails
closed as a D7 Category-A deterministic structured failure with stable code
`MC1_NON_FINITE_EVIDENCE` at `MC1_ANALYSIS`. Bootstrap-specific failure codes
must not be reused; no failed observation or trial may be dropped, retried, or
replaced.

Stable non-finite reasons are `NON_FINITE_NAN`,
`NON_FINITE_POSITIVE_INFINITY`, and `NON_FINITE_NEGATIVE_INFINITY`; raw runtime
NaN payloads or strings are not authoritative identity truth. Source failure
evidence (`SOURCE_OBSERVATION_NON_FINITE`) binds canonical Primary-OOS source
identity, offending `OOSTradeEvidence` fingerprint, canonical source index,
offending field, and stable reason. Generated-path failure evidence
(`GENERATED_PATH_NON_FINITE`) binds source identity, `MC1Policy` identity,
method identity, derived-seed identity, deterministic trial and path-position
indices, and stable reason.

### 47.5 Derived seed and canonical source scope

MC-1 reuses existing deterministic seed machinery. Its versioned derived-seed
identity binds root seed, `RandomizedAnalysisKind.MC1`, canonical Primary-OOS
source identity, validation identity, full instrument/scope identity,
`MC1Policy/v1` fingerprint, and
`MC1_FULL_PERMUTATION_ABSOLUTE_DRAWDOWN_V1` identity. Python `hash()`, global
RNG, and process/thread/worker completion-order dependence are prohibited.

Step 4B runs once per instrument over that instrument's aggregate chronological
canonical Primary-OOS completed-trade evidence from successful eligible windows.
Window and trade provenance remain bound in the source identity. Bootstrap and
MC-1 should share generic canonical Primary-OOS validation/scope logic where
possible, but Bootstrap-specific source schemas and existing
`BootstrapEvidence/v1` fingerprints must not change. Any generic source
projection is additive. Synchronized multi-instrument Monte Carlo episodes are
outside Step 4B.

### 47.6 `MC1Evidence/v1`

`MC1Evidence/v1` is immutable authoritative outcome evidence. It binds at
minimum the canonical Primary-OOS source identity, validation identity, full
instrument/scope identity, `MC1Policy` fingerprint, method identity,
quantile-method identity, root-seed identity, derived seed and derived-seed
identity, source trade count `N`, randomized trial count `T`, original-order
absolute maximum drawdown, canonical requested quantile set, canonical
randomized drawdown quantile results, worst observed randomized absolute maximum
drawdown, randomized-trial-distribution identity/fingerprint, `ValidationStatus`,
stable reason where applicable, and a deterministic D4 result fingerprint.

A high/unfavourable drawdown is still a valid computed MC-1 outcome, not
`INVALID`. MC-1 never satisfies the under-200 Bootstrap profitability exception.

### 47.7 `RandomizedAnalysisCollection/v1` finalization and replay

`RandomizedAnalysisCollection/v1` is immutable compound result evidence that
allows Bootstrap, MC-1, and future MC-2 to coexist under the one existing
`ResultEvidenceFamily.RANDOMIZED_ANALYSIS` parent without overwriting each
other. Each entry binds analysis kind (`BOOTSTRAP`, `MC1`, or future `MC2`),
scope identity, evidence schema/version, and evidence result fingerprint.

Entries are canonically ordered by `(analysis_kind, scope_identity)`. Duplicate
authoritative `(analysis_kind, scope_identity)` keys are invalid and fail
closed; later evidence must never overwrite prior evidence. Caller, insertion,
execution, and worker order cannot affect collection identity.

When this compound collection applies, the sole `RANDOMIZED_ANALYSIS` child of
the successful result is the `RandomizedAnalysisCollection/v1` fingerprint, not
a direct Bootstrap or MC-1 fingerprint. The collection independently preserves
each child. D6 remains authoritative at the family level and must permit
diagnostic localization of changed `BOOTSTRAP`, `MC1`, and future `MC2` entries
without parallel replay infrastructure.

Existing finalized direct-Bootstrap children remain compatible where practical;
they must not be silently reinterpreted as historical compound collections. A
new parent representation or migration must be explicit and versioned.

### 47.8 Scope boundary

Step 4B implements only canonical per-instrument Primary-OOS MC-1 evidence.
MC-2, synchronized multi-instrument episodes, sensitivity, promotion-gate
orchestration, Risk, Paper/Live, broker APIs, UI, and ORB remain out of scope.

## 48. Owner-Locked Step-4C MC-2 Per-Window Block-Resampling Policy

These Step-4C decisions are additive on top of §27.5, §46, §47, and D1-D7.
They do not replace or weaken existing Bootstrap, MC-1, reproducibility,
failure, accounting, or metric contracts. D1 reproducibility, D4 canonical
encoding/fingerprinting, D6 replay, and D7 structured-failure semantics remain
authoritative. No parallel RNG, fingerprint, replay, failure, accounting, or
metrics system is authorized.

### 48.1 Method and scope

The sole Step-4C method is
`MC2_PER_WINDOW_CIRCULAR_BLOCK_ABSOLUTE_DRAWDOWN_V1`. Step 4C is
per-instrument only: it consumes aggregate chronological canonical
Primary-OOS completed-trade net-realized-P&L evidence for one exact
`InstrumentIdentity`, from successful eligible OOS windows only. Training,
selection, warm-up, sensitivity, research, failed-window, relabelled, and
noncanonical evidence are excluded.

Aggregate multi-instrument MC-2 remains deferred. It must later use
`SynchronizedEconomicEpisode` evidence; independent instrument sequences must
never be merged.

### 48.2 Per-window resampling domains and blocks

Every successful OOS window is an independent MC-2 resampling domain. Blocks
must not cross walk-forward OOS-window boundaries. For window `W`, let `Nw` be
its canonical Primary-OOS completed-trade count. Sampling occurs independently
within every `W`; window order is never randomized. Each resulting window path
is exactly `Nw` observations, and these paths are concatenated in canonical
original window order to form the exact aggregate trial path of length
`N = sum(Nw)`.

Within `W`, blocks are circular contiguous trade blocks of explicit length `L`.
Starts are sampled with replacement; repeated blocks are valid. Blocks are
appended until accumulated length is at least `Nw`, then truncated exactly to
`Nw`. There is no block deduplication, retry, automatic reduction of `L`, or
global-concatenated-window sampling.

Circular wrap is strictly local: valid starts satisfy `0 <= p < Nw`, and the
window-local source index for block element `i` is `(p + i) mod Nw` for
`i = 0 ... L - 1`. The modulus is always that window's `Nw`, never aggregate
`N`, another window's count, or a concatenated length. A block near a window
end wraps to that same window's beginning and never to another OOS window.

### 48.3 `MC2Policy/v1` and sufficiency

`MC2Policy/v1` is immutable and explicitly binds schema/version, method
identity, trial count `T`, block length `L`, root seed, and requested drawdown
quantiles. There are no hidden defaults. `T` and `L` are non-boolean integers
at least one. Invalid `T` is `MC2_INVALID_TRIAL_COUNT`; invalid `L` is
`MC2_INVALID_BLOCK_LENGTH`; each is `INVALID_POLICY` / `INVALID`, and must not
initialize RNG or be silently repaired.

The total canonical source count `N < 2` is legitimate `INSUFFICIENT_DATA`
with `MC2_INSUFFICIENT_SOURCE_TRADES`. For every included successful window,
`Nw < L` is legitimate `INSUFFICIENT_DATA` with
`MC2_INSUFFICIENT_WINDOW_TRADES_FOR_BLOCK`; `L` must not be reduced. All-zero
or all-equal finite outcomes are valid degenerate evidence.

### 48.4 Economics, baseline, and quantiles

Step 4C uses canonical net realized P&L only. Costs already represented in net
evidence must not be charged again. It uses the existing Decimal/internal
precision policy, never floats or display rounding, and must not invent
starting equity, percentage drawdown, leverage, compounding, prices, fills,
slippage, costs, or position-sizing changes.

The sole drawdown is absolute peak-to-trough maximum drawdown: `S0 = Decimal(0)`,
`Sk` is cumulative P&L, `running_peak(k) = max(S0 ... Sk)`, and
`drawdown(k) = running_peak(k) - Sk`; maximum drawdown is the maximum across
the complete path. The verified MC-1 Decimal helper must be reused where
semantically exact. Original chronological aggregate Primary-OOS maximum
drawdown is separate baseline evidence only, not an additional randomized
trial. Percentage/equity drawdown remains outside Step 4C.

`MC2Evidence/v1` contains only original-order absolute maximum drawdown, the
randomized block-resampled drawdown distribution, requested quantiles and their
results, and the worst randomized absolute maximum drawdown. Terminal-P&L,
Bootstrap expectancy, and MC-1 statistics are not Step-4C outputs.

The quantile method is `MC2_EMPIRICAL_NEAREST_RANK_V1`. Quantiles are explicit
finite `Decimal` values with `0 < q <= 1`; invalid values are
`MC2_INVALID_QUANTILE` / `INVALID_POLICY` / `INVALID`. They are canonically
ascending with exact Decimal duplicates removed; an empty tuple is valid. From
exactly `T` finite drawdowns sorted ascending, each quantile is index
`ceil(q * T) - 1`, clamped to `[0, T - 1]`, without interpolation or a generic
library percentile function. Changing this rule requires a new method/version.

### 48.5 Seeds and randomized path identity

MC-2 reuses deterministic seed derivation. Its derived-seed identity binds the
root-seed identity, `RandomizedAnalysisKind.MC2`, canonical Primary-OOS source
identity, validation identity/scope, full instrument/scope identity,
`MC2Policy/v1` fingerprint, method identity, and block-construction identity.
Python `hash()`, process-global RNG, and thread/process/worker-order dependence
are prohibited.

Every trial binds its index. For each canonical window it also binds window ID,
`Nw`, ordered block starts, `L`, ordered window-local source indices, and the
corresponding canonical `OOSTradeEvidence` identities/fingerprints. The full
aggregate source-index path identity and the trial's absolute maximum drawdown
are bound. Equal summary drawdowns must not collapse distinct sampled paths.

### 48.6 Non-finite evidence and D7 failure

Non-finite MC-2 evidence is the D7 Category-A deterministic structured failure
`MC2_NON_FINITE_EVIDENCE` at `MC2_ANALYSIS`, classified `INVALID`. Its subtypes
are `SOURCE_OBSERVATION_NON_FINITE` and `GENERATED_PATH_NON_FINITE`; Bootstrap-
and MC1-specific codes must not be reused. Stable non-finite reasons are
`NON_FINITE_NAN`, `NON_FINITE_POSITIVE_INFINITY`, and
`NON_FINITE_NEGATIVE_INFINITY`.

Source failure evidence binds canonical source identity, window ID, offending
`OOSTradeEvidence` identity/fingerprint, canonical and window-local source
indices, offending field, and stable reason. Generated-path failure evidence
binds source, policy, method, derived-seed identity, trial index, window ID,
sampled-block ordinal and start, path/window-local position, calculation field
(`cumulative_pnl` or `drawdown`), and stable reason. A deterministic failure
must not drop/retry a trial, reduce `T`, replace values, or continue analysis.

### 48.7 `MC2Evidence/v1`

`MC2Evidence/v1` is immutable authoritative outcome evidence. It binds schema,
canonical Primary-OOS source, validation identity/scope, full instrument/scope,
policy, method, block-construction and quantile-method identities, root and
derived seed identities where applicable, total `N`, canonical per-window
counts/identities, `T`, `L`, baseline drawdown where applicable, canonical
requested quantiles/results, worst randomized drawdown where applicable,
randomized block/path-distribution identity, `ValidationStatus`, stable reason
where applicable, and a D4 deterministic result fingerprint. Insufficient
evidence preserves unavailable randomized outputs as immutable empty/`None`
values; it must not fabricate results.

### 48.8 Collection, finalization, replay, and reporting

`MC2Evidence/v1` enters existing `RandomizedAnalysisCollection/v1` as
`analysis_kind = MC2`. Bootstrap, MC1, and MC2 remain independent collection
entries; existing canonical ordering and duplicate-key rejection remain
authoritative. Existing finalization, D6 replay-localization, and reporting
collection-mode infrastructure must be reused. Legacy direct Bootstrap-only
compatibility must not change.

### 48.9 Scope boundary

Step 4C does not implement aggregate multi-instrument MC-2, synchronized
economic episodes, sensitivity, promotion-gate orchestration, Risk, Paper/Live,
broker APIs, UI, or ORB.

## 49. Owner-Locked Step-5 Parameter-Sensitivity / Robustness Policy

These Step-5 decisions are additive on top of §27.6, D1-D7, and verified
Steps 3A, 3B, 4A, 4B, and 4C. They do not redefine selection, canonical
Primary-OOS, metrics, execution, accounting, costs, randomized analysis, or
promotion-gate ownership. Sensitivity is deterministic diagnostic robustness
evidence, not an optimization/reselection stage.

### 49.1 Purpose, anchor, and applicable domain

Sensitivity proves local robustness around an already selected configuration
and detects isolated parameter spikes. Each successful walk-forward window is
independently anchored to its immutable `ParameterPlan`,
`ParameterSelectionEvidence`, selected candidate fingerprint, and authoritative
training/selection evidence. Selections must never be flattened across
windows, and no sensitivity outcome may choose a new winner after OOS exists.

`SensitivityParameterDomain/v1` is the conceptual immutable typed-domain
contract. It binds parameter name, canonical type, finite allowed/sensitivity
values, explicit tunable status, and domain provenance. Permitted types are
`INTEGER`, `DECIMAL`, and `CATEGORICAL`. Values use D4 typed canonical encoding:
integer `1` and string `"1"` are distinct. Ranges, steps, percentages, radii,
neighbors, and domains are never inferred. BOOLs, structural configuration,
identifiers, strategy version, timeframe, instrument, execution/cost
configuration, and other non-tunable configuration are excluded unless a
strategy contract explicitly declares a suitable tunable domain. No applicable
domain is `NOT_APPLICABLE`.

### 49.2 Neighborhood forms, baseline, and boundaries

The legal forms are `COORDINATE`, `LOCAL_GRID`, and
`EXPLICIT_CANDIDATE_SET`.

- `COORDINATE` changes exactly one declared tunable parameter at a time while
  every other value remains the selected base value.
- `LOCAL_GRID` is the finite Cartesian product of explicit sensitivity values
  over applicable domains. Its complete grid is constructed before execution.
- `EXPLICIT_CANDIDATE_SET` contains only its explicitly supplied typed points.

The selected configuration is baseline-only and is not a neighbor or part of
the neighbor denominator. Values outside their declared domain are omitted;
they must not be clamped, wrapped, substituted, or manufactured. Canonical
duplicate values and points are removed before execution. If no actual
neighbor remains, the result is `INSUFFICIENT_DATA` with
`SENSITIVITY_NO_VALID_NEIGHBORS`.

`SensitivityPolicy/v1` is immutable and explicitly binds schema/method
version, form, typed applicable domains, explicit point-generation contract,
boundary/normalization rule, baseline-only rule, required metrics, baseline
applicability rule, robustness thresholds, minimum valid-neighbor count,
minimum robust-neighbor ratio, `max_evaluated_points`, and a deterministic
no-RNG method identity. There are no hidden defaults. `max_evaluated_points`
is a non-boolean integer at least one. A canonical LOCAL_GRID larger than this
limit is `INVALID_POLICY` with `SENSITIVITY_GRID_EXCEEDS_POLICY_LIMIT`; it must
not be truncated, sampled, partially evaluated, or have its cap increased.

### 49.3 Evidence partition, isolation, and metrics

Step-5 sensitivity runs only against each selected window's training/selection
partition, retaining completed-bar availability/no-look-ahead and the primary
window/embargo construction. OOS sensitivity remains a future, separate
diagnostic capability. Neighbor evidence must never enter `CanonicalPrimaryOOS`,
the primary-OOS completed-trade count, Bootstrap, MC-1, or MC-2 inputs.

Every point uses a fresh isolated existing run/factory boundary. No strategy,
portfolio, positions, pending orders, ledger, protective, metrics, costs, or
observations state may leak between base/neighbor runs, points, or windows.

Each valid neighbor and baseline binds completed-trade count, canonical finite
Net Expectancy, canonical finite Max Drawdown, and authoritative metric-evidence
identity. Floats and display-rounded values are not calculation truth. Before
relative robustness, baseline Net Expectancy must be finite and strictly
positive. Otherwise the window is `NOT_APPLICABLE` with
`SENSITIVITY_BASELINE_NON_POSITIVE`; it does not retroactively invalidate the
Step-3A selection.

A valid neighbor is robust exactly when it has more than zero completed trades,
positive Net Expectancy, Net Expectancy at least `0.50 * base_net_expectancy`,
and Max Drawdown no more than `1.50 * base_max_drawdown`. These thresholds are
versioned `SensitivityPolicy/v1` truth. A window passes only with at least two
valid neighbors and `robust_neighbor_count / valid_neighbor_count >= 0.60`.
Fewer than two legitimate valid neighbors is `INSUFFICIENT_DATA`; sufficient
evidence below the ratio is `FAIL` / non-promotable.

### 49.4 Point and window terminal-state semantics

Zero trades are retained point evidence with status `INELIGIBLE` and reason
`ZERO_COMPLETED_TRADES`. Undefined/non-finite required metrics and
corrupt/contradictory evidence are `INVALID`. A deterministic structured point
or run failure is retained as canonical failure evidence. Independent points
may continue where safe; failed/ineligible points must never disappear or be
reclassified as ordinary weak performance.

Per-window terminal states are distinct: `PASS`, `FAIL`, `INSUFFICIENT_DATA`,
`INVALID`, and `NOT_APPLICABLE`. Across all required successful walk-forward
windows, any `INVALID` makes the aggregate `INVALID`; otherwise any
`INSUFFICIENT_DATA` makes it `INSUFFICIENT_DATA` / non-promotable; otherwise
every applicable window must pass, and any applicable `FAIL` makes the
aggregate `FAIL` / non-promotable. `NOT_APPLICABLE` windows are excluded from
the applicable denominator and alone neither fail nor pass it. If all required
windows are `NOT_APPLICABLE`, aggregate status is `NOT_APPLICABLE` with
`SENSITIVITY_NO_APPLICABLE_WINDOWS`, never `PASS`.

### 49.5 Canonical evidence and aggregation

Each `SensitivityPoint` binds a canonical typed parameter-value tuple. Points
are lexicographically ordered by that tuple, independent of caller,
generation, evaluation, worker, dictionary, set, process, or thread order.

`SensitivityEvidence/v1` is immutable per-window evidence binding schema,
window identity, selected `ParameterPlan` identity, selection-evidence identity,
selected parameter fingerprint, training/selection source identity,
`SensitivityPolicy/v1` fingerprint, baseline metrics, the complete retained
point universe, each point's typed identity/status/reason and metric/failure
identity, valid and robust counts, applicable robustness ratio, terminal status
and reason, and a D4 result fingerprint.

The smallest immutable aggregate sensitivity evidence binds the complete
required window schedule, ordered per-window evidence identities, terminal
status collections/counts, aggregate status/reason, policy identity, and D4
aggregate fingerprint. Window order is the established `(oos_start, window_id)`
order. Every required window appears in exactly one terminal-status collection;
the union must equal the required universe. Duplicate, missing, unknown, or
multiply classified windows are contradictory and fail closed as `INVALID`.

### 49.6 Determinism, finalization boundary, and scope

Step-5 sensitivity uses no RNG, root seed, derived seed, or
`RandomizedAnalysisCollection`. It reuses `CanonicalCodec` and existing typed
parameter/candidate identity discipline; `repr()`, floats narrowing,
process-hash, and unordered serialization are forbidden.

The first Step-5 implementation stops at per-window and aggregate sensitivity
evidence production. It does not implement promotion decisions and does not
enter `RANDOMIZED_ANALYSIS`. If later finalization/replay/reporting requires
compound deterministic validation evidence, it must be a versioned collection
under the existing `VALIDATION` family with sensitivity as a distinct child,
preserving D6 localization without overwriting other validation evidence.

Step 5 does not authorize aggregate multi-instrument MC-2 episodes, Risk,
Paper/Live, brokers, UI, ORB, OOS neighbor selection, replacement of the
Step-3A winner, or new optimization.

## 50. Owner-Locked Step-5 Additive Selection / Training / Factory Contracts

These decisions extend §49 and are backward-compatible with verified Step-3A
and Step-3B semantics. They add evidence and a parameterized factory boundary;
they do not redefine existing `WalkForwardCandidate`, `ParameterPlan`,
`ParameterSelectionEvidence`, selection eligibility, or historical result
identities.

### 50.1 `SelectedParameterConfiguration/v1`

`SelectedParameterConfiguration/v1` is immutable additive Step-3A selection
evidence. It binds schema/version, selected candidate fingerprint, canonical
typed parameter mapping/names/types/values, configuration fingerprint, and
selection/window provenance. Supported sensitivity-relevant values are
`INTEGER`, `DECIMAL`, and `CATEGORICAL`.

Typed values are captured authoritatively when a candidate is selected. They
must never be reconstructed, reverse-decoded, or inferred from a candidate
fingerprint. D4 canonical encoding is required; `repr()` identity and float
narrowing are prohibited. The new configuration fingerprint explicitly binds
the selected candidate fingerprint and provenance, and does not replace the
existing selection contracts.

### 50.2 Parameterized fresh-run factory

An additive `ParameterizedRunFactory` / `SensitivityRunFactory` boundary is
authorized:

`create_run(parameter_configuration: SelectedParameterConfiguration/v1) -> fresh WalkForwardRun`

Input must already be an authorized immutable typed configuration. Every call
returns a fresh isolated runner and must not mutate the selected/base runner or
shared strategy configuration. It must not reuse state across points or
windows, including portfolio, ledger, positions, orders, protective state,
metrics, costs, observations, or runtime strategy state. It may not coerce
hidden values or infer them from fingerprints.

Existing `WalkForwardCandidate.create_run()` remains unchanged for predeclared
Step-3A candidate evaluation. The new factory exists only to construct
authorized sensitivity configurations without reopening selection.

### 50.3 Retained selected training baseline

Each successful Step-3A window may retain immutable selected-training baseline
evidence binding the selected candidate fingerprint, selected typed
configuration fingerprint, authoritative training `MetricSummary` and
`MetricSummary.evidence_id`, completed-trade count, canonical finite Net
Expectancy, canonical finite Max Drawdown, training/source identity, window
identity, and selection provenance.

This retained evidence is the authoritative Step-5 baseline. Step 5 must not
rerun/recompute the selected baseline when it exists, and OOS evidence must
never substitute for it.

### 50.4 Deterministic sensitivity-point failures

A deterministic `StructuredFailureResult` from an otherwise authorized point
is retained as complete canonical point evidence with state `FAILED` /
`NON_VALID`; it does not automatically make the entire window `INVALID`.
Independent points may continue safely. Failed points remain in the canonical
universe and are excluded from valid and robust neighbor counts; they are not
dropped or recast as weak performance. After all points, fewer than two valid
neighbors is `INSUFFICIENT_DATA`; otherwise §49 robustness applies to valid
neighbors only.

The distinct states are locked:

- zero completed trades: `INELIGIBLE` / `ZERO_COMPLETED_TRADES`;
- legitimate deterministic run failure: `FAILED` / `NON_VALID`;
- corrupt/contradictory/invalid-policy/non-finite required evidence: `INVALID`;
- valid finite metrics: `VALID`, then `ROBUST` or `NON_ROBUST` under §49.

Invalid required evidence remains `INVALID` under §49/D7; this failure rule
does not weaken that distinction. All new evidence reuses `CanonicalCodec`,
`StructuredFailureResult`, D4 fingerprinting, and D7 deterministic-failure
semantics. It is schema-versioned and replay-deterministic; no parallel
identity or failure system is authorized.

### 50.5 Compatibility and scope

Negative-expectancy candidates retain their existing Step-3A eligibility.
Existing `WalkForwardCandidate.create_run()`, `ParameterPlan`, and
`ParameterSelectionEvidence` remain valid. Existing single-window and
multi-window fingerprints must not change unless a new versioned containing
contract explicitly includes new additive evidence.

This lock does not implement sensitivity execution, promotion gates,
finalization/replay/reporting sensitivity collections, Risk, Paper/Live,
brokers, UI, or ORB.

## 51. Owner-Locked Step-6 Promotion-Gate Orchestration

### 51.1 Boundary and authoritative artifacts

Step 6 is a pure, deterministic validation-layer promotion decision over
already-established evidence.  It introduces only versioned validation
artifacts: `PromotionPolicy/v1`, `PromotionGateResult/v1`, and
`PromotionDecisionEvidence/v1`.  It consumes Step 3B aggregate evidence,
BootstrapEvidence/v1, MC1Evidence/v1, MC2Evidence/v1, and Step-5 sensitivity
evidence; it must not rerun walk-forward candidates, historical runs, or any
randomized analysis.

The policy and decision bind the canonical ordered complete window schedule,
per-window selection identities, canonical Primary OOS evidence, all required
analysis evidence and identities, and canonical blocker/reason evidence.  The
existing D4 canonical encoding and D6 replay machinery are the only allowed
identity/replay mechanism.  No global selected-parameter fingerprint may
flatten or replace the per-window Step-3B selection identities.

### 51.2 Complete-window promotion rule

Promotion requires at least **three** complete eligible Promotion OOS windows.
Step 6 consumes Step 3B's achieved/required complete-window evidence and
validates its consistency; it does not rerun any window.  Limited historical
depth may be reported as limited evidence but cannot reduce this requirement.

If the minimum is not met, the result is `INSUFFICIENT_DATA` /
`NON_PROMOTABLE` with canonical reason
`PROMOTION_INSUFFICIENT_COMPLETE_WINDOWS`.  Corrupt or contradictory window
evidence, duplicate identities, overlapping Promotion OOS intervals, or a
policy/evidence count inconsistency remain `INVALID` and fail closed.

### 51.3 Sample sufficiency and Bootstrap applicability

The canonical completed Primary OOS trade count is evaluated as follows:

- At `N >= 200`, the sample-sufficiency gate passes without Bootstrap.
  Supplied Bootstrap evidence is diagnostic/statistical evidence and must be
  valid and provenance-consistent, but its CI sign does not independently veto
  promotion unless a later owner-approved policy says so.
- At `N < 200`, BootstrapEvidence/v1 is required.  The gate passes only if it
  has `PASS` status, `under_200_exception_eligible` is true, `ci_lower` is
  present, and `ci_lower > 0`.  A lower bound equal to or below zero does not
  qualify.  Missing required Bootstrap evidence is `INVALID`, not a substitute
  for another analysis.

MC-1, MC-2, and sensitivity evidence cannot substitute for the required
under-200 Bootstrap exception.

### 51.4 Independent MC-1 and MC-2 gates

MC-1 and MC-2 are separate mandatory gates.  Each requires its applicable
`/v1` policy to request quantile `Decimal("0.95")` and its evidence to contain
the corresponding authoritative randomized absolute-Max-Drawdown quantile.

- MC-1 passes only when `q95_randomized_abs_maxdd <= 1.50 *
  original_order_abs_maxdd`.
- MC-2 passes under the same inequality against its block-resampled
  distribution.
- When the original-order baseline is zero, the respective q95 must be
  exactly zero.

Missing q95 or policy/evidence inconsistency is `INVALID`; legitimate
insufficient source evidence is `INSUFFICIENT_DATA` / `NON_PROMOTABLE`; and a
threshold breach is `FAIL` / `NON_PROMOTABLE`.  Neither analysis may satisfy
or mask the other.

### 51.5 Sensitivity applicability

Step-5 aggregate sensitivity is consumed as already-computed authoritative
evidence.  `PASS` passes; `FAIL` fails; `INSUFFICIENT_DATA` remains
insufficient; and `INVALID` remains invalid.  `NOT_APPLICABLE` is neutral: it
does not block promotion and is not positive proof.  Its reason and
fingerprint remain bound into the promotion decision.

### 51.6 Full-gate evaluation and status precedence

The gate evaluates every available input without short-circuiting, in this
canonical order:

1. provenance/schema;
2. complete windows;
3. sample sufficiency / Bootstrap;
4. MC-1;
5. MC-2;
6. sensitivity.

All canonical blocker evidence is retained.  Terminal precedence is
`INVALID > INSUFFICIENT_DATA > FAIL > PASS`, with `NOT_APPLICABLE` neutral.

Ordinary Step-6 policy, schema, provenance, identity, or evidence defects
produce `PromotionDecisionEvidence/v1` with `INVALID` and a stable canonical
reason.  They do not create a new D7 failure.  Existing upstream D7 structured
failures retain their established identity and are preserved as upstream
evidence.

### 51.7 Explicit scope exclusion

This first promotion-gate step stops at the validation artifacts in this
section.  It must not overload the closed `ValidationOutcomeIdentity/v1` and
does not wire a finalizer, result-evidence family, replay comparison family,
or reporting schema.  That integration requires a separate preflight after
the pure Step-6 validation boundary is verified.

## 52. Owner-Locked PromotionDecision Finalization, Replay, and Reporting Composition

### 52.1 Valid non-promotable finalization

`PromotionDecisionEvidence/v1` statuses `PASS`, `FAIL`, and
`INSUFFICIENT_DATA` are all valid completed promotion evaluations.  They may
finalize through the normal completed-backtest `SuccessfulResult` path.
`SuccessfulResult` means authoritative result assembly completed successfully;
it does not mean a strategy passed promotion.

`PASS` binds `promotable=true`; `FAIL` and `INSUFFICIENT_DATA` bind
`promotable=false`.  Valid non-promotable evidence must not become D7
failures, engine/runtime errors, discarded evidence, or a fabricated `PASS`.

### 52.2 Invalid promotion finalization

`PromotionDecisionEvidence/v1` with `INVALID` status must not produce a
`SuccessfulResult` and must not be converted to a D7 `StructuredFailureResult`.
It is a deterministically completed audit with invalid authoritative promotion
evidence, not a computation/runtime-stage failure.

`InvalidFinalizedResult/v1` is authorized as an immutable distinct result. It
binds its schema/version, manifest fingerprint, `ValidationEvidenceCollection/v1`
fingerprint, `PromotionDecisionEvidence/v1` fingerprint, terminal `INVALID`
status, canonical invalid-reason identities, `promotable=false`, the complete
canonical parent `ResultEvidence` collection validly established before the
invalid promotion outcome, and a deterministic D4 result fingerprint.

The three result classes are deliberately distinct: `SuccessfulResult` for
valid completed evidence assembly, `InvalidFinalizedResult/v1` for completed
audit with invalid promotion evidence, and `StructuredFailureResult` for D7
deterministic computation/runtime-stage failures.

### 52.3 `ValidationEvidenceCollection/v1`

`ValidationEvidenceCollection/v1` is the additive, immutable compound parent
for new collection-aware `ResultEvidenceFamily.VALIDATION` results.  Its only
initial child kinds and canonical order are:

1. `VALIDATION_OUTCOME`;
2. `PROMOTION_DECISION`.

Each entry binds `validation_analysis_kind`, `scope_identity`,
`evidence_schema_version`, and `evidence_result_fingerprint`.  The collection
uses D4 `CanonicalCodec` fingerprinting over that explicit ordered collection.
Duplicate authoritative `(analysis_kind, scope_identity)` keys are invalid and
fail closed.

Initial v1 does not include `AggregateSensitivityEvidence` directly because
`PromotionDecisionEvidence/v1` already binds it transitively.  Bootstrap,
MC-1, and MC-2 remain exclusively under `ResultEvidenceFamily.RANDOMIZED_ANALYSIS`
and must not be duplicated under `VALIDATION`.

### 52.4 Legacy and finalization input compatibility

Legacy finalized results remain unchanged: their sole `VALIDATION` child is a
direct `ValidationOutcomeIdentity/v1` fingerprint.  New collection-aware
results explicitly use a `ValidationEvidenceCollection/v1` fingerprint.  An
old direct identity must never be silently reinterpreted as a collection.

Finalization accepts exactly one mode: legacy direct
`ValidationOutcomeIdentity/v1` or collection-mode
`ValidationEvidenceCollection/v1`.  Supplying both is contradictory and must
fail deterministically; no precedence or silent selection is allowed.

### 52.5 D6 replay localization

Collection-mode replay retains the top-level `VALIDATION` mismatch and may
additively localize deterministic child differences as
`VALIDATION:VALIDATION_OUTCOME` and `VALIDATION:PROMOTION_DECISION`.  Equivalent
child evidence must match.  Changed promotion decision, policy, gate, blocker,
or source identity must alter the `PROMOTION_DECISION` child and collection
fingerprint.  Legacy replay remains unchanged, and no parallel replay engine
is authorized.

### 52.6 Public reporting / v3

`sentinelx-report/v3` is authorized.  Existing v1/v2 reports remain unchanged.
The minimal public-safe promotion projection is promotion status, promotable,
canonical ordered gate summaries (`gate_kind`, `status`, `reason`), promotion
evidence fingerprint, and validation-collection fingerprint.  An
`InvalidFinalizedResult/v1` report additionally carries `result_status=INVALID`,
`promotable=false`, and canonical invalid reasons.  No unnecessary internal
provenance or unrelated report redesign is authorized.

### 52.7 Invalid-result audit evidence retention

`InvalidFinalizedResult/v1` retains the complete canonical parent
`ResultEvidence` collection that was already established, structurally valid,
provenance-valid, and supplied to finalization for the same authoritative
manifest/run scope.  At minimum that collection contains its sole `VALIDATION`
parent bound to `ValidationEvidenceCollection/v1`; it also retains the existing
direct or collection-mode `RANDOMIZED_ANALYSIS` parent where legitimately
supplied, plus any other already-authorized canonical result-evidence families
that normal finalization would retain.

Malformed, unsupported-schema, contradictory, foreign, failed-collection, or
placeholder evidence is never retained.  Such malformed finalization input
remains a deterministic input error and must not fabricate an
`InvalidFinalizedResult/v1`.  No randomized evidence is recomputed.

The invalid-result D4 fingerprint binds schema/version, manifest, terminal
`INVALID`, `promotable=false`, validation-collection fingerprint,
promotion-decision fingerprint, canonically ordered unique invalid-reason
identities, and the retained parent evidence ordered by the existing
authoritative `ResultEvidenceFamily` ordering rather than caller insertion
order.

D6 comparison of invalid finalized results compares this retained parent
collection and the explicit validation/promotion/reason bindings.  A
randomized-only change localizes under `RANDOMIZED_ANALYSIS`; a promotion-only
change localizes under `VALIDATION:PROMOTION_DECISION`; and both diagnostics
may correctly occur when both authoritative families change.  Cross-result-type
replay remains a deterministic mismatch.

### 52.8 No recomputation and scope

Finalization, replay, and reporting consume established evidence only.  They
must not rerun the promotion evaluator, sensitivity, Bootstrap, MC-1, MC-2,
walk-forward, strategy execution, RNG, or seed derivation.

This lock authorizes no implementation in this documentation step.

## 53. Owner-Locked D4 Migration Sub-step 1 — Validation Identities

All authoritative validation policy, scope, randomized-seed, synchronized
episode, and validation-run identities use `CanonicalCodec` only.  Plain JSON
hashing, delimiter-concatenated hashing, `repr()`, pickle, and parallel custom
canonicalizers are prohibited.

The first migration schemas are:

1. `sentinelx-resolved-embargo-map/v2`;
2. `sentinelx-walk-forward-policy/v2`;
3. `sentinelx-randomized-derived-seed/v2`;
4. `sentinelx-synchronized-economic-episode/v2`;
5. `sentinelx-aggregate-mc1-scope/v2`;
6. `sentinelx-aggregate-mc2-scope/v2`; and
7. `sentinelx-validation-run-evidence/v2`.

Each schema supplies explicit ordered fields directly to `CanonicalCodec`.
`timedelta` values are represented by schema-owned `(days, seconds,
microseconds)` integer tuples; this preserves exact duration evidence without
inventing a second codec type.  Derived randomized seeds are the first eight
bytes of the D4 schema digest, interpreted as an unsigned integer.  Existing
pre-migration identities are not D4-compatible and must not be retained as
authoritative equivalents or compared as like-for-like D6 replay evidence.

This decision authorizes no cost, metric, regime, live-halt, audit-log,
broker, UI, or strategy migration.

## 54. Owner-Locked D4 Migration Sub-step 2 — Transaction-Cost Identities

All authoritative transaction-cost policy and evidence identities in
`engine/costs/model.py` use `CanonicalCodec` only.  Plain JSON hashing,
delimiter-concatenated hashing, `repr()`, pickle, and parallel custom
canonicalizers are prohibited; the former `_digest` JSON/SHA-256 helper was
removed.

The migrated cost identity schemas are:

1. `sentinelx-cost-schedule/v2` — `CostSchedule.fingerprint`;
2. `sentinelx-trade-evidence/v2` — `trade_evidence_fingerprint`;
3. `sentinelx-cost-assessment/v2` — `assessment_identity`;
4. `sentinelx-cost-leg-assessment/v2` — `leg_assessment_identity` (and the
   stored `CostLegAssessment.version` schema tag);
5. `sentinelx-cost-leg-evidence/v2` — `leg_evidence_fingerprint`; and
6. `sentinelx-cost-result-evidence/v2` — `cost_evidence_fingerprint`.

Each schema supplies explicit ordered fields directly to `CanonicalCodec` with
caller-owned ordering.  Instrument identity reuses the established D4 ordered
field scope `(market, instrument, segment, underlying, expiry, strike,
option_type)`; ledger event keys use explicit `(run_id, accounting_sequence)`
integer/string tuples.  Decimals, dates, datetimes (UTC-normalized at fixed
nine-digit nanosecond precision), enums, and None values are passed as typed
values, never as `str()`/`.value`/isoformat pre-digests.  Existing
pre-migration cost identities are not D4-compatible and are not retained as
authoritative equivalents or compared as like-for-like D6 replay evidence.

Identity scope is unchanged: schedules bind schedule/version/currency/
effective window/scope selectors/ordered component rules; trade evidence binds
cost-relevant completed-trade, leg, and instrument evidence; assessment and
leg-assessment identities bind canonical provenance; and result evidence
binds sorted leg/completed assessment history.  No commission, fee, slippage,
cost arithmetic, trade P&L, execution, or validation behavior changed.

This decision authorizes no metric, regime, live-halt, audit-log, broker, UI,
or strategy migration.

## 55. Owner-Locked D4 Migration Sub-step 3 — Metric Identities

The authoritative metric evidence identity in `engine/metrics.py`
(`MetricsCalculator._evidence_id`, stored as `MetricSummary.evidence_id`) uses
`CanonicalCodec` only.  Plain JSON hashing, delimiter-concatenated hashing,
`repr()`, pickle, and parallel custom canonicalizers are prohibited; the
former `_canonical_json` / `_canonical_value` JSON canonicalizers and the
ad-hoc `_*_body` JSON builders were removed.

The migrated metric identity schema is `sentinelx-metric-evidence/v2`.

Explicit ordered fields bind, in order: scope (kind, run_id, account_id,
strategy_id, instrument), policy (policy_id, version,
annualization_sessions, market_profile_refs canonicalized by sorting,
risk_free_rate, sortino_target_rate), the `NET_OF_COSTS` net-basis literal,
and canonically sorted collections of trades, equity observations, cost
assessments, session intervals, and position intervals.  Each element is a
schema-owned ordered record; instrument identity reuses the established D4
field order `(market, instrument, segment, underlying, expiry, strike,
option_type)`; ledger event keys use `(run_id, accounting_sequence)`;
`timedelta` uses the §53 `(days, seconds, microseconds)` integer tuple; trade
provenance mappings are encoded as sorted (str-key, value) pairs; and
Decimals, datetimes (UTC-normalized at fixed nine-digit nanosecond
precision), enums, and None values are passed as typed values.  Collections
are canonically ordered by `CanonicalCodec.encode_value`, preserving the
established input-order independence.  `EquityObservation.complete`, computed
metric output values, and regime projection evidence/`regime_buckets` remain
intentionally excluded from the identity.  Existing pre-migration metric
identities are not D4-compatible and are not retained as authoritative
equivalents or compared as like-for-like D6 replay evidence.

No metric mathematics, economic calculations, definitions, thresholds,
ordering/eligibility logic, reporting behavior, or unrelated architecture
changed.

> **OWNER DECISION:** `sentinelx-metric-evidence/v2` is approved and frozen
> as the authoritative D4 schema for `MetricSummary.evidence_id` (produced by
> `MetricsCalculator._evidence_id`).  The §55 implementation is accepted as
> the frozen contract, including CanonicalCodec-only authoritative identity
> generation, explicit caller-owned field ordering, the existing metric
> evidence field scope, canonically ordered input collections,
> `market_profile_refs` order-independent canonicalization, the established
> 7-field `InstrumentIdentity` ordering, event keys as `(run_id,
> accounting_sequence)`, schema-owned `(days, seconds, microseconds)`
> `timedelta` representation, non-comparable legacy pre-migration metric
> fingerprints, and unchanged metric mathematics and behavior.

This decision authorizes no regime, live-halt, audit-log, broker, UI, or
strategy migration.

## 56. Owner-Locked D4 Migration Sub-step 4 — Legacy Regime Identities

The remaining authoritative legacy regime identities in `engine/regime.py`
use `CanonicalCodec` only.  Plain JSON hashing and parallel custom
canonicalizers are prohibited; the former `json`/`sha256` imports were
removed.

The migrated regime identity schemas are:

1. `sentinelx-entry-regime-snapshot/v1` — the `EntryRegimeSnapshot/v1`
   fingerprint (v1 evidence without `account_id`), replacing the legacy
   JSON/SHA-256 body; and
2. `sentinelx-entry-regime-evidence/v1` — the all-v1 run-level aggregate
   entry-regime evidence fingerprint, replacing the legacy JSON list digest.

The already-canonical v2 siblings (`sentinelx-entry-regime-snapshot/v2`,
`sentinelx-entry-regime-evidence/v2`), `RegimeEvidence.fingerprint`
(`sentinelx-regime-evidence/v2`), and
`RegimeClassifier.evidence_fingerprint`
(`sentinelx-regime-evidence-aggregate/v2`) are unchanged.

The migrated v1 snapshot fingerprint binds the v1 evidence contract exactly
(`schema_version`, entry event key `(run_id, accounting_sequence)`, fill
timestamp UTC-normalized at fixed nine-digit nanosecond precision, policy
identity, regime status, regime value or None, and source evidence
fingerprint) and, per §36.1, now binds the complete canonical
`InstrumentIdentity` plus `StreamKey` timeframe through
`_stream_identity_fields` — previously the legacy body bound only four stream
fields.  The v1 aggregate binds the ordered v1 snapshot fingerprints sorted by
`(run_id, accounting_sequence)` with `entry_event_key` deduplication,
mirroring the v2 composition under its v1 schema.  v1 evidence (no
`account_id`) remains under its producing contract; mixed v1/v2 collections
continue to route to the v2 aggregate.  The V1/V2 evidence boundary, the
validation-side applicable-snapshot scoping, and the run-level REGIME result
child semantics are unchanged; foreign/unrelated snapshots remain excluded
from scoped validation identity and the run-level aggregate still binds the
full run snapshot set by design.  Legacy pre-migration v1 fingerprint bytes
are non-comparable and are not retained for compatibility.

No regime classification rules, taxonomy, thresholds, indicator
calculations, warm-up behavior, or unrelated architecture changed.

This decision authorizes no live-halt, audit-log, broker, UI, or strategy
migration.

## 57. Owner-Locked P1 Reconciliation — `alert_and_halt()` / `NoReturn` Contract

The §11 known unresolved defect is resolved.  `engine/strategy_halt.py` now
implements the frozen Rule 7 contract:

- `alert_and_halt(strategy_id, exception) -> NoReturn` always terminates the
  current control-flow path: it emits the halt alert (unchanged behavior),
  retains the per-strategy halted state and first halt reason in the
  facade's in-process registry (`halted_reason(strategy_id)`), and then
  raises a dedicated `StrategyHaltError`.
- `StrategyHaltError` is a plain `Exception` subclass — deliberately not a
  `RuntimeError`, `ValueError`, or any type a strategy may raise — so broad
  handlers for the original strategy error cannot accidentally swallow the
  fatal halt and continue.  No signal, order, or action can be produced from
  the halted control-flow path.
- `safe_generate_signal` is unchanged: its live failure branch already ends
  at the halt call, which now raises instead of returning; the backtest HOLD
  fallback and audit-record ordering are unchanged.  Orchestration remains
  backtest-mode only (`"backtest"`).
- Per-strategy halt scope is preserved: only the failing strategy is recorded
  as halted, never the entire live system.  Full per-strategy process
  isolation and alert delivery remain Phase 7/8 live-control dependencies
  behind this same narrow facade.
- Repeated halt handling is deterministic and idempotent: the first recorded
  reason is retained and every invocation raises the same fatal signal.

No trading strategy, backtest, cost, metric, regime, validation, D4
fingerprint, ORB, or unrelated exception-handling behavior changed.

This decision authorizes no audit-log, broker, UI, or strategy migration.

## 58. Owner-Locked Phase 3A — Production Risk Policy and Q64 Position Sizing

### 58.1 Owner-locked Phase 3 risk policy (backtest / paper trading)

The owner explicitly locked the following Phase 3 risk values for backtest and
paper-trading risk policy.  They are NOT automatically approved as final live
real-money risk settings; live deployment requires a separate owner review
before broker activation.

- **Q55 — per-trade risk:** 0.5% of authoritative deployable capital.
- **Q56 — maximum daily loss:** 2.0% of authoritative start-of-day risk capital.
- **Q58 — maximum simultaneously open positions:** 3.
- **Q59 — maximum aggregate portfolio risk:** 3.0% of authoritative deployable capital.
- **Q61 — capital allocation method:** FIXED.  Performance-weighted or adaptive
  allocation is NOT implemented in Phase 3.
- **Q63 — minimum risk:reward:** 1 : 1.5.  A proposed trade below 1:1.5 is
  risk-ineligible and must be rejected.
- Preserved existing locks: **Q57** max_daily_trades = 10; **Q60** correlation
  filter enabled, initial owner-locked action for a correlation violation =
  REJECT; **Q62** signal priority = confidence_score; **Q65** insufficient
  capital/margin = REJECT.

### 58.2 Stop-distance source lock

The authoritative stop distance used by the frozen Q64 position-sizing formula
must come from the strategy-owned / PositionKey-bound ProtectiveExit STOP_LOSS
contract.  Arbitrary `Signal.metadata` is NOT an authoritative stop-distance
source.  Risk Management does not create a second stop-loss implementation;
ProtectiveExit remains the owner of exit behavior.  If no valid authoritative
protective stop exists for a trade that requires risk sizing: **FAIL CLOSED /
REJECT** — never invent a stop.

### 58.3 Risk failure semantics lock

Phase 3 risk gates are fail-closed.  For per-trade risk violation, daily loss
limit, max open positions, max portfolio risk, minimum risk:reward,
missing/invalid sizing inputs, insufficient capital/margin, and correlation
conflict, the default Phase 3 behavior is **STRUCTURED REJECTION**: do not
silently resize, clamp quantity, modify a strategy stop, or convert a rejected
trade into another trade.  Q60's frozen block/reduce wording is owner-resolved
for the initial production risk policy as **BLOCK / REJECT**.  Automatic
risk-based resize is DEFERRED until separately owner-approved with its own
explicit versioned policy.  A risk rejection by itself does NOT invoke the
fatal live strategy halt; fatal engine/invariant failures continue to use the
separately frozen `alert_and_halt()` contract.

### 58.4 Implemented Phase 3A contract

`engine/risk_manager.py` implements the Phase 3A scope only:

- **`RiskPolicy`** — versioned Tier-1 production risk policy with explicit
  CanonicalCodec identity `sentinelx-risk-policy/v1` (established
  `sentinelx-<domain>-policy/vN` family; NOT the temporary
  `sentinelx-slice14-integration-quantity-policy/v1`, which is prohibited as
  production risk sizing policy).  It binds: policy version, per-trade risk
  percentage (0.5%), FIXED capital allocation, minimum risk:reward (1.5),
  authoritative stop source (`PROTECTIVE_EXIT_STOP_LOSS`), structured-REJECT
  failure semantics, and the authoritative quantity-normalization identity
  (`InstrumentQuantityNormalization/v1`).  Owner-locked values are enforced at
  construction; Phase 3B/3C gate fields are deliberately not bound yet.
- **Q64 fixed-fractional sizing** — `RiskManager.size_position(...)` computes
  `risk capital = capital × per_trade_risk_pct`, `raw quantity = risk capital ÷
  abs(entry_price − authoritative stop price)` using exact Decimal arithmetic
  only (never float, never a fixed lot size).  The authoritative stop price is
  read from the strategy-owned STOP_LOSS `ProtectiveExit`; quantity is
  normalized only through authoritative `InstrumentSpecification` metadata
  (largest `quantity_step` multiple that does not exceed the raw size, subject
  to `minimum_quantity`).  Missing/invalid capital, entry, stop, zero stop
  distance, non-finite inputs, and quantity below the minimum all FAIL CLOSED.
- **`RiskDecision`** — structured deterministic result distinguishing
  APPROVED / REJECTED with an explicit machine-readable snake_case rejection
  reason, following the existing `ExecutionOutcome` / `AccountingOutcome`
  result conventions.

Protected exits, portfolio, orders, execution, costs, metrics, regime,
validation, D4 fingerprints, and orchestration were NOT changed by Phase 3A.
The daily-loss, max-open-position, max-portfolio-risk, correlation, and
risk:reward eligibility gates, signal-priority scheduling, adaptive resizing,
and allocation methods remain later Phase 3 sub-steps.

## 59. Owner-Locked Phase 3A Corrective Reconciliation — Multiplier-Aware Q64, PositionKey Ownership, and LONG Directional R:R

The Phase 3A reconciliation (§58) found an economic sizing defect: the Q64
formula omitted ``contract_multiplier`` while authoritative accounting applies
it everywhere (``PnL = quantity × price_delta × contract_multiplier``; BUY cash
requirement, SELL proceeds, realized and unrealized P&L).  This section locks
the corrective reconciliation and supersedes §58.4's sizing semantics.

### 59.1 RiskPolicy v2 identity

- The authoritative production RiskPolicy identity is now
  **`sentinelx-risk-policy/v2`** (CanonicalCodec-based, explicit schema-owned
  ordering, exact Decimal semantics, deterministic replay-comparable inside the
  v2 schema family).
- `sentinelx-risk-policy/v1` MUST NOT be silently mutated and is legacy /
  non-comparable: the authoritative Q64 economic sizing semantics changed, so
  v1-sized results must never be compared with v2-sized results under one
  identity.  No compatibility hack preserves old v1 quantities or fingerprints.
- Bound fields are unchanged from the owner-locked Phase 3A set: version,
  per_trade_risk_pct = 0.5%, capital_allocation = FIXED, min_risk_reward = 1.5,
  stop source = PROTECTIVE_EXIT_STOP_LOSS, failure semantics = REJECT,
  authoritative instrument quantity normalization.  Phase 3B/3C gate fields are
  still not bound.

### 59.2 Multiplier-aware Q64 and exact Decimal/rounding order

Authoritative LONG / BUY-TO-OPEN sizing contract, exact order:

1. Exact Decimal input conversion/validation (entry > 0, stop > 0,
   contract_multiplier > 0, capital > 0, per_trade_risk_pct > 0; all finite).
2. Directional `risk_distance = entry_price - stop_price` — LONG requires
   `stop_price < entry_price`; `stop_price >= entry_price` REJECTS.  `abs()` is
   never used to repair invalid directional placement.
3. `risk_per_quantity = risk_distance × contract_multiplier` — must be finite
   and > 0; otherwise structured REJECT (`invalid_risk_per_quantity`) BEFORE
   division.
4. `risk_capital = capital × per_trade_risk_pct`.
5. `raw_quantity = risk_capital / risk_per_quantity` (prec-50 Decimal context).
6. Floor raw quantity to the authoritative `quantity_step` (never round to
   nearest, so normalization cannot increase the risk budget).
7. Validate normalized quantity >= `minimum_quantity` and > 0.
8. Only then APPROVE.

No float conversion anywhere; `InstrumentSpecification.contract_multiplier` is
authoritative Decimal instrument evidence.  Parity invariant: `normalized ×
risk_distance × contract_multiplier ≤ risk_capital`.  M = 1 behaves exactly as
before; M > 1 reduces quantity so actual loss-at-stop never exceeds the budget.
Accounting P&L mathematics are unchanged.

### 59.3 PositionKey ownership — runtime-verified, never caller-trusted

- Sizing requires an explicit authoritative intended `PositionKey`; the
  supplied STOP_LOSS `ProtectiveExit` must satisfy
  `protective_stop.position_key == intended_position_key` EXACTLY
  (binding strategy_id, strategy_version, and the full `InstrumentIdentity`),
  and `intended_position_key.identity == specification.identity` (exact
  canonical InstrumentIdentity equality — never strategy_id-only, symbol-only,
  or partial field matching).
- The TARGET follows the same ownership discipline:
  `target.position_key == protective_stop.position_key == intended_position_key`
  and `target.position_key.identity == specification.identity`.
- Any mismatch — foreign strategy, wrong strategy version, wrong expiry/strike,
  CE-vs-PE mismatch, wrong market/segment/instrument, foreign stop or target —
  fails closed with a structured REJECT.  RiskManager never selects another or
  nearest stop, never uses a same-symbol stop, never falls back to
  `Signal.metadata`, and never continues with caller-trusted provenance.
- The authoritative stop remains `ProtectiveExitKind.STOP_LOSS` from the
  strategy-owned / PositionKey-bound protective contract.  RiskManager only
  CONSUMES the protective stop; it implements no second stop-loss and derives no
  stop from metadata/ATR/percentage defaults/inferred R:R.

### 59.4 TARGET source and LONG directional R:R contract

- The authoritative reward target is `ProtectiveExitKind.TARGET` (its
  authoritative limit price).  `Signal.metadata` targets, arbitrary caller
  Decimals, targets inferred from 1:1.5, and generated/synthetic targets are
  prohibited.
- Current phase-3 direction scope is LONG / BUY-TO-OPEN only.  Direction comes
  from the explicit `PositionDirection` contract, never inferred from price
  ordering.  SHORT / SELL-TO-OPEN fails closed with `unsupported_direction`;
  the short formula (`target < entry < stop`) is documentary future context
  only and is not activated.
- LONG R:R: require `stop < entry < target`; `risk_distance = entry - stop`,
  `reward_distance = target - entry`; `risk_reward = reward_distance /
  risk_distance` in exact Decimal; eligibility requires `risk_reward >=
  min_risk_reward (1.5)`.  `stop >= entry` or `target <= entry` REJECTS;
  `abs()` never repairs invalid geometry.
- Missing authoritative target when R:R eligibility is evaluated, and
  terminated (FILLED/CANCELLED) protective evidence as the active trade plan,
  REJECT.  Duplicate/ambiguous candidate selection is not silently performed at
  this layer (exact-match only); candidate ambiguity resolves upstream at the
  protective-book boundary.
- OCO membership is NOT required for R:R eligibility: PositionKey symmetry is
  the authoritative ownership/applicability proof.  Existing OCO behavior and
  `ProtectiveExitBook` semantics remain unchanged and continue to govern
  execution-time sibling cancellation/exclusivity.

### 59.5 Structured rejection semantics

All fail-closed cases return a deterministic structured `RiskDecision`
(APPROVED / REJECTED with an explicit machine-readable snake_case reason),
including at minimum: `unsupported_direction`, `stop_position_key_mismatch`,
`target_position_key_mismatch`, `stop_instrument_mismatch`,
`target_instrument_mismatch`, `missing_authoritative_stop`,
`missing_authoritative_target`, `invalid_stop_placement`,
`invalid_target_placement`, `invalid_risk_per_quantity`,
`quantity_below_minimum_quantity`, `missing_or_invalid_capital`,
`non_positive_capital`, `missing_or_invalid_entry_price`,
`risk_reward_below_minimum`.  No ambiguous None/bool results; unrelated
`AccountingOutcome` / `ExecutionOutcome` contracts are unchanged.

This section authorizes no Phase 3B gates, daily-loss / max-open-position /
max-portfolio-risk / correlation gates, confidence scheduling, adaptive
resizing, performance-weighted allocation, kill switch, broker/live
integration, durable audit logging, strategy, ORB, or protective-exit changes.

## 60. Owner-Locked Phase 3B — RiskPolicy v3 and the Deterministic Pre-Order Risk Gate

### 60.1 Phase 3B owner locks (backtest / paper trading)

The owner locked the Phase 3B risk contracts (Q55–Q65 preserved): daily loss is
authoritative net-equity drawdown against a fixed RiskDay baseline (2.0%); the
RiskDay is account-level, derived from the deployment's market calendar /
timezone / regular session boundary (conflicting calendar identities fail
closed; local-machine and UTC midnight are never the basis unless explicitly
the deployment RiskDay); first RiskDay baseline = authoritative starting
capital, each later RiskDay baseline = the previous RiskDay's closing net
-equity (never rebased intraday); daily trade count = +1 on the FIRST non-zero
fill of each logical new entry order (partial fills, rejects, cancels, expiries
and exits = +0, reset on the RiskDay boundary, max 10); R:R entry reference is
the decision-time reference price (MARKET) / OrderRequest.limit_price (LIMIT),
never future fill prices; every open LONG PositionKey must have exactly one
valid ACTIVE PositionKey-bound STOP_LOSS or new entries fail closed
(`invalid_risk_evidence`); max open positions counts exact PositionKeys (3);
max portfolio risk is the sum of per-position risk at active protective stops
plus the candidate trade risk, vs 3.0% of the SAME authoritative
deployable-capital basis consumed by sizing; Q60 correlation = same-direction
exact-same-InstrumentIdentity overlap (not a statistical engine), action =
REJECT; signal priority = Q62 highest confidence first with an explicit
canonical tie-break; all gate violations are structured REJECTions and never
invoke `alert_and_halt()` (exits/protective exits are never gated).

### 60.2 RiskPolicy v3 identity

- The authoritative production RiskPolicy schema is now
  **`sentinelx-risk-policy/v3`** (CanonicalCodec, explicit ordered fields).
  `sentinelx-risk-policy/v1` and `/v2` are legacy/non-comparable schema
  families; v2 keeps its Phase-3A semantics and is never silently mutated, and
  Phase-3B fields are never silently added to v2.
- v3 binds all economically meaningful fields: version; per_trade_risk_pct
  (0.5%); max_daily_loss_pct (2.0%); max_daily_trades (10); max_open_positions
  (3); max_portfolio_risk_pct (3.0%); capital_allocation (FIXED);
  min_risk_reward (1.5); stop_source (PROTECTIVE_EXIT_STOP_LOSS);
  failure_semantics (REJECT); quantity_normalization
  (InstrumentQuantityNormalization/v1); correlation_policy
  (Q60SameDirectionSameInstrument/v1); correlation_action (REJECT);
  signal_priority_policy (Q62StrategyScopedConfidence/v2 active since the
  Phase 3 contract correction, §62.4; Q62ConfidenceScore/v1 preserved as the
  legacy identity); daily_loss_measure (NetEquityDrawdownRiskDay/v1);
  risk_day_policy (MarketSessionRiskDay/v1);
  daily_trade_count_policy (FirstEntryFillRiskDay/v1);
  missing_risk_evidence_policy (REJECT); rr_entry_reference_policy
  (DecisionTimeReferencePrice/v1).  Owner-locked values are enforced at
  construction.

### 60.3 Phase 3B-1 implemented contracts

`engine/risk_manager.py` implements the deterministic pre-order gate:

- **`RiskDay`** — explicit account-level risk-day identity (calendar_identity +
  session_date), evidence-derived from the deployment calendar/session
  boundary; conflicting calendar identities fail closed.
- **`RiskGateState`** — immutable account-level daily state (RiskDay,
  start_of_day_net_equity fixed baseline, current_net_equity, daily_trade_count
  with per-entry dedup).  `record_entry_fill(entry_identity)` increments
  exactly once per logical entry order; same-identity partial fills never
  increment again.  The baseline rebases exactly once per RiskDay transition
  (first day = starting_capital; later days = prior closing net equity).
- **`RiskGate.evaluate_pre_order(...)`** — the frozen 15-step pipeline for one
  NEW entry candidate: direction validation → exact PositionKey-bound
  STOP/TARGET resolution (exactly-one-or-REJECT via
  `ProtectiveExitBook.authoritative_exits`) → LONG geometry → R:R (≥ 1.5) →
  corrected multiplier-aware Q64 sizing (reused RiskManager) → candidate risk →
  daily-loss gate → daily-trade-count gate → max-open-positions gate (exact
  PositionKey counting) → aggregate portfolio-risk gate (fail-closed on
  missing/ambiguous stop evidence) → Q60 same-direction same-instrument
  conflict gate.  Returns APPROVED with the sized quantity or REJECTED with an
  explicit snake_case reason; normal rejection never calls `alert_and_halt()`.
- **`rank_candidates(...)` / `SignalPriorityEvidence`** — versioned deterministic
  Q62 ranking: legacy `Q62ConfidenceScore/v1` keeps the original
  confidence-first semantics (explicit `policy_identity` for legacy replay);
  active `Q62StrategyScopedConfidence/v2` (default) orders by canonical
  strategy identity first (`strategy_id`, `strategy_version`) with confidence
  descending only WITHIN the same strategy/version, then the canonical
  tie-break on (full InstrumentIdentity, timeframe, originating_timestamp);
  unknown identities fail closed; no Python hash, no insertion/caller order,
  no mixing of capital-allocation priority into signal priority (§62.4).
- `engine/protective.py` gains the read-only
  `ProtectiveExitBook.authoritative_exits(position_key, *, kind)` exact-match
  selection (ACTIVE + exact position_key + exact kind, stable protective_id
  iteration; never selects by price/insertion/recency; OCO semantics
  untouched).

The Phase 3A corrected sizing/ownership/R:R contracts are reused unchanged.
No orchestration migration, kill switch, broker/live integration, durable
audit logging, strategy, ORB, or protective-exit behavior changed.  Phase 3B-2
later slices (orchestration wiring of the gate, capital-config identity
binding into the manifest risk slot) remain unstarted.

### 60.4 Phase 3B-1 narrow contract clarifications (hardening patch)

No economic policy changed; `sentinelx-risk-policy/v3` identity semantics are
unchanged (no v4).  These clarifications lock existing behavior:

1. **Phase 3B-1 is explicitly LONG / BUY-TO-OPEN ONLY.**  All R:R and
   portfolio-risk geometry is intentionally LONG-only (`STOP < ENTRY <
   TARGET`, both distances > 0).  SHORT / SELL-TO-OPEN is NOT active: an
   authoritative SHORT direction is a structured `unsupported_direction`
   REJECT.  The gate never evaluates a short-side formula, never infers side
   from price ordering, never uses `abs()`, never auto-swaps STOP/TARGET, and
   never silently accepts `TARGET < ENTRY < STOP`.  Future short support
   requires a separately owner-approved policy/contract extension.
2. **Candidate geometry dependency:** `candidate_trade_risk =
   normalized_quantity × risk_distance × contract_multiplier` is admitted to
   the aggregate portfolio-risk sum ONLY from a successful, directionally
   valid RiskManager sizing result (LONG direction, STOP/TARGET ownership,
   `STOP < ENTRY < TARGET`, positive risk_distance, R:R eligibility,
   multiplier-aware sizing).  A candidate that failed directional geometry
   validation never enters aggregate portfolio-risk computation; if pipeline
   order ever changes, candidate geometry must be independently re-verified
   before candidate risk is admitted.
3. **Same-PositionKey / Q60 interaction:** a candidate targeting an
   already-open exact PositionKey is NOT a new PositionKey and therefore does
   NOT consume an additional max-open-position slot (the branch is reachable
   and explicit, not dead).  Under the current LONG-only Q60 policy it must
   nevertheless reject later with `correlation_conflict` (existing open LONG
   exposure on the exact same InstrumentIdentity).  The max-position exemption
   is NOT permission to pyramid / average in / scale in / add to existing
   LONG exposure; the branch remains explicit for semantic correctness and
   future versioned policy changes.

## 61. Owner-Locked Phase 3B-2C — Strategy-Owned Pre-Entry Protective Plan Foundation

Phase 3B-2 orchestration wiring is blocked on two gaps proven by the targeted
protective-plan audits (Phase 3B-2A/2B, source hashes verified): no
authoritative fresh per-entry STOP/TARGET price producer exists, and no
deterministic per-entry ProtectiveExit identity contract exists.  This slice
implements the reusable foundation ONLY; RiskGate is NOT wired into
`BacktestOrchestrator`, RiskPolicy v4 and its cost-adjusted-equity capital
basis remain unstarted, and full Phase 3B-2 orchestration remains unstarted.

### 61.1 Owner contract — ProtectivePlanPolicy

The engine does NOT globally dictate one STOP/TARGET formula.  Different
strategies may legitimately use ATR-derived protection, fixed distance,
percentage distance, or strategy-specific frozen rules.  Therefore a
strategy-owned `ProtectivePlanPolicy` contract is introduced
(`engine/protective_plan.py`):

- Responsibility: completed decision-time evidence + strategy-owned
  configuration/state -> one concrete STOP_LOSS price + one concrete TARGET
  price, produced BEFORE RiskGate eligibility.
- RiskGate MUST NOT calculate these prices; it consumes the resulting
  materialized protective instances.
- No default trading formula exists at the engine level; concrete production
  implementations are strategy-owned and come later; tests use a
deterministic test-local stub policy.

### 61.2 Authoritative safety rules

- Plan calculation may use only evidence available at decision time.
- Forbidden: `Signal.metadata` as an authoritative STOP/TARGET source; future
execution fill / next-bar-open prices; future market data; stale previous-trade
runtime protective prices; arbitrary fallback Decimals; RiskGate inventing
prices; reviving terminal ProtectiveExit instances.
- A policy that cannot produce valid evidence FAILS CLOSED (raises) — it never
fabricates protection and never invents fallback prices.

### 61.3 PreEntryProtectivePlan

Immutable evidence for ONE entry cycle binding: intended_position_key,
originating_timestamp (timezone-aware, canonical rules), timeframe,
protective_plan_policy_identity, and concrete finite positive stop_price /
target_price (exact Decimal; no float authority).  Structural validation is
fail-closed; the object never `abs()`s, reorders, swaps, or repairs prices,
and never independently invents R:R semantics — LONG geometry
(`STOP < ENTRY < TARGET`) remains RiskManager/RiskGate authority.

### 61.4 Protective-instance identity — `sentinelx-protective-instance/v1`

Plan/template and runtime instance are separate concepts.  The RUNTIME
ProtectiveExit instance identity is the new canonical family
`sentinelx-protective-instance/v1` (CanonicalCodec, explicit ordered fields,
suitable as the `ProtectiveExit.protective_id`):

1. run_identity
2. strategy_id
3. strategy_version
4. full InstrumentIdentity (established 7-field order: market, instrument,
   segment, underlying, expiry, strike, option_type)
5. timeframe
6. originating_timestamp (CanonicalCodec UTC/nanosecond rules)
7. protective_plan_policy_identity
8. protective kind (exactly STOP_LOSS or TARGET)

No JSON/SHA legacy identity, no Python `hash()`, no `repr()`, no
delimiter-string canonicalizer, no random UUID, no wall-clock timestamp, no
insertion/caller order.  Identical evidence replays to the identical
fingerprint; one entry cycle yields STOP id != TARGET id (kind participates);
a later entry cycle on the same exact PositionKey (later
originating_timestamp) yields fresh STOP/TARGET ids; old terminal instances
remain historical evidence and their ids are never reused.

### 61.5 Materialization and exactly-one-ACTIVE safety

`materialize_protective_plan(plan, *, run_identity, quantity, book)`
deterministically materializes one plan into exactly TWO fresh ACTIVE
ProtectiveExit instances (STOP_LOSS then TARGET) registered in the runtime
book: exact intended PositionKey, concrete plan prices,
`sentinelx-protective-instance/v1` ids, ACTIVE start state.  If an ACTIVE
STOP_LOSS or ACTIVE TARGET already exists for the intended PositionKey it
fails closed (raises) rather than adding another active plan; it never cancels
a legitimate existing active protection to make room and never selects a
winner by protective_id ordering.  No execution is evaluated, no order
submitted, `PortfolioAccount` never mutated, RiskGate never invoked.

### 61.5a Owner-locked quantity authority (corrective patch)

A provisional quantity on runtime protective instances is INVALID
architecture: `reconcile_position` shrinks excessive protection but never
authoritatively grows under-sized protection, so a provisional quantity could
leave a position incompletely protected.  The owner lock therefore separates
two stages:

- **STAGE A — pre-gate price evidence:** `ProtectivePlanPolicy` ->
  `PreEntryProtectivePlan`.  The plan is PRICE / PROVENANCE evidence only and
  owns NO quantity field (quantity, raw_quantity, normalized_quantity, and
  position_size are all forbidden), so a plan policy can never become a second
  sizing authority.
- **STAGE B — post-sizing runtime materialization:** only after
  RiskManager/RiskGate has produced the authoritative approved Q64 quantity
  may the plan be converted into runtime ProtectiveExit instances.
  `materialize_protective_plan(plan, *, run_identity, quantity, book)`
  requires an explicit keyword-only `quantity` with NO default.  No
  provisional, sentinel, inferred, configured Slice-14, or Signal.metadata
  quantity is permitted.

Materialization validates the supplied quantity only (numeric, finite,
> 0) and then uses the EXACT resulting Decimal for the STOP and TARGET
OrderRequest/ProtectiveExit quantities (STOP quantity == TARGET quantity ==
supplied quantity); no second flooring, normalization, rounding, clamping,
resizing, or account derivation exists.  RiskManager/RiskGate is the SOLE
quantity authority; in the future gate-wired flow the materialized quantity
MUST equal the RiskGate APPROVED quantity exactly.  `reconcile_position`
remains unchanged: it may reduce protection after legitimate position
reductions but is NOT an initial sizing authority.

Quantity deliberately does NOT participate in the
`sentinelx-protective-instance/v1` identity: the identity identifies the
entry-cycle protective instance/provenance, while quantity is authoritative
runtime sizing evidence that changes legitimately through position
reduction/reconciliation.  The 8 canonical identity fields are unchanged.

Repeated-entry lifecycle proof: ENTRY CYCLE 1 (Plan-1 -> STOP-1/TARGET-1
ACTIVE at its own explicit quantity) closes and STOP-1/TARGET-1 become
terminal under the existing lifecycle; ENTRY CYCLE 2 on the same exact
PositionKey with a new originating_timestamp materializes NEW STOP-2/TARGET-2
ACTIVE with fresh ids and its own explicitly supplied quantity; old terminal
instances remain terminal and are never reactivated, rewritten, or deleted.
Existing `ProtectiveExitBook` OCO, stale-cancel, and protective execution
semantics are unchanged; `book.add` remains the registration path.

### 61.6 Out of scope for this slice

Full BacktestOrchestrator RiskGate wiring, Q62 ranking wiring, RiskGateState
orchestration persistence, daily first-fill recording,
RuntimeConfigurationSnapshot risk binding, RiskPolicy v4,
cost_adjusted_equity wiring, Q65 ordering changes, strategy-specific
ATR/fixed-stop production formulas, SHORT protection, live/paper broker
integration, and durable audit logging remain unstarted and are later slices.

## 62. Owner-Locked Phase 3B-2D — Candidate Protective Evidence Reconciliation

Phase 3B-2D reconciles the RiskGate candidate-evidence boundary.  No
orchestration wiring was performed; `BacktestOrchestrator`, RiskPolicy v4, and
full Phase 3B-2 remain unstarted.

### 62.1 Candidate-evidence contract

- **NEW BUY candidate:** the authoritative STOP/TARGET price evidence is the
  strategy-owned `PreEntryProtectivePlan` bound to the exact intended
  PositionKey (`candidate_plan`).  Candidate STOP = `candidate_plan.stop_price`;
  candidate TARGET = `candidate_plan.target_price`, used for LONG geometry, R:R
  eligibility, the Q64 sizing risk distance, and candidate portfolio-risk
  calculation.
- **EXISTING open positions:** the authoritative risk evidence remains the
  ACTIVE exact PositionKey-bound `ProtectiveExitBook` STOP_LOSS (zero /
  duplicate / foreign / terminal STOP evidence remains fail-closed); existing
  positions do NOT use `PreEntryProtectivePlan` as current runtime risk
  evidence.  A candidate plan cannot substitute for a missing runtime STOP on
  an already-open position.
- Forbidden for candidate evidence: `Signal.metadata`, loose caller Decimals,
  a synthesized ProtectiveExit, and inserting the plan into `ProtectiveExitBook`
  before approval/fill.

### 62.2 Lifecycle lock — no runtime materialization in the gate

Runtime ProtectiveExit objects are NOT materialized merely because RiskGate
approved an entry.  Correct lifecycle:

```
ProtectivePlanPolicy -> PreEntryProtectivePlan -> RiskGate candidate evaluation
-> APPROVED quantity Q -> entry order -> accepted entry fill
-> materialize runtime STOP_LOSS + TARGET (frozen plan prices + quantity Q)
```

A RiskGate-approved order may still be unfilled, cancelled, expired, or
rejected downstream; creating ACTIVE runtime protection before a position
exists could leave orphan ACTIVE protection and block later entries.  RiskGate
itself never calls `materialize_protective_plan`, never adds to
`ProtectiveExitBook`, never creates an OrderRequest, never mutates the
protective lifecycle or `PortfolioAccount`.  A REJECT leaves the book,
account, execution, and orders unchanged.  Runtime materialization belongs to
later accepted-fill orchestration wiring.

### 62.3 Implementation

- `RiskGate.evaluate_pre_order(...)` gains `candidate_plan:
  PreEntryProtectivePlan | None`; the candidate STOP/TARGET `ProtectiveExitBook`
  lookups are removed.  Missing/absent plan for a BUY candidate fails closed
  with `missing_candidate_plan`; wrong PositionKey plan fails closed with
  `candidate_plan_position_key_mismatch`; instrument mismatch fails closed with
  `candidate_plan_instrument_mismatch`.  (Candidate target ambiguity no longer
  exists — the plan is the singular candidate target source; `ambiguous_duplicate_target`
  remains an existing-position evidence concept where applicable.)
- `RiskManager.size_position_from_plan(...)` sizes a candidate from the plan
  prices with the same ownership/price validation and the SAME frozen Q64 /
  R:R mathematics as `size_position` (shared `_size_from_prices` /
  `_risk_reward_from_prices`; no duplicated sizing logic).  The
  ProtectiveExit-based `size_position` API and its reason codes are unchanged.
- `sentinelx-risk-policy/v3` is NOT mutated.  When RiskPolicy v4 is
  implemented it MUST bind the final candidate-protective-evidence policy
  identity (the plan-price candidate evidence contract) as an explicit
  versioned sub-policy.

### 62.4 Phase 3 Contract Correction — Q62 Strategy-Scoped Priority + Target-Optional Representation

Owner decision (narrow production patch; no broad Phase 3B-2 integration).
Two contract corrections with REPRESENTATION and ELIGIBILITY kept separate.
No RiskGate → `BacktestOrchestrator` wiring, no temporary Slice-14
orchestration quantity-policy removal, no RiskPolicy v4, no Option Selector,
no LONG_SHORT / statistical correlation, no real ORB/EMA strategy logic.

**A. Q62 — versioned strategy-scoped ranking.**  Raw confidence values emitted
by DIFFERENT `strategy_id` / `strategy_version` pairs are NOT inherently
comparable: the generic engine MUST NOT rank one strategy's candidate ahead of
another's merely because its raw confidence is numerically higher.  Within the
SAME strategy_id + strategy_version, confidence remains a deterministic local
ranking signal.  Until an explicit common calibrated-comparability contract
exists, cross-strategy ordering is deterministic canonical strategy ordering.

- `Q62ConfidenceScore/v1` (LEGACY, preserved): global raw-confidence-first
  ranking with the canonical tie-break — unchanged semantics, reachable via
  `rank_candidates(candidates, policy_identity="Q62ConfidenceScore/v1")` for
  legacy replay.
- `Q62StrategyScopedConfidence/v2` (ACTIVE, new): candidates order FIRST by
  canonical strategy identity (`strategy_id`, then `strategy_version`);
  confidence descending applies only WITHIN the same strategy/version group;
  `None` confidence sorts behind numeric confidence deterministically within
  its own group; then the existing canonical candidate tie-break (full
  InstrumentIdentity, timeframe, originating_timestamp).
- Versioned boundary: `rank_candidates(candidates, *,
  policy_identity=<active v2 identity>)`; any unknown identity FAILS CLOSED
  (deterministic `ValueError`).  No Python `hash()`, no insertion order, no
  caller order, no calibration engine, no normalization invention.
- `sentinelx-risk-policy/v3` schema is unchanged (NOT v4).  The v3 fingerprint
  already binds `signal_priority_policy`; the ACTIVE v2 identity is now the
  default `RiskPolicy` sub-policy identity, so it participates in every v3
  fingerprint.

**B. Protective-plan representability (target-optional).**  The generic engine
must be able to REPRESENT a strategy with an authoritative protective STOP and
NO fixed profit TARGET (exit by trailing stop, strategy signal, reversal
signal, time exit, or another strategy-owned exit rule).

- `PreEntryProtectivePlan.stop_price` remains MANDATORY (numeric, finite,
  positive, exact Decimal normalization).
- `PreEntryProtectivePlan.target_price` may be Decimal-compatible OR `None`
  (Python `None` only — never zero as a sentinel, never Infinity/NaN, never a
  synthesized huge target, never `Signal.metadata` as target authority);
  `None` is preserved exactly.
- The plan never validates LONG geometry; RiskManager/RiskGate remain
  geometry/R:R authority.
- `materialize_protective_plan(plan, *, run_identity, quantity, book)` keeps
  its explicit REQUIRED keyword-only `quantity` (no provisional quantity
  reintroduced; the plan remains quantity-free).  A plan WITH a target
  materializes exactly STOP_LOSS + TARGET; a targetless plan materializes
  exactly STOP_LOSS only — no TARGET instance, no TARGET OrderRequest, no
  TARGET `sentinelx-protective-instance/v1` identity.  Return contract is one
  or two fresh ACTIVE instances.  Duplicate-active safety, exact PositionKey
  ownership, deterministic instance ids, terminal lifecycle, and quantity
  semantics unchanged.
- REPRESENTATION != ELIGIBILITY: the current RiskPolicy still requires minimum
  R:R 1.5, so a targetless candidate fails RiskGate policy eligibility
  deterministically with `missing_authoritative_target`
  (`evaluate_pre_order` → `size_position_from_plan(...,
  require_risk_reward=True)`).  The failure occurs at POLICY ELIGIBILITY,
  never at plan construction.  min R:R 1.5 is NOT weakened; no fake target is
  invented.
- `engine/orchestration.py` and `engine/protective.py` were NOT modified by
  this correction.

## 63. Owner-Locked Phase 3B-2 — Gate-Enabled Orchestration Integration

Owner decision (controlled production implementation; no RiskPolicy v4, no
live trading, no Option Selector, no LONG_SHORT, no STOP/STOP_LIMIT
entry-reference semantics).  Gate-enabled deployment remains OPTION-BUYING
ONLY: BUY CE / BUY PE are LONG; SELL may only close/reduce an owned LONG.

**A. RiskGate is wired into the gate-enabled `BacktestOrchestrator`.**  The
pre-order pipeline is now: planned terms → authoritative entry reference →
frozen `PreEntryProtectivePlan` → `RiskGate.evaluate_pre_order` (with current
pending commitments) → approved quantity → `OrderRequest` using the SAME
planned terms → pending → execution → accepted fill → ownership → protective
materialization.  The legacy risk-deferred path (no `risk_gate`) is preserved
unchanged and still uses the temporary Slice-14 `rule.quantity` behavior.

**B. Planned order terms separate pricing from gate quantity.**
`PlannedOrderTerms` (order_type, time_in_force, limit_price, stop_price) is
resolved EXACTLY ONCE by `SignalToOrderPolicy.planned_terms(intent,
source_bar)` from the existing `SignalToOrderRule` / `PriceSource` authority;
`order_for(..., quantity=<optional override>, planned_terms=<optional
already-resolved terms>)` never resolves prices twice and never creates a
second pricing authority.  Gate-enabled runs pass the RiskGate-approved
quantity; legacy runs omit the override and preserve `rule.quantity`.

**C. Entry reference by order type (gate-enabled BUY).**  MARKET → completed
decision/source bar close; LIMIT → the authoritative planned `limit_price`
(never blindly `source.close`).  The SAME reference is passed to
`ProtectivePlanPolicy.plan_for(reference_price=...)` and
`RiskGate.evaluate_pre_order(entry_price=...)`; fill prices never participate
in pre-order R:R eligibility.  BUY STOP / STOP_LIMIT in gate-enabled mode
FAIL CLOSED at construction until a separate owner-locked entry-reference
policy exists.

**D. `sentinelx-entry-intent/v1` logical entry identity.**  Deterministic
pre-fill identity via `CanonicalCodec` only, exact semantic field order:
strategy_id, strategy_version, full InstrumentIdentity (established 7-field
order), timeframe, originating_timestamp (codec UTC/nanosecond encoding).
Quantity, protective-plan prices, confidence, and fill prices are EXCLUDED.
No delimiter concatenation, no JSON-SHA parallel identity, no repr(), no
pickle, no Python hash().  Stable from gate evaluation through pending
commitment, pending order, first accepted entry fill
(`RiskGateState.record_entry_fill` dedup), and commitment release.

**E. `PendingRiskCommitment` semantics.**  Frozen risk-layer reservation for a
gate-approved but not-yet-filled BUY: `entry_identity`, `intended_position_key`,
`approved_quantity`, `nominal_stop_risk` (gate-computed; orchestrator never
recomputes risk formulas).  It is NOT an economic position: never an
`AccountSnapshot` position, never cash/P&L, never a TradeLedger fill, never a
runtime ProtectiveExit, never a `ProtectiveExitBook` entry, never a daily
loss/cash/equity/trade-count input.  Pending commitments reserve:

- MAX POSITION SLOTS: effective committed/open keys = actual snapshot
  positions + unique pending-commitment keys.
- AGGREGATE NOMINAL STOP-RISK: existing real open-position risk + sum of
  pending-commitment nominal risk + candidate risk.
- Q60 exact InstrumentIdentity overlap: candidate rejected if the identity
  exists in real positions OR pending commitments (`correlation_conflict`).

Duplicate `entry_identity` values and invalid commitment values FAIL CLOSED.
`RiskGate.evaluate_pre_order(..., pending_commitments=...)` is the sole
interpreter of commitments; `BacktestOrchestrator` carries lifecycle state but
never reimplements risk formulas.  No notional `PositionSnapshot` and no fake
runtime STOP is ever created before an accepted fill (fake positions would
wrongly demand runtime STOP evidence via `_existing_open_risk`).

**F. Approval evidence on `RiskGateResult`.**  Additive defaulted fields
`quantity` (existing) and `nominal_stop_risk` (new) — both present on
APPROVED, both `None` on REJECTED (validated fail-closed in `__post_init__`).
The value is the gate's existing `candidate_trade_risk`
(`quantity × stop_distance × contract_multiplier`); the orchestrator never
recomputes it.

**G. Full-fill-only accepted-fill materialization.**  Current engine is
FULL_FILL_ONLY (`filled_quantity == order.quantity`).  On an accepted BUY
fill: the pending commitment and its entry association are released, the risk
state is advanced to the FILL-TIME RiskDay via the public
`RiskGate.advance_state` (first day rebases to `starting_capital`; same day
retains baseline/count; new day rebases start-of-day to prior closing equity
and resets daily counters; calendar-identity conflict fails closed) using
PRE-FILL net equity, then `record_entry_fill(entry_identity)` counts the first
accepted entry fill exactly once on the fill-time day (D1 approval → D2 fill
counts on D2), then `materialize_protective_plan(plan, *, run_identity,
quantity, book)` runs at the approved/full-filled quantity.  Protection NEVER
materializes at signal generation, plan creation, gate approval, or before an
accepted entry fill.

**H. Shared authoritative calendar.**  Gate-enabled runs require
`calendars: Mapping[str, WeekendCalendar]` keyed by `MarketProfile.calendar_id`
(deployment-supplied authoritative dates; no holiday downloads in engine core;
no hidden/default empty calendar; no first-calendar selection).  RiskDay is
derived as `RiskDay(calendar_identity=profile.calendar_id,
session_date=MarketSessionBoundary(profile, calendar=calendar).session_date(
decision_time))`.  `ExecutionEngine(..., calendars=...)` resolves the SAME
mapping by `calendar_id` and fails closed on a missing id; legacy
`calendars=None` preserves the default-boundary behavior.  The orchestrator
verifies at construction that a supplied execution engine resolves the SAME
`WeekendCalendar` instance for every used calendar_id (gate-enabled mismatch
fails closed).  Multi-calendar streams fail closed at the account RiskDay
layer (`invalid_risk_evidence`).

**I. Risk rejection channel.**  `OrchestrationResult.risk_rejections:
tuple[RiskGateResult, ...] = ()` (additive defaulted field; not part of
canonical result fingerprints).  An ordinary RiskGate rejection: no
`StrategyHaltError`, no `alert_and_halt`, no OrderRequest, no execution, no
accounting leg, no position, no commitment, no protective materialization.
Engine failure / `StructuredFailureResult` semantics stay separate.  Q65
cost-adjusted affordability remains at its existing fill-time location AFTER
gate sizing/approval and BEFORE `apply_execution`; RiskPolicy v3 capital basis
remains `snapshot.starting_capital` while Q56 `current_net_equity` is the
authoritative cost-inclusive net equity
(`CostAdjustedAccountProjection.cost_adjusted_equity`, §65); RiskPolicy v4
cost-adjusted capital basis remains DESIGN_LOCKED_IMPLEMENTATION_PENDING
(superseded by §64 implementation).

**J. Q62 same-timestamp ordering (gate-enabled).**  Active
`Q62StrategyScopedConfidence/v2` ranking is applied per decision-time candidate
batch: canonical strategy/version group ordering first, confidence descending
within the same strategy/version, then the canonical tie-break; candidates are
then RiskGate-evaluated ONE AT A TIME in rank order so each candidate sees the
risk/capital state (including newly created pending commitments) of the
candidates before it.  Legacy risk-deferred ordering is unchanged.

**K. `_exit_intent` symbol casefold correction (required by this wiring).**
Materialized protective exit orders now use `symbol=key.identity.instrument.
casefold()` to match the canonical intake/execution symbol convention
(`SignalIntake` stores `source_event.symbol.casefold()`; execution compares
`bar.symbol.casefold()` against the order symbol).  Without this, a
materialized protective order never matches a real bar at runtime evaluation
— the latent case mismatch was unreachable until gate-enabled orchestration
began evaluating materialized exits.  No other `engine/protective_plan.py`
semantics changed.

### 63.1 Owner-Locked Correction — Hard Daily Entry-Fill Cap (falsification-driven)

Owner decision (narrow production patch; no broad audit, no RiskPolicy v4, no
fill-after-the-fact rejection).  A temporary falsification test CONFIRMED a
real defect in the initial §63 wiring: with `max_daily_trades = 1`, two
pre-approved pending BUY entries (both approved on D1 when the daily count
was 0) could BOTH be accepted on D2, producing **2 accepted BUY entries on one
RiskDay against a hard cap of 1** (risk rejections: none).  The defect existed
because the daily-trade-count gate ran only at decision/approval time and
nothing accounted for the capacity that already-approved pending entries would
consume when they later filled.

Locked semantics:

- `RiskPolicy.max_daily_trades` is a HARD account-level maximum on first
  accepted logical entry fills per RiskDay.  Approval itself is NOT a trade;
  pending commitments NEVER increment `RiskGateState.daily_trade_count`;
  rejected/unfilled/cancelled orders and exits never count.
- Every active validated `PendingRiskCommitment` reserves exactly ONE future
  logical entry-fill capacity slot.  Eligibility for a new entry is:
  `state.daily_trade_count + number_of_active_pending_entry_commitments <
  policy.max_daily_trades`; otherwise the candidate is REJECTED with the
  existing `daily_trade_count_exceeded` reason (no new reason invented).  The
  candidate itself is not included until approved.
- Reservations persist across RiskDay boundaries: a new RiskDay resets the
  ACTUAL daily count via the existing `_derive_state` / `advance_state` rules,
  but pending entry reservations are NOT reset.  A pending order from D1 still
  consumes capacity on D2 until it terminally releases (expiry / terminal
  cancellation / Q65 or accounting rejection / accepted fill).  Terminal
  release frees the slot for a new candidate.
- No fill-after-the-fact rejection: the execution layer never reports FILLED
  while risk/accounting pretends the fill did not happen.  The hard cap is
  guaranteed BEFORE excessive pending exposure exists, at approval time.
- Accepted-fill lifecycle is unchanged: ownership accepted → pending
  commitment released → advance state to fill-time RiskDay →
  `record_entry_fill` exactly once.  This converts one reservation into one
  actual fill count without changing the combined used-capacity invariant
  (actual fills + active reservations never exceed `max_daily_trades`).

Implementation: the ONLY production change is the daily-trade-count eligibility
step inside `RiskGate.evaluate_pre_order` (step 9) — it now uses
`state.daily_trade_count + len(validated_commitments) >= max_daily_trades` to
reject.  `engine/orchestration.py` was NOT modified for this correction (the
commitment lifecycle already created commitments immediately after approval
and passed them to subsequent candidate evaluations, and already released them
at every terminal outcome).  `record_entry_fill` semantics, execution
semantics, RiskPolicy v3 schema, Q55/Q59/Q60, Q62 v2, Q63, Q64, Q65, calendar
contracts, `entry_intent_identity`, and protective materialization lifecycle
are unchanged.

`engine/risk_manager.py`, `engine/orchestration.py`, and
`engine/execution/engine.py` were modified by the §63 integration; the §63.1
correction modified `engine/risk_manager.py` only.  `engine/protective.py` was
NOT modified.

## 64. Owner-Locked Phase 3 — RiskPolicy v4 Cost-Adjusted-Equity Capital Basis + Runtime Risk-Fingerprint Binding

### 64.1 RiskPolicy v4 schema and capital-basis identity

- `sentinelx-risk-policy/v4` is the next explicit schema/version after v3.
  v3 remains the current fixed-capital schema with byte-identical fingerprints
  and economic semantics (a v3-versioned policy is restricted to
  `FixedCapitalBasis/v1`).
- v4 adds the explicit `risk_capital_basis_policy` field:
  - `FixedCapitalBasis/v1` — v3 behavior: Q55/Q59 denominator is the
    authoritative deployable capital input (`snapshot.starting_capital`).
  - `CostAdjustedEquityCapitalBasis/v1` — Q55 per-trade risk capital AND the
    Q59 aggregate portfolio-risk budget are computed against the
    authoritative `CostAdjustedAccountProjection.cost_adjusted_equity`
    (recognized costs only).
- The capital-basis field participates in the v4 fingerprint; v3 fingerprints
  are unchanged (the field is excluded under the v3 schema).  Unknown basis
  identities and v3-versioned cost-adjusted requests fail closed.

### 64.2 Evidence boundary — no circularity, no duplicated cost math

- `cost_adjusted_equity = snapshot.equity − recognized_cost` uses ONLY
  already-recognized evidence, never candidate quantity or candidate costs,
  so Q55 sizing has its denominator BEFORE quantity exists — no fixed-point
  solver, no iterative sizing.
- RiskGate consumes `CostAdjustedAccountProjection` as authoritative evidence
  (`cost_projection=` keyword) and never reproduces cost math.  Missing
  projection → `missing_cost_adjusted_equity_evidence`; zero/negative/non-
  finite equity → `invalid_cost_adjusted_equity`.
- Q65 affordability remains the single cost authority in the cost/projection
  layer (`available_buying_power`, unchanged location: accepted-fill time,
  before `PortfolioAccount.apply_execution`).  v4 does not create a second
  affordability rule.

### 64.3 Daily-loss and commitment semantics unchanged by the capital basis

- The Q56 daily-loss gate is a separate contract from the Q55/Q59 capital
  basis: the capital basis never alters the daily-loss evidence path.
- Q56 `current_net_equity` is the authoritative cost-inclusive net equity
  (`CostAdjustedAccountProjection.cost_adjusted_equity` = gross
  `AccountSnapshot.equity` minus already-recognized leg costs, applied exactly
  once through the projection/evidence layer; §65).  The capital basis (v3
  fixed / v4 cost-adjusted-equity) moves only the Q55/Q59 denominator, never
  the daily-loss comparison.
- PendingRiskCommitment `nominal_stop_risk` stays frozen at approval; only the
  Q59 denominator moves when equity changes.  Pending commitments remain
  non-economic (no cash/P&L/positions/trade count/protective exits).

### 64.4 Runtime/replay risk-fingerprint binding (approved OPTION A)

- Gate-enabled runs must carry the ACTIVE `RiskPolicy.fingerprint` in
  `RuntimeConfigurationSnapshot.risk` under the `config/v2` schema
  (`sentinelx-runtime-configuration/v2` fingerprint identity; v1 free-form
  fingerprints are never compared against v2 authoritative evidence).
- `risk-deferred` remains valid ONLY for explicit non-gated legacy runs.
- `BacktestOrchestrator` verifies equality at construction and FAILS CLOSED on
  mismatch — it never silently rewrites caller evidence.  A gate-enabled run
  never masquerades as risk-deferred; a mismatch is a reproducibility/
  configuration-integrity failure, never an ordinary risk rejection.
- Because `configuration.risk` already participates in
  `RuntimeConfigurationSnapshot.fingerprint` →
  `ReproducibilityManifest.manifest_fingerprint`, the binding propagates
  automatically into run/replay identity; no parallel `risk_fingerprint`
  field is added.

### 64.5 Unknown RiskPolicy version fail-closed (falsification-driven correction)

- The ONLY active `RiskPolicy.version` values are exactly `risk-policy/v3`
  and `risk-policy/v4`.  Any other value — future versions, malformed
  strings, suffix matches — FAILS CLOSED at construction with
  `unsupported RiskPolicy version`.
- The historical `sentinelx-risk-policy/v1` and `/v2` schema identities may
  remain as identity-history constants but never authorize constructing
  active policy objects with `risk-policy/v1` or `risk-policy/v2`.
- Semantic dispatch (v4 schema fingerprint, fixed-basis restriction) uses
  exact supported-version identity (`== risk-policy/v4`), never suffix
  matching, so `foo/v4` cannot inherit v4 semantics and unknown versions
  cannot silently inherit v3 semantics.
- Supported `risk-policy/v3` and `risk-policy/v4` fingerprints are
  BYTE-IDENTICAL before and after this hardening (verified by exact-value
  regression test); canonical schema names and field ordering unchanged.

Implementation: `engine/risk_manager.py` only (`SUPPORTED_RISK_POLICY_VERSIONS`
allow-list in `__post_init__`; exact-identity dispatch).  No Q55/Q59/Q65,
binding, replay, cost, execution, or protective-semantics change.

### 64.6 Real-cost end-to-end orchestration evidence (D5, P2 MANDATORY_BEFORE_PHASE_4)

- Orchestration-level proof that a REAL recognized transaction cost changes the
  v4 `CostAdjustedEquityCapitalBasis/v1` Q55/Q59 denominator and the FINAL
  `OrderRequest` carries that exact changed approved quantity is provided by
  the permanent paired regression
  `test_v4_real_recognized_cost_changes_end_to_end_order_quantity`
  (`tests/test_orchestration_risk_gate.py`).
- Proven chain (real gate-enabled `BacktestOrchestrator`, real FIXED-100
  `CostSchedule`, capital 100000, `per_trade_risk_pct=0.005`, stop distance
  10): accepted alpha fill -> actual `CostLegAssessment` total 100.00
  recognized -> gross `snapshot.equity` stays 100000.00 ->
  `cost_adjusted_equity` 99900.00 -> v4 risk capital 99900 x 0.005 = 499.5 ->
  raw quantity 499.5 / 10 = 49.95 -> floor to step 1 -> approved quantity 49
  -> beta `OrderRequest.quantity == 49`.  Zero-cost control: denominator
  100000.00 -> quantity 50.  The paired runs differ ONLY in the recognized-
  cost evidence; no second sizing authority exists.
- Q56 neutrality: recognized cost 100 = 0.1% of 100000, comfortably below the
  2% daily-loss limit (no `daily_loss_limit_exceeded` in this scenario); Q59
  budget and Q65 affordability are non-blocking at these magnitudes.  The
  D5 evidence is about the v4 Q55/Q59 capital basis, NOT the Q56 daily-loss
  gate.

### 65. Q56 Cost-Inclusive Net Equity (falsification-driven correction)

A gate-enabled orchestration falsification CONFIRMED that Q56 previously
compared `start_of_day_net_equity` against GROSS `snapshot.equity`, so
already-recognized transaction costs never contributed to the daily-loss
drawdown: a BUY was APPROVED when gross loss 1900 + recognized cost 100
reached the 2% threshold of 100000 (severity P1).

- **Q56 `current_net_equity` is cost-inclusive net equity.**  Both Q56 evidence
  paths now consume `CostAdjustedAccountProjection.cost_adjusted_equity`
  (gross `AccountSnapshot.equity` − already-recognized leg costs, applied
  exactly once through the authoritative projection/evidence layer):
  - normal pre-order gate evaluation: the SAME projection object built once
    per candidate supplies both `current_net_equity` and the v4 Q55/Q59
    `cost_projection` evidence (v3 ignores the projection for Q55/Q59 but Q56
    still receives cost-inclusive net equity);
  - fill-time RiskDay rollover (`RiskGate.advance_state`): the projection is
    built from the PRE-FILL snapshot and ONLY costs recognized before the
    current fill, so an accepted D1-approval → D2-fill seeds the D2
    start-of-day baseline with cost-inclusive pre-fill net equity.
- **`AccountSnapshot.equity` remains gross.**  `PortfolioAccount` accounting
  never applies transaction costs; recognized costs live exclusively in
  `CostLegAssessment` / `CostAdjustedAccountProjection` evidence.  No double
  subtraction: each recognized cost enters the net-equity view exactly once,
  inside the projection.
- **Pre-fill SOD baseline excludes the current fill's newly-recognized cost.**
  The accepted leg's cost is appended to the recognized-cost evidence only
  AFTER the fill-time `advance_state` call (inside `_record_accepted_leg`), so
  the new cost affects later `current_net_equity` on the fill-time RiskDay but
  never the start-of-day baseline used to begin that day.
- **Start-of-day semantics:** first RiskDay of a fresh run = starting capital;
  same RiskDay retains the fixed baseline; a new RiskDay reached by normal
  gate evaluation OR first by a pending accepted fill rebases to the
  authoritative cost-inclusive net equity at the transition (pre-fill for the
  fill-time path).  Prior days' recognized costs are therefore embedded in
  both the new baseline and later current net equity, so only new same-day
  economic change contributes to that day's loss.
- **Do NOT change:** Q55/Q57/Q58/Q59/Q60/Q62/Q63/Q64/Q65 semantics, RiskPolicy
  v3/v4 fingerprints, projection equations, portfolio accounting, protective
  lifecycle, order pricing, or calendar authority.

Implementation: `engine/orchestration.py` only (both Q56 evidence call
sites).  Permanent regressions in `tests/test_orchestration_risk_gate.py`:
same-day recognized-cost rejection at the 2% threshold; zero-cost control
pass; overnight fill-time rollover proving cost-inclusive pre-fill SOD;
cost-timing regression proving the new fill's cost never seeds the pre-fill
baseline.

### 66. Pending-Entry Q56 Pre-Execution Reauthorization (falsification-driven correction)

A gate-enabled orchestration falsification CONFIRMED that an already-APPROVED
pending BUY could execute AFTER the account had subsequently breached the
locked Q56 daily-loss limit: it FILLED @95, quantity 380, accounting ACCEPTED,
new position created, despite cost-inclusive daily loss 2000 >= 2000 (severity
P1).  Q56 is a DYNAMIC account-level hard entry permission.

- **Q56 approval is NOT permanent while an entry remains pending.**  If,
  before economic execution, ``daily_loss >= max_daily_loss_pct``, an
  outstanding gate-enabled BUY entry must no longer be permitted to create a
  new position.  Existing exits remain allowed.
- **Dynamic Q56-only reauthorization.**  ``RiskGate.
  evaluate_pending_entry_pre_execution(...)`` derives/advances the
  authoritative ``RiskGateState`` with the existing RiskDay rules, evaluates
  the SAME Q56 daily-loss contract via the single shared ``_daily_loss_breach``
  helper (byte-consistent with ``evaluate_pre_order``; no second formula), and
  returns existing ``RiskGateResult`` semantics with the existing reason
  ``daily_loss_limit_exceeded``.  It performs NO sizing and NO other
  strategy/order calculations: the pending order already carries its approved
  quantity, frozen entry identity, PendingRiskCommitment, frozen protective
  plan, planned order terms, and Q55/Q57/Q58/Q59/Q60 reservations.  The
  authorization-only APPROVED ``RiskGateResult`` carries neither
  ``quantity`` nor ``nominal_stop_risk`` (both-or-neither validation rule);
  sizing results from ``evaluate_pre_order`` always carry both.
- **Authoritative equity.**  The check consumes
  ``CostAdjustedAccountProjection.from_evidence(current_pre_execution_snapshot,
  already_recognized_leg_assessments).cost_adjusted_equity`` — gross
  ``AccountSnapshot.equity`` minus recognized costs applied exactly once;
  portfolio accounting is never mutated.
- **Pre-execution boundary and no look-ahead.**  The check runs in
  ``BacktestOrchestrator._evaluate_pending`` immediately BEFORE
  ``ExecutionEngine.evaluate`` for each gate-enabled pending BUY that has a
  matching bar.  It uses only the latest authoritative completed-bar account
  snapshot already available before the pending execution opportunity (the
  mark loop for the same bar runs later, so a same-bar close can never be used
  to manufacture a breach retroactively).  On REJECT the entry is terminally
  dropped: no execution evaluation, no FILLED result, no ``apply_execution``,
  no PositionKey ownership, no daily trade-count increment, no protective
  materialization, no recognized entry cost; the PendingRiskCommitment and its
  frozen PendingEntryAssociation are released deterministically and the
  rejection is recorded via the existing
  ``OrchestrationResult.risk_rejections`` channel with
  ``daily_loss_limit_exceeded`` (no StrategyHalt, no new reason).  The
  submitted OrderRequest remains in historical ``result.orders`` evidence only.
- **Unchanged by this correction:** pending Q57/Q58/Q59/Q60 reservations,
  Q65 fill-time affordability authority, max_daily_trades configuration,
  RiskPolicy v3/v4 fingerprints, and all §65 cost-inclusive Q56 semantics.
  Strategy Entry Validity (valid_for_bars / signal age / price drift /
  opposite-signal cancellation / strategy thesis invalidation) remains a
  separate Phase-4 concern and is NOT implemented here.

Implementation: `engine/risk_manager.py` (``RiskGateResult`` both-or-neither
validation, shared ``_daily_loss_breach`` helper, new
``evaluate_pending_entry_pre_execution``) and `engine/orchestration.py`
(pre-execution Q56 reauthorization in the pending loop).  Permanent
regressions in `tests/test_orchestration_risk_gate.py` (breach blocks
execution; rejection releases commitment/association proven by a later-day
re-approval; below-threshold control fills) and `tests/test_risk_gate.py`
(direct authorization API: approve/reject boundary, RiskDay rules,
fail-closed invalid evidence, single-formula agreement with
``evaluate_pre_order``).

## 67. Formal Phase-3 Closure Marker (owner-approved)

- **PHASE 3 VERIFIED_COMPLETE.**  Owner approval of the Phase-3 closure audit
  accepted; this marker records the formal closure only and does not rewrite
  any frozen decision.
- **Severity ledger at closure: P0/P1/P2 = 0/0/0.**  Q56 recognized-cost
  daily-loss correction (§65), Q56 pending-entry pre-execution
  reauthorization (§66), and the D5 v4 real-cost end-to-end order-quantity
  regression (§64.6) were each independently verified before closure.
- **Test baseline:** full suite = 857 passed, 1 skipped, 0 failures.
- **Next phase:** Phase-4 pre-implementation architecture/contract review
  (order abstraction / order lifecycle).  Phase 4 was NOT started during
  Phase-3 closure.  `max_daily_trades` remains configurable
  RiskPolicy/deployment configuration (value 10 is not a universal engine
  ceiling); strategy-owned Entry Validity / Invalidation (expiry /
  valid-for-bars / setup / price / opposite-signal / stale-pending
  cancellation) stays separate from RiskGate, and the Phase-3 Q56 pending
  pre-execution reauthorization remains intact (never replaced by
  strategy-validity logic).

## 68. Phase-4 Slice 1 — Pending-Entry Validity / Order Lifecycle (implemented)

Owner locks D1/D2/D3 and decision O1 from the Phase-4 pre-implementation
architecture review were implemented as Slice 1:

- **Separate strategy-owned capability `PendingEntryValidityPolicy/v1`**
  (`engine/orders/validity.py`): bound alongside the strategy on
  `StrategyBinding.entry_validity_policy` (default `None`).
  `StrategySignalGenerator/v1` is UNCHANGED — `generate_signal` remains the
  single strategy interface method and `interface_version` stays `"1.0"`.
  No provider bound ⇒ default semantics: pending entry remains
  strategy-valid, subject to existing mechanical lifecycle and RiskGate
  rules.
- **Spec freeze authority**: only the bound policy's `freeze_spec(...)`
  creates the immutable `EntryValiditySpec` from the logical entry context
  (planned terms + entry reference resolved once).  Slice-1 mechanical
  fields are ONLY `valid_until_timestamp` and `valid_through_session`
  (authoritative calendar identity + session date).  `valid_for_bars`
  remains DEFERRED_CORE (no frozen universal bar-count authority for
  multi-stream / multi-timeframe strategies).  The spec never depends on
  approved quantity, RiskGate sizing, fill price, or future market
  evidence.
- **`EntryValidityResult`**: VALID (reason None) or INVALID (deterministic
  non-empty strategy/lifecycle reason).  Engine risk reasons
  (`daily_loss_limit_exceeded`, `portfolio_risk_exceeded`, insufficient
  buying power) are FORBIDDEN here and remain owned by RiskGate /
  accounting.  CanonicalCodec-only identities.
- **Purity**: validity `evaluate` receives an isolated deep copy of the
  authoritative strategy state; any mutation is discarded.  Deepcopy
  failure fails closed (structured deterministic error).  Authoritative
  strategy state is mutated only through the existing `generate_signal`
  path.
- **No-lookahead**: at execution opportunity T the evaluator receives the
  retained MOST-RECENT PRE-T immutable `MarketDataView` (bars strictly
  before T) with the same data-delivery shape as `generate_signal`.  No
  same-bar look-ahead: a T close can never retroactively invalidate a
  fill eligible at T open.
- **Pre-execution ordering** (gate-enabled pending BUY): mechanical
  validity → strategy semantic validity → existing Phase-3 Q56
  `evaluate_pending_entry_pre_execution` → `ExecutionEngine.evaluate`.
  Any failing check terminally removes the entry with NO execution
  evaluation, NO fill, NO accounting position, NO entry cost, NO
  trade-count increment, NO protective materialization; the commitment
  and `PendingEntryAssociation` are released deterministically.
- **OrderLifecycle** (`engine/orders/lifecycle.py`): existing vocabulary
  preserved (CREATED / VALIDATED / QUEUED / CANCELLED / REJECTED /
  EXPIRED); ONLY `FILLED` added as a terminal state from QUEUED.  No
  SUBMITTED/PENDING duplicate.  `OrderLifecycleEvent` is additive
  one-authority-per-fact terminal evidence: strategy invalidation,
  mechanical expiry, DAY expiry, Q56, Q65, accounting rejection, and
  accepted fill each reference EXISTING authoritative evidence and never
  recompute reasons/formulas.  `OrchestrationResult.order_lifecycle` is an
  additive channel (no finalization-fingerprint change).
- **FILLED ownership boundary**: `ExecutionResult.FILLED` alone is NOT
  lifecycle FILLED — QUEUED→FILLED occurs only after Q65 and
  `PortfolioAccount.apply_execution` ACCEPTED (accepted accounting
  ownership).
- **Replacement**: no in-place OrderRequest mutation — old pending
  CANCELLED (commitment/association released), new SignalIntent → new
  entry identity → full normal planning / RiskGate approval / new
  commitment.
- **Opposite/new signal**: NO universal "new signal cancels old pending"
  engine rule; semantic invalidation is strategy-owned.  A signal from
  completed bar T cannot retroactively cancel an order eligible at T
  open; it may affect T+1+ opportunities.
- **STOP / STOP_LIMIT**: remain FAIL-CLOSED in gate-enabled deployment
  (owner decision D1) — unchanged.
- **Legacy path**: `risk-deferred` unchanged — no validity policy,
  spec, or lifecycle handling required (owner decision D3).
- **O1 run-level binding**: `RuntimeConfigurationSnapshot/v3` adds the
  canonical strategy-keyed `entry_validity` binding evidence
  (`entry_validity_binding_fingerprint`, sorted by strategy_id, `None`
  encoded distinctly from any provider identity).  v2 historical
  replay identity is UNCHANGED (the new field exists only under v3);
  validity-enabled runs require v3 and fail closed on mismatch.
  `sentinelx-entry-intent/v1` is unchanged — ordinary validity
  re-evaluation never creates a new entry identity.

Test evidence (Slice 1): full suite = 886 passed, 1 skipped, 0 failures
(baseline 857 → +29 permanent tests: lifecycle FILLED/events in
test_orders.py, runtime-config v3 + binding-fingerprint tests in
test_reproducibility.py, and the orchestration scenarios in
test_orchestration_risk_gate.py covering default-preservation, VALID /
INVALID, cancellation-before-execution, terminal-invalidation, commitment/
association release, economic neutrality, Q56/Q65/accounting lifecycle
causes, DAY expiry, valid_until boundaries, valid_through_session
same/cross-session, no-lookahead bounded view, state-copy purity, multi-
strategy and multi-identity isolation, replacement, D1→D2 GTC pass/fail,
STOP/STOP_LIMIT fail-closed, and legacy unchanged).

## 69. Phase-4 Slice-1 Provenance Correction (P2-A / P2-D)

A temporary falsification audit independently confirmed two P2 provenance
gaps in the Slice-1 validity/lifecycle evidence (both corrected; no
RiskGate / accounting / execution / protective / StrategySignalGenerator
changes):

- **P2-A — returned result policy identity must fail closed.**  A
  `PendingEntryValidityPolicy` is bound to exactly one identity, so the
  engine must never consume a result claiming a DIFFERENT policy identity.
  Immediately after `validity_policy.evaluate(...)` and the
  `EntryValidityResult` type check, orchestration now enforces:

  ```
  validity_result.policy_identity == validity_policy.policy_identity
      == association.validity_policy_identity
  ```

  BEFORE the VALID/INVALID outcome is consumed, before strategy
  invalidation / Q56 / execution / accounting / lifecycle-cause creation.
  A mismatched result is NOT authoritative evidence: a mismatched INVALID
  is never classified as STRATEGY_INVALIDATION and a mismatched VALID
  never proceeds toward execution.  Mismatch raises the existing
  deterministic orchestration invariant channel (`ValueError` with an
  explicit provenance message) — never a new trading-risk rejection
  reason, never a RiskGate rule.  The association identity check covers
  the case where the runtime policy identity drifts from the
  approval-time frozen identity.
- **P2-D — entry-scoped Q56 rejection evidence.**  `RiskGateResult` is
  generic risk-engine output and remains UNCHANGED (no `entry_identity`
  added).  The orchestration layer owns `entry_identity`, so the exact
  linkage is created at the orchestration evidence layer via the new
  additive immutable `EntryRiskRejectionEvidence`
  (`engine/orchestration.py`):

  ```
  EntryRiskRejectionEvidence:
      entry_identity
      decision_timestamp
      risk_result            # authoritative RiskGateResult
      evidence_identity      # sentinelx-entry-risk-rejection/v1
                             # canonical fingerprint over entry +
                             # decision_time + outcome + reason
  ```

  `entry_identity` participates in the canonical evidence identity, so two
  distinct pending entries rejected with the same reason at the same
  decision time produce DISTINCT evidence identities — no positional
  inference required.  The Q56 lifecycle `cause_reference` now points at
  that entry-scoped evidence identity instead of the old shared
  reason-only synthetic hash.  `OrchestrationResult` gains an additive
  `entry_risk_rejections` channel alongside the unchanged raw
  `risk_rejections` tuple (existing API preserved; `RiskGateResult`
  untouched).
- **Other reason-only cause references (DAY_EXPIRY, Q65_REJECTION,
  ACCOUNTING_REJECTION) exhibit the same mechanical multi-event ambiguity
  but are OUT OF SCOPE for this patch** (owner default scope: A/A2 +
  Q56).  The same small additive evidence mechanism can cover them if a
  future owner decision extends it.

Identity semantics: `EntryValiditySpec.spec_identity`,
`EntryValidityResult.evidence_identity`, `OrderLifecycleEvent.event_identity`,
`sentinelx-entry-intent/v1`, and `RuntimeConfigurationSnapshot/v2` are
UNCHANGED.  v3 validity binding remains deterministic; correct-policy runs
replay identically and policy mismatch fails deterministically.

Test evidence: full suite = 893 passed, 1 skipped, 0 failures (886 → +7
permanent tests in test_orchestration_risk_gate.py: mismatched-VALID and
mismatched-INVALID fail closed, matched-VALID/matched-INVALID controls
preserved, association-identity mismatch fail-closed, single-entry Q56
entry-scoped linkage, and two-pending-entry Q56 linkage with distinct
evidence identities and per-entry cause references).

## 70. Formal Phase-4 Slice-1 Closure Marker (owner/independent review)

PHASE-4 SLICE 1 VERIFIED_COMPLETE — P0/P1/P2: 0 / 0 / 0.  Latest
independent repository verification: 893 passed, 1 skipped, 0 failures
(software regression evidence only).  Closed contracts: separate
`PendingEntryValidityPolicy/v1`; `StrategySignalGenerator/v1` unchanged;
mechanical validity (`valid_until_timestamp` / `valid_through_session`);
strategy-semantic validity; PRE-T no-lookahead; validity evaluator state
isolation; pending cleanup (commitment/association release); lifecycle
terminal semantics (QUEUED → FILLED | CANCELLED | REJECTED | EXPIRED,
FILLED only after accepted accounting); Phase-3 Q56 preservation;
RuntimeConfigurationSnapshot/v3 validity binding (v2 identity preserved);
P2-A provenance fail-closed (result identity == provider identity ==
association identity before outcome consumption); P2-D Q56 entry-scoped
rejection evidence; DAY/Q65/accounting terminal provenance HOLDS through
the retained evidence graph (entry_identity + retained
ExecutionResult/AccountingResult + run stream binding) — reason-only cause
references there are not a defect; entry-distinct self-contained references
are optional P3 defense-in-depth, not mandatory Slice-2 work.  Frozen
decisions above are not rewritten.

## 71. Phase-4 Slice 2 — Idempotency / Duplicate-Order Protection (owner lock + coverage record)

**Owner lock — authoritative backtest-core idempotency key:**
`sentinelx-entry-intent/v1` (via `engine.risk_manager.entry_intent_identity`)
is the sole logical-entry identity.  NO `OrderRequest.id`, `OrderRequest.identity`,
`request_id`, UUID, random identity, or parallel fingerprint is added.
Future broker/exchange order IDs are a DIFFERENT semantic entity and belong
only to future broker-adapter/live evidence.  No additional identity schema
or version is introduced.

**Frozen semantics — run-lifetime order-creation idempotency:**  once
logical entry identity E has created an OrderRequest, E MUST NOT create a
second OrderRequest in that same run.  The current architecture achieves this
structurally, without a historical seen-set:

- Identity is a canonical fingerprint over (strategy_id, strategy_version,
  full InstrumentIdentity, timeframe, originating_timestamp).  The strategy
  cannot forge the timestamp: `SignalIntake` binds `originating_timestamp`
  to the source-event bar timestamp, and per-stream bar timestamps strictly
  increase within a run (the coordinator rejects duplicate (stream, timestamp)
  events at the input boundary).
- Active duplicate: while a `PendingEntryAssociation` exists, presenting the
  exact same identity fails closed deterministically with
  `ValueError("duplicate logical entry identity within the same run")`
  (orchestration.py duplicate check) — no second RiskGate approval, no second
  OrderRequest, no second lifecycle chain, no duplicate economic position.
- Legitimate re-entry: a new source-event `originating_timestamp` produces a
  new `sentinelx-entry-intent/v1` identity, a fresh RiskGate approval, a fresh
  OrderRequest, and a fresh commitment/lifecycle.  Idempotency does NOT
  suppress a legitimate new trading opportunity.
- Cross-run replay: the same deterministic input may recreate the same
  deterministic identities in a fresh run.  Runs are independent; idempotency
  scope is ONE run, never process-global uniqueness.

**MANDATORY end-of-data qualification (do not over-broaden):**  for a
MID-RUN terminal release after which later decision opportunities can still
occur, the pending entry reaches its terminal path through a matching bar on
its order/source stream; that matching bar advances the source stream, so any
later legitimate BUY carries a newer originating_timestamp and therefore a new
entry identity.  END OF DATA is different: end-of-data cleanup may release the
pending association without a matching bar, but this happens AFTER the final
decision opportunity, so there is no later same-run opportunity to present
that identity again.

**Active same-E behavior is preserved as-is:** the deterministic
`ValueError("duplicate logical entry identity within the same run")` is the
accepted fail-closed Slice-2 behavior.  It is NOT converted into a silent
skip, RiskGate rejection, StrategyHalt, or lifecycle cancellation during this
slice.

**No production implementation change was required.**  Six permanent
regressions added to `tests/test_orchestration_risk_gate.py` (active-duplicate
fail-closed determinism; terminal-release-then-re-signal new identity; distinct
legitimate re-entry with fill; GTC multi-bar no re-send; cross-run replay
independence; duplicate public input rejected at the coordinator boundary).
Test evidence: full suite = 899 passed, 1 skipped, 0 failures (893 → +6
permanent Slice-2 tests; skip = pre-existing openpyxl import skip).  The
899 test count is SOFTWARE REGRESSION EVIDENCE ONLY — never market validity
or trading-strategy profitability evidence.

## 72. Formal Phase-4 Slice-2 Closure Marker (owner / independent review)

PHASE-4 SLICE 2 — VERIFIED_COMPLETE — P0/P1/P2: 0 / 0 / 0.
Independent regression baseline: 899 passed / 1 skipped / 0 failures
(software regression/contract evidence only — never market validity,
strategy profitability, or live-trading performance evidence).

Closed contracts:

- `sentinelx-entry-intent/v1` authoritative backtest-core idempotency key;
  no OrderRequest identity added (no `OrderRequest.id`/`identity`, no
  `request_id`, no UUID, no parallel fingerprint).
- Run-lifetime order-creation idempotency: once E creates an OrderRequest,
  E cannot create a second OrderRequest in that same run.
- Active same-E duplicate: deterministic fail-closed
  (`ValueError("duplicate logical entry identity within the same run")`),
  preserved as-is.
- Structural post-terminal uniqueness: identity embeds the source-event
  `originating_timestamp`; per-stream bar timestamps strictly increase.
- Legitimate re-entry receives a new identity (new `originating_timestamp`),
  fresh RiskGate approval, fresh OrderRequest.
- GTC pending evaluation does not resend the logical order (one OrderRequest
  per identity).
- Cross-run independence: identical deterministic input may recreate the
  same deterministic identities; idempotency scope is one run, never
  process-global uniqueness.
- Coordinator duplicate-input rejection: duplicate same-stream/same-timestamp
  public market input fails closed at the coordinator boundary.
- End-of-data qualification: MID-RUN terminal release requires a matching
  order/source-stream bar that advances the source stream; END OF DATA may
  release without a matching bar but occurs AFTER the final decision
  opportunity, so no later same-run re-presentation exists.
- No production behavior change was required; STOP/STOP_LIMIT remain
  fail-closed and were NOT changed.

§71 and all earlier frozen decisions are NOT rewritten.  The remaining
mandatory Phase-4 order-type gap — gate-enabled STOP / STOP_LIMIT activation
— remains BLOCKED on owner decision O2 (authoritative PRE-ENTRY RiskGate
entry-reference price for STOP and STOP_LIMIT) and is NOT resolved by this
closure.

## 73. Owner Decision O2 — Gate-Enabled STOP / STOP_LIMIT Entry Reference

OWNER DECISION O2 IS NOW MADE.  Pre-implementation preflight (read-only
source audit) recorded below.  STOP / STOP_LIMIT are NOT activated by this
decision; this section records the locked entry-reference authority only.

**Authoritative planned RiskGate / protective entry references (gate-enabled
BUY-to-open):**

- MARKET → `source_bar.close` (UNCHANGED / ALREADY FROZEN)
- LIMIT → `planned.limit_price` (UNCHANGED / ALREADY FROZEN)
- STOP → `planned.stop_price` (NEW O2 LOCK)
- STOP_LIMIT → `planned.limit_price` (NEW O2 LOCK; `planned.stop_price` is
  the ACTIVATION/TRIGGER level only — never the RiskGate entry reference)

**Owner locks (16):**

1. Single planned-reference authority: the exact SAME reference feeds
   RiskGate `evaluate_pre_order(entry_price=...)` AND
   `ProtectivePlanPolicy.plan_for(reference_price=...)` — resolved exactly
   once by `SignalToOrderPolicy.planned_terms` / `_gate_entry_reference`;
   no double resolution, no second price authority.
2. No lookahead: the reference exists at order-planning time from completed
   decision-time evidence; never future next-bar open / actual fill /
   intrabar / slippage / lower-TF / broker acknowledgment.
3. No actual-fill-based re-sizing: approved quantity is never recomputed
   from fill price; no second sizing authority.
4. No protective-plan regeneration from actual fill; frozen plan unchanged.
5. Q65 remains the fill-time actual-fill affordability authority (after
   ExecutionEngine fill candidate, before ownership acceptance) — never
   moved into pre-order sizing, never duplicated, never replaced by
   planned-price affordability.
6. STOP gap fill may differ from `planned.stop_price` under existing
   execution semantics (e.g., planned stop 100, gap open 105 → fill at
   open 105 per existing rules); no post-fill recalculation, no max-gap
   formula, no guessed slippage cap.
7. STOP_LIMIT BUY limit protection remains authoritative: accepted BUY fill
   MUST NOT exceed `planned.limit_price` under any current legal path.
   Preflight PROVEN from current source: `_stop_limit_basis` caps basis at
   the limit (open ≤ limit → open; open > limit → limit only if low ≤
   limit; intrabar → stop ≤ limit when limit ≥ stop, else no assumed
   fill) AND the post-slippage clamp
   `min(fill_price, limit_price)` for BUY LIMIT/STOP_LIMIT
   (`engine/execution/engine.py`) guarantees the accepted fill never
   exceeds the limit even under adverse slippage.  PROVEN by current
   permanent tests (`test_stop_limit_uses_only_unambiguous_available_ohlc_evidence`,
   `test_zero_slippage_is_identified_and_nonzero_models_cannot_break_limit_protection`).
8. STOP_LIMIT same-bar ambiguity remains conservative: no lower-timeframe
   resolver exists (`ExecutionEngine.lower_timeframe_resolver_available is
   False`); ambiguous intrabar trigger → NO ASSUMED FILL; no optimistic
   sequencing; no future lower-TF bars.
9. STOP trigger occurrence is NOT ownership, trade-count increment, or
   protection materialization.
10. Triggered-but-unfilled STOP_LIMIT remains pending under ordinary TIF
    semantics (DAY/GTC); no STOP_LIMIT-specific timeout invented.
11. Terminal lifecycle must release `PendingRiskCommitment` exactly once
    (existing `_release_commitment` on EXPIRED / CANCELLED / REJECTED /
    accepted FILLED / end-of-data terminal cleanup); no stranded capacity.
    Preflight: DAY expiry and GTC end-of-data paths already release
    exactly once through existing generic lifecycle; no new mechanism
    needed.
12. Scope: current LONG BUY-to-open deployment only; SHORT/SELL-to-open,
    naked short, future LONG_SHORT, and short option writing are NOT
    covered by O2 (current SELL remains close/reduce of owned LONG).
13. Legacy risk-deferred orchestration unchanged; no O2 RiskGate path
    inserted into legacy runs; `rule.quantity` legacy authority preserved.
14. Protective exits (runtime STOP_LOSS / TARGET / trailing) unchanged.
15. Future short-entry order geometry requires a separate owner decision.
16. STOP_LIMIT stop/limit GEOMETRY is NOT implicitly owner-locked by O2.
    Preflight determination: current order/execution contracts ALREADY
    constrain the relationship deterministically — OrderRequest validation
    requires positive finite stop and limit; intrabar activation requires
    `limit_price >= stop_price` for an assumed fill at the stop, while
    `limit_price < stop_price` is deterministic NO-ASSUMED-FILL intrabar
    and gap-through fills stay capped at the limit or no-fill.  Every
    currently legal geometry is deterministic, BUY-limit-protected,
    lifecycle-safe, and reservation-safe.  **O3 is NOT required.**  A
    `limit_price >= stop_price` recommendation may be discussed later but
    is NOT silently adopted.

**Preflight outcome:** O2 OWNER_LOCKED — IMPLEMENTATION_READY.

Preflight basis: `_gate_entry_reference` (`engine/orchestration.py`) and the
construction-time gate rule check are the only production surfaces requiring
controlled extension at implementation time; RiskGate consumes one
authoritative Decimal reference and needs no change; execution STOP/STOP_LIMIT
semantics, limit protection, ambiguity conservatism, DAY/GTC/end-of-data
lifecycle, and reservation cleanup all hold from current source and current
permanent tests.  No lookahead, no new replay ambiguity (order type and
planned prices already participate in `SignalToOrderPolicy.tier1_identity`
and the manifest execution-policy binding; no schema bump required —
RuntimeConfigurationSnapshot/v2/v3, RiskPolicy, and `sentinelx-entry-intent/v1`
identities unchanged).  STOP/STOP_LIMIT are NOT activated by this section.

## 74. Owner Decision O4 — Persistent STOP_LIMIT Activation State

**Controlled implementation task.**  Owner O4 is LOCKED.  The temporary O2
STOP_LIMIT persistent-trigger-state falsification returned classification **B**
(STOP_LIMIT TRIGGER STATE IS NOT PERSISTED — EXECUTION CONTRACT GAP
CONFIRMED; P1 = 1): a STOP_LIMIT that authoritatively triggered on BAR1 with
an unreachable LIMIT was evaluated from scratch on BAR2, so a later
limit-executable bar (open <= limit, high < stop) returned UNFILLED instead of
filling as an active LIMIT.  Severity recorded: P0 = 0, P1 = 1, P2 = 0.

Falsification evidence (engine/execution/engine.py + engine/execution/model.py
+ engine/orchestration.py + tests/test_execution.py + tests/test_orchestration_risk_gate.py):

- BUY STOP_LIMIT stop=100 limit=99 GTC; BAR1 open=105 low=101 → STOP
  authoritatively triggered (open >= stop), limit unreachable (low > limit) →
  UNFILLED; BAR2 open=98 high=99 → limit executable, stop not newly satisfied
  → pre-O4 engine returned UNFILLED (trigger forgotten).  After O4: BAR2
  FILLED at 98 as an already-active LIMIT.
- No activation state existed anywhere: not in OrderRequest (immutable),
  not in ExecutionResult, not in orchestration pending state, no
  STOP_TRIGGERED/ACTIVATED lifecycle state, ExecutionEngine had no per-order
  memory.

**O4 core semantic lock.**  A STOP_LIMIT order has two distinct execution
substates: **NOT_YET_ACTIVATED** and **ACTIVATED_BUT_UNFILLED**.  Once an
eligible real execution bar authoritatively triggers the STOP, activation is
**MONOTONIC**: it never reverts to NOT_YET_ACTIVATED, and subsequent eligible
bars evaluate the order using **LIMIT semantics only** — the STOP trigger is
NOT required again.  The activated order stays live until the existing
terminal contract reaches FILLED / EXPIRED / CANCELLED / REJECTED /
deterministic end-of-data termination.

**State authority.**  ExecutionEngine remains deterministic and stateless
across calls: it owns STOP-trigger detection and same-bar fill determination
and produces immutable activation evidence; orchestration pending state stores
the evidence with the pending executable and passes it back into the next
`ExecutionEngine.evaluate` call; ExecutionEngine consumes explicit prior
activation evidence and evaluates an already-activated STOP_LIMIT as an active
LIMIT.  No STOP-trigger formula is duplicated inside orchestration; no hidden
mutable per-order dictionary exists inside ExecutionEngine.

**Immutable activation evidence.**  New frozen type
`StopLimitActivationEvidence` (`engine/execution/model.py`):
`activation_bar_timestamp` (timezone-aware), `activation_price` (finite,
positive; OPEN/GAP trigger uses the existing trigger basis e.g. bar.open,
INTRABAR uses the order stop price), `activation_basis` (`OPEN` |
`INTRABAR_STOP_TOUCH`).  No random id, UUID, Python hash, duplicated entry
identity, or duplicated strategy/instrument identity.  Evidence is valid only
with STOP_LIMIT orders (fail-closed otherwise) and is immutable once created.
`ExecutionResult.stop_limit_activation: StopLimitActivationEvidence | None =
None` is an additive typed field: never-triggered UNFILLED → None; trigger +
same-bar FILLED → newly-created evidence; trigger + UNFILLED → newly-created
evidence; already-activated + later UNFILLED/FILLED → same original evidence
preserved; already-activated + EXPIRED / GTC end-of-data → evidence retained in
the terminal execution evidence.

**Public API.**  Additive extension, existing callers remain valid:
`evaluate(order, bar, market_profile, *, stop_limit_activation=None)` and
`end_of_data(order, *, stop_limit_activation=None)`.  Identical (order, bar,
profile, activation evidence) inputs produce identical results regardless of
engine instance reuse.

**BUY activation semantics (activation None).**  A: OPEN/GAP trigger
(`bar.open >= stop`) is AUTHORITATIVE → create activation evidence, then
evaluate LIMIT eligibility on the same bar with the existing BUY LIMIT basis
(fill if executable, else UNFILLED WITH activation evidence that persists to
future bars).  B: no trigger (`bar.high < stop`) → UNFILLED, activation None.
C: INTRABAR stop touch (`bar.open < stop <= bar.high`) → activation is
authoritative; same-bar FILL stays governed by the existing conservative
ambiguity rule (no lower-TF resolver exists, `lower_timeframe_resolver_available
is False`): NO-ASSUMED-FILL does NOT mean NO-ACTIVATION — ambiguous intrabar
returns UNFILLED WITH activation evidence, and later bars evaluate the order
as an active LIMIT.

**Already-activated BUY STOP_LIMIT.**  When activation evidence is present, the
STOP trigger is NOT inspected again for fill eligibility; the original LIMIT is
evaluated with the existing BUY LIMIT basis.  Critical regression: stop=100
limit=99, BAR1 open=105/low=101 → activate + UNFILLED; BAR2 open=98/high=99 →
FILLED at 98 (pre-slippage).  Post-slippage BUY limit protection remains
`min(fill_price, limit_price)` (final fill <= 99).

**SELL / exit symmetry.**  ExecutionEngine STOP_LIMIT semantics are generic;
no BUY-only hidden execution state.  SELL STOP_LIMIT authoritative activation
follows the existing SELL stop logic (`open <= stop`, or intrabar low reaches
stop); once activated, later bars evaluate under SELL LIMIT semantics without
re-triggering.  Existing SELL limit protection remains authoritative (accepted
SELL fill is never worse than its limit under the existing engine rule).  This
repairs generic execution semantics only and does NOT authorize naked short
entry.

**Lower-timeframe / same-bar ambiguity.**  Frozen policy preserved:
authoritative synchronized lower-TF evidence first IF a resolver exists
(`lower_timeframe_resolver_available = False` today; no resolver added in this
task); otherwise NO ASSUMED SAME-BAR FILL.  TRIGGER OCCURRENCE and SAME-BAR
FILL SEQUENCE are distinct questions: if OHLC authoritatively proves the STOP
touched, activation is recorded even when same-bar fill is not assumed, and the
activation persists into future bars.

**Ineligible / synthetic bars.**  An ineligible execution opportunity does NOT
newly activate a STOP_LIMIT; an already-activated STOP_LIMIT evaluated against
an ineligible/synthetic bar keeps its activation evidence unchanged (the bar
must not erase activation).

**DAY / GTC / END OF DATA.**  DAY: an activated-but-unfilled DAY STOP_LIMIT
remains an active LIMIT during the same valid session; at ordinary DAY
terminal expiry → EXPIRED with no later fill; activation evidence may remain
attached to the terminal evidence for audit; no STOP_LIMIT-specific expiry
mechanism.  GTC: activation persists across sessions (no re-trigger); the
active LIMIT stays live until fill/cancel/end-of-data per existing GTC
semantics.  END OF DATA: generic end-of-data terminal handling remains; no
stranded pending state, no duplicate terminal transition.

**Orchestration pending state.**  The tuple-only pending representation now
carries a fourth element: the private pending-executable record is
`(order, source_stream, entry_identity, stop_limit_activation)`.  The pending
execution record owns activation; `PendingEntryAssociation` continues to own
the gate association, frozen protective plan, approved quantity, entry
reference, and validity provenance — activation is NOT duplicated into it.
On UNFILLED the survivor carries the activation evidence returned by
ExecutionEngine; on INELIGIBLE it retains prior activation unchanged; on
FILLED/EXPIRED/other terminal the pending state disappears normally.

**Legacy + future gate scope.**  The O4 fix applies to GENERIC STOP_LIMIT
execution, therefore it also corrects legacy risk-deferred STOP_LIMIT
execution (intentional — the incorrect trigger-forgotten behavior is not
preserved); legacy semantics outside this exact cross-bar activation issue are
unchanged.  Gate-enabled STOP/STOP_LIMIT MUST STILL FAIL CLOSED after O4 — the
O2 construction restriction is NOT relaxed; O4 repairs execution semantics
first, and O2 gate activation is a separate later task after independent O4
verification.

**Risk / commitment scope.**  RiskGate, Q55/Q56/Q57/Q58/Q59/Q60/Q63/Q64/Q65
are NOT modified.  O4 execution activation is NOT risk approval: trigger
occurrence does not increment trade count, create a position, consume cash,
materialize protection, or alter approved quantity.  When O2 is later
activated, the commitment remains reserved while the activated STOP_LIMIT is
legitimately pending.

**Protective plan.**  No protective-plan regeneration at activation or at
actual fill; O2 reference semantics unchanged (STOP_LIMIT RiskGate/protective
planned entry reference remains `planned.limit_price` when O2 is later
activated).

**Reproducibility.**  Reproducibility preflight: the O4 semantic change is
distinguished in replay identity by the EXISTING Tier-1
`SourceIdentityPolicy/v1` source binding (engine/**/*.py content bytes →
`source.fingerprint` → `manifest_fingerprint`), so a changed ExecutionEngine
semantic is a changed logical run without any new identity authority.  No
`RuntimeConfigurationSnapshot` schema bump; `RiskPolicy`, `sentinelx-entry-intent/v1`,
`SignalToOrderPolicy.tier1_identity`, and the manifest execution-policy binding
are unchanged.  `StopLimitActivationEvidence` participates in result evidence
only (deterministic execution evidence), never in manifest identity.  No
`engine/reproducibility/model.py` change required.

**No new lifecycle state.**  `OrderLifecycleState` is NOT extended:
activation is execution substate/evidence; lifecycle remains
CREATED/VALIDATED/QUEUED + true terminal states as frozen.

**OrderRequest identity unchanged.**  No `OrderRequest.id`/`identity`/
activation/triggered field; `sentinelx-entry-intent/v1` remains the sole
backtest-core logical-entry/idempotency key.  Activation is execution-state
evidence, not a new logical order.

**Tests (16 permanent).**  `tests/test_execution.py`: never-triggered control
(UNFILLED, activation None); same-bar gap activation + fill; CRITICAL cross-bar
persistence (stop=100/limit=99, BAR1 105→activate+UNFILLED, BAR2 98→FILLED
without re-trigger); limit-above-stop persistence; intrabar ambiguity retains
activation without same-bar fill; activation monotonic; adverse-slippage
limit protection after persistent activation; ineligible/synthetic bar
preserves activation; DAY active-limit + next-session expiry; GTC
cross-session persistence; GTC end-of-data provenance; SELL cross-bar
persistence; activation evidence on non-STOP_LIMIT fails closed; invalid
activation evidence fails closed; MARKET/LIMIT/STOP regression unchanged.
`tests/test_orchestration_risk_gate.py`: legacy risk-deferred STOP_LIMIT
cross-bar regression (one OrderRequest, BAR1 UNFILLED + activation persisted,
BAR2 FILLED at 98 via active-LIMIT semantics, no resend, no duplicate
lifecycle) + gate-enabled STOP/STOP_LIMIT construction STILL fails closed
(O2 not implemented).

**Verification.**  py_compile of the four changed production modules — PASS.
Explicit O4 tests — 16 passed.  Focused `tests/test_execution.py` — 55 passed.
Integration `tests/test_execution.py tests/test_backtest_integration.py
tests/test_orchestration_risk_gate.py tests/test_orders.py` — 185 passed.
Regression `tests/test_execution.py tests/test_orders.py
tests/test_backtest_integration.py tests/test_orchestration_risk_gate.py
tests/test_reproducibility.py tests/test_risk_gate.py tests/test_protective.py
tests/test_protective_plan.py` — 383 passed.  FULL SUITE `python -m pytest -q`
— **915 passed, 1 skipped, 0 failures** (pre-O4 baseline 899 passed / 1
skipped / 0 failures; +16 permanent tests).  Test counts are regression
/contract evidence only — never market-validity or profitability evidence.

O4 is AGENT_VERIFIED / PENDING_INDEPENDENT_VERIFICATION.  O2 gate-enabled
STOP/STOP_LIMIT activation remains FAIL-CLOSED.

## 75. Owner Decision O5 — Execution-Evidence V1/V2 Collection Routing

**O4 P2 repair (P2 falsification → evidence identity repair).**

O5 routing lock:

- `sentinelx-execution-evidence/v1` frozen — byte-for-byte unchanged.
- `sentinelx-execution-evidence/v2` added — activation-aware.
- Collection-level routing: IF ZERO executions carry non-None
  `StopLimitActivationEvidence` → v1; IF ONE OR MORE → v2.
- Evidence-shape routing, NOT historical-run detection.
- v2 binds activation component for EVERY execution:
  `("NONE",)` or `("PRESENT", activation_bar_timestamp,
  activation_price, activation_basis)`.
- Mixed collection (MARKET no-activation + STOP_LIMIT activation) →
  entire collection v2; MARKET contributes `("NONE",)`.
- v2 field order preserves v1 fields exactly (1–11) then appends (12).
- `SourceIdentityPolicy/v1` unchanged.
- `SuccessfulResult` schema unchanged.
- Manifest/config unchanged.
- O4 runtime files unchanged (`engine/execution/model.py`,
  `engine/execution/engine.py`, `engine/orchestration.py`).
- O2 STOP/STOP_LIMIT gate activation remains FAIL-CLOSED.

P2 repair evidence: temporary falsification proved v1 collides activated
vs never-activated UNFILLED results; v2 repairs the collision; v1
fingerprints remain byte-stable for non-activation evidence.

12 permanent tests (A–L) added covering:

- v1 locked fixture byte-stability
- v1 collision preservation
- v2 collision repair
- owner-routed selection
- activation timestamp/price/basis provenance
- v2 determinism
- mixed collection binding
- order-independent collection identity
- real finalization path v2 selection
- real replay localization to EXECUTION

Full suite: 927 passed / 1 skipped / 0 failures.

P0 = 0, P1 = 0, P2 = 0 (agent-side).

## 76. Formal Phase-4 O4/O5 Closure Marker (Owner / Independent Review)

PHASE-4 O4 (PERSISTENT STOP_LIMIT ACTIVATION EXECUTION CONTRACT) AND O5
(EXECUTION-EVIDENCE V2 COLLECTION ROUTING P2 REPAIR) ARE FORMALLY
VERIFIED_COMPLETE.

P0 / P1 / P2: 0 / 0 / 0.

Owner-run independent verification evidence:
- Full repository test suite: 927 passed, 1 skipped in 21.44s
- 0 failures
- PowerShell verification guard: `O4/O5 INDEPENDENT VERIFICATION PASSED`
- Software regression and contract evidence only — never market validity,
  strategy profitability, or live-trading performance evidence.

Closed contracts:

- O4 Persistent STOP_LIMIT Activation (§74):
  - STOP_LIMIT orders have two execution substates: NOT_YET_ACTIVATED and
    ACTIVATED_BUT_UNFILLED.
  - Activation is monotonic: once authoritatively triggered, subsequent bars
    evaluate under LIMIT semantics only (STOP trigger is never re-required).
  - State authority: ExecutionEngine remains deterministic/stateless and
    produces immutable `StopLimitActivationEvidence` (activation_bar_timestamp,
    activation_price, activation_basis OPEN | INTRABAR_STOP_TOUCH).
  - Orchestration pending state stores `stop_limit_activation` and passes it
    back to `ExecutionEngine.evaluate`.
  - Generic BUY and SELL execution symmetry; post-slippage BUY/SELL limit
    protection preserved (`min(fill_price, limit_price)`).
  - DAY session-bounded active limit / GTC cross-session persistence /
    end-of-data terminal retention.
  - Reproducibility preserved through existing SourceIdentityPolicy/v1;
    OrderLifecycleState and `sentinelx-entry-intent/v1` unchanged.

- O5 Execution-Evidence V1/V2 Collection Routing (§75):
  - Collection-level routing: runs with ZERO executions carrying activation
    evidence route to `sentinelx-execution-evidence/v1` (byte-stable).
  - Runs with ONE OR MORE activations route to `sentinelx-execution-evidence/v2`.
  - v2 binds explicit `("NONE",)` or `("PRESENT", activation_bar_timestamp,
    activation_price, activation_basis)` per execution.
  - 12 permanent tests (A–L) verify collision repair, byte stability, and
    replay localization.

- Gate-enabled STOP / STOP_LIMIT orders remain FAIL-CLOSED until the
  controlled O2 implementation.

- NEXT SINGLE REQUIRED STEP:
  Controlled implementation of Owner Decision O2 — gate-enabled STOP /
  STOP_LIMIT entry reference and activation (§73):
  1. STOP gate entry reference = `planned.stop_price`.
  2. STOP_LIMIT gate entry reference = `planned.limit_price`
     (`planned.stop_price` remains the activation trigger level only).
  3. Single planned reference authority (same reference feeds RiskGate and
     `ProtectivePlanPolicy.plan_for`).
  4. Controlled relaxation of the construction-time fail-closed block in
     `BacktestOrchestrator`.
  5. Required permanent end-to-end integration tests proving sizing, commitment
     reservation, execution, limit protection, and protective plan
     materialization.

## 77. Formal Phase-4 O2 Closure Marker (Owner / Independent Review)

OWNER DECISION O2 (GATE-ENABLED STOP / STOP_LIMIT ENTRY REFERENCE AND
ACTIVATION) IS FORMALLY VERIFIED_COMPLETE.

P0 / P1 / P2: 0 / 0 / 0.

Owner-run independent verification evidence:
- Focused O2 suite:            90 passed in 1.63s
- Relevant regression suite:  432 passed in 2.63s
- Full repository test suite: 937 passed, 1 skipped in 19.72s
- 0 failures
- Guard output: O2 REGRESSION + FULL OWNER VERIFICATION PASSED
- Software regression and contract evidence only — never market validity,
  strategy profitability, or live-trading performance evidence.

Full-suite test delta:
- Pre-O2 independently verified baseline: 927 passed, 1 skipped
- Post-O2:                                937 passed, 1 skipped
- Net increase: +10 permanent O2 integration tests

Implementation scope:
- Production: engine/orchestration.py only
- Tests: tests/test_orchestration_risk_gate.py only
  (2 existing tests updated, 10 new permanent test_o2_* tests added)

Owner verification history:
- Initial focused run exposed test-suite migration/setup defects
  (test-contract failures only; no production-code defect was found or
  required correction).
- Repairs were made to the test suite only; production code was not
  changed beyond the O2 implementation.
- Final independent verification: 90 focused / 432 regression / 937 full
  — 0 failures.

Closed O2 contract (§73 locks confirmed implemented):

1.  STOP gate/protective reference = planned.stop_price (NEW O2 lock).
2.  STOP_LIMIT gate/protective reference = planned.limit_price (NEW O2 lock);
    planned.stop_price is the activation/trigger level only — never the
    RiskGate entry reference.
3.  Single planned-reference authority: _gate_entry_reference resolves the
    reference exactly once; the same value feeds both
    ProtectivePlanPolicy.plan_for(reference_price=...) and
    RiskGate.evaluate_pre_order(entry_price=...).
4.  Gate-enabled BUY entry supports exactly:
    MARKET | LIMIT | STOP | STOP_LIMIT.
    Construction-time allowlist relaxed from {MARKET, LIMIT} to
    {MARKET, LIMIT, STOP, STOP_LIMIT}; any other BUY type fails closed
    at construction.
5.  No actual-fill-based re-sizing; approved quantity frozen from gate.
6.  No protective-plan regeneration from actual fill price.
7.  Q65 remains the fill-time actual-fill affordability authority
    (unchanged location, unchanged semantics).
8.  O4 persistent STOP_LIMIT activation (§74) preserved and unchanged.
9.  O5 execution-evidence v1/v2 collection routing (§75) preserved
    and unchanged.
10. Ambiguous intrabar no-assumed-fill conservative behavior preserved.
11. Pending commitment lifecycle, idempotency, accounting ownership, and
    legacy risk-deferred behavior all preserved.

PHASE 4 — ORDER ABSTRACTION / ORDER LIFECYCLE IS FORMALLY
VERIFIED_COMPLETE.

All Phase-4 checklist items satisfied:
- Broker-independent order interface & lifecycle state machine:
  VERIFIED_COMPLETE (§68–§70).
- Slice 1: Pending-entry validity & order lifecycle: VERIFIED_COMPLETE
  (§68–§70).
- Slice 2: Run-lifetime idempotency & duplicate protection:
  VERIFIED_COMPLETE (§71–§72).
- O4 / O5: Persistent STOP_LIMIT activation & execution-evidence V2:
  VERIFIED_COMPLETE (§74–§76).
- O2: Gate-enabled STOP / STOP_LIMIT entry reference & activation:
  VERIFIED_COMPLETE (§73, this section).

## 78. Backtest Engine Completion Gate — Formal Owner Sign-Off (§19 Criterion 15)

THE BACKTESTING ENGINE IS FORMALLY VERIFIED_COMPLETE AND OWNER_APPROVED.

BACKTEST_ENGINE_FREEZE.md §19 COMPLETION GATE IS FULLY PASSED (CRITERIA 1–15 SATISFIED).

Owner sign-off evidence and audit findings:
- §19 Criteria 1–14 established SATISFIED via formal read-only completion gate audit.
- §19 Criterion 15 established SATISFIED via formal project owner sign-off.
- Authoritative local independent verification evidence:
  - Focused O2 suite:            90 passed in 1.63s
  - Relevant regression suite:  432 passed in 2.63s
  - Full repository test suite: 937 passed, 1 skipped in 19.72s
  - 0 failures
  - Guard output: `O2 REGRESSION + FULL OWNER VERIFICATION PASSED`
  - Software regression and contract evidence only — never market validity,
    strategy profitability, or live-trading performance evidence.
- Defect counts: P0 = 0, P1 = 0, P2 = 0, P3 = 0.

Completion summary:
- Phase 1 (Data Foundation): VERIFIED_COMPLETE
- Phase 2 (Strategy Interface & Boundaries): VERIFIED_COMPLETE
- Phase 3 (Risk Management & Pre-Order Risk Gate): VERIFIED_COMPLETE (§58–§67)
- Phase 4 (Order Abstraction & Order Lifecycle): VERIFIED_COMPLETE (§68–§77)
- Long-term stable backtesting core complete across: market data synchronization,
  no-look-ahead execution loop, full order types (MARKET, LIMIT, STOP, STOP_LIMIT),
  gap handling, costs & slippage simulation, portfolio accounting, trade ledger,
  protective plans (STOP_LOSS, TARGET, trailing), OCO, 15 standard metrics,
  validation engine (walk-forward, bootstrap, Monte Carlo, parameter sensitivity),
  reproducibility & canonical codec fingerprints, and reporting generator.
- All historical verification, repair, and preflight records remain preserved.

NEXT SINGLE REQUIRED STEP:
  First narrowly-scoped Phase 5 implementation preflight/slice.

Phase 5 pre-implementation architecture/contract/scope review is OWNER_APPROVED.
Phase 5 implementation contracts are frozen in §79–§95 below.
Phase 5 code implementation was NOT performed.
Defect counts: P0 = 0, P1 = 0, P2 = 0, P3 = 0.
Real ORB/EMA strategy logic and Option Selector remain DEFERRED.
No market validation claim — test success means SOFTWARE / CONTRACT VERIFIED only.

**END OF BACKTEST ENGINE ARCHITECTURE DECISIONS**

---

# PHASE 5 — PAPER TRADING — OWNER-LOCKED ARCHITECTURE DECISIONS

The following sections record owner-approved Phase 5 (Paper Trading) architecture,
contract, and scope decisions. These are frozen Phase 5 contracts.
Amendment authority: `BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md` §1.

## 79. Phase 5 Pre-Implementation Review — Formal Closure Marker

PHASE 5 — PAPER TRADING PRE-IMPLEMENTATION ARCHITECTURE / CONTRACT / SCOPE
REVIEW — OWNER_APPROVED.

Review produced three iterations:
1. Initial 10-section review
2. Self-audit and repair (contradictions, scope discipline, reconciliation,
   logging, blocker classification, completed-bar policy)
3. Final targeted consistency repairs (D1/LiveDataFeed, D8/kill-switch,
   D3/missing-bar, D4/D5 promotion wording, D11 three-layer idempotency,
   D10 SQLite syntax, D9 state persistence classification)

Defect counts at closure: P0 = 0, P1 = 0, P2 = 0, P3 = 0.
No code was modified during this review.
No existing frozen contracts were overridden.

Owner-approved decisions D1–D16 and D3a are frozen in §80–§95 below.

## 80. Phase 5 Owner Decision D1 — Initial Paper Data Source

OWNER APPROVED.

Historical replay first. The actual Zerodha WebSocket `LiveDataFeed`
implementation is deferred until the API/live-data milestone.

Phase 5 must:
1. Freeze and test the `DataFeed` live compatibility boundary (the
   `fetch(instrument, timeframe) -> DataFrame` contract from
   `architecture-rules.md` Rule 4).
2. Implement `HistoricalReplayFeed(DataFeed)` — a `DataFeed`
   implementation that replays historical data at a controlled pace
   through the same contract boundary.
3. Integrate the paper runner with `HistoricalReplayFeed`.
4. Test that strategy/engine behavior is identical when driven by
   `HistoricalReplayFeed` vs `HistoricalDataFeed` in backtest mode.

The `DataFeed` swap contract (Rule 4) means adding the real
`LiveDataFeed` later requires zero architectural change — only a new
`DataFeed` subclass.

Deferred: Zerodha WebSocket `LiveDataFeed(DataFeed)` — actual WebSocket
connection, tick aggregation, reconnection, and tick-to-bar assembly.

## 81. Phase 5 Owner Decision D2 — Paper Runner Architecture

OWNER APPROVED.

Use a separate `PaperTradingRunner`. It must reuse the existing verified
strategy, RiskGate, execution, accounting, protective-exit, cost,
order-lifecycle, and other applicable engine components.

Do NOT refactor the verified `BacktestOrchestrator` merely to create the
paper loop. The backtest orchestrator's synchronous bar loop and the
paper event-driven loop are structurally different. A separate runner
imports engine internals and drives them from events, preserving Rule 4
parity (same strategy code, same risk math, same execution semantics,
same accounting) without modifying frozen backtest production code.

## 82. Phase 5 Owner Decision D3 — Completed-Bar Determination

OWNER APPROVED.

Completed-bar determination is authoritative market-calendar/event-time
based.

- Historical replay uses a simulated market clock derived from historical
event timestamps.
- Future live mode uses exchange/provider market timestamps for bar
assignment.
- System/wall clock must NOT silently redefine market timestamps.
- If clock/timestamp assignment is ambiguous, fail closed and halt signal
evaluation.

Authoritative calendar infrastructure (`WeekendCalendar`,
`MarketSessionBoundary` from §63 H) determines bar boundaries. A bar
is closed at the calendar-determined close time IF at least one tick was
observed during that bar interval. The handling of zero-tick intervals
is governed by D3a (§83).

## 83. Phase 5 Owner Decision D3a — Zero-Observation Bar Intervals

OWNER APPROVED.

Zero-observation interval policy = `MISSING_BAR` / `DATA_GAP` health
event.

- Do NOT fabricate a synthetic OHLC bar.
- Do NOT carry forward the prior close as fake O/H/L/C.
- Do NOT give the strategy a fake bar.
- No strategy signal evaluation occurs for that missing interval.
- The runner/data-health layer records the gap and applies applicable
  safety/order-validity rules (e.g., pending order DAY/TIF expiry
  evaluation proceeds against the actual elapsed time).

## 84. Phase 5 Owner Decision D4 — Simulated Fill Semantics

OWNER APPROVED.

Slippage is configurable for research. Promotion eligibility is
configuration-based.

A promotion-tracked run is eligible ONLY when its execution/slippage
configuration identity exactly matches the approved canonical backtest
configuration.

All non-canonical slippage modes, including zero-slippage research mode,
are `PROMOTION_INELIGIBLE` by policy classification regardless of whether
their resulting metrics accidentally satisfy numeric Q68 thresholds.

Promotion eligibility is determined by CONFIGURATION, not by outcome.

## 85. Phase 5 Owner Decision D5 — Fee/Cost Simulation

OWNER APPROVED.

Costs/fees are configurable for research. Promotion eligibility requires
exact identity match with the approved canonical backtest cost
configuration.

Zero-cost or otherwise non-canonical cost modes are
`PROMOTION_INELIGIBLE` by policy classification regardless of whether
their resulting metrics accidentally satisfy numeric Q68 thresholds.

Promotion eligibility is determined by CONFIGURATION, not by outcome.

## 86. Phase 5 Owner Decision D6 — Paper Broker Contract

OWNER APPROVED.

Full simulated paper-broker contract.

- Normal paper operation must deterministically model supported order
  lifecycle/fill behavior using the frozen engine semantics (MARKET,
  LIMIT, STOP, STOP_LIMIT with O2/O4/O5 contracts preserved).
- Rejection, timeout, retry, and failure-injection capabilities must exist
  for testing.
- Artificial fault-injection runs must NOT contribute promotion evidence
  unless separately owner-approved.

## 87. Phase 5 Owner Decision D7 — Paper Reconciliation

OWNER APPROVED.

Paper reconciliation compares the engine/accounting state against the
simulated paper broker's independently maintained persistent order/position
ledger.

- Mismatch must alert and halt/fail closed according to the frozen
  safety contract.
- Do NOT implement paper reconciliation as a no-op.

## 88. Phase 5 Owner Decision D8 — Safety Mechanisms in Paper Mode

OWNER APPROVED.

All applicable paper-scoped safety mechanisms are active.

Paper kill-switch behavior:
1. Halt `PaperTradingRunner`.
2. Reject new paper orders.
3. Cancel simulated pending orders.
4. Persist current state.
5. Emit alerts (Telegram/email per Q83/Q85).
6. Require explicit operator resume.

Open positions are NOT automatically liquidated by the paper kill switch
unless a separate future owner decision explicitly authorizes liquidation.

Real-broker disconnection/cancellation remains future Live scope.

Additional safety mechanisms active in paper:
- Disconnect handling (halt + alert + await reconnect).
- Heartbeat monitoring.
- Auto-stop on max daily loss (Q84).
- Auto-stop on error threshold (Q86).
- Auto-stop on reconciliation mismatch (Q87).
- Telegram + email alerts (Q83, Q85).

## 89. Phase 5 Owner Decision D9 — State Persistence

OWNER APPROVED.

Phase 5 adopts full runtime-state persistence using SQLite.

Persisted state includes:
- Strategy state (preserving Rule 2 / IFC-5 after-every-signal
  requirement)
- Positions
- Pending orders
- Paper-broker ledger state
- Daily trade count
- Daily P&L
- Halt/safety state
- Promotion metadata
- Required recovery identities

Persistence rules:
- Atomic at each committed state-changing event.
- If an authoritative state commit fails, fail closed and halt rather
  than silently continuing only in memory.
- Do NOT advance recovery-sensitive state past an uncommitted
  authoritative mutation.

## 90. Phase 5 Owner Decision D10 — Duration/Promotion Tracking

OWNER APPROVED.

Duration/promotion metadata lives in the same authoritative SQLite
persistence layer (§89).

- The six-month paper period starts from an explicit
  `PROMOTION_TRACKING_ACTIVATED` timestamp, NOT from the first signal
  or first trade.
- A strategy's low trade frequency must not shorten or delay the
  definition of the paper operating period.
- Store: activation timestamp, halt/disconnect/data-invalid intervals,
  configuration eligibility flags, metrics evidence, and promotion
  status.
- Unresolved or ambiguous data-integrity periods must NOT be silently
  counted as clean promotion evidence.
- Meeting numeric Q68 thresholds only makes the strategy eligible for
  manual review (Q120); it never auto-promotes.

## 91. Phase 5 Owner Decision D11 — Duplicate/Replay Handling

OWNER APPROVED. Three-layer defense-in-depth.

**Layer 1 — Persistent market-event/replay deduplication at the
feed/event boundary:**
- For historical replay: canonical replay/bar identity bound to
  source/data identity + instrument + timeframe + authoritative bar
  timestamp.
- For future live provider: authoritative provider event/sequence
  identity where available; otherwise a separately frozen
  collision-safe composite identity is required.
- Ambiguous event identity fails closed.
- Persistent across process restarts.

**Layer 2 — Existing engine entry-intent idempotency (§71):**
- `sentinelx-entry-intent/v1` run-lifetime idempotency preserved.
- Per-run scope. Defense-in-depth against Layer 1 bugs.

**Layer 3 — Persistent paper-broker order idempotency:**
- Paper broker rejects duplicate order submissions using a persistent
  identity check against its independent order ledger.
- Cross-restart scope.
- Defense-in-depth against Layer 1 or Layer 2 bugs.

No single-layer failure results in a duplicate order.

Timestamp alone is NOT a sufficient universal raw-event identity.

## 92. Phase 5 Owner Decision D12 — Gap Handling

OWNER APPROVED.

Preserve the existing >1.5x ATR informational gap flagging rule (Q28).

## 93. Phase 5 Owner Decision D13 — Paper Configuration Schema

OWNER APPROVED.

Use `paper_config.yaml` for paper-environment-specific configuration.

- Do NOT duplicate ownership of canonical strategy/risk/execution
  configuration fields.
- Reference/bind shared canonical configurations through their
  approved identities/fingerprints where applicable.
- `CONFIG_SCHEMA.md` is updated to reserve/freeze paper configuration
  ownership and schema boundaries.

## 94. Phase 5 Owner Decision D14 — Concurrent Capital Competition

OWNER APPROVED.

Concurrent capital competition rules are identical to the verified
backtest engine (§60). No paper-specific relaxation.

## 95. Phase 5 Owner Decision D15 — Indicator Warm-Up

OWNER APPROVED.

Indicator warm-up uses historical data before paper/live processing
begins.

- Warm-up data must end immediately before the first authoritative
  paper event for each required stream.
- No overlap, no future leakage, no duplicate bar ingestion, and no
  silent gap are allowed.
- Signal evaluation remains blocked until warm-up requirements are
  satisfied (Phase 4.6).

## 96. Phase 5 Owner Decision D16 — Logging Schema

OWNER APPROVED.

Freeze a versioned, storage-independent log/event schema shared by
Paper and future Live.

**Minimum common event envelope:**

| Field | Description |
|---|---|
| `schema_version` | Schema contract version |
| `event_id` | Unique event identity |
| `event_type` | Event family (see below) |
| `event_time_utc` | UTC timestamp of event creation |
| `market_timestamp` | Authoritative market timestamp where applicable |
| `environment` | `backtest` / `paper` / `live` |
| `run_id` | Run/session identity |
| `strategy_id` | Strategy identity |
| `strategy_version` | Strategy semantic version |
| `instrument` | Instrument identity |
| `timeframe` | Timeframe where applicable |
| `source_identity` | Data source identity |
| `canonical_configuration_fingerprint` | Canonical config/runtime fingerprint(s) |
| `correlation_id` | Correlation identity for related events |
| `causation_id` | Causation identity (cause -> effect chain) |
| `status` | Event outcome status |
| `severity` | Severity level |
| `payload` | Versioned event-specific payload |

**Required event families (minimum):**
- Signal evaluation
- Order submission/state transition
- Fill
- Rejection
- Trade
- Reconciliation
- Error
- Disconnect/recovery
- Safety halt / kill switch
- Operator/manual intervention

Paper and Live must use the same schema contract; environment/value
differences are data, not schema differences.

Full durable logging infrastructure remains in its later approved phase
unless an interface/hook is required by Phase 5.

## 97. Phase 5 — Formal Documentation-Gate Closure Marker

PHASE 5 — PAPER TRADING PRE-IMPLEMENTATION REVIEW —
OWNER_APPROVED / DOCUMENTATION GATE COMPLETE.

- Owner decisions D1–D16 and D3a are frozen in §80–§96.
- No code implementation was performed.
- No existing frozen contracts were overridden.
- Defect counts: P0 = 0, P1 = 0, P2 = 0, P3 = 0.
- Real ORB/EMA strategy logic and Option Selector remain DEFERRED.

**NEXT SINGLE REQUIRED STEP:**
  First narrowly-scoped Phase 5 implementation preflight/slice derived
  from the frozen contracts in §80–§96.

  Suggested first slice: DataFeed compatibility boundary +
  HistoricalReplayFeed (§80 deliverables 1–4). This is the narrowest
  scope that produces testable output and validates the fundamental
  `DataFeed` swap contract before the paper runner or paper broker
  are built.


## 98. Phase 5 Slice 1 — HistoricalReplayFeed Implementation / Verification Checkpoint

PHASE 5 SLICE 1 — DATAFEED COMPATIBILITY BOUNDARY + HISTORICALREPLAYFEED —
VERIFIED_COMPLETE.

Satisfies §80 deliverables 1–2 (DataFeed boundary freeze +
HistoricalReplayFeed implementation). Deliverables 3–4 (paper runner
integration + backtest-mode parity) require PaperTradingRunner (§81)
and are deferred to Slice 2.

Implementation:
- engine/feeds/replay_feed.py (new; HistoricalReplayFeed(DataFeed)
  with forward-only replay cursor, deterministic advance, no synthetic
  bars, no look-ahead, timestamp normalization, OHLCV validation).
- tests/test_replay_feed.py (new; 30 tests: DataFeed contract,
  deterministic replay, no look-ahead, timestamp preservation, ordered
  replay, missing-interval/no-synthetic-carry-forward, get_data
  compatibility, HistoricalDataFeed parity, edge cases).

No existing frozen backtest contract was modified.
Actual Zerodha WebSocket LiveDataFeed remains deferred per D1 (§80).
PaperTradingRunner has NOT been implemented.

Owner-independent local verification evidence:
- Focused:            30 passed in 7.28s
- Feed/data regression: 53 passed in 1.34s
- Import-boundary:    11 passed in 1.69s
- Full repository:    967 passed, 1 skipped, 0 failures in 20.86s

Defect counts: P0 = 0, P1 = 0, P2 = 0, P3 = 0.
No market validation claim — test success means SOFTWARE / CONTRACT
VERIFIED only.

**NEXT SINGLE REQUIRED STEP:**
  Phase 5 Slice 2 — PaperTradingRunner skeletal structure +
  event-driven replay loop using HistoricalReplayFeed and existing
  verified engine components (§81, §80 deliverable 3).
  This does NOT include simulated broker (D6, §86), SQLite
  persistence (D9, §89), safety/logging (D8/D16, §88/§96),
  or other later Phase 5 components.

## 99. Phase 5 Owner Scope Refreeze — OD-1 through OD-7

PHASE 5 OWNER SCOPE REFREEZE — OWNER_APPROVED.
Refreeze date: 2026-08-19.
Trigger: Master spec conflict audit identified 7 material conflicts between the new
`SentinelX-Paper-Trading-Engine-Spec-v1.0.md` DRAFT and existing frozen contracts.
The owner approved seven scope-refreeze decisions (OD-1 through OD-7) which are frozen below.

### Superseded/amended prior decisions:

| Prior Decision | Original Wording | Amendment | Reason |
|---|---|---|---|
| **D1 (§80)** | "Historical replay first. The actual Zerodha WebSocket LiveDataFeed implementation is deferred until the API/live-data milestone." | **Amended:** Historical replay is the **development/testing/reproducibility tool**; Phase 5 VERIFIED_COMPLETE requires live-market data connector operational. Replay success alone MUST NOT satisfy the Phase 5 completion gate. | Owner clarified that historical replay alone does not constitute Phase 5 completion. |
| **D4 (§84)** | "Slippage is configurable for research. Promotion eligibility is configuration-based." | **Expanded:** Paper fill model uses **live bid/ask** pricing (not bar OHLC); `SlippageModel` protocol is backtest-only; a separate `PaperFillAdapter` with bid/ask fills, rejection, latency, and stale-quote handling is required. | New spec requires execution-realistic fills that the bar-based engine cannot provide. |
| **D6 (§86)** | "Full simulated paper-broker contract." | **Expanded:** Must include bid/ask fill pricing, fill rejection on price gap, latency simulation, and the `PaperFillAdapter` as a distinct execution path from `BacktestFillAdapter`. | OD-3 defines specific MUST_HAVE_V1 fill realism requirements. |
| **D10 (§90)** | No mention of Option Selector dependency. | **Amended:** Promotion tracking cannot start until Option Selector resolves option contracts. Option Selector is a BLOCKING DEPENDENCY for Phase 5 VERIFIED_COMPLETE. | OD-4 makes Option Selector mandatory for automated options paper trading. |

### Preserved unchanged prior decisions:
- **D2 (§81)** — Separate PaperTradingRunner, no BacktestOrchestrator refactoring
- **D3 (§82)** — Calendar/event-time-based completed bars
- **D3a (§83)** — Zero-observation = MISSING_BAR/DATA_GAP event, no synthetic bars
- **D5 (§85)** — Configurable costs, PROMOTION_INELIGIBLE by policy for non-canonical
- **D7 (§87)** — Paper reconciliation (engine vs paper-broker), not a no-op
- **D8 (§88)** — Safety mechanisms, kill switch behavior
- **D9 (§89)** — SQLite full runtime-state persistence
- **D11 (§91)** — Three-layer defense-in-depth idempotency
- **D12 (§92)** — Preserve >1.5x ATR gap flagging
- **D13 (§93)** — paper_config.yaml schema
- **D14 (§94)** — Concurrent capital competition identical to backtest §60
- **D15 (§95)** — Indicator warm-up from historical data
- **D16 (§96)** — Versioned storage-independent log/event schema

### OD-1 — Phase 5 Completion Definition (OWNER APPROVED)

Phase 5 is NOT complete when historical replay works.

HistoricalReplayFeed is permanent:
**TEST / REPLAY / DEBUG / DETERMINISTIC VALIDATION infrastructure.**

Phase 5 VERIFIED_COMPLETE requires operational LIVE-MARKET AUTOMATED PAPER TRADING using:
- real live market data
- actual market hours
- virtual/demo money only
- no real broker order placement
- automatic strategy evaluation
- automatic options contract resolution (**OD-4**)
- realistic simulated order execution (**OD-2/OD-3**)
- virtual portfolio/account
- live MTM P&L
- live-price SL / Target / Trailing (**OD-6**)
- costs/slippage/latency handling
- persistence/recovery
- safety
- reconciliation
- audit/logging
- multi-strategy/shared-capital operation

Replay success alone MUST NOT satisfy the Phase 5 completion gate.

### OD-2 — Execution Architecture (OWNER APPROVED)

Introduce/freeze the architectural boundary:
```
ExecutionAdapter
├── BacktestFillAdapter
├── PaperFillAdapter
└── LiveBrokerAdapter
```

This decision MUST NOT authorize rewriting the verified Backtest ExecutionEngine.
BacktestFillAdapter will eventually reuse/wrap the existing verified Backtest ExecutionEngine.
PaperFillAdapter will own paper-specific execution-realistic fill behavior.
LiveBrokerAdapter is the future real broker execution path.
Strategy and risk logic should remain mode-independent wherever existing frozen contracts permit.
This task freezes architecture only. Do NOT implement these adapters now.

### OD-3 — Paper Fill Realism V1 (OWNER APPROVED)

MUST_HAVE_V1:
1. BUY simulated fill based on executable ASK-side market evidence.
2. SELL simulated fill based on executable BID-side market evidence.
3. Do NOT use naive LTP-only optimistic fills.
4. Configurable slippage.
5. Configurable signal-to-execution latency.
6. Stale quote rejection/fail-closed behavior.
7. Reject/avoid fabricated fills when price has moved beyond approved execution tolerance.
8. Applicable brokerage/statutory/exchange costs included.
9. Conservative execution behavior: impossible or unsupported fills must not be magically accepted.

PARTIAL FILLS: NOT required in v1 without reliable market-depth/liquidity evidence.
CALIBRATION_LATER: empirical latency/slippage calibration, liquidity-depth calibration, advanced partial fills.
V2/LATER: queue-position simulation, market-impact modeling.
Do NOT claim paper execution can be guaranteed 100% identical to exchange execution.
Goal: conservative, execution-realistic paper behavior.

### OD-4 — Option Selector (OWNER APPROVED)

Option Selector is a **BLOCKING DEPENDENCY** for Phase 5 VERIFIED_COMPLETE.

SentinelX Phase 5 target is automated OPTIONS paper trading.
Therefore Phase 5 cannot be declared VERIFIED_COMPLETE until the system can automatically resolve,
using frozen strategy/configuration rules: underlying intent, CE/PE, expiry, strike, tradable option instrument,
lot size/contract multiplier, required live quote/instrument identity.

Strategy logic itself must NOT hard-code broker-specific option contracts.
Infrastructure work may proceed before Option Selector is complete, but the final Phase 5 completion gate requires it.
Supersedes any wording that implies Phase 5 can be fully completed without Option Selector.

### OD-5 — Order Lifecycle (OWNER APPROVED)

Preserve the currently verified frozen core order lifecycle for v1:
CREATED → VALIDATED → QUEUED → FILLED / EXPIRED / CANCELLED / REJECTED.

Do NOT add OPEN merely because the new draft spec used that terminology.
Do NOT add PARTIALLY_FILLED to the frozen core lifecycle during v1.
The master spec terminology must be reconciled to the existing lifecycle.
If reliable partial-fill support is later approved, lifecycle expansion must receive a separate owner architecture decision.
Do NOT create a hidden incompatible paper-only lifecycle state machine.

### OD-6 — Live-Price Protective Monitoring (OWNER APPROVED)

Operational paper trading must evaluate protective exits against live price updates rather than waiting
for completed strategy candles. This includes stop loss, target, trailing stop.

Existing verified protective rules/state semantics should be reused as far as possible.
However: do NOT make 5-minute/strategy-bar close the required trigger point for a protective exit in live paper trading.
Freeze a requirement for a dedicated live-price/tick/quote protective trigger integration path or adapter
that reuses existing protective semantics.
Do NOT implement it during this documentation task.
Do NOT silently replace live-price monitoring with completed-bar-only protective behavior.

### OD-7 — Implementation Order (OWNER APPROVED)

Use deterministic replay first to develop and verify the paper pipeline, then connect the same
architecture to live market data. Historical replay is a TEST HARNESS, not the operational Phase 5 target.

High-level dependency order:
1. HistoricalReplayFeed — STATUS: VERIFIED_COMPLETE
2. PaperTradingRunner replay/core orchestration
3. ExecutionAdapter architectural integration
4. PaperFillAdapter / simulated paper broker
5. Option Selector (**BLOCKING DEPENDENCY**)
6. LiveDataFeed / real-time market data connector (including required option quote/bid/ask data)
7. Virtual account + live MTM integration
8. Live-price SL / Target / Trailing integration
9. SQLite full runtime-state persistence / recovery
10. Safety / kill switch / stale-data / disconnect handling
11. D16 logging / audit event implementation
12. Paper reconciliation
13. Multi-strategy + shared-capital verification
14. Full replay-pipeline regression verification
15. Actual live-market paper-trading verification
16. Final Phase 5 architecture + implementation audit
17. PHASE 5 VERIFIED_COMPLETE

The exact slicing may later be refined by read-only preflight audits, but dependencies must not violate
the frozen owner decisions above.

### Phase 5 Final Completion Gate (Frozen per OD-1)

Phase 5 may be marked VERIFIED_COMPLETE only when ALL mandatory items are implemented and independently verified.

MANDATORY:
A. Replay/testing infrastructure — HistoricalReplayFeed preserved and verified; deterministic replay of paper pipeline; replay end-to-end regression path available.
B. Operational live paper trading — true live-market data connector; actual market-hour event processing; automatic strategies on unseen live data; automatic Option Selector; live option contract/quote resolution; PaperFillAdapter with bid/ask conservative fills; latency/slippage/stale-price/rejection; applicable costs; configurable virtual capital; virtual positions; realized P&L; unrealized/live MTM P&L; protective exits against live prices; multi-strategy shared capital/risk; SQLite runtime persistence; restart/recovery; kill switch/safety; stale data/disconnect; reconciliation; D16-compatible logging/audit.
C. Verification — deterministic tests; regression tests; full repository tests; live-paper controlled validation; no unresolved P0/P1 defects; final owner audit.

NOT SUFFICIENT FOR COMPLETION: HistoricalReplayFeed alone; PaperTradingRunner replay alone; strategy signals alone; futures-only without Option Selector; fake LTP fills; completed-bar-only protective monitoring; non-persistent state.

### Promotion / Six-Month Rule (Preserved)

Existing D10 / Q67 / Q68 / Q120 owner contracts preserved unless direct conflict discovered.
Phase 5 CODE COMPLETION and six-month operational paper evidence are distinct.
Do NOT auto-promote. Meeting numeric criteria = eligible for review only. Final go-live = explicit manual owner approval.

### Slice 1 Status (Preserved)

Phase 5 Slice 1 remains VERIFIED_COMPLETE exactly as recorded in §98.
Its permanent role: TEST / REPLAY / DEBUG / DETERMINISTIC VALIDATION INFRASTRUCTURE.
No modification to engine/feeds/replay_feed.py or tests/test_replay_feed.py during this refreeze.

### Slice 2 Status

Phase 5 Slice 2 (PaperTradingRunner replay/core orchestration) is **VERIFIED_COMPLETE**.

Files: `engine/paper_runner.py` (new), `tests/test_paper_runner.py` (new, 62 tests).
`engine/market/data.py` was NOT modified. No existing frozen contracts were changed.
Owner-local verification: 1029 passed, 1 skipped, 0 failures.

Its permanent role: TEST / REPLAY / DEBUG / DETERMINISTIC VALIDATION INFRASTRUCTURE.
No modification to engine/feeds/replay_feed.py or tests/test_replay_feed.py during or after Slice 2.

Explicitly NOT delivered: PaperFillAdapter, simulated broker, Option Selector, LiveDataFeed,
virtual P&L, live MTM, live-price protective execution, SQLite persistence, safety/kill-switch.
Phase 5 is NOT complete from replay alone (OD-1).

## 100. Phase 5 Slice 3A — ExecutionAdapter / QuoteSnapshot / PaperFillAdapter — VERIFIED_COMPLETE

PHASE 5 SLICE 3A — EXECUTIONADAPTER + QUOTESNAPSHOT + PAPERFILLADAPTER — VERIFIED_COMPLETE
SLICE_3A_NON_PROMOTION_EXECUTION_EVIDENCE

Refreeze date: 2026-08-19.
Scope: OD-2 ExecutionAdapter architecture (PaperFillAdapter only), OD-3 Paper Fill Realism V1
(fill economics: bid/ask, slippage, stale/crossed quote rejection, price-move tolerance).

### Files Created
- `engine/execution/adapter.py` — ExecutionAdapter Protocol (model_id + evaluate)
- `engine/execution/quote.py` — QuoteSnapshot (frozen dataclass; tz-aware timestamp, validated prices,
  None bid/ask allowed, non-positive rejected, crossed allowed at construction → UNFILLED at evaluation)
- `engine/execution/paper_fill.py` — PaperSlippageModel protocol, FixedBasisPointsSlippage,
  PaperFillPolicy (frozen, constructor-owned), ExecutionEvaluationContext (frozen, per-evaluation),
  PaperFillAdapter (evaluate/evaluate_market/evaluate_limit), tick-rounding helpers
- `tests/test_paper_fill.py` — 64 focused tests

### No Existing Files Modified
All production code and tests remain unchanged from the Slice 2 baseline.

### Permanent Slice 3A Role
- Deterministic quote-based paper execution evaluation (stateless adapter)
- ExecutionAdapter synchronous evaluation seam (protocol)
- Immutable QuoteSnapshot evidence
- BUY execution uses ASK; SELL execution uses BID; LTP is not executable fill evidence
- PaperFillPolicy is immutable/static adapter policy (constructor-owned, shared across orders)
- ExecutionEvaluationContext carries per-order reference price and tick increment
- Price-move (current vs reference executable) and slippage are separate OD-3 controls with separate formulas
- Adverse tick rounding is included in effective slippage (step 8 of 11-step sequence)
- LIMIT fills are never synthetically capped to limit price; adverse slippage beyond limit → UNFILLED
- All retryable quote conditions use UNFILLED (not REJECTED)
- REJECTED remains terminal/broker-owned (Slice 3B)
- STOP/STOP_LIMIT direct evaluate() → ValueError (contract misuse; trigger is 3B-owned)
- Triggered STOP may use evaluate_market(); triggered STOP_LIMIT may use evaluate_limit()
- Original order identity preserved in ExecutionResult
- Costs remain downstream (CostCalculator.assess_leg is the correct entry point; adapter does NOT compute costs)
- RiskGate remains outside PaperFillAdapter (no risk/cost logic in adapter)
- No live broker claim; no operational paper-trading completion claim

### 11-Step Evaluation Sequence (Locked)
1. Validate types (QuoteSnapshot, ExecutionEvaluationContext)
2. Select executable side (BUY→ask, SELL→bid)
3. Reject missing/crossed quote (UNFILLED)
4. Price-move tolerance check (current executable vs reference_price; favorable = no reject)
5. LIMIT pre-slippage eligibility (ask > limit for BUY, bid < limit for SELL → UNFILLED)
6. Compute slippage amount from PaperSlippageModel
7. Apply slippage to executable price
8. Apply tick rounding (ceil for BUY, floor for SELL)
9. Max slippage check (effective slippage vs current_executable × max_slippage_bps/10000)
10. LIMIT post-slippage hard boundary (rounded fill beyond limit → UNFILLED "adverse_slippage_exceeds_limit")
11. FILLED

### Owner-Local Verification Evidence
- py_compile: PASS
- tests/test_paper_fill.py: **64 passed in 0.19s**
- tests/test_execution.py: **56 passed in 6.01s**
- tests/test_orders.py: **22 passed in 0.57s**
- tests/test_costs.py: **41 passed in 0.64s**
- Risk regression (test_risk.py + test_risk_gate.py + test_orchestration_risk_gate.py): **254 passed in 1.42s**
- Protective regression (test_protective.py + test_protective_plan.py): **64 passed in 0.61s**
- tests/test_paper_runner.py: **62 passed in 0.97s**
- tests/test_import_boundaries.py: **11 passed in 1.58s**
- FULL REPOSITORY: **1093 passed, 1 skipped, 0 failures in 20.15s**

The 11 AutoClaw embedded-Python import-boundary failures (PYTHONPATH subprocess suppression)
are confirmed environment-specific and NOT repository defects. Owner-local Python 3.13.14 passes all 11.

### Defect Counts
P0 = 0, P1 = 0, P2 = 0, P3 = 0

### Slice 3B Status
VERIFIED_COMPLETE. See §101.

### Phase 5 Completion Status
Phase 5 is NOT VERIFIED_COMPLETE. Verified so far:
1. HistoricalReplayFeed - VERIFIED_COMPLETE
2. PaperTradingRunner replay/core - VERIFIED_COMPLETE
3A. ExecutionAdapter / QuoteSnapshot / PaperFillAdapter - VERIFIED_COMPLETE
3B. SimulatedPaperBroker - VERIFIED_COMPLETE (``101)

Still missing: Option Selector (OD-4 BLOCKING DEPENDENCY), LiveDataFeed,
virtual account, live MTM, live-price protective integration, SQLite persistence/recovery,
safety/kill-switch, D16 logging, reconciliation, live-market verification, final Phase 5 audit.

### NEXT SINGLE REQUIRED STEP
PHASE 5 - OPTION SELECTOR - PRE-IMPLEMENTATION ARCHITECTURE AUDIT
(per OD-4: Option Selector is a BLOCKING DEPENDENCY for Phase 5 VERIFIED_COMPLETE).
Must reconcile: strategy directional intent (BULLISH/BEARISH/EXIT/HOLD) -> CE/PE resolution,
ATM/ITM/OTM/strike-distance/expiry-selection policy, tradable instrument discovery,
lot size/contract multiplier from instrument metadata, required live quote/instrument identity,
existing InstrumentIdentity/CanonicalIdentity contract, configuration ownership boundaries.
Do NOT start the audit or implementation in this task.
## 101. Phase 5 Slice 3B — SimulatedPaperBroker — VERIFIED_COMPLETE

PHASE 5 SLICE 3B — SIMULATED PAPER BROKER — VERIFIED_COMPLETE
SLICE_3B_NON_PROMOTION_EXECUTION_EVIDENCE

Refreeze date: 2026-08-19.
Scope: OD-2 ExecutionAdapter architecture (SimulatedPaperBroker consuming PaperFillAdapter),
OD-3 Paper Fill Realism V1 (broker-level lifecycle, latency, stale quote, idempotency),
OD-5 order lifecycle (CREATED→VALIDATED→QUEUED→terminal), D6 full simulated paper broker
contract, D11 Layer 3 order idempotency (in-memory pre-persistence).

### Files Created
- `engine/execution/broker.py` (new; SimulatedPaperBroker, PaperOrder, BrokerResult, etc.)
- `tests/test_paper_broker.py` (new; 89 focused tests)

### No Existing Files Modified
All production code and tests remain unchanged from the Slice 3A baseline.

### Permanent Slice 3B Role
- Deterministic in-memory simulated broker for paper order lifecycle, execution, and fill management
- TEST / REPLAY / DEBUG / DETERMINISTIC VALIDATION INFRASTRUCTURE — NOT operational live paper trading
- Consumes PaperFillAdapter (Slice 3A) for fill evaluation
- OD-5 order lifecycle: CREATED→VALIDATED→QUEUED→terminal (FILLED/EXPIRED/CANCELLED/REJECTED)
- No OPEN or PARTIALLY_FILLED lifecycle states (OD-5)

### Verified Behavior
1. **Deterministic in-memory simulated broker** — no persistence (D9 deferred), no WebSocket
2. **QUEUED lifecycle** — orders enter QUEUED after VALIDATED; terminal states are FILLED, EXPIRED, CANCELLED, REJECTED
3. **Latency eligibility** — configurable signal-to-execution latency; orders below latency threshold remain latency-ineligible
4. **Stale quote fail-closed handling** — stale quotes (exceeding configurable staleness window) cause UNFILLED, not fabricated fills
5. **Event-id dedup** — broker-level deduplication of market events by event identity
6. **Old/out-of-order suppression** — events older than the broker's last-seen timestamp are silently skipped
7. **Immutable submission reference price** — reference price captured at order submission and frozen; evaluation uses this immutable reference
8. **ConcreteCloseInstruction support** — EXIT signals resolve to concrete close instructions with instrument, side, and quantity
9. **Raw unresolved EXIT fail closed** — EXIT signals that cannot resolve to a concrete close instruction (no matching position) are REJECTED
10. **Retryable UNFILLED remains QUEUED** — UNFILLED orders (stale quote, adverse slippage, no executable price) remain in QUEUED state for re-evaluation
11. **STOP last_price-only trigger** — STOP orders trigger based on last_price crossing the stop price (not bid/ask)
12. **Persistent STOP trigger** — once a STOP triggers, it remains triggered; does not un-trigger on price reversion
13. **Persistent STOP_LIMIT activation** — once a STOP_LIMIT's stop triggers, the limit portion remains activated for subsequent bars
14. **Terminal double-fill prevention** — orders in terminal states (FILLED, EXPIRED, CANCELLED, REJECTED) cannot be re-evaluated or re-filled
15. **Duplicate submission prevention** — broker rejects duplicate order submissions using order identity deduplication
16. **Deterministic multiple-order evaluation** — multiple pending orders are evaluated in deterministic order per tick
17. **Cancel** — orders can be cancelled from QUEUED state; terminal-state cancellation is rejected
18. **DAY expiry** — DAY orders expire at session boundary; expired orders move to EXPIRED terminal state
19. **GTC preservation** — GTC orders persist across sessions until fill, cancellation, or end-of-data
20. **No RiskGate logic** — broker does not perform risk evaluation; RiskGate remains upstream
21. **No cost duplication** — broker does not compute costs; costs remain downstream via CostCalculator
22. **No persistence** — broker is in-memory only; SQLite persistence is a later Phase 5 component (D9, §89)
23. **No WebSocket** — broker consumes quotes/events via synchronous API; no WebSocket implementation
24. **No Option Selector implementation** — option contract resolution is deferred to dedicated Option Selector (OD-4)

### Owner-Local Verification Evidence
- Compile: **PASS**
- `tests/test_paper_broker.py`: **89 passed**
- `tests/test_paper_fill.py`: **64 passed**
- `tests/test_execution.py`: **56 passed**
- `tests/test_orders.py`: **22 passed**
- `tests/test_costs.py`: **41 passed**
- Risk regression (test_risk.py + test_risk_gate.py + test_orchestration_risk_gate.py): **254 passed**
- Protective regression (test_protective.py + test_protective_plan.py): **64 passed**
- `tests/test_paper_runner.py`: **62 passed**
- `tests/test_import_boundaries.py`: **11 passed**
- **FULL REPOSITORY: 1182 passed, 1 skipped, 0 failures in 23.06s**

Previous baseline: 1093 passed (Slice 3A). Net new: +89 Slice 3B tests = 1182 total.

The 11 AutoClaw embedded-Python import-boundary failures (PYTHONPATH subprocess suppression)
are confirmed environment-specific and NOT repository defects. Owner-local Python 3.13.14 passes all 11.

### Defect Counts
P0 = 0, P1 = 0, P2 = 0, P3 = 0

### Phase 5 Completion Status
Phase 5 is NOT VERIFIED_COMPLETE. Verified so far:
1. HistoricalReplayFeed — VERIFIED_COMPLETE
2. PaperTradingRunner replay/core — VERIFIED_COMPLETE
3A. ExecutionAdapter / QuoteSnapshot / PaperFillAdapter — VERIFIED_COMPLETE
3B. SimulatedPaperBroker — VERIFIED_COMPLETE

Still missing: Option Selector (OD-4 BLOCKING DEPENDENCY), LiveDataFeed,
live MTM, virtual account, live protective integration, SQLite persistence/recovery,
safety/kill-switch, D16 logging, reconciliation, live-market verification, final Phase 5 audit.

### NEXT SINGLE REQUIRED STEP
PHASE 5 — OPTION SELECTOR — PRE-IMPLEMENTATION ARCHITECTURE AUDIT
(per OD-4: Option Selector is a BLOCKING DEPENDENCY for Phase 5 VERIFIED_COMPLETE).
Must reconcile: strategy directional intent (BULLISH/BEARISH/EXIT/HOLD) → CE/PE resolution,
ATM/ITM/OTM/strike-distance/expiry-selection policy, tradable instrument discovery,
lot size/contract multiplier from instrument metadata, required live quote/instrument identity,
existing `InstrumentIdentity`/`CanonicalIdentity` contract, configuration ownership boundaries.
Do NOT start the audit or implementation in this task.


## 102. Phase 5 Option Selector Slice A — VERIFIED_COMPLETE

PHASE 5 OPTION SELECTOR SLICE A — PURE BROKER-INDEPENDENT SELECTOR CORE

Owner-local status: **VERIFIED_COMPLETE**.

The permanent Slice A boundary is pure contract resolution only:

`SignalIntent -> OptionSelector -> ResolvedOptionEntry | OptionSelectionRejection`

It does not own broker execution, RiskGate evaluation, PaperFillAdapter,
protective execution, persistence, or live connectivity.

### Frozen Option Selector V1 Rules

1. Semantic BUY resolves to a CE candidate.
2. Semantic SELL resolves to a PE candidate.
3. Both are long-options semantics; semantic SELL is bearish direction and
   MUST NOT be interpreted as naked option SELL execution.
4. HOLD produces no option entry.
5. EXIT/protective actions bypass the selector and operate on the exact held
   contract.
6. Expiry selection is explicit NEAREST_LISTED.
7. `min_dte_days` and `allow_expiry_day` are explicit per-strategy policy
   fields; no silent defaults are permitted.
8. Strike mode is explicit ATM / ITM / OTM with explicit non-negative
   `offset_steps`.
9. Strike ladders come only from the authoritative InstrumentCatalog.
10. ATM equal-distance tie resolves to the lower numeric strike.
11. CE ITM moves down the ladder; CE OTM moves up.
12. PE ITM moves up the ladder; PE OTM moves down.
13. Required offset outside the authoritative ladder fails closed.
14. Instrument identity/specification must come from the catalog and MUST NOT
    be synthesized from hard-coded symbol, strike interval, lot size,
    multiplier, tick size, expiry, or exchange-token assumptions.
15. Catalog entries with future effective authority are ineligible.
16. Duplicate/ambiguous selection authority fails closed.
17. Selected `InstrumentIdentity` and `InstrumentSpecification.identity` must
    agree.
18. No delta, IV, liquidity, open-interest, volume, premium-ranking, or random
    tie-break policy exists in Slice A.
19. Missing option-selection configuration fails closed.

### Verification

- focused Option Selector suite: **63 passed**
- full repository after Slice A: **1245 passed, 1 skipped, 0 failures**

### Known Non-Blocking Finding

P2: internal strike-selection failure causes may share the outward
`no_eligible_strikes` rejection reason. Selection remains deterministic and
fail-closed.

---

## 103. Phase 5 Option Entry Slice B — MARKET-ONLY BRIDGE — VERIFIED_COMPLETE

PHASE 5 OPTION ENTRY SLICE B — MARKET-ONLY LONG-OPTION EXECUTION BRIDGE

Owner-local status: **VERIFIED_COMPLETE**.

### Frozen Semantic / Executable-Side Contract

- semantic BUY -> CE -> executable BUY
- semantic SELL -> PE -> executable BUY
- original semantic BUY/SELL provenance remains immutable
- no option entry may reach execution as SELL

`ConcreteOpenInstruction` is the additive executable projection that preserves
the semantic source order while exposing concrete opening execution authority.

### Frozen Instrument Authority

The semantic source intent keeps the underlying symbol for provenance.

The executable instruction exposes the concrete selected option instrument.

The selected `InstrumentIdentity`, selected `InstrumentSpecification.identity`,
submission `QuoteSnapshot.instrument_identity`, and concrete executable symbol
must identify the same option contract.

### Frozen Quantity Authority

There is exactly one approved quantity authority:

`RiskGate approved quantity
 -> source_entry_order.quantity
 -> ConcreteOpenInstruction.quantity`

`ConcreteOpenInstruction.quantity` is a property and is NOT an independent
dataclass field.

### MARKET-Only V1

Supported option-entry order type:

- MARKET

Explicitly deferred:

- LIMIT
- STOP
- STOP_LIMIT

This restriction applies only to the Phase-5 option-entry bridge.
Existing frozen backtest STOP / STOP_LIMIT behavior is unchanged.

### MARKET Safety / Risk Reference

For Slice B MARKET option entry:

- `max_execution_tolerance_bps` MUST be strictly positive
- `max_slippage_bps` MUST be strictly positive

Current PaperFill semantics interpret zero as disabling the corresponding
check. The option bridge therefore fails closed for zero/non-positive safety
bounds.

For authoritative option submission ask `A`:

`worst_permitted_fill =
 A * (1 + max_execution_tolerance_bps / 10000)
   * (1 + max_slippage_bps / 10000)`

The same value is used as:

- `ProtectivePlanPolicy.plan_for(reference_price=...)`
- `RiskGate.evaluate_pre_order(entry_price=...)`

The accepted-fill bound is valid because execution-tolerance bounds the
executable ask and max-slippage validation is applied to the post-tick-rounded
fill.

### Single Quote Authority

The exact authoritative selected-option `QuoteSnapshot` used to calculate the
MARKET reference must also be passed to `SimulatedPaperBroker.submit()`.

A new quote may not silently inherit the prior RiskGate approval.

### Protective Plan Contract

A strategy-owned option-premium-domain `ProtectivePlanPolicy` is mandatory.

- missing policy -> fail closed
- no generic production fallback
- no underlying/index protective numerical-price reuse
- test-only stubs do not establish production strategy policy

### Additive Runtime Contract

`ConcreteOpenInstruction` is included in the executable-order runtime contract
and `ExecutionResult` validation.

`PaperFillAdapter.evaluate()` directly accepts the MARKET
`ConcreteOpenInstruction`; correctness does not rely only on a broker bypass.

BacktestOrchestrator remains unchanged in accordance with Phase-5 D2.

The option bridge remains standalone at this checkpoint because the verified
PaperTradingRunner Slice-2 boundary intentionally stops before operational
broker/execution integration. Operational wiring follows the later Phase-5
live-paper components.

### Owner-Local Verification

Initial Slice B bridge verification:

- focused bridge tests: **32 passed**
- focused regression group: **300 passed**
- full repository: **1277 passed, 1 skipped, 0 failures**

Quantity single-authority repair verification:

- focused bridge tests: **41 passed**
- focused regression group: **300 passed**
- full repository: **1286 passed, 1 skipped, 0 failures**

Net final increase from the pre-Slice-B repository baseline:

- **+41 permanent Slice B tests**
- zero regressions

### Remaining Status

P0: 0  
P1: 0

Known P2:

- Option Selector strike-rejection diagnostic granularity.

Known deferred P3:

- option LIMIT / STOP / STOP_LIMIT premium-domain entry support.

Phase 5 remains **NOT VERIFIED_COMPLETE**.

The next required Phase-5 architecture step is the broker-independent live
option bid/ask market-data boundary and its integration contract with the
verified Option Selector and MARKET-only option-entry bridge.


## 104. Phase 5 Slice 4A - Live Quote Core Infrastructure - VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Slice 4A establishes the provider-independent live option quote foundation.

### Permanent Boundary

Created production modules:

- `engine/feeds/live_feed.py`
- `engine/feeds/subscription.py`
- `engine/feeds/quote_cache.py`

No existing production module changed.

### Subscription Ownership

`SubscriptionOwnerKey` is immutable and preserves:

- strategy_id
- strategy_version

Logical subscription ownership is:

`InstrumentIdentity -> set[SubscriptionOwnerKey]`

The first owner creates a physical-subscribe requirement.

Additional owners share that requirement.

Only release by the final owner creates a physical-unsubscribe requirement.

### Live Feed Contract

The historical `DataFeed` contract remains synchronous DataFrame-based
historical/bar infrastructure.

Live quote delivery uses a separate provider-neutral `LiveMarketDataFeed`
Protocol.

Core live feed state is limited to:

- DISCONNECTED
- CONNECTED
- RECONNECTING

Provider authentication and broker/exchange token details remain adapter-owned.

### LiveQuoteEvent

The immutable transport envelope contains:

- event_id
- QuoteSnapshot

`QuoteSnapshot.exchange_timestamp` remains market event-time authority.

No wall-clock receive timestamp becomes execution/event-order authority.

### LatestQuoteCache

The cache owns ordering and ambiguity only.

It does not own execution-price policy or an independent staleness threshold.

Per instrument, logical state is:

- EMPTY
- VALID
- AMBIGUOUS

Rules:

- strictly newer timestamp -> accepted
- older timestamp -> rejected
- same timestamp + identical evidence -> duplicate/idempotent
- same timestamp + conflicting evidence -> AMBIGUOUS
- AMBIGUOUS -> no executable cached quote
- only strictly newer valid evidence clears ambiguity
- reused event-id with conflicting payload fails closed
- old corrupt reused event-id cannot lower the conflict recovery boundary

Existing execution/broker contracts remain authoritative for:

- quote staleness
- crossed quote rejection
- fill execution
- slippage
- execution tolerance

### Owner-Local Verification

- focused Slice 4A: **42 passed**
- Phase-5 regression: **319 passed**
- full repository: **1328 passed, 1 skipped, 0 failures**
- net permanent Slice 4A tests: **+42**
- zero regressions

### Completion Status

Phase 5 remains **NOT VERIFIED_COMPLETE**.

The next required architecture step is Slice 4B:
Live Quote Delivery / Live Paper Coordinator pre-implementation audit.


## 105. Phase 5 Slice 4B - Live Paper Coordinator - VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Slice 4B establishes the additive runtime coordination boundary between the
provider-neutral live quote core and SentinelX option paper execution.

### Permanent Runtime Boundary

Production:

- `engine/paper_coordinator.py`

Tests:

- `tests/test_paper_coordinator.py`

### Runtime Context Authority

Mutable account/risk evidence is sampled through `EntryRuntimeContext` at the
authoritative market evaluation timestamp.

Immediate entry:

- runtime context sampled at strategy selection/evaluation time

Deferred pending-entry resume:

- runtime context sampled again at the waking accepted quote exchange timestamp

Pending attempts do not retain stale mutable risk/account state.

### Pending Entry Contract

`PendingOptionEntryAttempt` retains only immutable decision/selection evidence.

An option entry may remain unsubmitted while awaiting the first authoritative
quote for the preselected contract.

Pending validity is bar-bound and market-event-time based.

At the expiry boundary itself, expiry wins; the old signal cannot be
resurrected by an equal-timestamp quote.

### Option Selection / Quote Authority

The coordinator may preselect a contract for subscription purposes.

`OptionEntryBridge` preserves its existing selection/validation authority.

Catalog drift or quote/selection identity mismatch fails closed.

The exact same authoritative `QuoteSnapshot` used for bridge/risk evaluation is
used for broker submission.

No hidden quote refresh occurs after risk approval.

### Subscription Claims

Coordinator-local intent claims allow multiple pending attempts to depend on
the same logical `(SubscriptionOwnerKey, InstrumentIdentity)` ownership.

Pre-existing manager ownership is preserved.

Physical subscribe/unsubscribe authority remains with
`OptionSubscriptionManager` first-owner / final-owner transitions.

### Live Quote Dispatch

Only `QuoteCacheStatus.ACCEPTED` evidence may proceed to broker quote
evaluation and pending-entry resume.

Duplicate, older, ambiguous, conflicted, or reused-event-id-corrupt evidence
does not proceed downstream.

### Disconnect / Reconnect

Disconnect or reconnecting state terminates unsubmitted pending strategy
attempts fail-closed.

Terminated attempts are not revived.

Logical active subscriptions remain available for deterministic physical
resubscription after reconnect.

### Verification

Owner-local:

- public contract inspection: PASS
- `py_compile`: PASS
- focused Slice 4B: **60 passed**
- Phase-5 regression: **361 passed**
- full repository: **1388 passed, 1 skipped, 0 failures**

Pre-Slice-4B baseline:

- **1328 passed, 1 skipped**

Net:

- **+60 permanent tests**
- zero regressions

Known deferred project findings remain:

- P2: Option Selector strike-rejection diagnostic granularity
- P3: option LIMIT / STOP / STOP_LIMIT premium-domain entry support

Phase 5 remains **NOT VERIFIED_COMPLETE**.

The next architecture step is Phase 5 Slice 4C:
operational provider-neutral live market-data integration for underlying
strategy evidence and selected option bid/ask quote delivery.


## 106. Phase 5 Slice 4C-1 - Provider Instrument Mapping and Live Catalog - VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Slice 4C-1 establishes the provider-neutral transport identity and operational
option-catalog snapshot foundation.

### Provider Instrument Mapping

`ProviderInstrumentRef` remains transport-layer authority only.

Provider tokens never become part of canonical `InstrumentIdentity`.

`ProviderInstrumentMapper` provides deterministic bidirectional mapping:

`ProviderInstrumentRef <-> InstrumentIdentity`

The in-memory implementation enforces a strict one-to-one bijection.

Unknown and ambiguous mappings fail closed.

Exact duplicate pairs are idempotent.

### Operational Catalog

`LiveInstrumentCatalog` implements the existing verified
`InstrumentCatalog` protocol unchanged.

Snapshots are completely validated before atomic replacement.

A failed replacement produces zero catalog mutation.

Catalog output is immutable and deterministically ordered.

Conflicting identity or specification authority for the same canonical option
selection key fails closed.

Provider mapping and catalog specification authority remain separate.

### Verification

Owner-local:

- public contract inspection: PASS
- provider SDK isolation: PASS
- py_compile: PASS
- focused Slice 4C-1: **43 passed**
- relevant regression: **206 passed**
- full repository: **1431 passed, 1 skipped, 0 failures**

Previous baseline:

- **1388 passed, 1 skipped**

Net:

- **+43 permanent tests**
- zero regressions

Known deferred findings remain:

- P2: Option Selector strike-rejection diagnostic granularity
- P3: option LIMIT / STOP / STOP_LIMIT premium-domain entry support

Phase 5 remains **NOT VERIFIED_COMPLETE**.

Next:

Phase 5 Slice 4C-2 - provider-neutral live underlying market events,
MarketTimeEvent, deterministic live bar building, and D3a gap evidence.


## 107. Phase 5 Slice 4C-2 - Provider-Neutral Live Market Events, Market Time, and Live Bar Builder - VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Slice 4C-2 establishes the provider-neutral live underlying market-event,
authoritative market-time, missing-interval evidence, and deterministic
live-bar construction boundary.

### Permanent Runtime Boundary

Production module:

- `engine/feeds/live_bar_builder.py`

Permanent tests:

- `tests/test_live_bar_builder.py`

The implementation remains provider-neutral and creates no real broker orders.

### Event Contracts

The Slice 4C-2 boundary includes immutable provider-neutral live evidence for:

- trade ticks
- provider-completed one-minute base bars
- authoritative market-time advancement
- explicit missing-data evidence
- deterministic completed-bar results

Underlying bar construction rejects option contracts.

Market timestamps are timezone-aware exchange/session evidence.

The machine wall clock is not market-ordering authority.

### Gap / Finality Contract

A closed expected trading interval with zero observations creates explicit
`DataGapEvidence`.

No synthetic OHLC is created.

No carry-forward candle is manufactured.

Finalized intervals cannot be rewritten by later evidence.

Backward authoritative market-time fails closed.

Session/calendar authority determines which intervals are expected.

### Multi-Timeframe Contract

Canonical one-minute evidence is the aggregation base.

Larger timeframe output requires complete required base evidence.

Missing constituents cannot create a partial bar presented as complete.

Multi-stream output uses deterministic canonical ordering.

### Ingestion Isolation

Each declared stream owns one ingestion mode:

- TICK
- PROVIDER_BAR

Silent mixing or mode switching fails closed.

One canonical underlying identity may fan out into multiple registered
strategy/timeframe streams while preserving per-stream state isolation.

### Verification

Owner-local verification:

- controlled baseline/hash check: PASS
- contract inspection: PASS
- py_compile: PASS
- critical finality suite: **18 passed**
- focused Slice 4C-2 suite: **100 passed**
- Phase-5 regression: **311 passed**
- full repository: **1531 passed, 1 skipped, 0 failures**

Previous full baseline:

- **1431 passed, 1 skipped**

Net:

- **+100 permanent tests**
- zero regressions

Slice 4C-2:

- P0 = 0
- P1 = 0

Existing non-blocking/deferred project findings remain:

- P2: Option Selector strike-rejection diagnostic granularity
- P3: option LIMIT / STOP / STOP_LIMIT premium-domain entry support

Slice 4C-2 remains part of OD-7 item 6 and does not change the frozen Phase-5
dependency order.

Phase 5 remains **NOT VERIFIED_COMPLETE**.

The next required implementation step is:

**Phase 5 Slice 4C-3 - Provider-Neutral Live Strategy Coordinator.**


## 108. Phase 5 Slice 4C-3 - Provider-Neutral Live Strategy Coordinator - VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Slice 4C-3 establishes the provider-neutral live strategy runtime boundary:

`BoundBarEvent batch`
-> `MarketDataCoordinator`
-> `EvaluationRequest`
-> `safe_generate_signal(mode="live")`
-> `SignalIntake`
-> `LivePaperCoordinator`

### Runtime Ownership

`LiveStrategyCoordinator` does not own:

- provider transport
- quote normalization
- option selection
- RiskGate internals
- simulated broker fills
- virtual account
- persistence
- real broker execution

These remain separate verified or future authorities.

### Strategy Identity

Runtime ownership and policy lookup use:

`SubscriptionOwnerKey(strategy_id, strategy_version)`

No cross-version fallback is allowed.

Strategy halt state is isolated by the same exact owner identity.

### Event-Time / Expiry Authority

Option-entry selection time is the authoritative evaluation decision time.

Next evaluation boundaries are computed through the session-aware
`compute_next_evaluation_boundary(...)` contract.

The boundary may be capped at regular session close.

Decision time at or after regular session close fails closed for V1 rather
than inventing an out-of-session pending boundary.

No local wall clock becomes market-event authority.

### Bounded Runtime State

Per-stream retained live history is bounded according to required strategy
history.

Recent duplicate evidence is also bounded.

Old evaluation suppression is represented by bounded monotonic
per-owner decision-time authority.

Exact recent duplicate bars are idempotent.

Conflicting bar evidence fails closed.

Ancient out-of-retention replay fails closed.

### Forwarding Boundary

`on_market_time_boundary(...)` forwards exact strategy/version/timeframe
evaluation boundaries to `LivePaperCoordinator`.

`on_feed_state_change(...)` forwards connection-state transitions to
`LivePaperCoordinator`.

No pending-entry or subscription lifecycle logic is duplicated.

### Verification

Owner-local:

- documentation hash baseline: PASS
- public contract/source inspection: PASS
- py_compile: PASS
- critical contract subset: **20 passed**
- focused Slice 4C-3: **55 passed**
- Phase-5 regression: **466 passed**
- full repository: **1586 passed, 1 skipped, 0 failures**

Previous full baseline:

- **1531 passed, 1 skipped**

Net:

- **+55 permanent tests**
- zero regressions

Slice 4C-3:

- P0 = 0
- P1 = 0

Known project findings remain:

- P2: Option Selector strike-rejection diagnostic granularity
- P3: option LIMIT / STOP / STOP_LIMIT premium-domain entry support

Slice 4C-3 remains within OD-7 item 6.

Phase 5 remains **NOT VERIFIED_COMPLETE**.

The next required step is:

**Phase 5 Slice 4C-4 - Operational Provider Live Feed Adapter / Serialized Dispatcher - pre-implementation owner decision and contract review.**


## 109. Phase 5 Slice 4C-4 - Upstox V3 Operational Provider Live Feed Adapter - VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Slice 4C-4 establishes the provider-specific operational live market data feed adapter, single-reader bounded serialized dispatcher, and Protobuf normalization boundary.

### Provider Role and Execution Boundaries

Provider: Upstox Market Data Feed V3.
Upstox V3 operates strictly as Phase-5 MARKET DATA provider.

Zero real broker execution is introduced:
- NO real broker order placement
- NO real broker order modification
- NO real broker order cancellation
- NO real funds/positions/holdings authority
- Real broker execution remains strictly Phase 7.

### Permanent Runtime Modules

Production files in `engine/feeds/upstox/`:
- `auth.py`: `UpstoxV3AuthorizationClient`
- `decoder.py`: `UpstoxV3Decoder`
- `catalog_loader.py`: `UpstoxInstrumentCatalogLoader`
- `normalizer.py`: `UpstoxV3Normalizer`
- `dispatcher.py`: `UpstoxSerializedDispatcher`
- `feed.py`: `UpstoxLiveMarketDataFeed`
- `proto/market_data_feed_pb2.py`: Official generated Protobuf code

Permanent test suites in `tests/`:
- `test_upstox_auth.py`
- `test_upstox_decoder.py`
- `test_upstox_catalog_loader.py`
- `test_upstox_normalizer.py`
- `test_upstox_dispatcher.py`
- `test_upstox_feed.py`

### Frozen Architecture Contracts

1. **Provider Identity:** `instrument_key` is the sole canonical provider transport token.
2. **Exchange Token:** `exchange_token` is NOT canonical/stable provider identity.
3. **Authentication:** Fresh V3 `authorized_redirect_uri` requested on each connection/reconnect; secrets redacted from all logs/errors.
4. **Runtime Dependencies:** `pandas==3.0.5`, `protobuf==7.35.1`, `pyarrow==25.0.0`, `websockets==17.0`.
5. **Build-Only Protobuf Authority:** `grpcio-tools==1.83.0` isolated in build tooling; NOT a runtime dependency.
6. **Official Proto Source SHA256:** `E9B74950CC5D0A73D12B26D0B3A9C1F21FBA984A5B14A47FDC165F5080628BBA`.
7. **Generated pb2 SHA256:** `099879ABB1A2C9CFA206F9923B4DCD167CBB939E9FD6DEB7A48BBB10EEB11E24`.
8. **Subscription Mode:** Command-side JSON uses `"mode": "full"`.
9. **Decoded Mode:** Decoded Protobuf Feed level uses `RequestMode.full_d5`.
10. **Bounded Dispatcher:** Default capacity `10,000` frames; single-reader / single-consumer model.
11. **Reader Authority:** Exactly one reader authority per connection generation.
12. **Generation Counter:** Monotonically increasing `generation_id` per connection attempt.
13. **Stale Generation:** Dropped before enqueue/dispatch with zero engine-state mutation.
14. **Queue Overflow:** Fails closed immediately -> invalidates generation -> drains queue -> triggers `RECONNECTING`.
15. **Corrupt Protobuf:** Fails closed immediately -> invalidates generation -> triggers reconnect.
16. **Deterministic Normalization:** Intra-packet processing strictly follows `sorted(response.feeds.keys())`.
17. **MarketTimeEvent Ordering:** Dispatched strictly AFTER same-packet instrument evidence has completed dispatch.
18. **Quote Timestamp Authority:** `QuoteSnapshot.exchange_timestamp` uses timezone-aware `FeedResponse.currentTs`.
19. **LTPC LTT Role:** `ltpc.ltt` is last-trade metadata only; strictly NOT depth quote ordering authority.
20. **CurrentTs Integrity:** `currentTs <= 0` FAILS CLOSED with `UpstoxNormalizerError`; ZERO local wall-clock fallback (`datetime.now`, `datetime.utcnow`, `time.time`).
21. **Provider Bar Start:** Exact provider `marketOHLC.ohlc.ts` owns bar start.
22. **I1 Completion Finality:** Completed `LiveProviderBar` emitted ONLY when `currentTs >= bar_start + 1 minute`.
23. **No Synthetic Future Time:** `exchange_timestamp` set to `currentTs`; never exceeds `currentTs`.
24. **No Fake Index Quantity:** Actual provider `vol` mapped without synthetic trade quantity or ticks.
25. **Index Underlying Path:** NIFTY / BANKNIFTY provider OHLC normalized through existing `LiveProviderBar` path.
26. **Catalog Effective From:** Authoritative business date of the Upstox BOD snapshot from which specification was loaded; NOT contract listing date.
27. **Prior Snapshot Preservation:** Previous validated BOD snapshot preserves original business date.
28. **No Silent Carry-Forward:** Slice 4C-4 does NOT own silent snapshot-source carry-forward.
29. **No Validated Source:** Fails closed atomically on invalid candidate records.

### Verification

Owner-local verification:
- controlled documentation baseline/hash check: PASS
- public contract/source inspection: PASS
- py_compile: PASS
- critical repaired test files: **24 passed**
- all Upstox focused suite: **49 passed**
- Phase-5 regression: **668 passed**
- full repository: **1635 passed, 1 skipped, 0 failures**
- static wall-clock authority scan: **0 occurrences**

Previous full repository baseline:
- **1586 passed, 1 skipped**

Net Slice 4C-4 increase:
- **+49 permanent tests**
- zero repository regressions

Slice 4C-4 defect status:
- P0 = 0
- P1 = 0

Known project findings remain unchanged:
- P2: Option Selector strike-rejection diagnostic granularity
- P3: option LIMIT / STOP / STOP_LIMIT premium-domain entry support

### Roadmap Alignment

- Sub-slices 4C-1 through 4C-4 complete OD-7 item 6 (**OD-7 ITEM 6 — VERIFIED_COMPLETE**).
- Actual live-market automated paper-trading promotion verification remains a later Phase-5 requirement.
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Real broker execution remains strictly Phase 7.

The next required step is:

**Phase 5 — OD-7 Item 7 — Virtual Account + Live MTM — pre-implementation owner decision and contract review.**


## 110. Phase 5 OD-7 Item 7 — Virtual Account + Live MTM — VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Item 7 establishes the in-memory stateful `VirtualPaperAccount`, conservative executable-BID live mark-to-market valuation, 5-second market-time staleness boundary, pre-submit premium cash commitment reservations, and atomic broker-fill accounting parity with canonical D5 backtest cost modeling.

### Production Architecture & Ownership Contracts

1. **VA-1 (Single Mutable Account Owner):** `VirtualPaperAccount` is the sole mutable live-paper account owner. `PortfolioAccount` remains the pure canonical accounting-transformation authority. `SimulatedPaperBroker` owns order/fill lifecycle only.
2. **VA-2 (Single Shared Capital Pool):** Starting capital is owned as a single account-level shared capital pool across strategies under D14.
3. **VA-3 (Fill-Driven Mutation):** Only canonical `FILLED` broker evidence mutates settled cash, open positions, average entry prices, quantities, and gross realized P&L.
4. **VA-4 / VA-4A (Premium Cash Commitments):** `RiskGate` owns stop-risk commitments. `VirtualPaperAccount` separately owns pending PAPER premium cash commitments:
   $$\text{premium\_commitment} = \text{approved\_quantity} \times \text{worst\_permitted\_fill\_price} \times \text{contract\_multiplier}$$
   $$\text{available\_cash} = \text{snapshot.cash} - \sum(\text{active premium commitments})$$
5. **VA-4B (Reservation Timing):** Cash reservation occurs after option entry is approved by `RiskGate` and strictly before broker submission.
6. **VA-4C (Reservation Identity):** Reservation identity is keyed by canonical `entry_intent_identity`.
7. **VA-4D (Reservation Release):** Synchronous broker rejections/exceptions immediately release pre-submit reservations. Submitted-order reservations release on authoritative terminal disposition (`FILLED`, `EXPIRED`, `CANCELLED`, `REJECTED`).
8. **VA-5 (Multi-Strategy Isolation):** Multiple strategies share account cash under D14 while open positions remain strictly isolated by `PositionKey(strategy_id, strategy_version, identity)`.
9. **VA-6 (Conservative BID Mark):** Current long option MTM uses authoritative executable `bid_price`. No fallback to LTP, mid, or ASK is permitted.
10. **VA-7 / VA-7A (5-Second Staleness Boundary):** Invalid or missing BID marks position `STALE` (or `UNAVAILABLE` if no prior mark). Stale threshold is exactly 5 seconds ($>5\text{s} \implies \text{STALE}$; $0 \le \text{age} \le 5\text{s} \implies \text{LIVE}$; $\text{age} < 0 \implies \text{UNAVAILABLE}$). Aging authority is provider-neutral `MarketTime`, never local wall clock.
11. **VA-7B (Sidecar Valuation Metadata):** Valuation states (`LIVE`, `STALE`, `UNAVAILABLE`) and reasons are tracked in sidecar metadata (`PositionValuationRecord`) without mutating core immutable `AccountSnapshot` / `PositionSnapshot` schemas.
12. **VA-7C / VA-7D (Valuation Gating):** `VirtualPaperAccount.on_market_time(...)` advances valuation age. Any held position in `STALE` or `UNAVAILABLE` state marks account valuation non-actionable, rejecting new signal intake before `RiskGate`.
13. **VA-8 / VA-9 (Gross Equity & Timestamp Authority):** `AccountSnapshot.equity` remains canonical gross marked equity. Mark timestamp is `QuoteSnapshot.exchange_timestamp`. Zero local wall clock authority (`datetime.now`, `datetime.utcnow`, `time.time`).
14. **VA-10 (Feed Disconnection & Reconnection):** `DISCONNECTED` / `RECONNECTING` transitions set all held positions to `STALE`. `CONNECTED` alone does NOT restore `LIVE`; fresh accepted quote on exact held contract is required.
15. **VA-11 / VA-11A / VA-11B / VA-11C (Broker Terminal Events & Single Authority):** `VirtualPaperAccount` consumes `BrokerTerminalEvent` stream. Identical duplicate fills are idempotent; conflicting duplicates fail closed. `LivePaperCoordinator` enforces single runtime-context authority (`virtual_account.get_entry_runtime_context`), rejecting conflicting providers with `ValueError`. Legacy Slice-4B mode (`virtual_account=None`) remains supported.
16. **VA-12 (In-Memory Scope):** Item 7 is strictly in-memory and non-restart-safe until OD-7 Item 9 SQLite persistence.
17. **VA-13 (D5 Cost Parity):** `AccountSnapshot` maintains gross accounting. Canonical completed-trade transaction costs are assessed via `TradeLedger` and `CostCalculator`, exposing `gross_equity`, `recognized_costs`, and `cost_adjusted_equity` without altering gross accounting semantics.

### Production Runtime Wiring Verified

1. **MarketTime Wiring:** Live feed `add_market_time_listener` $\longrightarrow$ `LivePaperCoordinator._on_market_time_event` $\longrightarrow$ `VirtualPaperAccount.on_market_time`.
2. **Feed State Wiring:** Live feed `add_state_listener` $\longrightarrow$ `LivePaperCoordinator.on_feed_state_change` $\longrightarrow$ `VirtualPaperAccount.on_feed_state_change`.
3. **Terminal Dispatch Wiring:** `LivePaperCoordinator.cancel_order` and `expire_day_session` dispatch terminal events directly into `VirtualPaperAccount.on_broker_terminal_event`.
4. **Opening vs Closing Fill Invariant:** Opening `BUY` fill without active reservation breaches accounting integrity; closing / exit fills (`ConcreteCloseInstruction` or non-BUY action) do not require opening reservations.

### Verification Evidence

- Production wiring contract: **PASSED**
- Zero wall-clock scan: **PASSED (0 occurrences)**
- py_compile: **PASSED**
- Item-7 focused tests: **87 passed**
- Live-feed + Item-7 integration regression: **527 passed**
- Full repository test suite: **1662 passed, 1 skipped, 0 failures**

### Roadmap Status

- **OD-7 ITEM 7 — VERIFIED_COMPLETE**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 8 — Live-Price SL / Target / Trailing — pre-implementation owner decision and contract review.**


## 111. Phase 5 OD-7 Item 8 — Live-Price SL / Target / Trailing — VERIFIED_COMPLETE

Owner-local status: **VERIFIED_COMPLETE**.

Item 8 establishes tick/quote-driven live protective exit evaluation (stop-loss, target, trailing excursion/stop) and broker execution bridging, adapting accepted live option quote evidence to canonical protective domain contracts while enforcing strict trigger-versus-fill separation, BID trigger authority, trailing non-retroactivity, OCO fill-timing finality, and pending-close concurrency locks.

### Production Architecture & Ownership Contracts

1. **PE-1 (Materialization Timing):** Protective state materializes only after confirmed opening BUY `FILLED`. No protection exists at signal approval or broker submission.
2. **PE-2 (Long Option Stop Authority — OWNER_APPROVED):** Long option STOP triggers when `quote.bid_price <= stop_price`.
3. **PE-3 (Long Option Target Authority — OWNER_APPROVED):** Long option TARGET triggers when `quote.bid_price >= target_price`.
4. **PE-4 (Trailing Excursion Authority — OWNER_APPROVED):** Long option trailing favorable excursion advances when `quote.bid_price > reference_extreme`.
5. **PE-5 (Trailing Stop Authority — OWNER_APPROVED):** Long option trailing stop triggers when `quote.bid_price <= current_stop`.
6. **Authoritative BID Trigger Evidence:** Executable `bid_price` is the sole authoritative liquidation trigger evidence for long option positions. Missing/invalid BID produces zero triggers. No fallback to LTP, MID, ASK, or underlying spot.
7. **PE-6 (Execution Price Authority Separation):** `PaperBroker` remains the actual execution-price authority. Trigger evidence and execution fill price remain separate authorities.
8. **PE-7 (Fresh Quote Mark Requirement):** Protective evaluation requires fresh accepted exact-contract quote evidence. STALE / UNAVAILABLE valuation marks never evaluate or trigger exits.
9. **PE-8 / PE-25 (Single In-Flight Close Authority & Pending-Close Lock):** At most one active live protective close per `PositionKey`. `_pending_closes[PositionKey]` suppresses duplicate/competing protective submissions while a close order is in flight.
10. **PE-9 (Terminal Failure & Re-Arming):** Protective close `REJECTED`, `EXPIRED`, or `CANCELLED` clears the pending-close lock, leaves held position intact, and keeps protective exit `ACTIVE` so subsequent fresh accepted quotes can re-trigger.
11. **PE-10 (Held Quantity Sizing):** Protective quantity strictly follows current held position quantity. `reconcile_position(...)` delegates to canonical book logic for partial reduction or full-close cleanup.
12. **PE-11 (Session Expiry Non-Fabrication):** Session expiry does not fabricate position liquidation. Pending protective close may expire while active protection remains for later fresh session evidence.
13. **PE-12 / PE-16 (OCO Cancellation on Confirmed Fill):** OCO sibling cancellation occurs ONLY after confirmed `BrokerTerminalEvent(FILLED)`. Triggering alone does not mutate protective state or cancel siblings.
14. **PE-13 (In-Memory Scope):** Item 8 is strictly in-memory and non-restart-safe until OD-7 Item 9 SQLite persistence.
15. **PE-14 (Feed Disconnect / Reconnect Resilience):** Disconnection / reconnecting produces zero synthetic protective triggers. Protection remains in memory and resumes on fresh accepted quote.
16. **PE-15 (TRIGGERED != FILLED):** Live evaluator detects triggers and submits `ConcreteCloseInstruction` without calling backtest-synchronous `ProtectiveExitBook.evaluate(...)`.
17. **PE-17 / PE-18 (Pre-Entry Plan Retention & Consumption):** Pre-entry protective plan is retained deterministically by submitted opening order identity and consumed exactly once upon opening fill. Stop/target levels are absolute premium levels computed before submission using `worst_permitted_fill` without post-fill re-anchoring.
18. **PE-19 (Trailing Non-Retroactivity):** Trailing live `effective_after` uses `QuoteSnapshot.exchange_timestamp`. A newly ratcheted trailing level is effective only for subsequent quotes ($Q.\text{exchange\_timestamp} > \text{effective\_after}$); the ratcheting quote cannot retroactively trigger the new stop.
19. **PE-20 (Live Quote-Cycle Processing Sequence):**
    1. Broker evaluates pending orders.
    2. Collect terminal broker events.
    3. Process terminal broker events (FILLED $\to$ virtual account update $\to$ materialize opening plan / consume protective fill via `record_external_fill` and reconcile position; REJECTED/CANCELLED/EXPIRED $\to$ discard retained plan / clear pending close lock).
    4. Apply current QuoteSnapshot MTM to `VirtualPaperAccount`.
    5. Evaluate live protection against `quote.bid_price` (including immediate same-quote post-fill evaluation).
    6. Submit close order to `PaperBroker` and establish pending-close lock.
    7. Resume deferred opening candidates LAST.
20. **PE-21 / PE-22 (Public Domain Completion API & Encapsulation):** `ProtectiveExitBook.record_external_fill(protective_id, *, termination_reason="filled")` added as minimal additive domain API. Live code never touches `_exits` or `_cancel_siblings`.
21. **PE-23 (Opening Failure Plan Discard):** Opening order `REJECTED`, `EXPIRED`, or `CANCELLED` discards retained pre-entry protective plan.
22. **PE-24 (Same-Quote Post-Fill Evaluation):** After opening fill is booked and protection materialized, the same fresh accepted quote immediately evaluates protection, eliminating the unprotected gap.

### Component Design & Responsibilities

- **`LiveProtectiveEvaluator` (`engine/protective_live.py`):**
  - Evaluates fresh accepted `QuoteSnapshot` against active protective exits using `bid_price`.
  - Manages trailing state advancement with timezone-aware `QuoteSnapshot.exchange_timestamp`.
  - Resolves triggered exits into `ConcreteCloseInstruction` and tracks in-flight close provenance via `LiveProtectivePendingClose`.
  - Routes external fills and terminal failures through public `ProtectiveExitBook` completion APIs.
  - Does NOT own portfolio accounting, fill simulation, provider normalization, or wall-clock timing.
- **Protective Close Action:**
  - `SELL` exact held option contract keyed by `PositionKey(strategy_id, strategy_version, InstrumentIdentity)`.
  - Zero underlying substitution, alternate strike, alternate expiry, or provider token identity.
- **Protective Fill Semantic Ordering:**
  - `BrokerTerminalEvent(FILLED)` $\longrightarrow$ `VirtualPaperAccount` canonical accounting $\longrightarrow$ `ProtectiveExitBook.record_external_fill(...)` $\longrightarrow$ OCO sibling cancellation $\longrightarrow$ `reconcile_position(...)` $\longrightarrow$ pending-close lock release.
  - If canonical account application fails, protective domain does not mark fill complete.
- **Accounting / Cost Parity:**
  - Protective trigger causes ZERO direct accounting mutation.
  - Only confirmed broker fills through `VirtualPaperAccount` $\longrightarrow$ `PortfolioAccount` mutate settled cash, open positions, and realized P&L.
  - Transaction costs follow Item-7 canonical `TradeLedger` and `CostCalculator` (D5 parity).

### Verification Evidence

- Item-8 source contract: **PASSED**
- Zero wall-clock scan: **PASSED (0 occurrences)**
- Private protective-state access scan: **PASSED**
- py_compile: **PASSED**
- Item-8 focused tests: **93 passed**
- Protective integration regression: **250 passed**
- Phase-5 live regression: **560 passed**
- Full repository test suite: **1681 passed, 1 skipped, 0 failures**

Final owner-local marker:

`OD7_ITEM8_LIVE_PROTECTIVE_ENGINE_OWNER_LOCAL_VERIFIED_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 8 — VERIFIED_COMPLETE**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 9 — SQLite atomic / fail-closed persistence — pre-implementation owner decision and contract review.**

## 112. Phase 5 OD-7 Item 9 — SQLite Atomic / Fail-Closed Persistence — VERIFIED_COMPLETE

### Production Architecture & Ownership Contracts

1. **D9 (Atomic & Fail-Closed SQLite Persistence):** SQLite persistence is strictly atomic and fail-closed. `SQLitePaperStateStore` is the single authority owning physical database transactions. Canonical domain objects (`VirtualPaperAccount`, `SimulatedPaperBroker`, `LiveProtectiveEvaluator`, `TradeLedger`, `RiskGate`) remain the operational domain authorities; SQLite is not a secondary calculation engine.
2. **Durable Aggregate State:** Restart-critical state includes `AccountSnapshot` / positions, premium cash commitments, `PendingRiskCommitment` exact evidence, broker queued and terminal order lifecycle, per-instrument broker event-time watermarks, entry-intent dedup lifecycle, retained protective plans, `ProtectiveExitBook` exits, trailing stop state, pending protective closes, `TradeLedger` records, complete `CostAssessment` history, processed-fill idempotency evidence, `RiskGateState`, accounting sequence, accounting-integrity breach status, and persistence metadata.
3. **PendingRiskCommitment Exactness:** `PendingRiskCommitment` fields (`entry_identity`, `intended_position_key`, `approved_quantity`, `nominal_stop_risk`) round-trip with 100% exact numerical and object equality. `nominal_stop_risk` is persisted as exact Decimal TEXT and loaded directly from SQLite on restart without caller recomputation. Missing, non-positive, or corrupted nominal stop risk fails closed (`PersistenceCorruptedError`). `PaperHydratedState` exposes restored `pending_risk_commitments`.
4. **CostAssessment Lossless Exactness:** `CostAssessment` persistence is complete and lossless. Full constituent `CostComponentResult` breakdowns (basis, rate, unrounded amount, amount, leg event keys), `ScheduleReference` items, and closed `TradeRecord` evidence round-trip exactly. Persisted historical assessments are restored as authoritative historical evidence without recomputation from current cost schedules. Missing or malformed JSON, contradictory column vs JSON `total_cost`, or empty component restoration for non-empty records fails closed (`PersistenceCorruptedError`).
5. **SQLite WAL & Durability Contract:** Enforces `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = FULL;`, `PRAGMA busy_timeout = 5000;`. Durability is provided according to SQLite, operating-system, filesystem, and storage-device guarantees under WAL + `synchronous=FULL`.
6. **Database Compatibility Authority:** Validates `schema_version` (1), `database_instance_id`, `account_id`, `currency`, `monetary_quantum`, `starting_capital`, `paper_session_id`, `risk_policy_identity`, `cost_schedule_fingerprint`, `execution_policy_identity`, and `state_generation`. `paper_session_id` remains stable across restarts of the same session. Incompatible contracts or state-affecting identity mismatches fail closed with `DatabaseIdentityMismatchError` or `IncompatibleContractError` without silent database recreation.
7. **`state_generation` Semantics:** SQLite transaction atomicity is the aggregate consistency authority. `state_generation` is a monotonic committed-transaction sequence / diagnostic metadata field only; it is not a full-table snapshot requirement. Older unchanged rows do not need to equal the latest generation.
8. **D11 Three-Layer Restart Deduplication:** Restores 3-layer dedup authority: (1) feed/event dedup, (2) entry-intent dedup, (3) broker-order dedup. Persisted entry-intent lifecycle restores coordinator dedup authority so identical replayed signals after restart are rejected before RiskGate evaluation, cash reservation, or broker submission.
9. **Broker Event-Time Watermark:** Per-instrument `last_exchange_ts` watermark is persisted. Quotes with `quote.exchange_timestamp <= last_exchange_ts` are ignored for fill evaluation; quotes with `quote.exchange_timestamp > last_exchange_ts` are eligible for evaluation. Restart does not reset broker event-time authority.
10. **Restart Valuation Non-Liveness:** Held positions restore strictly as `STALE` or `UNAVAILABLE` (`reason="restart_hydration"`), never immediately `LIVE`. Fresh accepted exact-contract quote evidence is required before valuation becomes `LIVE`. Persisted display marks are not executable evidence.
11. **Transaction Failure & Terminal Poisoning:** All durable consequences of a coordinator transition are executed inside an atomic SQLite transaction. If SQLite write or commit fails after in-memory state mutation, `PersistenceHealth` transitions to `FAILED`, the current runtime becomes terminally poisoned, and all further state-changing operations are rejected. Recovery requires process restart and rehydration from the last successfully committed SQLite state.
12. **Atomic Transition Families T1–T6:**
    - **T1:** Entry submission lifecycle + risk/premium commitment + retained protective plan + broker pending order.
    - **T2:** Opening order `FILLED` + account state + ledger/cost + processed fill idempotency evidence + reservation release + protective plan materialization.
    - **T3:** Protective trigger submission + pending protective close lock + broker queued close order.
    - **T4:** Protective order `FILLED` + account/ledger/cost + processed fill + protective/OCO/reconciliation cleanup + pending-close release.
    - **T5:** Cancel / expire / reject terminal event + appropriate reservation / plan / pending-close cleanup.
    - **T6:** Trailing stop ratchet state advancement.
13. **Serialization & Type Safety:** Zero `pickle` usage. Zero SQLite `REAL` types for monetary columns; all monetary values stored as exact `TEXT` Decimals. All datetimes serialized as timezone-aware UTC/IST ISO strings.
14. **Fail-Closed Startup Integrity Validation:** Startup gate validates database metadata, schema compatibility, foreign key integrity, canonical JSON decodes, and cross-table referential consistency. Contradictory durable state fails closed with `PersistenceCorruptedError` without silent repair.

### Component Design & Responsibilities

- **`engine/persistence/schema.py`**:
  - DDL definition for schema V1 tables: `paper_metadata`, `account_state`, `positions`, `premium_commitments`, `broker_orders`, `broker_watermarks`, `entry_intents`, `retained_protective_plans`, `protective_exits`, `protective_pending_closes`, `trade_records`, `trade_pending_lifecycles`, `trade_legs`, `trade_processed`, `cost_assessments`, `risk_gate_state`, and `processed_fills`.
  - PRAGMAs: `foreign_keys = ON`, `journal_mode = WAL`, `synchronous = FULL`, `busy_timeout = 5000`.
- **`engine/persistence/sqlite_store.py`**:
  - `SQLitePaperStateStore`: Single authority for durable state and transactions.
  - `PaperHydratedState`: Immutable container holding restored domain state, including `pending_risk_commitments`.
  - Atomic transaction methods `save_t1_entry_submission`, `save_t2_opening_fill`, `save_t3_protective_submission`, `save_t4_protective_fill`, `save_t5_terminal_cancellation`, `save_t6_trailing_ratchet`.
  - Terminal poisoning context manager: Any write/commit failure immediately sets `PersistenceHealth.FAILED`.
  - Exact round-trip serialization routines for `TradeRecord`, `TradeLeg`, `CostAssessment`, `ExecutionResult`, `PreEntryProtectivePlan`, `OrderRequest`, `AccountSnapshot`, `PositionSnapshot`, `PremiumCommitmentRecord`.

### Verification Evidence

- Controlled document hash guard: **PASSED**
- Critical Item-9 source contract: **PASSED**
- SQLite schema safety: **PASSED**
- Static wall-clock / pickle audit: **PASSED**
- py_compile: **PASSED**
- Critical restart-exactness tests: **6 passed**
- Full Item-9 persistence suite: **21 passed**
- Affected-component regression: **346 passed**
- Phase-5 live regression: **657 passed**
- Full repository test suite: **1702 passed, 1 skipped, 0 failures**

Final owner-local marker:

`OD7_ITEM9_SQLITE_PERSISTENCE_OWNER_LOCAL_VERIFIED_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 9 — VERIFIED_COMPLETE**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 10 — Safety / Disconnect / Kill-Switch — pre-implementation owner decision and contract review.**

## 113. Phase 5 OD-7 Item 10 — Safety / Disconnect / Kill-Switch — VERIFIED_COMPLETE

### Production Architecture & Ownership Contracts

1. **Safety Orchestration Model & Authority Separation:** `LivePaperCoordinator` is the single serialized safety orchestration authority. `SafetyManager` is an encapsulated domain helper calculating derived effective safety state from separate, non-duplicated canonical authorities:
   - `LiveMarketDataFeed.connection_state`: Transport connection authority (`FeedConnectionState`).
   - `SQLitePaperStateStore.PersistenceHealth`: Persistence authority (`PersistenceHealth.HEALTHY` vs `PersistenceHealth.FAILED`).
   - `VirtualPaperAccount.accounting_integrity_breached`: Canonical accounting integrity authority (persisted in `account_state`).
   - `SafetyManager.is_kill_switch_active`: Durable kill-switch authority (persisted in `safety_state`).
2. **Derived Effective Safety Precedence:** Precedence strictly follows:
   `PERSISTENCE_FAILED > INTEGRITY_BREACHED > KILL_SWITCH_ACTIVE > DISCONNECTED > OPERATIONAL`.
   `DISCONNECTED`, `PERSISTENCE_FAILED`, and `INTEGRITY_BREACHED` are not stored as redundant flags in `safety_state`.
3. **Durable Item-10 Schema V2 Authority:** Schema Version is advanced to `SCHEMA_VERSION = 2`. The new durable table `safety_state` references `account_state(account_id)` and stores exclusively the kill-switch authority (`account_id`, `kill_switch_active`, `kill_switch_reason`, `activation_source`, `activation_market_timestamp`, `activated_at`).
4. **Schema Version Policy:** Clean new databases are created as Schema V2. Existing Schema V1 databases fail closed on initialization with `DatabaseIdentityMismatchError` (`Incompatible schema_version: database has 1, expected 2`). Zero automatic migration, zero silent upgrade, and zero destructive recreation.
5. **Feed Disconnect Safety (SAF-4 & SAF-5):**
   - Disconnect immediately blocks all new signal intake.
   - All queued OPENING paper orders are cancelled, releasing premium cash reservations, `PendingRiskCommitment`, and retained pre-entry protective plans.
   - All queued protective close orders are cancelled, clearing the pending-close lock and re-arming the corresponding `ProtectiveExit` as `ACTIVE` to re-trigger on subsequent fresh quotes.
   - Held positions remain held. Zero disconnect auto-liquidation.
6. **Administrative Cancellation Timestamp Authority (SAF-24):** Administrative cancellations (feed disconnect, kill switch, strategy shutdown) use the latest accepted authoritative `MarketTime` if available, falling back to the persisted order's `submission_market_timestamp`. Zero wall clock (`datetime.now()`), zero fabricated later exchange timestamp.
7. **Ordinary Reconnect Freshness:** Socket `CONNECTED` state alone is insufficient to return to `OPERATIONAL`. Held positions require post-reconnect fresh accepted exact-contract executable `bid_price` and `ValuationState.LIVE`. Zero held positions require post-reconnect authoritative `MarketTime` / quote evidence. Zero fabricated provider ACK requirement.
8. **Required Subscription / Data Readiness (R1):** Every held protected `InstrumentIdentity` requires fresh accepted exact-contract BID evidence in `LatestQuoteCache` post-reconnect. Missing market evidence fails closed with `required_subscriptions_not_ready` or `held_positions_valuation_not_live`. Zero held positions do not require fabricated option-subscription confirmation.
9. **Session-Time Regression Guard (R2):** Explicit resume validates the latest authoritative `MarketTime` against canonical session history (`_last_canonical_session_date`) and persisted `RiskDay.session_date`. If date regresses, resume fails closed with `session_time_regression`. Zero system wall clock, zero second RiskDay authority, zero silent RiskDay reset.
10. **Manual Kill Switch Activation & Sequencing (SAF-8 & SAF-12):**
    - Idempotent public `activate_kill_switch` API.
    - Persist-first ordering: (1) block new entries in serialized coordinator context, (2) persist `kill_switch_active = TRUE` first, (3) cancel queued simulated orders, (4) persist T5 cancellations, (5) keep runner halted.
    - Kill switch NEVER automatically resumes.
11. **Restart with Active Kill Switch & K2 Crash Cleanup (SAF-10 & R3):** Active kill switch survives restart via SQLite hydration. Startup restores Schema V2 state, restores active kill, blocks new entries, and deterministically cleans up any remaining persisted queued paper orders. Already-cancelled orders remain terminal without duplication or conflict. Verified by `test_crash_k2_partial_kill_cancellation_restart_finishes_cleanup`.
12. **Protective Autonomy (SAF-13 & SAF-26):** While `KILL_SWITCH_ACTIVE`, new entries are prohibited, but held-position protective exits (`STOP_LOSS`, `TARGET`, `TRAILING_STOP`) evaluate on fresh executable BID quotes and submit reduce-only closes to `SimulatedPaperBroker`. Zero blanket liquidation, zero stale/replayed quote execution.
13. **Manual Reduce-Only Close (SAF-14 & SAF-27):** `manual_close_position(...)` allows manual liquidation of held positions during `KILL_SWITCH_ACTIVE` if safety state is otherwise healthy. Sized strictly $\le$ held position quantity, validated against held contract, submitting reduce-only `ConcreteCloseInstruction` via `PortfolioAccount.resolve_exit`. Forbidden under `PERSISTENCE_FAILED` or `INTEGRITY_BREACHED`.
14. **Persistence Failure & K6 Commit-Failure Terminal Poisoning (SAF-16 & R4):** Persistence failure sets `PersistenceHealth.FAILED` and derives `SafetyState.PERSISTENCE_FAILED`, terminally poisoning the runtime. If SQLite commit fails during `resume_from_kill_switch`, resume fails with `persistence_commit_failed`, in-memory kill remains active, persistence is marked `FAILED`, and the database retains last committed kill-active truth. Verified by `test_crash_k6_resume_commit_failure_terminally_poisons_runtime`.
15. **Accounting Integrity (SAF-15):** `VirtualPaperAccount.accounting_integrity_breached` is owned by the virtual account and persisted in `account_state`. When breached, effective safety state is `INTEGRITY_BREACHED` and entries/resumes are blocked.
16. **Explicit Prerequisite-Gated Resume (SAF-11 & SAF-32):** Resume is explicit only. Prerequisites validated FIRST: `PersistenceHealth.HEALTHY`, accounting integrity clean, feed `CONNECTED`, zero pending kill-cleanup orders, fresh market evidence, held valuation `LIVE`, required subscriptions ready, zero session regression. Persists `kill_switch_active = FALSE` atomically before clearing in-memory kill state and restoring entry processing.
17. **WebSocket Liveness & Alert Surfacing:** Reuses existing WebSocket ping/pong transport liveness. Alert surfacing implemented via `SafetyAlert`, `SafetyTransitionResult`, `SafetyResumeResult`, structured logging, and local callback. Zero external cloud dependencies.

### Component Design & Responsibilities

- **`engine/safety.py` (NEW):**
  - Defines `SafetyState` enum, `KillSwitchState` dataclass, `SafetyAlert`, `SafetyTransitionResult`, `SafetyResumeResult`.
  - `SafetyManager`: Encapsulates kill switch durable authority, derive-effective-state precedence calculation, and alert emission.
- **`engine/persistence/schema.py`:**
  - Advances `SCHEMA_VERSION = 2`.
  - DDL for `safety_state` table with foreign key `FOREIGN KEY (account_id) REFERENCES account_state(account_id)`.
- **`engine/persistence/sqlite_store.py`:**
  - `save_safety_state(...)`: Atomic transaction for durable kill-switch state.
  - Hydrates `PaperHydratedState.kill_switch_state`.
  - Fail-closed Schema V2 validation.
- **`engine/paper_coordinator.py`:**
  - Wires `SafetyManager`, derived `safety_state` property, `latest_market_timestamp`, `on_market_time`.
  - Enforces disconnect order cancellations, persist-first kill switch activation, prerequisite-gated explicit resume, protective autonomy, manual reduce-only close, session regression check, and startup kill cleanup.
- **`engine/portfolio/virtual_account.py`:**
  - Exposes `@property def accounting_integrity_breached(self) -> bool`.

### Verification Evidence

- Runtime Schema V2: **PASSED**
- Actual SQLite durable-authority inspection: **PASSED**
- Static wall-clock / pickle / SQL REAL audit: **PASSED**
- py_compile: **PASSED**
- Schema V2 direct tests: **2 passed**
- Final repair tests (K2, K6, R1, R2): **5 passed**
- Item-10 safety suite: **23 passed**
- Affected-component regression: **410 passed**
- Phase-5 live regression: **936 passed**
- Full repository test suite: **1725 passed, 1 skipped, 0 failures**

Final owner-local marker:

`OD7_ITEM10_SAFETY_OWNER_LOCAL_VERIFIED_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 10 — VERIFIED_COMPLETE**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 11 — D16 Audit / Event Envelope — pre-implementation owner decision and contract review.**

---

## 114. Phase 5 OD-7 Item 11 — D16 Audit / Event Envelope — VERIFIED_COMPLETE

### Production Architecture & Ownership Contracts

1. **Audit Journal Purpose & Authority Separation:**
   - Item 11 implements the Phase-5 D16 audit/event envelope (`sentinelx-audit-envelope/v1`) and durable local historical evidence journal.
   - The audit journal is **historical evidence**; it is NOT accounting authority, broker authority, RiskGate authority, TradeLedger authority, protective state authority, or reconciliation authority.
   - Canonical domain/state tables (`account_state`, `positions`, `orders`, `protective_exits`, `safety_state`) remain authoritative current-state truth.
   - `SQLitePaperStateStore` is the sole durable journal persistence owner.
   - `LivePaperCoordinator` produces and orchestrates business evidence.
2. **Durable Item-11 Schema V3 Authority:**
   - Schema Version is advanced to `SCHEMA_VERSION = 3`.
   - The new durable table `audit_events` stores all structured event envelopes with indexes on `event_type`, `(aggregate_type, aggregate_identity)`, `correlation_id`, `market_timestamp`, `broker_order_identity`, `trade_id`, and `protective_id`.
   - Clean new databases are created as Schema V3. Existing Schema V1 and V2 databases fail closed on initialization with `DatabaseIdentityMismatchError`. Zero automatic migration, zero silent upgrade, and zero destructive recreation.
3. **Audit Envelope Model (`sentinelx-audit-envelope/v1`):**
   - Core sparse fields: `audit_sequence`, `event_id`, `event_schema_version`, `event_family`, `event_type`, `aggregate_type`, `aggregate_identity`, `market_timestamp`, `recorded_at_utc`, `state_generation`, `transaction_event_ordinal`, `correlation_id`, `causation_event_id`, `strategy_id`, `strategy_version`, `instrument_key`, `position_key_json`, `entry_intent_identity`, `broker_order_identity`, `trade_id`, `protective_id`, `payload_version`, `payload_json`.
   - `recorded_at_utc` is diagnostic UTC operational observation time only. `market_timestamp` remains authoritative market-time evidence. `recorded_at_utc` MUST NEVER be described as trading authority.
4. **D16 Event-Family Taxonomy (E1–E20):**
   - Covers 20 canonical families: `SESSION`, `FEED_CONNECTIVITY`, `STRATEGY_SIGNAL`, `OPTION_SELECTION`, `ENTRY_INTENT`, `RISK_DECISION`, `CAPITAL_RESERVATION`, `ORDER_LIFECYCLE`, `FILL`, `ACCOUNTING`, `TRADE_LEDGER`, `COST_ASSESSMENT`, `PROTECTIVE_LIFECYCLE`, `SAFETY_KILL_SWITCH`, `PERSISTENCE_FAILURE`, `ACCOUNTING_INTEGRITY`, `RESTART_HYDRATION`, `ADMIN_CANCELLATION`, `REJECTION_FAIL_CLOSED`, `MANUAL_REDUCE_CLOSE`.
   - Captures actionable/business evidence only; raw market ticks do NOT constitute a full market-data journal.
5. **Append-Only Contract:**
   - `audit_events` is append-only by application policy. No normal runtime `UPDATE audit_events` or `DELETE audit_events`.
   - Corrections, if ever required, are new appended evidence.
   - Item 11 V1 has no cryptographic hash chain (zero `previous_event_hash` / chaining; no claim of cryptographic tamper-proof / tamper-evident security).
6. **State Transaction Atomicity & Monotonic Generation:**
   - Required audit evidence for state transitions (T1, T2, T3, T4, T5, T6, `save_safety_state`, session rollover) commits in the SAME SQLite transaction as corresponding state mutations.
   - If audit insertion or state write fails: transaction rolls back, `PersistenceHealth` becomes `FAILED`, and runtime becomes terminally poisoned. No state-commit-then-audit-commit split.
   - State-coupled events receive `state_generation` equal to the exact generation committed by that transaction.
   - Standalone observational audit events receive `state_generation = NULL` and MUST NOT increment business `state_generation`.
   - `transaction_event_ordinal` provides deterministic ordering of multiple events within one transaction.
7. **Hybrid Event Identity & Idempotency:**
   - State-coupled audit events use deterministic canonical event IDs derived from event family/type, aggregate identity, `state_generation`, `transaction_event_ordinal`, canonical domain identity, and canonical payload fingerprint.
   - Standalone observational events without stable canonical identity use UUIDv4 generated once at event creation.
   - `audit_sequence` and `recorded_at_utc` do NOT participate in deterministic state-event identity.
   - Same `event_id` + identical canonical semantic projection: idempotent no-op / existing event.
   - Same `event_id` + conflicting canonical semantic evidence: `AuditIntegrityError`, FAIL CLOSED. Zero `INSERT OR IGNORE` authority bypass, zero overwrite.
8. **Timestamp Model & Wall-Clock Centralization:**
   - `market_timestamp`: authoritative market/exchange/MarketTime evidence.
   - `recorded_at_utc`: diagnostic audit observation timestamp only. Cannot create bars, advance RiskDay, authorize entries, authorize fills, trigger protectives, determine quote freshness, size risk, or roll market session.
   - Approved UTC wall-clock call (`recorded_at_utc_now()`) is isolated in audit infrastructure.
9. **Signal & Option Selection Audit:**
   - Actionable `BUY` / `SELL` signals produce durable `SIGNAL_EMITTED` audit evidence (`state_generation = NULL`).
   - `HOLD` signals are NOT durably journaled (0 audit events, 0 T1 state transactions, 0 orders, 0 reservations).
   - Duplicate actionable intent generates fail-closed rejection evidence (`SIGNAL_REJECTED_DUPLICATE`).
   - Accepted option selection emits `OPTION_SELECTED`; rejected option selection emits `OPTION_SELECTION_REJECTED`. References canonical metadata without full catalog dump. Known P2 finding remains unchanged.
10. **Risk, Order Lifecycle, Accounting & Protective Audit:**
    - RiskGate evaluations emit `RISK_EVALUATED_APPROVED` or `RISK_EVALUATED_REJECTED` (no risk recomputation from journal).
    - Durable V1 order lifecycle evidence: `QUEUED`, `FILLED`, `CANCELLED`, `EXPIRED`, `REJECTED`. Exact T5 terminal audit types: `ORDER_CANCELLED`, `ORDER_EXPIRED`, `ORDER_REJECTED`. No `OPEN` / `PARTIAL` states.
    - `FILL_EXECUTED` references canonical accepted `FILLED` broker evidence. Accounting audit uses compact delta evidence (no duplicate full `AccountSnapshot` storage).
    - Protective transitions (`PLAN_RETAINED`, `PROTECTIVE_MATERIALIZED`, `PROTECTIVE_TRIGGERED`, `PROTECTIVE_FILLED`, OCO cancellation, termination, `TRAILING_RATCHETED`) are durably journaled. Every committed T6 trailing ratchet has same-transaction audit evidence. `LiveProtectiveEvaluator` provides single-pass evaluation via `TrailingRatchetEvidence` without double evaluation.
11. **Feed Connectivity, Startup & Safety Events:**
    - Initial connection emits `FEED_CONNECTED`; disconnect emits `FEED_DISCONNECTED`; subsequent reconnect after established disconnect emits `FEED_RECONNECTED`. `FEED_RECONNECTED` is audit evidence only and does NOT bypass Item-10 safety gates.
    - `RUNTIME_STARTED` and `STATE_HYDRATED` are appended only after successful V3 DB open, identity validation, and state hydration.
    - `STARTUP_KILL_CLEANUP_COMPLETED` is emitted only after actual active-kill startup queued-order cleanup completes.
    - `KILL_SWITCH_ACTIVATED` and `RESUME_SUCCEEDED` are transaction-coupled. `KILL_SWITCH_IDEMPOTENT_REPEAT` and `RESUME_REJECTED` are standalone observational (`state_generation = NULL`).
12. **Persistence Failure Paradox & Raw Market-Data Boundary:**
    - If SQLite persistence itself fails, SentinelX cannot persist a durable `PERSISTENCE_HEALTH_FAILED` event into that failed transaction. `PersistenceHealth` becomes `FAILED`, runtime fails closed, local `SafetyAlert` logs failure, but no fake durable DB event is claimed.
    - Raw idle quotes/ticks that cause no fills, triggers, ratchets, or transitions produce zero business audit records.
13. **Local Read-Only Query API & Serialization:**
    - `query_audit_events(...)` and `get_audit_event_by_id(...)` support local filtering (aggregate, intent, broker order, trade, protective ID, market timestamp). No dashboard, no analytics, no reconciliation logic.
    - Serialization uses exact Decimal strings, ISO datetimes, canonical JSON. No pickle, no non-finite numeric values, no SQL REAL. Secret tokens and credentials are never persisted.
    - Durability wording: "Durability is provided according to SQLite, operating-system, filesystem, and storage-device guarantees under WAL + synchronous=FULL."
    - Complete journal is retained for the paper session and through the D10 6-month promotion evidence window.
14. **Item-12 Reconciliation Boundary:**
    - Item 11 supplies durable historical evidence; Item 12 performs independent reconciliation. The journal does NOT itself reconcile.

### Component Design & Responsibilities

- **`engine/audit.py` (NEW):**
  - Defines `AuditEvent`, `AuditEventFamily`, `AuditEventType`, `AuditIntegrityError`.
  - Canonical JSON serialization (`canonical_json_dumps`), payload fingerprinting, and deterministic event ID derivation (`derive_audit_event_id`).
  - Isolated UTC observation timestamp authority (`recorded_at_utc_now`).
- **`engine/persistence/schema.py`:**
  - Advances `SCHEMA_VERSION = 3`.
  - DDL for `audit_events` table and associated performance indexes.
- **`engine/persistence/sqlite_store.py`:**
  - `_insert_audit_events_in_transaction`: Atomically binds state-coupled audit events to `state_generation`.
  - `append_audit_events`: Durable standalone observational event logging.
  - `query_audit_events` & `get_audit_event_by_id`: Read-only audit filtering.
  - `load_state`: Appends `RUNTIME_STARTED` and `STATE_HYDRATED` upon verified hydration.
- **`engine/paper_coordinator.py`:**
  - Wires audit emission across actionable signal intake (`SIGNAL_EMITTED`), option selection (`OPTION_SELECTED`, `OPTION_SELECTION_REJECTED`), RiskGate outcomes (`RISK_EVALUATED_APPROVED`, `RISK_EVALUATED_REJECTED`), duplicate intents (`SIGNAL_REJECTED_DUPLICATE`), feed transitions (`FEED_CONNECTED`, `FEED_DISCONNECTED`, `FEED_RECONNECTED`), and startup kill cleanup (`STARTUP_KILL_CLEANUP_COMPLETED`).
  - Assembles T1–T5 atomic audit bundles during entry evaluation, fill processing, protective execution, and order cancellations.
- **`engine/protective_live.py`:**
  - Introduces `TrailingRatchetEvidence` for single-pass ratchet evaluation and T6 audit bundle emission.

### Verification Evidence

- Mandatory event repair tests: **14 passed**
- Full Item-11 audit suite (`tests/test_paper_audit.py`): **32 passed**
- Safety / Persistence interaction: **169 passed**
- Affected regression: **560 passed**
- Phase-5 regression: **968 passed**
- Static Item-11 audit: **PASSED**
- py_compile: **PASSED**
- Full repository test suite: **1757 passed, 1 skipped, 0 failures**
- Controlled hash guard: **PASSED before and after**

Authoritative final marker:

`OD7_ITEM11_D16_OWNER_LOCAL_VERIFIED_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 11 — VERIFIED_COMPLETE**
- Items formally complete through: **11 of 17 (64.7%)**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved project findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 12 — Independent Reconciliation — pre-implementation owner decision and contract review.**

---

## 115. Phase 5 OD-7 Item 12 — Independent Reconciliation — VERIFIED_COMPLETE

### Production Architecture & Ownership Contracts

1. **Reconciliation Purpose & Authority Boundaries:**
   - Item 12 implements independent, cross-domain structural reconciliation for Phase-5 paper trading.
   - It reads canonical state authorities (`PortfolioAccount`, `SimulatedPaperBroker`, `RiskGate`, `TradeLedger`, `LiveProtectiveEvaluator`, `SafetyManager`, `SQLitePaperStateStore`), compares independently maintained and cross-domain evidence, detects and classifies discrepancies, persists immutable reconciliation reports and findings, and gates new strategy exposure when reconciliation is unhealthy.
   - The reconciliation engine is **observational and gating only**; it does NOT repair canonical state, replace accounting authority, replace broker lifecycle authority, replace RiskGate, replace TradeLedger, replace protective exit ownership, or modify Item-11 historical audit records.

2. **Durable Item-12 Schema V4 Authority:**
   - Schema Version is advanced to `SCHEMA_VERSION = 4`.
   - Two dedicated durable tables are established: `reconciliation_reports` and `reconciliation_findings`.
   - Clean new databases bootstrap as Schema V4. Existing Schema V1, V2, and V3 databases fail closed on initialization with `DatabaseIdentityMismatchError`. Zero automatic migration, zero silent upgrade, and zero destructive recreation.

3. **Observational Persistence & Zero Business Generation Bump:**
   - Reconciliation snapshot acquisition (`get_reconciliation_snapshot()`) and report persistence (`save_reconciliation_report()`) are strictly observational.
   - Persisting a reconciliation report and its findings MUST NOT increment business `state_generation`.
   - One `ReconciliationReport` and all of its associated `ReconciliationFinding` records commit in a single atomic SQLite transaction.
   - If SQLite report persistence fails: the transaction rolls back, `PersistenceHealth` transitions to `FAILED`, the coordinator latches to fail-closed, and no fake successful report is recorded.

4. **Identity Model & Determinism (R1):**
   - `report_id`: A UUIDv4 string generated exactly once per reconciliation run (never derived from SHA-256 state hashes). Store retries/persistence operations never manufacture a new `report_id`.
   - `finding_key`: A deterministic, stable SHA-256 fingerprint derived from canonical JSON discrepancy evidence: `(finding_type, aggregate_type, aggregate_identity, expected_json, observed_json)`. Identical discrepancies in separate reconciliation runs produce the exact same `finding_key`.
   - `finding_id`: A deterministic run-bound identifier computed as `SHA256(report_id || "|" || finding_key)`. Finding IDs are uniquely bound to their parent run report.

5. **Live vs Restart Independence Boundary:**
   - *Same Live Process:* In-memory broker/account evidence and SQLite persisted rows are independently maintained sinks; divergence between them is meaningful reconciliation evidence.
   - *Post-Restart Hydration:* In-memory broker/account objects restored from those exact SQLite rows are same-source mirrors. Their equality must NOT be described as independent proof. Restart reconciliation relies additionally on cross-table, cross-domain, and accounting arithmetic invariants.

6. **Structural V1 Boundary (Zero Live-Quote Dependency):**
   - Item-12 V1 is structural and durable reconciliation.
   - It operates entirely on discrete transaction evidence, order records, and account snapshots; it does NOT require fresh BID, fresh ASK, fresh LTP, current live market quotes, current MTM marks, or a connected data feed to evaluate and produce `MATCHED`.
   - A disconnected feed coexists with structurally `MATCHED` reconciliation. Item-10 `DISCONNECTED` safety state independently blocks new signal intake. Reconciliation never bypasses disconnect safety.

7. **Broker Order & Terminal Lifecycle Reconciliation:**
   - Compares in-memory and persisted broker orders across `broker_order_identity`, `order_id`, instrument identity, order action, quantity, order type, lifecycle state, terminal state, and execution fills.
   - Detects runtime/persisted orphan orders, lifecycle state conflicts, duplicate broker identities, and quantity/instrument discrepancies.
   - Broker inspection uses the public read-only `get_order_snapshots()` API. Zero reconciliation-engine access to private `_pending` / `_terminal` internals.

8. **Processed Fill & Economic Leg Reconciliation:**
   - Every `FILLED` order requires canonical processed-fill evidence.
   - Processed fills must correspond strictly to `FILLED` broker lifecycle states. No processed fill may correspond to `QUEUED`, `CANCELLED`, `EXPIRED`, or `REJECTED`.
   - Validates fill price, quantity, execution timestamp, and instrument identity.

9. **Position Quantity & Multi-Leg Scale-In / Reduction Reconciliation:**
   - Position reconciliation supports multi-leg scale-in (multiple BUY fills) and partial reduction (multiple SELL fills).
   - Derived net position quantity per `PositionKey`: `SUM(BUY filled quantity) - SUM(SELL filled quantity)`.
   - Positive derived quantity must match active position snapshot quantity. Zero derived quantity requires active position to be absent. Negative derived quantity triggers a `CRITICAL` mismatch. Zero claim of simplistic one-entry/one-exit-only position semantics.

10. **Cash & Realized P&L Invariants (Zero Fee Double-Deduction):**
    - Canonical gross-cash invariant:
      $$\text{cash} = \text{starting\_capital} - \sum(\text{BUY consideration}) + \sum(\text{SELL proceeds})$$
    - Consideration and proceeds use exact `quantity * fill_price * contract_multiplier`.
    - Transaction costs are NOT deducted from `AccountSnapshot.cash` (cost recognition remains separate in `recognized_costs`). Gross cash reconciliation never subtracts transaction costs again.
    - Multi-leg `TradeRecord` gross realized P&L matches the sum of exit-leg `realized_pnl_delta` across closed trades.

11. **Premium & Risk Commitments Reconciliation (R2):**
    - Active premium commitments are reconciled against eligible `QUEUED` opening BUY orders, verifying reservation key, instrument identity, approved quantity, worst permitted fill price, contract multiplier, and required cash (`approved_quantity * worst_permitted_price * multiplier`). Terminal orders have zero active commitment.
    - Canonical `PendingRiskCommitment` authority remains `RiskGate` in `engine/risk_manager.py`. `engine/reconciliation.py` imports this canonical model directly and does NOT define a duplicate domain type. Active risk commitments must agree with eligible in-flight opening orders.

12. **Historical Trade & Cost Assessment Reconciliation:**
    - Closed `TradeRecord` instances require valid opening and closing execution evidence.
    - Trade and cost reconciliation uses stored historical evidence. `CostAssessment` verifies assessment identity, `trade_evidence_fingerprint`, stored schedule references, component aggregation, total cost, and net realized P&L relationship.
    - Does NOT rerun the current `CostCalculator` policy against historical closed trades.

13. **Protective Exit & Pending Close Reconciliation:**
    - Active protective exits must reference held position keys with protective quantity $\le$ held position quantity.
    - Pending protective close records must correspond to an exact eligible `QUEUED` closing broker order.
    - An orphan pending close triggers a `CRITICAL` finding for that specific position key. Zero reconciliation-side state mutation or auto-repair.

14. **Item-11 D16 Audit Taxonomy Coexistence:**
    - The Item-11 E1–E20 audit event taxonomy remains untouched and closed.
    - Item 12 adds NO new `AuditEventFamily` (e.g. `RECONCILIATION`) and NO new `AuditEventType` values (e.g. `RECONCILIATION_STARTED`, `RECONCILIATION_PASSED`, `RECONCILIATION_FAILED`).
    - Reconciliation findings and reports reside in dedicated Item-12 tables. Rejections caused by reconciliation failure use existing fail-closed audit rejection structures (`SIGNAL_REJECTED_RISK` / `OPTION_SELECTION_REJECTED`). The audit journal remains read-only.

15. **Reconciliation Health State Machine & Latching:**
    - Coordinator owns four orthogonal health states: `UNKNOWN`, `DIRTY`, `MATCHED`, `FAILED`.
    - `UNKNOWN`: Startup state before initial reconciliation.
    - `DIRTY`: Set on any committed state transition (T1–T6) before post-transition reconciliation completes.
    - `MATCHED`: Complete reconciliation succeeded with zero `CRITICAL` findings and durable report persistence succeeded.
    - `FAILED`: Latched when any `CRITICAL` discrepancy exists.
    - Automatic reconciliation runs CANNOT clear `FAILED`.
    - Explicit operator-requested reconciliation (`operator_requested=True`) clears `FAILED` to `MATCHED` ONLY IF a full clean evaluation succeeds and report persistence completes.

16. **New-Entry Gate & Protective Autonomy per PositionKey:**
    - *New-Entry Gate:* New strategy entry requires Item-10 safety eligibility (`OPERATIONAL`), `ReconciliationHealth.MATCHED`, and normal `RiskGate` approval. `UNKNOWN`, `DIRTY`, or `FAILED` blocks new signal intake fail-closed with structured rejection (`reconciliation_unknown`, `reconciliation_dirty`, `reconciliation_failed`).
    - *Protective Autonomy:* A global reconciliation `FAILED` state does NOT blanket-disable protective exits for all held positions. Unrelated `PositionKey` instances retain autonomous protective execution. If a `CRITICAL` finding specifically matches the `PositionKey` / instrument identity / held quantity / pending close of a position, protective exit for that specific key fails closed. Other valid positions remain autonomous. `PersistenceHealth.FAILED` remains governed by Item-10 global fail-close.

17. **Execution Cadence & Coherent Transaction Ordering:**
    - Automatic reconciliation executes on startup, after committed T1–T6 transitions, on session rollover, and upon startup active-kill cleanup completion.
    - Explicit operator reconciliation is supported via `run_reconciliation(operator_requested=True)`. Zero periodic background wall-clock timers in V1.
    - Execution ordering: Canonical state transaction `COMMIT` $\to$ health `DIRTY` $\to$ coherent post-commit snapshot (single SQLite read transaction with checked `state_generation`) $\to$ reconciliation evaluation $\to$ atomic report persistence $\to$ `MATCHED` only after successful persistence.

18. **Startup Sequencing, Disconnect, Kill Switch & No Auto-Repair:**
    - *Startup:* DB open $\to$ Schema V4 check $\to$ canonical hydration $\to$ safety/kill hydration $\to$ startup active-kill cleanup $\to$ final startup reconciliation $\to$ report persistence $\to$ `MATCHED`/`FAILED` $\to$ signal admission.
    - *Disconnect:* Structural reconciliation may execute and `MATCH`; disconnect safety independently blocks entries.
    - *Kill Switch:* Active kill switch permits read-only reconciliation; clean reconciliation never clears an active kill switch.
    - *No Auto-Repair:* Reconciliation detects, classifies, surfaces, and gates. It NEVER mutates or overrides canonical state to force a match.

### Component Design & Responsibilities

- **`engine/reconciliation.py` (NEW):**
  - Defines `ReconciliationHealth`, `ReconciliationSeverity`, `ReconciliationStatus`, `ReconciliationFinding`, `ReconciliationReport`, `ReconciliationRuntimeSnapshot`, `ReconciliationPersistedSnapshot`.
  - Implements `PaperReconciliationEngine` pure invariant evaluator.
  - Implements `derive_reconciliation_finding_key` and `derive_reconciliation_finding_id`.
  - Reuses canonical `PendingRiskCommitment` imported directly from `engine.risk_manager`.
- **`engine/persistence/schema.py`:**
  - Advances `SCHEMA_VERSION = 4`.
  - DDL for `reconciliation_reports` and `reconciliation_findings` tables and indexes.
- **`engine/persistence/sqlite_store.py`:**
  - `save_reconciliation_report()`: Atomic persistence of report and findings without bumping `state_generation`.
  - `query_reconciliation_reports()`: Read-only query API for historical reconciliation reports.
  - `get_reconciliation_snapshot()`: Single read transaction capturing all persisted evidence.
  - Enforces Schema V4 validation and fail-closed V1/V2/V3 rejection.
- **`engine/paper_coordinator.py`:**
  - Coordinates reconciliation lifecycle, post-commit triggers (T1–T6), operator execution, and startup reconciliation.
  - Implements `can_execute_protective_exit(position_key)` per-position protective autonomy gating.
  - Enforces new-entry gating on `ReconciliationHealth.MATCHED`.
- **`engine/execution/paper_broker.py`:**
  - Exposes public read-only `get_order_snapshots()` API.
- **`tests/test_paper_reconciliation.py` (NEW):**
  - 53 dedicated tests covering all 50 required contract items plus R1 and R2 repairs.

### Verification Evidence

- Report / Finding identity (R1): **5 passed**
- Schema V4 / persistence: **7 passed**
- Reconciliation health state machine: **8 passed**
- Protective isolation per position: **5 passed**
- Structural reconciliation boundary: **5 passed**
- Item-12 focused suite: **53 passed**
- Item-10 / Item-11 integrity: **55 passed**
- Item-11 / Item-12 interaction: **194 passed**
- Affected regression suite: **558 passed**
- Phase-5 live regression: **1021 passed**
- Static owner audit: **PASSED**
- py_compile: **PASSED**
- Full repository test suite: **1810 passed, 1 skipped, 0 failures**
- Controlled hash guard: **PASSED before and after**

Authoritative final marker:

`OD7_ITEM12_RECONCILIATION_OWNER_LOCAL_VERIFIED_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 12 — VERIFIED_COMPLETE**
- Items formally complete through: **12 of 17 (70.6%)**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved project findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 13 — Multi-Strategy / Shared Capital — pre-implementation owner decision and contract review.**

---

## 116. Phase 5 OD-7 Item 13 — Multi-Strategy / Shared Capital — VERIFIED_COMPLETE

### Production Architecture & Ownership Contracts

1. **Item-13 Purpose & Implementation Character:**
   - Item 13 is a pure contract verification slice. Production changes in `engine/`: **NONE**.
   - Zero database migrations, zero schema modifications, zero config alterations.
   - Comprehensive test suite in `tests/test_multi_strategy_shared_capital.py` (35 dedicated tests) proving that existing production architecture natively satisfies multi-strategy shared-capital execution without modifications.

2. **Canonical Shared Capital Authority:**
   - `VirtualPaperAccount` remains the single mutable account authority.
   - There is exactly ONE `starting_capital`, ONE `cash`, ONE `reserved_cash`, ONE `available_cash`, and ONE `realized_pnl` across all strategies sharing the account.
   - No per-strategy subaccounts. No fake per-strategy cash pools. No secondary capital allocator.

3. **Canonical Strategy Identity & Position Ownership:**
   - `(strategy_id, strategy_version)` is the canonical strategy owner identity.
   - Position ownership remains strictly: `PositionKey(strategy_id, strategy_version, InstrumentIdentity)`.
   - Strategy A state must never mutate Strategy B-owned `PositionKey` state.

4. **Shared Cash Invariants & Cost Independence:**
   - Account-wide gross cash invariant:
     $$\text{cash} = \text{starting\_capital} - \sum(\text{all strategy BUY considerations}) + \sum(\text{all strategy SELL proceeds})$$
   - Reserved cash invariant:
     $$\text{reserved\_cash} = \sum(\text{required\_cash of all active PremiumCommitmentRecords})$$
   - Available deployable cash invariant:
     $$\text{available\_cash} = \text{cash} - \text{reserved\_cash}$$
   - Transaction costs remain separate from gross account cash according to the existing accounting contract (`recognized_costs`).

5. **Capital Allocation Rule (First Valid Reservation Wins):**
   - Phase-5 V1 policy: **FIRST VALID RESERVATION WINS** in existing canonical serialized evaluation order.
   - First successful reservation immediately reduces shared `available_cash`.
   - Later candidates evaluated in the same decision timestamp see remaining deployable cash.
   - No proportional allocation, no random allocation, no thread-race allocation, no round-robin fairness system.
   - Existing `AllocationPriorityConfig` behavior is preserved when configured; no new priority subsystem was added.

6. **Concurrency Model:**
   - Multi-strategy account mutation remains strictly synchronous and serialized.
   - No parallel mutable account execution. No threads introduced for account/risk/broker mutation.
   - Deterministic strategy ordering remains authoritative.

7. **Premium Commitment Isolation:**
   - Premium commitments share one account-wide reservation pool, but each commitment remains isolated by canonical `entry_intent_identity`.
   - Strategy A reservation cannot be released by Strategy B lifecycle. Terminal processing releases only the exact matching commitment.

8. **Risk Commitments Authority:**
   - `PendingRiskCommitment` remains canonical `RiskGate` authority.
   - Commitments remain exact: entry identity, `PositionKey`, approved quantity, nominal stop risk. No second risk authority was added.

9. **Account-Global Risk Policy:**
   - Account-global risk limits apply across all strategies sharing the account:
     - `max_daily_loss_pct`
     - `max_daily_trades`
     - `max_open_positions`
     - `max_portfolio_risk_pct`
     - Q60 same-direction same-instrument correlation policy
   - No independent daily-trade allowance or portfolio-risk pool per strategy.

10. **Same-Instrument Distinction vs Live Q60 Risk Policy:**
    - Lower-level `PortfolioAccount` accounting representation supports distinct `PositionKey(A, option X)` and `PositionKey(B, option X)` because `PositionKey` includes strategy identity.
    - However, live `RiskGate` policy Q60 is account-global. If Strategy A already holds/reserves exact `InstrumentIdentity` X, another same-direction LONG on exact X from Strategy B is rejected under the existing correlation policy (`correlation_conflict`).
    - The live system does NOT allow duplicate exact same-instrument LONG exposure merely because the accounting representation can model it.

11. **Opposing Strategy Signals & Options Buy-Only Semantics:**
    - Signals from different strategies are never semantically netted.
    - Options-buy-only semantics remain: BUY $\to$ CE BUY; SELL semantic $\to$ PE BUY.
    - CE and PE have different `InstrumentIdentity` values and can coexist if all account-wide cash/risk gates permit.

12. **Cross-Strategy Close Prohibition:**
    - Strategy A cannot close Strategy B's position.
    - Exit resolution requires exact matching `(strategy_id, strategy_version, InstrumentIdentity)`.
    - No owned `PositionKey` fails closed via existing invalid-position behavior (`no_owned_position_for_exit`).

13. **Broker Identity Discipline:**
    - `broker_order_identity` includes canonical entry intent identity.
    - Because entry intent identity includes strategy identity, otherwise equivalent orders belonging to different strategies are deterministically distinguished by the identity contract (not claiming cryptographic collision impossibility).

14. **Protective & OCO Lifecycle Isolation:**
    - Every protective exit remains exact `PositionKey`-scoped.
    - Strategy A stop/target/trailing event cannot close Strategy B position, alter Strategy B quantity, cancel Strategy B OCO siblings, or release Strategy B commitment.
    - OCO ownership remains isolated to the exact position/entry run.

15. **TradeLedger Lifecycle Isolation:**
    - `TradeLedger` lifecycle is `PositionKey`-specific.
    - Multiple strategies have independent pending lifecycles, `TradeRecord` instances, `trade_id` values, and realized P&L evidence.
    - Zero cross-strategy trade aggregation.

16. **Kill Switch Multi-Strategy Proof:**
    - Verified using the real public `LivePaperCoordinator.activate_kill_switch(...)` API.
    - For Strategy A and Strategy B queued opening orders, both were cancelled through the production kill path (`OrderLifecycleState.CANCELLED`).
    - Both premium reservations were released through canonical terminal processing.
    - Zero direct `broker.cancel()` calls in the repaired verification test.
    - Held positions remain preserved without fake liquidation.

17. **Feed Disconnect Multi-Strategy Proof:**
    - Verified using the real public `LivePaperCoordinator.on_feed_state_change(FeedConnectionState.DISCONNECTED)` API.
    - For Strategy A and Strategy B pending opening orders, both were cancelled through production disconnect handling.
    - Premium reservations were released by exact identity.
    - Held positions remain held. Portfolio valuation transitions to `ValuationState.STALE`.
    - Zero fake liquidation. Zero direct `broker.cancel()` calls in the repaired verification test.

18. **Restart & Hydration Multi-Strategy Ownership:**
    - Schema V4 hydration preserves exact multi-strategy ownership for positions, premium commitments, broker lifecycle evidence, protective state, and trade records.
    - No merge solely by `InstrumentIdentity`.

19. **Reconciliation Interaction:**
    - Item-12 independent reconciliation already supports multi-strategy shared capital across multiple `PositionKey` entries, multiple commitments, multiple broker orders, shared gross cash, trade records, and protective exits.
    - Item 13 did NOT redesign reconciliation.

20. **Schema & Taxonomy Invariants:**
    - `SCHEMA_VERSION` remains exactly 4. Zero Schema V5, zero migrations, zero new Item-13 tables.
    - Item-11 audit taxonomy remains unchanged (zero new event families/types; audit envelope already carries strategy identity).

21. **Fairness & Starvation:**
    - Phase-5 V1 correctness requirement is deterministic allocation and non-overbooking.
    - Starvation prevention / fair scheduling is a future enhancement, not an Item-13 correctness requirement.

### Verification Evidence

- Item-13 focused suite: **35 passed**
- Critical owner contracts: **15 passed**
- Affected multi-strategy regression: **473 passed**
- Complete Phase-5 regression: **1056 passed**
- Full repository test suite: **1845 passed, 1 skipped, 0 failures**
- Final safety repair: **2 passed**
- Final repaired safety owner check: **2 passed**
- Final full Item-13 owner check: **35 passed**

Authoritative final marker:

`OD7_ITEM13_TWO_SAFETY_TESTS_OWNER_LOCAL_VERIFIED_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 13 — VERIFIED_COMPLETE**
- Items formally complete through: **13 of 17 (76.5%)**
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved project findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

---

## 117. Phase 5 OD-7 Item 14 — Full Pipeline Replay (FULL PIPELINE REPLAY) — VERIFIED_COMPLETE

### Production Architecture & Ownership Contracts

1. **Item-14 Purpose & Implementation Character:**
   - Item 14 implements deterministic FULL PIPELINE REPLAY runner integration, proving that recorded completed underlying bars, option quotes, feed-state transitions, and session boundaries can drive the actual Phase-5 live paper-trading pipeline end-to-end without a parallel execution engine.
   - Core production delivery: `ReplayLiveMarketFeed(LiveMarketDataFeed)` in `engine/feeds/replay_feed.py`. `HistoricalReplayFeed` is preserved for historical backtest/replay use.
   - Replay operates with zero network activity using static `InMemoryInstrumentCatalog` for Item-14 V1.
   - Business time authority derives strictly from recorded `MarketTime` evidence; system wall-clock never dictates market timestamps.

2. **Canonical Full-Pipeline Route:**
   - The end-to-end event sequence proceeds deterministically through the canonical live pipeline:
     $$\text{Recorded Completed Underlying Bars / Option Quotes / Feed State / Session Boundary}$$
     $$\Downarrow$$
     $$\text{MarketDataCoordinator} \longrightarrow \text{LiveStrategyCoordinator} \longrightarrow \text{Strategy Signal}$$
     $$\Downarrow$$
     $$\text{OptionSelector} \longrightarrow \text{Subscription} \longrightarrow \text{Pending Option Attempt}$$
     $$\Downarrow$$
     $$\text{RiskGate} \longrightarrow \text{Premium Reservation} \longrightarrow \text{SimulatedPaperBroker}$$
     $$\Downarrow$$
     $$\text{Subsequent Quote Fill} \longrightarrow \text{VirtualPaperAccount} \longrightarrow \text{Protective SL / Target / Trailing Book}$$
     $$\Downarrow$$
     $$\text{TradeLedger} \longrightarrow \text{SQLite Schema V4} \longrightarrow \text{Item-11 Audit} \longrightarrow \text{Item-12 Reconciliation}$$

3. **Causal Execution & Quote/Fill Contract:**
   - Causal sequence is strictly preserved across 4 distinct execution phases:
     - `Q_ENTRY_WAKE`: Pending option attempt wakes $\to$ `RiskGate` evaluation $\to$ premium reservation $\to$ opening order `QUEUED` (NO same-quote fill).
     - `Q_ENTRY_FILL`: Subsequent option quote arrived $\to$ broker evaluates existing queued opening order $\to$ `FILLED`.
     - `Q_TARGET_TRIGGER`: Protective target condition fires on live price $\to$ protective close order `QUEUED` (NO same-quote fill).
     - `Q_EXIT_FILL`: Subsequent quote arrived $\to$ close order `FILLED`.
   - `SimulatedPaperBroker.submit()` does NOT execute using `submission_quote`; `submission_quote` serves as validation/reference evidence only.
   - Zero retroactive quote reuse.

4. **Canonical Integration Economic Fixture:**
   - Option quantity: 50
   - Contract multiplier: 1
   - Entry fill price: 150.50 INR
   - Required premium reserved: 7,525.00 INR
   - Protective stop: 130.00 INR
   - Protective target: 180.00 INR
   - Exit fill price: 180.50 INR
   - Gross realized P&L: +1,500.00 INR ($50 \times (180.50 - 150.50)$)
   - Primary replay lifecycle: 8 deterministic events including explicit session boundary. Multiplier semantics preserved.

5. **Session Semantics & Multi-Session Rollover:**
   - Stream exhaustion $\neq$ session close.
   - Explicit session boundary invokes canonical production session lifecycle (`on_session_boundary`).
   - DAY orders expire only on explicit session boundary handling.
   - Valid premium reservations release according to canonical lifecycle.
   - Open positions are NOT forcibly liquidated merely because replay stream ends.
   - Overnight positions carry forward cleanly to the next session across multi-session rollover.

6. **Multi-Strategy Shared Capital Replay Preservation:**
   - Replay preserves all Item-13 shared-capital invariants: single `VirtualPaperAccount`, shared cash authority, first valid reservation wins, account-global risk limits, and strict `PositionKey` strategy isolation without per-strategy fake capital pools.

7. **Latent Defects Discovered & Repaired:**
   - `ITEM14_DISCOVERED_LATENT_DEFECT_REPAIR_1`: Missing `PendingRiskCommitment` import in `engine/paper_coordinator.py` reconciliation path. Repaired with canonical import.
   - `ITEM14_DISCOVERED_LATENT_DEFECT_REPAIR_2`: `PositionSnapshot` reconciliation hydration in `engine/persistence/sqlite_store.py` used invalid `position_key=pkey` constructor keyword. Repaired with canonical `key=pkey`.
   - `ITEM14_DISCOVERED_LATENT_DEFECT_REPAIR_3`: `ConcreteCloseInstruction` persistence deserialization in `engine/persistence/sqlite_store.py` used obsolete flattened constructor arguments. Repaired with canonical nested `OrderRequest` reconstruction.
   - `ITEM14_DISCOVERED_LATENT_DEFECT_REPAIR_4`: Opening T2 persistence in `engine/paper_coordinator.py` released premium commitment using broker `order_id` instead of canonical `entry_intent_identity` reservation key. Repaired with canonical `res_key`.
   - `ITEM14_DISCOVERED_LATENT_DEFECT_REPAIR_5`: Queued BUY reconciliation projection replaced Layer-3 `broker_order_identity` with Layer-2 `entry_intent_identity`, creating a false MATCHED condition when broker identities differed. Repaired by preserving actual Layer-3 broker identity in `BrokerOrderRecord` and independently deriving Layer-2 `entry_intent_identity` for commitment linking. Dedicated regression test proves `BROKER_ORDER_IDENTITY_MISMATCH` is emitted on diverging broker identities.
   - `ITEM14_DISCOVERED_LATENT_DEFECT_REPAIR_6`: `ConcreteCloseInstruction` persistence deserialization contained fallbacks (`action=intent_dict.get("action") or "EXIT"`, `confidence=float(intent_dict.get("confidence") or 0.0)`). Repaired with strict fail-closed validation for `closing_action`, `source_intent` mapping, `strategy_id`, `strategy_version`, `symbol`, `timeframe`, `originating_timestamp`, `action`, and `confidence`. Explicit `confidence: 0.0` is valid; missing field fails closed. Zero implicit fallback to `SELL`, `EXIT`, or `0.0`.

8. **Three-Layer Identity Architecture:**
   - Layer 2 (`entry_intent_identity`, `sentinelx-entry-intent/v1`): Strategy intent provenance and premium/risk commitment linkage.
   - Layer 3 (`broker_order_identity`, `sentinelx-paper-broker-order/v1`): Concrete broker order execution entity and lifecycle integrity.
   - `order_id`: Individual broker submission/lifecycle instance identifier.
   - `BrokerOrderRecord.broker_order_identity` strictly remains Layer-3 across all lifecycles (`QUEUED`, `FILLED`, `CANCELLED`, `EXPIRED`, `REJECTED`, protective exits).

9. **Persistence & Reconciliation Invariants:**
   - Schema V4 remains unchanged (21 SQLite tables). Zero migrations.
   - Item-11 audit envelope (`sentinelx-audit-envelope/v1`) unchanged.
   - Item-12 reconciliation remains strictly observational (no mutation of live state).

### Verification Evidence

- Concrete close fail-closed tests: **13 passed**
- Reconciliation identity semantic tests: **2 passed**
- Item-14 focused full pipeline replay tests: **12 passed**
- Critical Item-12 / Item-13 / Item-14 interaction: **102 passed**
- Full repository test suite: **1872 passed, 1 skipped, 0 failures**
- Final controlled hash guard: **PASS**

Authoritative final marker:

`OD7_ITEM14_FINAL_OWNER_LOCAL_VERIFICATION_COMPLETE`

### Roadmap Status

- **OD-7 ITEM 14 — VERIFIED_COMPLETE**
- Items formally complete through: **14 / 17 (82.4%)** (14 of 17)
- Phase 5 remains **NOT VERIFIED_COMPLETE**.
- Preserved project findings:
  - **P2:** Option Selector strike-rejection diagnostic granularity
  - **P3:** option LIMIT / STOP / STOP_LIMIT premium-domain entry support

The next single required step is:

**Phase 5 — OD-7 Item 15 — Actual Live-Market Paper Verification (ACTUAL LIVE-MARKET PAPER VERIFICATION).**

Item 15 verifies automated options paper trading against actual live market data using virtual/demo money only.
Item 15 is NOT real-money execution.
---

## 118. Phase 5 OD-7 Item 17 — Formal Phase-5 Engineering Closure — VERIFIED_COMPLETE

### 1. Formal Engineering Closure Boundary
- **PHASE 5 — PAPER TRADING ENGINEERING: VERIFIED_COMPLETE**
- All Phase-5 software architecture, production engines, live paper coordinators, Upstox V3 feed adapters, completed-bar builders, strategy execution loops, option selectors, risk gates, premium reservations, simulated paper brokers, virtual portfolio accounting, protective plans, persistence stores, reconciliation engines, and top-level live paper runner capabilities are complete, verified, and internally consistent.
- **ACTUAL EXTERNAL LIVE-MARKET EVIDENCE: OWNER-DEFERRED**
- Real external broker/market connectivity, live API credentials (UPSTOX_ACCESS_TOKEN), and active trading-day instrument masters (data/upstox_instrument_master.json) will be supplied directly by the operator in future live sessions. No actual live market connection was made or claimed during this engineering closure.

### 2. Verified Live Paper Runner Identity
- Production Runner: engine/live_paper_runner.py (SHA256: 507530EF106100E2E8B43B2568D05379451B3B778CEE50EDE49F893640BC46A2)
- Runner Tests: 	ests/test_live_paper_runner.py (SHA256: C3FC0F065E095A6943E2DED724BC8BA03AF89F5249B6859D20FB21EFB2629F89)
- Offline verification modes (--help, --validate-only) verified with 0 network calls and 0 token exposure.

### 3. Final Verification Baseline & Test Evidence
- Focused Phase-5 Regression Suite: **594 passed in 7.88s**
- Full Repository Regression Suite: **1890 passed, 1 skipped, 0 failures in 26.38s**
- P0 Defects: 0
- P1 Defects: 0

### 4. Schema & Data Invariants
- SCHEMA_VERSION = 4 across 21 canonical SQLite tables (WAL mode, synchronous=FULL).
- Zero database migrations introduced.

### 5. Paper-Only Execution Authority & Safety Boundaries
- Execution Authority: Strictly SimulatedPaperBroker (virtual paper execution only).
- Account Authority: Strictly VirtualPaperAccount (simulated virtual capital only).
- Real Broker Endpoints: Zero reachability of real trading or order placement APIs (no KiteConnect, no real Upstox/Zerodha order placement).
- Secret Protection: Access tokens resolved dynamically via callable at runtime, never logged, dumped, or persisted.
- Graceful Shutdown: Transport disconnect and signal termination cleanly preserve open positions and accounting state without triggering session-close forced liquidation.

### 6. Preserved Known Project Findings
- **P2:** Option Selector strike-rejection diagnostic granularity preserved (does not block MARKET option paper execution).
- **P3:** Option LIMIT / STOP / STOP_LIMIT premium-domain entry support preserved (MARKET option entry path fully supported).

### 7. Formally Closed OD-7 Items & Markers
- Items 1–14: FORMALLY CLOSED
- Item 15: ITEM15_ENGINEERING_COMPLETE_EXTERNAL_EVIDENCE_PENDING (Runner & live integration engineering VERIFIED_COMPLETE; external live evidence deferred)
- Item 16: FINAL PHASE-5 ENGINEERING AUDIT — VERIFIED_COMPLETE
- Item 17: FORMAL PHASE-5 ENGINEERING CLOSURE — VERIFIED_COMPLETE

### 8. Roadmap Status & Next Phase
- Phase 5 Paper Trading Engineering is **FORMALLY VERIFIED_COMPLETE** (OD-7 Items 1–17 complete).
- Actual external live-market connection remains **DEFERRED BY OWNER**.
- Next Development Phase: **PHASE 6 — LOGGING / AUDIT** (do not begin implementation until authorized).

Authoritative Final Markers:
OD7_PHASE5_ENGINEERING_FORMALLY_CLOSED
OD7_ITEM17_FORMAL_ENGINEERING_CLOSURE_COMPLETE

---

## 119. Owner-Locked P1-05 — Production Live-Paper Runner Restart Hydration Contract

**Status:** VERIFIED_COMPLETE / FORMALLY CLOSED  
**Scope:** Phase 5 corrective finding **P1-05** only.  
**Implementation status:** COMPLETE AND INDEPENDENTLY VERIFIED.  
**Authoritative full-suite verification baseline:** **1944 passed, 1 skipped, 0 failures**.

### 119.0 Finding under decision

P1-05: the production live-paper runner (`engine/live_paper_runner.py`) constructs fresh runtime
authorities and never invokes the existing durable hydration path (`SQLitePaperStateStore.load_state()`,
`VirtualPaperAccount.restore(...)`, `SimulatedPaperBroker.restore(...)`, the coordinator
`kill_switch_state` / `retained_protective_plans` / `intent_lifecycles` seams).  Because the startup
reconciliation pass runs with `is_restart_hydration=True`, the broker-order ledger comparison is
deliberately suppressed (`engine/reconciliation.py`), so the unhydrated startup is reported MATCHED
instead of failing closed for every durable state except filled positions and cash.

This decision does NOT amend, weaken, or supersede any frozen Phase-5 contract.  It binds the exact
ordering and scope of the corrective work.  The `is_restart_hydration` suppression in
`engine/reconciliation.py` remains the authoritative contract: the precondition (hydration) is what
must be fixed, never the detector.

### 119.1 OD-A — Write-side inclusion (APPROVED)

P1-05 MUST include the minimum production writers required for durable restart hydration:

- `risk_gate_state` MUST be durably persisted by the production path (`SQLitePaperStateStore.save_session_rollover(...)`
  and `SQLitePaperStateStore.save_t2_opening_fill(...)`).
- `accounting_integrity_breached = True` MUST be durably persisted when the production runtime
  actually enters that state (`SQLitePaperStateStore.save_accounting_integrity_breached(...)`).

This authorization is strictly limited to the minimum writers required for restart hydration.  It
MUST NOT be broadened into any unrelated persistence redesign.

### 119.2 OD-B — RiskGate continuity (APPROVED)

`prior_risk_state` continuity belongs to P1-05.  Daily risk state that is already part of the durable
hydration contract (`RiskGateState`: `RiskDay` identity, daily-loss baseline, daily trade count) MUST
survive restart and MUST be supplied back to the runtime authority so the pre-order risk gate
evaluates against restored, not reset, daily evidence.

RiskPolicy, its versions (`risk-policy/v3` / `risk-policy/v4`, §64), its fingerprints, and its
economics MUST NOT be redesigned by P1-05.

### 119.3 OD-C — Active kill switch on restart (APPROVED)

A persisted active kill switch MUST NOT be cleared on restart.

- The runner MAY initialize successfully, but MUST remain in `KILL_SWITCH_ACTIVE` / halted state.
- It MUST NOT accept actionable trading until an explicit operator-authorized resume occurs through
  the existing safety contract (`LivePaperCoordinator.resume_from_kill_switch(...)`, §113 SAF-11 /
  SAF-32 prerequisites unchanged).
- Automatic resume is PROHIBITED.
- The existing restart kill-cleanup behaviour and its `STARTUP_KILL_CLEANUP_COMPLETED` audit evidence
  remain unchanged.

### 119.4 OD-D — Strategy-state boundary (APPROVED)

Strategy runtime / indicator state remains exclusively **P1-07**.

P1-05 MAY restore only state already represented by the existing durable `PaperHydratedState`
contract: account snapshot, positions, broker orders (pending and terminal), processed fills,
premium commitments, pending risk commitments, protective exits and pending closes, retained
protective plans, entry intents, broker watermarks, trade ledger, cost evidence, accounting sequence,
accounting integrity state, safety / kill-switch state and risk state.

Prohibited in P1-05:
- Creating a strategy-state table.
- Changing `SCHEMA_VERSION` for strategy state (Schema V4, 21 canonical tables, zero migrations).
- Absorbing any part of P1-07 into P1-05.

**Explicitly recorded as UNRESOLVED until P1-07:** the temporary cold-strategy-state asymmetry —
after a P1-05 restart, account/position/protective/safety/risk state is restored while strategy
runtime and indicator state restarts cold from `initial_state()`.  This asymmetry is a known,
owner-accepted, temporary condition and is not a P1-05 defect.

### 119.5 OD-E — Critical reconciliation / recovery (APPROVED)

P1-05 remains strictly fail-closed.  If hydrated state still produces a CRITICAL reconciliation
failure, startup MUST abort before feed/network acceptance (before authorization-URL retrieval,
WebSocket connection, and any frame ingress).

Prohibited in P1-05: operator recovery modes, overrides, repair paths, and degraded-start modes.
Those remain **P1-06** territory.

### 119.6 OD-F — Session identity (APPROVED)

P1-05 MUST NOT change `paper_session_id` or session-identity semantics.  It uses the existing
persistence/session contract only as required to hydrate the currently opened durable state.

Session reuse, session-mismatch validation, recovery identity, and configuration-identity validation
remain **P1-06**.

### 119.7 Owner-locked startup ordering

The production live-paper runner startup sequence is locked to exactly:

1. Configuration resolution (`load_paper_configuration`).
2. Persistence open (`SQLitePaperStateStore` schema/metadata bootstrap).
3. Durable-state hydration (`store.load_state()`), which also emits the D16 `RESTART_HYDRATION`
   `RUNTIME_STARTED` / `STATE_HYDRATED` audit evidence in production.
4. Runtime object construction / restoration strictly from the hydrated state (virtual account,
   simulated paper broker, protective book and pending closes, coordinator safety / retained plans /
   intent lifecycles / pending risk commitments).
5. Startup reconciliation (`is_restart_hydration=True`) — MUST be MATCHED.
6. Feed / network acceptance (authorization URL, WebSocket connection, frame ingress).

Token resolution and instrument catalog/mapper readiness remain before hydration where already
required (catalog specifications are an input to account restoration); no feed listener, auth call,
or network connection may occur before step 5 returns MATCHED.

### 119.8 Zero-Fill / Session-Rollover Risk Continuity Resolution

During independent verification, a P1 closure blocker was identified: if market time rolled over to a
new session date with zero entry fills, a subsequent process restart would rebase `RiskGateState` from
stale T2 entry-fill equity rather than the canonical closing net equity of the prior session.

Under owner-approved OD-A and OD-B, this was corrected without schema or contract changes:
1. `LivePaperCoordinator._sync_risk_gate_equity()` maintains synchronization between in-memory
   `risk_gate_state.current_net_equity` and `virtual_account.cost_adjusted_equity` across all terminal
   events (including T4 closes) and market-time advancements.
2. `LivePaperCoordinator._handle_session_rollover(market_time)` advances `RiskGateState` via the authoritative
   `RiskGate.advance_state(...)` engine upon canonical session date rollover and durably persists it
   via `SQLitePaperStateStore.save_session_rollover(...)`.
3. Process restart on a zero-fill day hydrates the rebased `start_of_day_net_equity`, ensuring that pre-order
   risk gate evaluations evaluate against the true session baseline with zero false `daily_loss_limit_exceeded`
   rejections. Multi-day zero-fill continuity through Day 3 is verified in permanent regression test 14.

### 119.9 Boundaries preserved

- Execution authority remains strictly `SimulatedPaperBroker`; account authority remains strictly
  `VirtualPaperAccount`; virtual money only; zero real-broker execution reachability.
- Restored positions MUST NOT be revalued as `LIVE` on restart (VA-7 / §110 unchanged): they restore
  `STALE` / `UNAVAILABLE` until fresh accepted quote evidence arrives.
- Schema V4, 21 canonical tables, zero migrations.
- Reconciliation detector in `engine/reconciliation.py` remains unchanged.
- Strategy runtime state remains deferred to P1-07.
- P1-06 recovery/configuration/session identity remains untouched.
- P1-01 through P1-04 remain VERIFIED_COMPLETE.
- P1-06 through P1-10 remain untouched.
- Phase 6 (Logging / Audit) remains unstarted and unauthorized.

### 119.10 Authoritative marker

`P1_05_VERIFIED_COMPLETE`

---

## 120. Owner-Locked P1-06 — Recovery / Configuration / Session Identity Validation Contract

**Status:** VERIFIED_COMPLETE / FORMALLY CLOSED.  
**Scope:** Phase 5 corrective finding **P1-06** only.  
**Implementation status:** COMPLETE AND INDEPENDENTLY VERIFIED.  
**Authoritative baseline at closure:** **1960 passed, 1 skipped, 0 failures**.

### 120.0 Finding under decision

P1-06: the production live-paper runner (`engine/live_paper_runner.py`) resolves a complete `ResolvedPaperConfiguration` but omitted `risk_policy_identity`, `cost_profile_identity`, `execution_policy_identity`, and `configuration_identity` when instantiating `SQLitePaperStateStore`. Furthermore, `SQLitePaperStateStore._bootstrap_schema` failed to validate `starting_capital`, `monetary_quantum`, `cost_schedule_fingerprint`, `execution_policy_identity`, and `configuration_identity` against persisted `paper_metadata` on restart. As a result, a restart against an existing database could silently accept a mutated configuration (altered starting capital, modified strategy bindings, changed cost schedule, or altered execution policies) without failing closed.

### 120.1 OD-A — Full Identity Dual-Layer Validation (APPROVED & IMPLEMENTED)

`LivePaperTradingRunner` passes the freshly resolved identities into `SQLitePaperStateStore`:

- `resolved.risk_policy_identity`
- `resolved.cost_profile_identity`
- `resolved.execution_policy_identity`
- `resolved.configuration_identity`

`SQLitePaperStateStore` fails closed on existing-database reopen if any authoritative durable identity differs from the freshly resolved runtime identity.

Validated at restart:

- `account_id`
- `currency`
- `starting_capital`
- `monetary_quantum`
- `paper_session_id`
- `risk_policy_identity`
- `cost_schedule_fingerprint`
- `execution_policy_identity`
- `configuration_identity`

Both layers are enforced:

1. Individual component identity validation (for precise diagnostics); and
2. Canonical `configuration_identity` validation (for complete cryptographic defense-in-depth).

The canonical configuration digest does NOT replace explicit financial / account-instance identity checks.

### 120.2 OD-B — Paper Session Identity Lifetime (APPROVED & IMPLEMENTED)

`paper_session_id` is the immutable logical identity of one continuous multi-day paper-trading run bound 1:1 to a SQLite paper-state database.

- Process restarts against that database MUST reuse the same `paper_session_id`.
- A mismatched `paper_session_id` MUST fail closed (`DatabaseIdentityMismatchError`).
- A new logical paper run requires:
  - a new `paper_session_id`; and
  - a new paper-state database.
- Silently retagging an existing database is PROHIBITED.

### 120.3 OD-C — Legacy / Unverifiable Database Policy (APPROVED & IMPLEMENTED)

An existing database that lacks mandatory P1-06 identity evidence is LEGACY / UNVERIFIABLE and MUST fail closed (`DatabaseIdentityMismatchError` or `IncompatibleContractError`).

Examples of unverifiable databases rejected fail-closed:

- missing `configuration_identity`
- absent/unpopulated risk policy identity
- empty/unverifiable cost profile identity
- absent/unverifiable execution policy identity
- other required identity metadata that cannot prove equivalence

PROHIBITED AND PREVENTED:

- Silently backfilling current runtime identities into an unverifiable DB.
- Accepting missing evidence.
- Asserting that historical state used the current configuration without proof.

### 120.4 OD-D — Promotion Eligibility Identity Binding (APPROVED & IMPLEMENTED)

`ResolvedPaperConfiguration.configuration_identity` cryptographically binds:

- `promotion_eligible`
- `promotion_ineligibility_reasons`

These fields are part of P1-06 durable configuration identity. A restart that changes promotion eligibility or ineligibility reasons and thereby changes `configuration_identity` fails closed.

NOTE: Broader promotion tracking lifecycle remains **P1-08**.

### 120.5 OD-E — Schema V4 / Zero-DDL-Migration (APPROVED & IMPLEMENTED)

Uses the existing `paper_metadata` key/value table (`key TEXT PRIMARY KEY, value TEXT NOT NULL`) for additional identity metadata.

- `SCHEMA_VERSION` remains **4**.
- 21 canonical tables remain unchanged.
- No DDL migration is required or exists.

### 120.6 OD-F — Database Instance ID (APPROVED & IMPLEMENTED)

`database_instance_id` remains:

- Internally generated once via UUID when the physical database is created;
- Stored durably in `paper_metadata`;
- Stable and immutable for the physical lifetime of the database;
- Never supplied from YAML, CLI, or runtime configuration.

### 120.7 OD-G — Configuration Identity Coverage (APPROVED & IMPLEMENTED)

`configuration_identity` is the canonical semantic digest produced by `ResolvedPaperConfiguration`. It binds:

- Risk policy identity (`risk_policy_identity`)
- Cost profile identity (`cost_profile_identity`)
- Execution policy identity (`execution_policy_identity`)
- Complete sorted strategy binding set:
  - `strategy_id`
  - `strategy_version`
  - `activation`
  - `instrument`
  - `timeframe`
  - `protective_policy` identity
- `promotion_eligible`
- `promotion_ineligibility_reasons`

Account-instance fields are validated separately:

- `account_id`
- `currency`
- `starting_capital`
- `monetary_quantum`
- `paper_session_id`

File-system paths (`source_path`, `database_path`, etc.) are NOT semantic configuration identities and are excluded.

### 120.8 OD-H — Cost Identity Mapping (APPROVED & IMPLEMENTED)

`resolved.cost_profile_identity` is the authoritative semantic value stored and validated through the existing durable metadata key:

`cost_schedule_fingerprint`

### 120.9 Scope Boundaries Preserved

- `engine/persistence/schema.py` remains unchanged (`SCHEMA_VERSION = 4`, 21 tables).
- `engine/reconciliation.py` remains unchanged.
- P1-01 through P1-05 remain VERIFIED_COMPLETE.
- P1-07 (strategy runtime-state persistence / restoration), P1-08 (promotion tracking / promotion evidence lifecycle), P1-09 (signal/audit identity collision/version issue), and P1-10 (XLS/XLSX importer/support defect) remain untouched.
- Phase 6 (Logging / Audit) remains unstarted and unauthorized.

### 120.10 Authoritative Marker

`P1_06_VERIFIED_COMPLETE`

---

## 121. Owner-Locked P1-07 — Durable Strategy Runtime-State Persistence / Restoration Contract

**Status:** **VERIFIED_COMPLETE / OWNER_APPROVED**.  
**Scope:** Phase 5 corrective finding **P1-07** only.  
**Implementation status:** **VERIFIED_COMPLETE**. Full independent audit, implementation, and final codec re-verification completed.  
**Authoritative baseline at closure:** **1974 passed, 1 skipped, 0 failures**.

### 121.0 Finding under decision

P1-07: in `engine/live_strategy_coordinator.py`, mutable strategy runtime state is stored solely inside an in-memory dictionary `self._strategy_states: dict[SubscriptionOwnerKey, dict]`. On process restart, `LiveStrategyCoordinator.__init__` unconditionally resets all strategy states by invoking `deepcopy(binding.strategy.initial_state())`. Furthermore, as market bars complete and `safe_generate_signal(adapter, data, state, mode="live")` mutates state in-place, those mutations are never persisted to SQLite. In addition, `self._latest_evaluated_decision_time` is kept in-memory and wiped on restart. As a result, process restarts wipe all multi-bar indicator accumulators, counters, and state machines, causing post-restart evaluation to diverge from continuous runs, miss or duplicate signals, and lack replay protection.

### 121.1 OD-A — Dedicated `strategy_states` Table / Schema V5 (APPROVED)

P1-07 introduces a dedicated SQLite table:

`strategy_states`

`SCHEMA_VERSION` changes:

`4 -> 5`

Canonical table count changes:

`21 -> 22`

No V4 -> V5 migration or backfill is authorized.

Existing Schema-V4 paper databases contain no provable strategy runtime history and MUST fail closed under P1-07.

A P1-07-compatible run requires:
- a new Schema-V5 database; and
- a new `paper_session_id`.

Do not infer historical strategy state from `initial_state()` for an existing V4 session.

### 121.2 OD-B — Strategy State Ownership Key (APPROVED)

Strategy runtime state remains owned exactly according to existing runtime semantics:

`SubscriptionOwnerKey(strategy_id, strategy_version)`

The canonical `strategy_states` primary key is:

`PRIMARY KEY (strategy_id, strategy_version)`

Do NOT split strategy state by instrument or timeframe.

One owner may subscribe to multiple streams/timeframes, but the strategy receives and mutates one shared state dictionary.

`paper_session_id` and `configuration_identity` remain mandatory validation attributes but are not part of the logical ownership key.

### 121.3 OD-C — Canonical State Serialization Contract (APPROVED)

Persist strategy runtime state using the project's canonical JSON / `CanonicalCodec` authority.

Root must be:

`dict[str, Any]`

Supported canonical values are limited to values actually accepted by the canonical serialization contract, including:

- `str`
- `int`
- `bool`
- `None`
- finite `float`
- finite `Decimal`
- timezone-aware `datetime`
- `date`
- `Enum`
- `StrEnum`
- `IntEnum`
- lists / tuples containing supported values
- nested dictionaries with string keys

`NaN`, infinities, unsupported custom objects, numpy/pandas objects, non-string dictionary keys, and non-canonical values MUST fail closed.

Enum decoding resolves classes and strictly verifies `isinstance(enum_cls, type) and issubclass(enum_cls, Enum)`, failing closed on forged or non-Enum envelopes.

Persist explicit:

`codec_version = "sentinelx-strategy-state/v1"`

Compatibility is bound by:

`strategy_version + codec_version + configuration_identity`

No pickle or arbitrary-object serialization is allowed.

### 121.4 OD-D — Actionable Signal Atomicity (APPROVED)

For actionable strategy evaluations that produce `BUY` / `SELL` / `EXIT`:

The strategy post-state and its replay watermark MUST become durable in the SAME SQLite atomic transaction as the downstream durable actionable evidence owned by the paper pipeline.

The transaction must couple strategy state/watermark with the applicable durable intent/order/reservation/protective-plan evidence.

PROHIBITED:

1. Persist strategy state first and order evidence later. This could permanently lose a signal after crash.
2. Persist downstream actionable evidence first and strategy state later. This could cause replay to double-mutate strategy state.

Existing deterministic intent identity / D11 dedup does NOT authorize double mutation of strategy state.

Implementation must preserve one atomic commit or one atomic rollback.

### 121.5 OD-E — Non-Actionable Persistence Cadence (APPROVED)

For evaluations that do not create downstream actionable durable evidence, including:

- `HOLD`
- rejected/non-actionable evaluation
- `observation_only` evaluation

the mutated strategy state and replay watermark MUST be durably persisted atomically at completion of that evaluation.

State mutation from `HOLD` is real state and must not be discarded.

### 121.6 OD-F — Single Replay Watermark (APPROVED)

Persist:

`last_evaluated_decision_time`

as the single authoritative replay watermark per strategy owner.

A completed evaluation with:

`decision_time <= last_evaluated_decision_time`

MUST be skipped after restart and MUST NOT mutate strategy state again.

Do NOT add `last_completed_bar_timestamp` as a second competing authority.

For multi-timeframe subscriptions, `MarketDataCoordinator`'s synchronized `EvaluationRequest.decision_time` remains the canonical decision timestamp.

### 121.7 OD-G — Deterministic Fresh-Session Bootstrap (APPROVED)

A genuinely new Schema-V5 paper session MUST seed one `strategy_states` row for every configured strategy owner before live market-event acceptance.

Seed each row from:

`strategy.initial_state()`

with:

- `codec_version = "sentinelx-strategy-state/v1"`
- `state_generation = 0`
- `last_evaluated_decision_time = NULL`
- `paper_session_id = current durable session identity`
- `configuration_identity = current P1-06 configuration identity`
- `state_json = canonical serialized initial state`
- `state_fingerprint = canonical cryptographic fingerprint`

This explicitly distinguishes:

`VALID NEW OWNER THAT HAS NOT YET EVALUATED A BAR`

from:

`MISSING / CORRUPTED STATE IN AN ONGOING SESSION`

### 121.8 OD-H — Hydration / Corruption Fail-Closed (APPROVED)

On Schema-V5 existing-database reopen:

Every configured strategy owner MUST have exactly one valid durable `strategy_states` row.

Fail closed on:

- missing configured owner row
- malformed `state_json`
- unsupported/non-canonical state
- `state_fingerprint` mismatch
- `codec_version` mismatch
- negative/invalid `state_generation`
- `paper_session_id` mismatch
- `configuration_identity` mismatch

Extra/removed strategy ownership remains protected by P1-06 `configuration_identity` validation.

Do not silently recreate `initial_state()` in an ongoing session.

### 121.9 OD-I — Observation-Only Durability (APPROVED)

`observation_only` strategies receive the SAME strategy-state persistence, restoration and replay guarantees as actionable strategies.

Observation-only means no order authority.

It does NOT mean disposable indicator/runtime state.

### 121.10 OD-J — Live-Paper Persistence Authority (APPROVED)

`engine/state_store.py` MUST NOT become a second live-paper state authority.

Live paper strategy runtime state belongs exclusively to:

`SQLitePaperStateStore`

under the same durable database/session/configuration authority as the rest of paper runtime state.

Reusable canonical serialization helpers may be reused narrowly, but the filesystem JSON storage semantics of `engine/state_store.py` are prohibited for live-paper state.

### 121.11 OD-K — Restore Ordering (APPROVED)

Startup ordering is locked to:

1. resolve configuration / P1-06 identities
2. open Schema-V5 `SQLitePaperStateStore`
3. load and validate durable state including `strategy_states`
4. restore account / broker / protective / safety / risk authorities
5. construct paper coordinator
6. startup reconciliation must be `MATCHED`
7. construct `LiveStrategyCoordinator` with hydrated strategy state and `last_evaluated_decision_time`
8. only after all strategy state is restored may feed/listener/network acceptance occur

No market decision event may reach a cold strategy before hydration.

### 121.12 OD-L — State Generation (APPROVED)

Every committed strategy-state transition increments a monotonic `state_generation` for that owner.

Fresh seeded state begins at generation 0.

Persisted generation must never be negative or regress.

Atomic actionable transactions must increment strategy generation exactly once when the associated evaluation becomes durable.

### 121.13 Verified Data Model

Implemented schema design for `strategy_states`:

```sql
CREATE TABLE IF NOT EXISTS strategy_states (
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    paper_session_id TEXT NOT NULL,
    configuration_identity TEXT NOT NULL,
    codec_version TEXT NOT NULL,
    state_json TEXT NOT NULL,
    state_fingerprint TEXT NOT NULL,
    last_evaluated_decision_time TEXT,
    state_generation INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (strategy_id, strategy_version)
);
CREATE INDEX IF NOT EXISTS idx_strategy_states_session ON strategy_states (paper_session_id);
```

### 121.14 Verified Implementation Deliverables

- `engine/persistence/schema.py`: `SCHEMA_VERSION = 5`, 22 canonical tables, `strategy_states` table DDL and index.
- `engine/persistence/sqlite_store.py`: Canonical codec `sentinelx-strategy-state/v1`, lossless type round-trip, Enum subclass validation, fresh DB generation-0 bootstrap, hydration fail-closed validation, `save_strategy_state` for non-actionable persistence, and `save_t1_entry_submission` atomic coupling.
- `engine/paper_coordinator.py`: Forwarding strategy state transition into atomic T1 entry submission.
- `engine/live_strategy_coordinator.py`: State hydration, replay protection (`decision_time <= last_evaluated_decision_time`), non-actionable persistence, and exception handling / owner halting.
- `engine/live_paper_runner.py`: Resolution of strategy bindings before store construction, passing initial states for clean DB seeding and hydrated states to coordinator.
- Tests: `tests/test_paper_persistence.py`, `tests/test_live_strategy_coordinator.py`, `tests/test_live_paper_runner.py`, and updated schema-version assertions across test suites.

### 121.15 Corrective Register State & Authoritative Marker

The authoritative Phase-5 corrective P1 register is:
- P1-01: Wrong paper RiskGate / configuration values (**VERIFIED_COMPLETE**)
- P1-02: Generic protective-policy fallback (**VERIFIED_COMPLETE**)
- P1-03: Mandatory paper configuration / economics wiring (**VERIFIED_COMPLETE**)
- P1-04: Runtime / WebSocket failures falsely returning completed (**VERIFIED_COMPLETE**)
- P1-05: Production live-paper restart hydration (**VERIFIED_COMPLETE**)
- P1-06: Recovery / configuration / session identity validation (**VERIFIED_COMPLETE**)
- P1-07: Durable strategy runtime-state persistence / restoration (**VERIFIED_COMPLETE**)
- P1-08: Promotion tracking / promotion evidence lifecycle (Decisions Locked)
- P1-09: Signal / audit identity collision / version issue
- P1-10: XLS / XLSX importer / support defect

`P1_07_VERIFIED_COMPLETE`

---

## 122. Owner-Locked P1-08 — Promotion Tracking / Promotion Evidence Lifecycle Contract

**Status:** **VERIFIED_COMPLETE / OWNER_APPROVED**.  
**Scope:** Phase 5 corrective finding **P1-08** only.  
**Implementation status:** **VERIFIED_COMPLETE**. Full independent audit, implementation, bounded OD-W through OD-AC remediation, final Owner policy verification, and 73 promotion tracking tests passing.  
**Authoritative baseline at closure:** **2047 passed, 1 skipped, 0 failures** (73 passed in promotion tracking test suite).

### 122.0 Finding under decision

P1-08: While Step 6 validation produces an immutable backtest statistical gate evaluation (`PromotionDecisionEvidence/v1`) and P1-06 binds static environment flags (`promotion_eligible: bool`, `promotion_ineligibility_reasons: tuple[str, ...]`) into `configuration_identity`, there is currently no durable tracking engine, no promotion state machine, no tracking activation mechanism (`PROMOTION_TRACKING_ACTIVATED`), no SQLite schema/table or persistent record for daily paper promotion progress, no data-gap/fault disqualification tracker, and no cryptographic provenance linking paper runtime execution back to upstream `PromotionDecisionEvidence` or forward to downstream Owner Go-Live review (Q67, Q68, Q120). Process restarts restore no promotion tracking progress, and continuous 6-month paper evidence cannot be verified or proven.

### 122.1 OD-A — Two Independent Promotion Gates (APPROVED)

Two orthogonal promotion gates MUST remain separate:

**GATE A — Upstream Backtest Statistical Gate:**
`PromotionDecisionEvidence.promotable` (in `engine/validation.py`, ADR §51, §52).
- *Meaning:* The strategy candidate passed Step 6 statistical / walk-forward promotion validation ($\ge 3$ complete OOS windows, sample sufficiency $N \ge 200$ or positive Bootstrap CI, MC-1 $q95 \le 1.50 \times \text{baseline}$, MC-2 $q95 \le 1.50 \times \text{baseline}$, stable sensitivity) and is eligible to be selected for paper trading.

**GATE B — Paper Runtime Configuration Eligibility:**
`ResolvedPaperConfiguration.promotion_eligible` (in `engine/paper_configuration.py`, ADR §84, §85, §120).
- *Meaning:* The paper execution environment is canonical (canonical costs, canonical slippage, no fault injection) such that its operational results are qualified to count toward promotion tracking.

These are NOT synonyms and must not be conflated.

**Truth Contract:**
- `promotable = True` + `promotion_eligible = True` $\implies$ May accumulate actionable paper-promotion credit.
- `promotable = True` + `promotion_eligible = False` $\implies$ Paper execution/research allowed, zero promotion credit.
- `promotable = False` + `promotion_eligible = True` $\implies$ Statistically unpromotable, zero promotion credit.
- `promotable = False` + `promotion_eligible = False` $\implies$ Zero promotion credit.

Do NOT redefine `promotion_eligible` to imply upstream validation passed.

### 122.2 OD-B — Per-Owner Upstream Validation Binding (APPROVED)

Upstream `PromotionDecisionEvidence` belongs per:
`SubscriptionOwnerKey(strategy_id, strategy_version)`

Every promotion-tracked strategy binding must bind:
`upstream_promotion_evidence_fingerprint: str`

An optional:
`upstream_promotion_evidence_path: str | null`
may be used only as an artifact locator. The path is NOT semantic identity.

At configuration load / tracking eligibility validation:
1. Load the referenced `PromotionDecisionEvidence` artifact;
2. Recompute its authoritative canonical fingerprint;
3. Compare against configured `upstream_promotion_evidence_fingerprint`;
4. Verify evidence belongs to the configured strategy owner using the actual identity/provenance fields available in the authoritative validation artifact;
5. Verify `promotable == True` / authoritative `PASS` status.

If the existing `PromotionDecisionEvidence` object does not itself contain `strategy_id`/`strategy_version` fields, implementation MUST bind ownership through its existing authoritative parent manifest/finalization provenance rather than inventing fields.

`upstream_promotion_evidence_fingerprint` MUST become part of the strategy binding contribution to `configuration_identity`. Fingerprint mismatch fails closed.

### 122.3 OD-C — Tracking Activation Authority (APPROVED)

The existing root configuration field:
`promotion_tracking_activated`
is the explicit activation authority. It is an ISO-8601 timezone-aware timestamp.

One configured activation timestamp applies to the paper run. Each eligible strategy owner maintains its own durable tracking state in SQLite.

For deterministic session accounting:
- If activation occurs before a full scheduled NSE session begins, that session may become the first tracked session;
- If activation occurs after a scheduled session has already begun, that partial session MUST NOT count as a clean promotion session;
- The first promotable clean-window session is therefore the first full scheduled NSE trading session beginning at or after activation.

No implicit activation is allowed. `promotion_tracking_activated = null` means normal paper operation with promotion tracking `NOT_ACTIVATED`.

### 122.4 OD-D — Contiguous Six-Calendar-Month Contract (APPROVED)

“6 months continuous operational paper trading” means:
A contiguous period spanning at least six full calendar months under the NSE exchange calendar in `Asia/Kolkata`, during which EVERY required scheduled NSE trading session in the clean window has authoritative qualified promotion evidence.

Track:
`window_start_date`

For any evaluation date $D$, tracking completion requires:
$$D \ge \text{window\_start\_date} + \text{relativedelta}(\text{months}=6)$$
AND every required scheduled NSE trading session in that interval has a qualified session record (`SESSION_QUALIFIED`).

A missing or disqualified required market session breaks continuity. After a disqualified session, the previous clean interval cannot be used. The new `window_start_date` becomes the next subsequent full scheduled NSE session that successfully qualifies.

Therefore, one missing/disqualified required session resets the contiguous six-month window. Process restart within the same valid paper session does NOT reset it.

### 122.5 OD-E — NSE Calendar / Timezone Authority (APPROVED)

Promotion session dates use:
- NSE scheduled exchange sessions
- Timezone: `Asia/Kolkata` (IST, UTC+05:30)

Session identity is the canonical NSE trading date (`YYYY-MM-DD`), not UTC calendar date. Weekends and exchange holidays are not missing sessions. Only scheduled NSE market sessions require qualification evidence.

### 122.6 OD-F — Price Gap vs Data-Feed Gap (APPROVED)

Natural market PRICE GAP ($> 1.5 \times \text{14-period daily ATR}$, Q28 / D12) is an informational market condition under its existing frozen authority. It does NOT by itself disqualify promotion credit. Do NOT treat ATR magnitude as a feed-completeness criterion.

DATA-FEED GAP (D3a / D10) means unresolved missing required market-data intervals/bars during a scheduled session. A required unresolved feed gap causes `SESSION_DISQUALIFIED` and breaks/resets the contiguous promotion window.

### 122.7 OD-G — Fault / Failure Semantics (APPROVED)

Three cases remain distinct:
1. **Configuration-level intentional fault injection enabled (D6):**
   `ResolvedPaperConfiguration.promotion_eligible = False`. Entire run is `TRACKING_INELIGIBLE` for promotion credit.
2. **Natural runtime/feed/reconciliation failure during an otherwise canonical promotion-eligible run:**
   Affected scheduled session becomes `SESSION_DISQUALIFIED` and the contiguous clean window resets ($W_{\text{start}}$ moves to next clean session).
3. **Dedicated intentional fault-injection test run:**
   `TRACKING_INELIGIBLE` and isolated from canonical promotion tracking. Do NOT mix deliberate testing evidence with canonical promotion evidence.

### 122.8 OD-H — Observation_Only Evidence (APPROVED)

`observation_only` strategies may maintain promotion-continuity telemetry, but cannot earn actionable promotion credit.

For scheduled sessions they may record:
`EVIDENCE_ONLY_NO_PROMOTION_CREDIT`

Such sessions:
- Do not increment actionable clean-session credit;
- Do not satisfy the contiguous actionable six-month gate;
- Cannot advance the owner to `CRITERIA_MET_PENDING_REVIEW`.

Observation-only evidence remains useful operational evidence but does not replace actionable paper execution evidence.

### 122.9 OD-I — Paper Session Lifetime (APPROVED)

Promotion tracking belongs to one durable logical paper run.

Within the SAME SQLite database + `paper_session_id`, process restarts continue promotion tracking without resetting the clean window.

A new database / new `paper_session_id` begins a NEW promotion tracking ledger and a NEW clean-window lifecycle. Historical previous-session evidence remains immutable history. Promotion credit MUST NOT be silently carried across independent paper sessions.

### 122.10 OD-J — Schema V6 / Zero Migration (APPROVED)

P1-08 advances:
- `SCHEMA_VERSION`: `5 -> 6`
- Canonical tables: `22 -> 24`

Add exactly two dedicated Phase-5 promotion tables:
1. `promotion_tracking_state`
2. `promotion_session_records`

P1-08 MUST NOT depend on Phase-6 `audit_events`.

No Schema-V5 $\rightarrow$ Schema-V6 migration or backfill of historical promotion tracking evidence is authorized. A Schema-V5 database has no provable complete P1-08 session history and therefore MUST fail closed under Schema-V6 code. A P1-08-compatible promotion-tracking run requires a fresh Schema-V6 database and new `paper_session_id`.

### 122.11 OD-K — `promotion_tracking_state` Contract (APPROVED)

One mutable current-state row per `SubscriptionOwnerKey(strategy_id, strategy_version)`.

At minimum bind:
- `strategy_id`
- `strategy_version`
- `paper_session_id`
- `configuration_identity`
- `upstream_promotion_fingerprint`
- `tracking_status`
- `activated_at`
- `window_start_date`
- `clean_days_count`
- `disqualified_days_count`
- `last_evaluated_session_date`
- `milestone_status`
- `state_generation`
- `updated_at`

Primary ownership remains: `(strategy_id, strategy_version)`. `paper_session_id` and `configuration_identity` are mandatory validation attributes. Fresh state generation begins at 0. Every durable state transition increments `state_generation` monotonically.

### 122.12 OD-L — Append-Only Session Evidence (APPROVED)

`promotion_session_records` is append-only promotion evidence for every scheduled NSE session relevant to tracking.

Canonical identity:
`PRIMARY KEY (strategy_id, strategy_version, session_date)`

Each record must be bound to the current `paper_session_id`, `configuration_identity`, and `upstream_promotion_fingerprint`, and include at minimum:
- `session_status` (`SESSION_QUALIFIED` | `SESSION_DISQUALIFIED` | `EVIDENCE_ONLY_NO_PROMOTION_CREDIT`)
- Reason codes / canonical reasons payload (`reasons_json`)
- `recorded_at_utc`

It may include deterministic evidence references required to prove why a session qualified/disqualified. Do NOT duplicate account/trade metrics unnecessarily in each row. A replay/restart for an already-recorded owner/session_date MUST be idempotent and MUST NOT increment promotion counters twice.

### 122.13 OD-M — Lifecycle Evidence Authority (APPROVED)

The combination of:
`promotion_tracking_state` + append-only `promotion_session_records` + final immutable promotion report artifact
is the P1-08 evidence authority.

No third Phase-5 event table is required unless implementation proves that a mandatory lifecycle transition cannot be reconstructed or cryptographically proven from these authorities.

The current state row records current lifecycle state. The append-only session ledger proves session-by-session continuity. The final promotion report snapshots milestone evaluation and all evidence references used for Owner review. Do NOT use Phase-6 `audit_events` as a P1-08 dependency.

### 122.14 OD-N — Performance Metric Authority (APPROVED)

Promotion tracking MUST NOT maintain a duplicate PnL/performance accounting engine.

Canonical paper execution sources remain the existing paper accounting / trade ledger authorities (`trade_records`, `account_state`).

At milestone evaluation, compute/reference:
- Profit Factor (PF)
- Max Drawdown (Max DD)
- Net PnL
- Trade Count
from the authoritative existing paper trade/account evidence. Do not incrementally maintain duplicate metric truth inside promotion state.

### 122.15 OD-O — OOS Authority (APPROVED)

“Out-of-sample profitable” belongs to upstream backtest/walk-forward / validation evidence.

P1-08 references the verified upstream promotion/validation evidence. Paper tracking MUST NOT recompute OOS evidence.

### 122.16 OD-P — Q68 Deviation Sequencing (OWNER RESOLUTION APPROVED)

The frozen requirements contain a sequencing contradiction: Q68 lists `live-vs-paper deviation ≤ 20%` alongside criteria used before initial live authorization. Initial pre-live review cannot possess live execution evidence because no live trades exist yet.

**Owner Resolution:**
- **Phase 5 / P1-08 Pre-Live Gate:** Evaluate the criteria that can actually exist before first live authorization:
  1. Paper PF threshold ($\ge 1.5$)
  2. Paper Max DD threshold ($\le 15\%$)
  3. Upstream OOS profitability
  4. Completed continuous six-month actionable paper evidence
- The literal `live-vs-paper deviation ≤ 20%` is NOT fabricated or renamed to paper-vs-backtest. It is explicitly **DEFERRED** as a post-live Phase-7 monitoring gate after live evidence exists. Do NOT silently reinterpret it as paper-vs-backtest $\le 20\%$.

### 122.17 OD-Q — Latency Evidence Boundary (APPROVED)

`RUNTIME_PERFORMANCE_REQUIREMENTS.md` defines latency targets. There is currently NO canonical latency certificate artifact/schema.

P1-08 MUST NOT invent a fake latency certificate. P1-08 may reference currently available authoritative runtime evidence where such evidence genuinely exists. Creation of a generalized performance certificate belongs to its owning performance/runtime scope, not P1-08. Lack of a fictional certificate must not be hidden by fabricated evidence.

### 122.18 OD-R — Milestone Status Model (APPROVED)

Keep promotion concepts separated rather than creating one giant conflated enum:

- **Configuration / Gate Eligibility:** `ELIGIBLE` | `INELIGIBLE`
- **Tracking Operational Status:** `NOT_ACTIVATED` | `TRACKING_ACTIVE` | `TRACKING_COMPLETED` | `TRACKING_INELIGIBLE`
- **Session Evidence:** `SESSION_QUALIFIED` | `SESSION_DISQUALIFIED` | `EVIDENCE_ONLY_NO_PROMOTION_CREDIT`
- **Milestone Status:** `EVALUATION_PENDING` | `CRITERIA_MET_PENDING_REVIEW` | `CRITERIA_FAILED`

Do NOT include `LIVE_AUTHORIZED` or `REVOKED` as automated P1-08 runtime states.

### 122.19 OD-S — Owner Go-Live Boundary (APPROVED)

P1-08 NEVER automatically activates live trading.

When all pre-live criteria are satisfied, the maximum automatic result is:
`CRITERIA_MET_PENDING_REVIEW` (or semantically equivalent: `ELIGIBLE_FOR_OWNER_REVIEW`)

The engine then emits the final promotion evidence artifact. Actual live authorization is a separate explicit manual Owner decision (Q120). No broker live activation occurs in P1-08.

### 122.20 OD-T — Supersession / Revocation Boundary (APPROVED)

A new strategy semantic version creates a new `SubscriptionOwnerKey` and therefore a new promotion lifecycle.

Old promotion evidence remains immutable historical evidence. It does not need to be mutated to `SUPERSEDED` if newer identity naturally makes it non-current. `LIVE_AUTHORIZED -> REVOKED` belongs outside P1-08 / Phase-5 paper tracking. Do not expand P1-08 into Phase-7 live lifecycle.

### 122.21 OD-U — Final Promotion Report (APPROVED)

When pre-live promotion criteria reach Owner-review readiness, emit:
`sentinelx-paper-promotion-report/v1`

The report MUST be:
- Immutable after finalization;
- Canonical;
- Deterministically fingerprinted via `CanonicalCodec`;
- Bound to strategy owner;
- Bound to `paper_session_id`;
- Bound to `configuration_identity`;
- Bound to `upstream_promotion_evidence_fingerprint`;
- Bound to the promotion tracking `state_generation`;
- Bound to the qualifying session-record evidence;
- Bound to the authoritative performance/OOS evidence used.

Do NOT claim a cryptographic digital signature unless a separate signing authority/key contract actually exists. Canonical fingerprinting is required. Digital signing is NOT introduced by P1-08.

### 122.22 OD-V — Fail-Closed / Credit Rules Matrix (APPROVED)

| Condition / Event | Authoritative Outcome Classification | Rationale / Runtime Action |
|---|---|---|
| Upstream evidence absent on requested activation | `TRACKING_INELIGIBLE` | Cannot activate tracking without backtest validation evidence. |
| Upstream fingerprint mismatch / tampering | `FAIL_STARTUP` | Cryptographic mismatch fails closed immediately. |
| Upstream `promotable = False` | `TRACKING_INELIGIBLE` | Statistically failed strategy cannot accumulate promotion credit. |
| Paper `promotion_eligible = False` | `TRACKING_INELIGIBLE` | Research environment runs for observation, not promotion. |
| `promotion_tracking_activated = null` | `TRACKING_NOT_ACTIVATED` | Normal paper execution; sessions are not tracked for promotion. |
| `observation_only` strategy | `EVIDENCE_ONLY_NO_PROMOTION_CREDIT` | Records session history; zero actionable promotion credit. |
| Natural price gap $> 1.5\times$ ATR (Q28) | Does NOT disqualify | Informational market condition; normal qualification rules continue. |
| Unresolved required data-feed interval missing | `SESSION_DISQUALIFIED` | Missing data interval; session disqualified; clean-window resets. |
| Natural runtime/reconciliation failure affecting required session | `SESSION_DISQUALIFIED` | Coordinator halts fail-closed; clean-window resets. |
| Intentional fault-injection configuration | `TRACKING_INELIGIBLE` | Entire run ineligible for promotion credit. |
| Machine offline for required scheduled NSE session | `SESSION_DISQUALIFIED` | Missing trading session; clean-window resets. |
| Duplicate / replayed `owner + session_date` | `IDEMPOTENT_IGNORE` | Replay protection skips without double-counting. |
| Corrupt promotion state in DB | `FAIL_STARTUP` | Persistence corruption fails closed (`PersistenceCorruptedError`). |
| Corrupt append-only session evidence in DB | `FAIL_STARTUP` | Persistence corruption fails closed (`PersistenceCorruptedError`). |
| Configuration identity mismatch on restart | `FAIL_STARTUP` | P1-06 identity mismatch fails closed (`DatabaseIdentityMismatchError`). |
| Schema V5 DB opened by V6 runtime | `FAIL_STARTUP` | Incompatible schema version fails closed (`DatabaseIdentityMismatchError`). |
| Six-month contiguous window incomplete | `MILESTONE_INCOMPLETE` | Cannot transition to `CRITERIA_MET_PENDING_REVIEW`. |
| Pre-live Q68 PF/Max-DD/OOS criteria failure | `CRITERIA_FAILED` | 6 months completed, but numeric thresholds failed; review blocked. |
| Q68 live-vs-paper $\le 20\%$ before first live deployment | `DEFERRED_TO_PHASE7` | Post-live monitoring gate; not evaluated pre-live. |
| All Phase-5 pre-live criteria satisfied | `CRITERIA_MET_PENDING_REVIEW` | Emits `sentinelx-paper-promotion-report/v1` for Owner review. |

### 122.23 Expected Schema Design / DDL

Expected DDL for Schema V6:

```sql
CREATE TABLE IF NOT EXISTS promotion_tracking_state (
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    paper_session_id TEXT NOT NULL,
    configuration_identity TEXT NOT NULL,
    upstream_promotion_fingerprint TEXT,
    tracking_status TEXT NOT NULL,
    activated_at TEXT,
    window_start_date TEXT,
    clean_days_count INTEGER NOT NULL DEFAULT 0,
    disqualified_days_count INTEGER NOT NULL DEFAULT 0,
    last_evaluated_session_date TEXT,
    milestone_status TEXT NOT NULL,
    state_generation INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (strategy_id, strategy_version)
);
CREATE INDEX IF NOT EXISTS idx_promotion_tracking_session ON promotion_tracking_state (paper_session_id);

CREATE TABLE IF NOT EXISTS promotion_session_records (
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    session_date TEXT NOT NULL,
    session_status TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    metrics_snapshot_json TEXT,
    recorded_at_utc TEXT NOT NULL,
    PRIMARY KEY (strategy_id, strategy_version, session_date)
);
CREATE INDEX IF NOT EXISTS idx_promotion_session_date ON promotion_session_records (session_date);
```

### 122.24 Implementation Boundary

Anticipated production files:
- `engine/paper_configuration.py`
- `engine/persistence/schema.py`
- `engine/persistence/sqlite_store.py`
- `engine/live_paper_runner.py`
- `engine/paper_coordinator.py`
- `engine/promotion_tracking.py`

Expected tests:
- `tests/test_paper_promotion_tracking.py`
- `tests/test_paper_configuration.py`
- `tests/test_paper_persistence.py`
- `tests/test_live_paper_runner.py`

Scope firewalls:
- P1-01 through P1-07 remain `VERIFIED_COMPLETE`.
- P1-09 (signal/audit identity collision/version issue) and P1-10 (XLS/XLSX importer/support defect) remain untouched.
- Phase 6 (Logging / Audit) remains unstarted, unauthorized, and firewalled.

### 122.26 OD-W — Canonical Upstream Promotion Provenance Bundle (APPROVED)

Existing `PromotionDecisionEvidence/v1` is NOT sufficient by itself to prove the configured paper strategy owner because its canonical schema does not contain a structured `(strategy_id, strategy_version)` pair. Unfingerprinted wrapper JSON fields MUST NOT be trusted.

P1-08 introduces exactly ONE canonical upstream provenance authority:
`sentinelx-upstream-promotion-bundle/v1`

The bundle is immutable and canonically fingerprinted. It must semantically bind at minimum:
- `schema_version = "sentinelx-upstream-promotion-bundle/v1"`
- `strategy_id: str`
- `strategy_version: str`
- `manifest_fingerprint: str`
- `promotion_decision_fingerprint: str`
- `promotion_decision: PromotionDecisionEvidence`

The bundle fingerprint MUST cover:
`strategy_id`, `strategy_version`, `manifest_fingerprint`, `promotion_decision_fingerprint`, and every other semantic identity field in the bundle.

At load time:
1. Deserialize the canonical bundle;
2. Recompute bundle fingerprint;
3. Verify configured `upstream_promotion_evidence_fingerprint` equals bundle fingerprint;
4. Verify bundle `strategy_id`/`strategy_version` equals configured `SubscriptionOwnerKey`;
5. Deserialize/verify `PromotionDecisionEvidence`;
6. Recompute its authoritative `result_fingerprint`;
7. Verify it equals `promotion_decision_fingerprint`;
8. Verify its `manifest_fingerprint` equals the bundle `manifest_fingerprint`;
9. Verify `promotable == True` / authoritative `PASS` before actionable promotion credit can be earned.

Any mismatch fails closed (`PaperConfigurationError`). Paper configuration's `upstream_promotion_evidence_fingerprint` refers to the canonical bundle fingerprint. The locator path remains non-semantic. Changing bundle fingerprint MUST change `configuration_identity`; changing only locator path MUST NOT.

### 122.27 OD-X — Immutable NSE Calendar Closure Snapshot (APPROVED)

SentinelX has `WeekendCalendar` plus injected closures but no built-in authoritative annual NSE holiday dataset. P1-08 MUST NOT depend on mutable network calendar lookup.

A promotion-tracked paper run must receive an explicit immutable exchange calendar snapshot in configuration.
Canonical schema/version: `sentinelx-calendar-closure-snapshot/v1`

The snapshot must bind at minimum:
- `calendar_id: str`
- `exchange = "NSE"`
- `timezone = "Asia/Kolkata"`
- `coverage_start: date`
- `coverage_end: date`
- `closed_dates: tuple[date, ...]` (sorted canonically)
- Session-time overrides (if any represent an exchange session differing from the normal `MarketProfile`).

Canonical fingerprint `calendar_fingerprint` is computed through `CanonicalCodec.fingerprint` over all semantic snapshot fields. `calendar_fingerprint` MUST be bound into `ResolvedPaperConfiguration.configuration_identity`.

Fail closed before promotion tracking if:
- Snapshot is malformed;
- Fingerprint mismatch;
- Exchange / timezone mismatch;
- Requested active promotion window lies outside snapshot coverage;
- Session schedule cannot be determined unambiguously.

Weekends and snapshot-declared NSE closures are not required trading sessions. Only canonical scheduled exchange sessions require promotion evidence.

### 122.28 OD-Y — Caller-Supplied Promotion Report Destination (APPROVED)

Existing SentinelX `ReportWriter` convention uses a destination supplied explicitly by the caller. `PromotionReportWriter` MUST NOT hard-code `data/promotion_reports` and P1-08 MUST NOT owner-lock an implicit default such as `reports/promotion`.

The promotion report destination must be supplied explicitly through the existing runtime/configuration/caller artifact-destination authority (`ResolvedPaperConfiguration.promotion_report_destination_dir` or caller argument). The path itself is strictly NON-SEMANTIC.

If report publication becomes required and no valid destination is supplied: FAIL CLOSED / publication cannot be declared complete. Canonical report filename and canonical report fingerprint remain strictly path-independent. Moving the finalized artifact to another destination MUST NOT change its semantic fingerprint.

### 122.29 OD-Z — Append-Only Session Record Integrity (APPROVED)

Every row in `promotion_session_records` must carry:
- `record_schema_version = "sentinelx-promotion-session-record/v1"`
- `record_fingerprint: str`

`record_fingerprint` is computed using `CanonicalCodec.fingerprint` over all semantic row fields:
- `strategy_id`
- `strategy_version`
- `paper_session_id`
- `configuration_identity`
- `upstream_promotion_fingerprint`
- `session_date`
- `session_status`
- Canonical sorted `reasons` payload

`recorded_at_utc` is metadata/wall-clock evidence and is NOT part of semantic identity.
On hydration, `load_promotion_session_records` recomputes every record fingerprint. Any mismatch raises `PersistenceCorruptedError` and immediately halts startup. Append-only historical rows MUST NOT be silently rewritten.

### 122.30 OD-AA — State / Ledger Consistency Validation (APPROVED)

On hydration, `promotion_tracking_state` must be cross-validated against the owner's append-only `promotion_session_records`:
1. `clean_days_count` equals the number of actionable `SESSION_QUALIFIED` records that actually count for promotion credit.
2. `disqualified_days_count` equals the number of `SESSION_DISQUALIFIED` records counted by the aggregate state contract.
3. If session rows exist: `last_evaluated_session_date == max(session_date)`.
4. If `window_start_date is not None`: every actionable promotion-credit session from `window_start_date` through `last_evaluated_session_date` must preserve the contiguous-clean-window contract; zero `SESSION_DISQUALIFIED` records may exist inside the currently claimed clean window.
5. Tracking status / milestone status must not claim completion when the ledger cannot prove the required contiguous interval.
6. `state_generation` must be non-negative and compatible with durable state-transition history.

Any deterministic contradiction raises `PersistenceCorruptedError` and halts startup. The engine must NOT silently repair aggregate state from corrupted evidence.

### 122.31 OD-AB — Full-Session Observation / Early Shutdown (APPROVED)

`SESSION_QUALIFIED` requires authoritative proof that the runner observed the entire required scheduled exchange session from regular open through regular close. Merely reaching `LivePaperTradingRunner.run()` `finally:` does NOT prove qualification.

The contract uses `MarketSessionBoundary` and `MarketProfile` authority (`profile.regular_session_open` and `profile.regular_session_close`); literal timestamps (`09:15` / `15:30`) describe the standard India/NSE profile baseline but MUST NOT be hardcoded as generic constants.

Qualification requires:
- Runner active no later than authoritative `market_boundary.profile.regular_session_open`;
- Runner remains operational through authoritative `market_boundary.profile.regular_session_close`;
- No promotion-disqualifying runtime / feed / reconciliation condition exists;
- The session is a required scheduled exchange session under OD-X.

If the runner terminates before `market_boundary.profile.regular_session_close`:
- Clean / manual stop $\implies$ `SESSION_DISQUALIFIED` with reason `INCOMPLETE_SESSION_OBSERVATION`.
- Failed stop $\implies$ `SESSION_DISQUALIFIED` with authoritative failure reason (`RUNTIME_FAILURE`).
- Runner starting after `market_boundary.profile.regular_session_open` cannot earn full-session actionable credit for that session (`PARTIAL_SESSION_AT_ACTIVATION` where activation-related, otherwise `INCOMPLETE_SESSION_OBSERVATION`).
- Starting after market close does NOT retroactively prove that the day's session was observed and MUST NOT receive `SESSION_QUALIFIED`.

### 122.32 OD-AC — Offline Recovery Anchor (APPROVED)

Offline recovery MUST NOT use `window_start_date` as its recovery-existence gate.
Canonical durable recovery anchor:
1. If `last_evaluated_session_date` exists:
   `anchor = last_evaluated_session_date`.
2. Else if promotion tracking has activated:
   Convert `activated_at` through the authoritative exchange timezone and `MarketSessionBoundary` / calendar to determine the FIRST FULL REQUIRED EXCHANGE SESSION requiring promotion evidence under OD-C / OD-AB. Recovery begins immediately before that first required session. If activation occurred after regular open on that session date, apply locked partial-session semantics rather than using raw calendar date arithmetic.
3. Else:
   There is no activated promotion recovery work.

Recovery then evaluates every fully elapsed required exchange session strictly after `anchor` and before the currently active/uncompleted session (`current_trading_date`), in canonical chronological order.
For an eligible actionable owner: missing required elapsed session $\implies$ `SESSION_DISQUALIFIED` with `OFFLINE_REQUIRED_SESSION`.
A previously disqualified owner with `window_start_date = None` MUST STILL undergo offline missing-session reconciliation. Repeated recovery must be idempotent. The current not-yet-completed market session must not be prematurely disqualified.


### 122.33 Bounded Implementation Remediation (COMPLETED)

All 7 bounded defects (OD-W through OD-AC) have been implemented and verified:
1. Runner session finalization verifies `now_ist >= regular_session_close` and start boundary before awarding `SESSION_QUALIFIED` (OD-AB);
2. Upstream promotion evidence verifier requires canonical `UpstreamPromotionEvidenceBundle` with full strategy owner binding and SHA-256 fingerprint verification (OD-W);
3. Offline recovery anchors cleanly to `last_evaluated_session_date` or `activated_at` and never skips owners with `window_start_date is None` (OD-AC);
4. Calendar authority incorporates immutable `CalendarClosureSnapshot` with coverage assertions and inclusion in `configuration_identity` (OD-X);
5. Promotion report writers require explicit caller-supplied `destination_dir` with zero ambient defaults (OD-Y);
6. `promotion_session_records` table carries `record_schema_version` and `record_fingerprint` with hydration verification and `recorded_at_utc` excluded from semantic hash (OD-Z);
7. Hydration executes strict aggregate-state vs ledger consistency validation (OD-AA).

### 122.35 Owner Policy Override — Zero Mandatory Minimum Paper Duration & Explicit Mode Authority (APPROVED)

The Owner ruling overrides any prior assumption of a mandatory six-month paper trading lock:
1. **Zero Mandatory Minimum Paper Duration:** There is NO mandatory minimum paper-trading duration before the Owner may choose LIVE mode. Minimum required paper duration is ZERO.
2. **Explicit Owner Mode Authority:** PAPER and LIVE mode choice is an explicit Owner-controlled authority. The Owner may choose PAPER or LIVE at any time.
3. **Independent Evidence Validation:** Walk-forward, backtest, and statistical validation remain independent evidence sources and do not create a mandatory six-month runtime lock.
4. **Optional Telemetry / Reporting:** Six-month promotion tracking remains ONLY as OPTIONAL telemetry, evidence generation, and reporting.
5. **No Live-Mode Prerequisites:** Six-month completion is NEVER required for owner mode selection, enabling LIVE mode, or switching between PAPER and LIVE.
6. **No Automatic Switching:** SentinelX MUST NOT automatically switch PAPER -> LIVE.
7. **Optional Tracking Integrity:** If optional tracking is enabled, its persistence, calendar closure snapshot, session integrity, reports, restart handling, and state/ledger cross-validation remain fully enforced.
8. **Tracking Disabled Non-Invasiveness:** If optional tracking is disabled, normal PAPER/LIVE mode operation MUST NOT require `promotion_tracking_activated`, `calendar_closure_snapshot`, `upstream_promotion_evidence_bundle`, six-month completion, or promotion report destination.
9. **Status Meaning:** Status such as `CRITERIA_MET_PENDING_REVIEW` exists only as OPTIONAL evidence status and is never a live-mode authorization prerequisite.
10. **Semantic Fingerprint Invariant:** `recorded_at_utc` is metadata-only wall-clock evidence and MUST NOT participate in `sentinelx-promotion-session-record/v1` semantic record fingerprint.

### 122.36 Authoritative Marker

`P1_08_VERIFIED_COMPLETE`
`P1_08_FORMAL_CLOSURE_COMPLETE`
`COMMIT_PERFORMED: NO`
`PUSH_PERFORMED: NO`

---

## 123. Phase 6 — Logging / Audit — Owner Decision Register (APPROVED)

**Status:** **OWNER APPROVED — Phase-6 owner decision stage CLOSED.**

**Scope:** Build-order Phase 6 (Logging / Audit). **Phase 6 implementation remains NOT STARTED** and requires separate owner authorization.

**Authority:** Recorded under §1 items 3–6. Every supersession is enumerated in §123.10. All superseded text is preserved.

### 123.0 Decision context

The Phase-6 pre-implementation architecture / contract / scope review identified fourteen candidate owner decisions, consolidated to nine, and independently challenged before owner ruling. This section records the owner's binding rulings on all nine, the single taxonomy question resolved within them, and the compliance obligations that follow. It decides scope only; it implements nothing.

### 123.1 OD-1 — D16 Envelope Closure, Envelope v2, Schema V7 (APPROVED)

The D16 §96 minimum envelope is closed. `AUDIT_ENVELOPE_SCHEMA_VERSION` advances to `sentinelx-audit-envelope/v2` and `SCHEMA_VERSION` advances **6 → 7**.

Seven fields are added to `AuditEvent` and to the `audit_events` table as **proper persisted fields**, not payload keys:

| Field | Nullability | Authoritative provider |
|---|---|---|
| `environment` | NOT NULL | New `paper_metadata` key; `paper` or `live` only |
| `run_id` | NOT NULL | `paper_metadata.paper_session_id` |
| `canonical_configuration_fingerprint` | NOT NULL | `paper_metadata.configuration_identity` (§120.7) |
| `source_identity` | NOT NULL | New `paper_metadata` key — non-secret data-source identity |
| `timeframe` | **NULLABLE** | Resolved strategy binding (§120.7); NULL where not applicable |
| `status` | NOT NULL | Total derivation from `AuditEventType` |
| `severity` | NOT NULL | Total derivation from `AuditEventType` |

Binding constraints:

1. **`derive_audit_event_id()` inputs remain unchanged.** No new field enters ID derivation. Every existing deterministic `event_id` remains byte-identical.
2. **All seven fields join `AuditEvent.semantic_projection()`.** Conflict comparison is intra-database, and all seven values are deterministic within a session, so §117 replay idempotency is preserved. `audit_sequence` and `recorded_at_utc` remain excluded.
3. **Zero migration.** Clean databases bootstrap at V7; Schema V1–V6 databases fail closed. Zero automatic migration, zero silent upgrade, zero destructive recreation. This is the established policy of §113.3, §114.2, §115.2, §121 and §122 — not an exception to it.
4. `source_identity` is the **data-source** identity of §96 (feed/adapter identity plus instrument-master fingerprint). It is never the source-code identity of `engine/reproducibility/source.py`, and never a credential or token (§118.5, Q107).
5. `event_schema_version` validation remains strict single-value fail-closed. Envelope v1 is not readable by v2 code. No v1 database exists.
6. `environment` retains the D16 vocabulary `backtest` / `paper` / `live`. Phase 6 populates `paper` and `live` only; the `backtest` value is defined but never emitted (see §123.4). This is intentional and must not be "fixed".
7. `status` and `severity` derivations must be **total** over `AuditEventType`. Partial coverage is a defect.

### 123.2 OD-2 — Non-Audit Per-Strategy Evaluation Logging (APPROVED)

Q90 is satisfied by a **separate, non-audit** per-strategy evaluation log. Every evaluation, including `HOLD`, is recorded there.

§114.9 remains in full force and unamended: `HOLD` signals produce **zero `audit_events`, zero T1 state transitions, zero orders, zero reservations**. The evaluation log is debugging and diagnostic evidence; it is not the audit journal, not an accounting or execution authority, and carries no D16 envelope obligation. It is the highest-volume sink and is rotation-bounded under §123.6.

### 123.3 OD-3 — Event-Family Scope: One Additive Family, Three Refusals (APPROVED)

**(a) RECONCILIATION — REFUSED.** No `RECONCILIATION` `AuditEventFamily` and no reconciliation `AuditEventType` values are added. §115.14 stands in full force. `reconciliation_reports` and `reconciliation_findings` remain the sole reconciliation authority; the audit journal remains read-only to Item 12. D16's Reconciliation family obligation is discharged by documented **equivalence**: the Item-12 tables carry `report_id` (§115.4), deterministic `finding_key` / `finding_id`, severity, status and timestamps, which map field-for-field onto the D16 envelope without duplicating evidence into the journal. Phase 6 documents that mapping and implements no emitter.

**(b) CONFIGURATION_CHANGE and STRATEGY_VERSION_CHANGE — REFUSED as unreachable.** `configuration_identity` binds risk-policy, cost-profile and execution-policy identities plus the complete strategy binding set (`strategy_id`, `strategy_version`, `activation`, `instrument`, `timeframe`, protective-policy identity) plus promotion eligibility (§120.7). Any change to configuration or to a strategy version changes that digest, and a changed digest **fails closed** on reopen (§120.4, §121.8). Configuration and strategy version are therefore **session-boundary immutable**: a change is definitionally a new database with a new `paper_session_id` and a new `configuration_identity`. An in-session emitter would be dead code and is prohibited.

The applicable Phase-4.5 audit-trail requirement is satisfied by: durable fail-closed `configuration_identity` and `paper_session_id` validation on every open; `canonical_configuration_fingerprint` present on **every** audit row (§123.1); `strategy_version` already carried on the envelope (§116.20); and E1 `SESSION_STARTED` / E17 `RUNTIME_STARTED` + `STATE_HYDRATED` as boundary markers. This is stronger evidence than a self-reported change event.

**(c) APPROVAL_SIGNOFF — OBLIGATION DEFINED, IMPLEMENTATION DEFERRED.** Explicit owner mode authority and the prohibition on automatic PAPER → LIVE switching are governed by §122.35 items 2, 5, 6 and 9 and by `CLAUDE.md` ("Going live is always a manual, explicit approval — never automatic"). The obligation is recorded here: the future live-authorization workflow must produce durable, immutable, D16-envelope-conformant sign-off evidence identifying the approver, the approved configuration fingerprint, the evidence relied upon, and the UTC decision time. **Phase 6 implements no `APPROVAL_SIGNOFF` emitter.**

**(d) ERROR — APPROVED as E21, under explicit supersession.** D16 §96 names Error as a required minimum family and Q89 requires durable error evidence; §123.6 makes error files rotation-bounded, so a file-only path cannot by itself provide immutable evidence. One family is added:

- `AuditEventFamily.ERROR` — **D16-E21**
- `AuditEventType.STRATEGY_EXCEPTION` — a Rule 7 strategy exception caught in paper or live
- `AuditEventType.RUNTIME_ERROR` — a contained non-strategy runtime error in the paper/live runtime

E1–E20 are **never renamed, renumbered or reordered**. This extension is additive only. It is authorized as an explicit §1 item 3 supersession of the closure wording enumerated in §123.10, and it does **not** reopen §123.3(a): no RECONCILIATION family is added, now or later, without a further explicit owner decision.

E21 contracts:

1. **Observational only.** `state_generation = NULL`, zero business generation bump, zero T1 transaction, UUIDv4 identity via the existing observational branch of `derive_audit_event_id()`. Consistent with §114.6 and §115.3.
2. **Bounded.** Durable emission occurs on the **first occurrence only** per `(paper_session_id, strategy_id, error_class)`. Every occurrence is written to the Q89 error file. The existing per-strategy halt latch bounds the strategy path to approximately one event per strategy per process.
3. **Payload bounded and sanitized.** Payload carries exception class name, a fingerprint of the sanitized message, Rule 7 `strategy_id` and `interface_version`, and a correlation reference into the error file. It carries **no traceback and no raw message** — unbounded size and a secret-exposure surface (Q107, §118.5).
4. **Q89 detail stays in the error file.** Full timestamp, stack trace and context remain in the separate error file, which is the Q89 authority for detail, retained per §123.6.
5. **Persistence-failure paradox preserved (§114.12).** Emission is best-effort and never an authority. If the durable append fails, the runtime must not raise from the error path, must not retry recursively, and must not fabricate an event; `PersistenceHealth` transitions to `FAILED` through the existing Item-10 path, and the error file retains the evidence. No fake durable database event is ever claimed.
6. **No interface change.** Emission is registered behind the existing `engine/audit_log.py` Rule 7 facade. `safe_generate_signal(strategy, data, state, mode)` is unchanged. Where no durable sink is registered — including all backtest execution — no event is emitted and the error file is the only sink.

### 123.4 OD-4 — Backtest Exemption, Docs-Level Clarification Only (APPROVED)

No D16 journal wiring is added to the backtest engine. The backtest engine remains frozen behind its completion gate; zero production changes.

Q69 requires **paper ↔ live** comparability, and §96 scopes the shared schema to Paper and future Live. Backtest evidence remains its existing reproducibility/report model (`StructuredBacktestResult`, `ReportProvenance`, versioned report schemas, `engine/reproducibility/`), which independently satisfies the Phase-4.5 reproducibility requirements. Phase 6 adds a **documentation clarification only**, describing the two separate evidence models and why they are not unified.

**No permanent backtest → D16 mapping conformance test is created.** No frozen requirement mandates one. The paper ↔ live parity conformance obligation belongs to Phase 7, when Live exists.

### 123.5 OD-5 — SQLite Sole Durable Journal Authority (APPROVED)

`SQLitePaperStateStore` / `audit_events` remains the **sole durable journal authority** (§114.1). `logs/audit_log/` is a **derived, regenerable, non-authoritative export**, produced through the read-only query API, never read back as authority, and never a second writer. D16 storage-independence is demonstrated by the export, not by a second source of truth.

`PROJECT_STRUCTURE.md` wording is corrected accordingly: the directory is not the authority, and it does not contain "every signal" — `HOLD` is excluded by §114.9 and §123.2.

### 123.6 OD-6 — Logging Configuration and Retention (APPROVED)

A separate `config/logging_config.yaml` with a corresponding `CONFIG_SCHEMA.md` section is established. The frozen §93 paper-configuration schema is **not** amended and gains no logging block.

1. Configuration may control **levels, sinks, rotation and retention only**.
2. **Redaction is mandatory and MUST NOT be disableable by configuration.** It is a non-optional filter on every sink, not a policy toggle. No secret, token or credential is ever written to any sink (Q107, §118.5).
3. **Required evidence retention is preserved.** The audit journal and its derived export are never auto-deleted. Error-log retention must cover the §114.13 evidence-retention requirement and, where optional promotion tracking is enabled, the active promotion-evidence window — because the error file is the Q89 detail authority. Per §122.35 items 1 and 4 there is no mandatory minimum paper duration and promotion tracking is optional telemetry, so no fixed six-month retention floor is asserted here. Rotation of operational and evaluation logs must never reduce evidence retention below the applicable floor.
4. Logging configuration carries its own version identity.

### 123.7 OD-7 — Q88 Reason Capture: Lifecycle Evidence Is Authority (APPROVED)

`Signal` is unchanged. Rule 1, Rule 6, Rule 8 and `safe_generate_signal` are untouched.

1. **Lifecycle/order evidence is the sole exit-reason authority** — E13 protective lifecycle, E8 terminal order lifecycle, E20 manual reduce/close. Exit reason is derived from that evidence and never self-reported.
2. `Signal.metadata["reason"]` may only be **validated, length-bounded, character-sanitized, redaction-filtered DESCRIPTIVE logging and reporting data.** It is optional; absence is legal and never causes rejection.
3. It **MUST NOT** become execution, risk, sizing, order, identity or protective authority. It must not enter `derive_audit_event_id()` inputs, `configuration_identity`, position or order identity, or any gating decision. It may appear only inside descriptive payload and report projections.
4. Net P&L and average exit price for the Q88 trade log are derived by joining canonical trade, leg and cost records. No `TradeRecord` change.

### 123.8 OD-8 — Reference Catalog (APPROVED)

`REFERENCE_REPOS.md` gains a Phase-6 logging/audit capability mapping for **Freqtrade — Class D, concept-only, GPL-3.0, no code/test/fixture copying** (`REFERENCE_ROUTING_RULES.md` §5, §8). Recorded so the §4 coverage gate is answerable from the catalog at Phase-6 closure.

### 123.9 OD-9 — Documentation Numbering and Structure Cleanup (APPROVED)

Docs-only. A numbering-equivalence note is added — **build-order Phase 6 (Logging) ≡ `requirements-freeze-125.md` Phase 9 (Q88–Q93) plus the Phase 4.5 audit-trail requirements** — and **all** stale phase labels are swept, not only one line. `requirements-freeze-125.md` is **not** renumbered or edited; every existing Q-number citation remains valid.

### 123.10 Supersession Register (§1 items 3–5)

This section explicitly supersedes the following clauses, for the identified scope only. All superseded text is preserved for traceability (§1 item 5). All unrelated frozen requirements and engineering contracts remain completely unchanged (§1 item 6).

| Superseded clause | Scope of supersession |
|---|---|
| §114.3 core envelope field list | Extended by the seven §123.1 fields; existing fields unchanged |
| §114.4 / `AUDIT_ENVELOPE_SCHEMA_VERSION = v1` | Advanced to `v2` |
| §115.14 "taxonomy remains untouched and closed" | Additive E21 `ERROR` only. The RECONCILIATION prohibition is **not** superseded and remains in force |
| §116.20 "Item-11 audit taxonomy remains unchanged (zero new event families/types)" | Additive E21 `ERROR` only |
| §116.20 / §118.4 "`SCHEMA_VERSION` remains exactly 4" | Already superseded by §121 (V5) and §122 (V6); now V7 |
| §122 "`SCHEMA_VERSION` 5 → 6" as terminal | Advanced to V7 |
| `SENTINELX_PROGRESS.md` P1-09 item 7 — "`semantic_projection()` … remain untouched; schema remains V6" | Projection extended per §123.1 item 2; schema V7. `derive_audit_event_id`, `audit_events UNIQUE(event_id)` and `AuditIntegrityError` remain **untouched** |
| `PROJECT_STRUCTURE.md` `logs/audit_log/` description | Corrected per §123.5 |

**Not superseded, and reaffirmed:** §114.1 sole-owner rule; §114.5 append-only-by-policy with no cryptographic tamper-evidence claim; §114.6 same-transaction atomicity; §114.7 hybrid identity and `AuditIntegrityError` fail-closed; §114.8 `recorded_at_utc_now()` as sole wall-clock; §114.9 HOLD exclusion; §114.12 persistence-failure paradox; §114.13 no dashboard / no analytics / retention; §114.14 journal-does-not-reconcile; §115.14 RECONCILIATION prohibition; §120 and §121 identity validation; §122.35 owner mode authority; the Rule 1 / 6 / 7 / 8 contracts; and `safe_generate_signal(strategy, data, state, mode)`.

### 123.11 Standing Constraints (compliance obligations, not decisions)

1. **Q92 daily summary and Q93 monthly per-strategy report remain Phase-6 scope.** Neither may be deferred to dashboard or UI. §114.13's "no dashboard, no analytics" constrains the journal, not report generation.
2. Q92 / Q93 aggregate **only** from canonical accounting, trade, leg and cost records. `audit_events` is never an accounting authority (§114.1, §114.14).
3. **No promotion-tracking dependency** in any Phase-6 path, consistent with §122.35 item 8.
4. `recorded_at_utc_now()` remains the sole approved wall-clock source; it never informs a trading, sizing, fill or protective decision.
5. `safe_generate_signal(strategy, data, state, mode)` remains unchanged; Phase 6 implements behind the Rule 7 facades.
6. **No live alert transport in Phase 6** — no Telegram, SMS or email. Phase 6 delivers the durable sink behind the existing `SafetyManager.on_alert` seam only.
7. No secret, token or credential is written to any sink.
8. Tests currently pinning `SCHEMA_VERSION == 6` or envelope `v1` are **implementation-update obligations, not additional owner decisions.**

### 123.12 Explicitly Out of Scope for Phase 6

SQLite trigger-level immutability and cryptographic hash chaining (backlog; §114.5's stance is reaffirmed, not reopened); any second `audit_events` writer; backtest journal wiring; a `RECONCILIATION` family; `CONFIGURATION_CHANGE` / `STRATEGY_VERSION_CHANGE` emitters; an `APPROVAL_SIGNOFF` emitter; live alert transport; dashboard or analytics surfaces; any `Signal`, `TradeRecord` or Rule 1 interface change.

### 123.13 Authoritative Marker

`PHASE_6_OWNER_DECISIONS_RECORDED`
`PHASE_6_OWNER_DECISION_STAGE: CLOSED`
`PHASE_6_IMPLEMENTATION_STARTED: NO`
`SCHEMA_VERSION_CHANGED: NO — V7 IS APPROVED SCOPE, NOT YET IMPLEMENTED`

---

## 124. Phase 6 Slice 3 — Owner Rulings: Q92/Q93 Recognition, Empty Day, Auto-Finalization (APPROVED)

**Status:** OWNER APPROVED (Slice-3 owner rulings). Append-only record; §123 text is unchanged and remains in force. These rulings bind the Q92/Q93 implementation on top of §123.11.

### 124.1 R1 — Q92 Daily Recognition Date (APPROVED)

A completed trade belongs to the Q92 daily summary for `TradeRecord.closed_at`, converted to Asia/Kolkata and reduced to the local calendar date. This is the canonical Q92 recognition/grouping key. Realized P&L and canonical costs belong to the completion/recognition period; entry timestamp is NOT the Q92 grouping authority; wall-clock time is NEVER a grouping authority.

### 124.2 R2 — Q92 Empty Day (APPROVED)

A valid empty daily summary is exactly: `completed_trade_count = 0`, `gross_realized_pnl = Decimal("0")`, `total_cost = Decimal("0")`, `net_realized_pnl = Decimal("0")`, `strategies = ()`, `currency = None`.

### 124.3 R3 — Q93 Auto-Generation Trigger (APPROVED)

Q93 is NOT merely an on-demand aggregation helper. During PAPER/LIVE runtime, when the runtime first observes market/event time belonging to a NEW Asia/Kolkata calendar month, it must automatically finalize the immediately previous calendar month (and any further completed months skipped by an observation gap, each exactly once). The trigger uses only canonical market/event time already flowing through the runtime. `datetime.now()`, `time.time()`, or any independent wall clock MUST NOT decide a month rollover.

### 124.4 R4 — Current Partial Month (APPROVED)

The current/incomplete IST month MUST NOT be finalized as a final Q93 monthly report. Only a completed previous month is eligible for auto-finalization.

### 124.5 R5 — Restart-Safe Exactly-Once Finalization (APPROVED)

A final monthly publication identity is `(paper_session_id, year, month)`. For the same identity, restart/reopen MUST NOT create a second final monthly report. Exactly-once means durable/idempotent final publication semantics, not an in-memory set.

### 124.6 R6 — Q93 Content (APPROVED)

A finalized month contains deterministic per-strategy rows ordered by strategy_id then strategy_version (plus existing deterministic month ordering). Financial values derive ONLY from canonical TradeRecord/TradeLeg and cost_assessments/canonical cost-accounting evidence — never audit_events, never promotion_tracking.

### 124.7 R7 — Monthly ↔ Daily Reconciliation (APPROVED, permanent regression contract)

For each strategy/version and completed month: Q93 completed_trade_count == Σ(Q92 daily counts); Q93 gross_realized_pnl == Σ(Q92 daily gross); Q93 total_cost == Σ(Q92 daily costs); Q93 net_realized_pnl == Σ(Q92 daily net). Exact Decimal equality.

### 124.8 Publication Mechanics (binding implementation note)

Publication reuses the established reporting conventions (exclusive claim, staging + fsync + atomic replace, deterministic content-derived identity, PUBLISHED/ALREADY_PUBLISHED outcomes, conflict fails closed) without modifying the frozen backtest `ReportWriter` contract. The destination directory is explicitly caller-supplied (OD-Y convention); if a month rollover fires without a supplied destination the runtime fails closed rather than silently skipping mandatory Q92/Q93 evidence.

---

## 125. Phase 6 Slice 3 — Compatibility & Monotonicity Ruling: Q93 State Contract v1 (APPROVED)

**Status:** OWNER APPROVED (Slice-3 compatibility ruling). Append-only record; §123 and §124 remain in force.

### 125.1 C1 — Q93 Contract Version (APPROVED)

The existing generic `paper_metadata` facility carries an additive key:

`q93_contract_version = "sentinelx-q93-state/v1"`

No new table, no DDL, no migration; `SCHEMA_VERSION` remains 7.

### 125.2 C2 — Existing V7 Database Compatibility (APPROVED)

An EXISTING Schema-V7 paper database/session that predates the Q93 contract (i.e., lacks `q93_contract_version`) MUST NOT be silently upgraded. Opening such a database under Q93-enabled code fails closed as an incompatible Q93 reporting contract and requires a fresh paper session/database. No backfill, no inference of historical Q93 state.

### 125.3 C3 — Fresh Q93 Database (APPROVED)

A genuinely fresh database/session created under Q93-enabled code records `q93_contract_version = "sentinelx-q93-state/v1"` during the existing bootstrap path (additive paper_metadata key only). The observation marker `q93_last_observed_ist_month` is NOT written at creation time.

### 125.4 C4 — No Historical Inference (APPROVED)

Historical Q93 month state is never reconstructed or guessed from audit_events, broker watermarks, strategy watermarks, filesystem timestamps, existing report filenames, wall clock, `datetime.now()`, or `time.time()`.

### 125.5 C5 — Valid Session Marker Semantics (APPROVED)

Inside a valid `sentinelx-q93-state/v1` session, `q93_last_observed_ist_month` may be missing only before that session has accepted its first authoritative market/event time through the Q93-enabled contract; the first accepted event durably establishes the marker.

### 125.6 C6 — Monotonic Q93 Marker (APPROVED)

Allowed transitions: missing → M; M → M (idempotent); M → later month. Forbidden: any regression to an earlier month — such attempts fail closed at the durable store itself inside the same exclusive transaction (caller discipline is insufficient). A regression attempt does NOT mark a valid database corrupted; it raises the narrow Q93 regression error and leaves durable data untouched.

### 125.7 C7 — Preservation (APPROVED)

Still locked: SCHEMA_VERSION = 7; no migration; no q93_state table; no second reporting store; no audit-event reporting authority; no promotion-tracking dependency.

---

## 126. Phase 6 Slice 4 — Owner Rulings: Q89 Scope and Log Retention (APPROVED)

**Status:** OWNER APPROVED (Slice-4 owner rulings). Append-only record; §123–§125 text is unchanged and remains in force. These rulings bind the Q88/Q89/Q90 file-sink implementation on top of §123.2/§123.3(d)/§123.6/§123.7.

### 126.1 OD-A — Q89 Phase-6 Production Scope Is Paper/Live Only (APPROVED)

Phase-6 Slice-4 Q89 production wiring is **paper/live only**. The frozen backtest engine production execution remains untouched: no Q89 file sink is registered inside backtest execution, and existing backtest behavior is preserved exactly. Where no Q89 sink is registered — including all backtest execution — the pre-existing `engine/audit_log.py` structured application-log behavior remains the only effect, per §123.3(d)(6).

### 126.2 OD-B — Q88/Q89/Q90 Retention: Automatic Deletion Disabled (APPROVED)

For the Q88 trade log, Q89 error log and Q90 strategy evaluation log:

1. **Automatic deletion is DISABLED.** No numeric retention duration (days/months) is invented or configured.
2. Logs may ROTATE into bounded individual files/segments, but rotated evidence MUST NOT be automatically deleted or pruned. There is no finite backup-count pruning of historical rotated segments.
3. The §123.6(3) floors are satisfied structurally: with auto-deletion disabled, error-log retention covers the §114.13 evidence window and any promotion-evidence window by construction.
4. The audit SQLite journal and its derived export remain never-auto-deleted as previously frozen (§123.5, §123.6(3)).

### 126.3 Authoritative Marker

`PHASE_6_SLICE_4_OWNER_RULINGS_RECORDED`
`Q89_SCOPE: PAPER_LIVE_ONLY`
`LOG_AUTO_DELETE: DISABLED`
`NUMERIC_RETENTION_INVENTED: NO`

---

## 127. Phase 7 Slice 0 — Owner Decision Register: Broker-Independent Adapter Architecture + Deterministic Offline Mock/Sandbox Contract Only (APPROVED)

**Status:** OWNER APPROVED (Phase-7 pre-implementation review COMPLETE; OD-1 … OD-9 approved). Append-only record; no prior section is altered, renumbered, or rewritten, and §1–§126 remain in force. Slice 0 is a DOCS-ONLY contract freeze: **no production Python, no tests, no configuration, no persistence-schema change, no migration, no broker integration, no API keys/access tokens/credentials, no brokerage-account connection, and no order placement were created or modified by this recording step.** Nothing is committed or pushed by the recording session.

### 127.0 Decision Context and Scope Freeze (APPROVED)

Phase 6 (Logging / Audit) is VERIFIED_COMPLETE / OWNER_APPROVED (final independent milestone audit at HEAD `3e02102`; full suite 2266 passed, 0 skipped, 0 failures; P0 = 0, P1 = 0, P2 = 0, P3 = 2 documented non-blocking). The Phase-7 pre-implementation architecture/contract/scope review is COMPLETE, and the owner approved Phase 7 OD-1 … OD-9 with: Option A adapter-contained partial fills, mandatory fail-closed observability, adapter-only fill dedup, deterministic mock-only scope, and fail-closed reconciliation precedence.

**Phase 7 frozen scope:** BROKER-INDEPENDENT ADAPTER ARCHITECTURE + DETERMINISTIC OFFLINE MOCK/SANDBOX CONTRACT ONLY.

Phase 7 explicitly EXCLUDES: a real Zerodha adapter; real broker integration; API credentials; account login/authentication execution; external live order submission; real-money execution; broker-native protective orders; dashboard/UI; deployment; strategy changes; profitability changes; backtest redesign; Phase-6 redesign. A future real-provider adapter requires a separate owner-approved pre-implementation review before any such work starts.

### 127.1 OD-1 — Partial Fills: Option A, Adapter-Contained (APPROVED)

1. Existing SentinelX core lifecycle remains unchanged; `PARTIALLY_FILLED` is NOT added to `OrderLifecycleState`.
2. The adapter/mock boundary may generate, retain, deduplicate, and aggregate partial-fill fragments for adapter-contract testing.
3. Individual partial-fill fragments MUST NOT be projected into existing SentinelX core lifecycle/accounting.
4. While cumulative filled quantity remains below full order quantity: the canonical core lifecycle remains at its last valid state (normally QUEUED); no accounting mutation occurs from a fragment; no fabricated full fill occurs.
5. Only a supported terminal FULL FILL may be projected to the existing core full-fill path.
6. PARTIAL THEN TERMINAL NON-FULL CASE: if an order receives one or more partial fragments and then becomes CANCELLED, EXPIRED, or REJECTED before reaching full quantity, that sequence is unsupported for Phase-7 core projection. It MUST fail closed at the adapter/integration boundary. It MUST NOT fabricate a full fill, silently discard the exposure, mutate canonical accounting as if no partial occurred, or create a `PARTIALLY_FILLED` lifecycle state.
7. Full partial-fill accounting/lifecycle support requires a future separate owner-authorized contract.

### 127.2 OD-1 Binding Constraint — Defensive Bridge Fallback / Mandatory Fail-Closed Observability (APPROVED)

1. Normal Phase-7 contract: partial fragments never reach the core integration bridge. If a contract violation/bug nevertheless delivers an individual partial-fill fragment to the core bridge, the bridge MUST: reject it as `UNSUPPORTED_PARTIAL_FILL`; fail closed for the affected integration path; keep `OrderLifecycleState` at its last valid state; NOT mutate accounting; NOT fabricate FILLED; NOT silently ignore it; NOT add a new HALTED lifecycle state.
2. MANDATORY OBSERVABILITY: any `UNSUPPORTED_PARTIAL_FILL` contract violation reaching the bridge MUST emit explicit ERROR/CRITICAL operational evidence. That evidence is DIAGNOSTIC ONLY and MUST NOT become order-state authority, accounting authority, risk authority, or reconciliation authority. The affected integration path stays fail-closed until reconciled/cleared.
3. No new AuditEvent family/type is invented in Slice 0 unless an existing frozen contract already explicitly provides one. The implementation slice must select the correct existing Phase-6 logging/audit diagnostic surface while preserving E1–E21 authority (§127.13).

### 127.3 OD-2 — Broker Adapter Shape: Hybrid Boundary (APPROVED)

A HYBRID broker-independent boundary is frozen: (a) a callback/event path for broker/mock-initiated observations; plus (b) a synchronous query path for reconciliation/state inspection. Broker-specific API method names are NOT frozen. The core engine consumes SentinelX canonical types only; broker/provider-specific models remain inside the adapter boundary.

### 127.4 OD-3 — Idempotency: SentinelX-Owned Submission Identity (APPROVED)

`entry_intent_identity` remains the SentinelX-owned deterministic submission/dedup identity. No assumption is made that any external broker provides native idempotency. Phase-7 retry/idempotency behavior is MOCK-ONLY; a future real broker requires a provider-specific owner review before any submission-retry behavior is authorized.

### 127.5 OD-4 — Dual Order Identity (APPROVED)

SentinelX internal deterministic order identity remains authoritative. External/mock broker order identity is a separate opaque reference. A broker ID MUST NOT replace SentinelX internal order identity and MUST NOT become strategy/accounting authority. All fragments of one adapter order share the same SentinelX `order_id` and the same `broker_order_identity`; each fill fragment carries its own unique `broker_fill_id`. Existing SentinelX order identity is NOT switched to UUID.

### 127.6 Adapter-Only Fill Dedup Scope (APPROVED; bound to OD-4)

Fragment dedup identity = `(broker_order_identity, broker_fill_id)`. This identity applies ONLY inside the adapter/mock boundary and does NOT replace or alter existing SentinelX core order dedup, lifecycle identity, accounting identity, or reconciliation identity. Duplicate adapter fill fragments must not change deterministic aggregate results.

### 127.7 OD-5 — Protective Orders: SentinelX-Side Only (APPROVED)

Phase-7 protective behavior is SENTINELX-SIDE ONLY. Existing protective planning/evaluation remains authoritative. Broker-native stop/target projection is neither designed nor implemented in Phase 7 and is deferred to separate future owner authorization.

### 127.8 OD-6 — Retry: Deterministic Mock-Only Testing (APPROVED)

Retry state-machine work is DETERMINISTIC MOCK-ONLY TESTING; no real external submission retry is authorized. Mock tests may cover timeout, retryable transport error, rate-limit condition, retry attempt count, and idempotent duplicate prevention — software-contract simulations only.

### 127.9 OD-7 — Provider Scope (APPROVED)

Phase 7 implementation scope: broker-independent contracts; deterministic offline mock adapter; normalization; mock reconnect/reconciliation; mock idempotency/retry; integration/parity tests. Explicitly OUT OF SCOPE: Zerodha adapter implementation; Upstox order adapter implementation; any real broker order API; real credentials; external order placement.

### 127.10 OD-8 — Reconnect / Reconciliation Precedence Over Retry (APPROVED)

DISCONNECT suspends submission-retry activity. RECONNECT queries mock/broker-contract state and reconciles it against SentinelX-owned state. Clean, deterministically matched reconciliation permits the mock processing path to become eligible to continue. Mismatched, uncertain, incomplete, or unsupported reconciliation FAILS CLOSED / halts the affected integration path. No automatic external/live recovery is authorized; no submission retry may execute while reconnect/reconciliation safety is unresolved. ABSOLUTE PRECEDENCE: RECONNECT/RECONCILIATION SAFETY > RETRY LOGIC.

### 127.11 PaperReconciliationEngine Separation (APPROVED; binding boundary)

PaperReconciliationEngine remains PAPER-SPECIFIC and is NOT converted into a live-broker reconciliation engine. Phase 7 may reuse concepts, canonical types, and comparison semantics through a separate thin broker-contract/mock reconciliation boundary. No live-provider state is added into PaperReconciliationEngine during Phase 7.

### 127.12 OD-9 — Determinism / Reproducibility Contract (APPROVED)

MockBrokerAdapter MUST obey existing SentinelX reproducibility requirements: same canonical inputs + same scripted mock scenario + same event ordering + same canonical timestamps ⇒ same observable outputs and state transitions. Phase-7 mock correctness MUST NOT depend on uncontrolled randomness, system wall clock, random latency, nondeterministic thread scheduling, race-dependent correctness, or sleep()-based timing correctness. Timeouts, rate limits, disconnects, reconnects, duplicates, out-of-order events, and partial fragments must be driven by deterministic scripted scenarios. No probabilistic fault injection in Phase 7; any future probabilistic fault injection requires an explicit deterministic seed contract and owner approval.

### 127.13 Audit / Logging and Persistence Boundaries (binding)

1. The Phase-6 audit/logging architecture remains authoritative: NO second audit writer; NO invented reconciliation audit-event authority; E1–E21 NOT redesigned.
2. `UNSUPPORTED_PARTIAL_FILL` observability must reuse an appropriate existing diagnostic/logging path unless a separate owner decision is explicitly required later.
3. Slice 0 authorizes NO schema change. SCHEMA_VERSION remains 7. No schema 8, no new columns, tables, or migrations. Any implementation finding that genuinely requires persistence changes must STOP and return OWNER_DECISION_REQUIRED before modifying schema.

### 127.14 Corrected Six-Slice Plan (APPROVED)

The pre-implementation review's five-slice count is corrected. **PROPOSED_PHASE_7_SLICE_COUNT = 6**, Slices 0 through 5:

| Slice | Content |
| --- | --- |
| 0 | Owner decisions + architecture/contract freeze (this register; docs-only) |
| 1 | Broker-independent interfaces/types |
| 2 | Deterministic offline MockBrokerAdapter |
| 3 | Order identity / status / fill normalization |
| 4 | Mock disconnect/reconnect + reconciliation + dedup/idempotency behavior |
| 5 | Integration/parity tests + final Phase-7 audit |

The incorrect previous value 5 is superseded by 6 and is not preserved anywhere as current.

### 127.15 Build-Order vs Frozen-Requirements Numbering Equivalence (documentation note only)

`requirements-freeze-125.md` preserves its own historical numbering and is deliberately NOT edited by this freeze. Build-order **Phase 7 (Zerodha Live / broker adapters)** corresponds in capability terms primarily to freeze-doc "**Phase 7 - Order Management**" requirements Q71–Q77 (broker-independent interface abstraction; v1 Zerodha-only scope with add-later interface; position reconciliation), together with the live-safety/state-persistence obligations referenced therein (freeze Phases 8 / 8.5) that remain gated behind their own future authorizations. This equivalence note documents build-order ↔ freeze-doc correspondence only; no frozen requirement text is renumbered or rewritten.

### 127.16 Supersession Register

None. §127 alters no prior owner ruling; §1–§126 remain in force unchanged (append-only record).

### 127.17 Authoritative Marker

`PHASE_7_SLICE_0_CONTRACT_FREEZE_RECORDED`
`PARTIAL_FILL_OPTION_A_ADAPTER_CONTAINED`
`UNSUPPORTED_PARTIAL_FILL_FAIL_CLOSED_OBSERVABILITY`
`ADAPTER_ONLY_FILL_DEDUP_BROKER_ORDER_IDENTITY_X_BROKER_FILL_ID`
`RECONCILIATION_SAFETY_OVER_RETRY`
`DETERMINISTIC_MOCK_ONLY_SCOPE`
`PAPER_RECONCILIATION_ENGINE_STAYS_PAPER_SPECIFIC`
`PROPOSED_PHASE_7_SLICE_COUNT = 6`
`REAL_BROKER_ADAPTER_IN_SCOPE: NO`
`SCHEMA_VERSION: 7 (UNCHANGED)`

---

## 128. Phase 8 Slice 0 — Owner Decision Register: Live Safety / Recovery Contract Hardening (APPROVED)

**Status:** OWNER APPROVED (Phase-8 pre-implementation review COMPLETE; OD-1 … OD-9 approved). Append-only record; no prior section is altered, renumbered, or rewritten, and §1–§127 remain in force. `requirements-freeze-125.md` is NOT edited by this freeze. Slice 0 is a DOCS-ONLY contract freeze: **no production Python, no tests, no configuration, no persistence-schema change, and no migration were created or modified by this recording step.** No real broker API, credentials, account connection, external order placement, real-money execution, or Telegram/SMS/email network delivery is authorized or implemented. Nothing is committed or pushed by the recording session.

### 128.0 Decision Context and Phase-8 Scope Freeze (APPROVED)

Phase 7 (broker-independent adapter architecture + deterministic offline mock) is VERIFIED_COMPLETE / OWNER_APPROVED. The Phase-8 pre-implementation review is COMPLETE, and the owner approved OD-1 … OD-9 below.

**Build-order Phase 8 frozen scope:** LIVE SAFETY / RECOVERY CONTRACT HARDENING using deterministic offline/mock/local behavior only.

Phase 8 builds on the EXISTING safety architecture — `SafetyManager`, `SafetyState`, `KillSwitchState`, `LivePaperCoordinator` safety gates, `LiveStrategyCoordinator` strategy-halt isolation, `StrategyHaltError`, reconciliation health, Phase-6 audit/logging, and Phase-7 broker/mock contracts — and must NOT reinvent it.

Phase 8 explicitly EXCLUDES: real broker API; real provider adapter work; credentials/tokens; real account connection; external order execution; broker-native protective orders; dashboard/UI; deployment; strategy/profitability changes; backtest redesign; schema migration; real Telegram/SMS/email delivery.

### 128.1 OD-1 — Auto-Halt Scope Matrix (APPROVED)

MAX DAILY LOSS ⇒ GLOBAL kill switch. AUTHORITATIVE RECONCILIATION FAILED ⇒ GLOBAL kill switch. ISOLATED STRATEGY EXCEPTION ⇒ the affected strategy only is halted. Each isolated strategy exception increments the canonical Phase-8 per-session error count; when that count reaches the §128.3 (OD-3) threshold ⇒ GLOBAL kill switch. The FIRST isolated strategy exception does NOT globally halt all strategies.

### 128.2 OD-2 — Disconnect Safety and Manual-Review Recovery (APPROVED)

Disconnect immediately blocks global submissions. Existing DISCONNECTED safety semantics may be reused, but a disconnect that fires a safety alert creates a manual-review requirement. Reconnect alone MUST NOT restore submission eligibility. Recovery requires ALL of: connectivity healthy; required fresh market evidence; reconciliation resolved cleanly where applicable; every other applicable safety prerequisite healthy; AND explicit human/operator resume. Connectivity restoration alone never auto-resumes anything.

### 128.3 OD-3 — One Configurable Per-Session Strategy-Error Threshold (APPROVED)

Exactly ONE configurable positive PER-SESSION strategy-error threshold is frozen — the same threshold referenced by OD-1. No second error-threshold config exists. No wall-clock rolling window in Phase 8. Conceptual flow: isolated StrategyHaltError ⇒ affected-strategy halt ⇒ increment session error count; count < threshold ⇒ only the affected strategy remains halted; count reaches threshold ⇒ global kill switch. NO numeric default is invented in Slice 0: any implementation/config default not already frozen must return OWNER_DECISION_REQUIRED before being invented.

### 128.4 OD-4 — Reconciliation FAILED = Immediate Global Kill Switch (APPROVED)

The first authoritative `ReconciliationHealth.FAILED` triggers an IMMEDIATE GLOBAL kill switch. There is no N-failure grace counter. Reconciliation evidence remains the reconciliation authority; audit/log evidence is observational and MUST NOT become reconciliation authority.

### 128.5 OD-5 — Halt Scope Consolidation (APPROVED)

Per-strategy scope: isolated strategy exception; attributable strategy-specific protective invariant failure. Global scope: max daily loss; reconciliation FAILED; OD-3 error threshold reached; ambiguous/integrity-threatening protective failure; existing persistence/integrity failures according to current authority. An isolated strategy-specific fault NEVER causes an unnecessary global halt.

### 128.6 OD-6 — Universal Affected-Scope Manual Resume; Independent Latches (APPROVED)

Manual resume applies to ANY safety halt at the affected scope. GLOBAL HALT requires explicit human/operator global resume. PER-STRATEGY HALT requires explicit human/operator resume for that strategy. Becoming healthy establishes RESUME ELIGIBILITY only; health becoming clean MUST NOT automatically clear a halt; there is NO automatically self-clearing safety halt. Unaffected strategies may continue while only one strategy is halted, provided no global safety condition is active. Global and per-strategy latches are INDEPENDENT: clearing a strategy halt does not clear the global kill switch, and a global resume does not silently clear unresolved per-strategy halts.

### 128.7 Unified Global Manual-Review Gate (binding)

Global safety uses ONE canonical global manual-review gate / kill-switch authority — a separate persisted boolean latch per global cause is PROHIBITED. Each distinct safety cause must be independently observable, independently become healthy/resolved, and remain represented by its canonical authority. Resolving one cause MUST NOT permit resume while another applicable global safety prerequisite remains unsafe. Explicit operator resume succeeds only after ALL currently applicable global safety prerequisites are clean. Example: disconnect + reconciliation FAILED — clearing the disconnect alone ≠ resume; reconciliation must also become clean, and explicit operator resume is still then required.

### 128.8 Durable Per-Strategy Halt Latch + Restart Contract (binding correction)

Targeted persistence review established the CURRENT state: `strategy_halt._halted` is in-memory only, and `LiveStrategyCoordinator._halted_owners` is in-memory only — neither survives restart. Frozen Phase-8 correction:

1. The per-strategy safety halt/manual-resume latch IS durable safety-gating state and MUST survive process restart.
2. `LiveStrategyCoordinator._halted_owners` remains the RUNTIME strategy-gating authority.
3. Persisted strategy halt state MUST be hydrated BEFORE strategy evaluation or submission becomes eligible after restart.
4. Restart MUST NOT silently clear a strategy safety halt.
5. `strategy_halt._halted` remains EPHEMERAL short-lived control-flow state and is NOT durable authority.

Restart sequence: load global safety state (already durable under existing safety-state persistence) → hydrate durable per-strategy halt owners → restore other canonical safety prerequisites → block affected scopes → NO automatic resume → explicit operator action required after prerequisites become healthy.

### 128.9 Existing paper_metadata Reuse + Canonical Structured Serialization (binding)

Per-strategy durable halt state uses the EXISTING `paper_metadata` key/value facility: NO new table, NO new column, NO SCHEMA_VERSION change, NO migration. Contract version concept: `halt_contract_version = sentinelx-halt-state/v1`. State concept: `halted_strategy_owners` as canonical deterministic structured serialization of owner records conceptually equivalent to `[{"strategy_id": "...", "strategy_version": "..."}]` with deterministic lexical canonical ordering. Ambiguous colon-concatenated strings such as `strategy_id:strategy_version` are PROHIBITED. The repository's existing canonical codec OWNS serialization where one exists; no arbitrary JSON encoder is prescribed over it.

### 128.10 Halt Persistence Authority Semantics (binding)

Per-strategy halt state is operational SAFETY-GATING authority — it must NOT be described or implemented as mere observational/audit state. Audit/log evidence remains observational. Persistence must be atomic, fail closed on authoritative write failure, preserve deterministic owner identity, and hydrate before strategy eligibility. `audit_only_transaction` must NOT be blindly reused merely because Q93 used it: the implementation must use persistence transaction semantics legally appropriate for authoritative operational safety state. If current persistence APIs cannot provide this safely without schema/authority changes, implementation STOPs with OWNER_DECISION_REQUIRED before Slice 1.

### 128.11 OD-7 — Heartbeat / Stale-Data Threshold Reuse (APPROVED)

The EXISTING `heartbeat_timeout_seconds` config key is reused; NO second timeout key is created and NO numeric default is invented. If explicitly configured to a valid positive value, it is the deterministic heartbeat/stale-data threshold. If unset/null, the existing connection/fresh-market-evidence authority remains in force and no hidden arbitrary timeout is assumed. Heartbeat/staleness correctness uses deterministic canonical timing authority: no sleep()-based correctness, no uncontrolled wall-clock test authority. A heartbeat/stale-data safety alert requires manual review before resume.

### 128.12 OD-8 — Protective Inconsistency Scope Model (APPROVED)

If a protective invariant failure is clearly attributable to ONE strategy and does NOT create broader accounting/integrity ambiguity ⇒ halt the affected strategy, emit safety evidence, require explicit human resume for that strategy. If ownership is ambiguous OR integrity/accounting safety cannot be proven ⇒ GLOBAL fail closed / kill switch. Protective logic remains SentinelX-side; no broker-native protection authority.

### 128.13 OD-9 — Alert Transport Scope: Local/Mock Contract Now; Network Transports Deferred (APPROVED)

Frozen requirements mention Telegram/SMS/email alerts. Build-order Phase-8 implementation scope is deliberately narrower: implement/freeze the broker-independent/local `SafetyAlert` contract, deterministic mock/local alert sink(s), alert routing/dispatch contract, severity/source/reason/context validation, deterministic tests, and mandatory redaction. DO NOT implement Telegram/SMS/email network transports, external webhooks, or API credentials/tokens. Real external alert transports require a separate owner-authorized integration step. Historical frozen requirements retaining their future Telegram/SMS/email requirement are preserved UNCHANGED — this is documented as implementation-scope deferral/equivalence, NOT requirements deletion.

### 128.14 Alert → Human Review Rule (binding)

Any safety alert associated with a safety halt creates a human-review requirement before the affected scope may resume. Alert evidence itself is NOT safety-state authority; the underlying safety controller/latch IS the authority. No alert may automatically clear a halt.

### 128.15 Safety Precedence (binding preservation)

Conceptual precedence: SAFETY HALT > RECONCILIATION SAFETY > RETRY > NEW SUBMISSION. Existing more-specific SafetyState precedence remains authoritative, including persistence-failure and integrity-failure precedence. The existing RiskGate is NOT weakened: a safety halt is an ADDITIONAL outer blocking condition, and a RiskGate approval can never bypass a safety halt.

### 128.16 Schema / Config Verdict (binding)

SCHEMA_VERSION = **7**. NEW TABLE = NO. NEW COLUMN = NO. MIGRATION = NO. Existing `paper_metadata` is reused for per-strategy halt safety state. Config impact: reuse `heartbeat_timeout_seconds`; the single OD-3 per-session error-threshold count may require config authority through the established configuration contract; NO second error threshold; NO arbitrary numeric defaults. Any implementation need for another config key/default not frozen here returns OWNER_DECISION_REQUIRED.

### 128.17 Existing Surfaces Preserved (binding)

NOT redesigned in Phase 8: `SafetyManager`; `SafetyState`; `KillSwitchState`; `LivePaperCoordinator`; `LiveStrategyCoordinator`; `StrategyHaltError`; `PaperReconciliationEngine` (remains paper-specific); Phase-6 audit/logging; Phase-7 broker adapter/mock contracts; RiskGate; protective authority. No second reconciliation authority is created.

### 128.18 Phase-8 Six-Slice Plan (APPROVED)

**PHASE_8_SLICE_COUNT = 6**, Slices 0 through 5:

| Slice | Content |
| --- | --- |
| 0 | Owner decisions + §128 architecture/contract freeze (this register; docs-only) |
| 1 | Safety controller / auto-halt bridges + durable per-strategy halt persistence |
| 2 | Deterministic heartbeat / stale-data safety |
| 3 | SafetyAlert routing + deterministic mock/local sinks |
| 4 | Recovery/restart/protective integration |
| 5 | Parity / comprehensive regression / final audit checkpoint |

### 128.19 Supersession Register

None. §128 alters no prior owner ruling; §1–§127 remain in force unchanged (append-only record).

### 128.20 Authoritative Marker

`PHASE_8_SLICE_0_CONTRACT_FREEZE_RECORDED`
`AUTO_HALT_SCOPE_MATRIX_FROZEN`
`DISCONNECT_MANUAL_REVIEW_RECOVERY`
`SINGLE_PER_SESSION_ERROR_THRESHOLD_NO_DEFAULT`
`RECONCILIATION_FAILED_IMMEDIATE_GLOBAL_KILL_SWITCH`
`UNIVERSAL_AFFECTED_SCOPE_MANUAL_RESUME`
`UNIFIED_GLOBAL_MANUAL_REVIEW_GATE`
`PER_STRATEGY_HALT_LATCH_DURABLE`
`HALT_CONTRACT_VERSION: sentinelx-halt-state/v1`
`STRATEGY_HALT_MODULE_STATE_EPHEMERAL`
`HEARTBEAT_TIMEOUT_SECONDS_REUSED_NO_DEFAULT`
`MOCK_LOCAL_ALERT_TRANSPORT_ONLY`
`SAFETY_PRECEDENCE_HALT_OVER_RECONCILIATION_OVER_RETRY_OVER_SUBMISSION`
`PHASE_8_SLICE_COUNT = 6`
`SCHEMA_VERSION: 7 (UNCHANGED)`

## 129. Phase 8.5 Slice 0 — Owner Decision Register: Historical Data Automation Contract Freeze (APPROVED)

**Status:** OWNER APPROVED (Phase-8.5 pre-implementation audit COMPLETE; OD-A … OD-H approved). Append-only record; no prior section is altered, renumbered, or rewritten, and §1–§128 remain in force. `requirements-freeze-125.md` is NOT edited by this freeze. Slice 0 is a DOCS-ONLY contract freeze: **no production Python, no tests, no configuration, no persistence-schema change, no `.gitignore` change, no historical dataset download, and NO NSE or other outbound network request were created, modified, or performed by this recording step.** Nothing is committed or pushed by the recording session.

### 129.0 Decision Context and Phase-8.5 Identity Freeze (APPROVED)

Phase 8 (Live Safety / Recovery Contract Hardening) is VERIFIED_COMPLETE / OWNER_APPROVED. The historical-data pre-implementation audit is COMPLETE, and the owner has APPROVED the Data Automation decisions OD-A … OD-H below.

This milestone is frozen as:

> **PHASE 8.5 — HISTORICAL DATA AUTOMATION**

It MUST NOT be called Phase 9. **Phase 9 remains reserved** for the future dashboard/security work.

Phase 8.5 purpose boundaries: source-acquisition boundary; manual-drop ingestion; raw evidence preservation; source-format versioning; manifest/checksum/idempotency; data-gap handling; and a future **authorized** acquisition adapter boundary. Phase 8.5 authorizes NO network acquisition in any form (see §129.2).

### 129.1 Existing Ingestion Authority Reuse (binding)

The acquisition layer is **NOT a second importer**. The canonical flow is frozen:

```
SOURCE ACQUISITION
        ↓
data/incoming/
        ↓
existing SentinelX importer/orchestrator
        ↓
existing cleaning/validation
        ↓
existing canonical StorageLayout/v2
        ↓
HistoricalDataFeed / ReplayFeed / Backtest
```

Existing authorities remain authoritative for: discovery (`importer_discovery.py`), filename/content detection (`importer_detection.py`), run identity (`claim_import_run`), canonical pathing (`StorageLayout/v2` via `importer_storage.py`), validation/cleaning (`ingestion.py`, `data_cleaning.py`), normalization, gap handling (`gap_handler.py`), quarantine, import reporting (`importer_reporting.py` manifests), reproducibility identity (`engine/reproducibility/*`), and fail-closed filesystem safety (`path_safety.py`, `canonical_lock.py`). Any new acquisition system MUST FEED these authorities rather than duplicate them. Creating a competing discovery/detection/storage/reporting tree is prohibited.

### 129.2 OD-A — External Data Acquisition Authorization: Engineering Compliance Risk, FAIL CLOSED (APPROVED)

SentinelX does NOT make a legal determination about NSE licensing or Terms of Use. The identified terms/licensing issue is treated strictly as an **engineering compliance risk**. Therefore SentinelX MUST **FAIL CLOSED**: until (a) written authorization, (b) an applicable licensed-data arrangement, or (c) another owner-approved legally permitted source is independently confirmed, SentinelX MUST NOT perform programmatic network acquisition from NSE. This is risk-control architecture, NOT legal advice. Before production/commercial use that relies on automated NSE data acquisition, applicable permissions/licensing must be independently verified. Network scheduling remains unauthorized until OD-A is superseded by a new explicit owner ruling (see §129.10).

### 129.3 Manual Download vs Programmatic Fetch Boundary (binding)

MANUAL DOWNLOAD means: a human individually uses the official NSE website/interface to obtain each file.

Allowed current workflow:

```
human opens official NSE site
→ human downloads file
→ file saved locally
→ file placed into data/incoming/
→ SentinelX automatically processes LOCAL file only
```

NOT authorized: a human running a Python downloader; a PowerShell downloader; a program that sends NSE HTTP requests; browser automation; CLI fetchers; HTTP clients; scheduled tasks; cron jobs; bots; scrapers; programmatic download scripts. **A human manually launching software that itself fetches the file is STILL programmatic acquisition.** The authorization boundary is based on WHO/WHAT PERFORMS THE FETCH, not merely who initiates execution.

### 129.4 Future Network Adapter — Dormant, Disabled By Default (binding)

Any future network-acquisition adapter MUST remain DISABLED BY DEFAULT and MUST be unreachable from normal SentinelX runtime configuration until a NEW explicit owner ruling authorizes the source. Enabling a network source requires recorded evidence of authorization such as applicable written permission, an approved licensed-data-provider arrangement, or another independently verified lawful source arrangement. The following are NOT sufficient authorization: code exists; tests pass; endpoint works; public URL exists; operator manually clicks "run". An unsupported or unauthorized source FAILS CLOSED **BEFORE ANY OUTBOUND NETWORK REQUEST**.

### 129.5 OD-B — EOD First (APPROVED)

Phase 8.5 V1 is EOD/daily historical data first. Targets: NIFTY index EOD; NIFTY F&O EOD; NIFTY CE EOD; NIFTY PE EOD. Historical 1m/5m/tick acquisition is DEFERRED. No daily/EOD file may ever be converted or represented as genuine intraday candles. Intraday requires its own proven lawful/reliable source later.

### 129.6 OD-C — Coverage Claims Discipline (APPROVED)

Do NOT claim arbitrary historical depth. The current verified hard baseline: **F&O UDiFF format — 08-Jul-2024 onward is the verified format-era baseline** established by the pre-implementation audit. Older history is supported conceptually through legacy/backfill handling, but the exact retrievable floor remains **NOT_PROVEN** until separately verified. The NIFTY index base date MUST NOT be presented as guaranteed downloadable coverage. No "20 years available" claim without evidence.

### 129.7 OD-D — Future Authorized Acquisition Model: HYBRID (APPROVED)

Future authorized acquisition preference is HYBRID. Primary: the daily complete F&O archive / UDiFF file — one daily source file can represent the full derivatives universe deterministically. Backfill: contract-wise historical archives where required for older/deeper NIFTY options coverage. This is architecture preference ONLY. NO network acquisition is authorized in Slice 0 (or any slice, absent a superseding ruling).

### 129.8 OD-E — Data Root Policy (APPROVED)

The current operational root remains the existing repository `data/` root. Data MUST NOT be moved during Slice 0. Future architecture MUST allow a configurable external data root (e.g. `D:\SentinelXData` or VPS persistent storage). Because existing code retains `Path("data")` assumptions (e.g. `CANONICAL_STORAGE_ROOT`, `IMPORT_REPORT_ROOT`, `HistoricalDataFeed` legacy paths), relocation implementation is DEFERRED to a later Phase-8.5 slice. No config change now.

### 129.9 OD-F — Raw Source Evidence Immutability (APPROVED)

Original downloaded/source file bytes are IMMUTABLE EVIDENCE. For manually acquired files: original file → preserved unchanged. Original source bytes are NEVER rewritten during normalization. Normalized canonical data remains separately produced by the existing SentinelX ingestion/storage authority (§129.1). V1 retention rule: preserve original source evidence. Compression optimization may occur later ONLY without destroying source provenance.

### 129.10 OD-G — Update Schedule Boundary (APPROVED)

There is NO scheduled NSE network updater, NO startup network downloader, and NO daily programmatic NSE fetch. Current automation begins ONLY AFTER a local file is available: `data/incoming/` → automatic detection/import/validation. Network scheduling remains unauthorized until OD-A (§129.2) is superseded by a new explicit owner ruling.

### 129.11 OD-H — Revised Source Files / Supersession Evidence (APPROVED)

Never silently overwrite previously accepted source evidence. If a historically published source file changes: preserve original evidence; preserve new evidence; checksum both; record the supersession relationship; deterministically determine which version is canonical; NEVER erase history silently.

### 129.12 Storage Layout Extension (binding)

Preserve the existing frozen layout and extend minimally. Current authority includes `data/incoming/`, `data/parquet/`, `data/quarantine/`, `data/import_reports/`, `data/state/`, `data/snapshots/` (consistent with `PROJECT_STRUCTURE.md`, which already reserves `data/raw/` for untouched source dumps). Phase 8.5 may introduce `data/raw/` and `data/manifests/` ONLY if consistent with existing path/storage authority and its fail-closed path-safety contracts. Conceptual raw layout:

```
data/raw/
    nse/
        indices/
        derivatives/
```

A competing normalized tree MUST NOT be created. Canonical normalized output MUST remain through StorageLayout/v2 (`data/parquet/{market}/…` per the one resolver rule).

### 129.13 Acquisition Manifest Contract (binding)

Deterministic acquisition/import manifests are REQUIRED. At minimum, manifest identity/evidence captures: source identity; dataset identity; source filename; source format/version; trading date or covered range; checksum; acquisition mode; import status; normalization/import version where applicable; and supersession evidence where applicable. The manifest is NOT a replacement for reproducibility fingerprints. `CanonicalCodec` and the existing importer identity/reporting authority own serialization and identity.

### 129.14 Source-Format Versioning and Detection Fail-Closed (binding)

Source-format handling is explicit and versioned. Minimum recognized format concepts: `FO_UDIFF_V1`; `FO_BHAVCOPY_LEGACY`. Unknown/unrecognized format: DO NOT GUESS → QUARANTINE → FAIL CLOSED. The 08-Jul-2024 boundary may be recorded as format-era evidence, but parser selection MUST validate the actual schema/header rather than blindly trust the date alone.

### 129.15 Dataset Identity (binding)

Use structured canonical identity. For INDEX data include applicable fields: exchange; segment; instrument/index; trade_date; granularity; source_format_version. For OPTIONS include applicable fields: exchange; segment; underlying; instrument; expiry; strike; option_type; trade_date; granularity; source_format_version. Ambiguous string concatenation is PROHIBITED. The existing `CanonicalIdentity` / `CanonicalCodec` fingerprint authority remains canonical.

### 129.16 Idempotency Contract (binding)

Same source file + same checksum ⇒ NO duplicate acquisition/import publication. Missing local file ⇒ await acquisition. Corrupt local file ⇒ quarantine. Source content unexpectedly changes ⇒ preserve evidence; never silently overwrite canonical history (§129.11). Duplicate rows ⇒ existing canonical ingestion rules apply. NO partial canonical publication.

### 129.17 Gap Handling Reuse (binding)

Reuse the existing gap/calendar authority. Weekends and holidays are NEVER treated as missing-data errors. For derivatives/options, distinguish where possible: contract not yet listed; contract expired; no trading; source file unavailable; actual missing trading-session evidence. Never fabricate unflagged data (existing `is_gap_filled` / `signal_eligible` flags and §83/D3a no-synthetic-bars authority remain in force).

### 129.18 Git Bulk-Data Exclusion Requirement (recorded implementation work)

Historical bulk market data MUST NOT enter Git history. Future implementation MUST update `.gitignore` appropriately for: raw historical archives; bulk normalized/parquet datasets; temporary downloads; cache; and quarantine payloads. Small deterministic test fixtures may remain tracked. `.gitignore` is NOT modified in this Slice 0 (docs-only scope). This is recorded as REQUIRED IMPLEMENTATION WORK for a subsequent slice.

### 129.19 Failure Model — Fail Safe, Never Destroy Valid History (binding)

For future acquisition/import: network failure; source unavailable; rate limit; HTML instead of an expected data file; truncated ZIP; checksum mismatch; unknown format; invalid rows; duplicate rows; disk full; permission failure — NONE of these may EVER delete or corrupt existing valid historical data. Bad new payload ⇒ quarantine / fail safely. No partial canonical publication.

### 129.20 Real-Time / Live-Feed Boundary (binding)

Historical acquisition remains SEPARATE from live-feed authority. Do NOT contaminate `engine/feeds/upstox/*`, live_feed, or subscription authority with bulk historical source acquisition. Recommended future boundary: `data_acquisition/` → `data/incoming/`; live-feed provider code remains independent.

### 129.21 Backtest Compatibility (binding)

The acquisition layer adapts source data TO existing SentinelX canonical contracts. BacktestEngine, HistoricalDataFeed, HistoricalReplayFeed, the Option catalog, and canonical OHLC contracts are NOT redesigned merely because NSE raw schemas differ.

### 129.22 Schema / Config Verdict (binding)

SCHEMA CHANGE REQUIRED = **NO**. No new SQLite table is required merely for historical-file acquisition. CONFIG CHANGE REQUIRED = **TBD**, deferred to future data-root/source-authorization work. SCHEMA_VERSION remains **7**. Slice 0 makes NO schema or configuration changes.

### 129.23 Phase-8.5 Eight-Slice Plan (APPROVED)

**PHASE_8_5_SLICE_COUNT = 8**, Slices 0 through 7:

| Slice | Content |
| --- | --- |
| 0 | Source/compliance-risk/storage/owner contract freeze (this register; docs-only) |
| 1 | Offline acquisition contracts + manifest/checksum/idempotency core |
| 2 | NIFTY index local-source adapter / ingestion wiring |
| 3 | F&O archive local-source handling + legacy/UDiFF format detection |
| 4 | NIFTY CE/PE extraction + contract-wise historical backfill ingestion |
| 5 | Gap detection + incremental LOCAL update processing |
| 6 | Data-root abstraction + replay/backtest compatibility |
| 7 | Parity / comprehensive regression / independent audit checkpoint |

Slices 1–7 MUST remain offline/fixture/manual-local-file driven unless a future owner ruling supersedes OD-A. No slice may silently introduce NSE network acquisition. Slices 1–7 are NOT STARTED / NOT AUTHORIZED.

### 129.24 Supersession Register

None. §129 alters no prior owner ruling; §1–§128 remain in force unchanged (append-only record).

### 129.25 Authoritative Marker

`PHASE_8_5_DATA_AUTOMATION_SLICE_0_CONTRACT_FREEZE_RECORDED`
`PHASE_8_5_IDENTITY_FROZEN`
`NSE_NETWORK_ACQUISITION_NOT_AUTHORIZED_FAIL_CLOSED`
`MANUAL_VS_PROGRAMMATIC_FETCH_BOUNDARY_FROZEN`
`FUTURE_NETWORK_ADAPTER_DISABLED_BY_DEFAULT`
`EOD_FIRST_INTRADAY_DEFERRED`
`UDIFF_FORMAT_ERA_BASELINE_2024_07_08_RECORDED_COVERAGE_FLOOR_NOT_PROVEN`
`HYBRID_FUTURE_ACQUISITION_MODEL_FROZEN`
`RAW_SOURCE_EVIDENCE_IMMUTABLE`
`ACQUISITION_MANIFEST_REQUIRED`
`UNKNOWN_SOURCE_FORMAT_QUARANTINE_FAIL_CLOSED`
`BULK_DATA_GIT_EXCLUSION_REQUIRED`
`EXISTING_IMPORTER_AUTHORITY_REUSED_NO_SECOND_IMPORTER`
`PHASE_8_5_SLICE_COUNT = 8`
`SCHEMA_VERSION: 7 (UNCHANGED)`

---

## 130. Phase 8 Safety Repair — Independent Audit Finding, Bounded Production-Wiring Repair, and Formal Closure Documentation

**Status:** DOCUMENTATION ONLY — NO PRODUCTION CODE CHANGES, NO TEST CHANGES, NO PHASE 8.5 IMPLEMENTATION.

**Date:** 2026-08-24

**Context:** Following the Phase 8 owner-closure at HEAD `23b50d8` (final independent audit accepted; full suite 2554 passed, 0 skipped, 0 failures), and the subsequent M1–M11 structural migration (finalized at `01a9fc6`), a post-structural-migration independent full audit was performed. This audit identified two PRE-EXISTING production-wiring defects in `LivePaperTradingRunner` that were present before and independent of the structural migration.

### 130.1 F-SAFETY-01 — P0 — Strategy Halt Bridge Not Wired in Production Runner

**Finding:** `LivePaperTradingRunner` did not wire `initial_halted_owners` or `strategy_halt_bridge` into the actual production `LiveStrategyCoordinator` construction path.

**Consequences before repair:**
- Durable strategy halts were not hydrated into the runtime strategy-entry latch during production-runner restart.
- New runtime strategy halts were not persisted through the production strategy-halt bridge.
- This violated the frozen restart invariant: restart must never silently clear a strategy halt.

**Repair status:** CLOSED at commit `043ca15`.

### 130.2 F-SAFETY-02 — P1 — Phase8SafetyController Not Wired in Production Runner

**Finding:** `LivePaperTradingRunner` did not instantiate or wire the existing `Phase8SafetyController` into the actual `LivePaperCoordinator` production path.

**Consequences before repair:**
- Existing Phase-8 automatic escalation bridges existed at component level.
- But the real runner-created coordinator did not activate them.

**Repair status:** CLOSED at commit `043ca15`.

### 130.3 Repair Checkpoint — Commit `043ca15`

**Commit:** `043ca15 Repair Phase 8 production safety wiring`

**Repair characteristics (all verified):**
- Production wiring only — no second runtime strategy halt latch
- No second global kill switch
- No persistence schema change; `SCHEMA_VERSION` remains 7
- No risk calculation change; no order/execution change
- No protective behavior change; no strategy business logic change
- No structural migration change

**F-SAFETY-01 repair (CLOSED):**
The actual production runner now:
- Loads durable halted strategy owners
- Hydrates `LiveStrategyCoordinator` before strategy eligibility
- Wires the existing `strategy_halt_bridge`
- Persists new runtime strategy halts through the existing durable store

`LiveStrategyCoordinator._halted_owners` remains the sole runtime strategy-entry gating authority.

**F-SAFETY-02 repair (CLOSED):**
The actual production runner now wires the existing `Phase8SafetyController` into `LivePaperCoordinator`.

Verified actual coordinator bridge paths include:
- Authoritative RiskGate daily-loss rejection → `LivePaperCoordinator` bridge → `Phase8SafetyController` → existing canonical global kill switch
- First reconciliation FAILED → `LivePaperCoordinator` bridge → `Phase8SafetyController` → existing canonical global kill switch

### 130.4 Regression Evidence

| Milestone | Test Count |
| --- | --- |
| Previous suite (pre-repair) | 2554 passed |
| After initial production-wiring repair | 2560 passed |
| After adding actual coordinator-bridge regression proofs | 2562 passed |
| **Final verification** | **2562 passed, 0 skipped, 0 failures** |
| Focused bridge verification | 412 passed, 0 failures |
| `git diff --check` | PASS |
| Working tree after commit | CLEAN |

### 130.5 Structural Migration Status

The independent audit concluded: **M1–M11 STRUCTURAL MIGRATION: PASS**.

No migration-introduced business-logic regression was identified. The physical structure established at `01a9fc6` (Finalize SentinelX physical project structure) remains accepted/frozen. The Phase-8 safety defects were PRE-EXISTING and were not introduced by the M1–M11 structural migration.

### 130.6 Current Blocker Status

**No known open P0/P1 findings from the completed independent audit.**

This does not claim that SentinelX can never contain undiscovered defects.

### 130.7 Next Owner-Approved Work

Phase 8.5 implementation may now begin from the already-frozen Phase 8.5 Slice 0 historical-data-automation contract.

### 130.8 Repair Scope Constraints

- This recording step changed: `BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md` (this section), `SENTINELX_PROGRESS.md`.
- No production code, tests, configuration, schema, or persistence files were changed.
- No Phase 8.5 implementation files were created or modified.
- No commit was performed; changes left uncommitted for owner review.

### 130.9 Documentation Rules Preserved

Append-only historical evidence preserved. No old historical records were rewritten to make defects appear as if they never existed. The original Phase-8 completion record, independent audit discovery, bounded repair, and final closure are clearly distinguished.

### 130.10 Authoritative Marker

`PHASE_8_SAFETY_REPAIR_DOCUMENTATION_CLOSURE`
`F_SAFETY_01_CLOSED`
`F_SAFETY_02_CLOSED`
`REPAIR_COMMIT_043CA15_RECORDED`
`FINAL_SUITE_2562_PASSED_0_SKIPPED_0_FAILURES`
`STRUCTURAL_MIGRATION_PASS_NO_BUSINESS_LOGIC_REGRESSION`
`NO_KNOWN_OPEN_P0_FINDINGS`
`NO_KNOWN_OPEN_P1_FINDINGS`
`NEXT_SINGLE_REQUIRED_STEP: Phase 8.5 implementation from frozen Slice 0 contract`
`SCHEMA_VERSION: 7 (UNCHANGED)`

---

## 131. Phase 9 — Dashboard + Security + Operational Control Surface + Strategy Governance + Future-Ready Multi-User Foundation — Owner Decision / Architecture Contract Freeze

**Status:** DOCUMENTATION / CONTRACT FREEZE ONLY — **NO PHASE 9 IMPLEMENTATION HAS STARTED.** This recording step created no production code, no FastAPI code, no React/TypeScript/Vite code, no authentication code, no strategy-upload code, no API endpoints, no database migrations, no new runtime dependencies, no dashboard directory, no Phase-9 tests, and performed no commit/push. Append-only record; no prior section is altered, renumbered, or rewritten, and §1–§130 remain in force.

**Date:** 2026-08-26

**Context:** This is the pre-implementation owner decision / architecture freeze for the Phase 9 dashboard/control surface, mandated before any Phase 9 implementation slice begins. It formalizes the owner-approved P9 purpose, technology stack, security decisions (P9-OD1 … P9-OD6), control-center principle, strategy governance, user-isolation / future multi-user boundary, retention placeholder, and implementation governance.

### 131.0 Phase-9 Identity and Purpose Freeze (APPROVED)

Phase 9 is: **DASHBOARD + SECURITY + OPERATIONAL CONTROL SURFACE + STRATEGY GOVERNANCE + FUTURE-READY MULTI-USER FOUNDATION.**

Current active operating mode remains **SINGLE OWNER / ADMIN ONLY**. The architecture must be future-ready for multiple users, but **NO** normal multi-user onboarding, public signup, billing, subscriptions, or customer launch is authorized in Phase 9. A separate future OWNER decision is mandatory before any multi-user launch.

**Numbering note:** this "Phase 9" is the build-order/release phase for the dashboard/control surface. It is distinct from `requirements-freeze-125.md` document-phase "Phase 9 (Q88–Q93)", which §123.9 maps to build-order Phase 6 (Logging/Audit). These are different sequences. This §131 governs the dashboard/control-surface Phase 9 and does not reopen the logging/audit Phase 9 (Q88–Q93).

### 131.1 P9 Dashboard Production Framework — EXPLICIT SUPERSESSION of Streamlit (APPROVED)

The earlier Streamlit production-dashboard requirements — `requirements-freeze-125.md` Q70 ("Real-time dashboard: 🔒 Yes, Streamlit, as established") and Q94–100 (freeze-doc "Phase 10 – UI" dashboard feature set: "Streamlit, as decided") — and the `PROJECT_STRUCTURE.md` `dashboard/` entry marked "Phase 10 — not built yet, Streamlit" — are **EXPLICITLY SUPERSEDED** (named supersession, not silent replacement). Phase 10 – UI Q101 (single-admin username/password login, the historical freeze-doc authentication item — not the separate Phase 11 Deployment Q101) is likewise superseded by P9-OD1 in §131.3.

**AUTHORITATIVE PHASE 9 PRODUCTION STACK:**
- **Backend:** FastAPI (Python), a controlled API/service boundary over existing SentinelX authorities. REST where appropriate; WebSocket/event streaming where appropriate.
- **Frontend:** React + TypeScript + Vite.
- **UI/component/styling ecosystem:** may use suitable open-source dependencies (e.g. Tailwind/shadcn-style components and appropriate charting libraries). Exact dependency versions must be selected and frozen during implementation without destabilizing the existing SentinelX runtime.
- **Streamlit:** remains usable only for optional/internal diagnostic prototypes if ever separately authorized. It is NOT the authoritative Phase 9 production control-center framework.
- **Dependency isolation:** dashboard dependencies remain isolated from the core SentinelX runtime where necessary to preserve the frozen core dependency closure.

### 131.2 General Dashboard Control-Center Principle (APPROVED)

The Phase 9 dashboard is the primary governed user-facing **control center** for SentinelX — **not** merely a reporting/charting interface. Every existing SentinelX capability that is meaningfully user-facing must have an appropriate dashboard surface unless an explicit safety/security reason requires it to remain CLI-only or backend-only.

The dashboard **exposes existing authorities**; it must **NOT create competing authorities**. It must NOT become: a second risk engine, a second strategy engine, a second persistence authority, a second audit authority, a second historical-data authority, or an unrestricted execution authority. Existing SentinelX backend authorities remain authoritative.

### 131.3 P9-OD1 — Strong Authentication (APPROVED)

- **FIDO2 / WebAuthn is mandatory.** Password-only authentication is **forbidden**.
- The OWNER/Admin must have **at least two authenticators**: a primary passkey/authenticator and a backup hardware authenticator/key.
- No implementation convenience may downgrade the system to password-only auth.

### 131.4 P9-OD2 — No Single Access Dependency (APPROVED)

- Normal administrative access may use a private VPN/overlay.
- The operator must not depend on one single access mechanism. Failure or compromise of the private VPN/overlay must not permanently lock out the OWNER.
- An **independent break-glass access path is mandatory**.

**CRITICAL CROSS-DEPENDENCY RULE:** If normal access depends on `VPN/overlay → mTLS → FIDO2/WebAuthn`, then the independent break-glass route **MUST NOT** depend on the same VPN or mTLS failure chain. Break-glass must remain independently reachable when the normal VPN/overlay and/or normal mTLS access infrastructure is unavailable. **No common failure dependency may defeat both normal access and break-glass access simultaneously.**

### 131.5 P9-OD3 — Break-Glass Is Access Recovery, Not Safety Bypass (APPROVED)

Break-glass exists only to restore administrative access. It must **NEVER** bypass: risk controls, safety gates, persistence safety, fail-closed state, manual-resume requirements, execution restrictions, or recovery semantics. Break-glass restores **ACCESS**, not unrestricted SentinelX authority.

### 131.6 P9-OD4 — Safety Semantics Survive Every Access Path (APPROVED)

Normal access, VPN access, recovery access, and break-glass access must obey the same existing SentinelX safety rules. No alternate access path may create auto-resume, risk bypass, safety bypass, persistence bypass, or execution bypass. Existing manual-resume and fail-closed semantics remain authoritative.

### 131.7 P9-OD5 / P9-OD6 — Security Recovery / Audit Authority (APPROVED)

Security-sensitive actions must be attributable, timestamped, auditable, and reviewable. This applies to: authentication recovery, authenticator enrollment/replacement, device recovery, break-glass use, security-setting changes, and other privileged recovery actions.

Recovery must not erase evidence, silently reset safety state, weaken risk controls, silently replace an existing authority, or create an invisible backdoor. Existing SentinelX audit/safety authorities remain authoritative.

### 131.8 Advanced Security / Safety Design (APPROVED)

- **mTLS** is an additional device/channel identity layer for NORMAL administrative access. Conceptual layers: VPN/overlay = private network boundary; mTLS = device/channel identity; FIDO2 = operator/human authentication. mTLS must NOT become a mandatory dependency of the independent break-glass route when that would place break-glass in the same normal-access failure chain.
- **FIDO2 device/authenticator attestation:** the architecture must support policy-driven authenticator attestation where compatible. Do not assume all passkey authenticators provide identical attestation. The exact mandatory/optional hardware policy must preserve interoperability and security and must not silently weaken P9-OD1.
- **Deterministic session-risk / step-up policy:** use explicit deterministic security rules, not opaque ML scoring. Possible signals: unknown device, unexpected certificate, unexpected authenticator, changed access route, abnormal session condition, repeated auth failures, break-glass usage. Conceptual decisions: `NORMAL`, `STEP_UP_REQUIRED`, `DENY_OR_REVIEW`.
- **Dashboard-originated security evidence:** support tamper-evident / hash-chain-style evidence where appropriate, subordinate and cross-linked to the existing authoritative SentinelX audit system. Never create a second competing audit truth.

### 131.9 Global Dashboard Safe Mode (APPROVED)

Phase 9 includes a global dashboard **SAFE MODE**: freeze dashboard-originated mutable operations during security/incident review without necessarily shutting down the SentinelX engine. Safe mode allows monitoring, audit review, historical inspection, and reports/state inspection. Safe mode blocks dashboard-originated settings writes, configuration mutation, and other mutable control actions. Safe mode is **NOT** a risk bypass, a safety bypass, or an auto-resume mechanism.

### 131.10 Settings Governance (APPROVED)

Mutable settings follow: **PROPOSE → VALIDATE → DRY RUN → EXACT BEFORE/AFTER DIFF → EXPLICIT CONFIRMATION → ATOMIC WRITE → VERIFY → AUDIT**. Risk/safety-sensitive settings are not ordinary convenience settings. Existing owner/risk-change authority must remain respected. Secrets/private keys/passwords must never be exposed in plaintext through the dashboard, including to OWNER where plaintext disclosure is unnecessary. Use safe secret status — `CONFIGURED`, `NOT_CONFIGURED`, `NEEDS_ROTATION` — where appropriate.

### 131.11 Data Trust / Display Semantics (APPROVED)

Important widgets must expose authoritative freshness information: `FRESH`, `STALE`, `UNKNOWN`. Display authoritative "as-of" timestamps where applicable. `UNKNOWN` must never be displayed as healthy/fresh. Historical/snapshot state must be clearly distinguished from live/current state. Point-in-time views must visibly state **`FROZEN HISTORICAL VIEW`** and include appropriate evidence (timestamp, run identity, config identity, source identity, state fingerprint) where authoritative evidence exists.

### 131.12 Strategy Plugin Architecture (APPROVED)

The dashboard exposes SentinelX's existing strategy-pluggable architecture. Required user-facing flow: **Strategies → + Add Strategy → Python strategy/plugin submission → safety/static validation → strategy interface/contract conformance → BACKTEST → results/evidence → PAPER eligibility promotion → paper results/evidence → LIVE eligibility promotion.**

A new strategy must NOT require rewriting the engine. Strategy code must follow the authoritative strategy interface/ABC and existing SentinelX contracts. Strategy code must NOT receive direct unrestricted authority over broker execution, the risk engine, persistence, audit, or unrelated filesystem/system capabilities. Dangerous/banned imports or calls must be rejected according to the eventual frozen sandbox/static-validation policy.

### 131.13 Backtest / Paper / Live Staged Eligibility (APPROVED)

For a valid/conforming strategy, BACKTEST is immediately available. "Backtest open" means no promotion gate is required for backtesting; it does NOT mean static safety validation is skipped, contract/conformance validation is skipped, or malformed/unsafe code is executed.

Staged lifecycle: `ADDED / VALIDATED → BACKTEST_ELIGIBLE → explicit promotion → PAPER_ELIGIBLE → explicit promotion → LIVE_ELIGIBLE`. No strategy may jump directly to LIVE eligibility. Eligibility does NOT itself bypass existing execution/risk/safety controls.

### 131.14 Protective Policy (APPROVED)

Do not silently assign a generic protective policy. A strategy must define its explicit compatible protective policy, OR remain in an explicit `NOT_YET_DEFINED`/equivalent state. Existing fail-closed protective-policy semantics remain authoritative.

### 131.15 Strategy Archive / Delete (APPROVED)

Normal strategy deletion means **SAFE ARCHIVE / DISABLE**. Do not hard-delete historical evidence by default. Preserve versions, backtests, paper evidence, promotion history, audit references, and historical attribution.

### 131.16 Strategy Quality Score (APPROVED)

Provide an evidence-based 0–100 Strategy Quality Score. Owner-approved weighting: OOS / Walk-forward 25; Robustness / stability 20; Drawdown quality 15; Expectancy 15; Profit Factor 10; Statistical confidence / bootstrap 10; Trade evidence sufficiency 5.

Grades: 90–100 Exceptional; 80–89 Strong; 70–79 Good; 60–69 Moderate; <60 Weak / Needs Review.

**QUALITY SCORE and ELIGIBILITY are separate.** A high score never overrides mandatory safety/conformance/promotion gates. Example: QUALITY SCORE 92/100 with ELIGIBILITY BACKTEST YES, PAPER YES, LIVE NO. 99/100 + mandatory safety failure = FAIL.

### 131.17 Owner / User Governance (APPROVED)

Architecture contains two roles: **OWNER** and **USER**. Current runtime/launch mode remains OWNER-only.

- **OWNER:** system-wide administrative visibility; users list; user strategies; backtests; paper evidence; performance; account suspend/disable; strategy quarantine; system-wide governed settings; system/security/audit review. OWNER still cannot bypass existing SentinelX risk/safety/audit rules.
- **USER:** only own permitted dashboard/data; own strategies; own backtests; own paper/live-eligibility records; own performance; own allowed settings; own security/activity history. User-A must NEVER access User-B's private domain. Owner must never receive plaintext user passwords/private keys/secrets.
- Future roles such as Support/Analyst may have extension points but must NOT be implemented now.

### 131.18 Per-User Data Isolation (APPROVED)

Each user must have an immutable internal UUID-style identity. Do NOT use a mutable display name as storage identity. Conceptual namespace: `users/usr_<immutable-id>/{profile,strategies,backtests,paper,reports,exports}`. Logical user isolation is mandatory. Physical architecture may be hybrid (structured database state + isolated artifact namespaces). Expected entities/tables conceptually: `users`, `strategies`, `strategy_versions`, `backtest_runs`, `paper_runs`, `promotions`, `user_actions`, `security_events`, `audit_references`. Each strategy must be attributable to its immutable owner/user identity. Current single-owner mode uses the OWNER identity. Do not scatter literal "admin" assumptions through business logic; use an authoritative current-owner identity boundary.

### 131.19 Per-User History (APPROVED)

Future user domains must maintain attributable history for: identity/verification references; security/login history; strategies submitted; strategy versions; backtests; quality/performance evidence; paper runs; promotion history; settings/actions; security events; audit references; reports/exports. Multi-user architecture is built as foundation, but no second user is onboarded during current Phase 9 operation.

### 131.20 User Data Lifecycle + Retention (APPROVED)

Lifecycle: `ACTIVE → SUSPENDED → CLOSED → ARCHIVED`. When CLOSED: login disabled immediately; active sessions revoked; authenticators revoked as applicable; relevant API credentials revoked; new runs blocked. Historical evidence is NOT immediately destroyed.

**RETENTION DURATION IS UNCONFIRMED.** Do not freeze an arbitrary number. Architecture should contain retention-policy fields/metadata for future use. **AUTOMATIC / SCHEDULED DELETION MUST REMAIN DISABLED** — no data may be silently deleted using a placeholder retention period. PII anonymization/pseudonymization automation remains inactive until an applicable legal/policy decision is explicitly approved. Long-lived evidence may later use immutable pseudonymous `usr_<id>` references where legally appropriate.

### 131.21 Multi-User Deployment Boundary (APPROVED)

Phase 9 builds the architecture/foundation. Current active use: **SINGLE OWNER / PRIVATE USE**. NOT AUTHORIZED now: public signup, customer onboarding, billing, subscriptions, multi-user commercial launch, Support/Analyst roles, automated retention deletion. Future multi-user launch requires a separate explicit OWNER decision.

### 131.22 External Alert Transports (APPROVED)

Telegram/email/SMS or other real external transports are **NOT automatically authorized** by Phase 9. The existing deferred external-transport boundary remains. Dashboard-local/internal warnings are allowed. External transport requires separate explicit authorization.

### 131.23 Live / Execution Boundary (APPROVED)

The dashboard may expose existing live-system status and governed strategy LIVE eligibility. However, LIVE_ELIGIBLE != unrestricted execution authority. The dashboard must not create a parallel bypass around risk, execution, broker, manual-resume, fail-closed, or safety authorities.

### 131.24 Fail-Closed UI (APPROVED)

The dashboard must not convert uncertainty into apparent success: UNKNOWN != HEALTHY, STALE != LIVE, MISSING != VALID, FAILED PERSISTENCE != NORMAL, AUTH FAILURE != PASSWORD FALLBACK. The UI must visibly represent uncertainty/failure states.

### 131.25 No Silent Supersession Rule (APPROVED)

Any frozen P9 owner decision may be changed only by an explicit later OWNER ruling that (1) names the exact decision being superseded, (2) defines replacement semantics, and (3) records the reason. Silence, implementation convenience, dependency conflicts, later prose, or agent assumptions must never implicitly supersede an owner decision.

### 131.26 Phase 9 Implementation Governance (APPROVED)

No implementation is authorized by this freeze. Correct sequence after this docs-only freeze: 1. Phase 9 docs/ADR freeze; 2. independent read-only audit (another agent, e.g. Ox Alpha); 3. OWNER review; 4. explicit implementation authorization; 5. Codex implementation in controlled slices; 6. targeted tests per slice; 7. full regression/security audit; 8. Phase 9 final closure.

**Recorded Phase 9 implementation technology target (for future implementation):** Frontend React + TypeScript + Vite; Backend/API boundary FastAPI; Communication REST and/or WebSocket per authoritative use case. Existing SentinelX engine/services remain backend authority. The implementation agent will install/select required open-source packages from normal package registries. No Hugging Face or external AI model is required merely to implement the Phase 9 dashboard.

### 131.27 Supersession Register

Superseded by this §131 owner ruling:

- `requirements-freeze-125.md` Q70 (Streamlit production dashboard) — **SUPERSEDED** as the authoritative Phase 9 production dashboard framework by §131.1; the historical requirement text is preserved verbatim and NOT rewritten.
- `requirements-freeze-125.md` Q94–100 (freeze-doc "Phase 10 – UI" Streamlit dashboard feature set) — **SUPERSEDED** by §131.1 (FastAPI + React + TypeScript + Vite); historical text preserved verbatim.
- `requirements-freeze-125.md` Phase 10 – UI Q101 (single admin username/password login, the historical freeze-doc authentication item — not the separate Phase 11 Deployment Q101) — **SUPERSEDED** by P9-OD1 (§131.3; FIDO2/WebAuthn mandatory, password-only forbidden).
- `PROJECT_STRUCTURE.md` `dashboard/` entry labelled "Phase 10 — not built yet, Streamlit" — **SUPERSEDED** to build-order Phase 9 / FastAPI + React + TypeScript + Vite per §131.1; stale "Phase 10"/Streamlit naming retired in that document.
- No other prior owner ruling is altered; §1–§130 remain in force.

### 131.28 Authoritative Marker

`PHASE_9_DASHBOARD_SECURITY_CONTRACT_FREEZE_RECORDED`
`STREAMLIT_PRODUCTION_DASHBOARD_SUPERSEDED`
`FASTAPI_BACKEND_REACT_TYPESCRIPT_VITE_FRONTEND`
`P9_OD1_FIDO2_WEBAUTHN_MANDATORY_NO_PASSWORD_ONLY`
`P9_OD2_NO_SINGLE_ACCESS_DEPENDENCY_BREAK_GLASS_INDEPENDENT_OF_NORMAL_VPN_MTLS_CHAIN`
`P9_OD3_BREAK_GLASS_IS_ACCESS_RECOVERY_NOT_SAFETY_BYPASS`
`P9_OD4_SAFETY_SURVIVES_EVERY_ACCESS_PATH`
`P9_OD5_P9_OD6_RECOVERY_ATTRIBUTABLE_AUDITABLE`
`DASHBOARD_IS_CONTROL_CENTER_NOT_COMPETING_AUTHORITY`
`GLOBAL_DASHBOARD_SAFE_MODE_FROZEN`
`SETTINGS_GOVERNANCE_PROPOSE_VALIDATE_DRYRUN_DIFF_CONFIRM_ATOMIC_VERIFY_AUDIT`
`DATA_TRUST_FRESH_STALE_UNKNOWN_FROZEN_HISTORICAL_VIEW`
`STRATEGY_STAGED_ELIGIBILITY_ADDED_VALIDATED_BACKTEST_PAPER_LIVE`
`STRATEGY_QUALITY_SCORE_SEPARATE_FROM_ELIGIBILITY`
`PROTECTIVE_POLICY_NEVER_SILENTLY_GENERIC`
`STRATEGY_DELETE_IS_SAFE_ARCHIVE`
`SINGLE_OWNER_MODE_FROZEN`
`MULTI_USER_LAUNCH_NOT_AUTHORIZED`
`RETENTION_DURATION_UNCONFIRMED`
`AUTOMATIC_RETENTION_DELETION_DISABLED`
`NO_PHASE_9_IMPLEMENTATION_STARTED`
`SCHEMA_VERSION: 7 (UNCHANGED)`

### 131.29 P9 — Professional Market Chart / Trading Terminal View — Mandatory Phase 9 Dashboard Capability (APPROVED)

**Date:** 2026-08-26. Additive owner refinement to §131. All prior §131 decisions and P9-OD1 … P9-OD6 remain in force, unchanged. Docs-only; no implementation started by this recording step.

The Phase 9 dashboard **MUST** include a professional, trading-terminal-style interactive market chart. This is a **mandatory Phase 9 dashboard capability**, not an optional enhancement. **"TradingView-style"** describes the required user interaction, visual quality, and chart capability; it does **NOT** authorize dependence on TradingView Desktop, TradingView MCP integration, proprietary TradingView APIs, copying TradingView proprietary code, or the creation of a new market-data or execution/trading authority.

**Required capabilities:**

1. **Price visualization.** Candlestick / OHLC market visualization with clear price and time axes, professional trading-terminal visual quality, and smooth desktop-grade interaction.
2. **Timeframe selection.** The user must be able to switch among SentinelX-supported timeframes. Timeframe availability must come from authoritative SentinelX data capability/configuration, not from invented UI-only values.
3. **Live data view.** Where authoritative SentinelX live market data exists, the chart must update from that existing authoritative data path. It must **NOT** create a separate live market-data source or authority.
4. **Historical / backtest view.** The same chart surface must be usable for supported historical and backtest inspection. Historical/backtest state must be clearly distinguishable from current/live state.
5. **Live vs. historical trust semantics.** LIVE/current and FROZEN HISTORICAL/BACKTEST views must be visibly distinct. §131.11 FRESH / STALE / UNKNOWN and authoritative "as-of" semantics apply. Historical state must use the §131.11 **FROZEN HISTORICAL VIEW** principle where applicable. STALE/UNKNOWN must never appear as authoritative live data.
6. **Volume.** Display volume when the authoritative source data contains valid volume evidence. Missing volume must never be fabricated.
7. **Strategy signal / trade markers.** Where authoritative evidence exists, the chart should display relevant strategy signals, entries, exits, and trade markers. Markers must derive from existing SentinelX strategy/backtest/paper/live records, never reconstructed or invented independently by the frontend.
8. **Protective overlays.** Where authoritative evidence exists, display relevant stop-loss, target, and trailing/protective state. The chart is visualization only; it must not calculate or become a second protective-policy/risk authority.
9. **Strategy / backtest analysis (MANDATORY).** The chart MUST support visual strategy/backtest analysis, including reviewing where authoritative strategy signals, entries, exits, trades, and supported protective overlays occurred against historical market data. This remains visualization over authoritative SentinelX records; it must NOT become a second strategy/backtest/risk/protective authority. The existing Backtest Engine remains the authoritative computation engine.
10. **Dashboard authority boundary.** The chart consumes existing SentinelX data/state and MUST NOT become a market-data, strategy, backtest, risk, protective-policy, execution, or audit authority (per §131.2 the dashboard exposes existing authorities and creates no competing authority).
11. **Fail-closed display.** Missing, stale, corrupt, unavailable, or unknown data must be represented honestly (consistent with §131.24 fail-closed UI). The frontend must never fabricate candles, signals, trade states, SL, targets, volume, or confidence.
12. **No external TradingView dependency requirement.** "TradingView-style" refers to professional interaction/design quality. Phase 9 does NOT require TradingView Desktop, TradingView MCP, or proprietary TradingView services. Any eventual chart library must be chosen separately during implementation under the frozen dependency/security boundaries (§131.1, §131.26).
13. **Responsive / professional UX.** Primary target is a professional desktop trading control-center. The chart must remain usable on smaller supported displays without corrupting or hiding critical safety/freshness. No generic low-information admin-template chart satisfies this requirement.

**Distinction preserved:** This instrument-level market chart (candlestick/OHLC price action) is a requirement concept distinct from, and in addition to, the equity-curve / drawdown chart already referenced in historical requirements (`requirements-freeze-125.md` Phase 10 – UI Q94–100). The equity/drawdown chart does NOT satisfy this market-chart requirement, and vice versa.

**Unchanged invariants:** QUALITY SCORE != ELIGIBILITY (§131.16); LIVE_ELIGIBLE != unrestricted execution authority (§131.23); DASHBOARD != second engine/authority (§131.2). This requirement authorizes NO implementation by itself and changes no existing authority, dependency, or schema (`SCHEMA_VERSION: 7 UNCHANGED`).

**Authoritative markers:** `P9_MARKET_CHART_TRADING_TERMINAL_IS_MANDATORY` · `TRADINGVIEW_STYLE_IS_UX_NOT_DEPENDENCY` · `NO_TRADINGVIEW_DESKTOP_MCP_OR_PROPRIETARY_API_DEPENDENCY` · `CHART_CONSUMES_EXISTING_AUTHORITY_NOT_A_SECOND_DATA_SOURCE` · `CHART_NEVER_FABRICATES_DATA_OR_STATE`

### 131.30 First-Party Multi-Surface SentinelX (APPROVED)

**Date:** 2026-08-26. Additive owner decision to §131. All prior §131 decisions and P9-OD1 … P9-OD6 remain in force, unchanged. Docs-only; no implementation started by this recording step.

SentinelX must be designed and delivered as a **first-party product** on its own owned/branded surfaces. These are distinct user-facing presentation/control surfaces, not independent products or engines:

1. **Public first-party website.** A SentinelX-branded public information site (`sentinelx.com` or an owner-selected SentinelX domain) providing product information, documentation, posts/updates, and an entry/link into the secure application.
2. **First-party web application.** A web-based SentinelX Control Center (e.g. `app.sentinelx.com`) implementing the full governed Phase 9 dashboard capabilities: strategies, backtests, paper state, the professional market chart (§131.29), and portfolio/data/audit/settings/security surfaces.
3. **First-party desktop application.** A SentinelX-branded desktop application that requires no third-party-branded control panel for normal use. It must consume the same authoritative SentinelX services/contracts as web/mobile. Final installer/release packaging may remain in the later owner-designated packaging phase.
4. **First-party mobile application.** A SentinelX-branded mobile application. The architecture must support a mobile surface from Phase 9 onward. Mobile permissions/actions remain governed by the same security, risk, safety, and authorization rules as every other surface. Current operation remains OWNER-only until multi-user launch is separately authorized.

**CRITICAL ARCHITECTURE RULE:** Do NOT build four independent SentinelX engines. Use **ONE authoritative SentinelX backend/domain architecture**. Web, Desktop, and Mobile are first-party client/control surfaces over the same authoritative SentinelX contracts. They must not duplicate: risk authority, strategy authority, backtest authority, persistence authority, historical/live market-data authority, protective-policy authority, audit authority, or unrestricted execution authority. Shared frontend/domain components should be reused wherever technically safe and appropriate instead of rewriting the same product independently for each surface.

**"Everything first-party"** means the final user-facing SentinelX product, branding, domain, and control surfaces belong to SentinelX. It does NOT mean rewriting operating systems, browsers, frameworks, or every open-source library from scratch; open-source/internal implementation dependencies are allowed. TradingView Desktop/MCP remains unnecessary (§131.29.12).

**Deployment boundary preserved:** Current active use remains **SINGLE OWNER / PRIVATE USE**. A public first-party website may exist as a public information surface, but normal USER onboarding, customer accounts, billing/subscriptions, and commercial multi-user launch remain **unauthorized** until a separate future OWNER decision (§131.0/§131.21).

**Packaging boundary preserved:** Phase 9 builds the first-party application surfaces and architecture. Final installer/release packaging, bundled distribution, update/rollback, and clean-machine release packaging may remain governed by the later owner-designated packaging phase; that phase is not performed by this docs task.

**Unchanged invariants:** QUALITY SCORE != ELIGIBILITY (§131.16); LIVE_ELIGIBLE != unrestricted execution authority (§131.23); DASHBOARD != second engine/authority (§131.2); ONE authoritative backend/core (§131.30). This decision authorizes NO implementation by itself and changes no existing authority, dependency, or schema (`SCHEMA_VERSION: 7 UNCHANGED`).

### 131.31 Phase 9 Security / Identity Store and WebAuthn Production Identities (APPROVED)

**Date:** 2026-08-27. Additive owner decision. The normal production WebAuthn RP ID is `sentinelx.com` with the sole application origin `https://app.sentinelx.com`; the public information website is not a WebAuthn origin. The independent recovery RP ID is `sentinelx-recovery.com` with the sole recovery origin `https://access.sentinelx-recovery.com`. Recovery credentials are separately enrolled and the recovery path remains independent of normal VPN/mTLS. A development-only profile may use `localhost` and an explicitly configured `http://localhost:<port>` origin; it is never accepted by production configuration.

Owner authorizes the independent durable store `<configured_data_root>/security/sentinelx_security.sqlite3`, with `SECURITY_STORE_SCHEMA_VERSION = 1`, for users, WebAuthn credentials, one-time challenges, safe session verifier material, and authoritative core-audit references only. It is not a second audit authority. **Engine `SCHEMA_VERSION` remains exactly 7; `engine/persistence/schema.py` receives no Phase 9 security tables or migration.**

**Authoritative markers:** `SENTINELX_FIRST_PARTY_PRODUCT_MULTI_SURFACE` · `PUBLIC_WEBSITE_MANDATORY` · `WEB_APP_MANDATORY` · `DESKTOP_APP_MANDATORY` · `MOBILE_APP_MANDATORY` · `ONE_AUTHORITATIVE_BACKEND_NOT_FOUR_ENGINES` · `SINGLE_OWNER_CURRENT_USE_PRESERVED` · `MULTI_USER_LAUNCH_REMAINS_UNAUTHORIZED` · `FINAL_PACKAGING_PHASE_REMAINS_SEPARATE`
