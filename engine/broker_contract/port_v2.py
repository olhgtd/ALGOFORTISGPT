"""AlgoFortis V2 structural broker-mode firewall.

The boundary is deliberately broker-neutral.  It binds a process mode to an
adapter descriptor before any adapter operation is reachable.  Paper and
backtest processes can bind simulated/no-credential adapters only.  LIVE
mutation is intentionally unavailable in Phase 2 even if a real-broker shaped
adapter is supplied; the live boundary remains READ_ONLY/DISARMED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from engine.orders.contracts_v2 import ApprovedOrder, RunMode


BROKER_PORT_V2_CONTRACT = "BrokerPortV2@1"


class BrokerPortV2Error(RuntimeError):
    """Raised when broker-port composition would violate mode isolation."""


class BrokerMutationKind(str, Enum):
    SIMULATED = "SIMULATED"
    REAL_BROKER = "REAL_BROKER"


class BrokerCredentialScope(str, Enum):
    NONE = "NONE"
    REAL_BROKER = "REAL_BROKER"


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class BrokerPortDescriptor:
    adapter_id: str
    run_mode: RunMode
    mutation_kind: BrokerMutationKind
    credential_scope: BrokerCredentialScope
    contract_version: str = BROKER_PORT_V2_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _text(self.adapter_id, "adapter_id"))
        if not isinstance(self.run_mode, RunMode):
            raise TypeError("run_mode must be a RunMode")
        if not isinstance(self.mutation_kind, BrokerMutationKind):
            raise TypeError("mutation_kind must be a BrokerMutationKind")
        if not isinstance(self.credential_scope, BrokerCredentialScope):
            raise TypeError("credential_scope must be a BrokerCredentialScope")
        contract = _text(self.contract_version, "contract_version")
        if contract != BROKER_PORT_V2_CONTRACT:
            raise ValueError(f"contract_version must be {BROKER_PORT_V2_CONTRACT}")
        object.__setattr__(self, "contract_version", contract)


class BrokerPortAdapterV2(Protocol):
    descriptor: BrokerPortDescriptor

    def capabilities(self) -> frozenset[str]: ...
    def place(self, order: ApprovedOrder) -> object: ...
    def cancel(self, client_order_id: str) -> object: ...
    def orders(self) -> object: ...
    def positions(self) -> object: ...
    def funds(self) -> object: ...
    def health(self) -> object: ...


class BoundBrokerPort:
    """Mode-bound adapter façade with checks before every mutation call."""

    def __init__(
        self,
        *,
        process_mode: RunMode,
        adapter: BrokerPortAdapterV2,
        read_only: bool,
        disarmed: bool,
    ) -> None:
        self._process_mode = process_mode
        self._adapter = adapter
        self._read_only = read_only
        self._disarmed = disarmed

    @classmethod
    def bind(
        cls,
        *,
        process_mode: RunMode,
        adapter: BrokerPortAdapterV2,
        read_only: bool = True,
        disarmed: bool = True,
    ) -> "BoundBrokerPort":
        if not isinstance(process_mode, RunMode):
            raise TypeError("process_mode must be a RunMode")
        if not isinstance(read_only, bool) or not isinstance(disarmed, bool):
            raise TypeError("read_only and disarmed must be bool values")

        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(descriptor, BrokerPortDescriptor):
            raise BrokerPortV2Error("adapter must expose a BrokerPortDescriptor")

        if descriptor.run_mode is not process_mode:
            raise BrokerPortV2Error(
                f"mode mismatch: {process_mode.value} process cannot bind "
                f"{descriptor.run_mode.value} adapter {descriptor.adapter_id}"
            )

        if process_mode in {RunMode.PAPER, RunMode.BACKTEST}:
            if descriptor.mutation_kind is BrokerMutationKind.REAL_BROKER:
                raise BrokerPortV2Error(
                    f"{process_mode.value} process cannot bind a real broker mutation adapter"
                )
            if descriptor.credential_scope is not BrokerCredentialScope.NONE:
                raise BrokerPortV2Error(
                    f"{process_mode.value} process cannot bind real broker credential scope"
                )
            if descriptor.mutation_kind is not BrokerMutationKind.SIMULATED:
                raise BrokerPortV2Error(
                    f"{process_mode.value} process requires a simulated mutation adapter"
                )

        return cls(
            process_mode=process_mode,
            adapter=adapter,
            read_only=read_only,
            disarmed=disarmed,
        )

    @property
    def descriptor(self) -> BrokerPortDescriptor:
        return self._adapter.descriptor

    @property
    def process_mode(self) -> RunMode:
        return self._process_mode

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def disarmed(self) -> bool:
        return self._disarmed

    def capabilities(self) -> frozenset[str]:
        result = self._adapter.capabilities()
        if not isinstance(result, frozenset) or not all(
            isinstance(item, str) and item for item in result
        ):
            raise BrokerPortV2Error("adapter capabilities must be a frozenset of non-empty strings")
        return result

    def place(self, order: ApprovedOrder) -> object:
        if not isinstance(order, ApprovedOrder):
            raise TypeError("order must be an ApprovedOrder")
        if order.run_mode is not self._process_mode:
            raise BrokerPortV2Error(
                f"ApprovedOrder run_mode {order.run_mode.value} does not match "
                f"bound process run_mode {self._process_mode.value}"
            )
        self._require_mutation_allowed("place")
        return self._adapter.place(order)

    def cancel(self, client_order_id: str) -> object:
        identity = _text(client_order_id, "client_order_id")
        self._require_mutation_allowed("cancel")
        return self._adapter.cancel(identity)

    def orders(self) -> object:
        return self._adapter.orders()

    def positions(self) -> object:
        return self._adapter.positions()

    def funds(self) -> object:
        return self._adapter.funds()

    def health(self) -> object:
        return self._adapter.health()

    def _require_mutation_allowed(self, operation: str) -> None:
        if self._process_mode is RunMode.LIVE:
            # Phase 2 is qualification-only.  Even a caller that passes False
            # flags cannot turn this module into a live execution path.
            if self._read_only or self._disarmed:
                raise BrokerPortV2Error(
                    f"LIVE mutation {operation} blocked by READ_ONLY/DISARMED safety overlay"
                )
            raise BrokerPortV2Error(
                "LIVE real-broker mutation is unavailable in Phase 2; "
                "READ_ONLY/DISARMED qualification only"
            )
        if self.descriptor.mutation_kind is not BrokerMutationKind.SIMULATED:
            raise BrokerPortV2Error(
                f"{self._process_mode.value} mutation requires a simulated adapter"
            )


__all__ = [
    "BROKER_PORT_V2_CONTRACT",
    "BrokerPortV2Error",
    "BrokerMutationKind",
    "BrokerCredentialScope",
    "BrokerPortDescriptor",
    "BrokerPortAdapterV2",
    "BoundBrokerPort",
]
