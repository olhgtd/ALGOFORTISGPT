# SentinelX — Paper Trading Engine Specification (v1.0 OWNER_APPROVED)

> Scope: Layer 3, Box 2 ("Paper Trading Engine") from SentinelX High-Level System Diagram.
> Goal: Live-market, virtual-money simulation that is execution-realistic — not a naive "fill at LTP" toy.
> Status: **OWNER_APPROVED** — Phase 5 architecture and completion gate refrozen per OD-1 through OD-7.
> Refreeze date: 2026-08-19
> Original draft: 2026-08-19

> **Amendment record:** This document was originally submitted as DRAFT. Following a master-spec conflict
> audit against all frozen contracts, the owner approved seven scope-refreeze decisions (OD-1 through OD-7)
> which are incorporated below. Sections conflicting with the approved decisions have been reconciled.
> The original DRAFT text is preserved in the project's conversation history and audit record per
> `BACKTEST_ENGINE_ARCHITECTURE_DECISIONS.md` §1 (Authority and amendment rule item 5).

---

## 0. Design Principle (non-negotiable)

Paper P&L must be **conservative relative to live**, never optimistically better. If a fill can't realistically happen (no liquidity, price already moved), the engine must reject/adjust it — not magically fill it.

### 0.1 ExecutionAdapter Architecture (OD-2)

Define one `ExecutionAdapter` interface with three implementations:

```
ExecutionAdapter
├── BacktestFillAdapter  — wraps/reuses the verified backtest ExecutionEngine (unchanged)
├── PaperFillAdapter     — owns paper-specific execution-realistic fill behavior
└── LiveBrokerAdapter    — future real broker execution path
```

Strategy and risk logic remain mode-independent wherever existing frozen contracts permit.

**IMPORTANT:** This decision does NOT authorize rewriting the verified backtest ExecutionEngine.
`BacktestFillAdapter` will eventually reuse/wrap the existing verified backtest `ExecutionEngine`.

This architecture is frozen. Implementation is a future Phase 5 implementation slice.

---

## 1. Components Required

### 1.1 Live Data Connector
- Zerodha WebSocket (or Angel One) live tick/quote feed
- Subscribes to: index LTP, option chain **bid/ask/OI** (where needed)
- Reconnect handling on drop (see 1.9)
- Tick-to-bar assembly for completed bars (for bar-based engine components)
- Raw tick delivery for tick-sensitive components (protective monitoring, fill pricing)
- **Status: NOT BUILT — mandatory Phase 5 dependency per OD-7 item 6**

### 1.2 Execution Simulator (Fill Engine) — NEW, core component
- Input: signal (BUY/SELL, instrument, qty) from Strategy Engine via Option Selector
- **Fill price logic: use live bid/ask, NOT last-traded-price** (OD-3)
  - BUY → fill near executable **ASK** + configurable slippage bps
  - SELL → fill near executable **BID** − configurable slippage bps
  - Do NOT use naive LTP-only optimistic fills
- Slippage model: configurable bps constant (placeholder), calibrate later (see Section 4)
- Latency model: configurable delay (ms) between signal time and fill time
- **Stale quote rejection / fail-closed behavior** (OD-3)
- **Price-gap rejection**: reject fill if price has moved beyond approved execution tolerance
- **Conservative execution**: impossible or unsupported fills must not be magically accepted
- **Applicable brokerage/statutory/exchange costs included** (OD-3)
- Partial fill logic: **NOT required for v1 without reliable market-depth/liquidity evidence** (OD-3)
- **Do NOT claim that paper execution can be guaranteed 100% identical to exchange execution** (OD-3)
- Goal: conservative, execution-realistic paper behavior

### 1.3 Cost Model
- Brokerage (flat/per-order per Zerodha/Angel One schedule)
- STT (Securities Transaction Tax)
- GST on brokerage
- Exchange transaction charges
- Stamp duty
- Applied at fill time, deducted from virtual P&L
- **Status: reusable infrastructure — `CostCalculator` + `CostSchedule` (broker-agnostic, FIXED/PER_UNIT/NOTIONAL/DEPENDENCY) already exist; needs Zerodha-specific schedule configuration (data, not code)**

### 1.4 Virtual Account / Ledger
- Configurable virtual capital (₹50k / ₹1L / ₹10L etc.)
- Available margin vs used margin tracking
- Multiple concurrent virtual accounts (for testing multiple strategies independently, sharing portfolio-level risk rules) — **future enhancement, not a Phase 5 v1 blocker**

### 1.5 Order Lifecycle State Machine

> **Reconciled per OD-5:**
> The original spec assumed `PENDING → OPEN → FILLED / PARTIALLY_FILLED / REJECTED / EXPIRED`.
> The verified frozen core order lifecycle is:
>
> `CREATED → VALIDATED → QUEUED → FILLED / EXPIRED / CANCELLED / REJECTED`
>
> **OPEN** and **PARTIALLY_FILLED** are NOT added to the frozen core lifecycle during v1.
> The spec's terminology is reconciled to the existing lifecycle:
> - "PENDING" ≈ `QUEUED` (order awaiting execution)
> - "OPEN" ≈ `QUEUED` (order is active in the paper broker)
> - "FILLED" = `FILLED`
> - "REJECTED" = `REJECTED`
> - "EXPIRED" = `EXPIRED`
> - "PARTIALLY_FILLED" = deferred; requires separate owner architecture decision
>
> No hidden incompatible paper-only lifecycle state machine is created.

### 1.6 P&L Engine
- Realized P&L (on exit)
- Unrealized/live MTM P&L (updates on every tick/price update while position open)
- Net P&L after costs (Section 1.3)
- Existing `PortfolioAccount.mark_to_market` provides bar-based MTM; tick-level MTM is a
  required extension for live paper trading

### 1.7 SL / Target / Trailing Execution
- Reuses Risk Engine's SL/Target/Trailing **logic/semantics** as far as possible
- **Must trigger against live price updates, NOT completed strategy candles only** (OD-6)
- Existing verified protective rules/state semantics should be reused
- **A dedicated live-price/tick/quote protective trigger integration path or adapter is required** (OD-6)
- Do NOT make 5-minute/strategy-bar close the required trigger point for protective exits in live paper trading

### 1.8 Multi-Strategy Concurrency
- N strategies running paper trades simultaneously
- Shared portfolio-level risk/capital caps enforced across all of them (not per-strategy silos)
- **Existing infrastructure verified:** concurrent capital competition (§60 / D14), `AllocationPriorityConfig`,
  strategy isolation via `StrategyBinding`

### 1.9 Reconciliation, Logging, Audit Trail
- Full trade log: signal time, fill time, fill price, costs, exit reason
- State persistence (so a restart doesn't lose open virtual positions)
- Disconnect/recovery: freeze MTM, alert, don't fake-exit
- D16-compatible logging/audit evidence (versioned storage-independent schema, 17-field envelope, 10 event families)

### 1.10 Option Contract Resolution — **BLOCKING DEPENDENCY** (OD-4)

Option Selector is a **BLOCKING DEPENDENCY** for Phase 5 VERIFIED_COMPLETE.

SentinelX Phase 5 target is **automated OPTIONS paper trading**. Therefore Phase 5 cannot be
declared VERIFIED_COMPLETE until the system can automatically resolve, using frozen
strategy/configuration rules:

- underlying intent (BULLISH / BEARISH / EXIT / HOLD)
- CE / PE
- expiry
- strike
- tradable option instrument
- lot size / contract multiplier
- required live quote / instrument identity

Strategy logic itself must NOT hard-code broker-specific option contracts.

Infrastructure work may proceed before Option Selector is complete, but the final Phase 5
completion gate requires Option Selector.

### 1.11 Calibration Module — NOT part of MVP build, but required before trusting output
- Micro-capital (₹500–2000) real trades run in parallel with paper trades on same signals
- Compare: actual fill vs paper-predicted fill, actual slippage vs modeled slippage
- Feed results back to adjust slippage/latency constants in 1.2
- This is a **data-gathering process over weeks**, not a code component — can't be "built" faster by working harder on it

---

## 2. What Is Reused vs What Is New

| Component | Status |
|---|---|
| Strategy Engine (ORB/EMA/etc.) | Reused as-is |
| Signal Engine / SignalIntake | Reused as-is |
| Option Selector | **NOT BUILT — BLOCKING DEPENDENCY for Phase 5 completion** |
| Risk & Capital Engine | Reused (SL/Target logic); needs live-tick trigger wiring (OD-6) |
| HistoricalReplayFeed | **BUILT — permanent TEST / REPLAY / DEBUG / DETERMINISTIC VALIDATION infrastructure** (NOT operational paper trading) |
| Live Data Connector | **NOT BUILT — mandatory Phase 5 dependency** |
| ExecutionAdapter (OD-2) | **Architecture frozen — NOT YET IMPLEMENTED** |
| BacktestFillAdapter | Future: wraps existing verified ExecutionEngine |
| PaperFillAdapter | **NEW — bid/ask fills, latency, rejection, slippage bps** (OD-3) |
| LiveBrokerAdapter | Future: real broker execution path |
| Cost Model | **Infrastructure exists** (`CostCalculator`/`CostSchedule`); needs Zerodha schedule configuration |
| Virtual Ledger / Order Lifecycle | **Infrastructure exists** (`PortfolioAccount`/`AccountSnapshot`); multi-account = future |
| P&L Engine (live MTM) | **Bar-based MTM exists**; tick-level MTM = NEW |
| Protective Exits | **Bar-based evaluation exists**; live-price trigger path = NEW (OD-6) |
| Reconciliation/Audit/Recovery | NEW (D7, D9, D16) |
| Calibration Module | New process, not pure code — ongoing |

---

## 3. Explicit Dependency Order

> **Superseded by OD-7.** The original Section 3 listed Option Selector, Risk Engine, and one validated
> strategy as preconditions. The owner-approved Phase 5 implementation dependency order is:

> See **Section 3.1 — Owner-Approved Phase 5 Implementation Dependency Order (OD-7)** below.

### 3.1 Owner-Approved Phase 5 Implementation Dependency Order (OD-7)

1. HistoricalReplayFeed — **VERIFIED_COMPLETE** (permanent test/replay/debug infrastructure)
2. PaperTradingRunner replay/core orchestration
3. ExecutionAdapter architectural integration
4. PaperFillAdapter / simulated paper broker
5. Option Selector (**BLOCKING DEPENDENCY** — OD-4)
6. LiveDataFeed / real-time market data connector (including required option quote/bid/ask data)
7. Virtual account + live MTM integration
8. Live-price SL / Target / Trailing integration (OD-6)
9. SQLite full runtime-state persistence / recovery (D9)
10. Safety / kill switch / stale-data / disconnect handling (D8)
11. D16 logging / audit event implementation
12. Paper reconciliation (D7)
13. Multi-strategy + shared-capital verification
14. Full replay-pipeline regression verification
15. Actual live-market paper-trading verification
16. Final Phase 5 architecture + implementation audit
17. **PHASE 5 VERIFIED_COMPLETE**

The exact slicing may later be refined by read-only preflight audits, but dependencies must not violate the frozen owner decisions above.

---

## 4. Calibration (not MVP)

> Retained from original spec. Empirical calibration is a post-build process, not a code dependency.

---

## 5. Phase 5 Final Completion Gate (OD-1)

Phase 5 may be marked **VERIFIED_COMPLETE** only when ALL mandatory items are implemented and independently verified.

### MANDATORY:

**A. Replay/testing infrastructure**
- HistoricalReplayFeed preserved and verified
- Deterministic replay of paper pipeline
- Replay end-to-end regression path available

**B. Operational live paper trading**
- True live-market data connector operational
- Actual market-hour event processing
- Automatic strategies operating on unseen live data
- Automatic Option Selector operational for approved options strategies (**OD-4**)
- Live option contract/quote resolution
- PaperFillAdapter operational
- Bid/ask-based conservative fills (**OD-3**)
- Latency/slippage/stale-price/rejection behavior (**OD-3**)
- Applicable costs
- Configurable virtual capital
- Virtual positions
- Realized P&L
- Unrealized/live MTM P&L
- Protective exits against live price updates (**OD-6**)
- Multiple strategies with shared capital/risk rules
- SQLite runtime persistence (D9)
- Restart/recovery
- Kill switch/safety (D8)
- Stale data/disconnect handling
- Reconciliation (D7)
- D16-compatible logging/audit evidence

**C. Verification**
- Deterministic tests
- Regression tests
- Full repository tests
- Live-paper controlled validation
- No unresolved P0/P1 defects
- Final owner audit

### NOT SUFFICIENT FOR COMPLETION:

- HistoricalReplayFeed alone
- PaperTradingRunner replay alone
- Strategy signal generation alone
- Futures-only paper capability without automated Option Selector (**OD-4**)
- Fake LTP fills (**OD-3**)
- Completed-bar-only live protective monitoring (**OD-6**)
- Non-persistent virtual state

---

## 6. Promotion / Six-Month Rule (OD-1)

Existing D10 / Q67 / Q68 / Q120 owner contracts are preserved unless a direct conflict is discovered.

Phase 5 CODE COMPLETION and six-month operational paper evidence are distinct.

Do NOT automatically promote a strategy to real-money live trading.

Meeting numeric promotion criteria only makes a strategy **eligible for owner review**.
Final go-live remains **explicit manual owner approval** (Q120).

---

## 7. Paper Fill Realism V1 Scope (OD-3)

### MUST_HAVE_V1:
1. BUY simulated fill based on executable ASK-side market evidence
2. SELL simulated fill based on executable BID-side market evidence
3. Do NOT use naive LTP-only optimistic fills
4. Configurable slippage
5. Configurable signal-to-execution latency
6. Stale quote rejection / fail-closed behavior
7. Reject/avoid fabricated fills when price has moved beyond approved execution tolerance
8. Applicable brokerage/statutory/exchange costs included
9. Conservative execution behavior: impossible or unsupported fills must not be magically accepted

### PARTIAL FILLS:
- Do NOT require fake partial-fill modeling in v1 without reliable market-depth/liquidity evidence
- Partial fills become a later capability when available data and approved model can support them responsibly

### CALIBRATION_LATER:
- Empirical latency calibration
- Empirical slippage calibration
- Liquidity-depth calibration
- Advanced partial fills

### V2 / LATER:
- Queue-position simulation
- Market-impact modeling

### IMPORTANT:
- Do NOT claim that paper execution can be guaranteed 100% identical to exchange execution
- The goal is conservative, execution-realistic paper behavior
