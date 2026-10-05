from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "systemOps.ts"
SCREEN = ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "SystemOperations.tsx"
PRODUCT_ROUTER = ROOT / "dashboard" / "backend" / "product_ops_v2" / "router.py"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_product_ops_boundary_remains_read_only() -> None:
    source = text(PRODUCT_ROUTER)
    assert "Read-only Phase 9 Product Operations HTTP boundary" in source
    assert '@router.get("/owner/health")' in source
    assert not re.search(r"(?m)^\s*@router\.post\(", source)


def test_owner_system_client_has_no_generic_shell_path_or_process_control() -> None:
    source = text(CLIENT).lower()
    for forbidden in ("powershell", "cmd.exe", "subprocess", "shell", "terminal", "process/kill", "arbitrary_path", "file://"):
        assert forbidden not in source
    assert "/api/v1/product-ops/owner/health" in source
    assert "/api/v1/owner/admin/authority" in source
    assert "/api/v1/owner/admin/incidents" in source


def test_system_operations_truthfully_marks_unsupported_commands_unavailable() -> None:
    screen = text(SCREEN)
    for label in ("System Operations", "Persistence", "Audit", "Backup", "Restore", "Rollback", "Runbooks", "UNAVAILABLE"):
        assert label in screen
    assert "Run shell" not in screen
    assert "Edit path" not in screen
