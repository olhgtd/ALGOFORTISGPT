"""Phase 1 RED tests for AF2-OPS-002 module-boundary enforcement."""

from pathlib import Path

from build.tools.check_module_boundaries import (
    BoundaryViolation,
    check_repository,
    check_source_text,
)


def _codes(violations: list[BoundaryViolation]) -> set[str]:
    return {violation.code for violation in violations}


def test_domain_cannot_import_broker_adapters_or_dashboard_transport() -> None:
    broker = check_source_text(
        "engine/risk/example.py",
        "from engine.broker_adapters.kite_adapter import KiteAdapter\n",
    )
    ui = check_source_text(
        "engine/orders/example.py",
        "from dashboard.backend.app import app\n",
    )

    assert "AF2-OPS-002-DOMAIN-ADAPTER" in _codes(broker)
    assert "AF2-OPS-002-DOMAIN-TRANSPORT" in _codes(ui)


def test_backtest_and_paper_cannot_import_live_broker_implementations() -> None:
    backtest = check_source_text(
        "engine/backtest/example.py",
        "import engine.broker_adapters.angel_adapter\n",
    )
    paper = check_source_text(
        "engine/paper/example.py",
        "from engine.broker_adapters.factory import BrokerAdapterFactory\n",
    )

    assert "AF2-OPS-002-MODE-ISOLATION" in _codes(backtest)
    assert "AF2-OPS-002-MODE-ISOLATION" in _codes(paper)


def test_safe_domain_and_port_style_imports_are_allowed() -> None:
    source = """
from decimal import Decimal
from engine.core.runtime import Clock
from engine.orders.model import OrderRequest
"""
    assert check_source_text("engine/risk/example.py", source) == []


def test_checker_reports_syntax_errors_fail_closed() -> None:
    violations = check_source_text("engine/risk/broken.py", "from engine.core import (\n")
    assert "AF2-OPS-002-SYNTAX" in _codes(violations)


def test_current_repository_has_no_enforced_boundary_violations() -> None:
    root = Path(__file__).resolve().parents[1]
    assert check_repository(root) == []
