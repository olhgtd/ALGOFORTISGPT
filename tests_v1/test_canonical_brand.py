from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = "senti" + "nel"
LEGACY_PATTERN = re.compile(re.escape(LEGACY_ROOT) + r"[\s_-]*x", re.IGNORECASE)


def tracked_files() -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return [p.decode("utf-8") for p in raw.split(b"\0") if p]


def test_only_canonical_product_brand_remains_in_tracked_source_tree() -> None:
    findings: list[str] = []
    for rel in tracked_files():
        if LEGACY_PATTERN.search(rel):
            findings.append(f"path:{rel}")
        path = ROOT / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if LEGACY_PATTERN.search(line):
                findings.append(f"{rel}:{line_no}")
                if len(findings) >= 50:
                    break
        if len(findings) >= 50:
            break
    assert findings == [], "legacy product brand remains: " + ", ".join(findings)
