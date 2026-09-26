from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from importlib import import_module

import pytest


def _manifest_api():
    try:
        return import_module("strategies.orb.manifest_v2")
    except ModuleNotFoundError:
        pytest.fail("strategies.orb.manifest_v2 is missing", pytrace=False)


def _orb_api():
    try:
        return import_module("strategies.orb.orb_v2")
    except ModuleNotFoundError:
        pytest.fail("strategies.orb.orb_v2 is missing", pytrace=False)


def _snapshot(*, close: str, high: str = "22010", low: str = "21990"):
    api = _orb_api()
    return api.ORBSignalSnapshot(
        symbol="NIFTY",
        timestamp=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc),
        close=Decimal(close),
        opening_range_high=Decimal(high),
        opening_range_low=Decimal(low),
    )


def test_orb_manifest_is_sdk_v2_broker_neutral_and_requires_protective_policy():
    manifest_api = _manifest_api()
    manifest = manifest_api.ORB_MANIFEST_V2

    assert manifest.strategy_id == "orb"
    assert manifest.strategy_version == "2.0.0"
    assert manifest.required_timeframes == ("5m",)
    assert manifest.required_data_kinds == ("bars",)
    assert manifest.supported_instruments == ("index", "index_option")
    assert manifest.protective_policy_required is True
    assert manifest.validate_parameters({})["signal_price_field"] == "close"


def test_orb_reference_signal_is_strict_breakout_buy_sell_hold_only():
    api = _orb_api()
    strategy = api.ORBReferenceStrategyV2()

    assert strategy.generate_signal(_snapshot(close="22011")).action == api.ORBAction.BUY
    assert strategy.generate_signal(_snapshot(close="21989")).action == api.ORBAction.SELL
    assert strategy.generate_signal(_snapshot(close="22000")).action == api.ORBAction.HOLD
    assert strategy.generate_signal(_snapshot(close="22010")).action == api.ORBAction.HOLD
    assert strategy.generate_signal(_snapshot(close="21990")).action == api.ORBAction.HOLD


def test_orb_signal_is_deterministic_and_carries_no_executable_order():
    api = _orb_api()
    strategy = api.ORBReferenceStrategyV2()
    snapshot = _snapshot(close="22011")

    first = strategy.generate_signal(snapshot)
    second = strategy.generate_signal(snapshot)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.symbol == "NIFTY"
    assert not hasattr(first, "order_id")
    assert not hasattr(first, "qty")
    assert not hasattr(first, "broker")


def test_orb_snapshot_rejects_ambiguous_range_or_non_decimal_prices():
    api = _orb_api()

    with pytest.raises(api.ORBReferenceError):
        api.ORBSignalSnapshot(
            symbol="NIFTY",
            timestamp=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc),
            close=Decimal("22000"),
            opening_range_high=Decimal("21990"),
            opening_range_low=Decimal("22010"),
        )

    with pytest.raises(api.ORBReferenceError):
        api.ORBSignalSnapshot(
            symbol="NIFTY",
            timestamp=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc),
            close=22000.0,
            opening_range_high=Decimal("22010"),
            opening_range_low=Decimal("21990"),
        )


def test_orb_executable_simulation_preparation_fails_without_versioned_policy_ref():
    api = _orb_api()
    strategy = api.ORBReferenceStrategyV2()

    with pytest.raises(Exception):
        strategy.prepare_simulation(protective_policy_ref=None)
    with pytest.raises(Exception):
        strategy.prepare_simulation(protective_policy_ref="orb-protection")

    prepared = strategy.prepare_simulation(
        protective_policy_ref="TEST_ONLY/orb-protection@v1"
    )
    assert prepared.protective_policy_ref == "TEST_ONLY/orb-protection@v1"
    assert prepared.promotion_eligible is False
    assert prepared.evidence_scope == "TEST_ONLY"


def test_orb_research_policy_preparation_remains_non_promotable_in_phase4_default():
    api = _orb_api()
    strategy = api.ORBReferenceStrategyV2()

    prepared = strategy.prepare_simulation(
        protective_policy_ref="research/orb-protection@v1"
    )
    assert prepared.evidence_scope == "RESEARCH_ONLY"
    assert prepared.promotion_eligible is False
