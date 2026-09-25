# Laya Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a model-agnostic Laya integration shell to AlgoFortis so a future fine-tuned local model can perform strategy hunting, continuous market intelligence, independent opportunity detection, and bounded fast tasks without gaining broker or Live execution authority.

**Architecture:** Add an isolated `engine.ai.laya` package with immutable deterministic contracts, disabled-by-default configuration, explicit model provenance, an adapter/router boundary, continuous market freshness checks, a non-executable opportunity engine, and research-only strategy/fast-task services. The real model stays disconnected; tests use deterministic fake adapters only.

**Tech Stack:** CPython 3.13.14, stdlib dataclasses/enums/typing/datetime/decimal, existing `engine.reproducibility.codec.CanonicalCodec`, pytest, existing Windows GitHub Actions workflow.

**Spec:** `docs/superpowers/specs/2026-09-25-laya-integration-design.md`

## Global Constraints

- No Laya weights, tokenizer files, fine-tuning runtime, or new model dependency is added in this milestone.
- Default state is disabled and fail-closed. No silent fallback model is permitted.
- Laya code must not import broker mutation modules, order-placement modules, Live adapters, network clients, or auto-arm controls.
- Laya may emit a candidate while rule-based strategies are silent, but that candidate is never execution authority.
- Existing Live state stays `READ_ONLY/DISARMED`.
- Existing Phase-4 built-in promotion remains research-only and `NON_PROMOTABLE`.
- Authoritative confidence/score values use finite `Decimal` in the inclusive range zero to one.
- Every accepted timestamp is timezone-aware.
- Every material request/result identity uses `CanonicalCodec` with explicit field ordering.
- Branch `laya-integration` is stacked on Phase-4 head `20310e359eeeb13ee2b4e443717cf654466f68c4`.
- If PR #6 is still open when the Laya PR is created, the temporary base is `v2-phase4-strategy-research-backtest`. After PR #6 merges, retarget to `main` and require fresh exact-head CI.
- Do not merge the Laya PR without explicit owner authorization.

## Review Focus

1. Naive or stale market timestamps must fail closed before adapter inference.
2. Unknown or mismatched model provenance must be rejected.
3. Non-finite or out-of-range confidence/score values must be rejected.
4. Unsupported or disabled task roles must fail before adapter invocation.
5. Broker, Live, order, or network imports inside `engine/ai/laya` must fail static verification.

## File Map

Create:
- `engine/ai/__init__.py`
- `engine/ai/laya/__init__.py`
- `engine/ai/laya/contracts.py`
- `engine/ai/laya/config.py`
- `engine/ai/laya/model_registry.py`
- `engine/ai/laya/adapter.py`
- `engine/ai/laya/router.py`
- `engine/ai/laya/market_intelligence.py`
- `engine/ai/laya/opportunity_engine.py`
- `engine/ai/laya/strategy_hunter.py`
- `engine/ai/laya/fast_tasks.py`
- `build/tools/laya_probe.py`
- `tests_v1/test_laya_contracts.py`
- `tests_v1/test_laya_disabled_adapter.py`
- `tests_v1/test_laya_router.py`
- `tests_v1/test_laya_market_intelligence.py`
- `tests_v1/test_laya_opportunity_engine.py`
- `tests_v1/test_laya_strategy_hunter.py`
- `tests_v1/test_laya_fast_tasks.py`
- `tests_v1/test_laya_ci_guard.py`
- `tests_v1/test_laya_probe.py`

Modify:
- `build/tools/check_phase4_research_backtest.py`
- `.github/workflows/v2-phase0-baseline.yml`

Do not modify:
- `engine/strategy/promotion_v2.py`
- `engine/strategy/lifecycle_v2.py`
- broker adapters
- Live state machine
- order placement paths

---

### Task 1: Deterministic Laya Contracts

**Files:**
- Create: `engine/ai/__init__.py`
- Create: `engine/ai/laya/__init__.py`
- Create: `engine/ai/laya/contracts.py`
- Test: `tests_v1/test_laya_contracts.py`

**Interfaces:**
- Consumes: `CanonicalCodec.fingerprint`.
- Produces: `LayaContractError`, `LayaRole`, `MarketRegime`, `DirectionalBias`, `VolatilityState`, `OpportunityIntent`, `ModelProvenance`, `MarketIntelligenceRequest`, `MarketInsight`, `OpportunityCandidate`, `StrategyHuntRequest`, `StrategyCandidate`, `FastTaskRequest`, `FastTaskResult`.

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.contracts import (
    DirectionalBias,
    FastTaskRequest,
    LayaContractError,
    MarketInsight,
    MarketIntelligenceRequest,
    MarketRegime,
    ModelProvenance,
    VolatilityState,
)


def provenance():
    return ModelProvenance(
        model_id="laya-test",
        model_version="v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def test_market_request_fingerprint_is_deterministic():
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    first = MarketIntelligenceRequest.create(
        symbol="NIFTY", timeframe="5m", event_timestamp=now,
        features={"rsi": Decimal("61.2"), "atr": Decimal("42.1")},
        data_lineage="dataset@v1", existing_strategy_signals=(),
    )
    second = MarketIntelligenceRequest.create(
        symbol="nifty", timeframe="5m", event_timestamp=now,
        features={"atr": Decimal("42.1"), "rsi": Decimal("61.2")},
        data_lineage="dataset@v1", existing_strategy_signals=(),
    )
    assert first.fingerprint == second.fingerprint


def test_contracts_reject_naive_timestamp_and_nonfinite_confidence():
    with pytest.raises(LayaContractError):
        MarketIntelligenceRequest.create(
            symbol="NIFTY", timeframe="5m",
            event_timestamp=datetime(2026, 1, 5, 9, 30),
            features={"atr": Decimal("42")}, data_lineage="dataset@v1",
            existing_strategy_signals=(),
        )
    with pytest.raises(LayaContractError):
        MarketInsight.create(
            request_fingerprint="b" * 64,
            regime=MarketRegime.UPTREND,
            bias=DirectionalBias.BULLISH,
            volatility=VolatilityState.HIGH,
            event_tags=("REVERSAL_CANDIDATE",),
            confidence=Decimal("NaN"),
            produced_at=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
            provenance=provenance(),
        )


def test_fast_task_rejects_unknown_kind():
    with pytest.raises(LayaContractError):
        FastTaskRequest.create(
            task_kind="PLACE_ORDER",
            payload=(("symbol", "NIFTY"),),
            request_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        )
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests_v1/test_laya_contracts.py -q
```

Expected: import/collection failure because the Laya package does not exist.

- [ ] **Step 3: Implement contracts**

Use frozen, slotted dataclasses. Normalize symbol with `casefold()`. Normalize mappings to sorted tuples before hashing. Use schema names `algofortis-laya-market-request/v1`, `algofortis-laya-market-insight/v1`, `algofortis-laya-opportunity/v1`, `algofortis-laya-strategy-hunt/v1`, `algofortis-laya-strategy-candidate/v1`, `algofortis-laya-fast-request/v1`, and `algofortis-laya-fast-result/v1`.

Enums are fixed to:

```python
class LayaRole(str, Enum):
    MARKET_INTELLIGENCE = "MARKET_INTELLIGENCE"
    STRATEGY_HUNTING = "STRATEGY_HUNTING"
    FAST_TASKS = "FAST_TASKS"

class MarketRegime(str, Enum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"
    UNCERTAIN = "UNCERTAIN"

class DirectionalBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"

class VolatilityState(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    UNCERTAIN = "UNCERTAIN"

class OpportunityIntent(str, Enum):
    CE_CANDIDATE = "CE_CANDIDATE"
    PE_CANDIDATE = "PE_CANDIDATE"
```

Allowed fast-task kinds are exactly:

```python
ALLOWED_FAST_TASKS = frozenset({
    "REGIME_CLASSIFICATION",
    "REVERSAL_CLASSIFICATION",
    "BREAKOUT_CLASSIFICATION",
    "STRATEGY_RANKING",
    "FEATURE_SCORING",
    "SIGNAL_FILTERING",
    "CANDIDATE_PRUNING",
    "TRADE_QUALITY_SCORING",
    "RESEARCH_PRIORITY_RANKING",
})
```

Required constructors and fields:

```text
ModelProvenance(model_id, model_version, model_hash, adapter_version, feature_schema_version)
MarketIntelligenceRequest.create(symbol, timeframe, event_timestamp, features, data_lineage, existing_strategy_signals)
MarketInsight.create(request_fingerprint, regime, bias, volatility, event_tags, confidence, produced_at, provenance)
OpportunityCandidate.create(request, insight, intent, setup_type, evidence_tags, valid_until)
StrategyHuntRequest.create(dataset_refs, feature_schema_version, allowed_strategy_families, max_candidates, seed)
StrategyCandidate.create(entry_concept, exit_requirements, parameter_names, target_regimes, provenance)
FastTaskRequest.create(task_kind, payload, request_timestamp)
FastTaskResult.create(task_kind, request_fingerprint, ranked_items, provenance)
```

`StrategyCandidate.create` sets `status="RESEARCH_ONLY"`. `OpportunityCandidate.create` sets `source="LAYA"` and `status="CANDIDATE_ONLY"`. Every 64-hex identity is validated with a full lowercase-hex match.

- [ ] **Step 4: Run GREEN**

```powershell
python -m pytest tests_v1/test_laya_contracts.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/ai engine/ai/laya tests_v1/test_laya_contracts.py
git commit -m "feat: add deterministic Laya contracts"
```

---

### Task 2: Disabled Config, Registry, and Adapter Boundary

**Files:**
- Create: `engine/ai/laya/config.py`
- Create: `engine/ai/laya/model_registry.py`
- Create: `engine/ai/laya/adapter.py`
- Test: `tests_v1/test_laya_disabled_adapter.py`

**Interfaces:**
- Produces: `LayaConfig.disabled()`, `RegisteredLayaModel.ref`, `LayaModelRegistry.resolve`, `LayaAdapter`, `DisabledLayaAdapter`, `LayaUnavailable`, `LayaRegistryError`.

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.adapter import DisabledLayaAdapter, LayaUnavailable
from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import MarketIntelligenceRequest
from engine.ai.laya.model_registry import LayaModelRegistry, LayaRegistryError, RegisteredLayaModel


def test_disabled_config_has_no_enabled_roles_or_model():
    config = LayaConfig.disabled()
    assert config.enabled is False
    assert config.enabled_roles == ()
    assert config.model_ref is None


def test_registry_resolves_only_explicit_registered_ref():
    model = RegisteredLayaModel(
        model_id="laya-test", model_version="v1", model_hash="a" * 64,
        adapter_version="fake@v1", feature_schema_version="features@v1",
        local_path="models/laya/laya-test-v1",
    )
    registry = LayaModelRegistry((model,))
    assert registry.resolve("laya-test@v1") == model
    with pytest.raises(LayaRegistryError):
        registry.resolve("missing@v1")


def test_disabled_adapter_fails_closed():
    request = MarketIntelligenceRequest.create(
        symbol="NIFTY", timeframe="5m",
        event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        features={"atr": Decimal("42")}, data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )
    with pytest.raises(LayaUnavailable, match="disabled"):
        DisabledLayaAdapter().market_intelligence(request)
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests_v1/test_laya_disabled_adapter.py -q
```

- [ ] **Step 3: Implement exact fail-closed behavior**

```python
@dataclass(frozen=True, slots=True)
class LayaConfig:
    enabled: bool
    enabled_roles: tuple[LayaRole, ...]
    model_ref: str | None
    max_input_age_seconds: int

    @classmethod
    def disabled(cls) -> "LayaConfig":
        return cls(False, (), None, 0)
```

`RegisteredLayaModel.ref` returns `f"{model_id}@{model_version}"`. Registry construction rejects duplicate refs. `resolve()` strips input and raises `LayaRegistryError("model is not registered")` on a miss. `local_path` must be a non-empty relative path without URL scheme or UNC prefix.

Adapter contract methods are `market_intelligence(request)`, `strategy_hunt(request)`, and `fast_task(request)`. `DisabledLayaAdapter` implements all three and always raises `LayaUnavailable("Laya is disabled")` without fallback.

- [ ] **Step 4: Run GREEN**

```powershell
python -m pytest tests_v1/test_laya_disabled_adapter.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/ai/laya/config.py engine/ai/laya/model_registry.py engine/ai/laya/adapter.py tests_v1/test_laya_disabled_adapter.py
git commit -m "feat: add fail-closed Laya adapter boundary"
```

---

### Task 3: Provenance-Bound Router

**Files:**
- Create: `engine/ai/laya/router.py`
- Test: `tests_v1/test_laya_router.py`

**Interfaces:**
- Produces: `LayaRouter.route_market`, `LayaRouter.route_strategy_hunt`, `LayaRouter.route_fast_task`, `LayaRoutingError`.

- [ ] **Step 1: Write RED tests**

Use a deterministic fake adapter in the test file with a `calls` list. Pin three cases:

```python
def test_disabled_market_role_rejects_before_adapter_call():
    router = build_router(enabled_roles=())
    with pytest.raises(LayaRoutingError, match="role is disabled"):
        router.route_market(market_request())
    assert fake.calls == []


def test_unregistered_output_provenance_is_rejected():
    router = build_router(enabled_roles=(LayaRole.MARKET_INTELLIGENCE,), registered=False)
    with pytest.raises(LayaRoutingError, match="provenance"):
        router.route_market(market_request())


def test_registered_market_result_is_request_bound():
    router = build_router(enabled_roles=(LayaRole.MARKET_INTELLIGENCE,), registered=True)
    result = router.route_market(market_request())
    assert result.request_fingerprint == fake.calls[0][1]
    assert len(fake.calls) == 1
```

The test helpers create one registered model ref `laya-test@v1` and a fake `MarketInsight` whose model hash, adapter version, and feature schema match that registry entry.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests_v1/test_laya_router.py -q
```

- [ ] **Step 3: Implement router rules**

Constructor requires `LayaConfig`, `LayaModelRegistry`, and `LayaAdapter`. Every route method first checks `config.enabled is True` and the required role is in `enabled_roles`. Then it calls exactly one adapter method. After the call, resolve `model_id@model_version` and require exact equality for `model_hash`, `adapter_version`, and `feature_schema_version`. Market and fast-task results must carry the input request fingerprint. Strategy hunt must return no more than `max_candidates`.

- [ ] **Step 4: Run GREEN**

```powershell
python -m pytest tests_v1/test_laya_router.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/ai/laya/router.py tests_v1/test_laya_router.py
git commit -m "feat: add provenance-bound Laya router"
```

---

### Task 4: Continuous Market Freshness and Independent Opportunity Candidate

**Files:**
- Create: `engine/ai/laya/market_intelligence.py`
- Create: `engine/ai/laya/opportunity_engine.py`
- Test: `tests_v1/test_laya_market_intelligence.py`
- Test: `tests_v1/test_laya_opportunity_engine.py`

**Interfaces:**
- Produces: `MarketIntelligenceService.analyze`, `OpportunityEngine.from_insight`, `LayaMarketError`, `LayaOpportunityError`.

- [ ] **Step 1: Write market freshness tests**

```python
def test_stale_input_is_rejected_before_adapter_call():
    service = MarketIntelligenceService(router=router, max_input_age_seconds=30)
    request = request_at("2026-01-05T09:30:00+00:00")
    with pytest.raises(LayaMarketError, match="stale"):
        service.analyze(request, observed_at=aware("2026-01-05T09:31:00+00:00"))
    assert fake.calls == []


def test_fresh_input_reaches_router_once():
    service = MarketIntelligenceService(router=router, max_input_age_seconds=30)
    result = service.analyze(
        request_at("2026-01-05T09:30:00+00:00"),
        observed_at=aware("2026-01-05T09:30:15+00:00"),
    )
    assert result.request_fingerprint == fake.calls[0][1]
    assert len(fake.calls) == 1
```

`aware()` uses `datetime.fromisoformat`; `request_at()` creates the fixed market request used by the test.

- [ ] **Step 2: Write independent opportunity tests**

```python
def test_bearish_reversal_can_emit_pe_candidate_when_strategy_is_silent():
    candidate = OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
        request=request_without_strategy_signal,
        insight=bearish_reversal_insight,
        validity_seconds=60,
    )
    assert candidate is not None
    assert candidate.source == "LAYA"
    assert candidate.intent is OpportunityIntent.PE_CANDIDATE
    assert candidate.status == "CANDIDATE_ONLY"


def test_low_confidence_or_neutral_insight_emits_no_candidate():
    engine = OpportunityEngine(min_confidence=Decimal("0.70"))
    assert engine.from_insight(
        request=request_without_strategy_signal,
        insight=neutral_insight,
        validity_seconds=60,
    ) is None
```

Also assert `OpportunityCandidate.__dataclass_fields__` does not contain `broker`, `broker_id`, `quantity`, `price`, `order_type`, or `order_id`.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests_v1/test_laya_market_intelligence.py tests_v1/test_laya_opportunity_engine.py -q
```

- [ ] **Step 4: Implement exact market/opportunity rules**

`MarketIntelligenceService` rejects an unaware `observed_at`, a future input skew greater than five seconds, any input age greater than `max_input_age_seconds`, and non-positive `max_input_age_seconds`. Rejection happens before router invocation.

`OpportunityEngine` requires a finite `min_confidence` from zero through one. It verifies insight/request fingerprint binding. It creates a candidate only when `event_tags` contains `REVERSAL_CANDIDATE` or `BREAKOUT_CANDIDATE`, confidence meets threshold, and bias is directional. Bearish maps to `PE_CANDIDATE`; bullish maps to `CE_CANDIDATE`; neutral/uncertain returns `None`. `validity_seconds` must be positive. `valid_until` is `insight.produced_at + timedelta(seconds=validity_seconds)`.

- [ ] **Step 5: Run GREEN**

```powershell
python -m pytest tests_v1/test_laya_market_intelligence.py tests_v1/test_laya_opportunity_engine.py -q
```

- [ ] **Step 6: Commit**

```bash
git add engine/ai/laya/market_intelligence.py engine/ai/laya/opportunity_engine.py tests_v1/test_laya_market_intelligence.py tests_v1/test_laya_opportunity_engine.py
git commit -m "feat: add Laya market and opportunity services"
```

---

### Task 5: Research-Only Strategy Hunting and Bounded Fast Tasks

**Files:**
- Create: `engine/ai/laya/strategy_hunter.py`
- Create: `engine/ai/laya/fast_tasks.py`
- Test: `tests_v1/test_laya_strategy_hunter.py`
- Test: `tests_v1/test_laya_fast_tasks.py`

**Interfaces:**
- Produces: `StrategyHunter.hunt`, `FastTaskService.run`, `LayaStrategyHuntError`, `LayaFastTaskError`.

- [ ] **Step 1: Write RED tests**

```python
def test_strategy_hunter_keeps_all_candidates_research_only():
    candidates = StrategyHunter(router).hunt(request)
    assert candidates
    assert all(item.status == "RESEARCH_ONLY" for item in candidates)


def test_strategy_hunter_rejects_adapter_budget_overrun():
    with pytest.raises(LayaStrategyHuntError, match="max_candidates"):
        StrategyHunter(overproducing_router).hunt(request_with_max_one)


def test_fast_task_result_is_bound_to_request():
    result = FastTaskService(router).run(fast_request)
    assert result.request_fingerprint == fast_request.fingerprint
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests_v1/test_laya_strategy_hunter.py tests_v1/test_laya_fast_tasks.py -q
```

- [ ] **Step 3: Implement thin services**

`StrategyHunter.hunt()` calls only `router.route_strategy_hunt()`, rejects a result count above request budget, rejects any candidate whose status is not `RESEARCH_ONLY`, and returns the tuple unchanged otherwise. It does not import promotion or lifecycle authorities.

`FastTaskService.run()` calls only `router.route_fast_task()`, requires matching `request_fingerprint` and `task_kind`, and returns the result. Unsupported task kinds are already rejected by `FastTaskRequest.create()` before routing.

- [ ] **Step 4: Run GREEN**

```powershell
python -m pytest tests_v1/test_laya_strategy_hunter.py tests_v1/test_laya_fast_tasks.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/ai/laya/strategy_hunter.py engine/ai/laya/fast_tasks.py tests_v1/test_laya_strategy_hunter.py tests_v1/test_laya_fast_tasks.py
git commit -m "feat: add Laya research and fast-task services"
```

---

### Task 6: Static Broker/Live/Order/Network Boundary

**Files:**
- Modify: `build/tools/check_phase4_research_backtest.py`
- Test: `tests_v1/test_laya_ci_guard.py`

**Interfaces:**
- Consumes existing `REQUIRED`, `SCOPES`, `FORBIDDEN`, `verify()`.
- Produces Laya static scope and required-presence coverage.

- [ ] **Step 1: Write RED guard tests**

```python
from build.tools.check_phase4_research_backtest import REQUIRED, verify


def test_laya_scope_rejects_broker_live_order_and_network_imports(tmp_path):
    samples = {
        "broker.py": "from engine.broker_adapters import mock_broker\n",
        "live.py": "from engine.live import state\n",
        "orders.py": "from engine.orders import lifecycle\n",
        "network.py": "import httpx\n",
    }
    for name, source in samples.items():
        file = tmp_path / "engine" / "ai" / "laya" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source, encoding="utf-8")
    assert len(verify(tmp_path, check_presence=False)) == 4


def test_laya_required_authorities_are_pinned():
    expected = {
        "engine/ai/laya/contracts.py",
        "engine/ai/laya/config.py",
        "engine/ai/laya/model_registry.py",
        "engine/ai/laya/adapter.py",
        "engine/ai/laya/router.py",
        "engine/ai/laya/market_intelligence.py",
        "engine/ai/laya/opportunity_engine.py",
        "engine/ai/laya/strategy_hunter.py",
        "engine/ai/laya/fast_tasks.py",
        "tests_v1/test_laya_contracts.py",
        "tests_v1/test_laya_disabled_adapter.py",
        "tests_v1/test_laya_router.py",
        "tests_v1/test_laya_market_intelligence.py",
        "tests_v1/test_laya_opportunity_engine.py",
        "tests_v1/test_laya_strategy_hunter.py",
        "tests_v1/test_laya_fast_tasks.py",
        "tests_v1/test_laya_ci_guard.py",
    }
    assert expected <= set(REQUIRED)
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests_v1/test_laya_ci_guard.py -q
```

- [ ] **Step 3: Harden guard**

Append `engine/ai/laya` to `SCOPES`. Append `engine.live` and `engine.orders` to `FORBIDDEN`; retain all existing bans. Append the Laya authority/test paths from the test above to `REQUIRED`. Do not remove or relax any existing Phase-4 entry.

- [ ] **Step 4: Run GREEN**

```powershell
python build/tools/check_phase4_research_backtest.py
python -m pytest tests_v1/test_laya_ci_guard.py -q
```

- [ ] **Step 5: Commit**

```bash
git add build/tools/check_phase4_research_backtest.py tests_v1/test_laya_ci_guard.py
git commit -m "test: enforce Laya execution boundaries"
```

---

### Task 7: Deterministic Probe and Dual-Windows Qualification

**Files:**
- Create: `build/tools/laya_probe.py`
- Test: `tests_v1/test_laya_probe.py`
- Modify: `build/tools/check_phase4_research_backtest.py`
- Modify: `.github/workflows/v2-phase0-baseline.yml`

**Interfaces:**
- Produces a fixed deterministic fake-model fingerprint output and cross-Windows equality check.

- [ ] **Step 1: Write RED probe test**

```python
from build.tools.laya_probe import run


def test_laya_probe_is_deterministic_and_non_executable():
    first = run()
    second = run()
    assert first == second
    assert first["OPPORTUNITY_STATUS"] == "CANDIDATE_ONLY"
    assert first["STRATEGY_SIGNAL_COUNT"] == "0"
    assert first["DEFAULT_LIVE_STATE"] == "READ_ONLY/DISARMED"
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests_v1/test_laya_probe.py -q
```

- [ ] **Step 3: Implement probe**

Use fixed timestamp `2026-01-05T09:30:00+00:00`, symbol `NIFTY`, timeframe `5m`, features `atr=42.1` and `rsi=68.2`, registered fake model `laya-test@v1`, hash of 64 `a` characters, adapter `fake@v1`, feature schema `features@v1`, and fake bearish reversal confidence `0.81`. The request has zero existing strategy signals. Run through `LayaRouter`, `MarketIntelligenceService`, and `OpportunityEngine(min_confidence=Decimal("0.70"))`.

`run()` returns string values for these keys and the CLI prints them in exactly this order:

```text
MARKET_REQUEST=<64 lowercase hex>
MARKET_INSIGHT=<64 lowercase hex>
LAYA_OPPORTUNITY=<64 lowercase hex>
OPPORTUNITY_STATUS=CANDIDATE_ONLY
STRATEGY_SIGNAL_COUNT=0
DEFAULT_LIVE_STATE=READ_ONLY/DISARMED
```

- [ ] **Step 4: Pin probe files in static required list**

Add `build/tools/laya_probe.py` and `tests_v1/test_laya_probe.py` to `REQUIRED`.

- [ ] **Step 5: Extend both Windows jobs**

After existing Phase-4 focused validation, add:

```yaml
      - name: Laya integration focused validation
        shell: pwsh
        run: python -m pytest tests_v1 -k laya -q
      - name: Laya deterministic fingerprint probe
        shell: pwsh
        run: python build/tools/laya_probe.py | Set-Content laya.txt
```

Upload `laya-fingerprint-a` in Windows A and `laya-fingerprint-b` in Windows B. Add a job named `Laya cross-Windows deterministic fingerprint comparison` that downloads both artifacts and fails when raw `laya.txt` contents differ. Preserve the existing Phase-4 G4 comparison unchanged.

- [ ] **Step 6: Run local qualification**

```powershell
python build/tools/check_phase4_research_backtest.py
python build/tools/laya_probe.py
python -m pytest tests_v1 -k laya -q
```

- [ ] **Step 7: Commit**

```bash
git add build/tools/laya_probe.py tests_v1/test_laya_probe.py build/tools/check_phase4_research_backtest.py .github/workflows/v2-phase0-baseline.yml
git commit -m "ci: qualify Laya integration across Windows"
```

---

### Task 8: Full Regression and Stacked PR

**Files:**
- Modify only when a verification failure identifies a defect in a Task 1-7 file.
- No merge action belongs to this task.

- [ ] **Step 1: Run static/compile gates**

```powershell
python -m compileall -q engine dashboard/backend build/tools tests_v1
python build/tools/check_module_boundaries.py
python build/tools/check_phase1_foundation.py
python build/tools/check_phase2_safety_spine.py
python build/tools/check_phase3_data_v2.py
python build/tools/check_phase4_research_backtest.py
```

Every command must exit zero.

- [ ] **Step 2: Run focused suites**

```powershell
python -m pytest tests_v1 -k laya -q
python -m pytest tests_v1 -k phase4 -q
```

Both must pass.

- [ ] **Step 3: Run full regression**

```powershell
python -m pytest tests_v1 -q
python build/tools/run_regression_certification.py
```

Both must pass.

- [ ] **Step 4: Verify diff and prohibited imports**

```powershell
git diff --name-only 20310e359eeeb13ee2b4e443717cf654466f68c4..HEAD
git grep -n -E "engine\.broker_adapters|engine\.live|engine\.orders|engine\.execution\.live|import requests|import httpx|import socket" -- engine/ai/laya
```

The changed-file list must contain only planned Laya/docs/guard/workflow/test files. The grep command must return no prohibited Laya import.

- [ ] **Step 5: Verify fail-closed defaults**

```powershell
@'
from engine.ai.laya.config import LayaConfig
from engine.strategy.promotion_v2 import PromotionProfile, evaluate_promotion

assert LayaConfig.disabled().enabled is False
assert evaluate_promotion(PromotionProfile.research_only(), {}).status == "NON_PROMOTABLE"
print("LAYA_DISABLED=PASS")
print("PROMOTION_FAIL_CLOSED=PASS")
print("LIVE_STATE=READ_ONLY/DISARMED")
'@ | python -
```

- [ ] **Step 6: Create stacked PR without merge**

If PR #6 is open, create:

```text
base: v2-phase4-strategy-research-backtest
head: laya-integration
title: Laya integration: model-agnostic fast intelligence shell
```

PR body must state that the real model is not connected, default adapter is disabled, strategy hunting is research-only, Laya-only opportunities are candidate-only, broker/Live/order/network imports are blocked, Live remains `READ_ONLY/DISARMED`, and built-in promotion remains `NON_PROMOTABLE`.

After PR #6 merges, retarget the Laya PR to `main`, verify the diff is Laya-only, and require fresh exact-head success for:

```text
Current HEAD regression A (Windows latest / Python 3.13.14)
Current HEAD regression B (Windows 2022 / Python 3.13.14)
G4 cross-Windows deterministic fingerprint comparison
Laya cross-Windows deterministic fingerprint comparison
```

- [ ] **Step 7: Stop before merge**

Report exactly:

```text
Implemented: Laya integration shell
Verified: local static/focused/full regression + exact-head dual-Windows CI
Model: NOT CONNECTED
Live: READ_ONLY/DISARMED
Promotion: NON_PROMOTABLE
Remaining shared-branch action: owner-approved merge only
```

Do not merge without a new explicit owner instruction.
