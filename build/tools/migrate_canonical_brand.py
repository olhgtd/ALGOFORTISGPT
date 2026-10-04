from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = "senti" + "nel"
LEGACY_PATTERN = re.compile(re.escape(LEGACY_ROOT) + r"[\s_-]*x", re.IGNORECASE)
CANONICAL = "AlgoFortis"


def run_git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return cp.stdout


def tracked_files() -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return [p.decode("utf-8") for p in raw.split(b"\0") if p]


def replacement(match: re.Match[str]) -> str:
    token = re.sub(r"[\s_-]+", "", match.group(0))
    if token.isupper():
        return CANONICAL.upper()
    if token.islower():
        return CANONICAL.lower()
    return CANONICAL


def canonicalize(value: str) -> str:
    return LEGACY_PATTERN.sub(replacement, value)


def migrate_paths() -> None:
    originals = sorted(
        (p for p in tracked_files() if LEGACY_PATTERN.search(p)),
        key=lambda p: (p.count("/"), len(p)),
        reverse=True,
    )
    for old in originals:
        new = canonicalize(old)
        if old == new:
            continue
        src = ROOT / old
        dst = ROOT / new
        if not src.exists():
            continue
        if dst.exists():
            run_git("rm", "--", old)
            print(f"DROP_LEGACY_COLLISION {old} -> {new}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            run_git("mv", "--", old, new)
            print(f"RENAME {old} -> {new}")


def migrate_text() -> None:
    for rel in tracked_files():
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
        updated = canonicalize(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="")
            print(f"TEXT {rel}")


FINAL_AUDIT = '"""Fail-closed canonical product-brand audit for the tracked source tree."""\nfrom __future__ import annotations\n\nimport re\nimport subprocess\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[2]\nLEGACY_ROOT = "senti" + "nel"\nLEGACY_PATTERN = re.compile(re.escape(LEGACY_ROOT) + r"[\\s_-]*x", re.IGNORECASE)\n\n\ndef tracked_files() -> list[str]:\n    raw = subprocess.run(\n        ["git", "ls-files", "-z"],\n        cwd=ROOT,\n        check=True,\n        stdout=subprocess.PIPE,\n    ).stdout\n    return [p.decode("utf-8") for p in raw.split(b"\\0") if p]\n\n\ndef scan_repository() -> list[str]:\n    findings: list[str] = []\n    for rel in tracked_files():\n        if LEGACY_PATTERN.search(rel):\n            findings.append(f"path:{rel}")\n        path = ROOT / rel\n        if not path.is_file():\n            continue\n        data = path.read_bytes()\n        if b"\\0" in data:\n            continue\n        try:\n            text = data.decode("utf-8")\n        except UnicodeDecodeError:\n            continue\n        for line_no, line in enumerate(text.splitlines(), 1):\n            if LEGACY_PATTERN.search(line):\n                findings.append(f"{rel}:{line_no}:{line.strip()}")\n    return findings\n\n\ndef main() -> int:\n    findings = scan_repository()\n    if findings:\n        print("CANONICAL_BRAND=FAIL")\n        for item in findings:\n            print(f"- {item}")\n        return 1\n    print("CANONICAL_BRAND=PASS")\n    print("PRODUCT_NAME=AlgoFortis")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
FINAL_WORKFLOW = 'name: Canonical AlgoFortis Brand Guard\n\non:\n  pull_request:\n    branches: [main]\n  push:\n    branches: [main]\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\njobs:\n  brand-guard:\n    name: Canonical brand / source tree\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: "3.13.14"\n      - name: Install test dependency\n        run: python -m pip install pytest\n      - name: Canonical brand audit\n        run: python build/tools/brand_audit.py\n      - name: Canonical brand regression\n        run: python -m pytest tests_v1/test_canonical_brand.py -q\n'


def install_permanent_guard() -> None:
    (ROOT / "build" / "tools" / "brand_audit.py").write_text(
        FINAL_AUDIT, encoding="utf-8", newline=""
    )
    workflow = ROOT / ".github" / "workflows" / "canonical-brand.yml"
    workflow.write_text(FINAL_WORKFLOW, encoding="utf-8", newline="")
    marker = ROOT / ".canonical-brand-migration-required"
    if marker.exists():
        marker.unlink()
    self_path = Path(__file__).resolve()
    if self_path.exists():
        self_path.unlink()


def main() -> int:
    migrate_paths()
    migrate_text()
    install_permanent_guard()
    print("CANONICAL_BRAND_MIGRATION=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
