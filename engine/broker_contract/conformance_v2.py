"""Side-effect-free conformance checks for AlgoFortis V2 broker ports."""

from __future__ import annotations

from engine.broker_contract.port_v2 import (
    BROKER_PORT_V2_CONTRACT,
    BrokerCredentialScope,
    BrokerMutationKind,
    BrokerPortDescriptor,
    BrokerPortV2Error,
)
from engine.orders.contracts_v2 import RunMode


_REQUIRED_METHODS = (
    "capabilities",
    "place",
    "cancel",
    "orders",
    "positions",
    "funds",
    "health",
)
_REQUIRED_CAPABILITIES = frozenset({"orders", "cancel", "positions", "funds", "health"})


def assert_broker_port_conformance(adapter: object, *, expected_mode: RunMode) -> None:
    """Validate broker-neutral shape without performing any mutation."""
    if not isinstance(expected_mode, RunMode):
        raise TypeError("expected_mode must be a RunMode")

    descriptor = getattr(adapter, "descriptor", None)
    if not isinstance(descriptor, BrokerPortDescriptor):
        raise BrokerPortV2Error("adapter must expose a BrokerPortDescriptor")
    if descriptor.contract_version != BROKER_PORT_V2_CONTRACT:
        raise BrokerPortV2Error("broker port contract version mismatch")
    if descriptor.run_mode is not expected_mode:
        raise BrokerPortV2Error(
            f"mode mismatch: expected {expected_mode.value}, got {descriptor.run_mode.value}"
        )

    for method_name in _REQUIRED_METHODS:
        if not callable(getattr(adapter, method_name, None)):
            raise BrokerPortV2Error(f"adapter missing required method: {method_name}")

    capabilities = adapter.capabilities()
    if not isinstance(capabilities, frozenset):
        raise BrokerPortV2Error("adapter capabilities must be a frozenset")
    if not _REQUIRED_CAPABILITIES.issubset(capabilities):
        missing = sorted(_REQUIRED_CAPABILITIES - capabilities)
        raise BrokerPortV2Error(f"adapter missing required capabilities: {missing}")

    if expected_mode in {RunMode.PAPER, RunMode.BACKTEST}:
        if descriptor.mutation_kind is not BrokerMutationKind.SIMULATED:
            raise BrokerPortV2Error(
                f"{expected_mode.value} conformance forbids real broker mutation"
            )
        if descriptor.credential_scope is not BrokerCredentialScope.NONE:
            raise BrokerPortV2Error(
                f"{expected_mode.value} conformance forbids real broker credentials"
            )


__all__ = ["assert_broker_port_conformance"]
