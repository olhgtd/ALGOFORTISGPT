"""Static Phase-3 Data V2 policy gate.

This checker deliberately avoids importing project modules. It verifies required
Data V2 authorities/tests, forbids network/scraper/concrete-broker imports from
Phase-3 data modules, and locks frozen licensing/feed-safety markers for G3.
"""

from __future__ import annotations

import ast
from pathlib import Path


REQUIRED_FILES = (
    "engine/data/catalog.py",
    "engine/data/store.py",
    "engine/data/catalog_store.py",
    "engine/data/instruments.py",
    "engine/data/calendar.py",
    "engine/data/quality.py",
    "engine/data/resample.py",
    "engine/data/licensing.py",
    "engine/data/live_feed.py",
    "engine/data/feed_monitor.py",
    "tests_v1/test_v2_phase3_dataset_catalog.py",
    "tests_v1/test_v2_phase3_historical_store.py",
    "tests_v1/test_v2_phase3_instrument_master.py",
    "tests_v1/test_v2_phase3_data_quality.py",
    "tests_v1/test_v2_phase3_resampling.py",
    "tests_v1/test_v2_phase3_data_licensing.py",
    "tests_v1/test_v2_phase3_live_feed.py",
    "tests_v1/test_v2_phase3_ci_guard.py",
    "docs/v2/adr/ADR-011-phase3-data-scope-and-storage.md",
)

PHASE3_DATA_FILES = (
    "engine/data/catalog.py",
    "engine/data/store.py",
    "engine/data/catalog_store.py",
    "engine/data/instruments.py",
    "engine/data/calendar.py",
    "engine/data/quality.py",
    "engine/data/resample.py",
    "engine/data/licensing.py",
    "engine/data/live_feed.py",
    "engine/data/feed_monitor.py",
)

FORBIDDEN_DATA_IMPORT_PREFIXES = (
    "requests",
    "httpx",
    "urllib",
    "selenium",
    "playwright",
    "bs4",
    "scrapy",
    "engine.broker_adapters",
    "engine.broker.angel_adapter",
    "engine.broker.dhan_adapter",
    "engine.broker.kite_adapter",
    "engine.broker.upstox_adapter",
)

REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "engine/data/licensing.py": (
        "NSE_PROGRAMMATIC_ACQUISITION_PROHIBITED",
        "SYNTHETIC_NOT_PROMOTION_EVIDENCE",
        "programmatic_acquisition",
    ),
    "engine/data/feed_monitor.py": (
        "entries_allowed",
        "protective_exits_allowed",
        "RESUBSCRIBE_REQUIRED",
        "STALE",
        "SEQUENCE_GAP",
        "OUT_OF_ORDER",
        "CLOCK_SKEW",
    ),
    "engine/data/store.py": (
        "parquet",
        "checksum",
    ),
    "engine/data/catalog.py": (
        "dataset_id",
        "version_id",
        "checksum",
        "provenance",
    ),
}


def _module_names(tree: ast.AST) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def _is_forbidden(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in FORBIDDEN_DATA_IMPORT_PREFIXES
    )


def check_phase3_data_v2(root: Path) -> tuple[str, ...]:
    root = Path(root)
    diagnostics: list[str] = []

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            diagnostics.append(f"missing required Phase-3 file: {relative}")

    for relative in PHASE3_DATA_FILES:
        path = root / relative
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError) as error:
            diagnostics.append(f"cannot statically inspect {relative}: {error}")
            continue
        for module_name in _module_names(tree):
            if _is_forbidden(module_name):
                diagnostics.append(f"forbidden Phase-3 import in {relative}: {module_name}")

    for relative, markers in REQUIRED_MARKERS.items():
        path = root / relative
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            diagnostics.append(f"cannot read {relative}: {error}")
            continue
        lower_source = source.lower()
        for marker in markers:
            if marker not in source and marker.lower() not in lower_source:
                diagnostics.append(f"required Phase-3 marker missing in {relative}: {marker}")

    return tuple(sorted(diagnostics))


def main() -> int:
    diagnostics = check_phase3_data_v2(Path("."))
    if diagnostics:
        print("PHASE3_DATA_V2_STATIC_FAIL")
        for diagnostic in diagnostics:
            print(f"- {diagnostic}")
        return 1
    print(
        "PHASE3_DATA_V2_STATIC_PASS: required data authorities/tests present; "
        "no network/scraper/concrete-broker imports; licensing/feed-safety markers locked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
