"""Phase 1 RED tests for AF2-ARC-009 immutable layered configuration."""

from decimal import Decimal

import pytest

from engine.core.configuration import (
    ConfigurationError,
    ConfigurationLayer,
    ConfigurationResolver,
)


LAYER_NAMES = ("system", "environment", "user", "strategy", "run")


def _validator(schema_version: str, values) -> None:
    assert schema_version.endswith("/v1")
    assert values is not None


def _resolver() -> ConfigurationResolver:
    return ConfigurationResolver({name: _validator for name in LAYER_NAMES})


def test_layer_resolution_uses_frozen_precedence_and_deep_merge() -> None:
    snapshot = _resolver().resolve(
        ConfigurationLayer("system", "system-config/v1", {"mode": "PAPER", "risk": {"max_daily_trades": 10, "max_loss": Decimal("0.02")}}),
        ConfigurationLayer("environment", "environment-config/v1", {"risk": {"max_daily_trades": 8}, "region": "local"}),
        ConfigurationLayer("user", "user-config/v1", {"risk": {"max_daily_trades": 6}}),
        ConfigurationLayer("strategy", "strategy-config/v1", {"strategy_id": "orb", "risk": {"max_daily_trades": 5}}),
        ConfigurationLayer("run", "run-config/v1", {"seed": 42, "risk": {"max_daily_trades": 4}}),
    )

    assert snapshot.values["mode"] == "PAPER"
    assert snapshot.values["region"] == "local"
    assert snapshot.values["strategy_id"] == "orb"
    assert snapshot.values["seed"] == 42
    assert snapshot.values["risk"]["max_daily_trades"] == 4
    assert snapshot.values["risk"]["max_loss"] == Decimal("0.02")
    assert snapshot.layer_versions == (
        ("system", "system-config/v1"),
        ("environment", "environment-config/v1"),
        ("user", "user-config/v1"),
        ("strategy", "strategy-config/v1"),
        ("run", "run-config/v1"),
    )


def test_snapshot_is_deeply_immutable() -> None:
    snapshot = _resolver().resolve(
        ConfigurationLayer("system", "system-config/v1", {"nested": {"items": [1, 2, 3]}}),
    )

    with pytest.raises(TypeError):
        snapshot.values["new"] = "nope"  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.values["nested"]["x"] = 1  # type: ignore[index]
    assert snapshot.values["nested"]["items"] == (1, 2, 3)


def test_snapshot_fingerprint_is_order_independent_and_replayable() -> None:
    first = _resolver().resolve(
        ConfigurationLayer("system", "system-config/v1", {"b": 2, "a": {"y": "2", "x": "1"}}),
        ConfigurationLayer("run", "run-config/v1", {"seed": 123}),
    )
    second = _resolver().resolve(
        ConfigurationLayer("system", "system-config/v1", {"a": {"x": "1", "y": "2"}, "b": 2}),
        ConfigurationLayer("run", "run-config/v1", {"seed": 123}),
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id.startswith("cfg_")


def test_layer_order_duplicate_and_missing_validator_fail_closed() -> None:
    resolver = _resolver()
    with pytest.raises(ConfigurationError, match="order"):
        resolver.resolve(
            ConfigurationLayer("run", "run-config/v1", {"seed": 1}),
            ConfigurationLayer("user", "user-config/v1", {"limit": 1}),
        )

    with pytest.raises(ConfigurationError, match="duplicate"):
        resolver.resolve(
            ConfigurationLayer("system", "system-config/v1", {"a": 1}),
            ConfigurationLayer("system", "system-config/v1", {"b": 2}),
        )

    missing = ConfigurationResolver({"system": _validator})
    with pytest.raises(ConfigurationError, match="validator"):
        missing.resolve(ConfigurationLayer("run", "run-config/v1", {"seed": 1}))


def test_schema_validator_failure_is_wrapped_fail_closed() -> None:
    def reject(_version: str, _values) -> None:
        raise ValueError("invalid owner policy")

    resolver = ConfigurationResolver({"system": reject})
    with pytest.raises(ConfigurationError, match="schema validation failed"):
        resolver.resolve(ConfigurationLayer("system", "system-config/v1", {"mode": "PAPER"}))


def test_raw_secret_fields_are_rejected_but_secret_refs_are_allowed() -> None:
    resolver = _resolver()
    with pytest.raises(ConfigurationError, match="secret"):
        resolver.resolve(ConfigurationLayer("system", "system-config/v1", {"broker": {"api_secret": "plaintext"}}))
    with pytest.raises(ConfigurationError, match="secret"):
        resolver.resolve(ConfigurationLayer("system", "system-config/v1", {"password": "plaintext"}))

    snapshot = resolver.resolve(
        ConfigurationLayer("system", "system-config/v1", {"broker": {"secret_ref": "dpapi://broker/main"}}),
    )
    assert snapshot.values["broker"]["secret_ref"] == "dpapi://broker/main"


def test_noncanonical_float_values_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match="float"):
        _resolver().resolve(ConfigurationLayer("system", "system-config/v1", {"risk": 0.02}))
