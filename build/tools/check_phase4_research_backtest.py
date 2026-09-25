"""Static Phase-4 research-only boundary and required-contract guard."""
from __future__ import annotations

import ast
from pathlib import Path


REQUIRED = (
    ".github/workflows/v2-phase0-baseline.yml",
    "build/tools/check_phase4_research_backtest.py",
    "build/tools/phase4_probe.py",
    "docs/v2/phase4/G4_EVIDENCE.md",
    "engine/strategy/contracts_v2.py",
    "engine/strategy/state_v2.py",
    "engine/strategy/lifecycle_v2.py",
    "engine/strategy/promotion_v2.py",
    "engine/strategy/protective_policy_v2.py",
    "engine/research/experiments.py",
    "engine/research/trials.py",
    "engine/research/search.py",
    "engine/research/stability.py",
    "engine/research/validation_v2.py",
    "engine/research/overfitting.py",
    "engine/research/walk_forward_v2.py",
    "engine/research/durable_ledger.py",
    "engine/research/robustness_v2.py",
    "engine/backtest/v2/contracts.py",
    "engine/backtest/v2/execution.py",
    "engine/backtest/v2/replay.py",
    "engine/backtest/v2/options.py",
    "engine/backtest/v2/batch.py",
    "engine/backtest/v2/orb_reference.py",
    "strategies/orb/manifest_v2.py",
    "strategies/orb/orb_v2.py",
    "engine/ai/laya/contracts.py",
    "engine/ai/laya/config.py",
    "engine/ai/laya/model_registry.py",
    "engine/ai/laya/adapter.py",
    "engine/ai/laya/router.py",
    "engine/ai/laya/market_intelligence.py",
    "engine/ai/laya/opportunity_engine.py",
    "engine/ai/laya/strategy_hunter.py",
    "engine/ai/laya/fast_tasks.py",
    "tests_v1/test_v2_phase4_strategy_sdk.py",
    "tests_v1/test_v2_phase4_orb_reference.py",
    "tests_v1/test_v2_phase4_experiment_tracking.py",
    "tests_v1/test_v2_phase4_search_budget.py",
    "tests_v1/test_v2_phase4_research_validation.py",
    "tests_v1/test_v2_phase4_overfitting.py",
    "tests_v1/test_v2_phase4_promotion.py",
    "tests_v1/test_v2_phase4_backtest_v2.py",
    "tests_v1/test_v2_phase4_no_lookahead.py",
    "tests_v1/test_v2_phase4_options_sim.py",
    "tests_v1/test_v2_phase4_batch.py",
    "tests_v1/test_v2_phase4_ci_guard.py",
    "tests_v1/test_v2_phase4_durable_ledger.py",
    "tests_v1/test_v2_phase4_evidence_bundle.py",
    "tests_v1/test_v2_phase4_lifecycle.py",
    "tests_v1/test_v2_phase4_orb_backtest.py",
    "tests_v1/test_v2_phase4_probe.py",
    "tests_v1/test_v2_phase4_protective_policy.py",
    "tests_v1/test_v2_phase4_robustness.py",
    "tests_v1/test_v2_phase4_walk_forward_v2.py",
    "tests_v1/test_laya_contracts.py",
    "tests_v1/test_laya_disabled_adapter.py",
    "tests_v1/test_laya_router.py",
    "tests_v1/test_laya_market_intelligence.py",
    "tests_v1/test_laya_opportunity_engine.py",
    "tests_v1/test_laya_strategy_hunter.py",
    "tests_v1/test_laya_fast_tasks.py",
    "tests_v1/test_laya_ci_guard.py",
)
SCOPES = (
    "engine/strategy",
    "engine/research",
    "engine/backtest/v2",
    "strategies/orb",
    "engine/ai/laya",
)
FORBIDDEN = (
    "engine.broker_adapters",
    "engine.live",
    "engine.orders",
    "engine.execution.live",
    "requests",
    "urllib",
    "socket",
    "http",
    "httpx",
    "aiohttp",
    "websocket",
    "websockets",
)


def verify(root: Path, *, check_presence: bool = True) -> tuple[str, ...]:
    issues: list[str] = []
    if check_presence:
        issues.extend("missing " + path for path in REQUIRED if not (root / path).is_file())
    for scope in SCOPES:
        path = root / scope
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path] if path.is_file() else []
        for file in files:
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            except (SyntaxError, UnicodeError) as exc:
                issues.append(f"syntax {file}: {exc}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names = (node.module or "",)
                else:
                    continue
                for name in names:
                    if any(name == banned or name.startswith(banned + ".") for banned in FORBIDDEN):
                        issues.append(f"broker/network import {file}:{node.lineno}: {name}")
    return tuple(issues)


if __name__ == "__main__":
    problems = verify(Path(__file__).resolve().parents[2])
    if problems:
        raise SystemExit("\n".join(problems))
    print("Phase-4 research/backtest static guard: PASS")
