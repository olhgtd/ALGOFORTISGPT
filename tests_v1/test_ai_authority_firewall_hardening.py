"""Hardening tests: AI/Laya can never reach order, broker or RiskGate authority."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "build" / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load("check_ai_import_allowlist")

STRICT_BYPASSES = {
    "module-qualified ApprovedOrder": "from engine.orders import contracts_v2\nx = contracts_v2.ApprovedOrder(a=1)",
    "private mint helper": "from engine.orders.contracts_v2 import _mint_approved_order\nx = _mint_approved_order()",
    "paper broker import": "from engine.execution.paper_broker import PaperBroker",
    "risk gate import": "from engine.risk.gate_v2 import RiskGateV2",
    "from-engine submodule import": "from engine import execution",
    "from-risk submodule import": "from engine.risk import gate_v2",
    "broker adapter import": "from engine.broker_adapters.angel_adapter import AngelAdapter",
    "live package import": "import engine.live.mutation_release_gate_v2 as g",
    "importlib": "import importlib\nimportlib.import_module('engine.execution')",
    "__import__": "m = __import__('engine.execution')",
    "eval": "eval('1+1')",
    "exec": "exec('x=1')",
    "relative escape": "from ...execution import paper_broker",
    "dashboard import": "from dashboard.backend import paper_service",
    "network library": "import requests",
    "raw socket": "import socket",
    "subprocess": "import subprocess",
    "pickle": "import pickle",
    "attribute reference only": "import engine.core as c\nx = c.ApprovedOrder",
}


@pytest.mark.parametrize("name", sorted(STRICT_BYPASSES))
def test_strict_scope_blocks_every_known_bypass(name: str) -> None:
    findings = guard.scan_source("engine/ai/v2/sample.py", STRICT_BYPASSES[name])
    assert findings, f"firewall missed bypass: {name}"


def test_strict_scope_allows_legitimate_ai_code() -> None:
    code = (
        "from __future__ import annotations\n"
        "import json, os, re\nfrom urllib.parse import urlsplit\n"
        "from dataclasses import dataclass\n"
        "from engine.ai.v2.contracts import TradeCandidate\n"
        "from engine.core.runtime import Clock\n"
        "from engine.data.licensing import X\n"
        "from engine.reproducibility.codec import CanonicalCodec\n"
        "from .contracts import AIRequest\n"
    )
    assert guard.scan_source("engine/ai/v2/sample.py", code) == []


def test_docstrings_and_strings_do_not_trigger() -> None:
    code = '"""Mentions ApprovedOrder and broker.place_order only in prose."""\nMARK = "ApprovedOrder("\n'
    assert guard.scan_source("engine/ai/v2/sample.py", code) == []


def test_adjacent_scope_blocks_execution_surfaces_but_allows_web_stack() -> None:
    assert guard.scan_source("dashboard/backend/owner_admin/x.py", "from engine.broker_adapters.factory import f")
    assert guard.scan_source("dashboard/backend/ai_control.py", "from engine.execution.paper_broker import P")
    assert guard.scan_source("dashboard/backend/ai_control.py", "from engine.risk import gate_v2")
    assert guard.scan_source("dashboard/backend/owner_admin/x.py", "x = ApprovedOrder")
    assert guard.scan_source("dashboard/backend/owner_admin/x.py", "import importlib")
    assert guard.scan_source("dashboard/backend/owner_admin/x.py", "import fastapi\nimport pydantic\nimport json\nfrom engine.ai.contracts import AIAvailability") == []


def test_unparseable_file_fails_closed() -> None:
    assert guard.scan_source("engine/ai/v2/broken.py", "def (:")


def test_files_outside_scope_are_ignored() -> None:
    assert guard.scan_source("engine/execution/engine.py", "from engine.broker_adapters.factory import f") == []


def test_real_repository_passes_the_firewall() -> None:
    assert guard.check_repository(ROOT) == []


def test_combined_boundary_checker_includes_the_ast_firewall() -> None:
    boundary = _load("check_ai_decision_intelligence_boundary")
    assert boundary.check_repository() == []
    assert "check_ai_import_allowlist" in (ROOT / "build/tools/check_ai_decision_intelligence_boundary.py").read_text(encoding="utf-8")


# ---- ToolGateway allowlist ---------------------------------------------------
from engine.ai.v2.contracts import DataClass  # noqa: E402
from engine.ai.v2.tool_gateway import (  # noqa: E402
    ToolAccess, ToolGateway, ToolGatewayError, ToolManifest, ToolSideEffect,
)


def _gateway(tool_id: str, access=ToolAccess.READ, side=ToolSideEffect.NONE) -> ToolGateway:
    m = ToolManifest(tool_id, "1.0.0", access, ("/safe",), (DataClass.MARKET_RESEARCH,), 5, 1, side, True)
    return ToolGateway(manifests=(m,), implementations={tool_id: lambda i: {}},
                       audit_sink=lambda e: None, usage_supplier=lambda a, t: None, path_resolver=lambda p: p)


@pytest.mark.parametrize("tool_id", [
    "orders.place", "paper.submit_order", "execution.submit", "portfolio.close_position",
    "risk_gate.approve", "broker.place_order", "live.arm", "credentials.read",
    "kill_switch.disable", "promotion.approve", "RESEARCH.read", "researchx.read", "system.shell",
])
def test_tool_gateway_rejects_non_research_tools(tool_id: str) -> None:
    with pytest.raises(ToolGatewayError):
        _gateway(tool_id)


@pytest.mark.parametrize("tool_id", ["research.read", "research.write_report", "data.read.bars"])
def test_tool_gateway_accepts_research_namespaces(tool_id: str) -> None:
    side = ToolSideEffect.RESEARCH_ARTIFACT if "write" in tool_id else ToolSideEffect.NONE
    access = ToolAccess.WRITE if "write" in tool_id else ToolAccess.READ
    assert _gateway(tool_id, access, side)


def test_write_tool_must_declare_research_artifact_side_effect() -> None:
    with pytest.raises(ToolGatewayError):
        _gateway("research.write_report", ToolAccess.WRITE, ToolSideEffect.NONE)
