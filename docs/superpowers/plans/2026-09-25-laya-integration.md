# Laya Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-quality, model-agnostic Laya integration shell to AlgoFortis so a future fine-tuned local Laya model can perform strategy hunting, continuous market intelligence, independent opportunity detection, and bounded fast tasks without gaining broker or Live execution authority.

**Architecture:** Add an isolated `engine.ai.laya` package with immutable deterministic contracts, an adapter boundary, fail-closed configuration/model registry, a router, market-intelligence and opportunity services, and research-only strategy-hunting/fast-task services. The actual model stays disconnected; deterministic fake adapters are used only in tests. Existing Phase-4 promotion, RiskGate, broker, Live, and execution authorities remain unchanged.

**Tech Stack:** CPython 3.13.14, stdlib dataclasses/enums/typing/datetime/decimal, existing `engine.reproducibility.codec.CanonicalCodec`, pytest, existing Windows GitHub Actions workflow.

**Spec:** `docs/superpowers/specs/2026-09-25-laya-integration-design.md`

## Global Constraints

- No model weights, tokenizer files, fine-tuning runtime, or external model dependency is added in this milestone.
- Default state is disabled and fail-closed; no silent fallback to another model is permitted.
- Laya code must not import broker mutation modules, order-placement modules, Live adapters, network clients, or auto-arm controls.
- Laya may emit research/paper candidates even when rule-based strategies are silent, but those outputs are never execution authority.
- Existing Live state remains `READ_ONLY/DISARMED`.
- Existing Phase-4 built-in promotion policy remains research-only and `NON_PROMOTABLE` until separate evidence-backed criteria exist.
- Money/price/risk-like numeric values and confidence values use finite `Decimal` where authoritative evidence is involved; no binary floating-point is introduced into Laya evidence contracts.
- All timestamps accepted into Laya evidence contracts are timezone-aware.
- All material request/result identities use `CanonicalCodec`; no `repr()`, Python `hash()`, ad-hoc JSON hash, or delimiter-concatenation identity is added.
- `laya-integration` is stacked on Phase-4 head `20310e359eeeb13ee2b4e443717cf654466f68c4`. If PR #6 is still open when the Laya PR is created, use `v2-phase4-strategy-research-backtest` as the temporary PR base. After PR #6 merges, retarget the Laya PR to `main` and re-run exact-head CI before merge consideration.
- Do not merge the Laya PR without explicit owner authorization.

## Review Focus

1. **Naive or stale timestamps:** naive timestamps or market inputs older than the configured freshness window must fail closed rather than produce a candidate. Covered in Task 4.
2. **Unregistered model provenance:** an output that names an unknown model id/version/hash must be rejected even if its content otherwise looks valid. Covered in Task 2 and Task 3.
3. **Non-finite/out-of-range scores:** `NaN`, infinity, negative confidence, or confidence above one must be rejected at contract construction. Covered in Task 1.
4. **Unsupported routing task:** an unknown fast-task or disabled Laya role must raise a typed error and must not fall through to any adapter method. Covered in Task 3 and Task 5.
5. **Execution boundary regression:** any direct Laya import of broker/Live/order/network modules must be caught by static tests and CI. Covered in Task 6 and Task 7.

---

## File Map

Create:
- `engine/ai/__init__.py` — package boundary marker only.
- `engine/ai/laya/__init__.py` — public Laya API exports.
- `engine/ai/laya/contracts.py` — immutable request/output contracts, enums, validation, canonical fingerprints.
- `engine/ai/laya/config.py` — immutable disabled-by-default role/runtime configuration.
- `engine/ai/laya/model_registry.py` — immutable registered-model metadata and explicit lookup authority.
- `engine/ai/laya/adapter.py` — adapter Protocol, `DisabledLayaAdapter`, typed adapter errors.
- `engine/ai/laya/router.py` — single role-aware dispatch entry point.
- `engine/ai/laya/market_intelligence.py` — freshness validation and market-intelligence service.
- `engine/ai/laya/opportunity_engine.py` — pure conversion of validated market insight into a non-executable Laya opportunity candidate.
- `engine/ai/laya/strategy_hunter.py` — research-only strategy candidate service.
- `engine/ai/laya/fast_tasks.py` — bounded fast-task service.
- `build/tools/laya_probe.py` — deterministic fake-adapter probe for Windows parity.
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
- `build/tools/check_phase4_research_backtest.py` — extend required-presence/static boundary coverage to `engine/ai/laya` without weakening existing Phase-4 checks.
- `.github/workflows/v2-phase0-baseline.yml` — add Laya focused validation and a separate cross-Windows Laya fingerprint comparison while leaving Phase-4 G4 probe/comparison intact.

Do not modify:
- `engine/strategy/promotion_v2.py`
- `engine/strategy/lifecycle_v2.py`
- broker adapters
- Live execution state machine
- order placement paths

---

### Task 1: Immutable Laya Contracts and Deterministic Identity

**Files:**
- Create: `engine/ai/__init__.py`
- Create: `engine/ai/laya/__init__.py`
- Create: `engine/ai/laya/contracts.py`
- Create: `tests_v1/test_laya_contracts.py`

**Interfaces:**
- Consumes: `CanonicalCodec.fingerprint(schema: str, fields: Sequence[tuple[str, object]]) -> str`.
- Produces: `LayaContractError`, `LayaRole`, `MarketRegime`, `DirectionalBias`, `VolatilityState`, `OpportunityIntent`, `ModelProvenance`, `MarketIntelligenceRequest`, `MarketInsight`, `OpportunityCandidate`, `StrategyHuntRequest`, `StrategyCandidate`, `FastTaskRequest`, `FastTaskResult`.

- [ ] **Step 1: Write failing contract tests**

Create `tests_v1/test_laya_contracts.py` with tests that import the not-yet-created package and pin validation/determinism:

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


def _provenance() -> ModelProvenance:
    return ModelProvenance(
        model_id="laya-test",
        model_version="test@v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
    )


def test_market_request_fingerprint_is_order_independent_for_features():
    now = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)
    first = MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=now,
        features={"rsi": Decimal("61.2"), "atr": Decimal("42.1")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )
    second = MarketIntelligenceRequest.create(
        symbol="nifty",
        timeframe="5m",
        event_timestamp=now,
        features={"atr": Decimal("42.1"), "rsi": Decimal("61.2")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )
    assert first.fingerprint == second.fingerprint


def test_market_contracts_reject_naive_time_and_non_finite_confidence():
    with pytest.raises(LayaContractError):
        MarketIntelligenceRequest.create(
            symbol="NIFTY",
            timeframe="5m",
            event_timestamp=datetime(2026, 1, 5, 9, 30),
            features={"atr": Decimal("42")},
            data_lineage="dataset@v1",
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
            provenance=_provenance(),
        )


def test_fast_task_request_rejects_unknown_task_kind():
    with pytest.raises(LayaContractError):
        FastTaskRequest.create(
            task_kind="unbounded-arbitrary-code",
            payload=(("x", "y"),),
            request_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests_v1/test_laya_contracts.py -q
```

Expected: collection/import failure because `engine.ai.laya.contracts` does not exist.

- [ ] **Step 3: Implement deterministic contracts**

Create package markers and `contracts.py` using frozen/slots dataclasses, finite `Decimal` validation, aware timestamps, sorted canonical feature pairs, and explicit enums. The public shapes must be:

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

@dataclass(frozen=True, slots=True)
class ModelProvenance:
    model_id: str
    model_version: str
    model_hash: str
    adapter_version: str
    feature_schema_version: str

@dataclass(frozen=True, slots=True)
class MarketIntelligenceRequest:
    symbol: str
    timeframe: str
    event_timestamp: datetime
    features: tuple[tuple[str, Decimal], ...]
    data_lineage: str
    existing_strategy_signals: tuple[str, ...]
    fingerprint: str

    @classmethod
    def create(cls, *, symbol: str, timeframe: str, event_timestamp: datetime,
               features: Mapping[str, Decimal], data_lineage: str,
               existing_strategy_signals: tuple[str, ...] | list[str]) -> "MarketIntelligenceRequest": ...

@dataclass(frozen=True, slots=True)
class MarketInsight:
    request_fingerprint: str
    regime: MarketRegime
    bias: DirectionalBias
    volatility: VolatilityState
    event_tags: tuple[str, ...]
    confidence: Decimal
    produced_at: datetime
    provenance: ModelProvenance
    fingerprint: str

    @classmethod
    def create(cls, *, request_fingerprint: str, regime: MarketRegime,
               bias: DirectionalBias, volatility: VolatilityState,
               event_tags: tuple[str, ...] | list[str], confidence: Decimal,
               produced_at: datetime, provenance: ModelProvenance) -> "MarketInsight": ...

@dataclass(frozen=True, slots=True)
class OpportunityCandidate:
    source: str
    request_fingerprint: str
    insight_fingerprint: str
    symbol: str
    timeframe: str
    intent: OpportunityIntent
    setup_type: str
    evidence_tags: tuple[str, ...]
    confidence: Decimal
    valid_until: datetime
    provenance: ModelProvenance
    status: str
    fingerprint: str

@dataclass(frozen=True, slots=True)
class StrategyHuntRequest:
    dataset_refs: tuple[str, ...]
    feature_schema_version: str
    allowed_strategy_families: tuple[str, ...]
    max_candidates: int
    seed: int
    fingerprint: str

@dataclass(frozen=True, slots=True)
class StrategyCandidate:
    hypothesis_id: str
    entry_concept: str
    exit_requirements: tuple[str, ...]
    parameter_names: tuple[str, ...]
    target_regimes: tuple[MarketRegime, ...]
    provenance: ModelProvenance
    status: str
    fingerprint: str

@dataclass(frozen=True, slots=True)
class FastTaskRequest:
    task_kind: str
    payload: tuple[tuple[str, str], ...]
    request_timestamp: datetime
    fingerprint: str

@dataclass(frozen=True, slots=True)
class FastTaskResult:
    task_kind: str
    request_fingerprint: str
    ranked_items: tuple[tuple[str, Decimal], ...]
    provenance: ModelProvenance
    fingerprint: str
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

Every `.create()` computes identity with an explicit `algofortis-laya-.../v1` schema string and ordered fields. Mapping inputs must be converted to sorted tuples before calling `CanonicalCodec`.

- [ ] **Step 4: Run contract tests GREEN**

```powershell
python -m pytest tests_v1/test_laya_contracts.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add engine/ai engine/ai/laya tests_v1/test_laya_contracts.py
git commit -m "feat: add deterministic Laya contracts"
```

---

### Task 2: Disabled-By-Default Config, Model Registry, and Adapter Boundary

**Files:**
- Create: `engine/ai/laya/config.py`
- Create: `engine/ai/laya/model_registry.py`
- Create: `engine/ai/laya/adapter.py`
- Create: `tests_v1/test_laya_disabled_adapter.py`

**Interfaces:**
- Consumes: Task-1 contracts.
- Produces: `LayaConfig`, `RegisteredLayaModel`, `LayaModelRegistry`, `LayaAdapter` Protocol, `LayaUnavailable`, `LayaRegistryError`, `DisabledLayaAdapter`.

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.ai.laya.adapter import DisabledLayaAdapter, LayaUnavailable
from engine.ai.laya.config import LayaConfig
from engine.ai.laya.contracts import LayaRole, MarketIntelligenceRequest
from engine.ai.laya.model_registry import LayaModelRegistry, LayaRegistryError, RegisteredLayaModel


def test_config_is_disabled_by_default():
    config = LayaConfig.disabled()
    assert config.enabled is False
    assert config.enabled_roles == ()
    assert config.model_ref is None


def test_registry_requires_explicit_known_model():
    registry = LayaModelRegistry((RegisteredLayaModel(
        model_id="laya-test",
        model_version="test@v1",
        model_hash="a" * 64,
        adapter_version="fake@v1",
        feature_schema_version="features@v1",
        local_path="models/laya/laya-test",
    ),))
    assert registry.resolve("laya-test@test@v1").model_id == "laya-test"
    with pytest.raises(LayaRegistryError):
        registry.resolve("missing@v1")


def test_disabled_adapter_fails_closed_without_fallback():
    request = MarketIntelligenceRequest.create(
        symbol="NIFTY",
        timeframe="5m",
        event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc),
        features={"atr": Decimal("42")},
        data_lineage="dataset@v1",
        existing_strategy_signals=(),
    )
    with pytest.raises(LayaUnavailable, match="disabled"):
        DisabledLayaAdapter().market_intelligence(request)
```

The registry test intentionally pins exact lookup behavior; normalize the public registry key to `f"{model_id}@{model_version}"`. Therefore the test data should use `model_version="v1"` and lookup `"laya-test@v1"` in the final committed test.

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests_v1/test_laya_disabled_adapter.py -q
```

Expected: import failure for missing config/registry/adapter modules.

- [ ] **Step 3: Implement config, registry, and Protocol**

Use these exact public signatures:

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

@dataclass(frozen=True, slots=True)
class RegisteredLayaModel:
    model_id: str
    model_version: str
    model_hash: str
    adapter_version: str
    feature_schema_version: str
    local_path: str

    @property
    def ref(self) -> str:
        return f"{self.model_id}@{self.model_version}"

class LayaModelRegistry:
    def __init__(self, models: tuple[RegisteredLayaModel, ...] | list[RegisteredLayaModel] = ()) -> None: ...
    def resolve(self, model_ref: str) -> RegisteredLayaModel: ...
    def list_models(self) -> tuple[RegisteredLayaModel, ...]: ...

@runtime_checkable
class LayaAdapter(Protocol):
    adapter_version: str
    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight: ...
    def strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]: ...
    def fast_task(self, request: FastTaskRequest) -> FastTaskResult: ...

class DisabledLayaAdapter:
    adapter_version = "disabled@v1"
    def market_intelligence(self, request: MarketIntelligenceRequest) -> MarketInsight:
        raise LayaUnavailable("Laya is disabled")
    def strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        raise LayaUnavailable("Laya is disabled")
    def fast_task(self, request: FastTaskRequest) -> FastTaskResult:
        raise LayaUnavailable("Laya is disabled")
```

`RegisteredLayaModel` rejects missing text, non-64-lowercase-hex hash, absolute/network path forms, and blank adapter/schema versions. `LayaModelRegistry` rejects duplicate refs.

- [ ] **Step 4: Run tests GREEN**

```powershell
python -m pytest tests_v1/test_laya_disabled_adapter.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/ai/laya/config.py engine/ai/laya/model_registry.py engine/ai/laya/adapter.py tests_v1/test_laya_disabled_adapter.py
git commit -m "feat: add fail-closed Laya adapter boundary"
```

---

### Task 3: Role-Aware Laya Router and Provenance Enforcement

**Files:**
- Create: `engine/ai/laya/router.py`
- Create: `tests_v1/test_laya_router.py`

**Interfaces:**
- Consumes: `LayaConfig`, `LayaModelRegistry`, `LayaAdapter`, Task-1 request/result contracts.
- Produces: `LayaRouter.route_market(request)`, `LayaRouter.route_strategy_hunt(request)`, `LayaRouter.route_fast_task(request)`.

- [ ] **Step 1: Write failing tests with a deterministic fake adapter**

The fake stays in the test file and must not enter production code:

```python
class FakeAdapter:
    adapter_version = "fake@v1"
    def __init__(self, provenance):
        self.provenance = provenance
        self.calls = []

    def market_intelligence(self, request):
        self.calls.append(("market", request.fingerprint))
        return MarketInsight.create(
            request_fingerprint=request.fingerprint,
            regime=MarketRegime.UPTREND,
            bias=DirectionalBias.BULLISH,
            volatility=VolatilityState.NORMAL,
            event_tags=("TREND",),
            confidence=Decimal("0.75"),
            produced_at=request.event_timestamp,
            provenance=self.provenance,
        )
```

Pin these behaviors:

```python
def test_router_rejects_disabled_role_before_adapter_call(): ...
def test_router_rejects_output_from_unregistered_model(): ...
def test_router_accepts_registered_market_output_with_matching_provenance(): ...
```

The registered-model case must assert adapter call count is exactly one. The disabled-role case must assert call count remains zero.

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests_v1/test_laya_router.py -q
```

Expected: import failure for `engine.ai.laya.router`.

- [ ] **Step 3: Implement router**

```python
class LayaRoutingError(ValueError):
    pass

class LayaRouter:
    def __init__(self, *, config: LayaConfig, registry: LayaModelRegistry, adapter: LayaAdapter) -> None: ...

    def route_market(self, request: MarketIntelligenceRequest) -> MarketInsight:
        self._require_enabled(LayaRole.MARKET_INTELLIGENCE)
        result = self._adapter.market_intelligence(request)
        self._verify_provenance(result.provenance)
        if result.request_fingerprint != request.fingerprint:
            raise LayaRoutingError("market result is not bound to request")
        return result

    def route_strategy_hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]: ...
    def route_fast_task(self, request: FastTaskRequest) -> FastTaskResult: ...
```

`_verify_provenance()` resolves `f"{model_id}@{model_version}"` from the registry and requires exact equality of model hash, adapter version, and feature schema version. No best-effort matching is allowed.

- [ ] **Step 4: Run router tests GREEN**

```powershell
python -m pytest tests_v1/test_laya_router.py -q
```

- [ ] **Step 5: Commit**

```bash
git add engine/ai/laya/router.py tests_v1/test_laya_router.py
git commit -m "feat: add provenance-bound Laya router"
```

---

### Task 4: Continuous Market Intelligence Freshness and Independent Opportunity Engine

**Files:**
- Create: `engine/ai/laya/market_intelligence.py`
- Create: `engine/ai/laya/opportunity_engine.py`
- Create: `tests_v1/test_laya_market_intelligence.py`
- Create: `tests_v1/test_laya_opportunity_engine.py`

**Interfaces:**
- Consumes: `LayaRouter.route_market`, `MarketIntelligenceRequest`, `MarketInsight`, `OpportunityCandidate`.
- Produces: `MarketIntelligenceService.analyze(request, *, observed_at)`, `OpportunityEngine.from_insight(...)`.

- [ ] **Step 1: Write freshness tests**

```python
def test_market_service_rejects_stale_input_before_model_call():
    service = MarketIntelligenceService(router=router, max_input_age_seconds=30)
    request = _request(event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc))
    with pytest.raises(LayaMarketError, match="stale"):
        service.analyze(
            request,
            observed_at=datetime(2026, 1, 5, 9, 31, tzinfo=timezone.utc),
        )
    assert fake.calls == []


def test_market_service_accepts_fresh_input_and_returns_bound_insight():
    service = MarketIntelligenceService(router=router, max_input_age_seconds=30)
    result = service.analyze(
        _request(event_timestamp=datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)),
        observed_at=datetime(2026, 1, 5, 9, 30, 15, tzinfo=timezone.utc),
    )
    assert result.request_fingerprint == fake.calls[0][1]
```

- [ ] **Step 2: Write Laya-only opportunity tests**

Use a bearish reversal insight while `existing_strategy_signals=()`:

```python
def test_reversal_can_emit_laya_only_pe_candidate_when_strategy_is_silent():
    candidate = OpportunityEngine(min_confidence=Decimal("0.70")).from_insight(
        request=request_without_strategy_signal,
        insight=bearish_reversal_insight,
        validity_seconds=60,
    )
    assert candidate is not None
    assert candidate.source == "LAYA"
    assert candidate.intent is OpportunityIntent.PE_CANDIDATE
    assert candidate.status == "CANDIDATE_ONLY"


def test_neutral_or_low_confidence_insight_does_not_emit_candidate(): ...
```

Also assert no type in `OpportunityCandidate` exposes broker id, quantity, price, order type, or executable order fields.

- [ ] **Step 3: Verify RED**

```powershell
python -m pytest tests_v1/test_laya_market_intelligence.py tests_v1/test_laya_opportunity_engine.py -q
```

- [ ] **Step 4: Implement services**

```python
class LayaMarketError(ValueError):
    pass

class MarketIntelligenceService:
    def __init__(self, *, router: LayaRouter, max_input_age_seconds: int) -> None: ...

    def analyze(self, request: MarketIntelligenceRequest, *, observed_at: datetime) -> MarketInsight:
        # require aware observed_at; reject negative/future-skewed ages beyond 5 seconds;
        # reject age > max_input_age_seconds before adapter invocation
        return self._router.route_market(request)

class OpportunityEngine:
    def __init__(self, *, min_confidence: Decimal) -> None: ...

    def from_insight(self, *, request: MarketIntelligenceRequest,
                     insight: MarketInsight, validity_seconds: int) -> OpportunityCandidate | None:
        # require request/insight binding and confidence >= threshold
        # only REVERSAL_CANDIDATE or BREAKOUT_CANDIDATE can create a candidate
        # BEARISH -> PE_CANDIDATE, BULLISH -> CE_CANDIDATE
        # NEUTRAL/UNCERTAIN -> None
        # status is always CANDIDATE_ONLY
```

Candidate validity is `insight.produced_at + timedelta(seconds=validity_seconds)`. The service remains pure and broker-neutral.

- [ ] **Step 5: Run tests GREEN**

```powershell
python -m pytest tests_v1/test_laya_market_intelligence.py tests_v1/test_laya_opportunity_engine.py -q
```

- [ ] **Step 6: Commit**

```bash
git add engine/ai/laya/market_intelligence.py engine/ai/laya/opportunity_engine.py tests_v1/test_laya_market_intelligence.py tests_v1/test_laya_opportunity_engine.py
git commit -m "feat: add Laya market and opportunity services"
```

---

### Task 5: Research-Only Strategy Hunter and Bounded Fast Tasks

**Files:**
- Create: `engine/ai/laya/strategy_hunter.py`
- Create: `engine/ai/laya/fast_tasks.py`
- Create: `tests_v1/test_laya_strategy_hunter.py`
- Create: `tests_v1/test_laya_fast_tasks.py`

**Interfaces:**
- Consumes: `LayaRouter.route_strategy_hunt`, `LayaRouter.route_fast_task`, `StrategyHuntRequest`, `StrategyCandidate`, `FastTaskRequest`, `FastTaskResult`.
- Produces: `StrategyHunter.hunt(request)`, `FastTaskService.run(request)`.

- [ ] **Step 1: Write strategy-hunter tests**

```python
def test_strategy_hunter_returns_research_only_candidates():
    candidates = StrategyHunter(router).hunt(request)
    assert candidates
    assert all(item.status == "RESEARCH_ONLY" for item in candidates)
    assert all(item.hypothesis_id.startswith("laya_") for item in candidates)


def test_strategy_hunter_rejects_more_results_than_request_budget():
    with pytest.raises(LayaStrategyHuntError, match="max_candidates"):
        StrategyHunter(router_with_overproducing_fake).hunt(request_with_max_candidates_1)
```

No strategy-hunter result is converted into `PromotionEvidenceBundle` or lifecycle state in this task.

- [ ] **Step 2: Write fast-task tests**

```python
def test_fast_task_service_returns_request_bound_result():
    result = FastTaskService(router).run(request)
    assert result.request_fingerprint == request.fingerprint


def test_unsupported_fast_task_is_rejected_before_adapter_call():
    with pytest.raises(LayaContractError):
        FastTaskRequest.create(
            task_kind="PLACE_ORDER",
            payload=(("symbol", "NIFTY"),),
            request_timestamp=aware_now,
        )
    assert fake.calls == []
```

- [ ] **Step 3: Verify RED**

```powershell
python -m pytest tests_v1/test_laya_strategy_hunter.py tests_v1/test_laya_fast_tasks.py -q
```

- [ ] **Step 4: Implement thin services**

```python
class StrategyHunter:
    def __init__(self, router: LayaRouter) -> None:
        self._router = router

    def hunt(self, request: StrategyHuntRequest) -> tuple[StrategyCandidate, ...]:
        results = self._router.route_strategy_hunt(request)
        if len(results) > request.max_candidates:
            raise LayaStrategyHuntError("adapter exceeded max_candidates")
        if any(item.status != "RESEARCH_ONLY" for item in results):
            raise LayaStrategyHuntError("strategy candidate escaped research-only state")
        return results

class FastTaskService:
    def __init__(self, router: LayaRouter) -> None:
        self._router = router

    def run(self, request: FastTaskRequest) -> FastTaskResult:
        result = self._router.route_fast_task(request)
        if result.request_fingerprint != request.fingerprint:
            raise LayaFastTaskError("result is not bound to request")
        return result
```

- [ ] **Step 5: Run tests GREEN**

```powershell
python -m pytest tests_v1/test_laya_strategy_hunter.py tests_v1/test_laya_fast_tasks.py -q
```

- [ ] **Step 6: Commit**

```bash
git add engine/ai/laya/strategy_hunter.py engine/ai/laya/fast_tasks.py tests_v1/test_laya_strategy_hunter.py tests_v1/test_laya_fast_tasks.py
git commit -m "feat: add Laya research and fast-task services"
```

---

### Task 6: Extend Static Safety Guard to Laya

**Files:**
- Modify: `build/tools/check_phase4_research_backtest.py`
- Create: `tests_v1/test_laya_ci_guard.py`

**Interfaces:**
- Consumes: existing `REQUIRED`, `SCOPES`, `FORBIDDEN`, `verify()` static guard.
- Produces: Laya files are required and `engine/ai/laya` is scanned with stronger broker/Live/order/network bans.

- [ ] **Step 1: Write RED guard tests**

```python
from pathlib import Path

from build.tools.check_phase4_research_backtest import REQUIRED, verify


def test_laya_guard_rejects_broker_live_order_and_network_imports(tmp_path):
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
    problems = verify(tmp_path, check_presence=False)
    assert len(problems) == 4


def test_laya_guard_requires_integration_authorities_and_tests():
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

- [ ] **Step 2: Verify RED against current guard**

```powershell
python -m pytest tests_v1/test_laya_ci_guard.py -q
```

Expected: failure because `engine/ai/laya` is absent from `SCOPES`, Laya files are absent from `REQUIRED`, and `engine.live`/`engine.orders` are not yet banned.

- [ ] **Step 3: Harden existing guard without weakening Phase-4 scope**

Update:

```python
SCOPES = (
    "engine/strategy",
    "engine/research",
    "engine/backtest/v2",
    "strategies/orb",
    "engine/ai/laya",
)
```

Append to `FORBIDDEN`:

```python
"engine.live",
"engine.orders",
```

Append all Task-6 `expected` paths plus `build/tools/laya_probe.py` and `tests_v1/test_laya_probe.py` to `REQUIRED` when those files exist by Task 7. To keep Task 6 independently green, add the probe paths in Task 7, not before.

- [ ] **Step 4: Run static guard and focused tests GREEN**

```powershell
python build/tools/check_phase4_research_backtest.py
python -m pytest tests_v1/test_laya_ci_guard.py -q
```

Expected: guard prints `Phase-4 research/backtest static guard: PASS`; tests pass.

- [ ] **Step 5: Commit**

```bash
git add build/tools/check_phase4_research_backtest.py tests_v1/test_laya_ci_guard.py
git commit -m "test: enforce Laya execution boundaries"
```

---

### Task 7: Deterministic Laya Probe and Dual-Windows CI

**Files:**
- Create: `build/tools/laya_probe.py`
- Create: `tests_v1/test_laya_probe.py`
- Modify: `build/tools/check_phase4_research_backtest.py`
- Modify: `.github/workflows/v2-phase0-baseline.yml`

**Interfaces:**
- Consumes: public Laya contracts/router/services only; fake adapter defined inside the probe.
- Produces: deterministic text fingerprint file with no network/model dependency; separate Windows A/B comparison.

- [ ] **Step 1: Write failing probe test**

```python
from build.tools.laya_probe import run


def test_laya_probe_is_deterministic_and_candidate_only():
    first = run()
    second = run()
    assert first == second
    assert first["MARKET_INSIGHT"]
    assert first["LAYA_OPPORTUNITY"]
    assert first["OPPORTUNITY_STATUS"] == "CANDIDATE_ONLY"
    assert first["DEFAULT_LIVE_STATE"] == "READ_ONLY/DISARMED"
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests_v1/test_laya_probe.py -q
```

Expected: import failure because `build.tools.laya_probe` does not exist.

- [ ] **Step 3: Implement probe**

`build/tools/laya_probe.py` must use a fixed timestamp, fixed features, a fixed registered fake model, a deterministic fake adapter, `LayaRouter`, `MarketIntelligenceService`, and `OpportunityEngine`. It prints exactly these lines in this order:

```text
MARKET_REQUEST=<64-hex>
MARKET_INSIGHT=<64-hex>
LAYA_OPPORTUNITY=<64-hex>
OPPORTUNITY_STATUS=CANDIDATE_ONLY
STRATEGY_SIGNAL_COUNT=0
DEFAULT_LIVE_STATE=READ_ONLY/DISARMED
```

`run()` returns a dict containing those exact keys/values. The fake insight is a bearish `REVERSAL_CANDIDATE` with `Decimal("0.81")`, while the request has `existing_strategy_signals=()` so the probe proves a Laya-only candidate path without creating an order.

- [ ] **Step 4: Add probe files to required-presence guard**

Append:

```python
"build/tools/laya_probe.py",
"tests_v1/test_laya_probe.py",
```

to `REQUIRED`.

- [ ] **Step 5: Update workflow with focused Laya checks on both Windows jobs**

In both `current-head-regression-a` and `current-head-regression-b`, after Phase-4 focused validation add:

```yaml
      - name: Laya integration focused validation
        shell: pwsh
        run: python -m pytest tests_v1 -k laya -q
      - name: Laya deterministic fingerprint probe
        shell: pwsh
        run: python build/tools/laya_probe.py | Set-Content laya.txt
```

Upload artifacts with unique names:

```yaml
      - name: Upload Laya fingerprint A
        uses: actions/upload-artifact@v4
        with:
          name: laya-fingerprint-a
          path: laya.txt
```

and on Windows B use `laya-fingerprint-b`.

Add a separate job, preserving existing `g4-fingerprint-compare` unchanged:

```yaml
  laya-fingerprint-compare:
    name: Laya cross-Windows deterministic fingerprint comparison
    needs: [current-head-regression-a, current-head-regression-b]
    runs-on: windows-latest
    steps:
      - name: Download Windows latest Laya fingerprint
        uses: actions/download-artifact@v4
        with:
          name: laya-fingerprint-a
          path: a
      - name: Download Windows 2022 Laya fingerprint
        uses: actions/download-artifact@v4
        with:
          name: laya-fingerprint-b
          path: b
      - name: Require identical Laya fingerprint output
        shell: pwsh
        run: |
          $a = Get-Content a/laya.txt -Raw
          $b = Get-Content b/laya.txt -Raw
          if ($a -ne $b) { throw "Laya cross-Windows fingerprint mismatch" }
          Write-Output $a
```

- [ ] **Step 6: Run local qualification commands**

```powershell
python build/tools/check_phase4_research_backtest.py
python build/tools/laya_probe.py
python -m pytest tests_v1 -k laya -q
```

Expected: static guard PASS; probe prints six deterministic lines; Laya-focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add build/tools/laya_probe.py tests_v1/test_laya_probe.py build/tools/check_phase4_research_backtest.py .github/workflows/v2-phase0-baseline.yml
git commit -m "ci: qualify Laya integration across Windows"
```

---

### Task 8: Full Regression, Safety Verification, and Stacked PR Preparation

**Files:**
- Modify only if verification finds a real defect in files owned by Tasks 1-7.
- No merge action in this task.

**Interfaces:**
- Consumes: entire Laya shell and existing AlgoFortis regression suite.
- Produces: exact-head verification evidence and a reviewable stacked PR.

- [ ] **Step 1: Run compile/static gates**

```powershell
python -m compileall -q engine dashboard/backend build/tools tests_v1
python build/tools/check_module_boundaries.py
python build/tools/check_phase1_foundation.py
python build/tools/check_phase2_safety_spine.py
python build/tools/check_phase3_data_v2.py
python build/tools/check_phase4_research_backtest.py
```

All commands must exit 0.

- [ ] **Step 2: Run Laya and Phase-4 focused suites**

```powershell
python -m pytest tests_v1 -k laya -q
python -m pytest tests_v1 -k phase4 -q
```

Both must pass.

- [ ] **Step 3: Run full regression and existing certification**

```powershell
python -m pytest tests_v1 -q
python build/tools/run_regression_certification.py
```

Both must pass before creating or updating the PR.

- [ ] **Step 4: Verify no prohibited imports or model artifacts entered the diff**

Run repository checks equivalent to:

```powershell
git diff --name-only 20310e359eeeb13ee2b4e443717cf654466f68c4...HEAD
git grep -n -E "engine\.broker_adapters|engine\.live|engine\.orders|engine\.execution\.live|import requests|import httpx|import socket" -- engine/ai/laya
```

Expected: the changed-file list contains only planned Laya/docs/guard/workflow/test files; grep returns no prohibited Laya imports.

- [ ] **Step 5: Verify default fail-closed behavior explicitly**

Run:

```powershell
@'
from engine.ai.laya.adapter import DisabledLayaAdapter, LayaUnavailable
from engine.ai.laya.config import LayaConfig
from engine.strategy.promotion_v2 import PromotionProfile, evaluate_promotion

assert LayaConfig.disabled().enabled is False
try:
    DisabledLayaAdapter().market_intelligence(None)
except LayaUnavailable:
    pass
else:
    raise AssertionError("disabled adapter did not fail closed")

assert evaluate_promotion(PromotionProfile.research_only(), {}).status == "NON_PROMOTABLE"
print("LAYA_DISABLED=PASS")
print("PROMOTION_FAIL_CLOSED=PASS")
print("LIVE_STATE=READ_ONLY/DISARMED")
'@ | python -
```

Expected output is exactly the three PASS/state lines.

- [ ] **Step 6: Prepare stacked PR without merging**

If PR #6 is still open, create the Laya PR with:

```text
base: v2-phase4-strategy-research-backtest
head: laya-integration
```

PR title:

```text
Laya integration: model-agnostic fast intelligence shell
```

PR body must state:

```text
- actual Laya model is not included or enabled
- default adapter is disabled/fail-closed
- strategy hunting is research-only
- Laya can emit independent opportunity candidates when strategies are silent
- candidates are non-executable and cannot bypass RiskGate
- broker/Live/order/network imports are statically blocked in engine/ai/laya
- existing Live remains READ_ONLY/DISARMED
- built-in promotion remains NON_PROMOTABLE
- exact-head local/full regression evidence is attached in the PR description
```

After PR #6 merges, retarget the Laya PR to `main`, confirm the diff no longer contains unrelated Phase-4 ancestry as new changes, and require fresh exact-head GitHub Actions success on:

```text
Current HEAD regression A (Windows latest / Python 3.13.14)
Current HEAD regression B (Windows 2022 / Python 3.13.14)
G4 cross-Windows deterministic fingerprint comparison
Laya cross-Windows deterministic fingerprint comparison
```

- [ ] **Step 7: Stop before merge**

Report:

```text
Implemented: Laya integration shell
Verified: local static/focused/full regression + exact-head dual-Windows CI
Model: NOT CONNECTED
Live: READ_ONLY/DISARMED
Promotion: NON_PROMOTABLE
Remaining shared-branch action: owner-approved merge only
```

Do not merge without a new explicit owner instruction.
