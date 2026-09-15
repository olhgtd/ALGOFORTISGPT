"""Trusted, immutable registration of strategy-owned protective policies.

This module deliberately knows no concrete strategy package and contains no
protective-price economics.  Application composition supplies registrations;
configuration resolves only exact registered identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping

from engine.protective.plan import ProtectivePlanPolicy


class ProtectivePolicyRegistryError(ValueError):
    """Raised for invalid registrations or failed exact policy resolution."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtectivePolicyRegistryError(f"{field} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, order=True)
class ProtectivePolicyRegistrationKey:
    """Exact owner and semantic selector for one trusted policy factory."""

    strategy_id: str
    strategy_version: str
    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        for field in ("strategy_id", "strategy_version", "policy_id", "policy_version"):
            object.__setattr__(self, field, _text(getattr(self, field), field))


ProtectivePolicyFactory = Callable[[Mapping[str, object]], ProtectivePlanPolicy]


@dataclass(frozen=True)
class ProtectivePolicyRegistration:
    """One trusted exact-key factory supplied by application composition."""

    key: ProtectivePolicyRegistrationKey
    factory: ProtectivePolicyFactory

    def __post_init__(self) -> None:
        if not isinstance(self.key, ProtectivePolicyRegistrationKey):
            raise TypeError("key must be a ProtectivePolicyRegistrationKey")
        if not callable(self.factory):
            raise TypeError("factory must be callable")


class ProtectivePolicyRegistry:
    """Immutable exact-match registry for strategy-owned policy factories."""

    def __init__(self, registrations: tuple[ProtectivePolicyRegistration, ...] = ()) -> None:
        entries: dict[ProtectivePolicyRegistrationKey, ProtectivePolicyRegistration] = {}
        for registration in registrations:
            if not isinstance(registration, ProtectivePolicyRegistration):
                raise TypeError("registrations must contain ProtectivePolicyRegistration values")
            if registration.key in entries:
                raise ProtectivePolicyRegistryError(
                    f"duplicate protective policy registration: {registration.key!r}"
                )
            entries[registration.key] = registration
        self._registrations = MappingProxyType({key: entries[key] for key in sorted(entries)})

    @property
    def registrations(self) -> Mapping[ProtectivePolicyRegistrationKey, ProtectivePolicyRegistration]:
        return self._registrations

    def resolve(
        self,
        key: ProtectivePolicyRegistrationKey,
        parameters: Mapping[str, object],
    ) -> ProtectivePlanPolicy:
        if not isinstance(key, ProtectivePolicyRegistrationKey):
            raise TypeError("key must be a ProtectivePolicyRegistrationKey")
        if not isinstance(parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        registration = self._registrations.get(key)
        if registration is None:
            same_owner_policy = any(
                item.strategy_id == key.strategy_id
                and item.strategy_version == key.strategy_version
                and item.policy_id == key.policy_id
                for item in self._registrations
            )
            same_policy_elsewhere = any(
                item.policy_id == key.policy_id and item.policy_version == key.policy_version
                for item in self._registrations
            )
            if same_owner_policy:
                raise ProtectivePolicyRegistryError(
                    f"unsupported protective policy version {key.policy_version!r} for "
                    f"{key.strategy_id}/{key.strategy_version} policy {key.policy_id!r}"
                )
            if same_policy_elsewhere:
                raise ProtectivePolicyRegistryError(
                    f"protective policy {key.policy_id!r}/{key.policy_version!r} is not registered for "
                    f"strategy owner {key.strategy_id}/{key.strategy_version}"
                )
            raise ProtectivePolicyRegistryError(
                f"unknown protective policy {key.policy_id!r}/{key.policy_version!r} for "
                f"strategy owner {key.strategy_id}/{key.strategy_version}"
            )
        try:
            policy = registration.factory(parameters)
        except Exception as error:
            raise ProtectivePolicyRegistryError(
                f"protective policy factory rejected configuration for "
                f"{key.strategy_id}/{key.strategy_version} {key.policy_id!r}/{key.policy_version!r}"
            ) from error
        if not isinstance(policy, ProtectivePlanPolicy):
            raise ProtectivePolicyRegistryError("protective policy factory must return a ProtectivePlanPolicy")
        try:
            identity = policy.policy_identity
        except Exception as error:
            raise ProtectivePolicyRegistryError("protective policy must provide a readable policy_identity") from error
        if not isinstance(identity, str) or not identity.strip():
            raise ProtectivePolicyRegistryError("protective policy policy_identity must be a non-empty string")
        return policy
