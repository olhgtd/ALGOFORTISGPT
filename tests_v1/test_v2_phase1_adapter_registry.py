"""Phase 1 RED tests for AF2-ARC-007/008 internal adapter registry."""

from __future__ import annotations

import pytest

from engine.core.adapter_registry import (
    AdapterKind,
    AdapterManifest,
    AdapterRegistration,
    AdapterRegistryError,
    InternalAdapterRegistry,
)


def _manifest(
    version: str,
    *,
    compatible_core: str = ">=2.0,<3.0",
    contract: str = "BrokerPort@2",
) -> AdapterManifest:
    return AdapterManifest(
        adapter_id="broker.paper",
        kind=AdapterKind.BROKER,
        version=version,
        contract=contract,
        capabilities=("orders", "positions", "funds"),
        permissions=("network:broker-api", "secret:broker-credentials"),
        compatible_core=compatible_core,
    )


def _registration(version: str, *, compatible_core: str = ">=2.0,<3.0", contract: str = "BrokerPort@2") -> AdapterRegistration:
    manifest = _manifest(version, compatible_core=compatible_core, contract=contract)
    return AdapterRegistration(manifest=manifest, factory=lambda: {"version": version})


def _registry(events: list) -> InternalAdapterRegistry:
    return InternalAdapterRegistry(
        core_version="2.0.0",
        supported_contracts={"BrokerPort": 2},
        audit_sink=events.append,
    )


def test_manifest_and_discovery_are_immutable_and_exact() -> None:
    events: list = []
    registry = _registry(events)
    registration = _registration("1.0.0")
    registry.register(registration)

    discovered = registry.discover(kind=AdapterKind.BROKER, capability="positions")

    assert discovered == (registration.manifest,)
    assert registration.manifest.capabilities == ("orders", "positions", "funds")
    assert registration.manifest.permissions == (
        "network:broker-api",
        "secret:broker-credentials",
    )
    assert registry.active_manifest("broker.paper") is None


def test_enable_requires_core_and_contract_compatibility() -> None:
    events: list = []
    incompatible_core = InternalAdapterRegistry(
        core_version="3.0.0",
        supported_contracts={"BrokerPort": 2},
        audit_sink=events.append,
    )
    incompatible_core.register(_registration("1.0.0"))
    with pytest.raises(AdapterRegistryError, match="core compatibility"):
        incompatible_core.enable("broker.paper", "1.0.0")

    incompatible_contract = InternalAdapterRegistry(
        core_version="2.0.0",
        supported_contracts={"BrokerPort": 1},
        audit_sink=events.append,
    )
    incompatible_contract.register(_registration("1.0.0"))
    with pytest.raises(AdapterRegistryError, match="contract"):
        incompatible_contract.enable("broker.paper", "1.0.0")


def test_enable_disable_and_rollback_are_audited_and_version_exact() -> None:
    events: list = []
    registry = _registry(events)
    registry.register(_registration("1.0.0"))
    registry.register(_registration("1.1.0"))

    first = registry.enable("broker.paper", "1.0.0")
    second = registry.enable("broker.paper", "1.1.0")
    rolled_back = registry.rollback("broker.paper")

    assert first.instance == {"version": "1.0.0"}
    assert second.instance == {"version": "1.1.0"}
    assert rolled_back.instance == {"version": "1.0.0"}
    assert registry.active_manifest("broker.paper").version == "1.0.0"

    registry.disable("broker.paper")
    assert registry.active_manifest("broker.paper") is None

    assert [event.action for event in events] == ["ENABLE", "ENABLE", "ROLLBACK", "DISABLE"]
    assert events[1].previous_version == "1.0.0"
    assert events[2].previous_version == "1.1.0"
    assert events[2].version == "1.0.0"


def test_activation_fails_closed_when_audit_sink_fails() -> None:
    def broken_audit(_event) -> None:
        raise OSError("audit unavailable")

    registry = InternalAdapterRegistry(
        core_version="2.0.0",
        supported_contracts={"BrokerPort": 2},
        audit_sink=broken_audit,
    )
    registry.register(_registration("1.0.0"))

    with pytest.raises(AdapterRegistryError, match="audit"):
        registry.enable("broker.paper", "1.0.0")
    assert registry.active_manifest("broker.paper") is None


def test_duplicate_or_unknown_exact_registration_fails_closed() -> None:
    events: list = []
    registry = _registry(events)
    registry.register(_registration("1.0.0"))

    with pytest.raises(AdapterRegistryError, match="duplicate"):
        registry.register(_registration("1.0.0"))
    with pytest.raises(AdapterRegistryError, match="unknown"):
        registry.enable("broker.paper", "9.9.9")
    with pytest.raises(AdapterRegistryError, match="rollback"):
        registry.rollback("broker.paper")


def test_manifest_rejects_duplicate_capabilities_permissions_and_bad_contract() -> None:
    with pytest.raises(AdapterRegistryError, match="capabilit"):
        AdapterManifest(
            adapter_id="broker.paper",
            kind=AdapterKind.BROKER,
            version="1.0.0",
            contract="BrokerPort@2",
            capabilities=("orders", "orders"),
            permissions=("network:broker-api",),
            compatible_core=">=2.0,<3.0",
        )

    with pytest.raises(AdapterRegistryError, match="permission"):
        AdapterManifest(
            adapter_id="broker.paper",
            kind=AdapterKind.BROKER,
            version="1.0.0",
            contract="BrokerPort@2",
            capabilities=("orders",),
            permissions=("network:broker-api", "network:broker-api"),
            compatible_core=">=2.0,<3.0",
        )

    with pytest.raises(AdapterRegistryError, match="contract"):
        _manifest("1.0.0", contract="not-versioned")
