# AlgoFortis Laya Integration Design

Date: 2026-09-25
Status: Design approved in chat; implementation not started
Branch: `laya-integration`
Base: Phase-4 head `20310e359eeeb13ee2b4e443717cf654466f68c4`

## 1. Goal

Create a model-agnostic Laya integration layer inside AlgoFortis now, while leaving the actual fine-tuned Laya model disconnected until it is trained, validated, and explicitly enabled.

Laya will be the fast-intelligence layer for:

1. strategy hunting,
2. continuous market-behaviour understanding,
3. independent opportunity detection when rule-based strategies are silent,
4. fast ranking/filtering/scoring tasks,
5. future routing to specialized fine-tuned Laya variants if needed.

The integration must preserve current AlgoFortis research, safety, audit, and execution boundaries.

## 2. Non-goals for this change

This change does not:

- ship or fine-tune a Laya model,
- download model weights,
- enable broker mutation,
- enable unrestricted real-money execution,
- bypass RiskGate or strategy promotion evidence,
- claim Laya signals are profitable before validation,
- change the existing Phase-4 promotion policy from fail-closed research-only behaviour.

## 3. Architectural Position

Laya is not embedded directly into a strategy or broker adapter. It sits between normalized AlgoFortis data/features and existing research/strategy/orchestration authorities.

```text
Market / Research / Strategy Inputs
                |
                v
        Laya Fast Intelligence
        |       |        |
        |       |        +--> Fast Tasks
        |       +-----------> Market Intelligence
        +-------------------> Strategy Hunting
                |
                v
      Candidate / Insight Contracts
                |
        +-------+---------+
        |                 |
        v                 v
 Research / Backtest   Signal Arbiter
        |                 |
        v                 v
 WFO/OOS/Robustness     RiskGate
        |                 |
        +--------+--------+
                 v
          Paper / approved execution
```

Laya produces evidence-bearing candidates and insights. Existing AlgoFortis authorities decide what happens next.

## 4. Proposed Package

Create a new isolated package:

```text
engine/
  ai/
    __init__.py
    laya/
      __init__.py
      contracts.py
      adapter.py
      config.py
      model_registry.py
      router.py
      strategy_hunter.py
      market_intelligence.py
      opportunity_engine.py
      fast_tasks.py
```

Initial tests:

```text
tests_v1/
  test_laya_contracts.py
  test_laya_disabled_adapter.py
  test_laya_router.py
  test_laya_market_intelligence.py
  test_laya_opportunity_engine.py
  test_laya_strategy_hunter.py
```

No model binary is committed as part of this work.

## 5. Core Contracts

### 5.1 Requests

`MarketIntelligenceRequest`
- symbol/instrument identity
- timeframe / event timestamp
- normalized market features
- source fingerprint / data lineage
- optional existing strategy signals

`StrategyHuntRequest`
- dataset/evidence references
- feature schema version
- search constraints and budget
- allowed strategy family boundaries

`FastTaskRequest`
- task kind
- bounded input payload
- deterministic request id
- optional timeout/budget metadata

### 5.2 Outputs

`MarketInsight`
- regime: uptrend / downtrend / sideways / uncertain
- directional bias: bullish / bearish / neutral / uncertain
- volatility state
- event tags such as breakout / exhaustion / reversal-candidate
- confidence score with model/version provenance
- timestamp and input fingerprint

`OpportunityCandidate`
- source = `LAYA`
- direction / instrument intent such as CE-candidate or PE-candidate where applicable
- setup type
- evidence tags
- confidence
- expiry/validity window
- model id/version
- input fingerprint
- status = candidate only, never execution authority

`StrategyCandidate`
- hypothesis id
- entry concept
- exit/protective-policy requirements
- parameter schema
- target regimes
- evidence/provenance
- never marked promotable until existing research gates pass

`FastTaskResult`
- task kind
- ranked/scored/filter result
- model/version provenance
- deterministic request id

## 6. Adapter Boundary

All AlgoFortis code talks to one interface, not directly to a specific runtime.

```text
LayaAdapter
  |- DisabledLayaAdapter   (default now)
  |- LocalLayaAdapter      (future)
  |- ONNXLayaAdapter       (optional future)
  |- PyTorchLayaAdapter    (optional future)
  `- RemoteLayaAdapter     (optional future, only if explicitly allowed)
```

Initial state is `DisabledLayaAdapter`.

When disabled, calls fail closed with a typed `LayaUnavailable`/disabled result rather than silently falling back to another model.

## 7. Continuous Market Behaviour

Laya should be able to observe the market independently of rule-based strategy signals.

The preferred runtime pattern is hybrid rather than running a heavy model on every tick:

1. normalized market features update continuously,
2. cheap deterministic/event detectors watch for meaningful changes,
3. an inference trigger fires on selected events and/or candle close,
4. Laya emits a new `MarketInsight`,
5. stale insights expire automatically.

Example:

```text
Existing strategy: HOLD / no signal
Market regime: uptrend
New evidence: momentum weakening + reversal structure
Laya output: bearish reversal candidate / PE candidate
```

A silent rule-based strategy does not force Laya to stay silent.

## 8. Independent Opportunity Engine

`opportunity_engine.py` converts market intelligence into bounded candidates.

It may create an `OpportunityCandidate` even when no conventional strategy generated a signal.

It must not:

- place an order,
- call a broker adapter,
- mutate Live state,
- bypass RiskGate,
- create promotion evidence from unverified model confidence alone.

Expected flow:

```text
Laya market insight
      |
      v
OpportunityCandidate
      |
      v
Signal Arbiter / policy
      |
      v
RiskGate
      |
      v
Paper validation first
```

Laya-alone signals must be ledgered separately so their real contribution can be measured without mixing them with strategy-originated trades.

## 9. Strategy Hunting

`strategy_hunter.py` uses Laya only to produce research hypotheses/candidates.

A Laya-generated strategy must enter the existing Phase-4 research path:

```text
Laya hypothesis
  -> experiment registry
  -> Backtest V2
  -> WFO/OOS
  -> robustness/stress
  -> overfitting evidence
  -> promotion gate
```

Laya confidence, natural-language reasoning, or one backtest result is never sufficient promotion evidence.

## 10. Fast Task Router

`router.py` is the single entry point for Laya work.

Supported initial task classes:

- market regime classification,
- reversal/breakout candidate classification,
- strategy-candidate ranking,
- feature scoring,
- signal filtering,
- candidate pruning,
- trade-quality scoring for research/paper evidence,
- research-priority ranking.

The router should reject unsupported task types explicitly.

## 11. Future Fine-Tuned Model Connection

Future model files are expected outside core code, for example:

```text
models/
  laya/
    laya-algofortis-v1/
      <runtime-specific model files>
      metadata.json
```

Runtime config concept:

```yaml
enabled: true
provider: local
model:
  id: laya-algofortis-v1
  path: models/laya/laya-algofortis-v1
roles:
  strategy_hunting: true
  market_intelligence: true
  fast_tasks: true
```

Connection sequence after fine-tuning:

1. place/export the validated model into the configured model directory,
2. register its immutable model id/version and metadata,
3. select the matching adapter/runtime,
4. run adapter contract tests,
5. run offline replay/backtest evaluation,
6. run OOS/WFO/robustness evaluation for strategy-oriented outputs,
7. run paper-mode validation for live-market candidates,
8. enable only the approved Laya roles.

AlgoFortis consumers remain unchanged because they depend only on the adapter/contracts.

## 12. Model Registry and Provenance

Every Laya output must carry enough provenance to reconstruct what produced it:

- model id,
- model version/hash,
- adapter/runtime version,
- feature/schema version,
- request/input fingerprint,
- timestamp,
- role/task kind.

Unknown or unregistered model versions fail closed.

## 13. Safety and Execution Boundaries

Laya code must remain broker-neutral.

The Laya package cannot import or invoke:

- broker mutation APIs,
- Live execution adapters,
- order-placement functions,
- auto-arm controls.

Initial integration is research/paper capable only.

Existing Live state remains `READ_ONLY/DISARMED`. Existing fail-closed promotion behaviour remains unchanged.

A future decision to permit any Laya-originated live action requires a separate reviewed change after evidence-backed validation; it is not part of this design.

## 14. Failure Behaviour

Fail closed for:

- model missing,
- model disabled,
- unsupported task,
- invalid schema,
- stale market input,
- unknown model/version,
- non-finite confidence/score,
- malformed output,
- inference timeout/error.

No failure may silently convert into an execution instruction.

## 15. Audit and Ledgering

Every material Laya request/result used in research or paper decision-making should be auditable.

At minimum log/reference:

- deterministic request id,
- input fingerprint,
- model provenance,
- task role,
- output/candidate id,
- downstream disposition: rejected / research-only / paper-evaluated / expired.

Strategy-originated and Laya-originated candidates remain distinguishable.

## 16. Testing Strategy

Implementation follows TDD.

Minimum tests:

1. disabled adapter is default and fail-closed,
2. contracts are immutable/deterministic where required,
3. invalid or stale market inputs are rejected,
4. opportunity engine can emit a Laya-only candidate when strategy signal is absent,
5. Laya-only candidate cannot call execution/broker code,
6. unsupported fast task is rejected,
7. model registry rejects unknown versions,
8. strategy-hunter output enters research state only,
9. deterministic request/input fingerprints are stable,
10. existing Phase-4 full regression remains green.

A static boundary guard should include the new `engine/ai/laya` package and reject broker/live/network imports not explicitly permitted by the final implementation plan.

## 17. Initial Delivery Boundary

The first implementation should stop at a production-quality integration shell:

- contracts,
- disabled adapter,
- router,
- model registry/config,
- market-intelligence interface,
- opportunity-candidate interface,
- strategy-hunter interface,
- tests and static safety guard.

No real Laya model is required for this milestone. Tests may use deterministic fake adapters only.

## 18. Acceptance Criteria

The placeholder integration is complete when:

- AlgoFortis has a stable Laya package and adapter contract,
- default state has no model enabled,
- a deterministic fake adapter proves strategy-hunting, market-intelligence, fast-task, and Laya-only opportunity flows,
- Laya candidates remain separated from execution authority,
- broker/live mutation imports are blocked by tests/static checks,
- existing Phase-4 regression and safety invariants remain green,
- future fine-tuned model connection requires only adapter/config/model registration work rather than a core architecture rewrite.
