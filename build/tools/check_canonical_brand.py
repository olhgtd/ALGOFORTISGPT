"""Fail-closed canonical AlgoFortis brand guard.

Scans every tracked path and tracked file byte stream for the retired product
name without embedding that name contiguously in this guard itself.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETIRED = ("sentinel" + "x").encode("ascii")


@dataclass(frozen=True)
class Finding:
    path: str
    kind: str


def _tracked() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def scan() -> list[Finding]:
    findings: list[Finding] = []
    for rel in _tracked():
        if RETIRED.decode("ascii") in rel.lower():
            findings.append(Finding(rel, "PATH"))
        path = ROOT / rel
        if path.is_file():
            try:
                raw = path.read_bytes()
            except OSError:
                findings.append(Finding(rel, "READ_ERROR"))
                continue
            if RETIRED in raw.lower():
                findings.append(Finding(rel, "CONTENT"))
    return findings


def main() -> int:
    findings = scan()
    if findings:
        for finding in findings:
            print(f"CANONICAL_BRAND_FAIL: {finding.kind}: {finding.path}", file=sys.stderr)
        print(f"CANONICAL_BRAND_FAIL_COUNT={len(findings)}", file=sys.stderr)
        return 1
    print("CANONICAL_BRAND_PASS: no retired product-name token in tracked paths or bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
