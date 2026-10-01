# ADR-017 — Laya Market Intelligence Role

| Field | Value |
|---|---|
| Date | 2026-09-29 |
| Status | **FROZEN — Owner decision** |
| Scope | AlgoFortis V2 AI / agent architecture |
| Related | `AF2-AIA-001` through `AF2-AIA-007`, Architecture §11 |

## Decision

**Laya is a Market Intelligence Agent only. Laya is not a router, orchestrator, task dispatcher, provider selector, or agent controller.**

Routing and orchestration belong to the **Prime Agent / Agent Orchestrator**. The existing provider-registry concept (`AF2-AIA-002`) remains generic infrastructure owned by orchestration/configuration; it must not be implemented as a Laya responsibility.

## Laya responsibilities

Laya may:

- continuously analyse authoritative market data available through approved data ports;
- classify market regime and multi-timeframe context;
- analyse price structure, momentum, volatility, volume, support/resistance, breakouts/reversals and session context;
- consume authoritative options context when available, including strikes, CE/PE observations, OI, volume, bid/ask/spread, IV and Greeks where the selected data source provides them;
- produce structured market observations, hypotheses, `TradeCandidate` / `NO-TRADE` outputs and supporting evidence;
- operate in research/shadow scope subject to the normal strategy lifecycle, deterministic validation and Risk Gate constraints.

## Explicitly removed / prohibited responsibilities

Laya must **not**:

- decide which specialist agent receives a task;
- dispatch work to Research Agent, Risk Challenger or other agents;
- choose or switch AI providers/models for other agents;
- own provider fallback/routing policy;
- coordinate the overall multi-agent workflow;
- bypass deterministic validation, strategy rules, Risk Gate or execution controls;
- access broker mutation authority or place/cancel/modify orders directly.

## Orchestration ownership

The intended responsibility split is:

```text
Prime Agent / Agent Orchestrator
    ├── Research Agent
    ├── Risk Challenger
    └── Laya — Market Intelligence only
```

The Prime Agent / Agent Orchestrator owns task delegation, workflow coordination and provider/model routing through the provider registry/configuration layer.

Laya publishes market intelligence into that workflow; it does not control the workflow.

## Safety invariants

This decision does not weaken existing AlgoFortis safety rules:

- AI remains advisory by default.
- Laya has no direct broker or database mutation authority.
- Laya output is never an executable broker command.
- AI candidates still pass deterministic validation and the normal strategy/risk lifecycle.
- RiskGate remains the only authority capable of producing an executable approved order.
- Live remains `READ_ONLY / DISARMED` until separately qualified and Owner-approved.

## Implementation impact

At the time of this decision, the repository contains **no dedicated Laya-Router component/path to remove**. Therefore this ADR freezes the contract before Phase-8 agent implementation: future code must not introduce Laya-owned routing.

Generic `Agent Orchestrator` / provider-registry routing in the V2 architecture is retained, but ownership is Prime/orchestration infrastructure rather than Laya.

## Acceptance criteria

When the AI/agent phase is implemented:

1. No `LayaRouter`, `Laya-Router`, or equivalent Laya-owned routing component exists.
2. Laya's public contract exposes market-intelligence inputs/outputs only, not agent-dispatch/provider-selection methods.
3. Agent/task/provider routing tests target Prime/orchestrator/provider-registry components, not Laya.
4. Laya tests cover market-intelligence behaviour, provenance, freshness, shadow/research boundaries and fail-closed handling.
5. Any attempt to give Laya broker mutation or order authority fails architecture/safety tests.
