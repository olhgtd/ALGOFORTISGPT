# AlgoFortis — Runtime Latency and Performance Requirements

**Status:** Owner-approved mandatory future architecture contract.  
**Scope:** Paper Trading, Live deployment, broker orchestration, and the runtime
boundaries that support them. This document defines requirements and acceptance
gates only; it does not implement instrumentation, benchmarks, Paper Trading,
Live Trading, broker integration, asynchronous infrastructure, or a UI.

## 1. Authority and placement

This is the detailed cross-phase performance authority for the existing
mandatory `requirements-freeze-125.md` **Phase X – Performance** capability.
It supplements, and does not override, frozen requirements, architecture
rules, approved Backtest Engine decisions, or verified public contracts.

## 2. Critical runtime path and latency scopes

The future synchronous trading path is:

```text
market event received
→ normalized/validated event available
→ strategy evaluation
→ risk/authorization decision
→ concrete order ready for broker submission
```

Where a broker adapter is active, the additional boundary is:

```text
concrete order ready → broker-adapter submission invoked
```

Performance evidence must distinguish, and must not combine, these separate
latencies:

1. **AlgoFortis internal latency:** receipt through internal decision/order
   preparation.
2. **Broker/network/API latency:** time after the adapter submission boundary
   attributable to transport and broker API processing.
3. **Exchange acknowledgement/fill latency:** external acknowledgement or fill
   time after broker/API submission.

## 3. Memory-first, event-driven hot-path rule

The Paper/Live critical path must be memory-first and event-driven. Required
runtime configuration and state must already be available in memory or through
an approved low-latency state boundary before a trading decision is made.

The synchronous hot path must not require blocking disk reads, file parsing,
database reporting queries, dashboard rendering, report generation, historical
analytics, unnecessary serialization/export, external AI/LLM inference, or
reference-repository/documentation research.

Non-critical support work may be outside the synchronous path where correctness
allows it, including UI refresh, reporting, analytics, export, verbose logs,
dashboard statistics, and historical summaries. Audit-critical evidence must
not be lost. Any future asynchronous handling must retain deterministic,
auditable records and explicit failure behavior.

## 4. Development reference routing is not runtime behavior

`REFERENCE_ROUTING_RULES.md` governs development and engineering agents only.
It must never be interpreted as Paper/Live market-event behavior. Runtime
market events must not trigger Backtrader, vectorbt, Freqtrade, Zipline, or
KiteConnect source reads, documentation analysis, or repository research.

## 5. Mandatory future latency instrumentation

Future runtime instrumentation must capture this ordered measurement chain:

| Timestamp | Boundary |
|---|---|
| T0 | Market event received by AlgoFortis |
| T1 | Normalized event ready |
| T2 | Strategy evaluation complete |
| T3 | Risk/authorization complete |
| T4 | Concrete order ready |
| T5 | Broker-adapter submission invoked |

Derived elapsed measurements include normalization, strategy, risk,
order-construction, total internal decision latency (`T4 - T0`), and internal
submission latency (`T5 - T0`). Implementations must use monotonic,
high-resolution process timing for elapsed latency; wall-clock timestamps alone
are insufficient for benchmarking.

## 6. Benchmark establishment and acceptance gates

No hard millisecond threshold is approved yet. AlgoFortis must not invent a
10 ms, 100 ms, one-second, or other latency target without realistic Paper
Trading evidence.

### Stage A — Paper benchmark establishment

Paper Trading/performance validation must measure latency distributions under
realistic configured load, identify bottlenecks, and establish owner-approved
latency budgets.

### Stage B — Live promotion gate

Before Phase 7 Live/Zerodha deployment, the approved budgets must pass. Any
regression above an approved limit blocks Live promotion. Completion of Paper
Trading alone never authorizes Live if this performance gate fails.

Future reports must include at least sample count, median/p50, p95, p99, and
maximum observed latency, with per-stage distributions where useful. Average
latency alone is insufficient.

## 7. Required load scenarios and regression evidence

Future benchmarks must cover at least:

- single strategy / single stream;
- multiple strategies;
- multi-symbol and multi-timeframe inputs;
- same-timestamp event batches;
- multiple simultaneous signals;
- Paper Trading broker-simulation path;
- logging/audit enabled; and
- realistic configured strategy load.

An empty or no-op strategy benchmark alone is insufficient. Once budgets are
approved, relevant runtime changes require a repeatable performance-regression
workflow using known configuration, event/dataset fixture, strategy set, and
hardware/environment metadata. Correctness tests must not be mixed with noisy
microbenchmark assertions.

## 8. AI/LLM, backpressure, and correctness boundaries

Core deterministic strategy execution must not depend on a slow LLM/AI call
unless a separately approved strategy expressly requires it and defines its
latency and failure semantics. A slow or unavailable local model must not
silently block ordinary deterministic strategies. Future AI advisory/analysis
work should remain outside the critical path wherever possible.

Before Live, Paper/Live orchestration must have an explicit owner-approved
queue, backpressure, and lag policy. It must never silently drop or reorder
events, use future evidence, fabricate completion, or submit delayed orders
without provenance. The exact policy is intentionally not invented here.

Correctness, determinism, no-look-ahead, provenance, and risk controls must
never be disabled for speed. Forbidden shortcuts include skipping validation,
bypassing risk checks, using incomplete bars, dropping provenance, reordering
same-timestamp evidence, and unsafe shared mutable strategy state.

## 9. Benchmark provenance and future UI

Benchmark evidence should retain CPU, RAM, OS, Python version, AlgoFortis
version/commit or build fingerprint, strategy set/version, number of
symbols/timeframes, and benchmark configuration. GPU hardware is not mandatory
for deterministic core execution.

A future UI may display or configure latency measurements, benchmark status,
warnings, approved performance profiles, and environment information. It is
not the authoritative measurement engine; instrumentation and benchmark
evidence remain runtime/domain owned.

## 10. Implementation status

Runtime instrumentation, benchmark tooling, asynchronous support-work
infrastructure, Paper Trading performance validation, Live broker performance
validation, and the owner-approved backpressure policy are mandatory future
work. None is implemented by this contract.
