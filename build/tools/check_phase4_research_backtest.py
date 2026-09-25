"""Static Phase-4 research-only boundary and required-contract guard."""
from __future__ import annotations

import ast
from pathlib import Path


REQUIRED = (
    "engine/strategy/contracts_v2.py", "engine/strategy/state_v2.py",
    "engine/strategy/promotion_v2.py", "engine/research/trials.py",
    "engine/strategy/protective_policy_v2.py",
    "engine/research/validation_v2.py", "engine/research/overfitting.py",
    "engine/research/walk_forward_v2.py", "engine/research/durable_ledger.py",
    "engine/research/robustness_v2.py",
    "engine/backtest/v2/execution.py", "engine/backtest/v2/replay.py",
    "engine/backtest/v2/options.py", "engine/backtest/v2/batch.py",
    "engine/backtest/v2/orb_reference.py",
    "strategies/orb/orb_v2.py", "tests_v1/test_v2_phase4_no_lookahead.py",
)
SCOPES = ("engine/strategy", "engine/research", "engine/backtest/v2", "strategies/orb")
FORBIDDEN = ("engine.broker_adapters", "engine.execution.live", "requests", "urllib", "socket")


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
