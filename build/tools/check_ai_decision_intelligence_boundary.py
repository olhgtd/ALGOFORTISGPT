from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_ai_import_allowlist  # noqa: E402  AST-based firewall (replaces regex-only gaps)

ROOT = Path(__file__).resolve().parents[2]

REUSED_AUTHORITIES = {
    "risk": "engine/risk/gate_v2.py::RiskGateV2",
    "portfolio": "engine/portfolio/",
    "identity": "dashboard/backend/account_v2/gate.py::DeviceSessionGate",
    "admin": "dashboard/owner-dashboard/authoritative/AIControlCenter.tsx",
}


def scan_text(path: str, text: str) -> list[str]:
    """Return authority-boundary violations for AI/Laya implementation text."""
    p = path.replace("\\", "/").lower()
    if not (
        p.startswith("engine/ai/")
        or p.startswith("dashboard/backend/owner_admin/")
        or p.startswith("dashboard/owner-dashboard/authoritative/")
    ):
        return []

    violations: list[str] = []
    patterns = (
        (r"\bclass\s+AI\w*RiskGate\w*\b", "parallel risk authority is forbidden; reuse RiskGateV2"),
        (r"\bclass\s+AI\w*(?:Accounting|Ledger)\w*\b", "parallel accounting authority is forbidden; reuse engine/portfolio"),
        (r"\bclass\s+AI\w*(?:Session|Identity|Auth)Authority\w*\b", "parallel identity authority is forbidden; reuse S2 DeviceSessionGate"),
        (r"\bclass\s+AI\w*AdminAuthority\w*\b", "parallel admin authority is forbidden; reuse Owner/Admin authority"),
    )
    for pattern, message in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(message)

    if re.search(r"(?<![\w.])ApprovedOrder\s*\(", text):
        violations.append("ApprovedOrder direct construction is forbidden outside RiskGateV2")
    if re.search(r"\b(?:mint|create|issue)_approved_order\s*\(", text, re.IGNORECASE):
        violations.append("ApprovedOrder mint/bypass helper is forbidden outside RiskGateV2")
    if re.search(r"from\s+engine\.broker_adapters\.[\w.]+\s+import", text):
        violations.append("AI/Laya direct broker-adapter import is forbidden")
    return violations


def _iter_scanned_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for base in (ROOT / "engine" / "ai", ROOT / "dashboard" / "backend" / "owner_admin"):
        if base.exists():
            files.extend(p for p in base.rglob("*.py") if p.is_file())
    owner = ROOT / "dashboard" / "owner-dashboard" / "authoritative"
    if owner.exists():
        files.extend(p for p in owner.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx"})
    return tuple(sorted(set(files)))


def check_repository() -> list[str]:
    failures: list[str] = []
    for path in _iter_scanned_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for issue in scan_text(rel, text):
            failures.append(f"{rel}: {issue}")

    required = (
        ROOT / "engine" / "risk" / "gate_v2.py",
        ROOT / "engine" / "portfolio",
        ROOT / "dashboard" / "backend" / "account_v2" / "gate.py",
        ROOT / "dashboard" / "owner-dashboard" / "authoritative" / "AIControlCenter.tsx",
    )
    for item in required:
        if not item.exists():
            failures.append(f"required reused authority missing: {item.relative_to(ROOT).as_posix()}")

    failures.extend(check_ai_import_allowlist.check_repository(ROOT))

    freeze = ROOT / "docs" / "v2" / "phase8" / "PHASE8_DECISION_FREEZE.md"
    if not freeze.exists() or "READ_ONLY / DISARMED" not in freeze.read_text(encoding="utf-8"):
        failures.append("Phase-8 freeze must preserve Live READ_ONLY / DISARMED")
    return failures


def main() -> int:
    failures = check_repository()
    if failures:
        print("AI_DECISION_INTELLIGENCE_BOUNDARY=FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("AI_DECISION_INTELLIGENCE_BOUNDARY=PASS")
    print("APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY")
    print("PORTFOLIO_AUTHORITY=ENGINE_PORTFOLIO_ONLY")
    print("IDENTITY_AUTHORITY=S2_DEVICE_SESSION_GATE")
    print("ADMIN_AUTHORITY=EXISTING_OWNER_ADMIN_ONLY")
    print("AI_IMPORT_ALLOWLIST=PASS")
    print("LIVE_STATE=READ_ONLY/DISARMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
