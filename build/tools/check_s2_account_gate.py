"""Fail closed if S2 account code gains trading authority or qualification pieces disappear."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_V2 = ROOT / "dashboard" / "backend" / "account_v2"
FORBIDDEN_MODULE_PREFIXES = (
    "engine.broker_adapters",
    "engine.execution",
    "engine.live",
    "engine.orders",
    "engine.risk.gate_v2",
)
FORBIDDEN_TOKENS = (
    "ApprovedOrder",
    "place_order",
    "submit_order",
    "cancel_order",
    "modify_order",
    "arm(",
)
REQUIRED_PATHS = (
    "dashboard/backend/account_v2/__init__.py",
    "dashboard/backend/account_v2/contracts.py",
    "dashboard/backend/account_v2/repository.py",
    "dashboard/backend/account_v2/v1_store_adapter.py",
    "dashboard/backend/account_v2/webauthn_authority.py",
    "dashboard/backend/account_v2/device_service.py",
    "dashboard/backend/account_v2/session_service.py",
    "dashboard/backend/account_v2/rate_limit.py",
    "dashboard/backend/account_v2/recovery_service.py",
    "dashboard/backend/account_v2/gate.py",
    "dashboard/backend/account_v2/safety_mode.py",
    "dashboard/backend/account_v2/policy_seams.py",
    "dashboard/backend/account_v2/audit.py",
    "dashboard/backend/account_v2/authority_service.py",
    "dashboard/backend/account_v2/evidence.py",
    "build/tools/s2_deterministic_probe.py",
    "tests_v1/test_s2_contracts.py",
    "tests_v1/test_s2_architecture_guard.py",
    "tests_v1/test_s2_repository.py",
    "tests_v1/test_s2_webauthn_authority.py",
    "tests_v1/test_s2_device_service.py",
    "tests_v1/test_s2_session_service.py",
    "tests_v1/test_s2_rate_limit.py",
    "tests_v1/test_s2_recovery.py",
    "tests_v1/test_s2_device_session_gate.py",
    "tests_v1/test_s2_cloud_outage.py",
    "tests_v1/test_s2_policy_seams.py",
    "tests_v1/test_s2_audit_fail_closed.py",
    "tests_v1/test_s2_inv04_isolation.py",
    "tests_v1/test_s2_evidence.py",
    "tests_v1/test_s2_qualification_guard.py",
    "tests_v1/test_s2_ci_guard.py",
)
REQUIRED_EVIDENCE_MARKERS = (
    "S2_SCHEMA_VERSION",
    "ACCOUNT_AUTHORITY_FINGERPRINT",
    "DEVICE_REPROOF_FINGERPRINT",
    "SESSION_REPLAY_RESULT",
    "CROSS_USER_ESCAPE_COUNT",
    "OUTAGE_GATE_STATUS",
    "OUTAGE_RUNTIME_MODE",
    "RATE_LIMIT_FLOWS",
    "DEVICE_LIMIT",
    "PRODUCTION_DOMAIN",
    "LIVE_STATE",
    "BROKER_MUTATION_CAPABILITY",
)


def check() -> list[str]:
    violations: list[str] = []
    files = sorted(ACCOUNT_V2.rglob("*.py")) if ACCOUNT_V2.is_dir() else []
    if not files:
        return ["S2 account_v2 package is missing or empty"]

    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).is_file():
            violations.append(f"required GP-S2 path missing: {relative}")

    evidence_path = ACCOUNT_V2 / "evidence.py"
    if evidence_path.is_file():
        evidence_text = evidence_path.read_text(encoding="utf-8")
        for marker in REQUIRED_EVIDENCE_MARKERS:
            if marker not in evidence_text:
                violations.append(f"required GP-S2 evidence marker missing: {marker}")

    for path in files:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []
            for module in modules:
                if module.startswith(FORBIDDEN_MODULE_PREFIXES):
                    violations.append(f"{path.relative_to(ROOT)} imports forbidden module {module}")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                violations.append(f"{path.relative_to(ROOT)} contains forbidden capability token {token!r}")
    return violations


if __name__ == "__main__":
    failures = check()
    if failures:
        raise SystemExit("\n".join(failures))
    print("S2 account authority boundary: PASS")
