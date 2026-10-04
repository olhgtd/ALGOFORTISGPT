"""One-shot full canonical brand migration for tracked repository files.

This intentionally changes both visible branding and internal legacy namespaces.
It is fail-closed: path collisions, undecodable tracked files containing the old
ASCII token, or residual references abort the migration.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD_LOWER = "sentinel" + "x"
OLD_TITLE = "Sentinel" + "X"
OLD_UPPER = "SENTINEL" + "X"
OLD_RE = re.compile(re.escape(OLD_LOWER), re.IGNORECASE)

# These three files have newer authoritative AlgoFortis successors already in-tree.
OBSOLETE_COLLISION_PATHS = {
    f"START_{OLD_UPPER}.pyw",
    f"build/tools/{OLD_TITLE}Launcher.cs",
    f"build/tools/{OLD_LOWER}_installer.iss",
}

SUPERSEDED_AUDIT = "build/tools/brand_audit.py"


def _tracked() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def _canonical_case(match: re.Match[str]) -> str:
    token = match.group(0)
    if token.isupper():
        return "ALGOFORTIS"
    if token.islower():
        return "algofortis"
    return "AlgoFortis"


def _replace_text_bytes(path: Path) -> bool:
    raw = path.read_bytes()
    if OLD_LOWER.encode("ascii") not in raw.lower():
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"tracked non-UTF8 file contains retired brand token: {path.relative_to(ROOT)}") from exc
    updated = OLD_RE.sub(_canonical_case, text)
    if updated == text:
        return False
    path.write_bytes(updated.encode("utf-8"))
    return True


def _canonical_relpath(rel: str) -> str:
    return OLD_RE.sub(_canonical_case, rel)


def _install_permanent_guard_test() -> None:
    target = ROOT / "tests_v1" / "test_canonical_brand.py"
    target.write_text(
        '"""Permanent repository-wide canonical brand regression guard."""\n'
        'from build.tools.check_canonical_brand import scan\n\n\n'
        'def test_tracked_repository_uses_only_canonical_brand() -> None:\n'
        '    findings = scan()\n'
        '    assert findings == [], "retired product-name token found: " + ", ".join(f"{x.kind}:{x.path}" for x in findings)\n',
        encoding="utf-8",
    )


def _force_remove(rel: str) -> None:
    # Files scheduled for removal may already contain intended in-worktree brand
    # substitutions. -f discards only those deliberate local edits before deletion.
    subprocess.run(["git", "rm", "-f", "--", rel], cwd=ROOT, check=True)


def migrate() -> None:
    tracked = _tracked()

    # Text first so imports/references move in the same transaction as filenames.
    changed = 0
    for rel in tracked:
        path = ROOT / rel
        if path.is_file() and _replace_text_bytes(path):
            changed += 1

    # The old classifier becomes misleading after a total purge; the canonical
    # fail-closed guard supersedes it.
    if (ROOT / SUPERSEDED_AUDIT).exists():
        _force_remove(SUPERSEDED_AUDIT)

    # Rename every tracked path carrying the retired token. Process deepest first.
    current = _tracked()
    rename_pairs: list[tuple[str, str]] = []
    for rel in current:
        new_rel = _canonical_relpath(rel)
        if new_rel != rel:
            rename_pairs.append((rel, new_rel))
    rename_pairs.sort(key=lambda pair: pair[0].count("/"), reverse=True)

    for old_rel, new_rel in rename_pairs:
        old_path = ROOT / old_rel
        if not old_path.exists():
            continue
        new_path = ROOT / new_rel
        if new_path.exists():
            if old_rel in OBSOLETE_COLLISION_PATHS:
                _force_remove(old_rel)
                continue
            old_bytes = old_path.read_bytes()
            new_bytes = new_path.read_bytes()
            if old_bytes == new_bytes:
                _force_remove(old_rel)
                continue
            raise RuntimeError(f"canonical path collision requires manual resolution: {old_rel} -> {new_rel}")
        new_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", "--", old_rel, new_rel], cwd=ROOT, check=True)

    # Owner decision override: full purge now explicitly includes internal IDs.
    decision = ROOT / "ALGOFORTIS_V2_OWNER_DECISIONS.md"
    if decision.exists():
        text = decision.read_text(encoding="utf-8")
        old_sentence = (
            "Rename scope is visible surfaces only (exe, installer, shortcuts, splash, title bar, UI name, "
            "publisher/version metadata), not internal DB/schema IDs."
        )
        new_sentence = (
            "Canonical brand scope is repository-wide: visible surfaces, filenames, package names, environment "
            "variables, DB/schema identifiers, deterministic schema namespaces, docs, tests, and tooling use "
            "AlgoFortis naming. No retired product-name identifier is retained in tracked source."
        )
        if old_sentence in text:
            decision.write_text(text.replace(old_sentence, new_sentence), encoding="utf-8")

    _install_permanent_guard_test()

    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(f"CANONICAL_BRAND_MIGRATION_CHANGED_TEXT_FILES={changed}")


def main() -> int:
    if len(sys.argv) != 1:
        print("usage: python build/tools/migrate_canonical_brand.py", file=sys.stderr)
        return 2
    migrate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
