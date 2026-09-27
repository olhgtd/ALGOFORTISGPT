from __future__ import annotations

from pathlib import Path
import re

_FORBIDDEN = (
    (re.compile(r"\bengine\.broker_adapters\b"), "forbidden broker import"),
    (re.compile(r"\b_mint_approved_order\b"), "forbidden ApprovedOrder mint authority"),
    (re.compile(r"\bApprovedOrder\s*\("), "forbidden ApprovedOrder construction"),
    (re.compile(r"(?:^|\n)\s*(?:import|from)\s+[^\n]*(?:credential|private[_-]?key|secret[_-]?store)|\b(?:CredentialStore|PrivateKeyStore|SecretStore)\s*\(", re.I), "forbidden credential/private-key authority"),
    (re.compile(r"\bengine\.(?:live|broker_contract).*?(?:submit|place|mutat|arm)", re.I), "forbidden Live/broker mutation import"),
)
_NETWORK = re.compile(r"(^|\n)\s*(?:import|from)\s+(requests|httpx|urllib|aiohttp|socket)\b")
_DATABASE = re.compile(r"(^|\n)\s*(?:import|from)\s+(sqlite3|sqlalchemy|psycopg)\b")
_GUESSED_DEFAULT = re.compile(r"(?:DEFAULT|PRODUCTION)_(?:TOKEN|BUDGET|QUOTA|TIMEOUT|PROVIDER)\s*=", re.I)


def scan_phase8_tree(repo_root: Path | str) -> tuple[str, ...]:
    root = Path(repo_root) / "engine" / "ai" / "v2"
    if not root.exists():
        return ("engine/ai/v2 is missing",)
    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        for pattern, message in _FORBIDDEN:
            if pattern.search(text):
                findings.append(f"{rel}: {message}")
        if "adapters" not in rel.parts:
            m = _NETWORK.search(text)
            if m:
                findings.append(f"{rel}: direct network import {m.group(2)} is forbidden in pure domain code")
            m = _DATABASE.search(text)
            if m:
                findings.append(f"{rel}: direct database import {m.group(2)} is forbidden in pure domain code")
        if _GUESSED_DEFAULT.search(text):
            findings.append(f"{rel}: guessed production provider/quota/budget default is forbidden")
    return tuple(findings)


def main() -> int:
    findings = scan_phase8_tree(Path.cwd())
    if findings:
        for item in findings:
            print(f"PHASE8_FIREWALL_FAIL={item}")
        return 1
    print("PHASE8_FIREWALL=PASS")
    print("AI_AUTHORITY=RESEARCH_SHADOW_ONLY")
    print("LIVE_STATE=READ_ONLY/DISARMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
