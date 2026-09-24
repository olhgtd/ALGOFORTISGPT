from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


def _api():
    try:
        return import_module("build.tools.check_phase3_data_v2")
    except ModuleNotFoundError:
        pytest.fail("build.tools.check_phase3_data_v2 is missing", pytrace=False)


def test_phase3_static_gate_passes_current_repository():
    api = _api()
    assert api.check_phase3_data_v2(Path(".")) == ()


def test_phase3_static_gate_forbids_network_scraper_and_concrete_broker_imports():
    api = _api()
    forbidden = set(api.FORBIDDEN_DATA_IMPORT_PREFIXES)
    assert {"requests", "httpx", "urllib", "selenium", "playwright", "bs4", "scrapy"} <= forbidden
    assert "engine.broker_adapters" in forbidden


def test_phase3_static_gate_locks_required_safety_markers():
    api = _api()
    markers = api.REQUIRED_MARKERS
    assert "NSE_PROGRAMMATIC_ACQUISITION_PROHIBITED" in markers["engine/data/licensing.py"]
    assert "SYNTHETIC_NOT_PROMOTION_EVIDENCE" in markers["engine/data/licensing.py"]
    assert "entries_allowed" in markers["engine/data/feed_monitor.py"]
    assert "protective_exits_allowed" in markers["engine/data/feed_monitor.py"]
