from __future__ import annotations

from decimal import Decimal
from importlib import import_module
import json

import pytest


def _contracts():
    try:
        return import_module("engine.strategy.contracts_v2")
    except ModuleNotFoundError:
        pytest.fail("engine.strategy.contracts_v2 is missing", pytrace=False)


def _state():
    try:
        return import_module("engine.strategy.state_v2")
    except ModuleNotFoundError:
        pytest.fail("engine.strategy.state_v2 is missing", pytrace=False)


def _manifest(*, reverse: bool = False, protective: bool = True):
    api = _contracts()
    lookback = api.ParameterSpec(
        kind=api.ParameterKind.INTEGER,
        required=True,
        minimum=Decimal("1"),
        maximum=Decimal("100"),
    )
    volume = api.ParameterSpec(
        kind=api.ParameterKind.DECIMAL,
        required=True,
        minimum=Decimal("0.1"),
        maximum=Decimal("10"),
    )
    schema = (
        {"volume_multiplier": volume, "lookback": lookback}
        if reverse
        else {"lookback": lookback, "volume_multiplier": volume}
    )
    dependencies = (
        {"data_contract": "phase3/v1", "engine": "v2"}
        if reverse
        else {"engine": "v2", "data_contract": "phase3/v1"}
    )
    return api.StrategyManifestV2(
        strategy_id="orb",
        strategy_version="2.0.0",
        parameter_schema=schema,
        required_data_kinds=("bars",),
        required_timeframes=("5m",),
        supported_instruments=("index", "index_option"),
        dependency_lock=dependencies,
        protective_policy_required=protective,
    )


def test_manifest_fingerprint_is_deterministic_across_mapping_insertion_order():
    first = _manifest(reverse=False)
    second = _manifest(reverse=True)

    assert first.fingerprint == second.fingerprint
    assert tuple(first.parameter_schema) == ("lookback", "volume_multiplier")
    assert tuple(first.dependency_lock) == ("data_contract", "engine")


def test_manifest_rejects_ambiguous_or_incomplete_contracts():
    api = _contracts()
    spec = api.ParameterSpec(kind=api.ParameterKind.INTEGER, required=True)

    with pytest.raises(api.StrategySDKError):
        api.StrategyManifestV2(
            strategy_id=" ",
            strategy_version="2.0.0",
            parameter_schema={"x": spec},
            required_data_kinds=("bars",),
            required_timeframes=("5m",),
            supported_instruments=("index",),
            dependency_lock={"engine": "v2"},
        )

    with pytest.raises(api.StrategySDKError):
        api.StrategyManifestV2(
            strategy_id="orb",
            strategy_version="2.0.0",
            parameter_schema={"x": spec},
            required_data_kinds=("bars",),
            required_timeframes=("5m", "5m"),
            supported_instruments=("index",),
            dependency_lock={"engine": "v2"},
        )

    with pytest.raises(api.StrategySDKError):
        api.StrategyManifestV2(
            strategy_id="orb",
            strategy_version="2.0.0",
            parameter_schema={"x": spec},
            required_data_kinds=("bars",),
            required_timeframes=("5m",),
            supported_instruments=("index",),
            dependency_lock={},
        )


def test_parameter_validation_is_fail_closed_and_decimal_safe():
    api = _contracts()
    manifest = _manifest()

    validated = manifest.validate_parameters(
        {"lookback": 35, "volume_multiplier": Decimal("1.2")}
    )
    assert validated["lookback"] == 35
    assert validated["volume_multiplier"] == Decimal("1.2")

    with pytest.raises(api.StrategySDKError):
        manifest.validate_parameters({"lookback": 35})
    with pytest.raises(api.StrategySDKError):
        manifest.validate_parameters(
            {"lookback": 0, "volume_multiplier": Decimal("1.2")}
        )
    with pytest.raises(api.StrategySDKError):
        manifest.validate_parameters(
            {"lookback": 35, "volume_multiplier": Decimal("1.2"), "surprise": 1}
        )
    with pytest.raises(api.StrategySDKError):
        manifest.validate_parameters(
            {"lookback": True, "volume_multiplier": Decimal("1.2")}
        )


def test_executable_readiness_requires_explicit_versioned_protective_policy_reference():
    api = _contracts()
    manifest = _manifest(protective=True)

    with pytest.raises(api.StrategySDKError):
        manifest.assert_executable_ready(None)
    with pytest.raises(api.StrategySDKError):
        manifest.assert_executable_ready("orb-protection")

    assert manifest.assert_executable_ready("orb-protection@v1") == "orb-protection@v1"


def test_strategy_state_round_trip_is_deterministic_and_manifest_bound():
    state_api = _state()
    manifest = _manifest()
    first = state_api.StrategyStateEnvelope.create(
        manifest=manifest,
        state={"opening_range_high": Decimal("22010.5"), "bars_seen": 3},
    )
    second = state_api.StrategyStateEnvelope.create(
        manifest=manifest,
        state={"bars_seen": 3, "opening_range_high": Decimal("22010.5")},
    )

    assert first.fingerprint == second.fingerprint
    serialized = first.to_json()
    restored = state_api.StrategyStateEnvelope.from_json(
        serialized, expected_manifest=manifest
    )
    assert restored.fingerprint == first.fingerprint
    assert restored.state["opening_range_high"] == Decimal("22010.5")
    assert restored.state["bars_seen"] == 3


def test_strategy_state_rejects_tampering_and_wrong_manifest_version():
    state_api = _state()
    api = _contracts()
    manifest = _manifest()
    envelope = state_api.StrategyStateEnvelope.create(
        manifest=manifest,
        state={"bars_seen": 3},
    )

    payload = json.loads(envelope.to_json())
    payload["state"]["bars_seen"] = 4
    tampered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with pytest.raises(state_api.StrategyStateError):
        state_api.StrategyStateEnvelope.from_json(tampered, expected_manifest=manifest)

    other = api.StrategyManifestV2(
        strategy_id="orb",
        strategy_version="2.0.1",
        parameter_schema=manifest.parameter_schema,
        required_data_kinds=manifest.required_data_kinds,
        required_timeframes=manifest.required_timeframes,
        supported_instruments=manifest.supported_instruments,
        dependency_lock=manifest.dependency_lock,
        protective_policy_required=True,
    )
    with pytest.raises(state_api.StrategyStateError):
        state_api.StrategyStateEnvelope.from_json(
            envelope.to_json(), expected_manifest=other
        )
